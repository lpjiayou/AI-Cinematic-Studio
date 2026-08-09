import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.server import (
    CONFIRM_PLAN_ENDPOINT,
    EPISODES_ENDPOINT,
    SERIES_ENDPOINT,
    create_server,
)
from services.v4_platform import FakeTextProvider
from services.v5_core_os.series_episode import SeriesEpisodePublicBoundary
from services.v5_core_os.series_episode.foundation import (
    InMemorySeriesEpisodeAdapter,
    SeriesEpisodeService,
    SqliteSeriesEpisodeAdapter,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "creator-workspace-mvp"
WORKSPACE = "workspace-http"
PROFILE = "content-profile-http"


class CreatorSeriesEpisodeHttpTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemorySeriesEpisodeAdapter()
        self.boundary = SeriesEpisodePublicBoundary(SeriesEpisodeService(self.repository))
        self.provider = FakeTextProvider([])
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(self.provider),
            APP_ROOT,
            series_episode_boundary=self.boundary,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return request.urlopen(
            request.Request(
                f"{self.base_url}{path}",
                data=body,
                method="POST",
                headers={"Content-Type": "application/json"},
            ),
            timeout=5,
        )

    def get_json(self, path, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        with request.urlopen(f"{self.base_url}{path}{suffix}", timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def create_series(self, **overrides):
        payload = {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "Wanlight",
            "description": "Series",
            "plannedEpisodeCount": 12,
        }
        payload.update(overrides)
        with self.post(SERIES_ENDPOINT, payload) as response:
            return json.loads(response.read().decode("utf-8"))["series"]

    def confirm_plan(self, **overrides):
        payload = {
            "workspaceRef": WORKSPACE,
            "humanConfirmed": True,
            "brief": valid_brief(),
            "plan": valid_plan(),
            "sourcePlanRef": "ai-director-plan-live-1",
            "sourcePlanVersion": 1,
        }
        payload.update(overrides)
        with self.post(CONFIRM_PLAN_ENDPOINT, payload) as response:
            return json.loads(response.read().decode("utf-8"))["confirmedPlan"]

    def create_episode(self, series, plan, **overrides):
        payload = {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "creativePlanRef": plan["creativePlanRef"],
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Episode 001",
        }
        payload.update(overrides)
        with self.post(EPISODES_ENDPOINT, payload) as response:
            return json.loads(response.read().decode("utf-8"))["episode"]

    def test_post_series_returns_v5_owned_workspace_scoped_record(self):
        series = self.create_series()
        self.assertEqual(series["workspaceRef"], WORKSPACE)
        self.assertEqual(series["contentProfileRef"], PROFILE)
        self.assertTrue(series["schemaVersion"].startswith("v5.series."))

    def test_content_profile_is_accepted_as_opaque_upstream_ref(self):
        series = self.create_series(contentProfileRef="opaque-profile-ref")
        self.assertEqual(series["contentProfileRef"], "opaque-profile-ref")

    def test_confirmation_then_episode_creation_preserves_lineage(self):
        series = self.create_series()
        plan = self.confirm_plan()
        episode = self.create_episode(series, plan)
        self.assertEqual(episode["seriesRef"], series["seriesRef"])
        self.assertEqual(episode["sourcePlanRef"], plan["sourcePlanRef"])
        self.assertIsNone(episode["canonicalProjectRef"])

    def test_series_read_model_is_workspace_scoped_and_nests_episode(self):
        series = self.create_series()
        episode = self.create_episode(series, self.confirm_plan())
        status, payload = self.get_json(SERIES_ENDPOINT, workspaceRef=WORKSPACE)
        self.assertEqual(status, 200)
        self.assertEqual(payload["series"][0]["episodes"][0]["episodeRef"], episode["episodeRef"])

    def test_episode_detail_requires_full_series_scope_and_preserves_source_plan(self):
        series = self.create_series()
        episode = self.create_episode(series, self.confirm_plan())
        status, payload = self.get_json(
            f"{EPISODES_ENDPOINT}/{episode['episodeRef']}",
            workspaceRef=WORKSPACE,
            seriesRef=series["seriesRef"],
        )
        self.assertEqual(status, 200)
        binding = payload["episode"]["confirmedPlanBinding"]
        self.assertEqual(binding["sourcePlanSchemaVersion"], "creator.ai-director.plan.v1")
        self.assertEqual(binding["sourcePlan"], valid_plan())

    def test_wrong_series_scope_cannot_read_episode(self):
        series = self.create_series()
        episode = self.create_episode(series, self.confirm_plan())
        with self.assertRaises(error.HTTPError) as context:
            self.get_json(
                f"{EPISODES_ENDPOINT}/{episode['episodeRef']}",
                workspaceRef=WORKSPACE,
                seriesRef="series-other",
            )
        self.assertEqual(context.exception.code, 404)

    def test_script_studio_bridge_reads_binding_without_provider(self):
        series = self.create_series()
        episode = self.create_episode(series, self.confirm_plan())
        status, payload = self.get_json(
            f"{EPISODES_ENDPOINT}/{episode['episodeRef']}/script-studio-bootstrap",
            workspaceRef=WORKSPACE,
            seriesRef=series["seriesRef"],
        )
        self.assertEqual(status, 200)
        bootstrap = payload["bootstrap"]
        self.assertEqual(bootstrap["schemaVersion"], "creator.script-studio.bootstrap-input.v1")
        self.assertEqual(bootstrap["storyboardPlan"], valid_plan()["storyboardPlan"])
        self.assertEqual(bootstrap["sourcePlanVersion"], 1)

    def test_story_projection_source_chain_reads_episode_binding_without_provider(self):
        series = self.create_series()
        confirmed = self.confirm_plan()
        episode = self.create_episode(series, confirmed)
        status, payload = self.get_json(
            f"{EPISODES_ENDPOINT}/{episode['episodeRef']}",
            workspaceRef=WORKSPACE,
            seriesRef=series["seriesRef"],
        )
        self.assertEqual(status, 200)
        loaded = payload["episode"]
        binding = loaded["confirmedPlanBinding"]
        self.assertEqual(loaded["seriesRef"], series["seriesRef"])
        self.assertEqual(loaded["episodeRef"], episode["episodeRef"])
        self.assertEqual(binding["sourcePlanRef"], confirmed["sourcePlanRef"])
        self.assertEqual(binding["sourcePlanSchemaVersion"], "creator.ai-director.plan.v1")
        self.assertEqual(binding["sourcePlanVersion"], 1)
        self.assertEqual(binding["sourcePlan"]["storyDirection"], valid_plan()["storyDirection"])
        self.assertEqual(binding["sourcePlan"]["creativeInterpretation"], valid_plan()["creativeInterpretation"])
        self.assertEqual(binding["sourcePlan"]["productionPlan"], valid_plan()["productionPlan"])
        self.assertEqual(self.provider.requests, [])

    def test_unconfirmed_plan_ref_is_rejected_with_stable_json_error(self):
        series = self.create_series()
        with self.assertRaises(error.HTTPError) as context:
            self.create_episode(series, {"creativePlanRef": "missing"})
        payload = json.loads(context.exception.read().decode("utf-8"))
        self.assertEqual(context.exception.code, 409)
        self.assertEqual(payload["error"]["code"], "creative_plan_not_confirmed")

    def test_episode_without_series_is_rejected_without_orphan(self):
        plan = self.confirm_plan()
        with self.assertRaises(error.HTTPError) as context:
            self.post(EPISODES_ENDPOINT, {
                "workspaceRef": WORKSPACE,
                "seriesRef": "series-missing",
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Orphan",
            })
        self.assertEqual(context.exception.code, 404)
        self.assertEqual(self.repository.list_episodes(), [])

    def test_ui_cannot_submit_canonical_project_binding_during_m2(self):
        series = self.create_series()
        plan = self.confirm_plan()
        with self.assertRaises(error.HTTPError) as context:
            self.create_episode(series, plan, canonicalProjectRef="ui-project-id")
        self.assertEqual(context.exception.code, 400)

    def test_malformed_json_is_structured_and_static_get_still_works(self):
        bad = request.Request(
            f"{self.base_url}{SERIES_ENDPOINT}",
            data=b"{bad",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(error.HTTPError) as context:
            request.urlopen(bad, timeout=5)
        self.assertEqual(json.loads(context.exception.read().decode("utf-8"))["error"]["code"], "invalid_request")
        with request.urlopen(f"{self.base_url}/app.js", timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_responses_hide_provider_secret_and_storage_details(self):
        series = self.create_series()
        _, payload = self.get_json(
            f"{SERIES_ENDPOINT}/{series['seriesRef']}",
            workspaceRef=WORKSPACE,
        )
        serialized = json.dumps(payload)
        for forbidden in ("PROVIDER_API_KEY", "Authorization", "sqlite", "database_path"):
            self.assertNotIn(forbidden, serialized)


class CreatorSeriesEpisodeRestartIntegrationTests(unittest.TestCase):
    def test_http_visible_state_survives_v5_local_adapter_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v5-local-development.sqlite3"
            first_service = SeriesEpisodeService(SqliteSeriesEpisodeAdapter(path))
            series = first_service.create_series({
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": "Wanlight",
            })
            source = valid_plan()
            plan = first_service.confirm_creative_plan({
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "brief": valid_brief(),
                "sourcePlan": source,
                "sourcePlanRef": "source-plan-restart",
                "sourcePlanSchemaVersion": source["schemaVersion"],
                "sourcePlanVersion": 1,
            })
            episode = first_service.create_episode({
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Episode 001",
            })
            restarted = SeriesEpisodeService(SqliteSeriesEpisodeAdapter(path))
            loaded = restarted.get_episode(WORKSPACE, series["seriesRef"], episode["episodeRef"])
            self.assertEqual(loaded["confirmedPlanBinding"]["sourcePlanRef"], "source-plan-restart")


if __name__ == "__main__":
    unittest.main()
