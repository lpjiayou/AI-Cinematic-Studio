import inspect
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp.server import (
    CONFIRM_PLAN_ENDPOINT,
    EPISODES_ENDPOINT,
    SERIES_ENDPOINT,
)
from services.v5_core_os import series_episode as public_package
from services.v5_core_os.series_episode.foundation import (
    CONFIRMED_PLAN_SCHEMA_VERSION,
    EPISODE_SCHEMA_VERSION,
    PLAN_BINDING_SCHEMA_VERSION,
    SERIES_SCHEMA_VERSION,
    ConfirmedCreativePlanBinding,
    EpisodeRecord,
    InMemorySeriesEpisodeAdapter,
    SeriesEpisodeRepository,
    SeriesEpisodeError,
    SeriesEpisodeService,
    SqliteSeriesEpisodeAdapter,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


ROOT = Path(__file__).resolve().parents[2]
APP_PACKAGE = ROOT / "apps" / "creator_workspace_mvp"
SERVER = APP_PACKAGE / "server.py"
WORKSPACE = "workspace-contract"
PROFILE = "content-profile-contract"


class PrefixRefs:
    def __init__(self):
        self.values = {}

    def __call__(self, prefix):
        self.values[prefix] = self.values.get(prefix, 0) + 1
        return f"{prefix}-contract-{self.values[prefix]}"


def complete_chain(adapter):
    service = SeriesEpisodeService(
        adapter,
        ref_factory=PrefixRefs(),
        clock=lambda: "2026-08-09T00:00:00.000Z",
    )
    series = service.create_series({
        "workspaceRef": WORKSPACE,
        "contentProfileRef": PROFILE,
        "title": "Series",
        "plannedEpisodeCount": 2,
    })
    source = valid_plan()
    plan = service.confirm_creative_plan({
        "workspaceRef": WORKSPACE,
        "humanConfirmed": True,
        "brief": valid_brief(),
        "sourcePlan": source,
        "sourcePlanRef": "source-plan-contract",
        "sourcePlanSchemaVersion": source["schemaVersion"],
        "sourcePlanVersion": 1,
    })
    episode = service.create_episode({
        "workspaceRef": WORKSPACE,
        "seriesRef": series["seriesRef"],
        "creativePlanRef": plan["creativePlanRef"],
        "episodeNumber": 1,
        "title": "Episode 001",
    })
    return service, series, plan, episode


class SeriesEpisodeRepositoryContractTests(unittest.TestCase):
    def adapter_cases(self, directory):
        return (
            ("in-memory", InMemorySeriesEpisodeAdapter()),
            ("sqlite-local-development", SqliteSeriesEpisodeAdapter(Path(directory) / "contract.sqlite3")),
        )

    def test_common_repository_contract_create_get_and_list(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, _, episode = complete_chain(adapter)
                    self.assertEqual(adapter.get_series(WORKSPACE, series["seriesRef"]).title, "Series")
                    self.assertEqual(
                        adapter.get_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"]).episodeNumber,
                        1,
                    )
                    self.assertEqual(len(adapter.list_episodes(WORKSPACE, series["seriesRef"])), 1)

    def test_common_repository_contract_stores_immutable_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, _, episode = complete_chain(adapter)
                    binding = adapter.get_plan_binding(WORKSPACE, series["seriesRef"], episode["episodeRef"])
                    self.assertEqual(binding.schemaVersion, PLAN_BINDING_SCHEMA_VERSION)
                    self.assertEqual(binding.sourcePlanRef, "source-plan-contract")
                    self.assertIn("storyDirection", binding.sourcePlanJson)

    def test_common_repository_contract_deletes_episode_and_binding_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, _, episode = complete_chain(adapter)
                    deleted = adapter.delete_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"])
                    self.assertEqual(deleted.episodeRef, episode["episodeRef"])
                    self.assertIsNone(adapter.get_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"]))
                    self.assertIsNone(adapter.get_plan_binding(WORKSPACE, series["seriesRef"], episode["episodeRef"]))

    def test_common_repository_contract_cascades_series_episode_records(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, _, episode = complete_chain(adapter)
                    deleted_series, deleted_episodes = adapter.delete_series(WORKSPACE, series["seriesRef"])
                    self.assertEqual(deleted_series.seriesRef, series["seriesRef"])
                    self.assertEqual([item.episodeRef for item in deleted_episodes], [episode["episodeRef"]])
                    self.assertIsNone(adapter.get_series(WORKSPACE, series["seriesRef"]))
                    self.assertEqual(adapter.list_episodes(WORKSPACE, series["seriesRef"]), [])

    def test_common_repository_contract_enforces_series_episode_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, _, episode = complete_chain(adapter)
                    self.assertIsNone(adapter.get_episode(WORKSPACE, "different-series", episode["episodeRef"]))
                    self.assertIsNotNone(adapter.get_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"]))

    def test_common_repository_contract_rolls_back_episode_when_binding_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, adapter in self.adapter_cases(directory):
                with self.subTest(adapter=name):
                    _, series, plan, _ = complete_chain(adapter)
                    plan_record = adapter.get_confirmed_plan(WORKSPACE, plan["creativePlanRef"])
                    episode = EpisodeRecord(
                        EPISODE_SCHEMA_VERSION,
                        WORKSPACE,
                        "episode-rollback",
                        series["seriesRef"],
                        2,
                        1,
                        1,
                        "Rollback candidate",
                        "draft",
                        None,
                        plan["creativePlanRef"],
                        "2026-08-09T00:00:00.000Z",
                        "2026-08-09T00:00:00.000Z",
                        1,
                    )
                    mismatched_binding = ConfirmedCreativePlanBinding(
                        PLAN_BINDING_SCHEMA_VERSION,
                        WORKSPACE,
                        "series-mismatch",
                        episode.episodeRef,
                        plan_record.creativePlanRef,
                        plan_record.sourcePlanRef,
                        plan_record.sourcePlanSchemaVersion,
                        plan_record.sourcePlanVersion,
                        plan_record.briefJson,
                        plan_record.sourcePlanJson,
                        "2026-08-09T00:00:00.000Z",
                        1,
                    )
                    with self.assertRaises(SeriesEpisodeError):
                        adapter.create_episode_with_binding(episode, mismatched_binding)
                    self.assertIsNone(
                        adapter.get_episode(WORKSPACE, series["seriesRef"], episode.episodeRef)
                    )
                    self.assertIsNone(
                        adapter.get_plan_binding(WORKSPACE, series["seriesRef"], episode.episodeRef)
                    )


class CreatorSeriesEpisodeArchitectureContractTests(unittest.TestCase):
    def test_public_package_exports_only_application_facing_surface(self):
        self.assertEqual(
            set(public_package.__all__),
            {
                "SeriesEpisodePublicBoundary",
                "SeriesEpisodePublicError",
                "create_in_memory_boundary",
                "create_local_development_boundary",
                "create_local_development_boundary_from_environment",
            },
        )

    def test_application_imports_v5_public_package_not_foundation(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn("from services.v5_core_os.series_episode import", source)
        self.assertNotIn("series_episode.foundation", source)
        self.assertNotIn("SqliteSeriesEpisodeAdapter", source)
        self.assertNotIn("InMemorySeriesEpisodeAdapter", source)

    def test_application_package_contains_no_direct_sqlite_or_sql(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in APP_PACKAGE.glob("*.py"))
        for forbidden in (
            "sqlite3.connect",
            "CREATE TABLE",
            "INSERT INTO series",
            "INSERT INTO episode",
            "INSERT INTO v5_",
        ):
            self.assertNotIn(forbidden, source)

    def test_owner_implementation_is_physically_under_v5(self):
        foundation_path = Path(inspect.getfile(SeriesEpisodeService)).resolve()
        self.assertIn("services", foundation_path.parts)
        self.assertIn("v5_core_os", foundation_path.parts)
        self.assertNotIn("apps", foundation_path.parts)

    def test_repository_port_exposes_domain_operations_not_storage_details(self):
        methods = {
            name
            for name, value in inspect.getmembers(SeriesEpisodeRepository, inspect.isfunction)
            if not name.startswith("__")
        }
        self.assertEqual(
            methods,
            {
                "create_series",
                "get_series",
                "list_series",
                "store_confirmed_plan",
                "get_confirmed_plan",
                "create_episode_with_binding",
                "get_episode",
                "list_episodes",
                "get_plan_binding",
                "delete_episode",
                "delete_series",
            },
        )

    def test_v5_contract_versions_and_m3_bridge_namespace_are_explicit(self):
        for version in (SERIES_SCHEMA_VERSION, CONFIRMED_PLAN_SCHEMA_VERSION, EPISODE_SCHEMA_VERSION, PLAN_BINDING_SCHEMA_VERSION):
            self.assertTrue(version.startswith("v5."))
            self.assertTrue(version.endswith(".v1"))
        self.assertEqual(public_package.SeriesEpisodePublicBoundary.__module__, "services.v5_core_os.series_episode.public")

    def test_episode_contract_has_nullable_canonical_project_relation(self):
        fields = EpisodeRecord.__dataclass_fields__
        self.assertIn("workspaceRef", fields)
        self.assertIn("seriesRef", fields)
        self.assertIn("episodeRef", fields)
        self.assertIn("canonicalProjectRef", fields)

    def test_binding_contract_preserves_full_source_lineage(self):
        fields = ConfirmedCreativePlanBinding.__dataclass_fields__
        for field in (
            "workspaceRef",
            "seriesRef",
            "episodeRef",
            "sourcePlanRef",
            "sourcePlanSchemaVersion",
            "sourcePlanVersion",
            "sourcePlanJson",
        ):
            self.assertIn(field, fields)

    def test_endpoints_are_same_origin_application_contracts(self):
        for endpoint in (SERIES_ENDPOINT, CONFIRM_PLAN_ENDPOINT, EPISODES_ENDPOINT):
            self.assertTrue(endpoint.startswith("/creator/internal/"))
            self.assertNotIn("://", endpoint)

    def test_content_profile_is_not_implemented_as_application_account_api(self):
        server_source = SERVER.read_text(encoding="utf-8")
        self.assertNotIn("content-profiles", server_source)

    def test_public_boundary_hides_repository_and_adapter_errors(self):
        source = inspect.getsource(public_package.SeriesEpisodePublicBoundary)
        self.assertIn("SeriesEpisodePublicError", source)
        self.assertNotIn("sqlite3", source)


if __name__ == "__main__":
    unittest.main()
