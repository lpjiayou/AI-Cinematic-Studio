"""G6 deterministic composition, QC, explicit decisions and immutable master."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from services.v3_render_core.digests import (
    DigestError,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
)
from services.v4_platform import (
    ArtifactVerificationError,
    CompositionExecutionError,
    probe_media,
)

from .audio_timing import AudioCue, AudioStemSet
from .evidence import (
    EpisodeProductionEvidenceRepository,
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    validated_evidence_snapshot,
)
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .media import ArtifactRejectedError, K2MediaExecutionService, WorkerUnavailableError
from .glyph_reveal_v2 import (
    DigestPinnedBasePlateGlyphInspectionAdapter,
    GlyphRevealRequirementV2,
    build_glyph_reveal_composition_result_v2,
    build_glyph_reveal_execution_request_v2,
)
from .shot_graph import ValidationFailedError
from .timeline_preview import (
    AudioInputBinding,
    COMPOSITION_RESULT_SCHEMA_VERSION,
    PREVIEW_CANDIDATE_SCHEMA_VERSION_V2,
    TIMELINE_VERSION_SCHEMA_VERSION_V2,
    build_timeline,
    build_timeline_clip,
    build_composition_result,
    build_mask_asset_version_binding,
    build_preview_candidate,
    build_subtitle_manifest,
    build_timeline_input_bundle,
    build_timeline_mix_request,
    build_timeline_track,
    build_timeline_version,
    map_sample_boundary_to_frame,
    project_timeline_mix_request,
    validate_audio_input_binding,
    validate_composition_result,
    validate_mask_asset_version_binding,
    validate_preview_candidate,
    validate_subtitle_manifest,
    validate_timeline,
    validate_timeline_clip,
    validate_timeline_input_bundle,
    validate_timeline_mix_request,
    validate_timeline_track,
    validate_timeline_version,
)


COMPOSITION_GATE = "G6_COMPOSITION"
QC_GATE = "G6_QC"
APPROVAL_GATE = "G6_APPROVALS"
MASTER_GATE = "G6_MASTER"
TIMELINE_SCHEMA_VERSION = "v5.timeline-version.v1"
PREVIEW_SCHEMA_VERSION = "v5.preview-candidate.v1"
QC_SCHEMA_VERSION = "v5.qc-report.v1"
APPROVAL_SCHEMA_VERSION = "v5.approval-decision.v2"
APPROVAL_SUBJECT_SCHEMA_VERSION = "v5.delivery-approval-subject.v1"
VERIFIED_APPROVAL_SCHEMA_VERSION = "v5.verified-delivery-approval.v1"
MASTER_SCHEMA_VERSION = "v5.episode-master.v1"
EXPORT_SCHEMA_VERSION = "v5.export-artifact.v1"
DELIVERY_ID = "v5.k2.delivery.v1"
TIMELINE_PREVIEW_DELIVERY_ID = "v5.k2.timeline-preview-delivery.v1"
APPROVAL_KINDS = (
    "CREATIVE_DIRECTION",
    "IDENTITY_CONTINUITY",
    "TECHNICAL_QC",
    "FINAL_MASTER",
)


class ApprovalRequiredError(EpisodeProductionError):
    code = "approval_required"


class ApprovalRejectedError(EpisodeProductionError):
    code = "approval_rejected"


class CompositionExecutionPort(Protocol):
    artifact_root: Path

    def compose(self, command: Mapping[str, Any]) -> dict[str, Any]: ...
    def compose_glyph_reveal_v2(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    def compose_timeline_preview_v1(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    def finalize(self, command: Mapping[str, Any]) -> dict[str, Any]: ...


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_timestamp(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 64
    ):
        return False
    candidate = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _subject_ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise StaleInputError(f"approval subject {field} is invalid") from exc


@dataclass(frozen=True, slots=True)
class ApprovalSubject:
    """Closed-world identity of the exact media evidence being approved."""

    workspace_ref: str
    production_run_ref: str
    kind: str
    timeline_version_ref: str
    timeline_digest: str
    preview_candidate_version_ref: str
    preview_candidate_digest: str
    qc_report_ref: str
    qc_report_digest: str
    subject_digest: str

    @classmethod
    def create(
        cls,
        *,
        workspace_ref: str,
        production_run_ref: str,
        kind: str,
        timeline_version_ref: str,
        timeline_digest: str,
        preview_candidate_version_ref: str,
        preview_candidate_digest: str,
        qc_report_ref: str,
        qc_report_digest: str,
    ) -> "ApprovalSubject":
        if kind not in APPROVAL_KINDS:
            raise StaleInputError("approval subject kind is invalid")
        values = {
            "schemaVersion": APPROVAL_SUBJECT_SCHEMA_VERSION,
            "workspaceRef": _subject_ref(workspace_ref, "workspaceRef"),
            "productionRunRef": _subject_ref(
                production_run_ref, "productionRunRef"
            ),
            "kind": kind,
            "timelineVersionRef": _subject_ref(
                timeline_version_ref, "timelineVersionRef"
            ),
            "timelineDigest": timeline_digest,
            "previewCandidateVersionRef": _subject_ref(
                preview_candidate_version_ref,
                "previewCandidateVersionRef",
            ),
            "previewCandidateDigest": preview_candidate_digest,
            "qcReportRef": _subject_ref(qc_report_ref, "qcReportRef"),
            "qcReportDigest": qc_report_digest,
        }
        for field in (
            "timelineDigest",
            "previewCandidateDigest",
            "qcReportDigest",
        ):
            if not _is_sha256(values[field]):
                raise StaleInputError(f"approval subject {field} is invalid")
        return cls(
            values["workspaceRef"],
            values["productionRunRef"],
            values["kind"],
            values["timelineVersionRef"],
            values["timelineDigest"],
            values["previewCandidateVersionRef"],
            values["previewCandidateDigest"],
            values["qcReportRef"],
            values["qcReportDigest"],
            _digest(values),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ApprovalSubject":
        fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "kind",
            "timelineVersionRef",
            "timelineDigest",
            "previewCandidateVersionRef",
            "previewCandidateDigest",
            "qcReportRef",
            "qcReportDigest",
            "subjectDigest",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != fields
            or value.get("schemaVersion") != APPROVAL_SUBJECT_SCHEMA_VERSION
        ):
            raise ApprovalRequiredError("approval subject fields are invalid")
        try:
            subject = cls.create(
                workspace_ref=value["workspaceRef"],
                production_run_ref=value["productionRunRef"],
                kind=value["kind"],
                timeline_version_ref=value["timelineVersionRef"],
                timeline_digest=value["timelineDigest"],
                preview_candidate_version_ref=value[
                    "previewCandidateVersionRef"
                ],
                preview_candidate_digest=value["previewCandidateDigest"],
                qc_report_ref=value["qcReportRef"],
                qc_report_digest=value["qcReportDigest"],
            )
        except StaleInputError as exc:
            raise ApprovalRequiredError("approval subject is invalid") from exc
        if value.get("subjectDigest") != subject.subject_digest:
            raise ApprovalRequiredError("approval subject digest does not match")
        return subject

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": APPROVAL_SUBJECT_SCHEMA_VERSION,
            "workspaceRef": self.workspace_ref,
            "productionRunRef": self.production_run_ref,
            "kind": self.kind,
            "timelineVersionRef": self.timeline_version_ref,
            "timelineDigest": self.timeline_digest,
            "previewCandidateVersionRef": self.preview_candidate_version_ref,
            "previewCandidateDigest": self.preview_candidate_digest,
            "qcReportRef": self.qc_report_ref,
            "qcReportDigest": self.qc_report_digest,
            "subjectDigest": self.subject_digest,
        }


@dataclass(frozen=True, slots=True)
class VerifiedApproval:
    """Auditable authority decision bound to one exact ApprovalSubject."""

    authority_ref: str
    approval_ref: str
    actor_ref: str
    kind: str
    authority_type: str
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
        kind: str,
        authority_type: str,
        decision: str,
        authority_decision_ref: str,
        decided_at: str,
        subject_digest: str,
    ) -> str:
        return _digest(
            {
                "schemaVersion": VERIFIED_APPROVAL_SCHEMA_VERSION,
                "authorityRef": authority_ref,
                "approvalRef": approval_ref,
                "actorRef": actor_ref,
                "kind": kind,
                "authorityType": authority_type,
                "decision": decision,
                "authorityDecisionRef": authority_decision_ref,
                "decidedAt": decided_at,
                "subjectDigest": subject_digest,
            }
        )

    @classmethod
    def create(
        cls,
        *,
        authority_ref: str,
        approval_ref: str,
        actor_ref: str,
        kind: str,
        authority_type: str,
        decision: str,
        authority_decision_ref: str,
        authority_decision_digest: str,
        decided_at: str,
        subject_digest: str,
    ) -> "VerifiedApproval":
        try:
            authority = _required_ref(authority_ref, "authorityRef")
            approval = _required_ref(approval_ref, "approvalRef")
            actor = _required_ref(actor_ref, "actorRef")
            authority_decision = _required_ref(
                authority_decision_ref, "authorityDecisionRef"
            )
        except EpisodeProductionError as exc:
            raise ApprovalRequiredError("approval authority evidence is invalid") from exc
        if (
            kind not in APPROVAL_KINDS
            or authority_type != "HUMAN"
            or decision not in {"ACCEPT", "REJECT"}
            or not _is_timestamp(decided_at)
            or not _is_sha256(subject_digest)
            or not _is_sha256(authority_decision_digest)
        ):
            raise ApprovalRequiredError("approval authority evidence is invalid")
        expected_digest = cls.expected_decision_digest(
            authority_ref=authority,
            approval_ref=approval,
            actor_ref=actor,
            kind=kind,
            authority_type=authority_type,
            decision=decision,
            authority_decision_ref=authority_decision,
            decided_at=decided_at,
            subject_digest=subject_digest,
        )
        if authority_decision_digest != expected_digest:
            raise ApprovalRequiredError(
                "approval authority decision digest does not match"
            )
        return cls(
            authority,
            approval,
            actor,
            kind,
            authority_type,
            decision,
            authority_decision,
            authority_decision_digest,
            decided_at,
            subject_digest,
        )

    def matches(
        self,
        *,
        subject: ApprovalSubject,
        approval_ref: str,
        actor_ref: str,
    ) -> bool:
        return (
            self.approval_ref == approval_ref
            and self.actor_ref == actor_ref
            and self.kind == subject.kind
            and self.authority_type == "HUMAN"
            and self.subject_digest == subject.subject_digest
            and self.authority_decision_digest
            == self.expected_decision_digest(
                authority_ref=self.authority_ref,
                approval_ref=self.approval_ref,
                actor_ref=self.actor_ref,
                kind=self.kind,
                authority_type=self.authority_type,
                decision=self.decision,
                authority_decision_ref=self.authority_decision_ref,
                decided_at=self.decided_at,
                subject_digest=self.subject_digest,
            )
        )


class ApprovalAuthorityPort(Protocol):
    def verify(
        self,
        *,
        subject: ApprovalSubject,
        approval_ref: str,
        actor_ref: str,
    ) -> VerifiedApproval: ...


class RejectingApprovalAuthority:
    def verify(self, **kwargs: Any) -> VerifiedApproval:
        del kwargs
        raise ApprovalRequiredError("an external approval authority is required")


class StaticApprovalAuthority:
    """Explicit test/local integration authority; never configured implicitly."""

    def __init__(self, approvals: Mapping[str, Mapping[str, Any]]) -> None:
        self._approvals = deepcopy(dict(approvals))

    def verify(
        self,
        *,
        subject: ApprovalSubject,
        approval_ref: str,
        actor_ref: str,
    ) -> VerifiedApproval:
        value = self._approvals.get(approval_ref)
        if (
            not isinstance(value, Mapping)
            or value.get("workspaceRef") != subject.workspace_ref
            or value.get("productionRunRef") != subject.production_run_ref
            or value.get("kind") != subject.kind
            or value.get("actorRef") != actor_ref
            or value.get("authorityType") != "HUMAN"
            or value.get("subjectDigest")
            not in (None, subject.subject_digest)
        ):
            raise ApprovalRequiredError("approval authority rejected evidence")
        if "subject" in value:
            try:
                configured_subject = ApprovalSubject.from_mapping(value["subject"])
            except (ApprovalRequiredError, TypeError) as exc:
                raise ApprovalRequiredError(
                    "approval authority rejected evidence"
                ) from exc
            if configured_subject != subject:
                raise ApprovalRequiredError("approval authority rejected evidence")
        authority_ref = value.get(
            "authorityRef", "static-delivery-approval-authority"
        )
        decision = value.get("decision", "ACCEPT")
        decided_at = value.get("decidedAt", "1970-01-01T00:00:00Z")
        authority_decision_ref = value.get(
            "authorityDecisionRef",
            f"static-authority-decision-{_digest({'approvalRef': approval_ref})[:24]}",
        )
        authority_decision_digest = value.get("authorityDecisionDigest")
        if authority_decision_digest is None:
            authority_decision_digest = VerifiedApproval.expected_decision_digest(
                authority_ref=authority_ref,
                approval_ref=approval_ref,
                actor_ref=actor_ref,
                kind=subject.kind,
                authority_type="HUMAN",
                decision=decision,
                authority_decision_ref=authority_decision_ref,
                decided_at=decided_at,
                subject_digest=subject.subject_digest,
            )
        return VerifiedApproval.create(
            authority_ref=authority_ref,
            approval_ref=approval_ref,
            actor_ref=actor_ref,
            kind=subject.kind,
            authority_type=value["authorityType"],
            decision=decision,
            authority_decision_ref=authority_decision_ref,
            authority_decision_digest=authority_decision_digest,
            decided_at=decided_at,
            subject_digest=subject.subject_digest,
        )


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value["payloadDigest"] = _digest(value)
    return value


def _fact(gate: Mapping[str, Any], kind: str) -> dict[str, Any]:
    matches = [
        item for item in gate.get("facts", [])
        if isinstance(item, Mapping) and item.get("factKind") == kind
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("payload"), Mapping):
        raise RepositoryUnavailableError("G6 evidence fact is inconsistent")
    return deepcopy(dict(matches[0]["payload"]))


def _approval_facts(gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = [
        deepcopy(dict(item["payload"]))
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and str(item.get("factKind", "")).startswith("ApprovalDecision:")
        and isinstance(item.get("payload"), Mapping)
    ]
    order = {kind: index for index, kind in enumerate(APPROVAL_KINDS)}
    return sorted(values, key=lambda item: order[item["kind"]])


def _immutable_payload(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationFailedError(f"{label} must be an immutable object")
    payload = deepcopy(dict(value))
    claimed_digest = payload.pop("payloadDigest", None)
    if not _is_sha256(claimed_digest) or _digest(payload) != claimed_digest:
        raise StaleInputError(f"{label} payload digest is invalid")
    payload["payloadDigest"] = claimed_digest
    return payload


def _positive_version(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationFailedError(f"{field} is invalid")
    return value


def _contains_path_authority(value: Any) -> bool:
    forbidden = {
        "absolutepath",
        "filepath",
        "internalpath",
        "localpath",
        "path",
        "sourcepath",
    }
    if isinstance(value, Mapping):
        for field, item in value.items():
            if (
                isinstance(field, str)
                and field.replace("_", "").replace("-", "").lower()
                in forbidden
            ):
                return True
            if _contains_path_authority(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_path_authority(item) for item in value)
    return False


def _audio_role_from_binding(value: Mapping[str, Any]) -> str:
    asset = value.get("assetVersion")
    if not isinstance(asset, Mapping):
        raise RepositoryUnavailableError("audio binding AssetVersion is invalid")
    asset_type = value.get("assetVersionType")
    role = (
        asset.get("speechRole")
        if asset_type == "DialogueAssetVersion"
        else {
            "MusicAssetVersion": "music",
            "SfxAssetVersion": "sfx",
            "AmbienceAssetVersion": "ambience",
        }.get(asset_type)
    )
    if role not in {"dialogue", "narration", "music", "sfx", "ambience"}:
        raise RepositoryUnavailableError("audio binding role is invalid")
    return str(role)


class K2DeliveryService:
    def __init__(
        self,
        media: K2MediaExecutionService,
        evidence: EpisodeProductionEvidenceRepository,
        composition: CompositionExecutionPort | None,
        approval_authority: ApprovalAuthorityPort,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
        glyph_inspection_adapter: (
            DigestPinnedBasePlateGlyphInspectionAdapter | None
        ) = None,
    ) -> None:
        self.media = media
        self.evidence = evidence
        self.composition = composition
        self.approval_authority = approval_authority
        self.glyph_inspection_adapter = glyph_inspection_adapter
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _input_record(
        *,
        workspace: str,
        run_ref: str,
        record_kind: str,
        record_ref: str,
        record_version: int,
        client_key: str,
        slot: str,
        batch_digest: str,
        created_at: str,
        payload: Mapping[str, Any],
    ) -> EvidenceRecord:
        canonical = _immutable_payload(payload, record_kind)
        reference = _required_ref(record_ref, "recordRef")
        version = _positive_version(record_version, "recordVersion")
        record_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "record-m12-m13-inputs",
                "slot": slot,
            }
        )
        request_digest = _digest(
            {
                "schemaVersion": "v5.m12-m13-input-record-request.v1",
                "batchDigest": batch_digest,
                "recordKind": record_kind,
                "recordRef": reference,
                "recordVersion": version,
                "payloadDigest": canonical["payloadDigest"],
            }
        )
        return EvidenceRecord(
            workspaceRef=workspace,
            productionRunRef=run_ref,
            recordKind=record_kind,
            recordRef=reference,
            recordVersion=version,
            idempotencyKey=record_key,
            requestDigest=request_digest,
            createdAt=created_at,
            payload=canonical,
            payloadDigest=canonical["payloadDigest"],
        )

    @staticmethod
    def _composition_record(
        *,
        workspace: str,
        run_ref: str,
        record_kind: str,
        record_ref: str,
        record_version: int,
        client_key: str,
        operation_ref: str,
        composition_request_digest: str,
        slot: str,
        created_at: str,
        payload: Mapping[str, Any],
    ) -> EvidenceRecord:
        canonical = _immutable_payload(payload, record_kind)
        reference = _required_ref(record_ref, "recordRef")
        version = _positive_version(record_version, "recordVersion")
        record_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "operationRef": operation_ref,
                "stage": "compose-m12-m13-preview",
                "slot": slot,
            }
        )
        request_digest = _digest(
            {
                "schemaVersion": "v5.m12-m13-composition-record-request.v1",
                "compositionRequestDigest": composition_request_digest,
                "recordKind": record_kind,
                "recordRef": reference,
                "recordVersion": version,
                "payloadDigest": canonical["payloadDigest"],
            }
        )
        return EvidenceRecord(
            workspaceRef=workspace,
            productionRunRef=run_ref,
            recordKind=record_kind,
            recordRef=reference,
            recordVersion=version,
            idempotencyKey=record_key,
            requestDigest=request_digest,
            createdAt=created_at,
            payload=canonical,
            payloadDigest=canonical["payloadDigest"],
        )

    def _stable_record_head(
        self, workspace: str, run_ref: str, revision: str
    ) -> str:
        head = self.evidence.record_journal_head(workspace, run_ref)
        confirmed = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        if confirmed.revisionToken != revision:
            raise StaleInputError("episode evidence changed during input validation")
        return head

    @staticmethod
    def _snapshot_record_payload(
        snapshot: Any, *, record_kind: str, record_ref: str
    ) -> dict[str, Any]:
        matches = [
            item
            for item in snapshot.records
            if item.get("recordKind") == record_kind
            and item.get("recordRef") == record_ref
        ]
        if len(matches) != 1:
            raise UpstreamNotReadyError(
                f"exact {record_kind} evidence is not available"
            )
        record = matches[0]
        payload = _immutable_payload(record.get("payload"), record_kind)
        if payload["payloadDigest"] != record.get("payloadDigest"):
            raise RepositoryUnavailableError(
                f"{record_kind} evidence digest is inconsistent"
            )
        return payload

    def _composition_storage_path(self, storage_key: Any) -> Path:
        if self.composition is None:
            raise WorkerUnavailableError("composition execution is not configured")
        if (
            not isinstance(storage_key, str)
            or not storage_key
            or storage_key != storage_key.strip()
            or "\\" in storage_key
        ):
            raise ArtifactRejectedError("artifact storage key is invalid")
        relative = Path(storage_key)
        if relative.is_absolute() or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            raise ArtifactRejectedError("artifact storage key is invalid")
        root = Path(self.composition.artifact_root).resolve()
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ArtifactRejectedError("artifact escaped configured root")
        return path

    @staticmethod
    def _file_sha256_and_size(path: Path) -> tuple[str, int]:
        digest = sha256()
        byte_size = 0
        try:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_size += len(block)
        except OSError as exc:
            raise ArtifactRejectedError("artifact cannot be read") from exc
        return digest.hexdigest(), byte_size

    def _verify_audio_binding_file(
        self, binding: Mapping[str, Any]
    ) -> dict[str, Any]:
        current = validate_audio_input_binding(binding).as_dict()
        asset = current["assetVersion"]
        validation = current["technicalValidation"]
        artifact = asset.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ArtifactRejectedError("audio artifact evidence is invalid")
        storage_key = validation.get("storageKey")
        if (
            artifact.get("storageKey") != storage_key
            or artifact.get("byteSize") != validation.get("byteSize")
            or artifact.get("fileDigest") != current["fileDigest"]
        ):
            raise StaleInputError("audio artifact binding is stale")
        path = self._composition_storage_path(storage_key)
        actual_sha, actual_size = self._file_sha256_and_size(path)
        if (
            actual_sha != current["fileDigest"]
            or actual_size != validation.get("byteSize")
        ):
            raise ArtifactRejectedError("audio artifact file digest changed")
        try:
            pcm = canonical_pcm_digest_metadata(
                path,
                expected_sample_count=current["sampleCount"],
            )
        except DigestError as exc:
            raise ArtifactRejectedError(
                "audio artifact PCM verification failed"
            ) from exc
        if (
            pcm.get("pcmContentDigest") != current["pcmContentDigest"]
            or pcm.get("pcmDigestSpec") != validation.get("pcmDigestSpec")
            or pcm.get("sampleRate") != current["sampleRate"]
            or pcm.get("sourceChannelCount") != current["channelCount"]
        ):
            raise ArtifactRejectedError("audio artifact PCM digest changed")
        final_sha, final_size = self._file_sha256_and_size(path)
        if final_sha != actual_sha or final_size != actual_size:
            raise ArtifactRejectedError(
                "audio artifact changed during verification"
            )
        return current

    def _verify_timeline_composition_artifact(
        self, result: Mapping[str, Any]
    ) -> Path:
        output_digest = result.get("outputDigest")
        output_probe = result.get("outputMediaProbe")
        if not isinstance(output_digest, Mapping) or not isinstance(
            output_probe, Mapping
        ):
            raise ArtifactRejectedError("preview artifact evidence is invalid")
        prefixed_file_digest = output_digest.get("fileDigest")
        if (
            not isinstance(prefixed_file_digest, str)
            or not prefixed_file_digest.startswith("sha256:")
            or not _is_sha256(prefixed_file_digest.removeprefix("sha256:"))
            or result.get("providerUsed") is not False
            or result.get("gpuUsed") is not False
            or result.get("publicationAllowed") is not False
        ):
            raise ArtifactRejectedError("preview artifact authority is invalid")
        path = self._composition_storage_path(result.get("outputStorageKey"))
        actual_sha, actual_size = self._file_sha256_and_size(path)
        if (
            actual_sha != prefixed_file_digest.removeprefix("sha256:")
            or actual_size != result.get("outputByteSize")
        ):
            raise ArtifactRejectedError("preview artifact file digest changed")
        try:
            observed_probe = probe_media(path)
        except ArtifactVerificationError as exc:
            raise ArtifactRejectedError("preview artifact probe failed") from exc
        observed_streams = observed_probe.get("streams")
        videos = [
            item
            for item in observed_streams or []
            if isinstance(item, Mapping) and item.get("codec_type") == "video"
        ]
        audios = [
            item
            for item in observed_streams or []
            if isinstance(item, Mapping) and item.get("codec_type") == "audio"
        ]
        if len(videos) != 1 or len(audios) != 1:
            raise ArtifactRejectedError("preview artifact streams changed")
        video = videos[0]
        audio = audios[0]
        try:
            observed_frames = int(
                video.get("nb_read_frames") or video.get("nb_frames")
            )
            rate_parts = str(video.get("avg_frame_rate")).split("/", 1)
            observed_rate = {
                "numerator": int(rate_parts[0]),
                "denominator": int(rate_parts[1]),
            }
            observed_sample_rate = int(audio.get("sample_rate"))
        except (TypeError, ValueError, IndexError, ZeroDivisionError):
            raise ArtifactRejectedError(
                "preview artifact probe cannot be normalized"
            ) from None
        format_names = str(observed_probe.get("formatName", "")).split(",")
        if (
            output_probe.get("container") not in format_names
            or video.get("codec_name") != output_probe.get("videoCodec")
            or video.get("pix_fmt") != output_probe.get("pixelFormat")
            or video.get("width") != output_probe.get("width")
            or video.get("height") != output_probe.get("height")
            or observed_frames != output_probe.get("frameCount")
            or observed_rate != output_probe.get("frameRate")
            or audio.get("codec_name") != output_probe.get("audioCodec")
            or observed_sample_rate != output_probe.get("sampleRate")
            or audio.get("channels") != output_probe.get("channelCount")
        ):
            raise ArtifactRejectedError("preview artifact probe changed")
        try:
            pixels = decoded_frame_pixel_digest_metadata(path)
            pcm = canonical_pcm_digest_metadata(
                path,
                expected_sample_count=output_digest.get("sampleCount"),
                allow_aac_frame_padding=True,
            )
        except DigestError as exc:
            raise ArtifactRejectedError(
                "preview artifact PCM verification failed"
            ) from exc
        if (
            pixels.get("fileDigest") != prefixed_file_digest
            or pixels.get("decodedFramePixelDigest")
            != output_digest.get("decodedFramePixelDigest")
            or pixels.get("decodedFramePixelDigestSpec")
            != output_digest.get("decodedFramePixelDigestSpec")
            or pixels.get("width") != output_digest.get("width")
            or pixels.get("height") != output_digest.get("height")
            or pixels.get("frameCount") != output_digest.get("frameCount")
            or pcm.get("pcmContentDigest")
            != output_digest.get("pcmContentDigest")
            or pcm.get("pcmDigestSpec") != output_digest.get("pcmDigestSpec")
            or pcm.get("sampleRate") != output_digest.get("sampleRate")
            or pcm.get("channelCount") != output_digest.get("channelCount")
            or output_probe.get("sampleCount")
            != output_digest.get("sampleCount")
            or output_probe.get("sampleRate")
            != output_digest.get("sampleRate")
            or output_probe.get("channelCount")
            != output_digest.get("channelCount")
            or output_probe.get("frameCount")
            != output_digest.get("frameCount")
            or output_probe.get("width") != output_digest.get("width")
            or output_probe.get("height") != output_digest.get("height")
            or output_probe.get("frameRate")
            != output_digest.get("frameRate")
        ):
            raise ArtifactRejectedError("preview artifact content digest changed")
        final_sha, final_size = self._file_sha256_and_size(path)
        if final_sha != actual_sha or final_size != actual_size:
            raise ArtifactRejectedError(
                "preview artifact changed during verification"
            )
        return path

    def _glyph_video_input(
        self,
        *,
        requirement: GlyphRevealRequirementV2,
        execution_request: Mapping[str, Any],
        artifact_evidence: Mapping[str, Any],
        video_facts: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        glyph_result = build_glyph_reveal_composition_result_v2(
            requirement,
            execution_request,
            artifact_evidence,
        ).as_dict()
        output_digest = artifact_evidence.get("outputDigest")
        output_probe = artifact_evidence.get("outputMediaProbe")
        if not isinstance(output_digest, Mapping) or not isinstance(
            output_probe, Mapping
        ):
            raise ArtifactRejectedError("glyph artifact evidence is invalid")
        path = self._composition_storage_path(
            artifact_evidence.get("outputStorageKey")
        )
        actual_sha, actual_size = self._file_sha256_and_size(path)
        if (
            output_digest.get("fileDigest") != f"sha256:{actual_sha}"
            or artifact_evidence.get("outputByteSize") != actual_size
            or artifact_evidence.get("provenance") != "LOCAL_EVIDENCE"
            or artifact_evidence.get("gpuUsed") is not False
            or artifact_evidence.get("publicationAllowed") is not False
            or output_probe.get("width") != video_facts["width"]
            or output_probe.get("height") != video_facts["height"]
            or output_probe.get("frameCount") != video_facts["frameCount"]
            or output_probe.get("frameRate")
            != video_facts["frameRate"]["numerator"]
        ):
            raise ArtifactRejectedError("glyph artifact file identity changed")
        projection = {
            "glyphRevealRequirementRef": requirement.requirement_ref,
            "glyphRevealRequirementDigest": requirement.payload_digest,
            "glyphRevealExecutionRequestRef": execution_request[
                "executionRequestRef"
            ],
            "glyphRevealExecutionRequestDigest": execution_request[
                "payloadDigest"
            ],
            "glyphRevealArtifactEvidenceRef": artifact_evidence[
                "artifactEvidenceRef"
            ],
            "glyphRevealArtifactEvidenceDigest": artifact_evidence[
                "payloadDigest"
            ],
            "storageKey": artifact_evidence["outputStorageKey"],
            "fileDigest": output_digest["fileDigest"],
            "decodedFramePixelDigest": output_digest[
                "decodedFramePixelDigest"
            ],
            "decodedFramePixelDigestSpec": output_digest[
                "decodedFramePixelDigestSpec"
            ],
            "codec": "h264",
            "pixelFormat": video_facts["pixelFormat"],
            "width": video_facts["width"],
            "height": video_facts["height"],
            "frameCount": video_facts["frameCount"],
            "frameRate": deepcopy(video_facts["frameRate"]),
        }
        return projection, glyph_result

    @staticmethod
    def _mask_binding_wrapper(
        *,
        workspace: str,
        run_ref: str,
        glyph_slug: str,
        ordinal: int,
        asset: Mapping[str, Any],
    ) -> Any:
        binding = build_mask_asset_version_binding(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "maskAssetVersionBindingRef": (
                    "m13-mask-binding-"
                    + _digest(
                        {"assetVersionRef": asset.get("assetVersionRef")}
                    )[:32]
                ),
                "glyphSlug": glyph_slug,
                "maskOrdinal": ordinal,
            },
            asset_version=asset,
        )
        return validate_mask_asset_version_binding(binding)

    @staticmethod
    def _timeline_input_bundle_ref(
        *,
        workspace: str,
        run_ref: str,
        binding_payloads: Sequence[Mapping[str, Any]],
        cue_payloads: Sequence[Mapping[str, Any]],
        stem_payload: Mapping[str, Any],
        requirement_payload: Mapping[str, Any],
        mask_binding_payloads: Sequence[Mapping[str, Any]],
    ) -> str:
        identity = {
            "schemaVersion": "v5.m12-m13-timeline-input-bundle-identity.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "audioInputBindings": [
                (item["audioInputBindingRef"], item["payloadDigest"])
                for item in binding_payloads
            ],
            "audioCues": [
                (item["cueVersionRef"], item["payloadDigest"])
                for item in cue_payloads
            ],
            "audioStemSet": (
                stem_payload["stemSetVersionRef"],
                stem_payload["payloadDigest"],
            ),
            "glyphRevealRequirement": (
                requirement_payload["requirementRef"],
                requirement_payload["payloadDigest"],
            ),
            "maskAssetVersions": [
                (item["assetVersionRef"], item["payloadDigest"])
                for item in mask_binding_payloads
            ],
        }
        return "timeline-input-bundle-" + _digest(identity)[:32]

    @staticmethod
    def _assert_timeline_input_ref_closure(
        bundle: Mapping[str, Any],
    ) -> None:
        """Require the registered refs to equal the exact Stem member closure."""

        bindings = bundle.get("audioInputBindings")
        cues = bundle.get("audioCues")
        members = bundle.get("audioStemMembers")
        stems = bundle.get("audioStemSet")
        if (
            not isinstance(bindings, list)
            or not isinstance(cues, list)
            or not isinstance(members, list)
            or not isinstance(stems, Mapping)
        ):
            raise StaleInputError("Timeline input closure is malformed")
        bindings_by_asset = {
            item.get("assetVersionRef"): item
            for item in bindings
            if isinstance(item, Mapping)
        }
        if len(bindings_by_asset) != len(bindings):
            raise StaleInputError("Timeline audio binding closure is ambiguous")
        expected_binding_refs: set[str] = set()
        expected_cue_refs: set[str] = set()
        member_cue_refs: list[str] = []
        for member in members:
            if not isinstance(member, Mapping):
                raise StaleInputError("Timeline Stem member closure is malformed")
            binding = bindings_by_asset.get(member.get("sourceAssetVersionRef"))
            if binding is None:
                raise StaleInputError("Timeline Stem member has no audio binding")
            expected_binding_refs.add(
                _required_ref(
                    binding.get("audioInputBindingRef"),
                    "audioInputBindingRef",
                )
            )
            cue_ref = member.get("sourceCueVersionRef")
            if cue_ref is not None:
                canonical_cue_ref = _required_ref(
                    cue_ref, "audioCueVersionRef"
                )
                expected_cue_refs.add(canonical_cue_ref)
                member_cue_refs.append(canonical_cue_ref)
        actual_binding_refs = {
            _required_ref(
                item.get("audioInputBindingRef"), "audioInputBindingRef"
            )
            for item in bindings
        }
        actual_cue_refs = {
            _required_ref(item.get("cueVersionRef"), "audioCueVersionRef")
            for item in cues
        }
        if (
            len(member_cue_refs) != len(expected_cue_refs)
            or actual_binding_refs != expected_binding_refs
            or actual_cue_refs != expected_cue_refs
            or stems.get("members") != members
        ):
            raise StaleInputError(
                "Timeline refs are not the exact AudioStemSet closure"
            )

    @staticmethod
    def _base_video_facts(asset: Mapping[str, Any]) -> dict[str, Any]:
        probe = asset.get("probe")
        streams = probe.get("streams") if isinstance(probe, Mapping) else None
        videos = [
            item
            for item in streams or []
            if isinstance(item, Mapping) and item.get("codec_type") == "video"
        ]
        if len(videos) != 1:
            raise ArtifactRejectedError("base video probe is invalid")
        stream = videos[0]
        try:
            width = int(stream["width"])
            height = int(stream["height"])
            frame_count = int(
                stream.get("nb_read_frames") or stream.get("nb_frames")
            )
            rate_parts = str(stream["avg_frame_rate"]).split("/", 1)
            rate_numerator = int(rate_parts[0])
            rate_denominator = int(rate_parts[1])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            raise ArtifactRejectedError("base video probe is invalid") from None
        if (
            width < 1
            or height < 1
            or frame_count < 1
            or rate_numerator < 1
            or rate_denominator != 1
            or stream.get("codec_name") != "h264"
            or stream.get("pix_fmt") not in {"yuv420p", "yuv422p", "yuv444p"}
        ):
            raise ArtifactRejectedError("base video profile is unsupported")
        return {
            "width": width,
            "height": height,
            "frameCount": frame_count,
            "frameRate": {
                "numerator": rate_numerator,
                "denominator": rate_denominator,
            },
            "pixelFormat": stream["pix_fmt"],
        }

    def record_m12_m13_inputs(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        idempotency_key: str,
        audio_input_bindings: Sequence[AudioInputBinding],
        audio_cues: Sequence[AudioCue],
        audio_stem_set: AudioStemSet,
        glyph_reveal_requirement: GlyphRevealRequirementV2,
        mask_assets: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Register trusted, validated M12/M13 inputs without HTTP exposure."""

        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        client_key = _idempotency_key(idempotency_key)
        if (
            not isinstance(audio_input_bindings, Sequence)
            or isinstance(audio_input_bindings, (str, bytes))
            or not audio_input_bindings
            or not isinstance(audio_cues, Sequence)
            or isinstance(audio_cues, (str, bytes))
            or not audio_cues
            or not isinstance(mask_assets, Sequence)
            or isinstance(mask_assets, (str, bytes))
            or not mask_assets
        ):
            raise ValidationFailedError(
                "M12/M13 input collections must be non-empty sequences"
            )
        if any(type(item) is not AudioInputBinding for item in audio_input_bindings):
            raise ValidationFailedError(
                "exact AudioInputBinding wrappers are required"
            )
        if any(type(item) is not AudioCue for item in audio_cues):
            raise ValidationFailedError("exact AudioCue wrappers are required")
        if type(audio_stem_set) is not AudioStemSet:
            raise ValidationFailedError("an exact AudioStemSet wrapper is required")
        if type(glyph_reveal_requirement) is not GlyphRevealRequirementV2:
            raise ValidationFailedError(
                "an exact GlyphRevealRequirementV2 wrapper is required"
            )
        if any(not isinstance(item, Mapping) for item in mask_assets):
            raise ValidationFailedError("mask AssetVersions must be server mappings")
        if any(_contains_path_authority(item) for item in mask_assets):
            raise ValidationFailedError(
                "mask AssetVersions cannot contain path authority"
            )
        if self.glyph_inspection_adapter is None:
            raise UpstreamNotReadyError(
                "server-held glyph inspection evidence is not configured"
            )

        verified = self.media.verify_media_current(workspace, run_ref)
        requirement = GlyphRevealRequirementV2.from_mapping(
            glyph_reveal_requirement.as_dict()
        )
        if (
            requirement.workspace_ref != workspace
            or requirement.production_run_ref != run_ref
        ):
            raise StaleInputError("GlyphRevealRequirementV2 scope is stale")
        base_matches = [
            item
            for item in verified["assetVersions"]
            if isinstance(item, Mapping)
            and item.get("assetVersionRef")
            == requirement.base_plate_asset_version_ref
        ]
        if len(base_matches) != 1:
            raise StaleInputError(
                "GlyphRevealRequirementV2 base plate is not current G5 media"
            )
        base_plate = deepcopy(dict(base_matches[0]))
        canonical_masks = [deepcopy(dict(item)) for item in mask_assets]
        build_glyph_reveal_execution_request_v2(
            requirement,
            base_plate_asset=base_plate,
            mask_assets=canonical_masks,
            inspection_adapter=self.glyph_inspection_adapter,
        )

        binding_payloads = [
            validate_audio_input_binding(item.as_dict()).as_dict()
            for item in audio_input_bindings
        ]
        binding_payloads.sort(key=lambda item: item["audioInputBindingRef"])
        if len({item["audioInputBindingRef"] for item in binding_payloads}) != len(
            binding_payloads
        ):
            raise ValidationFailedError("AudioInputBinding refs must be unique")
        cue_payloads = [
            _immutable_payload(item.as_dict(), "AudioCue") for item in audio_cues
        ]
        cue_payloads.sort(key=lambda item: item["cueVersionRef"])
        if len({item["cueVersionRef"] for item in cue_payloads}) != len(cue_payloads):
            raise ValidationFailedError("AudioCue version refs must be unique")
        stem_payload = _immutable_payload(audio_stem_set.as_dict(), "AudioStemSet")
        requirement_payload = _immutable_payload(
            requirement.as_dict(), "GlyphRevealRequirementV2"
        )

        mask_binding_wrappers: list[Any] = []
        mask_binding_payloads: list[dict[str, Any]] = []
        for ordinal, asset in enumerate(canonical_masks, start=1):
            wrapper = self._mask_binding_wrapper(
                workspace=workspace,
                run_ref=run_ref,
                glyph_slug=requirement.glyph_slug,
                ordinal=ordinal,
                asset=asset,
            )
            mask_binding_wrappers.append(wrapper)
            mask_binding_payloads.append(wrapper.as_dict())
        if [
            item["assetVersionRef"] for item in mask_binding_payloads
        ] != list(requirement.mask_asset_version_refs):
            raise StaleInputError("mask AssetVersion order is stale")

        bundle_ref = self._timeline_input_bundle_ref(
            workspace=workspace,
            run_ref=run_ref,
            binding_payloads=binding_payloads,
            cue_payloads=cue_payloads,
            stem_payload=stem_payload,
            requirement_payload=requirement_payload,
            mask_binding_payloads=mask_binding_payloads,
        )
        input_bundle = validate_timeline_input_bundle(
            build_timeline_input_bundle(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "timelineInputBundleRef": bundle_ref,
                    "scriptVersionRef": stem_payload["scriptVersionRef"],
                    "scriptVersionDigest": stem_payload["scriptVersionDigest"],
                },
                audio_input_bindings=audio_input_bindings,
                audio_cues=audio_cues,
                audio_stem_set=audio_stem_set,
                audio_stem_members=tuple(stem_payload["members"]),
                glyph_reveal_requirements=(glyph_reveal_requirement,),
                mask_asset_bindings=mask_binding_wrappers,
            )
        ).as_dict()
        self._assert_timeline_input_ref_closure(input_bundle)

        batch_members = [
            {
                "recordKind": "AudioInputBinding",
                "recordRef": item["audioInputBindingRef"],
                "recordVersion": 1,
                "payloadDigest": item["payloadDigest"],
            }
            for item in binding_payloads
        ] + [
            {
                "recordKind": "AudioCue",
                "recordRef": item["cueVersionRef"],
                "recordVersion": item["version"],
                "payloadDigest": item["payloadDigest"],
            }
            for item in cue_payloads
        ] + [
            {
                "recordKind": "AudioStemSet",
                "recordRef": stem_payload["stemSetVersionRef"],
                "recordVersion": stem_payload["version"],
                "payloadDigest": stem_payload["payloadDigest"],
            },
            {
                "recordKind": "GlyphRevealRequirement",
                "recordRef": requirement.requirement_ref,
                "recordVersion": 2,
                "payloadDigest": requirement.payload_digest,
            },
        ] + [
            {
                "recordKind": "MaskAssetVersion",
                "recordRef": item["assetVersionRef"],
                "recordVersion": _positive_version(
                    asset.get("version", 1), "mask AssetVersion version"
                ),
                "payloadDigest": asset["payloadDigest"],
            }
            for item, asset in zip(mask_binding_payloads, canonical_masks)
        ]
        batch_digest = _digest(
            {
                "schemaVersion": "v5.m12-m13-input-batch.v1",
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "timelineInputBundleRef": input_bundle[
                    "timelineInputBundleRef"
                ],
                "timelineInputBundleDigest": input_bundle["payloadDigest"],
                "members": batch_members,
            }
        )
        now = self._clock()
        records: list[EvidenceRecord] = []
        for index, item in enumerate(binding_payloads):
            records.append(
                self._input_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="AudioInputBinding",
                    record_ref=item["audioInputBindingRef"],
                    record_version=1,
                    client_key=client_key,
                    slot=f"audio-input-binding:{index}",
                    batch_digest=batch_digest,
                    created_at=now,
                    payload=item,
                )
            )
        for index, item in enumerate(cue_payloads):
            records.append(
                self._input_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="AudioCue",
                    record_ref=item["cueVersionRef"],
                    record_version=item["version"],
                    client_key=client_key,
                    slot=f"audio-cue:{index}",
                    batch_digest=batch_digest,
                    created_at=now,
                    payload=item,
                )
            )
        records.extend(
            (
                self._input_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="AudioStemSet",
                    record_ref=stem_payload["stemSetVersionRef"],
                    record_version=stem_payload["version"],
                    client_key=client_key,
                    slot="audio-stem-set",
                    batch_digest=batch_digest,
                    created_at=now,
                    payload=stem_payload,
                ),
                self._input_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="GlyphRevealRequirement",
                    record_ref=requirement.requirement_ref,
                    record_version=2,
                    client_key=client_key,
                    slot="glyph-reveal-requirement",
                    batch_digest=batch_digest,
                    created_at=now,
                    payload=requirement_payload,
                ),
            )
        )
        for index, asset in enumerate(canonical_masks):
            records.append(
                self._input_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="MaskAssetVersion",
                    record_ref=asset["assetVersionRef"],
                    record_version=_positive_version(
                        asset.get("version", 1), "mask AssetVersion version"
                    ),
                    client_key=client_key,
                    slot=f"mask-asset-version:{index}",
                    batch_digest=batch_digest,
                    created_at=now,
                    payload=asset,
                )
            )

        snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        existing = [
            self.evidence.get_record_by_idempotency_key(
                workspace, run_ref, item.idempotencyKey
            )
            for item in records
        ]
        if snapshot.currentState != "MEDIA_READY" and not all(existing):
            raise UpstreamNotReadyError(
                "M12/M13 inputs can only be registered from MEDIA_READY"
            )
        journal_head = self._stable_record_head(
            workspace, run_ref, snapshot.revisionToken
        )
        stored, replayed = self.evidence.append_records(
            records,
            expected_record_journal_head=journal_head,
        )
        result_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        return {
            "inputBundleDigest": input_bundle["payloadDigest"],
            "inputBatchDigest": batch_digest,
            "recordRefs": [
                {
                    "recordKind": item["recordKind"],
                    "recordRef": item["recordRef"],
                    "recordVersion": item["recordVersion"],
                    "payloadDigest": item["payloadDigest"],
                }
                for item in stored
            ],
            "evidenceRevision": result_snapshot.revisionToken,
            "idempotentReplay": replayed,
        }

    @staticmethod
    def _timeline_preview_command(
        command: Mapping[str, Any],
    ) -> dict[str, Any]:
        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "expectedEvidenceRevision",
            "timelineInputRefs",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M12/M13 preview contract"
            )
        references = command.get("timelineInputRefs")
        reference_fields = {
            "videoAssetVersionRef",
            "audioInputBindingRefs",
            "audioCueVersionRefs",
            "audioStemSetVersionRef",
            "glyphRevealRequirementRef",
        }
        if not isinstance(references, Mapping) or set(references) != reference_fields:
            raise EpisodeProductionError("timelineInputRefs fields are invalid")
        normalized: dict[str, Any] = {
            "workspaceRef": _required_ref(command.get("workspaceRef"), "workspaceRef"),
            "productionRunRef": _required_ref(
                command.get("productionRunRef"), "productionRunRef"
            ),
            "operationRef": _required_ref(command.get("operationRef"), "operationRef"),
            "idempotencyKey": _idempotency_key(command.get("idempotencyKey")),
            "expectedRunVersion": _positive_version(
                command.get("expectedRunVersion"), "expectedRunVersion"
            ),
            "expectedEvidenceRevision": command.get("expectedEvidenceRevision"),
            "timelineInputRefs": {
                "videoAssetVersionRef": _required_ref(
                    references.get("videoAssetVersionRef"),
                    "videoAssetVersionRef",
                ),
                "audioStemSetVersionRef": _required_ref(
                    references.get("audioStemSetVersionRef"),
                    "audioStemSetVersionRef",
                ),
                "glyphRevealRequirementRef": _required_ref(
                    references.get("glyphRevealRequirementRef"),
                    "glyphRevealRequirementRef",
                ),
            },
        }
        if not _is_sha256(normalized["expectedEvidenceRevision"]):
            raise EpisodeProductionError("expectedEvidenceRevision is invalid")
        for field in ("audioInputBindingRefs", "audioCueVersionRefs"):
            values = references.get(field)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(item, str) for item in values)
            ):
                raise EpisodeProductionError(f"{field} is invalid")
            canonical = [_required_ref(item, field) for item in values]
            if canonical != sorted(set(canonical)):
                raise EpisodeProductionError(f"{field} must be unique and canonical")
            normalized["timelineInputRefs"][field] = canonical
        return normalized

    def _resolve_registered_timeline_inputs(
        self,
        *,
        workspace: str,
        run_ref: str,
        references: Mapping[str, Any],
        snapshot: Any,
        verified_media: Mapping[str, Any],
    ) -> dict[str, Any]:
        binding_payloads = [
            self._snapshot_record_payload(
                snapshot,
                record_kind="AudioInputBinding",
                record_ref=reference,
            )
            for reference in references["audioInputBindingRefs"]
        ]
        binding_wrappers = [
            validate_audio_input_binding(item) for item in binding_payloads
        ]
        cue_payloads = [
            self._snapshot_record_payload(
                snapshot,
                record_kind="AudioCue",
                record_ref=reference,
            )
            for reference in references["audioCueVersionRefs"]
        ]
        stem_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="AudioStemSet",
            record_ref=references["audioStemSetVersionRef"],
        )
        requirement_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="GlyphRevealRequirement",
            record_ref=references["glyphRevealRequirementRef"],
        )
        requirement = GlyphRevealRequirementV2.from_mapping(requirement_payload)
        if (
            references["videoAssetVersionRef"]
            != requirement.base_plate_asset_version_ref
        ):
            raise StaleInputError("Timeline video and glyph base plate differ")
        base_matches = [
            item
            for item in verified_media["assetVersions"]
            if isinstance(item, Mapping)
            and item.get("assetVersionRef")
            == references["videoAssetVersionRef"]
        ]
        if len(base_matches) != 1:
            raise StaleInputError("Timeline video AssetVersion is not current")
        base_plate = deepcopy(dict(base_matches[0]))
        mask_assets = [
            self._snapshot_record_payload(
                snapshot,
                record_kind="MaskAssetVersion",
                record_ref=reference,
            )
            for reference in requirement.mask_asset_version_refs
        ]
        if any(_contains_path_authority(item) for item in mask_assets):
            raise RepositoryUnavailableError(
                "stored mask AssetVersion contains path authority"
            )
        mask_wrappers = [
            self._mask_binding_wrapper(
                workspace=workspace,
                run_ref=run_ref,
                glyph_slug=requirement.glyph_slug,
                ordinal=ordinal,
                asset=asset,
            )
            for ordinal, asset in enumerate(mask_assets, start=1)
        ]
        mask_payloads = [item.as_dict() for item in mask_wrappers]
        bundle_ref = self._timeline_input_bundle_ref(
            workspace=workspace,
            run_ref=run_ref,
            binding_payloads=binding_payloads,
            cue_payloads=cue_payloads,
            stem_payload=stem_payload,
            requirement_payload=requirement_payload,
            mask_binding_payloads=mask_payloads,
        )
        bundle = validate_timeline_input_bundle(
            build_timeline_input_bundle(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "timelineInputBundleRef": bundle_ref,
                    "scriptVersionRef": stem_payload["scriptVersionRef"],
                    "scriptVersionDigest": stem_payload["scriptVersionDigest"],
                },
                audio_input_bindings=binding_wrappers,
                audio_cues=cue_payloads,
                audio_stem_set=stem_payload,
                audio_stem_members=tuple(stem_payload["members"]),
                glyph_reveal_requirements=(requirement,),
                mask_asset_bindings=mask_wrappers,
            )
        ).as_dict()
        self._assert_timeline_input_ref_closure(bundle)
        if (
            [
                item["audioInputBindingRef"]
                for item in bundle["audioInputBindings"]
            ]
            != list(references["audioInputBindingRefs"])
            or [item["cueVersionRef"] for item in bundle["audioCues"]]
            != list(references["audioCueVersionRefs"])
            or bundle["audioStemSet"]["stemSetVersionRef"]
            != references["audioStemSetVersionRef"]
        ):
            raise StaleInputError("Timeline input refs are not canonical")
        verified_bindings = [
            self._verify_audio_binding_file(item)
            for item in bundle["audioInputBindings"]
        ]
        return {
            "bundle": bundle,
            "audioInputBindings": verified_bindings,
            "audioCues": deepcopy(bundle["audioCues"]),
            "audioStemSet": deepcopy(bundle["audioStemSet"]),
            "audioStemMembers": deepcopy(bundle["audioStemMembers"]),
            "glyphRevealRequirement": requirement,
            "basePlateAssetVersion": base_plate,
            "maskAssetVersions": mask_assets,
            "maskAssetVersionBindings": mask_payloads,
        }

    def _build_timeline_projection(
        self,
        *,
        command: Mapping[str, Any],
        run: Mapping[str, Any],
        inputs: Mapping[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        workspace = command["workspaceRef"]
        run_ref = command["productionRunRef"]
        base = inputs["basePlateAssetVersion"]
        bundle = validate_timeline_input_bundle(inputs["bundle"])
        bundle_payload = bundle.as_dict()
        video_facts = self._base_video_facts(base)
        identity = {
            "schemaVersion": "v5.m13-timeline-identity.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "operationRef": command["operationRef"],
            "timelineInputBundleDigest": bundle_payload["payloadDigest"],
            "videoAssetVersionRef": base["assetVersionRef"],
            "videoAssetVersionDigest": base["payloadDigest"],
        }
        timeline_ref = "m13-timeline-" + _digest(identity)[:32]
        timeline = validate_timeline(
            build_timeline(
                {
                    "workspaceRef": workspace,
                    "projectRef": run["projectRef"],
                    "seriesRef": run["seriesRef"],
                    "episodeRef": run["episodeRef"],
                    "productionRunRef": run_ref,
                    "timelineRef": timeline_ref,
                    "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                    "createdAt": created_at,
                }
            )
        )
        frame_rate = video_facts["frameRate"]
        duration_frames = video_facts["frameCount"]
        track_refs = {
            kind: f"{timeline_ref}-track-{kind.lower()}"
            for kind in ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
        }

        def clip_ref(kind: str, source_ref: str) -> str:
            return "m13-timeline-clip-" + _digest(
                {
                    "timelineRef": timeline_ref,
                    "trackKind": kind,
                    "sourceRef": source_ref,
                }
            )[:32]

        clip_payloads: dict[str, list[Any]] = {
            "VIDEO": [],
            "AUDIO": [],
            "SUBTITLE": [],
            "EFFECT": [],
        }
        video_clip_mapping = build_timeline_clip(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "timelineClipRef": clip_ref("VIDEO", base["assetVersionRef"]),
                "timelineTrackRef": track_refs["VIDEO"],
                "trackKind": "VIDEO",
                "timelineStartFrame": 0,
                "timelineEndFrameExclusive": duration_frames,
                "sourceBinding": {
                    "creativeShotRef": base["creativeShotRef"],
                    "assetVersionRef": base["assetVersionRef"],
                    "assetVersionDigest": base["payloadDigest"],
                    "storageKey": base["storageKey"],
                    "fileDigest": f"sha256:{base['sha256']}",
                    "sourceStartFrame": 0,
                    "sourceEndFrameExclusive": duration_frames,
                },
            },
            timeline_input_bundle=bundle,
            frame_rate=frame_rate,
            duration_frames=duration_frames,
        )
        clip_payloads["VIDEO"].append(
            validate_timeline_clip(
                video_clip_mapping,
                timeline_input_bundle=bundle,
                frame_rate=frame_rate,
                duration_frames=duration_frames,
            )
        )

        bindings_by_asset = {
            item["assetVersionRef"]: item
            for item in bundle_payload["audioInputBindings"]
        }
        members_by_cue = {
            item["sourceCueVersionRef"]: item
            for item in bundle_payload["audioStemMembers"]
            if item["sourceCueVersionRef"] is not None
        }
        for member in bundle_payload["audioStemMembers"]:
            binding = bindings_by_asset.get(member["sourceAssetVersionRef"])
            if binding is None:
                raise StaleInputError("Timeline AUDIO member binding is stale")
            start_frame = map_sample_boundary_to_frame(
                member["stemStartSample"],
                sample_rate=binding["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
            end_frame = map_sample_boundary_to_frame(
                member["stemEndSample"],
                sample_rate=binding["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
            audio_mapping = build_timeline_clip(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "timelineClipRef": clip_ref(
                        "AUDIO", member["stemMemberRef"]
                    ),
                    "timelineTrackRef": track_refs["AUDIO"],
                    "trackKind": "AUDIO",
                    "timelineStartFrame": start_frame,
                    "timelineEndFrameExclusive": end_frame,
                    "sourceBinding": {
                        "audioInputBindingRef": binding[
                            "audioInputBindingRef"
                        ],
                        "stemMemberRef": member["stemMemberRef"],
                        "gainDb": 0,
                        "fadeInSamples": 0,
                        "fadeOutSamples": 0,
                    },
                },
                timeline_input_bundle=bundle,
                frame_rate=frame_rate,
                duration_frames=duration_frames,
            )
            clip_payloads["AUDIO"].append(
                validate_timeline_clip(
                    audio_mapping,
                    timeline_input_bundle=bundle,
                    frame_rate=frame_rate,
                    duration_frames=duration_frames,
                )
            )

        for cue in bundle_payload["audioCues"]:
            subtitle = cue.get("subtitleTimingReference")
            if not isinstance(subtitle, Mapping):
                continue
            member = members_by_cue.get(cue["cueVersionRef"])
            if member is None:
                raise StaleInputError("Timeline SUBTITLE member binding is stale")
            binding = bindings_by_asset.get(member["sourceAssetVersionRef"])
            if binding is None:
                raise StaleInputError("Timeline SUBTITLE audio binding is stale")
            start_frame = map_sample_boundary_to_frame(
                member["stemStartSample"],
                sample_rate=binding["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
            end_frame = map_sample_boundary_to_frame(
                member["stemEndSample"],
                sample_rate=binding["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
            subtitle_mapping = build_timeline_clip(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "timelineClipRef": clip_ref(
                        "SUBTITLE", cue["cueVersionRef"]
                    ),
                    "timelineTrackRef": track_refs["SUBTITLE"],
                    "trackKind": "SUBTITLE",
                    "timelineStartFrame": start_frame,
                    "timelineEndFrameExclusive": end_frame,
                    "sourceBinding": {
                        "audioCueVersionRef": cue["cueVersionRef"],
                        "stemMemberRef": member["stemMemberRef"],
                        "language": subtitle["language"],
                    },
                },
                timeline_input_bundle=bundle,
                frame_rate=frame_rate,
                duration_frames=duration_frames,
            )
            clip_payloads["SUBTITLE"].append(
                validate_timeline_clip(
                    subtitle_mapping,
                    timeline_input_bundle=bundle,
                    frame_rate=frame_rate,
                    duration_frames=duration_frames,
                )
            )
        if not clip_payloads["SUBTITLE"]:
            raise UpstreamNotReadyError(
                "the minimal Timeline requires one subtitle Cue"
            )

        requirement = inputs["glyphRevealRequirement"]
        effect_mapping = build_timeline_clip(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "timelineClipRef": clip_ref(
                    "EFFECT", requirement.requirement_ref
                ),
                "timelineTrackRef": track_refs["EFFECT"],
                "trackKind": "EFFECT",
                "timelineStartFrame": (
                    requirement.frame_range_start_inclusive
                ),
                "timelineEndFrameExclusive": (
                    requirement.frame_range_end_exclusive
                ),
                "sourceBinding": {
                    "glyphRevealRequirementRef": requirement.requirement_ref
                },
            },
            timeline_input_bundle=bundle,
            frame_rate=frame_rate,
            duration_frames=duration_frames,
        )
        clip_payloads["EFFECT"].append(
            validate_timeline_clip(
                effect_mapping,
                timeline_input_bundle=bundle,
                frame_rate=frame_rate,
                duration_frames=duration_frames,
            )
        )

        tracks: list[Any] = []
        for ordinal, kind in enumerate(
            ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
        ):
            mapping = build_timeline_track(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "timelineTrackRef": track_refs[kind],
                    "trackKind": kind,
                    "ordinal": ordinal,
                },
                clips=clip_payloads[kind],
                timeline_input_bundle=bundle,
                frame_rate=frame_rate,
                duration_frames=duration_frames,
            )
            tracks.append(
                validate_timeline_track(
                    mapping,
                    timeline_input_bundle=bundle,
                    frame_rate=frame_rate,
                    duration_frames=duration_frames,
                )
            )
        timeline_version_ref = "m13-timeline-version-" + _digest(
            {
                "timelineRef": timeline_ref,
                "timelineDigest": timeline.as_dict()["payloadDigest"],
                "timelineInputBundleDigest": bundle_payload["payloadDigest"],
                "trackDigests": [
                    item.as_dict()["payloadDigest"] for item in tracks
                ],
            }
        )[:32]
        timeline_version_mapping = build_timeline_version(
            {
                "workspaceRef": workspace,
                "projectRef": run["projectRef"],
                "seriesRef": run["seriesRef"],
                "episodeRef": run["episodeRef"],
                "productionRunRef": run_ref,
                "timelineVersionRef": timeline_version_ref,
                "version": 1,
                "supersedesTimelineVersionRef": None,
                "supersedesTimelineVersionDigest": None,
                "scriptVersionRef": bundle_payload["scriptVersionRef"],
                "scriptVersionDigest": bundle_payload["scriptVersionDigest"],
                "frameRate": frame_rate,
                "width": video_facts["width"],
                "height": video_facts["height"],
                "pixelFormat": video_facts["pixelFormat"],
                "durationFrames": duration_frames,
                "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                "createdAt": created_at,
            },
            timeline=timeline,
            tracks=tracks,
            timeline_input_bundle=bundle,
        )
        timeline_version = validate_timeline_version(
            timeline_version_mapping,
            timeline=timeline,
            timeline_input_bundle=bundle,
        )
        version_payload = timeline_version.as_dict()
        subtitle_manifest = validate_subtitle_manifest(
            build_subtitle_manifest(
                {
                    "subtitleManifestRef": (
                        "m13-subtitle-manifest-"
                        + _digest(
                            {
                                "timelineVersionRef": version_payload[
                                    "timelineVersionRef"
                                ],
                                "timelineVersionDigest": version_payload[
                                    "payloadDigest"
                                ],
                            }
                        )[:32]
                    ),
                    "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                    "createdAt": created_at,
                },
                timeline_version=timeline_version,
            ),
            timeline_version=timeline_version,
        )
        mix_request = validate_timeline_mix_request(
            build_timeline_mix_request(
                {
                    "mixRequestRef": (
                        "m13-timeline-mix-"
                        + _digest(
                            {
                                "timelineVersionRef": version_payload[
                                    "timelineVersionRef"
                                ],
                                "timelineVersionDigest": version_payload[
                                    "payloadDigest"
                                ],
                                "stemSetVersionRef": bundle_payload[
                                    "audioStemSet"
                                ]["stemSetVersionRef"],
                                "stemSetDigest": bundle_payload[
                                    "audioStemSet"
                                ]["payloadDigest"],
                            }
                        )[:32]
                    ),
                    "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                    "createdAt": created_at,
                },
                timeline_version=timeline_version,
                timeline_input_bundle=bundle,
            ),
            timeline_version=timeline_version,
            timeline_input_bundle=bundle,
        )
        return {
            "timeline": timeline,
            "timelineVersion": timeline_version,
            "timelineInputBundle": bundle,
            "subtitleManifest": subtitle_manifest,
            "timelineMixRequest": mix_request,
            "audioMixProjection": project_timeline_mix_request(mix_request),
            "tracks": tracks,
            "clips": clip_payloads,
            "videoFacts": video_facts,
        }

    def _validated_stored_timeline_preview(
        self,
        *,
        command: Mapping[str, Any],
        composition_gate: Mapping[str, Any],
        snapshot: Any,
        verified_media: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Rebuild authority wrappers from append-only evidence, then pin bytes."""

        workspace = command["workspaceRef"]
        run_ref = command["productionRunRef"]
        inputs = self._resolve_registered_timeline_inputs(
            workspace=workspace,
            run_ref=run_ref,
            references=command["timelineInputRefs"],
            snapshot=snapshot,
            verified_media=verified_media,
        )
        timeline_fact = _immutable_payload(
            _fact(composition_gate, "TimelineVersion"), "TimelineVersion"
        )
        preview_fact = _immutable_payload(
            _fact(composition_gate, "PreviewCandidate"), "PreviewCandidate"
        )
        if (
            timeline_fact.get("schemaVersion")
            != TIMELINE_VERSION_SCHEMA_VERSION_V2
            or preview_fact.get("schemaVersion")
            != PREVIEW_CANDIDATE_SCHEMA_VERSION_V2
        ):
            raise StaleInputError("stored preview does not use the M12/M13 contract")

        timeline_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="Timeline",
            record_ref=_required_ref(
                timeline_fact.get("timelineRef"), "timelineRef"
            ),
        )
        timeline_version_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="TimelineVersion",
            record_ref=_required_ref(
                timeline_fact.get("timelineVersionRef"), "timelineVersionRef"
            ),
        )
        subtitle_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="SubtitleManifest",
            record_ref=_required_ref(
                preview_fact.get("subtitleManifestRef"),
                "subtitleManifestRef",
            ),
        )
        composition_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="CompositionResult",
            record_ref=_required_ref(
                preview_fact.get("compositionResultRef"),
                "compositionResultRef",
            ),
        )
        mix_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="TimelineMixRequest",
            record_ref=_required_ref(
                composition_payload.get("mixRequestRef"), "mixRequestRef"
            ),
        )
        preview_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="PreviewCandidate",
            record_ref=_required_ref(
                preview_fact.get("previewCandidateVersionRef"),
                "previewCandidateVersionRef",
            ),
        )
        if (
            timeline_version_payload != timeline_fact
            or preview_payload != preview_fact
            or composition_payload.get("schemaVersion")
            != COMPOSITION_RESULT_SCHEMA_VERSION
        ):
            raise RepositoryUnavailableError(
                "G6 facts and append-only preview records differ"
            )

        timeline = validate_timeline(timeline_payload)
        timeline_version = validate_timeline_version(
            timeline_version_payload,
            timeline=timeline,
            timeline_input_bundle=inputs["bundle"],
        )
        subtitle_manifest = validate_subtitle_manifest(
            subtitle_payload,
            timeline_version=timeline_version,
        )
        mix_request = validate_timeline_mix_request(
            mix_payload,
            timeline_version=timeline_version,
            timeline_input_bundle=inputs["bundle"],
        )
        if mix_request.as_dict()["payloadDigest"] != composition_payload.get(
            "mixRequestDigest"
        ):
            raise StaleInputError("TimelineMixRequest record lineage is stale")
        composition_result = validate_composition_result(
            composition_payload,
            timeline_version=timeline_version,
            timeline_mix_request=mix_request,
            subtitle_manifest=subtitle_manifest,
        )
        preview_candidate = validate_preview_candidate(
            preview_payload,
            timeline_version=timeline_version,
            timeline_mix_request=mix_request,
            subtitle_manifest=subtitle_manifest,
            composition_result=composition_result,
        )
        artifact_path = self._verify_timeline_composition_artifact(
            composition_result.as_dict()
        )
        return {
            "inputs": inputs,
            "timeline": timeline,
            "timelineVersion": timeline_version,
            "subtitleManifest": subtitle_manifest,
            "timelineMixRequest": mix_request,
            "compositionResult": composition_result,
            "previewCandidate": preview_candidate,
            "artifactPath": artifact_path,
        }

    def _timeline_input_refs_from_version(
        self,
        snapshot: Any,
        timeline_version: Mapping[str, Any],
        timeline_mix_request: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Recover the closed input-ref envelope from a validated v2 graph."""

        version = _immutable_payload(timeline_version, "TimelineVersion")
        mix = _immutable_payload(timeline_mix_request, "TimelineMixRequest")
        if (
            mix.get("timelineVersionRef") != version.get("timelineVersionRef")
            or mix.get("timelineVersionDigest") != version.get("payloadDigest")
        ):
            raise StaleInputError("TimelineMixRequest version lineage is stale")
        tracks = timeline_version.get("tracks")
        if not isinstance(tracks, list):
            raise RepositoryUnavailableError("TimelineVersion tracks are invalid")
        by_kind = {
            item.get("trackKind"): item
            for item in tracks
            if isinstance(item, Mapping)
        }
        if set(by_kind) != {"VIDEO", "AUDIO", "SUBTITLE", "EFFECT"}:
            raise RepositoryUnavailableError("TimelineVersion tracks are incomplete")

        def sources(kind: str) -> list[Mapping[str, Any]]:
            clips = by_kind[kind].get("clips")
            if not isinstance(clips, list):
                raise RepositoryUnavailableError(
                    f"TimelineVersion {kind} clips are invalid"
                )
            values = [
                item.get("sourceBinding")
                for item in clips
                if isinstance(item, Mapping)
                and isinstance(item.get("sourceBinding"), Mapping)
            ]
            if len(values) != len(clips):
                raise RepositoryUnavailableError(
                    f"TimelineVersion {kind} sources are invalid"
                )
            return values

        videos = sources("VIDEO")
        audios = sources("AUDIO")
        subtitles = sources("SUBTITLE")
        effects = sources("EFFECT")
        if len(videos) != 1 or not audios or not subtitles or len(effects) != 1:
            raise RepositoryUnavailableError(
                "minimal TimelineVersion source coverage is invalid"
            )
        audio_binding_refs = sorted(
            {
                _required_ref(
                    item.get("audioInputBindingRef"),
                    "audioInputBindingRef",
                )
                for item in audios
            }
        )
        stem_member_refs = sorted(
            {
                _required_ref(item.get("stemMemberRef"), "stemMemberRef")
                for item in audios
            }
        )
        stem_set = self._snapshot_record_payload(
            snapshot,
            record_kind="AudioStemSet",
            record_ref=_required_ref(
                mix.get("stemSetVersionRef"), "audioStemSetVersionRef"
            ),
        )
        if stem_set.get("payloadDigest") != mix.get("stemSetDigest"):
            raise StaleInputError("TimelineMixRequest StemSet lineage is stale")
        members = stem_set.get("members")
        if not isinstance(members, list):
            raise RepositoryUnavailableError("AudioStemSet members are invalid")
        members_by_ref = {
            item.get("stemMemberRef"): item
            for item in members
            if isinstance(item, Mapping)
        }
        if (
            len(members_by_ref) != len(members)
            or sorted(members_by_ref) != stem_member_refs
        ):
            raise StaleInputError("Timeline AudioStemSet member closure is stale")
        audio_by_member = {
            item.get("stemMemberRef"): item for item in audios
        }
        if len(audio_by_member) != len(audios) or any(
            audio_by_member[member_ref].get("stemMemberDigest")
            != member.get("payloadDigest")
            for member_ref, member in members_by_ref.items()
        ):
            raise StaleInputError("Timeline Stem member projection is stale")
        mix_clips = mix.get("clips")
        if not isinstance(mix_clips, list) or sorted(
            item.get("stemMemberRef")
            for item in mix_clips
            if isinstance(item, Mapping)
        ) != stem_member_refs:
            raise StaleInputError("Timeline mix Stem member closure is stale")
        cue_refs = sorted(
            {
                _required_ref(item.get("sourceCueVersionRef"), "audioCueVersionRef")
                for item in members
                if item.get("sourceCueVersionRef") is not None
            }
        )
        subtitle_cue_refs = {
            _required_ref(
                item.get("audioCueVersionRef"), "audioCueVersionRef"
            )
            for item in subtitles
        }
        if not subtitle_cue_refs.issubset(set(cue_refs)):
            raise StaleInputError("Timeline subtitle Cue closure is stale")
        return {
            "videoAssetVersionRef": _required_ref(
                videos[0].get("assetVersionRef"), "videoAssetVersionRef"
            ),
            "audioInputBindingRefs": audio_binding_refs,
            "audioCueVersionRefs": cue_refs,
            "audioStemSetVersionRef": _required_ref(
                stem_set.get("stemSetVersionRef"),
                "audioStemSetVersionRef",
            ),
            "glyphRevealRequirementRef": _required_ref(
                effects[0].get("glyphRevealRequirementRef"),
                "glyphRevealRequirementRef",
            ),
        }

    @staticmethod
    def _timeline_preview_qc_checks(
        *,
        timeline_version: Mapping[str, Any],
        composition_result: Mapping[str, Any],
        subtitle_manifest: Mapping[str, Any],
        timeline_input_bundle: Mapping[str, Any],
        glyph_requirement: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "checkId": "artifact-file-pixel-pcm-and-probe",
                "status": "PASSED",
                "evidence": composition_result["payloadDigest"],
            },
            {
                "checkId": "timeline-source-lineage",
                "status": "PASSED",
                "evidence": timeline_version["payloadDigest"],
            },
            {
                "checkId": "typed-audio-and-technical-validation",
                "status": "PASSED",
                "evidence": timeline_input_bundle["payloadDigest"],
            },
            {
                "checkId": "subtitle-cue-time-reference",
                "status": "PASSED",
                "evidence": subtitle_manifest["payloadDigest"],
            },
            {
                "checkId": "glyph-effect-binding",
                "status": "PASSED",
                "evidence": glyph_requirement["payloadDigest"],
            },
            {
                "checkId": "local-evidence-publication-lock",
                "status": "PASSED",
                "evidence": composition_result["provenance"],
            },
        ]

    @staticmethod
    def _timeline_preview_qc_ref(
        preview_candidate: Mapping[str, Any],
    ) -> str:
        return "m13-qc-report-" + _digest(
            {
                "previewCandidateDigest": preview_candidate["payloadDigest"],
                "qcProfile": "k2.m12-m13.machine-verifiable.v1",
            }
        )[:32]

    def _validated_m12_m13_qc(
        self,
        value: Any,
        *,
        workspace: str,
        run_ref: str,
        timeline_version: Mapping[str, Any],
        preview_candidate: Mapping[str, Any],
        composition_result: Mapping[str, Any],
        subtitle_manifest: Mapping[str, Any],
        timeline_input_bundle: Mapping[str, Any],
        glyph_requirement: Mapping[str, Any],
    ) -> dict[str, Any]:
        qc = _immutable_payload(value, "M12/M13 QCReport")
        fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "qcReportRef",
            "version",
            "previewCandidateRef",
            "previewCandidateVersionRef",
            "previewCandidateDigest",
            "timelineVersionRef",
            "timelineDigest",
            "checks",
            "result",
            "approvalStatus",
            "machineVerified",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        expected_checks = self._timeline_preview_qc_checks(
            timeline_version=timeline_version,
            composition_result=composition_result,
            subtitle_manifest=subtitle_manifest,
            timeline_input_bundle=timeline_input_bundle,
            glyph_requirement=glyph_requirement,
        )
        if (
            set(qc) != fields
            or qc.get("schemaVersion") != QC_SCHEMA_VERSION
            or qc.get("workspaceRef") != workspace
            or qc.get("productionRunRef") != run_ref
            or qc.get("qcReportRef")
            != self._timeline_preview_qc_ref(preview_candidate)
            or qc.get("version") != 1
            or qc.get("previewCandidateRef")
            != preview_candidate.get("previewCandidateRef")
            or qc.get("previewCandidateVersionRef")
            != preview_candidate.get("previewCandidateVersionRef")
            or qc.get("previewCandidateDigest")
            != preview_candidate.get("payloadDigest")
            or qc.get("timelineVersionRef")
            != timeline_version.get("timelineVersionRef")
            or qc.get("timelineDigest")
            != timeline_version.get("payloadDigest")
            or qc.get("checks") != expected_checks
            or qc.get("result") != "PASS"
            or qc.get("approvalStatus") != "UNAPPROVED"
            or qc.get("machineVerified") is not True
            or qc.get("publicationAllowed") is not False
            or qc.get("createdBy") != TIMELINE_PREVIEW_DELIVERY_ID
            or not _is_timestamp(qc.get("createdAt"))
            or qc.get("createdAt") != composition_result.get("createdAt")
        ):
            raise StaleInputError("M12/M13 preview QC evidence is stale")
        return qc

    def compose_timeline_preview(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Compose the closed M12/M13 preview slice and stop at ``QC_READY``."""

        normalized = self._timeline_preview_command(command)
        workspace = normalized["workspaceRef"]
        run_ref = normalized["productionRunRef"]
        run = self.media.assets.shot_graph.root_service.get_run(
            workspace, run_ref
        )
        if run.get("version") != normalized["expectedRunVersion"]:
            raise StaleInputError("EpisodeProductionRun version changed")
        if self.composition is None:
            raise WorkerUnavailableError("composition execution is not configured")

        client_key = normalized["idempotencyKey"]
        operation_ref = normalized["operationRef"]
        composition_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "operationRef": operation_ref,
                "stage": "m12-m13-timeline-composition",
            }
        )
        composition_request_digest = _digest(
            {
                "schemaVersion": "v5.m12-m13-preview-command.v1",
                "command": normalized,
                "deliveryId": TIMELINE_PREVIEW_DELIVERY_ID,
            }
        )
        composition_gate = self._existing(
            workspace,
            run_ref,
            COMPOSITION_GATE,
            composition_key,
            composition_request_digest,
        )
        composition_replay = composition_gate is not None
        verified_media = self.media.verify_media_current(workspace, run_ref)

        if composition_gate is not None:
            snapshot = validated_evidence_snapshot(
                self.evidence.read_snapshot(workspace, run_ref),
                workspace_ref=workspace,
                run_ref=run_ref,
            )
            stored = self._validated_stored_timeline_preview(
                command=normalized,
                composition_gate=composition_gate,
                snapshot=snapshot,
                verified_media=verified_media,
            )
            timeline = stored["timeline"]
            timeline_version = stored["timelineVersion"]
            subtitle_manifest = stored["subtitleManifest"]
            mix_request = stored["timelineMixRequest"]
            composition_result = stored["compositionResult"]
            preview_candidate = stored["previewCandidate"]
            inputs = stored["inputs"]
            now = composition_result.as_dict()["createdAt"]
        else:
            if any(
                not callable(getattr(self.composition, method, None))
                for method in (
                    "compose_glyph_reveal_v2",
                    "compose_timeline_preview_v1",
                )
            ):
                raise WorkerUnavailableError(
                    "M12/M13 composition execution is not configured"
                )
            if self.glyph_inspection_adapter is None:
                raise UpstreamNotReadyError(
                    "server-held glyph inspection evidence is not configured"
                )
            snapshot = validated_evidence_snapshot(
                self.evidence.read_snapshot(workspace, run_ref),
                workspace_ref=workspace,
                run_ref=run_ref,
            )
            if snapshot.revisionToken != normalized["expectedEvidenceRevision"]:
                raise StaleInputError("episode evidence revision changed")
            if snapshot.currentState != "MEDIA_READY":
                raise UpstreamNotReadyError(
                    "M12/M13 preview requires MEDIA_READY"
                )
            inputs = self._resolve_registered_timeline_inputs(
                workspace=workspace,
                run_ref=run_ref,
                references=normalized["timelineInputRefs"],
                snapshot=snapshot,
                verified_media=verified_media,
            )
            now = self._clock()
            projection = self._build_timeline_projection(
                command=normalized,
                run=run,
                inputs=inputs,
                created_at=now,
            )
            timeline = projection["timeline"]
            timeline_version = projection["timelineVersion"]
            subtitle_manifest = projection["subtitleManifest"]
            mix_request = projection["timelineMixRequest"]
            requirement = inputs["glyphRevealRequirement"]
            execution_request = build_glyph_reveal_execution_request_v2(
                requirement,
                base_plate_asset=inputs["basePlateAssetVersion"],
                mask_assets=inputs["maskAssetVersions"],
                inspection_adapter=self.glyph_inspection_adapter,
            )
            try:
                glyph_evidence = self.composition.compose_glyph_reveal_v2(
                    execution_request
                )
                video_input, _ = self._glyph_video_input(
                    requirement=requirement,
                    execution_request=execution_request,
                    artifact_evidence=glyph_evidence,
                    video_facts=projection["videoFacts"],
                )
                version_payload = timeline_version.as_dict()
                subtitle_payload = subtitle_manifest.as_dict()
                execution_result = self.composition.compose_timeline_preview_v1(
                    {
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "timelineVersionRef": version_payload[
                            "timelineVersionRef"
                        ],
                        "timelineVersionDigest": version_payload[
                            "payloadDigest"
                        ],
                        "videoInput": video_input,
                        "audioMix": projection["audioMixProjection"],
                        "subtitleManifest": {
                            "subtitleManifestRef": subtitle_payload[
                                "subtitleManifestRef"
                            ],
                            "subtitleManifestDigest": subtitle_payload[
                                "payloadDigest"
                            ],
                        },
                        "output": deepcopy(version_payload["output"]),
                    }
                )
            except CompositionExecutionError as exc:
                raise WorkerUnavailableError(
                    "M12/M13 deterministic composition failed"
                ) from exc

            composition_result = validate_composition_result(
                build_composition_result(
                    {
                        "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                        "createdAt": now,
                    },
                    timeline_version=timeline_version,
                    timeline_mix_request=mix_request,
                    subtitle_manifest=subtitle_manifest,
                    execution_result=execution_result,
                ),
                timeline_version=timeline_version,
                timeline_mix_request=mix_request,
                subtitle_manifest=subtitle_manifest,
            )
            composition_payload = composition_result.as_dict()
            preview_identity = {
                "timelineVersionRef": version_payload["timelineVersionRef"],
                "timelineVersionDigest": version_payload["payloadDigest"],
                "compositionResultRef": composition_payload[
                    "compositionResultRef"
                ],
                "compositionResultDigest": composition_payload[
                    "payloadDigest"
                ],
            }
            preview_ref = "m13-preview-candidate-" + _digest(
                preview_identity
            )[:32]
            preview_candidate = validate_preview_candidate(
                build_preview_candidate(
                    {
                        "previewCandidateRef": preview_ref,
                        "previewCandidateVersionRef": (
                            f"{preview_ref}-version-1"
                        ),
                        "version": 1,
                        "supersedesPreviewCandidateVersionRef": None,
                        "supersedesPreviewCandidateVersionDigest": None,
                        "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                        "createdAt": now,
                    },
                    timeline_version=timeline_version,
                    timeline_mix_request=mix_request,
                    subtitle_manifest=subtitle_manifest,
                    composition_result=composition_result,
                ),
                timeline_version=timeline_version,
                timeline_mix_request=mix_request,
                subtitle_manifest=subtitle_manifest,
                composition_result=composition_result,
            )
            self._verify_timeline_composition_artifact(composition_payload)

            timeline_payload = timeline.as_dict()
            mix_payload = mix_request.as_dict()
            preview_payload = preview_candidate.as_dict()
            records = (
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="Timeline",
                    record_ref=timeline_payload["timelineRef"],
                    record_version=1,
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="timeline",
                    created_at=now,
                    payload=timeline_payload,
                ),
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="TimelineVersion",
                    record_ref=version_payload["timelineVersionRef"],
                    record_version=version_payload["version"],
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="timeline-version",
                    created_at=now,
                    payload=version_payload,
                ),
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="SubtitleManifest",
                    record_ref=subtitle_payload["subtitleManifestRef"],
                    record_version=1,
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="subtitle-manifest",
                    created_at=now,
                    payload=subtitle_payload,
                ),
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="TimelineMixRequest",
                    record_ref=mix_payload["mixRequestRef"],
                    record_version=1,
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="timeline-mix-request",
                    created_at=now,
                    payload=mix_payload,
                ),
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="CompositionResult",
                    record_ref=composition_payload["compositionResultRef"],
                    record_version=1,
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="composition-result",
                    created_at=now,
                    payload=composition_payload,
                ),
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="PreviewCandidate",
                    record_ref=preview_payload[
                        "previewCandidateVersionRef"
                    ],
                    record_version=preview_payload["version"],
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="preview-candidate",
                    created_at=now,
                    payload=preview_payload,
                ),
            )
            journal_head = self._stable_record_head(
                workspace, run_ref, snapshot.revisionToken
            )
            _, composition_gate, atomic_replay = (
                self.evidence.append_records_and_gate(
                    records,
                    GateAppend(
                        workspace,
                        run_ref,
                        COMPOSITION_GATE,
                        composition_key,
                        verified_media["root"]["payloadDigest"],
                        composition_request_digest,
                        "MEDIA_READY",
                        "PREVIEW_READY",
                        now,
                        (
                            EvidenceFact(
                                "TimelineVersion",
                                version_payload["timelineVersionRef"],
                                version_payload["version"],
                                version_payload,
                                version_payload["payloadDigest"],
                            ),
                            EvidenceFact(
                                "PreviewCandidate",
                                preview_payload[
                                    "previewCandidateVersionRef"
                                ],
                                preview_payload["version"],
                                preview_payload,
                                preview_payload["payloadDigest"],
                            ),
                        ),
                    ),
                    expected_record_journal_head=journal_head,
                )
            )
            composition_replay = atomic_replay

        version_payload = timeline_version.as_dict()
        preview_payload = preview_candidate.as_dict()
        composition_payload = composition_result.as_dict()
        subtitle_payload = subtitle_manifest.as_dict()
        mix_payload = mix_request.as_dict()
        qc_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "operationRef": operation_ref,
                "stage": "m12-m13-timeline-qc",
            }
        )
        qc_request_digest = _digest(
            {
                "schemaVersion": "v5.m12-m13-preview-qc-request.v1",
                "timelineVersionDigest": version_payload["payloadDigest"],
                "compositionResultDigest": composition_payload[
                    "payloadDigest"
                ],
                "previewCandidateDigest": preview_payload["payloadDigest"],
                "subtitleManifestDigest": subtitle_payload[
                    "payloadDigest"
                ],
                "mixRequestDigest": mix_payload["payloadDigest"],
                "qcProfile": "k2.m12-m13.machine-verifiable.v1",
            }
        )
        qc_gate = self._existing(
            workspace, run_ref, QC_GATE, qc_key, qc_request_digest
        )
        qc_replay = qc_gate is not None
        if qc_gate is None:
            self._verify_timeline_composition_artifact(composition_payload)
            bundle_payload = validate_timeline_input_bundle(
                inputs["bundle"]
            ).as_dict()
            glyph_requirement_payload = inputs[
                "glyphRevealRequirement"
            ].as_dict()
            checks = self._timeline_preview_qc_checks(
                timeline_version=version_payload,
                composition_result=composition_payload,
                subtitle_manifest=subtitle_payload,
                timeline_input_bundle=bundle_payload,
                glyph_requirement=glyph_requirement_payload,
            )
            qc = _sealed(
                {
                    "schemaVersion": QC_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "qcReportRef": self._timeline_preview_qc_ref(
                        preview_payload
                    ),
                    "version": 1,
                    "previewCandidateRef": preview_payload[
                        "previewCandidateRef"
                    ],
                    "previewCandidateVersionRef": preview_payload[
                        "previewCandidateVersionRef"
                    ],
                    "previewCandidateDigest": preview_payload[
                        "payloadDigest"
                    ],
                    "timelineVersionRef": version_payload[
                        "timelineVersionRef"
                    ],
                    "timelineDigest": version_payload["payloadDigest"],
                    "checks": checks,
                    "result": "PASS",
                    "approvalStatus": "UNAPPROVED",
                    "machineVerified": True,
                    "publicationAllowed": False,
                    "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                    "createdAt": now,
                }
            )
            qc_gate, _ = self.evidence.append_gate(
                GateAppend(
                    workspace,
                    run_ref,
                    QC_GATE,
                    qc_key,
                    verified_media["root"]["payloadDigest"],
                    qc_request_digest,
                    "PREVIEW_READY",
                    "QC_READY",
                    now,
                    (
                        EvidenceFact(
                            "QCReport",
                            qc["qcReportRef"],
                            qc["version"],
                            qc,
                            qc["payloadDigest"],
                        ),
                    ),
                )
            )
        qc = self._validated_m12_m13_qc(
            _fact(qc_gate, "QCReport"),
            workspace=workspace,
            run_ref=run_ref,
            timeline_version=version_payload,
            preview_candidate=preview_payload,
            composition_result=composition_payload,
            subtitle_manifest=subtitle_payload,
            timeline_input_bundle=validate_timeline_input_bundle(
                inputs["bundle"]
            ).as_dict(),
            glyph_requirement=inputs["glyphRevealRequirement"].as_dict(),
        )
        return {
            "timelineVersion": version_payload,
            "compositionResult": composition_payload,
            "previewCandidate": preview_payload,
            "subtitleManifest": subtitle_payload,
            "qcReport": qc,
            "state": qc_gate["toState"],
            "idempotentReplay": composition_replay and qc_replay,
        }

    def _existing(
        self,
        workspace: str,
        run_ref: str,
        gate_name: str,
        key: str,
        request_digest: str,
    ) -> dict[str, Any] | None:
        gate = self.evidence.get_gate(workspace, run_ref, gate_name)
        if gate is None:
            return None
        if gate.get("idempotencyKey") != key or gate.get("requestDigest") != request_digest:
            raise IdempotencyConflictError(f"{gate_name} command conflicts")
        return gate

    def _verify_artifact(
        self, artifact: Mapping[str, Any], *, expected_sha: str | None = None
    ) -> tuple[Path, dict[str, Any]]:
        if self.composition is None:
            raise WorkerUnavailableError("composition execution is not configured")
        root = Path(self.composition.artifact_root).resolve()
        try:
            path = Path(artifact["internalPath"]).resolve()
        except (KeyError, TypeError):
            raise ArtifactRejectedError("composition artifact path is invalid") from None
        if root not in path.parents or not path.is_file():
            raise ArtifactRejectedError("composition artifact escaped configured root")
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        if (
            artifact.get("storageKey") != str(path.relative_to(root))
            or artifact.get("byteSize") != len(content)
            or artifact.get("sha256") != digest
            or (expected_sha is not None and digest != expected_sha)
            or artifact.get("provenance") != "LOCAL_EVIDENCE"
            or artifact.get("gpuUsed") is not False
            or artifact.get("publicationAllowed") is not False
        ):
            raise ArtifactRejectedError("composition artifact metadata is invalid")
        probe = probe_media(path)
        if probe != artifact.get("probe"):
            raise ArtifactRejectedError("composition artifact probe changed")
        return path, probe

    @staticmethod
    def _timeline(
        *,
        workspace: str,
        run_ref: str,
        root: Mapping[str, Any],
        graph: Mapping[str, Any],
        shots: list[Mapping[str, Any]],
        assets: list[Mapping[str, Any]],
        timeline_ref: str,
        timeline_version_ref: str,
        created_at: str,
    ) -> dict[str, Any]:
        by_pair = {
            (item.get("creativeShotRef"), item.get("mediaKind")): item
            for item in assets
        }
        if len(by_pair) != len(assets):
            raise ValidationFailedError("media asset selection is ambiguous")
        items = []
        cursor = 0
        for shot in shots:
            video = by_pair.get((shot["creativeShotRef"], "video"))
            audio = by_pair.get((shot["creativeShotRef"], "audio"))
            if not isinstance(video, Mapping) or not isinstance(audio, Mapping):
                raise ValidationFailedError("timeline requires one video and audio per shot")
            end = cursor + shot["durationFrames"]
            items.append(
                {
                    "ordinal": shot["globalOrder"],
                    "creativeShotRef": shot["creativeShotRef"],
                    "creativeShotVersionRef": shot["creativeShotVersionRef"],
                    "creativeShotDigest": shot["payloadDigest"],
                    "startFrame": cursor,
                    "endFrameExclusive": end,
                    "durationFrames": shot["durationFrames"],
                    "videoAssetVersionRef": video["assetVersionRef"],
                    "videoAssetDigest": video["payloadDigest"],
                    "videoStorageKey": video["storageKey"],
                    "audioAssetVersionRef": audio["assetVersionRef"],
                    "audioAssetDigest": audio["payloadDigest"],
                    "audioStorageKey": audio["storageKey"],
                }
            )
            cursor = end
        if cursor != graph["output"]["totalFrames"]:
            raise ValidationFailedError("timeline frame accounting is inconsistent")
        return _sealed(
            {
                "schemaVersion": TIMELINE_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "timelineRef": timeline_ref,
                "timelineVersionRef": timeline_version_ref,
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "items": items,
                "output": deepcopy(graph["output"]),
                "state": "COMPOSITION_READY",
                "provenance": "LOCAL_EVIDENCE",
                "publicationAllowed": False,
                "createdBy": DELIVERY_ID,
                "createdAt": created_at,
            }
        )

    def compose_and_qc(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(command, Mapping) and set(command) == {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "expectedEvidenceRevision",
            "timelineInputRefs",
        }:
            return self.compose_timeline_preview(command)
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey"
        }:
            raise EpisodeProductionError("command fields do not match the G6 preview contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        verified = self.media.verify_media_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        media_manifest = verified["mediaManifest"]
        now = self._clock()
        composition_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "composition"}
        )
        composition_request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "rootPayloadDigest": root["payloadDigest"],
                "shotGraphDigest": graph["payloadDigest"],
                "mediaManifestDigest": media_manifest["payloadDigest"],
                "deliveryId": DELIVERY_ID,
            }
        )
        composition_gate = self._existing(
            workspace, run_ref, COMPOSITION_GATE, composition_key,
            composition_request_digest,
        )
        composition_replay = composition_gate is not None
        if composition_gate is None:
            if self.composition is None:
                raise WorkerUnavailableError("composition execution is not configured")
            timeline = self._timeline(
                workspace=workspace,
                run_ref=run_ref,
                root=root,
                graph=graph,
                shots=verified["creativeShotVersions"],
                assets=verified["assetVersions"],
                timeline_ref=_required_ref(
                    self._ref_factory("timeline"), "timelineRef"
                ),
                timeline_version_ref=_required_ref(
                    self._ref_factory("timeline-version"), "timelineVersionRef"
                ),
                created_at=now,
            )
            try:
                artifact = self.composition.compose(
                    {
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "timelineDigest": timeline["payloadDigest"],
                        "items": timeline["items"],
                        "output": timeline["output"],
                    }
                )
            except CompositionExecutionError as exc:
                raise WorkerUnavailableError("V3 composition failed") from exc
            _, probe = self._verify_artifact(artifact)
            preview = _sealed(
                {
                    "schemaVersion": PREVIEW_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "previewCandidateRef": _required_ref(
                        self._ref_factory("preview-candidate"), "previewCandidateRef"
                    ),
                    "previewCandidateVersionRef": _required_ref(
                        self._ref_factory("preview-candidate-version"),
                        "previewCandidateVersionRef",
                    ),
                    "version": 1,
                    "timelineRef": timeline["timelineRef"],
                    "timelineVersionRef": timeline["timelineVersionRef"],
                    "timelineDigest": timeline["payloadDigest"],
                    "mediaManifestRef": media_manifest["mediaManifestRef"],
                    "mediaManifestDigest": media_manifest["payloadDigest"],
                    "storageKey": artifact["storageKey"],
                    "mediaType": "video/mp4",
                    "byteSize": artifact["byteSize"],
                    "sha256": artifact["sha256"],
                    "probe": probe,
                    "adapterIdentity": artifact["adapterIdentity"],
                    "composerIdentity": artifact["composerIdentity"],
                    "state": "CANDIDATE",
                    "approvalStatus": "UNAPPROVED",
                    "provenance": "LOCAL_EVIDENCE",
                    "rightsState": "LOCAL_EVIDENCE_ONLY",
                    "gpuUsed": False,
                    "publicationAllowed": False,
                    "createdBy": DELIVERY_ID,
                    "createdAt": now,
                }
            )
            composition_gate, _ = self.evidence.append_gate(
                GateAppend(
                    workspace, run_ref, COMPOSITION_GATE, composition_key,
                    root["payloadDigest"], composition_request_digest,
                    "MEDIA_READY", "PREVIEW_READY", now,
                    (
                        EvidenceFact(
                            "TimelineVersion", timeline["timelineVersionRef"], 1,
                            timeline, timeline["payloadDigest"]
                        ),
                        EvidenceFact(
                            "PreviewCandidate", preview["previewCandidateVersionRef"],
                            1, preview, preview["payloadDigest"]
                        ),
                    ),
                )
            )
        timeline = _fact(composition_gate, "TimelineVersion")
        preview = _fact(composition_gate, "PreviewCandidate")
        qc_key = _digest({"clientIdempotencyKey": client_key, "stage": "qc"})
        qc_request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "timelineDigest": timeline["payloadDigest"],
                "previewDigest": preview["payloadDigest"],
                "mediaManifestDigest": media_manifest["payloadDigest"],
                "qcProfile": "k2.machine-verifiable.v1",
            }
        )
        qc_gate = self._existing(
            workspace, run_ref, QC_GATE, qc_key, qc_request_digest
        )
        qc_replay = qc_gate is not None
        if qc_gate is None:
            if self.composition is None:
                raise WorkerUnavailableError("composition execution is not configured")
            artifact = {
                "internalPath": str(
                    (Path(self.composition.artifact_root) / preview["storageKey"]).resolve()
                ),
                **{key: preview[key] for key in (
                    "storageKey", "byteSize", "sha256", "probe", "provenance",
                    "gpuUsed", "publicationAllowed",
                )},
            }
            _, probe = self._verify_artifact(artifact, expected_sha=preview["sha256"])
            videos = [s for s in probe["streams"] if s.get("codec_type") == "video"]
            audios = [s for s in probe["streams"] if s.get("codec_type") == "audio"]
            frame_count = videos[0].get("nb_read_frames") or videos[0].get("nb_frames")
            checks = [
                {
                    "checkId": "artifact-digest-and-probe",
                    "status": "PASSED",
                    "evidence": preview["sha256"],
                },
                {
                    "checkId": "video-stream-contract",
                    "status": "PASSED" if len(videos) == 1
                    and videos[0].get("width") == timeline["output"]["width"]
                    and videos[0].get("height") == timeline["output"]["height"]
                    and int(frame_count or -1) == timeline["output"]["totalFrames"]
                    else "FAILED",
                },
                {
                    "checkId": "audio-stream-contract",
                    "status": "PASSED" if len(audios) == 1
                    and int(audios[0].get("sample_rate", -1)) == 48_000
                    and audios[0].get("channels") == 2 else "FAILED",
                },
                {
                    "checkId": "timeline-contiguity",
                    "status": "PASSED" if all(
                        item["startFrame"] == (0 if index == 0 else timeline["items"][index - 1]["endFrameExclusive"])
                        for index, item in enumerate(timeline["items"])
                    ) and timeline["items"][-1]["endFrameExclusive"]
                    == timeline["output"]["totalFrames"] else "FAILED",
                },
                {
                    "checkId": "identity-continuity-lineage",
                    "status": "PASSED" if all(
                        shot.get("requiredCharacterIdentityLocks")
                        for shot in graph["shots"]
                    ) else "FAILED",
                },
                {
                    "checkId": "local-evidence-publication-lock",
                    "status": "PASSED" if preview["publicationAllowed"] is False
                    and preview["provenance"] == "LOCAL_EVIDENCE" else "FAILED",
                },
            ]
            result = "PASS" if all(item["status"] == "PASSED" for item in checks) else "FAIL"
            if result != "PASS":
                raise ArtifactRejectedError("preview failed machine QC")
            qc = _sealed(
                {
                    "schemaVersion": QC_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "qcReportRef": _required_ref(
                        self._ref_factory("qc-report"), "qcReportRef"
                    ),
                    "version": 1,
                    "previewCandidateRef": preview["previewCandidateRef"],
                    "previewCandidateVersionRef": preview[
                        "previewCandidateVersionRef"
                    ],
                    "previewCandidateDigest": preview["payloadDigest"],
                    "timelineVersionRef": timeline["timelineVersionRef"],
                    "timelineDigest": timeline["payloadDigest"],
                    "checks": checks,
                    "result": result,
                    "approvalStatus": "UNAPPROVED",
                    "machineVerified": True,
                    "publicationAllowed": False,
                    "createdBy": DELIVERY_ID,
                    "createdAt": now,
                }
            )
            qc_gate, _ = self.evidence.append_gate(
                GateAppend(
                    workspace, run_ref, QC_GATE, qc_key, root["payloadDigest"],
                    qc_request_digest, "PREVIEW_READY", "QC_READY", now,
                    (EvidenceFact("QCReport", qc["qcReportRef"], 1, qc, qc["payloadDigest"]),),
                )
            )
        return {
            "timelineVersion": timeline,
            "previewCandidate": preview,
            "qcReport": _fact(qc_gate, "QCReport"),
            "state": qc_gate["toState"],
            "idempotentReplay": composition_replay and qc_replay,
        }

    def _verified_preview_qc(
        self, workspace: str, run_ref: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        verified = self.media.verify_media_current(workspace, run_ref)
        if self.composition is None:
            raise WorkerUnavailableError("composition execution is not configured")
        composition_gate = self.evidence.get_gate(workspace, run_ref, COMPOSITION_GATE)
        qc_gate = self.evidence.get_gate(workspace, run_ref, QC_GATE)
        if composition_gate is None or qc_gate is None:
            raise UpstreamNotReadyError("G6 preview and QC are not ready")
        timeline = _fact(composition_gate, "TimelineVersion")
        preview = _fact(composition_gate, "PreviewCandidate")
        qc = _fact(qc_gate, "QCReport")
        if preview.get("schemaVersion") == PREVIEW_CANDIDATE_SCHEMA_VERSION_V2:
            raise UpstreamNotReadyError(
                "M12/M13 preview finalization is not implemented"
            )
        if (
            timeline.get("rootPayloadDigest") != verified["root"]["payloadDigest"]
            or timeline.get("executableShotGraphDigest")
            != verified["executableShotGraph"]["payloadDigest"]
            or preview.get("timelineDigest") != timeline["payloadDigest"]
            or preview.get("mediaManifestDigest")
            != verified["mediaManifest"]["payloadDigest"]
            or qc.get("previewCandidateDigest") != preview["payloadDigest"]
            or qc.get("timelineDigest") != timeline["payloadDigest"]
            or qc.get("result") != "PASS"
        ):
            raise StaleInputError("G6 preview or QC lineage is stale")
        artifact = {
            "internalPath": str(
                (Path(self.composition.artifact_root) / preview["storageKey"]).resolve()
            ),
            **{key: preview[key] for key in (
                "storageKey", "byteSize", "sha256", "probe", "provenance",
                "gpuUsed", "publicationAllowed",
            )},
        }
        self._verify_artifact(artifact, expected_sha=preview["sha256"])
        return verified, timeline, preview, qc

    def approve_and_finalize(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey", "decisions"
        }:
            raise EpisodeProductionError("command fields do not match the G6 approval contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        decisions_input = command.get("decisions")
        if not isinstance(decisions_input, list) or len(decisions_input) != len(APPROVAL_KINDS):
            raise ValidationFailedError("all four approval decisions are required")
        by_kind: dict[str, Mapping[str, Any]] = {}
        approval_refs: set[str] = set()
        for item in decisions_input:
            if not isinstance(item, Mapping) or set(item) != {
                "kind", "decision", "approvalRef", "actorRef"
            }:
                raise ValidationFailedError("approval decision fields are invalid")
            kind = item.get("kind")
            if kind not in APPROVAL_KINDS or kind in by_kind:
                raise ValidationFailedError("approval decision kinds are invalid")
            if item.get("decision") != "ACCEPT":
                raise ApprovalRejectedError("rejected decision cannot finalize a master")
            approval_ref = _required_ref(item.get("approvalRef"), "approvalRef")
            actor_ref = _required_ref(item.get("actorRef"), "actorRef")
            if approval_ref in approval_refs:
                raise ValidationFailedError("approvalRef must be unique per decision")
            approval_refs.add(approval_ref)
            by_kind[kind] = {
                "kind": kind,
                "decision": "ACCEPT",
                "approvalRef": approval_ref,
                "actorRef": actor_ref,
            }
        if set(by_kind) != set(APPROVAL_KINDS):
            raise ValidationFailedError("approval decision coverage is incomplete")
        verified, timeline, preview, qc = self._verified_preview_qc(workspace, run_ref)
        root = verified["root"]
        now = self._clock()
        normalized = [deepcopy(dict(by_kind[kind])) for kind in APPROVAL_KINDS]
        subjects = {
            kind: ApprovalSubject.create(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                kind=kind,
                timeline_version_ref=timeline["timelineVersionRef"],
                timeline_digest=timeline["payloadDigest"],
                preview_candidate_version_ref=preview[
                    "previewCandidateVersionRef"
                ],
                preview_candidate_digest=preview["payloadDigest"],
                qc_report_ref=qc["qcReportRef"],
                qc_report_digest=qc["payloadDigest"],
            )
            for kind in APPROVAL_KINDS
        }
        approval_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "approvals"}
        )
        approval_request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "previewDigest": preview["payloadDigest"],
                "qcDigest": qc["payloadDigest"],
                "decisions": normalized,
                "approvalSubjects": [
                    subjects[kind].as_dict() for kind in APPROVAL_KINDS
                ],
            }
        )
        approval_gate = self._existing(
            workspace, run_ref, APPROVAL_GATE, approval_key,
            approval_request_digest,
        )
        approval_replay = approval_gate is not None
        if approval_gate is None:
            decisions = []
            for ordinal, item in enumerate(normalized, start=1):
                approval_ref = item["approvalRef"]
                actor_ref = item["actorRef"]
                subject = subjects[item["kind"]]
                authority = self.approval_authority.verify(
                    subject=subject,
                    approval_ref=approval_ref,
                    actor_ref=actor_ref,
                )
                if (
                    not isinstance(authority, VerifiedApproval)
                    or not authority.matches(
                        subject=subject,
                        approval_ref=approval_ref,
                        actor_ref=actor_ref,
                    )
                ):
                    raise ApprovalRequiredError(
                        "approval authority returned mismatched evidence"
                    )
                if authority.decision != "ACCEPT":
                    raise ApprovalRejectedError(
                        "authority rejected decision cannot finalize a master"
                    )
                decisions.append(
                    _sealed(
                        {
                            "schemaVersion": APPROVAL_SCHEMA_VERSION,
                            "workspaceRef": workspace,
                            "productionRunRef": run_ref,
                            "approvalDecisionRef": _required_ref(
                                self._ref_factory("approval-decision"),
                                "approvalDecisionRef",
                            ),
                            "version": 1,
                            "ordinal": ordinal,
                            "kind": item["kind"],
                            "decision": "ACCEPT",
                            "approvalRef": approval_ref,
                            "actorRef": actor_ref,
                            "subjectSchemaVersion": (
                                APPROVAL_SUBJECT_SCHEMA_VERSION
                            ),
                            "subjectDigest": subject.subject_digest,
                            "authorityRef": authority.authority_ref,
                            "authorityType": authority.authority_type,
                            "authorityDecisionRef": (
                                authority.authority_decision_ref
                            ),
                            "authorityDecisionDigest": (
                                authority.authority_decision_digest
                            ),
                            "authorityDecidedAt": authority.decided_at,
                            "previewCandidateVersionRef": preview[
                                "previewCandidateVersionRef"
                            ],
                            "previewCandidateDigest": preview["payloadDigest"],
                            "qcReportRef": qc["qcReportRef"],
                            "qcReportDigest": qc["payloadDigest"],
                            "timelineVersionRef": timeline["timelineVersionRef"],
                            "timelineDigest": timeline["payloadDigest"],
                            "state": "ACCEPTED",
                            "createdBy": actor_ref,
                            "createdAt": now,
                        }
                    )
                )
            approval_gate, _ = self.evidence.append_gate(
                GateAppend(
                    workspace, run_ref, APPROVAL_GATE, approval_key,
                    root["payloadDigest"], approval_request_digest,
                    "QC_READY", "APPROVAL_READY", now,
                    tuple(
                        EvidenceFact(
                            f"ApprovalDecision:{item['kind']}",
                            item["approvalDecisionRef"], 1, item,
                            item["payloadDigest"],
                        )
                        for item in decisions
                    ),
                )
            )
        decisions = _approval_facts(approval_gate)
        lineage_is_current = len(decisions) == len(APPROVAL_KINDS)
        for item in decisions:
            kind = item.get("kind")
            if kind not in subjects:
                lineage_is_current = False
                continue
            subject = subjects[kind]
            expected_input = by_kind[kind]
            lineage_is_current = lineage_is_current and all(
                (
                    item.get("schemaVersion") == APPROVAL_SCHEMA_VERSION,
                    item.get("decision") == "ACCEPT",
                    item.get("state") == "ACCEPTED",
                    item.get("approvalRef") == expected_input["approvalRef"],
                    item.get("actorRef") == expected_input["actorRef"],
                    item.get("subjectSchemaVersion")
                    == APPROVAL_SUBJECT_SCHEMA_VERSION,
                    item.get("subjectDigest") == subject.subject_digest,
                    item.get("timelineVersionRef")
                    == subject.timeline_version_ref,
                    item.get("timelineDigest") == subject.timeline_digest,
                    item.get("previewCandidateVersionRef")
                    == subject.preview_candidate_version_ref,
                    item.get("previewCandidateDigest")
                    == subject.preview_candidate_digest,
                    item.get("qcReportRef") == subject.qc_report_ref,
                    item.get("qcReportDigest") == subject.qc_report_digest,
                )
            )
            try:
                persisted_authority = VerifiedApproval.create(
                    authority_ref=item.get("authorityRef"),
                    approval_ref=item.get("approvalRef"),
                    actor_ref=item.get("actorRef"),
                    kind=kind,
                    authority_type=item.get("authorityType"),
                    decision=item.get("decision"),
                    authority_decision_ref=item.get("authorityDecisionRef"),
                    authority_decision_digest=item.get(
                        "authorityDecisionDigest"
                    ),
                    decided_at=item.get("authorityDecidedAt"),
                    subject_digest=item.get("subjectDigest"),
                )
            except ApprovalRequiredError:
                lineage_is_current = False
            else:
                lineage_is_current = lineage_is_current and persisted_authority.matches(
                    subject=subject,
                    approval_ref=expected_input["approvalRef"],
                    actor_ref=expected_input["actorRef"],
                )
        if (
            [item.get("kind") for item in decisions] != list(APPROVAL_KINDS)
            or not lineage_is_current
        ):
            raise StaleInputError("approval decision lineage is stale")
        master_key = _digest(
            {
                "previewSha256": preview["sha256"],
                "approvalDecisionDigests": [item["payloadDigest"] for item in decisions],
            }
        )
        master_gate_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "master"}
        )
        master_request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "previewDigest": preview["payloadDigest"],
                "qcDigest": qc["payloadDigest"],
                "approvalDecisionDigests": [item["payloadDigest"] for item in decisions],
                "masterKey": master_key,
            }
        )
        master_gate = self._existing(
            workspace, run_ref, MASTER_GATE, master_gate_key, master_request_digest
        )
        master_replay = master_gate is not None
        if master_gate is None:
            if self.composition is None:
                raise WorkerUnavailableError("composition execution is not configured")
            try:
                artifact = self.composition.finalize(
                    {
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "previewStorageKey": preview["storageKey"],
                        "masterKey": master_key,
                    }
                )
            except CompositionExecutionError as exc:
                raise WorkerUnavailableError("V3 master finalization failed") from exc
            _, probe = self._verify_artifact(artifact, expected_sha=preview["sha256"])
            master = _sealed(
                {
                    "schemaVersion": MASTER_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "episodeMasterRef": _required_ref(
                        self._ref_factory("episode-master"), "episodeMasterRef"
                    ),
                    "episodeMasterVersionRef": _required_ref(
                        self._ref_factory("episode-master-version"),
                        "episodeMasterVersionRef",
                    ),
                    "version": 1,
                    "rootPayloadDigest": root["payloadDigest"],
                    "timelineVersionRef": timeline["timelineVersionRef"],
                    "timelineDigest": timeline["payloadDigest"],
                    "previewCandidateVersionRef": preview[
                        "previewCandidateVersionRef"
                    ],
                    "previewCandidateDigest": preview["payloadDigest"],
                    "qcReportRef": qc["qcReportRef"],
                    "qcReportDigest": qc["payloadDigest"],
                    "approvalDecisionRefs": [
                        item["approvalDecisionRef"] for item in decisions
                    ],
                    "approvalDecisionDigests": [
                        item["payloadDigest"] for item in decisions
                    ],
                    "storageKey": artifact["storageKey"],
                    "mediaType": "video/mp4",
                    "byteSize": artifact["byteSize"],
                    "sha256": artifact["sha256"],
                    "probe": probe,
                    "state": "IMMUTABLE_MASTER",
                    "provenance": "LOCAL_EVIDENCE",
                    "rightsState": "LOCAL_EVIDENCE_ONLY",
                    "gpuUsed": False,
                    "publicationAllowed": False,
                    "createdBy": DELIVERY_ID,
                    "createdAt": now,
                }
            )
            export = _sealed(
                {
                    "schemaVersion": EXPORT_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "exportArtifactRef": _required_ref(
                        self._ref_factory("export-artifact"), "exportArtifactRef"
                    ),
                    "version": 1,
                    "episodeMasterRef": master["episodeMasterRef"],
                    "episodeMasterVersionRef": master["episodeMasterVersionRef"],
                    "episodeMasterDigest": master["payloadDigest"],
                    "storageKey": master["storageKey"],
                    "fileName": f"k2-{root['episodeRef']}.mp4",
                    "mediaType": "video/mp4",
                    "byteSize": master["byteSize"],
                    "sha256": master["sha256"],
                    "state": "PLAYABLE_LOCAL_EVIDENCE",
                    "downloadAllowed": True,
                    "publicationAllowed": False,
                    "createdBy": DELIVERY_ID,
                    "createdAt": now,
                }
            )
            master_gate, _ = self.evidence.append_gate(
                GateAppend(
                    workspace, run_ref, MASTER_GATE, master_gate_key,
                    root["payloadDigest"], master_request_digest,
                    "APPROVAL_READY", "MASTER_READY", now,
                    (
                        EvidenceFact(
                            "EpisodeMaster", master["episodeMasterVersionRef"], 1,
                            master, master["payloadDigest"]
                        ),
                        EvidenceFact(
                            "ExportArtifact", export["exportArtifactRef"], 1,
                            export, export["payloadDigest"]
                        ),
                    ),
                )
            )
        return {
            "approvalDecisions": decisions,
            "episodeMaster": _fact(master_gate, "EpisodeMaster"),
            "exportArtifact": _fact(master_gate, "ExportArtifact"),
            "state": master_gate["toState"],
            "idempotentReplay": approval_replay and master_replay,
        }

    def get_delivery_bundle(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        run = self.media.assets.shot_graph.root_service.get_run(workspace_ref, run_ref)
        result: dict[str, Any] = {
            "state": self.evidence.current_state(workspace_ref, run_ref),
            "productionRunRef": run_ref,
        }
        composition = self.evidence.get_gate(workspace_ref, run_ref, COMPOSITION_GATE)
        qc = self.evidence.get_gate(workspace_ref, run_ref, QC_GATE)
        approvals = self.evidence.get_gate(workspace_ref, run_ref, APPROVAL_GATE)
        master = self.evidence.get_gate(workspace_ref, run_ref, MASTER_GATE)
        if composition is not None:
            result.update(
                {
                    "timelineVersion": _fact(composition, "TimelineVersion"),
                    "previewCandidate": _fact(composition, "PreviewCandidate"),
                }
            )
        if qc is not None:
            result["qcReport"] = _fact(qc, "QCReport")
        if approvals is not None:
            result["approvalDecisions"] = _approval_facts(approvals)
        if master is not None:
            result.update(
                {
                    "episodeMaster": _fact(master, "EpisodeMaster"),
                    "exportArtifact": _fact(master, "ExportArtifact"),
                }
            )
        return result

    def get_preview_bundle(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        """Return an artifact-verified, locator-free preview summary."""

        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run_ref = _required_ref(run_ref, "productionRunRef")
        composition_gate = self.evidence.get_gate(
            workspace, production_run_ref, COMPOSITION_GATE
        )
        qc_gate = self.evidence.get_gate(
            workspace, production_run_ref, QC_GATE
        )
        if composition_gate is None or qc_gate is None:
            raise UpstreamNotReadyError("G6 preview and QC are not ready")
        timeline_fact = _immutable_payload(
            _fact(composition_gate, "TimelineVersion"), "TimelineVersion"
        )
        preview_fact = _immutable_payload(
            _fact(composition_gate, "PreviewCandidate"), "PreviewCandidate"
        )
        qc = _immutable_payload(_fact(qc_gate, "QCReport"), "QCReport")

        if preview_fact.get("schemaVersion") != PREVIEW_CANDIDATE_SCHEMA_VERSION_V2:
            _, timeline, preview, _ = self._verified_preview_qc(
                workspace, production_run_ref
            )
            return {
                "state": qc_gate["toState"],
                "productionRunRef": production_run_ref,
                "timeline": {
                    key: deepcopy(timeline[key])
                    for key in (
                        "timelineRef",
                        "timelineVersionRef",
                        "version",
                        "output",
                        "state",
                        "provenance",
                        "publicationAllowed",
                        "payloadDigest",
                    )
                },
                "preview": {
                    key: deepcopy(preview[key])
                    for key in (
                        "previewCandidateRef",
                        "previewCandidateVersionRef",
                        "version",
                        "timelineVersionRef",
                        "timelineDigest",
                        "mediaType",
                        "byteSize",
                        "sha256",
                        "probe",
                        "state",
                        "approvalStatus",
                        "provenance",
                        "rightsState",
                        "gpuUsed",
                        "publicationAllowed",
                        "payloadDigest",
                    )
                },
                "audio": {
                    "assetVersionRefs": [
                        item["audioAssetVersionRef"]
                        for item in timeline["items"]
                    ]
                },
                "cues": [],
                "effect": None,
            }

        snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, production_run_ref),
            workspace_ref=workspace,
            run_ref=production_run_ref,
        )
        composition_record = self._snapshot_record_payload(
            snapshot,
            record_kind="CompositionResult",
            record_ref=_required_ref(
                preview_fact.get("compositionResultRef"),
                "compositionResultRef",
            ),
        )
        mix_record = self._snapshot_record_payload(
            snapshot,
            record_kind="TimelineMixRequest",
            record_ref=_required_ref(
                composition_record.get("mixRequestRef"), "mixRequestRef"
            ),
        )
        if mix_record.get("payloadDigest") != composition_record.get(
            "mixRequestDigest"
        ):
            raise StaleInputError("TimelineMixRequest record lineage is stale")
        references = self._timeline_input_refs_from_version(
            snapshot, timeline_fact, mix_record
        )
        verified_media = self.media.verify_media_current(
            workspace, production_run_ref
        )
        stored = self._validated_stored_timeline_preview(
            command={
                "workspaceRef": workspace,
                "productionRunRef": production_run_ref,
                "timelineInputRefs": references,
            },
            composition_gate=composition_gate,
            snapshot=snapshot,
            verified_media=verified_media,
        )
        timeline = stored["timelineVersion"].as_dict()
        preview = stored["previewCandidate"].as_dict()
        mix = stored["timelineMixRequest"].as_dict()
        inputs = stored["inputs"]
        qc = self._validated_m12_m13_qc(
            qc,
            workspace=workspace,
            run_ref=production_run_ref,
            timeline_version=timeline,
            preview_candidate=preview,
            composition_result=stored["compositionResult"].as_dict(),
            subtitle_manifest=stored["subtitleManifest"].as_dict(),
            timeline_input_bundle=validate_timeline_input_bundle(
                inputs["bundle"]
            ).as_dict(),
            glyph_requirement=inputs["glyphRevealRequirement"].as_dict(),
        )
        bindings = inputs["audioInputBindings"]
        cues = inputs["audioCues"]
        requirement = inputs["glyphRevealRequirement"].as_dict()
        return {
            "state": qc_gate["toState"],
            "productionRunRef": production_run_ref,
            "timeline": {
                key: deepcopy(timeline[key])
                for key in (
                    "timelineRef",
                    "timelineVersionRef",
                    "version",
                    "frameRate",
                    "durationFrames",
                    "trackRefs",
                    "output",
                    "state",
                    "authorityState",
                    "provenance",
                    "publicationAllowed",
                    "payloadDigest",
                )
            },
            "preview": {
                key: deepcopy(preview[key])
                for key in (
                    "previewCandidateRef",
                    "previewCandidateVersionRef",
                    "version",
                    "timelineVersionRef",
                    "timelineVersionDigest",
                    "mixRequestRef",
                    "mixRequestDigest",
                    "subtitleManifestRef",
                    "subtitleManifestDigest",
                    "compositionResultRef",
                    "compositionResultDigest",
                    "compositionRequestDigest",
                    "artifactRef",
                    "fileDigest",
                    "decodedFramePixelDigest",
                    "pcmContentDigest",
                    "outputByteSize",
                    "mediaProbe",
                    "outputMediaProbe",
                    "runtimeIdentity",
                    "state",
                    "approvalStatus",
                    "provenance",
                    "rightsState",
                    "providerUsed",
                    "gpuUsed",
                    "publicationAllowed",
                    "payloadDigest",
                )
            },
            "audio": {
                "stemSetVersionRef": mix["stemSetVersionRef"],
                "stemSetDigest": mix["stemSetDigest"],
                "mixRequestRef": mix["mixRequestRef"],
                "mixRequestDigest": mix["payloadDigest"],
                "sampleRate": mix["sampleRate"],
                "channelCount": mix["channelCount"],
                "durationSamples": mix["durationSamples"],
                "roundingRule": mix["roundingRule"],
                "mixParametersDigest": mix["mixParametersDigest"],
                "bindings": [
                    {
                        key: item[key]
                        for key in (
                            "audioInputBindingRef",
                            "assetVersionRef",
                            "assetVersionType",
                            "assetVersionDigest",
                            "technicalValidationRef",
                            "technicalValidationDigest",
                            "fileDigest",
                            "pcmContentDigest",
                            "sampleRate",
                            "channelCount",
                            "sampleCount",
                            "rightsBindingRef",
                            "rightsBindingDigest",
                            "provenanceDigest",
                            "sourceLabels",
                            "payloadDigest",
                        )
                    }
                    | {"audioRole": _audio_role_from_binding(item)}
                    for item in bindings
                ],
            },
            "cues": [
                {
                    "cueRef": item["cueRef"],
                    "cueVersionRef": item["cueVersionRef"],
                    "version": item["version"],
                    "cueRole": item["cueRole"],
                    "assetVersionRef": item["assetVersionRef"],
                    "sourceStartSample": item["sourceStartSample"],
                    "sourceEndSample": item["sourceEndSample"],
                    "subtitleTimingReference": deepcopy(
                        item["subtitleTimingReference"]
                    ),
                    "payloadDigest": item["payloadDigest"],
                }
                for item in cues
            ],
            "effect": {
                "requirementRef": requirement["requirementRef"],
                "glyphSlug": requirement["glyphSlug"],
                "targetShotRef": requirement["targetShotRef"],
                "frameRangeStartInclusive": requirement[
                    "frameRangeStartInclusive"
                ],
                "frameRangeEndExclusive": requirement[
                    "frameRangeEndExclusive"
                ],
                "maskAssetVersionRefs": [
                    item["assetVersionRef"]
                    for item in requirement["maskAssetVersionBindings"]
                ],
                "maskAssetVersionBindings": deepcopy(
                    requirement["maskAssetVersionBindings"]
                ),
                "compositeParams": deepcopy(requirement["compositeParams"]),
                "layer": 1,
                "blendMode": requirement["compositeParams"]["blendMode"],
                "payloadDigest": requirement["payloadDigest"],
            },
        }

    def get_preview_file(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run_ref = _required_ref(run_ref, "productionRunRef")
        composition_gate = self.evidence.get_gate(
            workspace, production_run_ref, COMPOSITION_GATE
        )
        qc_gate = self.evidence.get_gate(workspace, production_run_ref, QC_GATE)
        if composition_gate is None or qc_gate is None:
            raise UpstreamNotReadyError("G6 preview and QC are not ready")
        preview = _fact(composition_gate, "PreviewCandidate")
        if preview.get("schemaVersion") == PREVIEW_CANDIDATE_SCHEMA_VERSION_V2:
            preview = _immutable_payload(preview, "PreviewCandidate")
            timeline_fact = _immutable_payload(
                _fact(composition_gate, "TimelineVersion"),
                "TimelineVersion",
            )
            snapshot = validated_evidence_snapshot(
                self.evidence.read_snapshot(workspace, production_run_ref),
                workspace_ref=workspace,
                run_ref=production_run_ref,
            )
            composition_record = self._snapshot_record_payload(
                snapshot,
                record_kind="CompositionResult",
                record_ref=_required_ref(
                    preview.get("compositionResultRef"),
                    "compositionResultRef",
                ),
            )
            mix_record = self._snapshot_record_payload(
                snapshot,
                record_kind="TimelineMixRequest",
                record_ref=_required_ref(
                    composition_record.get("mixRequestRef"), "mixRequestRef"
                ),
            )
            if mix_record.get("payloadDigest") != composition_record.get(
                "mixRequestDigest"
            ):
                raise StaleInputError("TimelineMixRequest record lineage is stale")
            references = self._timeline_input_refs_from_version(
                snapshot, timeline_fact, mix_record
            )
            verified_media = self.media.verify_media_current(
                workspace, production_run_ref
            )
            stored = self._validated_stored_timeline_preview(
                command={
                    "workspaceRef": workspace,
                    "productionRunRef": production_run_ref,
                    "timelineInputRefs": references,
                },
                composition_gate=composition_gate,
                snapshot=snapshot,
                verified_media=verified_media,
            )
            timeline = stored["timelineVersion"].as_dict()
            preview = stored["previewCandidate"].as_dict()
            composition = stored["compositionResult"].as_dict()
            inputs = stored["inputs"]
            self._validated_m12_m13_qc(
                _fact(qc_gate, "QCReport"),
                workspace=workspace,
                run_ref=production_run_ref,
                timeline_version=timeline,
                preview_candidate=preview,
                composition_result=composition,
                subtitle_manifest=stored["subtitleManifest"].as_dict(),
                timeline_input_bundle=validate_timeline_input_bundle(
                    inputs["bundle"]
                ).as_dict(),
                glyph_requirement=inputs[
                    "glyphRevealRequirement"
                ].as_dict(),
            )
            path = stored["artifactPath"]
            digest = composition["outputDigest"]["fileDigest"].removeprefix(
                "sha256:"
            )
            return {
                "path": path,
                "fileName": f"preview-{production_run_ref}.mp4",
                "mediaType": "video/mp4",
                "byteSize": composition["outputByteSize"],
                "sha256": digest,
                "contentDisposition": "inline",
            }

        _, _, preview, _ = self._verified_preview_qc(
            workspace, production_run_ref
        )
        artifact = {
            "internalPath": str(
                (
                    Path(self.composition.artifact_root)
                    / preview["storageKey"]
                ).resolve()
            ),
            **{
                key: preview[key]
                for key in (
                    "storageKey",
                    "byteSize",
                    "sha256",
                    "probe",
                    "provenance",
                    "gpuUsed",
                    "publicationAllowed",
                )
            },
        }
        path, _ = self._verify_artifact(
            artifact, expected_sha=preview["sha256"]
        )
        return {
            "path": path,
            "fileName": f"preview-{run_ref}.mp4",
            "mediaType": preview["mediaType"],
            "byteSize": preview["byteSize"],
            "sha256": preview["sha256"],
            "contentDisposition": "inline",
        }

    def get_export_file(
        self, workspace_ref: str, run_ref: str, export_ref: str
    ) -> dict[str, Any]:
        self._verified_preview_qc(workspace_ref, run_ref)
        gate = self.evidence.get_gate(workspace_ref, run_ref, MASTER_GATE)
        if gate is None:
            raise UpstreamNotReadyError("episode master is not ready")
        master = _fact(gate, "EpisodeMaster")
        export = _fact(gate, "ExportArtifact")
        if export.get("exportArtifactRef") != export_ref:
            raise RecordNotFoundError("export artifact was not found")
        if (
            export.get("episodeMasterDigest") != master["payloadDigest"]
            or export.get("sha256") != master["sha256"]
            or export.get("storageKey") != master["storageKey"]
        ):
            raise StaleInputError("export lineage is stale")
        artifact = {
            "internalPath": str(
                (Path(self.composition.artifact_root) / master["storageKey"]).resolve()
            ),
            **{key: master[key] for key in (
                "storageKey", "byteSize", "sha256", "probe", "provenance",
                "gpuUsed", "publicationAllowed",
            )},
        }
        path, _ = self._verify_artifact(artifact, expected_sha=export["sha256"])
        return {
            "path": path,
            "fileName": export["fileName"],
            "mediaType": export["mediaType"],
            "byteSize": export["byteSize"],
            "sha256": export["sha256"],
        }
