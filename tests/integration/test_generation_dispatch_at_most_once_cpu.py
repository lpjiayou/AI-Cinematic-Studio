from copy import deepcopy
from hashlib import sha256
from threading import Barrier, Thread
import unittest

from services.v4_platform.generation_dispatch_execution import (
    GenerationDispatchExecutor, GenerationDispatchResultBoundary,
    MediaJobGenerationDispatchPort,
)
from services.v4_platform.media_jobs import MediaJobStateError
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_authority import PinnedApprovalReader
from services.v5_core_os.episode_production.generation_dispatch_consumption import GenerationDispatchConsumer
from tests.support.generation_dispatch_execution_fixtures import (
    CpuIsolatedFakeTransport, ExecutionFixture, TestWorkerExecutionContext,
    export_pkg3_evidence,
)
from tests.support.generation_dispatch_fixtures import approval_for


class GenerationDispatchAtMostOnceCpuIntegrationTests(unittest.TestCase):
    def test_two_workers_create_one_attempt_one_terminal_and_one_commit(self):
        fixture = ExecutionFixture(self, worker_ref="test-pkg3-worker-a")
        second_context = TestWorkerExecutionContext("test-pkg3-worker-b")
        second_port = MediaJobGenerationDispatchPort(
            coordinator=fixture.coordinators[1],
            coordination=fixture.dispatch.coordination, clock=fixture.clock)
        second_consumer = GenerationDispatchConsumer(
            foundation=fixture.dispatch.boundary._foundation,
            job_port=second_port, worker_context=second_context,
            clock=fixture.clock)
        second_transport = CpuIsolatedFakeTransport(fixture.clock,
            root=fixture.root)
        second_result = GenerationDispatchResultBoundary(
            fixture.coordinators[1], clock=fixture.clock)
        second_executor = GenerationDispatchExecutor(
            coordinator=fixture.coordinators[1], consumer=second_consumer,
            worker_context=second_context, transport=second_transport,
            clock=fixture.clock, coordination=fixture.dispatch.coordination,
            result_boundary=second_result, job_port=second_port)
        barrier = Barrier(3)
        outcomes = []

        def run(executor, name):
            barrier.wait()
            try:
                outcomes.append((name, executor.execute(fixture.scope["workspaceRef"],
                    fixture.scope["productionRunRef"], fixture.job["jobRef"])))
            except BaseException as exc:
                outcomes.append((name, exc))

        threads = [Thread(target=run, args=(fixture.executor, "a")),
            Thread(target=run, args=(second_executor, "b"))]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(timeout=180)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        successes = [value for _, value in outcomes if isinstance(value, dict)]
        failures = [value for _, value in outcomes if isinstance(value, BaseException)]
        self.assertEqual(len(successes), 1, outcomes)
        self.assertEqual(len(failures), 1, outcomes)
        self.assertIsInstance(failures[0], MediaJobStateError)
        current = fixture.current_job()
        self.assertEqual(current["state"], "SUCCEEDED")
        self.assertEqual(len(current["attempts"]), 1)
        terminals = [row for row in fixture.evidence.list_records(
            fixture.scope["workspaceRef"], fixture.scope["productionRunRef"])
            if row["recordKind"] == "GenerationDispatchGrantTerminal"]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(fixture.transport.commit_count
            + second_transport.commit_count, 1)
        export_pkg3_evidence("at_most_once_concurrent_actual.json", {
            "TEST_ONLY": True, "workerOutcomeCount": len(outcomes),
            "successfulWorkerCount": len(successes),
            "failedWorkerCount": len(failures),
            "attemptCount": len(current["attempts"]),
            "terminalCount": len(terminals),
            "transportCommitCount": fixture.transport.commit_count
                + second_transport.commit_count,
            "jobState": current["state"]})

    def test_same_attempt_heartbeat_revision_is_allowed_at_l2(self):
        fixture = ExecutionFixture(self)
        claimed, _, consumed = fixture.claim_and_consume()
        capability = consumed["continuation"]
        fixture.advance(5)
        renewed = fixture.coordinators[0]._renew_running_lease(
            fixture.scope["workspaceRef"], fixture.scope["productionRunRef"],
            claimed["jobRef"], claimed["lease"]["workerRef"],
            claimed["lease"]["leaseToken"], claimed["attempts"][-1]["attemptRef"])
        self.assertGreater(renewed["revision"], claimed["revision"])
        transport = CpuIsolatedFakeTransport(fixture.clock, root=fixture.root,
            fault="after_commit")
        with self.assertRaises(Exception):
            capability.send_once(transport)
        self.assertEqual(transport.commit_count, 1)

    def test_real_sqlite_consume_revoke_race_has_one_terminal(self):
        fixture = ExecutionFixture(self)
        claimed, consume_command = fixture.claim_command()
        revocation = approval_for(grant_digest=fixture.grant["payloadDigest"])
        fixture.originals.register(revocation)
        bundle = {"schemaVersion": c.REVOCATION_SCHEMA,
            "authorityRef": revocation["authorityRef"],
            "revocations": [revocation]}
        path = fixture.root / "test-pkg3-revocation.json"
        path.write_bytes(c.canonical(bundle))
        fixture.dispatch.boundary._foundation.revocation_reader = PinnedApprovalReader(
            path, sha256(path.read_bytes()).hexdigest(), original=fixture.originals,
            revocation=True)
        revoke_command = {"workspaceRef": fixture.scope["workspaceRef"],
            "productionRunRef": fixture.scope["productionRunRef"],
            "generationDispatchGrantRef": fixture.grant["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": fixture.grant["payloadDigest"],
            "authorityDecisionRef": revocation["authorityDecisionRef"],
            "idempotencyKey": "test-pkg3-race-revoke",
            "snapshotTokens": deepcopy(consume_command["snapshotTokens"])}
        barrier = Barrier(3)
        outcomes = []

        def consume():
            barrier.wait()
            try: outcomes.append(("consume", fixture.consumer.consume(consume_command)))
            except c.DispatchError as exc: outcomes.append(("consume-error", exc.code))

        def revoke():
            barrier.wait()
            try: outcomes.append(("revoke", fixture.dispatch.boundary._foundation.revoke(revoke_command)))
            except c.DispatchError as exc: outcomes.append(("revoke-error", exc.code))

        threads = [Thread(target=consume), Thread(target=revoke)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(timeout=60)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        terminals = [row for row in fixture.evidence.list_records(
            fixture.scope["workspaceRef"], fixture.scope["productionRunRef"])
            if row["recordKind"] == "GenerationDispatchGrantTerminal"]
        self.assertEqual(len(terminals), 1, outcomes)
        self.assertEqual(sum(name in {"consume", "revoke"}
            for name, _ in outcomes), 1, outcomes)
        self.assertEqual(len(fixture.current_job()["attempts"]), 1)
        self.assertEqual(fixture.transport.commit_count, 0)
        export_pkg3_evidence("consume_revoke_race_sqlite_actual.json", {
            "TEST_ONLY": True, "outcomes": [name for name, _ in outcomes],
            "terminalCount": len(terminals),
            "terminalKind": terminals[0]["payload"]["kind"],
            "attemptCount": len(fixture.current_job()["attempts"]),
            "transportCommitCount": fixture.transport.commit_count,
            "realTemporarySqlite": True,
            "sharedWorkspaceGate": True,
            "mediaJobRef": claimed["jobRef"]})

    def test_cancel_and_expired_lease_are_rejected_before_transport(self):
        cancelled = ExecutionFixture(self)
        claimed, _, consumed = cancelled.claim_and_consume()
        cancelled.coordinators[0].cancel(cancelled.scope["workspaceRef"],
            cancelled.scope["productionRunRef"], claimed["jobRef"])
        with self.assertRaises(c.DispatchError):
            consumed["continuation"].send_once(cancelled.transport)
        self.assertEqual(cancelled.transport.commit_count, 0)

        expired = ExecutionFixture(self)
        _, _, consumed = expired.claim_and_consume()
        expired.advance(31)
        with self.assertRaises(c.DispatchError):
            consumed["continuation"].send_once(expired.transport)
        self.assertEqual(expired.transport.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
