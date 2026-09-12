from copy import deepcopy
import os
from threading import get_ident
import unittest

from services.v4_platform.generation_dispatch_execution import LocalWorkerExecutionContext
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_execution_fixtures import (
    LightweightConsumptionFixture,
)
from tests.support.generation_dispatch_fixtures import fault_at


class GenerationDispatchConsumptionUnitTests(unittest.TestCase):
    def test_linux_worker_identity_is_trusted_local_process_and_current_thread(self):
        context = LocalWorkerExecutionContext("test-pkg3-linux-worker",
            core_commit="b" * 40)
        identity = context.current()
        self.assertEqual(identity["processId"], os.getpid())
        self.assertEqual(identity["threadId"], get_ident())
        c.sha(identity["workerProcessIdentityDigest"])

    def test_first_consume_commits_one_terminal_and_replay_has_no_capability(self):
        fixture = LightweightConsumptionFixture(self)
        first = fixture.consume()
        self.assertFalse(first["receipt"]["recordReplay"])
        self.assertIsNotNone(first["continuation"])
        replay = fixture.consume()
        self.assertTrue(replay["receipt"]["recordReplay"])
        self.assertIsNone(replay["continuation"])
        terminals = [record for record in fixture.grants.records()
            if record["recordKind"] == "GenerationDispatchGrantTerminal"]
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0]["payload"]["kind"], "CONSUMPTION_COMMITTED")
        self.assertEqual(fixture.job_port.read_phases, ["CONSUME", "CONSUME"])

    def test_attempt_revision_worker_and_lease_are_fail_closed_before_append(self):
        mutations = {
            "expectedJobRevision": lambda command: command.update(
                expectedJobRevision=command["expectedJobRevision"] + 1),
            "attemptRef": lambda command: command.update(attemptRef="test-other-attempt"),
            "workerRef": lambda command: command.update(workerRef="test-other-worker"),
            "expectedLeaseTokenDigest": lambda command: command.update(
                expectedLeaseTokenDigest=c.digest("test-other-lease")),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                fixture = LightweightConsumptionFixture(self)
                command = deepcopy(fixture.command)
                mutate(command)
                with self.assertRaises(c.DispatchError):
                    fixture.consumer.consume(command)
                self.assertEqual(len(fixture.grants.records()), 1)

    def test_commit_outcome_unknown_returns_no_capability_and_history_is_read_only(self):
        fixture = LightweightConsumptionFixture(self, memory=False)
        with fault_at(fixture.grants.repo, "after_commit"):
            with self.assertRaises(c.CommitOutcomeUnknown):
                fixture.consume()
        history = fixture.consumer.read_consumption_receipt(
            fixture.grant["workspaceRef"], fixture.grant["productionRunRef"],
            fixture.grant["generationDispatchGrantRef"])
        self.assertIsNotNone(history)
        self.assertIsNone(history["continuation"])
        before = fixture.grants.records()
        self.assertEqual(len(before), 2)
        self.assertEqual(before, fixture.grants.records())

    def test_l1_requires_the_complete_execution_window_before_terminal_append(self):
        fixture = LightweightConsumptionFixture(self)
        fixture.clock.value = "2030-01-01T00:59:30.000000Z"
        with self.assertRaises(c.DispatchError) as error:
            fixture.consume()
        self.assertEqual(error.exception.code, "OUTSIDE_VALIDITY_WINDOW")
        self.assertEqual(len(fixture.grants.records()), 1)

    def test_consumed_grant_rejects_changed_semantics_and_new_idempotency(self):
        fixture = LightweightConsumptionFixture(self)
        fixture.consume()
        changed = deepcopy(fixture.command)
        changed["attemptRef"] = "test-other-attempt"
        with self.assertRaises(c.DispatchError) as error:
            fixture.consumer.consume(changed)
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
        new_key = deepcopy(fixture.command)
        new_key["idempotencyKey"] = "test-pkg3-other-consume"
        with self.assertRaises(c.DispatchError) as error:
            fixture.consumer.consume(new_key)
        self.assertEqual(error.exception.code, "ALREADY_CONSUMED")
        self.assertEqual(len(fixture.grants.records()), 2)


if __name__ == "__main__":
    unittest.main()
