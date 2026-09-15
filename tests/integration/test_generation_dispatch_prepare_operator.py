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


class HostInputBindingTests(unittest.TestCase):
    """New wiring uses the unchanged real entrypoint and original temporary stores."""
    fixture = PrepareOperatorTests.fixture
    store_hashes = PrepareOperatorTests.store_hashes

    def host(self, f):
        from services.v5_core_os.episode_production.generation_dispatch_host import D1OperatorHost
        from services.v5_core_os.episode_production.generation_dispatch_live_sources import OriginalFile, PinnedCostOriginal
        args = dict(f.deployment._dependencies)
        materials = args.pop("material_reader")
        prerequisites = args.pop("prerequisite_reader")
        approval = args.pop("approval_reader")
        selection = args.pop("selection")
        for key in ("backend_reader", "runtime_reader", "cost_reader"):
            args.pop(key)
        # This is the historical PREPARE-only fixture, not an installed new-input
        # host. The optional port must never be smuggled through store bindings.
        self.assertIsNone(args.pop("image_video_installation"))
        cost = f.external.template["materials"]["costBasis"]
        raw = c.canonical(cost)
        path = f.root / "test-host-cost-basis.json"
        path.write_bytes(raw)
        proof_pins = [*cost["sourceEvidence"], cost["billingResponsibility"]["continuingChargesEvidence"]]
        proofs = {pin["ref"]: OriginalFile(f.external.proof_files[pin["ref"]]["path"],
            f.external.proof_files[pin["ref"]]["sha256"]) for pin in proof_pins}
        cost_reader = PinnedCostOriginal(basis=OriginalFile(path, sha256(raw).hexdigest()), proofs=proofs,
            verifier=lambda value, originals, package, lease: f.external.cost(package, lease))
        f.operator_context.__exit__(None, None, None)
        return D1OperatorHost(configuration=materials._configuration,
            input_image=OriginalFile(f.external.input_path, sha256(f.external.input_path.read_bytes()).hexdigest()),
            selection=selection, runtime_original=materials._runtime_file,
            runtime_current=materials._runtime_current, cost_owner=cost_reader,
            prerequisite_originals=prerequisites._originals, prerequisite_verifiers=prerequisites._verifiers,
            approval_reader=approval, store_arguments=args)

    def test_host_bound_main_prepare_reads_pinned_inputs_and_complete_cost_without_writes(self):
        from apps.creator_workspace_mvp.generation_dispatch_operator import main
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        f = self.fixture()
        host = self.host(f)
        before = self.store_hashes(f)
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            offline = host.check_inputs()
            self.assertEqual(offline["missingBindings"], [])
            self.assertFalse(offline["liveCurrentnessChecked"])
            self.assertFalse(offline["operatorPrepareCompleted"])
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["prepare"], host=host), 0)
            result = json.loads(out.getvalue())
            self.assertIn("planPackage", result, result)
            c.validate_plan_package(result["planPackage"])
            self.assertEqual(result["sendPermission"], "NONE")
            self.assertEqual(len(result["currentSubjectReadSet"]["selectors"]), 15)
            self.assertEqual(result["planPackage"]["materials"]["costBasis"], f.external.template["materials"]["costBasis"])
        self.assertEqual(self.store_hashes(f), before)
        self.assertFalse((f.root / "test-generation-approval.json").exists())

    def test_host_rejects_local_anchor_change_before_opening_stores(self):
        f = self.fixture()
        host = self.host(f)
        host.input_image.path.write_bytes(b"changed fixture input")
        with patch("sqlite3.connect", side_effect=AssertionError("must not open stores")), \
                patch("socket.socket", side_effect=AssertionError("must not contact runtime")):
            with self.assertRaises(c.DispatchError) as stopped:
                host.deployment()
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_host_missing_verifier_is_named_offline_and_never_becomes_permission(self):
        f = self.fixture()
        host = self.host(f)
        host.verifiers.pop("rightsEvaluation")
        with patch("sqlite3.connect", side_effect=AssertionError("stores forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")):
            result = host.check_inputs()
            self.assertIn("prerequisite_verifier:rightsEvaluation", result["missingBindings"])
            self.assertEqual(result["sendPermission"], "NONE")
            with self.assertRaises(c.DispatchError) as stopped:
                host.deployment()
        self.assertEqual(stopped.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")

    def test_host_rejects_protected_ports_in_store_arguments_before_opening_stores(self):
        f = self.fixture()
        host = self.host(f)
        before = self.store_hashes(f)
        stores = dict(host.store_arguments)
        for key in ("selection", "approval_reader", "prerequisite_reader", "material_reader",
                    "backend_reader", "runtime_reader", "cost_reader", "image_video_installation"):
            host.store_arguments = {**stores, key: None}
            with self.subTest(key=key), \
                    patch("sqlite3.connect", side_effect=AssertionError("must not open stores")), \
                    patch("socket.socket", side_effect=AssertionError("must not contact runtime")):
                with self.assertRaises(c.DispatchError) as stopped:
                    host.deployment()
                self.assertEqual(stopped.exception.code, "CONFIG_CHANGED")
        self.assertEqual(self.store_hashes(f), before)
