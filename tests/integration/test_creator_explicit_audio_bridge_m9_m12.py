from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
    create_local_development_boundary,
)
from tests.unit.test_episode_production_k2 import WORKSPACE, run_command
from tests.unit.test_execution_method_planning_m8_m9 import plan_command
from tests.unit.test_explicit_audio_bridge_m9_m12 import (
    confirm_fixed_voice,
    explicit_audio_service,
    fixed_voice_asset,
    route_command,
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


class ExplicitAudioBridgePersistenceIntegrationTests(unittest.TestCase):
    def test_sqlite_restart_replay_uses_existing_journal_without_legacy_writes(self):
        seed = seed_m7()
        assembly = seed["assembly"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "episode-production.sqlite3"
            evidence = root / "episode-production.evidence.sqlite3"
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
                clock=lambda: "2026-09-02T08:00:00Z",
            )
            run = first.create_run(
                run_command(seed["project"], seed["series"], seed["episode"])
            )
            local_seed = {**seed, "boundary": first, "run": run}
            validation = first.create_narrative_validation(
                validation_command(local_seed, key="integration-m9-m12-validation")
            )
            plan = first.create_execution_method_plan(
                plan_command(
                    local_seed,
                    validation,
                    key="integration-m9-m12-plan",
                )
            )
            confirmed = confirm_fixed_voice(
                local_seed, "character-gu", "integration-gu"
            )
            voice = fixed_voice_asset(
                local_seed, confirmed, "integration-gu"
            )
            requirement = plan["audioRequirements"][0]
            command = route_command(
                local_seed,
                plan,
                requirement,
                key="integration-m9-m12-route",
                voices={"character-gu": voice},
            )
            evidence_tables_before = sqlite_tables(evidence)
            files_before = {path.name for path in root.iterdir()}
            created = first.create_explicit_audio_generation_request(command)

            restarted = create_local_development_boundary(
                database,
                **kwargs,
                initialize_if_missing=False,
            )
            replay = restarted.create_explicit_audio_generation_request(command)
            restored = restarted.get_explicit_audio_requirement_route(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                run["productionRunRef"],
                created["audioRequirementRouteVersionRef"],
            )

            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["currentness"], "CURRENT")
            self.assertEqual(sqlite_tables(evidence), evidence_tables_before)
            self.assertEqual({path.name for path in root.iterdir()}, files_before)
            self.assertFalse(
                any(
                    marker in table.lower()
                    for table in sqlite_tables(evidence)
                    for marker in (
                        "m9_m12",
                        "audio_route",
                        "generation_request",
                        "media_job",
                    )
                )
            )
            records = explicit_audio_service(
                restarted
            ).evidence_repository.list_records(
                WORKSPACE, run["productionRunRef"]
            )
            kinds = [record["recordKind"] for record in records]
            self.assertEqual(kinds.count(AUDIO_REQUIREMENT_ROUTE_RECORD_KIND), 1)
            self.assertNotIn("GenerationRequest", kinds)
            self.assertNotIn("AudioGenerationRequest", kinds)
            self.assertNotIn("MediaJob", kinds)


if __name__ == "__main__":
    unittest.main()
