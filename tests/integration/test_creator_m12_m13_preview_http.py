from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import secrets
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
    PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)
from services.v5_core_os.episode_production.timeline_preview import (
    TECHNICAL_FIXTURE_LABELS,
)
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.integration.test_m12_m13_minimal_preview import (
    _preview_command,
    _register_inputs,
    _seed_media_ready,
    _service,
    _source_template,
)
from tests.unit.test_episode_production_k2 import seed_k2_roots


HTTP_TIMEOUT_SECONDS = 180
FOREIGN_WORKSPACE = "workspace-m12-foreign"


class CreatorM12M13PreviewHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.artifact_root = Path(self.temporary_directory.name)
        self.inputs = _source_template(self.artifact_root)
        self.delivery, self.evidence, self.composition = _service(
            self.artifact_root,
            self.artifact_root / "creator-preview-evidence.sqlite3",
            self.inputs,
            initialize=True,
        )
        _seed_media_ready(self.evidence, self.inputs)

        # The public boundary remains the single application-facing owner.  The
        # fixture replaces only its delivery collaborator because this test is
        # scoped to the already-existing preview routes.
        self.public_boundary = object.__new__(EpisodeProductionPublicBoundary)
        setattr(
            self.public_boundary,
            "_EpisodeProductionPublicBoundary__delivery",
            self.delivery,
        )
        self.registration = _register_inputs(
            self.public_boundary,
            self.inputs,
        )

        self.token = secrets.token_urlsafe(48)
        self.foreign_token = secrets.token_urlsafe(48)
        authenticator = PublicApiAuthenticator.from_mapping(
            {
                "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                "credentials": [
                    {
                        "credentialRef": "creator-preview-primary",
                        "workspaceRef": self.inputs.run["workspaceRef"],
                        "tokenSha256": token_sha256(self.token),
                        "enabled": True,
                    },
                    {
                        "credentialRef": "creator-preview-foreign",
                        "workspaceRef": FOREIGN_WORKSPACE,
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
            episode_production_boundary=self.public_boundary,
            public_authenticator=authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        encoded_run_ref = parse.quote(
            self.inputs.run["productionRunRef"],
            safe="",
        )
        self.preview_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run_ref}/preview"
        )
        self.content_path = f"{self.preview_path}/content"
        self.delivery_path = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/"
            f"{encoded_run_ref}/delivery"
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary_directory.cleanup()

    def _post(
        self,
        payload: dict,
        *,
        token: str | None = None,
    ) -> tuple[int, dict]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}{self.preview_path}",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token or self.token}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(
            http_request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8")),
            )

    def _get_json(
        self,
        path: str,
        *,
        token: str | None = None,
    ) -> tuple[int, dict]:
        http_request = request.Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {token or self.token}"},
        )
        with request.urlopen(
            http_request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8")),
            )

    def _get_bytes(
        self,
        *,
        token: str | None = None,
    ) -> tuple[int, object, bytes]:
        http_request = request.Request(
            f"{self.base_url}{self.content_path}",
            headers={"Authorization": f"Bearer {token or self.token}"},
        )
        with request.urlopen(
            http_request,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as response:
            return response.status, response.headers, response.read()

    def _assert_http_error(
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

    def _assert_preview_is_sanitized(self, value: object) -> None:
        forbidden_exact = {
            "absolutepath",
            "artifactpath",
            "artifactroot",
            "argv",
            "candidatepath",
            "credential",
            "credentialref",
            "diagnostics",
            "ffmpegargv",
            "ffmpegcommand",
            "ffmpegfilter",
            "filesystempath",
            "filter",
            "filterexpression",
            "finalpath",
            "inputpath",
            "internalpath",
            "outputpath",
            "path",
            "privatediagnostics",
            "privateruntimediagnostics",
            "runtimediagnostics",
            "stderr",
            "stdout",
            "token",
        }

        def visit(item: object) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    normalized = key.replace("_", "").replace("-", "").lower()
                    self.assertNotIn(normalized, forbidden_exact)
                    self.assertFalse(normalized.endswith("storagekey"))
                    self.assertFalse(normalized.endswith("storagekeys"))
                    self.assertFalse(normalized.endswith("argv"))
                    self.assertFalse(normalized.endswith("filterexpression"))
                    visit(nested)
            elif isinstance(item, (list, tuple)):
                for nested in item:
                    visit(nested)

        visit(value)

    def _composition_artifact_path(self) -> Path:
        records = self.evidence.list_records(
            self.inputs.run["workspaceRef"],
            self.inputs.run["productionRunRef"],
        )
        matches = [
            item["payload"]
            for item in records
            if item["recordKind"] == "CompositionResult"
        ]
        self.assertEqual(len(matches), 1)
        return self.artifact_root / matches[0]["outputStorageKey"]

    def test_authenticated_closed_preview_chain_and_tamper_rejection(self) -> None:
        internal_command = _preview_command(
            self.inputs,
            self.registration,
        )
        public_command = {
            key: deepcopy(value)
            for key, value in internal_command.items()
            if key not in {"workspaceRef", "productionRunRef"}
        }
        self.assertEqual(
            set(public_command),
            {
                "operationRef",
                "idempotencyKey",
                "expectedRunVersion",
                "expectedEvidenceRevision",
                "timelineInputRefs",
            },
        )

        workspace_override = {
            **deepcopy(public_command),
            "workspaceRef": self.inputs.run["workspaceRef"],
        }
        self._assert_http_error(
            lambda: self._post(workspace_override),
            status=400,
            code="client_workspace_scope_forbidden",
        )
        run_override = {
            **deepcopy(public_command),
            "productionRunRef": self.inputs.run["productionRunRef"],
        }
        self._assert_http_error(
            lambda: self._post(run_override),
            status=400,
            code="invalid_request",
        )
        for field, value in (
            ("absolutePath", "/tmp/client-selected-preview.mp4"),
            ("ffmpegFilter", "movie=/tmp/input.mp4;[0:v]overlay"),
            ("publicationAllowed", True),
        ):
            with self.subTest(rejected_field=field):
                self._assert_http_error(
                    lambda field=field, value=value: self._post(
                        {**deepcopy(public_command), field: value}
                    ),
                    status=400,
                    code="invalid_request",
                )

        status, created = self._post(public_command)
        self.assertEqual(status, 201)
        self.assertTrue(created["ok"])
        self.assertEqual(created["state"], "QC_READY")
        self.assertFalse(created["idempotentReplay"])
        self.assertEqual(
            created["timelineVersion"]["workspaceRef"],
            self.inputs.run["workspaceRef"],
        )
        self.assertEqual(
            created["timelineVersion"]["productionRunRef"],
            self.inputs.run["productionRunRef"],
        )
        self.assertFalse(created["previewCandidate"]["publicationAllowed"])
        self.assertFalse(created["qcReport"]["publicationAllowed"])
        self._assert_preview_is_sanitized(created)

        status, replay = self._post(public_command)
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            replay["previewCandidate"]["payloadDigest"],
            created["previewCandidate"]["payloadDigest"],
        )
        self._assert_preview_is_sanitized(replay)

        status, projection = self._get_json(self.preview_path)
        self.assertEqual(status, 200)
        self.assertTrue(projection["ok"])
        self.assertEqual(projection["state"], "QC_READY")
        self.assertEqual(
            projection["productionRunRef"],
            self.inputs.run["productionRunRef"],
        )
        self.assertFalse(projection["preview"]["publicationAllowed"])
        self.assertEqual(
            projection["preview"]["compositionRequestDigest"],
            created["previewCandidate"]["compositionRequestDigest"],
        )
        self.assertEqual(
            projection["preview"]["runtimeIdentity"],
            created["previewCandidate"]["runtimeIdentity"],
        )
        self.assertEqual(
            projection["preview"]["mediaProbe"],
            projection["preview"]["outputMediaProbe"],
        )
        self.assertEqual(
            projection["audio"]["bindings"][0]["sourceLabels"],
            sorted(TECHNICAL_FIXTURE_LABELS),
        )
        self.assertEqual(projection["effect"]["layer"], 1)
        self.assertEqual(
            projection["effect"]["blendMode"],
            projection["effect"]["compositeParams"]["blendMode"],
        )
        self._assert_preview_is_sanitized(projection)

        status, delivery = self._get_json(self.delivery_path)
        self.assertEqual(status, 200)
        self.assertTrue(delivery["ok"])
        self.assertEqual(delivery["state"], "QC_READY")
        self.assertEqual(
            delivery["timelineVersion"]["payloadDigest"],
            created["timelineVersion"]["payloadDigest"],
        )
        self._assert_preview_is_sanitized(delivery)

        status, headers, content = self._get_bytes()
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "video/mp4")
        self.assertEqual(int(headers["Content-Length"]), len(content))
        expected_sha256 = projection["preview"]["fileDigest"].removeprefix(
            "sha256:"
        )
        self.assertEqual(sha256(content).hexdigest(), expected_sha256)
        self.assertEqual(
            len(content),
            projection["preview"]["outputByteSize"],
        )

        self._assert_http_error(
            lambda: self._get_json(
                self.preview_path,
                token=self.foreign_token,
            ),
            status=409,
            code="upstream_not_confirmed",
        )

        artifact_path = self._composition_artifact_path()
        original = artifact_path.read_bytes()
        self.assertEqual(len(original), len(content))
        tampered = bytearray(original)
        tampered[-1] ^= 1
        artifact_path.write_bytes(tampered)
        self.assertEqual(artifact_path.stat().st_size, len(original))

        self._assert_http_error(
            lambda: self._get_json(self.preview_path),
            status=422,
            code="artifact_verification_failed",
        )
        self._assert_http_error(
            self._get_bytes,
            status=422,
            code="artifact_verification_failed",
        )


if __name__ == "__main__":
    unittest.main()
