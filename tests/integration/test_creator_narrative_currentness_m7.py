from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    DEFAULT_VALIDATION_PROFILE_REF,
    EpisodeProductionPublicError,
    NarrativeValidationProfile,
    NarrativeValidationProfileRegistry,
    NarrativeValidationRule,
    create_local_development_boundary,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from tests.unit.test_episode_production_k2 import (
    K2ApprovalAuthority,
    K2ScopeAuthority,
    Refs,
    WORKSPACE,
    run_command,
)
from tests.unit.test_narrative_currentness_m7 import (
    seed_m7,
    validation_command,
    validation_profiles,
)
from tests.unit.test_script_studio_m3 import content_from_candidate
from tests.unit.test_series_intelligence_consumer_m6_p3 import seed_consumer_on


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


class NarrativeCurrentnessPersistenceIntegrationTests(unittest.TestCase):
    def test_script_v2_round_trip_reuses_existing_lifecycle_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "creator.sqlite3"
            first = LifecycleAssembly.sqlite(
                database,
                initialize_or_upgrade=True,
                ref_factory=Refs(),
                clock=lambda: "2026-09-02T02:00:00Z",
                m6_scope_authority=K2ScopeAuthority(),
                m6_approval_authority=K2ApprovalAuthority(),
            )
            seed = seed_consumer_on(first, workspace="workspace-m7-sqlite")
            tables_before = sqlite_tables(database)
            context = seed["context"]
            created = first.script_studio.create_version(
                {
                    **context,
                    "changeKind": "ai-generation",
                    "content": content_from_candidate(),
                }
            )
            binding = created["scriptVersion"]["m6ConsumerBinding"]
            second = LifecycleAssembly.sqlite(
                database,
                m6_scope_authority=K2ScopeAuthority(),
                m6_approval_authority=K2ApprovalAuthority(),
            )
            restored = second.script_studio.get_workspace(
                context["workspaceRef"],
                context["seriesRef"],
                context["episodeRef"],
            )
            self.assertEqual(
                restored["versions"][0]["schemaVersion"],
                "creator.script-studio.script-version.v2",
            )
            self.assertEqual(
                restored["versions"][0]["m6ConsumerBinding"], binding
            )
            self.assertEqual(sqlite_tables(database), tables_before)

    def test_m7_exact_replay_survives_restart_without_new_evidence_tables(self):
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
            first = create_local_development_boundary(database, **kwargs)
            tables_before = sqlite_tables(evidence)
            run = first.create_run(
                run_command(seed["project"], seed["series"], seed["episode"])
            )
            local_seed = {**seed, "run": run, "boundary": first}
            command = validation_command(local_seed, key="m7-sqlite-replay")
            created = first.create_narrative_validation(command)

            restarted = create_local_development_boundary(
                database,
                **kwargs,
                initialize_if_missing=False,
            )
            replay = restarted.create_narrative_validation(command)
            restored = restarted.get_narrative_validation(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                run["productionRunRef"],
                created["consistencyValidationVersionRef"],
            )
            self.assertTrue(replay["idempotentReplay"])
            self.assertEqual(replay["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["payloadDigest"], created["payloadDigest"])
            self.assertEqual(restored["currentness"], "CURRENT")
            self.assertEqual(sqlite_tables(evidence), tables_before)
            self.assertFalse(any("m7" in name.lower() for name in tables_before))

            changed_profiles = NarrativeValidationProfileRegistry(
                (
                    NarrativeValidationProfile(
                        DEFAULT_VALIDATION_PROFILE_REF,
                        1,
                        (
                            NarrativeValidationRule(
                                "m7.rule.profile-drift.v1",
                                "WORLD_RULE_CONFLICT",
                                "WARN",
                                "ACTION",
                                "林澈",
                                {"policyRef": "changed-profile"},
                            ),
                        ),
                    ),
                )
            )
            changed = create_local_development_boundary(
                database,
                **{
                    **kwargs,
                    "narrative_validation_profiles": changed_profiles,
                },
                initialize_if_missing=False,
            )
            stale = changed.get_narrative_validation(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                run["productionRunRef"],
                created["consistencyValidationVersionRef"],
            )
            self.assertEqual(stale["currentness"], "STALE")
            with self.assertRaises(EpisodeProductionPublicError) as conflict:
                changed.create_narrative_validation(command)
            self.assertEqual(conflict.exception.code, "idempotency_conflict")


if __name__ == "__main__":
    unittest.main()
