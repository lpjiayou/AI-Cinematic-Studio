"""V4 single-episode media queue, worker lifecycle and local evidence adapter."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from threading import RLock
from typing import Any, Callable, Mapping, Protocol


JOB_SCHEMA_VERSION = "v4.media-job.v1"
ARTIFACT_SCHEMA_VERSION = "v4.media-artifact-handoff.v1"
M11_VIDEO_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-video-request.v1"
M11_VIDEO_CAPABILITY = "self-hosted-wan22-image-to-video-v1"
M11_VIDEO_PROVENANCE = "SELF_HOSTED_AI_GENERATED"


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


def _hex_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_m11_video_request(request: Mapping[str, Any]) -> None:
    fields = {
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
    parameters = request.get("parameters")
    prompt_spec = request.get("promptSpec")
    source_probe = request.get("sourceImageProbe")
    if (
        set(request) != fields
        or request.get("schemaVersion") != M11_VIDEO_REQUEST_SCHEMA_VERSION
        or _digest({k: v for k, v in request.items() if k != "payloadDigest"})
        != request.get("payloadDigest")
        or request.get("version") != 1
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
        or isinstance(source_probe.get("width"), bool)
        or not isinstance(source_probe.get("width"), int)
        or source_probe["width"] < 32
        or isinstance(source_probe.get("height"), bool)
        or not isinstance(source_probe.get("height"), int)
        or source_probe["height"] < 32
        or not isinstance(prompt_spec, Mapping)
        or set(prompt_spec)
        != {"cameraInstruction", "action", "continuityConstraints"}
        or not isinstance(prompt_spec.get("cameraInstruction"), Mapping)
        or not isinstance(prompt_spec.get("action"), str)
        or not prompt_spec["action"].strip()
        or len(prompt_spec["action"]) > 2000
        or not isinstance(prompt_spec.get("continuityConstraints"), list)
        or not all(
            isinstance(item, str) and item.strip() and len(item) <= 1000
            for item in prompt_spec["continuityConstraints"]
        )
        or len(_canonical(prompt_spec)) > 8_000
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
        or len(parameters["negativePrompt"]) > 4000
    ):
        raise MediaJobError("invalid exact M11 video generation request")


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    digest = sha256()
    size = 0
    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
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
        and request.get("schemaVersion") == M11_VIDEO_REQUEST_SCHEMA_VERSION
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


def _validate_job(job: Mapping[str, Any]) -> None:
    if (
        job.get("schemaVersion") != JOB_SCHEMA_VERSION
        or job.get("state")
        not in {
            "QUEUED", "LEASED", "RUNNING", "SUCCEEDED", "FAILED",
            "RETRYING", "CANCELLED",
        }
        or not isinstance(job.get("revision"), int)
        or not isinstance(job.get("attempts"), list)
        or not isinstance(job.get("maxAttempts"), int)
        or job.get("maxAttempts", 0) < 1
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


class InMemoryMediaJobAdapter:
    def __init__(self) -> None:
        self._jobs: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._idem: dict[tuple[str, str, str], str] = {}
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
            value["revision"] = expected_revision + 1
            self._jobs[key] = value
            return deepcopy(value)


class SqliteMediaJobAdapter:
    _TABLES = {"v4_media_job_schema", "v4_media_jobs"}
    _COLUMNS = {
        "v4_media_job_schema": ("component", "schema_version"),
        "v4_media_jobs": (
            "workspace_ref", "production_run_ref", "job_ref", "idempotency_key",
            "request_digest", "state", "revision", "payload_json",
        ),
    }

    def __init__(self, database_path: Path | str, *, initialize_if_missing: bool = True) -> None:
        self.path = Path(database_path)
        if initialize_if_missing:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        self._verify_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS v4_media_job_schema ("
                "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO v4_media_job_schema VALUES ('media_jobs',1)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS v4_media_jobs (
                workspace_ref TEXT NOT NULL,
                production_run_ref TEXT NOT NULL,
                job_ref TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(workspace_ref,production_run_ref,job_ref),
                UNIQUE(workspace_ref,production_run_ref,idempotency_key)
                )"""
            )
            connection.commit()
        finally:
            connection.close()

    def _verify_schema(self) -> None:
        connection = self._connect()
        try:
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != self._TABLES:
                raise MediaJobError("media job schema mismatch")
            for table, expected in self._COLUMNS.items():
                actual = tuple(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if actual != expected:
                    raise MediaJobError("media job schema columns mismatch")
            marker = connection.execute(
                "SELECT component,schema_version FROM v4_media_job_schema"
            ).fetchall()
            if [tuple(row) for row in marker] != [("media_jobs", 1)]:
                raise MediaJobError("media job schema marker mismatch")
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
        value["revision"] = expected_revision + 1
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
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


def probe_media(path: Path) -> dict[str, Any]:
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
    return {
        "streams": normalized,
        "formatName": payload.get("format", {}).get("format_name"),
        "durationSeconds": payload.get("format", {}).get("duration"),
    }


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
        max_attempts: int = 3,
    ) -> None:
        self.repository = repository
        self.adapter = adapter
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._ref_factory = ref_factory
        self._clock = clock
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts

    def _run_root(self, workspace_ref: str, run_ref: str) -> Path:
        workspace_hash = sha256(workspace_ref.encode()).hexdigest()[:20]
        run_hash = sha256(run_ref.encode()).hexdigest()[:20]
        root = (self.artifact_root / workspace_hash / run_hash).resolve()
        if self.artifact_root not in root.parents:
            raise ArtifactVerificationError("run artifact root escaped configured root")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _safe_path(self, workspace_ref: str, run_ref: str, candidate: Path) -> Path:
        run_root = self._run_root(workspace_ref, run_ref)
        resolved = candidate.resolve()
        if run_root not in resolved.parents:
            raise ArtifactVerificationError("worker artifact escaped run scope")
        return resolved

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
            lease = job.get("lease")
            if job["state"] not in {"LEASED", "RUNNING"} or not isinstance(lease, Mapping):
                continue
            if _parse_time(lease["expiresAt"]) > now:
                continue
            expected = job["revision"]
            if job["attempts"] and job["attempts"][-1].get("state") == "RUNNING":
                job["attempts"][-1].update(
                    {"state": "FAILED", "errorCode": "lease_expired", "finishedAt": self._clock()}
                )
            job.update({"state": "QUEUED", "lease": None, "updatedAt": self._clock()})
            recovered.append(self.repository.save(job, expected))
        return recovered

    def lease_next(
        self, workspace_ref: str, run_ref: str, worker_ref: str
    ) -> dict[str, Any] | None:
        self.recover_expired(workspace_ref, run_ref)
        for job in self.repository.list(workspace_ref, run_ref):
            if job["state"] != "QUEUED":
                continue
            expected = job["revision"]
            now = _parse_time(self._clock())
            job.update(
                {
                    "state": "LEASED",
                    "lease": {
                        "workerRef": worker_ref,
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
        job.update({"state": "CANCELLED", "lease": None, "updatedAt": self._clock()})
        if job["attempts"] and job["attempts"][-1].get("state") == "RUNNING":
            job["attempts"][-1].update(
                {"state": "CANCELLED", "finishedAt": self._clock()}
            )
        return self.repository.save(job, expected)

    def retry(self, workspace_ref: str, run_ref: str, job_ref: str) -> dict[str, Any]:
        job = self.repository.get(workspace_ref, run_ref, job_ref)
        if job is None or job["state"] != "FAILED":
            raise MediaJobStateError("only failed media jobs may retry")
        if len(job["attempts"]) >= job["maxAttempts"]:
            raise MediaJobStateError("media job retry limit reached")
        expected = job["revision"]
        job.update({"state": "RETRYING", "lease": None, "updatedAt": self._clock()})
        job = self.repository.save(job, expected)
        expected = job["revision"]
        job.update({"state": "QUEUED", "updatedAt": self._clock()})
        return self.repository.save(job, expected)

    def run_leased(self, job: Mapping[str, Any], worker_ref: str) -> dict[str, Any]:
        current = self.repository.get(
            job["workspaceRef"], job["productionRunRef"], job["jobRef"]
        )
        if (
            current is None
            or current["state"] != "LEASED"
            or current.get("lease", {}).get("workerRef") != worker_ref
        ):
            raise MediaJobStateError("valid worker lease is required")
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
        current.update({"state": "RUNNING", "updatedAt": self._clock()})
        current = self.repository.save(current, expected)
        extension = ".mp4" if request["mediaKind"] == "video" else ".wav"
        run_root = self._run_root(current["workspaceRef"], current["productionRunRef"])
        request_hash = sha256(request["generationRequestRef"].encode()).hexdigest()[:20]
        directory = run_root / "jobs" / request_hash
        final_path = directory / f"attempt-{attempt_number}{extension}"
        candidate_path = directory / f"attempt-{attempt_number}.part{extension}"
        try:
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
            if produced_path != candidate_path.resolve() or not produced_path.is_file():
                raise ArtifactVerificationError("adapter returned an unexpected artifact")
            probe = verify_media_against_request(produced_path, request)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            produced_path.replace(final_path)
            safe_final = self._safe_path(
                current["workspaceRef"], current["productionRunRef"], final_path
            )
            content_digest, content_size = _file_digest_and_size(safe_final)
            provenance = request["requestedProvenance"]
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
                "internalPath": str(safe_final),
                "storageKey": str(safe_final.relative_to(self.artifact_root)),
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
            expected = current["revision"]
            attempt_result = {
                "state": "SUCCEEDED",
                "finishedAt": self._clock(),
                "artifactSha256": artifact["sha256"],
            }
            if execution is not None:
                attempt_result["providerExecution"] = deepcopy(execution)
            current["attempts"][-1].update(attempt_result)
            current.update(
                {"state": "SUCCEEDED", "lease": None, "artifact": artifact, "updatedAt": self._clock()}
            )
            return self.repository.save(current, expected)
        except Exception as exc:
            if candidate_path.exists():
                quarantine = run_root / "quarantine"
                quarantine.mkdir(parents=True, exist_ok=True)
                candidate_path.replace(
                    quarantine / f"{current['jobRef']}-{attempt_number}.failed{extension}"
                )
            expected = current["revision"]
            current["attempts"][-1].update(
                {
                    "state": "FAILED", "finishedAt": self._clock(),
                    "errorCode": getattr(exc, "code", "adapter_failed"),
                }
            )
            current.update({"state": "FAILED", "lease": None, "updatedAt": self._clock()})
            return self.repository.save(current, expected)

    def execute_batch(
        self,
        workspace_ref: str,
        run_ref: str,
        requests: list[Mapping[str, Any]],
        *,
        batch_idempotency_key: str,
    ) -> list[dict[str, Any]]:
        for request in requests:
            if request.get("workspaceRef") != workspace_ref or request.get("productionRunRef") != run_ref:
                raise MediaJobError("generation request scope mismatch")
            self.dispatch(
                request,
                idempotency_key=_digest(
                    {
                        "batchIdempotencyKey": batch_idempotency_key,
                        "generationRequestRef": request["generationRequestRef"],
                    }
                ),
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
        relevant = {
            request["generationRequestRef"] for request in requests
        }
        selected = [
            job for job in jobs
            if job["request"]["generationRequestRef"] in relevant
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

    def list_jobs(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        return self.repository.list(workspace_ref, run_ref)
