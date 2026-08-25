import json
import secrets
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.script_studio import ScriptStudioApplicationService
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production import EpisodeProductionPublicError
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability


WORKSPACE = "workspace-dynamic-preflight-http"


class FakeEpisodeProductionBoundary:
    def preflight_dynamic_real_media_plan(self, command):
        if set(command) != {"workspaceRef", "productionRunRef"}:
            raise EpisodeProductionPublicError("invalid_request", 400)
        self.command = dict(command)
        return {
            "schemaVersion": "v5.k2-dynamic-image-preflight.v1",
            "workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"],
            "dispatchBlockers": [
                {
                    "blockerType": "M10_CANONICAL_APPEND_NOT_IMPLEMENTED",
                    "scope": "K2_002_IMAGE_PREFLIGHT",
                    "status": "BLOCKING",
                }
            ],
            "shotPlanInputAuthority": (
                "LOCAL_STRUCTURAL_REPRESENTATION / "
                "NOT APPROVED INPUT AUTHORITY"
            ),
            "integrationState": "PREFLIGHT_ONLY_NOT_INTEGRATED",
            "executionAuthorizationState": "PREFLIGHT_ONLY_NOT_AUTHORIZED",
            "canonicalMutation": False,
            "dispatchAllowed": False,
            "candidateAdmissionAllowed": False,
            "videoPlanState": "OUT_OF_SCOPE_NOT_BUILT",
            "audioPlanState": "OUT_OF_SCOPE_NOT_BUILT",
            "nextGate": "M10_REAL_IMAGE_PLAN_V2_CANONICAL_APPEND",
            "nextGateState": "BLOCKED",
            "publicationAllowed": False,
        }

    def _reject_legacy_mutation(self, command):
        self.blocked_command = dict(command)
        raise EpisodeProductionPublicError("execution_not_authorized", 409)

    def resolve_assets(self, command):
        return self._reject_legacy_mutation(command)

    def execute_media(self, command):
        return self._reject_legacy_mutation(command)

    def plan_real_images(self, command):
        return self._reject_legacy_mutation(command)


class CreatorDynamicMediaPreflightHttpTests(unittest.TestCase):
    def setUp(self):
        assembly = LifecycleAssembly.in_memory()
        capability = FakeTextGenerationCapability([])
        self.boundary = FakeEpisodeProductionBoundary()
        self.token = secrets.token_urlsafe(48)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(capability),
            series_episode_boundary=assembly.series_episode,
            project_boundary=assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(capability),
            series_planning_boundary=assembly.series_planning,
            series_intelligence_boundary=assembly.series_intelligence,
            script_studio_service=ScriptStudioApplicationService(capability),
            script_studio_boundary=assembly.script_studio,
            episode_production_boundary=self.boundary,
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token, WORKSPACE
            ),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.run_base = (
            f"http://127.0.0.1:{self.server.server_port}"
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/run-k2-002"
        )
        self.url = f"{self.run_base}/dynamic-media-preflight"

    def post(self, payload, *, url=None):
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.url if url is None else url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_authenticated_workspace_and_path_run_are_server_injected(self):
        status, payload = self.post({})
        self.assertEqual(status, 200)
        self.assertEqual(
            self.boundary.command,
            {"workspaceRef": WORKSPACE, "productionRunRef": "run-k2-002"},
        )
        preflight = payload["preflight"]
        self.assertFalse(preflight["canonicalMutation"])
        self.assertFalse(preflight["dispatchAllowed"])
        self.assertFalse(preflight["candidateAdmissionAllowed"])
        self.assertEqual(
            preflight["executionAuthorizationState"],
            "PREFLIGHT_ONLY_NOT_AUTHORIZED",
        )
        self.assertEqual(preflight["nextGateState"], "BLOCKED")
        self.assertEqual(
            preflight["integrationState"], "PREFLIGHT_ONLY_NOT_INTEGRATED"
        )

    def test_client_cannot_supply_workspace_run_graph_or_identity_authority(self):
        cases = (
            {"workspaceRef": "forged"},
            {"productionRunRef": "forged"},
            {"shotGraph": {}},
            {"identityLock": {}},
        )
        for payload in cases:
            body = json.dumps(payload).encode("utf-8")
            req = request.Request(
                self.url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
            )
            with self.subTest(payload=payload), self.assertRaises(
                error.HTTPError
            ) as caught:
                request.urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 400)
            response = json.loads(caught.exception.read().decode("utf-8"))
            self.assertIn(
                response["error"]["code"],
                {"client_workspace_scope_forbidden", "invalid_request"},
            )

    def test_public_legacy_mutation_routes_preserve_the_v2_block(self):
        for resource in ("assets", "media", "real-media-revision"):
            with self.subTest(resource=resource), self.assertRaises(
                error.HTTPError
            ) as caught:
                self.post(
                    {"idempotencyKey": f"blocked-{resource}"},
                    url=f"{self.run_base}/{resource}",
                )
            self.assertEqual(caught.exception.code, 409)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(
                payload["error"]["code"], "execution_not_authorized"
            )
            self.assertEqual(
                self.boundary.blocked_command,
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": "run-k2-002",
                    "idempotencyKey": f"blocked-{resource}",
                },
            )


if __name__ == "__main__":
    unittest.main()
