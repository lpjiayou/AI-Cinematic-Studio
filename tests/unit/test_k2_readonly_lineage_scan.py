from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "scripts" / "k2_readonly_lineage_scan.py"


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class K2ReadonlyLineageScanTests(unittest.TestCase):
    def test_reports_safe_lineage_without_payload_or_idempotency_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode-production.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE v5_episode_production_runs (
                    workspace_ref TEXT, production_run_ref TEXT, schema_version TEXT,
                    idempotency_key TEXT, content_profile_ref TEXT, project_ref TEXT,
                    series_ref TEXT, episode_ref TEXT, series_plan_ref TEXT,
                    series_plan_version_ref TEXT, episode_plan_item_ref TEXT,
                    script_ref TEXT, script_version_ref TEXT, manifest_json TEXT,
                    upstream_snapshot_json TEXT, upstream_digest TEXT,
                    payload_digest TEXT, state TEXT, created_at TEXT,
                    updated_at TEXT, version INTEGER
                );
                """
            )
            connection.execute(
                "INSERT INTO v5_episode_production_runs VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "workspace-k2",
                    "production-run-k2",
                    "v5.episode-production-run.v1",
                    "idempotency-must-not-print",
                    "content-profile-k2",
                    "project-k2",
                    "series-k2",
                    "episode-k2",
                    "series-plan-k2",
                    "series-plan-version-k2",
                    "episode-plan-item-k2",
                    "script-k2",
                    "script-version-k2",
                    '{"creativeText":"must-not-print"}',
                    '{"providerSecret":"must-not-print"}',
                    "a" * 64,
                    "b" * 64,
                    "ROOTS_READY",
                    "2026-08-17T00:00:00Z",
                    "2026-08-17T00:00:00Z",
                    1,
                ),
            )
            connection.commit()
            connection.close()
            before = _digest(database)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("K2_CURRENT_LINEAGE_STATUS=FOUND_READ_ONLY", result.stdout)
            self.assertIn('"production_run_ref":"production-run-k2"', result.stdout)
            self.assertIn('"script_version_ref":"script-version-k2"', result.stdout)
            self.assertNotIn("idempotency-must-not-print", result.stdout)
            self.assertNotIn("creativeText", result.stdout)
            self.assertNotIn("providerSecret", result.stdout)
            self.assertEqual(_digest(database), before)

    def test_reports_not_found_without_creating_a_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("K2_DATABASES_FOUND=0", result.stdout)
            self.assertIn("K2_CURRENT_LINEAGE_STATUS=NOT_FOUND", result.stdout)
            self.assertEqual(list(root.iterdir()), [])

    def test_row_limit_is_bounded_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "policy.sqlite3"
            connection = sqlite3.connect(database)
            connection.execute(
                "CREATE TABLE v5_production_policy_bundles ("
                "workspace_ref TEXT, production_run_ref TEXT, idempotency_key TEXT, "
                "request_digest TEXT, payload_json TEXT, payload_digest TEXT, "
                "created_at TEXT)"
            )
            for index in range(3):
                connection.execute(
                    "INSERT INTO v5_production_policy_bundles VALUES (?,?,?,?,?,?,?)",
                    (
                        "workspace-k2",
                        f"run-{index}",
                        f"idempotency-{index}",
                        "c" * 64,
                        '{"private":"must-not-print"}',
                        "d" * 64,
                        f"2026-08-17T00:00:0{index}Z",
                    ),
                )
            connection.commit()
            connection.close()

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--max-rows",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertEqual(result.returncode, 3, result.stderr)
            self.assertIn("K2_ROWS_TRUNCATED=", result.stdout)
            self.assertNotIn("idempotency-", result.stdout)
            self.assertNotIn("must-not-print", result.stdout)


if __name__ == "__main__":
    unittest.main()
