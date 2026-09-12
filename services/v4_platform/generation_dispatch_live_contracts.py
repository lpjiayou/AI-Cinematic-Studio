"""Closed live wire evidence; deliberately disjoint from the historical Fake DTOs.

These are internal data contracts, not execution authority. In particular a local
submission reference never stands in for the server's prompt UUID, and a missing
receipt cannot prove that no bytes were sent.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import math
import re
from typing import Any, Mapping

from .generation_dispatch_transport import (
    CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED, REQUEST_BYTES_COMMITTED,
    RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN, _canonical, _exact, _ref,
    _sha, _utc, _sealed, _verify_seal, _LINEAGE_FIELDS, digest,
)

LIVE_REQUEST_SCHEMA = "v4.generation-dispatch-live-transport-request.v1"
LIVE_SUBMISSION_SCHEMA = "v4.generation-dispatch-live-transport-submission.v1"
LIVE_RESULT_SCHEMA = "v4.generation-dispatch-live-transport-result.v1"
LIVE_DISPATCH_RESULT_SCHEMA = "v4.generation-dispatch-live-result.v1"
NOT_STARTED = "NOT_STARTED"
ZERO_BYTES_PROVEN = "ZERO_BYTES_PROVEN"
MAY_HAVE_BEEN_SENT = "MAY_HAVE_BEEN_SENT"
LOCAL_WRITE_COMPLETE = "LOCAL_WRITE_COMPLETE"
WRITE_STATES = {NOT_STARTED, ZERO_BYTES_PROVEN, MAY_HAVE_BEEN_SENT, LOCAL_WRITE_COMPLETE}
_PROMPT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_COMPONENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,199}")
_ERROR = re.compile(r"[A-Z][A-Z0-9_]{0,119}")
_PIN_FIELDS = {"endpointDigest", "executionConfigDigest", "runtimeBindingDigest", "backendDecisionDigest"}
_TIMEOUT_FIELDS = {"connectionTimeoutMs", "requestTimeoutMs", "historyTimeoutMs", "postprocessTimeoutMs"}
_POLICY = {"maxPromptSubmissions": 1, "postRetryAllowed": False,
           "redirectAllowed": False, "fallbackAllowed": False}


def validate_prompt_id(value: Any) -> str:
    if type(value) is not str or _PROMPT_ID.fullmatch(value) is None:
        raise ValueError("invalid provider prompt identifier")
    return value


def _positive(value: Any) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("invalid positive integer")


def _component(value: Any) -> None:
    if (type(value) is not str or _COMPONENT.fullmatch(value) is None
            or ".." in value):
        raise ValueError("invalid output path component")


def _subfolder(value: Any) -> None:
    if type(value) is not str or len(value) > 500:
        raise ValueError("invalid output subfolder")
    if value:
        for component in value.split("/"):
            _component(component)


def _lineage(value: Mapping[str, Any]) -> None:
    for name in _LINEAGE_FIELDS:
        (_ref if name.endswith("Ref") else _sha)(value[name])


def validate_output_binding(value: Any) -> dict:
    _exact(value, {"nodeId", "outputKey", "mediaType", "frameCount", "filenamePrefix", "subfolder"})
    _ref(value["nodeId"]); _component(value["filenamePrefix"]); _subfolder(value["subfolder"])
    if (value["mediaType"], value["outputKey"], value["frameCount"]) not in {
            ("image/png", "images", 49), ("video/mp4", "images", 1),
            ("video/mp4", "videos", 1)} or type(value["frameCount"]) is not int:
        raise ValueError("unapproved native output shape")
    return deepcopy(value)


def _postprocess(value: Any, output: Mapping[str, Any]) -> None:
    if output["mediaType"] == "video/mp4":
        if value is not None:
            raise ValueError("direct output cannot claim frame derivation")
        return
    _exact(value, {"profileId", "keepIndices", "dropIndices", "frameRate"})
    _ref(value["profileId"])
    if (type(value["keepIndices"]) is not list or value["keepIndices"] != list(range(48))
            or any(type(i) is not int for i in value["keepIndices"])
            or value["dropIndices"] != [48] or type(value["dropIndices"][0]) is not int
            or type(value["frameRate"]) is not int or value["frameRate"] != 24):
        raise ValueError("unapproved frame derivation")


def validate_live_transport_request(value: Any) -> dict:
    _exact(value, {"schemaVersion", "workspaceRef", "productionRunRef", "workerRef",
        *_LINEAGE_FIELDS, *_PIN_FIELDS, *_TIMEOUT_FIELDS, "workflow", "outputConstraints",
        "outputBinding", "postprocessBinding", "transportPolicy", "payloadDigest"})
    if value["schemaVersion"] != LIVE_REQUEST_SCHEMA:
        raise ValueError("not a live transport request")
    _lineage(value)
    for name in ("workspaceRef", "productionRunRef", "workerRef"):
        _ref(value[name])
    for name in _PIN_FIELDS:
        _sha(value[name])
    for name in _TIMEOUT_FIELDS:
        _positive(value[name])
    if value["connectionTimeoutMs"] > value["requestTimeoutMs"]:
        raise ValueError("connection budget exceeds request budget")
    if _canonical(value["transportPolicy"]) != _canonical(_POLICY):
        raise ValueError("transport policy is not at-most-once")
    _exact(value["outputConstraints"], {"mediaKind", "mediaType", "width", "height", "durationFrames", "frameRate"})
    constraints = value["outputConstraints"]
    if (constraints["mediaKind"], constraints["mediaType"]) != ("video", "video/mp4"):
        raise ValueError("unsupported final output")
    for name in ("width", "height", "durationFrames", "frameRate"):
        _positive(constraints[name])
    output = validate_output_binding(value["outputBinding"])
    _postprocess(value["postprocessBinding"], output)
    if output["mediaType"] == "image/png" and tuple(constraints[n] for n in
            ("width", "height", "durationFrames", "frameRate")) != (704, 1280, 48, 24):
        raise ValueError("native frame derivation final shape mismatch")
    if (type(value["workflow"]) is not dict
            or digest(value["workflow"]) != value["workflowDigest"]
            or output["nodeId"] not in value["workflow"]):
        raise ValueError("live workflow binding mismatch")
    _verify_seal(value)
    return deepcopy(value)


def make_live_transport_request(*, workspace_ref: str, production_run_ref: str,
        worker_ref: str, generation_dispatch_grant_ref: str,
        generation_dispatch_grant_digest: str, media_job_ref: str, attempt_ref: str,
        generation_request_ref: str, generation_request_digest: str,
        execution_envelope_digest: str, workflow_digest: str,
        output_constraints: Mapping[str, Any], workflow: Mapping[str, Any],
        connection_timeout_ms: int, request_timeout_ms: int, history_timeout_ms: int,
        postprocess_timeout_ms: int, transport_policy: Mapping[str, Any],
        endpoint_digest: str, execution_config_digest: str, runtime_binding_digest: str,
        backend_decision_digest: str, output_binding: Mapping[str, Any],
        postprocess_binding: Mapping[str, Any] | None) -> dict:
    value = {"schemaVersion": LIVE_REQUEST_SCHEMA, "workspaceRef": workspace_ref,
        "productionRunRef": production_run_ref, "workerRef": worker_ref,
        "generationDispatchGrantRef": generation_dispatch_grant_ref,
        "generationDispatchGrantDigest": generation_dispatch_grant_digest,
        "mediaJobRef": media_job_ref, "attemptRef": attempt_ref,
        "generationRequestRef": generation_request_ref,
        "generationRequestDigest": generation_request_digest,
        "executionEnvelopeDigest": execution_envelope_digest, "workflowDigest": workflow_digest,
        "outputConstraints": dict(output_constraints), "workflow": dict(workflow),
        "connectionTimeoutMs": connection_timeout_ms, "requestTimeoutMs": request_timeout_ms,
        "historyTimeoutMs": history_timeout_ms, "postprocessTimeoutMs": postprocess_timeout_ms,
        "transportPolicy": dict(transport_policy), "endpointDigest": endpoint_digest,
        "executionConfigDigest": execution_config_digest, "runtimeBindingDigest": runtime_binding_digest,
        "backendDecisionDigest": backend_decision_digest, "outputBinding": dict(output_binding),
        "postprocessBinding": dict(postprocess_binding) if postprocess_binding is not None else None}
    return validate_live_transport_request(_sealed(value))


def validate_live_transport_submission(value: Any) -> dict:
    _exact(value, {"schemaVersion", "phase", "transportSubmissionRef", "requestDigest",
        *_LINEAGE_FIELDS, "requestWriteState", "committedAt", "payloadDigest"})
    if (value["schemaVersion"] != LIVE_SUBMISSION_SCHEMA
            or value["phase"] != REQUEST_BYTES_COMMITTED
            or value["requestWriteState"] != LOCAL_WRITE_COMPLETE):
        raise ValueError("invalid local live submission")
    _lineage(value); _ref(value["transportSubmissionRef"]); _sha(value["requestDigest"])
    if not value["transportSubmissionRef"].startswith("local-submission-"):
        raise ValueError("local submission namespace is required")
    _utc(value["committedAt"]); _verify_seal(value)
    return deepcopy(value)


def make_live_transport_submission(*, request: Mapping[str, Any],
        transport_submission_ref: str, committed_at: str) -> dict:
    request = validate_live_transport_request(request)
    return validate_live_transport_submission(_sealed({"schemaVersion": LIVE_SUBMISSION_SCHEMA,
        "phase": REQUEST_BYTES_COMMITTED, "transportSubmissionRef": transport_submission_ref,
        "requestDigest": request["payloadDigest"], **{n: request[n] for n in _LINEAGE_FIELDS},
        "requestWriteState": LOCAL_WRITE_COMPLETE, "committedAt": committed_at}))


def validate_native_artifacts(value: Any) -> list:
    if type(value) is not list or len(value) not in {0, 1, 49}:
        raise ValueError("invalid native artifact count")
    identities = set()
    for index, item in enumerate(value):
        _exact(item, {"index", "nodeId", "filename", "subfolder", "type", "mediaType", "byteSize", "sha256"})
        if type(item["index"]) is not int or item["index"] != index or item["type"] != "output":
            raise ValueError("invalid native artifact order or owner")
        _ref(item["nodeId"]); _component(item["filename"]); _subfolder(item["subfolder"])
        _positive(item["byteSize"]); _sha(item["sha256"])
        if item["mediaType"] not in {"image/png", "video/mp4"}:
            raise ValueError("invalid native media type")
        key = (item["nodeId"], item["subfolder"], item["filename"])
        if key in identities:
            raise ValueError("duplicate native artifact")
        identities.add(key)
    if value and ((len(value) == 49) != all(i["mediaType"] == "image/png" for i in value)):
        raise ValueError("native sequence shape mismatch")
    if len(value) == 49:
        previous = None
        first = value[0]
        for item in value:
            match = re.fullmatch(r"(.+)_([0-9]{5,})_\.png", item["filename"])
            if (match is None or item["nodeId"] != first["nodeId"]
                    or item["subfolder"] != first["subfolder"]):
                raise ValueError("native sequence origin mismatch")
            current = (match.group(1), int(match.group(2)))
            if previous is not None and (current[0] != previous[0] or current[1] != previous[1] + 1):
                raise ValueError("native sequence counter order mismatch")
            previous = current
    return deepcopy(value)


def validate_derivation(value: Any, native_artifacts: list, artifact_digest: str | None) -> dict | None:
    if value is None:
        if len(native_artifacts) == 49:
            raise ValueError("native frame derivation missing")
        return None
    _exact(value, {"schemaVersion", "profileId", "nativeSequenceDigest", "keptIndices",
        "droppedIndices", "frameRate", "width", "height", "frameCount", "outputSha256"})
    _ref(value["profileId"])
    if (value["schemaVersion"] != "v4.generation-dispatch-frame-derivation.v1"
            or len(native_artifacts) != 49 or value["nativeSequenceDigest"] != digest(native_artifacts)
            or value["keptIndices"] != list(range(48)) or value["droppedIndices"] != [48]
            or any(type(i) is not int for i in value["keptIndices"] + value["droppedIndices"])
            or any(type(value[n]) is not int for n in ("frameRate", "width", "height", "frameCount"))
            or tuple(value[n] for n in ("frameRate", "width", "height", "frameCount")) != (24, 704, 1280, 48)
            or value["outputSha256"] != artifact_digest):
        raise ValueError("invalid frame derivation binding")
    _sha(value["outputSha256"])
    return deepcopy(value)


def _result_common(value: Mapping[str, Any]) -> None:
    _lineage(value)
    if value["outcome"] not in {"SUCCEEDED", "FAILED", "UNKNOWN"} or value["requestWriteState"] not in WRITE_STATES:
        raise ValueError("invalid live outcome or write state")
    if value["phase"] not in {CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
            REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN}:
        raise ValueError("invalid live phase")
    for n in ("transportSubmissionRef", "transportSubmissionDigest"):
        if value[n] is not None:
            (_ref if n.endswith("Ref") else _sha)(value[n])
    if (value["transportSubmissionRef"] is None) != (value["transportSubmissionDigest"] is None):
        raise ValueError("incomplete local submission binding")
    if value["transportSubmissionRef"] is not None and value["requestWriteState"] != LOCAL_WRITE_COMPLETE:
        raise ValueError("local completion evidence is inconsistent")
    if value["requestWriteState"] in {NOT_STARTED, ZERO_BYTES_PROVEN} and (
            value["outcome"] != "FAILED" or value["phase"] not in {
                CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED}):
        raise ValueError("zero-write phase evidence is inconsistent")
    if value["providerPromptId"] is not None:
        validate_prompt_id(value["providerPromptId"])
        if value["requestWriteState"] != LOCAL_WRITE_COMPLETE or value["transportSubmissionRef"] is None:
            raise ValueError("provider receipt lacks local binding")
    native = validate_native_artifacts(value["nativeArtifacts"])
    validate_derivation(value["derivation"], native, value["artifactDigest"])
    if value["outcome"] == "SUCCEEDED":
        _sha(value["artifactDigest"])
        if (value["failureCode"] is not None or value["phase"] != RESPONSE_RECEIVED
                or value["providerPromptId"] is None or not native):
            raise ValueError("inconsistent live success")
    else:
        if (value["artifactDigest"] is not None or native or value["derivation"] is not None
                or type(value["failureCode"]) is not str or _ERROR.fullmatch(value["failureCode"]) is None):
            raise ValueError("inconsistent live failure")
        if (value["outcome"] == "UNKNOWN") != (value["phase"] == SUBMISSION_OUTCOME_UNKNOWN):
            raise ValueError("unknown live phase mismatch")
        if value["requestWriteState"] == MAY_HAVE_BEEN_SENT and value["outcome"] != "UNKNOWN":
            raise ValueError("possible send cannot be classified as zero write")
    _verify_seal(value)


_RESULT_FIELDS = {"outcome", "phase", *_LINEAGE_FIELDS, "transportSubmissionRef",
    "transportSubmissionDigest", "requestWriteState", "providerPromptId", "artifactDigest",
    "failureCode", "nativeArtifacts", "derivation", "payloadDigest"}


def validate_live_transport_result(value: Any) -> dict:
    _exact(value, {"schemaVersion", "requestDigest", "receivedAt", *_RESULT_FIELDS})
    if value["schemaVersion"] != LIVE_RESULT_SCHEMA:
        raise ValueError("not a live transport result")
    _sha(value["requestDigest"]); _utc(value["receivedAt"]); _result_common(value)
    return deepcopy(value)


def make_live_transport_result(*, request: Mapping[str, Any], submission: Mapping[str, Any] | None,
        outcome: str, phase: str, request_write_state: str, provider_prompt_id: str | None,
        artifact_digest: str | None, failure_code: str | None, received_at: str,
        native_artifacts: list | None = None, derivation: dict | None = None) -> dict:
    request = validate_live_transport_request(request)
    bound = validate_live_transport_submission(submission) if submission is not None else None
    if bound is not None and (bound["requestDigest"] != request["payloadDigest"]
            or any(bound[n] != request[n] for n in _LINEAGE_FIELDS)):
        raise ValueError("live submission belongs to another request")
    return validate_live_transport_result(_sealed({"schemaVersion": LIVE_RESULT_SCHEMA,
        "requestDigest": request["payloadDigest"], **{n: request[n] for n in _LINEAGE_FIELDS},
        "outcome": outcome, "phase": phase, "requestWriteState": request_write_state,
        "transportSubmissionRef": bound["transportSubmissionRef"] if bound else None,
        "transportSubmissionDigest": bound["payloadDigest"] if bound else None,
        "providerPromptId": provider_prompt_id, "artifactDigest": artifact_digest,
        "failureCode": failure_code, "receivedAt": received_at,
        "nativeArtifacts": native_artifacts or [], "derivation": derivation}))


def validate_live_dispatch_result(value: Any, *, job: Mapping[str, Any] | None = None) -> dict:
    _exact(value, {"schemaVersion", "createdAt", "transportResultDigest", *_RESULT_FIELDS})
    if value["schemaVersion"] != LIVE_DISPATCH_RESULT_SCHEMA:
        raise ValueError("not a live dispatch result")
    _utc(value["createdAt"]); _result_common(value)
    if value["transportResultDigest"] is not None:
        _sha(value["transportResultDigest"])
    if value["outcome"] == "SUCCEEDED" and value["transportResultDigest"] is None:
        raise ValueError("successful dispatch lacks transport receipt")
    if job is not None:
        expected = _job_lineage(job, value["workflowDigest"])
        if any(value[n] != expected[n] for n in _LINEAGE_FIELDS):
            raise ValueError("live dispatch job lineage mismatch")
    return deepcopy(value)


def _job_lineage(job: Mapping[str, Any], workflow_digest: str) -> dict:
    request, binding = job["request"], job["dispatchGrantBinding"]
    return {"generationDispatchGrantRef": binding["generationDispatchGrantRef"],
        "generationDispatchGrantDigest": binding["generationDispatchGrantDigest"],
        "mediaJobRef": job["jobRef"], "attemptRef": job["attempts"][-1]["attemptRef"],
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestDigest": job["requestDigest"],
        "executionEnvelopeDigest": job["executionEnvelope"]["envelopeDigest"],
        "workflowDigest": workflow_digest}


def make_live_dispatch_result(*, outcome: str, phase: str, job: Mapping[str, Any],
        submission: Mapping[str, Any] | None, workflow_digest: str, artifact_digest: str | None,
        failure_code: str | None, created_at: str, request_write_state: str,
        provider_prompt_id: str | None = None, native_artifacts: list | None = None,
        derivation: dict | None = None, transport_result_digest: str | None = None) -> dict:
    bound = validate_live_transport_submission(submission) if submission is not None else None
    lineage = _job_lineage(job, workflow_digest)
    if bound is not None and any(bound[n] != lineage[n] for n in _LINEAGE_FIELDS):
        raise ValueError("live submission job lineage mismatch")
    return validate_live_dispatch_result(_sealed({"schemaVersion": LIVE_DISPATCH_RESULT_SCHEMA,
        **lineage, "outcome": outcome, "phase": phase, "requestWriteState": request_write_state,
        "transportSubmissionRef": bound["transportSubmissionRef"] if bound else None,
        "transportSubmissionDigest": bound["payloadDigest"] if bound else None,
        "providerPromptId": provider_prompt_id, "artifactDigest": artifact_digest,
        "failureCode": failure_code, "createdAt": created_at, "nativeArtifacts": native_artifacts or [],
        "derivation": derivation, "transportResultDigest": transport_result_digest}), job=job)


class LiveGenerationDispatchTransportError(RuntimeError):
    """Safe phase facts, never raw response bodies, URLs or exception strings."""
    def __init__(self, code: str, phase: str, *, request_write_state: str,
            submission: Mapping[str, Any] | None = None, provider_prompt_id: str | None = None):
        if (type(code) is not str or _ERROR.fullmatch(code) is None
                or request_write_state not in WRITE_STATES):
            raise ValueError("invalid live transport failure")
        if (phase not in {CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
                REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED, SUBMISSION_OUTCOME_UNKNOWN}
                or request_write_state == MAY_HAVE_BEEN_SENT and phase != SUBMISSION_OUTCOME_UNKNOWN):
            raise ValueError("invalid live failure phase")
        self.code, self.phase, self.request_write_state = code, phase, request_write_state
        self.submission = validate_live_transport_submission(submission) if submission is not None else None
        if self.submission is not None and request_write_state != LOCAL_WRITE_COMPLETE:
            raise ValueError("inconsistent live failure submission")
        self.provider_prompt_id = validate_prompt_id(provider_prompt_id) if provider_prompt_id is not None else None
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class LiveTransportReadResult:
    request: dict
    submission: dict
    receipt: dict
    artifact_bytes: bytes | None
    native_frames: tuple[bytes, ...] = ()
    deadline_monotonic: float = 0.0

    def __post_init__(self) -> None:
        request = validate_live_transport_request(self.request)
        submission = validate_live_transport_submission(self.submission)
        receipt = validate_live_transport_result(self.receipt)
        if (receipt["requestDigest"] != request["payloadDigest"]
                or submission["requestDigest"] != request["payloadDigest"]
                or receipt["transportSubmissionDigest"] != submission["payloadDigest"]
                or receipt["transportSubmissionRef"] != submission["transportSubmissionRef"]
                or any(receipt[n] != request[n] or submission[n] != request[n] for n in _LINEAGE_FIELDS)):
            raise ValueError("live read result lineage mismatch")
        if type(self.deadline_monotonic) not in {int, float} or not math.isfinite(self.deadline_monotonic):
            raise ValueError("invalid in-process result deadline")
        if receipt["outcome"] == "SUCCEEDED":
            if (type(self.artifact_bytes) is not bytes or not self.artifact_bytes
                    or sha256(self.artifact_bytes).hexdigest() != receipt["artifactDigest"]):
                raise ValueError("live artifact digest mismatch")
            native = receipt["nativeArtifacts"]
            if request["outputBinding"]["mediaType"] == "image/png":
                if type(self.native_frames) is not tuple or len(self.native_frames) != 49:
                    raise ValueError("missing native frame bytes")
                if any(type(b) is not bytes or len(b) != item["byteSize"] or sha256(b).hexdigest() != item["sha256"]
                       for b, item in zip(self.native_frames, native)):
                    raise ValueError("native frame bytes mismatch")
                if receipt["derivation"]["profileId"] != request["postprocessBinding"]["profileId"]:
                    raise ValueError("derivation profile mismatch")
            elif self.native_frames or native[0]["sha256"] != receipt["artifactDigest"]:
                raise ValueError("direct native output mismatch")
            output = request["outputBinding"]
            if len(native) != output["frameCount"] or any(item["nodeId"] != output["nodeId"]
                    or item["mediaType"] != output["mediaType"] or item["subfolder"] != output["subfolder"]
                    or not item["filename"].startswith(output["filenamePrefix"] + "_") for item in native):
                raise ValueError("native artifact output binding mismatch")
        elif self.artifact_bytes is not None or self.native_frames:
            raise ValueError("failed result carries artifacts")
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "submission", submission)
        object.__setattr__(self, "receipt", receipt)
