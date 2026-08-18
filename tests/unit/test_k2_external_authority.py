from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.v5_core_os.episode_production import (
    ExternalAuthorityConfigurationError,
    external_authorities_from_environment,
)
from services.v5_core_os.episode_production import public as production_public


def _write(path: Path, value) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    path.write_bytes(payload)
    return sha256(payload).hexdigest()


def _grant():
    return {
        "inputRef": "script-version-k2-v1",
        "inputKind": "SCRIPT",
        "contentDigest": "1" * 64,
        "rightsOwnerRef": "rights-owner-k2",
        "grantBasis": "OWNED",
        "permittedUses": [
            "AI_GENERATION", "DERIVATIVE_WORK", "PUBLICATION", "COMMERCIAL_USE"
        ],
        "providerProcessingAllowed": True,
        "territories": ["WORLDWIDE"],
        "validFrom": "2026-01-01T00:00:00Z",
        "validUntil": "2027-01-01T00:00:00Z",
        "attributionText": "",
        "likenessVoiceMusicScope": ["SCRIPT"],
        "evidenceRef": "rights-evidence-k2-script-v1",
        "evidenceDigest": "2" * 64,
    }


def _capability():
    return {
        "mediaKind": "video",
        "providerId": "funhpc-comfyui",
        "modelId": "wan2.2-i2v",
        "region": "operator-approved-region",
        "authority": {
            "enabled": True,
            "endpointClass": "server-side-managed",
            "safetyPolicyRef": "safety-policy-k2-v1",
            "privacyMode": "no-training-no-retention",
            "gpuAttestationSupported": True,
            "providerCapabilityRef": "provider-capability-wan22-v1",
            "credentialSourceRef": "secret-handle-comfyui-v1",
            "usageTermsRef": "usage-terms-funhpc-v1",
            "budgetAuthorityRef": "budget-authority-k2-v1",
            "validUntil": "2027-01-01T00:00:00Z",
            "evidenceDigest": "3" * 64,
            "runtimeAttestationRef": "runtime-attestation-a100-wan22-v1",
            "runtimeAttestationDigest": "4" * 64,
        },
    }


class ExternalAuthorityConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.rights_path = root / "rights.json"
        self.provider_path = root / "provider.json"
        self.grant = _grant()
        self.capability = _capability()
        self.rights_digest = _write(
            self.rights_path,
            {
                "schemaVersion": "v5.external-rights-authority-bundle.v1",
                "authorityRef": "rights-authority-k2-v1",
                "grants": [self.grant],
            },
        )
        self.provider_digest = _write(
            self.provider_path,
            {
                "schemaVersion": "v5.external-provider-authority-bundle.v1",
                "authorityRef": "provider-authority-k2-v1",
                "capabilities": [self.capability],
            },
        )

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return {
            "CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH": str(self.rights_path),
            "CREATOR_RIGHTS_AUTHORITY_BUNDLE_SHA256": self.rights_digest,
            "CREATOR_PROVIDER_AUTHORITY_BUNDLE_PATH": str(self.provider_path),
            "CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256": self.provider_digest,
        }

    def test_no_configuration_remains_fail_closed(self):
        rights, providers = external_authorities_from_environment({})
        self.assertFalse(rights.available)
        self.assertFalse(providers.available)

    def test_digest_pinned_bundles_activate_exact_authorities(self):
        rights, providers = external_authorities_from_environment(self.environment())
        claimed_grant = {key: value for key, value in self.grant.items() if key != "evidenceDigest"}
        self.assertEqual(
            rights.verify_grant(claimed_grant)["evidenceDigest"], "2" * 64
        )
        execution = {
            "mediaKind": "video",
            "providerId": "funhpc-comfyui",
            "modelId": "wan2.2-i2v",
            "region": "operator-approved-region",
            "endpointClass": "server-side-managed",
            "safetyPolicyRef": "safety-policy-k2-v1",
            "privacyMode": "no-training-no-retention",
            "maximumAttempts": 1,
            "timeoutSeconds": 900,
            "maxCostMinor": 100,
            "seedPolicy": "record-when-supported",
            "gpuAttestationRequired": True,
        }
        decision = providers.verify_execution(execution)
        self.assertEqual(decision["credentialSourceRef"], "secret-handle-comfyui-v1")
        self.assertNotIn("token", json.dumps(decision).lower())

    def test_partial_configuration_and_tampering_fail_closed(self):
        with self.assertRaises(ExternalAuthorityConfigurationError):
            external_authorities_from_environment(
                {"CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH": str(self.rights_path)}
            )
        environment = self.environment()
        environment["CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256"] = "9" * 64
        with self.assertRaises(ExternalAuthorityConfigurationError):
            external_authorities_from_environment(environment)

    def test_provider_bundle_rejects_secret_shaped_extra_fields(self):
        capability = _capability()
        capability["authority"]["bearerToken"] = "must-not-enter-v5"
        digest = _write(
            self.provider_path,
            {
                "schemaVersion": "v5.external-provider-authority-bundle.v1",
                "authorityRef": "provider-authority-k2-v1",
                "capabilities": [capability],
            },
        )
        environment = self.environment()
        environment["CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256"] = digest
        with self.assertRaises(ExternalAuthorityConfigurationError):
            external_authorities_from_environment(environment)

    def test_creator_environment_factory_injects_both_authorities(self):
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
        self.assertTrue(
            create_boundary.call_args.kwargs["rights_evidence_authority"].available
        )
        self.assertTrue(
            create_boundary.call_args.kwargs["provider_policy_authority"].available
        )


if __name__ == "__main__":
    unittest.main()
