from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
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
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
)
from services.v5_core_os.episode_production.assets import (
    ASSET_PLAN_SCHEMA_VERSION,
    ASSET_REQUIREMENT_SCHEMA_VERSION,
    GENERATION_REQUEST_SCHEMA_VERSION,
)
from services.v5_core_os.episode_production.evidence import EvidenceRecord
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.media import (
    ASSET_VERSION_SCHEMA_VERSION,
    GENERATION_RESULT_SCHEMA_VERSION,
    MEDIA_MANIFEST_SCHEMA_VERSION,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability
from services.v4_platform import (
    DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    SqliteMediaJobAdapter,
)
from tests.contract.test_m12_audio_authority_contract import rights_binding
from tests.integration.test_generic_upstream_method_closure import (
    GenericApprovalAuthority,
    GenericRefs,
    GenericScopeAuthority,
    NoCallVideoAdapter,
    append_generic_anchor,
    confirm_fixed_voice,
    execution_plan_command,
    fixed_voice_asset,
    load_fixture,
    method_service,
    run_command as generic_run_command,
    seed_generic_roots,
    source_span,
    sqlite_tables,
    validation_command,
)
from tests.support.legacy_k2_history import seed_legacy_g4, seed_legacy_g5
from tests.unit.test_episode_production_k2 import (
    WORKSPACE as K2_WORKSPACE,
    activate_k2_m6_baseline,
    g2_command as k2_g2_command,
    g3_command as k2_g3_command,
    g4_command as k2_g4_command,
    g5_command as k2_g5_command,
    k2_identity_authority,
    run_command as k2_run_command,
    seed_k2_roots,
)


WORKSPACE = "workspace-method-aware-http"
RUN = "run-method-aware-http"


class _JsonHttpClient:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.token = token

    def post(self, path: str, payload: dict, *, timeout: int = 5):
        req = request.Request(
            f"{self.base}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def get(self, path: str, **query):
        suffix = f"?{parse.urlencode(query)}" if query else ""
        req = request.Request(
            f"{self.base}{path}{suffix}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with request.urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))


@contextmanager
def _serve_public_boundary(boundary, lifecycle, workspace_ref: str):
    token = secrets.token_urlsafe(48)
    capability = FakeTextGenerationCapability([])
    server = create_server(
        ("127.0.0.1", 0),
        AiDirectorService(capability),
        series_episode_boundary=lifecycle.series_episode,
        project_boundary=lifecycle.project_context,
        series_director_service=SeriesDirectorApplicationService(capability),
        series_planning_boundary=lifecycle.series_planning,
        series_intelligence_boundary=lifecycle.series_intelligence,
        script_studio_service=ScriptStudioApplicationService(capability),
        script_studio_boundary=lifecycle.script_studio,
        episode_production_boundary=boundary,
        public_authenticator=PublicApiAuthenticator.for_token(
            token, workspace_ref
        ),
        allow_internal_routes=False,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield _JsonHttpClient(
            f"http://127.0.0.1:{server.server_port}", token
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _CountingLegacyMediaAdapter(DeterministicLocalFfmpegAdapter):
    def __init__(self) -> None:
        self.generate_call_count = 0

    def generate(self, media_request, candidate_path):
        self.generate_call_count += 1
        return super().generate(media_request, candidate_path)


def _legacy_evidence_state(boundary, workspace_ref: str, run_ref: str) -> dict:
    evidence = boundary._EpisodeProductionPublicBoundary__assets.evidence
    snapshot = evidence.read_snapshot(workspace_ref, run_ref)
    facts = tuple(
        fact for gate in snapshot.gates for fact in gate.get("facts", [])
    )
    return {
        "state": snapshot.currentState,
        "gateCount": len(snapshot.gates),
        "factCount": len(facts),
        "recordCount": len(snapshot.records),
        "generationRequestCount": sum(
            str(fact.get("factKind", "")).startswith("GenerationRequest:")
            for fact in facts
        ),
        "assetVersionCount": sum(
            str(fact.get("factKind", "")).startswith("AssetVersion:")
            for fact in facts
        ),
        "revisionToken": snapshot.revisionToken,
    }


def _artifact_file_state(root: Path) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        sorted(
            (
                str(path.relative_to(root)),
                path.stat().st_size,
                path.stat().st_mtime_ns,
            )
            for path in root.rglob("*")
            if path.is_file()
        )
    )


def _json_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_json_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_json_keys(item) for item in value))
    return set()


def _json_strings(value) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(
            item
            for child in value.values()
            for item in _json_strings(child)
        )
    if isinstance(value, list):
        return tuple(
            item for child in value for item in _json_strings(child)
        )
    return (value,) if isinstance(value, str) else ()


def _evidence_record(
    *,
    workspace_ref: str,
    run_ref: str,
    record_kind: str,
    record_ref: str,
    payload: dict,
    ordinal: int,
) -> EvidenceRecord:
    return EvidenceRecord(
        workspaceRef=workspace_ref,
        productionRunRef=run_ref,
        recordKind=record_kind,
        recordRef=record_ref,
        recordVersion=1,
        idempotencyKey=f"public-cutover-authority-fixture-{ordinal}",
        requestDigest=_digest({"fixtureOrdinal": ordinal}),
        createdAt="2026-09-03T06:00:00Z",
        payload=deepcopy(payload),
        payloadDigest=payload["payloadDigest"],
    )


def _append_public_audio_authority(
    boundary, fixture: dict, run: dict, requirements: list[dict]
) -> tuple[dict[str, dict], dict]:
    confirmed = confirm_fixed_voice(boundary, fixture)
    voice_asset = fixed_voice_asset(fixture, run, confirmed)
    records = []
    rights_by_type = {}
    for ordinal, requirement in enumerate(requirements, start=1):
        audio_type = requirement["audioType"]
        if audio_type in {"SILENCE", "MUSIC"}:
            continue
        value = rights_binding(
            asset_requirement_ref=requirement["audioRequirementRef"],
            asset_requirement_digest=requirement["payloadDigest"],
        )
        value = {
            key: item
            for key, item in value.items()
            if key != "payloadDigest"
        }
        value["rightsBindingRef"] = (
            f"public-cutover-rights-{audio_type.lower()}"
        )
        value["payloadDigest"] = _digest(value)
        rights_by_type[audio_type] = value
        records.append(
            _evidence_record(
                workspace_ref=fixture["workspaceRef"],
                run_ref=run["productionRunRef"],
                record_kind="RightsBinding",
                record_ref=value["rightsBindingRef"],
                payload=value,
                ordinal=ordinal,
            )
        )
    records.append(
        _evidence_record(
            workspace_ref=fixture["workspaceRef"],
            run_ref=run["productionRunRef"],
            record_kind="AssetVersion",
            record_ref=voice_asset["assetVersionRef"],
            payload=voice_asset,
            ordinal=100,
        )
    )
    method_service(boundary).evidence_repository.append_records(records)
    return rights_by_type, voice_asset


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
            run_input = generic_run_command(fixture)
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


class K2MethodAwarePublicCutoverAcceptanceTests(unittest.TestCase):
    def test_legacy_g4_g5_new_writes_are_frozen_and_exact_replay_is_read_only(
        self,
    ):
        (
            lifecycle,
            refs,
            project,
            series,
            episode,
            _,
        ) = seed_k2_roots(with_m6_authority=True)
        activate_k2_m6_baseline(lifecycle, project, series)

        with tempfile.TemporaryDirectory() as directory:
            artifact_root = Path(directory) / "legacy-media"
            adapter = _CountingLegacyMediaAdapter()
            coordinator = MediaJobCoordinator(
                InMemoryMediaJobAdapter(),
                adapter,
                artifact_root,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            boundary = create_in_memory_boundary(
                project_boundary=lifecycle.project_context,
                series_episode_boundary=lifecycle.series_episode,
                series_planning_boundary=lifecycle.series_planning,
                script_studio_boundary=lifecycle.script_studio,
                identity_reference_authority=k2_identity_authority(),
                media_execution=coordinator,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            run = boundary.create_run(k2_run_command(project, series, episode))
            boundary.authorize_and_lock(k2_g2_command(run))
            boundary.compile_shot_graph(k2_g3_command(run))
            endpoint = (
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{parse.quote(run['productionRunRef'], safe='')}"
            )
            public_g4 = {
                key: value
                for key, value in k2_g4_command(run).items()
                if key not in {"workspaceRef", "productionRunRef"}
            }
            public_g5 = {
                key: value
                for key, value in k2_g5_command(run).items()
                if key not in {"workspaceRef", "productionRunRef"}
            }

            with _serve_public_boundary(
                boundary, lifecycle, K2_WORKSPACE
            ) as client:
                before_g4 = _legacy_evidence_state(
                    boundary, K2_WORKSPACE, run["productionRunRef"]
                )
                refs_before_g4 = dict(refs.counts)
                with self.assertRaises(error.HTTPError) as rejected_g4:
                    client.post(f"{endpoint}/assets", public_g4)
                self.assertEqual(rejected_g4.exception.code, 409)
                rejection = json.loads(
                    rejected_g4.exception.read().decode("utf-8")
                )
                self.assertEqual(
                    rejection["error"]["code"],
                    "legacy_asset_resolution_write_disabled",
                )
                self.assertEqual(
                    _legacy_evidence_state(
                        boundary, K2_WORKSPACE, run["productionRunRef"]
                    ),
                    before_g4,
                )
                self.assertEqual(refs.counts, refs_before_g4)
                self.assertEqual(before_g4["generationRequestCount"], 0)

                g4_history = seed_legacy_g4(boundary, k2_g4_command(run))
                self.assertFalse(g4_history["idempotentReplay"])
                self.assertEqual(
                    g4_history["assetResolutionManifest"]["schemaVersion"],
                    ASSET_PLAN_SCHEMA_VERSION,
                )
                self.assertEqual(
                    {
                        item["schemaVersion"]
                        for item in g4_history["assetRequirements"]
                    },
                    {ASSET_REQUIREMENT_SCHEMA_VERSION},
                )
                self.assertEqual(
                    {
                        item["schemaVersion"]
                        for item in g4_history["generationRequests"]
                    },
                    {GENERATION_REQUEST_SCHEMA_VERSION},
                )
                before_g4_replay = _legacy_evidence_state(
                    boundary, K2_WORKSPACE, run["productionRunRef"]
                )
                refs_before_g4_replay = dict(refs.counts)
                status, replayed_g4 = client.post(
                    f"{endpoint}/assets", public_g4
                )
                self.assertEqual(status, 200)
                self.assertTrue(replayed_g4["idempotentReplay"])
                self.assertEqual(
                    replayed_g4["assetResolutionManifest"]["payloadDigest"],
                    g4_history["assetResolutionManifest"]["payloadDigest"],
                )
                self.assertEqual(
                    replayed_g4["assetResolutionManifest"]["summary"],
                    g4_history["assetResolutionManifest"]["summary"],
                )
                self.assertEqual(
                    _legacy_evidence_state(
                        boundary, K2_WORKSPACE, run["productionRunRef"]
                    ),
                    before_g4_replay,
                )
                self.assertEqual(refs.counts, refs_before_g4_replay)

                before_g5 = _legacy_evidence_state(
                    boundary, K2_WORKSPACE, run["productionRunRef"]
                )
                jobs_before_g5 = coordinator.list_jobs(
                    K2_WORKSPACE, run["productionRunRef"]
                )
                artifacts_before_g5 = _artifact_file_state(artifact_root)
                worker_calls_before_g5 = adapter.generate_call_count
                with self.assertRaises(error.HTTPError) as rejected_g5:
                    client.post(f"{endpoint}/media", public_g5, timeout=30)
                self.assertEqual(rejected_g5.exception.code, 409)
                rejection = json.loads(
                    rejected_g5.exception.read().decode("utf-8")
                )
                self.assertEqual(
                    rejection["error"]["code"],
                    "legacy_media_execution_write_disabled",
                )
                self.assertEqual(
                    _legacy_evidence_state(
                        boundary, K2_WORKSPACE, run["productionRunRef"]
                    ),
                    before_g5,
                )
                self.assertEqual(
                    coordinator.list_jobs(
                        K2_WORKSPACE, run["productionRunRef"]
                    ),
                    jobs_before_g5,
                )
                self.assertEqual(
                    _artifact_file_state(artifact_root), artifacts_before_g5
                )
                self.assertEqual(
                    adapter.generate_call_count, worker_calls_before_g5
                )

                g5_history = seed_legacy_g5(boundary, k2_g5_command(run))
                self.assertFalse(g5_history["idempotentReplay"])
                self.assertEqual(
                    {
                        item["schemaVersion"]
                        for item in g5_history["generationResults"]
                    },
                    {GENERATION_RESULT_SCHEMA_VERSION},
                )
                self.assertEqual(
                    {
                        item["schemaVersion"]
                        for item in g5_history["assetVersions"]
                    },
                    {ASSET_VERSION_SCHEMA_VERSION},
                )
                self.assertEqual(
                    g5_history["mediaManifest"]["schemaVersion"],
                    MEDIA_MANIFEST_SCHEMA_VERSION,
                )
                before_g5_replay = _legacy_evidence_state(
                    boundary, K2_WORKSPACE, run["productionRunRef"]
                )
                jobs_before_g5_replay = coordinator.list_jobs(
                    K2_WORKSPACE, run["productionRunRef"]
                )
                artifacts_before_g5_replay = _artifact_file_state(
                    artifact_root
                )
                worker_calls_before_g5_replay = adapter.generate_call_count
                status, replayed_g5 = client.post(
                    f"{endpoint}/media", public_g5, timeout=30
                )
                self.assertEqual(status, 200)
                self.assertTrue(replayed_g5["idempotentReplay"])
                self.assertEqual(
                    replayed_g5["mediaManifest"]["payloadDigest"],
                    g5_history["mediaManifest"]["payloadDigest"],
                )
                self.assertEqual(
                    _legacy_evidence_state(
                        boundary, K2_WORKSPACE, run["productionRunRef"]
                    ),
                    before_g5_replay,
                )
                self.assertEqual(
                    coordinator.list_jobs(
                        K2_WORKSPACE, run["productionRunRef"]
                    ),
                    jobs_before_g5_replay,
                )
                self.assertEqual(
                    _artifact_file_state(artifact_root),
                    artifacts_before_g5_replay,
                )
                self.assertEqual(
                    adapter.generate_call_count,
                    worker_calls_before_g5_replay,
                )

                lower_keys = {key.lower() for key in _json_keys(replayed_g5)}
                self.assertTrue(
                    lower_keys.isdisjoint(
                        {
                            "internalpath",
                            "credential",
                            "credentials",
                            "authority",
                            "internalauthority",
                        }
                    )
                )
                self.assertFalse(
                    any(
                        value.startswith("/")
                        for value in _json_strings(replayed_g5)
                    )
                )

    def test_sqlite_public_chain_covers_three_axis_routing_and_explicit_audio(
        self,
    ):
        fixture = load_fixture()
        refs = GenericRefs(fixture)
        scope = {
            "projectRef": fixture["projectRef"],
            "seriesRef": fixture["seriesRef"],
            "episodeRef": fixture["episodeRef"],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            creator_database = root / "creator.sqlite3"
            production_database = root / "episode-production.sqlite3"
            evidence_database = root / "episode-production.evidence.sqlite3"
            media_jobs_database = root / "media-jobs.sqlite3"
            artifact_root = root / "artifacts"
            lifecycle = LifecycleAssembly.sqlite(
                creator_database,
                initialize_or_upgrade=True,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
                m6_scope_authority=GenericScopeAuthority(),
                m6_approval_authority=GenericApprovalAuthority(),
            )
            roots = seed_generic_roots(lifecycle, fixture)
            adapter = NoCallVideoAdapter()
            coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(media_jobs_database),
                adapter,
                artifact_root,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            boundary_kwargs = {
                "project_boundary": lifecycle.project_context,
                "series_episode_boundary": lifecycle.series_episode,
                "series_planning_boundary": lifecycle.series_planning,
                "script_studio_boundary": lifecycle.script_studio,
                "evidence_database_path": evidence_database,
                "media_execution": coordinator,
            }
            boundary = create_local_development_boundary(
                production_database,
                **boundary_kwargs,
                ref_factory=refs,
                clock=lambda: "2026-09-03T06:00:00Z",
            )
            run_input = generic_run_command(fixture)
            run = boundary.create_run(run_input)
            validation_input = validation_command(
                fixture,
                run,
                key="public-cutover-acceptance-validation",
            )
            validation = boundary.create_narrative_validation(validation_input)
            execution_input = execution_plan_command(
                fixture, run, roots["boundScript"], validation
            )
            first_scene = roots["boundScript"]["scriptVersion"]["scenes"][0]
            execution_input["shots"][0]["audioIntents"].insert(
                1,
                {
                    "audioType": "NARRATION",
                    "beatRef": "beat-static",
                    "sourceSpan": source_span(first_scene, "NARRATION"),
                    "timingReference": {
                        "startFrameInclusive": 0,
                        "endFrameExclusive": 10,
                    },
                },
            )
            execution_input["shots"][0]["audioIntents"].append(
                {
                    "audioType": "MUSIC",
                    "beatRef": "beat-micro",
                    "timingReference": {
                        "startFrameInclusive": 10,
                        "endFrameExclusive": 20,
                    },
                }
            )
            public_execution_input = {
                key: value
                for key, value in execution_input.items()
                if key not in {"workspaceRef", "productionRunRef"}
            }
            endpoint = (
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{parse.quote(run['productionRunRef'], safe='')}"
            )
            repository = method_service(boundary).evidence_repository
            creator_tables = sqlite_tables(creator_database)
            evidence_tables = sqlite_tables(evidence_database)
            media_job_tables = sqlite_tables(media_jobs_database)
            files_before = {path.name for path in root.iterdir()}

            with _serve_public_boundary(
                boundary, lifecycle, fixture["workspaceRef"]
            ) as client:
                forged_fields = {
                    "executionMethod": "SINGLE_ANCHOR_I2V",
                    "adapterCapability": "forged-capability",
                    "adapterIdentity": "forged-adapter",
                    "provider": "forged-provider",
                    "fallbackPolicy": "ALLOW_WAN",
                    "storageKey": "forged/storage-key",
                    "localPath": "/tmp/forged-media",
                    "authorityDigest": "f" * 64,
                    "publicationAllowed": True,
                }
                for ordinal, (field, value) in enumerate(
                    forged_fields.items(), start=1
                ):
                    before_records = repository.list_records(
                        fixture["workspaceRef"], run["productionRunRef"]
                    )
                    forged = deepcopy(public_execution_input)
                    forged["idempotencyKey"] = (
                        f"public-cutover-forged-{ordinal}"
                    )
                    forged[field] = value
                    with self.subTest(forged_field=field), self.assertRaises(
                        error.HTTPError
                    ) as rejected:
                        client.post(
                            f"{endpoint}/execution-method-plan", forged
                        )
                    self.assertEqual(rejected.exception.code, 400)
                    payload = json.loads(
                        rejected.exception.read().decode("utf-8")
                    )
                    self.assertEqual(
                        payload["error"]["code"], "invalid_request"
                    )
                    self.assertEqual(
                        repository.list_records(
                            fixture["workspaceRef"],
                            run["productionRunRef"],
                        ),
                        before_records,
                    )

                status, execution_response = client.post(
                    f"{endpoint}/execution-method-plan",
                    public_execution_input,
                )
                self.assertEqual(status, 201)
                execution_plan = {
                    key: value
                    for key, value in execution_response.items()
                    if key != "ok"
                }
                self.assertEqual(execution_plan["currentness"], "CURRENT")
                self.assertEqual(
                    (
                        execution_plan[
                            "consistencyValidationVersionRef"
                        ],
                        execution_plan["consistencyValidationDigest"],
                    ),
                    (
                        validation["consistencyValidationVersionRef"],
                        validation["payloadDigest"],
                    ),
                )
                self.assertEqual(
                    [
                        item["audioType"]
                        for item in execution_plan["audioRequirements"]
                    ],
                    [
                        "DIALOGUE",
                        "NARRATION",
                        "AMBIENCE",
                        "SFX",
                        "MUSIC",
                        "SILENCE",
                    ],
                )
                self.assertEqual(
                    {
                        item["executionClass"]
                        for item in execution_plan[
                            "visualExecutionRequirements"
                        ]
                    },
                    {
                        "STATIC_HOLD",
                        "MICRO_MOTION",
                        "CONTACT_ACTION",
                        "GAIT_LOCOMOTION",
                        "DETERMINISTIC_EVENT",
                    },
                )

                anchor = append_generic_anchor(
                    boundary, fixture, run, execution_plan
                )
                public_input_plan = {
                    **scope,
                    "assetBindings": [
                        {
                            key: value
                            for key, value in anchor.items()
                            if key != "assetVersionDigest"
                        }
                    ],
                    "idempotencyKey": "public-cutover-acceptance-input-plan",
                }
                status, input_response = client.post(
                    f"{endpoint}/method-aware-input-plan",
                    public_input_plan,
                )
                self.assertEqual(status, 201)
                input_plan = {
                    key: value
                    for key, value in input_response.items()
                    if key != "ok"
                }
                self.assertEqual(
                    (
                        input_plan["executionMethodPlanVersionRef"],
                        input_plan["executionMethodPlanDigest"],
                    ),
                    (
                        execution_plan["executionMethodPlanVersionRef"],
                        execution_plan["payloadDigest"],
                    ),
                )

                public_video_route = {
                    **scope,
                    "idempotencyKey": "public-cutover-acceptance-video-route",
                }
                status, video_response = client.post(
                    f"{endpoint}/method-aware-video-route",
                    public_video_route,
                )
                self.assertEqual(status, 201)
                video_route = {
                    key: value
                    for key, value in video_response.items()
                    if key != "ok"
                }
                self.assertEqual(
                    (
                        video_route["methodAwareInputPlanVersionRef"],
                        video_route["methodAwareInputPlanDigest"],
                        video_route["executionMethodPlanVersionRef"],
                        video_route["executionMethodPlanDigest"],
                    ),
                    (
                        input_plan["methodAwareInputPlanVersionRef"],
                        input_plan["payloadDigest"],
                        execution_plan["executionMethodPlanVersionRef"],
                        execution_plan["payloadDigest"],
                    ),
                )
                routes_by_class = {
                    item["executionClass"]: item
                    for item in video_route["routes"]
                }
                self.assertEqual(
                    {
                        key: (
                            item["executionMethod"], item["routingState"]
                        )
                        for key, item in routes_by_class.items()
                    },
                    {
                        "STATIC_HOLD": (
                            "STATIC_PLATE_OR_REUSE",
                            "BYPASSED_STATIC_PLATE",
                        ),
                        "MICRO_MOTION": (
                            "SINGLE_ANCHOR_I2V",
                            "QUEUED_EXISTING_MEDIA_JOB",
                        ),
                        "CONTACT_ACTION": (
                            "CONTACT_CONDITIONED_VIDEO",
                            "CAPABILITY_UNAVAILABLE",
                        ),
                        "GAIT_LOCOMOTION": (
                            "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
                            "CAPABILITY_UNAVAILABLE",
                        ),
                        "DETERMINISTIC_EVENT": (
                            "V3_DETERMINISTIC_COMPOSITION",
                            "REJECTED_DETERMINISTIC_POSTPROCESS",
                        ),
                    },
                )
                self.assertEqual(
                    routes_by_class["DETERMINISTIC_EVENT"]["targetBoundary"],
                    "M13_DETERMINISTIC_POSTPROCESS",
                )
                for execution_class in (
                    "STATIC_HOLD",
                    "CONTACT_ACTION",
                    "GAIT_LOCOMOTION",
                    "DETERMINISTIC_EVENT",
                ):
                    self.assertIsNone(
                        routes_by_class[execution_class][
                            "videoGenerationRequestRef"
                        ]
                    )
                    self.assertFalse(
                        routes_by_class[execution_class]["fallbackUsed"]
                    )
                self.assertFalse(video_route["wanFallbackUsed"])
                self.assertEqual(video_route["videoGenerationRequestCount"], 1)
                unconditional_video_requests = sum(
                    not request_value.get("visualExecutionRequirementRef")
                    or not request_value.get(
                        "visualExecutionRequirementDigest"
                    )
                    for request_value in video_route[
                        "videoGenerationRequests"
                    ]
                )
                self.assertEqual(unconditional_video_requests, 0)
                self.assertEqual(adapter.generate_calls, 0)

                rights_by_type, voice_asset = _append_public_audio_authority(
                    boundary,
                    fixture,
                    run,
                    execution_plan["audioRequirements"],
                )
                audio_commands = {}
                audio_routes = {}
                for requirement in execution_plan["audioRequirements"]:
                    audio_type = requirement["audioType"]
                    command = {
                        **scope,
                        "audioRequirementRef": requirement[
                            "audioRequirementRef"
                        ],
                        "idempotencyKey": (
                            "public-cutover-acceptance-audio-"
                            + audio_type.lower()
                        ),
                    }
                    if audio_type not in {"SILENCE", "MUSIC"}:
                        command["rightsBindingRef"] = rights_by_type[
                            audio_type
                        ]["rightsBindingRef"]
                    if audio_type in {"DIALOGUE", "NARRATION"}:
                        command["voiceAssetVersionRef"] = voice_asset[
                            "assetVersionRef"
                        ]
                    status, response = client.post(
                        f"{endpoint}/explicit-audio-requirement-route",
                        command,
                    )
                    self.assertEqual(status, 201)
                    audio_commands[audio_type] = command
                    audio_routes[audio_type] = {
                        key: value
                        for key, value in response.items()
                        if key != "ok"
                    }

                for audio_type in (
                    "DIALOGUE",
                    "NARRATION",
                    "AMBIENCE",
                    "SFX",
                ):
                    route = audio_routes[audio_type]
                    requirement = next(
                        item
                        for item in execution_plan["audioRequirements"]
                        if item["audioType"] == audio_type
                    )
                    audio_request = route["audioGenerationRequest"]
                    self.assertEqual(route["routeDisposition"], "REQUEST_CREATED")
                    self.assertEqual(
                        (
                            route["executionMethodPlanVersionRef"],
                            route["executionMethodPlanDigest"],
                            route["audioRequirementRef"],
                            route["audioRequirementDigest"],
                        ),
                        (
                            execution_plan[
                                "executionMethodPlanVersionRef"
                            ],
                            execution_plan["payloadDigest"],
                            requirement["audioRequirementRef"],
                            requirement["payloadDigest"],
                        ),
                    )
                    self.assertEqual(
                        (
                            audio_request["audioRequirementRef"],
                            audio_request["audioRequirementDigest"],
                        ),
                        (
                            requirement["audioRequirementRef"],
                            requirement["payloadDigest"],
                        ),
                    )
                    self.assertFalse(route["m12RuntimeInstalled"])
                    self.assertFalse(route["publicationAllowed"])

                for audio_type, disposition in (
                    ("MUSIC", "MUSIC_NOT_IMPLEMENTED"),
                    ("SILENCE", "NO_REQUEST_SILENCE"),
                ):
                    self.assertEqual(
                        audio_routes[audio_type]["routeDisposition"],
                        disposition,
                    )
                    self.assertIsNone(
                        audio_routes[audio_type]["audioGenerationRequest"]
                    )

                dialogue_requirement = next(
                    item
                    for item in execution_plan["audioRequirements"]
                    if item["audioType"] == "DIALOGUE"
                )
                dialogue_request = audio_routes["DIALOGUE"][
                    "audioGenerationRequest"
                ]
                self.assertEqual(
                    (
                        dialogue_request["scriptVersionRef"],
                        dialogue_request["scriptVersionDigest"],
                        dialogue_request["sourceSpan"],
                        dialogue_request["speakerCharacterRef"],
                        dialogue_request["audioRequirementRef"],
                        dialogue_request["audioRequirementDigest"],
                    ),
                    (
                        dialogue_requirement["scriptVersionRef"],
                        dialogue_requirement["scriptVersionDigest"],
                        dialogue_requirement["sourceSpan"],
                        dialogue_requirement["speakerCharacterRef"],
                        dialogue_requirement["audioRequirementRef"],
                        dialogue_requirement["payloadDigest"],
                    ),
                )
                narration_request = audio_routes["NARRATION"][
                    "audioGenerationRequest"
                ]
                self.assertNotIn("speakerCharacterRef", narration_request)
                self.assertEqual(
                    narration_request["requestSpec"]["speechRole"],
                    "narration",
                )
                self.assertIsNone(
                    narration_request["requestSpec"]["dialogueRef"]
                )
                self.assertIsNotNone(
                    narration_request["requestSpec"]["narrationRef"]
                )
                self.assertNotIn(
                    "normalizedSpeechParameters",
                    audio_routes["SFX"]["audioGenerationRequest"][
                        "requestSpec"
                    ],
                )
                self.assertNotIn(
                    "normalizedSpeechParameters",
                    audio_routes["AMBIENCE"]["audioGenerationRequest"][
                        "requestSpec"
                    ],
                )
                unconditional_audio_requests = sum(
                    not request_value.get("audioRequirementRef")
                    or not request_value.get("audioRequirementDigest")
                    for route in audio_routes.values()
                    if (
                        request_value := route["audioGenerationRequest"]
                    ) is not None
                )
                self.assertEqual(unconditional_audio_requests, 0)
                serialized_audio = json.dumps(
                    audio_routes, ensure_ascii=False
                ).lower()
                self.assertNotIn("sine", serialized_audio)
                self.assertNotIn("storagekey", serialized_audio)
                self.assertNotIn("internalpath", serialized_audio)
                self.assertNotIn("rightsbinding", serialized_audio)

                expected_scope = (
                    fixture["workspaceRef"],
                    fixture["projectRef"],
                    fixture["seriesRef"],
                    fixture["episodeRef"],
                    run["productionRunRef"],
                )
                for resource_value in (
                    execution_plan,
                    input_plan,
                    video_route,
                    *audio_routes.values(),
                ):
                    self.assertEqual(
                        (
                            resource_value["workspaceRef"],
                            resource_value["projectRef"],
                            resource_value["seriesRef"],
                            resource_value["episodeRef"],
                            resource_value["productionRunRef"],
                        ),
                        expected_scope,
                    )

                projections = {
                    "execution-method-plan": (
                        execution_plan,
                        "executionMethodPlanVersionRef",
                    ),
                    "method-aware-input-plan": (
                        input_plan,
                        "methodAwareInputPlanVersionRef",
                    ),
                    "method-aware-video-route": (
                        video_route,
                        "videoMethodRouteVersionRef",
                    ),
                }
                for resource, (created, version_field) in projections.items():
                    status, restored = client.get(
                        f"{endpoint}/{resource}",
                        **scope,
                        versionRef=created[version_field],
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        (
                            restored[version_field],
                            restored["payloadDigest"],
                            restored["currentness"],
                        ),
                        (
                            created[version_field],
                            created["payloadDigest"],
                            "CURRENT",
                        ),
                    )
                for created in audio_routes.values():
                    status, restored = client.get(
                        f"{endpoint}/explicit-audio-requirement-route",
                        **scope,
                        versionRef=created[
                            "audioRequirementRouteVersionRef"
                        ],
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        (
                            restored["audioRequirementRouteVersionRef"],
                            restored["payloadDigest"],
                            restored["currentness"],
                        ),
                        (
                            created["audioRequirementRouteVersionRef"],
                            created["payloadDigest"],
                            "CURRENT",
                        ),
                    )

            records_before_restart = repository.list_records(
                fixture["workspaceRef"], run["productionRunRef"]
            )
            jobs_before_restart = coordinator.list_jobs(
                fixture["workspaceRef"], run["productionRunRef"]
            )
            restarted_lifecycle = LifecycleAssembly.sqlite(
                creator_database,
                clock=lambda: "2026-09-03T06:00:01Z",
                m6_scope_authority=GenericScopeAuthority(),
                m6_approval_authority=GenericApprovalAuthority(),
            )
            restarted_adapter = NoCallVideoAdapter()
            restarted_coordinator = MediaJobCoordinator(
                SqliteMediaJobAdapter(
                    media_jobs_database, initialize_if_missing=False
                ),
                restarted_adapter,
                artifact_root,
                ref_factory=lambda prefix: (
                    f"{prefix}-restart-{secrets.token_hex(16)}"
                ),
                clock=lambda: "2026-09-03T06:00:01Z",
            )
            restarted = create_local_development_boundary(
                production_database,
                project_boundary=restarted_lifecycle.project_context,
                series_episode_boundary=restarted_lifecycle.series_episode,
                series_planning_boundary=restarted_lifecycle.series_planning,
                script_studio_boundary=restarted_lifecycle.script_studio,
                evidence_database_path=evidence_database,
                media_execution=restarted_coordinator,
                clock=lambda: "2026-09-03T06:00:01Z",
                initialize_if_missing=False,
            )
            restarted_repository = method_service(
                restarted
            ).evidence_repository

            with _serve_public_boundary(
                restarted, restarted_lifecycle, fixture["workspaceRef"]
            ) as client:
                for resource, (created, version_field) in projections.items():
                    status, restored = client.get(
                        f"{endpoint}/{resource}",
                        **scope,
                        versionRef=created[version_field],
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        (
                            restored[version_field],
                            restored["payloadDigest"],
                            restored["currentness"],
                        ),
                        (
                            created[version_field],
                            created["payloadDigest"],
                            "CURRENT",
                        ),
                    )
                    if resource == "method-aware-video-route":
                        self.assertEqual(restored["routes"], created["routes"])

                for created in audio_routes.values():
                    status, restored = client.get(
                        f"{endpoint}/explicit-audio-requirement-route",
                        **scope,
                        versionRef=created[
                            "audioRequirementRouteVersionRef"
                        ],
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(
                        (
                            restored["audioRequirementRouteVersionRef"],
                            restored["payloadDigest"],
                            restored["routeDisposition"],
                            restored["currentness"],
                        ),
                        (
                            created["audioRequirementRouteVersionRef"],
                            created["payloadDigest"],
                            created["routeDisposition"],
                            "CURRENT",
                        ),
                    )

                for resource, command, created in (
                    (
                        "execution-method-plan",
                        public_execution_input,
                        execution_plan,
                    ),
                    (
                        "method-aware-input-plan",
                        public_input_plan,
                        input_plan,
                    ),
                    (
                        "method-aware-video-route",
                        public_video_route,
                        video_route,
                    ),
                ):
                    status, replay = client.post(
                        f"{endpoint}/{resource}", command
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(replay["idempotentReplay"])
                    self.assertEqual(
                        replay["payloadDigest"], created["payloadDigest"]
                    )
                for audio_type, command in audio_commands.items():
                    status, replay = client.post(
                        f"{endpoint}/explicit-audio-requirement-route",
                        command,
                    )
                    self.assertEqual(status, 200)
                    self.assertTrue(replay["idempotentReplay"])
                    self.assertEqual(
                        replay["payloadDigest"],
                        audio_routes[audio_type]["payloadDigest"],
                    )
                self.assertEqual(
                    restarted_repository.list_records(
                        fixture["workspaceRef"], run["productionRunRef"]
                    ),
                    records_before_restart,
                )
                self.assertEqual(
                    restarted_coordinator.list_jobs(
                        fixture["workspaceRef"], run["productionRunRef"]
                    ),
                    jobs_before_restart,
                )
                self.assertEqual(restarted_adapter.generate_calls, 0)

                changed_execution = deepcopy(public_execution_input)
                changed_execution["shots"][0]["cameraInstruction"][
                    "movement"
                ] = "LOCKED"
                with self.assertRaises(error.HTTPError) as conflict:
                    client.post(
                        f"{endpoint}/execution-method-plan",
                        changed_execution,
                    )
                self.assertEqual(conflict.exception.code, 409)
                payload = json.loads(
                    conflict.exception.read().decode("utf-8")
                )
                self.assertEqual(
                    payload["error"]["code"], "idempotency_conflict"
                )

                with _serve_public_boundary(
                    restarted,
                    restarted_lifecycle,
                    "workspace-public-cutover-foreign",
                ) as foreign_client:
                    with self.assertRaises(error.HTTPError) as foreign:
                        foreign_client.get(
                            f"{endpoint}/method-aware-video-route",
                            **scope,
                            versionRef=video_route[
                                "videoMethodRouteVersionRef"
                            ],
                        )
                    self.assertEqual(foreign.exception.code, 404)
                    payload = json.loads(
                        foreign.exception.read().decode("utf-8")
                    )
                    self.assertEqual(payload["error"]["code"], "not_found")

                newer_validation = restarted.create_narrative_validation(
                    validation_command(
                        fixture,
                        run,
                        key="public-cutover-acceptance-validation-successor",
                    )
                )
                self.assertEqual(newer_validation["currentness"], "CURRENT")
                stale_projections = {
                    **projections,
                    "explicit-audio-requirement-route": (
                        audio_routes["DIALOGUE"],
                        "audioRequirementRouteVersionRef",
                    ),
                }
                for resource, (created, version_field) in (
                    stale_projections.items()
                ):
                    status, restored = client.get(
                        f"{endpoint}/{resource}",
                        **scope,
                        versionRef=created[version_field],
                    )
                    self.assertEqual(status, 200)
                    self.assertEqual(restored["currentness"], "STALE")

                stale_audio = deepcopy(audio_commands["DIALOGUE"])
                stale_audio["idempotencyKey"] = (
                    "public-cutover-audio-stale-plan"
                )
                records_before_stale_rejection = (
                    restarted_repository.list_records(
                        fixture["workspaceRef"], run["productionRunRef"]
                    )
                )
                with self.assertRaises(error.HTTPError) as stale:
                    client.post(
                        f"{endpoint}/explicit-audio-requirement-route",
                        stale_audio,
                    )
                self.assertEqual(stale.exception.code, 409)
                payload = json.loads(stale.exception.read().decode("utf-8"))
                self.assertEqual(
                    payload["error"]["code"], "execution_not_authorized"
                )
                self.assertEqual(
                    restarted_repository.list_records(
                        fixture["workspaceRef"], run["productionRunRef"]
                    ),
                    records_before_stale_rejection,
                )

            self.assertEqual(sqlite_tables(creator_database), creator_tables)
            self.assertEqual(sqlite_tables(evidence_database), evidence_tables)
            self.assertEqual(
                sqlite_tables(media_jobs_database), media_job_tables
            )
            self.assertEqual(
                {path.name for path in root.iterdir()}, files_before
            )
            self.assertEqual(
                len(
                    [
                        path
                        for path in root.iterdir()
                        if path.name == "media-jobs.sqlite3"
                    ]
                ),
                1,
            )
            self.assertEqual(adapter.generate_calls, 0)
            self.assertEqual(restarted_adapter.generate_calls, 0)


if __name__ == "__main__":
    unittest.main()
