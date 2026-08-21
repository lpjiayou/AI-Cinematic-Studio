from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import (
    ExternalAuthorityConfigurationError,
    identity_reference_authority_from_environment,
)
from services.v5_core_os.episode_production.authority import AuthorityRequiredError
from services.v5_core_os.episode_production.external_authority import (
    DigestPinnedIdentityReferenceAuthority,
)
from services.v5_core_os.episode_production import public as production_public
from services.v5_core_os.lifecycle_integrity import composition as lifecycle_composition
from services.v5_core_os.series_intelligence import (
    M6ExternalAuthorityConfigurationError,
    m6_external_authorities_from_environment,
)
from services.v5_core_os.series_intelligence.external_authority import (
    DigestPinnedM6ApprovalAuthority,
    DigestPinnedM6ScopeAuthority,
)
from services.v5_core_os.series_intelligence.errors import AuthorityUnavailableError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    path.write_bytes(payload)
    return sha256(payload).hexdigest()


def _m6_bundle():
    scope = {
        "businessDomain": "series-production",
        "tenantId": "tenant-k2",
        "workspaceRef": "workspace-k2",
        "projectRef": "project-k2",
        "seriesRef": "series-k2",
    }
    return {
        "schemaVersion": "v5.external-m6-authority-bundle.v1",
        "authorityRef": "m6-authority-k2-v1",
        "scopes": [scope],
        "approvals": [
            {
                "workspaceRef": scope["workspaceRef"],
                "projectRef": scope["projectRef"],
                "seriesRef": scope["seriesRef"],
                "approvalRef": "approval-k2-bible-v1",
                "action": "confirm-series-bible-version",
                "actorRef": "actor-project-owner",
                "actorKind": "human",
            },
            {
                "workspaceRef": scope["workspaceRef"],
                "projectRef": scope["projectRef"],
                "seriesRef": scope["seriesRef"],
                "approvalRef": "approval-k2-character-v1",
                "action": "confirm-character-continuity-version",
                "actorRef": "actor-project-owner",
                "actorKind": "human",
            },
            {
                "workspaceRef": scope["workspaceRef"],
                "projectRef": scope["projectRef"],
                "seriesRef": scope["seriesRef"],
                "approvalRef": "approval-k2-activation-v1",
                "action": "activate-m6-baseline",
                "actorRef": "actor-project-owner",
                "actorKind": "human",
            },
        ],
    }


def _identity_bundle():
    return {
        "schemaVersion": "v5.external-identity-reference-authority-bundle.v1",
        "authorityRef": "identity-authority-k2-v1",
        "references": [
            {
                "workspaceRef": "workspace-k2",
                "productionRunRef": "production-run-k2",
                "characterRef": "character-lin-che",
                "referenceRef": "identity-reference-lin-che",
                "referenceVersionRef": "identity-reference-version-lin-che-v1",
                "contentDigest": "4" * 64,
                "mediaType": "image",
                "rightsState": "APPROVED",
                "provenance": "AUTHORITY_APPROVED",
                "approvalRef": "approval-identity-lin-che-v1",
            }
        ],
    }


class K2G2ExternalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.m6_path = root / "m6-authority.json"
        self.identity_path = root / "identity-authority.json"
        self.m6_digest = _write(self.m6_path, _m6_bundle())
        self.identity_digest = _write(self.identity_path, _identity_bundle())

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return {
            "CREATOR_M6_AUTHORITY_BUNDLE_PATH": str(self.m6_path),
            "CREATOR_M6_AUTHORITY_BUNDLE_SHA256": self.m6_digest,
            "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_PATH": str(
                self.identity_path
            ),
            "CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256": (
                self.identity_digest
            ),
        }

    def test_no_configuration_remains_fail_closed(self):
        scope, approval = m6_external_authorities_from_environment({})
        with self.assertRaises(AuthorityUnavailableError):
            scope.resolve_scope("workspace-k2", "project-k2", "series-k2")
        with self.assertRaises(AuthorityUnavailableError):
            approval.verify_approval(
                scope=None,
                approval_ref="approval-k2-bible-v1",
                action="confirm-series-bible-version",
            )
        identity = identity_reference_authority_from_environment({})
        with self.assertRaises(AuthorityRequiredError):
            identity.authorize_reference(
                workspace_ref="workspace-k2",
                production_run_ref="production-run-k2",
                character={"characterRef": "character-lin-che"},
            )

    def test_digest_pinned_m6_authority_is_exact_scope_and_action(self):
        scope_authority, approval_authority = (
            m6_external_authorities_from_environment(self.environment())
        )
        self.assertIsInstance(scope_authority, DigestPinnedM6ScopeAuthority)
        self.assertIsInstance(approval_authority, DigestPinnedM6ApprovalAuthority)
        scope = scope_authority.resolve_scope(
            "workspace-k2", "project-k2", "series-k2"
        )
        actor = approval_authority.verify_approval(
            scope=scope,
            approval_ref="approval-k2-bible-v1",
            action="confirm-series-bible-version",
        )
        self.assertEqual(actor.actor_ref, "actor-project-owner")
        with self.assertRaises(AuthorityUnavailableError):
            scope_authority.resolve_scope(
                "workspace-other", "project-k2", "series-k2"
            )
        with self.assertRaises(AuthorityUnavailableError):
            approval_authority.verify_approval(
                scope=scope,
                approval_ref="approval-k2-bible-v1",
                action="activate-m6-baseline",
            )

    def test_scope_only_bundle_can_author_drafts_but_cannot_approve(self):
        bundle = _m6_bundle()
        bundle["approvals"] = []
        digest = _write(self.m6_path, bundle)
        environment = self.environment()
        environment["CREATOR_M6_AUTHORITY_BUNDLE_SHA256"] = digest
        scope_authority, approval_authority = (
            m6_external_authorities_from_environment(environment)
        )
        scope = scope_authority.resolve_scope(
            "workspace-k2", "project-k2", "series-k2"
        )
        with self.assertRaises(AuthorityUnavailableError):
            approval_authority.verify_approval(
                scope=scope,
                approval_ref="approval-not-yet-created",
                action="confirm-series-bible-version",
            )

    def test_digest_pinned_identity_is_exact_workspace_run_and_character(self):
        authority = identity_reference_authority_from_environment(self.environment())
        self.assertIsInstance(authority, DigestPinnedIdentityReferenceAuthority)
        decision = authority.authorize_reference(
            workspace_ref="workspace-k2",
            production_run_ref="production-run-k2",
            character={"characterRef": "character-lin-che"},
        )
        self.assertEqual(decision["contentDigest"], "4" * 64)
        for wrong in ("workspace-other", "production-run-other"):
            values = {
                "workspace_ref": "workspace-k2",
                "production_run_ref": "production-run-k2",
            }
            field = (
                "workspace_ref"
                if wrong == "workspace-other"
                else "production_run_ref"
            )
            values[field] = wrong
            with self.assertRaises(AuthorityRequiredError):
                authority.authorize_reference(
                    **values,
                    character={"characterRef": "character-lin-che"},
                )
        with self.assertRaises(AuthorityRequiredError):
            authority.authorize_reference(
                workspace_ref="workspace-k2",
                production_run_ref="production-run-k2",
                character={"characterRef": "character-gu-yan"},
            )

    def test_partial_tampered_and_closed_world_bundles_fail(self):
        with self.assertRaises(M6ExternalAuthorityConfigurationError):
            m6_external_authorities_from_environment(
                {"CREATOR_M6_AUTHORITY_BUNDLE_PATH": str(self.m6_path)}
            )
        environment = self.environment()
        environment["CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"] = "9" * 64
        with self.assertRaises(ExternalAuthorityConfigurationError):
            identity_reference_authority_from_environment(environment)

        identity = _identity_bundle()
        identity["references"][0]["unexpected"] = True
        digest = _write(self.identity_path, identity)
        environment = self.environment()
        environment["CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"] = digest
        with self.assertRaises(ExternalAuthorityConfigurationError):
            identity_reference_authority_from_environment(environment)

        identity = _identity_bundle()
        identity["authorityRef"] = "invalid authority ref"
        digest = _write(self.identity_path, identity)
        environment = self.environment()
        environment["CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"] = digest
        with self.assertRaises(ExternalAuthorityConfigurationError):
            identity_reference_authority_from_environment(environment)

    def test_duplicate_json_keys_fail_closed(self):
        m6_payload = (
            b'{"schemaVersion":"v5.external-m6-authority-bundle.v1",'
            b'"authorityRef":"m6-one","authorityRef":"m6-two",'
            b'"scopes":[],"approvals":[]}'
        )
        self.m6_path.write_bytes(m6_payload)
        environment = self.environment()
        environment["CREATOR_M6_AUTHORITY_BUNDLE_SHA256"] = sha256(
            m6_payload
        ).hexdigest()
        with self.assertRaises(M6ExternalAuthorityConfigurationError):
            m6_external_authorities_from_environment(environment)

        identity_payload = (
            b'{"schemaVersion":'
            b'"v5.external-identity-reference-authority-bundle.v1",'
            b'"authorityRef":"identity-one","authorityRef":"identity-two",'
            b'"references":[]}'
        )
        self.identity_path.write_bytes(identity_payload)
        environment = self.environment()
        environment["CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"] = sha256(
            identity_payload
        ).hexdigest()
        with self.assertRaises(ExternalAuthorityConfigurationError):
            identity_reference_authority_from_environment(environment)

    def test_m6_rejects_ai_approval_and_identity_rejects_rights_mismatch(self):
        m6 = _m6_bundle()
        m6["approvals"][0]["actorKind"] = "provider"
        digest = _write(self.m6_path, m6)
        environment = self.environment()
        environment["CREATOR_M6_AUTHORITY_BUNDLE_SHA256"] = digest
        with self.assertRaises(M6ExternalAuthorityConfigurationError):
            m6_external_authorities_from_environment(environment)

        identity = _identity_bundle()
        identity["references"][0]["provenance"] = "LOCAL_EVIDENCE"
        digest = _write(self.identity_path, identity)
        environment = self.environment()
        environment["CREATOR_IDENTITY_REFERENCE_AUTHORITY_BUNDLE_SHA256"] = digest
        with self.assertRaises(ExternalAuthorityConfigurationError):
            identity_reference_authority_from_environment(environment)

    def test_lifecycle_environment_factory_injects_m6_authorities(self):
        environment = self.environment()
        environment["CREATOR_DATA_PATH"] = str(
            Path(self.temporary.name) / "creator-workspace.sqlite3"
        )
        sentinel = object()
        with patch.object(
            lifecycle_composition.LifecycleAssembly,
            "sqlite",
            return_value=sentinel,
        ) as sqlite:
            result = (
                lifecycle_composition.LifecycleAssembly.sqlite_from_environment(
                    environment
                )
            )
        self.assertIs(result, sentinel)
        self.assertIsInstance(
            sqlite.call_args.kwargs["m6_scope_authority"],
            DigestPinnedM6ScopeAuthority,
        )
        self.assertIsInstance(
            sqlite.call_args.kwargs["m6_approval_authority"],
            DigestPinnedM6ApprovalAuthority,
        )

    def test_episode_environment_factory_injects_identity_authority(self):
        environment = self.environment()
        environment["CREATOR_EPISODE_PRODUCTION_DATA_PATH"] = str(
            Path(self.temporary.name) / "episode-production.sqlite3"
        )
        sentinel = object()
        with patch.object(
            production_public,
            "create_local_development_boundary",
            return_value=sentinel,
        ) as create_boundary:
            result = production_public.create_local_development_boundary_from_environment(
                project_boundary=object(),
                series_episode_boundary=object(),
                series_planning_boundary=object(),
                script_studio_boundary=object(),
                environ=environment,
            )
        self.assertIs(result, sentinel)
        self.assertIsInstance(
            create_boundary.call_args.kwargs["identity_reference_authority"],
            DigestPinnedIdentityReferenceAuthority,
        )

    def test_operator_is_validate_only_and_prints_only_digest_pinned_exports(self):
        environment = os.environ.copy()
        result = subprocess.run(
            [
                sys.executable,
                str(
                    REPOSITORY_ROOT
                    / "scripts"
                    / "k2_g2_external_authority_activate.py"
                ),
                "--m6-bundle",
                str(self.m6_path),
                "--identity-bundle",
                str(self.identity_path),
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(line.startswith("export CREATOR_") for line in lines))
        self.assertNotIn("actor-project-owner", result.stdout)
        self.assertNotIn("identity-reference-lin-che", result.stdout)
        self.assertNotIn("approval-k2", result.stdout)

    def test_operator_supports_scope_only_draft_preparation(self):
        bundle = _m6_bundle()
        bundle["approvals"] = []
        _write(self.m6_path, bundle)
        result = subprocess.run(
            [
                sys.executable,
                str(
                    REPOSITORY_ROOT
                    / "scripts"
                    / "k2_g2_external_authority_activate.py"
                ),
                "--m6-bundle",
                str(self.m6_path),
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.startswith("export CREATOR_M6_") for line in lines))


if __name__ == "__main__":
    unittest.main()
