import json
import secrets
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_contract import (
    CAPABILITIES_ENDPOINT,
    PUBLIC_AI_DIRECTOR_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_M6_BIBLE_VERSION_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT,
    PUBLIC_SCRIPT_CONFIRM_ENDPOINT,
    PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
    PUBLIC_SERIES_INTELLIGENCE_WORKSPACE_ENDPOINT,
)
from apps.creator_workspace_mvp import public_contract
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.script_studio import ScriptStudioApplicationService
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_script_studio_m3 import script_candidate


WORKSPACE = "workspace-public-v1"
PROFILE = "content-profile-public-v1"


class CreatorPublicHttpV1IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assembly = LifecycleAssembly.in_memory()
        capability = FakeTextGenerationCapability(
            [json.dumps(valid_plan(), ensure_ascii=False)]
        )
        self.token = secrets.token_urlsafe(48)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(capability),
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_service=ScriptStudioApplicationService(capability),
            script_studio_boundary=self.assembly.script_studio,
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token, WORKSPACE
            ),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def get(self, path, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        req = request.Request(
            f"{self.base_url}{path}{suffix}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with request.urlopen(
            request.Request(
                f"{self.base_url}{path}",
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
            ),
            timeout=5,
        ) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_capability_projection_is_public_and_truthful(self):
        status, payload = self.get(CAPABILITIES_ENDPOINT)
        self.assertEqual(status, 200)
        self.assertEqual(payload["schemaVersion"], "creator.public.capabilities.v1")
        self.assertEqual(len(payload["capabilities"]), 19)
        self.assertEqual(payload["capabilities"][5]["state"], "authority_required")
        self.assertEqual(
            payload["capabilities"][6]["state"], "local_evidence_only"
        )
        self.assertEqual(
            payload["capabilities"][9]["state"], "local_evidence_only"
        )
        self.assertEqual(payload["capabilities"][15]["state"], "not_open")

    def test_m1_candidate_and_m2_m4_project_flow_use_public_routes(self):
        status, candidate = self.post(
            PUBLIC_AI_DIRECTOR_ENDPOINT, {"brief": valid_brief()}
        )
        self.assertEqual(status, 200)
        self.assertTrue(candidate["ok"])
        self.assertTrue(candidate["confirmationRequired"])
        self.assertTrue(
            candidate["sourcePlanRef"].startswith("ai-director-candidate-")
        )
        self.assertEqual(candidate["sourcePlanVersion"], 1)
        self.assertNotIn("projectId", candidate)

        status, series_payload = self.post(
            PUBLIC_SERIES_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "title": "Public Series",
                "description": "Created through public v1",
                "plannedEpisodeCount": 6,
            },
        )
        self.assertEqual(status, 201)
        series = series_payload["series"]

        status, confirmation_payload = self.post(
            PUBLIC_CONFIRM_PLAN_ENDPOINT,
            {
                "humanConfirmed": True,
                "brief": valid_brief(),
                "plan": candidate["plan"],
                "sourcePlanRef": candidate["sourcePlanRef"],
                "sourcePlanVersion": candidate["sourcePlanVersion"],
            },
        )
        self.assertEqual(status, 201)
        confirmed_plan = confirmation_payload["confirmedPlan"]
        self.assertEqual(
            confirmed_plan["sourcePlanRef"], candidate["sourcePlanRef"]
        )

        status, episode_payload = self.post(
            PUBLIC_EPISODES_ENDPOINT,
            {
                "seriesRef": series["seriesRef"],
                "creativePlanRef": confirmed_plan["creativePlanRef"],
                "episodeNumber": 1,
                "seasonNumber": 1,
                "volumeNumber": 1,
                "title": "Public Episode",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            episode_payload["episode"]["creativePlanRef"],
            confirmed_plan["creativePlanRef"],
        )

        status, project_payload = self.post(
            PUBLIC_PROJECTS_ENDPOINT,
            {
                "contentProfileRef": PROFILE,
                "projectType": "series",
                "seriesRef": series["seriesRef"],
                "title": "Public Project",
                "description": "Authoritative project context",
                "targetPlatform": "streaming",
                "aspectRatio": "16:9",
                "plannedEpisodeCount": 6,
            },
        )
        self.assertEqual(status, 201)
        project = project_payload["project"]
        status, listed = self.get(PUBLIC_PROJECTS_ENDPOINT)
        self.assertEqual(status, 200)
        self.assertEqual(listed["projects"][0]["projectRef"], project["projectRef"])

        status, detail = self.get(
            f"{PUBLIC_PROJECTS_ENDPOINT}/{parse.quote(project['projectRef'])}",
        )
        self.assertEqual(status, 200)
        self.assertEqual(detail["project"]["seriesRefs"], [series["seriesRef"]])

    def test_m6_public_routes_preserve_default_authority_failure(self):
        for method, path, payload in (
            (
                "GET",
                PUBLIC_SERIES_INTELLIGENCE_WORKSPACE_ENDPOINT
                + "?"
                + parse.urlencode(
                    {
                        "projectRef": "project-missing",
                        "seriesRef": "series-missing",
                    }
                ),
                None,
            ),
            (
                "POST",
                PUBLIC_M6_BIBLE_VERSION_ENDPOINT,
                {
                    "projectRef": "project-missing",
                    "seriesRef": "series-missing",
                    "operationRef": "m6-public-test",
                    "idempotencyKey": "m6-public-test",
                    "content": {},
                },
            ),
        ):
            body = (
                json.dumps(payload).encode("utf-8")
                if payload is not None
                else None
            )
            req = request.Request(
                f"{self.base_url}{path}",
                data=body,
                method=method,
                headers={
                    **({"Content-Type": "application/json"} if body else {}),
                    "Authorization": f"Bearer {self.token}",
                },
            )
            with self.subTest(method=method), self.assertRaises(error.HTTPError) as caught:
                request.urlopen(req, timeout=5)
            response = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(caught.exception.code, 403)
            self.assertEqual(response["error"]["code"], "authority_unavailable")

    def test_reviewed_import_is_service_credential_bound_with_unverified_digest_assertions(self):
        series = self.assembly.series_episode.create_series(
            {
                "workspaceRef": WORKSPACE,
                "contentProfileRef": PROFILE,
                "title": "Reviewed Import Series",
                "plannedEpisodeCount": 1,
            }
        )
        plan = self.assembly.series_episode.confirm_creative_plan(
            {
                "workspaceRef": WORKSPACE,
                "humanConfirmed": True,
                "sourcePlanRef": "reviewed-import-source-plan",
                "sourcePlanSchemaVersion": "creator.ai-director.plan.v1",
                "sourcePlanVersion": 1,
                "brief": valid_brief(),
                "sourcePlan": valid_plan(),
            }
        )
        episode = self.assembly.series_episode.create_episode(
            {
                "workspaceRef": WORKSPACE,
                "seriesRef": series["seriesRef"],
                "creativePlanRef": plan["creativePlanRef"],
                "episodeNumber": 1,
                "title": "Reviewed Import Episode",
            }
        )
        candidate = script_candidate()
        content = {
            key: candidate[key]
            for key in (
                "title",
                "logline",
                "synopsis",
                "targetDurationSec",
                "scenes",
            )
        }
        command = {
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "uploadedSourceByteDigest": "a" * 64,
            "normalizedSourceDocumentDigest": "b" * 64,
            "reviewedDocumentDigest": "c" * 64,
            "content": content,
        }
        for forged_field, forged_value in (
            ("importedByRef", "client-actor"),
            ("humanConfirmed", True),
            ("reviewApprovalRef", "client-approval"),
            ("canonicalScriptContentDigest", "d" * 64),
        ):
            with self.subTest(forged_field=forged_field), self.assertRaises(
                error.HTTPError
            ) as caught:
                self.post(
                    PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT,
                    {**command, forged_field: forged_value},
                )
            self.assertEqual(caught.exception.code, 400)
            failure = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(failure["error"]["code"], "invalid_request")

        forged_scene_command = json.loads(json.dumps(command, ensure_ascii=False))
        forged_scene_command["content"]["scenes"][0][
            "scriptSceneRef"
        ] = "k2-001-reused-scene"
        with self.assertRaises(error.HTTPError) as caught:
            self.post(PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT, forged_scene_command)
        self.assertEqual(caught.exception.code, 400)

        status, imported = self.post(
            PUBLIC_SCRIPT_REVIEWED_IMPORT_ENDPOINT, command
        )
        self.assertEqual(status, 201)
        self.assertIsNone(imported["script"]["confirmedScriptVersionRef"])
        provenance = imported["scriptVersion"]["importProvenance"]
        self.assertEqual(provenance["uploadedSourceByteDigest"], "a" * 64)
        self.assertEqual(
            provenance["normalizedSourceDocumentDigest"], "b" * 64
        )
        self.assertEqual(provenance["reviewedDocumentDigest"], "c" * 64)
        self.assertEqual(provenance["importedByRef"], "runtime-test-credential")
        self.assertEqual(
            provenance["digestAssertionState"],
            "AUTHENTICATED_SERVICE_CREDENTIAL_DECLARATION_UNVERIFIED",
        )
        self.assertEqual(
            provenance["reviewedDocumentToContentBindingState"], "NOT_VERIFIED"
        )
        self.assertRegex(
            provenance["canonicalScriptContentDigest"], r"^[0-9a-f]{64}$"
        )
        self.assertRegex(
            provenance["importProvenanceDigest"], r"^[0-9a-f]{64}$"
        )

        with self.assertRaises(error.HTTPError) as caught:
            self.post(
                PUBLIC_SCRIPT_CONFIRM_ENDPOINT,
                {
                    "seriesRef": series["seriesRef"],
                    "episodeRef": episode["episodeRef"],
                    "scriptRef": imported["script"]["scriptRef"],
                    "scriptVersionRef": imported["scriptVersion"][
                        "scriptVersionRef"
                    ],
                    "humanConfirmed": True,
                },
            )
        self.assertEqual(caught.exception.code, 403)
        blocked = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(blocked["error"]["code"], "trusted_approval_required")

    def test_unknown_public_route_is_stable_404(self):
        with self.assertRaises(error.HTTPError) as caught:
            self.get("/creator/api/v1/not-a-resource")
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(payload["error"]["code"], "not_found")
        self.assertIsInstance(payload["error"]["message"], str)
        self.assertTrue(payload["error"]["message"])

    def test_every_declared_public_endpoint_requires_authentication(self):
        declared = sorted(
            {
                value
                for name, value in vars(public_contract).items()
                if isinstance(value, str)
                and (
                    name == "CAPABILITIES_ENDPOINT"
                    or (name.startswith("PUBLIC_") and name.endswith("_ENDPOINT"))
                )
            }
        )
        self.assertEqual(len(declared), 29)
        for path in declared:
            with self.subTest(path=path), self.assertRaises(error.HTTPError) as caught:
                request.urlopen(f"{self.base_url}{path}", timeout=5)
            self.assertEqual(caught.exception.code, 401)
            self.assertEqual(caught.exception.headers["WWW-Authenticate"], "Bearer")
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "authentication_required")

    def test_invalid_token_is_indistinguishable_from_missing_token(self):
        errors = []
        for headers in ({}, {"Authorization": "Bearer invalid-runtime-token"}):
            req = request.Request(
                f"{self.base_url}{CAPABILITIES_ENDPOINT}", headers=headers
            )
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(req, timeout=5)
            errors.append(
                (
                    caught.exception.code,
                    json.loads(caught.exception.read().decode("utf-8")),
                )
            )
        self.assertEqual(errors[0], errors[1])

    def test_public_clients_cannot_supply_workspace_scope(self):
        req = request.Request(
            f"{self.base_url}{PUBLIC_PROJECTS_ENDPOINT}?workspaceRef=forged",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(
            payload["error"]["code"], "client_workspace_scope_forbidden"
        )

        with self.assertRaises(error.HTTPError) as caught:
            self.post(
                PUBLIC_PROJECTS_ENDPOINT,
                {
                    "workspaceRef": "forged",
                    "contentProfileRef": PROFILE,
                    "projectType": "series",
                },
            )
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual(
            payload["error"]["code"], "client_workspace_scope_forbidden"
        )

    def test_health_is_liveness_only_and_core_remains_no_cors(self):
        with request.urlopen(f"{self.base_url}/health", timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
            self.assertEqual(
                json.loads(response.read().decode("utf-8")),
                {"ok": True, "status": "alive"},
            )

        status, _ = self.get(CAPABILITIES_ENDPOINT)
        self.assertEqual(status, 200)

    def test_public_only_server_hides_internal_compatibility_routes(self):
        req = request.Request(
            f"{self.base_url}/creator/internal/projects?workspaceRef={WORKSPACE}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with self.assertRaises(error.HTTPError) as caught:
            request.urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
