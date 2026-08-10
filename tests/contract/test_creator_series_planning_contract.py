import inspect
from pathlib import Path
import unittest

from services.v5_core_os import series_planning as public_package
from services.v5_core_os.series_planning import SeriesPlanningPublicBoundary
from tests.unit.test_series_planning_m5 import WORKSPACE, confirm, create_context


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "apps" / "creator_workspace_mvp" / "server.py"
APPLICATION = ROOT / "apps" / "creator_workspace_mvp" / "series_director.py"
BROWSER = ROOT / "apps" / "creator-workspace-mvp" / "app.js"


class CreatorSeriesPlanningContractTests(unittest.TestCase):
    def test_public_package_exports_only_stable_boundary_factories(self):
        self.assertEqual(
            public_package.__all__,
            [
                "SeriesPlanningPublicBoundary",
                "SeriesPlanningPublicError",
                "create_in_memory_boundary",
                "create_local_development_boundary",
                "create_local_development_boundary_from_environment",
            ],
        )
        self.assertTrue(inspect.isclass(SeriesPlanningPublicBoundary))

    def test_series_plan_identity_and_planned_episode_contract_are_v5_owned(self):
        series_boundary, _, planning, series, project = create_context()
        created = confirm(planning, series, project)
        version = created["version"]
        self.assertEqual(version["schemaVersion"], "v5.series-plan-version.v1")
        self.assertTrue(created["plan"]["seriesPlanRef"].startswith("series-plan-"))
        self.assertTrue(version["seriesPlanVersionRef"].startswith("series-plan-version-"))
        self.assertTrue(all("episodePlanItemRef" in item for item in version["episodePlanItems"]))
        self.assertTrue(all("episodeRef" not in item for item in version["episodePlanItems"]))
        self.assertEqual(series_boundary.list_series(WORKSPACE)[0]["episodes"], [])
        owner_path = Path(inspect.getfile(SeriesPlanningPublicBoundary)).resolve()
        self.assertIn("v5_core_os", owner_path.parts)
        self.assertNotIn("apps", owner_path.parts)

    def test_m6_bridge_preserves_lineage_and_contains_no_display_name_lookup(self):
        _, _, planning, series, project = create_context()
        created = confirm(planning, series, project)
        bridge = planning.build_m6_bootstrap(WORKSPACE, project["projectRef"], series["seriesRef"])
        self.assertEqual(bridge["schemaVersion"], "creator.series-plan.m6-bootstrap.v1")
        self.assertEqual(bridge["projectRef"], project["projectRef"])
        self.assertEqual(bridge["seriesRef"], series["seriesRef"])
        self.assertEqual(bridge["seriesPlanRef"], created["plan"]["seriesPlanRef"])
        self.assertEqual(bridge["seriesPlanVersionRef"], created["version"]["seriesPlanVersionRef"])
        self.assertNotIn("projectTitle", bridge)
        self.assertNotIn("seriesTitle", bridge)

    def test_application_uses_public_v5_boundary_and_v4_provider_port_only(self):
        server = SERVER.read_text(encoding="utf-8")
        application = APPLICATION.read_text(encoding="utf-8")
        self.assertIn("from services.v5_core_os.series_planning import", server)
        self.assertNotIn("series_planning.foundation", server)
        self.assertNotIn("SqliteSeriesPlanningAdapter", server)
        self.assertIn("from services.v4_platform import", application)
        v5_sources = "".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "services" / "v5_core_os" / "series_planning").glob("*.py")
        )
        self.assertNotIn("services.v4_platform", v5_sources)
        self.assertNotIn("DeepSeek", v5_sources)

    def test_browser_uses_same_origin_application_endpoint_without_provider_authority(self):
        browser = BROWSER.read_text(encoding="utf-8")
        self.assertIn('const seriesPlanningEndpoint = "/creator/internal/series-planning"', browser)
        self.assertIn("seriesPlanningGenerateEndpoint", browser)
        self.assertIn("seriesPlanningConfirmEndpoint", browser)
        self.assertNotIn("api.deepseek.com", browser)
        self.assertNotIn("Authorization", browser)
        self.assertNotIn("episodeRef: item.episodePlanItemRef", browser)

    def test_provider_failure_contract_exposes_only_safe_schema_diagnostics(self):
        server = SERVER.read_text(encoding="utf-8")
        block = server.split("def _send_series_director_product_error", 1)[1].split(
            "def _log_provider_error", 1
        )[0]
        self.assertIn('"validationIssues": issues', block)
        self.assertIn('for field, rule, _category in exc.validation_issues', block)
        for forbidden in ("raw provider", "Authorization", "PROVIDER_API_KEY", "response_body"):
            if forbidden == "raw provider":
                self.assertIn("Raw provider output", block)
            else:
                self.assertNotIn(forbidden, block)


if __name__ == "__main__":
    unittest.main()
