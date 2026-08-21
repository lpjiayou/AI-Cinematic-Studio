"""Digest-pinned external M6 scope and approval authorities.

The bundle is an operator-managed fact.  It is loaded only when both its absolute
path and independently supplied SHA-256 digest are present.  Missing configuration
keeps M6 fail-closed; partial or malformed configuration fails startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    M6Scope,
    RejectingApprovalAuthority,
    RejectingScopeAuthority,
    VerifiedActorContext,
)
from .errors import AuthorityUnavailableError, SeriesIntelligenceError


M6_AUTHORITY_BUNDLE_SCHEMA = "v5.external-m6-authority-bundle.v1"
MAX_M6_AUTHORITY_BUNDLE_BYTES = 512_000
_M6_ACTIONS = {
    "confirm-series-bible-version",
    "confirm-character-continuity-version",
    "activate-m6-baseline",
}
class M6ExternalAuthorityConfigurationError(SeriesIntelligenceError):
    code = "external_authority_configuration_invalid"


def _required_ref(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 240
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise M6ExternalAuthorityConfigurationError(f"{field} is invalid")
    return value


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise M6ExternalAuthorityConfigurationError(f"{field} is invalid")
    return value


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority bundle contains duplicate JSON keys"
            )
        result[key] = value
    return result


def _read_bundle(path_value: str, expected_digest: str) -> Mapping[str, Any]:
    path = Path(path_value)
    if not path.is_absolute() or not path.is_file():
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle path is unavailable"
        )
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle cannot be read"
        ) from exc
    if not payload or len(payload) > MAX_M6_AUTHORITY_BUNDLE_BYTES:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle size is invalid"
        )
    if sha256(payload).hexdigest() != _sha256(
        expected_digest, "M6 authority bundle digest"
    ):
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle digest does not match"
        )
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle is not valid JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle root is invalid"
        )
    return value


@dataclass(frozen=True, slots=True)
class _ApprovalKey:
    workspace_ref: str
    project_ref: str
    series_ref: str
    approval_ref: str
    action: str


class DigestPinnedM6ScopeAuthority:
    """Exact-scope authority built only from a verified external bundle."""

    def __init__(self, scopes: Mapping[tuple[str, str, str], M6Scope]) -> None:
        self._scopes = dict(scopes)

    def resolve_scope(
        self, workspace_ref: str, project_ref: str, series_ref: str
    ) -> M6Scope:
        try:
            return self._scopes[(workspace_ref, project_ref, series_ref)]
        except KeyError:
            raise AuthorityUnavailableError(
                "trusted M6 scope was not resolved"
            ) from None


class DigestPinnedM6ApprovalAuthority:
    """Approval authority keyed by the exact M6 scope, approval and action."""

    def __init__(
        self, approvals: Mapping[_ApprovalKey, VerifiedActorContext]
    ) -> None:
        self._approvals = dict(approvals)

    def verify_approval(
        self, *, scope: M6Scope, approval_ref: str, action: str
    ) -> VerifiedActorContext:
        key = _ApprovalKey(
            scope.workspace_ref,
            scope.project_ref,
            scope.series_ref,
            approval_ref,
            action,
        )
        try:
            return self._approvals[key]
        except KeyError:
            raise AuthorityUnavailableError(
                "trusted approval was not resolved for the exact M6 action"
            ) from None


def _authorities(
    bundle: Mapping[str, Any],
) -> tuple[DigestPinnedM6ScopeAuthority, DigestPinnedM6ApprovalAuthority]:
    if set(bundle) != {"schemaVersion", "authorityRef", "scopes", "approvals"}:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle fields are invalid"
        )
    if bundle["schemaVersion"] != M6_AUTHORITY_BUNDLE_SCHEMA:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle schema is invalid"
        )
    _required_ref(bundle["authorityRef"], "M6 authorityRef")

    raw_scopes = bundle["scopes"]
    if not isinstance(raw_scopes, list) or not raw_scopes or len(raw_scopes) > 100:
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority scopes are invalid"
        )
    scopes: dict[tuple[str, str, str], M6Scope] = {}
    scope_keys: set[tuple[str, str, str]] = set()
    scope_fields = {
        "businessDomain",
        "tenantId",
        "workspaceRef",
        "projectRef",
        "seriesRef",
    }
    for raw in raw_scopes:
        if not isinstance(raw, Mapping) or set(raw) != scope_fields:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority scope is invalid"
            )
        values = {
            field: _required_ref(raw[field], f"M6 scope {field}")
            for field in scope_fields
        }
        key = (
            values["workspaceRef"],
            values["projectRef"],
            values["seriesRef"],
        )
        if key in scopes:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority scope is duplicated"
            )
        scope_keys.add(key)
        scopes[key] = M6Scope(
            values["businessDomain"],
            values["tenantId"],
            *key,
        )

    raw_approvals = bundle["approvals"]
    if (
        not isinstance(raw_approvals, list)
        or len(raw_approvals) > 300
    ):
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority approvals are invalid"
        )
    approval_fields = {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "approvalRef",
        "action",
        "actorRef",
        "actorKind",
    }
    approvals: dict[_ApprovalKey, VerifiedActorContext] = {}
    seen_approval_refs: set[str] = set()
    for raw in raw_approvals:
        if not isinstance(raw, Mapping) or set(raw) != approval_fields:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority approval is invalid"
            )
        values = {
            field: _required_ref(raw[field], f"M6 approval {field}")
            for field in approval_fields
        }
        action = values["action"]
        if action not in _M6_ACTIONS:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority approval action is unsupported"
            )
        actor_kind = values["actorKind"]
        if actor_kind.lower() != "human":
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority approvals require a verified human actor"
            )
        scope_key = (
            values["workspaceRef"],
            values["projectRef"],
            values["seriesRef"],
        )
        if scope_key not in scope_keys:
            raise M6ExternalAuthorityConfigurationError(
                "M6 approval does not match a declared scope"
            )
        approval_ref = values["approvalRef"]
        if approval_ref in seen_approval_refs:
            raise M6ExternalAuthorityConfigurationError(
                "M6 authority approvalRef is duplicated"
            )
        seen_approval_refs.add(approval_ref)
        key = _ApprovalKey(*scope_key, approval_ref, action)
        approvals[key] = VerifiedActorContext(
            approval_ref,
            values["actorRef"],
            actor_kind,
        )

    return DigestPinnedM6ScopeAuthority(scopes), DigestPinnedM6ApprovalAuthority(
        approvals
    )


def m6_external_authorities_from_environment(environ: Mapping[str, str]):
    """Return rejecting authorities or one fully digest-pinned M6 pair."""

    names = (
        "CREATOR_M6_AUTHORITY_BUNDLE_PATH",
        "CREATOR_M6_AUTHORITY_BUNDLE_SHA256",
    )
    configured = {name: str(environ.get(name, "")).strip() for name in names}
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingScopeAuthority(), RejectingApprovalAuthority()
    if len(present) != len(names):
        raise M6ExternalAuthorityConfigurationError(
            "M6 authority bundle configuration is incomplete"
        )
    return _authorities(_read_bundle(configured[names[0]], configured[names[1]]))
