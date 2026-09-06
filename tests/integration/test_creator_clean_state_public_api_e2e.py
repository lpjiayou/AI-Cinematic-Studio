"""Clean-state acceptance for the authenticated Creator Public HTTP flow."""

from __future__ import annotations

import copy
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.project_foundation import (
    ProjectFoundationApplicationService,
)
from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    token_sha256,
)
from apps.creator_workspace_mvp.public_contract import (
    CAPABILITIES_ENDPOINT,
    PUBLIC_AI_DIRECTOR_ENDPOINT,
    PUBLIC_CONFIRM_PLAN_ENDPOINT,
    PUBLIC_EPISODES_ENDPOINT,
    PUBLIC_PROJECT_CONTEXT_ENDPOINT,
    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
    PUBLIC_PROJECTS_ENDPOINT,
    PUBLIC_SCRIPT_CONFIRM_ENDPOINT,
    PUBLIC_SCRIPT_GENERATE_ENDPOINT,
    PUBLIC_SCRIPT_WORKSPACE_ENDPOINT,
    PUBLIC_SERIES_ENDPOINT,
    PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
    PUBLIC_SERIES_PLANNING_ENDPOINT,
    PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
    PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT,
)
from apps.creator_workspace_mvp.script_studio import (
    ScriptStudioApplicationService,
)
from apps.creator_workspace_mvp.series_director import (
    SeriesDirectorApplicationService,
)
from apps.creator_workspace_mvp.series_plan_candidate_receipts import (
    create_local_development_receipt_service,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.project_engine.project_foundation import (
    PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
)
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.unit.test_ai_director_phase1 import valid_brief, valid_plan
from tests.unit.test_script_studio_m3 import script_candidate
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE_A = "clean-state-workspace-a"
WORKSPACE_B = "clean-state-workspace-b"
PROFILE = "clean-state-content-profile"

_BUSINESS_TABLES = (
    "v5_confirmed_creative_plans",
    "v5_series",
    "v5_projects",
    "v5_project_series_relationships",
    "v5_episode_projects",
    "v5_episode_plan_bindings",
    "creator_project_foundation_commands",
    "creator_series_plan_candidate_receipts",
    "v5_series_plans",
    "v5_series_plan_versions",
    "v5_scripts",
    "v5_script_versions",
    "v5_script_acceptances",
    "v5_canonical_registrations",
    "v5_episode_production_runs",
)


def _authenticator(token_a: str, token_b: str) -> PublicApiAuthenticator:
    return PublicApiAuthenticator.from_mapping(
        {
            "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
            "credentials": [
                {
                    "credentialRef": "clean-state-credential-a",
                    "workspaceRef": WORKSPACE_A,
                    "tokenSha256": token_sha256(token_a),
                    "enabled": True,
                },
                {
                    "credentialRef": "clean-state-credential-b",
                    "workspaceRef": WORKSPACE_B,
                    "tokenSha256": token_sha256(token_b),
                    "enabled": True,
                },
            ],
        }
    )


def _foundation_command(
    creative_plan_ref: str | None,
    *,
    key: str = "clean-state-project-foundation-v1",
) -> dict[str, object]:
    episode = None
    if creative_plan_ref is not None:
        episode = {
            "creativePlanRef": creative_plan_ref,
            "episodeNumber": 1,
            "seasonNumber": 1,
            "volumeNumber": 1,
            "title": "Clean State EP01",
        }
    return {
        "schemaVersion": PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
        "idempotencyKey": key,
        "contentProfileRef": PROFILE,
        "series": {
            "title": "Clean State Series",
            "description": "Public-only clean-state acceptance",
        },
        "project": {
            "projectType": "series",
            "title": "Clean State Project",
            "description": "Created by the recoverable public command",
            "targetPlatform": "streaming",
            "aspectRatio": "16:9",
            "defaultDurationSec": 30,
            "plannedEpisodeCount": 4,
        },
        "episode": episode,
    }


def _business_counts(database_path: Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        present = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        return {
            table: (
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if table in present
                else 0
            )
            for table in _BUSINESS_TABLES
        }


def _workspace_counts(
    database_path: Path,
    workspace_ref: str,
) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        return {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE workspace_ref = ?",
                (workspace_ref,),
            ).fetchone()[0]
            for table in (
                "v5_confirmed_creative_plans",
                "v5_series",
                "v5_projects",
                "v5_episode_projects",
                "creator_project_foundation_commands",
            )
        }


class _OneShotFault:
    def __init__(self, point: str) -> None:
        self.point = point
        self.fired = False

    def __call__(self, point: str) -> None:
        if point == self.point and not self.fired:
            self.fired = True
            raise RuntimeError(f"fault:{point}")


class _CleanStatePublicServer:
    def __init__(
        self,
        database_path: Path,
        token_a: str,
        token_b: str,
        *,
        foundation_fault_hook=None,
    ) -> None:
        self.database_path = database_path
        self.public_post_count = 0
        self.internal_route_request_count = 0
        self.ai_capability = FakeTextGenerationCapability(
            [json.dumps(valid_plan(), ensure_ascii=False)]
        )
        self.series_capability = FakeTextGenerationCapability(
            [json.dumps(valid_candidate(4), ensure_ascii=False)]
        )
        self.script_capability = FakeTextGenerationCapability(
            [json.dumps(script_candidate(), ensure_ascii=False)]
        )
        self.assembly = LifecycleAssembly.sqlite(
            database_path,
            initialize_or_upgrade=True,
        )
        self.receipt_service = create_local_development_receipt_service(
            database_path
        )
        self.foundation_service = ProjectFoundationApplicationService(
            self.assembly.project_foundation_store,
            self.assembly.coordinator,
            self.assembly.series_episode,
            self.assembly.project_context,
            fault_hook=foundation_fault_hook,
        )
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(self.ai_capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_director_service=SeriesDirectorApplicationService(
                self.series_capability
            ),
            series_plan_candidate_receipt_service=self.receipt_service,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_service=ScriptStudioApplicationService(
                self.script_capability
            ),
            script_studio_boundary=self.assembly.script_studio,
            canonical_registration_boundary=self.assembly.canonical_registration,
            project_foundation_service=self.foundation_service,
            public_authenticator=_authenticator(token_a, token_b),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.receipt_service.store.close()
        self.server = None

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        payload: dict[str, object] | None = None,
        body: bytes | None = None,
    ) -> tuple[int, dict[str, object]]:
        if path.startswith("/creator/internal/"):
            self.internal_route_request_count += 1
        if method == "POST" and path.startswith("/creator/api/v1/"):
            self.public_post_count += 1
        headers: dict[str, str] = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        if method == "POST":
            headers["Content-Type"] = "application/json"
            if body is None:
                body = json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers=headers,
        )
        try:
            response = request.urlopen(http_request, timeout=10)
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        with response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )


class CreatorCleanStatePublicApiE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database_path = Path(self.directory.name) / "creator.sqlite3"
        self.assertFalse(self.database_path.exists())
        self.token_a = secrets.token_urlsafe(48)
        self.token_b = secrets.token_urlsafe(48)
        self.harness = _CleanStatePublicServer(
            self.database_path,
            self.token_a,
            self.token_b,
        )
        self.addCleanup(self._close_active_harness)
        self.assertTrue(self.database_path.is_file())

    def _close_active_harness(self) -> None:
        self.harness.close()

    def _get(
        self,
        path: str,
        *,
        token: str | None = None,
        query: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        suffix = f"?{parse.urlencode(query)}" if query else ""
        return self.harness.request(
            "GET",
            f"{path}{suffix}",
            token=self.token_a if token is None else token,
        )

    def _post(
        self,
        path: str,
        payload: dict[str, object],
        *,
        token: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        return self.harness.request(
            "POST",
            path,
            token=self.token_a if token is None else token,
            payload=payload,
        )

    def test_clean_state_public_api_flow_reaches_storyboard_gate_without_preseed(
        self,
    ) -> None:
        empty = _business_counts(self.database_path)
        self.assertEqual({table: 0 for table in _BUSINESS_TABLES}, empty)

        unauthenticated_status, unauthenticated = self.harness.request(
            "GET",
            CAPABILITIES_ENDPOINT,
            token=None,
        )
        self.assertEqual(401, unauthenticated_status)
        self.assertEqual(
            "authentication_required",
            unauthenticated["error"]["code"],
        )

        forbidden_workspace = _foundation_command(None)
        forbidden_workspace["workspaceRef"] = "forged-workspace"
        status, payload = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            forbidden_workspace,
        )
        self.assertEqual((400, "client_workspace_scope_forbidden"), (
            status,
            payload["error"]["code"],
        ))

        fractional = _foundation_command(None)
        fractional["project"]["plannedEpisodeCount"] = 1.9
        status, payload = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            fractional,
        )
        self.assertEqual(400, status)
        self.assertFalse(payload["ok"])

        nonstandard = _foundation_command(None)
        nonstandard["project"]["plannedEpisodeCount"] = float("nan")
        status, payload = self.harness.request(
            "POST",
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            token=self.token_a,
            body=json.dumps(nonstandard, allow_nan=True).encode("utf-8"),
        )
        self.assertEqual((400, "invalid_request"), (
            status,
            payload["error"]["code"],
        ))
        self.assertEqual(empty, _business_counts(self.database_path))

        status, capabilities = self._get(CAPABILITIES_ENDPOINT)
        self.assertEqual(200, status)
        self.assertTrue(capabilities["ok"])

        status, candidate = self._post(
            PUBLIC_AI_DIRECTOR_ENDPOINT,
            {"brief": valid_brief()},
        )
        self.assertEqual(200, status)
        self.assertTrue(candidate["ok"])
        self.assertEqual("candidate-creative-plan", candidate["kind"])
        self.assertTrue(candidate["confirmationRequired"])
        self.assertTrue(candidate["sourcePlanRef"])
        self.assertEqual(1, candidate["sourcePlanVersion"])
        self.assertEqual(0, _business_counts(self.database_path)[
            "v5_confirmed_creative_plans"
        ])

        status, confirmed = self._post(
            PUBLIC_CONFIRM_PLAN_ENDPOINT,
            {
                "brief": valid_brief(),
                "plan": candidate["plan"],
                "sourcePlanRef": candidate["sourcePlanRef"],
                "sourcePlanVersion": candidate["sourcePlanVersion"],
                "humanConfirmed": True,
            },
        )
        self.assertEqual(201, status)
        creative_plan = confirmed["confirmedPlan"]
        self.assertTrue(confirmed["ok"])
        self.assertEqual(
            candidate["sourcePlanRef"], creative_plan["sourcePlanRef"]
        )
        self.assertEqual(1, _business_counts(self.database_path)[
            "v5_confirmed_creative_plans"
        ])

        command = _foundation_command(creative_plan["creativePlanRef"])
        status, created = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(201, status)
        self.assertFalse(created["idempotentReplay"])
        self.assertFalse(created["recoveredFromPending"])
        foundation = created["foundation"]
        foundation_ref = foundation["foundationRef"]
        series_ref = foundation["series"]["seriesRef"]
        project_ref = foundation["project"]["projectRef"]
        episode_ref = foundation["episode"]["episodeRef"]

        status, replay = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(200, status)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(foundation, replay["foundation"])
        counts_after_replay = _business_counts(self.database_path)
        self.assertEqual(1, counts_after_replay["v5_series"])
        self.assertEqual(1, counts_after_replay["v5_projects"])
        self.assertEqual(1, counts_after_replay["v5_episode_projects"])
        self.assertEqual(
            1, counts_after_replay["creator_project_foundation_commands"]
        )

        changed = copy.deepcopy(command)
        changed["project"]["title"] = "Changed replay title"
        status, conflict = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            changed,
        )
        self.assertEqual((409, "project_foundation_idempotency_conflict"), (
            status,
            conflict["error"]["code"],
        ))

        status, receipt = self._get(
            f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{parse.quote(foundation_ref)}"
        )
        self.assertEqual(200, status)
        self.assertEqual(foundation, receipt["foundation"])

        status, series_readback = self._get(
            f"{PUBLIC_SERIES_ENDPOINT}/{parse.quote(series_ref)}"
        )
        self.assertEqual(200, status)
        self.assertEqual(WORKSPACE_A, series_readback["series"]["workspaceRef"])
        self.assertEqual(PROFILE, series_readback["series"]["contentProfileRef"])
        status, project_readback = self._get(
            f"{PUBLIC_PROJECTS_ENDPOINT}/{parse.quote(project_ref)}"
        )
        self.assertEqual(200, status)
        self.assertEqual(WORKSPACE_A, project_readback["project"]["workspaceRef"])
        self.assertEqual(PROFILE, project_readback["project"]["contentProfileRef"])
        self.assertEqual([series_ref], project_readback["project"]["seriesRefs"])
        status, episode = self._get(
            f"{PUBLIC_EPISODES_ENDPOINT}/{parse.quote(episode_ref)}",
            query={"seriesRef": series_ref},
        )
        self.assertEqual(200, status)
        self.assertEqual(
            creative_plan["creativePlanRef"],
            episode["episode"]["creativePlanRef"],
        )
        scope = {
            "projectRef": project_ref,
            "seriesRef": series_ref,
            "episodeRef": episode_ref,
        }
        status, context = self._get(
            PUBLIC_PROJECT_CONTEXT_ENDPOINT,
            query=scope,
        )
        self.assertEqual(200, status)
        self.assertEqual(WORKSPACE_A, context["context"]["workspaceRef"])
        self.assertEqual(project_ref, context["context"]["projectRef"])
        self.assertEqual(series_ref, context["context"]["seriesRef"])
        self.assertEqual(episode_ref, context["context"]["episodeRef"])

        creative_input = "Generate the deterministic four-episode plan."
        status, series_candidate = self._post(
            PUBLIC_SERIES_PLANNING_GENERATE_ENDPOINT,
            {
                "projectRef": project_ref,
                "seriesRef": series_ref,
                "creativeInput": creative_input,
            },
        )
        self.assertEqual(200, status)
        self.assertTrue(series_candidate["ok"])
        self.assertEqual(
            "creator.series-plan.candidate.v1",
            series_candidate["candidate"]["schemaVersion"],
        )
        for field in ("candidateRef", "candidateDigest", "sourceContextDigest"):
            self.assertTrue(series_candidate[field])
        self.assertEqual(
            "creator.series-plan-candidate-receipt.v1",
            series_candidate["candidateReceiptSchemaVersion"],
        )
        candidate_counts = _business_counts(self.database_path)
        self.assertEqual(
            1, candidate_counts["creator_series_plan_candidate_receipts"]
        )
        self.assertEqual(0, candidate_counts["v5_series_plans"])
        status, series_confirmation = self._post(
            PUBLIC_SERIES_PLANNING_CONFIRM_ENDPOINT,
            {
                "projectRef": project_ref,
                "seriesRef": series_ref,
                "humanConfirmed": True,
                "candidate": series_candidate["candidate"],
            },
        )
        self.assertEqual(201, status)
        self.assertTrue(series_confirmation["ok"])
        status, planning_workspace = self._get(
            PUBLIC_SERIES_PLANNING_ENDPOINT,
            query={"projectRef": project_ref, "seriesRef": series_ref},
        )
        self.assertEqual(200, status)
        self.assertEqual(
            series_confirmation["plan"]["confirmedSeriesPlanVersionRef"],
            planning_workspace["workspace"]["plan"][
                "confirmedSeriesPlanVersionRef"
            ],
        )

        status, script_workspace = self._get(
            PUBLIC_SCRIPT_WORKSPACE_ENDPOINT,
            query={"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        self.assertEqual(200, status)
        self.assertIsNone(script_workspace["workspace"]["script"])

        before_script = _business_counts(self.database_path)
        script_status, generated_script = self._post(
            PUBLIC_SCRIPT_GENERATE_ENDPOINT,
            {"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        if script_status != 201:
            self.harness.close()
            after_script = _business_counts(self.database_path)
            self.fail(
                json.dumps(
                    {
                        "failedStage": "SCRIPT_GENERATION",
                        "failedEndpoint": PUBLIC_SCRIPT_GENERATE_ENDPOINT,
                        "expectedStatus": 201,
                        "actualStatus": script_status,
                        "actualErrorCode": generated_script.get("error", {}).get(
                            "code"
                        ),
                        "businessRowCountsBefore": before_script,
                        "businessRowCountsAfter": after_script,
                        "partialMutationDetected": before_script != after_script,
                    },
                    sort_keys=True,
                )
            )

        script_ref = generated_script["script"]["scriptRef"]
        script_version = generated_script["scriptVersion"]
        script_version_ref = script_version["scriptVersionRef"]
        self.assertEqual("v5.script.v1", generated_script["script"]["schemaVersion"])
        self.assertEqual(
            "creator.script-studio.script-version.v1",
            script_version["schemaVersion"],
        )
        self.assertEqual("ai-generation", script_version["changeKind"])
        self.assertNotIn("m6ConsumerBinding", script_version)
        self.assertIsNone(
            generated_script["script"]["confirmedScriptVersionRef"]
        )
        status, confirmed_script = self._post(
            PUBLIC_SCRIPT_CONFIRM_ENDPOINT,
            {
                "seriesRef": series_ref,
                "episodeRef": episode_ref,
                "scriptRef": script_ref,
                "scriptVersionRef": script_version_ref,
                "humanConfirmed": True,
            },
        )
        self.assertEqual(201, status)
        self.assertEqual(
            script_version_ref,
            confirmed_script["script"]["confirmedScriptVersionRef"],
        )
        status, script_workspace = self._get(
            PUBLIC_SCRIPT_WORKSPACE_ENDPOINT,
            query={"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        self.assertEqual(200, status)
        self.assertEqual(1, int(script_workspace["workspace"]["script"] is not None))
        self.assertEqual(1, len(script_workspace["workspace"]["versions"]))
        self.assertEqual(
            script_version_ref,
            script_workspace["workspace"]["script"][
                "confirmedScriptVersionRef"
            ],
        )
        self.assertEqual(
            "creator.script-studio.script-version.v1",
            script_workspace["workspace"]["versions"][0]["schemaVersion"],
        )
        self.assertNotIn(
            "m6ConsumerBinding",
            script_workspace["workspace"]["versions"][0],
        )
        status, storyboard = self._get(
            PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT,
            query={"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        self.assertEqual(200, status)
        self.assertEqual(
            "m4-ip-character-binding-required",
            storyboard["bootstrap"]["nextGate"],
        )
        self.assertEqual(WORKSPACE_A, storyboard["bootstrap"]["workspaceRef"])
        self.assertEqual(series_ref, storyboard["bootstrap"]["seriesRef"])
        self.assertEqual(episode_ref, storyboard["bootstrap"]["episodeRef"])
        self.assertEqual(script_ref, storyboard["bootstrap"]["scriptRef"])
        self.assertEqual(
            script_version_ref, storyboard["bootstrap"]["scriptVersionRef"]
        )
        self.assertFalse(storyboard["bootstrap"]["storyboardProductionAuthorized"])
        self.assertEqual(1, len(self.harness.ai_capability.commands))
        self.assertEqual(1, len(self.harness.series_capability.commands))
        self.assertEqual(1, len(self.harness.script_capability.commands))
        self.assertEqual(12, self.harness.public_post_count)
        self.assertEqual(0, self.harness.internal_route_request_count)

        expected_foundation = copy.deepcopy(foundation)
        expected_series = copy.deepcopy(series_readback["series"])
        expected_project = copy.deepcopy(project_readback["project"])
        expected_episode = copy.deepcopy(episode["episode"])
        expected_context = copy.deepcopy(context["context"])
        expected_planning = copy.deepcopy(planning_workspace["workspace"])
        expected_script = copy.deepcopy(script_workspace["workspace"])
        expected_storyboard = copy.deepcopy(storyboard["bootstrap"])
        counts_before_restart = _business_counts(self.database_path)

        self.harness.close()
        restarted = _CleanStatePublicServer(
            self.database_path,
            self.token_a,
            self.token_b,
        )
        self.harness = restarted

        status, restarted_receipt = self._get(
            f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/{parse.quote(foundation_ref)}"
        )
        self.assertEqual(200, status)
        self.assertEqual(expected_foundation, restarted_receipt["foundation"])
        status, restarted_series = self._get(
            f"{PUBLIC_SERIES_ENDPOINT}/{parse.quote(series_ref)}"
        )
        self.assertEqual((200, expected_series), (
            status,
            restarted_series.get("series"),
        ))
        status, restarted_project = self._get(
            f"{PUBLIC_PROJECTS_ENDPOINT}/{parse.quote(project_ref)}"
        )
        self.assertEqual((200, expected_project), (
            status,
            restarted_project.get("project"),
        ))
        status, restarted_episode = self._get(
            f"{PUBLIC_EPISODES_ENDPOINT}/{parse.quote(episode_ref)}",
            query={"seriesRef": series_ref},
        )
        self.assertEqual((200, expected_episode), (
            status,
            restarted_episode.get("episode"),
        ))
        status, restarted_context = self._get(
            PUBLIC_PROJECT_CONTEXT_ENDPOINT,
            query=scope,
        )
        self.assertEqual((200, expected_context), (
            status,
            restarted_context.get("context"),
        ))
        status, restarted_planning = self._get(
            PUBLIC_SERIES_PLANNING_ENDPOINT,
            query={"projectRef": project_ref, "seriesRef": series_ref},
        )
        self.assertEqual((200, expected_planning), (
            status,
            restarted_planning.get("workspace"),
        ))
        status, restarted_script = self._get(
            PUBLIC_SCRIPT_WORKSPACE_ENDPOINT,
            query={"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        self.assertEqual((200, expected_script), (
            status,
            restarted_script.get("workspace"),
        ))
        status, restarted_storyboard = self._get(
            PUBLIC_STORYBOARD_BOOTSTRAP_ENDPOINT,
            query={"seriesRef": series_ref, "episodeRef": episode_ref},
        )
        self.assertEqual((200, expected_storyboard), (
            status,
            restarted_storyboard.get("bootstrap"),
        ))

        status, restarted_replay = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(200, status)
        self.assertTrue(restarted_replay["idempotentReplay"])
        self.assertFalse(restarted_replay["recoveredFromPending"])
        self.assertEqual(expected_foundation, restarted_replay["foundation"])
        self.assertEqual(
            counts_before_restart,
            _business_counts(self.database_path),
        )
        self.assertEqual(0, len(restarted.ai_capability.commands))
        self.assertEqual(0, len(restarted.series_capability.commands))
        self.assertEqual(0, len(restarted.script_capability.commands))
        self.assertEqual(1, restarted.public_post_count)
        self.assertEqual(0, restarted.internal_route_request_count)

        restarted.close()
        final_counts = _business_counts(self.database_path)
        self.assertEqual(
            {
                "v5_confirmed_creative_plans": 1,
                "v5_series": 1,
                "v5_projects": 1,
                "v5_project_series_relationships": 1,
                "v5_episode_projects": 1,
                "v5_episode_plan_bindings": 1,
                "creator_project_foundation_commands": 1,
                "creator_series_plan_candidate_receipts": 1,
                "v5_series_plans": 1,
                "v5_series_plan_versions": 1,
                "v5_scripts": 1,
                "v5_script_versions": 1,
                "v5_script_acceptances": 0,
                "v5_canonical_registrations": 0,
                "v5_episode_production_runs": 0,
            },
            final_counts,
        )
        with sqlite3.connect(self.database_path) as connection:
            foundation_row = connection.execute(
                "SELECT state,request_json,request_digest,result_json,result_digest "
                "FROM creator_project_foundation_commands"
            ).fetchone()
            self.assertEqual("COMPLETED", foundation_row[0])
            self.assertEqual(
                sha256(foundation_row[1].encode("utf-8")).hexdigest(),
                foundation_row[2],
            )
            self.assertEqual(
                sha256(foundation_row[3].encode("utf-8")).hexdigest(),
                foundation_row[4],
            )
            candidate_row = connection.execute(
                "SELECT source_context_json,source_context_digest,"
                "creative_input_digest,candidate_json,candidate_digest "
                "FROM creator_series_plan_candidate_receipts"
            ).fetchone()
            self.assertEqual(
                sha256(candidate_row[0].encode("utf-8")).hexdigest(),
                candidate_row[1],
            )
            self.assertEqual(
                sha256(creative_input.encode("utf-8")).hexdigest(),
                candidate_row[2],
            )
            self.assertNotIn(creative_input, "".join(candidate_row))
            self.assertEqual(
                sha256(candidate_row[3].encode("utf-8")).hexdigest(),
                candidate_row[4],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM v5_series AS s LEFT JOIN "
                    "v5_project_series_relationships AS r ON "
                    "r.workspace_ref=s.workspace_ref AND r.series_ref=s.series_ref "
                    "WHERE r.series_ref IS NULL"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM v5_projects AS p LEFT JOIN "
                    "v5_project_series_relationships AS r ON "
                    "r.workspace_ref=p.workspace_ref AND r.project_ref=p.project_ref "
                    "WHERE r.project_ref IS NULL"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM v5_episode_projects AS e LEFT JOIN "
                    "v5_episode_plan_bindings AS b ON "
                    "b.workspace_ref=e.workspace_ref AND b.series_ref=e.series_ref "
                    "AND b.episode_ref=e.episode_ref WHERE b.episode_ref IS NULL"
                ).fetchone()[0],
            )
            self.assertEqual(
                0,
                connection.execute(
                    "SELECT COUNT(*) FROM (SELECT workspace_ref,result_digest,COUNT(*) "
                    "AS duplicate_count FROM creator_project_foundation_commands "
                    "WHERE result_digest IS NOT NULL GROUP BY workspace_ref,result_digest "
                    "HAVING duplicate_count > 1)"
                ).fetchone()[0],
            )
            self.assertEqual([], connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall())

    def test_public_response_loss_replays_committed_foundation_without_duplicates(
        self,
    ) -> None:
        self.harness.close()
        with tempfile.TemporaryDirectory() as response_directory:
            database_path = Path(response_directory) / "response-loss.sqlite3"
            self.assertFalse(database_path.exists())
            fault = _OneShotFault(
                "after-transaction-commit-before-http-response"
            )
            failed = _CleanStatePublicServer(
                database_path,
                self.token_a,
                self.token_b,
                foundation_fault_hook=fault,
            )
            try:
                status, candidate = failed.request(
                    "POST",
                    PUBLIC_AI_DIRECTOR_ENDPOINT,
                    token=self.token_a,
                    payload={"brief": valid_brief()},
                )
                self.assertEqual(200, status)
                status, confirmed = failed.request(
                    "POST",
                    PUBLIC_CONFIRM_PLAN_ENDPOINT,
                    token=self.token_a,
                    payload={
                        "brief": valid_brief(),
                        "plan": candidate["plan"],
                        "sourcePlanRef": candidate["sourcePlanRef"],
                        "sourcePlanVersion": candidate["sourcePlanVersion"],
                        "humanConfirmed": True,
                    },
                )
                self.assertEqual(201, status)
                command = _foundation_command(
                    confirmed["confirmedPlan"]["creativePlanRef"],
                    key="clean-state-response-loss-v1",
                )
                status, failure = failed.request(
                    "POST",
                    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
                    token=self.token_a,
                    payload=command,
                )
                self.assertEqual((500, "application_error"), (
                    status,
                    failure["error"]["code"],
                ))
                self.assertTrue(fault.fired)
                self.assertEqual(3, failed.public_post_count)
                self.assertEqual(0, failed.internal_route_request_count)
            finally:
                failed.close()

            committed_counts = _business_counts(database_path)
            self.assertEqual(1, committed_counts["v5_series"])
            self.assertEqual(1, committed_counts["v5_projects"])
            self.assertEqual(1, committed_counts["v5_episode_projects"])
            self.assertEqual(
                1, committed_counts["creator_project_foundation_commands"]
            )
            with sqlite3.connect(database_path) as connection:
                row = connection.execute(
                    "SELECT state,result_json FROM "
                    "creator_project_foundation_commands"
                ).fetchone()
                self.assertEqual("COMPLETED", row[0])
                committed_foundation = json.loads(row[1])

            replayed = _CleanStatePublicServer(
                database_path,
                self.token_a,
                self.token_b,
            )
            try:
                status, replay = replayed.request(
                    "POST",
                    PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
                    token=self.token_a,
                    payload=command,
                )
                self.assertEqual(200, status)
                self.assertTrue(replay["idempotentReplay"])
                self.assertFalse(replay["recoveredFromPending"])
                self.assertEqual(committed_foundation, replay["foundation"])
                self.assertEqual(1, replayed.public_post_count)
                self.assertEqual(0, replayed.internal_route_request_count)
            finally:
                replayed.close()
            self.assertEqual(committed_counts, _business_counts(database_path))

    def test_foreign_workspace_cannot_read_or_collide_with_foundation(
        self,
    ) -> None:
        status, candidate = self._post(
            PUBLIC_AI_DIRECTOR_ENDPOINT,
            {"brief": valid_brief()},
        )
        self.assertEqual(200, status)
        status, confirmed = self._post(
            PUBLIC_CONFIRM_PLAN_ENDPOINT,
            {
                "brief": valid_brief(),
                "plan": candidate["plan"],
                "sourcePlanRef": candidate["sourcePlanRef"],
                "sourcePlanVersion": candidate["sourcePlanVersion"],
                "humanConfirmed": True,
            },
        )
        self.assertEqual(201, status)
        command = _foundation_command(
            confirmed["confirmedPlan"]["creativePlanRef"],
            key="clean-state-shared-key-v1",
        )
        status, created = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            command,
        )
        self.assertEqual(201, status)
        foundation = created["foundation"]
        foundation_ref = foundation["foundationRef"]
        series_ref = foundation["series"]["seriesRef"]
        project_ref = foundation["project"]["projectRef"]
        episode_ref = foundation["episode"]["episodeRef"]

        foreign_reads = (
            (
                f"{PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT}/"
                f"{parse.quote(foundation_ref)}",
                None,
                "project_foundation_not_found",
            ),
            (
                f"{PUBLIC_SERIES_ENDPOINT}/{parse.quote(series_ref)}",
                None,
                "not_found",
            ),
            (
                f"{PUBLIC_PROJECTS_ENDPOINT}/{parse.quote(project_ref)}",
                None,
                "not_found",
            ),
            (
                f"{PUBLIC_EPISODES_ENDPOINT}/{parse.quote(episode_ref)}",
                {"seriesRef": series_ref},
                "not_found",
            ),
        )
        for endpoint, query, expected_code in foreign_reads:
            with self.subTest(endpoint=endpoint):
                suffix = f"?{parse.urlencode(query)}" if query else ""
                status, rejected = self.harness.request(
                    "GET",
                    f"{endpoint}{suffix}",
                    token=self.token_b,
                )
                self.assertEqual(404, status)
                self.assertEqual(expected_code, rejected["error"]["code"])
                serialized = json.dumps(rejected, sort_keys=True)
                self.assertNotIn(WORKSPACE_A, serialized)
                self.assertNotIn("requestJson", serialized)
                self.assertNotIn("resultJson", serialized)
                self.assertNotIn(str(self.database_path), serialized)

        foreign_command = _foundation_command(
            None,
            key="clean-state-shared-key-v1",
        )
        status, foreign_created = self._post(
            PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
            foreign_command,
            token=self.token_b,
        )
        self.assertEqual(201, status)
        self.assertNotEqual(
            foundation_ref,
            foreign_created["foundation"]["foundationRef"],
        )
        self.assertNotEqual(
            series_ref,
            foreign_created["foundation"]["series"]["seriesRef"],
        )
        self.assertNotEqual(
            project_ref,
            foreign_created["foundation"]["project"]["projectRef"],
        )
        self.assertIsNone(foreign_created["foundation"]["episode"])
        self.assertEqual(4, self.harness.public_post_count)
        self.assertEqual(0, self.harness.internal_route_request_count)
        self.harness.close()
        self.assertEqual(
            {
                "v5_confirmed_creative_plans": 1,
                "v5_series": 1,
                "v5_projects": 1,
                "v5_episode_projects": 1,
                "creator_project_foundation_commands": 1,
            },
            _workspace_counts(self.database_path, WORKSPACE_A),
        )
        self.assertEqual(
            {
                "v5_confirmed_creative_plans": 0,
                "v5_series": 1,
                "v5_projects": 1,
                "v5_episode_projects": 0,
                "creator_project_foundation_commands": 1,
            },
            _workspace_counts(self.database_path, WORKSPACE_B),
        )


if __name__ == "__main__":
    unittest.main()
