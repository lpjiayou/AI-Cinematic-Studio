from pathlib import Path
import copy
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_local_development_boundary,
)
from tests.unit.test_episode_production_k2 import WORKSPACE, run_command
from tests.unit.test_execution_method_planning_m8_m9 import plan_command
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


class ExecutionMethodPlanningPersistenceIntegrationTests(unittest.TestCase):
    def test_exact_replay_and_read_survive_restart_without_new_tables(self):
        seed = seed_m7()
        assembly = seed["assembly"]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            evidence = Path(directory) / "episode-production.evidence.sqlite3"
            kwargs = {
                "project_boundary": assembly.project_context,
                "series_episode_boundary": assembly.series_episode,
                "series_planning_boundary": assembly.series_planning,
                "script_studio_boundary": assembly.script_studio,
                "evidence_database_path": evidence,
                "narrative_validation_profiles": validation_profiles(),
            }
            first = create_local_development_boundary(
                database,
                **kwargs,
                ref_factory=seed["refs"],
                clock=lambda: "2026-09-02T03:00:00Z",
            )
            tables_before = sqlite_tables(evidence)
            run = first.create_run(
                run_command(seed["project"], seed["series"], seed["episode"])
            )
            local_seed = {**seed, "boundary": first, "run": run}
            validation = first.create_narrative_validation(
                validation_command(local_seed, key="m7-sqlite-for-m8")
            )
            command = plan_command(
                local_seed, validation, key="m8-m9-sqlite-replay"
            )
            created = first.create_execution_method_plan(command)

            restarted = create_local_development_boundary(
                database,
                **kwargs,
                initialize_if_missing=False,
            )
            replay = restarted.create_execution_method_plan(command)
            restored = restarted.get_execution_method_plan(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                run["productionRunRef"],
                created["executionMethodPlanVersionRef"],
            )
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["currentness"], "CURRENT")
            self.assertEqual(sqlite_tables(evidence), tables_before)
            self.assertFalse(
                any(
                    marker in table.lower()
                    for table in tables_before
                    for marker in ("m8", "m9", "execution_method")
                )
            )

            changed = copy.deepcopy(command)
            changed["shots"][1]["cameraInstruction"]["framing"] = "EXTREME_WIDE"
            with self.assertRaises(EpisodeProductionPublicError) as conflict:
                restarted.create_execution_method_plan(changed)
            self.assertEqual(conflict.exception.code, "idempotency_conflict")


if __name__ == "__main__":
    unittest.main()
