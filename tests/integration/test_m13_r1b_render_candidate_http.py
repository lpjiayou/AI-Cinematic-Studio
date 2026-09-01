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
from services.v5_core_os.episode_production.foundation import ScopeMismatchError
from services.v5_core_os.episode_production.public import (
    EpisodeProductionPublicBoundary,
)
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.unit.test_episode_production_k2 import seed_k2_roots


WORKSPACE = "workspace-m13-r1b-http"
FOREIGN_WORKSPACE = "workspace-m13-r1b-http-foreign"
RUN = "run-m13-r1b-http"
CANDIDATE = "candidate-m13-r1b-http"


class _DeliveryStub:
    def __init__(self, content_path: Path) -> None:
        self.content_path = content_path
        self.commands: list[dict] = []

    @staticmethod
    def _scope(workspace_ref: str) -> None:
        if workspace_ref != WORKSPACE:
            raise ScopeMismatchError("RenderCandidate scope mismatch")

    @staticmethod
    def _candidate() -> dict:
        return {
            "renderCandidateRef": CANDIDATE,
            "state": "RENDERED_CANDIDATE",
            "technicalValidationState": "PASS",
            "qcState": "NOT_RUN",
            "approvalState": "NOT_REQUESTED",
            "assetAdmissionState": "NOT_ADMITTED",
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
            "publicationAllowed": False,
            "storageBindingRef": "private-binding",
        }

    def create_render_candidate(self, command: dict) -> dict:
        self._scope(command.get("workspaceRef"))
        if command.get("productionRunRef") != RUN:
            raise ScopeMismatchError("RenderCandidate run mismatch")
        self.commands.append(deepcopy(command))
        return {
            "renderCandidate": self._candidate(),
            "runtimeEvidence": {
                "runtimeEvidenceRef": "runtime-1",
                "internalPath": "/private/runtime",
                "gpuUsed": False,
                "providerUsed": False,
                "publicationAllowed": False,
            },
            "artifactEvidence": {
                "artifactEvidenceRef": "artifact-1",
                "outputStorageKey": "private/output.mp4",
                "publicationAllowed": False,
            },
            "renderResult": {
                "renderResultRef": "result-1",
                "publicationAllowed": False,
            },
            "publicationAllowed": False,
            "idempotentReplay": False,
        }

    def list_render_candidates(self, workspace_ref: str, run_ref: str) -> dict:
        self._scope(workspace_ref)
        return {
            "renderCandidates": [self._candidate()],
            "publicationAllowed": False,
            "idempotentReplay": False,
        }

    def get_render_candidate(
        self, workspace_ref: str, run_ref: str, candidate_ref: str
    ) -> dict:
        self._scope(workspace_ref)
        if run_ref != RUN or candidate_ref != CANDIDATE:
            raise ScopeMismatchError("RenderCandidate identity mismatch")
        return {
            "renderCandidate": self._candidate(),
            "publicationAllowed": False,
            "idempotentReplay": False,
        }

    def get_render_candidate_content(
        self, workspace_ref: str, run_ref: str, candidate_ref: str
    ) -> dict:
        self._scope(workspace_ref)
        if run_ref != RUN or candidate_ref != CANDIDATE:
            raise ScopeMismatchError("RenderCandidate identity mismatch")
        body = self.content_path.read_bytes()
        return {
            "path": self.content_path,
            "byteSize": len(body),
            "sha256": sha256(body).hexdigest(),
            "mediaType": "video/mp4",
            "fileName": "candidate.mp4",
            "contentDisposition": "inline",
        }


class M13R1BRenderCandidateHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        content_path = Path(self.temporary.name) / "candidate.mp4"
        content_path.write_bytes(b"deterministic-render-candidate")
        self.delivery = _DeliveryStub(content_path)
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
                        "credentialRef": "creator-r1b-http",
                        "workspaceRef": WORKSPACE,
                        "tokenSha256": token_sha256(self.token),
                        "enabled": True,
                    },
                    {
                        "credentialRef": "creator-r1b-http-foreign",
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
            episode_production_boundary=boundary,
            public_authenticator=authenticator,
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        encoded_run = parse.quote(RUN, safe="")
        encoded_candidate = parse.quote(CANDIDATE, safe="")
        self.collection = (
            f"{PUBLIC_EPISODE_PRODUCTION_RUNS_ENDPOINT}/{encoded_run}/"
            "render-candidates"
        )
        self.detail = f"{self.collection}/{encoded_candidate}"
        self.content = f"{self.detail}/content"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    @staticmethod
    def _payload() -> dict:
        return {
            "operationRef": "operation-r1b-http",
            "idempotencyKey": "idempotency-r1b-http",
            "expectedRunVersion": 1,
            "timelineVersionRef": "timeline-version-1",
            "timelineVersionDigest": "a" * 64,
            "compositionVersionRef": "composition-version-1",
            "compositionVersionDigest": "b" * 64,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": "c" * 64,
        }

    def _open(self, value: request.Request):
        return request.urlopen(value, timeout=10)

    def test_authenticated_post_list_detail_and_inline_content(self) -> None:
        body = json.dumps(self._payload()).encode()
        post = request.Request(
            self.base_url + self.collection,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        with self._open(post) as response:
            self.assertEqual(response.status, 201)
            created = json.loads(response.read().decode())
        self.assertEqual(
            self.delivery.commands[0]["workspaceRef"], WORKSPACE
        )
        self.assertEqual(self.delivery.commands[0]["productionRunRef"], RUN)
        rendered = json.dumps(created).lower()
        for forbidden in (
            "storagebindingref",
            "storagekey",
            "internalpath",
            "outputstoragekey",
        ):
            self.assertNotIn(forbidden, rendered)
        for path in (self.collection, self.detail):
            query = request.Request(
                self.base_url + path,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            with self._open(query) as response:
                self.assertEqual(response.status, 200)
                payload = json.loads(response.read().decode())
                self.assertNotIn("storageBindingRef", json.dumps(payload))
        content = request.Request(
            self.base_url + self.content,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        with self._open(content) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(
                response.headers["Content-Disposition"],
                'inline; filename="candidate.mp4"',
            )
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.read(), b"deterministic-render-candidate")

    def test_authentication_foreign_scope_and_open_client_claims_are_rejected(self) -> None:
        unauthenticated = request.Request(self.base_url + self.collection)
        with self.assertRaises(error.HTTPError) as captured:
            self._open(unauthenticated)
        self.assertEqual(captured.exception.code, 401)
        foreign = request.Request(
            self.base_url + self.collection,
            headers={"Authorization": f"Bearer {self.foreign_token}"},
        )
        with self.assertRaises(error.HTTPError) as captured:
            self._open(foreign)
        self.assertEqual(captured.exception.code, 400)
        for field, value in (
            ("absolutePath", "/private/input.mp4"),
            ("storageKey", "private/input.mp4"),
            ("ffmpegFilter", "movie=private"),
            ("argv", ["ffmpeg"]),
            ("publicationAllowed", False),
        ):
            payload = {**self._payload(), field: value}
            post = request.Request(
                self.base_url + self.collection,
                data=json.dumps(payload).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            )
            with self.subTest(field=field), self.assertRaises(
                error.HTTPError
            ) as captured:
                self._open(post)
            self.assertEqual(captured.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
