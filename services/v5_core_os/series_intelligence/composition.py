"""Bounded in-memory Series Intelligence participant composition."""

from __future__ import annotations

from .contracts import (
    ApprovalAuthorityPort,
    IdentityAuthorizationPort,
    M6ScopeAuthorityPort,
    RejectingApprovalAuthority,
    RejectingIdentityAuthorization,
    RejectingScopeAuthority,
)
from .foundation import SeriesIntelligenceService
from .in_memory import InMemorySeriesIntelligenceRepository
from .public import SeriesIntelligencePublicBoundary


def create_in_memory_participant(
    *, lifecycle_state, source_reader, scope_authority: M6ScopeAuthorityPort | None = None,
    approval_authority: ApprovalAuthorityPort | None = None,
    identity_authority: IdentityAuthorizationPort | None = None,
    ref_factory=None, clock=None, outbox_hook=None,
):
    repository = InMemorySeriesIntelligenceRepository(outbox_hook=outbox_hook)
    lifecycle_state.register_resource("series-intelligence", repository.capture, repository.restore)
    kwargs = {}
    if ref_factory is not None:
        kwargs["ref_factory"] = ref_factory
    if clock is not None:
        kwargs["clock"] = clock
    service = SeriesIntelligenceService(
        repository,
        source_reader,
        scope_authority or RejectingScopeAuthority(),
        approval_authority or RejectingApprovalAuthority(),
        identity_authority or RejectingIdentityAuthorization(),
        **kwargs,
    )
    return SeriesIntelligencePublicBoundary(service, lifecycle_state=lifecycle_state)
