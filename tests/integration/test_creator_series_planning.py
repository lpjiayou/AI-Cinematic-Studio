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
    SERIES_PLANNING_MANUAL_VERSION_ENDPOINT,
    SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT,
    create_server,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation import TextGenerationPurpose
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-m5-http"
PROFILE = "content-profile-m5-http"


class CreatorSeriesPlanningHttpTests(unittest.TestCase):
    def setUp(self):
        self.assembly = LifecycleAssembly.in_memory()
        self.series_boundary = self.assembly.series_episode
        self.project_boundary = self.assembly.project_context
        self.planning_boundary = self.assembly.series_planning
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
        self.capability = FakeTextGenerationCapability([json.dumps(valid_candidate(), ensure_ascii=False)])
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.series_boundary,
            project_boundary=self.project_boundary,
            series_director_service=SeriesDirectorApplicationService(self.capability),
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
        self.assertEqual(len(self.capability.commands), 1)
        self.assertEqual(self.capability.commands[0].purpose, TextGenerationPurpose.SERIES_PLAN_CANDIDATE)
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
        before = len(self.capability.commands)
        _, first = self.get(SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT)
        _, second = self.get(SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT)
        self.assertEqual(first, second)
        self.assertEqual(len(self.capability.commands), before)
        self.assertEqual(first["bootstrap"]["projectRef"], self.project["projectRef"])

    def test_existing_workspace_http_passes_through_v2_while_manual_rejects_and_bootstrap_stays_v1(self):
        initial = self.planning_boundary.confirm_candidate(self.command(
            humanConfirmed=True, candidate=valid_candidate()
        ))
        bound = self.planning_boundary.create_episode_plan_item_binding_version({
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series["seriesRef"],
            "seriesPlanRef": initial["plan"]["seriesPlanRef"],
            "expectedPlanVersion": initial["plan"]["version"],
            "episodePlanItemBindings": [],
        })
        confirmed = self.planning_boundary.confirm_version({
            "workspaceRef": WORKSPACE,
            "seriesPlanRef": bound["plan"]["seriesPlanRef"],
            "seriesPlanVersionRef": bound["version"]["seriesPlanVersionRef"],
            "expectedPlanVersion": bound["plan"]["version"],
            "humanConfirmed": True,
        })

        status, workspace_payload = self.get(SERIES_PLANNING_ENDPOINT)
        self.assertEqual(status, 200)
        workspace = workspace_payload["workspace"]
        self.assertEqual(len(workspace["versions"]), 2)
        self.assertNotIn("episodePlanItemBindings", workspace["versions"][0])
        self.assertEqual(workspace["versions"][1]["schemaVersion"], "v5.series-plan-version.v2")
        self.assertEqual(workspace["versions"][1]["episodePlanItemBindings"], [])

        try:
            self.post(SERIES_PLANNING_MANUAL_VERSION_ENDPOINT, self.command(
                seriesPlanRef=confirmed["seriesPlanRef"],
                expectedPlanVersion=confirmed["version"],
                content={},
            ))
        except error.HTTPError as exc:
            self.assertEqual(exc.code, 409)
            error_payload = json.loads(exc.read().decode("utf-8"))
            self.assertEqual(error_payload["error"]["code"], "version_conflict")
        else:
            self.fail("manual v2 downgrade unexpectedly succeeded")
        _, after_rejection = self.get(SERIES_PLANNING_ENDPOINT)
        self.assertEqual(after_rejection["workspace"], workspace)

        _, bootstrap_payload = self.get(SERIES_PLANNING_M6_BOOTSTRAP_ENDPOINT)
        bootstrap = bootstrap_payload["bootstrap"]
        self.assertEqual(bootstrap["schemaVersion"], "creator.series-plan.m6-bootstrap.v1")
        self.assertNotIn("episodePlanItemBindings", bootstrap)
        self.assertEqual(
            set(bootstrap),
            {
                "schemaVersion", "workspaceRef", "contentProfileRef", "projectRef",
                "seriesRef", "seriesPlanRef", "seriesPlanVersionRef", "mainArcs",
                "episodePlanItems", "characterArcIntents", "worldIntent",
                "continuityIntent", "foreshadowingContext",
            },
        )

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
        self.assertEqual(len(self.capability.commands), 0)

if __name__ == "__main__":
    unittest.main()
