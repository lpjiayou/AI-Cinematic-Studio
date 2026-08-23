"""Digest-pinned exact-subject authority for K2 delivery approvals.

The operator-managed bundle is loaded only when both an absolute path and an
independently supplied SHA-256 are configured.  Each human decision is bound to
one closed-world :class:`ApprovalSubject`; a client actor claim cannot create or
broaden that authority.
"""

from __future__ import annotations

from typing import Any, Mapping

from .delivery import (
    ApprovalRequiredError,
    ApprovalSubject,
    RejectingApprovalAuthority,
    VerifiedApproval,
)
from .external_authority import (
    ExternalAuthorityConfigurationError,
    _authority_ref,
    _read_bundle,
    _sha256,
)


DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SCHEMA = (
    "v5.external-delivery-approval-authority-bundle.v1"
)
MAX_DELIVERY_APPROVALS = 300


class DigestPinnedDeliveryApprovalAuthority:
    """In-memory authority resolved from one verified immutable bundle."""

    def __init__(
        self,
        approvals: Mapping[str, tuple[ApprovalSubject, VerifiedApproval]],
    ) -> None:
        self._approvals = dict(approvals)

    def verify(
        self,
        *,
        subject: ApprovalSubject,
        approval_ref: str,
        actor_ref: str,
    ) -> VerifiedApproval:
        try:
            configured_subject, approval = self._approvals[approval_ref]
        except KeyError:
            raise ApprovalRequiredError(
                "delivery approval was not resolved for the exact subject"
            ) from None
        if (
            configured_subject != subject
            or not approval.matches(
                subject=subject,
                approval_ref=approval_ref,
                actor_ref=actor_ref,
            )
        ):
            raise ApprovalRequiredError(
                "delivery approval was not resolved for the exact subject"
            )
        return approval


def _delivery_approval_authority(
    bundle: Mapping[str, Any],
) -> DigestPinnedDeliveryApprovalAuthority:
    if set(bundle) != {"schemaVersion", "authorityRef", "approvals"}:
        raise ExternalAuthorityConfigurationError(
            "delivery approval authority fields are invalid"
        )
    if bundle["schemaVersion"] != DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SCHEMA:
        raise ExternalAuthorityConfigurationError(
            "delivery approval authority schema is invalid"
        )
    authority_ref = _authority_ref(
        bundle["authorityRef"], "delivery approval authorityRef"
    )
    raw_approvals = bundle["approvals"]
    if (
        not isinstance(raw_approvals, list)
        or len(raw_approvals) > MAX_DELIVERY_APPROVALS
    ):
        raise ExternalAuthorityConfigurationError(
            "delivery approval authority decisions are invalid"
        )
    fields = {
        "subject",
        "approvalRef",
        "actorRef",
        "authorityType",
        "decision",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "decidedAt",
    }
    approvals: dict[str, tuple[ApprovalSubject, VerifiedApproval]] = {}
    authority_decision_refs: set[str] = set()
    for raw in raw_approvals:
        if not isinstance(raw, Mapping) or set(raw) != fields:
            raise ExternalAuthorityConfigurationError(
                "delivery approval authority decision is invalid"
            )
        try:
            subject = ApprovalSubject.from_mapping(raw["subject"])
        except (ApprovalRequiredError, TypeError) as exc:
            raise ExternalAuthorityConfigurationError(
                "delivery approval authority subject is invalid"
            ) from exc
        approval_ref = _authority_ref(
            raw["approvalRef"], "delivery approval approvalRef"
        )
        actor_ref = _authority_ref(
            raw["actorRef"], "delivery approval actorRef"
        )
        authority_decision_ref = _authority_ref(
            raw["authorityDecisionRef"],
            "delivery approval authorityDecisionRef",
        )
        if approval_ref in approvals:
            raise ExternalAuthorityConfigurationError(
                "delivery approval approvalRef is duplicated"
            )
        if authority_decision_ref in authority_decision_refs:
            raise ExternalAuthorityConfigurationError(
                "delivery approval authorityDecisionRef is duplicated"
            )
        authority_decision_refs.add(authority_decision_ref)
        authority_decision_digest = _sha256(
            raw["authorityDecisionDigest"],
            "delivery approval authorityDecisionDigest",
        )
        try:
            approval = VerifiedApproval.create(
                authority_ref=authority_ref,
                approval_ref=approval_ref,
                actor_ref=actor_ref,
                kind=subject.kind,
                authority_type=raw["authorityType"],
                decision=raw["decision"],
                authority_decision_ref=authority_decision_ref,
                authority_decision_digest=authority_decision_digest,
                decided_at=raw["decidedAt"],
                subject_digest=subject.subject_digest,
            )
        except ApprovalRequiredError as exc:
            raise ExternalAuthorityConfigurationError(
                "delivery approval authority evidence is invalid"
            ) from exc
        approvals[approval_ref] = (subject, approval)
    return DigestPinnedDeliveryApprovalAuthority(approvals)


def delivery_approval_authority_from_environment(
    environ: Mapping[str, str],
):
    """Return rejecting authority or one fully digest-pinned human authority."""

    names = (
        "CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_PATH",
        "CREATOR_DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SHA256",
    )
    configured = {name: str(environ.get(name, "")).strip() for name in names}
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingApprovalAuthority()
    if len(present) != len(names):
        raise ExternalAuthorityConfigurationError(
            "delivery approval authority configuration is incomplete"
        )
    bundle = _read_bundle(
        configured[names[0]],
        configured[names[1]],
        "delivery approval authority bundle",
    )
    return _delivery_approval_authority(bundle)


__all__ = [
    "DELIVERY_APPROVAL_AUTHORITY_BUNDLE_SCHEMA",
    "DigestPinnedDeliveryApprovalAuthority",
    "delivery_approval_authority_from_environment",
]
