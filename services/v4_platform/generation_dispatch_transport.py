"""CPU-isolated Package 3 transport contracts.

This module deliberately provides no network implementation.  A transport is
injected into the internal executor and must expose the initial request-byte
commit separately from response collection so the V5 gate never surrounds a
long-running provider call.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Protocol


CONNECT_NOT_STARTED = "CONNECT_NOT_STARTED"
REQUEST_BYTES_NOT_COMMITTED = "REQUEST_BYTES_NOT_COMMITTED"
REQUEST_BYTES_COMMITTED = "REQUEST_BYTES_COMMITTED"
RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
SUBMISSION_OUTCOME_UNKNOWN = "SUBMISSION_OUTCOME_UNKNOWN"

TRANSPORT_REQUEST_SCHEMA = "v4.generation-dispatch-transport-request.v1"
TRANSPORT_SUBMISSION_SCHEMA = "v4.generation-dispatch-transport-submission.v1"
TRANSPORT_RESULT_SCHEMA = "v4.generation-dispatch-transport-result.v1"
DISPATCH_RESULT_SCHEMA = "v4.generation-dispatch-result.v1"

_HEX = re.compile(r"[0-9a-f]{64}")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}")
_ERROR = re.compile(r"[A-Z][A-Z0-9_]{0,119}")
_UTC = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z"
)


class GenerationDispatchTransportError(RuntimeError):
    """Closed transport failure carrying only safe phase facts."""

    def __init__(self, code: str, phase: str, *, request_committed: bool,
                 submission: Mapping[str, Any] | None = None):
        if (type(code) is not str or _ERROR.fullmatch(code) is None or phase not in {
                CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
                REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED,
                SUBMISSION_OUTCOME_UNKNOWN} or type(request_committed) is not bool):
            raise ValueError("invalid transport failure")
        if request_committed != (submission is not None):
            raise ValueError("transport failure submission state is inconsistent")
        self.code = code
        self.phase = phase
        self.request_committed = request_committed
        self.submission = (validate_transport_submission(submission)
                           if submission is not None else None)
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TransportReadResult:
    submission: dict[str, Any]
    receipt: dict[str, Any]
    artifact_bytes: bytes | None

    def __post_init__(self) -> None:
        submission = validate_transport_submission(self.submission)
        receipt = validate_transport_result(self.receipt)
        object.__setattr__(self, "submission", submission)
        object.__setattr__(self, "receipt", receipt)
        if (receipt["requestDigest"] != submission["requestDigest"]
                or receipt["transportSubmissionRef"]
                    != submission["transportSubmissionRef"]
                or receipt["transportSubmissionDigest"]
                    != submission["payloadDigest"]):
            raise ValueError("transport result/submission binding mismatch")
        if receipt["outcome"] == "SUCCEEDED":
            if type(self.artifact_bytes) is not bytes or not self.artifact_bytes:
                raise ValueError("successful transport result has no artifact bytes")
            if sha256(self.artifact_bytes).hexdigest() != receipt["artifactDigest"]:
                raise ValueError("transport artifact digest mismatch")
        elif self.artifact_bytes is not None:
            raise ValueError("non-success transport result contains artifact bytes")


class GenerationDispatchTransportPort(Protocol):
    TEST_ONLY: bool
    CPU_ISOLATED: bool

    def open_exchange(self, request: Mapping[str, Any]) -> Any:
        """Open an inert exchange without committing request bytes."""
        ...

    def commit_request_once(self, exchange: Any) -> dict[str, Any]:
        """Commit the initial request bytes exactly once or raise a closed error."""
        ...

    def read_result(self, exchange: Any,
                    submission: Mapping[str, Any]) -> TransportReadResult:
        """Wait for/read the result.  This is called after the V5 gate is released."""
        ...


def _canonical(value: Any) -> bytes:
    def walk(item: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("transport value is too deep")
        if type(item) is dict:
            if any(type(key) is not str for key in item):
                raise ValueError("transport object key is invalid")
            for child in item.values():
                walk(child, depth + 1)
        elif type(item) is list:
            for child in item:
                walk(child, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("transport value is not canonical JSON")
    walk(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _exact(value: Any, fields: set[str]) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("transport object is not closed")
    _canonical(value)
    return value


def _ref(value: Any) -> None:
    if type(value) is not str or _REF.fullmatch(value) is None:
        raise ValueError("transport ref is invalid")


def _sha(value: Any) -> None:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("transport digest is invalid")


def _utc(value: Any) -> None:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise ValueError("transport UTC value is invalid")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("transport UTC value is invalid") from exc


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = digest(result)
    return result


def _verify_seal(value: Mapping[str, Any]) -> None:
    _sha(value["payloadDigest"])
    if value["payloadDigest"] != digest({k: v for k, v in value.items()
                                         if k != "payloadDigest"}):
        raise ValueError("transport payload digest mismatch")


_LINEAGE_FIELDS = {
    "generationDispatchGrantRef", "generationDispatchGrantDigest",
    "mediaJobRef", "attemptRef", "generationRequestRef",
    "generationRequestDigest", "executionEnvelopeDigest", "workflowDigest",
}


def validate_transport_request(value: Any) -> dict[str, Any]:
    fields = {"schemaVersion", "workspaceRef", "productionRunRef", "workerRef",
        *_LINEAGE_FIELDS, "outputConstraints", "workflow", "connectionTimeoutMs",
        "requestTimeoutMs", "transportPolicy", "testOnly", "payloadDigest"}
    _exact(value, fields)
    if value["schemaVersion"] != TRANSPORT_REQUEST_SCHEMA or value["testOnly"] is not True:
        raise ValueError("only TEST_ONLY transport requests are accepted")
    for name in ("workspaceRef", "productionRunRef", "workerRef",
                 "generationDispatchGrantRef", "mediaJobRef", "attemptRef",
                 "generationRequestRef"):
        _ref(value[name])
    for name in ("generationDispatchGrantDigest", "generationRequestDigest",
                 "executionEnvelopeDigest", "workflowDigest"):
        _sha(value[name])
    if (type(value["connectionTimeoutMs"]) is not int
            or value["connectionTimeoutMs"] < 1
            or type(value["requestTimeoutMs"]) is not int
            or value["requestTimeoutMs"] < 1):
        raise ValueError("transport timeout is invalid")
    policy = _exact(value["transportPolicy"], {"maxPromptSubmissions",
        "postRetryAllowed", "redirectAllowed", "fallbackAllowed"})
    if policy != {"maxPromptSubmissions": 1, "postRetryAllowed": False,
            "redirectAllowed": False, "fallbackAllowed": False}:
        raise ValueError("transport policy is not at-most-once")
    output = _exact(value["outputConstraints"], {"mediaKind", "mediaType",
        "width", "height", "durationFrames", "frameRate"})
    if (output["mediaKind"], output["mediaType"]) != ("video", "video/mp4"):
        raise ValueError("transport output is not the approved video shape")
    for name in ("width", "height", "durationFrames", "frameRate"):
        if type(output[name]) is not int or output[name] < 1:
            raise ValueError("transport output constraint is invalid")
    if type(value["workflow"]) is not dict or digest(value["workflow"]) != value["workflowDigest"]:
        raise ValueError("transport workflow binding mismatch")
    _verify_seal(value)
    return deepcopy(value)


def make_transport_request(*, workspace_ref: str, production_run_ref: str,
        worker_ref: str, generation_dispatch_grant_ref: str,
        generation_dispatch_grant_digest: str, media_job_ref: str,
        attempt_ref: str, generation_request_ref: str,
        generation_request_digest: str, execution_envelope_digest: str,
        workflow_digest: str, output_constraints: Mapping[str, Any],
        workflow: Mapping[str, Any], connection_timeout_ms: int,
        request_timeout_ms: int, transport_policy: Mapping[str, Any]) -> dict[str, Any]:
    value = {"schemaVersion": TRANSPORT_REQUEST_SCHEMA,
        "workspaceRef": workspace_ref, "productionRunRef": production_run_ref,
        "workerRef": worker_ref,
        "generationDispatchGrantRef": generation_dispatch_grant_ref,
        "generationDispatchGrantDigest": generation_dispatch_grant_digest,
        "mediaJobRef": media_job_ref, "attemptRef": attempt_ref,
        "generationRequestRef": generation_request_ref,
        "generationRequestDigest": generation_request_digest,
        "executionEnvelopeDigest": execution_envelope_digest,
        "workflowDigest": workflow_digest,
        "outputConstraints": deepcopy(dict(output_constraints)),
        "workflow": deepcopy(dict(workflow)),
        "connectionTimeoutMs": connection_timeout_ms,
        "requestTimeoutMs": request_timeout_ms,
        "transportPolicy": deepcopy(dict(transport_policy)), "testOnly": True}
    return validate_transport_request(_sealed(value))


def validate_transport_submission(value: Any) -> dict[str, Any]:
    _exact(value, {"schemaVersion", "phase", "transportSubmissionRef",
        "requestDigest", "committedAt", "testOnly", "payloadDigest"})
    if (value["schemaVersion"] != TRANSPORT_SUBMISSION_SCHEMA
            or value["phase"] != REQUEST_BYTES_COMMITTED
            or value["testOnly"] is not True):
        raise ValueError("transport submission is invalid")
    _ref(value["transportSubmissionRef"])
    _sha(value["requestDigest"])
    _utc(value["committedAt"])
    _verify_seal(value)
    return deepcopy(value)


def make_transport_submission(*, transport_submission_ref: str,
        request_digest: str, committed_at: str) -> dict[str, Any]:
    return validate_transport_submission(_sealed({
        "schemaVersion": TRANSPORT_SUBMISSION_SCHEMA,
        "phase": REQUEST_BYTES_COMMITTED,
        "transportSubmissionRef": transport_submission_ref,
        "requestDigest": request_digest, "committedAt": committed_at,
        "testOnly": True}))


def validate_transport_result(value: Any) -> dict[str, Any]:
    _exact(value, {"schemaVersion", "phase", "outcome", "requestDigest",
        "transportSubmissionRef", "transportSubmissionDigest", "artifactDigest",
        "failureCode", "receivedAt", "testOnly", "payloadDigest"})
    if (value["schemaVersion"] != TRANSPORT_RESULT_SCHEMA
            or value["phase"] not in {RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN}
            or value["outcome"] not in {"SUCCEEDED", "FAILED", "UNKNOWN"}
            or value["testOnly"] is not True):
        raise ValueError("transport result is invalid")
    _sha(value["requestDigest"])
    for name in ("transportSubmissionRef", "transportSubmissionDigest"):
        if value[name] is not None:
            (_ref if name.endswith("Ref") else _sha)(value[name])
    if (value["transportSubmissionRef"] is None) != (value["transportSubmissionDigest"] is None):
        raise ValueError("transport result submission binding is incomplete")
    if value["outcome"] == "SUCCEEDED":
        _sha(value["artifactDigest"])
        if (value["phase"] != RESPONSE_RECEIVED or value["failureCode"] is not None
                or value["transportSubmissionRef"] is None):
            raise ValueError("successful transport result is inconsistent")
    else:
        if (value["artifactDigest"] is not None
                or type(value["failureCode"]) is not str
                or _ERROR.fullmatch(value["failureCode"]) is None):
            raise ValueError("failed transport result is inconsistent")
        if value["outcome"] == "UNKNOWN" and value["phase"] != SUBMISSION_OUTCOME_UNKNOWN:
            raise ValueError("unknown transport result phase is invalid")
    _utc(value["receivedAt"])
    _verify_seal(value)
    return deepcopy(value)


def make_transport_result(*, outcome: str, request_digest: str,
        submission: Mapping[str, Any] | None, artifact_digest: str | None,
        failure_code: str | None, received_at: str) -> dict[str, Any]:
    bound = validate_transport_submission(submission) if submission is not None else None
    value = {"schemaVersion": TRANSPORT_RESULT_SCHEMA,
        "phase": (SUBMISSION_OUTCOME_UNKNOWN if outcome == "UNKNOWN" else RESPONSE_RECEIVED),
        "outcome": outcome, "requestDigest": request_digest,
        "transportSubmissionRef": (bound["transportSubmissionRef"] if bound else None),
        "transportSubmissionDigest": (bound["payloadDigest"] if bound else None),
        "artifactDigest": artifact_digest, "failureCode": failure_code,
        "receivedAt": received_at, "testOnly": True}
    return validate_transport_result(_sealed(value))


def validate_dispatch_result(value: Any, *, job: Mapping[str, Any] | None = None) -> dict[str, Any]:
    _exact(value, {"schemaVersion", "outcome", "phase", *_LINEAGE_FIELDS,
        "transportSubmissionRef", "transportSubmissionDigest", "artifactDigest",
        "failureCode", "committedRequestBytes", "testOnly", "createdAt",
        "payloadDigest"})
    if (value["schemaVersion"] != DISPATCH_RESULT_SCHEMA
            or value["outcome"] not in {"SUCCEEDED", "FAILED", "UNKNOWN"}
            or value["phase"] not in {CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
                REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN}
            or type(value["committedRequestBytes"]) is not bool
            or value["testOnly"] is not True):
        raise ValueError("dispatch result is invalid")
    for name in ("generationDispatchGrantRef", "mediaJobRef", "attemptRef",
                 "generationRequestRef"):
        _ref(value[name])
    for name in ("generationDispatchGrantDigest", "generationRequestDigest",
                 "executionEnvelopeDigest", "workflowDigest"):
        _sha(value[name])
    for name in ("transportSubmissionRef", "transportSubmissionDigest"):
        if value[name] is not None:
            (_ref if name.endswith("Ref") else _sha)(value[name])
    if (value["transportSubmissionRef"] is None) != (value["transportSubmissionDigest"] is None):
        raise ValueError("dispatch result submission binding is incomplete")
    if value["committedRequestBytes"] != (value["transportSubmissionRef"] is not None):
        raise ValueError("dispatch result commit fact is inconsistent")
    if value["outcome"] == "SUCCEEDED":
        _sha(value["artifactDigest"])
        if value["phase"] != RESPONSE_RECEIVED or value["failureCode"] is not None:
            raise ValueError("successful dispatch result is inconsistent")
    else:
        if (value["artifactDigest"] is not None
                or type(value["failureCode"]) is not str
                or _ERROR.fullmatch(value["failureCode"]) is None):
            raise ValueError("non-success dispatch result is inconsistent")
        if value["outcome"] == "UNKNOWN" and value["phase"] != SUBMISSION_OUTCOME_UNKNOWN:
            raise ValueError("unknown dispatch result phase is invalid")
    _utc(value["createdAt"])
    _verify_seal(value)
    if job is not None:
        request = job.get("request", {})
        envelope = job.get("executionEnvelope", {})
        binding = job.get("dispatchGrantBinding", {})
        attempts = job.get("attempts", [])
        latest = attempts[-1] if isinstance(attempts, list) and attempts else {}
        expected = {
            "generationDispatchGrantRef": binding.get("generationDispatchGrantRef"),
            "generationDispatchGrantDigest": binding.get("generationDispatchGrantDigest"),
            "mediaJobRef": job.get("jobRef"), "attemptRef": latest.get("attemptRef"),
            "generationRequestRef": request.get("generationRequestRef"),
            "generationRequestDigest": job.get("requestDigest"),
            "executionEnvelopeDigest": envelope.get("envelopeDigest"),
        }
        if any(value[name] != expected[name] for name in _LINEAGE_FIELDS
               if name != "workflowDigest"):
            raise ValueError("dispatch result lineage mismatch")
    return deepcopy(value)


def make_dispatch_result(*, outcome: str, phase: str,
        job: Mapping[str, Any], submission: Mapping[str, Any] | None,
        workflow_digest: str, artifact_digest: str | None, failure_code: str | None,
        created_at: str) -> dict[str, Any]:
    bound = validate_transport_submission(submission) if submission is not None else None
    request, envelope, binding = job["request"], job["executionEnvelope"], job["dispatchGrantBinding"]
    latest = job["attempts"][-1]
    value = {"schemaVersion": DISPATCH_RESULT_SCHEMA, "outcome": outcome,
        "phase": phase,
        "generationDispatchGrantRef": binding["generationDispatchGrantRef"],
        "generationDispatchGrantDigest": binding["generationDispatchGrantDigest"],
        "mediaJobRef": job["jobRef"], "attemptRef": latest["attemptRef"],
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestDigest": job["requestDigest"],
        "executionEnvelopeDigest": envelope["envelopeDigest"],
        "workflowDigest": workflow_digest,
        "transportSubmissionRef": (bound["transportSubmissionRef"] if bound else None),
        "transportSubmissionDigest": (bound["payloadDigest"] if bound else None),
        "artifactDigest": artifact_digest, "failureCode": failure_code,
        "committedRequestBytes": bound is not None, "testOnly": True,
        "createdAt": created_at}
    return validate_dispatch_result(_sealed(value), job=job)
