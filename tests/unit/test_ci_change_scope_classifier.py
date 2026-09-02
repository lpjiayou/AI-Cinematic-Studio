"""Closed-fixture tests for the required-check CI scope classifier."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

from scripts.classify_ci_change_scope import (
    ChangedFile,
    DOCS_ONLY,
    FULL_SUITE,
    classify_records,
    classify_repository_change,
    payload_digest,
    verify_payload,
)


BASE = "1" * 40
HEAD = "2" * 40


def changed(
    path: str,
    *,
    status: str = "M",
    old_path: str | None = None,
    old_mode: str = "100644",
    new_mode: str = "100644",
) -> ChangedFile:
    if status.startswith("A"):
        return ChangedFile(status, None, path, "000000", new_mode)
    if status.startswith("D"):
        return ChangedFile(status, path, None, old_mode, "000000")
    if status.startswith(("R", "C")):
        if old_path is None:
            raise ValueError("rename/copy fixture requires old_path")
        return ChangedFile(status, old_path, path, old_mode, new_mode)
    return ChangedFile(status, path, path, old_mode, new_mode)


def classify(*records: ChangedFile, event: str = "pull_request"):
    return classify_records(event, BASE, HEAD, list(records))


class ChangeScopeClassifierTests(unittest.TestCase):
    def assert_scope(self, expected: str, *records: ChangedFile) -> dict[str, object]:
        outcome = classify(*records)
        self.assertFalse(outcome.failed)
        self.assertEqual(expected, outcome.payload["classification"])
        verify_payload(outcome.payload)
        return outcome.payload

    def test_current_milestone_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed("CURRENT_MILESTONE.md"))

    def test_docs_markdown_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed("docs/governance/policy.md"))

    def test_document_registry_json_is_docs_only(self) -> None:
        self.assert_scope(
            DOCS_ONLY,
            changed("docs/governance/DOCUMENT_REGISTRY.json"),
        )

    def test_deleted_historical_document_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed("docs/archive/old.md", status="D"))

    def test_service_source_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("services/api.py"))

    def test_test_source_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("tests/unit/test_example.py"))

    def test_experiment_markdown_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("experiments/report.md"))

    def test_workflow_is_full_suite(self) -> None:
        self.assert_scope(
            FULL_SUITE,
            changed(".github/workflows/repository-validation.yml"),
        )

    def test_classifier_itself_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("scripts/classify_ci_change_scope.py"))

    def test_mixed_docs_and_service_is_full_suite(self) -> None:
        payload = self.assert_scope(
            FULL_SUITE,
            changed("docs/status/state.md"),
            changed("services/api.py"),
        )
        self.assertEqual("MIXED_CHANGE_FULL_SUITE", payload["classificationReason"])

    def test_unknown_file_is_full_suite(self) -> None:
        payload = self.assert_scope(FULL_SUITE, changed("misc/unknown.bin"))
        self.assertTrue(payload["unknownMatches"])

    def test_empty_diff_is_full_suite(self) -> None:
        payload = self.assert_scope(FULL_SUITE)
        self.assertEqual("EMPTY_DIFF_FULL_SUITE", payload["classificationReason"])

    def test_docs_rename_to_service_is_full_suite(self) -> None:
        self.assert_scope(
            FULL_SUITE,
            changed("services/policy.md", status="R100", old_path="docs/policy.md"),
        )

    def test_service_rename_to_docs_is_full_suite(self) -> None:
        self.assert_scope(
            FULL_SUITE,
            changed("docs/policy.md", status="R100", old_path="services/policy.py"),
        )

    def test_symlink_mode_is_full_suite(self) -> None:
        payload = self.assert_scope(
            FULL_SUITE,
            changed("docs/link.md", old_mode="100644", new_mode="120000"),
        )
        self.assertEqual("MIXED_CHANGE_FULL_SUITE", payload["classificationReason"])

    def test_workflow_dispatch_is_always_full_suite(self) -> None:
        outcome = classify(changed("docs/policy.md"), event="workflow_dispatch")
        self.assertFalse(outcome.failed)
        self.assertEqual(FULL_SUITE, outcome.payload["classification"])
        self.assertEqual(
            "WORKFLOW_DISPATCH_ALWAYS_FULL_SUITE",
            outcome.payload["classificationReason"],
        )

    def test_missing_base_sha_fails_closed(self) -> None:
        outcome = classify_repository_change(
            repo_root=Path.cwd(),
            event_name="pull_request",
            base_sha="",
            head_sha=HEAD,
        )
        self.assertTrue(outcome.failed)
        self.assertEqual(FULL_SUITE, outcome.payload["classification"])

    def test_git_diff_failure_fails_closed(self) -> None:
        def failing_reader(_: Path, __: str, ___: str) -> list[ChangedFile]:
            raise subprocess.CalledProcessError(128, ["git", "diff"])

        outcome = classify_repository_change(
            repo_root=Path.cwd(),
            event_name="pull_request",
            base_sha=BASE,
            head_sha=HEAD,
            diff_reader=failing_reader,
        )
        self.assertTrue(outcome.failed)
        self.assertEqual("GIT_DIFF_FAILED_FAIL_CLOSED", outcome.payload["classificationReason"])

    def test_payload_digest_is_stable(self) -> None:
        first = classify(changed("docs/b.md"), changed("docs/a.md")).payload
        second = classify(changed("docs/a.md"), changed("docs/b.md")).payload
        self.assertEqual(first["payloadDigest"], second["payloadDigest"])
        self.assertEqual(first["payloadDigest"], payload_digest(first))

    def test_repeated_classification_is_identical(self) -> None:
        records = [changed("docs/policy.md"), changed("README.md")]
        first = classify_records("pull_request", BASE, HEAD, records).payload
        second = classify_records("pull_request", BASE, HEAD, records).payload
        self.assertEqual(first, second)

    def test_github_document_template_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed(".github/PULL_REQUEST_TEMPLATE.md"))

    def test_lowercase_existing_pr_template_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed(".github/pull_request_template.md"))

    def test_allowed_architecture_yaml_is_docs_only(self) -> None:
        self.assert_scope(DOCS_ONLY, changed("architecture/interfaces.yml"))

    def test_dependency_file_inside_docs_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("docs/requirements.txt"))

    def test_unapproved_document_suffix_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("docs/diagram.svg"))

    def test_type_change_status_is_full_suite(self) -> None:
        self.assert_scope(FULL_SUITE, changed("docs/policy.md", status="T"))

    def test_unsupported_event_fails_closed(self) -> None:
        outcome = classify(changed("docs/policy.md"), event="push")
        self.assertTrue(outcome.failed)
        self.assertEqual(FULL_SUITE, outcome.payload["classification"])


if __name__ == "__main__":
    unittest.main()
