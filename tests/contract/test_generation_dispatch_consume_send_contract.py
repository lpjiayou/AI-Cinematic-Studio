from copy import deepcopy
from threading import Barrier, Thread
import unittest

from services.v4_platform.generation_dispatch_transport import (
    CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
    REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED,
    SUBMISSION_OUTCOME_UNKNOWN, validate_transport_request,
    validate_transport_submission,
)
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_execution_fixtures import (
    CpuIsolatedFakeTransport, LightweightConsumptionFixture,
    export_pkg3_evidence,
)


class GenerationDispatchConsumeSendContractTests(unittest.TestCase):
    def test_consume_terminal_and_receipt_are_closed_and_fully_bound(self):
        fixture = LightweightConsumptionFixture(self)
        result = fixture.consume()
        receipt = c.validate_consume_receipt(result["receipt"])
        terminal = c.validate_terminal(receipt["terminal"])
        binding = terminal["attemptBinding"]
        self.assertEqual(set(binding), {"mediaJobRef", "attemptRef", "workerRef",
            "workerProcessIdentityDigest", "jobRevision", "leaseTokenDigest",
            "executionEnvelopeDigest", "workflowDigest", "currentSubjectReadSet",
            "currentSubjectReadSetDigest"})
        for value in (deepcopy(receipt), deepcopy(terminal)):
            value["unexpected"] = True
            with self.assertRaises(c.DispatchError):
                (c.validate_consume_receipt(value) if "operation" in value
                 else c.validate_terminal(value))

    def test_transport_contract_has_explicit_initial_write_phases_and_closed_policy(self):
        self.assertEqual(len({CONNECT_NOT_STARTED, REQUEST_BYTES_NOT_COMMITTED,
            REQUEST_BYTES_COMMITTED, RESPONSE_RECEIVED,
            SUBMISSION_OUTCOME_UNKNOWN}), 5)
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        transport = CpuIsolatedFakeTransport(fixture.clock, root=fixture.root,
            fault="after_commit")
        with self.assertRaises(Exception):
            capability.send_once(transport)
        request = validate_transport_request(transport.last_request)
        submission = validate_transport_submission(transport.last_submission)
        self.assertEqual(request["transportPolicy"], {
            "maxPromptSubmissions": 1, "postRetryAllowed": False,
            "redirectAllowed": False, "fallbackAllowed": False})
        self.assertEqual(submission["phase"], REQUEST_BYTES_COMMITTED)
        self.assertNotIn("endpoint", request)
        self.assertNotIn("credential", request)
        self.assertNotIn("/prompt", repr(request))
        invalid = deepcopy(request); invalid["retry"] = True
        with self.assertRaises(ValueError):
            validate_transport_request(invalid)

    def test_revoke_before_consume_and_consume_before_revoke_are_terminally_unique(self):
        revoked = LightweightConsumptionFixture(self)
        revoke_command = revoked.grants.revoke_command(revoked.grant)
        revoke = revoked.grants.service.revoke(revoke_command)
        self.assertEqual(revoke["terminal"]["kind"], "REVOKED")
        with self.assertRaises(c.DispatchError) as error:
            revoked.consume()
        self.assertEqual(error.exception.code, "ALREADY_REVOKED")

        consumed = LightweightConsumptionFixture(self)
        consumed.consume()
        with self.assertRaises(c.DispatchError) as error:
            consumed.grants.service.revoke(
                consumed.grants.revoke_command(consumed.grant))
        self.assertEqual(error.exception.code, "ALREADY_CONSUMED")

    def test_concurrent_consume_and_revoke_create_exactly_one_terminal(self):
        fixture = LightweightConsumptionFixture(self, memory=False)
        revoke_command = fixture.grants.revoke_command(fixture.grant)
        barrier = Barrier(3)
        outcomes = []

        def consume():
            barrier.wait()
            try:
                outcomes.append(("consume", fixture.consumer.consume(
                    deepcopy(fixture.command))))
            except c.DispatchError as exc:
                outcomes.append(("consume-error", exc.code))

        def revoke():
            barrier.wait()
            try:
                outcomes.append(("revoke", fixture.grants.service.revoke(
                    deepcopy(revoke_command))))
            except c.DispatchError as exc:
                outcomes.append(("revoke-error", exc.code))

        threads = [Thread(target=consume), Thread(target=revoke)]
        for thread in threads: thread.start()
        barrier.wait()
        for thread in threads: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        terminals = [row for row in fixture.grants.records()
            if row["recordKind"] == "GenerationDispatchGrantTerminal"]
        self.assertEqual(len(terminals), 1, outcomes)
        self.assertIn(terminals[0]["payload"]["kind"],
            {"CONSUMPTION_COMMITTED", "REVOKED"})
        self.assertEqual(sum(name in {"consume", "revoke"}
            for name, _ in outcomes), 1, outcomes)
        export_pkg3_evidence("consume_revoke_race_actual.json", {
            "TEST_ONLY": True, "outcomes": [name for name, _ in outcomes],
            "terminalCount": len(terminals),
            "terminalKind": terminals[0]["payload"]["kind"],
            "generationDispatchGrantRef": fixture.grant[
                "generationDispatchGrantRef"]})

    def test_public_boundary_still_has_no_consume_operation(self):
        fixture = LightweightConsumptionFixture(self)
        self.assertFalse(hasattr(fixture.grants.public, "consume"))


if __name__ == "__main__":
    unittest.main()
