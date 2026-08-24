"""Canonical candidate review and admission chain for K2 media revisions.

This module owns evidence semantics only.  V4 remains responsible for runtime
jobs and artifact bytes; V5 records the immutable chain that determines whether
those bytes may become an authoritative AssetVersion.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RecordNotFoundError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _positive_int,
    _required_ref,
)


CANDIDATE = "Candidate"
TECHNICAL_VALIDATION = "TechnicalValidation"
SEMANTIC_VISUAL_QC = "SemanticVisualQCDecision"
HUMAN_SELECTION = "HumanSelectionDecision"
ASSET_ADMISSION = "AssetAdmission"
ASSET_VERSION = "AssetVersion"

REQUIRED_VISUAL_CHECKS = (
    "identity",
    "wardrobe",
    "location",
    "action",
    "prop",
    "motion",
)

VISUAL_QC_PROFILE = {
    "schemaVersion": "v5.k2-semantic-visual-qc-profile.v1",
    "assessmentProfileRef": "k2-semantic-visual-qc-v1",
    "assessmentProfileVersion": 1,
    "criteria": list(REQUIRED_VISUAL_CHECKS),
}
VISUAL_QC_PROFILE_DIGEST = _digest(VISUAL_QC_PROFILE)
MEDIA_SELECTION_SUBJECT_SCHEMA_VERSION = "v5.k2-media-selection-subject.v1"
VERIFIED_MEDIA_SELECTION_SCHEMA_VERSION = "v5.k2-verified-media-selection.v1"
SUCCESSOR_VIDEO_CANDIDATE_SCHEMA_VERSION = "v5.k2-media-candidate.v2"


class CandidateLifecycleError(EpisodeProductionError):
    code = "candidate_lifecycle_invalid"


class CandidateNotSelectableError(EpisodeProductionError):
    code = "candidate_not_selectable"


class MediaSelectionApprovalRequiredError(EpisodeProductionError):
    code = "media_selection_approval_required"


def _is_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 64:
        return False
    candidate = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None


@dataclass(frozen=True, slots=True)
class MediaSelectionSubject:
    """Closed-world identity of one exact candidate/QC selection decision."""

    workspace_ref: str
    production_run_ref: str
    revision_ref: str
    slot_ref: str
    source_request_ref: str
    source_request_digest: str
    candidate_ref: str
    candidate_version: int
    candidate_digest: str
    artifact_digest: str
    visual_qc_ref: str
    visual_qc_version: int
    visual_qc_digest: str
    subject_digest: str

    @classmethod
    def create(
        cls,
        *,
        workspace_ref: str,
        production_run_ref: str,
        revision_ref: str,
        slot_ref: str,
        source_request_ref: str,
        source_request_digest: str,
        candidate_ref: str,
        candidate_version: int,
        candidate_digest: str,
        artifact_digest: str,
        visual_qc_ref: str,
        visual_qc_version: int,
        visual_qc_digest: str,
    ) -> "MediaSelectionSubject":
        values = {
            "schemaVersion": MEDIA_SELECTION_SUBJECT_SCHEMA_VERSION,
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "productionRunRef": _required_ref(
                production_run_ref, "productionRunRef"
            ),
            "revisionRef": _required_ref(revision_ref, "revisionRef"),
            "slotRef": _required_ref(slot_ref, "slotRef"),
            "sourceRequestRef": _required_ref(
                source_request_ref, "sourceRequestRef"
            ),
            "sourceRequestDigest": _digest_value(
                source_request_digest, "sourceRequestDigest"
            ),
            "candidateRef": _required_ref(candidate_ref, "candidateRef"),
            "candidateVersion": _positive_int(
                candidate_version, "candidateVersion", maximum=1_000_000
            ),
            "candidateDigest": _digest_value(candidate_digest, "candidateDigest"),
            "artifactDigest": _digest_value(artifact_digest, "artifactDigest"),
            "visualQcRef": _required_ref(visual_qc_ref, "visualQcRef"),
            "visualQcVersion": _positive_int(
                visual_qc_version, "visualQcVersion", maximum=1_000_000
            ),
            "visualQcDigest": _digest_value(visual_qc_digest, "visualQcDigest"),
        }
        return cls(
            values["workspaceRef"],
            values["productionRunRef"],
            values["revisionRef"],
            values["slotRef"],
            values["sourceRequestRef"],
            values["sourceRequestDigest"],
            values["candidateRef"],
            values["candidateVersion"],
            values["candidateDigest"],
            values["artifactDigest"],
            values["visualQcRef"],
            values["visualQcVersion"],
            values["visualQcDigest"],
            _digest(values),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MediaSelectionSubject":
        fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "revisionRef",
            "slotRef",
            "sourceRequestRef",
            "sourceRequestDigest",
            "candidateRef",
            "candidateVersion",
            "candidateDigest",
            "artifactDigest",
            "visualQcRef",
            "visualQcVersion",
            "visualQcDigest",
            "subjectDigest",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != fields
            or value.get("schemaVersion") != MEDIA_SELECTION_SUBJECT_SCHEMA_VERSION
        ):
            raise MediaSelectionApprovalRequiredError(
                "media selection subject is invalid"
            )
        try:
            subject = cls.create(
                workspace_ref=value["workspaceRef"],
                production_run_ref=value["productionRunRef"],
                revision_ref=value["revisionRef"],
                slot_ref=value["slotRef"],
                source_request_ref=value["sourceRequestRef"],
                source_request_digest=value["sourceRequestDigest"],
                candidate_ref=value["candidateRef"],
                candidate_version=value["candidateVersion"],
                candidate_digest=value["candidateDigest"],
                artifact_digest=value["artifactDigest"],
                visual_qc_ref=value["visualQcRef"],
                visual_qc_version=value["visualQcVersion"],
                visual_qc_digest=value["visualQcDigest"],
            )
        except EpisodeProductionError as exc:
            raise MediaSelectionApprovalRequiredError(
                "media selection subject is invalid"
            ) from exc
        if value.get("subjectDigest") != subject.subject_digest:
            raise MediaSelectionApprovalRequiredError(
                "media selection subject digest does not match"
            )
        return subject

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": MEDIA_SELECTION_SUBJECT_SCHEMA_VERSION,
            "workspaceRef": self.workspace_ref,
            "productionRunRef": self.production_run_ref,
            "revisionRef": self.revision_ref,
            "slotRef": self.slot_ref,
            "sourceRequestRef": self.source_request_ref,
            "sourceRequestDigest": self.source_request_digest,
            "candidateRef": self.candidate_ref,
            "candidateVersion": self.candidate_version,
            "candidateDigest": self.candidate_digest,
            "artifactDigest": self.artifact_digest,
            "visualQcRef": self.visual_qc_ref,
            "visualQcVersion": self.visual_qc_version,
            "visualQcDigest": self.visual_qc_digest,
            "subjectDigest": self.subject_digest,
        }


@dataclass(frozen=True, slots=True)
class VerifiedMediaSelection:
    authority_ref: str
    approval_ref: str
    actor_ref: str
    actor_kind: str
    decision: str
    authority_decision_ref: str
    authority_decision_digest: str
    decided_at: str
    subject_digest: str

    @staticmethod
    def expected_decision_digest(
        *,
        authority_ref: str,
        approval_ref: str,
        actor_ref: str,
        actor_kind: str,
        decision: str,
        authority_decision_ref: str,
        decided_at: str,
        subject_digest: str,
    ) -> str:
        return _digest(
            {
                "schemaVersion": VERIFIED_MEDIA_SELECTION_SCHEMA_VERSION,
                "authorityRef": authority_ref,
                "approvalRef": approval_ref,
                "actorRef": actor_ref,
                "actorKind": actor_kind,
                "decision": decision,
                "authorityDecisionRef": authority_decision_ref,
                "decidedAt": decided_at,
                "subjectDigest": subject_digest,
            }
        )

    @classmethod
    def create(cls, **values: Any) -> "VerifiedMediaSelection":
        try:
            authority_ref = _required_ref(values.get("authority_ref"), "authorityRef")
            approval_ref = _required_ref(values.get("approval_ref"), "approvalRef")
            actor_ref = _required_ref(values.get("actor_ref"), "actorRef")
            authority_decision_ref = _required_ref(
                values.get("authority_decision_ref"), "authorityDecisionRef"
            )
        except EpisodeProductionError as exc:
            raise MediaSelectionApprovalRequiredError(
                "media selection authority evidence is invalid"
            ) from exc
        actor_kind = values.get("actor_kind")
        decision = values.get("decision")
        decided_at = values.get("decided_at")
        subject_digest = values.get("subject_digest")
        authority_decision_digest = values.get("authority_decision_digest")
        if (
            actor_kind != "HUMAN"
            or decision not in {"SELECTED", "REJECTED"}
            or not _is_timestamp(decided_at)
            or not isinstance(subject_digest, str)
            or not isinstance(authority_decision_digest, str)
        ):
            raise MediaSelectionApprovalRequiredError(
                "media selection authority evidence is invalid"
            )
        _digest_value(subject_digest, "subjectDigest")
        _digest_value(authority_decision_digest, "authorityDecisionDigest")
        expected = cls.expected_decision_digest(
            authority_ref=authority_ref,
            approval_ref=approval_ref,
            actor_ref=actor_ref,
            actor_kind=actor_kind,
            decision=decision,
            authority_decision_ref=authority_decision_ref,
            decided_at=decided_at,
            subject_digest=subject_digest,
        )
        if authority_decision_digest != expected:
            raise MediaSelectionApprovalRequiredError(
                "media selection authority decision digest does not match"
            )
        return cls(
            authority_ref,
            approval_ref,
            actor_ref,
            actor_kind,
            decision,
            authority_decision_ref,
            authority_decision_digest,
            decided_at,
            subject_digest,
        )

    def matches(
        self,
        *,
        subject: MediaSelectionSubject,
        approval_ref: str,
        decision: str,
    ) -> bool:
        return (
            self.approval_ref == approval_ref
            and self.actor_kind == "HUMAN"
            and self.decision == decision
            and self.subject_digest == subject.subject_digest
            and self.authority_decision_digest
            == self.expected_decision_digest(
                authority_ref=self.authority_ref,
                approval_ref=self.approval_ref,
                actor_ref=self.actor_ref,
                actor_kind=self.actor_kind,
                decision=self.decision,
                authority_decision_ref=self.authority_decision_ref,
                decided_at=self.decided_at,
                subject_digest=self.subject_digest,
            )
        )


class MediaSelectionApprovalAuthorityPort(Protocol):
    def verify(
        self,
        *,
        subject: MediaSelectionSubject,
        approval_ref: str,
        decision: str,
    ) -> VerifiedMediaSelection: ...


class RejectingMediaSelectionApprovalAuthority:
    def verify(self, **kwargs: Any) -> VerifiedMediaSelection:
        del kwargs
        raise MediaSelectionApprovalRequiredError(
            "an external media selection authority is required"
        )


class StaticMediaSelectionApprovalAuthority:
    """Explicit test authority; production never configures this implicitly."""

    def __init__(
        self,
        approvals: Mapping[str, tuple[MediaSelectionSubject, VerifiedMediaSelection]],
    ) -> None:
        self._approvals = dict(approvals)

    def verify(
        self,
        *,
        subject: MediaSelectionSubject,
        approval_ref: str,
        decision: str,
    ) -> VerifiedMediaSelection:
        configured = self._approvals.get(approval_ref)
        if configured is None or configured[0] != subject or not configured[1].matches(
            subject=subject, approval_ref=approval_ref, decision=decision
        ):
            raise MediaSelectionApprovalRequiredError(
                "media selection authority rejected the exact subject"
            )
        return configured[1]


def _digest_value(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CandidateLifecycleError(f"{field} is invalid")
    return value


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise CandidateLifecycleError(f"{field} is invalid")
    return value


def _safe_text(value: Any, field: str, *, maximum: int = 1000) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > maximum:
        raise CandidateLifecycleError(f"{field} is invalid")
    return value


def _storage_key(value: Any) -> str:
    text = _safe_text(value, "storageKey", maximum=1000)
    if not text or text.startswith(("/", "\\")) or ".." in text.replace("\\", "/").split("/"):
        raise CandidateLifecycleError("storageKey is invalid")
    return text


def _payload(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise CandidateLifecycleError("canonical candidate evidence is invalid")
    return deepcopy(dict(value))


def _evidence_record(record: Mapping[str, Any]) -> EvidenceRecord:
    """Rehydrate one repository-verified record for an atomic replay batch."""

    try:
        return EvidenceRecord(
            workspaceRef=record["workspaceRef"],
            productionRunRef=record["productionRunRef"],
            recordKind=record["recordKind"],
            recordRef=record["recordRef"],
            recordVersion=record["recordVersion"],
            idempotencyKey=record["idempotencyKey"],
            requestDigest=record["requestDigest"],
            createdAt=record["createdAt"],
            payload=deepcopy(dict(record["payload"])),
            payloadDigest=record["payloadDigest"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateLifecycleError(
            "canonical candidate evidence is invalid"
        ) from exc


def _sealed(value: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    payload = deepcopy(dict(value))
    digest = _digest(payload)
    payload["payloadDigest"] = digest
    return payload, digest


def _record(
    *,
    workspace_ref: str,
    run_ref: str,
    kind: str,
    ref: str,
    version: int,
    idempotency_key: str,
    created_at: str,
    payload: Mapping[str, Any],
) -> EvidenceRecord:
    sealed, payload_digest = _sealed(payload)
    request_digest = _digest(
        {
            "recordKind": kind,
            "recordRef": ref,
            "recordVersion": version,
            "payloadDigest": payload_digest,
        }
    )
    return EvidenceRecord(
        workspaceRef=workspace_ref,
        productionRunRef=run_ref,
        recordKind=kind,
        recordRef=ref,
        recordVersion=version,
        idempotencyKey=idempotency_key,
        requestDigest=request_digest,
        createdAt=created_at,
        payload=sealed,
        payloadDigest=payload_digest,
    )


class CanonicalAssetVersionAuthority:
    """Read-only projection over the one canonical AssetVersion evidence stream."""

    def __init__(self, evidence: EpisodeProductionEvidenceRepository) -> None:
        self.evidence = evidence

    def list_asset_versions(
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        gates: Sequence[Mapping[str, Any]] | None = None,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        versions: dict[str, dict[str, Any]] = {}
        gate_values = (
            self.evidence.list_gates(workspace_ref, production_run_ref)
            if gates is None
            else gates
        )
        for gate in gate_values:
            for fact in gate.get("facts", []):
                if not isinstance(fact, Mapping):
                    continue
                if not str(fact.get("factKind", "")).startswith("AssetVersion"):
                    continue
                payload = fact.get("payload")
                if isinstance(payload, Mapping):
                    self._add(versions, dict(payload))
        record_values = (
            self.evidence.list_records(
                workspace_ref, production_run_ref, record_kind=ASSET_VERSION
            )
            if records is None
            else [
                item
                for item in records
                if item.get("recordKind") == ASSET_VERSION
            ]
        )
        for record in record_values:
            self._add(versions, _payload(record))
        return sorted(
            versions.values(),
            key=lambda item: (
                str(item.get("assetRef", "")),
                int(item.get("version", 0)),
                str(item.get("assetVersionRef", "")),
            ),
        )

    @staticmethod
    def _add(index: dict[str, dict[str, Any]], value: dict[str, Any]) -> None:
        ref = _required_ref(value.get("assetVersionRef"), "assetVersionRef")
        existing = index.get(ref)
        if existing is not None and existing != value:
            raise CandidateLifecycleError("AssetVersion authority has conflicting facts")
        index[ref] = deepcopy(value)


class K2MediaCandidateReviewService:
    """Enforces Candidate → Validation → QC → Selection → Admission."""

    def __init__(
        self,
        root_service: Any,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        clock: Callable[[], str],
        selection_authority: MediaSelectionApprovalAuthorityPort | None = None,
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.asset_versions = CanonicalAssetVersionAuthority(evidence)
        self._clock = clock
        self.selection_authority = (
            selection_authority or RejectingMediaSelectionApprovalAuthority()
        )

    def _scope(self, command: Mapping[str, Any]) -> tuple[str, str, str]:
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        key = _idempotency_key(command.get("idempotencyKey"))
        self.root_service.get_run(workspace, run_ref)
        return workspace, run_ref, key

    def _exact(
        self,
        workspace: str,
        run_ref: str,
        ref: Any,
        version: Any,
        digest: Any,
        kind: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        selected_ref = _required_ref(ref, f"{kind}Ref")
        selected_version = _positive_int(version, f"{kind}Version", maximum=1_000_000)
        selected_digest = _digest_value(digest, f"{kind}Digest")
        record = self.evidence.get_record(
            workspace, run_ref, selected_ref, selected_version
        )
        if record is None:
            raise UpstreamNotReadyError(f"{kind} evidence is required")
        if record.get("recordKind") != kind or record.get("payloadDigest") != selected_digest:
            raise StaleInputError(f"{kind} evidence changed")
        return record, _payload(record)

    def prepare_candidate_record(self, command: Mapping[str, Any]) -> EvidenceRecord:
        """Validate and seal a Candidate without mutating the journal.

        Trusted V4 handoff services use this to commit Candidate and
        TechnicalValidation records as one closed append-only batch.  Public
        callers still use :meth:`register_candidate`, which immediately
        appends the prepared record.
        """

        workspace, run_ref, key = self._scope(command)
        root = self.root_service.get_run(workspace, run_ref)
        root_digest = _digest_value(root.get("payloadDigest"), "rootPayloadDigest")
        candidate_ref = _required_ref(command.get("candidateRef"), "candidateRef")
        candidate_version = _positive_int(
            command.get("candidateVersion", 1), "candidateVersion", maximum=1_000_000
        )
        media_kind = _enum(command.get("mediaKind"), "mediaKind", {"IMAGE", "VIDEO"})
        source_assets = command.get("sourceAssetVersions", [])
        if not isinstance(source_assets, list):
            raise CandidateLifecycleError("sourceAssetVersions is invalid")
        normalized_source_assets: list[dict[str, str]] = []
        for value in source_assets:
            if not isinstance(value, Mapping) or set(value) != {
                "assetVersionRef",
                "assetVersionDigest",
            }:
                raise CandidateLifecycleError("sourceAssetVersions is invalid")
            normalized_source_assets.append(
                {
                    "assetVersionRef": _required_ref(
                        value.get("assetVersionRef"), "assetVersionRef"
                    ),
                    "assetVersionDigest": _digest_value(
                        value.get("assetVersionDigest"), "assetVersionDigest"
                    ),
                }
            )
        if len({item["assetVersionRef"] for item in normalized_source_assets}) != len(
            normalized_source_assets
        ):
            raise CandidateLifecycleError("sourceAssetVersions is ambiguous")
        if media_kind == "VIDEO" and len(normalized_source_assets) != 1:
            raise CandidateLifecycleError(
                "video candidate requires one exact source AssetVersion"
            )
        consumed_request = command.get("consumedGenerationRequest")
        consumed_revision = command.get("consumedRealVideoRevision")
        if (consumed_request is None) != (consumed_revision is None):
            raise CandidateLifecycleError(
                "successor video candidate consumption evidence is incomplete"
            )
        if consumed_request is not None:
            if media_kind != "VIDEO":
                raise CandidateLifecycleError(
                    "only video candidates may bind consumed video requests"
                )
            for value, field in (
                (consumed_request, "consumedGenerationRequest"),
                (consumed_revision, "consumedRealVideoRevision"),
            ):
                if not isinstance(value, Mapping):
                    raise CandidateLifecycleError(f"{field} is invalid")
                sealed = deepcopy(dict(value))
                digest = sealed.pop("payloadDigest", None)
                if digest is None or digest != _digest(sealed):
                    raise CandidateLifecycleError(f"{field} digest is invalid")
        payload = {
            "schemaVersion": (
                SUCCESSOR_VIDEO_CANDIDATE_SCHEMA_VERSION
                if consumed_request is not None
                else "v5.k2-media-candidate.v1"
            ),
            "candidateRef": candidate_ref,
            "candidateVersion": candidate_version,
            "rootPayloadDigest": root_digest,
            "revisionRef": _required_ref(command.get("revisionRef"), "revisionRef"),
            "mediaKind": media_kind,
            "slotRef": _required_ref(command.get("slotRef"), "slotRef"),
            "sourceRequestRef": _required_ref(
                command.get("sourceRequestRef"), "sourceRequestRef"
            ),
            "sourceRequestDigest": _digest_value(
                command.get("sourceRequestDigest"), "sourceRequestDigest"
            ),
            "artifactRef": _required_ref(command.get("artifactRef"), "artifactRef"),
            "artifactDigest": _digest_value(
                command.get("artifactDigest"), "artifactDigest"
            ),
            "artifactByteSize": _positive_int(
                command.get("artifactByteSize"), "artifactByteSize", maximum=10**12
            ),
            "sourceAssetVersions": normalized_source_assets,
            "provenance": _enum(
                command.get("provenance"),
                "provenance",
                {"SELF_HOSTED_AI_GENERATED", "LOCAL_EVIDENCE", "IMPORTED"},
            ),
            "lifecycleState": "CANDIDATE_RECORDED",
            "publicationAllowed": False,
        }
        if consumed_request is not None:
            request = deepcopy(dict(consumed_request))
            revision = deepcopy(dict(consumed_revision))
            if (
                request.get("generationRequestRef")
                != payload["sourceRequestRef"]
                or request.get("payloadDigest")
                != payload["sourceRequestDigest"]
                or request.get("creativeShotVersionRef") != payload["slotRef"]
                or revision.get("realVideoRevisionRef")
                != payload["revisionRef"]
                or request.get("payloadDigest")
                not in revision.get("generationRequestDigests", [])
            ):
                raise CandidateLifecycleError(
                    "successor video candidate consumption lineage is invalid"
                )
            payload["consumedGenerationRequest"] = request
            payload["consumedRealVideoRevision"] = revision
        if "storageKey" in command:
            payload["storageKey"] = _storage_key(command.get("storageKey"))
        if "sourceCandidateRef" in command:
            payload["sourceCandidateRef"] = _required_ref(
                command.get("sourceCandidateRef"), "sourceCandidateRef"
            )
        item = _record(
            workspace_ref=workspace,
            run_ref=run_ref,
            kind=CANDIDATE,
            ref=candidate_ref,
            version=candidate_version,
            idempotency_key=key,
            created_at=self._clock(),
            payload=payload,
        )
        return item

    def register_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        item = self.prepare_candidate_record(command)
        stored, replayed = self.evidence.append_record(item)
        return {"candidate": _payload(stored), "idempotentReplay": replayed}

    def _current_candidate_record(
        self,
        workspace: str,
        run_ref: str,
        candidate_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Return the journal-current candidate record for the requested ref.

        Candidate journal order is the explicit non-transition active-lineage
        mechanism.  A newer Candidate for the same media kind and timeline
        slot makes every older candidate (and therefore its QC) stale without
        rewriting history or advancing production state.
        """

        selected_record: dict[str, Any] | None = None
        selected_payload: dict[str, Any] | None = None
        latest: dict[str, Any] | None = None
        candidates = (
            self.evidence.list_records(
                workspace, run_ref, record_kind=CANDIDATE
            )
            if records is None
            else [
                item
                for item in records
                if item.get("recordKind") == CANDIDATE
            ]
        )
        for record in candidates:
            payload = _payload(record)
            if record.get("recordRef") == candidate_ref:
                selected_record = record
                selected_payload = payload
        if selected_record is None or selected_payload is None:
            return None
        for record in candidates:
            payload = _payload(record)
            if (
                payload.get("mediaKind") == selected_payload.get("mediaKind")
                and payload.get("slotRef") == selected_payload.get("slotRef")
            ):
                latest = record
        if (
            latest is None
            or latest.get("recordRef") != selected_record.get("recordRef")
            or latest.get("recordVersion")
            != selected_record.get("recordVersion")
            or latest.get("payloadDigest")
            != selected_record.get("payloadDigest")
        ):
            return None
        if not self._source_asset_versions_are_current(
            workspace, run_ref, selected_payload
        ):
            return None
        return selected_record

    def _source_asset_versions_are_current(
        self,
        workspace: str,
        run_ref: str,
        candidate: Mapping[str, Any],
    ) -> bool:
        """Verify that a VIDEO candidate still uses the canonical image version.

        Historical compatibility records created before ADR-0013 can exist in a
        journal that has no AssetVersion authority facts at all.  Once an
        authoritative AssetVersion stream exists, however, every VIDEO source
        binding must resolve to the latest immutable version of the same logical
        image asset and the same shot slot.  This makes an admitted image
        successor stale the old video candidate/QC without rewriting either.
        """

        if candidate.get("mediaKind") != "VIDEO":
            return True
        source_versions = candidate.get("sourceAssetVersions")
        if not isinstance(source_versions, list) or len(source_versions) != 1:
            return False
        canonical = self.asset_versions.list_asset_versions(workspace, run_ref)
        if not canonical:
            return False
        source = source_versions[0]
        if not isinstance(source, Mapping):
            return False
        matching = [
            item
            for item in canonical
            if item.get("assetVersionRef") == source.get("assetVersionRef")
            and item.get("payloadDigest") == source.get("assetVersionDigest")
        ]
        if len(matching) != 1:
            return False
        selected = matching[0]
        if (
            str(selected.get("mediaKind", "")).lower() != "image"
            or selected.get("creativeShotVersionRef") != candidate.get("slotRef")
        ):
            return False
        logical_versions = [
            item
            for item in canonical
            if item.get("assetRef") == selected.get("assetRef")
            and str(item.get("mediaKind", "")).lower() == "image"
        ]
        if not logical_versions:
            return False
        latest = max(
            logical_versions,
            key=lambda item: (
                int(item.get("version", 0)),
                str(item.get("assetVersionRef", "")),
            ),
        )
        return (
            latest.get("assetVersionRef") == selected.get("assetVersionRef")
            and latest.get("payloadDigest") == selected.get("payloadDigest")
        )

    def _applicable_visual_qc(
        self,
        workspace: str,
        run_ref: str,
        candidate_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        current_candidate = self._current_candidate_record(
            workspace, run_ref, candidate_ref, records=records
        )
        if current_candidate is None:
            return None
        decisions: list[tuple[dict[str, Any], dict[str, Any]]] = []
        qc_records = (
            self.evidence.list_records(
                workspace, run_ref, record_kind=SEMANTIC_VISUAL_QC
            )
            if records is None
            else [
                item
                for item in records
                if item.get("recordKind") == SEMANTIC_VISUAL_QC
            ]
        )
        for record in qc_records:
            payload = _payload(record)
            if (
                payload.get("candidateRef") == candidate_ref
                and payload.get("candidateVersion")
                == current_candidate.get("recordVersion")
                and payload.get("candidateDigest")
                == current_candidate.get("payloadDigest")
            ):
                decisions.append((record, payload))
        superseded: set[tuple[str, int, str]] = set()
        identities = {
            (
                record["recordRef"],
                record["recordVersion"],
                record["payloadDigest"],
            )
            for record, _ in decisions
        }
        for _, payload in decisions:
            prior = payload.get("supersedesVisualQc")
            if prior is None:
                continue
            if not isinstance(prior, Mapping):
                raise CandidateLifecycleError(
                    "semantic visual QC supersession is invalid"
                )
            identity = (
                prior.get("visualQcRef"),
                prior.get("visualQcVersion"),
                prior.get("visualQcDigest"),
            )
            if identity not in identities:
                raise CandidateLifecycleError(
                    "semantic visual QC supersession is stale"
                )
            superseded.add(identity)
        applicable = [
            (record, payload)
            for record, payload in decisions
            if (
                record["recordRef"],
                record["recordVersion"],
                record["payloadDigest"],
            )
            not in superseded
            and payload.get("assessmentProfile") == VISUAL_QC_PROFILE
            and payload.get("assessmentProfileDigest")
            == VISUAL_QC_PROFILE_DIGEST
        ]
        if len(applicable) > 1:
            raise CandidateLifecycleError(
                "semantic visual QC applicability is ambiguous"
            )
        return applicable[0] if applicable else None

    def prepare_technical_validation_record(
        self,
        command: Mapping[str, Any],
        *,
        candidate_record: EvidenceRecord | None = None,
    ) -> EvidenceRecord:
        workspace, run_ref, key = self._scope(command)
        if candidate_record is None:
            candidate, candidate_payload = self._exact(
                workspace,
                run_ref,
                command.get("candidateRef"),
                command.get("candidateVersion", 1),
                command.get("candidateDigest"),
                CANDIDATE,
            )
        else:
            if (
                candidate_record.workspaceRef != workspace
                or candidate_record.productionRunRef != run_ref
                or candidate_record.recordKind != CANDIDATE
                or candidate_record.recordRef
                != command.get("candidateRef")
                or candidate_record.recordVersion
                != command.get("candidateVersion", 1)
                or candidate_record.payloadDigest
                != command.get("candidateDigest")
            ):
                raise StaleInputError("Candidate evidence changed")
            candidate = {
                "recordRef": candidate_record.recordRef,
                "recordVersion": candidate_record.recordVersion,
                "payloadDigest": candidate_record.payloadDigest,
            }
            candidate_payload = deepcopy(dict(candidate_record.payload))
        result = _enum(command.get("result"), "result", {"PASS", "FAIL"})
        checks = command.get("checks")
        if not isinstance(checks, list) or not checks:
            raise CandidateLifecycleError("checks is invalid")
        normalized_checks: list[dict[str, Any]] = []
        for check in checks:
            if not isinstance(check, Mapping):
                raise CandidateLifecycleError("checks is invalid")
            normalized_checks.append(
                {
                    "check": _required_ref(check.get("check"), "check"),
                    "passed": check.get("passed") is True,
                }
            )
        if (result == "PASS") != all(item["passed"] for item in normalized_checks):
            raise CandidateLifecycleError("technical validation result is inconsistent")
        validation_ref = _required_ref(
            command.get("technicalValidationRef"), "technicalValidationRef"
        )
        version = _positive_int(
            command.get("technicalValidationVersion", 1),
            "technicalValidationVersion",
            maximum=1_000_000,
        )
        payload = {
            "schemaVersion": "v5.k2-technical-validation.v1",
            "technicalValidationRef": validation_ref,
            "technicalValidationVersion": version,
            "candidateRef": candidate["recordRef"],
            "candidateVersion": candidate["recordVersion"],
            "candidateDigest": candidate["payloadDigest"],
            "artifactDigest": candidate_payload["artifactDigest"],
            "validatorRef": _required_ref(command.get("validatorRef"), "validatorRef"),
            "checks": normalized_checks,
            "result": result,
            "lifecycleState": "TECHNICALLY_VERIFIED" if result == "PASS" else "TECHNICAL_REJECTED",
            "publicationAllowed": False,
        }
        item = _record(
            workspace_ref=workspace,
            run_ref=run_ref,
            kind=TECHNICAL_VALIDATION,
            ref=validation_ref,
            version=version,
            idempotency_key=key,
            created_at=self._clock(),
            payload=payload,
        )
        return item

    def record_technical_validation(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        item = self.prepare_technical_validation_record(command)
        stored, replayed = self.evidence.append_record(item)
        return {"technicalValidation": _payload(stored), "idempotentReplay": replayed}

    def record_semantic_visual_qc(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        required_fields = {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "technicalValidationRef",
            "technicalValidationVersion",
            "technicalValidationDigest",
            "visualQcRef",
            "visualQcVersion",
            "reviewerRef",
            "reviewProfile",
            "evidence",
            "supersedesVisualQc",
            "checks",
            "result",
        }
        if not isinstance(command, Mapping) or set(command) != required_fields:
            raise CandidateLifecycleError(
                "semantic visual QC command fields are invalid"
            )
        workspace, run_ref, key = self._scope(command)
        if command.get("reviewProfile") != VISUAL_QC_PROFILE["assessmentProfileRef"]:
            raise CandidateLifecycleError("semantic visual QC profile is invalid")
        validation_ref = _required_ref(
            command.get("technicalValidationRef"), "technicalValidationRef"
        )
        validation_version = _positive_int(
            command.get("technicalValidationVersion"),
            "technicalValidationVersion",
            maximum=1_000_000,
        )
        validation_digest = _digest_value(
            command.get("technicalValidationDigest"),
            "technicalValidationDigest",
        )
        qc_ref = _required_ref(command.get("visualQcRef"), "visualQcRef")
        version = _positive_int(
            command.get("visualQcVersion"),
            "visualQcVersion",
            maximum=1_000_000,
        )
        reviewer_ref = _required_ref(command.get("reviewerRef"), "reviewerRef")
        raw_evidence = command.get("evidence")
        if (
            not isinstance(raw_evidence, list)
            or not raw_evidence
            or len(raw_evidence) > 20
        ):
            raise CandidateLifecycleError("semantic visual QC evidence is invalid")
        evidence_items: list[dict[str, str]] = []
        for value in raw_evidence:
            if not isinstance(value, Mapping) or set(value) != {
                "evidenceRef",
                "evidenceDigest",
            }:
                raise CandidateLifecycleError(
                    "semantic visual QC evidence is invalid"
                )
            evidence_items.append(
                {
                    "evidenceRef": _required_ref(
                        value.get("evidenceRef"), "evidenceRef"
                    ),
                    "evidenceDigest": _digest_value(
                        value.get("evidenceDigest"), "evidenceDigest"
                    ),
                }
            )
        if len({item["evidenceRef"] for item in evidence_items}) != len(evidence_items):
            raise CandidateLifecycleError(
                "semantic visual QC evidence is ambiguous"
            )
        requested_supersession = command.get("supersedesVisualQc")
        supersession: dict[str, Any] | None = None
        if requested_supersession is not None:
            if not isinstance(requested_supersession, Mapping) or set(
                requested_supersession
            ) != {
                "visualQcRef",
                "visualQcVersion",
                "visualQcDigest",
                "staleReason",
            }:
                raise CandidateLifecycleError(
                    "semantic visual QC must explicitly supersede current evidence"
                )
            supersession = {
                "visualQcRef": _required_ref(
                    requested_supersession.get("visualQcRef"), "visualQcRef"
                ),
                "visualQcVersion": _positive_int(
                    requested_supersession.get("visualQcVersion"),
                    "visualQcVersion",
                    maximum=1_000_000,
                ),
                "visualQcDigest": _digest_value(
                    requested_supersession.get("visualQcDigest"),
                    "visualQcDigest",
                ),
                "staleReason": _safe_text(
                    requested_supersession.get("staleReason"),
                    "staleReason",
                    maximum=500,
                ),
            }
            if not supersession["staleReason"]:
                raise CandidateLifecycleError(
                    "semantic visual QC stale reason is required"
                )
        result = _enum(command.get("result"), "result", {"PASS", "FAIL"})
        checks = command.get("checks")
        if not isinstance(checks, Mapping) or set(checks) != set(REQUIRED_VISUAL_CHECKS):
            raise CandidateLifecycleError("semantic visual QC checks are incomplete")
        normalized: dict[str, dict[str, str]] = {}
        for name in REQUIRED_VISUAL_CHECKS:
            check = checks[name]
            if not isinstance(check, Mapping):
                raise CandidateLifecycleError("semantic visual QC check is invalid")
            normalized[name] = {
                "result": _enum(check.get("result"), f"checks.{name}.result", {"PASS", "FAIL"}),
                "note": _safe_text(check.get("note", ""), f"checks.{name}.note"),
            }
        all_pass = all(item["result"] == "PASS" for item in normalized.values())
        if (result == "PASS") != all_pass:
            raise CandidateLifecycleError("semantic visual QC result is inconsistent")

        # Historical replay is resolved before currentness/supersession checks.
        # Once committed, the exact command must remain replayable after a later
        # QC supersedes it or a successor Candidate makes its lineage stale.
        expected_input = {
            "recordKind": SEMANTIC_VISUAL_QC,
            "recordRef": qc_ref,
            "recordVersion": version,
            "technicalValidationRef": validation_ref,
            "technicalValidationVersion": validation_version,
            "technicalValidationDigest": validation_digest,
            "reviewerRef": reviewer_ref,
            "assessmentProfile": VISUAL_QC_PROFILE,
            "assessmentProfileDigest": VISUAL_QC_PROFILE_DIGEST,
            "evidence": evidence_items,
            "supersedesVisualQc": supersession,
            "checks": normalized,
            "result": result,
        }

        def replay_existing(existing: Mapping[str, Any]) -> dict[str, Any]:
            existing_payload = _payload(existing)
            actual_input = {
                "recordKind": existing.get("recordKind"),
                "recordRef": existing.get("recordRef"),
                "recordVersion": existing.get("recordVersion"),
                "technicalValidationRef": existing_payload.get(
                    "technicalValidationRef"
                ),
                "technicalValidationVersion": existing_payload.get(
                    "technicalValidationVersion"
                ),
                "technicalValidationDigest": existing_payload.get(
                    "technicalValidationDigest"
                ),
                "reviewerRef": existing_payload.get("reviewerRef"),
                "assessmentProfile": existing_payload.get("assessmentProfile"),
                "assessmentProfileDigest": existing_payload.get(
                    "assessmentProfileDigest"
                ),
                "evidence": existing_payload.get("evidence"),
                "supersedesVisualQc": existing_payload.get(
                    "supersedesVisualQc"
                ),
                "checks": existing_payload.get("checks"),
                "result": existing_payload.get("result"),
            }
            if actual_input != expected_input:
                raise IdempotencyConflictError(
                    "semantic visual QC idempotency content changed"
                )
            return {
                "semanticVisualQc": existing_payload,
                "idempotentReplay": True,
            }

        existing = self.evidence.get_record_by_idempotency_key(
            workspace, run_ref, key
        )
        if existing is not None:
            return replay_existing(existing)

        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        validation, validation_payload = self._exact(
            workspace,
            run_ref,
            validation_ref,
            validation_version,
            validation_digest,
            TECHNICAL_VALIDATION,
        )
        if validation_payload.get("result") != "PASS":
            raise CandidateNotSelectableError("technical validation did not pass")
        _, candidate_payload = self._exact(
            workspace,
            run_ref,
            validation_payload.get("candidateRef"),
            validation_payload.get("candidateVersion"),
            validation_payload.get("candidateDigest"),
            CANDIDATE,
        )
        if self._current_candidate_record(
            workspace, run_ref, candidate_payload["candidateRef"]
        ) is None:
            raise StaleInputError("Candidate evidence is no longer current")
        current = self._applicable_visual_qc(
            workspace, run_ref, candidate_payload["candidateRef"]
        )
        if current is None:
            if supersession is not None:
                raise CandidateLifecycleError(
                    "semantic visual QC has nothing to supersede"
                )
        else:
            current_record, _ = current
            if supersession is None:
                # The exact concurrent winner can become current between the
                # initial idempotency lookup and this currentness read.  Treat
                # that committed record as the canonical replay rather than as
                # an unrelated supersession requirement.
                if current_record.get("idempotencyKey") == key:
                    return replay_existing(current_record)
                raise CandidateLifecycleError(
                    "semantic visual QC must explicitly supersede current evidence"
                )
            if (
                supersession["visualQcRef"] != current_record["recordRef"]
                or supersession["visualQcVersion"]
                != current_record["recordVersion"]
                or supersession["visualQcDigest"]
                != current_record["payloadDigest"]
            ):
                raise StaleInputError("semantic visual QC supersession changed")
        payload = {
            "schemaVersion": "v5.k2-semantic-visual-qc-decision.v1",
            "visualQcRef": qc_ref,
            "visualQcVersion": version,
            "revisionRef": candidate_payload["revisionRef"],
            "slotRef": candidate_payload["slotRef"],
            "sourceRequestRef": candidate_payload["sourceRequestRef"],
            "sourceRequestDigest": candidate_payload["sourceRequestDigest"],
            "sourceAssetVersions": deepcopy(
                candidate_payload["sourceAssetVersions"]
            ),
            "candidateRef": validation_payload["candidateRef"],
            "candidateVersion": validation_payload["candidateVersion"],
            "candidateDigest": validation_payload["candidateDigest"],
            "artifactDigest": validation_payload["artifactDigest"],
            "technicalValidationRef": validation["recordRef"],
            "technicalValidationVersion": validation["recordVersion"],
            "technicalValidationDigest": validation["payloadDigest"],
            "reviewerRef": reviewer_ref,
            "assessorKind": "HUMAN_ASSISTED_REVIEW",
            "assessmentProfile": deepcopy(VISUAL_QC_PROFILE),
            "assessmentProfileDigest": VISUAL_QC_PROFILE_DIGEST,
            "evidence": evidence_items,
            "supersedesVisualQc": supersession,
            "checks": normalized,
            "result": result,
            "lifecycleState": "SEMANTIC_QC_PASSED" if result == "PASS" else "SEMANTIC_QC_FAILED",
            "publicationAllowed": False,
        }
        item = _record(
            workspace_ref=workspace,
            run_ref=run_ref,
            kind=SEMANTIC_VISUAL_QC,
            ref=qc_ref,
            version=version,
            idempotency_key=key,
            created_at=self._clock(),
            payload=payload,
        )
        stored_items, replayed = self.evidence.append_records(
            (item,),
            expected_record_journal_head=expected_record_journal_head,
        )
        stored = stored_items[0]
        return {"semanticVisualQc": _payload(stored), "idempotentReplay": replayed}

    def prepare_human_selection_record(
        self, command: Mapping[str, Any]
    ) -> EvidenceRecord:
        """Verify authority and seal a selection without writing it.

        A SELECTED decision is intentionally returned only as an uncommitted
        record.  The admission service must commit that record together with
        its AssetAdmission, AssetVersion and (when applicable) activation gate.
        """

        required_fields = {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "visualQcRef",
            "visualQcVersion",
            "visualQcDigest",
            "selectionRef",
            "selectionVersion",
            "approvalRef",
            "decision",
        }
        if not isinstance(command, Mapping) or set(command) != required_fields:
            raise CandidateLifecycleError("human selection command fields are invalid")
        workspace, run_ref, key = self._scope(command)
        qc_ref = _required_ref(command.get("visualQcRef"), "visualQcRef")
        qc_version = _positive_int(
            command.get("visualQcVersion"),
            "visualQcVersion",
            maximum=1_000_000,
        )
        qc_digest = _digest_value(command.get("visualQcDigest"), "visualQcDigest")
        selection_ref = _required_ref(command.get("selectionRef"), "selectionRef")
        version = _positive_int(
            command.get("selectionVersion"),
            "selectionVersion",
            maximum=1_000_000,
        )
        approval_ref = _required_ref(command.get("approvalRef"), "approvalRef")
        decision = _enum(command.get("decision"), "decision", {"SELECTED", "REJECTED"})

        expected_replay_input = {
            "recordKind": HUMAN_SELECTION,
            "selectionRef": selection_ref,
            "selectionVersion": version,
            "visualQcRef": qc_ref,
            "visualQcVersion": qc_version,
            "visualQcDigest": qc_digest,
            "approvalRef": approval_ref,
            "decision": decision,
        }

        def replay_existing(existing: Mapping[str, Any]) -> EvidenceRecord:
            existing_payload = _payload(existing)
            actual = {
                "recordKind": existing.get("recordKind"),
                "selectionRef": existing.get("recordRef"),
                "selectionVersion": existing.get("recordVersion"),
                "visualQcRef": existing_payload.get("visualQcRef"),
                "visualQcVersion": existing_payload.get("visualQcVersion"),
                "visualQcDigest": existing_payload.get("visualQcDigest"),
                "approvalRef": existing_payload.get("approvalRef"),
                "decision": existing_payload.get("decision"),
            }
            if actual != expected_replay_input:
                raise IdempotencyConflictError(
                    "human selection idempotency content changed"
                )
            return _evidence_record(existing)

        # Resolve a committed command before consulting live QC applicability or
        # the external authority.  A durable decision remains replayable after
        # supersession and while the authority service is unavailable.
        by_key = self.evidence.get_record_by_idempotency_key(
            workspace, run_ref, key
        )
        by_identity = self.evidence.get_record(
            workspace, run_ref, selection_ref, version
        )
        existing = by_key or by_identity
        if existing is not None:
            if (
                by_key is not None
                and by_identity is not None
                and (
                    by_key.get("recordRef") != by_identity.get("recordRef")
                    or by_key.get("recordVersion")
                    != by_identity.get("recordVersion")
                    or by_key.get("payloadDigest")
                    != by_identity.get("payloadDigest")
                )
            ):
                raise IdempotencyConflictError(
                    "human selection idempotency content changed"
                )
            return replay_existing(existing)

        qc, qc_payload = self._exact(
            workspace,
            run_ref,
            qc_ref,
            qc_version,
            qc_digest,
            SEMANTIC_VISUAL_QC,
        )
        if decision == "SELECTED" and qc_payload.get("result") != "PASS":
            raise CandidateNotSelectableError("semantic visual QC did not pass")
        current = self._applicable_visual_qc(
            workspace, run_ref, qc_payload["candidateRef"]
        )
        if (
            current is None
            or current[0]["recordRef"] != qc["recordRef"]
            or current[0]["recordVersion"] != qc["recordVersion"]
            or current[0]["payloadDigest"] != qc["payloadDigest"]
        ):
            raise CandidateNotSelectableError(
                "semantic visual QC is stale or superseded"
            )
        subject = MediaSelectionSubject.create(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            revision_ref=qc_payload["revisionRef"],
            slot_ref=qc_payload["slotRef"],
            source_request_ref=qc_payload["sourceRequestRef"],
            source_request_digest=qc_payload["sourceRequestDigest"],
            candidate_ref=qc_payload["candidateRef"],
            candidate_version=qc_payload["candidateVersion"],
            candidate_digest=qc_payload["candidateDigest"],
            artifact_digest=qc_payload["artifactDigest"],
            visual_qc_ref=qc["recordRef"],
            visual_qc_version=qc["recordVersion"],
            visual_qc_digest=qc["payloadDigest"],
        )
        authority = self.selection_authority.verify(
            subject=subject,
            approval_ref=approval_ref,
            decision=decision,
        )
        if (
            not isinstance(authority, VerifiedMediaSelection)
            or not authority.matches(
                subject=subject,
                approval_ref=approval_ref,
                decision=decision,
            )
        ):
            raise MediaSelectionApprovalRequiredError(
                "media selection authority returned mismatched evidence"
            )

        for existing_selection in self.evidence.list_records(
            workspace, run_ref, record_kind=HUMAN_SELECTION
        ):
            existing_payload = _payload(existing_selection)
            # The exact concurrent winner may commit after the first key read
            # but before this uniqueness scan.  Replay it; only a different
            # command is forbidden from consuming the same authority fact.
            if existing_selection.get("idempotencyKey") == key:
                return replay_existing(existing_selection)
            same_subject_approval = (
                existing_payload.get("candidateRef")
                == qc_payload["candidateRef"]
                and existing_payload.get("candidateVersion")
                == qc_payload["candidateVersion"]
                and existing_payload.get("candidateDigest")
                == qc_payload["candidateDigest"]
                and existing_payload.get("visualQcRef") == qc["recordRef"]
                and existing_payload.get("visualQcVersion")
                == qc["recordVersion"]
                and existing_payload.get("visualQcDigest")
                == qc["payloadDigest"]
                and existing_payload.get("approvalRef") == approval_ref
            )
            same_authority_decision = (
                existing_payload.get("authorityDecisionRef")
                == authority.authority_decision_ref
                or existing_payload.get("authorityDecisionDigest")
                == authority.authority_decision_digest
            )
            if same_subject_approval or same_authority_decision:
                raise IdempotencyConflictError(
                    "human selection authority decision was already consumed"
                )
        payload = {
            "schemaVersion": "v5.k2-human-selection-decision.v1",
            "selectionRef": selection_ref,
            "selectionVersion": version,
            "candidateRef": qc_payload["candidateRef"],
            "candidateVersion": qc_payload["candidateVersion"],
            "candidateDigest": qc_payload["candidateDigest"],
            "artifactDigest": qc_payload["artifactDigest"],
            "visualQcRef": qc["recordRef"],
            "visualQcVersion": qc["recordVersion"],
            "visualQcDigest": qc["payloadDigest"],
            "subjectDigest": subject.subject_digest,
            "approvalRef": approval_ref,
            "actorRef": authority.actor_ref,
            "actorKind": authority.actor_kind,
            "authorityRef": authority.authority_ref,
            "authorityDecisionRef": authority.authority_decision_ref,
            "authorityDecisionDigest": authority.authority_decision_digest,
            "authorityDecidedAt": authority.decided_at,
            "decision": decision,
            "lifecycleState": "SELECTED_BY_HUMAN" if decision == "SELECTED" else "REJECTED_BY_HUMAN",
            "publicationAllowed": False,
        }
        item = _record(
            workspace_ref=workspace,
            run_ref=run_ref,
            kind=HUMAN_SELECTION,
            ref=selection_ref,
            version=version,
            idempotency_key=key,
            created_at=self._clock(),
            payload=payload,
        )
        return item

    def record_human_selection(self, command: Mapping[str, Any]) -> dict[str, Any]:
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        item = self.prepare_human_selection_record(command)
        if item.payload.get("decision") == "SELECTED":
            raise CandidateLifecycleError(
                "SELECTED decisions must be committed atomically by admission"
            )
        stored_items, replayed = self.evidence.append_records(
            (item,),
            expected_record_journal_head=expected_record_journal_head,
        )
        stored = stored_items[0]
        return {"humanSelection": _payload(stored), "idempotentReplay": replayed}

    def get_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.root_service.get_run(workspace_ref, production_run_ref)
        record_values = (
            self.evidence.list_records(workspace_ref, production_run_ref)
            if records is None
            else [deepcopy(dict(item)) for item in records]
        )
        candidates: dict[str, dict[str, Any]] = {}
        latest_candidate_revision_ref: str | None = None
        latest_candidate_revision_refs: dict[str, str] = {}
        for record in record_values:
            payload = _payload(record)
            candidate_ref = payload.get("candidateRef")
            if record["recordKind"] == CANDIDATE:
                candidate_ref = record["recordRef"]
            if not isinstance(candidate_ref, str):
                continue
            item = candidates.setdefault(
                candidate_ref,
                {
                    "candidateRef": candidate_ref,
                    "technicalState": "NOT_STARTED",
                    "visualQcState": "NOT_STARTED",
                    "selectionState": "UNSELECTED",
                    "admissionState": "NOT_ADMITTED",
                    "assetVersionRef": None,
                },
            )
            if record["recordKind"] == CANDIDATE:
                item["candidate"] = payload
                item["revisionRef"] = payload["revisionRef"]
                latest_candidate_revision_ref = payload["revisionRef"]
                media_kind = payload.get("mediaKind")
                if isinstance(media_kind, str):
                    latest_candidate_revision_refs[media_kind] = payload[
                        "revisionRef"
                    ]
            elif record["recordKind"] == TECHNICAL_VALIDATION:
                item["technicalState"] = payload["lifecycleState"]
                item["technicalValidation"] = payload
            elif record["recordKind"] == HUMAN_SELECTION:
                item["selectionState"] = payload["lifecycleState"]
                item["humanSelection"] = payload
            elif record["recordKind"] == ASSET_ADMISSION:
                item["admissionState"] = payload["admissionState"]
                item["assetVersionRef"] = payload["assetVersionRef"]
        gate_values = (
            self.evidence.list_gates(workspace_ref, production_run_ref)
            if gates is None
            else gates
        )
        for gate in gate_values:
            for fact in gate.get("facts", []):
                if (
                    not isinstance(fact, Mapping)
                    or not str(fact.get("factKind", "")).startswith(
                        "AssetAdmission:"
                    )
                    or not isinstance(fact.get("payload"), Mapping)
                ):
                    continue
                admission = fact["payload"]
                candidate_ref = admission.get("candidateRef")
                if not isinstance(candidate_ref, str):
                    continue
                item = candidates.setdefault(
                    candidate_ref,
                    {
                        "candidateRef": candidate_ref,
                        "technicalState": "NOT_STARTED",
                        "visualQcState": "NOT_STARTED",
                        "selectionState": "UNSELECTED",
                        "admissionState": "NOT_ADMITTED",
                        "assetVersionRef": None,
                    },
                )
                item["admissionState"] = admission.get(
                    "admissionState", "ADMITTED"
                )
                item["assetVersionRef"] = admission.get("assetVersionRef")
        for candidate_ref, item in candidates.items():
            item["applicabilityState"] = (
                "CURRENT"
                if self._current_candidate_record(
                    workspace_ref, production_run_ref, candidate_ref
                )
                is not None
                else "STALE"
            )
            current_qc = self._applicable_visual_qc(
                workspace_ref,
                production_run_ref,
                candidate_ref,
                records=record_values,
            )
            if current_qc is None:
                historical_qc = [
                    _payload(record)
                    for record in records
                    if record.get("recordKind") == SEMANTIC_VISUAL_QC
                    and isinstance(record.get("payload"), Mapping)
                    and record["payload"].get("candidateRef") == candidate_ref
                ]
                if historical_qc and self._current_candidate_record(
                    workspace_ref, production_run_ref, candidate_ref
                ) is None:
                    item["visualQcState"] = "STALE"
                    item["latestHistoricalSemanticVisualQc"] = historical_qc[-1]
                continue
            _, qc_payload = current_qc
            item["visualQcState"] = qc_payload["lifecycleState"]
            item["semanticVisualQc"] = qc_payload
        return {
            "schemaVersion": "v5.k2-candidate-lifecycle-projection.v1",
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "latestCandidateRevisionRef": latest_candidate_revision_ref,
            "latestCandidateRevisionRefs": dict(
                sorted(latest_candidate_revision_refs.items())
            ),
            "candidates": sorted(candidates.values(), key=lambda item: item["candidateRef"]),
            "assetVersions": self.asset_versions.list_asset_versions(
                workspace_ref,
                production_run_ref,
                gates=gate_values,
                records=record_values,
            ),
            "publicationAllowed": False,
        }


__all__ = [
    "ASSET_ADMISSION",
    "ASSET_VERSION",
    "CANDIDATE",
    "HUMAN_SELECTION",
    "SEMANTIC_VISUAL_QC",
    "TECHNICAL_VALIDATION",
    "CandidateLifecycleError",
    "CandidateNotSelectableError",
    "CanonicalAssetVersionAuthority",
    "K2MediaCandidateReviewService",
    "MediaSelectionApprovalAuthorityPort",
    "MediaSelectionApprovalRequiredError",
    "MediaSelectionSubject",
    "RejectingMediaSelectionApprovalAuthority",
    "StaticMediaSelectionApprovalAuthority",
    "VerifiedMediaSelection",
]
