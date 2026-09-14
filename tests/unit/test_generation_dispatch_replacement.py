"""Narrow v2 replacement contract: synthetic originals, real original journal."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_fixtures import (
    Fixture, approval_for, rebuild_workflow, synthetic_consumption, fault_at,
)


class GenerationDispatchReplacementTests(unittest.TestCase):
    def fixture(self, *, revoked=True, memory=True, changed_code=True):
        f = Fixture(self, memory=memory)
        f.old = f.service.issue(f.command())["grant"]
        if revoked:
            f.revoked = f.service.revoke(f.revoke_command(f.old))["terminal"]
        if changed_code:
            f.package["plan"]["executionBinding"]["executionCode"].update(coreCommit="d" * 40, coreTree="e" * 40)
            rebuild_workflow(f.package)
        f.approval = approval_for(f.package, decision_ref="test-replacement-approved")
        f.service.approval_reader = f.write_approval()
        f.readers.package = deepcopy(f.package)
        f.proof = {"mediaJobRef": "test-original-job", "attemptRef": "test-original-attempt",
            "jobDigest": c.digest("test-original-failed-job"), "dispatchResultDigest": c.digest("test-zero-send")}
        def read(workspace, run, job, grant, lease):
            lease.assert_held()
            c.require((workspace, run, job, grant) == (f.old["workspaceRef"], f.old["productionRunRef"],
                "test-original-job", f.old), "ATTEMPT_OR_LEASE_CHANGED")
            return deepcopy(f.proof)
        f.failure_reader = SimpleNamespace(read_zero_send_failure=read)
        f.service.failure_reader = f.failure_reader
        return f

    def command(self, f, key="test-replacement-issue"):
        return {**f.command(key), "predecessorJobRef": "test-original-job"}

    def test_v2_one_child_original_records_preserved_and_replay_has_no_send(self):
        f = self.fixture()
        before = deepcopy(f.records())
        command = self.command(f)
        result = f.service.issue_replacement(command)
        grant = result["grant"]
        self.assertEqual(grant["schemaVersion"], c.REPLACEMENT_GRANT_SCHEMA)
        self.assertEqual(grant, c.validate_grant(grant))
        self.assertEqual(grant["replacementOf"]["originalGrantDigest"], f.old["payloadDigest"])
        self.assertEqual(grant["replacementOf"]["revokedTerminalDigest"], f.revoked["payloadDigest"])
        self.assertEqual(grant["replacementOf"]["jobDigest"], f.proof["jobDigest"])
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(len(f.records()), 3)
        self.assertTrue(all(row in f.records() for row in before))
        replay = f.service.issue_replacement(command)
        self.assertTrue(replay["recordReplay"])
        self.assertEqual(replay["grant"], grant)
        self.assertEqual(replay["sendPermission"], "NONE")
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue_replacement(self.command(f, "different-key"))
        self.assertEqual(stopped.exception.code, "GRANT_SUBJECT_ALREADY_RECORDED")

    def test_no_revocation_no_reader_or_wrong_job_fails_closed(self):
        for fault in ("revocation", "reader", "job"):
            with self.subTest(fault=fault):
                f = self.fixture(revoked=fault != "revocation")
                before = deepcopy(f.records())
                command = self.command(f)
                if fault == "reader":
                    f.service.failure_reader = None
                if fault == "job":
                    command["predecessorJobRef"] = "not-the-original-job"
                with self.assertRaises(c.DispatchError) as stopped:
                    f.service.issue_replacement(command)
                self.assertEqual(stopped.exception.code, {"revocation": "APPROVAL_UNAVAILABLE",
                    "reader": "CURRENTNESS_FENCE_UNAVAILABLE", "job": "ATTEMPT_OR_LEASE_CHANGED"}[fault])
                self.assertEqual(f.records(), before)

    def test_consumed_even_without_socket_is_never_replaceable(self):
        f = self.fixture(revoked=False, changed_code=False)
        # Consumption fixture must use the original approval it records.
        approval = f.approval
        f.approval = f.old["approval"]
        f.repo.append_record(synthetic_consumption(f, f.old))
        f.approval = approval
        before = deepcopy(f.records())
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue_replacement(self.command(f))
        self.assertEqual(stopped.exception.code, "ALREADY_CONSUMED")
        self.assertEqual(f.records(), before)

    def test_normal_issue_cannot_bypass_old_slot_or_accept_internal_command(self):
        f = self.fixture()
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue(f.command("new-normal-key"))
        self.assertEqual(stopped.exception.code, "GRANT_SUBJECT_ALREADY_RECORDED")
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue(self.command(f))
        self.assertEqual(stopped.exception.code, "INVALID_CLOSED_SCHEMA")

    def test_scope_content_budget_runtime_and_model_changes_forbidden(self):
        f = self.fixture()
        for key in ("scope", "subject", "permissions", "limits", "executionBinding"):
            bad = deepcopy(f.package["plan"])
            if key == "scope":
                bad[key]["workspaceRef"] = "other-workspace"
            elif key == "subject":
                bad[key]["cameraInstruction"]["movement"] = "other-camera"
            elif key == "permissions":
                bad[key]["dispatchAllowed"] = False
            elif key == "limits":
                bad[key]["expiresAt"] = "2030-01-02T00:00:00.000000Z"
            else:
                bad[key]["runtimeBinding"]["processIdentityDigest"] = "f" * 64
            with self.subTest(key=key), self.assertRaises(c.DispatchError) as stopped:
                c.validate_replacement_plan(f.old, bad, f.approval)
            self.assertEqual(stopped.exception.code, "APPROVAL_PLAN_MISMATCH")
        for field in ("executionProfile", "costBasis", "executionConfigDigest"):
            bad = deepcopy(f.package["plan"])
            bad["executionBinding"][field] = "changed"
            with self.subTest(field=field), self.assertRaises(c.DispatchError):
                c.validate_replacement_plan(f.old, bad, f.approval)

    def test_replacement_of_replacement_and_same_approval_are_rejected(self):
        f = self.fixture()
        with self.assertRaises(c.DispatchError) as stopped:
            c.validate_replacement_plan(f.old, f.package["plan"], f.old["approval"])
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
        child = f.service.issue_replacement(self.command(f))["grant"]
        with self.assertRaises(c.DispatchError) as stopped:
            c.validate_replacement_plan(child, f.package["plan"], f.approval)
        self.assertEqual(stopped.exception.code, "GRANT_SUBJECT_ALREADY_RECORDED")

    def test_proof_changes_during_currentness_read_do_not_commit(self):
        f = self.fixture()
        f.readers.source_hook = lambda: f.proof.update(jobDigest=c.digest("changed"))
        before = deepcopy(f.records())
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue_replacement(self.command(f))
        self.assertEqual(stopped.exception.code, "ATTEMPT_OR_LEASE_CHANGED")
        self.assertEqual(f.records(), before)

    def test_revocation_original_removed_blocks_replacement(self):
        f = self.fixture()
        f.originals.decisions.pop(f.revocation["authorityDecisionRef"])
        with self.assertRaises(c.DispatchError) as stopped:
            f.service.issue_replacement(self.command(f))
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_two_competing_issue_calls_have_one_child_only(self):
        f = self.fixture()
        commands = [self.command(f, "competing-" + str(i)) for i in range(2)]
        barrier = Barrier(2)
        def issue(command):
            barrier.wait(timeout=10)
            try:
                return f.service.issue_replacement(command)["grant"]["generationDispatchGrantRef"]
            except c.DispatchError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(issue, commands))
        self.assertCountEqual(results, [c.replacement_grant_ref(f.package["plan"]), "GRANT_SUBJECT_ALREADY_RECORDED"])
        self.assertEqual(len(f.records()), 3)

    def test_sqlite_restart_preserves_child_and_revocation(self):
        f = self.fixture(memory=False)
        command = self.command(f)
        child = f.service.issue_replacement(command)["grant"]
        f.reopen()
        f.service.failure_reader = f.failure_reader
        self.assertEqual(f.service.issue_replacement(command)["grant"], child)
        self.assertEqual(f.service._terminal(f.old), f.revoked)
        self.assertEqual(len(f.records()), 3)

    def test_unknown_commit_is_not_zero_write_or_new_child(self):
        f = self.fixture(memory=False)
        command = self.command(f)
        with fault_at(f.repo, "after_commit"), self.assertRaises(c.CommitOutcomeUnknown):
            f.service.issue_replacement(command)
        self.assertEqual(len(f.records()), 3)
        self.assertEqual(f.service.issue_replacement(command)["sendPermission"], "NONE")
        self.assertEqual(len(f.records()), 3)
