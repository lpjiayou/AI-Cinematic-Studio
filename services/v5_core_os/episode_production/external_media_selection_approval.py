"""Digest-pinned exact-subject authority for K2 media selection.

The bundle is operator managed and is accepted only when its bytes match an
independently supplied SHA-256.  A public caller supplies only ``approvalRef``;
actor and authority provenance are resolved here for one exact, immutable
``MediaSelectionSubject``.
"""

from __future__ import annotations

from typing import Any, Mapping

from .external_authority import (
    ExternalAuthorityConfigurationError,
    _authority_ref,
    _read_bundle,
    _sha256,
)
from .media_candidate_review import (
    MediaSelectionApprovalRequiredError,
    MediaSelectionSubject,
    RejectingMediaSelectionApprovalAuthority,
    VerifiedMediaSelection,
)


MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA = (
    "v5.external-media-selection-approval-authority-bundle.v1"
)
MAX_MEDIA_SELECTION_APPROVALS = 300


class DigestPinnedMediaSelectionApprovalAuthority:
    """Resolved immutable decisions indexed by their opaque approval ref."""

    def __init__(
        self,
        approvals: Mapping[
            str, tuple[MediaSelectionSubject, VerifiedMediaSelection]
        ],
    ) -> None:
        self._approvals = dict(approvals)

    def verify(
        self,
        *,
        subject: MediaSelectionSubject,
        approval_ref: str,
        decision: str,
    ) -> VerifiedMediaSelection:
        try:
            configured_subject, approval = self._approvals[approval_ref]
        except KeyError:
            raise MediaSelectionApprovalRequiredError(
                "media selection approval was not resolved for the exact subject"
            ) from None
        if (
            configured_subject != subject
            or not approval.matches(
                subject=subject,
                approval_ref=approval_ref,
                decision=decision,
            )
        ):
            raise MediaSelectionApprovalRequiredError(
                "media selection approval was not resolved for the exact subject"
            )
        return approval


def _media_selection_approval_authority(
    bundle: Mapping[str, Any],
) -> DigestPinnedMediaSelectionApprovalAuthority:
    if set(bundle) != {"schemaVersion", "authorityRef", "approvals"}:
        raise ExternalAuthorityConfigurationError(
            "media selection approval authority fields are invalid"
        )
    if (
        bundle["schemaVersion"]
        != MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA
    ):
        raise ExternalAuthorityConfigurationError(
            "media selection approval authority schema is invalid"
        )
    authority_ref = _authority_ref(
        bundle["authorityRef"], "media selection approval authorityRef"
    )
    raw_approvals = bundle["approvals"]
    if (
        not isinstance(raw_approvals, list)
        or len(raw_approvals) > MAX_MEDIA_SELECTION_APPROVALS
    ):
        raise ExternalAuthorityConfigurationError(
            "media selection approval authority decisions are invalid"
        )
    fields = {
        "subject",
        "approvalRef",
        "actorRef",
        "actorKind",
        "decision",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "decidedAt",
    }
    approvals: dict[
        str, tuple[MediaSelectionSubject, VerifiedMediaSelection]
    ] = {}
    authority_decision_refs: set[str] = set()
    for raw in raw_approvals:
        if not isinstance(raw, Mapping) or set(raw) != fields:
            raise ExternalAuthorityConfigurationError(
                "media selection approval authority decision is invalid"
            )
        try:
            subject = MediaSelectionSubject.from_mapping(raw["subject"])
        except (MediaSelectionApprovalRequiredError, TypeError) as exc:
            raise ExternalAuthorityConfigurationError(
                "media selection approval authority subject is invalid"
            ) from exc
        approval_ref = _authority_ref(
            raw["approvalRef"], "media selection approval approvalRef"
        )
        actor_ref = _authority_ref(
            raw["actorRef"], "media selection approval actorRef"
        )
        authority_decision_ref = _authority_ref(
            raw["authorityDecisionRef"],
            "media selection approval authorityDecisionRef",
        )
        if approval_ref in approvals:
            raise ExternalAuthorityConfigurationError(
                "media selection approval approvalRef is duplicated"
            )
        if authority_decision_ref in authority_decision_refs:
            raise ExternalAuthorityConfigurationError(
                "media selection approval authorityDecisionRef is duplicated"
            )
        authority_decision_refs.add(authority_decision_ref)
        authority_decision_digest = _sha256(
            raw["authorityDecisionDigest"],
            "media selection approval authorityDecisionDigest",
        )
        try:
            approval = VerifiedMediaSelection.create(
                authority_ref=authority_ref,
                approval_ref=approval_ref,
                actor_ref=actor_ref,
                actor_kind=raw["actorKind"],
                decision=raw["decision"],
                authority_decision_ref=authority_decision_ref,
                authority_decision_digest=authority_decision_digest,
                decided_at=raw["decidedAt"],
                subject_digest=subject.subject_digest,
            )
        except MediaSelectionApprovalRequiredError as exc:
            raise ExternalAuthorityConfigurationError(
                "media selection approval authority evidence is invalid"
            ) from exc
        approvals[approval_ref] = (subject, approval)
    return DigestPinnedMediaSelectionApprovalAuthority(approvals)


def media_selection_approval_authority_from_environment(
    environ: Mapping[str, str],
):
    """Return a rejecting authority or one fully digest-pinned authority."""

    names = (
        "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_PATH",
        "CREATOR_MEDIA_SELECTION_AUTHORITY_BUNDLE_SHA256",
    )
    configured = {name: str(environ.get(name, "")).strip() for name in names}
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingMediaSelectionApprovalAuthority()
    if len(present) != len(names):
        raise ExternalAuthorityConfigurationError(
            "media selection approval authority configuration is incomplete"
        )
    bundle = _read_bundle(
        configured[names[0]],
        configured[names[1]],
        "media selection approval authority bundle",
    )
    return _media_selection_approval_authority(bundle)


__all__ = [
    "MEDIA_SELECTION_APPROVAL_AUTHORITY_BUNDLE_SCHEMA",
    "DigestPinnedMediaSelectionApprovalAuthority",
    "media_selection_approval_authority_from_environment",
]
