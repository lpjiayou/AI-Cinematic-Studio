from __future__ import annotations

import json
import secrets
from pathlib import Path
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.script_studio import ScriptStudioApplicationService
from apps.creator_workspace_mvp.series_director import SeriesDirectorApplicationService
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production import EpisodeProductionPublicError
from services.v5_core_os.episode_production import create_in_memory_boundary
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v4_platform import InMemoryMediaJobAdapter, MediaJobCoordinator
from tests.integration.test_generic_upstream_method_closure import (
    GenericApprovalAuthority,
    GenericRefs,
    GenericScopeAuthority,
    NoCallVideoAdapter,
    append_generic_anchor,
    execution_plan_command,
    load_fixture,
    run_command,
    seed_generic_roots,
    validation_command,
)


WORKSPACE = "workspace-method-aware-http"
RUN = "run-method-aware-http"


class FakeMethodAwareBoundary:
    def __init__(self) -> None:
        self.commands: dict[str, dict] = {}

    def _result(self, resource: str, command: dict) -> dict:
        self.commands[resource] = dict(command)
        return {
            "schemaVersion": f"test.{resource}.v1",
            "idempotentReplay": False,
            "publicationAllowed": False,
        }

    def create_public_execution_method_plan(self, command):
        return self._result("execution-method-plan", command)

    def create_public_method_aware_input_plan(self, command):
        return self._result("method-aware-input-plan", command)

    def create_public_method_aware_video_route(self, command):
        return self._result("method-aware-video-route", command)

    def create_public_explicit_audio_requirement_route(self, command):
        return self._result("explicit-audio-requirement-route", command)

    def resolve_assets(self, command):
        self.commands["assets"] = dict(command)
        raise EpisodeProductionPublicError(
            "legacy_asset_resolution_write_disabled", 409
        )

    def execute_media(self, command):
        self.commands["media"] = dict(command)
        raise EpisodeProductionPublicError(
            "legacy_media_execution_write_disabled", 409
        )


class CreatorMethodAwareCutoverHttpTests(unittest.TestCase):
    def setUp(self):
        assembly = LifecycleAssembly.in_memory()
        capability = FakeTextGenerationCapability([])
        self.boundary = FakeMethodAwareBoundary()
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
        self.base = (
            f"http://127.0.0.1:{self.server.server_port}"
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/{RUN}"
        )

    def post(self, resource: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base}/{resource}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    @staticmethod
    def scope(key: str) -> dict:
        return {
            "projectRef": "project-method-aware-http",
            "seriesRef": "series-method-aware-http",
            "episodeRef": "episode-method-aware-http",
            "idempotencyKey": key,
        }

    def test_four_closed_resources_inject_workspace_and_run(self):
        commands = {
            "execution-method-plan": {
                **self.scope("execution-plan"),
                "consistencyValidationVersionRef": "validation-v1",
                "shots": [
                    {
                        "actionExecutionBeats": [
                            {"executionClass": "STATIC_HOLD"}
                        ]
                    }
                ],
            },
            "method-aware-input-plan": {
                **self.scope("input-plan"),
                "assetBindings": [],
            },
            "method-aware-video-route": self.scope("video-route"),
            "explicit-audio-requirement-route": {
                **self.scope("audio-route"),
                "audioRequirementRef": "audio-requirement-silence",
            },
        }
        for resource, command in commands.items():
            with self.subTest(resource=resource):
                status, payload = self.post(resource, command)
                self.assertEqual(status, 201)
                self.assertTrue(payload["ok"])
                self.assertEqual(
                    self.boundary.commands[resource],
                    {
                        **command,
                        "workspaceRef": WORKSPACE,
                        "productionRunRef": RUN,
                    },
                )

    def test_client_method_provider_path_and_authority_overrides_are_rejected(self):
        cases = (
            (
                "execution-method-plan",
                {
                    **self.scope("top-level-class"),
                    "consistencyValidationVersionRef": "validation-v1",
                    "shots": [],
                    "executionClass": "MICRO_MOTION",
                },
            ),
            (
                "method-aware-input-plan",
                {
                    **self.scope("forged-binding-digest"),
                    "assetBindings": [
                        {
                            "visualExecutionRequirementRef": "visual-1",
                            "inputRequirementKey": "anchor:visual-1",
                            "inputRole": "ACTION_READY_ANCHOR",
                            "assetVersionRef": "asset-version-1",
                            "assetVersionDigest": "f" * 64,
                        }
                    ],
                },
            ),
            (
                "method-aware-video-route",
                {**self.scope("provider"), "provider": "forged"},
            ),
            (
                "explicit-audio-requirement-route",
                {
                    **self.scope("raw-rights"),
                    "audioRequirementRef": "audio-1",
                    "rightsBinding": {"authorityDigest": "f" * 64},
                },
            ),
        )
        for resource, command in cases:
            body = json.dumps(command).encode("utf-8")
            req = request.Request(
                f"{self.base}/{resource}",
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.token}",
                },
            )
            with self.subTest(resource=resource), self.assertRaises(
                error.HTTPError
            ) as caught:
                request.urlopen(req, timeout=5)
            self.assertEqual(caught.exception.code, 400)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], "invalid_request")

    def test_legacy_mutation_routes_return_stable_conflict_codes(self):
        for resource, expected in (
            ("assets", "legacy_asset_resolution_write_disabled"),
            ("media", "legacy_media_execution_write_disabled"),
        ):
            with self.subTest(resource=resource), self.assertRaises(
                error.HTTPError
            ) as caught:
                self.post(resource, {"idempotencyKey": f"blocked-{resource}"})
            self.assertEqual(caught.exception.code, 409)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertEqual(payload["error"]["code"], expected)


class CreatorMethodAwareRealBoundaryHttpTests(unittest.TestCase):
    def test_current_facts_drive_the_complete_public_planning_route_chain(self):
        fixture = load_fixture()
        refs = GenericRefs(fixture)
        lifecycle = LifecycleAssembly.in_memory(
            ref_factory=refs,
            clock=lambda: "2026-09-03T06:00:00Z",
            m6_scope_authority=GenericScopeAuthority(),
            m6_approval_authority=GenericApprovalAuthority(),
        )
        roots = seed_generic_roots(lifecycle, fixture)
        with tempfile.TemporaryDirectory() as directory:
            adapter = NoCallVideoAdapter()
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                adapter,
                Path(directory) / "artifacts",
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            boundary = create_in_memory_boundary(
                project_boundary=lifecycle.project_context,
                series_episode_boundary=lifecycle.series_episode,
                series_planning_boundary=lifecycle.series_planning,
                script_studio_boundary=lifecycle.script_studio,
                media_execution=coordinator,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            run_input = run_command(fixture)
            run = boundary.create_run(run_input)
            validation = boundary.create_narrative_validation(
                validation_command(
                    fixture,
                    run,
                    key="public-cutover-http-validation",
                )
            )
            token = secrets.token_urlsafe(48)
            capability = FakeTextGenerationCapability([])
            server = create_server(
                ("127.0.0.1", 0),
                AiDirectorService(capability),
                series_episode_boundary=lifecycle.series_episode,
                project_boundary=lifecycle.project_context,
                series_director_service=SeriesDirectorApplicationService(
                    capability
                ),
                series_planning_boundary=lifecycle.series_planning,
                series_intelligence_boundary=lifecycle.series_intelligence,
                script_studio_service=ScriptStudioApplicationService(capability),
                script_studio_boundary=lifecycle.script_studio,
                episode_production_boundary=boundary,
                public_authenticator=PublicApiAuthenticator.for_token(
                    token, fixture["workspaceRef"]
                ),
                allow_internal_routes=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            base = (
                f"http://127.0.0.1:{server.server_port}"
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{run['productionRunRef']}"
            )

            def post(resource: str, payload: dict) -> tuple[int, dict]:
                req = request.Request(
                    f"{base}/{resource}",
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
                with request.urlopen(req, timeout=5) as response:
                    return response.status, json.loads(
                        response.read().decode("utf-8")
                    )

            scope = {
                "projectRef": fixture["projectRef"],
                "seriesRef": fixture["seriesRef"],
                "episodeRef": fixture["episodeRef"],
            }
            execution_command = execution_plan_command(
                fixture, run, roots["boundScript"], validation
            )
            status, execution_response = post(
                "execution-method-plan",
                {
                    key: value
                    for key, value in execution_command.items()
                    if key not in {"workspaceRef", "productionRunRef"}
                },
            )
            self.assertEqual(status, 201)
            execution_plan = {
                key: value
                for key, value in execution_response.items()
                if key != "ok"
            }
            anchor = append_generic_anchor(
                boundary, fixture, run, execution_plan
            )
            status, input_response = post(
                "method-aware-input-plan",
                {
                    **scope,
                    "assetBindings": [
                        {
                            key: value
                            for key, value in anchor.items()
                            if key != "assetVersionDigest"
                        }
                    ],
                    "idempotencyKey": "public-cutover-http-input-plan",
                },
            )
            self.assertEqual(status, 201)
            status, video_response = post(
                "method-aware-video-route",
                {
                    **scope,
                    "idempotencyKey": "public-cutover-http-video-route",
                },
            )
            self.assertEqual(status, 201)
            routes = video_response["routes"]
            self.assertEqual(
                {
                    (item["executionClass"], item["executionMethod"])
                    for item in routes
                },
                {
                    ("STATIC_HOLD", "STATIC_PLATE_OR_REUSE"),
                    ("MICRO_MOTION", "SINGLE_ANCHOR_I2V"),
                    ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"),
                    (
                        "GAIT_LOCOMOTION",
                        "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
                    ),
                    (
                        "DETERMINISTIC_EVENT",
                        "V3_DETERMINISTIC_COMPOSITION",
                    ),
                },
            )
            self.assertEqual(adapter.generate_calls, 0)
            silence = next(
                item
                for item in execution_plan["audioRequirements"]
                if item["audioType"] == "SILENCE"
            )
            status, audio_response = post(
                "explicit-audio-requirement-route",
                {
                    **scope,
                    "audioRequirementRef": silence["audioRequirementRef"],
                    "idempotencyKey": "public-cutover-http-audio-silence",
                },
            )
            self.assertEqual(status, 201)
            self.assertEqual(
                audio_response["routeDisposition"], "NO_REQUEST_SILENCE"
            )
            self.assertIsNone(audio_response["audioGenerationRequest"])
            serialized = json.dumps(
                {
                    "execution": execution_response,
                    "input": input_response,
                    "video": video_response,
                    "audio": audio_response,
                }
            ).lower()
            self.assertNotIn("storagekey", serialized)
            self.assertNotIn("internalpath", serialized)
            self.assertNotIn("rightsbinding", serialized)

            query = parse.urlencode(scope)
            for resource in (
                "execution-method-plan",
                "method-aware-input-plan",
                "method-aware-video-route",
                "explicit-audio-requirement-route",
            ):
                req = request.Request(
                    f"{base}/{resource}?{query}",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with request.urlopen(req, timeout=5) as response:
                    self.assertEqual(response.status, 200)


if __name__ == "__main__":
    unittest.main()
