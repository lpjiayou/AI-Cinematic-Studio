import json
from pathlib import Path
import secrets
import tempfile
import unittest

from apps.creator_workspace_mvp.public_auth import (
    PUBLIC_AUTH_SCHEMA_VERSION,
    PublicApiAuthenticator,
    PublicAuthConfigurationError,
    is_loopback_host,
    load_public_api_authenticator,
    public_server_configuration_from_environment,
    token_sha256,
)


class CreatorPublicAuthTests(unittest.TestCase):
    def setUp(self):
        self.token = secrets.token_urlsafe(48)
        self.mapping = {
            "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
            "credentials": [
                {
                    "credentialRef": "frontend-runtime",
                    "workspaceRef": "workspace-runtime",
                    "tokenSha256": token_sha256(self.token),
                    "enabled": True,
                }
            ],
        }

    def test_authenticator_returns_only_configured_principal(self):
        authenticator = PublicApiAuthenticator.from_mapping(self.mapping)
        principal = authenticator.authenticate([f"Bearer {self.token}"])
        self.assertIsNotNone(principal)
        self.assertEqual(principal.credential_ref, "frontend-runtime")
        self.assertEqual(principal.workspace_ref, "workspace-runtime")

        for values in (
            None,
            [],
            ["Bearer wrong"],
            [f"Basic {self.token}"],
            [f"Bearer  {self.token}"],
            [f"Bearer {self.token}", f"Bearer {self.token}"],
        ):
            with self.subTest(values=values):
                self.assertIsNone(authenticator.authenticate(values))

    def test_registry_rejects_ambiguous_or_raw_credentials(self):
        invalid_values = [
            {**self.mapping, "rawToken": self.token},
            {
                **self.mapping,
                "credentials": [
                    {**self.mapping["credentials"][0], "rawToken": self.token}
                ],
            },
            {
                **self.mapping,
                "credentials": [
                    self.mapping["credentials"][0],
                    {
                        **self.mapping["credentials"][0],
                        "credentialRef": "second",
                        "tokenSha256": token_sha256(secrets.token_urlsafe(48)),
                    },
                ],
            },
            {
                **self.mapping,
                "credentials": [
                    {**self.mapping["credentials"][0], "enabled": False}
                ],
            },
        ]
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(
                PublicAuthConfigurationError
            ):
                PublicApiAuthenticator.from_mapping(value)

    def test_registry_file_and_bind_configuration_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator-public-auth.json"
            path.write_text(json.dumps(self.mapping), encoding="utf-8")
            authenticator = load_public_api_authenticator(str(path))
            self.assertIsNotNone(
                authenticator.authenticate([f"Bearer {self.token}"])
            )

            host, port, configured, allow_internal = (
                public_server_configuration_from_environment(
                    {
                        "CREATOR_PUBLIC_API_TOKEN_CONFIG": str(path),
                        "CREATOR_PUBLIC_API_HOST": "0.0.0.0",
                        "CREATOR_PUBLIC_API_PORT": "9876",
                    }
                )
            )
            self.assertEqual((host, port, allow_internal), ("0.0.0.0", 9876, False))
            self.assertIsNotNone(
                configured.authenticate([f"Bearer {self.token}"])
            )

        for environment in (
            {},
            {"CREATOR_PUBLIC_API_TOKEN_CONFIG": "/missing/registry.json"},
            {
                "CREATOR_PUBLIC_API_TOKEN_CONFIG": "/missing/registry.json",
                "CREATOR_PUBLIC_API_PORT": "0",
            },
        ):
            with self.subTest(environment=environment), self.assertRaises(
                PublicAuthConfigurationError
            ):
                public_server_configuration_from_environment(environment)

    def test_loopback_detection_is_explicit(self):
        for host in ("127.0.0.1", "127.10.20.30", "::1", "[::1]", "localhost"):
            with self.subTest(host=host):
                self.assertTrue(is_loopback_host(host))
        for host in ("0.0.0.0", "::", "creator-core.internal"):
            with self.subTest(host=host):
                self.assertFalse(is_loopback_host(host))


if __name__ == "__main__":
    unittest.main()
