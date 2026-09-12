"""TEST_ONLY CPU synthetic media; no real ComfyUI, GPU or formal database.

The native-frame tests exercise real FFmpeg. Original-Job tests use the existing
temporary-SQLite fixture and a fabricated protocol result, not a live generation.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import zlib

from services.v4_platform.backend_registry import BackendValidationError, digest
from services.v4_platform.generation_dispatch_live_contracts import (
    LiveTransportReadResult, make_live_transport_request, make_live_transport_result,
    make_live_transport_submission,
)
from services.v4_platform.generation_dispatch_live_result import (
    GenerationDispatchLiveResultBoundary, POSTPROCESS_PROFILE, process_native_frames,
)
from services.v4_platform.media_jobs import (ArtifactRecoveryStoreError,
    ArtifactVerificationError, MediaJobError, MediaJobStateError, _validate_job, probe_media)
from services.v4_platform.method_aware_execution import validate_execution_result


def synthetic_png(index, *, width=704, height=1280):
    # Frames 0..47 have independently readable gray values; frame48 is red.
    rgb = bytes((16 + index * 4,) * 3) if index < 48 else bytes((255, 0, 0))
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + rgb * width) * height)) + chunk(b"IEND", b""))


def synthetic_request(*, job=None, workflow=None, native=True):
    workflow = workflow or {"16": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test_frames"}}}
    output_node = next((n for n, v in workflow.items() if v["class_type"] == "SaveVideo"), "16")
    value = {"workspace_ref": "test-workspace", "production_run_ref": "test-run", "worker_ref": "test-worker",
        "generation_dispatch_grant_ref": "test-grant", "generation_dispatch_grant_digest": digest("grant"),
        "media_job_ref": "test-job", "attempt_ref": "test-attempt", "generation_request_ref": "test-request",
        "generation_request_digest": digest("request"), "execution_envelope_digest": digest("envelope"),
        "workflow_digest": digest(workflow), "workflow": workflow,
        "output_constraints": {"mediaKind": "video", "mediaType": "video/mp4", "width": 704,
            "height": 1280, "durationFrames": 48, "frameRate": 24},
        "connection_timeout_ms": 100, "request_timeout_ms": 1000, "history_timeout_ms": 10000,
        "postprocess_timeout_ms": 60000,
        "transport_policy": {"maxPromptSubmissions": 1, "postRetryAllowed": False,
            "redirectAllowed": False, "fallbackAllowed": False},
        "endpoint_digest": digest("test-only-endpoint"), "execution_config_digest": digest("config"),
        "runtime_binding_digest": digest("runtime"), "backend_decision_digest": digest("backend"),
        "output_binding": {"nodeId": output_node, "outputKey": "images" if native else "videos",
            "mediaType": "image/png" if native else "video/mp4", "frameCount": 49 if native else 1,
            "filenamePrefix": "test_frames" if native else "test_video", "subfolder": ""},
        "postprocess_binding": {"profileId": POSTPROCESS_PROFILE, "keepIndices": list(range(48)),
            "dropIndices": [48], "frameRate": 24} if native else None}
    if job is not None:
        value.update(workspace_ref=job["workspaceRef"], production_run_ref=job["productionRunRef"],
            worker_ref=job["lease"]["workerRef"], media_job_ref=job["jobRef"],
            attempt_ref=job["attempts"][-1]["attemptRef"],
            generation_dispatch_grant_ref=job["dispatchGrantBinding"]["generationDispatchGrantRef"],
            generation_dispatch_grant_digest=job["dispatchGrantBinding"]["generationDispatchGrantDigest"],
            generation_request_ref=job["request"]["generationRequestRef"], generation_request_digest=job["requestDigest"],
            execution_envelope_digest=job["executionEnvelope"]["envelopeDigest"],
            output_constraints=deepcopy(job["executionEnvelope"]["outputConstraints"]),
            backend_decision_digest=digest(job["backendBinding"]))
    return make_live_transport_request(**value)


def native_manifest(frames, request):
    binding = request["outputBinding"]
    return [{"index": index, "nodeId": binding["nodeId"],
        "filename": binding["filenamePrefix"] + f"_{index:05d}_.png", "subfolder": binding["subfolder"],
        "type": "output", "mediaType": "image/png", "byteSize": len(frame),
        "sha256": sha256(frame).hexdigest()} for index, frame in enumerate(frames)]


class NativeFrameDerivationCpuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = synthetic_request()
        cls.frames = tuple(synthetic_png(i) for i in range(49))
        cls.manifest = native_manifest(cls.frames, cls.request)

    def test_49_distinct_native_frames_keep_0_through_47_and_drop_red_48(self):
        content, lineage = process_native_frames(self.frames, self.manifest, self.request,
            deadline_monotonic=time.monotonic() + 60)
        self.assertEqual(len({item["sha256"] for item in self.manifest}), 49)
        self.assertEqual(lineage["nativeSequenceDigest"], digest(self.manifest))
        self.assertEqual(lineage["keptIndices"], list(range(48)))
        self.assertEqual(lineage["droppedIndices"], [48])
        self.assertEqual(lineage["outputSha256"], sha256(content).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "derived.mp4"
            target.write_bytes(content)
            decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(target),
                "-vf", "crop=2:2:352:640", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                check=True, capture_output=True, timeout=30).stdout
            actual_probe = probe_media(target, fresh=True)
        # Sample a chroma-aligned crop, not a 1x1 rescale whose odd chroma
        # dimensions introduce a color-conversion bias unrelated to ordering.
        self.assertEqual(len(decoded), 48 * 12)
        for index in range(48):
            pixel = decoded[index * 12:index * 12 + 12]
            self.assertTrue(all(abs(channel - (16 + index * 4)) <= 1 for channel in pixel), (index, pixel))
        # PNG file digest and decoded lossy video pixels are distinct contracts.
        self.assertNotEqual(sha256(decoded).hexdigest(), digest(self.manifest))
        from tests.support.generation_dispatch_execution_fixtures import export_pkg3_evidence
        export_pkg3_evidence("result_native49_derived48_actual.json", {
            "classification": "TEST_ONLY_SYNTHETIC_CPU_NO_SH09_BINDING",
            "nativeArtifacts": self.manifest, "derivation": lineage, "ffprobe": actual_probe,
            "decodedCropSha256": sha256(decoded).hexdigest(),
            "decodedFrameSamples": [list(decoded[i * 12:i * 12 + 3]) for i in range(48)],
            "sampleContract": "DECODED_LOSSY_RGB24_CHROMA_ALIGNED_2X2_CROP_NOT_PNG_BYTE_DIGEST",
            "realComfyUIConnections": 0, "gpuExecutions": 0})

    def test_swapped_frames_and_changed_manifest_indices_are_rejected(self):
        frames = list(self.frames)
        frames[0], frames[1] = frames[1], frames[0]
        with self.assertRaises(ArtifactVerificationError):
            process_native_frames(tuple(frames), self.manifest, self.request, deadline_monotonic=time.monotonic() + 5)
        manifest = deepcopy(self.manifest)
        manifest[0]["index"] = 1
        with self.assertRaises(ValueError):
            process_native_frames(self.frames, manifest, self.request, deadline_monotonic=time.monotonic() + 5)

    def test_dropped_frame_is_still_fully_validated(self):
        frames = self.frames[:-1] + (self.frames[-1][:-1],)
        with self.assertRaises(ArtifactVerificationError):
            process_native_frames(frames, native_manifest(frames, self.request), self.request,
                deadline_monotonic=time.monotonic() + 5)

    def test_changed_dimensions_and_48_native_frames_rejected(self):
        frames = (synthetic_png(0, width=703),) + self.frames[1:]
        with self.assertRaises(ArtifactVerificationError):
            process_native_frames(frames, native_manifest(frames, self.request), self.request,
                deadline_monotonic=time.monotonic() + 5)
        with self.assertRaises(ValueError):
            process_native_frames(self.frames[:-1], self.manifest[:-1], self.request,
                deadline_monotonic=time.monotonic() + 5)

    def test_expired_deadline_does_not_launch_ffmpeg(self):
        with patch("services.v4_platform.generation_dispatch_live_result.subprocess.run") as run:
            with self.assertRaises(ArtifactVerificationError):
                process_native_frames(self.frames, self.manifest, self.request,
                    deadline_monotonic=time.monotonic() - 1)
            run.assert_not_called()

    def test_animated_png_is_not_accepted_as_one_native_frame(self):
        payload = struct.pack(">II", 2, 0)
        animation = struct.pack(">I", len(payload)) + b"acTL" + payload
        animation += struct.pack(">I", zlib.crc32(b"acTL" + payload) & 0xffffffff)
        animated = self.frames[0][:33] + animation + self.frames[0][33:]
        frames = (animated,) + self.frames[1:]
        with patch("services.v4_platform.generation_dispatch_live_result.subprocess.run") as run:
            with self.assertRaises(ArtifactVerificationError):
                process_native_frames(frames, native_manifest(frames, self.request), self.request,
                    deadline_monotonic=time.monotonic() + 5)
            run.assert_not_called()


def claimed_result(case):
    from tests.support.generation_dispatch_execution_fixtures import ExecutionFixture, CpuIsolatedFakeTransport
    fixture = ExecutionFixture(case)
    approval_bundle = json.loads((fixture.root / "test-generation-approval.json").read_text())
    workflow = approval_bundle["approvals"][0]["planPackage"]["materials"]["workflow"]
    case.assertEqual(digest(workflow), fixture.grant["executionBinding"]["workflowDigest"])
    claimed, command, consumed = fixture.claim_and_consume()
    case.assertIsNotNone(consumed["continuation"])
    request = synthetic_request(job=claimed, workflow=workflow, native=False)
    artifact = CpuIsolatedFakeTransport._video_bytes(request["outputConstraints"], fixture.root)
    submission = make_live_transport_submission(request=request, transport_submission_ref="local-submission-test",
        committed_at=fixture.clock.now())
    native = [{"index": 0, "nodeId": request["outputBinding"]["nodeId"], "filename": "test_video_00001_.mp4",
        "subfolder": "", "type": "output", "mediaType": "video/mp4", "byteSize": len(artifact),
        "sha256": sha256(artifact).hexdigest()}]
    receipt = make_live_transport_result(request=request, submission=submission, outcome="SUCCEEDED",
        phase="RESPONSE_RECEIVED", request_write_state="LOCAL_WRITE_COMPLETE",
        provider_prompt_id="00000000-0000-4000-8000-000000000001", artifact_digest=sha256(artifact).hexdigest(),
        failure_code=None, received_at=fixture.clock.now(), native_artifacts=native)
    result = LiveTransportReadResult(request, submission, receipt, artifact, (), time.monotonic() + 60)
    boundary = GenerationDispatchLiveResultBoundary(fixture.coordinators[0], clock=fixture.clock)
    return fixture, claimed, result, boundary


class OriginalJobLiveResultCpuTests(unittest.TestCase):
    def test_live_success_uses_original_job_attempt_and_unknown_facts(self):
        fixture, claimed, result, boundary = claimed_result(self)
        saved = boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        _validate_job(saved)
        self.assertEqual(saved["state"], "SUCCEEDED")
        self.assertEqual(saved["jobRef"], claimed["jobRef"])
        self.assertEqual(len(saved["attempts"]), 1)
        self.assertEqual(saved["attempts"][0]["attemptRef"], claimed["attempts"][0]["attemptRef"])
        execution = saved["artifact"]["providerExecution"]
        self.assertIsNone(execution["costMinor"])
        self.assertIsNone(execution["gpuUsed"])
        self.assertEqual(execution["executionDevice"], "UNKNOWN")
        self.assertNotEqual(execution["providerRequestRef"], result.submission["transportSubmissionRef"])
        self.assertFalse(saved["artifact"]["publicationAllowed"])
        self.assertEqual(fixture.queues[1].get(saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"]), saved)
        self.assertEqual(fixture.transport.commit_count, 0)  # fabricated receipt, no network submission
        with self.assertRaises(MediaJobStateError):
            fixture.execute()

    def test_original_result_reader_reads_v4_technical_result_without_job_mutation(self):
        from services.v4_platform.method_aware_results import MethodAwareMediaJobResultReader, MethodAwareJobResultError
        fixture, claimed, result, boundary = claimed_result(self)
        saved = boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        reader = MethodAwareMediaJobResultReader.from_coordinator(fixture.coordinators[1])
        arguments = (saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"],
            saved["request"]["generationRequestRef"], saved["requestDigest"],
            saved["backendBinding"]["registryVersion"], saved["backendBinding"]["registryDigest"])
        receipt = reader.require_verified_succeeded_result(*arguments)
        self.assertEqual(receipt["mediaJobRef"], saved["jobRef"])
        self.assertEqual(receipt["attemptRef"], saved["attempts"][0]["attemptRef"])
        self.assertEqual(receipt["artifactSha256"], saved["artifact"]["sha256"])
        self.assertFalse(receipt["publicationAllowed"])
        self.assertEqual(fixture.current_job(), saved)
        self.assertEqual(reader.project_statuses(*arguments[:2], [arguments[2]])[0]["state"], "SUCCEEDED")
        with self.assertRaises(MethodAwareJobResultError):
            reader.require_verified_succeeded_result(*arguments[:3], "foreign-request", *arguments[4:])
        foreign = deepcopy(saved)
        foreign["schemaVersion"] = "v4.media-job.v99"
        with patch.object(reader.repository, "get", return_value=foreign):
            with self.assertRaises(MethodAwareJobResultError):
                reader.require_verified_succeeded_result(*arguments)
        path = Path(saved["artifact"]["internalPath"])
        path.write_bytes(b"TEST_ONLY_INVALID_MEDIA")
        with self.assertRaises(MethodAwareJobResultError):
            reader.require_verified_succeeded_result(*arguments)
        self.assertEqual(fixture.current_job(), saved)

    def test_unknown_cost_device_only_live_schema_and_live_envelope(self):
        fixture, claimed, result, boundary = claimed_result(self)
        saved = boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        execution = saved["artifact"]["providerExecution"]
        for key, value in (("costMinor", 0), ("gpuUsed", False), ("executionDevice", "CPU_FAKE_TRANSPORT"),
                ("schemaVersion", "v4.method-aware-execution-result.v1")):
            changed = deepcopy(execution)
            changed[key] = value
            with self.assertRaises(BackendValidationError):
                validate_execution_result(changed, saved["executionEnvelope"])
        changed_envelope = deepcopy(saved["executionEnvelope"])
        changed_envelope["schemaVersion"] = "v4.method-aware-media-execution-envelope.v1"
        with self.assertRaises(BackendValidationError):
            validate_execution_result(execution, changed_envelope)

    def test_altered_artifact_execution_evidence_does_not_rebind_result(self):
        fixture, claimed, result, boundary = claimed_result(self)
        original = boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        saved = deepcopy(original)
        execution = saved["artifact"]["providerExecution"]
        execution["executionEvidence"]["transportResultDigest"] = digest("other receipt")
        execution["executionEvidenceDigest"] = digest(execution["executionEvidence"])
        with self.assertRaises(MediaJobError):
            _validate_job(saved)
        for key, value in (("gpuUsed", False), ("executionDevice", "CPU_FAKE_TRANSPORT"),
                ("provenance", "TEST_ONLY")):
            changed = deepcopy(original)
            changed["artifact"][key] = value
            with self.assertRaises(MediaJobError):
                _validate_job(changed)
        changed = deepcopy(original)
        execution = changed["artifact"]["providerExecution"]
        execution.update(schemaVersion="v4.method-aware-execution-result.v1", costMinor=0,
            gpuUsed=False, executionDevice="CPU_FAKE_TRANSPORT")
        execution.pop("costStatus")
        execution.pop("deviceStatus")
        with self.assertRaises(MediaJobError):
            _validate_job(changed)
        changed = deepcopy(original)
        execution = changed["attempts"][0]["providerExecution"]
        execution["providerRequestRef"] = "00000000-0000-4000-8000-000000000099"
        execution["executionEvidence"]["providerPromptId"] = execution["providerRequestRef"]
        execution["executionEvidenceDigest"] = digest(execution["executionEvidence"])
        # A valid backend-bound execution envelope may not split the original
        # Attempt's prompt identity from its persisted artifact/dispatch result.
        validate_execution_result(execution, changed["executionEnvelope"])
        with self.assertRaises(MediaJobError):
            _validate_job(changed)

    def test_foreign_result_request_rejected_before_candidate_write(self):
        fixture, claimed, result, boundary = claimed_result(self)
        result.request["mediaJobRef"] = "another-job"
        with self.assertRaises(ValueError):
            boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        self.assertIsNone(fixture.current_job().get("artifactCommitIntent"))

    def test_out_of_root_candidate_and_final_symlinks_rejected_before_write(self):
        fixture, claimed, result, boundary = claimed_result(self)
        sentinel = fixture.root / "test-outside-artifact-root.bin"
        sentinel.write_bytes(b"TEST_ONLY_OUTSIDE_ARTIFACT_ROOT_MUST_REMAIN_UNTOUCHED")
        before = sentinel.read_bytes()
        candidate, final = fixture.coordinators[0]._attempt_paths(claimed, 1)
        observations = []
        for target in (candidate, final):
            with self.subTest(path_kind="candidate" if target == candidate else "final"):
                target.symlink_to(sentinel)
                try:
                    with self.assertRaises((ArtifactVerificationError, ArtifactRecoveryStoreError)):
                        boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
                    self.assertEqual(sentinel.read_bytes(), before)
                    self.assertEqual(fixture.current_job(), claimed)
                    self.assertTrue(target.is_symlink())
                    observations.append({"pathKind": "candidate" if target == candidate else "final",
                        "rejectedBeforeWrite": True, "outsideTargetSha256": sha256(before).hexdigest(),
                        "outsideTargetUntouched": True, "originalJobUntouched": True})
                finally:
                    target.unlink()
        from tests.support.generation_dispatch_execution_fixtures import export_pkg3_evidence
        export_pkg3_evidence("result_local_symlink_rejection_actual.json", {
            "classification": "TEST_ONLY_TEMPORARY_LOCAL_ARTIFACT_SYMLINK_NOT_REMOTE_RUNTIME_PROOF",
            "observations": observations, "mockPostCount": 0})

    def test_expired_original_lease_cannot_write_live_success_or_failure(self):
        fixture, claimed, result, boundary = claimed_result(self)
        fixture.advance(120)
        with self.assertRaises(MediaJobStateError):
            boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
        with self.assertRaises(MediaJobStateError):
            boundary.record_failure(claimed, workflow_digest=result.request["workflowDigest"],
                code="RESULT_UNKNOWN", phase="SUBMISSION_OUTCOME_UNKNOWN", submission=result.submission,
                request_write_state="LOCAL_WRITE_COMPLETE")

    def test_partial_write_unknown_persists_no_fake_false_and_no_second_attempt(self):
        fixture, claimed, result, boundary = claimed_result(self)
        saved = boundary.record_failure(claimed, workflow_digest=result.request["workflowDigest"],
            code="PARTIAL_WRITE", phase="SUBMISSION_OUTCOME_UNKNOWN", submission=None,
            request_write_state="MAY_HAVE_BEEN_SENT")
        self.assertEqual(saved["dispatchResult"]["outcome"], "UNKNOWN")
        self.assertNotIn("committedRequestBytes", saved["dispatchResult"])
        self.assertIsNone(saved["dispatchResult"]["transportSubmissionRef"])
        self.assertEqual(boundary.read_only(saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"]), saved)
        with self.assertRaises(MediaJobStateError):
            fixture.execute()
        self.assertEqual(len(fixture.current_job()["attempts"]), 1)

    def test_commit_intent_fault_before_and_after_replace_is_original_read_only_recovery(self):
        for after_replace in (False, True):
            with self.subTest(after_replace=after_replace):
                fixture, claimed, result, boundary = claimed_result(self)
                store = fixture.coordinators[0]._artifact_recovery
                original = store.durable_replace
                def failed_replace(*args, **kwargs):
                    if after_replace:
                        original(*args, **kwargs)
                    raise ArtifactRecoveryStoreError("TEST_ONLY persistence fault")
                with patch.object(store, "durable_replace", failed_replace):
                    with self.assertRaises(ArtifactVerificationError):
                        boundary.record_success(claimed, result, workflow_digest=result.request["workflowDigest"])
                saved = fixture.current_job()
                self.assertEqual(saved["state"], "RUNNING")
                self.assertIsNotNone(saved["artifactCommitIntent"])
                self.assertEqual(saved["dispatchResult"]["outcome"], "SUCCEEDED")
                self.assertEqual(len(saved["attempts"]), 1)
                candidate, final = fixture.coordinators[0]._attempt_paths(saved, 1)
                self.assertEqual(final.exists(), after_replace)
                self.assertEqual(candidate.exists(), not after_replace)
                # A new boundary only observes the persisted original row.
                restarted = GenerationDispatchLiveResultBoundary(fixture.coordinators[1], clock=fixture.clock)
                self.assertEqual(restarted.read_only(saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"]), saved)
                with self.assertRaises(MediaJobStateError):
                    fixture.execute()
                self.assertEqual(fixture.transport.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
