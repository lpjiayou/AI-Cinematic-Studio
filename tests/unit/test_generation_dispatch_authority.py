"""Independent safe readers and original-approval trust, with temporary files."""
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import generation_dispatch_authority as a
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_fixtures import Fixture


class GenerationDispatchAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.x = Fixture(self, memory=True)

    def test_fresh_reads_original_identity_and_independent_pin(self):
        x = self.x
        first = x.approval_reader.resolve(x.approval["authorityDecisionRef"])
        second = x.approval_reader.resolve(x.approval["authorityDecisionRef"])
        self.assertEqual(len(x.originals.calls), 2)
        first.approval["actorRef"] = "tampered"
        self.assertEqual(second.approval, x.approval)
        x.approval_path.write_bytes(x.approval_path.read_bytes() + b" ")
        with self.assertRaises(c.DispatchError): x.approval_reader.resolve(x.approval["authorityDecisionRef"])

    def test_absent_partial_relative_and_no_implicit_environment(self):
        x = self.x
        with patch.dict(os.environ, dict(zip(a.APPROVAL_CONFIG_NAMES, (str(x.approval_path), x.approval_pin)))):
            rejecting = a.approval_reader_from_config({})
            with self.assertRaises(c.DispatchError): rejecting.resolve(x.approval["authorityDecisionRef"])
        for name in a.APPROVAL_CONFIG_NAMES:
            with self.assertRaises(c.DispatchError): a.approval_reader_from_config({name: "test"})
        for path in ("relative.json", str(x.root / ".." / x.root.name / "test-approval.json")):
            with self.assertRaises(c.DispatchError): a.PinnedApprovalReader(path, x.approval_pin)

    def test_symlink_parent_regular_size_and_missing_files(self):
        x = self.x
        link = x.root / "link.json"
        link.symlink_to(x.approval_path)
        parent_link = x.root / "linked-parent"
        parent_link.symlink_to(x.root, target_is_directory=True)
        empty = x.root / "empty.json"
        empty.write_bytes(b"")
        large = x.root / "large.json"
        large.write_bytes(b"x" * (c.MAX_JSON_BYTES + 1))
        for path in (link, parent_link / x.approval_path.name, x.root, empty, large, x.root / "missing.json"):
            with self.subTest(path=path.name), self.assertRaises(c.DispatchError):
                a.PinnedApprovalReader(path, x.approval_pin, original=x.originals).resolve(x.approval["authorityDecisionRef"])

    def test_duplicate_decisions_unknown_fields_and_invalid_json(self):
        x = self.x
        bad = deepcopy(x.bundle)
        bad["approvals"].append(deepcopy(bad["approvals"][0]))
        for data in (c.canonical(bad), b'{"schemaVersion":1,"schemaVersion":2}', b'{"v":"\xff"}', b'{"v":NaN}'):
            x.approval_path.write_bytes(data)
            with self.assertRaises(c.DispatchError):
                a.PinnedApprovalReader(x.approval_path, sha256(data).hexdigest(), original=x.originals).resolve(x.approval["authorityDecisionRef"])

    def test_configured_authority_or_self_signed_actor_is_not_original_approval(self):
        x = self.x
        with self.assertRaises(c.DispatchError):
            a.PinnedApprovalReader(x.approval_path, x.approval_pin).resolve(x.approval["authorityDecisionRef"])
        forged = deepcopy(x.bundle)
        forged["approvals"][0]["approval"]["actorRef"] = "test-self-asserted-lead"
        forged["approvals"][0]["approval"] = c.sealed(forged["approvals"][0]["approval"], "authorityDecisionDigest")
        data = c.canonical(forged)
        x.approval_path.write_bytes(data)
        with self.assertRaises(c.DispatchError):
            a.PinnedApprovalReader(x.approval_path, sha256(data).hexdigest(), original=x.originals).resolve(x.approval["authorityDecisionRef"])

    def test_historical_permission_kinds_cannot_replace_exact_generation(self):
        x = self.x
        for kind in ("ADR_ACCEPTED", "IMPLEMENTATION_APPROVED", "HUMAN_SELECTION", "TECHNICAL_INPUT_INTAKE", "OLD_BUDGET"):
            bad = deepcopy(x.bundle)
            approval = bad["approvals"][0]["approval"]
            approval["approvalKind"] = kind
            bad["approvals"][0]["approval"] = c.sealed(approval, "authorityDecisionDigest")
            data = c.canonical(bad)
            x.approval_path.write_bytes(data)
            with self.subTest(kind=kind), self.assertRaises(c.DispatchError):
                a.PinnedApprovalReader(x.approval_path, sha256(data).hexdigest(), original=x.originals).resolve(x.approval["authorityDecisionRef"])

    def test_atomic_file_replacement_during_read_is_rejected(self):
        x = self.x
        original = os.read
        changed = False
        replacement = x.root / "replacement.json"
        replacement.write_bytes(x.approval_path.read_bytes())
        def read(fd, size):
            nonlocal changed
            data = original(fd, size)
            if not changed:
                changed = True
                os.replace(replacement, x.approval_path)
            return data
        with patch.object(a.os, "read", side_effect=read), self.assertRaises(c.DispatchError):
            x.approval_reader.resolve(x.approval["authorityDecisionRef"])

    def test_in_place_file_change_during_read_is_rejected(self):
        x = self.x
        original = os.read
        changed = False
        def read(fd, size):
            nonlocal changed
            data = original(fd, size)
            if not changed:
                changed = True
                x.approval_path.write_bytes(x.approval_path.read_bytes() + b" ")
            return data
        with patch.object(a.os, "read", side_effect=read), self.assertRaises(c.DispatchError):
            x.approval_reader.resolve(x.approval["authorityDecisionRef"])

    def test_revocation_bundle_pin_and_kind_are_independent(self):
        x = self.x
        grant = x.public.issue(x.command())["grant"]
        command = x.revoke_command(grant)
        chosen = x.revocation_reader.resolve(command["authorityDecisionRef"])
        self.assertIsNone(chosen.plan_package)
        self.assertNotEqual(chosen.bundle_sha256, x.approval_pin)
        with self.assertRaises(c.DispatchError):
            a.PinnedApprovalReader(x.approval_path, x.approval_pin, original=x.originals, revocation=True).resolve(command["authorityDecisionRef"])


if __name__ == "__main__":
    unittest.main()
