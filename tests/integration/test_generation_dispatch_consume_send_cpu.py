import socket
import unittest
from unittest.mock import patch

from services.v4_platform.media_jobs import MediaJobStateError, _validate_job
from tests.support.generation_dispatch_execution_fixtures import (
    ExecutionFixture, export_pkg3_evidence,
)


class GenerationDispatchConsumeSendCpuIntegrationTests(unittest.TestCase):
    def test_package2_chain_to_test_only_result_is_one_closed_cpu_loop(self):
        fixture = ExecutionFixture(self)
        with patch.object(socket, "socket",
                side_effect=AssertionError("Package 3 socket call forbidden")):
            completed = fixture.execute()
        _validate_job(completed)
        self.assertEqual(completed["schemaVersion"], "v4.media-job.v4")
        self.assertEqual(completed["state"], "SUCCEEDED")
        self.assertEqual(len(completed["attempts"]), 1)
        self.assertEqual(completed["attempts"][0]["state"], "SUCCEEDED")
        result = completed["dispatchResult"]
        artifact = completed["artifact"]
        terminal = fixture.executor.recover_read_only(fixture.scope["workspaceRef"],
            fixture.scope["productionRunRef"], completed["jobRef"])["consumption"]["receipt"]["terminal"]
        self.assertEqual(terminal["kind"], "CONSUMPTION_COMMITTED")
        self.assertEqual(terminal["attemptBinding"]["mediaJobRef"], completed["jobRef"])
        self.assertEqual(terminal["attemptBinding"]["attemptRef"], completed["attempts"][0]["attemptRef"])
        self.assertEqual(result["generationDispatchGrantDigest"], fixture.grant["payloadDigest"])
        self.assertEqual(result["executionEnvelopeDigest"], completed["executionEnvelope"]["envelopeDigest"])
        self.assertEqual(result["workflowDigest"], fixture.grant["executionBinding"]["workflowDigest"])
        self.assertEqual(result["artifactDigest"], artifact["sha256"])
        self.assertEqual(artifact["dispatchResultDigest"], result["payloadDigest"])
        self.assertFalse(artifact["gpuUsed"])
        self.assertEqual(artifact["provenance"], "TEST_ONLY")
        self.assertEqual([item.adapter.generate_calls
            for item in fixture.coordinators], [0, 0])
        self.assertEqual(fixture.transport.evidence(), {"TEST_ONLY": True,
            "CPU_ISOLATED": True, "openCount": 1,
            "initialWriteAttemptCount": 1, "requestCommitCount": 1,
            "readCount": 1, "networkCalls": 0, "socketCalls": 0,
            "PROMPT_SUBMISSION_COUNT": 0, "COMFYUI_CONNECTIONS": 0,
            "GPU_CALLS": 0, "requestsImports": 0, "httpxImports": 0})
        export_pkg3_evidence("cpu_closed_loop_actual.json", {
            "TEST_ONLY": True,
            "generationDispatchGrantRef": fixture.grant[
                "generationDispatchGrantRef"],
            "mediaJobRef": completed["jobRef"],
            "attemptRef": completed["attempts"][0]["attemptRef"],
            "terminalKind": terminal["kind"], "jobState": completed["state"],
            "dispatchResultOutcome": result["outcome"],
            "transport": fixture.transport.evidence(),
            "artifactDigest": artifact["sha256"],
            "dispatchResultDigest": result["payloadDigest"]})

    def test_legacy_worker_entrypoints_still_reject_job_v4_before_claim(self):
        fixture = ExecutionFixture(self)
        before = fixture.current_job()
        with self.assertRaises(MediaJobStateError):
            fixture.coordinators[0].lease_job(fixture.scope["workspaceRef"],
                fixture.scope["productionRunRef"], fixture.job["jobRef"],
                "test-old-worker")
        with self.assertRaises(MediaJobStateError):
            fixture.coordinators[0].run_one(fixture.scope["workspaceRef"],
                fixture.scope["productionRunRef"], fixture.job["jobRef"],
                "test-old-worker")
        self.assertEqual(before, fixture.current_job())
        self.assertEqual(fixture.transport.commit_count, 0)

    def test_lost_capability_survives_only_as_terminal_and_cannot_be_rebuilt(self):
        fixture = ExecutionFixture(self)
        claimed, _, consumed = fixture.claim_and_consume()
        self.assertIsNotNone(consumed["continuation"])
        del consumed
        recovered = fixture.executor.recover_read_only(fixture.scope["workspaceRef"],
            fixture.scope["productionRunRef"], claimed["jobRef"])
        self.assertIsNone(recovered["continuation"])
        self.assertFalse(recovered["sendAttempted"])
        self.assertEqual(recovered["job"]["state"], "RUNNING")
        self.assertEqual(len(recovered["job"]["attempts"]), 1)
        self.assertEqual(recovered["consumption"]["receipt"]["terminal"]["kind"],
            "CONSUMPTION_COMMITTED")
        with self.assertRaises(MediaJobStateError):
            fixture.execute()
        self.assertEqual(fixture.transport.commit_count, 0)
        self.assertEqual(len(fixture.current_job()["attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
