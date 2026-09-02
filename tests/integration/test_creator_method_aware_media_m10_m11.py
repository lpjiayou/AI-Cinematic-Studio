from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v4_platform import MediaJobCoordinator, SqliteMediaJobAdapter
from services.v5_core_os.episode_production import create_local_development_boundary
from tests.unit.test_episode_production_k2 import WORKSPACE, run_command
from tests.unit.test_execution_method_planning_m8_m9 import plan_command
from tests.unit.test_method_aware_media_m10_m11 import (
    NoCallWanAdapter,
    append_admitted_image,
    m10_command,
    m11_command,
)
from tests.unit.test_narrative_currentness_m7 import (
    seed_m7,
    validation_command,
    validation_profiles,
)


def sqlite_tables(path):
    connection = sqlite3.connect(path)
    try:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        connection.close()


class MethodAwareMediaPersistenceIntegrationTests(unittest.TestCase):
    def test_sqlite_restart_replay_reuses_evidence_journal_and_media_queue(self):
        seed = seed_m7()
        assembly = seed["assembly"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode-production.sqlite3"
            evidence = root / "episode-production.evidence.sqlite3"
            jobs_path = root / "media-jobs.sqlite3"
            adapter = NoCallWanAdapter()
            coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(jobs_path),
                adapter,
                root / "artifacts",
                ref_factory=lambda prefix: f"{prefix}-integration",
                clock=lambda: "2026-09-02T06:00:00Z",
            )
            kwargs = {
                "project_boundary": assembly.project_context,
                "series_episode_boundary": assembly.series_episode,
                "series_planning_boundary": assembly.series_planning,
                "script_studio_boundary": assembly.script_studio,
                "evidence_database_path": evidence,
                "narrative_validation_profiles": validation_profiles(),
                "media_execution": coordinator,
            }
            first = create_local_development_boundary(
                database,
                **kwargs,
                ref_factory=seed["refs"],
                clock=lambda: "2026-09-02T06:00:00Z",
            )
            run = first.create_run(
                run_command(seed["project"], seed["series"], seed["episode"])
            )
            local_seed = {**seed, "boundary": first, "run": run}
            validation = first.create_narrative_validation(
                validation_command(local_seed, key="integration-m7")
            )
            execution_plan = first.create_execution_method_plan(
                plan_command(local_seed, validation, key="integration-m8-m9")
            )
            admitted = append_admitted_image(local_seed, execution_plan)
            evidence_tables_before = sqlite_tables(evidence)
            job_tables_before = sqlite_tables(jobs_path)

            input_command = m10_command(
                local_seed,
                execution_plan,
                [admitted["binding"]],
                key="integration-m10",
            )
            input_plan = first.create_method_aware_input_plan(input_command)
            route_command = m11_command(
                local_seed, input_plan, key="integration-m11"
            )
            route = first.route_method_aware_videos(route_command)
            self.assertEqual(route["queuedJobCount"], 1)
            self.assertEqual(adapter.generate_calls, 0)

            restarted_adapter = NoCallWanAdapter()
            restarted_coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(jobs_path, initialize_if_missing=False),
                restarted_adapter,
                root / "artifacts",
                ref_factory=lambda prefix: f"{prefix}-restart",
                clock=lambda: "2026-09-02T06:00:01Z",
            )
            restarted = create_local_development_boundary(
                database,
                **{**kwargs, "media_execution": restarted_coordinator},
                initialize_if_missing=False,
            )
            input_replay = restarted.create_method_aware_input_plan(input_command)
            route_replay = restarted.route_method_aware_videos(route_command)
            restored = restarted.get_method_aware_video_route(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                run["productionRunRef"],
                route["videoMethodRouteVersionRef"],
            )

            self.assertTrue(input_replay["idempotentReplay"])
            self.assertTrue(route_replay["idempotentReplay"])
            self.assertEqual(input_replay["payloadDigest"], input_plan["payloadDigest"])
            self.assertEqual(route_replay["payloadDigest"], route["payloadDigest"])
            self.assertEqual(restored["currentness"], "CURRENT")
            self.assertEqual(
                len(
                    restarted_coordinator.list_jobs(
                        WORKSPACE, run["productionRunRef"]
                    )
                ),
                1,
            )
            self.assertEqual(restarted_adapter.generate_calls, 0)
            self.assertEqual(sqlite_tables(evidence), evidence_tables_before)
            self.assertEqual(sqlite_tables(jobs_path), job_tables_before)
            self.assertFalse(
                any(
                    marker in table.lower()
                    for table in sqlite_tables(evidence) | sqlite_tables(jobs_path)
                    for marker in ("method_aware", "method_route", "m10_queue", "m11_queue")
                )
            )


if __name__ == "__main__":
    unittest.main()
