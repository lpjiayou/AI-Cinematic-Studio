from copy import copy, deepcopy
import json
import os
import pickle
from threading import Thread
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_execution_fixtures import (
    CpuIsolatedFakeTransport, LightweightConsumptionFixture,
    export_pkg3_evidence,
)


class GenerationDispatchSendCapabilityUnitTests(unittest.TestCase):
    def test_capability_has_no_dict_projection_and_rejects_all_serializers(self):
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        operations = (lambda: copy(capability), lambda: deepcopy(capability),
            lambda: pickle.dumps(capability), lambda: json.dumps(capability),
            lambda: vars(capability))
        for operation in operations:
            with self.subTest(operation=repr(operation)), self.assertRaises(TypeError):
                operation()
        self.assertNotIn(fixture.job["lease"]["leaseToken"], repr(capability))
        export_pkg3_evidence("capability_serialization_actual.json", {
            "TEST_ONLY": True, "copyRejected": True,
            "deepcopyRejected": True, "pickleRejected": True,
            "jsonRejected": True, "dictProjectionRejected": True,
            "rawLeaseTokenAbsentFromRepr": True})

    def test_cross_thread_use_is_rejected_and_permanently_consumes_authority(self):
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        transport = CpuIsolatedFakeTransport(fixture.clock, root=fixture.root)
        failures = []

        def other_thread():
            try:
                capability.send_once(transport)
            except BaseException as exc:
                failures.append(exc)

        thread = Thread(target=other_thread)
        thread.start(); thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], c.DispatchError)
        self.assertEqual(transport.commit_count, 0)
        self.assertTrue(capability.spent)
        with self.assertRaises(c.DispatchError):
            capability.send_once(transport)
        export_pkg3_evidence("capability_cross_thread_actual.json", {
            "TEST_ONLY": True, "crossThreadRejected": True,
            "transportCommitCount": transport.commit_count,
            "capabilitySpent": capability.spent})

    @unittest.skipUnless(hasattr(os, "fork"), "Linux fork is required")
    def test_cross_process_use_is_rejected_without_transport_commit(self):
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(read_fd)
                transport = CpuIsolatedFakeTransport(fixture.clock, root=fixture.root)
                try:
                    capability.send_once(transport)
                    outcome = b"accepted"
                except c.DispatchError:
                    outcome = b"rejected"
                os.write(write_fd, outcome + b":" + str(transport.commit_count).encode())
            finally:
                os.close(write_fd)
                os._exit(0)
        os.close(write_fd)
        try:
            outcome = os.read(read_fd, 100)
        finally:
            os.close(read_fd)
            waited, status = os.waitpid(pid, 0)
        self.assertEqual(waited, pid)
        self.assertEqual(status, 0)
        self.assertEqual(outcome, b"rejected:0")
        export_pkg3_evidence("capability_cross_process_actual.json", {
            "TEST_ONLY": True, "crossProcessRejected": True,
            "childObservation": outcome.decode("ascii")})

    def test_first_send_invocation_is_final_for_success_failure_or_unknown(self):
        for fault, expected_commits in (("connect", 0), ("partial_write", 0),
                ("after_commit", 1), ("timeout", 1), ("cancel", 1)):
            with self.subTest(fault=fault):
                fixture = LightweightConsumptionFixture(self)
                capability = fixture.consume()["continuation"]
                transport = CpuIsolatedFakeTransport(fixture.clock,
                    root=fixture.root, fault=fault)
                with self.assertRaises(Exception):
                    capability.send_once(transport)
                self.assertTrue(capability.spent)
                self.assertEqual(transport.commit_count, expected_commits)
                with self.assertRaises(c.DispatchError):
                    capability.send_once(transport)
                self.assertEqual(transport.commit_count, expected_commits)

    def test_l2_currentness_lease_and_budget_changes_commit_zero(self):
        for change in ("source", "backend", "runtime", "cost", "approval",
                       "lease", "attempt", "budget"):
            with self.subTest(change=change):
                fixture = LightweightConsumptionFixture(self)
                capability = fixture.consume()["continuation"]
                if change in {"source", "backend", "runtime", "cost"}:
                    fixture.grants.readers.failure = change
                elif change == "approval":
                    fixture.grants.originals.failure = True
                elif change == "lease":
                    fixture.job_port.lease_token = "test-replaced-lease"
                elif change == "attempt":
                    fixture.job_port.job["attempts"][-1]["attemptRef"] = "test-replaced-attempt"
                else:
                    fixture.clock.monotonic_value += 59.5
                with self.assertRaises(c.DispatchError):
                    capability.send_once(fixture.transport)
                self.assertTrue(capability.spent)
                self.assertEqual(fixture.transport.commit_count, 0)

    def test_heartbeat_revision_is_allowed_but_binding_change_is_rejected(self):
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        fixture.job_port.job["revision"] += 1
        fixture.job_port.job["lease"]["expiresAt"] = "2030-01-01T00:00:50.000Z"
        transport = CpuIsolatedFakeTransport(fixture.clock, root=fixture.root,
            fault="after_commit")
        with self.assertRaises(Exception):
            capability.send_once(transport)
        self.assertEqual(transport.commit_count, 1)

        changed = LightweightConsumptionFixture(self)
        denied = changed.consume()["continuation"]
        changed.job_port.stable_digest = c.digest("changed-binding")
        with self.assertRaises(c.DispatchError):
            denied.send_once(changed.transport)
        self.assertEqual(changed.transport.commit_count, 0)

    def test_capability_is_spent_before_open_and_response_read_is_outside_gate(self):
        fixture = LightweightConsumptionFixture(self)
        capability = fixture.consume()["continuation"]
        observations = []

        class ProbeTransport(CpuIsolatedFakeTransport):
            def open_exchange(self, request):
                observations.append(("open", capability.spent,
                    getattr(fixture.grants.fence.thread, "depth", 0)))
                return super().open_exchange(request)
            def read_result(self, exchange, submission):
                observations.append(("read", capability.spent,
                    getattr(fixture.grants.fence.thread, "depth", 0)))
                return super().read_result(exchange, submission)

        transport = ProbeTransport(fixture.clock, root=fixture.root, fault="read")
        with self.assertRaises(Exception):
            capability.send_once(transport)
        self.assertEqual(observations, [("open", True, 1), ("read", True, 0)])
        self.assertEqual(transport.commit_count, 1)


if __name__ == "__main__":
    unittest.main()
