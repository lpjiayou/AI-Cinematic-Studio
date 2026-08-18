"""Digest-pinned external authority bundles for governed K2 activation.

The files loaded here are operator-managed facts, not repository configuration.
Their exact SHA-256 digests must be injected independently through the process
environment.  Secret values are forbidden; provider credentials remain behind the
opaque ``credentialSourceRef`` returned by the provider authority.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .foundation import EpisodeProductionError, _required_ref
from .production_policy import (
    RIGHTS_ENTRY_FIELDS,
    RejectingProviderPolicyAuthority,
    RejectingRightsEvidenceAuthority,
    StaticProviderPolicyAuthority,
    StaticRightsEvidenceAuthority,
)


RIGHTS_AUTHORITY_BUNDLE_SCHEMA = "v5.external-rights-authority-bundle.v1"
PROVIDER_AUTHORITY_BUNDLE_SCHEMA = "v5.external-provider-authority-bundle.v1"
MAX_AUTHORITY_BUNDLE_BYTES = 512_000


class ExternalAuthorityConfigurationError(EpisodeProductionError):
    code = "external_authority_configuration_invalid"


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ExternalAuthorityConfigurationError(f"{field} is invalid")
    return value


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExternalAuthorityConfigurationError(
                "external authority bundle contains duplicate JSON keys"
            )
        result[key] = value
    return result


def _read_bundle(path_value: str, expected_digest: str, name: str) -> Mapping[str, Any]:
    path = Path(path_value)
    if not path.is_absolute() or not path.is_file():
        raise ExternalAuthorityConfigurationError(f"{name} path is unavailable")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ExternalAuthorityConfigurationError(f"{name} cannot be read") from exc
    if not payload or len(payload) > MAX_AUTHORITY_BUNDLE_BYTES:
        raise ExternalAuthorityConfigurationError(f"{name} size is invalid")
    if sha256(payload).hexdigest() != _sha256(expected_digest, f"{name} digest"):
        raise ExternalAuthorityConfigurationError(f"{name} digest does not match")
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalAuthorityConfigurationError(f"{name} is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise ExternalAuthorityConfigurationError(f"{name} root is invalid")
    return value


def _rights_authority(bundle: Mapping[str, Any]) -> StaticRightsEvidenceAuthority:
    if set(bundle) != {"schemaVersion", "authorityRef", "grants"}:
        raise ExternalAuthorityConfigurationError("rights authority fields are invalid")
    if bundle["schemaVersion"] != RIGHTS_AUTHORITY_BUNDLE_SCHEMA:
        raise ExternalAuthorityConfigurationError("rights authority schema is invalid")
    _required_ref(bundle["authorityRef"], "rights authorityRef")
    grants = bundle["grants"]
    if not isinstance(grants, list) or not grants or len(grants) > 100:
        raise ExternalAuthorityConfigurationError("rights authority grants are invalid")
    expected_fields = set(RIGHTS_ENTRY_FIELDS) | {"evidenceDigest"}
    by_ref: dict[str, Mapping[str, Any]] = {}
    for raw in grants:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise ExternalAuthorityConfigurationError("rights authority grant is invalid")
        evidence_ref = _required_ref(raw["evidenceRef"], "rights evidenceRef")
        if evidence_ref in by_ref:
            raise ExternalAuthorityConfigurationError(
                "rights authority evidenceRef is duplicated"
            )
        _sha256(raw["evidenceDigest"], "rights evidenceDigest")
        by_ref[evidence_ref] = dict(raw)
    return StaticRightsEvidenceAuthority(by_ref)


def _provider_authority(bundle: Mapping[str, Any]) -> StaticProviderPolicyAuthority:
    if set(bundle) != {"schemaVersion", "authorityRef", "capabilities"}:
        raise ExternalAuthorityConfigurationError("provider authority fields are invalid")
    if bundle["schemaVersion"] != PROVIDER_AUTHORITY_BUNDLE_SCHEMA:
        raise ExternalAuthorityConfigurationError("provider authority schema is invalid")
    _required_ref(bundle["authorityRef"], "provider authorityRef")
    capabilities = bundle["capabilities"]
    if not isinstance(capabilities, list) or not capabilities or len(capabilities) > 30:
        raise ExternalAuthorityConfigurationError(
            "provider authority capabilities are invalid"
        )
    by_key: dict[tuple[str, str, str, str], Mapping[str, Any]] = {}
    for raw in capabilities:
        if not isinstance(raw, Mapping) or set(raw) != {
            "mediaKind", "providerId", "modelId", "region", "authority"
        }:
            raise ExternalAuthorityConfigurationError(
                "provider authority capability is invalid"
            )
        key = tuple(
            _required_ref(raw[field], f"provider {field}")
            for field in ("mediaKind", "providerId", "modelId", "region")
        )
        if key in by_key:
            raise ExternalAuthorityConfigurationError(
                "provider authority capability is duplicated"
            )
        authority = raw["authority"]
        required_authority_fields = {
            "enabled", "endpointClass", "safetyPolicyRef", "privacyMode",
            "gpuAttestationSupported", "providerCapabilityRef",
            "credentialSourceRef", "usageTermsRef", "budgetAuthorityRef",
            "validUntil", "evidenceDigest",
        }
        optional_attestation_fields = {
            "runtimeAttestationRef", "runtimeAttestationDigest"
        }
        if (
            not isinstance(authority, Mapping)
            or not required_authority_fields.issubset(authority)
            or set(authority) - required_authority_fields
            not in (set(), optional_attestation_fields)
        ):
            raise ExternalAuthorityConfigurationError(
                "provider authority decision is invalid"
            )
        for field in (
            "providerCapabilityRef", "credentialSourceRef", "usageTermsRef",
            "budgetAuthorityRef",
        ):
            _required_ref(authority[field], f"provider authority {field}")
        _sha256(authority["evidenceDigest"], "provider authority evidenceDigest")
        has_attestation = set(authority) & optional_attestation_fields
        if has_attestation and has_attestation != optional_attestation_fields:
            raise ExternalAuthorityConfigurationError(
                "provider runtime attestation is incomplete"
            )
        if has_attestation:
            _required_ref(
                authority["runtimeAttestationRef"],
                "provider authority runtimeAttestationRef",
            )
            _sha256(
                authority["runtimeAttestationDigest"],
                "provider authority runtimeAttestationDigest",
            )
        by_key[key] = dict(authority)
    return StaticProviderPolicyAuthority(by_key)


def external_authorities_from_environment(
    environ: Mapping[str, str],
):
    """Return rejecting authorities or one fully digest-pinned authority pair."""

    names = (
        "CREATOR_RIGHTS_AUTHORITY_BUNDLE_PATH",
        "CREATOR_RIGHTS_AUTHORITY_BUNDLE_SHA256",
        "CREATOR_PROVIDER_AUTHORITY_BUNDLE_PATH",
        "CREATOR_PROVIDER_AUTHORITY_BUNDLE_SHA256",
    )
    configured = {name: str(environ.get(name, "")).strip() for name in names}
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingRightsEvidenceAuthority(), RejectingProviderPolicyAuthority()
    if len(present) != len(names):
        raise ExternalAuthorityConfigurationError(
            "external authority bundle configuration is incomplete"
        )
    rights_bundle = _read_bundle(
        configured[names[0]], configured[names[1]], "rights authority bundle"
    )
    provider_bundle = _read_bundle(
        configured[names[2]], configured[names[3]], "provider authority bundle"
    )
    return _rights_authority(rights_bundle), _provider_authority(provider_bundle)
