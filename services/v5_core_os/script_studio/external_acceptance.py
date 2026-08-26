"""Digest-pinned exact-subject authority for reviewed Script acceptance."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .foundation import (
    RejectingScriptAcceptanceAuthority,
    ScriptAcceptanceSubject,
    ScriptStudioError,
    TrustedApprovalRequiredError,
    VerifiedScriptAcceptance,
    _required_ref,
    _sha256_digest,
)


SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SCHEMA = (
    "v5.external-script-acceptance-authority-bundle.v1"
)
MAX_BUNDLE_BYTES = 512_000
MAX_APPROVALS = 100


class ScriptAcceptanceConfigurationError(ScriptStudioError):
    code = "script_acceptance_authority_configuration_invalid"


class DigestPinnedScriptAcceptanceAuthority:
    def __init__(
        self,
        approvals: Mapping[
            str, tuple[ScriptAcceptanceSubject, VerifiedScriptAcceptance]
        ],
    ) -> None:
        self._approvals = dict(approvals)

    def verify(
        self,
        *,
        subject: ScriptAcceptanceSubject,
        approval_ref: str,
    ) -> VerifiedScriptAcceptance:
        try:
            configured_subject, approval = self._approvals[approval_ref]
        except KeyError:
            raise TrustedApprovalRequiredError(
                "reviewed Script acceptance was not resolved for the exact subject"
            ) from None
        if configured_subject != subject or not approval.matches(
            subject=subject,
            approval_ref=approval_ref,
        ):
            raise TrustedApprovalRequiredError(
                "reviewed Script acceptance was not resolved for the exact subject"
            )
        return approval


def _configuration_ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except ScriptStudioError as exc:
        raise ScriptAcceptanceConfigurationError(f"{field} is invalid") from exc


def _configuration_digest(value: Any, field: str) -> str:
    try:
        return _sha256_digest(value, field)
    except ScriptStudioError as exc:
        raise ScriptAcceptanceConfigurationError(f"{field} is invalid") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScriptAcceptanceConfigurationError(
                "Script acceptance authority contains duplicate JSON keys"
            )
        result[key] = value
    return result


def _read_bundle(path_value: str, expected_digest: str) -> Mapping[str, Any]:
    path = Path(path_value)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority path is unavailable"
        )
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority cannot be read"
        ) from exc
    if not payload or len(payload) > MAX_BUNDLE_BYTES:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority size is invalid"
        )
    if sha256(payload).hexdigest() != _configuration_digest(
        expected_digest, "Script acceptance authority digest"
    ):
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority digest does not match"
        )
    try:
        value = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_unique_object
        )
    except ScriptAcceptanceConfigurationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority is not valid JSON"
        ) from exc
    if not isinstance(value, Mapping):
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority root is invalid"
        )
    return value


def _authority(
    bundle: Mapping[str, Any],
) -> DigestPinnedScriptAcceptanceAuthority:
    if set(bundle) != {"schemaVersion", "authorityRef", "approvals"}:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority fields are invalid"
        )
    if bundle.get("schemaVersion") != SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SCHEMA:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority schema is invalid"
        )
    authority_ref = _configuration_ref(
        bundle.get("authorityRef"), "authorityRef"
    )
    values = bundle.get("approvals")
    if not isinstance(values, list) or not values or len(values) > MAX_APPROVALS:
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority approvals are invalid"
        )
    subject_fields = {
        "schemaVersion",
        "workspaceRef",
        "seriesRef",
        "episodeRef",
        "scriptRef",
        "scriptVersionRef",
        "uploadedSourceByteDigest",
        "normalizedSourceDocumentDigest",
        "reviewedDocumentDigest",
        "canonicalScriptContentDigest",
        "importProvenanceDigest",
    }
    approval_fields = {
        "subject",
        "approvalRef",
        "actorRef",
        "actorKind",
        "decision",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "decidedAt",
        "governanceRecordRef",
    }
    approvals: dict[
        str, tuple[ScriptAcceptanceSubject, VerifiedScriptAcceptance]
    ] = {}
    decision_refs: set[str] = set()
    for raw in values:
        if not isinstance(raw, Mapping) or set(raw) != approval_fields:
            raise ScriptAcceptanceConfigurationError(
                "Script acceptance authority approval is invalid"
            )
        subject_value = raw.get("subject")
        if not isinstance(subject_value, Mapping) or set(subject_value) != subject_fields:
            raise ScriptAcceptanceConfigurationError(
                "Script acceptance authority subject is invalid"
            )
        try:
            subject = ScriptAcceptanceSubject.create(
                **{
                    key: value
                    for key, value in subject_value.items()
                    if key != "schemaVersion"
                }
            )
            if subject.as_mapping() != dict(subject_value):
                raise TrustedApprovalRequiredError("subject shape changed")
            approval_ref = _configuration_ref(
                raw.get("approvalRef"), "approvalRef"
            )
            decision_ref = _configuration_ref(
                raw.get("authorityDecisionRef"), "authorityDecisionRef"
            )
            approval = VerifiedScriptAcceptance.create(
                authorityRef=authority_ref,
                approvalRef=approval_ref,
                actorRef=raw.get("actorRef"),
                actorKind=raw.get("actorKind"),
                decision=raw.get("decision"),
                authorityDecisionRef=decision_ref,
                authorityDecisionDigest=raw.get("authorityDecisionDigest"),
                decidedAt=raw.get("decidedAt"),
                governanceRecordRef=raw.get("governanceRecordRef"),
                subjectDigest=subject.subject_digest,
            )
        except ScriptStudioError as exc:
            raise ScriptAcceptanceConfigurationError(
                "Script acceptance authority evidence is invalid"
            ) from exc
        if approval_ref in approvals or decision_ref in decision_refs:
            raise ScriptAcceptanceConfigurationError(
                "Script acceptance authority decision is duplicated"
            )
        decision_refs.add(decision_ref)
        approvals[approval_ref] = (subject, approval)
    return DigestPinnedScriptAcceptanceAuthority(approvals)


def script_acceptance_authority_from_environment(environ: Mapping[str, str]):
    names = (
        "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_PATH",
        "CREATOR_SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SHA256",
    )
    configured = {name: str(environ.get(name, "")).strip() for name in names}
    present = [name for name, value in configured.items() if value]
    if not present:
        return RejectingScriptAcceptanceAuthority()
    if len(present) != len(names):
        raise ScriptAcceptanceConfigurationError(
            "Script acceptance authority configuration is incomplete"
        )
    return _authority(_read_bundle(configured[names[0]], configured[names[1]]))


__all__ = [
    "SCRIPT_ACCEPTANCE_AUTHORITY_BUNDLE_SCHEMA",
    "DigestPinnedScriptAcceptanceAuthority",
    "ScriptAcceptanceConfigurationError",
    "script_acceptance_authority_from_environment",
]
