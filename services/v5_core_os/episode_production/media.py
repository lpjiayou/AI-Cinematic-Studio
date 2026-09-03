"""Read/replay compatibility for immutable legacy K2 G5 evidence.

Historic GenerationResult v1, AssetVersion v1 and MediaManifest v1 facts stay
fully readable.  New worker dispatch and G5 evidence writes are closed.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from services.v4_platform import (
    ArtifactVerificationError as V4ArtifactVerificationError,
    MediaJobError as V4MediaJobError,
    verify_media_against_request,
)

from .assets import K2AssetPipelineService
from .audio import reject_speech_synthesis_in_legacy_media
from .evidence import EpisodeProductionEvidenceRepository
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .shot_graph import require_legacy_executable_graph


MEDIA_EXECUTION_GATE = "G5_MEDIA_EXECUTION"
LEGACY_K2_G5_COMPATIBILITY_V1 = "LEGACY_K2_G5_COMPATIBILITY_V1"
GENERATION_RESULT_SCHEMA_VERSION = "v5.generation-result.v1"
ASSET_VERSION_SCHEMA_VERSION = "v5.asset-version.v1"
MEDIA_MANIFEST_SCHEMA_VERSION = "v5.media-manifest.v1"
ADMISSION_ID = "v5.k2.media-admission.v1"


class WorkerUnavailableError(EpisodeProductionError):
    code = "worker_unavailable"


class ArtifactRejectedError(EpisodeProductionError):
    code = "artifact_verification_failed"


class LegacyMediaExecutionWriteDisabledError(EpisodeProductionError):
    code = "legacy_media_execution_write_disabled"


class MediaExecutionPort(Protocol):
    artifact_root: Path

    def execute_batch(
        self,
        workspace_ref: str,
        run_ref: str,
        requests: list[Mapping[str, Any]],
        *,
        batch_idempotency_key: str,
    ) -> list[dict[str, Any]]: ...

    def list_jobs(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]: ...


class RejectingMediaExecution:
    artifact_root = Path("/")

    def dispatch(self, *args: Any, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        del args, kwargs
        raise V4MediaJobError("media worker is not configured")

    def execute_batch(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        raise V4MediaJobError("media worker is not configured")

    def list_jobs(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        del workspace_ref, run_ref
        return []


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value["payloadDigest"] = _digest(value)
    return value


def _fact(gate: Mapping[str, Any], kind: str) -> dict[str, Any]:
    matches = [
        item for item in gate.get("facts", [])
        if isinstance(item, Mapping) and item.get("factKind") == kind
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("payload"), Mapping):
        raise RepositoryUnavailableError("G5 evidence fact is inconsistent")
    return deepcopy(dict(matches[0]["payload"]))


def _facts(gate: Mapping[str, Any], prefix: str) -> list[dict[str, Any]]:
    result = [
        deepcopy(dict(item["payload"]))
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and str(item.get("factKind", "")).startswith(prefix)
        and isinstance(item.get("payload"), Mapping)
    ]
    return sorted(result, key=lambda item: item["ordinal"])


class K2MediaExecutionService:
    def __init__(
        self,
        assets: K2AssetPipelineService,
        evidence: EpisodeProductionEvidenceRepository,
        execution: MediaExecutionPort,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.assets = assets
        self.evidence = evidence
        self.execution = execution
        self._ref_factory = ref_factory
        self._clock = clock

    def _verify_handoff(
        self,
        job: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Path]:
        if (
            job.get("state") != "SUCCEEDED"
            or job.get("requestDigest") != request["payloadDigest"]
            or job.get("request", {}).get("generationRequestRef")
            != request["generationRequestRef"]
            or not isinstance(job.get("artifact"), Mapping)
        ):
            raise ArtifactRejectedError("V4 job handoff is inconsistent")
        artifact = deepcopy(dict(job["artifact"]))
        root = Path(self.execution.artifact_root).resolve()
        try:
            path = Path(artifact["internalPath"]).resolve()
        except (KeyError, TypeError):
            raise ArtifactRejectedError("V4 artifact path is missing") from None
        if root not in path.parents or not path.is_file():
            raise ArtifactRejectedError("V4 artifact escaped configured storage")
        try:
            storage_key = str(path.relative_to(root))
        except ValueError:
            raise ArtifactRejectedError("V4 artifact storage key is invalid") from None
        content = path.read_bytes()
        if (
            artifact.get("storageKey") != storage_key
            or artifact.get("byteSize") != len(content)
            or artifact.get("sha256") != sha256(content).hexdigest()
            or artifact.get("generationRequestDigest") != request["payloadDigest"]
            or artifact.get("provenance") != "LOCAL_EVIDENCE"
            or artifact.get("executionDevice") != "CPU_FFMPEG"
            or artifact.get("gpuUsed") is not False
            or artifact.get("publicationAllowed") is not False
        ):
            raise ArtifactRejectedError("V4 artifact metadata verification failed")
        try:
            independent_probe = verify_media_against_request(path, request)
        except V4ArtifactVerificationError as exc:
            raise ArtifactRejectedError("V5 media probe rejected artifact") from exc
        if independent_probe != artifact.get("probe"):
            raise ArtifactRejectedError("V4 and V5 media probes disagree")
        return artifact, path

    def execute_media(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey"
        }:
            raise EpisodeProductionError("command fields do not match the G5 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        # Resolve an already-written gate before touching the legacy worker
        # path.  With no historic G5 gate, even a completed G4 cannot be filled
        # in after the method-aware public cutover.
        self.assets.shot_graph.root_service.get_run(workspace, run_ref)
        existing_gate = self.evidence.get_gate(
            workspace, run_ref, MEDIA_EXECUTION_GATE
        )
        if existing_gate is None:
            raise LegacyMediaExecutionWriteDisabledError(
                "legacy G5 media-execution writes are disabled"
            )

        verified = self.assets.verify_asset_plan_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        require_legacy_executable_graph(graph)
        asset_manifest = verified["assetResolutionManifest"]
        requests = verified["generationRequests"]
        reject_speech_synthesis_in_legacy_media(requests)
        gate_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "media"}
        )
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "rootPayloadDigest": root["payloadDigest"],
                "assetPlanDigest": asset_manifest["payloadDigest"],
                "generationRequestDigests": [
                    item["payloadDigest"] for item in requests
                ],
                "admissionId": ADMISSION_ID,
            }
        )
        if (
            existing_gate.get("idempotencyKey") != gate_key
            or existing_gate.get("rootPayloadDigest") != root["payloadDigest"]
            or existing_gate.get("requestDigest") != request_digest
        ):
            raise IdempotencyConflictError("G5 media command conflicts")
        return {
            **self._bundle(existing_gate),
            "jobs": self.list_jobs(workspace, run_ref),
            "idempotentReplay": True,
        }

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "mediaManifest": _fact(gate, "MediaManifest"),
            "generationResults": _facts(gate, "GenerationResult:"),
            "assetVersions": _facts(gate, "AssetVersion:"),
            "state": gate["toState"],
        }

    def list_jobs(self, workspace_ref: str, run_ref: str) -> list[dict[str, Any]]:
        jobs = self.execution.list_jobs(workspace_ref, run_ref)
        return [
            {
                "jobRef": job["jobRef"],
                "generationRequestRef": job["request"]["generationRequestRef"],
                "mediaKind": job["request"]["mediaKind"],
                "state": job["state"],
                "attempts": deepcopy(job["attempts"]),
                "maxAttempts": job["maxAttempts"],
                "adapterIdentity": (
                    job["artifact"]["adapterIdentity"]
                    if isinstance(job.get("artifact"), Mapping) else None
                ),
                "provenance": (
                    job["artifact"]["provenance"]
                    if isinstance(job.get("artifact"), Mapping) else None
                ),
                "gpuUsed": (
                    job["artifact"]["gpuUsed"]
                    if isinstance(job.get("artifact"), Mapping) else None
                ),
            }
            for job in jobs
        ]

    def get_media_bundle(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        self.assets.shot_graph.root_service.get_run(workspace_ref, run_ref)
        gate = self.evidence.get_gate(workspace_ref, run_ref, MEDIA_EXECUTION_GATE)
        if gate is None:
            raise UpstreamNotReadyError("G5 media is not ready")
        return {**self._bundle(gate), "jobs": self.list_jobs(workspace_ref, run_ref)}

    def verify_media_current(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        verified = self.assets.verify_asset_plan_current(workspace_ref, run_ref)
        bundle = self.get_media_bundle(workspace_ref, run_ref)
        manifest = bundle["mediaManifest"]
        if (
            manifest.get("rootPayloadDigest") != verified["root"]["payloadDigest"]
            or manifest.get("executableShotGraphDigest")
            != verified["executableShotGraph"]["payloadDigest"]
            or manifest.get("assetResolutionManifestDigest")
            != verified["assetResolutionManifest"]["payloadDigest"]
            or manifest.get("publicationAllowed") is not False
            or manifest.get("gpuUsed") is not False
        ):
            raise StaleInputError("G5 media manifest lineage is stale")
        requests = {
            item["generationRequestRef"]: item for item in verified["generationRequests"]
        }
        root_path = Path(self.execution.artifact_root).resolve()
        for asset in bundle["assetVersions"]:
            request = requests.get(asset.get("generationRequestRef"))
            if not isinstance(request, Mapping):
                raise StaleInputError("G5 asset request is stale")
            path = (root_path / asset["storageKey"]).resolve()
            if root_path not in path.parents or not path.is_file():
                raise ArtifactRejectedError("registered media artifact is unavailable")
            content = path.read_bytes()
            if len(content) != asset["byteSize"] or sha256(content).hexdigest() != asset["sha256"]:
                raise ArtifactRejectedError("registered media artifact digest changed")
            try:
                if verify_media_against_request(path, request) != asset["probe"]:
                    raise ArtifactRejectedError("registered media probe changed")
            except V4ArtifactVerificationError as exc:
                raise ArtifactRejectedError("registered media probe failed") from exc
        return {**verified, **bundle}
