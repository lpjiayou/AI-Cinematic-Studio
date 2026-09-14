from copy import deepcopy
import unittest
from unittest.mock import patch

from services.v4_platform.media_jobs import MediaJobStateError, _validate_job
from tests.support.generation_dispatch_execution_fixtures import (
    ExecutionFixture, export_pkg3_evidence,
)
from services.v5_core_os.episode_production import generation_dispatch_contracts as c


class GenerationDispatchPreSendRecoveryTests(unittest.TestCase):
    def recover(self, fixture):
        return fixture.executor.finalize_unconsumed_expired(
            fixture.scope["workspaceRef"], fixture.scope["productionRunRef"],
            fixture.job["jobRef"])

    def assert_unsent_failure(self, fixture, job, code):
        _validate_job(job)
        self.assertEqual(job["state"], "FAILED")
        self.assertEqual(len(job["attempts"]), 1)
        self.assertTrue(job["attempts"][0]["nonRetryable"])
        self.assertEqual(job["dispatchResult"]["failureCode"], code)
        self.assertEqual(job["dispatchResult"]["phase"], "CONNECT_NOT_STARTED")
        self.assertFalse(job["dispatchResult"]["committedRequestBytes"])
        self.assertIsNone(job["lease"])
        self.assertEqual(fixture.transport.open_count, 0)
        self.assertEqual(fixture.transport.commit_count, 0)

    def test_snapshot_failure_before_claim_preserves_queued_job(self):
        f = ExecutionFixture(self)
        before = f.current_job()
        with patch.object(f.consumer, "snapshot_tokens", side_effect=c.DispatchError("RUNTIME_CHANGED")):
            with self.assertRaises(c.DispatchError) as failed:
                f.execute()
        self.assertEqual(failed.exception.code, "RUNTIME_CHANGED")
        self.assertEqual(f.current_job(), before)
        self.assertEqual(f.transport.open_count, 0)

    def test_consume_failure_closes_original_attempt_without_send(self):
        f = ExecutionFixture(self)
        with patch.object(f.consumer, "consume", side_effect=c.DispatchError("RUNTIME_CHANGED")):
            with self.assertRaises(c.DispatchError) as failed:
                f.execute()
        self.assertEqual(failed.exception.code, "RUNTIME_CHANGED")
        self.assert_unsent_failure(f, f.current_job(), "RUNTIME_CHANGED")
        self.assertIsNone(f.consumer.read_consumption_receipt(f.scope["workspaceRef"],
            f.scope["productionRunRef"], f.grant["generationDispatchGrantRef"]))
        with self.assertRaises(MediaJobStateError):
            f.execute()

    def test_unexpected_consume_error_is_sanitized_and_not_retried(self):
        f = ExecutionFixture(self)
        with patch.object(f.consumer, "consume", side_effect=OSError("private-secret-not-for-result")):
            with self.assertRaises(OSError):
                f.execute()
        self.assert_unsent_failure(f, f.current_job(), "PRE_CONSUMPTION_FAILED")
        self.assertNotIn("private-secret", str(f.current_job()))

    def test_consumption_committed_then_exception_never_refunds_terminal(self):
        f = ExecutionFixture(self)
        consume = f.consumer.consume
        def fail_after_commit(command):
            consume(command)
            raise OSError("return path failed before any send")
        with patch.object(f.consumer, "consume", side_effect=fail_after_commit):
            with self.assertRaises(OSError):
                f.execute()
        self.assert_unsent_failure(f, f.current_job(), "PRE_CONSUMPTION_FAILED")
        self.assertIsNotNone(f.consumer.read_consumption_receipt(f.scope["workspaceRef"],
            f.scope["productionRunRef"], f.grant["generationDispatchGrantRef"]))
        f.advance(60)
        before = f.current_job()
        with self.assertRaises(MediaJobStateError):
            self.recover(f)
        self.assertEqual(f.current_job(), before)

    def test_expired_unconsumed_attempt_is_closed_not_reclaimed(self):
        f = ExecutionFixture(self)
        claimed, _ = f.claim_command()
        before_identity = deepcopy(claimed["attempts"][0])
        f.advance(60)
        # Recovery must not impersonate or require the exited worker.
        f.worker_context.process_digest = c.digest("different-recovery-process")
        closed = self.recover(f)
        self.assert_unsent_failure(f, closed, "PRE_CONSUMPTION_LEASE_EXPIRED")
        for key, value in before_identity.items():
            if key != "state":
                self.assertEqual(closed["attempts"][0][key], value)
        self.assertEqual(self.recover(f), closed)
        with self.assertRaises(MediaJobStateError):
            f.execute()

    def test_unexpired_attempt_cannot_be_finalized(self):
        f = ExecutionFixture(self)
        f.claim_command()
        before = f.current_job()
        with self.assertRaises(MediaJobStateError):
            self.recover(f)
        self.assertEqual(f.current_job(), before)

    def test_consumed_attempt_never_reclassified_as_unsent(self):
        f = ExecutionFixture(self)
        f.claim_and_consume()
        f.advance(60)
        before = f.current_job()
        with self.assertRaises(MediaJobStateError):
            self.recover(f)
        self.assertEqual(f.current_job(), before)
        self.assertEqual(f.transport.open_count, 0)

    def test_expiry_during_consume_does_not_revive_lease(self):
        f = ExecutionFixture(self)
        def expire(command):
            f.advance(60)
            raise c.DispatchError("RUNTIME_CHANGED")
        with patch.object(f.consumer, "consume", side_effect=expire):
            with self.assertRaises(MediaJobStateError):
                f.execute()
        self.assertEqual(f.current_job()["state"], "RUNNING")
        closed = self.recover(f)
        self.assert_unsent_failure(f, closed, "PRE_CONSUMPTION_LEASE_EXPIRED")

    def test_expired_recovery_journal_failure_does_not_assume_no_consumption(self):
        f = ExecutionFixture(self)
        f.claim_command()
        f.advance(60)
        before = f.current_job()
        with patch.object(f.consumer, "read_failure_evidence", side_effect=OSError("journal unavailable")):
            with self.assertRaises(OSError):
                self.recover(f)
        self.assertEqual(f.current_job(), before)

    def test_failure_save_rejects_stale_cas_and_leaves_recoverable_evidence(self):
        from services.v4_platform import generation_dispatch_execution as execution
        f = ExecutionFixture(self)
        make_result = execution.make_dispatch_result
        advanced = []
        def advance_revision_before_failure_save(**fields):
            result = make_result(**fields)
            # Inject a competing revision through the real registered SQLite
            # writer. Never replace its fenced save method or fake its CAS.
            current = f.current_job()
            advanced.append(f.queues[0].save(current, current["revision"]))
            return result
        with patch.object(f.consumer, "consume", side_effect=c.DispatchError("RUNTIME_CHANGED")), \
                patch.object(execution, "make_dispatch_result",
                    side_effect=advance_revision_before_failure_save):
            with self.assertRaisesRegex(MediaJobStateError, "^media job revision changed$"):
                f.execute()
        self.assertEqual(len(advanced), 1)
        self.assertEqual(f.current_job(), advanced[0])
        self.assertEqual(f.current_job()["state"], "RUNNING")
        self.assertIsNone(f.current_job()["dispatchResult"])
        self.assertEqual(f.transport.open_count, 0)
        f.advance(60)
        self.assert_unsent_failure(f, self.recover(f), "PRE_CONSUMPTION_LEASE_EXPIRED")

    def test_late_consume_and_expired_cleanup_share_gate_without_send(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        f = ExecutionFixture(self)
        _, command = f.claim_command()
        f.advance(60)
        ready = Barrier(2)
        def late_consume():
            ready.wait(timeout=10)
            try:
                return f.consumer.consume(command)
            except c.DispatchError as exc:
                return exc.code
        def close():
            ready.wait(timeout=10)
            return self.recover(f)
        with ThreadPoolExecutor(max_workers=2) as pool:
            consuming = pool.submit(late_consume)
            closing = pool.submit(close)
            self.assertEqual(consuming.result(timeout=60), "ATTEMPT_OR_LEASE_CHANGED")
            self.assert_unsent_failure(f, closing.result(timeout=60), "PRE_CONSUMPTION_LEASE_EXPIRED")
        self.assertIsNone(f.consumer.read_consumption_receipt(f.scope["workspaceRef"],
            f.scope["productionRunRef"], f.grant["generationDispatchGrantRef"]))


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
