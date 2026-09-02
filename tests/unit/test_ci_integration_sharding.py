"""Coverage invariants for the Integration Tests CI shard plan."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from scripts.run_ci_fast_path import (
    ALLOWED_INTEGRATION_SKIPS,
    INTEGRATION_SHARDS,
    audit_integration_shard_files,
    discover_integration_files,
    discovered_integration_files,
    integration_test_counts,
)


def iter_tests(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from iter_tests(test)
        else:
            yield test


class IntegrationShardingTests(unittest.TestCase):
    def test_four_shards_cover_every_integration_file_exactly_once(self) -> None:
        audit = audit_integration_shard_files()
        self.assertEqual(4, len(INTEGRATION_SHARDS))
        self.assertEqual(48, len(audit["discovered"]))
        self.assertEqual((), audit["missing"])
        self.assertEqual((), audit["extra"])
        self.assertEqual(0, audit["duplicateCount"])
        self.assertEqual(len(audit["discovered"]), len(audit["assigned"]))

    def test_sharded_test_count_matches_complete_discovery(self) -> None:
        full_count, shard_counts = integration_test_counts()
        self.assertEqual(297, full_count)
        self.assertEqual(297, sum(shard_counts.values()))
        self.assertEqual(
            {"shard-1": 2, "shard-2": 91, "shard-3": 82, "shard-4": 122},
            shard_counts,
        )

    def test_duplicate_assignment_is_detected(self) -> None:
        shards = dict(INTEGRATION_SHARDS)
        duplicate = INTEGRATION_SHARDS["shard-1"][0]
        shards["shard-2"] = shards["shard-2"] + (duplicate,)
        audit = audit_integration_shard_files(shards=shards)
        self.assertEqual(1, audit["duplicateCount"])

    def test_missing_assignment_is_detected(self) -> None:
        shards = dict(INTEGRATION_SHARDS)
        missing = shards["shard-4"][-1]
        shards["shard-4"] = shards["shard-4"][:-1]
        audit = audit_integration_shard_files(shards=shards)
        self.assertEqual((missing,), audit["missing"])

    def test_extra_assignment_is_detected(self) -> None:
        shards = dict(INTEGRATION_SHARDS)
        extra = "tests/integration/test_not_in_repository.py"
        shards["shard-4"] = shards["shard-4"] + (extra,)
        audit = audit_integration_shard_files(shards=shards)
        self.assertEqual((extra,), audit["extra"])

    def test_skip_allowlist_names_existing_tests_only(self) -> None:
        suites = [discover_integration_files(files) for files in INTEGRATION_SHARDS.values()]
        test_ids = {test.id() for suite in suites for test in iter_tests(suite)}
        self.assertEqual(1, len(ALLOWED_INTEGRATION_SKIPS))
        self.assertTrue(ALLOWED_INTEGRATION_SKIPS <= test_ids)
        self.assertEqual(
            set(discovered_integration_files()),
            set(sum(INTEGRATION_SHARDS.values(), ())),
        )

    def test_workflow_preserves_required_context_and_aggregates_workers(self) -> None:
        workflow = Path(".github/workflows/repository-validation.yml").read_text(
            encoding="utf-8"
        )
        job_names = re.findall(r"^    name: (.+)$", workflow, flags=re.MULTILINE)
        required = {
            "Markdown",
            "Documentation Links",
            "Unit Tests",
            "Contract Tests",
            "Integration Tests",
        }
        self.assertEqual(required, required & set(job_names))
        for name in required:
            self.assertEqual(1, job_names.count(name))

        workers = workflow.split("  integration-shards:\n", 1)[1].split(
            "  integration-tests:\n", 1
        )[0]
        aggregator = workflow.split("  integration-tests:\n", 1)[1]
        self.assertEqual(4, len(re.findall(r"^          - shard: shard-", workers, re.MULTILINE)))
        self.assertIn("      fail-fast: false", workers)
        self.assertIn("    timeout-minutes: 20", workers)
        self.assertIn(
            "if ! command -v ffmpeg >/dev/null 2>&1 || "
            "! command -v ffprobe >/dev/null 2>&1; then",
            workers,
        )
        self.assertIn("    name: Integration Tests", aggregator)
        self.assertIn("    if: always()", aggregator)
        self.assertIn("      - integration-shards", aggregator)
        self.assertIn("${{ needs.integration-shards.result }}", aggregator)


if __name__ == "__main__":
    unittest.main()
