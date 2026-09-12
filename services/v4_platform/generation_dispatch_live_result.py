"""Bounded native-frame derivation and original-Job live artifact recovery.

This module owns no queue, provider, admission or persistent store. Temporary PNG
files are CPU work files; the sole durable output uses MediaJobCoordinator's
existing artifact commit intent and fenced durable replacement.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from math import isfinite
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from typing import Any, Mapping
import zlib

from .backend_registry import BackendValidationError, digest, exact, hex_digest, ref
from .media_jobs import (ARTIFACT_SCHEMA_VERSION, ArtifactRecoveryStoreError,
    ArtifactVerificationError, MediaJobError, MediaJobStateError,
    _file_digest_and_size, verify_media_against_request)

LIVE_EXECUTION_SCHEMA = "v4.generation-dispatch-live-execution-result.v1"
LIVE_EVIDENCE_SCHEMA = "v4.generation-dispatch-live-execution-evidence.v1"
DERIVATION_SCHEMA = "v4.generation-dispatch-frame-derivation.v1"
POSTPROCESS_PROFILE = "ACS-SPIKE0-POST-49TO48-24FPS-R1"


def _remaining(deadline: float) -> float:
    if type(deadline) not in {int, float} or not isfinite(deadline):
        raise ArtifactVerificationError("result deadline is invalid")
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ArtifactVerificationError("result deadline expired")
    return remaining


def _validate_png(data: bytes, width: int, height: int) -> None:
    """Check bounded PNG content, including the dropped native frame's bytes."""
    if type(data) is not bytes or not 33 <= len(data) <= 8 * 1024 * 1024 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ArtifactVerificationError("native PNG signature or size is invalid")
    offset, compressed, channels, ended = 8, bytearray(), None, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ArtifactVerificationError("native PNG is truncated")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ArtifactVerificationError("native PNG chunk is truncated")
        chunk = data[offset + 8:end - 4]
        crc = struct.unpack_from(">I", data, end - 4)[0]
        if zlib.crc32(kind + chunk) & 0xffffffff != crc:
            raise ArtifactVerificationError("native PNG chunk digest is invalid")
        if kind in {b"acTL", b"fcTL", b"fdAT"}:
            raise ArtifactVerificationError("animated PNG cannot represent one native frame")
        if kind == b"IHDR":
            if offset != 8 or size != 13:
                raise ArtifactVerificationError("native PNG header is invalid")
            w, h, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk)
            if ((w, h) != (width, height) or depth != 8 or color not in {2, 6}
                    or (compression, filtering, interlace) != (0, 0, 0)):
                raise ArtifactVerificationError("native PNG media specifications changed")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            if channels is None:
                raise ArtifactVerificationError("native PNG has no header")
            compressed.extend(chunk)
        elif kind == b"IEND":
            if size or end != len(data):
                raise ArtifactVerificationError("native PNG trailing content is invalid")
            ended = True
        elif kind and not kind[0] & 32 and kind != b"PLTE":
            raise ArtifactVerificationError("native PNG critical chunk is unsupported")
        offset = end
    if not ended or channels is None or not compressed:
        raise ArtifactVerificationError("native PNG structure is incomplete")
    expected = height * (1 + width * channels)
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ArtifactVerificationError("native PNG pixels are invalid") from exc
    if (len(decoded) != expected or not decoder.eof or decoder.unused_data
            or decoder.unconsumed_tail
            or any(decoded[row * (1 + width * channels)] > 4 for row in range(height))):
        raise ArtifactVerificationError("native PNG pixel stream is invalid")


def process_native_frames(native_frames: tuple[bytes, ...],
        native_artifacts: list[dict[str, Any]], request: dict[str, Any], *,
        deadline_monotonic: float) -> tuple[bytes, dict[str, Any]]:
    """Derive exactly indices 0..47, never fps-resample a 49-frame video."""
    from .generation_dispatch_live_contracts import validate_live_transport_request, validate_native_artifacts
    request = validate_live_transport_request(request)
    native_artifacts = validate_native_artifacts(native_artifacts)
    _remaining(deadline_monotonic)
    output, binding, post = (request["outputConstraints"], request["outputBinding"],
        request["postprocessBinding"])
    if (output != {"mediaKind": "video", "mediaType": "video/mp4", "width": 704,
            "height": 1280, "durationFrames": 48, "frameRate": 24}
            or binding["mediaType"] != "image/png" or binding["frameCount"] != 49
            or post != {"profileId": POSTPROCESS_PROFILE, "keepIndices": list(range(48)),
                "dropIndices": [48], "frameRate": 24}
            or type(native_frames) is not tuple or len(native_frames) != 49
            or type(native_artifacts) is not list or len(native_artifacts) != 49):
        raise ArtifactVerificationError("native-frame derivation contract changed")
    seen = set()
    for index, (data, item) in enumerate(zip(native_frames, native_artifacts)):
        _remaining(deadline_monotonic)
        if (set(item) != {"index", "nodeId", "filename", "subfolder", "type",
                "mediaType", "byteSize", "sha256"}
                or type(item["index"]) is not int or item["index"] != index
                or item["nodeId"] != binding["nodeId"] or item["mediaType"] != "image/png"
                or item["subfolder"] != binding["subfolder"] or item["type"] != "output"
                or not isinstance(item["filename"], str)
                or not item["filename"].startswith(binding["filenamePrefix"] + "_")
                or not item["filename"].endswith(".png")
                or "/" in item["filename"] or "\\" in item["filename"]
                or item["filename"] in seen or item["byteSize"] != len(data)
                or item["sha256"] != sha256(data).hexdigest()):
            raise ArtifactVerificationError("native frame lineage or order changed")
        seen.add(item["filename"])
        _validate_png(data, 704, 1280)
    with tempfile.TemporaryDirectory(prefix="acs-dispatch-frame-derivation-") as directory:
        root = Path(directory)
        # The decoded native bytes remain tied to their manifest index. No
        # glob, history search, response URL or provider filename chooses order.
        for index in range(48):
            _remaining(deadline_monotonic)
            (root / f"frame-{index:03d}.png").write_bytes(native_frames[index])
        destination = root / "derived.mp4"
        command = ["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
            "-framerate", "24", "-start_number", "0", "-i", str(root / "frame-%03d.png"),
            "-map", "0:v:0", "-an", "-frames:v", "48", "-c:v", "libx264",
            "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-n", str(destination)]
        try:
            subprocess.run(command, check=True, capture_output=True,
                timeout=_remaining(deadline_monotonic))
        except (OSError, subprocess.SubprocessError) as exc:
            raise ArtifactVerificationError("native-frame CPU derivation failed") from exc
        probe = verify_media_against_request(destination,
            {"mediaKind": "video", "mediaType": "video/mp4",
             "parameters": {key: output[key] for key in ("width", "height", "durationFrames", "frameRate")}},
            fresh_probe=True, deadline_monotonic=deadline_monotonic)
        if float(probe["durationSeconds"]) != 2.0:
            raise ArtifactVerificationError("derived duration is not exactly two seconds")
        _remaining(deadline_monotonic)
        content = destination.read_bytes()
    return content, {"schemaVersion": DERIVATION_SCHEMA, "profileId": POSTPROCESS_PROFILE,
        "nativeSequenceDigest": digest(native_artifacts), "keptIndices": list(range(48)),
        "droppedIndices": [48], "frameRate": 24, "width": 704, "height": 1280,
        "frameCount": 48, "outputSha256": sha256(content).hexdigest()}


def validate_live_execution_result(execution: Any, envelope: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schemaVersion", "backendBindingDigest", "providerId", "modelId", "region",
        "endpointClass", "adapterIdentity", "providerRequestRef", "costCurrency", "costMinor",
        "runtimeAttestationRef", "runtimeAttestationDigest", "executionEvidenceDigest",
        "executionEvidence", "executionDevice", "gpuUsed", "costStatus", "deviceStatus"}
    exact(execution, fields, "live execution result")
    binding = envelope["backendBinding"]
    if (execution["schemaVersion"] != LIVE_EXECUTION_SCHEMA
            or envelope.get("schemaVersion") != "v4.method-aware-media-execution-envelope.v2"
            or execution["backendBindingDigest"] != digest(binding)
            or execution["costStatus"] != "UNKNOWN" or execution["costMinor"] is not None
            or execution["deviceStatus"] != "UNKNOWN" or execution["gpuUsed"] is not None
            or execution["executionDevice"] != "UNKNOWN"):
        raise BackendValidationError("live unknown execution facts are invalid")
    for key in ("providerId", "modelId", "region", "endpointClass", "adapterIdentity",
            "costCurrency", "runtimeAttestationRef", "runtimeAttestationDigest"):
        if execution[key] != binding[key]:
            raise BackendValidationError("live execution backend changed")
    ref(execution["providerRequestRef"], "providerRequestRef")
    evidence = execution["executionEvidence"]
    exact(evidence, {"schemaVersion", "dispatchResultDigest", "transportSubmissionRef",
        "transportSubmissionDigest", "transportResultDigest", "providerPromptId",
        "artifactDigest", "nativeArtifacts", "derivation", "publicationAllowed"}, "live execution evidence")
    if (evidence["schemaVersion"] != LIVE_EVIDENCE_SCHEMA or evidence["publicationAllowed"] is not False
            or evidence["providerPromptId"] != execution["providerRequestRef"]
            or digest(evidence) != execution["executionEvidenceDigest"]):
        raise BackendValidationError("live execution evidence is invalid")
    for key in ("dispatchResultDigest", "transportSubmissionDigest", "transportResultDigest", "artifactDigest"):
        hex_digest(evidence[key], key)
    from .generation_dispatch_live_contracts import validate_native_artifacts, validate_derivation
    try:
        native = validate_native_artifacts(evidence["nativeArtifacts"])
        validate_derivation(evidence["derivation"], native, evidence["artifactDigest"])
        if not native:
            raise ValueError("successful execution has no native output")
    except ValueError as exc:
        raise BackendValidationError("live execution native lineage is invalid") from exc
    return deepcopy(dict(execution))


class GenerationDispatchLiveResultBoundary:
    """Live-only handoff, using the original lease, Attempt and commit intent."""

    def __init__(self, coordinator, *, clock):
        self.coordinator, self.repository, self.clock = coordinator, coordinator.repository, clock

    def _active(self, job):
        attempt = job["attempts"][-1]
        current = self.coordinator._active_worker_job(job["workspaceRef"],
            job["productionRunRef"], job["jobRef"], job["lease"]["workerRef"],
            job["lease"]["leaseToken"], attempt["attemptRef"])
        if (len(current["attempts"]) != 1 or current["attempts"][-1]["workerProcessIdentityDigest"]
                != attempt["workerProcessIdentityDigest"]):
            raise MediaJobStateError("live result original worker changed")
        return current

    @staticmethod
    def _provider_execution(job, result):
        binding = job["backendBinding"]
        evidence = {"schemaVersion": LIVE_EVIDENCE_SCHEMA,
            "dispatchResultDigest": result["payloadDigest"],
            **{key: deepcopy(result[key]) for key in ("transportSubmissionRef", "transportSubmissionDigest",
                "transportResultDigest", "providerPromptId", "artifactDigest", "nativeArtifacts", "derivation")},
            "publicationAllowed": False}
        return validate_live_execution_result({"schemaVersion": LIVE_EXECUTION_SCHEMA,
            "backendBindingDigest": digest(binding),
            **{key: binding[key] for key in ("providerId", "modelId", "region", "endpointClass",
                "adapterIdentity", "costCurrency", "runtimeAttestationRef", "runtimeAttestationDigest")},
            "providerRequestRef": result["providerPromptId"], "costMinor": None, "costStatus": "UNKNOWN",
            "gpuUsed": None, "executionDevice": "UNKNOWN", "deviceStatus": "UNKNOWN",
            "executionEvidenceDigest": digest(evidence), "executionEvidence": evidence}, job["executionEnvelope"])

    def record_success(self, job, result, *, workflow_digest):
        from .generation_dispatch_live_contracts import (LiveTransportReadResult,
            validate_live_transport_request, validate_live_transport_result,
            validate_live_transport_submission, make_live_dispatch_result)
        if type(result) is not LiveTransportReadResult or type(result.artifact_bytes) is not bytes:
            raise MediaJobError("live result type is invalid")
        # The dataclass is frozen, its JSON containers are not: revalidate at
        # the durable boundary rather than trusting construction-time checks.
        result = LiveTransportReadResult(result.request, result.submission, result.receipt,
            result.artifact_bytes, result.native_frames, result.deadline_monotonic)
        request = validate_live_transport_request(result.request)
        receipt = validate_live_transport_result(result.receipt)
        submission = validate_live_transport_submission(result.submission)
        current = self._active(job)
        expected = {"workspaceRef": current["workspaceRef"], "productionRunRef": current["productionRunRef"],
            "workerRef": current["lease"]["workerRef"], "mediaJobRef": current["jobRef"],
            "attemptRef": current["attempts"][-1]["attemptRef"],
            "generationRequestRef": current["request"]["generationRequestRef"],
            "generationRequestDigest": current["requestDigest"],
            "generationDispatchGrantRef": current["dispatchGrantBinding"]["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": current["dispatchGrantBinding"]["generationDispatchGrantDigest"],
            "executionEnvelopeDigest": current["executionEnvelope"]["envelopeDigest"],
            "backendDecisionDigest": digest(current["backendBinding"]),
            "workflowDigest": workflow_digest}
        if (any(request[key] != value for key, value in expected.items())
                or request["outputConstraints"] != current["executionEnvelope"]["outputConstraints"]
                or receipt["outcome"] != "SUCCEEDED"
                or receipt["requestDigest"] != request["payloadDigest"]
                or submission["requestDigest"] != request["payloadDigest"]
                or receipt["transportSubmissionDigest"] != submission["payloadDigest"]
                or receipt["artifactDigest"] != sha256(result.artifact_bytes).hexdigest()):
            raise ArtifactVerificationError("live result original Job lineage changed")
        _remaining(result.deadline_monotonic)
        dispatch_result = make_live_dispatch_result(outcome="SUCCEEDED", phase=receipt["phase"],
            job=current, submission=submission, workflow_digest=workflow_digest,
            artifact_digest=receipt["artifactDigest"], failure_code=None, created_at=self.clock.now(),
            request_write_state="LOCAL_WRITE_COMPLETE", provider_prompt_id=receipt["providerPromptId"],
            native_artifacts=receipt["nativeArtifacts"], derivation=receipt["derivation"],
            transport_result_digest=receipt["payloadDigest"])
        attempt = current["attempts"][-1]
        candidate, final = self.coordinator._attempt_paths(current, attempt["attemptNumber"])
        self.coordinator._artifact_recovery.require_absent(candidate)
        self.coordinator._artifact_recovery.require_absent(final)
        with candidate.open("xb") as stream:
            stream.write(result.artifact_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        probe = verify_media_against_request(candidate, self.coordinator._probe_request(current),
            fresh_probe=True, deadline_monotonic=result.deadline_monotonic)
        content_digest, content_size = _file_digest_and_size(candidate)
        if content_digest != receipt["artifactDigest"]:
            raise ArtifactVerificationError("live candidate bytes changed")
        execution = self._provider_execution(current, dispatch_result)
        artifact = {"schemaVersion": ARTIFACT_SCHEMA_VERSION,
            "workspaceRef": current["workspaceRef"], "productionRunRef": current["productionRunRef"],
            "jobRef": current["jobRef"], "attemptRef": attempt["attemptRef"],
            "generationRequestRef": current["request"]["generationRequestRef"],
            "generationRequestVersionRef": current["request"]["generationRequestVersionRef"],
            "generationRequestDigest": current["requestDigest"], "mediaKind": "video", "mediaType": "video/mp4",
            "internalPath": str(final), "storageKey": self.coordinator._artifact_recovery.storage_key(final),
            "byteSize": content_size, "sha256": content_digest, "probe": probe,
            "adapterIdentity": current["backendBinding"]["adapterIdentity"],
            "provenance": "TECHNICAL_EVIDENCE_ONLY", "executionDevice": "UNKNOWN", "gpuUsed": None,
            "publicationAllowed": False, "providerExecution": execution,
            "dispatchResultDigest": dispatch_result["payloadDigest"], "createdAt": self.clock.now()}
        current = self._active(job)
        expected_revision = current["revision"]
        current["dispatchResult"] = dispatch_result
        intent = self.coordinator._build_commit_intent(current, attempt, candidate, final, artifact)
        current.update(artifactCommitIntent=intent, updatedAt=self.clock.now())
        current = self.repository.save(current, expected_revision)
        try:
            self.coordinator._artifact_recovery.durable_replace(candidate, final,
                assert_fence=lambda: self._active(job))
        except ArtifactRecoveryStoreError as exc:
            raise ArtifactVerificationError(str(exc)) from exc
        artifact = self.coordinator._verify_final_from_intent(current, intent,
            deadline_monotonic=result.deadline_monotonic)
        current = self._active(job)
        expected_revision = current["revision"]
        current["attempts"][-1].update(state="SUCCEEDED", finishedAt=self.clock.now(),
            artifactSha256=artifact["sha256"], artifactCommitIntentDigest=intent["intentDigest"],
            providerExecution=execution, dispatchResultDigest=dispatch_result["payloadDigest"])
        current.update(state="SUCCEEDED", lease=None, artifact=artifact,
            artifactCommitIntent=None, updatedAt=self.clock.now())
        return self.repository.save(current, expected_revision)

    def record_failure(self, job, *, workflow_digest, code, phase, submission,
                       request_write_state="ZERO_BYTES_PROVEN", provider_prompt_id=None):
        from .generation_dispatch_live_contracts import make_live_dispatch_result
        current = self._active(job)
        if current.get("artifactCommitIntent") is not None:
            raise MediaJobStateError("live artifact commit intent requires original recovery")
        outcome = "UNKNOWN" if request_write_state in {"MAY_HAVE_BEEN_SENT", "LOCAL_WRITE_COMPLETE"} else "FAILED"
        if outcome == "UNKNOWN":
            phase = "SUBMISSION_OUTCOME_UNKNOWN"
        result = make_live_dispatch_result(outcome=outcome, phase=phase, job=current,
            submission=submission, workflow_digest=workflow_digest, artifact_digest=None,
            failure_code=code, created_at=self.clock.now(), request_write_state=request_write_state,
            provider_prompt_id=provider_prompt_id)
        expected = current["revision"]
        current["dispatchResult"] = result
        current["attempts"][-1].update(state="FAILED", finishedAt=self.clock.now(), errorCode=code,
            failureClass=code, nonRetryable=True, dispatchResultDigest=result["payloadDigest"],
            quarantineStorageKeys=[])
        current.update(state="FAILED", lease=None, artifact=None,
            artifactCommitIntent=None, updatedAt=self.clock.now())
        return self.repository.save(current, expected)

    def read_only(self, workspace_ref, production_run_ref, media_job_ref):
        return self.repository.get(workspace_ref, production_run_ref, media_job_ref)
