import json
from hashlib import sha256
import secrets
import threading
import unittest
from urllib import error, parse, request

from pathlib import Path
import tempfile

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production import (
    create_in_memory_boundary,
)
from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    V4CompositionExecutor,
)
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command,
    g3_command,
    g4_command,
    g5_command,
    g6_approval_authority,
    g6_finalize_command,
    g6_preview_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


class CreatorEpisodeProductionK2HttpTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = tempfile.TemporaryDirectory()
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(
            self.assembly, self.project, self.series
        )
        self.media_execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            DeterministicLocalFfmpegAdapter(),
            Path(self.artifacts.name),
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T01:00:00Z",
        )
        self.production = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            media_execution=self.media_execution,
            composition_execution=V4CompositionExecutor.from_artifact_root(
                Path(self.artifacts.name)
            ),
            approval_authority=g6_approval_authority(
                "episode-production-run-k2-1"
            ),
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
        self.artifacts.cleanup()

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

    def get_bytes(self, path):
        req = request.Request(
            f"{self.base}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()

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

    def test_public_g2_authority_identity_route_is_scoped_and_replay_safe(self):
        public_run_command = {
            key: value
            for key, value in run_command(
                self.project, self.series, self.episode
            ).items()
            if key != "workspaceRef"
        }
        _, created = self.post(
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run_command
        )
        run = created["run"]
        public_g2_command = {
            key: value
            for key, value in g2_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        endpoint = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}/authority-identity"
        )
        status, result = self.post(endpoint, public_g2_command)
        self.assertEqual(status, 201)
        self.assertEqual(result["state"], "AUTHORITY_READY")
        self.assertFalse(result["idempotentReplay"])
        self.assertEqual(result["authorityDecision"]["decision"], "AUTHORIZED")
        self.assertEqual(result["identityLock"]["state"], "LOCKED")

        status, replay = self.post(endpoint, public_g2_command)
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            replay["identityLock"]["identityLockRef"],
            result["identityLock"]["identityLockRef"],
        )

        status, detail = self.get(endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(
            detail["authorityDecision"]["authorityDecisionRef"],
            result["authorityDecision"]["authorityDecisionRef"],
        )
        status, projected = self.get(
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(projected["run"]["state"], "AUTHORITY_READY")

        with self.assertRaises(error.HTTPError) as forbidden_scope:
            self.post(endpoint, {**public_g2_command, "workspaceRef": WORKSPACE})
        self.assertEqual(forbidden_scope.exception.code, 400)
        payload = json.loads(forbidden_scope.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "client_workspace_scope_forbidden")

        with self.assertRaises(error.HTTPError) as forbidden_run:
            self.post(
                endpoint,
                {**public_g2_command, "productionRunRef": run["productionRunRef"]},
            )
        self.assertEqual(forbidden_run.exception.code, 400)
        payload = json.loads(forbidden_run.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_public_g3_shot_graph_route_is_scoped_and_replay_safe(self):
        public_run = {
            key: value
            for key, value in run_command(
                self.project, self.series, self.episode
            ).items()
            if key != "workspaceRef"
        }
        _, created = self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run)
        run = created["run"]
        authority_endpoint = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}/authority-identity"
        )
        authority_command = {
            key: value for key, value in g2_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        self.post(authority_endpoint, authority_command)

        endpoint = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}/shot-graph"
        )
        command = {
            key: value for key, value in g3_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, result = self.post(endpoint, command)
        self.assertEqual(status, 201)
        self.assertEqual(result["state"], "SHOTS_COMPILED")
        self.assertEqual(result["executableShotGraph"]["output"]["totalFrames"], 720)

        status, replay = self.post(endpoint, command)
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        status, restored = self.get(endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(
            restored["executableShotGraph"]["payloadDigest"],
            result["executableShotGraph"]["payloadDigest"],
        )

        with self.assertRaises(error.HTTPError) as caught:
            self.post(endpoint, {**command, "productionRunRef": run["productionRunRef"]})
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_public_g4_asset_plan_has_no_fabricated_provider_success(self):
        public_run = {
            key: value for key, value in run_command(
                self.project, self.series, self.episode
            ).items() if key != "workspaceRef"
        }
        _, created = self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run)
        run = created["run"]
        base = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}"
        )
        self.post(
            f"{base}/authority-identity",
            {key: value for key, value in g2_command(run).items()
             if key not in {"workspaceRef", "productionRunRef"}},
        )
        self.post(
            f"{base}/shot-graph",
            {key: value for key, value in g3_command(run).items()
             if key not in {"workspaceRef", "productionRunRef"}},
        )
        command = {
            key: value for key, value in g4_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, result = self.post(f"{base}/assets", command)
        self.assertEqual(status, 201)
        self.assertEqual(result["state"], "ASSETS_READY")
        self.assertEqual(len(result["generationRequests"]), 8)
        self.assertTrue(all(
            item["providerSelection"] == "UNSELECTED"
            for item in result["generationRequests"]
        ))
        status, restored = self.get(f"{base}/assets")
        self.assertEqual(status, 200)
        self.assertEqual(
            restored["assetResolutionManifest"]["payloadDigest"],
            result["assetResolutionManifest"]["payloadDigest"],
        )

    def test_public_g5_executes_real_local_evidence_without_exposing_paths(self):
        public_run = {
            key: value for key, value in run_command(
                self.project, self.series, self.episode
            ).items() if key != "workspaceRef"
        }
        _, created = self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run)
        run = created["run"]
        base = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}"
        )
        for resource, command in (
            ("authority-identity", g2_command(run)),
            ("shot-graph", g3_command(run)),
            ("assets", g4_command(run)),
        ):
            self.post(
                f"{base}/{resource}",
                {key: value for key, value in command.items()
                 if key not in {"workspaceRef", "productionRunRef"}},
            )
        command = {
            key: value for key, value in g5_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, result = self.post(f"{base}/media", command)
        self.assertEqual(status, 201)
        self.assertEqual(result["state"], "MEDIA_READY")
        self.assertEqual(len(result["assetVersions"]), 8)
        self.assertNotIn("internalPath", json.dumps(result, ensure_ascii=False))
        self.assertTrue(all(job["gpuUsed"] is False for job in result["jobs"]))
        status, restored = self.get(f"{base}/media")
        self.assertEqual(status, 200)
        self.assertEqual(
            restored["mediaManifest"]["payloadDigest"],
            result["mediaManifest"]["payloadDigest"],
        )

    def test_public_g6_preview_qc_approval_master_and_download_are_scoped(self):
        public_run = {
            key: value for key, value in run_command(
                self.project, self.series, self.episode
            ).items() if key != "workspaceRef"
        }
        _, created = self.post(PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run)
        run = created["run"]
        base = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}"
        )
        for resource, command in (
            ("authority-identity", g2_command(run)),
            ("shot-graph", g3_command(run)),
            ("assets", g4_command(run)),
            ("media", g5_command(run)),
        ):
            self.post(
                f"{base}/{resource}",
                {key: value for key, value in command.items()
                 if key not in {"workspaceRef", "productionRunRef"}},
            )
        preview_command = {
            key: value for key, value in g6_preview_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, preview = self.post(f"{base}/preview", preview_command)
        self.assertEqual(status, 201)
        self.assertEqual(preview["state"], "QC_READY")
        self.assertEqual(preview["qcReport"]["result"], "PASS")

        finalize_command = {
            key: value for key, value in g6_finalize_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, final = self.post(f"{base}/finalize", finalize_command)
        self.assertEqual(status, 201)
        self.assertEqual(final["state"], "MASTER_READY")
        self.assertNotIn("internalPath", json.dumps(final, ensure_ascii=False))

        status, delivery = self.get(f"{base}/delivery")
        self.assertEqual(status, 200)
        self.assertEqual(delivery["state"], "MASTER_READY")
        export = delivery["exportArtifact"]
        download = (
            f"{base}/exports/{parse.quote(export['exportArtifactRef'])}/content"
        )
        status, headers, content = self.get_bytes(download)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "video/mp4")
        self.assertEqual(len(content), export["byteSize"])
        self.assertEqual(sha256(content).hexdigest(), export["sha256"])

        with self.assertRaises(error.HTTPError) as caught:
            self.get(download, workspaceRef=WORKSPACE)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(
            payload["error"]["code"], "client_workspace_scope_forbidden"
        )


if __name__ == "__main__":
    unittest.main()
