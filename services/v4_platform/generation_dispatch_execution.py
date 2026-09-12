"""Dedicated CPU-isolated Package 3 executor for Grant-bound Job v4 records.

The legacy worker remains unchanged and continues to reject Job v4.  This
module claims the original queue row with its original revision CAS, creates
one original Attempt, invokes V5 consume, and records a TEST_ONLY result on the
same Job/Attempt.  It contains no provider, ComfyUI, GPU, HTTP or socket code.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import os
from pathlib import Path
from threading import get_ident
from typing import Any, Mapping

from .backend_registry import (BackendValidationError, attempt_binding,
    digest as backend_digest, validate_decision)
from .media_jobs import (ARTIFACT_SCHEMA_VERSION, ArtifactRecoveryStoreError,
    ArtifactVerificationError, MediaJobCoordinator, MediaJobError,
    MediaJobStateError, _file_digest_and_size, _format_time, _parse_time,
    _validate_job, verify_media_against_request)
from .method_aware_execution import (DISPATCH_JOB_SCHEMA_VERSION,
    validate_envelope, validate_execution_result)
from .generation_dispatch_transport import (
    REQUEST_BYTES_NOT_COMMITTED, RESPONSE_RECEIVED,
    SUBMISSION_OUTCOME_UNKNOWN, GenerationDispatchTransportError,
    TransportReadResult, make_dispatch_result, validate_transport_result,
)
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_consumption import (
    CurrentExecutionObservation, validate_worker_identity,
)


def _read_text(path: str) -> str:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise c.DispatchError("CURRENTNESS_FENCE_UNAVAILABLE") from exc
    c.require(bool(value), "CURRENTNESS_FENCE_UNAVAILABLE")
    return value


class LocalWorkerExecutionContext:
    """Trusted local process identity derived from Linux procfs, not a command."""

    def __init__(self, worker_ref: str, *, core_commit: str):
        c.ref(worker_ref); c.git_id(core_commit)
        self._worker_ref = worker_ref
        self._core_commit = core_commit
        self._pid = os.getpid()
        try:
            stat_value = Path("/proc/self/stat").read_text(encoding="utf-8")
            command_end = stat_value.rfind(")")
            if command_end < 1:
                raise ValueError("proc stat command field is invalid")
            # Fields after the parenthesized comm begin at procfs field 3;
            # starttime is field 22 and therefore index 19 in this suffix.
            start_ticks = stat_value[command_end + 2:].split()[19]
            pid_namespace = os.readlink("/proc/self/ns/pid")
        except (OSError, IndexError, ValueError) as exc:
            raise c.DispatchError("CURRENTNESS_FENCE_UNAVAILABLE") from exc
        process = {"hostBootIdDigest": c.digest(_read_text("/proc/sys/kernel/random/boot_id")),
            "pidNamespaceIdDigest": c.digest(pid_namespace), "processId": self._pid,
            "processStartTicks": start_ticks, "coreCommit": core_commit}
        self._process_digest = c.digest(process)

    def current(self) -> dict[str, Any]:
        c.require(os.getpid() == self._pid, "ATTEMPT_OR_LEASE_CHANGED")
        return validate_worker_identity({"workerRef": self._worker_ref,
            "workerProcessIdentityDigest": self._process_digest,
            "processId": self._pid, "threadId": get_ident()})


class MediaJobGenerationDispatchPort:
    """The sole Package 3 bridge to the existing V4 queue and Attempt CAS."""

    def __init__(self, *, coordinator: MediaJobCoordinator, coordination, clock):
        if coordinator is None or coordination is None or clock is None:
            raise MediaJobError("Package 3 execution dependencies are unavailable")
        self.coordinator = coordinator
        self.repository = coordinator.repository
        self.coordination = coordination
        self.clock = clock

    @staticmethod
    def _stable_binding(job: Mapping[str, Any]) -> str:
        value = deepcopy(dict(job))
        value.pop("revision", None)
        value.pop("updatedAt", None)
        lease = value.get("lease")
        if isinstance(lease, dict):
            lease.pop("expiresAt", None)
        return c.digest(value)

    def claim(self, workspace_ref: str, production_run_ref: str, media_job_ref: str,
              worker_identity: Mapping[str, Any]) -> dict[str, Any]:
        identity = validate_worker_identity(worker_identity)
        for value in (workspace_ref, production_run_ref, media_job_ref):
            c.ref(value)
        with self.coordination.critical_section(workspace_ref) as lease:
            lease.assert_held()
            current = self.repository.get(workspace_ref, production_run_ref, media_job_ref)
            if (current is None or current.get("schemaVersion") != DISPATCH_JOB_SCHEMA_VERSION
                    or current.get("state") != "QUEUED" or current.get("attempts")
                    or current.get("maxAttempts") != 1):
                raise MediaJobStateError("Grant-bound Job is not uniquely claimable")
            _validate_job(current)
            decision = validate_decision(current["backendBinding"])
            now = _parse_time(self.clock.now())
            expected = current["revision"]
            current["state"] = "LEASED"
            current["lease"] = {"workerRef": identity["workerRef"],
                "leaseToken": self.coordinator._ref_factory("media-job-lease"),
                "leasedAt": _format_time(now),
                "expiresAt": _format_time(now + timedelta(seconds=self.coordinator.lease_seconds))}
            current["updatedAt"] = _format_time(now)
            leased = self.repository.save(current, expected)
            attempt = {"attemptRef": self.coordinator._ref_factory("media-job-attempt"),
                "attemptNumber": 1, "workerRef": identity["workerRef"],
                "workerProcessIdentityDigest": identity["workerProcessIdentityDigest"],
                "adapterIdentity": decision["adapterIdentity"],
                "backendBinding": attempt_binding(decision, identity["workerRef"]),
                "state": "RUNNING", "startedAt": self.clock.now()}
            expected = leased["revision"]
            leased["attempts"].append(attempt)
            leased["state"] = "RUNNING"
            leased["updatedAt"] = self.clock.now()
            return self.repository.save(leased, expected)

    def read_current(self, command: Mapping[str, Any], grant: Mapping[str, Any],
                     worker_identity: Mapping[str, Any], now: str, lease: Any,
                     *, phase: str) -> CurrentExecutionObservation:
        identity = validate_worker_identity(worker_identity)
        if phase not in {"CONSUME", "SEND"}:
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
        lease.assert_held()
        job = self.repository.get(command["workspaceRef"], command["productionRunRef"],
                                  command["mediaJobRef"])
        try:
            if job is None:
                raise MediaJobError("missing Grant-bound Job")
            _validate_job(job)
            binding = job["dispatchGrantBinding"]
            expected_binding = {"generationDispatchGrantRef": grant["generationDispatchGrantRef"],
                "generationDispatchGrantDigest": grant["payloadDigest"],
                "subjectDigest": grant["subjectDigest"],
                "approvedPlanDigest": grant["approval"]["approvedPlanDigest"]}
            request, envelope = job["request"], job["executionEnvelope"]
            validate_envelope(envelope, request)
            attempt = job["attempts"][-1] if job["attempts"] else None
            job_lease = job.get("lease")
            if (job["schemaVersion"] != DISPATCH_JOB_SCHEMA_VERSION
                    or binding != expected_binding
                    or any(request[key] != grant[key] for key in c.SCOPE_FIELDS)
                    or job["workspaceRef"] != grant["workspaceRef"]
                    or job["productionRunRef"] != grant["productionRunRef"]
                    or envelope["backendBinding"] != grant["executionBinding"]["backendDecision"]
                    or envelope["outputConstraints"] != grant["subject"]["outputConstraints"]
                    or job["state"] != "RUNNING" or job["maxAttempts"] != 1
                    or len(job["attempts"]) != 1 or not isinstance(attempt, Mapping)
                    or attempt.get("state") != "RUNNING"
                    or attempt.get("attemptRef") != command["attemptRef"]
                    or attempt.get("workerRef") != command["workerRef"]
                    or attempt.get("workerProcessIdentityDigest")
                        != identity["workerProcessIdentityDigest"]
                    or identity["workerRef"] != command["workerRef"]
                    or not isinstance(job_lease, Mapping)
                    or job_lease.get("workerRef") != identity["workerRef"]
                    or not isinstance(job_lease.get("leaseToken"), str)
                    or not job_lease["leaseToken"]
                    or c.digest(job_lease["leaseToken"])
                        != command["expectedLeaseTokenDigest"]
                    or _parse_time(job_lease["expiresAt"]) <= _parse_time(now)):
                raise MediaJobError("Grant-bound Job/Attempt/lease binding changed")
            if phase == "CONSUME" and job["revision"] != command["expectedJobRevision"]:
                raise MediaJobError("Grant-bound Job revision changed")
        except (MediaJobError, BackendValidationError, KeyError, TypeError, ValueError) as exc:
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED") from exc
        lease.assert_held()
        return CurrentExecutionObservation(deepcopy(job), job_lease["leaseToken"],
                                           self._stable_binding(job))


class GenerationDispatchResultBoundary:
    """Persist TEST_ONLY transport outcomes on the original Job/Attempt authority."""

    def __init__(self, coordinator: MediaJobCoordinator, *, clock):
        self.coordinator = coordinator
        self.repository = coordinator.repository
        self.clock = clock

    @staticmethod
    def _provider_execution(job: Mapping[str, Any], dispatch_result: Mapping[str, Any]) -> dict[str, Any]:
        binding = job["backendBinding"]
        evidence = {"schemaVersion": "v4.generation-dispatch-test-only-execution-evidence.v1",
            "TEST_ONLY": True, "cpuIsolated": True,
            "dispatchResultDigest": dispatch_result["payloadDigest"],
            "transportSubmissionRef": dispatch_result["transportSubmissionRef"],
            "transportSubmissionDigest": dispatch_result["transportSubmissionDigest"],
            "artifactDigest": dispatch_result["artifactDigest"]}
        value = {"schemaVersion": "v4.method-aware-execution-result.v1",
            "backendBindingDigest": backend_digest(binding),
            **{key: binding[key] for key in ("providerId", "modelId", "region",
                "endpointClass", "adapterIdentity", "costCurrency",
                "runtimeAttestationRef", "runtimeAttestationDigest")},
            "providerRequestRef": dispatch_result["transportSubmissionRef"],
            "costMinor": 0, "executionEvidenceDigest": backend_digest(evidence),
            "executionEvidence": evidence, "executionDevice": "CPU_FAKE_TRANSPORT",
            "gpuUsed": False}
        return validate_execution_result(value, job["executionEnvelope"])

    def record_success(self, job: Mapping[str, Any], result: TransportReadResult,
                       *, workflow_digest: str) -> dict[str, Any]:
        receipt = validate_transport_result(result.receipt)
        if receipt["outcome"] != "SUCCEEDED" or result.artifact_bytes is None:
            raise MediaJobError("successful Package 3 result is invalid")
        current = self.repository.get(job["workspaceRef"], job["productionRunRef"], job["jobRef"])
        if current is None or current["state"] != "RUNNING" or current["attempts"][-1]["state"] != "RUNNING":
            raise MediaJobStateError("Package 3 result lost its active Attempt")
        artifact_digest = sha256(result.artifact_bytes).hexdigest()
        dispatch_result = make_dispatch_result(outcome="SUCCEEDED", phase=RESPONSE_RECEIVED,
            job=current, submission=result.submission,
            workflow_digest=workflow_digest, artifact_digest=artifact_digest,
            failure_code=None, created_at=self.clock.now())
        if dispatch_result["transportSubmissionDigest"] != receipt["transportSubmissionDigest"]:
            raise MediaJobError("transport submission binding changed")
        attempt = current["attempts"][-1]
        candidate_path, final_path = self.coordinator._attempt_paths(current,
            attempt["attemptNumber"])
        self.coordinator._artifact_recovery.require_absent(candidate_path)
        self.coordinator._artifact_recovery.require_absent(final_path)
        try:
            with candidate_path.open("xb") as stream:
                stream.write(result.artifact_bytes)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise ArtifactVerificationError("TEST_ONLY artifact staging failed") from exc
        probe = verify_media_against_request(candidate_path,
            self.coordinator._probe_request(current), fresh_probe=True)
        content_digest, content_size = _file_digest_and_size(candidate_path)
        if content_digest != artifact_digest:
            raise ArtifactVerificationError("TEST_ONLY artifact bytes changed")
        try:
            final_storage_key = self.coordinator._artifact_recovery.storage_key(final_path)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        execution = self._provider_execution(current, dispatch_result)
        artifact = {"schemaVersion": ARTIFACT_SCHEMA_VERSION,
            "workspaceRef": current["workspaceRef"],
            "productionRunRef": current["productionRunRef"],
            "jobRef": current["jobRef"], "attemptRef": attempt["attemptRef"],
            "generationRequestRef": current["request"]["generationRequestRef"],
            "generationRequestVersionRef": current["request"]["generationRequestVersionRef"],
            "generationRequestDigest": current["requestDigest"],
            "mediaKind": current["executionEnvelope"]["outputConstraints"]["mediaKind"],
            "mediaType": current["executionEnvelope"]["outputConstraints"]["mediaType"],
            "internalPath": str(final_path), "storageKey": final_storage_key,
            "byteSize": content_size, "sha256": content_digest, "probe": probe,
            "adapterIdentity": "v4.generation-dispatch-test-only-transport.v1",
            "provenance": "TEST_ONLY", "executionDevice": "CPU_FAKE_TRANSPORT",
            "gpuUsed": False, "publicationAllowed": False,
            "providerExecution": execution,
            "dispatchResultDigest": dispatch_result["payloadDigest"],
            "createdAt": self.clock.now()}
        expected = current["revision"]
        current["dispatchResult"] = dispatch_result
        intent = self.coordinator._build_commit_intent(current, attempt,
            candidate_path, final_path, artifact)
        current["artifactCommitIntent"] = intent
        current["updatedAt"] = self.clock.now()
        current = self.repository.save(current, expected)

        def assert_fence() -> None:
            self.coordinator._active_worker_job(current["workspaceRef"],
                current["productionRunRef"], current["jobRef"],
                current["lease"]["workerRef"], current["lease"]["leaseToken"],
                attempt["attemptRef"])

        try:
            self.coordinator._artifact_recovery.durable_replace(candidate_path,
                final_path, assert_fence=assert_fence)
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        artifact = self.coordinator._verify_final_from_intent(current, intent)
        expected = current["revision"]
        current["attempts"][-1].update({"state": "SUCCEEDED",
            "finishedAt": self.clock.now(), "artifactSha256": artifact["sha256"],
            "artifactCommitIntentDigest": intent["intentDigest"],
            "providerExecution": execution,
            "dispatchResultDigest": dispatch_result["payloadDigest"]})
        current.update(state="SUCCEEDED", lease=None, artifact=artifact,
            artifactCommitIntent=None, updatedAt=self.clock.now())
        return self.repository.save(current, expected)

    def record_failure(self, job: Mapping[str, Any], *, workflow_digest: str,
                       code: str, phase: str,
                       submission: Mapping[str, Any] | None) -> dict[str, Any]:
        current = self.repository.get(job["workspaceRef"], job["productionRunRef"], job["jobRef"])
        if current is None:
            raise MediaJobStateError("Package 3 Job disappeared")
        if current.get("state") != "RUNNING":
            return current
        outcome = "UNKNOWN" if phase == SUBMISSION_OUTCOME_UNKNOWN else "FAILED"
        result = make_dispatch_result(outcome=outcome, phase=phase, job=current,
            submission=submission, workflow_digest=workflow_digest,
            artifact_digest=None, failure_code=code, created_at=self.clock.now())
        expected = current["revision"]
        current["dispatchResult"] = result
        current["attempts"][-1].update({"state": "FAILED",
            "finishedAt": self.clock.now(), "errorCode": code,
            "failureClass": code, "nonRetryable": True,
            "dispatchResultDigest": result["payloadDigest"],
            "quarantineStorageKeys": []})
        current.update(state="FAILED", lease=None, artifact=None,
            artifactCommitIntent=None, updatedAt=self.clock.now())
        return self.repository.save(current, expected)

    def read_only(self, workspace_ref: str, production_run_ref: str,
                  media_job_ref: str) -> dict[str, Any] | None:
        """Recovery observation only: never claims, retries, sends or rewrites."""
        return self.repository.get(workspace_ref, production_run_ref, media_job_ref)


class GenerationDispatchExecutor:
    """One bounded execution of an already-routed Grant-bound Job v4."""

    def __init__(self, *, coordinator: MediaJobCoordinator, consumer,
                 worker_context, transport, clock, coordination,
                 result_boundary: GenerationDispatchResultBoundary,
                 job_port: MediaJobGenerationDispatchPort):
        if (coordinator is None or consumer is None or worker_context is None
                or transport is None or clock is None or coordination is None
                or result_boundary is None or job_port is None
                or getattr(transport, "TEST_ONLY", None) is not True
                or getattr(transport, "CPU_ISOLATED", None) is not True
                or job_port.coordinator is not coordinator
                or job_port.repository is not coordinator.repository
                or job_port.coordination is not coordination
                or job_port.clock is not clock
                or consumer._job_port is not job_port
                or consumer._worker_context is not worker_context
                or consumer._clock is not clock
                or consumer._foundation.coordination is not coordination
                or result_boundary.coordinator is not coordinator
                or result_boundary.repository is not coordinator.repository
                or result_boundary.clock is not clock):
            raise MediaJobError("CPU-isolated Package 3 composition is incomplete")
        self.coordinator, self.consumer = coordinator, consumer
        self.worker_context, self.transport = worker_context, transport
        self.clock, self.coordination = clock, coordination
        self.result_boundary, self.job_port = result_boundary, job_port

    def execute(self, workspace_ref: str, production_run_ref: str,
                media_job_ref: str) -> dict[str, Any]:
        identity = validate_worker_identity(self.worker_context.current())
        claimed = self.job_port.claim(workspace_ref, production_run_ref,
            media_job_ref, identity)
        binding = claimed["dispatchGrantBinding"]
        command = {"workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "generationDispatchGrantRef": binding["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": binding["generationDispatchGrantDigest"],
            "mediaJobRef": claimed["jobRef"],
            "attemptRef": claimed["attempts"][-1]["attemptRef"],
            "workerRef": identity["workerRef"],
            "expectedJobRevision": claimed["revision"],
            "expectedLeaseTokenDigest": c.digest(claimed["lease"]["leaseToken"]),
            "idempotencyKey": "generation-dispatch-consume-"
                + c.digest({"grant": binding["generationDispatchGrantRef"],
                    "job": claimed["jobRef"],
                    "attempt": claimed["attempts"][-1]["attemptRef"]}),
            "snapshotTokens": self.consumer.snapshot_tokens(workspace_ref,
                production_run_ref)}
        decision = self.consumer.consume(command)
        capability = decision["continuation"]
        if capability is None:
            raise MediaJobStateError("consume replay cannot execute transport")
        heartbeat = None
        workflow_digest = decision["receipt"]["terminal"]["attemptBinding"]["workflowDigest"]
        try:
            heartbeat = self.coordinator._start_lease_heartbeat(claimed,
                identity["workerRef"], claimed["attempts"][-1]["attemptRef"])
            try:
                transport_result = capability.send_once(self.transport)
            except GenerationDispatchTransportError as exc:
                current = self.coordinator._stop_lease_heartbeat(heartbeat, claimed,
                    identity["workerRef"], claimed["attempts"][-1]["attemptRef"])
                heartbeat = None
                return self.result_boundary.record_failure(current,
                    workflow_digest=workflow_digest, code=exc.code,
                    phase=exc.phase, submission=exc.submission)
            except c.DispatchError as exc:
                current = self.coordinator._stop_lease_heartbeat(heartbeat, claimed,
                    identity["workerRef"], claimed["attempts"][-1]["attemptRef"])
                heartbeat = None
                return self.result_boundary.record_failure(current,
                    workflow_digest=workflow_digest, code=exc.code,
                    phase=REQUEST_BYTES_NOT_COMMITTED, submission=None)
            current = self.coordinator._stop_lease_heartbeat(heartbeat, claimed,
                identity["workerRef"], claimed["attempts"][-1]["attemptRef"])
            heartbeat = None
            receipt = validate_transport_result(transport_result.receipt)
            if receipt["outcome"] != "SUCCEEDED":
                return self.result_boundary.record_failure(current,
                    workflow_digest=workflow_digest,
                    code=receipt["failureCode"], phase=receipt["phase"],
                    submission=transport_result.submission)
            return self.result_boundary.record_success(current, transport_result,
                workflow_digest=workflow_digest)
        finally:
            if heartbeat is not None:
                heartbeat[0].set()
                heartbeat[1].join(timeout=max(1.0,
                    min(self.coordinator.heartbeat_interval_seconds * 2, 15.0)))

    def recover_read_only(self, workspace_ref: str, production_run_ref: str,
                          media_job_ref: str) -> dict[str, Any]:
        job = self.result_boundary.read_only(workspace_ref, production_run_ref,
                                             media_job_ref)
        if job is None:
            raise MediaJobStateError("Package 3 Job was not found")
        binding = job["dispatchGrantBinding"]
        consumption = self.consumer.read_consumption_receipt(workspace_ref,
            production_run_ref, binding["generationDispatchGrantRef"])
        return {"job": job, "consumption": consumption,
            "continuation": None, "sendAttempted": False}
