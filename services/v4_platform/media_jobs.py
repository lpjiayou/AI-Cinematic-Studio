"""V4 single-episode media queue, worker lifecycle and local evidence adapter."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
from threading import Event, RLock, Thread
from typing import Any, Callable, Mapping, Protocol

from .artifact_recovery import ArtifactRecoveryStore, ArtifactRecoveryStoreError


LEGACY_JOB_SCHEMA_VERSION = "v4.media-job.v1"
JOB_SCHEMA_VERSION = "v4.media-job.v2"
ARTIFACT_SCHEMA_VERSION = "v4.media-artifact-handoff.v1"
ARTIFACT_COMMIT_INTENT_SCHEMA_VERSION = "v4.media-artifact-commit-intent.v1"
MEDIA_BATCH_SCHEMA_VERSION = "v4.media-batch.v1"
_RECOVERY_WORKER_REF = "v4-media-artifact-recovery"
M11_VIDEO_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-video-request.v1"
M11_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION = (
    "v5.k2-real-shot-video-request.v2"
)
M11_VIDEO_CAPABILITY = "self-hosted-wan22-image-to-video-v1"
M11_VIDEO_PROVENANCE = "SELF_HOSTED_AI_GENERATED"


_PROBE_MEDIA_CACHE: dict[tuple[str, int], dict[str, Any]] = {}
_PROBE_MEDIA_CACHE_LOCK = RLock()


class MediaJobError(RuntimeError):
    code = "worker_unavailable"


class MediaJobConflictError(MediaJobError):
    code = "idempotency_conflict"


class MediaJobStateError(MediaJobError):
    code = "invalid_state_transition"


class MediaAdapterUnavailableError(MediaJobError):
    code = "worker_unavailable"


class ArtifactVerificationError(MediaJobError):
    code = "artifact_verification_failed"


class MediaJobRepository(Protocol):
    def create(self, job: Mapping[str, Any]) -> tuple[dict[str, Any], bool]: ...
    def reserve_batch(
        self, batch: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]: ...
    def get(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any] | None: ...
    def list(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]: ...
    def save(self, job: Mapping[str, Any], expected_revision: int) -> dict[str, Any]: ...


class MediaGenerationAdapter(Protocol):
    adapter_identity: str
    provenance: str

    def generate(
        self, request: Mapping[str, Any], candidate_path: Path
    ) -> Path | "MediaAdapterResult": ...


@dataclass(frozen=True, slots=True)
class MediaAdapterResult:
    """Provider-neutral V4 candidate plus safe execution evidence.

    Provider credentials and private endpoints are deliberately absent.  The result
    is still untrusted: ``MediaJobCoordinator`` probes the file independently before
    it can become a V4 artifact handoff.
    """

    path: Path
    execution: Mapping[str, Any]


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


def _validate_batch(batch: Mapping[str, Any]) -> None:
    members = batch.get("members")
    if (
        set(batch)
        != {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "batchIdempotencyKey",
            "members",
            "payloadDigest",
        }
        or batch.get("schemaVersion") != MEDIA_BATCH_SCHEMA_VERSION
        or not isinstance(batch.get("workspaceRef"), str)
        or not batch["workspaceRef"]
        or not isinstance(batch.get("productionRunRef"), str)
        or not batch["productionRunRef"]
        or not isinstance(batch.get("batchIdempotencyKey"), str)
        or not batch["batchIdempotencyKey"]
        or not isinstance(members, list)
        or not members
        or _digest(
            {key: value for key, value in batch.items() if key != "payloadDigest"}
        )
        != batch.get("payloadDigest")
    ):
        raise MediaJobError("media batch reservation is invalid")
    expected_positions = list(range(1, len(members) + 1))
    positions: list[int] = []
    refs: list[str] = []
    for member in members:
        if (
            not isinstance(member, Mapping)
            or set(member)
            != {
                "position",
                "generationRequestRef",
                "generationRequestDigest",
            }
            or isinstance(member.get("position"), bool)
            or not isinstance(member.get("position"), int)
            or not isinstance(member.get("generationRequestRef"), str)
            or not member["generationRequestRef"]
            or not _hex_digest(member.get("generationRequestDigest"))
        ):
            raise MediaJobError("media batch member is invalid")
        positions.append(member["position"])
        refs.append(member["generationRequestRef"])
    if positions != expected_positions or len(set(refs)) != len(refs):
        raise MediaJobError("media batch members are not one ordered unique set")


def _hex_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _m11_rendered_prompt_size(prompt_spec: Mapping[str, Any]) -> int:
    camera = prompt_spec["cameraInstruction"]
    camera_text = (
        f"{camera['shotSize'].strip().replace('-', ' ')}, "
        f"{camera['angle'].strip().replace('-', ' ')}, "
        f"{camera['lensMm']:g}mm lens, "
        f"{camera['movement'].strip().replace('-', ' ')}; "
        f"{camera['intent'].strip().replace('-', ' ')}"
    )
    continuity = "; ".join(
        item.strip() for item in prompt_spec["continuityConstraints"]
    )
    prompt = (
        f"{prompt_spec['action'].strip()} Perform one restrained, continuous "
        f"story beat only. Camera: {camera_text}. Begin from the exact supplied "
        "first frame. Keep both people in their established screen positions and "
        "preserve their roles. Use natural micro-expressions and small controlled "
        "body or hand movement only. Preserve exact face identity, age, hairstyle, "
        "body proportions, wardrobe, lighting, environment, framing and all visible "
        "physical props. Do not introduce any physical prop that is absent from the "
        "first frame; only diegetic light or projection changes explicitly required "
        "by the action may appear. Do not remove, duplicate, exchange or transform a "
        f"prop. Continuity: {continuity}. No cut, role swap, abrupt pose change or "
        "unmotivated camera motion."
    )
    return len(prompt)


def _validate_m11_video_request(request: Mapping[str, Any]) -> None:
    base_fields = {
        "schemaVersion", "workspaceRef", "productionRunRef",
        "generationRequestRef", "generationRequestVersionRef", "version",
        "ordinal", "mediaKind", "mediaType", "creativeShotRef",
        "creativeShotVersionRef", "creativeShotDigest",
        "executableShotGraphVersionRef", "executableShotGraphDigest",
        "sourceImageAssetRef", "sourceImageAssetVersionRef",
        "sourceImageAssetVersionDigest", "sourceImageContentDigest",
        "sourceImageMediaType", "sourceImageProbe", "startImageBindingState",
        "promptSpec", "parameters", "adapterCapability", "executionMode",
        "executionAuthorizationState", "requestedProvenance", "rightsState",
        "providerPolicyState", "budgetAuthorityState", "selectionRequired",
        "publicationAllowed", "createdBy", "createdAt", "payloadDigest",
    }
    successor_fields = {
        "realVideoRevisionRef",
        "sourceRealVideoPlanRef",
        "sourceRealVideoPlanDigest",
        "supersedesGenerationRequestVersionRef",
        "supersedesGenerationRequestDigest",
    }
    schema_version = request.get("schemaVersion")
    is_successor = schema_version == M11_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION
    fields = base_fields | (successor_fields if is_successor else set())
    parameters = request.get("parameters")
    prompt_spec = request.get("promptSpec")
    source_probe = request.get("sourceImageProbe")
    camera_instruction = (
        prompt_spec.get("cameraInstruction")
        if isinstance(prompt_spec, Mapping)
        else None
    )
    if (
        set(request) != fields
        or schema_version
        not in {
            M11_VIDEO_REQUEST_SCHEMA_VERSION,
            M11_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION,
        }
        or _digest({k: v for k, v in request.items() if k != "payloadDigest"})
        != request.get("payloadDigest")
        or (
            schema_version == M11_VIDEO_REQUEST_SCHEMA_VERSION
            and (
                isinstance(request.get("version"), bool)
                or request.get("version") != 1
            )
        )
        or (
            is_successor
            and (
                isinstance(request.get("version"), bool)
                or not isinstance(request.get("version"), int)
                or request["version"] < 2
                or not all(
                    isinstance(request.get(field), str) and request[field]
                    for field in (
                        "realVideoRevisionRef",
                        "sourceRealVideoPlanRef",
                        "supersedesGenerationRequestVersionRef",
                    )
                )
                or request.get("generationRequestVersionRef")
                == request.get("supersedesGenerationRequestVersionRef")
                or not all(
                    _hex_digest(request.get(field))
                    for field in (
                        "sourceRealVideoPlanDigest",
                        "supersedesGenerationRequestDigest",
                    )
                )
            )
        )
        or isinstance(request.get("ordinal"), bool)
        or request.get("ordinal") not in {1, 2, 3, 4}
        or request.get("mediaKind") != "video"
        or request.get("mediaType") != "video/mp4"
        or request.get("sourceImageMediaType") != "image/png"
        or request.get("startImageBindingState")
        != "EXACT_ASSET_VERSION_BOUND"
        or request.get("adapterCapability") != M11_VIDEO_CAPABILITY
        or request.get("executionMode") != "INTERNAL_SELF_HOSTED"
        or request.get("executionAuthorizationState")
        != "NOT_DISPATCHED_BY_PLAN"
        or request.get("requestedProvenance") != M11_VIDEO_PROVENANCE
        or request.get("rightsState") != "NOT_REQUIRED_INTERNAL"
        or request.get("providerPolicyState")
        != "NOT_REQUIRED_SELF_HOSTED"
        or request.get("budgetAuthorityState") != "NOT_REQUIRED_INTERNAL"
        or request.get("selectionRequired") is not True
        or request.get("publicationAllowed") is not False
        or not all(
            isinstance(request.get(field), str) and request[field]
            for field in (
                "workspaceRef", "productionRunRef", "generationRequestRef",
                "generationRequestVersionRef", "creativeShotRef",
                "creativeShotVersionRef", "executableShotGraphVersionRef",
                "sourceImageAssetRef", "sourceImageAssetVersionRef",
                "createdBy", "createdAt",
            )
        )
        or not all(
            _hex_digest(request.get(field))
            for field in (
                "payloadDigest", "creativeShotDigest",
                "executableShotGraphDigest", "sourceImageAssetVersionDigest",
                "sourceImageContentDigest",
            )
        )
        or not isinstance(source_probe, Mapping)
        or set(source_probe) != {"width", "height", "format"}
        or isinstance(source_probe.get("width"), bool)
        or not isinstance(source_probe.get("width"), int)
        or source_probe["width"] < 32
        or isinstance(source_probe.get("height"), bool)
        or not isinstance(source_probe.get("height"), int)
        or source_probe["height"] < 32
        or source_probe.get("format") != "png"
        or not isinstance(prompt_spec, Mapping)
        or set(prompt_spec)
        != {"cameraInstruction", "action", "continuityConstraints"}
        or not isinstance(camera_instruction, Mapping)
        or set(camera_instruction)
        != {"shotSize", "movement", "angle", "lensMm", "intent"}
        or any(
            not isinstance(camera_instruction.get(field), str)
            or not camera_instruction[field].strip()
            or len(camera_instruction[field]) > 160
            for field in ("shotSize", "movement", "angle", "intent")
        )
        or isinstance(camera_instruction.get("lensMm"), bool)
        or not isinstance(camera_instruction.get("lensMm"), (int, float))
        or camera_instruction["lensMm"] < 8
        or camera_instruction["lensMm"] > 200
        or not isfinite(float(camera_instruction["lensMm"]))
        or not isinstance(prompt_spec.get("action"), str)
        or not prompt_spec["action"].strip()
        or len(prompt_spec["action"]) > 1000
        or not isinstance(prompt_spec.get("continuityConstraints"), list)
        or not prompt_spec["continuityConstraints"]
        or len(prompt_spec["continuityConstraints"]) > 24
        or not all(
            isinstance(item, str) and item.strip() and len(item) <= 300
            for item in prompt_spec["continuityConstraints"]
        )
        or _m11_rendered_prompt_size(prompt_spec) > 4_000
        or not isinstance(parameters, Mapping)
        or set(parameters)
        != {
            "durationFrames", "frameRate", "width", "height", "steps",
            "cfg", "samplerName", "scheduler", "modelShift", "seed",
            "negativePrompt",
        }
        or isinstance(parameters.get("durationFrames"), bool)
        or parameters.get("durationFrames") not in {168, 192}
        or parameters.get("frameRate") != 24
        or parameters.get("width") != 640
        or parameters.get("height") != 352
        or parameters.get("steps") != 20
        or parameters.get("cfg") != 5.0
        or parameters.get("samplerName") != "uni_pc"
        or parameters.get("scheduler") != "simple"
        or parameters.get("modelShift") != 8.0
        or isinstance(parameters.get("seed"), bool)
        or not isinstance(parameters.get("seed"), int)
        or parameters["seed"] < 0
        or not isinstance(parameters.get("negativePrompt"), str)
        or not parameters["negativePrompt"].strip()
        or len(parameters["negativePrompt"]) > 2000
    ):
        raise MediaJobError("invalid exact M11 video generation request")


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            os.close(descriptor)
            raise ArtifactVerificationError("artifact is not one exact regular file")
        with os.fdopen(descriptor, "rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
            closed_over = os.fstat(source.fileno())
        if (
            closed_over.st_dev != opened.st_dev
            or closed_over.st_ino != opened.st_ino
            or closed_over.st_size != opened.st_size
            or size != opened.st_size
        ):
            raise ArtifactVerificationError("artifact changed while being hashed")
    except ArtifactVerificationError:
        raise
    except OSError as exc:
        raise ArtifactVerificationError("artifact hashing failed") from exc
    return digest.hexdigest(), size


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise MediaJobError("invalid clock value") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_request(request: Mapping[str, Any]) -> None:
    if (
        isinstance(request, Mapping)
        and request.get("schemaVersion")
        in {
            M11_VIDEO_REQUEST_SCHEMA_VERSION,
            M11_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION,
        }
    ):
        _validate_m11_video_request(request)
        return
    required = {
        "workspaceRef", "productionRunRef", "generationRequestRef",
        "generationRequestVersionRef", "payloadDigest", "assetRequirementRef",
        "creativeShotRef", "creativeShotVersionRef", "mediaKind", "mediaType",
        "adapterCapability", "parameters", "state", "requestedProvenance",
        "publicationAllowed",
    }
    if not isinstance(request, Mapping):
        raise MediaJobError("invalid V5 generation request")
    provenance = request.get("requestedProvenance")
    if (
        not required.issubset(request)
        or request.get("state") != "READY_FOR_DISPATCH"
        or request.get("publicationAllowed") is not False
        or request.get("mediaKind") not in {"video", "audio"}
        or not isinstance(request.get("parameters"), Mapping)
        or _digest({k: v for k, v in request.items() if k != "payloadDigest"})
        != request.get("payloadDigest")
    ):
        raise MediaJobError("invalid V5 generation request")
    if provenance == "LOCAL_EVIDENCE":
        return
    if provenance != "LIVE_PROVIDER":
        raise MediaJobError("generation request provenance is unsupported")
    provider = request.get("providerSelection")
    legacy_provider_fields = {
        "providerId", "modelId", "region", "endpointClass",
        "providerCapabilityRef", "providerExecutionPolicyRef",
        "providerExecutionPolicyDigest", "rightsManifestRef",
        "rightsManifestDigest", "productionPolicyRef",
        "productionPolicyDigest", "credentialSourceRef",
        "usageTermsRef", "budgetAuthorityRef", "runtimeAttestationRef",
        "runtimeAttestationDigest", "costCurrency", "maxCostMinor",
        "timeoutSeconds",
    }
    internal_provider_fields = {
        "executionMode", "executionGrantRef", "executionGrantDigest",
        "providerId", "modelId", "region", "endpointClass",
        "runtimeAttestationRef", "runtimeAttestationDigest",
        "costCurrency", "maxCostMinor", "timeoutSeconds",
    }
    provider_fields = set(provider) if isinstance(provider, Mapping) else set()
    if provider_fields == legacy_provider_fields:
        digest_fields = {
            "providerExecutionPolicyDigest", "rightsManifestDigest",
            "productionPolicyDigest", "runtimeAttestationDigest",
        }
    elif (
        provider_fields == internal_provider_fields
        and provider.get("executionMode") == "INTERNAL_SELF_HOSTED"
    ):
        digest_fields = {
            "executionGrantDigest", "runtimeAttestationDigest",
        }
    else:
        raise MediaJobError("live provider request authority is incomplete")
    if (
        request.get("mediaKind") != "video"
        or request.get("adapterCapability") != "comfyui-wan22-ti2v-v1"
        or not isinstance(provider, Mapping)
        or not all(
            isinstance(provider.get(field), str) and provider[field]
            for field in provider
            if field not in digest_fields
            and field not in {"maxCostMinor", "timeoutSeconds"}
        )
        or any(
            not isinstance(provider.get(field), str)
            or len(provider[field]) != 64
            or any(character not in "0123456789abcdef" for character in provider[field])
            for field in digest_fields
        )
        or not isinstance(provider.get("costCurrency"), str)
        or len(provider["costCurrency"]) != 3
        or provider["costCurrency"] != provider["costCurrency"].upper()
        or isinstance(provider.get("maxCostMinor"), bool)
        or not isinstance(provider.get("maxCostMinor"), int)
        or provider["maxCostMinor"] < 0
        or isinstance(provider.get("timeoutSeconds"), bool)
        or not isinstance(provider.get("timeoutSeconds"), int)
        or provider["timeoutSeconds"] < 1
    ):
        raise MediaJobError("live provider request authority is incomplete")
    parameters = request["parameters"]
    live_fields = {
        "durationFrames", "frameRate", "width", "height", "prompt",
        "negativePrompt", "seed", "steps", "cfg", "samplerName",
        "scheduler", "modelShift",
    }
    if (
        set(parameters) != live_fields
        or not isinstance(parameters.get("prompt"), str)
        or not parameters["prompt"].strip()
        or len(parameters["prompt"]) > 4000
        or not isinstance(parameters.get("negativePrompt"), str)
        or len(parameters["negativePrompt"]) > 4000
        or any(
            isinstance(parameters.get(field), bool)
            or not isinstance(parameters.get(field), int)
            for field in (
                "durationFrames", "frameRate", "width", "height", "seed", "steps"
            )
        )
        or parameters["durationFrames"] < 1
        or parameters["durationFrames"] % 4 != 1
        or parameters["frameRate"] < 1
        or parameters["width"] < 32
        or parameters["width"] % 32 != 0
        or parameters["height"] < 32
        or parameters["height"] % 32 != 0
        or parameters["steps"] < 1
        or not isinstance(parameters.get("cfg"), (int, float))
        or isinstance(parameters.get("cfg"), bool)
        or not isinstance(parameters.get("modelShift"), (int, float))
        or isinstance(parameters.get("modelShift"), bool)
        or parameters.get("samplerName") not in {"uni_pc", "uni_pc_bh2"}
        or parameters.get("scheduler") != "simple"
    ):
        raise MediaJobError("live provider request parameters are invalid")


def _validate_live_execution(
    execution: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    required = {
        "providerId", "modelId", "region", "endpointClass",
        "providerRequestRef", "latencyMs", "costCurrency", "costMinor",
        "seed", "executionDevice", "gpuUsed", "runtimeFacts",
        "runtimeFactsDigest",
    }
    provider = request["providerSelection"]
    runtime_facts = execution.get("runtimeFacts") if isinstance(
        execution, Mapping
    ) else None
    if (
        not isinstance(execution, Mapping)
        or set(execution) != required
        or any(
            execution.get(field) != provider.get(field)
            for field in ("providerId", "modelId", "region", "endpointClass")
        )
        or not isinstance(execution.get("providerRequestRef"), str)
        or not execution["providerRequestRef"]
        or isinstance(execution.get("latencyMs"), bool)
        or not isinstance(execution.get("latencyMs"), int)
        or execution["latencyMs"] < 0
        or not isinstance(execution.get("costCurrency"), str)
        or len(execution["costCurrency"]) != 3
        or execution["costCurrency"] != execution["costCurrency"].upper()
        or isinstance(execution.get("costMinor"), bool)
        or not isinstance(execution.get("costMinor"), int)
        or execution["costMinor"] < 0
        or execution.get("seed") != request["parameters"]["seed"]
        or not isinstance(execution.get("executionDevice"), str)
        or not execution["executionDevice"]
        or execution.get("gpuUsed") is not True
        or not isinstance(runtime_facts, Mapping)
        or execution.get("runtimeFactsDigest") != _digest(runtime_facts)
        or any(
            runtime_facts.get(field) != provider.get(field)
            for field in ("providerId", "modelId", "region", "endpointClass")
        )
        or runtime_facts.get("runtimeAttestationRef")
        != provider.get("runtimeAttestationRef")
        or runtime_facts.get("runtimeAttestationDigest")
        != provider.get("runtimeAttestationDigest")
        or runtime_facts.get("deviceType") != "cuda"
        or runtime_facts.get("deviceName") != execution.get("executionDevice")
    ):
        raise ArtifactVerificationError("live provider execution evidence is invalid")
    return deepcopy(dict(execution))


def _validate_m11_execution(
    execution: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    required = {
        "providerId", "modelId", "region", "endpointClass",
        "providerRequestRef", "latencyMs", "costCurrency", "costMinor",
        "seed", "executionDevice", "gpuUsed", "runtimeFacts",
        "runtimeFactsDigest", "sourceImageContentDigest", "workflowDigest",
        "latentFrameCount", "outputFrameCount", "postprocessIdentity",
    }
    runtime_facts = execution.get("runtimeFacts") if isinstance(
        execution, Mapping
    ) else None
    if (
        not isinstance(execution, Mapping)
        or set(execution) != required
        or not all(
            isinstance(execution.get(field), str) and execution[field]
            for field in (
                "providerId", "modelId", "region", "endpointClass",
                "providerRequestRef", "executionDevice", "costCurrency",
                "postprocessIdentity",
            )
        )
        or len(execution["costCurrency"]) != 3
        or execution["costCurrency"] != execution["costCurrency"].upper()
        or isinstance(execution.get("latencyMs"), bool)
        or not isinstance(execution.get("latencyMs"), int)
        or execution["latencyMs"] < 0
        or isinstance(execution.get("costMinor"), bool)
        or not isinstance(execution.get("costMinor"), int)
        or execution["costMinor"] < 0
        or execution.get("seed") != request["parameters"]["seed"]
        or execution.get("gpuUsed") is not True
        or execution.get("sourceImageContentDigest")
        != request.get("sourceImageContentDigest")
        or not _hex_digest(execution.get("workflowDigest"))
        or execution.get("latentFrameCount")
        != request["parameters"]["durationFrames"] + 1
        or execution.get("outputFrameCount")
        != request["parameters"]["durationFrames"]
        or execution.get("postprocessIdentity")
        != "v4.ffmpeg-exact-frame-trim.v1"
        or not isinstance(runtime_facts, Mapping)
        or execution.get("runtimeFactsDigest") != _digest(runtime_facts)
        or any(
            runtime_facts.get(field) != execution.get(field)
            for field in ("providerId", "modelId", "region", "endpointClass")
        )
        or runtime_facts.get("deviceType") != "cuda"
        or runtime_facts.get("deviceName") != execution.get("executionDevice")
        or runtime_facts.get("startImageCapability")
        != "LOAD_IMAGE_TO_WAN_START_IMAGE_VERIFIED"
    ):
        raise ArtifactVerificationError(
            "M11 self-hosted execution evidence is invalid"
        )
    return deepcopy(dict(execution))


def _validate_job_state_shape(job: Mapping[str, Any]) -> None:
    state = job["state"]
    attempts = job["attempts"]
    latest = attempts[-1] if attempts else None
    lease = job.get("lease")
    artifact = job.get("artifact")
    intent = job.get("artifactCommitIntent")

    if any(attempt.get("state") != "FAILED" for attempt in attempts[:-1]):
        raise MediaJobError("historical media job attempts are not terminal failures")
    allowed_latest_states = {
        "QUEUED": {None, "FAILED"},
        "LEASED": {None, "FAILED"},
        "RUNNING": {"RUNNING"},
        "SUCCEEDED": {"SUCCEEDED"},
        "FAILED": {"FAILED"},
        "RETRYING": {None, "FAILED"},
        "CANCELLED": {None, "FAILED", "CANCELLED"},
    }
    if (latest.get("state") if isinstance(latest, Mapping) else None) not in (
        allowed_latest_states[state]
    ):
        raise MediaJobError("media job state and attempt history disagree")

    if state in {"LEASED", "RUNNING"}:
        expected_lease_fields = {"workerRef", "leasedAt", "expiresAt"}
        if job["schemaVersion"] == JOB_SCHEMA_VERSION:
            expected_lease_fields.add("leaseToken")
        if (
            not isinstance(lease, Mapping)
            or set(lease) != expected_lease_fields
            or any(
                not isinstance(lease.get(field), str) or not lease[field]
                for field in expected_lease_fields
            )
        ):
            raise MediaJobError("media job lease is invalid")
        if _parse_time(lease["expiresAt"]) <= _parse_time(lease["leasedAt"]):
            raise MediaJobError("media job lease interval is invalid")
    elif lease is not None:
        raise MediaJobError("terminal or queued media job cannot retain a lease")

    if state == "RUNNING":
        if not isinstance(latest, Mapping) or latest.get("state") != "RUNNING":
            raise MediaJobError("running media job has no running attempt")
    elif isinstance(intent, Mapping) and not (
        state in {"FAILED", "CANCELLED"}
        and isinstance(latest, Mapping)
        and latest.get("state")
        == ("FAILED" if state == "FAILED" else "CANCELLED")
    ):
        raise MediaJobError(
            "artifact commit intent is not a valid pending cleanup claim"
        )

    if state == "SUCCEEDED":
        if (
            not isinstance(latest, Mapping)
            or latest.get("state") != "SUCCEEDED"
            or not isinstance(artifact, Mapping)
            or artifact.get("schemaVersion") != ARTIFACT_SCHEMA_VERSION
            or artifact.get("workspaceRef") != job.get("workspaceRef")
            or artifact.get("productionRunRef") != job.get("productionRunRef")
            or artifact.get("jobRef") != job.get("jobRef")
            or artifact.get("attemptRef") != latest.get("attemptRef")
            or artifact.get("generationRequestRef")
            != job.get("request", {}).get("generationRequestRef")
            or artifact.get("generationRequestDigest") != job.get("requestDigest")
            or not isinstance(artifact.get("storageKey"), str)
            or not artifact["storageKey"]
            or not isinstance(artifact.get("internalPath"), str)
            or not artifact["internalPath"]
            or not _hex_digest(artifact.get("sha256"))
            or isinstance(artifact.get("byteSize"), bool)
            or not isinstance(artifact.get("byteSize"), int)
            or artifact["byteSize"] < 1
            or artifact.get("publicationAllowed") is not False
            or latest.get("artifactSha256") != artifact.get("sha256")
        ):
            raise MediaJobError("succeeded media job artifact is invalid")
    elif artifact is not None:
        raise MediaJobError("non-succeeded media job cannot retain an artifact")


def _validate_job(job: Mapping[str, Any]) -> None:
    if (
        job.get("schemaVersion")
        not in {LEGACY_JOB_SCHEMA_VERSION, JOB_SCHEMA_VERSION}
        or job.get("state")
        not in {
            "QUEUED", "LEASED", "RUNNING", "SUCCEEDED", "FAILED",
            "RETRYING", "CANCELLED",
        }
        or isinstance(job.get("revision"), bool)
        or not isinstance(job.get("revision"), int)
        or job.get("revision", -1) < 0
        or not isinstance(job.get("attempts"), list)
        or isinstance(job.get("maxAttempts"), bool)
        or not isinstance(job.get("maxAttempts"), int)
        or job.get("maxAttempts", 0) < 1
        or len(job.get("attempts", [])) > job.get("maxAttempts", 0)
        or job.get("executionScope") != "SINGLE_EPISODE"
        or job.get("batchProductionAllowed") is not False
    ):
        raise MediaJobError("invalid media job record")
    request = job.get("request")
    if not isinstance(request, Mapping):
        raise MediaJobError("media job request is missing")
    _validate_request(request)
    if (
        job.get("workspaceRef") != request.get("workspaceRef")
        or job.get("productionRunRef") != request.get("productionRunRef")
        or job.get("requestDigest") != request.get("payloadDigest")
    ):
        raise MediaJobError("media job request lineage is inconsistent")
    if any(
        not isinstance(attempt, Mapping)
        or attempt.get("state") not in {"RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"}
        for attempt in job["attempts"]
    ):
        raise MediaJobError("media job attempts are invalid")
    attempt_numbers = [attempt.get("attemptNumber") for attempt in job["attempts"]]
    attempt_refs = [attempt.get("attemptRef") for attempt in job["attempts"]]
    if (
        any(
            isinstance(number, bool)
            or not isinstance(number, int)
            for number in attempt_numbers
        )
        or attempt_numbers != list(range(1, len(attempt_numbers) + 1))
        or any(not isinstance(ref, str) or not ref for ref in attempt_refs)
        or len(set(attempt_refs)) != len(attempt_refs)
    ):
        raise MediaJobError("media job attempt identity is invalid")
    intent = job.get("artifactCommitIntent")
    if intent is not None:
        if job.get("schemaVersion") != JOB_SCHEMA_VERSION:
            raise MediaJobError(
                "legacy media job cannot contain an artifact commit intent"
            )
        _validate_artifact_commit_intent(intent, job)
    _validate_job_state_shape(job)


def _validate_artifact_commit_intent(
    intent: Mapping[str, Any], job: Mapping[str, Any]
) -> None:
    fields = {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "jobRef",
        "attemptRef",
        "attemptNumber",
        "generationRequestRef",
        "generationRequestDigest",
        "candidateStorageKey",
        "finalStorageKey",
        "artifact",
        "createdAt",
        "intentDigest",
    }
    artifact = intent.get("artifact") if isinstance(intent, Mapping) else None
    attempts = job.get("attempts")
    latest_attempt = attempts[-1] if isinstance(attempts, list) and attempts else None
    if (
        not isinstance(intent, Mapping)
        or set(intent) != fields
        or intent.get("schemaVersion") != ARTIFACT_COMMIT_INTENT_SCHEMA_VERSION
        or intent.get("workspaceRef") != job.get("workspaceRef")
        or intent.get("productionRunRef") != job.get("productionRunRef")
        or intent.get("jobRef") != job.get("jobRef")
        or not isinstance(latest_attempt, Mapping)
        or intent.get("attemptRef") != latest_attempt.get("attemptRef")
        or intent.get("attemptNumber") != latest_attempt.get("attemptNumber")
        or intent.get("generationRequestRef")
        != job.get("request", {}).get("generationRequestRef")
        or intent.get("generationRequestDigest") != job.get("requestDigest")
        or not isinstance(intent.get("candidateStorageKey"), str)
        or not intent["candidateStorageKey"]
        or not isinstance(intent.get("finalStorageKey"), str)
        or not intent["finalStorageKey"]
        or intent["candidateStorageKey"] == intent["finalStorageKey"]
        or not isinstance(intent.get("createdAt"), str)
        or not intent["createdAt"]
        or not _hex_digest(intent.get("intentDigest"))
        or _digest({key: value for key, value in intent.items() if key != "intentDigest"})
        != intent.get("intentDigest")
        or not isinstance(artifact, Mapping)
        or artifact.get("schemaVersion") != ARTIFACT_SCHEMA_VERSION
        or artifact.get("workspaceRef") != job.get("workspaceRef")
        or artifact.get("productionRunRef") != job.get("productionRunRef")
        or artifact.get("jobRef") != job.get("jobRef")
        or artifact.get("attemptRef") != intent.get("attemptRef")
        or artifact.get("generationRequestRef") != intent.get("generationRequestRef")
        or artifact.get("generationRequestDigest")
        != intent.get("generationRequestDigest")
        or artifact.get("storageKey") != intent.get("finalStorageKey")
        or not isinstance(artifact.get("internalPath"), str)
        or not artifact["internalPath"]
        or not _hex_digest(artifact.get("sha256"))
        or isinstance(artifact.get("byteSize"), bool)
        or not isinstance(artifact.get("byteSize"), int)
        or artifact["byteSize"] < 1
        or not isinstance(artifact.get("probe"), Mapping)
        or artifact.get("publicationAllowed") is not False
    ):
        raise MediaJobError("artifact commit intent is invalid")


_IMMUTABLE_JOB_FIELDS = (
    "workspaceRef",
    "productionRunRef",
    "jobRef",
    "idempotencyKey",
    "requestDigest",
    "request",
    "maxAttempts",
    "executionScope",
    "batchProductionAllowed",
    "createdAt",
)


def _validate_job_update(
    current: Mapping[str, Any], value: Mapping[str, Any]
) -> None:
    schema_transition = (
        current.get("schemaVersion"),
        value.get("schemaVersion"),
    )
    if (
        schema_transition
        not in {
            (LEGACY_JOB_SCHEMA_VERSION, LEGACY_JOB_SCHEMA_VERSION),
            (LEGACY_JOB_SCHEMA_VERSION, JOB_SCHEMA_VERSION),
            (JOB_SCHEMA_VERSION, JOB_SCHEMA_VERSION),
        }
        or any(
            current.get(field) != value.get(field)
            for field in _IMMUTABLE_JOB_FIELDS
        )
    ):
        raise MediaJobStateError("immutable media job identity changed")
    if schema_transition == (LEGACY_JOB_SCHEMA_VERSION, JOB_SCHEMA_VERSION) and (
        (current.get("state"), value.get("state"))
        not in {("QUEUED", "LEASED"), ("LEASED", "RUNNING")}
    ):
        raise MediaJobStateError("legacy media job upgrade is not at an attempt fence")
    if value.get("revision") != current.get("revision"):
        raise MediaJobStateError("media job revision changed inside payload")

    allowed_states = {
        "QUEUED": {"QUEUED", "LEASED", "FAILED", "RETRYING", "CANCELLED"},
        "LEASED": {"RUNNING", "QUEUED", "FAILED", "CANCELLED"},
        "RUNNING": {"RUNNING", "SUCCEEDED", "FAILED", "QUEUED", "CANCELLED"},
        "FAILED": {"FAILED", "QUEUED", "RETRYING", "CANCELLED"},
        "RETRYING": {"RETRYING", "QUEUED", "FAILED", "CANCELLED"},
        "SUCCEEDED": {"SUCCEEDED"},
        "CANCELLED": {"CANCELLED"},
    }
    if value["state"] not in allowed_states[current["state"]]:
        raise MediaJobStateError("invalid media job state transition")

    current_attempts = current["attempts"]
    next_attempts = value["attempts"]
    if (
        len(next_attempts) < len(current_attempts)
        or len(next_attempts) > len(current_attempts) + 1
    ):
        raise MediaJobStateError("media job attempt history is not append-only")
    if len(next_attempts) == len(current_attempts) + 1:
        if (
            current["state"] != "LEASED"
            or value["state"] != "RUNNING"
            or next_attempts[:-1] != current_attempts
            or next_attempts[-1].get("state") != "RUNNING"
        ):
            raise MediaJobStateError("invalid media job attempt append")
    elif current_attempts:
        if next_attempts[:-1] != current_attempts[:-1]:
            raise MediaJobStateError("historical media job attempt changed")
        previous = current_attempts[-1]
        latest = next_attempts[-1]
        if previous != latest:
            if previous.get("state") == "RUNNING":
                if (
                    latest.get("state")
                    not in {"SUCCEEDED", "FAILED", "CANCELLED"}
                    or any(
                        latest.get(field) != previous.get(field)
                        for field in previous
                        if field != "state"
                    )
                ):
                    raise MediaJobStateError(
                        "running media job attempt transition is invalid"
                    )
            else:
                mutable_cleanup_fields = {"quarantineStorageKeys"}
                if (
                    previous.get("state")
                    not in {"FAILED", "CANCELLED"}
                    or latest.get("state") != previous.get("state")
                    or {
                        key: item
                        for key, item in latest.items()
                        if key not in mutable_cleanup_fields
                    }
                    != {
                        key: item
                        for key, item in previous.items()
                        if key not in mutable_cleanup_fields
                    }
                    or not isinstance(
                        previous.get("quarantineStorageKeys"), list
                    )
                    or not isinstance(latest.get("quarantineStorageKeys"), list)
                    or not latest["quarantineStorageKeys"]
                    or latest["quarantineStorageKeys"][: len(
                        previous["quarantineStorageKeys"]
                    )]
                    != previous["quarantineStorageKeys"]
                    or any(
                        not isinstance(item, str) or not item
                        for item in latest["quarantineStorageKeys"]
                    )
                ):
                    raise MediaJobStateError("terminal media job attempt changed")

    current_lease = current.get("lease")
    next_lease = value.get("lease")
    if current["state"] in {"LEASED", "RUNNING"} and value["state"] in {
        "LEASED",
        "RUNNING",
    }:
        legacy_upgrade = (
            current["schemaVersion"] == LEGACY_JOB_SCHEMA_VERSION
            and value["schemaVersion"] == JOB_SCHEMA_VERSION
            and isinstance(current_lease, Mapping)
            and isinstance(next_lease, Mapping)
            and {
                key: item
                for key, item in next_lease.items()
                if key != "leaseToken"
            }
            == dict(current_lease)
            and isinstance(next_lease.get("leaseToken"), str)
            and bool(next_lease["leaseToken"])
        )
        recovery_rotation = (
            current["state"] == "RUNNING"
            and value["state"] == "RUNNING"
            and isinstance(current.get("artifactCommitIntent"), Mapping)
            and value.get("artifactCommitIntent")
            == current.get("artifactCommitIntent")
            and isinstance(next_lease, Mapping)
            and next_lease.get("workerRef") == _RECOVERY_WORKER_REF
            and isinstance(next_lease.get("leaseToken"), str)
            and bool(next_lease["leaseToken"])
            and _parse_time(next_lease["leasedAt"])
            >= _parse_time(current_lease["expiresAt"])
        )
        heartbeat_renewal = (
            current["schemaVersion"] == JOB_SCHEMA_VERSION
            and value["schemaVersion"] == JOB_SCHEMA_VERSION
            and current["state"] == "RUNNING"
            and value["state"] == "RUNNING"
            and isinstance(current_lease, Mapping)
            and isinstance(next_lease, Mapping)
            and next_lease.get("workerRef") == current_lease.get("workerRef")
            and next_lease.get("leaseToken") == current_lease.get("leaseToken")
            and next_lease.get("leasedAt") == current_lease.get("leasedAt")
            and _parse_time(next_lease["expiresAt"])
            > _parse_time(current_lease["expiresAt"])
        )
        if (
            next_lease != current_lease
            and not legacy_upgrade
            and not recovery_rotation
            and not heartbeat_renewal
        ):
            raise MediaJobStateError("media job lease identity changed")

    current_intent = current.get("artifactCommitIntent")
    next_intent = value.get("artifactCommitIntent")
    if isinstance(next_intent, Mapping) and current_intent not in (None, next_intent):
        raise MediaJobStateError("artifact commit intent changed")
    if value["state"] == "SUCCEEDED":
        if not isinstance(current_intent, Mapping) or next_intent is not None:
            raise MediaJobStateError("artifact success requires a consumed commit intent")


class InMemoryMediaJobAdapter:
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._idem: dict[tuple[str, str, str], str] = {}
        self._batches: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._lock = RLock()

    def create(self, job: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        value = deepcopy(dict(job))
        _validate_job(value)
        key = (value["workspaceRef"], value["productionRunRef"], value["jobRef"])
        idem = (value["workspaceRef"], value["productionRunRef"], value["idempotencyKey"])
        with self._lock:
            existing_ref = self._idem.get(idem)
            if existing_ref is not None:
                existing = self._jobs[(idem[0], idem[1], existing_ref)]
                if existing["requestDigest"] != value["requestDigest"]:
                    raise MediaJobConflictError("media dispatch idempotency conflict")
                return deepcopy(existing), True
            if key in self._jobs:
                raise MediaJobConflictError("duplicate media job ref")
            self._jobs[key] = value
            self._idem[idem] = value["jobRef"]
            return deepcopy(value), False

    def reserve_batch(
        self, batch: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        value = deepcopy(dict(batch))
        _validate_batch(value)
        key = (
            value["workspaceRef"],
            value["productionRunRef"],
            value["batchIdempotencyKey"],
        )
        with self._lock:
            existing = self._batches.get(key)
            if existing is not None:
                if existing["payloadDigest"] != value["payloadDigest"]:
                    raise MediaJobConflictError(
                        "media batch idempotency conflict"
                    )
                return deepcopy(existing), True
            self._batches[key] = value
            return deepcopy(value), False

    def get(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._jobs.get((workspace_ref, run_ref, job_ref))
            return deepcopy(value) if value is not None else None

    def list(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        with self._lock:
            values = [
                deepcopy(value) for (workspace, run, _), value in self._jobs.items()
                if workspace == workspace_ref and run == run_ref
            ]
        return sorted(values, key=lambda item: (item["createdAt"], item["jobRef"]))

    def save(self, job: Mapping[str, Any], expected_revision: int) -> dict[str, Any]:
        value = deepcopy(dict(job))
        _validate_job(value)
        key = (value["workspaceRef"], value["productionRunRef"], value["jobRef"])
        with self._lock:
            current = self._jobs.get(key)
            if current is None or current["revision"] != expected_revision:
                raise MediaJobStateError("media job revision changed")
            _validate_job_update(current, value)
            value["revision"] = expected_revision + 1
            self._jobs[key] = value
            return deepcopy(value)


class SqliteMediaJobAdapter:
    _SCHEMA_VERSION = 2
    _LEGACY_TABLES = {"v4_media_job_schema", "v4_media_jobs"}
    _TABLES = {
        "v4_media_job_schema",
        "v4_media_jobs",
        "v4_media_job_batches",
    }
    _DDL = {
        "v4_media_job_schema": (
            "CREATE TABLE v4_media_job_schema ("
            "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
        ),
        "v4_media_jobs": (
            "CREATE TABLE v4_media_jobs ("
            "workspace_ref TEXT NOT NULL,"
            "production_run_ref TEXT NOT NULL,"
            "job_ref TEXT NOT NULL,"
            "idempotency_key TEXT NOT NULL,"
            "request_digest TEXT NOT NULL,"
            "state TEXT NOT NULL,"
            "revision INTEGER NOT NULL,"
            "payload_json TEXT NOT NULL,"
            "PRIMARY KEY(workspace_ref,production_run_ref,job_ref),"
            "UNIQUE(workspace_ref,production_run_ref,idempotency_key))"
        ),
        "v4_media_job_batches": (
            "CREATE TABLE v4_media_job_batches ("
            "workspace_ref TEXT NOT NULL,"
            "production_run_ref TEXT NOT NULL,"
            "batch_idempotency_key TEXT NOT NULL,"
            "payload_digest TEXT NOT NULL,"
            "payload_json TEXT NOT NULL,"
            "PRIMARY KEY(workspace_ref,production_run_ref,batch_idempotency_key))"
        ),
    }
    _TABLE_INFO = {
        "v4_media_job_schema": (
            ("component", "TEXT", 0, None, 1),
            ("schema_version", "INTEGER", 1, None, 0),
        ),
        "v4_media_jobs": (
            ("workspace_ref", "TEXT", 1, None, 1),
            ("production_run_ref", "TEXT", 1, None, 2),
            ("job_ref", "TEXT", 1, None, 3),
            ("idempotency_key", "TEXT", 1, None, 0),
            ("request_digest", "TEXT", 1, None, 0),
            ("state", "TEXT", 1, None, 0),
            ("revision", "INTEGER", 1, None, 0),
            ("payload_json", "TEXT", 1, None, 0),
        ),
        "v4_media_job_batches": (
            ("workspace_ref", "TEXT", 1, None, 1),
            ("production_run_ref", "TEXT", 1, None, 2),
            ("batch_idempotency_key", "TEXT", 1, None, 3),
            ("payload_digest", "TEXT", 1, None, 0),
            ("payload_json", "TEXT", 1, None, 0),
        ),
    }
    _INDEXES = {
        "v4_media_job_schema": {
            ("pk", ("component",)),
        },
        "v4_media_jobs": {
            ("pk", ("workspace_ref", "production_run_ref", "job_ref")),
            (
                "u",
                ("workspace_ref", "production_run_ref", "idempotency_key"),
            ),
        },
        "v4_media_job_batches": {
            (
                "pk",
                (
                    "workspace_ref",
                    "production_run_ref",
                    "batch_idempotency_key",
                ),
            ),
        },
    }

    def __init__(self, database_path: Path | str, *, initialize_if_missing: bool = True) -> None:
        self.path = Path(database_path)
        try:
            if initialize_if_missing:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._initialize_or_migrate()
            elif not self.path.is_file():
                raise MediaJobError("media job database is unavailable")
            self._verify_schema()
        except MediaJobError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise MediaJobError("media job database is unavailable") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _normalized_ddl(value: str | None) -> str:
        if not isinstance(value, str):
            return ""
        normalized = re.sub(r"\s+", "", value).lower()
        return normalized.replace("ifnotexists", "")

    @staticmethod
    def _user_objects(connection: sqlite3.Connection) -> set[tuple[str, str]]:
        return {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                "SELECT type,name FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }

    @classmethod
    def _verify_table(
        cls, connection: sqlite3.Connection, table: str
    ) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if (
            row is None
            or cls._normalized_ddl(row[0])
            != cls._normalized_ddl(cls._DDL[table])
        ):
            raise MediaJobError("media job schema DDL mismatch")
        table_info = tuple(
            (str(row[1]), str(row[2]).upper(), int(row[3]), row[4], int(row[5]))
            for row in connection.execute(f"PRAGMA table_info({table})")
        )
        if table_info != cls._TABLE_INFO[table]:
            raise MediaJobError("media job schema columns mismatch")
        indexes: set[tuple[str, tuple[str, ...]]] = set()
        for row in connection.execute(f"PRAGMA index_list({table})"):
            if int(row[2]) != 1 or int(row[4]) != 0:
                raise MediaJobError("media job schema index mismatch")
            name = str(row[1])
            columns = tuple(
                str(index_row[2])
                for index_row in connection.execute(
                    f"PRAGMA index_info({name})"
                )
            )
            indexes.add((str(row[3]), columns))
        if indexes != cls._INDEXES[table]:
            raise MediaJobError("media job schema index mismatch")
        if connection.execute(f"PRAGMA foreign_key_list({table})").fetchall():
            raise MediaJobError("media job schema foreign keys mismatch")

    @classmethod
    def _verify_schema_connection(
        cls, connection: sqlite3.Connection, *, version: int
    ) -> None:
        expected_tables = cls._LEGACY_TABLES if version == 1 else cls._TABLES
        objects = cls._user_objects(connection)
        if objects != {("table", table) for table in expected_tables}:
            raise MediaJobError("media job schema mismatch")
        for table in expected_tables:
            cls._verify_table(connection, table)
        marker = connection.execute(
            "SELECT component,schema_version FROM v4_media_job_schema"
        ).fetchall()
        if [tuple(row) for row in marker] != [("media_jobs", version)]:
            raise MediaJobError("media job schema marker mismatch")
        integrity = connection.execute("PRAGMA quick_check").fetchall()
        if [tuple(row) for row in integrity] != [("ok",)]:
            raise MediaJobError("media job database integrity check failed")

    def _initialize_or_migrate(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            objects = self._user_objects(connection)
            if not objects:
                connection.execute(self._DDL["v4_media_job_schema"])
                connection.execute(
                    "INSERT INTO v4_media_job_schema VALUES ('media_jobs',?)",
                    (self._SCHEMA_VERSION,),
                )
                connection.execute(self._DDL["v4_media_jobs"])
                connection.execute(self._DDL["v4_media_job_batches"])
            elif objects == {
                ("table", table) for table in self._LEGACY_TABLES
            }:
                self._verify_schema_connection(connection, version=1)
                connection.execute(self._DDL["v4_media_job_batches"])
                connection.execute(
                    "UPDATE v4_media_job_schema SET schema_version=? "
                    "WHERE component='media_jobs' AND schema_version=1",
                    (self._SCHEMA_VERSION,),
                )
                if connection.total_changes != 1:
                    raise MediaJobError("media job schema migration failed")
            else:
                self._verify_schema_connection(
                    connection, version=self._SCHEMA_VERSION
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _verify_schema(self) -> None:
        connection = self._connect()
        try:
            self._verify_schema_connection(
                connection, version=self._SCHEMA_VERSION
            )
        finally:
            connection.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        try:
            value = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            raise MediaJobError("media job payload is corrupt") from None
        if not isinstance(value, dict):
            raise MediaJobError("media job payload is corrupt")
        _validate_job(value)
        if (
            value.get("workspaceRef") != row["workspace_ref"]
            or value.get("productionRunRef") != row["production_run_ref"]
            or value.get("jobRef") != row["job_ref"]
            or value.get("idempotencyKey") != row["idempotency_key"]
            or value.get("requestDigest") != row["request_digest"]
            or value.get("state") != row["state"]
            or value.get("revision") != row["revision"]
        ):
            raise MediaJobError("media job indexed fields are corrupt")
        return value

    @staticmethod
    def _decode_batch(row: sqlite3.Row) -> dict[str, Any]:
        try:
            value = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            raise MediaJobError("media batch payload is corrupt") from None
        if not isinstance(value, dict):
            raise MediaJobError("media batch payload is corrupt")
        _validate_batch(value)
        if (
            value.get("workspaceRef") != row["workspace_ref"]
            or value.get("productionRunRef") != row["production_run_ref"]
            or value.get("batchIdempotencyKey")
            != row["batch_idempotency_key"]
            or value.get("payloadDigest") != row["payload_digest"]
        ):
            raise MediaJobError("media batch indexed fields are corrupt")
        return value

    def create(self, job: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        value = deepcopy(dict(job))
        _validate_job(value)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM v4_media_jobs WHERE workspace_ref=? AND "
                "production_run_ref=? AND idempotency_key=?",
                (value["workspaceRef"], value["productionRunRef"], value["idempotencyKey"]),
            ).fetchone()
            if existing is not None:
                restored = self._decode(existing)
                if restored["requestDigest"] != value["requestDigest"]:
                    raise MediaJobConflictError("media dispatch idempotency conflict")
                connection.rollback()
                return deepcopy(restored), True
            connection.execute(
                "INSERT INTO v4_media_jobs VALUES (?,?,?,?,?,?,?,?)",
                (
                    value["workspaceRef"], value["productionRunRef"], value["jobRef"],
                    value["idempotencyKey"], value["requestDigest"], value["state"],
                    value["revision"], _canonical(value).decode("utf-8"),
                ),
            )
            connection.commit()
            return deepcopy(value), False
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise MediaJobConflictError("duplicate media job") from exc
        finally:
            connection.close()

    def reserve_batch(
        self, batch: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        value = deepcopy(dict(batch))
        _validate_batch(value)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM v4_media_job_batches WHERE workspace_ref=? "
                "AND production_run_ref=? AND batch_idempotency_key=?",
                (
                    value["workspaceRef"],
                    value["productionRunRef"],
                    value["batchIdempotencyKey"],
                ),
            ).fetchone()
            if existing is not None:
                restored = self._decode_batch(existing)
                if restored["payloadDigest"] != value["payloadDigest"]:
                    raise MediaJobConflictError(
                        "media batch idempotency conflict"
                    )
                connection.rollback()
                return deepcopy(restored), True
            connection.execute(
                "INSERT INTO v4_media_job_batches "
                "(workspace_ref,production_run_ref,batch_idempotency_key,"
                "payload_digest,payload_json) VALUES (?,?,?,?,?)",
                (
                    value["workspaceRef"],
                    value["productionRunRef"],
                    value["batchIdempotencyKey"],
                    value["payloadDigest"],
                    _canonical(value).decode("utf-8"),
                ),
            )
            connection.commit()
            return deepcopy(value), False
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise MediaJobConflictError("duplicate media batch") from exc
        finally:
            connection.close()

    def get(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM v4_media_jobs WHERE workspace_ref=? AND "
                "production_run_ref=? AND job_ref=?",
                (workspace_ref, run_ref, job_ref),
            ).fetchone()
            return deepcopy(self._decode(row)) if row is not None else None
        finally:
            connection.close()

    def list(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM v4_media_jobs WHERE workspace_ref=? AND "
                "production_run_ref=? ORDER BY job_ref",
                (workspace_ref, run_ref),
            ).fetchall()
            return [deepcopy(self._decode(row)) for row in rows]
        finally:
            connection.close()

    def save(self, job: Mapping[str, Any], expected_revision: int) -> dict[str, Any]:
        value = deepcopy(dict(job))
        _validate_job(value)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_row = connection.execute(
                "SELECT * FROM v4_media_jobs WHERE workspace_ref=? AND "
                "production_run_ref=? AND job_ref=?",
                (value["workspaceRef"], value["productionRunRef"], value["jobRef"]),
            ).fetchone()
            if current_row is None:
                connection.rollback()
                raise MediaJobStateError("media job revision changed")
            current = self._decode(current_row)
            if current["revision"] != expected_revision:
                connection.rollback()
                raise MediaJobStateError("media job revision changed")
            _validate_job_update(current, value)
            value["revision"] = expected_revision + 1
            cursor = connection.execute(
                "UPDATE v4_media_jobs SET state=?,revision=?,payload_json=? WHERE "
                "workspace_ref=? AND production_run_ref=? AND job_ref=? AND revision=?",
                (
                    value["state"], value["revision"],
                    _canonical(value).decode("utf-8"), value["workspaceRef"],
                    value["productionRunRef"], value["jobRef"], expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise MediaJobStateError("media job revision changed")
            connection.commit()
            return deepcopy(value)
        finally:
            connection.close()


def _probe_media_cache_key(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ArtifactVerificationError("ffprobe verification failed") from exc
    return digest.hexdigest(), size


def probe_media(path: Path) -> dict[str, Any]:
    cache_key = _probe_media_cache_key(path)
    with _PROBE_MEDIA_CACHE_LOCK:
        cached = _PROBE_MEDIA_CACHE.get(cache_key)
    if cached is not None:
        return deepcopy(cached)
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-count_frames", "-show_streams",
                "-show_format", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ArtifactVerificationError("ffprobe verification failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        raise ArtifactVerificationError("artifact has no media stream")
    normalized = []
    for stream in streams:
        if not isinstance(stream, Mapping):
            raise ArtifactVerificationError("artifact stream is malformed")
        normalized.append(
            {
                key: stream.get(key)
                for key in (
                    "codec_type", "codec_name", "width", "height", "pix_fmt",
                    "avg_frame_rate", "nb_frames", "nb_read_frames", "sample_rate",
                    "channels", "duration",
                )
                if stream.get(key) is not None
            }
        )
    probe = {
        "streams": normalized,
        "formatName": payload.get("format", {}).get("format_name"),
        "durationSeconds": payload.get("format", {}).get("duration"),
    }
    with _PROBE_MEDIA_CACHE_LOCK:
        cached = _PROBE_MEDIA_CACHE.setdefault(cache_key, deepcopy(probe))
    return deepcopy(cached)


def verify_media_against_request(path: Path, request: Mapping[str, Any]) -> dict[str, Any]:
    probe = probe_media(path)
    parameters = request["parameters"]
    kind = request["mediaKind"]
    matches = [item for item in probe["streams"] if item.get("codec_type") == kind]
    if len(matches) != 1:
        raise ArtifactVerificationError("artifact media kind is invalid")
    stream = matches[0]
    expected_seconds = parameters["durationFrames"] / parameters["frameRate"]
    try:
        actual_seconds = float(stream.get("duration", probe.get("durationSeconds")))
    except (TypeError, ValueError):
        raise ArtifactVerificationError("artifact duration is unavailable") from None
    tolerance = max(1 / parameters["frameRate"], 0.025)
    if abs(actual_seconds - expected_seconds) > tolerance:
        raise ArtifactVerificationError("artifact duration does not match request")
    if kind == "video":
        frame_count = stream.get("nb_read_frames") or stream.get("nb_frames")
        try:
            frames = int(frame_count)
        except (TypeError, ValueError):
            raise ArtifactVerificationError("video frame count is unavailable") from None
        if (
            stream.get("width") != parameters["width"]
            or stream.get("height") != parameters["height"]
            or frames != parameters["durationFrames"]
        ):
            raise ArtifactVerificationError("video probe does not match request")
    else:
        try:
            sample_rate = int(stream.get("sample_rate"))
        except (TypeError, ValueError):
            raise ArtifactVerificationError("audio sample rate is unavailable") from None
        if sample_rate != parameters["sampleRate"] or stream.get("channels") != parameters["channels"]:
            raise ArtifactVerificationError("audio probe does not match request")
    return probe


class DeterministicLocalFfmpegAdapter:
    adapter_identity = "v4.deterministic-local-ffmpeg.v1"
    provenance = "LOCAL_EVIDENCE"

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path:
        parameters = request["parameters"]
        frames = parameters["durationFrames"]
        frame_rate = parameters["frameRate"]
        duration = f"{frames / frame_rate:.9f}".rstrip("0").rstrip(".")
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        if request["mediaKind"] == "video":
            color = parameters["visualSeedDigest"][:6]
            command = [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"color=c=0x{color}:s={parameters['width']}x{parameters['height']}:"
                f"r={frame_rate}:d={duration}",
                "-frames:v", str(frames), "-an", "-c:v", "libx264",
                "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags",
                "+faststart", "-y", str(candidate_path),
            ]
        else:
            command = [
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"sine=frequency={parameters['toneFrequencyHz']}:"
                f"sample_rate={parameters['sampleRate']}:duration={duration}",
                "-ac", str(parameters["channels"]), "-c:a", "pcm_s16le",
                "-y", str(candidate_path),
            ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=120)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise MediaAdapterUnavailableError("local FFmpeg adapter failed") from exc
        return candidate_path


class MediaJobCoordinator:
    def __init__(
        self,
        repository: MediaJobRepository,
        adapter: MediaGenerationAdapter,
        artifact_root: Path | str,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
        lease_seconds: int = 30,
        heartbeat_interval_seconds: float | None = None,
        max_attempts: int = 3,
    ) -> None:
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 1
            or (
                heartbeat_interval_seconds is not None
                and (
                    isinstance(heartbeat_interval_seconds, bool)
                    or not isinstance(heartbeat_interval_seconds, (int, float))
                    or not isfinite(float(heartbeat_interval_seconds))
                    or heartbeat_interval_seconds <= 0
                    or heartbeat_interval_seconds >= lease_seconds
                )
            )
            or isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or max_attempts < 1
        ):
            raise MediaJobError("media worker recovery limits are invalid")
        self.repository = repository
        self.adapter = adapter
        try:
            self._artifact_recovery = ArtifactRecoveryStore(artifact_root)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        self.artifact_root = self._artifact_recovery.root
        self._ref_factory = ref_factory
        self._clock = clock
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = (
            float(heartbeat_interval_seconds)
            if heartbeat_interval_seconds is not None
            else min(max(lease_seconds / 3.0, 0.05), 5.0)
        )
        self.max_attempts = max_attempts

    def _active_worker_job(
        self,
        workspace_ref: str,
        run_ref: str,
        job_ref: str,
        worker_ref: str,
        lease_token: str,
        attempt_ref: str,
    ) -> dict[str, Any]:
        current = self.repository.get(workspace_ref, run_ref, job_ref)
        lease = current.get("lease") if current is not None else None
        attempts = current.get("attempts") if current is not None else None
        latest = attempts[-1] if isinstance(attempts, list) and attempts else None
        if (
            current is None
            or current.get("state") != "RUNNING"
            or not isinstance(lease, Mapping)
            or lease.get("workerRef") != worker_ref
            or lease.get("leaseToken") != lease_token
            or _parse_time(lease["expiresAt"]) <= _parse_time(self._clock())
            or not isinstance(latest, Mapping)
            or latest.get("attemptRef") != attempt_ref
            or latest.get("state") != "RUNNING"
        ):
            raise MediaJobStateError("worker lease was fenced")
        return current

    def _renew_running_lease(
        self,
        workspace_ref: str,
        run_ref: str,
        job_ref: str,
        worker_ref: str,
        lease_token: str,
        attempt_ref: str,
    ) -> dict[str, Any]:
        for _ in range(4):
            current = self._active_worker_job(
                workspace_ref,
                run_ref,
                job_ref,
                worker_ref,
                lease_token,
                attempt_ref,
            )
            lease = current["lease"]
            now = _parse_time(self._clock())
            proposed_expiry = now + timedelta(seconds=self.lease_seconds)
            if proposed_expiry <= _parse_time(lease["expiresAt"]):
                return current
            expected = current["revision"]
            current["lease"] = {
                **dict(lease),
                "expiresAt": _format_time(proposed_expiry),
            }
            current["updatedAt"] = _format_time(now)
            try:
                return self.repository.save(current, expected)
            except MediaJobStateError:
                continue
        raise MediaJobStateError("worker lease heartbeat lost its CAS fence")

    def _start_lease_heartbeat(
        self,
        job: Mapping[str, Any],
        worker_ref: str,
        attempt_ref: str,
    ) -> tuple[Event, Thread, list[BaseException]]:
        lease = job.get("lease")
        if not isinstance(lease, Mapping) or not isinstance(
            lease.get("leaseToken"), str
        ):
            raise MediaJobStateError("worker lease token is missing")
        lease_token = lease["leaseToken"]
        self._renew_running_lease(
            job["workspaceRef"],
            job["productionRunRef"],
            job["jobRef"],
            worker_ref,
            lease_token,
            attempt_ref,
        )
        stopped = Event()
        failures: list[BaseException] = []

        def heartbeat() -> None:
            while not stopped.wait(self.heartbeat_interval_seconds):
                try:
                    self._renew_running_lease(
                        job["workspaceRef"],
                        job["productionRunRef"],
                        job["jobRef"],
                        worker_ref,
                        lease_token,
                        attempt_ref,
                    )
                except BaseException as exc:
                    failures.append(exc)
                    stopped.set()
                    return

        thread = Thread(
            target=heartbeat,
            name=f"media-job-heartbeat-{sha256(job['jobRef'].encode()).hexdigest()[:8]}",
            daemon=True,
        )
        thread.start()
        return stopped, thread, failures

    def _stop_lease_heartbeat(
        self,
        heartbeat: tuple[Event, Thread, list[BaseException]],
        job: Mapping[str, Any],
        worker_ref: str,
        attempt_ref: str,
    ) -> dict[str, Any]:
        stopped, thread, failures = heartbeat
        stopped.set()
        thread.join(timeout=max(1.0, min(self.heartbeat_interval_seconds * 2, 15.0)))
        if thread.is_alive():
            raise MediaJobStateError("worker lease heartbeat did not stop")
        if failures:
            failure = failures[0]
            if isinstance(failure, MediaJobStateError):
                raise failure
            raise MediaJobStateError("worker lease heartbeat failed") from failure
        lease = job.get("lease")
        if not isinstance(lease, Mapping):
            raise MediaJobStateError("worker lease token is missing")
        return self._active_worker_job(
            job["workspaceRef"],
            job["productionRunRef"],
            job["jobRef"],
            worker_ref,
            str(lease.get("leaseToken", "")),
            attempt_ref,
        )

    def _run_root(self, workspace_ref: str, run_ref: str) -> Path:
        try:
            return self._artifact_recovery.run_root(workspace_ref, run_ref)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc

    def _safe_path(self, workspace_ref: str, run_ref: str, candidate: Path) -> Path:
        try:
            return self._artifact_recovery.scoped_path(
                workspace_ref,
                run_ref,
                candidate,
                require_regular_file=False,
            )
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc

    def _attempt_paths(
        self,
        job: Mapping[str, Any],
        attempt_number: int,
        *,
        create: bool = True,
    ) -> tuple[Path, Path]:
        extension = ".mp4" if job["request"]["mediaKind"] == "video" else ".wav"
        matching = [
            attempt
            for attempt in job["attempts"]
            if attempt.get("attemptNumber") == attempt_number
        ]
        if len(matching) != 1 or not isinstance(matching[0].get("attemptRef"), str):
            raise ArtifactVerificationError("artifact attempt identity is invalid")
        try:
            return self._artifact_recovery.attempt_paths(
                job["workspaceRef"],
                job["productionRunRef"],
                job["request"]["generationRequestRef"],
                job["jobRef"],
                matching[0]["attemptRef"],
                attempt_number,
                extension,
                create=create,
            )
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc

    def _build_commit_intent(
        self,
        job: Mapping[str, Any],
        attempt: Mapping[str, Any],
        candidate_path: Path,
        final_path: Path,
        artifact: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            candidate_key = self._artifact_recovery.storage_key(candidate_path)
            final_key = self._artifact_recovery.storage_key(final_path)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        value = {
            "schemaVersion": ARTIFACT_COMMIT_INTENT_SCHEMA_VERSION,
            "workspaceRef": job["workspaceRef"],
            "productionRunRef": job["productionRunRef"],
            "jobRef": job["jobRef"],
            "attemptRef": attempt["attemptRef"],
            "attemptNumber": attempt["attemptNumber"],
            "generationRequestRef": job["request"]["generationRequestRef"],
            "generationRequestDigest": job["requestDigest"],
            "candidateStorageKey": candidate_key,
            "finalStorageKey": final_key,
            "artifact": deepcopy(dict(artifact)),
            "createdAt": self._clock(),
        }
        value["intentDigest"] = _digest(value)
        return value

    def _validate_recovery_execution(
        self, artifact: Mapping[str, Any], request: Mapping[str, Any]
    ) -> None:
        provenance = request["requestedProvenance"]
        execution = artifact.get("providerExecution")
        if provenance == "LIVE_PROVIDER":
            _validate_live_execution(execution, request)
        elif provenance == M11_VIDEO_PROVENANCE:
            _validate_m11_execution(execution, request)
        elif provenance == "LOCAL_EVIDENCE":
            if execution is not None:
                raise ArtifactVerificationError(
                    "local artifact unexpectedly contains provider execution"
                )
        else:
            raise ArtifactVerificationError("artifact provenance is unsupported")

    def _repair_interrupted_publication(
        self, job: dict[str, Any], intent: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """CAS-claim and finish only durable_replace's exact two-link state."""

        try:
            candidate = self._artifact_recovery.path_from_storage_key(
                intent["candidateStorageKey"], require_regular_file=True
            )
            final = self._artifact_recovery.path_from_storage_key(
                intent["finalStorageKey"], require_regular_file=True
            )
            expected_candidate, expected_final = self._attempt_paths(
                job, intent["attemptNumber"], create=False
            )
            if candidate != expected_candidate or final != expected_final:
                return job, True
            candidate_stat = os.lstat(candidate)
            final_stat = os.lstat(final)
        except (KeyError, OSError, ArtifactVerificationError, ArtifactRecoveryStoreError):
            return job, True
        if (
            not stat.S_ISREG(candidate_stat.st_mode)
            or not stat.S_ISREG(final_stat.st_mode)
            or candidate_stat.st_dev != final_stat.st_dev
            or candidate_stat.st_ino != final_stat.st_ino
            or candidate_stat.st_nlink != 2
            or final_stat.st_nlink != 2
        ):
            return job, True

        expected = job["revision"]
        claim_time = _parse_time(self._clock())
        job["lease"] = {
            "workerRef": _RECOVERY_WORKER_REF,
            "leaseToken": self._ref_factory("media-job-recovery-lease"),
            "leasedAt": _format_time(claim_time),
            "expiresAt": _format_time(
                claim_time + timedelta(seconds=self.lease_seconds)
            ),
        }
        job["updatedAt"] = _format_time(claim_time)
        try:
            claimed = self.repository.save(job, expected)
        except MediaJobStateError:
            current = self.repository.get(
                job["workspaceRef"], job["productionRunRef"], job["jobRef"]
            )
            if current is None:
                raise
            return current, False
        try:
            self._artifact_recovery.complete_linked_publication(candidate, final)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        return claimed, True

    def _verify_final_from_intent(
        self, job: Mapping[str, Any], intent: Mapping[str, Any]
    ) -> dict[str, Any]:
        _validate_artifact_commit_intent(intent, job)
        attempt_number = intent["attemptNumber"]
        expected_candidate, expected_final = self._attempt_paths(job, attempt_number)
        try:
            candidate_key = self._artifact_recovery.storage_key(expected_candidate)
            final_key = self._artifact_recovery.storage_key(expected_final)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        if (
            intent["candidateStorageKey"] != candidate_key
            or intent["finalStorageKey"] != final_key
        ):
            raise ArtifactVerificationError(
                "artifact commit intent path identity changed"
            )
        try:
            final_path = self._artifact_recovery.path_from_storage_key(
                intent["finalStorageKey"], require_regular_file=True
            )
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        artifact = deepcopy(dict(intent["artifact"]))
        if (
            artifact.get("internalPath") != str(final_path)
            or artifact.get("storageKey") != intent["finalStorageKey"]
        ):
            raise ArtifactVerificationError("artifact commit path changed")
        if os.lstat(final_path).st_nlink != 1:
            raise ArtifactVerificationError("artifact commit has an unsafe hard link")
        content_digest, content_size = _file_digest_and_size(final_path)
        if (
            content_digest != artifact.get("sha256")
            or content_size != artifact.get("byteSize")
        ):
            raise ArtifactVerificationError("artifact commit bytes changed")
        probe = verify_media_against_request(final_path, job["request"])
        if probe != artifact.get("probe"):
            raise ArtifactVerificationError("artifact commit probe changed")
        self._validate_recovery_execution(artifact, job["request"])
        return artifact

    def _quarantine_intent_artifacts(
        self,
        job: Mapping[str, Any],
        intent: Mapping[str, Any],
        *,
        reason: str,
    ) -> tuple[list[str], bool]:
        quarantined: list[str] = []
        unsafe = False
        candidate_key = intent.get("candidateStorageKey")
        final_key = intent.get("finalStorageKey")
        if isinstance(candidate_key, str) and isinstance(final_key, str):
            try:
                candidate_path = self._artifact_recovery.path_from_storage_key(
                    candidate_key
                )
                final_path = self._artifact_recovery.path_from_storage_key(final_key)
                if os.path.lexists(candidate_path) and os.path.lexists(final_path):
                    candidate_stat = os.lstat(candidate_path)
                    final_stat = os.lstat(final_path)
                    if (
                        stat.S_ISREG(candidate_stat.st_mode)
                        and stat.S_ISREG(final_stat.st_mode)
                        and candidate_stat.st_dev == final_stat.st_dev
                        and candidate_stat.st_ino == final_stat.st_ino
                        and candidate_stat.st_nlink == 2
                        and final_stat.st_nlink == 2
                    ):
                        self._artifact_recovery.complete_linked_publication(
                            candidate_path, final_path
                        )
            except (OSError, ArtifactRecoveryStoreError):
                unsafe = True
        for field in ("finalStorageKey", "candidateStorageKey"):
            storage_key = intent.get(field)
            if not isinstance(storage_key, str):
                unsafe = True
                continue
            try:
                source = self._artifact_recovery.path_from_storage_key(storage_key)
                if not os.path.lexists(source):
                    continue
                result = self._artifact_recovery.quarantine(
                    job["workspaceRef"],
                    job["productionRunRef"],
                    storage_key,
                    category="recovery",
                    reason=reason,
                )
                quarantined.append(result["storageKey"])
            except ArtifactRecoveryStoreError:
                unsafe = True
        return quarantined, unsafe

    def _quarantine_after_recovery_save(
        self,
        saved: dict[str, Any],
        intent: Mapping[str, Any],
        *,
        reason: str,
        clear_commit_intent: bool = False,
        next_state: str | None = None,
    ) -> dict[str, Any]:
        quarantined, unsafe = self._quarantine_intent_artifacts(
            saved, intent, reason=reason
        )
        if not quarantined and (unsafe or not clear_commit_intent):
            return saved
        expected = saved["revision"]
        if saved["attempts"]:
            existing_quarantine = saved["attempts"][-1].get(
                "quarantineStorageKeys", []
            )
            combined_quarantine = list(existing_quarantine)
            combined_quarantine.extend(
                key for key in quarantined if key not in combined_quarantine
            )
            saved["attempts"][-1].update(
                {
                    "quarantineStorageKeys": combined_quarantine,
                }
            )
        if clear_commit_intent and not unsafe:
            saved["artifactCommitIntent"] = None
            if next_state is not None:
                saved["state"] = next_state
        saved["updatedAt"] = self._clock()
        try:
            return self.repository.save(saved, expected)
        except MediaJobStateError:
            current = self.repository.get(
                saved["workspaceRef"],
                saved["productionRunRef"],
                saved["jobRef"],
            )
            if current is None:
                raise
            return current

    def _recover_commit_intent(self, job: dict[str, Any]) -> dict[str, Any]:
        intent = job.get("artifactCommitIntent")
        if not isinstance(intent, Mapping):
            raise ArtifactVerificationError("artifact commit intent is missing")
        job, owns_repair = self._repair_interrupted_publication(job, intent)
        if not owns_repair:
            return job
        intent = job.get("artifactCommitIntent")
        if not isinstance(intent, Mapping):
            return job
        expected = job["revision"]
        try:
            artifact = self._verify_final_from_intent(job, intent)
            candidate_path = self._artifact_recovery.path_from_storage_key(
                intent["candidateStorageKey"]
            )
            if os.path.lexists(candidate_path):
                raise ArtifactVerificationError(
                    "candidate remained after final artifact publication"
                )
        except (ArtifactVerificationError, ArtifactRecoveryStoreError):
            next_state = (
                "FAILED"
                if len(job["attempts"]) >= job["maxAttempts"]
                else "QUEUED"
            )
            if job["attempts"] and job["attempts"][-1].get("state") == "RUNNING":
                job["attempts"][-1].update(
                    {
                        "state": "FAILED",
                        "finishedAt": self._clock(),
                        "errorCode": "artifact_recovery_mismatch",
                        "artifactCommitIntentDigest": intent["intentDigest"],
                        "quarantineStorageKeys": [],
                    }
                )
            job.update(
                {
                    "state": "FAILED",
                    "lease": None,
                    "artifact": None,
                    "updatedAt": self._clock(),
                }
            )
            try:
                saved = self.repository.save(job, expected)
            except MediaJobStateError:
                current = self.repository.get(
                    job["workspaceRef"], job["productionRunRef"], job["jobRef"]
                )
                if current is None:
                    raise
                return current
            return self._quarantine_after_recovery_save(
                saved,
                intent,
                reason="artifact_commit_recovery_failed",
                clear_commit_intent=True,
                next_state=next_state,
            )

        attempt_result = {
            "state": "SUCCEEDED",
            "finishedAt": self._clock(),
            "artifactSha256": artifact["sha256"],
            "artifactCommitIntentDigest": intent["intentDigest"],
            "recoveredFromCommitIntent": True,
        }
        if "providerExecution" in artifact:
            attempt_result["providerExecution"] = deepcopy(
                artifact["providerExecution"]
            )
        job["attempts"][-1].update(attempt_result)
        job.update(
            {
                "state": "SUCCEEDED",
                "lease": None,
                "artifact": artifact,
                "artifactCommitIntent": None,
                "updatedAt": self._clock(),
            }
        )
        try:
            return self.repository.save(job, expected)
        except MediaJobStateError:
            current = self.repository.get(
                job["workspaceRef"], job["productionRunRef"], job["jobRef"]
            )
            if current is None:
                raise
            return current

    def dispatch(
        self, request: Mapping[str, Any], *, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        _validate_request(request)
        if not isinstance(idempotency_key, str) or not idempotency_key:
            raise MediaJobError("dispatch idempotency key is invalid")
        now = self._clock()
        job = {
            "schemaVersion": JOB_SCHEMA_VERSION,
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "jobRef": self._ref_factory("media-job"),
            "idempotencyKey": idempotency_key,
            "requestDigest": request["payloadDigest"],
            "request": deepcopy(dict(request)),
            "state": "QUEUED",
            "revision": 0,
            "attempts": [],
            "lease": None,
            "artifact": None,
            "artifactCommitIntent": None,
            "maxAttempts": self.max_attempts,
            "executionScope": "SINGLE_EPISODE",
            "batchProductionAllowed": False,
            "createdAt": now,
            "updatedAt": now,
        }
        return self.repository.create(job)

    def recover_expired(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        recovered = []
        now = _parse_time(self._clock())
        for job in self.repository.list(workspace_ref, run_ref):
            pending_cleanup = job.get("artifactCommitIntent")
            if job["state"] in {"FAILED", "CANCELLED"} and isinstance(
                pending_cleanup, Mapping
            ):
                next_state = (
                    "CANCELLED"
                    if job["state"] == "CANCELLED"
                    else (
                        "FAILED"
                        if len(job["attempts"]) >= job["maxAttempts"]
                        else "QUEUED"
                    )
                )
                recovered.append(
                    self._quarantine_after_recovery_save(
                        job,
                        pending_cleanup,
                        reason=(
                            "media_job_cancelled_during_commit"
                            if job["state"] == "CANCELLED"
                            else "artifact_commit_recovery_failed"
                        ),
                        clear_commit_intent=True,
                        next_state=next_state,
                    )
                )
                continue
            if job["state"] == "RETRYING":
                expected = job["revision"]
                job.update(
                    {
                        "state": (
                            "FAILED"
                            if len(job["attempts"]) >= job["maxAttempts"]
                            else "QUEUED"
                        ),
                        "lease": None,
                        "updatedAt": self._clock(),
                    }
                )
                try:
                    recovered.append(self.repository.save(job, expected))
                except MediaJobStateError:
                    pass
                continue
            lease = job.get("lease")
            if job["state"] not in {"LEASED", "RUNNING"} or not isinstance(lease, Mapping):
                continue
            if _parse_time(lease["expiresAt"]) > now:
                continue
            if job["state"] == "RUNNING" and isinstance(
                job.get("artifactCommitIntent"), Mapping
            ):
                recovered.append(self._recover_commit_intent(job))
                continue
            expected = job["revision"]
            error_code = "lease_expired"
            synthetic_intent: dict[str, str] | None = None
            if job["attempts"] and job["attempts"][-1].get("state") == "RUNNING":
                attempt_number = job["attempts"][-1].get("attemptNumber")
                if isinstance(attempt_number, int) and not isinstance(
                    attempt_number, bool
                ):
                    try:
                        candidate_path, final_path = self._attempt_paths(
                            job, attempt_number
                        )
                        synthetic_intent = {
                            "candidateStorageKey": self._artifact_recovery.storage_key(
                                candidate_path
                            ),
                            "finalStorageKey": self._artifact_recovery.storage_key(
                                final_path
                            ),
                        }
                    except (ArtifactVerificationError, ArtifactRecoveryStoreError):
                        error_code = "artifact_recovery_unsafe"
                job["attempts"][-1].update(
                    {
                        "state": "FAILED",
                        "errorCode": error_code,
                        "finishedAt": self._clock(),
                        "quarantineStorageKeys": [],
                    }
                )
            job.update(
                {
                    "state": (
                        "FAILED"
                        if len(job["attempts"]) >= job["maxAttempts"]
                        else "QUEUED"
                    ),
                    "lease": None,
                    "artifactCommitIntent": None,
                    "updatedAt": self._clock(),
                }
            )
            try:
                saved = self.repository.save(job, expected)
            except MediaJobStateError:
                continue
            if synthetic_intent is not None:
                saved = self._quarantine_after_recovery_save(
                    saved,
                    synthetic_intent,
                    reason="expired_attempt_without_commit_intent",
                )
            recovered.append(saved)
        return recovered

    def lease_next(
        self, workspace_ref: str, run_ref: str, worker_ref: str
    ) -> dict[str, Any] | None:
        self.recover_expired(workspace_ref, run_ref)
        for job in self.repository.list(workspace_ref, run_ref):
            if job["state"] != "QUEUED":
                continue
            if len(job["attempts"]) >= job["maxAttempts"]:
                expected = job["revision"]
                job.update(
                    {
                        "state": "FAILED",
                        "lease": None,
                        "updatedAt": self._clock(),
                    }
                )
                try:
                    self.repository.save(job, expected)
                except MediaJobStateError:
                    pass
                continue
            expected = job["revision"]
            now = _parse_time(self._clock())
            job.update(
                {
                    "schemaVersion": JOB_SCHEMA_VERSION,
                    "state": "LEASED",
                    "lease": {
                        "workerRef": worker_ref,
                        "leaseToken": self._ref_factory("media-job-lease"),
                        "leasedAt": _format_time(now),
                        "expiresAt": _format_time(now + timedelta(seconds=self.lease_seconds)),
                    },
                    "updatedAt": self._clock(),
                }
            )
            try:
                return self.repository.save(job, expected)
            except MediaJobStateError:
                continue
        return None

    def cancel(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any]:
        job = self.repository.get(workspace_ref, run_ref, job_ref)
        if job is None:
            raise MediaJobError("media job not found")
        if job["state"] in {"SUCCEEDED", "CANCELLED"}:
            raise MediaJobStateError("terminal media job cannot be cancelled")
        expected = job["revision"]
        intent = job.get("artifactCommitIntent")
        if isinstance(intent, Mapping) and job["state"] != "RUNNING":
            raise MediaJobStateError(
                "media job artifact cleanup must finish before cancellation"
            )
        job.update({"state": "CANCELLED", "lease": None, "updatedAt": self._clock()})
        if job["attempts"] and job["attempts"][-1].get("state") == "RUNNING":
            job["attempts"][-1].update(
                {
                    "state": "CANCELLED",
                    "finishedAt": self._clock(),
                    "artifactCommitIntentDigest": (
                        intent.get("intentDigest")
                        if isinstance(intent, Mapping)
                        else None
                    ),
                    "quarantineStorageKeys": [],
                }
            )
        saved = self.repository.save(job, expected)
        if not isinstance(intent, Mapping):
            return saved
        return self._quarantine_after_recovery_save(
            saved,
            intent,
            reason="media_job_cancelled_during_commit",
            clear_commit_intent=True,
            next_state="CANCELLED",
        )

    def retry(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any]:
        job = self.repository.get(workspace_ref, run_ref, job_ref)
        if job is None or job["state"] != "FAILED":
            raise MediaJobStateError("only failed media jobs may retry")
        if isinstance(job.get("artifactCommitIntent"), Mapping):
            raise MediaJobStateError(
                "media job artifact cleanup must finish before retry"
            )
        if len(job["attempts"]) >= job["maxAttempts"]:
            raise MediaJobStateError("media job retry limit reached")
        expected = job["revision"]
        job.update({"state": "QUEUED", "lease": None, "updatedAt": self._clock()})
        return self.repository.save(job, expected)

    def run_leased(self, job: Mapping[str, Any], worker_ref: str) -> dict[str, Any]:
        current = self.repository.get(
            job["workspaceRef"], job["productionRunRef"], job["jobRef"]
        )
        supplied_lease = job.get("lease")
        current_lease = current.get("lease") if current is not None else None
        if (
            current is None
            or job.get("state") != "LEASED"
            or current["state"] != "LEASED"
            or current.get("revision") != job.get("revision")
            or not isinstance(supplied_lease, Mapping)
            or not isinstance(current_lease, Mapping)
            or dict(current_lease) != dict(supplied_lease)
            or current_lease.get("workerRef") != worker_ref
            or _parse_time(current_lease["expiresAt"])
            <= _parse_time(self._clock())
        ):
            raise MediaJobStateError("valid worker lease is required")
        if len(current["attempts"]) >= current["maxAttempts"]:
            raise MediaJobStateError("media job attempt limit reached")
        request = current["request"]
        if self.adapter.provenance != request["requestedProvenance"]:
            raise MediaJobStateError(
                "worker adapter provenance does not match the generation request"
            )
        expected = current["revision"]
        attempt_number = len(current["attempts"]) + 1
        attempt = {
            "attemptRef": self._ref_factory("media-job-attempt"),
            "attemptNumber": attempt_number,
            "workerRef": worker_ref,
            "adapterIdentity": self.adapter.adapter_identity,
            "state": "RUNNING",
            "startedAt": self._clock(),
        }
        current["attempts"].append(attempt)
        if current["schemaVersion"] == LEGACY_JOB_SCHEMA_VERSION:
            current["lease"] = {
                **dict(current["lease"]),
                "leaseToken": self._ref_factory("media-job-lease"),
            }
        current.update(
            {
                "schemaVersion": JOB_SCHEMA_VERSION,
                "state": "RUNNING",
                "artifactCommitIntent": None,
                "updatedAt": self._clock(),
            }
        )
        current = self.repository.save(current, expected)
        lease = current.get("lease")
        if not isinstance(lease, Mapping) or not isinstance(
            lease.get("leaseToken"), str
        ):
            raise MediaJobStateError("worker lease token is missing")
        attempt_lease_token = lease["leaseToken"]
        candidate_path, final_path = self._attempt_paths(current, attempt_number)
        intent_persisted = False
        heartbeat: tuple[Event, Thread, list[BaseException]] | None = None
        heartbeat_job: dict[str, Any] | None = None
        try:
            heartbeat_job = deepcopy(current)
            heartbeat = self._start_lease_heartbeat(
                heartbeat_job, worker_ref, attempt["attemptRef"]
            )
            try:
                self._artifact_recovery.require_absent(candidate_path)
                self._artifact_recovery.require_absent(final_path)
            except ArtifactRecoveryStoreError as exc:
                raise ArtifactVerificationError(str(exc)) from exc
            produced = self.adapter.generate(request, candidate_path)
            execution: dict[str, Any] | None = None
            if isinstance(produced, MediaAdapterResult):
                produced_value = produced.path
                if request["requestedProvenance"] == "LIVE_PROVIDER":
                    execution = _validate_live_execution(
                        produced.execution, request
                    )
                elif request["requestedProvenance"] == M11_VIDEO_PROVENANCE:
                    execution = _validate_m11_execution(
                        produced.execution, request
                    )
                else:
                    raise ArtifactVerificationError(
                        "local request returned live provider execution evidence"
                    )
            else:
                produced_value = produced
                if request["requestedProvenance"] != "LOCAL_EVIDENCE":
                    raise ArtifactVerificationError(
                        "live provider request omitted execution evidence"
                    )
            produced_path = self._safe_path(
                current["workspaceRef"], current["productionRunRef"],
                Path(produced_value),
            )
            try:
                produced_path = self._artifact_recovery.scoped_path(
                    current["workspaceRef"],
                    current["productionRunRef"],
                    produced_path,
                    require_regular_file=True,
                )
            except ArtifactRecoveryStoreError as exc:
                raise ArtifactVerificationError(str(exc)) from exc
            if produced_path != candidate_path:
                raise ArtifactVerificationError("adapter returned an unexpected artifact")
            probe = verify_media_against_request(produced_path, request)
            content_digest, content_size = _file_digest_and_size(produced_path)
            provenance = request["requestedProvenance"]
            try:
                final_storage_key = self._artifact_recovery.storage_key(final_path)
            except ArtifactRecoveryStoreError as exc:
                raise ArtifactVerificationError(str(exc)) from exc
            artifact = {
                "schemaVersion": ARTIFACT_SCHEMA_VERSION,
                "workspaceRef": current["workspaceRef"],
                "productionRunRef": current["productionRunRef"],
                "jobRef": current["jobRef"],
                "attemptRef": attempt["attemptRef"],
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestVersionRef": request["generationRequestVersionRef"],
                "generationRequestDigest": request["payloadDigest"],
                "mediaKind": request["mediaKind"],
                "mediaType": request["mediaType"],
                "internalPath": str(final_path),
                "storageKey": final_storage_key,
                "byteSize": content_size,
                "sha256": content_digest,
                "probe": probe,
                "adapterIdentity": self.adapter.adapter_identity,
                "provenance": provenance,
                "executionDevice": (
                    execution["executionDevice"] if execution is not None
                    else "CPU_FFMPEG"
                ),
                "gpuUsed": execution is not None,
                "publicationAllowed": False,
                "createdAt": self._clock(),
            }
            if execution is not None:
                artifact["providerExecution"] = deepcopy(execution)
            current = self._stop_lease_heartbeat(
                heartbeat,
                heartbeat_job,
                worker_ref,
                attempt["attemptRef"],
            )
            heartbeat = None
            expected = current["revision"]
            commit_intent = self._build_commit_intent(
                current, attempt, candidate_path, final_path, artifact
            )
            current["artifactCommitIntent"] = commit_intent
            current["updatedAt"] = self._clock()
            current = self.repository.save(current, expected)
            intent_persisted = True
            heartbeat_job = deepcopy(current)
            heartbeat = self._start_lease_heartbeat(
                heartbeat_job, worker_ref, attempt["attemptRef"]
            )

            def assert_publication_fence() -> None:
                self._active_worker_job(
                    current["workspaceRef"],
                    current["productionRunRef"],
                    current["jobRef"],
                    worker_ref,
                    attempt_lease_token,
                    attempt["attemptRef"],
                )

            try:
                self._artifact_recovery.durable_replace(
                    produced_path,
                    final_path,
                    assert_fence=assert_publication_fence,
                )
            except ArtifactRecoveryStoreError as exc:
                raise ArtifactVerificationError(str(exc)) from exc
            artifact = self._verify_final_from_intent(current, commit_intent)
            current = self._stop_lease_heartbeat(
                heartbeat,
                heartbeat_job,
                worker_ref,
                attempt["attemptRef"],
            )
            heartbeat = None
            expected = current["revision"]
            attempt_result = {
                "state": "SUCCEEDED",
                "finishedAt": self._clock(),
                "artifactSha256": artifact["sha256"],
                "artifactCommitIntentDigest": commit_intent["intentDigest"],
            }
            if execution is not None:
                attempt_result["providerExecution"] = deepcopy(execution)
            current["attempts"][-1].update(attempt_result)
            current.update(
                {
                    "state": "SUCCEEDED",
                    "lease": None,
                    "artifact": artifact,
                    "artifactCommitIntent": None,
                    "updatedAt": self._clock(),
                }
            )
            return self.repository.save(current, expected)
        except BaseException as exc:
            if heartbeat is not None:
                heartbeat[0].set()
                heartbeat[1].join(
                    timeout=max(
                        1.0,
                        min(self.heartbeat_interval_seconds * 2, 15.0),
                    )
                )
                if heartbeat[1].is_alive():
                    raise MediaJobStateError(
                        "worker lease heartbeat did not stop"
                    ) from exc
            if not isinstance(exc, Exception):
                raise
            if intent_persisted:
                raise
            try:
                refreshed = self._active_worker_job(
                    current["workspaceRef"],
                    current["productionRunRef"],
                    current["jobRef"],
                    worker_ref,
                    attempt_lease_token,
                    attempt["attemptRef"],
                )
            except MediaJobStateError:
                raise MediaJobStateError("worker lease was fenced") from exc
            if isinstance(refreshed.get("artifactCommitIntent"), Mapping):
                raise MediaJobStateError(
                    "worker artifact commit state changed"
                ) from exc
            current = refreshed
            current["artifactCommitIntent"] = None
            synthetic_intent: dict[str, str] | None = None
            error_code = getattr(exc, "code", "adapter_failed")
            try:
                synthetic_intent = {
                    "candidateStorageKey": self._artifact_recovery.storage_key(
                        candidate_path
                    ),
                    "finalStorageKey": self._artifact_recovery.storage_key(
                        final_path
                    ),
                }
            except (ArtifactVerificationError, ArtifactRecoveryStoreError):
                error_code = ArtifactVerificationError.code
            expected = current["revision"]
            current["attempts"][-1].update(
                {
                    "state": "FAILED", "finishedAt": self._clock(),
                    "errorCode": error_code,
                    "quarantineStorageKeys": [],
                }
            )
            current.update({"state": "FAILED", "lease": None, "updatedAt": self._clock()})
            saved = self.repository.save(current, expected)
            if synthetic_intent is None:
                return saved
            return self._quarantine_after_recovery_save(
                saved,
                synthetic_intent,
                reason="media_attempt_failed_before_commit",
            )

    def execute_batch(
        self,
        workspace_ref: str,
        run_ref: str,
        requests: list[Mapping[str, Any]],
        *,
        batch_idempotency_key: str,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(batch_idempotency_key, str)
            or not batch_idempotency_key
            or not isinstance(requests, list)
            or not requests
        ):
            raise MediaJobError("media batch identity is invalid")
        members: list[dict[str, Any]] = []
        for position, request in enumerate(requests, start=1):
            _validate_request(request)
            if request.get("workspaceRef") != workspace_ref or request.get("productionRunRef") != run_ref:
                raise MediaJobError("generation request scope mismatch")
            members.append(
                {
                    "position": position,
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                }
            )
        batch = {
            "schemaVersion": MEDIA_BATCH_SCHEMA_VERSION,
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "batchIdempotencyKey": batch_idempotency_key,
            "members": members,
        }
        batch["payloadDigest"] = _digest(batch)
        self.repository.reserve_batch(batch)
        expected_job_keys: set[str] = set()
        for request in requests:
            child_key = _digest(
                {
                    "batchIdempotencyKey": batch_idempotency_key,
                    "generationRequestRef": request["generationRequestRef"],
                }
            )
            expected_job_keys.add(child_key)
            self.dispatch(
                request,
                idempotency_key=child_key,
            )
        worker_ref = (
            "v4-media-worker-"
            + sha256(self.adapter.adapter_identity.encode("utf-8")).hexdigest()[:16]
        )
        while True:
            leased = self.lease_next(workspace_ref, run_ref, worker_ref)
            if leased is None:
                break
            result = self.run_leased(leased, worker_ref)
            if result["state"] == "FAILED" and len(result["attempts"]) < result["maxAttempts"]:
                self.retry(workspace_ref, run_ref, result["jobRef"])
        jobs = self.repository.list(workspace_ref, run_ref)
        selected = [
            job for job in jobs
            if job["idempotencyKey"] in expected_job_keys
        ]
        if len(selected) != len(requests):
            raise MediaAdapterUnavailableError("media batch did not complete")
        failed = [job for job in selected if job["state"] != "SUCCEEDED"]
        if failed:
            if any(
                job.get("attempts")
                and job["attempts"][-1].get("errorCode")
                == ArtifactVerificationError.code
                for job in failed
            ):
                raise ArtifactVerificationError(
                    "media batch candidate verification failed"
                )
            raise MediaAdapterUnavailableError("media batch did not complete")
        return sorted(
            selected, key=lambda item: item["request"]["ordinal"]
        )

    def _referenced_storage_keys(
        self, workspace_ref: str, run_ref: str
    ) -> set[str]:
        referenced: set[str] = set()
        for job in self.repository.list(workspace_ref, run_ref):
            artifact = job.get("artifact")
            if isinstance(artifact, Mapping) and isinstance(
                artifact.get("storageKey"), str
            ):
                referenced.add(artifact["storageKey"])
            intent = job.get("artifactCommitIntent")
            if job["state"] == "RUNNING" and isinstance(intent, Mapping):
                for field in ("candidateStorageKey", "finalStorageKey"):
                    if isinstance(intent.get(field), str):
                        referenced.add(intent[field])
            if (
                job["state"] == "RUNNING"
                and job["attempts"]
                and job["attempts"][-1].get("state") == "RUNNING"
            ):
                try:
                    candidate, final = self._attempt_paths(
                        job,
                        job["attempts"][-1]["attemptNumber"],
                        create=False,
                    )
                    referenced.add(self._artifact_recovery.storage_key(candidate))
                    referenced.add(self._artifact_recovery.storage_key(final))
                except (ArtifactVerificationError, ArtifactRecoveryStoreError):
                    continue
        return referenced

    def inventory_artifacts(
        self, workspace_ref: str, run_ref: str
    ) -> list[dict[str, Any]]:
        """Return a sanitized, read-only inventory for one exact production run."""

        referenced = self._referenced_storage_keys(workspace_ref, run_ref)
        try:
            entries = self._artifact_recovery.inventory(
                workspace_ref, run_ref, referenced
            )
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        by_key = {entry["storageKey"]: entry for entry in entries}
        for job in self.repository.list(workspace_ref, run_ref):
            if job["state"] != "SUCCEEDED" or not isinstance(
                job.get("artifact"), Mapping
            ):
                continue
            artifact = job["artifact"]
            storage_key = artifact.get("storageKey")
            if not isinstance(storage_key, str):
                continue
            try:
                expected_path = self._artifact_recovery.path_from_storage_key(
                    storage_key
                )
                internal_path_matches = artifact.get("internalPath") == str(
                    expected_path
                )
            except ArtifactRecoveryStoreError:
                internal_path_matches = False
            entry = by_key.get(storage_key)
            if entry is None:
                entry = {
                    "storageKey": storage_key,
                    "entryType": "MISSING",
                    "inventoryState": "INTEGRITY_BLOCKED",
                    "referenced": True,
                    "sha256": None,
                    "byteSize": None,
                }
                entries.append(entry)
                by_key[storage_key] = entry
            elif (
                entry.get("entryType") != "REGULAR_FILE"
                or entry.get("sha256") != artifact.get("sha256")
                or entry.get("byteSize") != artifact.get("byteSize")
                or not internal_path_matches
            ):
                entry["inventoryState"] = "INTEGRITY_BLOCKED"
            entry["jobRef"] = job["jobRef"]
        return sorted(entries, key=lambda item: item["storageKey"])

    def inventory_orphan_artifacts(
        self, workspace_ref: str, run_ref: str
    ) -> list[dict[str, Any]]:
        return [
            entry
            for entry in self.inventory_artifacts(workspace_ref, run_ref)
            if not entry["referenced"]
            and entry["inventoryState"] in {"ORPHAN", "UNSAFE"}
        ]

    def list_orphan_artifacts(
        self, workspace_ref: str, run_ref: str
    ) -> list[dict[str, Any]]:
        """Compatibility alias for the explicit orphan inventory operation."""

        return self.inventory_orphan_artifacts(workspace_ref, run_ref)

    def quarantine_orphan_artifact(
        self,
        workspace_ref: str,
        run_ref: str,
        storage_key: str,
        *,
        reason: str = "orphan_artifact",
    ) -> dict[str, Any]:
        """Move one still-unreferenced regular file; never delete or follow links."""

        if storage_key in self._referenced_storage_keys(workspace_ref, run_ref):
            raise MediaJobStateError("referenced artifact cannot be quarantined")
        try:
            return self._artifact_recovery.quarantine(
                workspace_ref,
                run_ref,
                storage_key,
                category="orphans",
                reason=reason,
            )
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc

    def reconcile_artifacts(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        """Inventory only; quarantine remains an explicit, non-destructive command."""

        inventory = self.inventory_artifacts(workspace_ref, run_ref)
        return {
            "schemaVersion": "v4.media-artifact-inventory.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": run_ref,
            "artifacts": inventory,
            "orphanCount": sum(
                1
                for item in inventory
                if not item["referenced"]
                and item["inventoryState"] in {"ORPHAN", "UNSAFE"}
            ),
            "integrityBlockerCount": sum(
                1
                for item in inventory
                if item["inventoryState"] == "INTEGRITY_BLOCKED"
            ),
            "publicationAllowed": False,
        }

    def list_jobs(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        return self.repository.list(workspace_ref, run_ref)
