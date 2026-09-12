"""TEST_ONLY Package 3 CPU transport and real-SQLite execution fixture."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from threading import Lock, get_ident
from uuid import uuid4

from services.v4_platform.generation_dispatch_execution import (
    GenerationDispatchExecutor, GenerationDispatchResultBoundary,
    MediaJobGenerationDispatchPort,
)
from services.v4_platform.generation_dispatch_transport import (
    CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
    SUBMISSION_OUTCOME_UNKNOWN, GenerationDispatchTransportError,
    TransportReadResult, make_transport_result, make_transport_submission,
    validate_transport_request,
)
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_consumption import (
    CurrentExecutionObservation, GenerationDispatchConsumer,
    validate_worker_identity,
)
from tests.support.generation_dispatch_binding_fixtures import BindingFixture
from tests.support.generation_dispatch_fixtures import Fixture as GrantFixture


def export_pkg3_evidence(filename: str, value) -> None:
    location = os.environ.get("PKG3_TEST_EVIDENCE_DIR")
    if location is None:
        return
    if (not filename.endswith(".json") or "/" in filename
            or "\\" in filename):
        raise ValueError("invalid Package 3 evidence filename")
    root = Path(location).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / filename).write_text(json.dumps(value, ensure_ascii=False,
        indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TestWorkerExecutionContext:
    TEST_ONLY = True

    def __init__(self, worker_ref: str):
        self.worker_ref = worker_ref
        self.process_id = os.getpid()
        self.process_digest = c.digest({"TEST_ONLY": True,
            "workerRef": worker_ref, "processId": self.process_id})

    def current(self):
        return validate_worker_identity({"workerRef": self.worker_ref,
            "workerProcessIdentityDigest": self.process_digest,
            "processId": self.process_id, "threadId": get_ident()})


class _FakeExchange:
    __slots__ = ("request", "commit_attempted", "committed")

    def __init__(self, request):
        self.request = validate_transport_request(request)
        self.commit_attempted = False
        self.committed = False


class CpuIsolatedFakeTransport:
    """No sockets/imported clients/background sends; one synchronized commit."""

    TEST_ONLY = True
    CPU_ISOLATED = True

    def __init__(self, clock, *, root: Path | None = None,
                 fault: str | None = None):
        if fault not in {None, "connect", "before_commit", "partial_write", "after_commit",
                "read", "timeout", "cancel"}:
            raise ValueError("unknown TEST_ONLY transport fault")
        self.clock, self.fault = clock, fault
        self.root = Path(root or os.environ.get("TMPDIR", "/tmp")).resolve()
        self._lock = Lock()
        self.open_count = self.write_attempt_count = self.commit_count = self.read_count = 0
        self.last_request = self.last_submission = self.last_result = None
        self.network_calls = self.socket_calls = self.prompt_submissions = 0
        self.comfyui_connections = self.gpu_calls = 0
        self.requests_imports = self.httpx_imports = 0

    def open_exchange(self, request):
        value = validate_transport_request(request)
        with self._lock:
            self.open_count += 1
            self.last_request = deepcopy(value)
        if self.fault == "connect":
            raise GenerationDispatchTransportError("CONNECT_FAILED",
                CONNECT_NOT_STARTED, request_committed=False)
        return _FakeExchange(value)

    def commit_request_once(self, exchange):
        if type(exchange) is not _FakeExchange:
            raise GenerationDispatchTransportError("EXCHANGE_INVALID",
                REQUEST_BYTES_NOT_COMMITTED, request_committed=False)
        with self._lock:
            if exchange.commit_attempted:
                raise GenerationDispatchTransportError("SECOND_COMMIT_FORBIDDEN",
                    REQUEST_BYTES_NOT_COMMITTED, request_committed=False)
            exchange.commit_attempted = True
            if self.fault == "before_commit":
                raise GenerationDispatchTransportError("REQUEST_NOT_COMMITTED",
                    REQUEST_BYTES_NOT_COMMITTED, request_committed=False)
            self.write_attempt_count += 1
            if self.fault == "partial_write":
                raise GenerationDispatchTransportError("PARTIAL_REQUEST_NOT_COMMITTED",
                    REQUEST_BYTES_NOT_COMMITTED, request_committed=False)
            exchange.committed = True
            self.commit_count += 1
            submission = make_transport_submission(
                transport_submission_ref="test-transport-submission-" + uuid4().hex,
                request_digest=exchange.request["payloadDigest"],
                committed_at=self.clock.now())
            self.last_submission = deepcopy(submission)
        if self.fault == "after_commit":
            raise GenerationDispatchTransportError("SUBMISSION_RECEIPT_LOST",
                SUBMISSION_OUTCOME_UNKNOWN, request_committed=True,
                submission=submission)
        return submission

    @staticmethod
    def _video_bytes(output, root: Path) -> bytes:
        target = root / ("test-transport-output-" + uuid4().hex + ".mp4")
        frames, fps = output["durationFrames"], output["frameRate"]
        duration = f"{frames / fps:.9f}".rstrip("0").rstrip(".")
        command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
            f"color=c=0x203040:s={output['width']}x{output['height']}:r={fps}:d={duration}",
            "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset",
            "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-y", str(target)]
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        return target.read_bytes()

    def read_result(self, exchange, submission):
        with self._lock:
            self.read_count += 1
        if self.fault in {"read", "timeout", "cancel"}:
            code = {"read": "RESPONSE_READ_FAILED", "timeout": "RESPONSE_TIMEOUT",
                "cancel": "RESPONSE_CANCELLED"}[self.fault]
            raise GenerationDispatchTransportError(code,
                SUBMISSION_OUTCOME_UNKNOWN, request_committed=True,
                submission=submission)
        artifact = self._video_bytes(exchange.request["outputConstraints"], self.root)
        artifact_digest = sha256(artifact).hexdigest()
        receipt = make_transport_result(outcome="SUCCEEDED",
            request_digest=exchange.request["payloadDigest"], submission=submission,
            artifact_digest=artifact_digest, failure_code=None,
            received_at=self.clock.now())
        self.last_result = deepcopy(receipt)
        return TransportReadResult(submission, receipt, artifact)

    def evidence(self):
        return {"TEST_ONLY": True, "CPU_ISOLATED": True,
            "openCount": self.open_count,
            "initialWriteAttemptCount": self.write_attempt_count,
            "requestCommitCount": self.commit_count,
            "readCount": self.read_count, "networkCalls": self.network_calls,
            "socketCalls": self.socket_calls,
            "PROMPT_SUBMISSION_COUNT": self.prompt_submissions,
            "COMFYUI_CONNECTIONS": self.comfyui_connections,
            "GPU_CALLS": self.gpu_calls, "requestsImports": self.requests_imports,
            "httpxImports": self.httpx_imports}


class SyntheticJobPort:
    """Unit-level trusted port double; integration uses the real SQLite port."""

    def __init__(self, job):
        self.job = deepcopy(job)
        self.lease_token = self.job["lease"]["leaseToken"]
        self.stable_digest = c.digest("test-pkg3-stable-binding")
        self.read_phases = []

    def read_current(self, command, grant, worker_identity, now, lease, *, phase):
        del grant, now
        lease.assert_held()
        self.read_phases.append(phase)
        if (self.job["state"] != "RUNNING"
                or self.job["attempts"][-1]["attemptRef"] != command["attemptRef"]
                or self.job["attempts"][-1]["workerRef"] != worker_identity["workerRef"]
                or c.digest(self.lease_token) != command["expectedLeaseTokenDigest"]
                or phase == "CONSUME" and self.job["revision"] != command["expectedJobRevision"]):
            raise c.DispatchError("ATTEMPT_OR_LEASE_CHANGED")
        return CurrentExecutionObservation(deepcopy(self.job), self.lease_token,
                                           self.stable_digest)


class LightweightConsumptionFixture:
    def __init__(self, case, *, memory: bool = True):
        self.grants = GrantFixture(case, memory=memory)
        self.grants.clock.monotonic_value = 1000.0
        self.grants.clock.monotonic = lambda: self.grants.clock.monotonic_value
        issued = self.grants.public.issue(self.grants.command())
        if "grant" not in issued:
            raise AssertionError(issued)
        self.grant = issued["grant"]
        self.clock = self.grants.clock
        self.root = self.grants.root
        self.worker_context = TestWorkerExecutionContext("test-pkg3-worker")
        identity = self.worker_context.current()
        envelope = {"envelopeDigest": c.digest("test-pkg3-envelope"),
            "outputConstraints": deepcopy(self.grant["subject"]["outputConstraints"])}
        request = {"generationRequestRef": "test-pkg3-generation-request"}
        request_digest = c.digest(request)
        self.job = {"jobRef": "test-pkg3-media-job", "revision": 2,
            "state": "RUNNING", "maxAttempts": 1,
            "request": request, "requestDigest": request_digest,
            "executionEnvelope": envelope,
            "attempts": [{"attemptRef": "test-pkg3-attempt", "attemptNumber": 1,
                "workerRef": identity["workerRef"], "state": "RUNNING"}],
            "lease": {"workerRef": identity["workerRef"],
                "leaseToken": "test-pkg3-lease", "leasedAt": "2030-01-01T00:00:10.000Z",
                "expiresAt": "2030-01-01T00:00:40.000Z"}}
        self.job_port = SyntheticJobPort(self.job)
        self.consumer = GenerationDispatchConsumer(foundation=self.grants.service,
            job_port=self.job_port, worker_context=self.worker_context,
            clock=self.clock)
        self.command = {"workspaceRef": self.grant["workspaceRef"],
            "productionRunRef": self.grant["productionRunRef"],
            "generationDispatchGrantRef": self.grant["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": self.grant["payloadDigest"],
            "mediaJobRef": self.job["jobRef"],
            "attemptRef": self.job["attempts"][-1]["attemptRef"],
            "workerRef": identity["workerRef"],
            "expectedJobRevision": self.job["revision"],
            "expectedLeaseTokenDigest": c.digest(self.job["lease"]["leaseToken"]),
            "idempotencyKey": "test-pkg3-consume",
            "snapshotTokens": self.consumer.snapshot_tokens(self.grant["workspaceRef"],
                self.grant["productionRunRef"])}
        self.transport = CpuIsolatedFakeTransport(self.clock, root=self.root)

    def consume(self):
        return self.consumer.consume(deepcopy(self.command))


class ExecutionFixture(BindingFixture):
    def __init__(self, case, *, fault: str | None = None,
                 worker_ref: str = "test-pkg3-worker"):
        super().__init__(case)
        self.clock.monotonic_value = 1000.0
        self.clock.monotonic = lambda: self.clock.monotonic_value
        issued = self.issue()
        if "grant" not in issued:
            raise AssertionError(issued)
        self.grant = issued["grant"]
        self.route_result = self.route(self.grant)
        self.job = self.jobs()[0]
        self.worker_context = TestWorkerExecutionContext(worker_ref)
        self.job_port = MediaJobGenerationDispatchPort(
            coordinator=self.coordinators[0], coordination=self.dispatch.coordination,
            clock=self.clock)
        self.consumer = GenerationDispatchConsumer(
            foundation=self.dispatch.boundary._foundation,
            job_port=self.job_port, worker_context=self.worker_context,
            clock=self.clock)
        self.transport = CpuIsolatedFakeTransport(self.clock, root=self.root,
            fault=fault)
        self.result_boundary = GenerationDispatchResultBoundary(
            self.coordinators[0], clock=self.clock)
        self.executor = GenerationDispatchExecutor(
            coordinator=self.coordinators[0], consumer=self.consumer,
            worker_context=self.worker_context, transport=self.transport,
            clock=self.clock, coordination=self.dispatch.coordination,
            result_boundary=self.result_boundary, job_port=self.job_port)

    def claim_command(self):
        identity = self.worker_context.current()
        claimed = self.job_port.claim(self.scope["workspaceRef"],
            self.scope["productionRunRef"], self.job["jobRef"], identity)
        binding = claimed["dispatchGrantBinding"]
        command = {"workspaceRef": self.scope["workspaceRef"],
            "productionRunRef": self.scope["productionRunRef"],
            "generationDispatchGrantRef": binding["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": binding["generationDispatchGrantDigest"],
            "mediaJobRef": claimed["jobRef"],
            "attemptRef": claimed["attempts"][-1]["attemptRef"],
            "workerRef": identity["workerRef"],
            "expectedJobRevision": claimed["revision"],
            "expectedLeaseTokenDigest": c.digest(claimed["lease"]["leaseToken"]),
            "idempotencyKey": "test-pkg3-consume",
            "snapshotTokens": self.consumer.snapshot_tokens(
                self.scope["workspaceRef"], self.scope["productionRunRef"])}
        return claimed, command

    def claim_and_consume(self):
        claimed, command = self.claim_command()
        return claimed, command, self.consumer.consume(command)

    def execute(self):
        return self.executor.execute(self.scope["workspaceRef"],
            self.scope["productionRunRef"], self.job["jobRef"])

    def current_job(self):
        return self.queues[0].get(self.scope["workspaceRef"],
            self.scope["productionRunRef"], self.job["jobRef"])

    def advance(self, seconds: float):
        self.clock.monotonic_value += seconds
        now = c.utc(self.clock.value) + timedelta(seconds=seconds)
        self.clock.value = now.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
