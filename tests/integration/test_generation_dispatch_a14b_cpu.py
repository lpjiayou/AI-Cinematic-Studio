"""A09/A08/A11: real original SQLite chain and fixture-owned staged HTTP.

No SH09 material, actual model, ComfyUI service, GPU or formal database is used.
Synthetic native PNGs have distinct visible frame IDs and a red discarded tail.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import http.client
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from services.v4_platform import comfyui_staged_transport as staged
from services.v4_platform.generation_dispatch_live_result import GenerationDispatchLiveResultBoundary
from services.v4_platform.generation_dispatch_live_contracts import LiveGenerationDispatchTransportError
from services.v4_platform.method_aware_results import MethodAwareMediaJobResultReader
from services.v4_platform.media_jobs import MediaJobStateError, _validate_job
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI, PROMPT_ID
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_execution_fixture
from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png


class A14BCpuIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = tuple(synthetic_png(index) for index in range(49))

    def assert_original_recovery_no_resend(self, fixture, server):
        before = fixture.current_job()
        recovery = fixture.executor.recover_read_only(fixture.scope["workspaceRef"],
            fixture.scope["productionRunRef"], before["jobRef"])
        self.assertEqual(recovery["job"], before)
        self.assertFalse(recovery["sendAttempted"])
        self.assertIsNone(recovery["continuation"])
        self.assertEqual(recovery["consumption"]["receipt"]["terminal"]["kind"], "CONSUMPTION_COMMITTED")
        observed_posts = server.post_count
        with self.assertRaises(MediaJobStateError):
            fixture.execute()
        self.assertEqual(server.post_count, observed_posts)
        self.assertEqual(len(fixture.current_job()["attempts"]), 1)
        self.assertEqual(len(fixture.jobs()), 1)

    def test_real_a14b_vertical_slice_from_original_grant_to_same_job_result(self):
        with LoopbackComfyUI(frames=self.frames) as server:
            fixture = make_a14b_execution_fixture(self, server.endpoint)
            before_job = deepcopy(fixture.job)
            observations = []
            original_commit = staged.ComfyUIStagedTransport.commit_request_once
            original_read = staged.ComfyUIStagedTransport.read_result
            def commit(transport, exchange):
                observations.append(("initial-write", getattr(fixture.dispatch.coordination._thread, "depth", 0)))
                self.assertGreater(observations[-1][1], 0)
                durable = fixture.consumer.read_consumption_receipt(fixture.scope["workspaceRef"],
                    fixture.scope["productionRunRef"], fixture.grant["generationDispatchGrantRef"])
                self.assertEqual(durable["receipt"]["terminal"]["kind"], "CONSUMPTION_COMMITTED")
                states = tuple(fixture.consumer._capabilities.values())
                self.assertEqual(len(states), 1)
                self.assertTrue(states[0].spent)
                observations.append(("durable-L1-and-spent-capability-before-write", True))
                return original_commit(transport, exchange)
            def read(transport, exchange, submission):
                observations.append(("response-and-artifacts", getattr(fixture.dispatch.coordination._thread, "depth", 0)))
                self.assertEqual(observations[-1][1], 0)
                return original_read(transport, exchange, submission)
            with patch.object(staged.ComfyUIStagedTransport, "commit_request_once", commit), \
                    patch.object(staged.ComfyUIStagedTransport, "read_result", read):
                saved = fixture.execute()
            _validate_job(saved)
            self.assertEqual(saved["state"], "SUCCEEDED")
            self.assertEqual(saved["jobRef"], before_job["jobRef"])
            self.assertEqual(saved["requestDigest"], before_job["requestDigest"])
            self.assertEqual(len(saved["attempts"]), 1)
            self.assertEqual((server.post_count, server.complete_post_count, server.view_count), (1, 1, 49))
            self.assertEqual(len(server.body["prompt"]), 16)
            self.assertEqual(server.body["prompt"]["5"]["inputs"]["text"], fixture.external.template["materials"]["backendProfile"]["parameters"]["positivePrompt"])
            self.assertEqual(server.body["extra_data"]["acs_dispatch"]["mediaJobRef"], saved["jobRef"])
            result, artifact = saved["dispatchResult"], saved["artifact"]
            self.assertEqual(result["derivation"]["keptIndices"], list(range(48)))
            self.assertEqual(result["derivation"]["droppedIndices"], [48])
            self.assertEqual([item["sha256"] for item in result["nativeArtifacts"]], [sha256(frame).hexdigest() for frame in self.frames])
            self.assertEqual(result["artifactDigest"], artifact["sha256"])
            self.assertNotEqual(result["derivation"]["nativeSequenceDigest"], artifact["sha256"])
            self.assertEqual(sha256(Path(artifact["internalPath"]).read_bytes()).hexdigest(), artifact["sha256"])
            self.assertIsNone(artifact["providerExecution"]["costMinor"])
            self.assertIsNone(artifact["providerExecution"]["gpuUsed"])
            self.assertFalse(artifact["publicationAllowed"])
            self.assertIsNone(saved["artifactCommitIntent"])
            self.assertEqual(fixture.queues[1].get(saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"]), saved)
            verified = MethodAwareMediaJobResultReader.from_coordinator(fixture.coordinators[0]).require_verified_succeeded_result(
                saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"], saved["request"]["generationRequestRef"],
                saved["requestDigest"], saved["backendBinding"]["registryVersion"], saved["backendBinding"]["registryDigest"])
            self.assertEqual(verified["artifactSha256"], artifact["sha256"])
            self.assertEqual(verified["sourceAssetVersionRef"], fixture.asset["assetVersionRef"])
            self.assert_original_recovery_no_resend(fixture, server)
            print("A14B_VERTICAL_EVIDENCE=" + json.dumps({"TEST_ONLY": True, "sameOriginalJob": True,
                "originalAttemptCount": 1, "realSQLite": True, "completePostCount": server.complete_post_count,
                "nativeGetCount": server.view_count, "gateObservations": observations,
                "modelOriginalCount": len(fixture.external.model_paths), "costStatus": "UNKNOWN", "gpuStatus": "UNKNOWN",
                "finalFrameCount": int(artifact["probe"]["streams"][0]["nb_read_frames"]),
                "SH09ExactBinding": "NOT_RUN_MISSING_ORIGINAL_EVIDENCE"}, sort_keys=True))

    @staticmethod
    def drift(fixture, kind):
        external = fixture.external
        if kind == "model":
            path = external.model_paths["HIGH_NOISE_EXPERT"]
            path.write_bytes(path.read_bytes() + b"TEST_ONLY drift")
        elif kind == "runtime":
            spec = external.proof_files[external.attestation["attestationRef"]]
            spec["path"].write_bytes(spec["path"].read_bytes() + b" ")
        elif kind == "input":
            fixture.source.write_bytes(fixture.content + b"TEST_ONLY drift")
        else:
            materials = external.template["materials"]
            if kind == "profile":
                materials["backendProfile"]["parameters"]["seed"] += 1
            elif kind == "template":
                materials["backendProfile"]["parameters"]["templateRef"] = "test-unapproved-template"
            elif kind == "config":
                materials["executionConfig"]["configRevision"] += 1
            else:
                raise AssertionError(kind)
            # A genuinely changed trusted selection, not silently updated approval.
            external.write_originals()

    def test_all_six_original_drifts_fail_before_first_write_at_l1_and_l2(self):
        kinds = ("model", "profile", "runtime", "template", "config", "input")
        def exercise(fixture, server, command, phase, kind, continuation=None):
            self.drift(fixture, kind)
            with self.assertRaises(c.DispatchError):
                if phase == "L1":
                    fixture.consumer.consume(command)
                else:
                    continuation.send_once(fixture.transport)
            self.assertEqual(server.paths, [])
            self.assertEqual(server.complete_post_count, 0)
            self.assertEqual(len(fixture.current_job()["attempts"]), 1)
            if continuation is not None:
                self.assertTrue(continuation.spent)
                with self.assertRaises(c.DispatchError):
                    continuation.send_once(fixture.transport)
                self.assert_original_recovery_no_resend(fixture, server)
            else:
                self.assertIsNone(fixture.consumer.read_consumption_receipt(fixture.scope["workspaceRef"],
                    fixture.scope["productionRunRef"], fixture.grant["generationDispatchGrantRef"]))
            print("A14B_CURRENTNESS_EVIDENCE=" + json.dumps({"TEST_ONLY": True, "phase": phase, "drift": kind,
                "httpRequestCount": len(server.paths), "completePostCount": server.complete_post_count,
                "originalAttemptCount": 1, "capabilitySpent": bool(continuation and continuation.spent)}, sort_keys=True))
        # Rejected L1 calls persist no Terminal and no queue mutation, so their
        # identical original fixture can be restored between independent faults.
        # L2 below uses a fresh original Grant/Attempt for every spent capability.
        with LoopbackComfyUI() as server:
            fixture = make_a14b_execution_fixture(self, server.endpoint)
            claimed, command = fixture.claim_command()
            external = fixture.external
            files = {path: path.read_bytes() for path in (external.path, fixture.source,
                external.input_path, *external.model_paths.values(),
                external.proof_files[external.attestation["attestationRef"]]["path"])}
            template, pin = deepcopy(external.template), external.pin
            original_tokens = fixture.consumer.snapshot_tokens(fixture.scope["workspaceRef"], fixture.scope["productionRunRef"])
            for kind in kinds:
                with self.subTest(phase="L1", drift=kind):
                    try:
                        exercise(fixture, server, command, "L1", kind)
                    finally:
                        external.template, external.pin = deepcopy(template), pin
                        for path, raw in files.items():
                            path.write_bytes(raw)
                    self.assertEqual(fixture.current_job(), claimed)
                    self.assertEqual(fixture.consumer.snapshot_tokens(fixture.scope["workspaceRef"], fixture.scope["productionRunRef"]), original_tokens)
        for kind in kinds:
            with self.subTest(phase="L2", drift=kind), LoopbackComfyUI() as server:
                fixture = make_a14b_execution_fixture(self, server.endpoint)
                claimed, command, consumed = fixture.claim_and_consume()
                self.assertIsNotNone(consumed["continuation"])
                exercise(fixture, server, command, "L2", kind, consumed["continuation"])

    def test_lost_response_after_real_post_is_unknown_not_retryable(self):
        def corrupt_history(value):
            value[PROMPT_ID]["prompt"][2]["5"]["inputs"]["text"] = "TEST_ONLY foreign history"
        for response_known in (False, True):
            options = {"history_mutation": corrupt_history, "frames": self.frames} if response_known else {
                "receipt_raw": b"TEST_ONLY invalid receipt"}
            with self.subTest(response_known=response_known), LoopbackComfyUI(**options) as server:
                fixture = make_a14b_execution_fixture(self, server.endpoint)
                failed = fixture.execute()
                _validate_job(failed)
                self.assertEqual(failed["state"], "FAILED")
                self.assertEqual(failed["dispatchResult"]["outcome"], "UNKNOWN")
                self.assertEqual(failed["dispatchResult"]["requestWriteState"], "LOCAL_WRITE_COMPLETE")
                self.assertEqual(failed["dispatchResult"]["providerPromptId"], PROMPT_ID if response_known else None)
                self.assertEqual(server.complete_post_count, 1)
                self.assertEqual(server.history_count, 1 if response_known else 0)
                self.assert_original_recovery_no_resend(fixture, server)

    def test_partial_real_write_without_submission_receipt_is_unknown(self):
        with LoopbackComfyUI() as server:
            fixture = make_a14b_execution_fixture(self, server.endpoint)
            original_endheaders = http.client.HTTPConnection.endheaders
            def partial(connection, *args, **kwargs):
                original_endheaders(connection, *args, **kwargs)
                raise OSError("TEST_ONLY failure after real header bytes")
            with patch.object(http.client.HTTPConnection, "endheaders", partial):
                failed = fixture.execute()
            self.assertEqual(failed["dispatchResult"]["outcome"], "UNKNOWN")
            self.assertEqual(failed["dispatchResult"]["requestWriteState"], "MAY_HAVE_BEEN_SENT")
            self.assertIsNone(failed["dispatchResult"]["transportSubmissionRef"])
            self.assertEqual(server.complete_post_count, 0)
            self.assert_original_recovery_no_resend(fixture, server)

    def test_pause_before_open_or_during_connect_rechecks_original_lease_before_write(self):
        for pause_at in ("before-open", "during-connect"):
            with self.subTest(pause_at=pause_at), LoopbackComfyUI() as server:
                fixture = make_a14b_execution_fixture(self, server.endpoint)
                claimed, command, consumed = fixture.claim_and_consume()
                continuation = consumed["continuation"]
                def expire_lease_only():
                    changed = c.utc(fixture.clock.value) + timedelta(seconds=31)
                    self.assertLess(changed, c.utc(fixture.grant["limits"]["expiresAt"]))
                    fixture.clock.value = changed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    fixture.clock.monotonic_value += 31
                if pause_at == "before-open":
                    original = staged.ComfyUIStagedTransport.open_exchange
                    def delayed_open(transport, *args, **kwargs):
                        expire_lease_only()
                        return original(transport, *args, **kwargs)
                    patched = patch.object(staged.ComfyUIStagedTransport, "open_exchange", delayed_open)
                else:
                    original = http.client.HTTPConnection.connect
                    def delayed_connect(connection):
                        original(connection)
                        expire_lease_only()
                    patched = patch.object(http.client.HTTPConnection, "connect", delayed_connect)
                with patched, self.assertRaises((c.DispatchError, LiveGenerationDispatchTransportError)):
                    continuation.send_once(fixture.transport)
                self.assertTrue(continuation.spent)
                self.assertEqual(server.paths, [])
                self.assertEqual(server.complete_post_count, 0)
                self.assert_original_recovery_no_resend(fixture, server)
                print("A14B_EXPIRED_LEASE_EVIDENCE=" + json.dumps({"TEST_ONLY": True, "pauseAt": pause_at,
                    "leaseExpiredWithinGrant": True, "httpRequestCount": len(server.paths),
                    "completePostCount": 0, "capabilitySpent": continuation.spent, "originalAttemptCount": 1}, sort_keys=True))

    def test_actual_result_sqlite_cas_failure_never_resends_or_creates_attempt(self):
        with LoopbackComfyUI(frames=self.frames) as server:
            fixture = make_a14b_execution_fixture(self, server.endpoint)
            failures = []
            def conflict(boundary, job, result, *, workflow_digest):
                # Deliberately stale CAS enters the actual existing SQLite save.
                # Never replace a registered repository writer: doing so correctly
                # invalidates the coverage fence before any Grant consumption.
                del result, workflow_digest
                failures.append("REAL_SQLITE_CAS_REJECTED")
                return boundary.repository.save(deepcopy(job), job["revision"] + 1)
            with patch.object(GenerationDispatchLiveResultBoundary, "record_success", conflict):
                try:
                    unexpected = fixture.execute()
                except MediaJobStateError:
                    pass
                else:
                    self.fail("actual result CAS was not reached: " + json.dumps(unexpected.get("dispatchResult"), sort_keys=True))
            self.assertEqual(failures, ["REAL_SQLITE_CAS_REJECTED"])
            self.assertEqual(server.complete_post_count, 1)
            self.assertEqual(fixture.current_job()["state"], "RUNNING")
            self.assert_original_recovery_no_resend(fixture, server)


if __name__ == "__main__":
    unittest.main()
