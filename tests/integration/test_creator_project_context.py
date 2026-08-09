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
    PROJECTS_ENDPOINT,
    PROJECT_CONTEXT_ENDPOINT,
    SERIES_ENDPOINT,
    create_server,
)
from services.v4_platform import FakeTextProvider
from services.v5_core_os.project_engine import (
    create_in_memory_boundary as create_project_boundary,
    create_local_development_boundary as create_local_project_boundary,
)
from services.v5_core_os.series_episode import (
    create_in_memory_boundary as create_series_boundary,
    create_local_development_boundary as create_local_series_boundary,
)
from services.v5_core_os.script_studio import create_in_memory_boundary as create_script_boundary
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "apps" / "creator-workspace-mvp"
WORKSPACE = "workspace-project-http"
PROFILE = "content-profile-project-http"


class CreatorProjectHttpTests(unittest.TestCase):
    def setUp(self):
        self.series_boundary = create_series_boundary()
        self.project_boundary = create_project_boundary(self.series_boundary)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextProvider([])),
            APP_ROOT,
            series_episode_boundary=self.series_boundary,
            project_boundary=self.project_boundary,
            script_studio_boundary=create_script_boundary(self.series_boundary),
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

    def get(self, path, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        with request.urlopen(f"{self.base_url}{path}{suffix}", timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def create_series(self):
        with self.post(
            SERIES_ENDPOINT,
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": "Wanlight",
                "plannedEpisodeCount": 12,
            },
        ) as response:
            return json.loads(response.read().decode("utf-8"))["series"]

    def create_project(self, series):
        with self.post(
            PROJECTS_ENDPOINT,
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": series["seriesRef"],
                "title": "Wanlight Production",
                "description": "Production context",
                "targetPlatform": "short-video",
                "aspectRatio": "9:16",
                "defaultDurationSec": 30,
                "plannedEpisodeCount": 12,
            },
        ) as response:
            self.assertEqual(response.status, 201)
            return json.loads(response.read().decode("utf-8"))["project"]

    def create_episode(self, series):
        plan_source = valid_plan()
        with self.post(
            CONFIRM_PLAN_ENDPOINT,
            {
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "brief": valid_brief(),
                "plan": plan_source,
                "sourcePlanRef": "source-plan-project-http",
                "sourcePlanVersion": 1,
            },
        ) as response:
            plan = json.loads(response.read().decode("utf-8"))["confirmedPlan"]
        with self.post(
            EPISODES_ENDPOINT,
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Episode 001",
            },
        ) as response:
            return json.loads(response.read().decode("utf-8"))["episode"]

    def test_create_list_read_and_context_endpoint_preserve_lineage(self):
        series = self.create_series()
        episode = self.create_episode(series)
        project = self.create_project(series)

        status, listed = self.get(PROJECTS_ENDPOINT, workspaceRef=WORKSPACE)
        self.assertEqual(status, 200)
        self.assertEqual(listed["projects"][0]["projectRef"], project["projectRef"])

        status, context = self.get(
            PROJECT_CONTEXT_ENDPOINT,
            workspaceRef=WORKSPACE,
            projectRef=project["projectRef"],
            seriesRef=series["seriesRef"],
            episodeRef=episode["episodeRef"],
        )
        self.assertEqual(status, 200)
        value = context["context"]
        self.assertEqual(value["projectRef"], project["projectRef"])
        self.assertEqual(value["seriesRef"], series["seriesRef"])
        self.assertEqual(value["episodeRef"], episode["episodeRef"])
        self.assertEqual(
            value["episode"]["confirmedPlanBinding"]["sourcePlanRef"],
            "source-plan-project-http",
        )

    def test_invalid_project_is_structured_4xx_without_partial_write(self):
        series = self.create_series()
        try:
            self.post(
                PROJECTS_ENDPOINT,
                {
                    "workspaceRef": WORKSPACE,
                    "contentProfileRef": "wrong-profile",
                    "projectType": "series",
                    "seriesRef": series["seriesRef"],
                    "title": "Invalid",
                },
            )
        except error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            payload = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "scope_mismatch")
        else:
            self.fail("invalid Project request unexpectedly succeeded")
        _, listed = self.get(PROJECTS_ENDPOINT, workspaceRef=WORKSPACE)
        self.assertEqual(listed["projects"], [])

    def test_linked_series_delete_is_blocked_to_prevent_orphan_project(self):
        series = self.create_series()
        self.create_project(series)
        url = (
            f"{self.base_url}{SERIES_ENDPOINT}/{parse.quote(series['seriesRef'])}"
            f"?{parse.urlencode({'workspaceRef': WORKSPACE})}"
        )
        try:
            request.urlopen(request.Request(url, method="DELETE"), timeout=5)
        except error.HTTPError as exc:
            self.assertEqual(exc.code, 409)
            payload = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "dependent_project_exists")
        else:
            self.fail("linked Series delete unexpectedly succeeded")

    def test_static_assets_continue_to_be_served(self):
        with request.urlopen(f"{self.base_url}/app.js", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"/creator/projects", response.read())


class CreatorProjectRestartTests(unittest.TestCase):
    def test_shared_local_database_preserves_project_series_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            series = create_local_series_boundary(path)
            series_record = series.create_series(
                {
                    "workspaceRef": WORKSPACE,
                    "contentProfileRef": PROFILE,
                    "title": "Persistent Series",
                    "plannedEpisodeCount": 4,
                }
            )
            project_boundary = create_local_project_boundary(path, series)
            project = project_boundary.create_project(
                {
                    "workspaceRef": WORKSPACE,
                    "contentProfileRef": PROFILE,
                    "projectType": "series",
                    "seriesRef": series_record["seriesRef"],
                    "title": "Persistent Project",
                }
            )
            restarted_series = create_local_series_boundary(path)
            restarted_projects = create_local_project_boundary(path, restarted_series)
            context = restarted_projects.build_context(WORKSPACE, project["projectRef"])
            self.assertEqual(context["projectRef"], project["projectRef"])
            self.assertEqual(context["seriesRef"], series_record["seriesRef"])
            self.assertEqual(context["series"]["seriesRef"], series_record["seriesRef"])


if __name__ == "__main__":
    unittest.main()
