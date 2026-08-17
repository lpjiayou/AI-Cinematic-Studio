"""Server-to-server authentication for Creator Public HTTP/API v1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
from typing import Any


PUBLIC_AUTH_SCHEMA_VERSION = "creator.public-auth.v1"
MAX_AUTH_CONFIG_BYTES = 512_000
MAX_BEARER_TOKEN_BYTES = 4_096
DEFAULT_PUBLIC_API_HOST = "127.0.0.1"
DEFAULT_PUBLIC_API_PORT = 8_765

_REFERENCE_PATTERN = re.compile(r"^\S{1,200}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = frozenset({"schemaVersion", "credentials"})
_CREDENTIAL_FIELDS = frozenset(
    {"credentialRef", "workspaceRef", "tokenSha256", "enabled"}
)


class PublicAuthConfigurationError(RuntimeError):
    """Raised when public API security configuration is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class PublicApiPrincipal:
    credential_ref: str
    workspace_ref: str


@dataclass(frozen=True, slots=True)
class _Credential:
    principal: PublicApiPrincipal
    token_sha256: str
    enabled: bool


class PublicApiAuthenticator:
    """Validate bearer tokens against a digest-only credential registry."""

    def __init__(self, credentials: Sequence[_Credential]) -> None:
        if not credentials or not any(item.enabled for item in credentials):
            raise PublicAuthConfigurationError(
                "Creator public authentication requires an enabled credential"
            )
        self._credentials = tuple(credentials)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PublicApiAuthenticator":
        if set(value) != _TOP_LEVEL_FIELDS:
            raise PublicAuthConfigurationError(
                "Creator public authentication registry fields are invalid"
            )
        if value.get("schemaVersion") != PUBLIC_AUTH_SCHEMA_VERSION:
            raise PublicAuthConfigurationError(
                "Creator public authentication registry schema is invalid"
            )
        raw_credentials = value.get("credentials")
        if not isinstance(raw_credentials, list) or not raw_credentials:
            raise PublicAuthConfigurationError(
                "Creator public authentication credentials are invalid"
            )

        credential_refs: set[str] = set()
        workspace_refs: set[str] = set()
        digests: set[str] = set()
        credentials: list[_Credential] = []
        for item in raw_credentials:
            if not isinstance(item, dict) or set(item) != _CREDENTIAL_FIELDS:
                raise PublicAuthConfigurationError(
                    "Creator public authentication credential fields are invalid"
                )
            credential_ref = _validated_reference(
                item.get("credentialRef"), "credentialRef"
            )
            workspace_ref = _validated_reference(
                item.get("workspaceRef"), "workspaceRef"
            )
            token_digest = item.get("tokenSha256")
            enabled = item.get("enabled")
            if not isinstance(token_digest, str) or not _DIGEST_PATTERN.fullmatch(
                token_digest
            ):
                raise PublicAuthConfigurationError(
                    "Creator public authentication token digest is invalid"
                )
            if not isinstance(enabled, bool):
                raise PublicAuthConfigurationError(
                    "Creator public authentication enabled flag is invalid"
                )
            if credential_ref in credential_refs:
                raise PublicAuthConfigurationError(
                    "Creator public authentication credentialRef must be unique"
                )
            if workspace_ref in workspace_refs:
                raise PublicAuthConfigurationError(
                    "Creator public authentication workspaceRef must be unique"
                )
            if token_digest in digests:
                raise PublicAuthConfigurationError(
                    "Creator public authentication token digest must be unique"
                )
            credential_refs.add(credential_ref)
            workspace_refs.add(workspace_ref)
            digests.add(token_digest)
            credentials.append(
                _Credential(
                    principal=PublicApiPrincipal(
                        credential_ref=credential_ref,
                        workspace_ref=workspace_ref,
                    ),
                    token_sha256=token_digest,
                    enabled=enabled,
                )
            )
        return cls(credentials)

    @classmethod
    def for_token(
        cls,
        token: str,
        workspace_ref: str,
        credential_ref: str = "runtime-test-credential",
    ) -> "PublicApiAuthenticator":
        """Create a runtime-only test authenticator without a raw-token fixture."""

        _validate_raw_token(token)
        return cls.from_mapping(
            {
                "schemaVersion": PUBLIC_AUTH_SCHEMA_VERSION,
                "credentials": [
                    {
                        "credentialRef": credential_ref,
                        "workspaceRef": workspace_ref,
                        "tokenSha256": token_sha256(token),
                        "enabled": True,
                    }
                ],
            }
        )

    def authenticate(
        self, authorization_values: Sequence[str] | None
    ) -> PublicApiPrincipal | None:
        if not authorization_values or len(authorization_values) != 1:
            return None
        header = authorization_values[0]
        if not isinstance(header, str):
            return None
        parts = header.split(" ")
        if len(parts) != 2 or parts[0].casefold() != "bearer":
            return None
        token = parts[1]
        try:
            _validate_raw_token(token)
        except PublicAuthConfigurationError:
            return None
        digest = token_sha256(token)
        principal: PublicApiPrincipal | None = None
        for credential in self._credentials:
            matches = hmac.compare_digest(digest, credential.token_sha256)
            if matches and credential.enabled:
                principal = credential.principal
        return principal


def token_sha256(token: str) -> str:
    _validate_raw_token(token)
    return sha256(token.encode("utf-8")).hexdigest()


def load_public_api_authenticator(path_value: str) -> PublicApiAuthenticator:
    if not isinstance(path_value, str) or not path_value.strip():
        raise PublicAuthConfigurationError(
            "CREATOR_PUBLIC_API_TOKEN_CONFIG is required"
        )
    path = Path(path_value.strip())
    try:
        size = path.stat().st_size
        if size <= 0 or size > MAX_AUTH_CONFIG_BYTES:
            raise PublicAuthConfigurationError(
                "Creator public authentication registry size is invalid"
            )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except PublicAuthConfigurationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicAuthConfigurationError(
            "Creator public authentication registry cannot be loaded"
        ) from exc
    if not isinstance(payload, dict):
        raise PublicAuthConfigurationError(
            "Creator public authentication registry must be an object"
        )
    return PublicApiAuthenticator.from_mapping(payload)


def public_server_configuration_from_environment(
    environment: Mapping[str, str] | None = None,
) -> tuple[str, int, PublicApiAuthenticator, bool]:
    values = environment if environment is not None else os.environ
    host = values.get("CREATOR_PUBLIC_API_HOST", DEFAULT_PUBLIC_API_HOST).strip()
    if (
        not host
        or len(host) > 255
        or any(character.isspace() or ord(character) < 32 for character in host)
        or "/" in host
    ):
        raise PublicAuthConfigurationError("CREATOR_PUBLIC_API_HOST is invalid")
    port_value = values.get("CREATOR_PUBLIC_API_PORT", str(DEFAULT_PUBLIC_API_PORT))
    try:
        port = int(port_value)
    except (TypeError, ValueError) as exc:
        raise PublicAuthConfigurationError(
            "CREATOR_PUBLIC_API_PORT is invalid"
        ) from exc
    if not 1 <= port <= 65_535:
        raise PublicAuthConfigurationError("CREATOR_PUBLIC_API_PORT is invalid")
    authenticator = load_public_api_authenticator(
        values.get("CREATOR_PUBLIC_API_TOKEN_CONFIG", "")
    )
    return host, port, authenticator, is_loopback_host(host)


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").casefold()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validated_reference(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise PublicAuthConfigurationError(
            f"Creator public authentication {field} is invalid"
        )
    if not _REFERENCE_PATTERN.fullmatch(value):
        raise PublicAuthConfigurationError(
            f"Creator public authentication {field} is invalid"
        )
    return value


def _validate_raw_token(token: Any) -> None:
    if not isinstance(token, str) or not token:
        raise PublicAuthConfigurationError("Creator bearer token is invalid")
    encoded = token.encode("utf-8")
    if len(encoded) > MAX_BEARER_TOKEN_BYTES or any(
        character.isspace() or ord(character) < 33 or ord(character) == 127
        for character in token
    ):
        raise PublicAuthConfigurationError("Creator bearer token is invalid")
