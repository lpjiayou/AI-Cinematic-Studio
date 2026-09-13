"""Coverage invariants for the Integration Tests CI shard plan."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from argparse import Namespace
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

from scripts import run_ci_fast_path as runner
from scripts.classify_ci_change_scope import (
    AFFECTED_TESTS, AFFECTED_TEST_ALLOWLIST, FULL_SUITE, ChangedFile, classify_records,
)

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
    def test_six_shards_cover_every_integration_file_exactly_once(self) -> None:
        audit = audit_integration_shard_files()
        discovered = tuple(audit["discovered"])
        assigned = tuple(audit["assigned"])
        assignment_counts = Counter(assigned)
        self.assertEqual(6, len(INTEGRATION_SHARDS))
        self.assertEqual(set(discovered), set(assigned))
        self.assertTrue(
            all(assignment_counts[path] == 1 for path in discovered)
        )
        self.assertEqual((), audit["missing"])
        self.assertEqual((), audit["extra"])
        self.assertEqual(0, audit["duplicateCount"])
        self.assertEqual(len(discovered), len(assigned))

    def test_sharded_test_count_matches_complete_discovery(self) -> None:
        full_count, shard_counts = integration_test_counts()
        self.assertGreater(full_count, 0)
        self.assertEqual(set(INTEGRATION_SHARDS), set(shard_counts))
        self.assertEqual(full_count, sum(shard_counts.values()))

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
        self.assertEqual(6, len(re.findall(r"^          - shard: shard-", workers, re.MULTILINE)))
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

    def test_daily_full_run_and_no_duplicate_push_trigger(self):
        workflow = Path(".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
        self.assertIn("  schedule:\n    - cron: '19 19 * * *'", workflow)
        self.assertNotIn("  push:", workflow)


class AffectedIntegrationRunnerTests(unittest.TestCase):
    def payload(self):
        path = sorted(AFFECTED_TEST_ALLOWLIST)[0]
        return classify_records("pull_request", "1" * 40, "2" * 40,
            [ChangedFile("M", path, path, "100644", "100644")]).payload

    def test_selected_files_are_assigned_exactly_once_and_no_unrelated_render(self):
        payload = self.payload()
        assigned = [p for shard in INTEGRATION_SHARDS
                    for p in runner.integration_files_for_scope(AFFECTED_TESTS, payload, shard)]
        self.assertEqual(Counter(payload["selectedIntegrationFiles"]), Counter(assigned))
        self.assertTrue(all("m13" not in path for path in assigned))

    def test_full_selection_is_unchanged_by_affected_payload(self):
        for shard, files in INTEGRATION_SHARDS.items():
            self.assertEqual(files, runner.integration_files_for_scope(FULL_SUITE, {}, shard))

    def test_discovery_import_failure_cannot_count_as_a_discovered_test(self):
        loader = unittest.TestLoader()
        loader.errors = ["synthetic import failure"]
        with patch.object(unittest, "TestLoader", return_value=loader), \
             patch.object(loader, "discover", return_value=unittest.TestSuite()):
            with self.assertRaises(SystemExit):
                runner.discover_suite(Path("tests/integration"))
            with self.assertRaises(SystemExit):
                runner.discover_integration_files(INTEGRATION_SHARDS["shard-1"])

    def test_unit_and_contract_still_run_complete_suites(self):
        for job in ("unit", "contract"):
            with patch.object(runner, "load_and_verify_scope", return_value=(AFFECTED_TESTS, self.payload())), \
                 patch.object(runner, "required_epoch", return_value=0), \
                 patch.object(runner, "run_full_suite") as execute, redirect_stdout(StringIO()) as output:
                runner.command_run_job(Namespace(job=job))
            execute.assert_called_once_with(job)
            self.assertIn("FULL_SUITE_EXECUTED=false", output.getvalue())

    def test_failed_cancelled_skipped_missing_workers_cannot_pass_aggregator(self):
        for state in ("failure", "cancelled", "skipped", "", "unknown"):
            with patch.object(runner, "load_and_verify_scope", return_value=(AFFECTED_TESTS, self.payload())), \
                 patch.object(runner, "required_epoch", return_value=0), redirect_stdout(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    runner.command_aggregate_integration(Namespace(workers_result=state))
                self.assertEqual(1, error.exception.code)

    def test_affected_shard_runs_real_selected_tests_and_propagates_failure(self):
        class Pass(unittest.TestCase):
            def runTest(self):
                self.assertEqual(1, 1)
        class Fail(unittest.TestCase):
            def runTest(self):
                self.fail("injected runner failure")
        payload = self.payload()
        shard = next(s for s in INTEGRATION_SHARDS
                     if runner.integration_files_for_scope(AFFECTED_TESTS, payload, s))
        for case, succeeds in ((Pass, True), (Fail, False)):
            suite = unittest.TestSuite([case()])
            with patch.object(runner, "load_and_verify_scope", return_value=(AFFECTED_TESTS, payload)), \
                 patch.object(runner, "required_epoch", return_value=0), \
                 patch.object(runner, "require_complete_integration_shard_plan"), \
                 patch.object(runner, "discover_integration_files", return_value=suite) as discover, \
                 patch.object(runner, "ffmpeg_process_count", return_value=0), \
                 patch.object(runner, "residual_listener_count", return_value=0), \
                 patch.object(runner, "current_process_group", return_value=0), \
                 redirect_stdout(StringIO()) as output, redirect_stderr(StringIO()):
                if succeeds:
                    runner.command_run_integration_shard(Namespace(shard=shard))
                else:
                    with self.assertRaises(SystemExit):
                        runner.command_run_integration_shard(Namespace(shard=shard))
            discover.assert_called_once_with(runner.integration_files_for_scope(AFFECTED_TESTS, payload, shard))
            self.assertEqual(1, suite.countTestCases())
            self.assertIn("SHARDED_EXECUTED_TEST_COUNT=1", output.getvalue())
            self.assertIn("FULL_SUITE_EXECUTED=false", output.getvalue())


if __name__ == "__main__":
    unittest.main()
