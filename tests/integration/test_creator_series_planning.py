import json
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.server import (
    SERIES_PLANNING_CONFIRM_ENDPOINT,
    SERIES_PLANNING_ENDPOINT,
    SERIES_PLANNING_GENERATE_ENDPOINT,
    SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT,
    create_server,
)
from services.v4_platform import FakeTextProvider
from services.v5_core_os.project_engine import create_in_memory_boundary as create_project_boundary
from services.v5_core_os.series_episode import create_in_memory_boundary as create_series_boundary
from services.v5_core_os.series_planning import create_in_memory_boundary as create_planning_boundary
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-m5-http"
PROFILE = "content-profile-m5-http"


class CreatorSeriesPlanningHttpTests(unittest.TestCase):
    def setUp(self):
        self.series_boundary = create_series_boundary()
        self.project_boundary = create_project_boundary(self.series_boundary)
        self.planning_boundary = create_planning_boundary(self.project_boundary)
        self.series = self.series_boundary.create_series({
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": "晚灯",
            "plannedEpisodeCount": 4,
        })
        self.project = self.project_boundary.create_project({
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "projectType": "series",
            "seriesRef": self.series["seriesRef"],
            "title": "晚灯系列制作",
            "plannedEpisodeCount": 4,
        })
        self.provider = FakeTextProvider([json.dumps(valid_candidate(), ensure_ascii=False)])
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextProvider([])),
            series_episode_boundary=self.series_boundary,
            project_boundary=self.project_boundary,
            series_director_service=SeriesDirectorApplicationService(self.provider),
            series_planning_boundary=self.planning_boundary,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return request.urlopen(request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        ), timeout=15)

    def get(self, path):
        query = parse.urlencode({
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series["seriesRef"],
        })
        with request.urlopen(f"{self.base_url}{path}?{query}", timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def command(self, **extra):
        return {
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series["seriesRef"],
            **extra,
        }

    def test_real_http_flow_generates_candidate_then_confirms_authoritative_version(self):
        with self.post(SERIES_PLANNING_GENERATE_ENDPOINT, self.command(creativeInput="规划四集陪伴故事")) as response:
            self.assertEqual(response.status, 200)
            candidate_payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(candidate_payload["confirmationRequired"])
        self.assertEqual(len(self.provider.requests), 1)
        with self.post(
            SERIES_PLANNING_CONFIRM_ENDPOINT,
            self.command(humanConfirmed=True, candidate=candidate_payload["candidate"]),
        ) as response:
            self.assertEqual(response.status, 201)
            confirmed = json.loads(response.read().decode("utf-8"))
        self.assertEqual(
            confirmed["plan"]["confirmedSeriesPlanVersionRef"],
            confirmed["version"]["seriesPlanVersionRef"],
        )
        status, workspace = self.get(SERIES_PLANNING_ENDPOINT)
        self.assertEqual(status, 200)
        self.assertEqual(len(workspace["workspace"]["versions"]), 1)
        self.assertEqual(self.series_boundary.list_series(WORKSPACE)[0]["episodes"], [])

    def test_m6_bootstrap_is_zero_provider_deterministic_projection(self):
        self.planning_boundary.confirm_candidate(self.command(
            humanConfirmed=True, candidate=valid_candidate()
        ))
        before = len(self.provider.requests)
        _, first = self.get(SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT)
        _, second = self.get(SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT)
        self.assertEqual(first, second)
        self.assertEqual(len(self.provider.requests), before)
        self.assertEqual(first["bootstrap"]["projectRef"], self.project["projectRef"])

    def test_invalid_candidate_returns_structured_4xx_without_partial_plan(self):
        invalid = valid_candidate()
        invalid["episodePlanItems"] = invalid["episodePlanItems"][:-1]
        try:
            self.post(SERIES_PLANNING_CONFIRM_ENDPOINT, self.command(humanConfirmed=True, candidate=invalid))
        except error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            payload = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "invalid_request")
        else:
            self.fail("invalid candidate unexpectedly persisted")
        _, workspace = self.get(SERIES_PLANNING_ENDPOINT)
        self.assertIsNone(workspace["workspace"]["plan"])

    def test_generate_rejects_wrong_project_series_scope_before_provider_call(self):
        wrong = self.command(seriesRef="series-missing", creativeInput="规划")
        try:
            self.post(SERIES_PLANNING_GENERATE_ENDPOINT, wrong)
        except error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
        else:
            self.fail("wrong scope unexpectedly generated")
        self.assertEqual(len(self.provider.requests), 0)

if __name__ == "__main__":
    unittest.main()
