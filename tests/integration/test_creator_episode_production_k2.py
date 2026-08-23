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
    K2InternalExecutionGrant,
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
from tests.unit.test_k2_provider_experiments import StubLiveVideoAdapter
from tests.unit.test_k2_real_image_selection import (
    SelectionAuthority,
    StubRealImageCandidateEvidence,
)
from tests.unit.test_k2_real_video_selection import VideoCandidateEvidence


DEFAULT_HTTP_TIMEOUT_SECONDS = 5
MEDIA_HTTP_TIMEOUT_SECONDS = 30


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
        self.real_image_candidate_evidence = StubRealImageCandidateEvidence()
        self.real_video_candidate_evidence = VideoCandidateEvidence()
        self.production = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            real_image_candidate_evidence=self.real_image_candidate_evidence,
            real_video_candidate_evidence=self.real_video_candidate_evidence,
            media_selection_approval_authority=SelectionAuthority(),
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

    def post(
        self,
        path,
        payload,
        *,
        token=None,
        timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
    ):
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
        with request.urlopen(req, timeout=timeout) as response:
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

    def test_public_production_readiness_reports_real_policy_and_rights_blockers(self):
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
        authority_command = {
            key: value
            for key, value in g2_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        self.post(
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}/authority-identity",
            authority_command,
        )

        status, payload = self.get(
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{parse.quote(run['productionRunRef'])}/production-readiness"
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["readiness"]["state"], "BLOCKED_POLICY")
        self.assertIn(
            "identity_reference_rights_not_approved",
            payload["readiness"]["blockers"],
        )
        self.assertIn(
            "live_provider_evidence_missing", payload["readiness"]["blockers"]
        )
        self.assertIn(
            "rights_evidence_authority_missing",
            payload["readiness"]["blockers"],
        )
        self.assertIn(
            "provider_policy_authority_missing",
            payload["readiness"]["blockers"],
        )
        self.assertFalse(payload["readiness"]["publicationAllowed"])

        with self.assertRaises(error.HTTPError) as forged_actor:
            self.post(
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{parse.quote(run['productionRunRef'])}/production-readiness",
                {
                    "idempotencyKey": "forged-production-policy-actor",
                    "actorRef": "browser-forged-actor",
                    "productionPolicy": {},
                    "rightsManifest": {},
                    "providerExecutionPolicy": {},
                },
            )
        self.assertEqual(forged_actor.exception.code, 400)
        forged_payload = json.loads(forged_actor.exception.read().decode("utf-8"))
        self.assertEqual(forged_payload["error"]["code"], "invalid_request")

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

        video_request = next(
            item for item in result["generationRequests"]
            if item["mediaKind"] == "video"
        )
        experiment_endpoint = f"{base}/provider-experiments"
        with self.assertRaises(error.HTTPError) as blocked:
            self.post(
                experiment_endpoint,
                {
                    "idempotencyKey": "blocked-provider-experiment-v1",
                    "sourceGenerationRequestRef": video_request[
                        "generationRequestRef"
                    ],
                    "providerCapabilityRef": "untrusted-browser-capability",
                },
            )
        self.assertEqual(blocked.exception.code, 409)
        blocked_payload = json.loads(blocked.exception.read().decode("utf-8"))
        self.assertEqual(
            blocked_payload["error"]["code"], "production_policy_required"
        )
        with self.assertRaises(error.HTTPError) as blocked_get:
            self.get(experiment_endpoint)
        self.assertEqual(blocked_get.exception.code, 409)

    def test_public_internal_p1_uses_existing_lineage_without_external_authority_fields(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        provider_execution = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            StubLiveVideoAdapter(),
            Path(self.artifacts.name) / "internal-provider-artifacts",
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T01:00:00Z",
            max_attempts=1,
        )
        grant = K2InternalExecutionGrant.create(
            workspace_ref=WORKSPACE,
            production_run_ref="episode-production-run-k2-1",
            provider_id="provider-video",
            model_id="model-video-v1",
            region="approved-region-1",
            endpoint_class="server-side-managed",
            runtime_attestation_ref="runtime-attestation-a100-v1",
            runtime_attestation_digest="4" * 64,
            cost_currency="USD",
            max_cost_minor=100,
            timeout_seconds=1800,
        )
        self.production = create_in_memory_boundary(
            project_boundary=self.assembly.project_context,
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            provider_experiment_execution=provider_execution,
            internal_execution_grant=grant,
            ref_factory=self.refs,
            clock=lambda: "2026-08-17T00:05:00Z",
        )
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
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

        public_run = {
            key: value
            for key, value in run_command(
                self.project, self.series, self.episode
            ).items()
            if key != "workspaceRef"
        }
        _, created = self.post(
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run
        )
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
            _, result = self.post(
                f"{base}/{resource}",
                {
                    key: value
                    for key, value in command.items()
                    if key not in {"workspaceRef", "productionRunRef"}
                },
            )
        assets = result
        source = next(
            item
            for item in assets["generationRequests"]
            if item["mediaKind"] == "video"
        )
        status, ready = self.get(f"{base}/production-readiness")
        self.assertEqual(status, 200)
        self.assertEqual(
            ready["readiness"]["state"], "READY_INTERNAL_EXECUTION"
        )

        status, experiment = self.post(
            f"{base}/provider-experiments",
            {
                "idempotencyKey": "public-internal-video-smoke-v1",
                "sourceGenerationRequestRef": source[
                    "generationRequestRef"
                ],
            },
            timeout=MEDIA_HTTP_TIMEOUT_SECONDS,
        )

        self.assertEqual(status, 201)
        self.assertEqual(
            experiment["readiness"]["state"],
            "PASSED_INTERNAL_VIDEO_EXECUTION",
        )
        self.assertEqual(
            experiment["candidate"]["provenance"],
            "SELF_HOSTED_AI_GENERATED",
        )
        serialized = json.dumps(experiment, ensure_ascii=False)
        self.assertNotIn("rightsManifestRef", serialized)
        self.assertNotIn("providerExecutionPolicyRef", serialized)
        self.assertNotIn("budgetAuthorityRef", serialized)
        self.assertFalse(experiment["candidate"]["publicationAllowed"])

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
        status, result = self.post(
            f"{base}/media",
            command,
            timeout=MEDIA_HTTP_TIMEOUT_SECONDS,
        )
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
                timeout=(
                    MEDIA_HTTP_TIMEOUT_SECONDS
                    if resource == "media"
                    else DEFAULT_HTTP_TIMEOUT_SECONDS
                ),
            )
        preview_command = {
            key: value for key, value in g6_preview_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, preview = self.post(
            f"{base}/preview",
            preview_command,
            timeout=MEDIA_HTTP_TIMEOUT_SECONDS,
        )
        self.assertEqual(status, 201)
        self.assertEqual(preview["state"], "QC_READY")
        self.assertEqual(preview["qcReport"]["result"], "PASS")
        status, headers, preview_content = self.get_bytes(
            f"{base}/preview/content"
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "video/mp4")
        self.assertEqual(headers.get_content_disposition(), "inline")
        self.assertEqual(
            sha256(preview_content).hexdigest(),
            preview["previewCandidate"]["sha256"],
        )

        finalize_command = {
            key: value for key, value in g6_finalize_command(run).items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        status, final = self.post(
            f"{base}/finalize",
            finalize_command,
            timeout=MEDIA_HTTP_TIMEOUT_SECONDS,
        )
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

    def test_public_m10_image_plan_is_scoped_and_never_accepts_paths(self):
        public_run = {
            key: value
            for key, value in run_command(
                self.project, self.series, self.episode
            ).items()
            if key != "workspaceRef"
        }
        _, created = self.post(
            PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT, public_run
        )
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
            ("preview", g6_preview_command(run)),
        ):
            self.post(
                f"{base}/{resource}",
                {
                    key: value
                    for key, value in command.items()
                    if key not in {"workspaceRef", "productionRunRef"}
                },
                timeout=(
                    MEDIA_HTTP_TIMEOUT_SECONDS
                    if resource in {"media", "preview"}
                    else DEFAULT_HTTP_TIMEOUT_SECONDS
                ),
            )
        endpoint = f"{base}/real-media-revision"
        status, planned = self.post(
            endpoint, {"idempotencyKey": "http-m10-image-plan-v1"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(planned["state"], "REAL_IMAGE_PLAN_READY")
        self.assertEqual(len(planned["generationRequests"]), 4)
        self.assertTrue(
            all(
                len(item["identityInputs"]) == 2
                and item["publicationAllowed"] is False
                for item in planned["generationRequests"]
            )
        )
        self.assertNotIn("path", json.dumps(planned, ensure_ascii=False).lower())

        status, restored = self.get(endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(
            restored["realImagePlan"]["payloadDigest"],
            planned["realImagePlan"]["payloadDigest"],
        )
        with self.assertRaises(error.HTTPError) as injected:
            self.post(
                endpoint,
                {
                    "idempotencyKey": "http-m10-image-plan-injected",
                    "identityImagePath": "/tmp/injected.png",
                },
            )
        self.assertEqual(injected.exception.code, 400)
        payload = json.loads(injected.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "invalid_request")

        legacy_selection_endpoint = f"{base}/real-image-selection"
        selection_endpoint = f"{base}/real-image-admission"
        status, recorded = self.post(
            f"{base}/real-image-candidates",
            {"idempotencyKey": "http-m10-image-candidates-v1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(recorded["candidates"]), 4)
        self.assertEqual(len(recorded["technicalValidations"]), 4)
        visual_qcs = []
        for ordinal, validation in enumerate(
            recorded["technicalValidations"], start=1
        ):
            status, assessed = self.post(
                f"{base}/semantic-visual-qc",
                {
                    "idempotencyKey": f"http-m10-visual-qc-{ordinal}-v1",
                    "technicalValidationRef": validation[
                        "technicalValidationRef"
                    ],
                    "technicalValidationVersion": 1,
                    "technicalValidationDigest": validation["payloadDigest"],
                    "visualQcRef": f"http-m10-visual-qc-{ordinal}-v1",
                    "visualQcVersion": 1,
                    "reviewProfile": "k2-semantic-visual-qc-v1",
                    "evidence": [
                        {
                            "evidenceRef": f"http-m10-review-frame-{ordinal}",
                            "evidenceDigest": str(ordinal) * 64,
                        }
                    ],
                    "supersedesVisualQc": None,
                    "checks": {
                        name: {"result": "PASS", "note": ""}
                        for name in (
                            "identity",
                            "wardrobe",
                            "location",
                            "action",
                            "prop",
                            "motion",
                        )
                    },
                    "result": "PASS",
                },
            )
            self.assertEqual(status, 201)
            visual_qcs.append(assessed["semanticVisualQc"])
        selection_payload = {
            "idempotencyKey": "http-m10-image-selection-v1",
            "selections": [
                {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"http-m10-selection-{ordinal}-v1",
                    "selectionVersion": 1,
                    "approvalRef": f"http-m10-approval-{ordinal}-v1",
                }
                for ordinal, qc in enumerate(visual_qcs, start=1)
            ],
        }
        status, selected = self.post(selection_endpoint, selection_payload)
        self.assertEqual(status, 201)
        self.assertEqual(selected["state"], "REAL_IMAGE_READY")
        self.assertEqual(len(selected["selectionDecisions"]), 4)
        self.assertEqual(len(selected["assetVersions"]), 4)
        self.assertEqual(
            {item["actorRef"] for item in selected["selectionDecisions"]},
            {"human-reviewer-k2-image-test"},
        )
        self.assertTrue(
            all(
                item["immutable"] is True
                and item["publicationAllowed"] is False
                for item in selected["assetVersions"]
            )
        )
        self.assertNotIn(
            "internalPath", json.dumps(selected, ensure_ascii=False)
        )
        status, restored = self.get(selection_endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(restored["state"], "REAL_IMAGE_READY")
        status, legacy_restored = self.get(legacy_selection_endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(
            legacy_restored["realImageAdmissionManifest"]["payloadDigest"],
            restored["realImageAdmissionManifest"]["payloadDigest"],
        )

        video_endpoint = f"{base}/real-video-revision"
        status, video_plan = self.post(
            video_endpoint,
            {"idempotencyKey": "http-m11-video-plan-v1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(video_plan["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(
            [
                item["parameters"]["durationFrames"]
                for item in video_plan["generationRequests"]
            ],
            [168, 168, 192, 192],
        )
        selected_assets = {
            item["ordinal"]: item for item in selected["assetVersions"]
        }
        self.assertTrue(
            all(
                item["sourceImageAssetVersionDigest"]
                == selected_assets[item["ordinal"]]["payloadDigest"]
                and item["startImageBindingState"]
                == "EXACT_ASSET_VERSION_BOUND"
                and item["publicationAllowed"] is False
                for item in video_plan["generationRequests"]
            )
        )
        self.assertNotIn(
            "internalPath", json.dumps(video_plan, ensure_ascii=False)
        )
        status, restored = self.get(video_endpoint)
        self.assertEqual(status, 200)
        self.assertEqual(restored["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(len(restored["videoGenerationRequests"]), 4)

        status, projected = self.get(f"{base}/state-projection")
        self.assertEqual(status, 200)
        self.assertEqual(projected["rootState"]["state"], "ROOTS_READY")
        self.assertEqual(
            projected["productionProjection"]["state"],
            "REAL_VIDEO_PLAN_READY",
        )
        self.assertEqual(projected["state"], "REAL_VIDEO_PLAN_READY")
        self.assertEqual(projected["productionState"], projected["state"])
        self.assertEqual(projected["visualQcState"]["state"], "NOT_RECORDED")
        self.assertEqual(
            projected["activeRevision"]["revisionRef"],
            video_plan["realVideoPlan"]["realVideoPlanRef"],
        )
        self.assertEqual(
            projected["invariants"]["assetVersionAuthority"],
            "V5_CANONICAL_EVIDENCE_ONLY",
        )

        with self.assertRaises(error.HTTPError) as forged_reviewer:
            self.post(
                f"{base}/semantic-visual-qc",
                {
                    "idempotencyKey": "forged-reviewer",
                    "reviewerRef": "browser-forged-reviewer",
                },
            )
        self.assertEqual(forged_reviewer.exception.code, 400)

        with self.assertRaises(error.HTTPError) as forged:
            self.post(
                selection_endpoint,
                {**selection_payload, "actorRef": "browser-forged-actor"},
            )
        self.assertEqual(forged.exception.code, 400)
        payload = json.loads(forged.exception.read().decode("utf-8"))
        self.assertEqual(payload["error"]["code"], "invalid_request")

        for forged_field in (
            "actorRef",
            "actorKind",
            "authorityRef",
            "authorityDecisionDigest",
            "subjectDigest",
        ):
            with self.subTest(forged_field=forged_field):
                with self.assertRaises(error.HTTPError) as forged_authority:
                    self.post(
                        f"{base}/media-selection",
                        {
                            "idempotencyKey": f"forged-{forged_field}",
                            "approvalRef": "opaque-human-approval-ref",
                            forged_field: "browser-forged-authority",
                        },
                    )
                self.assertEqual(forged_authority.exception.code, 400)
                rejected = json.loads(
                    forged_authority.exception.read().decode("utf-8")
                )
                self.assertEqual(rejected["error"]["code"], "invalid_request")

        # A closed-world request containing only approvalRef reaches Core
        # unchanged.  This scope has no matching QC, so the expected result is
        # an upstream conflict rather than a command-shape failure caused by a
        # server-injected actor/authority field.
        with self.assertRaises(error.HTTPError) as missing_qc:
            self.post(
                f"{base}/media-selection",
                {
                    "idempotencyKey": "media-selection-approval-ref-only",
                    "visualQcRef": "missing-visual-qc",
                    "visualQcVersion": 1,
                    "visualQcDigest": "7" * 64,
                    "selectionRef": "missing-qc-rejection",
                    "selectionVersion": 1,
                    "approvalRef": "opaque-human-approval-ref",
                    "decision": "REJECTED",
                },
            )
        self.assertEqual(missing_qc.exception.code, 409)
        missing_qc_payload = json.loads(
            missing_qc.exception.read().decode("utf-8")
        )
        self.assertEqual(
            missing_qc_payload["error"]["code"], "upstream_not_confirmed"
        )

        status, video_candidates = self.post(
            f"{base}/real-video-candidates",
            {"idempotencyKey": "http-m11-video-candidates-v1"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(video_candidates["candidates"]), 4)
        self.assertEqual(len(video_candidates["technicalValidations"]), 4)
        video_selections = []
        for ordinal, validation in enumerate(
            video_candidates["technicalValidations"], start=1
        ):
            status, assessed = self.post(
                f"{base}/semantic-visual-qc",
                {
                    "idempotencyKey": f"http-m11-visual-qc-{ordinal}-v1",
                    "technicalValidationRef": validation[
                        "technicalValidationRef"
                    ],
                    "technicalValidationVersion": 1,
                    "technicalValidationDigest": validation["payloadDigest"],
                    "visualQcRef": f"http-m11-visual-qc-{ordinal}-v1",
                    "visualQcVersion": 1,
                    "reviewProfile": "k2-semantic-visual-qc-v1",
                    "evidence": [
                        {
                            "evidenceRef": f"http-m11-review-frame-{ordinal}",
                            "evidenceDigest": format(ordinal + 4, "x") * 64,
                        }
                    ],
                    "supersedesVisualQc": None,
                    "checks": {
                        name: {"result": "PASS", "note": ""}
                        for name in (
                            "identity",
                            "wardrobe",
                            "location",
                            "action",
                            "prop",
                            "motion",
                        )
                    },
                    "result": "PASS",
                },
            )
            self.assertEqual(status, 201)
            qc = assessed["semanticVisualQc"]
            self.assertEqual(qc["reviewerRef"], "runtime-test-credential")
            video_selections.append(
                {
                    "visualQcRef": qc["visualQcRef"],
                    "visualQcVersion": qc["visualQcVersion"],
                    "visualQcDigest": qc["payloadDigest"],
                    "selectionRef": f"http-m11-selection-{ordinal}-v1",
                    "selectionVersion": 1,
                    "approvalRef": f"http-m11-approval-{ordinal}-v1",
                }
            )

        status, video_admitted = self.post(
            f"{base}/real-video-admission",
            {
                "idempotencyKey": "http-m11-video-admission-v1",
                "selections": video_selections,
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(video_admitted["state"], "REAL_VIDEO_READY")
        self.assertEqual(len(video_admitted["assetVersions"]), 4)
        self.assertTrue(
            all(
                item["publicationAllowed"] is False
                and item["immutable"] is True
                for item in video_admitted["assetVersions"]
            )
        )
        self.assertNotIn(
            "storageKey", json.dumps(video_admitted, ensure_ascii=False)
        )

        status, final_projection = self.get(f"{base}/state-projection")
        self.assertEqual(status, 200)
        self.assertEqual(final_projection["state"], "REAL_VIDEO_READY")
        self.assertEqual(
            final_projection["productionProjection"]["state"],
            "REAL_VIDEO_READY",
        )
        self.assertEqual(final_projection["visualQcState"]["state"], "PASS")
        active_candidates = final_projection["candidateLifecycle"]["candidates"]
        self.assertEqual(len(active_candidates), 4)
        self.assertTrue(
            all(
                item["technicalState"] == "TECHNICALLY_VERIFIED"
                and item["visualQcState"] == "VISUAL_QC_PASSED"
                and item["selectionState"] == "SELECTED_BY_HUMAN"
                and item["admissionState"] == "ADMITTED"
                for item in active_candidates
            ),
            active_candidates,
        )


if __name__ == "__main__":
    unittest.main()
