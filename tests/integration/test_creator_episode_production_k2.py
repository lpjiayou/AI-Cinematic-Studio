import json
import secrets
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production import create_in_memory_boundary
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    run_command,
    seed_k2_roots,
)


class CreatorEpisodeProductionK2HttpTests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots()
        self.production = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T00:05:00Z",
        )
        self.token = secrets.token_urlsafe(48)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            episode_production_boundary=self.production,
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token, WORKSPACE
            ),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, payload, *, token=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            f"{self.base}{path}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def get(self, path, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        req = request.Request(
            f"{self.base}{path}{suffix}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_public_run_create_replay_list_and_detail(self):
        public_command = {
            key: value
            for key, value in run_command(
                self.project, self.series, self.episode
            ).items()
            if key != "workspaceRef"
        }
        status, created = self.post(
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_command
        )
        self.assertEqual(status, 201)
        run = created["run"]
        self.assertEqual(run["state"], "ROOTS_READY")
        self.assertFalse(run["idempotentReplay"])

        status, replay = self.post(
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_command
        )
        self.assertEqual(status, 200)
        self.assertTrue(replay["run"]["idempotentReplay"])
        self.assertEqual(
            replay["run"]["productionRunRef"], run["productionRunRef"]
        )

        status, listed = self.get(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT)
        self.assertEqual(status, 200)
        self.assertEqual([item["productionRunRef"] for item in listed["runs"]], [run["productionRunRef"]])
        status, detail = self.get(
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/{parse.quote(run['productionRunRef'])}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(detail["run"]["payloadDigest"], run["payloadDigest"])

    def test_public_run_rejects_client_workspace_and_unbound_upstream(self):
        unbound, _, project, series, episode, _ = seed_k2_roots(bind_episode=False)
        self.production = create_in_memory_boundary(
            project_boundary=unbound.project_context,
            series_episode_boundary=unbound.series_episode,
            series_planning_boundary=unbound.series_planning,
            script_studio_boundary=unbound.script_studio,
        )
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=unbound.series_episode,
            project_boundary=unbound.project_context,
            series_planning_boundary=unbound.series_planning,
            series_intelligence_boundary=unbound.series_intelligence,
            script_studio_boundary=unbound.script_studio,
            episode_production_boundary=self.production,
            public_authenticator=PublicApiAuthenticator.for_token(self.token, WORKSPACE),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        command = run_command(project, series, episode)
        with self.assertRaises(error.HTTPError) as caught:
            self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, command)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "client_workspace_scope_forbidden")

        command.pop("workspaceRef")
        with self.assertRaises(error.HTTPError) as caught:
            self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, command)
        self.assertEqual(caught.exception.code, 409)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "upstream_not_confirmed")


if __name__ == "__main__":
    unittest.main()
