"""Regression coverage for current-state evidence, not historical substring matches."""

from pathlib import Path
from hashlib import sha256
import json
import subprocess
import unittest
from unittest.mock import patch

from scripts import validate_current_state as current
from scripts import validate_document_supersession as projection


class CurrentStatePairTests(unittest.TestCase):
    def errors_for(self, text: str) -> list[str]:
        errors: list[str] = []
        current.require_pair(text, "NEXT_TASK", "D1_PREFLIGHT", Path("fixture.md"), errors)
        return errors

    def test_exact_record_is_valid(self):
        self.assertEqual([], self.errors_for("NEXT_TASK=D1_PREFLIGHT\n"))

    def test_historical_prefix_cannot_satisfy_current_field(self):
        self.assertTrue(self.errors_for("SUPERSEDED_VALIDATOR_NEXT_TASK=D1_PREFLIGHT\n"))

    def test_longer_value_cannot_satisfy_current_field(self):
        self.assertTrue(self.errors_for("NEXT_TASK=D1_PREFLIGHT_NOT_AUTHORIZED\n"))

    def test_inline_receipt_cannot_satisfy_current_field(self):
        self.assertTrue(self.errors_for("Old receipt: `NEXT_TASK=D1_PREFLIGHT`\n"))

    def test_conflicting_duplicate_is_rejected(self):
        self.assertTrue(self.errors_for("NEXT_TASK=D1_PREFLIGHT\nNEXT_TASK=OTHER\n"))

    def test_identical_duplicate_is_rejected(self):
        self.assertTrue(self.errors_for("NEXT_TASK=D1_PREFLIGHT\nNEXT_TASK=D1_PREFLIGHT\n"))


def valid_state(**overrides: str) -> str:
    fields = {
        **current.REQUIRED_CURRENT, **current.REQUIRED_CI_GOVERNANCE,
        "CURRENT_TASK": "ACS-D1", "NEXT_TASK": "D1_EXACT_RUN_REQUEST", **overrides,
    }
    body = "\n".join(f"{key}={value}" for key, value in fields.items())
    return f"{current.STATE_BEGIN}\n```text\n{body}\n```\n{current.STATE_END}\n"


class ActiveProjectionTests(unittest.TestCase):
    def errors_for(self, text: str) -> list[str]:
        errors: list[str] = []
        current.validate_current_projection(text, errors)
        return errors

    def test_future_next_action_is_not_pinned_to_rejected_wsl_task(self):
        self.assertEqual([], self.errors_for(valid_state(NEXT_TASK="D1_BOUNDED_NEXT_ACTION")))

    def test_history_outside_active_block_cannot_supply_missing_key(self):
        value = valid_state().replace("NEXT_TASK=D1_EXACT_RUN_REQUEST\n", "")
        self.assertTrue(self.errors_for(value + "NEXT_TASK=D1_EXACT_RUN_REQUEST\n"))

    def test_missing_or_multiple_blocks_are_rejected(self):
        for value in ("", valid_state() * 2, valid_state().replace(current.STATE_END, "")):
            with self.subTest(value=value):
                self.assertTrue(self.errors_for(value))

    def test_reversed_markers_are_rejected(self):
        self.assertTrue(self.errors_for(current.STATE_END + valid_state().replace(current.STATE_END, "")))

    def test_unsafe_execution_claims_fail_closed(self):
        for key in ("PUBLICATION_ALLOWED", "M13_EXTENSION_G0_AUTHORIZED", "A100_START_AUTHORIZED"):
            with self.subTest(key=key):
                self.assertTrue(self.errors_for(valid_state(**{key: "true"})))

    def test_historical_validator_alias_is_rejected(self):
        self.assertTrue(self.errors_for(valid_state(SUPERSEDED_VALIDATOR_NEXT_TASK="OLD")))

    def test_compound_inline_records_are_rejected(self):
        self.assertTrue(self.errors_for(valid_state(NEXT_TASK="D1; OTHER=UNSAFE")))

    def test_duplicate_non_required_field_is_rejected(self):
        value = valid_state(EXTRA="A").replace("EXTRA=A", "EXTRA=A\nEXTRA=B")
        self.assertTrue(self.errors_for(value))

    def test_worktree_current_block_is_consistent(self):
        text = current.CURRENT.read_text(encoding="utf-8")
        self.assertEqual([], self.errors_for(text))
        self.assertLessEqual(len(text.splitlines()), 200)
        self.assertLessEqual(max(map(len, text.splitlines())), 800)

    def test_frozen_baseline_keys_are_scope_qualified_exact_records(self):
        text = current.BASELINE.read_text(encoding="utf-8")
        errors: list[str] = []
        for key, value in current.REQUIRED_BASELINE_VALUES.items():
            current.require_pair(text, key, value, current.BASELINE, errors)
        self.assertEqual([], errors)
        self.assertIn("M13_FROZEN_CORE_MAIN", current.REQUIRED_BASELINE_VALUES)
        self.assertNotIn("CORE_MAIN", current.REQUIRED_BASELINE_VALUES)

    def test_readme_does_not_duplicate_global_next_task(self):
        text = Path("README.md").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?m)^NEXT_TASK=")
        self.assertIn("(CURRENT_MILESTONE.md)", text)


class ImmutableHistoryTests(unittest.TestCase):
    evidence = b"# History\n\n## 0A. Frozen\nOutcome: FAIL\n"

    def check(self, worktree: bytes, committed: bytes | None = None, filtered: bytes | None = None):
        errors: list[str] = []
        expected = sha256(current.history_section(self.evidence)).hexdigest()
        with patch.object(Path, "read_bytes", return_value=worktree), \
             patch.object(current, "EXPECTED_HISTORY_SHA256", expected), \
             patch.object(current.subprocess, "check_output", side_effect=[committed, filtered]) as git:
            current.validate_history(Path("fixture.md"), errors)
        return errors, git

    def test_exact_original_needs_no_git_fallback(self):
        errors, git = self.check(self.evidence)
        self.assertEqual([], errors)
        git.assert_not_called()

    def test_declared_git_checkout_eol_conversion_preserves_evidence(self):
        crlf = self.evidence.replace(b"\n", b"\r\n")
        errors, git = self.check(crlf, self.evidence, crlf)
        self.assertEqual([], errors)
        self.assertEqual([
            unittest.mock.call(["git", "cat-file", "blob", "HEAD:fixture.md"]),
            unittest.mock.call(["git", "cat-file", "--filters", "HEAD:fixture.md"]),
        ], git.call_args_list)

    def test_unapproved_eol_conversion_is_rejected(self):
        errors, _ = self.check(self.evidence.replace(b"\n", b"\r\n"), self.evidence, self.evidence)
        self.assertTrue(errors)

    def test_worktree_failure_rewritten_to_pass_is_rejected(self):
        errors, _ = self.check(self.evidence.replace(b"FAIL", b"PASS"), self.evidence, self.evidence)
        self.assertTrue(errors)

    def test_changed_committed_history_cannot_rebaseline_expected_digest(self):
        changed = self.evidence.replace(b"FAIL", b"PASS")
        errors, _ = self.check(changed, changed, changed)
        self.assertTrue(errors)

    def test_missing_history_marker_is_rejected(self):
        errors, _ = self.check(b"# History\n")
        self.assertTrue(errors)

    def test_unavailable_git_fails_closed(self):
        errors: list[str] = []
        with patch.object(Path, "read_bytes", return_value=self.evidence), \
             patch.object(current.subprocess, "check_output", side_effect=subprocess.CalledProcessError(1, "git")):
            current.validate_history(Path("fixture.md"), errors)
        self.assertTrue(errors)


class RegistryProjectionTests(unittest.TestCase):
    def records(self):
        return [
            {"path": "docs/z.md", "documentClass": "IMPLEMENTATION_EVIDENCE", "status": "RECORDED", "owner": "Owner"},
            {"path": "CURRENT_MILESTONE.md", "documentClass": "CURRENT_STATUS", "status": "CURRENT", "owner": "Lead"},
            {"path": "docs/a.md", "documentClass": "IMPLEMENTATION_EVIDENCE", "status": "RECORDED", "owner": "Owner"},
        ]

    def test_sorted_output_and_class_counts_come_from_registry(self):
        index, authority = projection.render_projections(self.records())
        self.assertLess(index.index("`docs/a.md`"), index.index("`docs/z.md`"))
        self.assertIn("| `IMPLEMENTATION_EVIDENCE` | 2 | no |", authority)
        self.assertIn("| `CURRENT_STATUS` | 1 | yes |", authority)
        for record in self.records():
            self.assertEqual(1, index.count(f"`{record['path']}`"))
            self.assertEqual(1, authority.count(f"`{record['path']}`"))

    def test_links_resolve_from_each_projection_location(self):
        index, authority = projection.render_projections(self.records())
        self.assertIn("(a.md)", index)
        self.assertIn("(../CURRENT_MILESTONE.md)", index)
        self.assertIn("(../../docs/a.md)", authority)

    def test_duplicate_and_unknown_records_fail_closed(self):
        cases = [self.records() * 2, [dict(self.records()[0], documentClass="UNKNOWN")]]
        for records in cases:
            with self.subTest(records=records), self.assertRaises(ValueError):
                projection.render_projections(records)

    def test_manual_count_or_missing_record_is_detected(self):
        index, authority = projection.render_projections(self.records())
        for generated, heading, edited in (
            (index, "## ACCEPTED_DECISION", index.replace("`docs/a.md`", "`docs/old.md`")),
            (authority, "## Classification totals", authority.replace("| 2 | no |", "| 99 | no |")),
        ):
            self.assertIsNotNone(projection.check_projection(edited, heading, generated, Path("fixture.md")))

    def test_missing_or_duplicate_marker_is_not_silently_rewritten(self):
        for text in ("# Missing", "## Classification totals\n## Classification totals\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                projection.replace_projection(text, "## Classification totals", "generated\n")

    def test_regeneration_is_idempotent_and_preserves_preamble(self):
        _, generated = projection.render_projections(self.records())
        text = "# Human context\n\n" + generated
        self.assertEqual(text, projection.replace_projection(text, "## Classification totals", generated))

    def test_real_registry_and_both_projections_are_in_sync(self):
        records = json.loads(projection.REGISTRY.read_text(encoding="utf-8"))["documents"]
        generated = projection.render_projections(records)
        for path, heading, body in (
            (projection.INDEX, "## ACCEPTED_DECISION", generated[0]),
            (projection.AUTHORITY_MAP, "## Classification totals", generated[1]),
        ):
            self.assertIsNone(projection.check_projection(path.read_text(encoding="utf-8"), heading, body, path))


if __name__ == "__main__":
    unittest.main()
