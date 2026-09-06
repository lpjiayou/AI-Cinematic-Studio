"""Read-only, provider-neutral projections of exact method-aware media jobs."""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sqlite3
import stat
from typing import Any, Mapping, Sequence

from .backend_registry import canonical, digest, ref, validate_attempt_binding
from .media_jobs import (
    MediaJobCoordinator, MediaJobError, MediaJobRepository, _file_digest_and_size,
    _validate_job, verify_media_against_request,
)
from .method_aware_execution import (
    METHOD_AWARE_JOB_SCHEMA_VERSION, output_probe_request, validate_envelope,
    validate_execution_result,
)

V4_METHOD_AWARE_JOB_STATUS_SCHEMA = "v4.method-aware-media-job-status.v1"
V4_METHOD_AWARE_JOB_RESULT_SCHEMA = "v4.method-aware-media-job-result.v1"
STATES = frozenset({"QUEUED", "LEASED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"})
SAFE_FAILURES = frozenset({
    "PRE_EXECUTION_VALIDATION_FAILED", "REMOTE_SUBMISSION_INDETERMINATE",
    "ARTIFACT_RECOVERY_MISMATCH", "artifact_recovery_mismatch", "artifact_verification_failed",
    "backend_binding_invalid", "adapter_failed", "media_adapter_unavailable",
    "worker_lease_expired", "worker_terminated", "WORKER_TERMINATED",
})
RESULT_FIELDS = frozenset({
    "schemaVersion", "workspaceRef", "productionRunRef", "mediaJobRef", "mediaJobRevision",
    "generationRequestRef", "generationRequestVersionRef", "generationRequestDigest",
    "creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest",
    "sourceAssetRef", "sourceAssetVersionRef", "sourceAssetVersionDigest", "sourceContentDigest",
    "executionEnvelopeDigest", "backendBindingDigest", "attemptRef", "attemptNumber",
    "attemptBackendBindingDigest", "artifactRef", "artifactMediaKind", "artifactMediaType",
    "artifactStorageKey", "artifactByteSize", "artifactSha256", "artifactProbe", "artifactProbeDigest",
    "providerExecutionDigest", "technicalChecks", "publicationAllowed", "payloadDigest",
})


class MethodAwareJobResultError(ValueError):
    def __init__(self, code: str = "method_aware_job_result_invalid") -> None:
        self.code = code
        super().__init__(code)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = digest(result)
    return result


class MethodAwareMediaJobResultReader:
    """Has no adapter, scheduling or job-write port; never performs recovery."""

    def __init__(self, repository: MediaJobRepository, artifact_root: Path | str) -> None:
        self.repository = repository
        self.artifact_root = Path(artifact_root).absolute()

    @classmethod
    def from_coordinator(cls, coordinator: Any):
        if not isinstance(coordinator, MediaJobCoordinator):
            return None
        return cls(coordinator.repository, coordinator.artifact_root)

    def _job(self, workspace_ref: str, production_run_ref: str, media_job_ref: str) -> dict[str, Any]:
        try:
            for value in (workspace_ref, production_run_ref, media_job_ref):
                ref(value, "scope ref")
            if self.repository is None:
                raise MethodAwareJobResultError("method_aware_job_result_unavailable")
            value = self.repository.get(workspace_ref, production_run_ref, media_job_ref)
            if value is None:
                raise MethodAwareJobResultError("method_aware_job_not_found")
            if (value.get("workspaceRef"), value.get("productionRunRef"), value.get("jobRef")) != (
                workspace_ref, production_run_ref, media_job_ref
            ):
                raise MethodAwareJobResultError("method_aware_job_scope_mismatch")
            if value.get("schemaVersion") != METHOD_AWARE_JOB_SCHEMA_VERSION or value.get("state") not in STATES:
                raise MethodAwareJobResultError()
            _validate_job(value)
            return deepcopy(value)
        except MethodAwareJobResultError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise MethodAwareJobResultError("method_aware_job_result_unavailable") from exc
        except (MediaJobError, ValueError, TypeError, KeyError, RecursionError) as exc:
            raise MethodAwareJobResultError() from exc

    def _artifact_path(self, artifact: Mapping[str, Any]) -> Path:
        root = self.artifact_root
        key = artifact["storageKey"]
        relative = Path(key)
        if (not isinstance(key, str) or "\\" in key or relative.is_absolute()
                or any(part in {"", ".", ".."} for part in key.split("/"))):
            raise MethodAwareJobResultError()
        path = Path(artifact["internalPath"])
        if not path.is_absolute() or path != root / relative:
            raise MethodAwareJobResultError()
        for candidate in (root, *path.parents, path):
            if candidate.is_symlink():
                raise MethodAwareJobResultError()
        if not root.is_dir() or path.resolve(strict=True).relative_to(root.resolve(strict=True)) != relative:
            raise MethodAwareJobResultError()
        if not stat.S_ISREG(path.stat().st_mode):
            raise MethodAwareJobResultError()
        return path

    def require_verified_succeeded_result(
        self, workspace_ref: str, production_run_ref: str, media_job_ref: str,
        expected_generation_request_ref: str, expected_generation_request_digest: str,
        expected_route_registry_version: str, expected_route_registry_digest: str,
    ) -> dict[str, Any]:
        job = self._job(workspace_ref, production_run_ref, media_job_ref)
        state = job["state"]
        if state != "SUCCEEDED":
            raise MethodAwareJobResultError({
                "FAILED": "method_aware_job_failed", "CANCELLED": "method_aware_job_cancelled",
            }.get(state, "method_aware_job_not_terminal"))
        try:
            request = job["request"]
            binding = job["backendBinding"]
            if (job["lease"] is not None or job["artifactCommitIntent"] is not None
                    or job["maxAttempts"] != 1 or len(job["attempts"]) != 1
                    or request["generationRequestRef"] != expected_generation_request_ref
                    or request["payloadDigest"] != expected_generation_request_digest
                    or binding["registryVersion"] != expected_route_registry_version
                    or binding["registryDigest"] != expected_route_registry_digest):
                raise MethodAwareJobResultError()
            envelope = validate_envelope(job["executionEnvelope"], request)
            if envelope["semanticIntent"]["sourceAction"]["sourceText"] != job["executionContext"]["sourceText"]:
                raise MethodAwareJobResultError()
            attempt = job["attempts"][0]
            artifact = job["artifact"]
            validate_attempt_binding(attempt["backendBinding"], binding)
            if (attempt["state"] != "SUCCEEDED" or attempt["attemptNumber"] != 1
                    or artifact["generationRequestVersionRef"] != request["generationRequestVersionRef"]
                    or artifact["adapterIdentity"] != binding["adapterIdentity"]
                    or artifact["mediaKind"] != "video" or artifact["mediaType"] != "video/mp4"):
                raise MethodAwareJobResultError()
            execution = validate_execution_result(artifact["providerExecution"], envelope)
            if (attempt.get("providerExecution") != execution
                    or artifact["executionDevice"] != execution["executionDevice"]
                    or artifact["gpuUsed"] is not execution["gpuUsed"]):
                raise MethodAwareJobResultError()
            path = self._artifact_path(artifact)
            before_stat = path.stat()
            content_digest, size = _file_digest_and_size(path)
            if (content_digest, size) != (artifact["sha256"], artifact["byteSize"]):
                raise MethodAwareJobResultError()
            probe = verify_media_against_request(path, output_probe_request(envelope), fresh_probe=True)
            video = next(s for s in probe["streams"] if s.get("codec_type") == "video")
            if (Fraction(video["avg_frame_rate"]) != envelope["outputConstraints"]["frameRate"]
                    or canonical(probe) != canonical(artifact["probe"])):
                raise MethodAwareJobResultError()
            after_stat = path.stat()
            if (self._artifact_path(artifact) != path
                    or (before_stat.st_dev, before_stat.st_ino, before_stat.st_size, before_stat.st_mtime_ns)
                    != (after_stat.st_dev, after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns)
                    or _file_digest_and_size(path) != (content_digest, size)
                    or self._job(workspace_ref, production_run_ref, media_job_ref) != job):
                raise MethodAwareJobResultError()
            identity = {"workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
                        "mediaJobRef": media_job_ref, "attemptRef": attempt["attemptRef"], "artifactSha256": content_digest}
            source = envelope["sourceAsset"]
            result = _seal({
                "schemaVersion": V4_METHOD_AWARE_JOB_RESULT_SCHEMA,
                "workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
                "mediaJobRef": media_job_ref, "mediaJobRevision": job["revision"],
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestVersionRef": request["generationRequestVersionRef"],
                "generationRequestDigest": request["payloadDigest"],
                **{k:request[k] for k in ("creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest")},
                "sourceAssetRef": source["assetRef"], "sourceAssetVersionRef": source["assetVersionRef"],
                "sourceAssetVersionDigest": source["assetVersionDigest"], "sourceContentDigest": source["contentDigest"],
                "executionEnvelopeDigest": envelope["envelopeDigest"], "backendBindingDigest": digest(binding),
                "attemptRef": attempt["attemptRef"], "attemptNumber": attempt["attemptNumber"],
                "attemptBackendBindingDigest": digest(attempt["backendBinding"]),
                "artifactRef": "method-aware-artifact-" + digest(identity)[:40],
                "artifactMediaKind": "video", "artifactMediaType": "video/mp4",
                "artifactStorageKey": artifact["storageKey"], "artifactByteSize": size,
                "artifactSha256": content_digest, "artifactProbe": probe, "artifactProbeDigest": digest(probe),
                "providerExecutionDigest": digest(execution),
                "technicalChecks": [
                    {"check": name, "passed": True} for name in (
                        "media-job-terminal-succeeded", "execution-envelope-valid",
                        "attempt-backend-binding-valid", "artifact-byte-size-valid",
                        "artifact-sha256-valid", "artifact-probe-matches-output", "publication-disabled")
                ], "publicationAllowed": False,
            })
            if set(result) != RESULT_FIELDS:
                raise MethodAwareJobResultError()
            return result
        except MethodAwareJobResultError:
            raise
        except (MediaJobError, ValueError, TypeError, KeyError, OSError, StopIteration, ZeroDivisionError) as exc:
            raise MethodAwareJobResultError() from exc

    def project_statuses(
        self, workspace_ref: str, production_run_ref: str, exact_job_refs: Sequence[str],
    ) -> list[dict[str, Any]]:
        if (not isinstance(exact_job_refs, (tuple, list))
                or any(not isinstance(value, str) for value in exact_job_refs)
                or len(exact_job_refs) != len(set(exact_job_refs))):
            raise MethodAwareJobResultError()
        projected = []
        for job_ref in exact_job_refs:
            job = self._job(workspace_ref, production_run_ref, job_ref)
            result = None
            summary = None
            if job["state"] == "SUCCEEDED":
                request, binding = job["request"], job["backendBinding"]
                result = self.require_verified_succeeded_result(workspace_ref, production_run_ref, job_ref,
                    request["generationRequestRef"], request["payloadDigest"],
                    binding["registryVersion"], binding["registryDigest"])
                output = job["executionEnvelope"]["outputConstraints"]
                summary = {"mediaType": result["artifactMediaType"], "byteSize": result["artifactByteSize"],
                    "sha256": result["artifactSha256"], **{k:output[k] for k in ("width", "height", "frameRate", "durationFrames")},
                    "frameCount": output["durationFrames"]}
            failure = None
            error = None
            if job["state"] == "FAILED":
                last = job["attempts"][-1]
                failure = last.get("failureClass")
                error = last.get("errorCode")
                failure = failure if isinstance(failure, str) and failure in SAFE_FAILURES else "MEDIA_EXECUTION_FAILED"
                error = error if isinstance(error, str) and error in SAFE_FAILURES else "media_execution_failed"
            projected.append(_seal({
                "schemaVersion": V4_METHOD_AWARE_JOB_STATUS_SCHEMA,
                "workspaceRef": workspace_ref, "productionRunRef": production_run_ref, "mediaJobRef": job_ref,
                "generationRequestRef": job["request"]["generationRequestRef"],
                "generationRequestDigest": job["requestDigest"], "state": job["state"],
                "attemptCount": len(job["attempts"]), "failureClass": failure, "errorCode": error,
                "resultDigest": result["payloadDigest"] if result else None,
                "artifactSummary": summary, "publicationAllowed": False,
            }))
        return projected
