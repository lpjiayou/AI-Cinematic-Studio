from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import unittest
from urllib import error, parse, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    token_sha256,
)
from apps.creator_workspace_mvp.public_contract import (
    CAPABILITIES_ENDPOINT,
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import (
    EPISODE_PRODUCTION_SUBRESOURCES,
    create_server,
)
from services.v3_render_core import decoded_frame_pixel_digest_metadata
from services.v5_core_os.episode_production.evidence import (
    SqliteEpisodeProductionEvidenceAdapter,
)
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)
from services.v5_core_os.episode_production.foundation import ScopeMismatchError
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.contract.test_m13_e2_deterministic_effects_contract import (
    _smoke_command,
)
from tests.integration.test_m12_m13_minimal_preview import _source_template
from tests.integration.test_m13_e1_timeline_v3_preview import (
    _authority,
    _public,
    _register_inputs,
    _seed_real_video_ready,
    _service,
)
from tests.unit.test_episode_production_k2 import seed_k2_roots


WORKSPACE = "workspace-m13-e2-http"
RUN = "episode-production-run-m13-e2-http"


def _assert_public_effect_sanitized(
    test_case: unittest.TestCase, value: object
) -> None:
    forbidden = {
        "absolutepath",
        "artifactpath",
        "baseplatefiledigest",
        "baseplatepixeldigest",
        "canonicalmutations",
        "environmentoverride",
        "executionresult",
        "ffmpegargv",
        "ffmpegfilter",
        "filtergraph",
        "fontfiledigest",
        "fontlicensebindingversiondigest",
        "fontlicensebindingversionref",
        "fonttechnicalvalidationdigest",
        "fonttechnicalvalidationref",
        "identitylockdigest",
        "identitylockref",
        "identitylockversionref",
        "identityreferencecontentdigest",
        "identityreferenceprojectiondigest",
        "identityreferenceref",
        "identityreferenceversionref",
        "internalpath",
        "language",
        "markfiledigest",
        "markpixeldigest",
        "modelpath",
        "networkurl",
        "outputpath",
        "privateruntimediagnostics",
        "pythonexpression",
        "resolvedtext",
        "resolvedtextdigest",
        "shellcommand",
        "storagekey",
    }

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for field, nested in item.items():
                normalized = field.replace("_", "").replace("-", "").lower()
                test_case.assertNotIn(normalized, forbidden)
                test_case.assertNotIn("filter", normalized)
                test_case.assertFalse(normalized.endswith("path"))
                test_case.assertFalse(normalized.endswith("storagekey"))
                test_case.assertFalse(normalized.endswith("storagekeys"))
                test_case.assertFalse(normalized.endswith("argv"))
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)


class _DeterministicEffectDeliveryStub:
    def __init__(self) -> None:
        self.commands: list[dict] = []
        self.get_scopes: list[tuple[str, str]] = []
        self.listed_effect_kinds = ["FLAME_EXTINGUISH", "SMOKE"]

    @staticmethod
    def _private_chain(effect_kind: str) -> dict:
        requirement = {
            "schemaVersion": "v5.m13-effect-requirement.v1",
            "effectMode": effect_kind,
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "requirementRef": f"requirement-{effect_kind.lower()}",
            "payloadDigest": "1" * 64,
            "publicationAllowed": False,
            "absolutePath": "/private/base.mp4",
        }
        if effect_kind == "NAMEPLATE_TEXT":
            requirement.update(
                {
                    "textSourceRef": "script-private",
                    "resolvedText": "server-private-text",
                    "resolvedTextDigest": "7" * 64,
                    "language": "und",
                    "basePlateFileDigest": "sha256:" + "8" * 64,
                    "basePlatePixelDigest": "sha256:" + "9" * 64,
                    "fontFileDigest": "a" * 64,
                    "fontTechnicalValidationRef": "font-validation-private",
                    "fontTechnicalValidationDigest": "b" * 64,
                    "fontLicenseBindingVersionRef": "font-license-private",
                    "fontLicenseBindingVersionDigest": "c" * 64,
                }
            )
        elif effect_kind == "FACE_MARK_COMPENSATION":
            requirement.update(
                {
                    "characterRef": "character-public",
                    "identityReferenceRef": "identity-reference-private",
                    "identityReferenceVersionRef": "identity-version-private",
                    "identityReferenceContentDigest": "d" * 64,
                    "identityReferenceProjectionDigest": "e" * 64,
                    "identityLockRef": "identity-lock-private",
                    "identityLockVersionRef": "identity-lock-version-private",
                    "identityLockDigest": "f" * 64,
                    "basePlateFileDigest": "sha256:" + "8" * 64,
                    "basePlatePixelDigest": "sha256:" + "9" * 64,
                    "markFileDigest": "sha256:" + "a" * 64,
                    "markPixelDigest": "sha256:" + "b" * 64,
                }
            )
        return {
            "requirement": {
                **requirement,
            },
            "executionRequest": {
                "executionRequestRef": f"execution-{effect_kind.lower()}",
                "payloadDigest": "2" * 64,
                "storageKey": "private/effect/input",
                "ffmpegFilter": "movie=/private/base.mp4;overlay",
                "filterGraph": "private-filter-graph",
                "ffmpegArgv": ["ffmpeg", "-i", "/private/base.mp4"],
                "environmentOverride": {"TOKEN": "private"},
            },
            "artifactEvidence": {
                "artifactEvidenceRef": f"artifact-{effect_kind.lower()}",
                "payloadDigest": "3" * 64,
                "outputFileDigest": "sha256:" + "4" * 64,
                "outputMediaProbe": {
                    "width": 64,
                    "height": 64,
                    "frameCount": 4,
                },
                "artifactPath": "/private/output.mp4",
            },
            "runtimeEvidence": {
                "runtimeEvidenceRef": f"runtime-{effect_kind.lower()}",
                "payloadDigest": "5" * 64,
                "rendererIdentity": "v3.deterministic-effect-test",
                "privateRuntimeDiagnostics": {"stderr": "private"},
            },
            "result": {
                "resultRef": f"result-{effect_kind.lower()}",
                "effectMode": effect_kind,
                "state": "COMPOSED_CANDIDATE",
                "publicationAllowed": False,
                "payloadDigest": "6" * 64,
                "executionResult": {
                    "shellCommand": "ffmpeg private",
                    "outputPath": "/private/output.mp4",
                },
            },
        }

    def execute_deterministic_effect(self, command: dict) -> dict:
        if command.get("workspaceRef") != WORKSPACE:
            raise ScopeMismatchError("deterministic effect scope mismatch")
        self.commands.append(deepcopy(command))
        return {
            "idempotentReplay": False,
            "deterministicEffect": self._private_chain(command["effectKind"]),
        }

    def get_deterministic_effects(
        self, workspace_ref: str, run_ref: str
    ) -> dict:
        if workspace_ref != WORKSPACE:
            raise ScopeMismatchError("deterministic effect scope mismatch")
        self.get_scopes.append((workspace_ref, run_ref))
        return {
            "deterministicEffects": [
                self._private_chain(effect_kind)
                for effect_kind in self.listed_effect_kinds
            ],
            "publicationAllowed": False,
        }


class M13E2DeterministicEffectsHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.delivery = _DeterministicEffectDeliveryStub()
        boundary = object.__new__(EpisodeProductionPublicBoundary)
        setattr(
            boundary,
            "_EpisodeProductionPublicBoundary__delivery",
            self.delivery,
        )
        self.token = secrets.token_urlsafe(48)
        self.foreign_token = secrets.token_urlsafe(48)
        authenticator = PublicApiAuthenticator.from_mapping(
            {
                "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                "credentials": [
                    {
                        "credentialRef": "creator-m13-e2-http",
                        "workspaceRef": WORKSPACE,
                        "tokenSha256": token_sha256(self.token),
                        "enabled": True,
                    },
                    {
                        "credentialRef": "creator-m13-e2-http-foreign",
                        "workspaceRef": "workspace-m13-e2-http-foreign",
                        "tokenSha256": token_sha256(self.foreign_token),
                        "enabled": True,
                    },
                ],
            }
        )
        assembly, _, _, _, _, _ = seed_k2_roots()
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(FakeTextGenerationCapability([])),
            series_episode_boundary=assembly.series_episode,
            project_boundary=assembly.project_context,
            series_planning_boundary=assembly.series_planning,
            series_intelligence_boundary=assembly.series_intelligence,
            script_studio_boundary=assembly.script_studio,
            episode_production_boundary=boundary,
            public_authenticator=authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        encoded_run = parse.quote(RUN, safe="")
        self.effects_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run}/deterministic-effects"
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @staticmethod
    def _effect_payload(effect_kind: str = "FLAME_EXTINGUISH") -> dict:
        return {
            "expectedRunVersion": 1,
            "idempotencyKey": f"m13-e2-http-{effect_kind.lower()}",
            "effectKind": effect_kind,
            "requirement": {
                "effectMode": effect_kind,
                "requirementRef": f"requirement-{effect_kind.lower()}",
                "targetShotRef": "shot-m13-e2-http",
                "targetShotVersionRef": "shot-version-m13-e2-http",
                "targetShotVersionDigest": "a" * 64,
            },
        }

    @staticmethod
    def _e3_effect_payload(effect_kind: str) -> dict:
        requirement = {
            "effectMode": effect_kind,
            "requirementRef": f"requirement-{effect_kind.lower()}-http",
            "targetShotRef": "shot-m13-e3-http",
            "targetShotVersionRef": "shot-version-m13-e3-http",
            "targetShotVersionDigest": "a" * 64,
            "basePlateAssetVersionRef": "base-version-m13-e3-http",
            "basePlateAssetVersionDigest": "b" * 64,
            "frameRangeStartInclusive": 0,
            "frameRangeEndExclusive": 8,
            "blendMode": "NORMAL",
            "layer": (
                6 if effect_kind == "NAMEPLATE_TEXT" else 7
            ),
        }
        if effect_kind == "NAMEPLATE_TEXT":
            requirement.update(
                {
                    "textSourceKind": "SCRIPT_TEXT",
                    "textSourceRef": "script-m13-e3-http",
                    "textSourceVersionRef": "script-version-m13-e3-http",
                    "textSourceDigest": "c" * 64,
                    "fontAssetVersionRef": "font-version-m13-e3-http",
                    "fontAssetVersionDigest": "d" * 64,
                }
            )
        else:
            requirement.update(
                {
                    "characterRef": "character-m13-e3-http",
                    "markType": "MOLE",
                    "markAssetVersionRef": "mark-version-m13-e3-http",
                    "markAssetVersionDigest": "e" * 64,
                    "faceRegion": "LEFT_CHEEK",
                    "trackingSourceKind": "EXPLICIT_KEYFRAMES",
                    "occlusionPolicy": "ALWAYS_VISIBLE_WITHIN_TRACK",
                }
            )
        return {
            "expectedRunVersion": 1,
            "idempotencyKey": f"m13-e3-http-{effect_kind.lower()}",
            "effectKind": effect_kind,
            "requirement": requirement,
        }

    def _post(
        self,
        path: str,
        payload: dict,
        *,
        token: str | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token or self.token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(http_request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _get(
        self, path: str, *, token: str | None = None
    ) -> tuple[int, dict]:
        http_request = request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {token or self.token}"},
        )
        with request.urlopen(http_request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _assert_error(
        self,
        operation,
        *,
        status: int,
        code: str,
    ) -> None:
        with self.assertRaises(error.HTTPError) as caught:
            operation()
        self.assertEqual(caught.exception.code, status)
        payload = json.loads(caught.exception.read().decode("utf-8"))
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], code)

    def _assert_sanitized(self, value: object) -> None:
        _assert_public_effect_sanitized(self, value)

    def test_post_and_get_use_authenticated_scope_and_redact_internals(self) -> None:
        status, created = self._post(
            self.effects_path,
            self._effect_payload(),
        )
        self.assertEqual(status, 201)
        self.assertFalse(created["idempotentReplay"])
        self._assert_sanitized(created)
        self.assertEqual(len(self.delivery.commands), 1)
        self.assertEqual(self.delivery.commands[0]["workspaceRef"], WORKSPACE)
        self.assertEqual(self.delivery.commands[0]["productionRunRef"], RUN)

        status, current = self._get(self.effects_path)
        self.assertEqual(status, 200)
        self.assertEqual(self.delivery.get_scopes, [(WORKSPACE, RUN)])
        self.assertEqual(len(current["deterministicEffects"]), 2)
        self._assert_sanitized(current)

    def test_closed_kinds_scope_and_private_execution_claims_are_rejected(self) -> None:
        base = self._effect_payload()
        invalid_payloads = [
            {key: value for key, value in base.items() if key != "expectedRunVersion"},
            {**base, "expectedRunVersion": 0},
            {**base, "expectedRunVersion": True},
            {**base, "expectedRunVersion": "1"},
            {**base, "requirement": []},
            {**base, "unexpected": True},
            {**base, "effectKind": "LOCAL_EXPOSURE"},
            {
                **base,
                "effectKind": "SMOKE",
                "requirement": {**base["requirement"], "effectMode": "FLAME_EXTINGUISH"},
            },
            {**base, "workspaceRef": WORKSPACE},
            {**base, "productionRunRef": RUN},
        ]
        for field, value in (
            ("path", "/tmp/browser.mp4"),
            ("absolutePath", "/tmp/browser.mp4"),
            ("storageKey", "browser/object"),
            ("filter", "overlay"),
            ("ffmpegFilter", "movie=/tmp/browser.mp4"),
            ("argv", ["ffmpeg", "-version"]),
            ("ffmpegArgv", ["ffmpeg", "-i", "/tmp/browser.mp4"]),
            ("shellCommand", "ffmpeg private"),
            ("pythonExpression", "__import__('os')"),
            ("modelPath", "/tmp/model"),
            ("networkUrl", "https://example.invalid/smoke"),
            ("environmentOverride", {"TOKEN": "private"}),
            ("actorRef", "browser-actor"),
            ("approvalRef", "browser-approval"),
            ("publicationAllowed", True),
            ("canonicalMutations", ["publish"]),
            ("rawAssetVersion", {"assetVersionRef": "forged"}),
            ("rawTimelineVersion", {"timelineVersionRef": "forged"}),
        ):
            invalid_payloads.append(
                {
                    **base,
                    "requirement": {**base["requirement"], field: value},
                }
            )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                code = (
                    "client_workspace_scope_forbidden"
                    if "workspaceRef" in payload
                    else "invalid_request"
                )
                self._assert_error(
                    lambda payload=payload: self._post(self.effects_path, payload),
                    status=400,
                    code=code,
                )
        self.assertEqual(self.delivery.commands, [])

        self._assert_error(
            lambda: self._post(
                f"{self.effects_path}?workspaceRef={parse.quote(WORKSPACE)}",
                base,
            ),
            status=400,
            code="client_workspace_scope_forbidden",
        )
        self.assertEqual(self.delivery.commands, [])

        self._assert_error(
            lambda: self._post(
                self.effects_path,
                base,
                token=self.foreign_token,
            ),
            status=400,
            code="scope_mismatch",
        )
        self._assert_error(
            lambda: self._get(
                self.effects_path,
                token=self.foreign_token,
            ),
            status=400,
            code="scope_mismatch",
        )

    def test_only_generic_resource_is_exposed_and_capability_is_projected(self) -> None:
        status, capabilities = self._get(CAPABILITIES_ENDPOINT)
        self.assertEqual(status, 200)
        m13 = next(
            item for item in capabilities["capabilities"] if item["id"] == "M13"
        )
        self.assertIn(
            "episode-production-runs/deterministic-effects",
            m13["publicResources"],
        )

        base_prefix = self.effects_path.rsplit("/", 1)[0]
        for resource in ("m13", "flame", "smoke", "ffmpeg", "composition"):
            with self.subTest(resource=resource):
                self._assert_error(
                    lambda resource=resource: self._post(
                        f"{base_prefix}/{resource}",
                        self._effect_payload(),
                    ),
                    status=404,
                    code="not_found",
                )

    def test_e3_socket_rejects_server_claims_and_redacts_post_get(self) -> None:
        self.assertEqual(len(EPISODE_PRODUCTION_SUBRESOURCES), 30)
        self.assertIn(
            "deterministic-effects", EPISODE_PRODUCTION_SUBRESOURCES
        )
        base_prefix = self.effects_path.rsplit("/", 1)[0]
        for resource in (
            "nameplate-text",
            "face-mark-compensation",
            "fonts",
            "identity-references",
        ):
            with self.subTest(route=resource):
                self._assert_error(
                    lambda resource=resource: self._post(
                        f"{base_prefix}/{resource}",
                        self._e3_effect_payload("NAMEPLATE_TEXT"),
                    ),
                    status=404,
                    code="not_found",
                )

        forbidden_by_kind = {
            "NAMEPLATE_TEXT": {
                "basePlateFileDigest": "sha256:" + "0" * 64,
                "basePlatePixelDigest": "sha256:" + "1" * 64,
                "resolvedText": "client-forged",
                "resolvedTextDigest": "2" * 64,
                "language": "zh-CN",
                "fontFileDigest": "3" * 64,
                "fontTechnicalValidationRef": "client-validation",
                "fontTechnicalValidationDigest": "4" * 64,
                "fontLicenseBindingVersionRef": "client-license",
                "fontLicenseBindingVersionDigest": "5" * 64,
                "storageBindingRef": "client-font-storage",
                "fontPath": "/tmp/client-font.ttf",
                "ffmpegFilter": "drawtext=fontfile=/tmp/client-font.ttf",
            },
            "FACE_MARK_COMPENSATION": {
                "basePlateFileDigest": "sha256:" + "0" * 64,
                "basePlatePixelDigest": "sha256:" + "1" * 64,
                "identityVersionRef": "client-identity-version",
                "identityVersionDigest": "5" * 64,
                "identityReferenceRef": "client-identity",
                "identityReferenceVersionRef": "client-identity-version",
                "identityReferenceContentDigest": "6" * 64,
                "identityReferenceProjectionDigest": "7" * 64,
                "identityLockRef": "client-lock",
                "identityLockVersionRef": "client-lock-version",
                "identityLockDigest": "8" * 64,
                "markFileDigest": "sha256:" + "9" * 64,
                "markPixelDigest": "sha256:" + "a" * 64,
                "storageKey": "client/mark.png",
                "markPath": "/tmp/client-mark.png",
                "filterExpression": "movie=/tmp/client-mark.png",
            },
        }
        for effect_kind, forbidden in forbidden_by_kind.items():
            base = self._e3_effect_payload(effect_kind)
            for field, value in forbidden.items():
                with self.subTest(effect_kind=effect_kind, field=field):
                    payload = deepcopy(base)
                    payload["requirement"][field] = value
                    self._assert_error(
                        lambda payload=payload: self._post(
                            self.effects_path, payload
                        ),
                        status=400,
                        code="invalid_request",
                    )
        self.assertEqual(self.delivery.commands, [])

        created_by_kind = {}
        for effect_kind in ("NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"):
            status, created = self._post(
                self.effects_path,
                self._e3_effect_payload(effect_kind),
            )
            self.assertEqual(status, 201)
            self.assertEqual(
                created["deterministicEffect"]["result"]["effectMode"],
                effect_kind,
            )
            self._assert_sanitized(created)
            created_by_kind[effect_kind] = created

        self.delivery.listed_effect_kinds = [
            "NAMEPLATE_TEXT",
            "FACE_MARK_COMPENSATION",
        ]
        status, current = self._get(self.effects_path)
        self.assertEqual(status, 200)
        self.assertEqual(
            [
                item["result"]["effectMode"]
                for item in current["deterministicEffects"]
            ],
            ["NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"],
        )
        self._assert_sanitized(current)
        self.assertEqual(len(created_by_kind), 2)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13E2DeterministicEffectsRealHttpTests(unittest.TestCase):
    def test_real_smoke_post_executes_v4_and_persists_public_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_root = root / "artifacts"
            inputs = _source_template(artifact_root)
            run, storyboard, graph = _authority(inputs)
            inputs = type(inputs)(
                audio=inputs.audio,
                base=inputs.base,
                masks=inputs.masks,
                inspection=inputs.inspection,
                requirement=inputs.requirement,
                run=run,
            )
            repository = SqliteEpisodeProductionEvidenceAdapter(
                root / "evidence.sqlite3",
                initialize_if_missing=True,
            )
            _seed_real_video_ready(repository, run, storyboard, graph)
            service = _service(
                artifact_root,
                repository,
                inputs,
                run,
                graph,
            )
            _register_inputs(service, inputs)

            base = inputs.base
            emission_mask = inputs.masks[2]
            decoded = decoded_frame_pixel_digest_metadata(
                artifact_root / base["storageKey"]
            )
            requirement = _smoke_command(procedural=True)
            requirement.update(
                {
                    "requirementRef": "m13-e2-http-real-smoke-requirement",
                    "targetShotRef": base["creativeShotRef"],
                    "targetShotVersionRef": base["creativeShotVersionRef"],
                    "targetShotVersionDigest": base["creativeShotDigest"],
                    "basePlateAssetVersionRef": base["assetVersionRef"],
                    "basePlateAssetVersionDigest": base["payloadDigest"],
                    "basePlateFileDigest": f"sha256:{base['sha256']}",
                    "basePlatePixelDigest": decoded[
                        "decodedFramePixelDigest"
                    ],
                    "emissionMaskAssetVersionRef": emission_mask[
                        "assetVersionRef"
                    ],
                    "emissionMaskAssetVersionDigest": emission_mask[
                        "payloadDigest"
                    ],
                    "emissionMaskFileDigest": (
                        f"sha256:{emission_mask['sha256']}"
                    ),
                    "emissionMaskPixelDigest": emission_mask["pixelDigest"],
                }
            )
            requirement.pop("workspaceRef")
            requirement.pop("productionRunRef")

            token = secrets.token_urlsafe(48)
            authenticator = PublicApiAuthenticator.from_mapping(
                {
                    "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                    "credentials": [
                        {
                            "credentialRef": "creator-m13-e2-http-real",
                            "workspaceRef": run["workspaceRef"],
                            "tokenSha256": token_sha256(token),
                            "enabled": True,
                        }
                    ],
                }
            )
            assembly, _, _, _, _, _ = seed_k2_roots()
            server = create_server(
                ("127.0.0.1", 0),
                AiDirectorService(FakeTextGenerationCapability([])),
                series_episode_boundary=assembly.series_episode,
                project_boundary=assembly.project_context,
                series_planning_boundary=assembly.series_planning,
                series_intelligence_boundary=assembly.series_intelligence,
                script_studio_boundary=assembly.script_studio,
                episode_production_boundary=_public(service),
                public_authenticator=authenticator,
                allow_internal_routes=False,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            effects_path = (
                f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
                f"{parse.quote(run['productionRunRef'], safe='')}/"
                "deterministic-effects"
            )
            url = f"http://127.0.0.1:{server.server_port}{effects_path}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {
                "expectedRunVersion": 1,
                "idempotencyKey": "m13-e2-http-real-smoke-key",
                "effectKind": "SMOKE",
                "requirement": requirement,
            }
            try:
                http_request = request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    method="POST",
                    headers=headers,
                )
                with request.urlopen(http_request, timeout=30) as response:
                    created = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 201)
                self.assertTrue(created["ok"])
                self.assertFalse(created["idempotentReplay"])
                chain = created["deterministicEffect"]
                self.assertEqual(chain["result"]["effectMode"], "SMOKE")
                self.assertEqual(
                    chain["result"]["state"], "COMPOSED_CANDIDATE"
                )
                self.assertEqual(
                    chain["artifactEvidence"]["outputDigest"][
                        "decodedFramePixelDigestSpec"
                    ],
                    decoded["decodedFramePixelDigestSpec"],
                )
                self.assertNotEqual(
                    chain["artifactEvidence"]["outputDigest"][
                        "decodedFramePixelDigest"
                    ],
                    decoded["decodedFramePixelDigest"],
                )
                _assert_public_effect_sanitized(self, created)

                current_request = request.Request(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                )
                with request.urlopen(current_request, timeout=30) as response:
                    current = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(response.status, 200)
                self.assertEqual(len(current["deterministicEffects"]), 1)
                self.assertEqual(
                    current["deterministicEffects"][0]["result"][
                        "payloadDigest"
                    ],
                    chain["result"]["payloadDigest"],
                )
                _assert_public_effect_sanitized(self, current)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
