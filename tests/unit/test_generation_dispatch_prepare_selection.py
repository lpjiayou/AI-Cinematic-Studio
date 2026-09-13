"""Pre-approval bootstrap is read-only; approved actions stay fail-closed."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_live_sources import (
    OriginalFile, PinnedOwnerOriginal, PinnedPrerequisiteOriginals)
from services.v5_core_os.episode_production.generation_dispatch_operator import (
    ExistingStoreOperatorDeployment, GenerationDispatchOperator, OperatorSelection)
from services.v5_core_os.episode_production.generation_dispatch_readers import VerifiedOriginalObservation
from tests.support.generation_dispatch_fixtures import make_package


def prepare_command():
    package, _ = make_package()
    plan = package["plan"]
    subject = plan["subject"]
    return {"workspaceRef": plan["scope"]["workspaceRef"],
        "productionRunRef": plan["scope"]["productionRunRef"],
        "methodAwareInputPlanVersionRef": subject["methodAwareInputPlanVersion"]["ref"],
        "creativeShotVersionRef": subject["creativeShotVersion"]["ref"],
        "beatRef": subject["actionExecutionBeat"]["ref"],
        "inputAssetVersionRef": subject["inputAsset"]["assetVersionRef"],
        "backendRef": plan["executionBinding"]["backendDecision"]["backendRef"],
        "executionConfigRef": package["materials"]["executionConfig"]["configRef"],
        "costBasisRef": package["materials"]["costBasis"]["costBasisRef"], "limits": plan["limits"]}


class PrepareSelectionTests(unittest.TestCase):
    def test_unapproved_selection_and_host_construction_need_no_io_or_placeholder(self):
        selection = OperatorSelection(prepare_command())
        with patch("sqlite3.connect", side_effect=AssertionError("DB forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch.object(OriginalFile, "read", side_effect=AssertionError("file read forbidden")):
            selection.validate()
            ExistingStoreOperatorDeployment(selection=selection)
        self.assertIsNone(selection.approved_plan_digest)
        self.assertIsNone(selection.authority_decision_ref)

    def test_partial_approval_selection_never_falls_back_to_prepare(self):
        values = ("a" * 64, "test-decision", "test-issue", "test-route")
        for present in product((False, True), repeat=4):
            if all(present) or not any(present):
                continue
            with self.subTest(present=present), self.assertRaises(c.DispatchError) as stopped:
                OperatorSelection(prepare_command(), *(v if p else None for p, v in zip(present, values))).validate()
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_invalid_complete_selection_and_prepare_command_remain_rejected(self):
        valid = OperatorSelection(prepare_command(), "a" * 64, "test-decision", "test-issue", "test-route")
        valid.validate()
        for field in ("approved_plan_digest", "authority_decision_ref", "issue_idempotency_key", "route_idempotency_key"):
            with self.subTest(field=field), self.assertRaises(c.DispatchError) as stopped:
                replace(valid, **{field: ""}).validate()
            self.assertEqual(stopped.exception.code, "INVALID_CLOSED_SCHEMA")
        command = prepare_command()
        command["actorRole"] = "PROJECT_LEAD"
        with self.assertRaises(c.DispatchError) as stopped:
            OperatorSelection(command, None, None, None, None).validate()
        self.assertEqual(stopped.exception.code, "INVALID_CLOSED_SCHEMA")

    def test_unapproved_operator_rejects_every_non_prepare_action_before_participants(self):
        assembly, coordinator = Mock(), Mock()
        operator = GenerationDispatchOperator(assembly=assembly, coordinator=coordinator,
            clock=None, worker_context=None, endpoint=None,
            selection=OperatorSelection(prepare_command(), None, None, None, None))
        for action, args in (("issue", ()), ("inspect", ("test-grant",)),
                ("route", ("test-grant",)), ("execute_one", ("test-job",)), ("recover", ("test-job",))):
            with self.subTest(action=action), self.assertRaises(c.DispatchError) as stopped:
                getattr(operator, action)(*args)
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
        self.assertEqual(assembly.mock_calls, [])
        self.assertEqual(coordinator.mock_calls, [])


class PreparePrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.originals, self.verifiers = {}, {}
        for kind, (owner, _) in PinnedPrerequisiteOriginals._owners.items():
            value = {"TEST_ONLY": True, "kind": kind}
            self.originals[kind] = self.original(kind + ".json", value)
            self.verifiers[kind] = lambda value, resolved, lease, owner=owner, kind=kind: (
                VerifiedOriginalObservation(owner, kind, "test-" + kind, value))
        self.lease = SimpleNamespace(assert_held=Mock())
        self.resolved = SimpleNamespace(scope={})

    def original(self, name, value):
        raw = c.canonical(value)
        path = self.root / name
        path.write_bytes(raw)
        return OriginalFile(path, sha256(raw).hexdigest())

    def reader(self, **kwargs):
        return PinnedPrerequisiteOriginals(originals=self.originals, verifiers=self.verifiers,
            approval_original=kwargs.get("approval_original"), approval_evidence=kwargs.get("approval_evidence"))

    def test_prepare_reads_five_originals_without_owner_approval(self):
        with patch.object(OriginalFile, "read", side_effect=AssertionError("constructor I/O")):
            reader = self.reader()
        pins = reader.prepare(self.resolved, {}, self.lease)
        self.assertEqual(set(pins), set(c.PREREQUISITES))
        result = reader.read_current(self.resolved, {"materials": {"prerequisiteEvidence": pins}},
            None, "PREPARE", self.lease)
        self.assertEqual(len(result.originals), 5)
        self.assertNotIn("CURRENT_OWNER_APPROVAL", result.selectors)

    def test_other_phases_require_approval_originals_before_reading_prerequisites(self):
        reader = self.reader()
        for phase in ("ISSUE", "CONSUME", "SEND"):
            with self.subTest(phase=phase), patch.object(OriginalFile, "read",
                    side_effect=AssertionError("must fail before source I/O")), self.assertRaises(c.DispatchError) as stopped:
                reader.read_current(self.resolved, {}, {}, phase, self.lease)
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_partial_approval_original_pair_is_rejected(self):
        evidence = self.original("approval-evidence.json", {"TEST_ONLY": True})
        approval = PinnedOwnerOriginal(binding=evidence, authority_ref="test-owner", actor_ref="test-actor",
            evidence=evidence, verifier=lambda original, proof: original)
        for original, proof in ((approval, None), (None, evidence), (True, evidence)):
            with self.subTest(original=original, proof=proof), self.assertRaises(c.DispatchError) as stopped:
                self.reader(approval_original=original, approval_evidence=proof)
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_complete_independent_approval_originals_still_verify_at_every_later_gate(self):
        from tests.support.generation_dispatch_fixtures import approval_for
        package, _ = make_package()
        approval = approval_for(package)
        evidence = {"TEST_ONLY": True, "decision": "EXACT_SUBJECT_GENERATION_EXECUTION"}
        approval["approvalEvidenceDigest"] = c.digest(evidence)
        approval = c.sealed(approval, "authorityDecisionDigest")
        binding = self.original("approval.json", approval)
        proof = self.original("approval-evidence.json", evidence)
        verifier = Mock(side_effect=lambda original, evidence: original)
        original = PinnedOwnerOriginal(binding=binding, authority_ref=approval["authorityRef"],
            actor_ref=approval["actorRef"], evidence=proof, verifier=verifier)
        reader = self.reader(approval_original=original, approval_evidence=proof)
        package["materials"]["prerequisiteEvidence"] = reader.prepare(self.resolved, {}, self.lease)
        for phase in ("ISSUE", "CONSUME", "SEND"):
            with self.subTest(phase=phase):
                contribution = reader.read_current(self.resolved, package, approval, phase, self.lease)
                self.assertEqual(len(contribution.originals), 7)
                self.assertEqual(contribution.selectors["CURRENT_OWNER_APPROVAL"],
                    (approval["authorityDecisionRef"], approval["authorityDecisionDigest"]))
        self.assertEqual(verifier.call_count, 3)
        proof.path.write_bytes(b'{}')
        with self.assertRaises(c.DispatchError) as stopped:
            reader.read_current(self.resolved, package, approval, "SEND", self.lease)
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")

    def test_prepare_keeps_missing_and_changed_prerequisites_fail_closed(self):
        for kind in c.PREREQUISITES:
            with self.subTest(kind=kind), self.assertRaises(c.DispatchError) as stopped:
                PinnedPrerequisiteOriginals(originals={k: v for k, v in self.originals.items() if k != kind},
                    verifiers=self.verifiers, approval_original=None, approval_evidence=None)
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
        reader = self.reader()
        pins = reader.prepare(self.resolved, {}, self.lease)
        stale = deepcopy(pins)
        stale["scriptOwnerAcceptance"]["digest"] = "f" * 64
        with self.assertRaises(c.DispatchError) as stopped:
            reader.read_current(self.resolved, {"materials": {"prerequisiteEvidence": stale}}, None, "PREPARE", self.lease)
        self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")
        self.originals["costReview"].path.write_bytes(b'{}')
        with self.assertRaises(c.DispatchError) as stopped:
            reader.prepare(self.resolved, {}, self.lease)
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
