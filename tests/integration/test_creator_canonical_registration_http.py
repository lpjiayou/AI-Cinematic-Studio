import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import unittest
from urllib import error, request

from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.public_auth import PublicApiAuthenticator
from apps.creator_workspace_mvp.public_contract import (
    PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
    PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
)
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    migrate_lifecycle_database,
)
from services.v5_core_os.script_studio.foundation import (
    VerifiedScriptAcceptance,
)
from services.v5_core_os.text_generation.testing import (
    FakeTextGenerationCapability,
)
from tests.unit.test_ai_director_phase1 import valid_plan
from tests.unit.test_canonical_registration import (
    NOW,
    TARGET,
    WORKSPACE,
    registration_command,
)


class ExactRuntimeAuthority:
    def verify(self, *, subject, approval_ref):
        return VerifiedScriptAcceptance.create(
            authorityRef="authority-public-registration-test",
            approvalRef=approval_ref,
            actorRef="project-lead-public-test",
            actorKind="PROJECT_LEAD",
            decision="ACCEPTED",
            authorityDecisionRef="decision-public-registration-test",
            authorityDecisionDigest="d" * 64,
            decidedAt="2026-08-26",
            governanceRecordRef="ACS-K2-002-SCRIPT-ACC3",
            subjectDigest=subject.subject_digest,
        )


def public_command():
    value = registration_command()
    value.pop("workspaceRef")
    value.pop("importedByRef")
    return value


class CreatorCanonicalRegistrationHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "lifecycle.sqlite3"
        migrate_lifecycle_database(self.path, allow_upgrade=True)
        self.assembly = LifecycleAssembly.sqlite(
            self.path,
            canonical_target_ref=TARGET,
            script_acceptance_authority=ExactRuntimeAuthority(),
            clock=lambda: NOW,
        )
        capability = FakeTextGenerationCapability(
            [json.dumps(valid_plan(), ensure_ascii=False)]
        )
        self.token = secrets.token_urlsafe(48)
        self.server = create_server(
            ("127.0.0.1", 0),
            AiDirectorService(capability),
            series_episode_boundary=self.assembly.series_episode,
            project_boundary=self.assembly.project_context,
            series_planning_boundary=self.assembly.series_planning,
            series_intelligence_boundary=self.assembly.series_intelligence,
            script_studio_boundary=self.assembly.script_studio,
            canonical_registration_boundary=(
                self.assembly.canonical_registration
            ),
            public_authenticator=PublicApiAuthenticator.for_token(
                self.token,
                WORKSPACE,
                credential_ref="credential-public-registration-test",
            ),
            allow_internal_routes=False,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def post(self, path, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        with request.urlopen(
            request.Request(
                f"{self.base}{path}",
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
            ),
            timeout=5,
        ) as response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )

    def test_authenticated_preflight_apply_and_replay(self):
        status, preview = self.post(
            PUBLIC_CANONICAL_REGISTRATION_PREFLIGHT_ENDPOINT,
            public_command(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            preview["preflight"]["canonicalMutationCount"], 0
        )
        status, applied = self.post(
            PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
            public_command(),
        )
        self.assertEqual(status, 201)
        self.assertFalse(applied["idempotentReplay"])
        self.assertEqual(
            applied["registrationReceipt"]["requestDigest"],
            preview["preflight"]["requestDigest"],
        )
        status, replay = self.post(
            PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
            public_command(),
        )
        self.assertEqual(status, 200)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            replay["registrationReceipt"],
            applied["registrationReceipt"],
        )
        with sqlite3.connect(self.path) as connection:
            content = json.loads(
                connection.execute(
                    "SELECT content_json FROM v5_script_versions"
                ).fetchone()[0]
            )
        self.assertEqual(
            content["importProvenance"]["importedByRef"],
            "credential-public-registration-test",
        )

    def test_client_cannot_inject_workspace_or_import_actor(self):
        for field, value in (
            ("workspaceRef", "forged-workspace"),
            ("importedByRef", "forged-actor"),
        ):
            with self.subTest(field=field), self.assertRaises(
                error.HTTPError
            ) as caught:
                self.post(
                    PUBLIC_CANONICAL_REGISTRATIONS_ENDPOINT,
                    {**public_command(), field: value},
                )
            self.assertEqual(caught.exception.code, 400)
            payload = json.loads(caught.exception.read().decode("utf-8"))
            self.assertIn(
                payload["error"]["code"],
                {"client_workspace_scope_forbidden", "invalid_request"},
            )


if __name__ == "__main__":
    unittest.main()
