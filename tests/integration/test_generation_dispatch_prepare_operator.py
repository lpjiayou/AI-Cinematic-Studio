"""Actual D1 PREPARE before approval, using only isolated synthetic originals."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import unittest
from unittest.mock import patch

from apps.creator_workspace_mvp.generation_dispatch_operator import execute_command
from services.v4_platform.generation_dispatch_a14b_live import LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS
from services.v4_platform.generation_dispatch_live_result import encoder_tool_identity
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_operator import GenerationDispatchOperator
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_execution_fixture
from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime


class PrepareOperatorTests(unittest.TestCase):
    def fixture(self):
        # No listener: successful PREPARE must never contact even this endpoint.
        tools = encoder_tool_identity()
        return make_a14b_execution_fixture(self, "http://127.0.0.1:9/",
            profile_factory=lambda source: live_profile(source, tools), runtime_factory=live_runtime,
            adapter_identity=LIVE_ADAPTER_IDENTITY, adapter_capability=LIVE_CAPABILITY,
            endpoint_class=LIVE_ENDPOINT_CLASS, use_operator=True, prepare_only=True)

    def store_hashes(self, f):
        return {str(path.relative_to(f.root)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(f.root.glob("*.sqlite3"))}

    def selected_operator(self, f, prepared):
        return GenerationDispatchOperator(assembly=f.dispatch, coordinator=f.coordinators[0],
            clock=f.clock, worker_context=f.worker_context, endpoint="http://127.0.0.1:9/",
            selection=replace(f.operator._selection, approved_plan_digest=prepared["approvedPlanDigest"],
                authority_decision_ref="test-decision", issue_idempotency_key="test-issue", route_idempotency_key="test-route"))

    def test_first_prepare_through_original_operator_without_prior_approval_or_writes(self):
        f = self.fixture()
        before = self.store_hashes(f)
        self.assertFalse((f.root / "test-generation-approval.json").exists())
        self.assertEqual(f.jobs(), [])
        with patch("socket.socket", side_effect=AssertionError("no network allowed")):
            prepared = execute_command(f.operator, "prepare")
            self.assertIn("planPackage", prepared, prepared)
            c.validate_plan_package(prepared["planPackage"])
            self.assertEqual(prepared["operation"], "PREPARE_ONLY")
            self.assertEqual(prepared["sendPermission"], "NONE")
            self.assertEqual(prepared["approvedPlanDigest"], c.digest(prepared["planPackage"]["plan"]))
            selectors = prepared["currentSubjectReadSet"]["selectors"]
            self.assertEqual(len(selectors), 15)
            self.assertNotIn("CURRENT_OWNER_APPROVAL", {s["selectorKind"] for s in selectors})
            self.assertIsNone(f.operator._selection.approved_plan_digest)
            for operation, ref in (("issue-approved", None), ("inspect", "test-grant"),
                    ("route-approved", "test-grant"), ("execute-one", "test-job"), ("recover", "test-job")):
                with self.subTest(operation=operation), self.assertRaises(c.DispatchError) as stopped:
                    execute_command(f.operator, operation, ref)
                self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
            # Even a syntactically full host selection cannot replace an
            # independent approval reader with the digest PREPARE produced.
            with self.assertRaises(c.DispatchError) as stopped:
                self.selected_operator(f, prepared).issue()
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
            self.assertEqual(execute_command(f.operator, "prepare"), prepared)
        self.assertEqual(f.jobs(), [])
        self.assertEqual(self.store_hashes(f), before)
        self.assertFalse((f.root / "test-generation-approval.json").exists())
        self.assertNotIn("grant", prepared)

    def test_prepare_candidate_stays_blocked_when_required_original_is_missing(self):
        f = self.fixture()
        original = f.root / "test-d1-prerequisite-identityReferenceEvaluation.json"
        original.unlink()  # Only this fixture-owned temporary input.
        before = self.store_hashes(f)
        with patch("socket.socket", side_effect=AssertionError("no network allowed")):
            result = execute_command(f.operator, "prepare")
        self.assertEqual(result["code"], "APPROVAL_UNAVAILABLE", result)
        self.assertEqual(result["writesCommitted"], 0)
        self.assertEqual(result["sendPermission"], "NONE")
        self.assertEqual(f.jobs(), [])
        self.assertEqual(self.store_hashes(f), before)

    def test_issue_rechecks_exact_prepared_plan_without_replacing_owner_approval(self):
        f = self.fixture()
        prepared = execute_command(f.operator, "prepare")
        self.assertIn("planPackage", prepared, prepared)
        f.approve_package(prepared["planPackage"])
        operator = self.selected_operator(f, prepared)
        operator._selection = replace(operator._selection, authority_decision_ref=f.approval["authorityDecisionRef"])
        before = self.store_hashes(f)
        # Reaching this guard proves a real independent fixture approval was
        # resolved; the newly computed plan cannot silently replace its input.
        changed = deepcopy(prepared)
        changed["planPackage"]["plan"]["limits"]["maxCostMinor"] += 1
        with patch.object(operator, "prepare", return_value=changed), \
                patch("socket.socket", side_effect=AssertionError("no network allowed")):
            with self.assertRaises(c.DispatchError) as stopped:
                operator.issue()
        self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")
        self.assertEqual(self.store_hashes(f), before)
        self.assertEqual(f.jobs(), [])
