"""G5 V5 admission of V4-executed immutable K2 media artifacts."""

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
from .evidence import EpisodeProductionEvidenceRepository, EvidenceFact, GateAppend
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


MEDIA_EXECUTION_GATE = "G5_MEDIA_EXECUTION"
GENERATION_RESULT_SCHEMA_VERSION = "v5.generation-result.v1"
ASSET_VERSION_SCHEMA_VERSION = "v5.asset-version.v1"
MEDIA_MANIFEST_SCHEMA_VERSION = "v5.media-manifest.v1"
ADMISSION_ID = "v5.k2.media-admission.v1"


class WorkerUnavailableError(EpisodeProductionError):
    code = "worker_unavailable"


class ArtifactRejectedError(EpisodeProductionError):
    code = "artifact_verification_failed"


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
        verified = self.assets.verify_asset_plan_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        asset_manifest = verified["assetResolutionManifest"]
        requests = verified["generationRequests"]
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
        existing_gate = self.evidence.get_gate(
            workspace, run_ref, MEDIA_EXECUTION_GATE
        )
        if existing_gate is not None:
            if (
                existing_gate.get("idempotencyKey") != gate_key
                or existing_gate.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError("G5 media command conflicts")
            return {
                **self._bundle(existing_gate),
                "jobs": self.list_jobs(workspace, run_ref),
                "idempotentReplay": True,
            }
        try:
            jobs = self.execution.execute_batch(
                workspace,
                run_ref,
                requests,
                batch_idempotency_key=client_key,
            )
        except V4ArtifactVerificationError as exc:
            raise ArtifactRejectedError("V4 worker rejected its artifact") from exc
        except V4MediaJobError as exc:
            raise WorkerUnavailableError("V4 worker did not complete") from exc
        if len(jobs) != len(requests):
            raise WorkerUnavailableError("V4 returned an incomplete media batch")
        jobs_by_request = {
            job.get("request", {}).get("generationRequestRef"): job for job in jobs
        }
        if len(jobs_by_request) != len(requests):
            raise ArtifactRejectedError("V4 returned duplicate media handoffs")
        now = self._clock()
        results: list[dict[str, Any]] = []
        asset_versions: list[dict[str, Any]] = []
        for ordinal, request in enumerate(requests, start=1):
            job = jobs_by_request.get(request["generationRequestRef"])
            if not isinstance(job, Mapping):
                raise ArtifactRejectedError("V4 media handoff is missing")
            artifact, _ = self._verify_handoff(job, request)
            attempts = job.get("attempts")
            if not isinstance(attempts, list) or not attempts:
                raise ArtifactRejectedError("V4 attempt evidence is missing")
            accepted_attempt = attempts[-1]
            if accepted_attempt.get("state") != "SUCCEEDED":
                raise ArtifactRejectedError("V4 accepted attempt is not successful")
            result = _sealed(
                {
                    "schemaVersion": GENERATION_RESULT_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "generationResultRef": _required_ref(
                        self._ref_factory("generation-result"), "generationResultRef"
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "jobRef": job["jobRef"],
                    "attemptRef": accepted_attempt["attemptRef"],
                    "attemptNumber": accepted_attempt["attemptNumber"],
                    "adapterIdentity": artifact["adapterIdentity"],
                    "parameters": deepcopy(request["parameters"]),
                    "mediaKind": request["mediaKind"],
                    "mediaType": request["mediaType"],
                    "artifactSha256": artifact["sha256"],
                    "artifactByteSize": artifact["byteSize"],
                    "probe": deepcopy(artifact["probe"]),
                    "state": "VERIFIED",
                    "provenance": "LOCAL_EVIDENCE",
                    "rightsState": "LOCAL_EVIDENCE_ONLY",
                    "gpuUsed": False,
                    "publicationAllowed": False,
                    "createdBy": ADMISSION_ID,
                    "createdAt": now,
                }
            )
            asset_version = _sealed(
                {
                    "schemaVersion": ASSET_VERSION_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "assetRef": _required_ref(
                        self._ref_factory("generated-asset"), "assetRef"
                    ),
                    "assetVersionRef": _required_ref(
                        self._ref_factory("generated-asset-version"),
                        "assetVersionRef",
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "assetRequirementRef": request["assetRequirementRef"],
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "generationResultRef": result["generationResultRef"],
                    "generationResultDigest": result["payloadDigest"],
                    "creativeShotRef": request["creativeShotRef"],
                    "creativeShotVersionRef": request["creativeShotVersionRef"],
                    "creativeShotDigest": request["creativeShotDigest"],
                    "mediaKind": request["mediaKind"],
                    "mediaType": request["mediaType"],
                    "storageKey": artifact["storageKey"],
                    "byteSize": artifact["byteSize"],
                    "sha256": artifact["sha256"],
                    "probe": deepcopy(artifact["probe"]),
                    "adapterIdentity": artifact["adapterIdentity"],
                    "provenance": "LOCAL_EVIDENCE",
                    "rightsState": "LOCAL_EVIDENCE_ONLY",
                    "state": "REGISTERED",
                    "publicationAllowed": False,
                    "createdBy": ADMISSION_ID,
                    "createdAt": now,
                }
            )
            results.append(result)
            asset_versions.append(asset_version)
        manifest = _sealed(
            {
                "schemaVersion": MEDIA_MANIFEST_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "mediaManifestRef": _required_ref(
                    self._ref_factory("media-manifest"), "mediaManifestRef"
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "assetResolutionManifestRef": asset_manifest[
                    "assetResolutionManifestRef"
                ],
                "assetResolutionManifestDigest": asset_manifest["payloadDigest"],
                "generationResultRefs": [item["generationResultRef"] for item in results],
                "assetVersionRefs": [item["assetVersionRef"] for item in asset_versions],
                "summary": {
                    "requested": len(requests),
                    "verifiedResults": len(results),
                    "registeredAssets": len(asset_versions),
                    "videoAssets": sum(item["mediaKind"] == "video" for item in asset_versions),
                    "audioAssets": sum(item["mediaKind"] == "audio" for item in asset_versions),
                    "failed": 0,
                },
                "state": "MEDIA_VERIFIED",
                "executionScope": "SINGLE_EPISODE",
                "provenance": "LOCAL_EVIDENCE",
                "gpuUsed": False,
                "publicationAllowed": False,
                "createdBy": ADMISSION_ID,
                "createdAt": now,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"GenerationResult:{item['ordinal']:04d}", item["generationResultRef"],
                1, item, item["payloadDigest"]
            )
            for item in results
        ) + tuple(
            EvidenceFact(
                f"AssetVersion:{item['ordinal']:04d}", item["assetVersionRef"],
                1, item, item["payloadDigest"]
            )
            for item in asset_versions
        ) + (
            EvidenceFact(
                "MediaManifest", manifest["mediaManifestRef"], 1, manifest,
                manifest["payloadDigest"]
            ),
        )
        gate, replay = self.evidence.append_gate(
            GateAppend(
                workspace, run_ref, MEDIA_EXECUTION_GATE,
                gate_key,
                root["payloadDigest"], request_digest, "ASSETS_READY", "MEDIA_READY",
                now, facts,
            )
        )
        return {**self._bundle(gate), "jobs": self.list_jobs(workspace, run_ref), "idempotentReplay": replay}

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
