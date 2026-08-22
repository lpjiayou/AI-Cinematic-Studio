import unittest

from services.v5_core_os.episode_production import (
    InternalExecutionConfigurationError,
    internal_execution_grant_from_environment,
)


PROFILE = {
    "providerId": "self-hosted-comfyui",
    "modelId": "wan2.2-ti2v-5b-fp16",
    "region": "local-a100",
    "endpointClass": "loopback",
    "runtimeAttestationRef": "runtime-attestation-a100-v1",
    "runtimeAttestationDigest": "4" * 64,
    "costCurrency": "CNY",
    "maxCostMinor": 0,
    "timeoutSeconds": 1800,
}


class K2InternalExecutionGrantTests(unittest.TestCase):
    def test_absent_configuration_keeps_legacy_mode(self):
        self.assertIsNone(
            internal_execution_grant_from_environment(
                {}, provider_profile=None
            )
        )

    def test_exact_server_scope_creates_deterministic_secret_free_grant(self):
        environment = {
            "K2_P1_EXECUTION_AUTHORITY": "GRANTED_INTERNAL",
            "K2_P1_INTERNAL_WORKSPACE_REF": "workspace-k2",
            "K2_P1_INTERNAL_PRODUCTION_RUN_REF": "production-run-k2",
        }

        first = internal_execution_grant_from_environment(
            environment, provider_profile=PROFILE
        )
        second = internal_execution_grant_from_environment(
            environment, provider_profile=PROFILE
        )

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertTrue(first.matches("workspace-k2", "production-run-k2"))
        self.assertFalse(first.matches("workspace-k2", "other-run"))
        self.assertEqual(
            first.public_projection()["executionMode"],
            "INTERNAL_SELF_HOSTED",
        )
        self.assertFalse(first.public_projection()["publicationAllowed"])

    def test_partial_or_unknown_grant_fails_closed(self):
        with self.assertRaises(InternalExecutionConfigurationError):
            internal_execution_grant_from_environment(
                {"K2_P1_INTERNAL_WORKSPACE_REF": "workspace-k2"},
                provider_profile=None,
            )
        with self.assertRaises(InternalExecutionConfigurationError):
            internal_execution_grant_from_environment(
                {
                    "K2_P1_EXECUTION_AUTHORITY": "YES",
                    "K2_P1_INTERNAL_WORKSPACE_REF": "workspace-k2",
                    "K2_P1_INTERNAL_PRODUCTION_RUN_REF": "production-run-k2",
                },
                provider_profile=PROFILE,
            )
        with self.assertRaises(InternalExecutionConfigurationError):
            internal_execution_grant_from_environment(
                {
                    "K2_P1_EXECUTION_AUTHORITY": "GRANTED_INTERNAL",
                    "K2_P1_INTERNAL_WORKSPACE_REF": "workspace-k2",
                    "K2_P1_INTERNAL_PRODUCTION_RUN_REF": "production-run-k2",
                },
                provider_profile=None,
            )


if __name__ == "__main__":
    unittest.main()
