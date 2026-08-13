"""Trusted authority and upstream contracts for bounded M6."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .errors import AuthorityUnavailableError, IdentityBindingDeniedError


@dataclass(frozen=True, slots=True)
class M6Scope:
    business_domain: str
    tenant_id: str
    workspace_ref: str
    project_ref: str
    series_ref: str
    ip_universe_ref: str | None = None

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.business_domain,
            self.tenant_id,
            self.workspace_ref,
            self.project_ref,
            self.series_ref,
        )

    def mapping(self) -> dict[str, str]:
        return {
            "businessDomain": self.business_domain,
            "tenantId": self.tenant_id,
            "workspaceRef": self.workspace_ref,
            "projectRef": self.project_ref,
            "seriesRef": self.series_ref,
        }


@dataclass(frozen=True, slots=True)
class VerifiedActorContext:
    approval_ref: str
    actor_ref: str
    actor_kind: str


VerifiedApproval = VerifiedActorContext


class M6ScopeAuthorityPort(Protocol):
    def resolve_scope(self, workspace_ref: str, project_ref: str, series_ref: str) -> M6Scope: ...


class ApprovalAuthorityPort(Protocol):
    def verify_approval(self, *, scope: M6Scope, approval_ref: str, action: str) -> VerifiedActorContext: ...


class IdentityAuthorizationPort(Protocol):
    def authorize_bindings(self, *, scope: M6Scope, bindings: Sequence[Mapping[str, Any]]) -> None: ...


class ConfirmedM6SourceReader(Protocol):
    def get_confirmed_m6_source_snapshot(
        self, workspace_ref: str, project_ref: str, series_ref: str
    ) -> dict[str, Any]: ...


class RejectingScopeAuthority:
    def resolve_scope(self, workspace_ref: str, project_ref: str, series_ref: str) -> M6Scope:
        raise AuthorityUnavailableError("trusted M6 scope authority is unavailable")


class RejectingApprovalAuthority:
    def verify_approval(self, *, scope: M6Scope, approval_ref: str, action: str) -> VerifiedActorContext:
        raise AuthorityUnavailableError("trusted approval authority is unavailable")


class RejectingIdentityAuthorization:
    def authorize_bindings(self, *, scope: M6Scope, bindings: Sequence[Mapping[str, Any]]) -> None:
        if bindings:
            raise IdentityBindingDeniedError("identity bindings require an accepted authority")


class StaticScopeAuthority:
    """Explicit injectable authority for tests and bounded in-process composition."""

    def __init__(self, scopes: Sequence[M6Scope]) -> None:
        self._scopes = {
            (item.workspace_ref, item.project_ref, item.series_ref): item for item in scopes
        }

    def resolve_scope(self, workspace_ref: str, project_ref: str, series_ref: str) -> M6Scope:
        try:
            return self._scopes[(workspace_ref, project_ref, series_ref)]
        except KeyError:
            raise AuthorityUnavailableError("trusted M6 scope was not resolved") from None


class StaticApprovalAuthority:
    def __init__(self, approvals: Mapping[str, VerifiedActorContext]) -> None:
        self._approvals = dict(approvals)

    def verify_approval(self, *, scope: M6Scope, approval_ref: str, action: str) -> VerifiedActorContext:
        try:
            return self._approvals[approval_ref]
        except KeyError:
            raise AuthorityUnavailableError("trusted approval was not resolved") from None
