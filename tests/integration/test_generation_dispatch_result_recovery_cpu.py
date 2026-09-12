from copy import deepcopy
import unittest

from services.v4_platform.media_jobs import MediaJobStateError, _validate_job
from tests.support.generation_dispatch_execution_fixtures import (
    ExecutionFixture, export_pkg3_evidence,
)


class GenerationDispatchResultRecoveryCpuIntegrationTests(unittest.TestCase):
    def test_connect_failure_commits_zero_and_is_non_retryable(self):
        fixture = ExecutionFixture(self, fault="connect")
        failed = fixture.execute()
        _validate_job(failed)
        self.assertEqual(failed["state"], "FAILED")
        self.assertEqual(failed["dispatchResult"]["outcome"], "FAILED")
        self.assertEqual(failed["dispatchResult"]["phase"], "CONNECT_NOT_STARTED")
        self.assertFalse(failed["dispatchResult"]["committedRequestBytes"])
        self.assertEqual(fixture.transport.commit_count, 0)
        with self.assertRaises(MediaJobStateError):
            fixture.coordinators[0].retry(fixture.scope["workspaceRef"],
                fixture.scope["productionRunRef"], failed["jobRef"])
        export_pkg3_evidence("result_connect_failure_actual.json", {
            "TEST_ONLY": True, "transportCommitCount": 0,
            "jobState": failed["state"],
            "resultOutcome": failed["dispatchResult"]["outcome"],
            "resultPhase": failed["dispatchResult"]["phase"],
            "retryRejected": True})

    def test_receipt_loss_and_response_read_failure_commit_once_and_never_resend(self):
        for fault in ("after_commit", "read"):
            with self.subTest(fault=fault):
                fixture = ExecutionFixture(self, fault=fault)
                failed = fixture.execute()
                self.assertEqual(failed["state"], "FAILED")
                self.assertEqual(failed["dispatchResult"]["outcome"], "UNKNOWN")
                self.assertEqual(failed["dispatchResult"]["phase"],
                    "SUBMISSION_OUTCOME_UNKNOWN")
                self.assertTrue(failed["dispatchResult"]["committedRequestBytes"])
                self.assertEqual(fixture.transport.commit_count, 1)
                recovered = fixture.executor.recover_read_only(
                    fixture.scope["workspaceRef"], fixture.scope["productionRunRef"],
                    failed["jobRef"])
                self.assertFalse(recovered["sendAttempted"])
                self.assertIsNone(recovered["continuation"])
                with self.assertRaises(MediaJobStateError):
                    fixture.execute()
                self.assertEqual(fixture.transport.commit_count, 1)
                self.assertEqual(len(fixture.current_job()["attempts"]), 1)
                export_pkg3_evidence(f"result_{fault}_actual.json", {
                    "TEST_ONLY": True, "fault": fault,
                    "transportCommitCount": fixture.transport.commit_count,
                    "jobState": failed["state"],
                    "resultOutcome": failed["dispatchResult"]["outcome"],
                    "resultPhase": failed["dispatchResult"]["phase"],
                    "attemptCount": len(fixture.current_job()["attempts"]),
                    "readOnlyRecovery": True, "resendCount": 0})

    def test_result_persistence_failure_does_not_resend_and_recovery_is_read_only(self):
        fixture = ExecutionFixture(self)
        original_boundary = fixture.result_boundary

        class FailingResultPersistenceBoundary:
            def __init__(self): self.calls = 0
            def record_success(self, job, result, *, workflow_digest):
                del result, workflow_digest
                self.calls += 1
                # Exercise the real SQLite save/CAS boundary with a deliberately
                # stale expected revision.  No method, transaction or CAS is mocked.
                return original_boundary.repository.save(deepcopy(dict(job)),
                    job["revision"] + 1)
            def read_only(self, *args): return original_boundary.read_only(*args)

        failing = FailingResultPersistenceBoundary()
        fixture.executor.result_boundary = failing
        with self.assertRaises(MediaJobStateError):
            fixture.execute()
        self.assertEqual(failing.calls, 1)
        self.assertEqual(fixture.transport.commit_count, 1)
        before = fixture.current_job()
        self.assertEqual(before["state"], "RUNNING")
        self.assertEqual(len(before["attempts"]), 1)
        self.assertIsNone(before.get("dispatchResult"))
        fixture.executor.result_boundary = original_boundary
        recovered = fixture.executor.recover_read_only(fixture.scope["workspaceRef"],
            fixture.scope["productionRunRef"], before["jobRef"])
        self.assertEqual(recovered["job"], before)
        self.assertIsNone(recovered["continuation"])
        self.assertEqual(recovered["consumption"]["receipt"]["terminal"]["kind"],
            "CONSUMPTION_COMMITTED")
        self.assertEqual(fixture.transport.commit_count, 1)
        with self.assertRaises(MediaJobStateError):
            fixture.execute()
        self.assertEqual(fixture.transport.commit_count, 1)
        export_pkg3_evidence("result_persistence_failure_actual.json", {
            "TEST_ONLY": True, "resultBoundaryCalls": failing.calls,
            "persistenceFailure": "REAL_SQLITE_REVISION_CAS_REJECTED",
            "transportCommitCount": fixture.transport.commit_count,
            "persistedJobState": before["state"],
            "persistedAttemptCount": len(before["attempts"]),
            "persistedDispatchResult": before.get("dispatchResult"),
            "terminalKind": recovered["consumption"]["receipt"]["terminal"]["kind"],
            "readOnlyRecovery": True, "resendCount": 0})


if __name__ == "__main__":
    unittest.main()
