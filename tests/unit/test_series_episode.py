import inspect
import json
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.series_episode.foundation import (
    CONFIRMED_PLAN_SCHEMA_VERSION,
    EPISODE_SCHEMA_VERSION,
    PLAN_BINDING_SCHEMA_VERSION,
    SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION,
    SERIES_SCHEMA_VERSION,
    DuplicateRecordError,
    InMemorySeriesEpisodeAdapter,
    RecordNotFoundError,
    SeriesEpisodeError,
    SeriesEpisodeService,
    SqliteSeriesEpisodeAdapter,
    UnconfirmedPlanError,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


WORKSPACE = "workspace-test"
PROFILE = "content-profile-test"
NOW = "2026-08-09T00:00:00.000Z"


class DeterministicRefs:
    def __init__(self):
        self.counts = {}

    def __call__(self, prefix):
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix}-test-{self.counts[prefix]}"


class SeriesEpisodeServiceTests(unittest.TestCase):
    def setUp(self):
        self.adapter = InMemorySeriesEpisodeAdapter()
        self.service = SeriesEpisodeService(
            self.adapter,
            ref_factory=DeterministicRefs(),
            clock=lambda: NOW,
        )

    def create_series(self, **overrides):
        value = {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "Wanlight",
            "description": "Companion short-film series",
            "plannedEpisodeCount": 12,
        }
        value.update(overrides)
        return self.service.create_series(value)

    def confirm_plan(self, **overrides):
        plan = valid_plan()
        value = {
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "brief": valid_brief(),
            "sourcePlan": plan,
            "sourcePlanRef": "ai-director-plan-live-1",
            "sourcePlanSchemaVersion": plan["schemaVersion"],
            "sourcePlanVersion": 1,
        }
        value.update(overrides)
        return self.service.confirm_creative_plan(value)

    def create_episode(self, series=None, plan=None, **overrides):
        series = series or self.create_series()
        plan = plan or self.confirm_plan()
        value = {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Episode 001",
        }
        value.update(overrides)
        return self.service.create_episode(value)

    def test_create_series_uses_v5_schema_and_server_owned_ref(self):
        series = self.create_series()
        self.assertEqual(series["schemaVersion"], SERIES_SCHEMA_VERSION)
        self.assertEqual(series["seriesRef"], "series-test-1")
        self.assertEqual(series["workspaceRef"], WORKSPACE)
        self.assertEqual(series["contentProfileRef"], PROFILE)

    def test_content_profile_is_an_opaque_upstream_reference(self):
        series = self.create_series(contentProfileRef="upstream-profile-any")
        self.assertEqual(series["contentProfileRef"], "upstream-profile-any")
        self.assertFalse(hasattr(self.service, "create_content_profile"))

    def test_series_input_validation_rejects_empty_title(self):
        with self.assertRaises(SeriesEpisodeError):
            self.create_series(title="  ")

    def test_series_input_validation_rejects_invalid_episode_count(self):
        for value in (0, -1, True, "not-an-int"):
            with self.subTest(value=value), self.assertRaises(SeriesEpisodeError):
                self.create_series(plannedEpisodeCount=value)

    def test_series_identity_is_workspace_scoped(self):
        repository = InMemorySeriesEpisodeAdapter()
        fixed = lambda prefix: f"{prefix}-fixed"
        first = SeriesEpisodeService(repository, ref_factory=fixed, clock=lambda: NOW)
        first.create_series({"workspaceRef": "workspace-a", "contentProfileRef": "profile-a", "title": "A"})
        second = SeriesEpisodeService(repository, ref_factory=fixed, clock=lambda: NOW)
        second.create_series({"workspaceRef": "workspace-b", "contentProfileRef": "profile-b", "title": "B"})
        self.assertIsNotNone(repository.get_series("workspace-a", "series-fixed"))
        self.assertIsNotNone(repository.get_series("workspace-b", "series-fixed"))

    def test_confirm_plan_requires_explicit_human_confirmation(self):
        with self.assertRaises(UnconfirmedPlanError):
            self.confirm_plan(humanConfirmed=False)

    def test_confirm_plan_requires_m1_schema(self):
        with self.assertRaises(SeriesEpisodeError):
            self.confirm_plan(sourcePlanSchemaVersion="other.schema.v1")

    def test_confirm_plan_rejects_invalid_shot_count(self):
        plan = valid_plan()
        plan["productionPlan"]["shotCount"] = 99
        with self.assertRaises(SeriesEpisodeError):
            self.confirm_plan(sourcePlan=plan)

    def test_confirm_plan_preserves_source_identity_version_and_payload(self):
        confirmed = self.confirm_plan()
        self.assertEqual(confirmed["schemaVersion"], CONFIRMED_PLAN_SCHEMA_VERSION)
        self.assertEqual(confirmed["sourcePlanRef"], "ai-director-plan-live-1")
        self.assertEqual(confirmed["sourcePlanSchemaVersion"], "creator.ai-director.plan.v1")
        self.assertEqual(confirmed["sourcePlanVersion"], 1)
        self.assertEqual(confirmed["sourcePlan"], valid_plan())

    def test_episode_has_series_parent_and_v5_schema(self):
        series = self.create_series()
        plan = self.confirm_plan()
        episode = self.create_episode(series, plan)
        self.assertEqual(episode["schemaVersion"], EPISODE_SCHEMA_VERSION)
        self.assertEqual(episode["seriesRef"], series["seriesRef"])
        self.assertEqual(episode["creativePlanRef"], plan["creativePlanRef"])

    def test_episode_cannot_exist_without_series(self):
        plan = self.confirm_plan()
        with self.assertRaises(RecordNotFoundError):
            self.service.create_episode({
                "workspaceRef": WORKSPACE,
                "seriesRef": "series-missing",
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Orphan",
            })
        self.assertEqual(self.adapter.list_episodes(), [])

    def test_episode_cannot_bind_unconfirmed_plan(self):
        series = self.create_series()
        with self.assertRaises(UnconfirmedPlanError):
            self.service.create_episode({
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": "plan-missing",
                "episodeNumber": 1,
                "title": "Episode 001",
            })

    def test_duplicate_episode_number_is_rejected_within_series(self):
        series = self.create_series()
        self.create_episode(series, self.confirm_plan())
        with self.assertRaises(DuplicateRecordError):
            self.create_episode(series, self.confirm_plan())

    def test_same_episode_number_is_allowed_in_different_series(self):
        first = self.create_episode(self.create_series(title="A"), self.confirm_plan())
        second = self.create_episode(self.create_series(title="B"), self.confirm_plan())
        self.assertNotEqual(first["seriesRef"], second["seriesRef"])
        self.assertEqual(first["episodeNumber"], second["episodeNumber"])

    def test_canonical_project_ref_is_nullable_and_not_auto_created(self):
        episode = self.create_episode()
        self.assertIsNone(episode["canonicalProjectRef"])
        self.assertNotEqual(episode["episodeRef"], episode["canonicalProjectRef"])

    def test_m2_rejects_caller_manufactured_canonical_project_ref(self):
        with self.assertRaises(SeriesEpisodeError):
            self.create_episode(canonicalProjectRef="project-made-by-ui")

    def test_episode_and_binding_use_triple_scope_identity(self):
        episode = self.create_episode()
        stored = self.adapter.get_episode(WORKSPACE, episode["seriesRef"], episode["episodeRef"])
        binding = self.adapter.get_plan_binding(WORKSPACE, episode["seriesRef"], episode["episodeRef"])
        self.assertIsNotNone(stored)
        self.assertIsNotNone(binding)

    def test_confirmed_plan_binding_is_immutable_and_detached(self):
        episode = self.create_episode()
        loaded = self.service.get_episode(WORKSPACE, episode["seriesRef"], episode["episodeRef"])
        self.assertEqual(loaded["confirmedPlanBinding"]["schemaVersion"], PLAN_BINDING_SCHEMA_VERSION)
        loaded["confirmedPlanBinding"]["sourcePlan"]["storyDirection"]["title"] = "mutated"
        reloaded = self.service.get_episode(WORKSPACE, episode["seriesRef"], episode["episodeRef"])
        self.assertNotEqual(reloaded["confirmedPlanBinding"]["sourcePlan"]["storyDirection"]["title"], "mutated")

    def test_no_silent_rebind_operation_exists(self):
        for name in ("rebind_plan", "replace_binding", "update_episode_plan"):
            self.assertFalse(hasattr(self.service, name))

    def test_series_projection_orders_episodes_by_number(self):
        series = self.create_series()
        self.create_episode(series, self.confirm_plan(), episodeNumber=2, title="Episode 002")
        self.create_episode(series, self.confirm_plan(), episodeNumber=1, title="Episode 001")
        result = self.service.get_series(WORKSPACE, series["seriesRef"])
        self.assertEqual([item["episodeNumber"] for item in result["episodes"]], [1, 2])

    def test_m3_bootstrap_has_exact_lineage_and_source_sections(self):
        episode = self.create_episode()
        result = self.service.build_script_studio_bootstrap(WORKSPACE, episode["seriesRef"], episode["episodeRef"])
        self.assertEqual(result["schemaVersion"], SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION)
        for key in ("episodeRef", "seriesRef", "sourcePlanRef", "sourcePlanSchemaVersion", "sourcePlanVersion"):
            self.assertIn(key, result)
        for key in ("storyDirection", "scriptDraft", "characters", "scenes", "storyboardPlan", "visualStyle", "productionPlan"):
            self.assertEqual(result[key], {
                "storyDirection": valid_plan()["storyDirection"],
                "scriptDraft": valid_plan()["scriptDraft"],
                "characters": valid_plan()["productionPlan"]["characters"],
                "scenes": valid_plan()["productionPlan"]["scenes"],
                "storyboardPlan": valid_plan()["storyboardPlan"],
                "visualStyle": valid_plan()["visualStyle"],
                "productionPlan": valid_plan()["productionPlan"],
            }[key])

    def test_m3_bootstrap_does_not_have_provider_dependency(self):
        source = inspect.getsource(SeriesEpisodeService.build_script_studio_bootstrap)
        for forbidden in ("provider", "DeepSeek", "generate(", "TextGeneration"):
            self.assertNotIn(forbidden, source)

    def test_unknown_episode_is_rejected_with_full_scope(self):
        with self.assertRaises(RecordNotFoundError):
            self.service.get_episode(WORKSPACE, "series-missing", "episode-missing")

    def test_results_are_json_serializable(self):
        episode = self.create_episode()
        json.dumps(episode, ensure_ascii=False)
        json.dumps(self.service.list_series(WORKSPACE), ensure_ascii=False)


class SqliteSeriesEpisodeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database_path = Path(self.temporary.name) / "v5-series-episode.sqlite3"
        self.service = SeriesEpisodeService(
            SqliteSeriesEpisodeAdapter(self.database_path),
            ref_factory=DeterministicRefs(),
            clock=lambda: NOW,
        )

    def complete_chain(self):
        series = self.service.create_series({
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "Wanlight",
            "plannedEpisodeCount": 12,
        })
        plan_value = valid_plan()
        plan = self.service.confirm_creative_plan({
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "brief": valid_brief(),
            "sourcePlan": plan_value,
            "sourcePlanRef": "ai-director-plan-live-1",
            "sourcePlanSchemaVersion": plan_value["schemaVersion"],
            "sourcePlanVersion": 1,
        })
        episode = self.service.create_episode({
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "episodeNumber": 1,
            "title": "Episode 001",
        })
        return series, plan, episode

    def test_local_development_database_is_created(self):
        self.assertTrue(self.database_path.is_file())

    def test_complete_chain_survives_adapter_restart(self):
        series, _, episode = self.complete_chain()
        restarted = SeriesEpisodeService(SqliteSeriesEpisodeAdapter(self.database_path))
        loaded = restarted.get_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"])
        self.assertEqual(loaded["confirmedPlanBinding"]["sourcePlan"], valid_plan())

    def test_duplicate_episode_transaction_does_not_add_binding(self):
        series, _, _ = self.complete_chain()
        plan_value = valid_plan()
        second_plan = self.service.confirm_creative_plan({
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "brief": valid_brief(),
            "sourcePlan": plan_value,
            "sourcePlanRef": "ai-director-plan-live-2",
            "sourcePlanSchemaVersion": plan_value["schemaVersion"],
            "sourcePlanVersion": 2,
        })
        with self.assertRaises(DuplicateRecordError):
            self.service.create_episode({
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": second_plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Duplicate",
            })
        self.assertEqual(len(self.service.get_series(WORKSPACE, series["seriesRef"])["episodes"]), 1)

    def test_sqlite_schema_version_is_checked_on_restart(self):
        self.complete_chain()
        restarted = SqliteSeriesEpisodeAdapter(self.database_path)
        self.assertEqual(len(restarted.list_series(WORKSPACE)), 1)


if __name__ == "__main__":
    unittest.main()
