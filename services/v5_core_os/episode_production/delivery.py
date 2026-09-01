"""G6 deterministic composition, QC, explicit decisions and immutable master."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import gcd
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable, Mapping, Protocol, Sequence

from services.v3_render_core.digests import (
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
)
from services.v4_platform import (
    ArtifactVerificationError,
    CompositionExecutionError,
    probe_media,
)
from services.v4_platform.render_candidate import (
    build_render_execution_request,
    composition_command_digest,
    render_input_bindings_digest,
    runtime_binding_digest,
    validate_render_execution_request,
)

from .assets import (
    ASSET_PLAN_SCHEMA_VERSION as G4_ASSET_PLAN_SCHEMA_VERSION,
    ASSET_REQUIREMENT_SCHEMA_VERSION as G4_ASSET_REQUIREMENT_SCHEMA_VERSION,
    GENERATION_REQUEST_SCHEMA_VERSION as G4_GENERATION_REQUEST_SCHEMA_VERSION,
    RESOLVER_ID as ASSET_RESOLVER_ID,
)
from .audio_timing import AudioCue, AudioStemSet
from .evidence import (
    EpisodeProductionEvidenceRepository,
    EvidenceFact,
    EvidenceRecord,
    GateAppend,
    validated_evidence_snapshot,
)
from .deterministic_effects import (
    FLAME_EXTINGUISH,
    FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND,
    FLAME_EXTINGUISH_RESULT_RECORD_KIND,
    LOCAL_EXPOSURE,
    LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND,
    LOCAL_EXPOSURE_RESULT_RECORD_KIND,
    MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND,
    MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND,
    MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND,
    SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND,
    SCRATCH_LIGHT_RESULT_RECORD_KIND,
    SMOKE,
    SMOKE_REQUIREMENT_RECORD_KIND,
    SMOKE_RESULT_RECORD_KIND,
    append_deterministic_effect_result_chain,
    build_deterministic_effect_result,
    build_flame_extinguish_requirement,
    build_flame_smoke_execution_request,
    build_smoke_requirement,
    resolve_deterministic_effect_result_chain,
    validate_flame_local_exposure_compatibility,
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
from .media import (
    ADMISSION_ID as MEDIA_ADMISSION_ID,
    ASSET_VERSION_SCHEMA_VERSION as G5_ASSET_VERSION_SCHEMA_VERSION,
    GENERATION_RESULT_SCHEMA_VERSION as G5_GENERATION_RESULT_SCHEMA_VERSION,
    MEDIA_MANIFEST_SCHEMA_VERSION as G5_MEDIA_MANIFEST_SCHEMA_VERSION,
    ArtifactRejectedError,
    K2MediaExecutionService,
    WorkerUnavailableError,
)
from .media_candidate_review import CanonicalAssetVersionAuthority
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
    EFFECT_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION,
    PREVIEW_CANDIDATE_SCHEMA_VERSION_V2,
    PREVIEW_CANDIDATE_SCHEMA_VERSION_V3,
    DECODED_FRAME_PIXEL_DIGEST_SPEC,
    TIMELINE_MIX_PARAMETERS,
    TIMELINE_CLIP_SCHEMA_VERSION as LEGACY_TIMELINE_CLIP_SCHEMA_VERSION,
    TIMELINE_TRACK_SCHEMA_VERSION as LEGACY_TIMELINE_TRACK_SCHEMA_VERSION,
    TIMELINE_VERSION_SCHEMA_VERSION_V2,
    TIMELINE_SCHEMA_VERSION_V2,
    build_timeline,
    build_timeline_clip,
    build_composition_result,
    build_effect_preview_candidate,
    build_effect_preview_composition_result,
    build_mask_asset_version_binding,
    build_preview_candidate,
    build_subtitle_manifest,
    build_timeline_input_bundle,
    build_timeline_mix_request,
    build_timeline_track,
    build_timeline_version,
    map_frame_boundary_to_sample,
    map_sample_boundary_to_frame,
    project_timeline_mix_request,
    validate_audio_input_binding,
    validate_composition_result,
    validate_effect_preview_candidate,
    validate_effect_preview_composition_result,
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
from .timeline_editing import (
    TIMELINE_CLIP_SCHEMA_VERSION as EDITING_TIMELINE_CLIP_SCHEMA_VERSION,
    TIMELINE_CLIP_SCHEMA_VERSION_V3 as EDITING_TIMELINE_CLIP_SCHEMA_VERSION_V3,
    TIMELINE_EDIT_COMMAND_SCHEMA_VERSION as EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
    TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2 as EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
    TIMELINE_SCHEMA_VERSION as EDITING_TIMELINE_SCHEMA_VERSION,
    TIMELINE_TRACK_KINDS as EDITING_TIMELINE_TRACK_KINDS,
    TIMELINE_TRACK_SCHEMA_VERSION as EDITING_TIMELINE_TRACK_SCHEMA_VERSION,
    TIMELINE_VERSION_SCHEMA_VERSION as EDITING_TIMELINE_VERSION_SCHEMA_VERSION,
    Timeline as EditingTimeline,
    TimelineClip as EditingTimelineClip,
    TimelineEditCommand as EditingTimelineEditCommand,
    TimelineTrack as EditingTimelineTrack,
    TimelineVersion as EditingTimelineVersion,
    apply_timeline_edit,
    build_output_profile_binding,
    build_timeline as build_editing_timeline,
    build_timeline_edit_command,
    build_timeline_track as build_editing_timeline_track,
    build_timeline_version as build_editing_timeline_version,
    validate_timeline as validate_editing_timeline,
    validate_timeline_edit_chain,
    validate_timeline_snapshot as validate_editing_timeline_snapshot,
    validate_timeline_version as validate_editing_timeline_version,
)
from .rendering import (
    COMPOSITION_PROVENANCE,
    REQUIRED_EFFECT_KINDS,
    build_composition,
    build_composition_version,
    build_render_manifest,
    build_render_runtime_evidence,
    build_render_artifact_evidence,
    build_render_result,
    build_render_candidate,
    canonical_subtitle_timing,
    canonical_subtitle_timing_digest,
    composition_plan_digests,
    render_manifest_digest_specs,
    seal_composition_track_binding,
    validate_composition,
    validate_composition_version,
    validate_render_manifest,
    RenderRuntimeEvidence,
    RenderArtifactEvidence,
    RenderResult,
    RenderCandidate,
    validate_render_toolchain_identity,
)


COMPOSITION_GATE = "G6_COMPOSITION"
M13_EFFECT_COMPOSITION_GATE = "M13_EFFECT_COMPOSITION"
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
TIMELINE_EDITING_DELIVERY_ID = "v5.k2.timeline-editing-delivery.v1"
TIMELINE_EDIT_CREATE_REQUEST_SCHEMA_VERSION = (
    "v5.k2.timeline-edit-create-request.v1"
)
TIMELINE_EDIT_SUCCESSOR_REQUEST_SCHEMA_VERSION = (
    "v5.k2.timeline-edit-successor-request.v1"
)
M13_RENDER_DOMAIN_REQUEST_SCHEMA_VERSION = (
    "v5.k2.composition-render-manifest-request.v1"
)
M13_PREVIEW_STATE_TRANSITIONS = {
    "MEDIA_READY": "PREVIEW_READY",
    "REAL_VIDEO_READY": "REAL_PREVIEW_READY",
}
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
    def compose_timeline_preview_v2(
        self,
        command: Mapping[str, Any],
        *,
        resolved_artifacts: Mapping[str, Any],
    ) -> dict[str, Any]: ...
    def render_candidate(
        self,
        execution_request: Mapping[str, Any],
        *,
        composition_version: Mapping[str, Any],
        composition_command: Mapping[str, Any],
        resolved_artifacts: Mapping[str, Any],
        subtitle_cues: list[Mapping[str, Any]],
        font_projection: Mapping[str, Any] | None,
        font_required_text: str | None,
    ) -> dict[str, Any]: ...
    def inspect_render_candidate(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        storage_binding_ref: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any]: ...
    def execute_flame_smoke(
        self,
        request: Mapping[str, Any],
        *,
        resolved_asset_versions: Mapping[str, Mapping[str, Any]],
        resolved_effect_dependencies: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]: ...
    def execute_deterministic_overlay(
        self,
        request: Mapping[str, Any],
        *,
        resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]: ...
    def inspect_deterministic_overlay_image(
        self, asset: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    def inspect_deterministic_overlay_video(
        self, asset: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    def finalize(self, command: Mapping[str, Any]) -> dict[str, Any]: ...


class RealVideoAuthorityPort(Protocol):
    """Existing V5 owner projection for current immutable M11 videos."""

    def get_revision_bundle(
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        evidence_snapshot: Any | None = None,
    ) -> dict[str, Any]: ...


class IdentityReferenceProjectionReaderPort(Protocol):
    def require_current_identity_reference_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        character_ref: str,
    ) -> dict[str, Any]: ...


class ScriptTextReaderPort(Protocol):
    def get_workspace(
        self, workspace_ref: str, series_ref: str, episode_ref: str
    ) -> dict[str, Any]: ...


class FontAssetAuthorityPort(Protocol):
    def require_current_font_asset_projection(
        self,
        workspace_ref: str,
        production_run_ref: str,
        asset_version_ref: str,
        asset_version_digest: str,
        *,
        required_text: str | None = None,
    ) -> dict[str, Any]: ...


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
        real_video_authority: RealVideoAuthorityPort | None = None,
        glyph_inspection_adapter: (
            DigestPinnedBasePlateGlyphInspectionAdapter | None
        ) = None,
        identity_reference_projection_reader: (
            IdentityReferenceProjectionReaderPort | None
        ) = None,
        script_text_reader: ScriptTextReaderPort | None = None,
        font_asset_authority: FontAssetAuthorityPort | None = None,
        render_toolchain_identity: Mapping[str, Any] | None = None,
    ) -> None:
        self.media = media
        self.evidence = evidence
        self.composition = composition
        self.approval_authority = approval_authority
        self.real_video_authority = real_video_authority
        self.glyph_inspection_adapter = glyph_inspection_adapter
        self.identity_reference_projection_reader = (
            identity_reference_projection_reader
        )
        self.script_text_reader = script_text_reader
        self.font_asset_authority = font_asset_authority
        self.render_toolchain_identity = (
            None
            if render_toolchain_identity is None
            else validate_render_toolchain_identity(render_toolchain_identity)
        )
        self._ref_factory = ref_factory
        self._clock = clock

    def _current_glyph_video_assets(
        self,
        workspace: str,
        run_ref: str,
        *,
        evidence_snapshot: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Resolve only the existing current M11 video authority.

        Direct service fixtures created before the M11 authority was injected
        retain their historical current-media port as a compatibility reader.
        Production assembly always supplies ``real_video_authority``.
        """

        if self.real_video_authority is not None:
            bundle = self.real_video_authority.get_revision_bundle(
                workspace,
                run_ref,
                evidence_snapshot=evidence_snapshot,
            )
            assets = bundle.get("videoAssetVersions")
            lineage = bundle.get("videoLineageState")
            if (
                not isinstance(assets, list)
                or not assets
                or any(not isinstance(item, Mapping) for item in assets)
                or not isinstance(lineage, Mapping)
                or lineage.get("state") != "CURRENT"
                or bundle.get("publicationAllowed") is not False
            ):
                raise UpstreamNotReadyError(
                    "current immutable real-video authority is not ready"
                )
            return [
                deepcopy(dict(item))
                for item in assets
                if isinstance(item, Mapping)
            ]

        verify_media_current = getattr(self.media, "verify_media_current", None)
        if not callable(verify_media_current):
            raise RepositoryUnavailableError(
                "current media validator is unavailable"
            )
        current = verify_media_current(workspace, run_ref)
        assets = current.get("assetVersions") if isinstance(current, Mapping) else None
        if (
            not isinstance(assets, list)
            or any(not isinstance(item, Mapping) for item in assets)
        ):
            raise RepositoryUnavailableError("current media authority is invalid")
        return [
            deepcopy(dict(item))
            for item in assets
            if isinstance(item, Mapping)
        ]

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
    def _timeline_record_idempotency_key(client_key: str, slot: str) -> str:
        return _digest(
            {
                "clientIdempotencyKey": _idempotency_key(client_key),
                "stage": "m13-t1-timeline-editing",
                "slot": _required_ref(slot, "record slot"),
            }
        )

    @staticmethod
    def _timeline_evidence_record(
        *,
        workspace: str,
        run_ref: str,
        record_kind: str,
        record_ref: str,
        record_version: int,
        client_key: str,
        slot: str,
        request_digest: str,
        created_at: str,
        payload: Mapping[str, Any],
    ) -> EvidenceRecord:
        """Build one immutable M13-T1 record in the shared evidence journal."""

        canonical = _immutable_payload(payload, record_kind)
        return EvidenceRecord(
            workspaceRef=_required_ref(workspace, "workspaceRef"),
            productionRunRef=_required_ref(run_ref, "productionRunRef"),
            recordKind=record_kind,
            recordRef=_required_ref(record_ref, "recordRef"),
            recordVersion=_positive_version(record_version, "recordVersion"),
            idempotencyKey=K2DeliveryService._timeline_record_idempotency_key(
                client_key, slot
            ),
            requestDigest=request_digest,
            createdAt=created_at,
            payload=canonical,
            payloadDigest=canonical["payloadDigest"],
        )

    def _timeline_authority_context(
        self,
        workspace: str,
        run_ref: str,
        *,
        expected_run_version: int | None,
    ) -> dict[str, Any]:
        """Resolve the current run, ScriptVersion and StoryboardVersion.

        Timeline commands never get to establish these authority facts.  They
        are re-read from the existing Episode Production root and evidence
        journal immediately before the compare-and-swap append.
        """

        workspace = _required_ref(workspace, "workspaceRef")
        run_ref = _required_ref(run_ref, "productionRunRef")
        try:
            root_service = self.media.assets.shot_graph.root_service
            run = root_service.verify_run_current(workspace, run_ref)
        except AttributeError as exc:
            raise RepositoryUnavailableError(
                "Episode Production root authority is unavailable"
            ) from exc
        if not isinstance(run, Mapping):
            raise RepositoryUnavailableError(
                "Episode Production root projection is invalid"
            )
        run = deepcopy(dict(run))
        graph_service = self.media.assets.shot_graph
        verify_graph_current = getattr(
            graph_service, "verify_shot_graph_current", None
        )
        verified_graph_bundle = None
        if callable(verify_graph_current):
            verified_graph_bundle = verify_graph_current(workspace, run_ref)
            if not isinstance(verified_graph_bundle, Mapping):
                raise RepositoryUnavailableError(
                    "current ShotGraph authority is invalid"
                )
        expected = (
            _positive_version(run.get("version"), "run version")
            if expected_run_version is None
            else _positive_version(expected_run_version, "expectedRunVersion")
        )
        if (
            run.get("workspaceRef") != workspace
            or run.get("productionRunRef") != run_ref
            or run.get("version") != expected
        ):
            raise StaleInputError("Episode Production run version is stale")
        for field in ("projectRef", "seriesRef", "episodeRef", "scriptVersionRef"):
            _required_ref(run.get(field), field)
        upstream = run.get("upstreamSnapshot")
        script = upstream.get("script") if isinstance(upstream, Mapping) else None
        if (
            not isinstance(script, Mapping)
            or script.get("scriptVersionRef") != run["scriptVersionRef"]
            or not _is_sha256(script.get("versionDigest"))
        ):
            raise RepositoryUnavailableError(
                "frozen ScriptVersion authority is invalid"
            )

        snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        matching_gates = [
            gate for gate in snapshot.gates if gate.get("gateName") == "G3_SHOT_GRAPH"
        ]
        if len(matching_gates) != 1:
            raise UpstreamNotReadyError(
                "confirmed StoryboardVersion evidence is unavailable"
            )
        storyboard_facts = [
            fact
            for fact in matching_gates[0].get("facts", [])
            if isinstance(fact, Mapping)
            and fact.get("factKind") == "StoryboardVersion"
        ]
        if len(storyboard_facts) != 1:
            raise UpstreamNotReadyError(
                "confirmed StoryboardVersion evidence is unavailable"
            )
        storyboard = _immutable_payload(
            storyboard_facts[0].get("payload"), "StoryboardVersion"
        )
        graph_facts = [
            fact
            for fact in matching_gates[0].get("facts", [])
            if isinstance(fact, Mapping)
            and fact.get("factKind") == "ExecutableShotGraph"
        ]
        if len(graph_facts) != 1:
            raise UpstreamNotReadyError(
                "ExecutableShotGraph evidence is unavailable"
            )
        graph = _immutable_payload(
            graph_facts[0].get("payload"), "ExecutableShotGraph"
        )
        if (
            storyboard_facts[0].get("factRef")
            != storyboard.get("storyboardVersionRef")
            or storyboard_facts[0].get("payloadDigest")
            != storyboard.get("payloadDigest")
            or storyboard.get("workspaceRef") != workspace
            or storyboard.get("productionRunRef") != run_ref
            or storyboard.get("rootPayloadDigest") != run.get("payloadDigest")
            or storyboard.get("scriptVersionRef") != run["scriptVersionRef"]
            or storyboard.get("scriptVersionDigest") != script["versionDigest"]
            or graph_facts[0].get("factRef")
            != graph.get("executableShotGraphVersionRef")
            or graph_facts[0].get("payloadDigest")
            != graph.get("payloadDigest")
            or graph.get("workspaceRef") != workspace
            or graph.get("productionRunRef") != run_ref
            or graph.get("rootPayloadDigest") != run.get("payloadDigest")
            or graph.get("scriptVersionRef") != run["scriptVersionRef"]
            or graph.get("scriptVersionDigest") != script["versionDigest"]
            or graph.get("storyboardDigest") != storyboard["payloadDigest"]
        ):
            raise StaleInputError("Storyboard/ShotGraph authority is stale")
        if verified_graph_bundle is not None:
            current_graph = verified_graph_bundle.get("executableShotGraph")
            if not isinstance(current_graph, Mapping) or dict(current_graph) != graph:
                raise StaleInputError(
                    "ExecutableShotGraph does not match current authority"
                )
        return {
            "run": run,
            "scriptVersionRef": run["scriptVersionRef"],
            "scriptVersionDigest": script["versionDigest"],
            "storyboardVersionRef": storyboard["storyboardVersionRef"],
            "storyboardVersionDigest": storyboard["payloadDigest"],
            "executableShotGraph": graph,
            "snapshot": snapshot,
        }

    def _timeline_source_resolver(
        self,
        snapshot: Any,
        *,
        authority_context: Mapping[str, Any],
        expected_script_version_ref: str,
        expected_script_version_digest: str,
        expected_timeline_frame_rate: Mapping[str, Any],
        expected_root_digest: str,
        expected_graph_version_ref: str,
        expected_graph_digest: str,
    ) -> Callable[[str, str], Mapping[str, Any] | None]:
        """Project only fully revalidated server-held source authorities."""

        candidates: dict[tuple[str, str], list[dict[str, Any]]] = {}
        workspace = snapshot.workspaceRef
        run_ref = snapshot.productionRunRef
        if authority_context.get("snapshot") is not snapshot:
            raise RepositoryUnavailableError(
                "Timeline source authority context is inconsistent"
            )

        def add(source_type: str, source_ref: Any, payload: Any) -> None:
            if not isinstance(source_ref, str) or not isinstance(payload, Mapping):
                raise RepositoryUnavailableError(
                    "Timeline source authority identity is invalid"
                )
            candidates.setdefault((source_type, source_ref), []).append(
                deepcopy(dict(payload))
            )

        def records(kind: str, identity_field: str) -> list[dict[str, Any]]:
            result: list[dict[str, Any]] = []
            seen: set[str] = set()
            for record in snapshot.records:
                if record.get("recordKind") != kind:
                    continue
                payload = _immutable_payload(record.get("payload"), kind)
                record_version = record.get("recordVersion")
                payload_version = payload.get("version")
                expected_unversioned_record_version = {
                    "AudioInputBinding": 1,
                    "GlyphRevealRequirement": 2,
                    "MaskAssetVersion": 1,
                }.get(kind, 1)
                identity = payload.get(identity_field)
                if (
                    record.get("recordRef") != payload.get(identity_field)
                    or record.get("payloadDigest") != payload["payloadDigest"]
                    or isinstance(record_version, bool)
                    or not isinstance(record_version, int)
                    or record_version < 1
                    or (
                        payload_version is not None
                        and payload_version != record_version
                    )
                    or (
                        payload_version is None
                        and record_version
                        != expected_unversioned_record_version
                    )
                    or not isinstance(identity, str)
                    or identity in seen
                ):
                    raise RepositoryUnavailableError(
                        f"{kind} evidence envelope is invalid"
                    )
                seen.add(identity)
                result.append(payload)
            return result

        # VIDEO sources are accepted only from the real G5 producer fact shape;
        # arbitrary AssetVersion records are not a current media authority.
        g5_asset_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "assetRef",
            "assetVersionRef",
            "version",
            "ordinal",
            "assetRequirementRef",
            "generationRequestRef",
            "generationRequestVersionRef",
            "generationRequestDigest",
            "generationResultRef",
            "generationResultDigest",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "mediaKind",
            "mediaType",
            "storageKey",
            "byteSize",
            "sha256",
            "probe",
            "adapterIdentity",
            "provenance",
            "rightsState",
            "state",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        g4_request_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "generationRequestRef",
            "generationRequestVersionRef",
            "version",
            "ordinal",
            "assetRequirementRef",
            "assetRequirementDigest",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "mediaKind",
            "mediaType",
            "adapterCapability",
            "providerSelection",
            "parameters",
            "state",
            "requestedProvenance",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        g4_media_requirement_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "assetRequirementRef",
            "version",
            "ordinal",
            "requirementKey",
            "requirementType",
            "required",
            "mediaType",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "upstreamAuthorityRequirementKeys",
            "executableShotGraphVersionRef",
            "executableShotGraphDigest",
            "resolutionState",
            "resolutionKind",
            "requestedProvenance",
            "rightsState",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        g5_result_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "generationResultRef",
            "version",
            "ordinal",
            "generationRequestRef",
            "generationRequestVersionRef",
            "generationRequestDigest",
            "jobRef",
            "attemptRef",
            "attemptNumber",
            "adapterIdentity",
            "parameters",
            "mediaKind",
            "mediaType",
            "artifactSha256",
            "artifactByteSize",
            "probe",
            "state",
            "provenance",
            "rightsState",
            "gpuUsed",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        g5_manifest_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "mediaManifestRef",
            "version",
            "rootPayloadDigest",
            "executableShotGraphVersionRef",
            "executableShotGraphDigest",
            "assetResolutionManifestRef",
            "assetResolutionManifestDigest",
            "generationResultRefs",
            "assetVersionRefs",
            "summary",
            "state",
            "executionScope",
            "provenance",
            "gpuUsed",
            "publicationAllowed",
            "createdBy",
            "createdAt",
            "payloadDigest",
        }
        graph_facts = [
            fact
            for gate in snapshot.gates
            if gate.get("gateName") == "G3_SHOT_GRAPH"
            for fact in gate.get("facts", [])
            if isinstance(fact, Mapping)
            and fact.get("factKind") == "ExecutableShotGraph"
        ]
        if len(graph_facts) != 1:
            raise RepositoryUnavailableError(
                "current ExecutableShotGraph authority is ambiguous"
            )
        graph_payload = _immutable_payload(
            graph_facts[0].get("payload"), "ExecutableShotGraph"
        )
        graph_shots = graph_payload.get("shots")
        if (
            graph_payload.get("executableShotGraphVersionRef")
            != expected_graph_version_ref
            or graph_payload.get("payloadDigest") != expected_graph_digest
            or not isinstance(graph_shots, list)
        ):
            raise RepositoryUnavailableError(
                "current ExecutableShotGraph authority is stale"
            )
        graph_shots_by_version = {
            item.get("creativeShotVersionRef"): item
            for item in graph_shots
            if isinstance(item, Mapping)
        }
        if (
            len(graph_shots_by_version) != len(graph_shots)
            or None in graph_shots_by_version
        ):
            raise RepositoryUnavailableError(
                "current ExecutableShotGraph shot identity is invalid"
            )
        validated_videos: dict[str, dict[str, Any]] = {}
        media_gates = [
            gate
            for gate in snapshot.gates
            if gate.get("gateName") == "G5_MEDIA_EXECUTION"
        ]
        if len(media_gates) > 1:
            raise RepositoryUnavailableError("G5 media authority is ambiguous")
        for gate in media_gates:
            if (
                gate.get("workspaceRef") != workspace
                or gate.get("productionRunRef") != run_ref
                or gate.get("rootPayloadDigest") != expected_root_digest
                or gate.get("toState") != "MEDIA_READY"
            ):
                raise RepositoryUnavailableError("G5 media gate is stale")
            facts = gate.get("facts")
            if not isinstance(facts, list):
                raise RepositoryUnavailableError("G5 media facts are invalid")
            manifest_facts = [
                fact
                for fact in facts
                if isinstance(fact, Mapping)
                and fact.get("factKind") == "MediaManifest"
            ]
            if len(manifest_facts) != 1:
                raise RepositoryUnavailableError(
                    "G5 MediaManifest authority is ambiguous"
                )
            manifest_fact = manifest_facts[0]
            manifest = _immutable_payload(
                manifest_fact.get("payload"), "G5 MediaManifest"
            )
            asset_plan_gates = [
                item
                for item in snapshot.gates
                if item.get("gateName") == "G4_ASSET_RESOLUTION"
            ]
            if len(asset_plan_gates) != 1:
                raise RepositoryUnavailableError(
                    "G4 AssetResolution authority is ambiguous"
                )
            asset_plan_gate = asset_plan_gates[0]
            plan_facts = [
                fact
                for fact in asset_plan_gate.get("facts", [])
                if isinstance(fact, Mapping)
                and fact.get("factKind") == "AssetResolutionManifest"
            ]
            if len(plan_facts) != 1:
                raise RepositoryUnavailableError(
                    "G4 AssetResolutionManifest authority is ambiguous"
                )
            plan_fact = plan_facts[0]
            plan = _immutable_payload(
                plan_fact.get("payload"), "G4 AssetResolutionManifest"
            )
            if (
                plan.get("schemaVersion") != G4_ASSET_PLAN_SCHEMA_VERSION
                or asset_plan_gate.get("workspaceRef") != workspace
                or asset_plan_gate.get("productionRunRef") != run_ref
                or asset_plan_gate.get("toState") != "ASSETS_READY"
                or asset_plan_gate.get("rootPayloadDigest")
                != expected_root_digest
                or plan.get("rootPayloadDigest") != expected_root_digest
                or plan.get("executableShotGraphVersionRef")
                != expected_graph_version_ref
                or plan.get("executableShotGraphDigest")
                != expected_graph_digest
                or plan_fact.get("factRef")
                != plan.get("assetResolutionManifestRef")
                or plan_fact.get("factVersion") != plan.get("version")
                or plan_fact.get("payloadDigest") != plan["payloadDigest"]
            ):
                raise RepositoryUnavailableError(
                    "G4 AssetResolutionManifest authority is stale"
                )
            request_facts = [
                fact
                for fact in asset_plan_gate.get("facts", [])
                if isinstance(fact, Mapping)
                and str(fact.get("factKind", "")).startswith(
                    "GenerationRequest:"
                )
            ]
            requirement_facts = [
                fact
                for fact in asset_plan_gate.get("facts", [])
                if isinstance(fact, Mapping)
                and str(fact.get("factKind", "")).startswith(
                    "AssetRequirement:"
                )
            ]
            requests_by_ref: dict[str, dict[str, Any]] = {}
            requirements_by_ref: dict[str, dict[str, Any]] = {}
            for requirement_fact in requirement_facts:
                requirement = _immutable_payload(
                    requirement_fact.get("payload"), "G4 AssetRequirement"
                )
                requirement_ref = requirement.get("assetRequirementRef")
                if (
                    requirement.get("schemaVersion")
                    != G4_ASSET_REQUIREMENT_SCHEMA_VERSION
                    or requirement_fact.get("factKind")
                    != f"AssetRequirement:{requirement.get('ordinal'):04d}"
                    or requirement_fact.get("factRef") != requirement_ref
                    or requirement_fact.get("factVersion")
                    != requirement.get("version")
                    or requirement_fact.get("payloadDigest")
                    != requirement.get("payloadDigest")
                    or requirement.get("workspaceRef") != workspace
                    or requirement.get("productionRunRef") != run_ref
                    or requirement_ref in requirements_by_ref
                ):
                    raise RepositoryUnavailableError(
                        "G4 AssetRequirement authority is invalid"
                    )
                requirements_by_ref[requirement_ref] = requirement
            for request_fact in request_facts:
                request = _immutable_payload(
                    request_fact.get("payload"), "G4 GenerationRequest"
                )
                request_ref = request.get("generationRequestRef")
                shot = graph_shots_by_version.get(
                    request.get("creativeShotVersionRef")
                )
                requirement = requirements_by_ref.get(
                    request.get("assetRequirementRef")
                )
                if (
                    set(request) != g4_request_fields
                    or request.get("schemaVersion")
                    != G4_GENERATION_REQUEST_SCHEMA_VERSION
                    or request_fact.get("factKind")
                    != f"GenerationRequest:{request.get('ordinal'):04d}"
                    or request_fact.get("factRef")
                    != request.get("generationRequestVersionRef")
                    or request_fact.get("factVersion") != request.get("version")
                    or request_fact.get("payloadDigest")
                    != request.get("payloadDigest")
                    or request.get("workspaceRef") != workspace
                    or request.get("productionRunRef") != run_ref
                    or request.get("state") != "READY_FOR_DISPATCH"
                    or request.get("providerSelection") != "UNSELECTED"
                    or request.get("createdBy") != ASSET_RESOLVER_ID
                    or request.get("publicationAllowed") is not False
                    or request_ref in requests_by_ref
                    or not isinstance(shot, Mapping)
                    or request.get("creativeShotRef")
                    != shot.get("creativeShotRef")
                    or request.get("creativeShotDigest")
                    != shot.get("payloadDigest")
                    or not isinstance(requirement, Mapping)
                    or set(requirement) != g4_media_requirement_fields
                    or request.get("assetRequirementDigest")
                    != requirement.get("payloadDigest")
                    or request.get("creativeShotRef")
                    != requirement.get("creativeShotRef")
                    or request.get("creativeShotVersionRef")
                    != requirement.get("creativeShotVersionRef")
                    or request.get("creativeShotDigest")
                    != requirement.get("creativeShotDigest")
                    or request.get("mediaType") != requirement.get("mediaType")
                    or requirement.get("required") is not True
                    or requirement.get("requirementType")
                    != f"shot-{request.get('mediaKind')}"
                    or requirement.get("resolutionState")
                    != "GENERATION_REQUESTED"
                    or requirement.get("resolutionKind")
                    != "V4_ADAPTER_REQUIRED"
                    or requirement.get("executableShotGraphVersionRef")
                    != expected_graph_version_ref
                    or requirement.get("executableShotGraphDigest")
                    != expected_graph_digest
                    or requirement.get("createdBy") != ASSET_RESOLVER_ID
                    or requirement.get("publicationAllowed") is not False
                ):
                    raise RepositoryUnavailableError(
                        "G4 GenerationRequest authority is invalid"
                    )
                requests_by_ref[request_ref] = request
            plan_request_refs = plan.get("generationRequestRefs")
            plan_requirement_refs = plan.get("assetRequirementRefs")
            generation_requested_requirement_refs = {
                ref
                for ref, item in requirements_by_ref.items()
                if item.get("resolutionState") == "GENERATION_REQUESTED"
            }
            if (
                not isinstance(plan_request_refs, list)
                or len(set(plan_request_refs)) != len(plan_request_refs)
                or set(plan_request_refs) != set(requests_by_ref)
                or not isinstance(plan_requirement_refs, list)
                or len(set(plan_requirement_refs)) != len(plan_requirement_refs)
                or set(plan_requirement_refs) != set(requirements_by_ref)
                or {
                    item.get("assetRequirementRef")
                    for item in requests_by_ref.values()
                }
                != generation_requested_requirement_refs
            ):
                raise RepositoryUnavailableError(
                    "G4 AssetResolutionManifest membership is stale"
                )
            if (
                set(manifest) != g5_manifest_fields
                or manifest.get("schemaVersion")
                != G5_MEDIA_MANIFEST_SCHEMA_VERSION
                or manifest_fact.get("factRef")
                != manifest.get("mediaManifestRef")
                or manifest_fact.get("factVersion") != manifest.get("version")
                or manifest_fact.get("payloadDigest") != manifest["payloadDigest"]
                or manifest.get("workspaceRef") != workspace
                or manifest.get("productionRunRef") != run_ref
                or manifest.get("rootPayloadDigest") != expected_root_digest
                or manifest.get("executableShotGraphVersionRef")
                != expected_graph_version_ref
                or manifest.get("executableShotGraphDigest")
                != expected_graph_digest
                or manifest.get("assetResolutionManifestRef")
                != plan.get("assetResolutionManifestRef")
                or manifest.get("assetResolutionManifestDigest")
                != plan.get("payloadDigest")
                or manifest.get("state") != "MEDIA_VERIFIED"
                or manifest.get("executionScope") != "SINGLE_EPISODE"
                or manifest.get("createdBy") != MEDIA_ADMISSION_ID
                or manifest.get("publicationAllowed") is not False
            ):
                raise RepositoryUnavailableError(
                    "G5 MediaManifest authority is stale"
                )
            result_facts = [
                fact
                for fact in facts
                if isinstance(fact, Mapping)
                and str(fact.get("factKind", "")).startswith(
                    "GenerationResult:"
                )
            ]
            results_by_ref: dict[str, dict[str, Any]] = {}
            for result_fact in result_facts:
                result = _immutable_payload(
                    result_fact.get("payload"), "G5 GenerationResult"
                )
                result_ref = result.get("generationResultRef")
                request = requests_by_ref.get(
                    result.get("generationRequestRef")
                )
                if (
                    set(result) != g5_result_fields
                    or result.get("schemaVersion")
                    != G5_GENERATION_RESULT_SCHEMA_VERSION
                    or isinstance(result.get("ordinal"), bool)
                    or not isinstance(result.get("ordinal"), int)
                    or result_fact.get("factKind")
                    != f"GenerationResult:{result.get('ordinal'):04d}"
                    or result_fact.get("factRef") != result_ref
                    or result_fact.get("factVersion") != result.get("version")
                    or result_fact.get("payloadDigest")
                    != result.get("payloadDigest")
                    or result.get("workspaceRef") != workspace
                    or result.get("productionRunRef") != run_ref
                    or result_ref in results_by_ref
                    or not isinstance(request, Mapping)
                    or result.get("ordinal") != request.get("ordinal")
                    or result.get("generationRequestVersionRef")
                    != request.get("generationRequestVersionRef")
                    or result.get("generationRequestDigest")
                    != request.get("payloadDigest")
                    or result.get("parameters") != request.get("parameters")
                    or result.get("mediaKind") != request.get("mediaKind")
                    or result.get("mediaType") != request.get("mediaType")
                    or result.get("state") != "VERIFIED"
                    or result.get("provenance") != "LOCAL_EVIDENCE"
                    or result.get("rightsState") != "LOCAL_EVIDENCE_ONLY"
                    or result.get("gpuUsed") is not False
                    or result.get("publicationAllowed") is not False
                    or result.get("createdBy") != MEDIA_ADMISSION_ID
                ):
                    raise RepositoryUnavailableError(
                        "G5 GenerationResult authority is invalid"
                    )
                results_by_ref[result_ref] = result
            manifest_result_refs = manifest.get("generationResultRefs")
            if (
                not isinstance(manifest_result_refs, list)
                or len(set(manifest_result_refs)) != len(manifest_result_refs)
                or set(manifest_result_refs) != set(results_by_ref)
                or len(result_facts) != len(manifest_result_refs)
            ):
                raise RepositoryUnavailableError(
                    "G5 MediaManifest GenerationResult membership is stale"
                )
            asset_facts = [
                fact
                for fact in facts
                if isinstance(fact, Mapping)
                and str(fact.get("factKind", "")).startswith("AssetVersion:")
            ]
            manifest_asset_refs = manifest.get("assetVersionRefs")
            if (
                not isinstance(manifest_asset_refs, list)
                or len(set(manifest_asset_refs)) != len(manifest_asset_refs)
                or len({fact.get("factRef") for fact in asset_facts})
                != len(asset_facts)
                or {fact.get("factRef") for fact in asset_facts}
                != set(manifest_asset_refs)
                or len(asset_facts) != len(manifest_asset_refs)
            ):
                raise RepositoryUnavailableError(
                    "G5 MediaManifest AssetVersion membership is stale"
                )
            validated_asset_payloads: list[dict[str, Any]] = []
            for fact in asset_facts:
                payload = fact.get("payload")
                if not isinstance(payload, Mapping):
                    raise RepositoryUnavailableError(
                        "G5 AssetVersion authority is invalid"
                    )
                asset = _immutable_payload(payload, "G5 AssetVersion")
                request = requests_by_ref.get(
                    asset.get("generationRequestRef")
                )
                result = results_by_ref.get(asset.get("generationResultRef"))
                if (
                    set(asset) != g5_asset_fields
                    or asset.get("schemaVersion")
                    != G5_ASSET_VERSION_SCHEMA_VERSION
                    or isinstance(asset.get("ordinal"), bool)
                    or not isinstance(asset.get("ordinal"), int)
                    or fact.get("factKind")
                    != f"AssetVersion:{asset.get('ordinal'):04d}"
                    or fact.get("factRef") != asset.get("assetVersionRef")
                    or fact.get("factVersion") != asset.get("version")
                    or fact.get("payloadDigest") != asset["payloadDigest"]
                    or asset.get("workspaceRef") != workspace
                    or asset.get("productionRunRef") != run_ref
                    or not isinstance(request, Mapping)
                    or asset.get("ordinal") != request.get("ordinal")
                    or asset.get("assetRequirementRef")
                    != request.get("assetRequirementRef")
                    or asset.get("generationRequestVersionRef")
                    != request.get("generationRequestVersionRef")
                    or asset.get("generationRequestDigest")
                    != request.get("payloadDigest")
                    or asset.get("creativeShotRef")
                    != request.get("creativeShotRef")
                    or asset.get("creativeShotVersionRef")
                    != request.get("creativeShotVersionRef")
                    or asset.get("creativeShotDigest")
                    != request.get("creativeShotDigest")
                    or asset.get("mediaKind") != request.get("mediaKind")
                    or asset.get("mediaType") != request.get("mediaType")
                    or not isinstance(result, Mapping)
                    or asset.get("generationResultDigest")
                    != result.get("payloadDigest")
                    or asset.get("ordinal") != result.get("ordinal")
                    or asset.get("generationRequestRef")
                    != result.get("generationRequestRef")
                    or asset.get("generationRequestVersionRef")
                    != result.get("generationRequestVersionRef")
                    or asset.get("generationRequestDigest")
                    != result.get("generationRequestDigest")
                    or asset.get("mediaKind") != result.get("mediaKind")
                    or asset.get("mediaType") != result.get("mediaType")
                    or asset.get("sha256") != result.get("artifactSha256")
                    or asset.get("byteSize") != result.get("artifactByteSize")
                    or asset.get("probe") != result.get("probe")
                    or asset.get("adapterIdentity")
                    != result.get("adapterIdentity")
                    or asset.get("state") != "REGISTERED"
                    or asset.get("provenance") != "LOCAL_EVIDENCE"
                    or asset.get("rightsState") != "LOCAL_EVIDENCE_ONLY"
                    or asset.get("publicationAllowed") is not False
                    or asset.get("createdBy") != MEDIA_ADMISSION_ID
                ):
                    raise RepositoryUnavailableError(
                        "G5 AssetVersion authority is invalid"
                    )
                validated_asset_payloads.append(asset)
                if asset.get("mediaKind") != "video":
                    continue
                if asset.get("mediaType") != "video/mp4":
                    raise RepositoryUnavailableError(
                        "G5 VIDEO AssetVersion media type is invalid"
                    )
                video_facts = self._base_video_facts(asset)
                projected = {
                    **asset,
                    "frameCount": video_facts["frameCount"],
                    "frameRate": video_facts["frameRate"],
                }
                ref = _required_ref(asset.get("assetVersionRef"), "assetVersionRef")
                previous = validated_videos.get(ref)
                if previous is not None and previous != projected:
                    raise RepositoryUnavailableError(
                        "G5 VIDEO AssetVersion authority is ambiguous"
                    )
                validated_videos[ref] = projected
                add("ASSET_VERSION", ref, projected)

            manifest_summary = manifest.get("summary")
            if (
                len(validated_asset_payloads) != len(requests_by_ref)
                or {
                    item.get("generationRequestRef")
                    for item in validated_asset_payloads
                }
                != set(requests_by_ref)
                or {
                    item.get("generationResultRef")
                    for item in validated_asset_payloads
                }
                != set(results_by_ref)
                or len(
                    {
                        item.get("generationRequestRef")
                        for item in results_by_ref.values()
                    }
                )
                != len(results_by_ref)
                or not isinstance(manifest_summary, Mapping)
                or manifest_summary
                != {
                    "requested": len(requests_by_ref),
                    "verifiedResults": len(results_by_ref),
                    "registeredAssets": len(validated_asset_payloads),
                    "videoAssets": sum(
                        item.get("mediaKind") == "video"
                        for item in validated_asset_payloads
                    ),
                    "audioAssets": sum(
                        item.get("mediaKind") == "audio"
                        for item in validated_asset_payloads
                    ),
                    "failed": 0,
                }
            ):
                raise RepositoryUnavailableError(
                    "G5 media semantic closure is stale"
                )

            # Reuse the existing producer-side current-authority validator when
            # the production service is present.  The schema/envelope checks
            # above remain necessary for repository adapters used by restore;
            # this call additionally closes the live G1/G3/G4/G5 lineage and
            # re-probes the registered artifacts before their AssetVersions can
            # be consumed by a Timeline.
            verify_media_current = getattr(
                self.media, "verify_media_current", None
            )
            if not callable(verify_media_current):
                raise RepositoryUnavailableError(
                    "current G5 media validator is unavailable"
                )
            current_media = verify_media_current(workspace, run_ref)
            if not isinstance(current_media, Mapping):
                raise RepositoryUnavailableError(
                    "current G5 media authority is invalid"
                )
            current_assets = current_media.get("assetVersions")
            if (
                current_media.get("mediaManifest") != manifest
                or current_media.get("assetResolutionManifest") != plan
                or not isinstance(current_assets, list)
                or sorted(
                    (deepcopy(dict(item)) for item in current_assets),
                    key=lambda item: item.get("assetVersionRef", ""),
                )
                != sorted(
                    validated_asset_payloads,
                    key=lambda item: item.get("assetVersionRef", ""),
                )
            ):
                raise RepositoryUnavailableError(
                    "current G5 media authority changed during resolution"
                )

        # Audio is reconstructed through the existing closed TimelineInputBundle
        # validator.  This revalidates AudioInputBinding, Cue, StemMember and
        # StemSet shapes and their exact cross-record semantic closure.
        binding_wrappers: dict[str, AudioInputBinding] = {}
        for payload in records("AudioInputBinding", "audioInputBindingRef"):
            wrapper = validate_audio_input_binding(payload)
            mapping = wrapper.as_dict()
            if (
                mapping.get("workspaceRef") != workspace
                or mapping.get("productionRunRef") != run_ref
                or mapping["assetVersionRef"] in binding_wrappers
            ):
                raise RepositoryUnavailableError(
                    "AudioInputBinding authority is ambiguous or stale"
                )
            binding_wrappers[mapping["assetVersionRef"]] = wrapper
        cue_records = records("AudioCue", "cueVersionRef")
        cue_payloads = {item["cueVersionRef"]: item for item in cue_records}
        if len(cue_payloads) != len(cue_records):
            raise RepositoryUnavailableError("AudioCue authority is ambiguous")
        stem_sets = records("AudioStemSet", "stemSetVersionRef")
        for stem_set in stem_sets:
            members = stem_set.get("members")
            if not isinstance(members, list) or not members:
                raise RepositoryUnavailableError(
                    "AudioStemSet authority has no members"
                )
            asset_refs = {
                item.get("sourceAssetVersionRef")
                for item in members
                if isinstance(item, Mapping)
            }
            cue_refs = {
                item.get("sourceCueVersionRef")
                for item in members
                if isinstance(item, Mapping)
                and item.get("sourceCueVersionRef") is not None
            }
            if (
                len(asset_refs) == 0
                or any(ref not in binding_wrappers for ref in asset_refs)
                or any(ref not in cue_payloads for ref in cue_refs)
            ):
                raise RepositoryUnavailableError(
                    "AudioStemSet authority closure is incomplete"
                )
            selected_bindings = [
                binding_wrappers[str(ref)] for ref in sorted(asset_refs)
            ]
            selected_cues = [cue_payloads[str(ref)] for ref in sorted(cue_refs)]
            bundle_ref = "m13-source-authority-" + _digest(
                {
                    "stemSetVersionRef": stem_set.get("stemSetVersionRef"),
                    "stemSetDigest": stem_set.get("payloadDigest"),
                }
            )[:32]
            bundle = validate_timeline_input_bundle(
                build_timeline_input_bundle(
                    {
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "timelineInputBundleRef": bundle_ref,
                        "scriptVersionRef": expected_script_version_ref,
                        "scriptVersionDigest": expected_script_version_digest,
                    },
                    audio_input_bindings=selected_bindings,
                    audio_cues=selected_cues,
                    audio_stem_set=stem_set,
                    audio_stem_members=members,
                    glyph_reveal_requirements=(),
                    mask_asset_bindings=(),
                )
            ).as_dict()
            for binding in bundle["audioInputBindings"]:
                asset = deepcopy(dict(binding["assetVersion"]))
                asset["sampleRate"] = binding["sampleRate"]
                asset["sampleCount"] = binding["sampleCount"]
                add(
                    "AUDIO_ASSET_VERSION",
                    binding["assetVersionRef"],
                    asset,
                )
            for cue in bundle["audioCues"]:
                projected = deepcopy(dict(cue))
                subtitle = projected.get("subtitleTimingReference")
                if isinstance(subtitle, Mapping):
                    matching_members = [
                        member
                        for member in bundle["audioStemMembers"]
                        if member.get("sourceCueVersionRef")
                        == projected["cueVersionRef"]
                    ]
                    if len(matching_members) != 1:
                        raise RepositoryUnavailableError(
                            "AudioCue Timeline stem placement is ambiguous"
                        )
                    member = matching_members[0]
                    sample_rate = stem_set["sampleRate"]
                    rate = self._editing_frame_rate(
                        expected_timeline_frame_rate
                    )

                    def timeline_frame(source_sample: int) -> int:
                        timeline_sample = (
                            member["stemStartSample"]
                            + source_sample
                            - member["sourceStartSample"]
                        )
                        return map_sample_boundary_to_frame(
                            timeline_sample,
                            sample_rate=sample_rate,
                            frame_rate_numerator=rate["numerator"],
                            frame_rate_denominator=rate["denominator"],
                        )

                    projected.update(
                        {
                            "textStart": subtitle.get("textRangeStart"),
                            "textEndExclusive": subtitle.get(
                                "textRangeEndExclusive"
                            ),
                            "textDigest": subtitle.get("textDigest"),
                            "language": subtitle.get("language"),
                            "timelineStartFrameInclusive": timeline_frame(
                                projected["sourceStartSample"]
                            ),
                            "timelineEndFrameExclusive": timeline_frame(
                                projected["sourceEndSample"]
                            ),
                            "timelineWordTiming": [
                                {
                                    "wordRef": word["wordRef"],
                                    "textStart": word["textRangeStart"],
                                    "textEndExclusive": word[
                                        "textRangeEndExclusive"
                                    ],
                                    "timelineStartFrameInclusive": timeline_frame(
                                        word["sourceStartSample"]
                                    ),
                                    "timelineEndFrameExclusive": timeline_frame(
                                        word["sourceEndSample"]
                                    ),
                                    "textDigest": word["textDigest"],
                                }
                                for word in projected["wordTimings"]
                            ],
                        }
                    )
                add("AUDIO_CUE", projected["cueVersionRef"], projected)
            add("AUDIO_STEM_SET", stem_set["stemSetVersionRef"], stem_set)
            for member in bundle["audioStemMembers"]:
                projected = {
                    **deepcopy(dict(member)),
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "scriptVersionRef": expected_script_version_ref,
                    "scriptVersionDigest": expected_script_version_digest,
                    "sampleRate": stem_set["sampleRate"],
                }
                add("AUDIO_STEM_MEMBER", member["stemMemberRef"], projected)

        mask_records = records("MaskAssetVersion", "assetVersionRef")
        mask_payloads = {item["assetVersionRef"]: item for item in mask_records}
        if len(mask_payloads) != len(mask_records):
            raise RepositoryUnavailableError(
                "MaskAssetVersion authority is ambiguous"
            )
        for payload in records("GlyphRevealRequirement", "requirementRef"):
            requirement = GlyphRevealRequirementV2.from_mapping(payload)
            if (
                requirement.workspace_ref != workspace
                or requirement.production_run_ref != run_ref
            ):
                raise RepositoryUnavailableError(
                    "GlyphRevealRequirement authority scope is stale"
                )
            canonical_masks: list[dict[str, Any]] = []
            for ordinal, expected_mask in enumerate(
                requirement.mask_asset_version_bindings, start=1
            ):
                raw = mask_payloads.get(expected_mask["assetVersionRef"])
                if raw is None:
                    raise RepositoryUnavailableError(
                        "GlyphRevealRequirement mask authority is missing"
                    )
                binding = self._mask_binding_wrapper(
                    workspace=workspace,
                    run_ref=run_ref,
                    glyph_slug=requirement.glyph_slug,
                    ordinal=ordinal,
                    asset=raw,
                ).as_dict()
                expected_projection = {
                    "assetVersionRef": raw.get("assetVersionRef"),
                    "assetVersionDigest": raw.get("payloadDigest"),
                    "fileDigest": f"sha256:{raw.get('sha256')}",
                    "pixelDigest": raw.get("pixelDigest"),
                    "pixelDigestSpec": raw.get("pixelDigestSpec"),
                    "pixelMode": raw.get("pixelMode"),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "glyphSlug": raw.get("glyphSlug"),
                    "revealOrdinal": raw.get("revealOrdinal"),
                    "assetRole": raw.get("assetRole"),
                    "glyphManifestDigest": raw.get("glyphManifestDigest"),
                }
                if (
                    _contains_path_authority(raw)
                    or expected_projection != expected_mask
                    or binding["assetVersionDigest"]
                    != expected_mask["assetVersionDigest"]
                    or binding["fileDigest"] != expected_mask["fileDigest"]
                    or binding["pixelDigest"] != expected_mask["pixelDigest"]
                ):
                    raise RepositoryUnavailableError(
                        "GlyphRevealRequirement mask authority is stale"
                    )
                canonical_masks.append(raw)
                add("MASK_ASSET_VERSION", raw["assetVersionRef"], raw)

            base = validated_videos.get(requirement.base_plate_asset_version_ref)
            if base is None:
                # A Glyph v2 requirement is intentionally bound to the
                # immutable M11 real-video AssetVersion, not to the historical
                # G5 generated-video schema above.  Admit only that one exact
                # current producer projection, and only after the registered
                # requirement and every registered mask have been revalidated.
                current_assets = self._current_glyph_video_assets(
                    workspace,
                    run_ref,
                    evidence_snapshot=snapshot,
                )
                matches = [
                    deepcopy(dict(item))
                    for item in current_assets
                    if isinstance(item, Mapping)
                    and item.get("assetVersionRef")
                    == requirement.base_plate_asset_version_ref
                ]
                if (
                    len(matches) != 1
                    or self.glyph_inspection_adapter is None
                ):
                    raise RepositoryUnavailableError(
                        "GlyphRevealRequirement current base authority is stale"
                    )
                current_base = matches[0]
                shot = graph_shots_by_version.get(
                    current_base.get("creativeShotVersionRef")
                )
                if (
                    not isinstance(shot, Mapping)
                    or shot.get("creativeShotRef")
                    != requirement.target_shot_ref
                    or current_base.get("creativeShotRef")
                    != requirement.target_shot_ref
                    or current_base.get("creativeShotDigest")
                    != shot.get("payloadDigest")
                ):
                    raise RepositoryUnavailableError(
                        "GlyphRevealRequirement current Shot authority is stale"
                    )
                execution = build_glyph_reveal_execution_request_v2(
                    requirement,
                    base_plate_asset=current_base,
                    mask_assets=canonical_masks,
                    inspection_adapter=self.glyph_inspection_adapter,
                )
                output = execution.get("output")
                if not isinstance(output, Mapping):
                    raise RepositoryUnavailableError(
                        "GlyphRevealRequirement current base probe is invalid"
                    )
                base = {
                    **current_base,
                    "frameCount": output.get("totalFrames"),
                    "frameRate": self._editing_frame_rate(
                        output.get("frameRate")
                    ),
                }
                validated_videos[requirement.base_plate_asset_version_ref] = base
                add(
                    "ASSET_VERSION",
                    requirement.base_plate_asset_version_ref,
                    base,
                )
            if (
                base.get("payloadDigest")
                != requirement.base_plate_asset_version_digest
                or f"sha256:{base.get('sha256')}"
                != requirement.base_plate_file_digest
                or requirement.target_shot_ref
                not in {
                    base.get("creativeShotRef"),
                    base.get("creativeShotVersionRef"),
                }
            ):
                raise RepositoryUnavailableError(
                    "GlyphRevealRequirement base plate authority is stale"
                )
            add("EFFECT_REQUIREMENT", requirement.requirement_ref, payload)

        # M13-E1 stores one closed five-record Result chain in the existing
        # evidence journal.  Resolve through the production validator, then
        # prove that every member came from this exact snapshot before
        # projecting it into Timeline source authority.
        effect_record_specs = (
            (SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (SMOKE_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (
                MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND,
                "executionRequestRef",
            ),
            (
                MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND,
                "artifactEvidenceRef",
            ),
            (
                MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND,
                "runtimeEvidenceRef",
            ),
            (SCRATCH_LIGHT_RESULT_RECORD_KIND, "resultRef"),
            (LOCAL_EXPOSURE_RESULT_RECORD_KIND, "resultRef"),
            (FLAME_EXTINGUISH_RESULT_RECORD_KIND, "resultRef"),
            (SMOKE_RESULT_RECORD_KIND, "resultRef"),
        )
        effect_records: dict[tuple[str, str], dict[str, Any]] = {}
        for record_kind, identity_field in effect_record_specs:
            for payload in records(record_kind, identity_field):
                key = (record_kind, payload[identity_field])
                if key in effect_records:
                    raise RepositoryUnavailableError(
                        "deterministic Effect evidence is ambiguous"
                    )
                effect_records[key] = payload
        result_records = [
            (record_kind, payload)
            for (record_kind, _), payload in effect_records.items()
            if record_kind
            in {
                SCRATCH_LIGHT_RESULT_RECORD_KIND,
                LOCAL_EXPOSURE_RESULT_RECORD_KIND,
                FLAME_EXTINGUISH_RESULT_RECORD_KIND,
                SMOKE_RESULT_RECORD_KIND,
            }
        ]
        used_effect_records: set[tuple[str, str]] = set()
        resolved_effect_chains: list[dict[str, Any]] = []
        for result_record_kind, stored_result in result_records:
            try:
                chain = resolve_deterministic_effect_result_chain(
                    self.evidence,
                    workspace_ref=workspace,
                    production_run_ref=run_ref,
                    result_ref=stored_result["resultRef"],
                    result_digest=stored_result["payloadDigest"],
                )
            except EpisodeProductionError as exc:
                raise RepositoryUnavailableError(
                    "deterministic Effect Result chain is invalid"
                ) from exc
            resolved = chain.as_dict()
            resolved_effect_chains.append(resolved)
            requirement = resolved["requirement"]
            result = resolved["result"]
            requirement_record_kinds = {
                LOCAL_EXPOSURE: LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND,
                FLAME_EXTINGUISH: FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND,
                SMOKE: SMOKE_REQUIREMENT_RECORD_KIND,
            }
            result_record_kinds = {
                LOCAL_EXPOSURE: LOCAL_EXPOSURE_RESULT_RECORD_KIND,
                FLAME_EXTINGUISH: FLAME_EXTINGUISH_RESULT_RECORD_KIND,
                SMOKE: SMOKE_RESULT_RECORD_KIND,
            }
            requirement_record_kind = requirement_record_kinds.get(
                requirement["effectMode"],
                SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND,
            )
            expected_result_kind = result_record_kinds.get(
                result["effectMode"],
                SCRATCH_LIGHT_RESULT_RECORD_KIND,
            )
            members = (
                (
                    requirement_record_kind,
                    requirement["requirementRef"],
                    requirement,
                ),
                (
                    MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND,
                    resolved["executionRequest"]["executionRequestRef"],
                    resolved["executionRequest"],
                ),
                (
                    MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND,
                    resolved["artifactEvidence"]["artifactEvidenceRef"],
                    resolved["artifactEvidence"],
                ),
                (
                    MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND,
                    resolved["runtimeEvidence"]["runtimeEvidenceRef"],
                    resolved["runtimeEvidence"],
                ),
                (expected_result_kind, result["resultRef"], result),
            )
            if (
                result_record_kind != expected_result_kind
                or requirement.get("workspaceRef") != workspace
                or requirement.get("productionRunRef") != run_ref
                or any(
                    effect_records.get((kind, reference)) != payload
                    for kind, reference, payload in members
                )
            ):
                raise RepositoryUnavailableError(
                    "deterministic Effect snapshot closure is stale"
                )
            used_effect_records.update(
                (kind, reference) for kind, reference, _ in members
            )
            base = validated_videos.get(
                requirement["basePlateAssetVersionRef"]
            )
            if (
                base is None
                or base.get("payloadDigest")
                != requirement["basePlateAssetVersionDigest"]
                or f"sha256:{base.get('sha256')}"
                != requirement["basePlateFileDigest"]
                or base.get("creativeShotRef")
                != requirement["targetShotRef"]
                or base.get("creativeShotVersionRef")
                != requirement["targetShotVersionRef"]
                or base.get("creativeShotDigest")
                != requirement["targetShotVersionDigest"]
                or requirement["frameRangeEndExclusive"]
                > base.get("frameCount", -1)
            ):
                raise RepositoryUnavailableError(
                    "deterministic Effect Requirement base/shot is stale"
                )
            add(
                "EFFECT_REQUIREMENT",
                requirement["requirementRef"],
                requirement,
            )
            add(
                "EFFECT_RESULT",
                result["resultRef"],
                {
                    **result,
                    "targetShotRef": requirement["targetShotRef"],
                    "frameRangeStartInclusive": requirement[
                        "frameRangeStartInclusive"
                    ],
                    "frameRangeEndExclusive": requirement[
                        "frameRangeEndExclusive"
                    ],
                },
            )
        exposure_by_requirement = {
            chain["requirement"]["requirementRef"]: chain
            for chain in resolved_effect_chains
            if chain["requirement"]["effectMode"] == LOCAL_EXPOSURE
        }
        if len(exposure_by_requirement) != sum(
            chain["requirement"]["effectMode"] == LOCAL_EXPOSURE
            for chain in resolved_effect_chains
        ):
            raise RepositoryUnavailableError(
                "Local Exposure Result authority is ambiguous"
            )
        for chain in resolved_effect_chains:
            flame = chain["requirement"]
            if flame["effectMode"] != FLAME_EXTINGUISH:
                continue
            exposure_chain = exposure_by_requirement.get(
                flame["localExposureRequirementRef"]
            )
            if exposure_chain is None:
                raise RepositoryUnavailableError(
                    "Flame Extinguish requires one existing Local Exposure Result"
                )
            exposure = exposure_chain["requirement"]
            exposure_result = exposure_chain["result"]
            flame_request = chain["executionRequest"]
            if (
                exposure["payloadDigest"]
                != flame["localExposureRequirementDigest"]
                or flame_request.get("localExposureRequirementRef")
                != exposure["requirementRef"]
                or flame_request.get("localExposureRequirementDigest")
                != exposure["payloadDigest"]
                or flame_request.get("localExposureResultRef")
                != exposure_result["resultRef"]
                or flame_request.get("localExposureResultDigest")
                != exposure_result["payloadDigest"]
                or any(
                    exposure[field] != flame[field]
                    for field in (
                        "workspaceRef",
                        "productionRunRef",
                        "targetShotRef",
                        "targetShotVersionRef",
                        "targetShotVersionDigest",
                        "basePlateAssetVersionRef",
                        "basePlateAssetVersionDigest",
                        "basePlateFileDigest",
                        "basePlatePixelDigest",
                        "frameRangeStartInclusive",
                        "frameRangeEndExclusive",
                    )
                )
                or exposure["maskAssetVersionRef"]
                != flame["flameMaskAssetVersionRef"]
                or exposure["maskAssetVersionDigest"]
                != flame["flameMaskAssetVersionDigest"]
                or exposure["maskFileDigest"] != flame["flameMaskFileDigest"]
                or exposure["maskPixelDigest"]
                != flame["flameMaskPixelDigest"]
            ):
                raise RepositoryUnavailableError(
                    "Flame Extinguish Local Exposure binding is stale"
                )
        if used_effect_records != set(effect_records):
            raise RepositoryUnavailableError(
                "deterministic Effect evidence chain is incomplete"
            )

        # E3 uses the same generic journal and Timeline source types, but its
        # five typed records remain independently closed so an older masked
        # surface record can never be substituted into an overlay chain.
        from .deterministic_overlays import (
            FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND,
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
            NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND,
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
            OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND,
            OVERLAY_EXECUTION_REQUEST_RECORD_KIND,
            OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND,
        )

        overlay_specs = (
            (NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND, "requirementRef"),
            (OVERLAY_EXECUTION_REQUEST_RECORD_KIND, "executionRequestRef"),
            (OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND, "artifactEvidenceRef"),
            (OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND, "runtimeEvidenceRef"),
            (NAMEPLATE_TEXT_RESULT_RECORD_KIND, "resultRef"),
            (FACE_MARK_COMPENSATION_RESULT_RECORD_KIND, "resultRef"),
        )
        overlay_records: dict[tuple[str, str], dict[str, Any]] = {}
        for record_kind, identity_field in overlay_specs:
            for payload in records(record_kind, identity_field):
                key = (record_kind, payload[identity_field])
                if key in overlay_records:
                    raise RepositoryUnavailableError(
                        "deterministic overlay evidence is ambiguous"
                    )
                overlay_records[key] = payload
        overlay_result_kinds = {
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
        }
        used_overlay_records: set[tuple[str, str]] = set()
        for (result_kind, _), stored_result in overlay_records.items():
            if result_kind not in overlay_result_kinds:
                continue
            chain = self._resolve_effect_result_chain(
                context=authority_context,
                result_ref=stored_result["resultRef"],
                result_digest=stored_result["payloadDigest"],
            )
            requirement = chain["requirement"]
            request = chain["executionRequest"]
            artifact = chain["artifactEvidence"]
            runtime = chain["runtimeEvidence"]
            result = chain["result"]
            expected_requirement_kind = (
                NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND
                if requirement["effectMode"] == "NAMEPLATE_TEXT"
                else FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND
            )
            expected_result_kind = (
                NAMEPLATE_TEXT_RESULT_RECORD_KIND
                if result["effectMode"] == "NAMEPLATE_TEXT"
                else FACE_MARK_COMPENSATION_RESULT_RECORD_KIND
            )
            members = (
                (
                    expected_requirement_kind,
                    requirement["requirementRef"],
                    requirement,
                ),
                (
                    OVERLAY_EXECUTION_REQUEST_RECORD_KIND,
                    request["executionRequestRef"],
                    request,
                ),
                (
                    OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND,
                    artifact["artifactEvidenceRef"],
                    artifact,
                ),
                (
                    OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND,
                    runtime["runtimeEvidenceRef"],
                    runtime,
                ),
                (expected_result_kind, result["resultRef"], result),
            )
            base = validated_videos.get(
                requirement["basePlateAssetVersionRef"]
            )
            if (
                result_kind != expected_result_kind
                or any(
                    overlay_records.get((kind, reference)) != payload
                    for kind, reference, payload in members
                )
                or base is None
                or base.get("payloadDigest")
                != requirement["basePlateAssetVersionDigest"]
                or f"sha256:{base.get('sha256')}"
                != requirement["basePlateFileDigest"]
                or base.get("creativeShotRef")
                != requirement["targetShotRef"]
                or base.get("creativeShotVersionRef")
                != requirement["targetShotVersionRef"]
                or base.get("creativeShotDigest")
                != requirement["targetShotVersionDigest"]
            ):
                raise RepositoryUnavailableError(
                    "deterministic overlay snapshot closure is stale"
                )
            used_overlay_records.update(
                (kind, reference) for kind, reference, _ in members
            )
            add(
                "EFFECT_REQUIREMENT",
                requirement["requirementRef"],
                requirement,
            )
            add(
                "EFFECT_RESULT",
                result["resultRef"],
                {
                    **result,
                    "targetShotRef": requirement["targetShotRef"],
                    "frameRangeStartInclusive": requirement[
                        "frameRangeStartInclusive"
                    ],
                    "frameRangeEndExclusive": requirement[
                        "frameRangeEndExclusive"
                    ],
                },
            )
        if used_overlay_records != set(overlay_records):
            raise RepositoryUnavailableError(
                "deterministic overlay evidence chain is incomplete"
            )

        # E4 is a fifth independently typed Result chain in the same generic
        # evidence journal.  Re-resolve it and prove every resolved member was
        # observed in this exact snapshot before it becomes Timeline source
        # authority; the current media closure is re-read by the dispatcher.
        from .distance_state import (
            DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND,
            DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND,
            DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND,
            DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND,
            DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
        )

        distance_specs = (
            (
                DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND,
                "requirementRef",
            ),
            (
                DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND,
                "executionRequestRef",
            ),
            (
                DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND,
                "artifactEvidenceRef",
            ),
            (
                DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND,
                "runtimeEvidenceRef",
            ),
            (
                DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
                "resultRef",
            ),
        )
        distance_records: dict[tuple[str, str], dict[str, Any]] = {}
        for record_kind, identity_field in distance_specs:
            for payload in records(record_kind, identity_field):
                key = (record_kind, payload[identity_field])
                if key in distance_records:
                    raise RepositoryUnavailableError(
                        "Distance/State evidence is ambiguous"
                    )
                distance_records[key] = payload
        used_distance_records: set[tuple[str, str]] = set()
        for (record_kind, _), stored_result in distance_records.items():
            if record_kind != DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND:
                continue
            chain = self._resolve_effect_result_chain(
                context=authority_context,
                result_ref=stored_result["resultRef"],
                result_digest=stored_result["payloadDigest"],
            )
            requirement = chain["requirement"]
            request = chain["executionRequest"]
            artifact = chain["artifactEvidence"]
            runtime = chain["runtimeEvidence"]
            result = chain["result"]
            members = (
                (
                    DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND,
                    requirement["requirementRef"],
                    requirement,
                ),
                (
                    DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND,
                    request["executionRequestRef"],
                    request,
                ),
                (
                    DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND,
                    artifact["artifactEvidenceRef"],
                    artifact,
                ),
                (
                    DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND,
                    runtime["runtimeEvidenceRef"],
                    runtime,
                ),
                (
                    DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
                    result["resultRef"],
                    result,
                ),
            )
            base = validated_videos.get(
                requirement["basePlateAssetVersionRef"]
            )
            if (
                requirement.get("effectMode")
                != "DISTANCE_STATE_TRANSITION"
                or result.get("effectMode")
                != "DISTANCE_STATE_TRANSITION"
                or any(
                    distance_records.get((kind, reference)) != payload
                    for kind, reference, payload in members
                )
                or base is None
                or base.get("payloadDigest")
                != requirement["basePlateAssetVersionDigest"]
                or f"sha256:{base.get('sha256')}"
                != requirement["basePlateFileDigest"]
                or base.get("creativeShotRef")
                != requirement["targetShotRef"]
                or base.get("creativeShotVersionRef")
                != requirement["targetShotVersionRef"]
                or base.get("creativeShotDigest")
                != requirement["targetShotVersionDigest"]
            ):
                raise RepositoryUnavailableError(
                    "Distance/State snapshot closure is stale"
                )
            used_distance_records.update(
                (kind, reference) for kind, reference, _ in members
            )
            add(
                "EFFECT_REQUIREMENT",
                requirement["requirementRef"],
                requirement,
            )
            add(
                "EFFECT_RESULT",
                result["resultRef"],
                {
                    **result,
                    "targetShotRef": requirement["targetShotRef"],
                    "frameRangeStartInclusive": requirement[
                        "frameRangeStartInclusive"
                    ],
                    "frameRangeEndExclusive": requirement[
                        "frameRangeEndExclusive"
                    ],
                },
            )
        if used_distance_records != set(distance_records):
            raise RepositoryUnavailableError(
                "Distance/State evidence chain is incomplete"
            )

        def resolve(source_type: str, source_ref: str) -> Mapping[str, Any] | None:
            matches = candidates.get((source_type, source_ref), [])
            if len(matches) > 1:
                raise RepositoryUnavailableError(
                    "Timeline source authority is ambiguous"
                )
            return None if not matches else deepcopy(matches[0])

        return resolve

    @staticmethod
    def _editing_payload_records(
        snapshot: Any,
        *,
        record_kind: str,
        schema_version: str | frozenset[str],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        schema_versions = (
            frozenset({schema_version})
            if isinstance(schema_version, str)
            else schema_version
        )
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for record in snapshot.records:
            if record.get("recordKind") != record_kind:
                continue
            payload = record.get("payload")
            if not isinstance(payload, Mapping) or payload.get(
                "schemaVersion"
            ) not in schema_versions:
                continue
            canonical = _immutable_payload(payload, record_kind)
            if canonical["payloadDigest"] != record.get("payloadDigest"):
                raise RepositoryUnavailableError(
                    f"{record_kind} evidence digest is inconsistent"
                )
            result.append((deepcopy(dict(record)), canonical))
        return result

    @staticmethod
    def _timeline_authority_records_or_facts(snapshot: Any) -> tuple[dict[str, Any], ...]:
        """Audit and return every Timeline authority envelope.

        ``Timeline`` and ``TimelineVersion`` are authority record kinds.  An
        unknown schema on either kind is therefore evidence corruption, not an
        unrelated record that can safely be ignored.
        """

        schemas_by_kind = {
            "Timeline": {
                EDITING_TIMELINE_SCHEMA_VERSION: "editing",
                TIMELINE_SCHEMA_VERSION_V2: "legacy",
            },
            "TimelineVersion": {
                EDITING_TIMELINE_VERSION_SCHEMA_VERSION: "editing",
                TIMELINE_VERSION_SCHEMA_VERSION_V2: "legacy",
                TIMELINE_SCHEMA_VERSION: "legacy",
            },
            "TimelineTrack": {
                EDITING_TIMELINE_TRACK_SCHEMA_VERSION: "editing",
                LEGACY_TIMELINE_TRACK_SCHEMA_VERSION: "legacy",
            },
            "TimelineClip": {
                EDITING_TIMELINE_CLIP_SCHEMA_VERSION: "editing",
                EDITING_TIMELINE_CLIP_SCHEMA_VERSION_V3: "editing",
                LEGACY_TIMELINE_CLIP_SCHEMA_VERSION: "legacy",
            },
            "TimelineEditOperation": {
                EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION: "editing",
                EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2: "editing",
            },
        }
        identity_by_kind = {
            "Timeline": "timelineRef",
            "TimelineVersion": "timelineVersionRef",
            "TimelineTrack": "trackRef",
            "TimelineClip": "clipRef",
            "TimelineEditOperation": "operationRef",
        }
        result: list[dict[str, Any]] = []
        classifications: list[str] = []

        def audit(
            envelope: Mapping[str, Any],
            *,
            kind_field: str,
            ref_field: str,
            version_field: str,
        ) -> None:
            kind = envelope.get(kind_field)
            if kind not in schemas_by_kind:
                return
            payload = envelope.get("payload")
            if not isinstance(payload, Mapping):
                raise RepositoryUnavailableError(
                    f"{kind} authority payload is missing"
                )
            canonical = _immutable_payload(payload, str(kind))
            schema = canonical.get("schemaVersion")
            classification = schemas_by_kind[str(kind)].get(schema)
            if classification is None:
                raise RepositoryUnavailableError(
                    f"{kind} authority schema is unsupported"
                )
            if classification == "editing" and kind_field == "factKind":
                raise RepositoryUnavailableError(
                    "M13 Timeline authority must use the record journal"
                )
            identity_field = identity_by_kind[str(kind)]
            envelope_version = envelope.get(version_field)
            if (
                envelope.get(ref_field) != canonical.get(identity_field)
                or envelope.get("payloadDigest") != canonical["payloadDigest"]
                or isinstance(envelope_version, bool)
                or not isinstance(envelope_version, int)
                or envelope_version < 1
            ):
                raise RepositoryUnavailableError(
                    f"{kind} authority envelope is invalid"
                )
            if kind == "Timeline" and envelope_version != 1:
                raise RepositoryUnavailableError(
                    "Timeline root authority version is invalid"
                )
            if kind == "TimelineVersion":
                payload_version = canonical.get("versionNumber")
                if payload_version is None:
                    payload_version = canonical.get("version")
                if payload_version != envelope_version:
                    raise RepositoryUnavailableError(
                        "TimelineVersion authority version is invalid"
                    )
            if kind == "TimelineEditOperation" and envelope_version != 1:
                raise RepositoryUnavailableError(
                    "TimelineEditOperation authority version is invalid"
                )
            result.append(deepcopy(dict(envelope)))
            classifications.append(classification)

        for record in snapshot.records:
            if isinstance(record, Mapping):
                audit(
                    record,
                    kind_field="recordKind",
                    ref_field="recordRef",
                    version_field="recordVersion",
                )
        for gate in snapshot.gates:
            for fact in gate.get("facts", []):
                if isinstance(fact, Mapping):
                    audit(
                        fact,
                        kind_field="factKind",
                        ref_field="factRef",
                        version_field="factVersion",
                    )
        observed = set(classifications)
        if observed == {"editing", "legacy"}:
            raise RepositoryUnavailableError(
                "legacy and M13 Timeline authorities cannot coexist"
            )
        return tuple(result)

    @staticmethod
    def _has_editing_timeline_authority(snapshot: Any) -> bool:
        editing_schemas = {
            EDITING_TIMELINE_SCHEMA_VERSION,
            EDITING_TIMELINE_VERSION_SCHEMA_VERSION,
            EDITING_TIMELINE_TRACK_SCHEMA_VERSION,
            EDITING_TIMELINE_CLIP_SCHEMA_VERSION,
            EDITING_TIMELINE_CLIP_SCHEMA_VERSION_V3,
            EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
            EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        }
        return any(
            isinstance(item.get("payload"), Mapping)
            and item["payload"].get("schemaVersion") in editing_schemas
            for item in K2DeliveryService._timeline_authority_records_or_facts(
                snapshot
            )
        )

    @staticmethod
    def _reject_legacy_timeline_write_if_editing_authority(snapshot: Any) -> None:
        if K2DeliveryService._has_editing_timeline_authority(snapshot):
            raise IdempotencyConflictError(
                "M13 Timeline authority exists; legacy Timeline writes are closed"
            )

    def _restore_editing_timeline(
        self,
        context: Mapping[str, Any],
        *,
        timeline_version_ref: str | None = None,
    ) -> dict[str, Any]:
        snapshot = context["snapshot"]
        authorities = self._timeline_authority_records_or_facts(snapshot)
        editing_schemas = {
            EDITING_TIMELINE_SCHEMA_VERSION,
            EDITING_TIMELINE_VERSION_SCHEMA_VERSION,
            EDITING_TIMELINE_TRACK_SCHEMA_VERSION,
            EDITING_TIMELINE_CLIP_SCHEMA_VERSION,
            EDITING_TIMELINE_CLIP_SCHEMA_VERSION_V3,
            EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
            EDITING_TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        }
        if any(
            item["payload"].get("schemaVersion") not in editing_schemas
            for item in authorities
        ):
            raise RepositoryUnavailableError(
                "non-M13 Timeline authority cannot coexist with M13 restore"
            )
        roots = self._editing_payload_records(
            snapshot,
            record_kind="Timeline",
            schema_version=EDITING_TIMELINE_SCHEMA_VERSION,
        )
        if len(roots) != 1:
            if not roots:
                raise UpstreamNotReadyError("M13 Timeline is not ready")
            raise RepositoryUnavailableError("Timeline root authority is ambiguous")
        root_record, root_payload = roots[0]
        root = validate_editing_timeline(root_payload)
        root_mapping = root.as_dict()
        run = context["run"]
        if (
            root_record.get("recordRef") != root_mapping["timelineRef"]
            or root_record.get("recordVersion") != 1
            or root_record.get("createdAt") != root_mapping["createdAt"]
            or not _is_sha256(root_record.get("idempotencyKey"))
            or not _is_sha256(root_record.get("requestDigest"))
            or any(
                root_mapping.get(field) != run.get(field)
                for field in (
                    "workspaceRef",
                    "projectRef",
                    "seriesRef",
                    "episodeRef",
                    "productionRunRef",
                )
            )
        ):
            raise RepositoryUnavailableError("Timeline root evidence is invalid")

        version_records = self._editing_payload_records(
            snapshot,
            record_kind="TimelineVersion",
            schema_version=EDITING_TIMELINE_VERSION_SCHEMA_VERSION,
        )
        if any(
            item[1].get("timelineRef") != root_mapping["timelineRef"]
            for item in version_records
        ):
            raise RepositoryUnavailableError(
                "TimelineVersion authority has an orphan root"
            )
        version_records.sort(key=lambda item: item[1].get("versionNumber", -1))
        if not version_records:
            raise RepositoryUnavailableError("TimelineVersion history is missing")
        wrappers: list[EditingTimelineVersion] = []
        refs: set[str] = set()
        predecessor: EditingTimelineVersion | None = None
        for index, (record, payload) in enumerate(version_records, start=1):
            if (
                payload.get("versionNumber") != index
                or record.get("recordRef") != payload.get("timelineVersionRef")
                or record.get("recordVersion") != index
                or record.get("createdAt") != payload.get("createdAt")
                or not _is_sha256(record.get("idempotencyKey"))
                or not _is_sha256(record.get("requestDigest"))
                or payload.get("timelineVersionRef") in refs
            ):
                raise RepositoryUnavailableError(
                    "TimelineVersion journal is not a contiguous chain"
                )
            wrapper = validate_editing_timeline_version(
                payload,
                predecessor=predecessor,
            )
            refs.add(wrapper.as_dict()["timelineVersionRef"])
            wrappers.append(wrapper)
            predecessor = wrapper
        server_profile = self._server_output_profile(
            context["executableShotGraph"]
        )
        if any(
            item.as_dict().get("outputProfileBindings") != [server_profile]
            for item in wrappers
        ):
            raise StaleInputError(
                "Timeline OutputProfileBinding is not current server authority"
            )
        expected_script = {
            "scriptVersionRef": context["scriptVersionRef"],
            "scriptVersionDigest": context["scriptVersionDigest"],
        }
        expected_storyboard = {
            "storyboardVersionRef": context["storyboardVersionRef"],
            "storyboardVersionDigest": context["storyboardVersionDigest"],
        }
        all_track_records = self._editing_payload_records(
            snapshot,
            record_kind="TimelineTrack",
            schema_version=EDITING_TIMELINE_TRACK_SCHEMA_VERSION,
        )
        all_clip_records = self._editing_payload_records(
            snapshot,
            record_kind="TimelineClip",
            schema_version=frozenset(
                {
                    EDITING_TIMELINE_CLIP_SCHEMA_VERSION,
                    EDITING_TIMELINE_CLIP_SCHEMA_VERSION_V3,
                }
            ),
        )
        if any(
            payload.get("timelineVersionRef") not in refs
            for _, payload in (*all_track_records, *all_clip_records)
        ):
            raise RepositoryUnavailableError(
                "Timeline Track/Clip evidence has an orphan version"
            )
        source_resolver = self._timeline_source_resolver(
            snapshot,
            authority_context=context,
            expected_script_version_ref=context["scriptVersionRef"],
            expected_script_version_digest=context["scriptVersionDigest"],
            expected_timeline_frame_rate=wrappers[0].as_dict()["frameRate"],
            expected_root_digest=context["run"]["payloadDigest"],
            expected_graph_version_ref=context["executableShotGraph"][
                "executableShotGraphVersionRef"
            ],
            expected_graph_digest=context["executableShotGraph"][
                "payloadDigest"
            ],
        )
        snapshots_by_ref: dict[str, Any] = {}
        track_batches: dict[
            str, list[tuple[dict[str, Any], dict[str, Any]]]
        ] = {}
        clip_batches: dict[
            str, list[tuple[dict[str, Any], dict[str, Any]]]
        ] = {}
        for index, version in enumerate(wrappers):
            version_mapping = version.as_dict()
            version_ref = version_mapping["timelineVersionRef"]
            version_number = version_mapping["versionNumber"]
            track_records = [
                item
                for item in all_track_records
                if item[1].get("timelineVersionRef") == version_ref
            ]
            clip_records = [
                item
                for item in all_clip_records
                if item[1].get("timelineVersionRef") == version_ref
            ]
            track_batches[version_ref] = track_records
            clip_batches[version_ref] = clip_records
            if any(
                record.get("recordRef") != payload.get("trackRef")
                or record.get("recordVersion") != version_number
                or record.get("createdAt") != version_mapping["createdAt"]
                or not _is_sha256(record.get("idempotencyKey"))
                or not _is_sha256(record.get("requestDigest"))
                for record, payload in track_records
            ) or any(
                record.get("recordRef") != payload.get("clipRef")
                or record.get("recordVersion") != version_number
                or record.get("createdAt") != version_mapping["createdAt"]
                or not _is_sha256(record.get("idempotencyKey"))
                or not _is_sha256(record.get("requestDigest"))
                for record, payload in clip_records
            ):
                raise RepositoryUnavailableError(
                    "Timeline Track/Clip evidence envelope is invalid"
                )
            restored = validate_editing_timeline_snapshot(
                version,
                [
                    EditingTimelineTrack.from_mapping(item[1])
                    for item in track_records
                ],
                [
                    EditingTimelineClip.from_mapping(item[1])
                    for item in clip_records
                ],
                timeline=root,
                predecessor=None if index == 0 else wrappers[index - 1],
                source_resolver=source_resolver,
                expected_script=expected_script,
                expected_storyboard=expected_storyboard,
            )
            snapshots_by_ref[version_ref] = restored

        edit_records: list[tuple[dict[str, Any], EditingTimelineEditCommand]] = []
        for record in snapshot.records:
            if record.get("recordKind") != "TimelineEditOperation":
                continue
            canonical = _immutable_payload(
                record.get("payload"), "TimelineEditOperation"
            )
            command = EditingTimelineEditCommand.from_mapping(canonical)
            command_mapping = command.as_dict()
            if (
                record.get("recordRef") != command_mapping["operationRef"]
                or record.get("recordVersion") != 1
                or record.get("createdAt") != command_mapping["createdAt"]
                or record.get("idempotencyKey")
                != self._timeline_record_idempotency_key(
                    command_mapping["idempotencyKey"], "edit-operation"
                )
                or not _is_sha256(record.get("requestDigest"))
            ):
                raise RepositoryUnavailableError(
                    "TimelineEditOperation evidence envelope is invalid"
                )
            edit_records.append((deepcopy(dict(record)), command))
        validate_timeline_edit_chain(
            wrappers,
            [item[1] for item in edit_records],
        )
        version_records_by_ref = {
            payload["timelineVersionRef"]: record
            for record, payload in version_records
        }
        initial_version = wrappers[0].as_dict()
        initial_track_batch = sorted(
            track_batches[initial_version["timelineVersionRef"]],
            key=lambda item: (item[1]["order"], item[1]["trackRef"]),
        )
        initial_clip_batch = sorted(
            clip_batches[initial_version["timelineVersionRef"]],
            key=lambda item: item[1]["clipRef"],
        )
        initial_batch_records = [
            root_record,
            version_records_by_ref[initial_version["timelineVersionRef"]],
            *(item[0] for item in initial_track_batch),
            *(item[0] for item in initial_clip_batch),
        ]
        initial_seed = self._timeline_create_batch_request_digest(
            context,
            root,
            wrappers[0],
            [item[1] for item in initial_track_batch],
            [item[1] for item in initial_clip_batch],
        )
        initial_expected_keys = [
            self._timeline_record_idempotency_key(
                initial_seed, "timeline-root"
            ),
            self._timeline_record_idempotency_key(
                initial_seed, "timeline-version"
            ),
            *(
                self._timeline_record_idempotency_key(
                    initial_seed, f"track:{index}"
                )
                for index in range(
                    len(track_batches[initial_version["timelineVersionRef"]])
                )
            ),
            *(
                self._timeline_record_idempotency_key(
                    initial_seed, f"clip:{index}"
                )
                for index in range(
                    len(clip_batches[initial_version["timelineVersionRef"]])
                )
            ),
        ]
        if (
            any(
                item.get("createdAt") != initial_version["createdAt"]
                for item in initial_batch_records
            )
            or root_record.get("requestDigest") != initial_seed
            or len(
                {item.get("requestDigest") for item in initial_batch_records}
            )
            != 1
            or [
                item.get("idempotencyKey") for item in initial_batch_records
            ]
            != initial_expected_keys
        ):
            raise RepositoryUnavailableError(
                "Timeline create evidence batch metadata is inconsistent"
            )
        edit_records_by_successor = {
            command.as_dict()["newTimelineVersionRef"]: (record, command)
            for record, command in edit_records
        }
        for version in wrappers[1:]:
            version_mapping = version.as_dict()
            version_ref = version_mapping["timelineVersionRef"]
            edit_record, edit_command = edit_records_by_successor[version_ref]
            command_mapping = edit_command.as_dict()
            client_key = command_mapping["idempotencyKey"]
            expected_edit_request_digest = _digest(
                {
                    "schemaVersion": TIMELINE_EDIT_SUCCESSOR_REQUEST_SCHEMA_VERSION,
                    "workspaceRef": root_mapping["workspaceRef"],
                    "productionRunRef": root_mapping["productionRunRef"],
                    "operationRef": command_mapping["operationRef"],
                    "idempotencyKey": client_key,
                    "expectedRunVersion": context["run"]["version"],
                    "parentTimelineVersionRef": command_mapping[
                        "parentTimelineVersionRef"
                    ],
                    "parentTimelineVersionDigest": command_mapping[
                        "parentTimelineVersionDigest"
                    ],
                    "editCommand": {
                        "operation": command_mapping["operation"],
                        "arguments": command_mapping["arguments"],
                    },
                    "runDigest": context["run"]["payloadDigest"],
                    "scriptVersionRef": context["scriptVersionRef"],
                    "scriptVersionDigest": context["scriptVersionDigest"],
                    "storyboardVersionRef": context["storyboardVersionRef"],
                    "storyboardVersionDigest": context[
                        "storyboardVersionDigest"
                    ],
                }
            )
            batch_records = [
                edit_record,
                version_records_by_ref[version_ref],
                *(
                    item[0]
                    for item in sorted(
                        track_batches[version_ref],
                        key=lambda item: (
                            item[1]["order"], item[1]["trackRef"]
                        ),
                    )
                ),
                *(
                    item[0]
                    for item in sorted(
                        clip_batches[version_ref],
                        key=lambda item: item[1]["clipRef"],
                    )
                ),
            ]
            expected_keys = [
                self._timeline_record_idempotency_key(
                    client_key, "edit-operation"
                ),
                self._timeline_record_idempotency_key(
                    client_key, "timeline-version"
                ),
                *(
                    self._timeline_record_idempotency_key(
                        client_key, f"track:{index}"
                    )
                    for index in range(len(track_batches[version_ref]))
                ),
                *(
                    self._timeline_record_idempotency_key(
                        client_key, f"clip:{index}"
                    )
                    for index in range(len(clip_batches[version_ref]))
                ),
            ]
            if (
                [item.get("idempotencyKey") for item in batch_records]
                != expected_keys
                or edit_record.get("requestDigest")
                != expected_edit_request_digest
                or any(
                    item.get("requestDigest")
                    != edit_record.get("requestDigest")
                    for item in batch_records
                )
                or any(
                    item.get("createdAt") != command_mapping["createdAt"]
                    for item in batch_records
                )
            ):
                raise RepositoryUnavailableError(
                    "Timeline edit evidence batch metadata is inconsistent"
                )
        edits_by_successor = {
            item[1].as_dict()["newTimelineVersionRef"]: item[1]
            for item in edit_records
        }
        for predecessor_index, (predecessor, successor) in enumerate(
            zip(wrappers, wrappers[1:]), start=1
        ):
            predecessor_ref = predecessor.as_dict()["timelineVersionRef"]
            successor_ref = successor.as_dict()["timelineVersionRef"]
            predecessor_snapshot = snapshots_by_ref[predecessor_ref]
            persisted_successor = snapshots_by_ref[successor_ref]
            replayed_successor = apply_timeline_edit(
                predecessor_snapshot.timeline_version,
                predecessor_snapshot.tracks,
                predecessor_snapshot.clips,
                edits_by_successor[successor_ref],
                existing_timeline_versions=wrappers[:predecessor_index],
                timeline=root,
                source_resolver=source_resolver,
                expected_script=expected_script,
                expected_storyboard=expected_storyboard,
            )
            if (
                replayed_successor.timeline_version.as_dict()
                != persisted_successor.timeline_version.as_dict()
                or [item.as_dict() for item in replayed_successor.tracks]
                != [item.as_dict() for item in persisted_successor.tracks]
                or [item.as_dict() for item in replayed_successor.clips]
                != [item.as_dict() for item in persisted_successor.clips]
            ):
                raise RepositoryUnavailableError(
                    "Timeline successor does not match its edit operation"
                )

        selected_ref = (
            wrappers[-1].as_dict()["timelineVersionRef"]
            if timeline_version_ref is None
            else timeline_version_ref
        )
        selected = snapshots_by_ref.get(selected_ref)
        if selected is None:
            raise RecordNotFoundError("TimelineVersion was not found")
        return {
            "timeline": root,
            "timelineVersion": selected.timeline_version,
            "tracks": selected.tracks,
            "clips": selected.clips,
            "versionHistory": tuple(wrappers),
        }

    @staticmethod
    def _editing_projection(
        restored: Mapping[str, Any],
        *,
        evidence_revision: str,
        replayed: bool,
        edit_operation: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = {
            "timeline": restored["timeline"].as_dict(),
            "timelineVersion": restored["timelineVersion"].as_dict(),
            "tracks": [item.as_dict() for item in restored["tracks"]],
            "clips": [item.as_dict() for item in restored["clips"]],
            "lineage": [
                {
                    "timelineVersionRef": item.as_dict()["timelineVersionRef"],
                    "versionNumber": item.as_dict()["versionNumber"],
                    "payloadDigest": item.as_dict()["payloadDigest"],
                    "parentTimelineVersionRef": item.as_dict()[
                        "parentTimelineVersionRef"
                    ],
                    "parentTimelineVersionDigest": item.as_dict()[
                        "parentTimelineVersionDigest"
                    ],
                }
                for item in restored["versionHistory"]
            ],
            "stale": False,
            "publicationAllowed": False,
            "evidenceRevision": evidence_revision,
            "idempotentReplay": replayed,
        }
        if edit_operation is not None:
            result["editOperation"] = deepcopy(dict(edit_operation))
        return result

    @staticmethod
    def _editing_frame_rate(value: Any) -> dict[str, int]:
        if isinstance(value, bool):
            raise RepositoryUnavailableError("ShotGraph frameRate is invalid")
        if isinstance(value, int):
            numerator, denominator = value, 1
        elif isinstance(value, Mapping) and set(value) == {
            "numerator",
            "denominator",
        }:
            numerator, denominator = value["numerator"], value["denominator"]
        else:
            raise RepositoryUnavailableError("ShotGraph frameRate is invalid")
        if (
            isinstance(numerator, bool)
            or not isinstance(numerator, int)
            or isinstance(denominator, bool)
            or not isinstance(denominator, int)
            or numerator < 1
            or denominator < 1
        ):
            raise RepositoryUnavailableError("ShotGraph frameRate is invalid")
        common = gcd(numerator, denominator)
        return {
            "numerator": numerator // common,
            "denominator": denominator // common,
        }

    @classmethod
    def _server_output_profile(cls, graph: Mapping[str, Any]) -> dict[str, Any]:
        """Derive the only T1 OutputProfileBinding from current ShotGraph facts."""

        output = graph.get("output")
        if not isinstance(output, Mapping):
            raise RepositoryUnavailableError("ShotGraph output is invalid")
        frame_rate = cls._editing_frame_rate(output.get("frameRate"))
        width = _positive_version(output.get("width"), "canvasWidth")
        height = _positive_version(output.get("height"), "canvasHeight")
        aspect_common = gcd(width, height)
        output_digest = _digest(dict(output))
        return build_output_profile_binding(
            {
                "outputProfileRef": f"m13-output-profile-{output_digest[:32]}",
                "outputProfileDigest": output_digest,
                "canvasWidth": width,
                "canvasHeight": height,
                "frameRate": frame_rate,
                "pixelAspectRatio": {"numerator": 1, "denominator": 1},
                "displayAspectRatio": {
                    "numerator": width // aspect_common,
                    "denominator": height // aspect_common,
                },
            }
        )

    @staticmethod
    def _timeline_create_batch_request_digest(
        context: Mapping[str, Any],
        timeline: EditingTimeline | Mapping[str, Any],
        timeline_version: EditingTimelineVersion | Mapping[str, Any],
        tracks: Sequence[EditingTimelineTrack | Mapping[str, Any]],
        clips: Sequence[EditingTimelineClip | Mapping[str, Any]],
    ) -> str:
        """Seal the initial journal batch using only persisted/current facts.

        The Timeline ref embeds the digest of the exact client create command.
        Everything else here can be reconstructed during restart restore, so a
        coordinated SQL rewrite of requestDigest and the slot keys cannot mint
        a different create batch without also changing sealed authority data.
        """

        def mapping(value: Any) -> dict[str, Any]:
            if hasattr(value, "as_dict"):
                value = value.as_dict()
            if not isinstance(value, Mapping):
                raise RepositoryUnavailableError(
                    "Timeline create batch payload is invalid"
                )
            return deepcopy(dict(value))

        root = mapping(timeline)
        version = mapping(timeline_version)
        track_payloads = sorted(
            (mapping(item) for item in tracks),
            key=lambda item: (item.get("order", -1), item.get("trackRef", "")),
        )
        clip_payloads = sorted(
            (mapping(item) for item in clips),
            key=lambda item: item.get("clipRef", ""),
        )
        run = context.get("run")
        graph = context.get("executableShotGraph")
        if not isinstance(run, Mapping) or not isinstance(graph, Mapping):
            raise RepositoryUnavailableError(
                "Timeline create authority context is invalid"
            )
        return _digest(
            {
                "schemaVersion": TIMELINE_EDIT_CREATE_REQUEST_SCHEMA_VERSION,
                "timelineRef": root.get("timelineRef"),
                "timelineDigest": root.get("payloadDigest"),
                "timelineVersionRef": version.get("timelineVersionRef"),
                "timelineVersionDigest": version.get("payloadDigest"),
                "trackDigests": [item.get("payloadDigest") for item in track_payloads],
                "clipDigests": [item.get("payloadDigest") for item in clip_payloads],
                "workspaceRef": root.get("workspaceRef"),
                "productionRunRef": root.get("productionRunRef"),
                "expectedRunVersion": run.get("version"),
                "runDigest": run.get("payloadDigest"),
                "scriptVersionRef": context.get("scriptVersionRef"),
                "scriptVersionDigest": context.get("scriptVersionDigest"),
                "storyboardVersionRef": context.get("storyboardVersionRef"),
                "storyboardVersionDigest": context.get("storyboardVersionDigest"),
                "executableShotGraphDigest": graph.get("payloadDigest"),
            }
        )

    def _execute_deterministic_overlay(
        self,
        *,
        workspace: str,
        run_ref: str,
        client_key: str,
        expected_run_version: int,
        effect_kind: str,
        requirement_command: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Execute E3 through the same V4 owner and evidence journal."""

        from .deterministic_overlays import (
            FACE_MARK_COMPENSATION,
            NAMEPLATE_TEXT,
            append_overlay_result_chain,
            build_face_mark_compensation_requirement,
            build_nameplate_text_requirement,
            build_overlay_execution_request,
            build_overlay_result,
        )

        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        if context["snapshot"].currentState not in M13_PREVIEW_STATE_TRANSITIONS:
            raise UpstreamNotReadyError(
                "deterministic overlays require current video media"
            )
        base = self._current_overlay_base(
            context=context,
            asset_version_ref=requirement_command.get(
                "basePlateAssetVersionRef"
            ),
            asset_version_digest=requirement_command.get(
                "basePlateAssetVersionDigest"
            ),
            target_shot_ref=requirement_command.get("targetShotRef"),
            target_shot_version_ref=requirement_command.get(
                "targetShotVersionRef"
            ),
            target_shot_version_digest=requirement_command.get(
                "targetShotVersionDigest"
            ),
            frame_range_end_exclusive=requirement_command.get(
                "frameRangeEndExclusive"
            ),
        )
        if effect_kind == NAMEPLATE_TEXT:
            text = self._current_script_text_projection(context=context)
            font = self._current_font_projection(
                context=context,
                asset_version_ref=requirement_command.get(
                    "fontAssetVersionRef"
                ),
                asset_version_digest=requirement_command.get(
                    "fontAssetVersionDigest"
                ),
                required_text=text["resolvedText"],
            )
            requirement = build_nameplate_text_requirement(
                requirement_command,
                resolved_base=base,
                resolved_text_source=text,
                resolved_font=font,
            )
        elif effect_kind == FACE_MARK_COMPENSATION:
            projection = self._current_identity_reference_projection(
                context=context,
                character_ref=requirement_command.get("characterRef"),
                target_shot_ref=requirement_command.get("targetShotRef"),
                target_shot_version_ref=requirement_command.get(
                    "targetShotVersionRef"
                ),
                target_shot_version_digest=requirement_command.get(
                    "targetShotVersionDigest"
                ),
            )
            mark = self._current_mark_asset(
                context=context,
                asset_version_ref=requirement_command.get(
                    "markAssetVersionRef"
                ),
                asset_version_digest=requirement_command.get(
                    "markAssetVersionDigest"
                ),
                target_shot_ref=requirement_command.get("targetShotRef"),
                target_shot_version_ref=requirement_command.get(
                    "targetShotVersionRef"
                ),
                target_shot_version_digest=requirement_command.get(
                    "targetShotVersionDigest"
                ),
            )
            requirement = build_face_mark_compensation_requirement(
                requirement_command,
                resolved_base=base,
                identity_projection=projection,
                resolved_mark=mark,
            )
        else:  # pragma: no cover - guarded by the public dispatch above.
            raise EpisodeProductionError("effectKind is invalid")

        requirement_value = requirement.as_dict()
        # Creation-time resolution is not execution authority.  Re-read every
        # current dependency immediately before sealing the V4 request.
        execution_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        resolved_assets = self._resolved_overlay_authorities(
            context=execution_context,
            requirement=requirement_value,
        )
        execution_request = build_overlay_execution_request(requirement)
        execute = (
            getattr(self.composition, "execute_deterministic_overlay", None)
            if self.composition is not None
            else None
        )
        if not callable(execute):
            raise WorkerUnavailableError(
                "M13-E3 deterministic overlay execution is not configured"
            )
        record_head = self._stable_record_head(
            workspace,
            run_ref,
            execution_context["snapshot"].revisionToken,
        )
        try:
            execution = execute(
                execution_request.as_dict(),
                resolved_asset_versions=resolved_assets,
            )
        except CompositionExecutionError as exc:
            raise WorkerUnavailableError(
                "M13-E3 deterministic overlay execution failed"
            ) from exc
        if not isinstance(execution, Mapping) or set(execution) != {
            "artifactEvidence",
            "runtimeEvidence",
            "evidenceBindings",
        }:
            raise RepositoryUnavailableError(
                "M13-E3 deterministic overlay evidence is invalid"
            )
        result = build_overlay_result(
            requirement=requirement,
            execution_request=execution_request,
            evidence_bindings=execution["evidenceBindings"],
            artifact_evidence=execution["artifactEvidence"],
        )
        chain, replayed = append_overlay_result_chain(
            self.evidence,
            requirement=requirement,
            execution_request=execution_request,
            artifact_evidence=execution["artifactEvidence"],
            runtime_evidence=execution["runtimeEvidence"],
            result=result,
            idempotency_key=client_key,
            created_at=self._clock(),
            expected_record_journal_head=record_head,
        )
        return {
            "idempotentReplay": replayed,
            "deterministicEffect": chain.as_dict(),
        }

    def _execute_distance_state_transition(
        self,
        *,
        workspace: str,
        run_ref: str,
        client_key: str,
        expected_run_version: int,
        requirement_command: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Execute the closed E4 transition through the existing V4 owner."""

        from .distance_state import (
            append_distance_state_result_chain,
            build_distance_state_execution_request,
            build_distance_state_requirement,
            build_distance_state_result,
        )

        target_kind = requirement_command.get("targetKind")
        definitions = requirement_command.get("visualStateDefinitions")
        transition_mode = requirement_command.get("transitionMode")
        if not isinstance(definitions, list) or (
            transition_mode != "SCREEN_DISTANCE" and not definitions
        ):
            raise EpisodeProductionError(
                "visualStateDefinitions do not match transitionMode"
            )
        role_refs: dict[str, str] = {}

        def role(reference: Any, digest: Any, label: str) -> None:
            reference_value = _required_ref(reference, f"{label}Ref")
            if not _is_sha256(digest):
                raise EpisodeProductionError(f"{label}Digest is invalid")
            if reference_value in role_refs:
                raise EpisodeProductionError(
                    "Distance/State AssetVersion roles must be distinct"
                )
            role_refs[reference_value] = str(digest)

        role(
            requirement_command.get("basePlateAssetVersionRef"),
            requirement_command.get("basePlateAssetVersionDigest"),
            "basePlateAssetVersion",
        )
        variant_digests: dict[str, str] = {}
        for index, state in enumerate(definitions):
            if not isinstance(state, Mapping):
                raise EpisodeProductionError(
                    f"visualStateDefinitions[{index}] is invalid"
                )
            reference = state.get("variantAssetVersionRef")
            digest = state.get("variantAssetVersionDigest")
            if reference is None and digest is None:
                continue
            reference_value = _required_ref(
                reference,
                f"visualStateDefinitions[{index}].variantAssetVersionRef",
            )
            if not _is_sha256(digest):
                raise EpisodeProductionError(
                    f"visualStateDefinitions[{index}].variantAssetVersionDigest is invalid"
                )
            if reference_value in role_refs:
                raise EpisodeProductionError(
                    "Distance/State variant collides with another asset role"
                )
            previous = variant_digests.setdefault(reference_value, str(digest))
            if previous != digest:
                raise EpisodeProductionError(
                    "Distance/State variant ref has conflicting digests"
                )
        if target_kind == "FULL_FRAME":
            if any(
                requirement_command.get(field) is not None
                for field in (
                    "subjectLayerAssetVersionRef",
                    "subjectLayerAssetVersionDigest",
                    "maskAssetVersionRef",
                    "maskAssetVersionDigest",
                )
            ) or variant_digests:
                raise EpisodeProductionError(
                    "FULL_FRAME forbids subject, mask, and variant assets"
                )
        elif target_kind == "OVERLAY_LAYER":
            role(
                requirement_command.get("subjectLayerAssetVersionRef"),
                requirement_command.get("subjectLayerAssetVersionDigest"),
                "subjectLayerAssetVersion",
            )
            role(
                requirement_command.get("maskAssetVersionRef"),
                requirement_command.get("maskAssetVersionDigest"),
                "maskAssetVersion",
            )
            if any(reference in role_refs for reference in variant_digests):
                raise EpisodeProductionError(
                    "Distance/State variant collides with another asset role"
                )
        else:
            raise EpisodeProductionError("targetKind is invalid")

        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        if context["snapshot"].currentState not in M13_PREVIEW_STATE_TRANSITIONS:
            raise UpstreamNotReadyError(
                "Distance/State transitions require current video media"
            )
        creation_assets = self._resolved_distance_state_authorities(
            context=context,
            requirement=requirement_command,
            enforce_requirement_digests=False,
        )
        base = creation_assets[
            requirement_command["basePlateAssetVersionRef"]
        ]
        subject = (
            creation_assets[
                requirement_command["subjectLayerAssetVersionRef"]
            ]
            if requirement_command.get("subjectLayerAssetVersionRef")
            is not None
            else None
        )
        mask = (
            creation_assets[requirement_command["maskAssetVersionRef"]]
            if requirement_command.get("maskAssetVersionRef") is not None
            else None
        )
        variants: list[dict[str, Any]] = []
        seen_variants: set[str] = set()
        for state in requirement_command.get("visualStateDefinitions", []):
            if not isinstance(state, Mapping):
                continue
            reference = state.get("variantAssetVersionRef")
            if isinstance(reference, str) and reference not in seen_variants:
                variants.append(creation_assets[reference])
                seen_variants.add(reference)
        requirement = build_distance_state_requirement(
            requirement_command,
            resolved_base=base,
            resolved_subject=subject,
            resolved_mask=mask,
            resolved_variants=variants,
        )

        # Creation-time observations do not authorize execution.  Re-read the
        # current Root/Shot/media closure immediately before sealing V4.
        execution_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        resolved_assets = self._resolved_distance_state_authorities(
            context=execution_context,
            requirement=requirement.as_dict(),
        )
        execution_request = build_distance_state_execution_request(requirement)
        execute = (
            getattr(self.composition, "execute_distance_state", None)
            if self.composition is not None
            else None
        )
        if not callable(execute):
            raise WorkerUnavailableError(
                "M13-E4 deterministic Distance/State execution is not configured"
            )
        record_head = self._stable_record_head(
            workspace,
            run_ref,
            execution_context["snapshot"].revisionToken,
        )
        try:
            execution = execute(
                execution_request.as_dict(),
                resolved_asset_versions=resolved_assets,
            )
        except CompositionExecutionError as exc:
            raise WorkerUnavailableError(
                "M13-E4 deterministic Distance/State execution failed"
            ) from exc
        if not isinstance(execution, Mapping) or set(execution) != {
            "artifactEvidence",
            "runtimeEvidence",
            "evidenceBindings",
        }:
            raise RepositoryUnavailableError(
                "M13-E4 deterministic Distance/State evidence is invalid"
            )

        # Close the independent-authority window: the current Root/Shot/media
        # selection may change without changing the evidence-journal head.
        # Re-read it after rendering, then physically remeasure the produced
        # artifact before any immutable evidence is appended.
        post_execution_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        post_execution_assets = self._resolved_distance_state_authorities(
            context=post_execution_context,
            requirement=requirement.as_dict(),
        )
        if post_execution_assets != resolved_assets:
            raise StaleInputError(
                "Distance/State current media changed during execution"
            )
        verify_artifact = (
            getattr(self.composition, "verify_distance_state_artifact", None)
            if self.composition is not None
            else None
        )
        if not callable(verify_artifact):
            raise WorkerUnavailableError(
                "M13-E4 artifact verification is not configured"
            )
        try:
            verified_artifact = verify_artifact(
                execution["artifactEvidence"],
                runtime_evidence=execution["runtimeEvidence"],
            )
        except CompositionExecutionError as exc:
            raise WorkerUnavailableError(
                "M13-E4 artifact verification failed"
            ) from exc
        if verified_artifact != execution["artifactEvidence"]:
            raise RepositoryUnavailableError(
                "M13-E4 artifact verification projection is stale"
            )
        result = build_distance_state_result(
            requirement=requirement,
            execution_request=execution_request,
            evidence_bindings=execution["evidenceBindings"],
            artifact_evidence=execution["artifactEvidence"],
        )
        chain, replayed = append_distance_state_result_chain(
            self.evidence,
            requirement=requirement,
            execution_request=execution_request,
            artifact_evidence=execution["artifactEvidence"],
            runtime_evidence=execution["runtimeEvidence"],
            result=result,
            idempotency_key=client_key,
            created_at=self._clock(),
            expected_record_journal_head=record_head,
        )
        return {
            "idempotentReplay": replayed,
            "deterministicEffect": chain.as_dict(),
        }

    def execute_deterministic_effect(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Execute one closed M13-E2 Requirement through the existing V4 owner."""

        fields = {
            "workspaceRef",
            "productionRunRef",
            "expectedRunVersion",
            "idempotencyKey",
            "effectKind",
            "requirement",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the deterministic Effect contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        effect_kind = command.get("effectKind")
        if effect_kind not in {
            FLAME_EXTINGUISH,
            SMOKE,
            "NAMEPLATE_TEXT",
            "FACE_MARK_COMPENSATION",
            "DISTANCE_STATE_TRANSITION",
        }:
            raise EpisodeProductionError("effectKind is invalid")
        requirement_input = command.get("requirement")
        if not isinstance(requirement_input, Mapping):
            raise EpisodeProductionError("requirement must be an object")
        if any(
            field in requirement_input
            for field in ("workspaceRef", "productionRunRef")
        ):
            raise EpisodeProductionError(
                "Requirement workspace/run scope is server-owned"
            )
        requirement_command = {
            **deepcopy(dict(requirement_input)),
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
        }
        if requirement_command.get("effectMode") != effect_kind:
            raise EpisodeProductionError(
                "effectKind and Requirement effectMode differ"
            )
        if effect_kind in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}:
            return self._execute_deterministic_overlay(
                workspace=workspace,
                run_ref=run_ref,
                client_key=client_key,
                expected_run_version=_positive_version(
                    command.get("expectedRunVersion"), "expectedRunVersion"
                ),
                effect_kind=effect_kind,
                requirement_command=requirement_command,
            )
        if effect_kind == "DISTANCE_STATE_TRANSITION":
            return self._execute_distance_state_transition(
                workspace=workspace,
                run_ref=run_ref,
                client_key=client_key,
                expected_run_version=_positive_version(
                    command.get("expectedRunVersion"), "expectedRunVersion"
                ),
                requirement_command=requirement_command,
            )
        requirement = (
            build_flame_extinguish_requirement(requirement_command)
            if effect_kind == FLAME_EXTINGUISH
            else build_smoke_requirement(requirement_command)
        )
        requirement_value = requirement.as_dict()
        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=_positive_version(
                command.get("expectedRunVersion"), "expectedRunVersion"
            ),
        )
        if context["snapshot"].currentState not in M13_PREVIEW_STATE_TRANSITIONS:
            raise UpstreamNotReadyError(
                "deterministic Effects require current video media"
            )
        resolved_base = self._resolved_deterministic_effect_base(
            context=context,
            requirement=requirement_value,
        )
        resolved_assets: dict[str, dict[str, Any]] = {
            resolved_base["assetVersionRef"]: resolved_base
        }
        dependencies: dict[str, dict[str, Any]] = {}
        result_exposure_requirement = None
        result_exposure_result = None

        if effect_kind == FLAME_EXTINGUISH:
            resolved_flame_mask = self._resolved_effect_image_asset(
                snapshot=context["snapshot"],
                workspace=workspace,
                run_ref=run_ref,
                asset_version_ref=requirement_value[
                    "flameMaskAssetVersionRef"
                ],
                asset_version_digest=requirement_value[
                    "flameMaskAssetVersionDigest"
                ],
                file_digest=requirement_value["flameMaskFileDigest"],
                pixel_digest=requirement_value["flameMaskPixelDigest"],
                label="flame mask",
            )
            resolved_assets[
                resolved_flame_mask["assetVersionRef"]
            ] = resolved_flame_mask
            exposure_results: list[dict[str, Any]] = []
            for record in context["snapshot"].records:
                if record.get("recordKind") != LOCAL_EXPOSURE_RESULT_RECORD_KIND:
                    continue
                payload = _immutable_payload(
                    record.get("payload"), LOCAL_EXPOSURE_RESULT_RECORD_KIND
                )
                if (
                    payload.get("requirementRef")
                    == requirement_value["localExposureRequirementRef"]
                    and payload.get("requirementDigest")
                    == requirement_value["localExposureRequirementDigest"]
                ):
                    exposure_results.append(payload)
            if len(exposure_results) != 1:
                raise UpstreamNotReadyError(
                    "exact Local Exposure Result dependency is unavailable"
                )
            exposure_result = exposure_results[0]
            exposure_chain_wrapper = resolve_deterministic_effect_result_chain(
                self.evidence,
                workspace_ref=workspace,
                production_run_ref=run_ref,
                result_ref=exposure_result["resultRef"],
                result_digest=exposure_result["payloadDigest"],
            )
            exposure_chain = exposure_chain_wrapper.as_dict()
            exposure_requirement, exposure_result_wrapper = (
                validate_flame_local_exposure_compatibility(
                    requirement,
                    exposure_chain_wrapper.requirement,
                    exposure_chain_wrapper.result,
                )
            )
            if exposure_result_wrapper is None:
                raise RepositoryUnavailableError(
                    "Local Exposure Result dependency is invalid"
                )
            result_exposure_requirement = exposure_requirement
            result_exposure_result = exposure_result_wrapper
            exposure_mask_value = exposure_requirement.as_dict()
            resolved_exposure_mask = self._resolved_effect_image_asset(
                snapshot=context["snapshot"],
                workspace=workspace,
                run_ref=run_ref,
                asset_version_ref=exposure_mask_value[
                    "maskAssetVersionRef"
                ],
                asset_version_digest=exposure_mask_value[
                    "maskAssetVersionDigest"
                ],
                file_digest=exposure_mask_value["maskFileDigest"],
                pixel_digest=exposure_mask_value["maskPixelDigest"],
                label="Local Exposure mask",
            )
            exposure_artifact = exposure_chain["artifactEvidence"]
            exposure_output = exposure_artifact["outputDigest"]
            exposure_probe = exposure_artifact["outputMediaProbe"]
            workspace_hash = sha256(workspace.encode("utf-8")).hexdigest()[:20]
            run_hash = sha256(run_ref.encode("utf-8")).hexdigest()[:20]
            dependencies[exposure_result["resultRef"]] = {
                **exposure_chain,
                "assetVersions": {
                    resolved_base["assetVersionRef"]: deepcopy(resolved_base),
                    resolved_exposure_mask[
                        "assetVersionRef"
                    ]: resolved_exposure_mask,
                },
                "artifactStorage": {
                    "artifactEvidenceRef": exposure_artifact[
                        "artifactEvidenceRef"
                    ],
                    "artifactEvidenceDigest": exposure_artifact[
                        "payloadDigest"
                    ],
                    "storageKey": (
                        f"{workspace_hash}/{run_hash}/masked-surface/"
                        "masked-surface-"
                        f"{exposure_artifact['v3ExecutionRequestDigest']}.mp4"
                    ),
                    "fileDigest": exposure_output["fileDigest"],
                    "pixelDigest": exposure_output[
                        "decodedFramePixelDigest"
                    ],
                    "pixelDigestSpec": exposure_output[
                        "decodedFramePixelDigestSpec"
                    ],
                    "width": exposure_output["width"],
                    "height": exposure_output["height"],
                    "frameCount": exposure_output["frameCount"],
                    "frameRate": exposure_output["frameRate"],
                    "pixelFormat": exposure_probe["pixelFormat"],
                },
            }
            execution_request = build_flame_smoke_execution_request(
                requirement,
                local_exposure_requirement=exposure_requirement,
                local_exposure_result=exposure_result_wrapper,
            )
        else:
            resolved_emission_mask = self._resolved_effect_image_asset(
                snapshot=context["snapshot"],
                workspace=workspace,
                run_ref=run_ref,
                asset_version_ref=requirement_value[
                    "emissionMaskAssetVersionRef"
                ],
                asset_version_digest=requirement_value[
                    "emissionMaskAssetVersionDigest"
                ],
                file_digest=requirement_value["emissionMaskFileDigest"],
                pixel_digest=requirement_value["emissionMaskPixelDigest"],
                label="smoke emission mask",
            )
            resolved_assets[
                resolved_emission_mask["assetVersionRef"]
            ] = resolved_emission_mask
            if requirement_value["smokeSourceKind"] == "PINNED_SMOKE_LAYER":
                resolved_smoke_layer = self._resolved_effect_image_asset(
                    snapshot=context["snapshot"],
                    workspace=workspace,
                    run_ref=run_ref,
                    asset_version_ref=requirement_value[
                        "smokeLayerAssetVersionRef"
                    ],
                    asset_version_digest=requirement_value[
                        "smokeLayerAssetVersionDigest"
                    ],
                    file_digest=requirement_value["smokeLayerFileDigest"],
                    pixel_digest=requirement_value[
                        "smokeLayerPixelDigest"
                    ],
                    label="pinned smoke layer",
                    allow_canonical_asset=True,
                )
                resolved_assets[
                    resolved_smoke_layer["assetVersionRef"]
                ] = resolved_smoke_layer
            execution_request = build_flame_smoke_execution_request(
                requirement
            )

        if self.composition is None or not callable(
            getattr(self.composition, "execute_flame_smoke", None)
        ):
            raise WorkerUnavailableError(
                "M13-E2 deterministic Effect execution is not configured"
            )
        record_head = self._stable_record_head(
            workspace,
            run_ref,
            context["snapshot"].revisionToken,
        )
        try:
            execution = self.composition.execute_flame_smoke(
                execution_request.as_dict(),
                resolved_asset_versions=resolved_assets,
                resolved_effect_dependencies=dependencies,
            )
        except CompositionExecutionError as exc:
            raise WorkerUnavailableError(
                "M13-E2 deterministic Effect execution failed"
            ) from exc
        if not isinstance(execution, Mapping) or set(execution) != {
            "artifactEvidence",
            "runtimeEvidence",
            "evidenceBindings",
        }:
            raise RepositoryUnavailableError(
                "M13-E2 deterministic Effect evidence is invalid"
            )
        result = build_deterministic_effect_result(
            requirement=requirement,
            execution_request=execution_request,
            evidence_bindings=execution["evidenceBindings"],
            artifact_evidence=execution["artifactEvidence"],
            local_exposure_requirement=result_exposure_requirement,
            local_exposure_result=result_exposure_result,
        )
        chain, replayed = append_deterministic_effect_result_chain(
            self.evidence,
            requirement=requirement,
            execution_request=execution_request,
            artifact_evidence=execution["artifactEvidence"],
            runtime_evidence=execution["runtimeEvidence"],
            result=result,
            idempotency_key=client_key,
            created_at=self._clock(),
            expected_record_journal_head=record_head,
        )
        return {
            "idempotentReplay": replayed,
            "deterministicEffect": chain.as_dict(),
        }

    def _resolve_effect_result_chain(
        self,
        *,
        context: Mapping[str, Any],
        result_ref: str,
        result_digest: str,
    ) -> dict[str, Any]:
        """Dispatch one exact result ref to its existing closed chain owner."""

        from .deterministic_overlays import (
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
            resolve_overlay_result_chain,
        )
        from .distance_state import (
            DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
            resolve_distance_state_result_chain,
        )

        snapshot = context["snapshot"]
        matches = [
            item
            for item in snapshot.records
            if item.get("recordRef") == result_ref
            and item.get("recordKind")
            in {
                SCRATCH_LIGHT_RESULT_RECORD_KIND,
                LOCAL_EXPOSURE_RESULT_RECORD_KIND,
                FLAME_EXTINGUISH_RESULT_RECORD_KIND,
                SMOKE_RESULT_RECORD_KIND,
                NAMEPLATE_TEXT_RESULT_RECORD_KIND,
                FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
                DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
            }
        ]
        if len(matches) != 1 or matches[0].get("payloadDigest") != result_digest:
            raise UpstreamNotReadyError(
                "exact deterministic Effect Result evidence is unavailable"
            )
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        if matches[0]["recordKind"] in {
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
        }:
            chain = resolve_overlay_result_chain(
                self.evidence,
                workspace_ref=workspace,
                production_run_ref=run_ref,
                result_ref=result_ref,
                result_digest=result_digest,
            ).as_dict()
            self._resolved_overlay_authorities(
                context=context,
                requirement=chain["requirement"],
            )
            return chain
        if (
            matches[0]["recordKind"]
            == DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND
        ):
            chain = resolve_distance_state_result_chain(
                self.evidence,
                workspace_ref=workspace,
                production_run_ref=run_ref,
                result_ref=result_ref,
                result_digest=result_digest,
            ).as_dict()
            self._resolved_distance_state_authorities(
                context=context,
                requirement=chain["requirement"],
            )
            verify_artifact = (
                getattr(
                    self.composition,
                    "verify_distance_state_artifact",
                    None,
                )
                if self.composition is not None
                else None
            )
            if not callable(verify_artifact):
                raise WorkerUnavailableError(
                    "M13-E4 artifact verification is not configured"
                )
            try:
                verified = verify_artifact(
                    chain["artifactEvidence"],
                    runtime_evidence=chain["runtimeEvidence"],
                )
            except CompositionExecutionError as exc:
                raise WorkerUnavailableError(
                    "M13-E4 artifact verification failed"
                ) from exc
            if verified != chain["artifactEvidence"]:
                raise RepositoryUnavailableError(
                    "M13-E4 artifact verification projection is stale"
                )
            return chain
        return resolve_deterministic_effect_result_chain(
            self.evidence,
            workspace_ref=workspace,
            production_run_ref=run_ref,
            result_ref=result_ref,
            result_digest=result_digest,
        ).as_dict()

    def get_deterministic_effects(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        context = self._timeline_authority_context(
            workspace,
            production_run,
            expected_run_version=None,
        )
        snapshot = context["snapshot"]
        from .deterministic_overlays import (
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
        )
        from .distance_state import (
            DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
        )

        supported_result_kinds = {
            FLAME_EXTINGUISH_RESULT_RECORD_KIND,
            SMOKE_RESULT_RECORD_KIND,
            NAMEPLATE_TEXT_RESULT_RECORD_KIND,
            FACE_MARK_COMPENSATION_RESULT_RECORD_KIND,
            DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
        }
        result_records: list[dict[str, Any]] = []
        for record in snapshot.records:
            if record.get("recordKind") not in supported_result_kinds:
                continue
            payload = _immutable_payload(
                record.get("payload"), str(record.get("recordKind"))
            )
            if (
                payload.get("resultRef") != record.get("recordRef")
                or payload.get("payloadDigest")
                != record.get("payloadDigest")
            ):
                raise RepositoryUnavailableError(
                    "deterministic Effect Result evidence is invalid"
                )
            result_records.append(payload)
        result_records.sort(key=lambda item: item["resultRef"])
        return {
            "deterministicEffects": [
                self._resolve_effect_result_chain(
                    context=context,
                    result_ref=item["resultRef"],
                    result_digest=item["payloadDigest"],
                )
                for item in result_records
            ],
            "publicationAllowed": False,
        }

    def create_timeline(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M13 Timeline create contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        operation_ref = _required_ref(command.get("operationRef"), "operationRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        expected_run_version = _positive_version(
            command.get("expectedRunVersion"), "expectedRunVersion"
        )
        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        run = context["run"]
        graph = context["executableShotGraph"]
        output = graph.get("output")
        if not isinstance(output, Mapping):
            raise RepositoryUnavailableError("ShotGraph output is invalid")
        frame_rate = self._editing_frame_rate(output.get("frameRate"))
        width = _positive_version(output.get("width"), "canvasWidth")
        height = _positive_version(output.get("height"), "canvasHeight")
        duration = _positive_version(output.get("totalFrames"), "durationFrames")
        pixel_aspect = {"numerator": 1, "denominator": 1}
        aspect_common = gcd(width, height)
        display_aspect = {
            "numerator": width // aspect_common,
            "denominator": height // aspect_common,
        }
        output_digest = _digest(dict(output))
        create_operation_digest = _digest(
            {
                "schemaVersion": TIMELINE_EDIT_CREATE_REQUEST_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "operationRef": operation_ref,
                "idempotencyKey": client_key,
                "expectedRunVersion": expected_run_version,
                "runDigest": run["payloadDigest"],
                "scriptVersionRef": context["scriptVersionRef"],
                "scriptVersionDigest": context["scriptVersionDigest"],
                "storyboardVersionRef": context["storyboardVersionRef"],
                "storyboardVersionDigest": context["storyboardVersionDigest"],
                "executableShotGraphDigest": graph["payloadDigest"],
                "outputProfileDigest": output_digest,
            }
        )
        timeline_ref = f"m13-timeline-{create_operation_digest}"
        timeline_version_ref = f"{timeline_ref}-version-1"
        existing_matches = [
            item
            for item in context["snapshot"].records
            if item.get("recordKind") == "Timeline"
            and item.get("recordRef") == timeline_ref
        ]
        if len(existing_matches) > 1:
            raise RepositoryUnavailableError(
                "Timeline create replay authority is ambiguous"
            )
        if existing_matches:
            existing = existing_matches[0]
            payload = existing.get("payload")
            if (
                existing.get("recordKind") != "Timeline"
                or existing.get("recordVersion") != 1
                or not isinstance(payload, Mapping)
                or payload.get("schemaVersion")
                != EDITING_TIMELINE_SCHEMA_VERSION
                or existing.get("recordRef") != payload.get("timelineRef")
                or existing.get("payloadDigest") != payload.get("payloadDigest")
            ):
                raise RepositoryUnavailableError(
                    "Timeline create replay evidence is invalid"
                )
            initial_versions = [
                item
                for item in context["snapshot"].records
                if item.get("recordKind") == "TimelineVersion"
                and item.get("recordRef") == timeline_version_ref
                and item.get("recordVersion") == 1
            ]
            if len(initial_versions) != 1:
                raise RepositoryUnavailableError(
                    "Timeline create version replay evidence is invalid"
                )
            restored = self._restore_editing_timeline(
                context,
                timeline_version_ref=timeline_version_ref,
            )
            restored = {
                **restored,
                "versionHistory": (restored["timelineVersion"],),
            }
            return self._editing_projection(
                restored,
                evidence_revision=context["snapshot"].revisionToken,
                replayed=True,
            )
        if self._timeline_authority_records_or_facts(context["snapshot"]):
            raise IdempotencyConflictError(
                "Timeline authority already exists; T1 has no upgrade operation"
            )
        created_at = self._clock()
        timeline = validate_editing_timeline(
            build_editing_timeline(
                {
                    "timelineRef": timeline_ref,
                    "workspaceRef": workspace,
                    "projectRef": run["projectRef"],
                    "seriesRef": run["seriesRef"],
                    "episodeRef": run["episodeRef"],
                    "productionRunRef": run_ref,
                    "createdAt": created_at,
                }
            )
        )
        lane_policies = {
            "VIDEO": "LAYERED_Z_ORDER",
            "AUDIO": "MIX",
            "SUBTITLE": "LAYERED",
            "EFFECT": "LAYERED_Z_ORDER",
        }
        tracks = tuple(
            EditingTimelineTrack.from_mapping(
                build_editing_timeline_track(
                    {
                        "trackRef": f"{timeline_ref}-track-{kind.lower()}",
                        "timelineVersionRef": timeline_version_ref,
                        "trackKind": kind,
                        "order": order,
                        "enabled": True,
                        "lanePolicy": lane_policies[kind],
                    }
                )
            )
            for order, kind in enumerate(EDITING_TIMELINE_TRACK_KINDS)
        )
        output_profile = self._server_output_profile(graph)
        timeline_version = validate_editing_timeline_version(
            build_editing_timeline_version(
                {
                    "timelineRef": timeline_ref,
                    "timelineVersionRef": timeline_version_ref,
                    "versionNumber": 1,
                    "parentTimelineVersionRef": None,
                    "parentTimelineVersionDigest": None,
                    "workspaceRef": workspace,
                    "projectRef": run["projectRef"],
                    "seriesRef": run["seriesRef"],
                    "episodeRef": run["episodeRef"],
                    "productionRunRef": run_ref,
                    "scriptVersionRef": context["scriptVersionRef"],
                    "scriptVersionDigest": context["scriptVersionDigest"],
                    "storyboardVersionRef": context["storyboardVersionRef"],
                    "storyboardVersionDigest": context[
                        "storyboardVersionDigest"
                    ],
                    "frameRate": frame_rate,
                    "canvasWidth": width,
                    "canvasHeight": height,
                    "pixelAspectRatio": pixel_aspect,
                    "displayAspectRatio": display_aspect,
                    "durationFrames": duration,
                    "safeArea": {
                        "leftPixels": 0,
                        "topPixels": 0,
                        "rightPixels": 0,
                        "bottomPixels": 0,
                    },
                    "trackRefs": [item.as_dict()["trackRef"] for item in tracks],
                    "createdAt": created_at,
                },
                output_profile_bindings=(output_profile,),
                tracks=tracks,
                clips=(),
            )
        )
        created = validate_editing_timeline_snapshot(
            timeline_version,
            tracks,
            (),
            timeline=timeline,
            expected_script={
                "scriptVersionRef": context["scriptVersionRef"],
                "scriptVersionDigest": context["scriptVersionDigest"],
            },
            expected_storyboard={
                "storyboardVersionRef": context["storyboardVersionRef"],
                "storyboardVersionDigest": context["storyboardVersionDigest"],
            },
        )
        request_digest = self._timeline_create_batch_request_digest(
            context,
            timeline,
            created.timeline_version,
            created.tracks,
            created.clips,
        )
        records = [
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="Timeline",
                record_ref=timeline_ref,
                record_version=1,
                client_key=request_digest,
                slot="timeline-root",
                request_digest=request_digest,
                created_at=created_at,
                payload=timeline.as_dict(),
            ),
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineVersion",
                record_ref=timeline_version_ref,
                record_version=1,
                client_key=request_digest,
                slot="timeline-version",
                request_digest=request_digest,
                created_at=created_at,
                payload=created.timeline_version.as_dict(),
            ),
        ]
        records.extend(
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineTrack",
                record_ref=item.as_dict()["trackRef"],
                record_version=1,
                client_key=request_digest,
                slot=f"track:{index}",
                request_digest=request_digest,
                created_at=created_at,
                payload=item.as_dict(),
            )
            for index, item in enumerate(
                sorted(
                    created.tracks,
                    key=lambda track: (
                        track.as_dict()["order"],
                        track.as_dict()["trackRef"],
                    ),
                )
            )
        )
        journal_head = self._stable_record_head(
            workspace,
            run_ref,
            context["snapshot"].revisionToken,
        )
        _, replayed = self.evidence.append_records(
            records,
            expected_record_journal_head=journal_head,
        )
        result_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        result_context = {**context, "snapshot": result_snapshot}
        restored = self._restore_editing_timeline(
            result_context,
            timeline_version_ref=timeline_version_ref,
        )
        return self._editing_projection(
            restored,
            evidence_revision=result_snapshot.revisionToken,
            replayed=replayed,
        )

    def edit_timeline(self, command: Mapping[str, Any]) -> dict[str, Any]:
        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "parentTimelineVersionRef",
            "parentTimelineVersionDigest",
            "editCommand",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M13 Timeline edit contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        operation_ref = _required_ref(command.get("operationRef"), "operationRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        expected_run_version = _positive_version(
            command.get("expectedRunVersion"), "expectedRunVersion"
        )
        parent_ref = _required_ref(
            command.get("parentTimelineVersionRef"),
            "parentTimelineVersionRef",
        )
        parent_digest = command.get("parentTimelineVersionDigest")
        if not _is_sha256(parent_digest):
            raise EpisodeProductionError(
                "parentTimelineVersionDigest is invalid"
            )
        edit_input = command.get("editCommand")
        if not isinstance(edit_input, Mapping) or set(edit_input) != {
            "operation",
            "arguments",
        }:
            raise EpisodeProductionError("editCommand fields are invalid")
        edit_input = deepcopy(dict(edit_input))
        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        request_digest = _digest(
            {
                "schemaVersion": TIMELINE_EDIT_SUCCESSOR_REQUEST_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "operationRef": operation_ref,
                "idempotencyKey": client_key,
                "expectedRunVersion": expected_run_version,
                "parentTimelineVersionRef": parent_ref,
                "parentTimelineVersionDigest": parent_digest,
                "editCommand": edit_input,
                "runDigest": context["run"]["payloadDigest"],
                "scriptVersionRef": context["scriptVersionRef"],
                "scriptVersionDigest": context["scriptVersionDigest"],
                "storyboardVersionRef": context["storyboardVersionRef"],
                "storyboardVersionDigest": context["storyboardVersionDigest"],
            }
        )
        replay_key = self._timeline_record_idempotency_key(
            client_key, "edit-operation"
        )
        existing = self.evidence.get_record_by_idempotency_key(
            workspace, run_ref, replay_key
        )
        if existing is not None:
            if existing.get("requestDigest") != request_digest:
                raise IdempotencyConflictError(
                    "Timeline edit idempotency content changed"
                )
            if existing.get("recordKind") != "TimelineEditOperation":
                raise RepositoryUnavailableError(
                    "Timeline edit replay evidence is invalid"
                )
            edit_operation = EditingTimelineEditCommand.from_mapping(
                existing.get("payload")
            ).as_dict()
            restored = self._restore_editing_timeline(
                context,
                timeline_version_ref=edit_operation["newTimelineVersionRef"],
            )
            selected_version_number = restored[
                "timelineVersion"
            ].as_dict()["versionNumber"]
            restored = {
                **restored,
                "versionHistory": tuple(
                    item
                    for item in restored["versionHistory"]
                    if item.as_dict()["versionNumber"]
                    <= selected_version_number
                ),
            }
            return self._editing_projection(
                restored,
                evidence_revision=context["snapshot"].revisionToken,
                replayed=True,
                edit_operation=edit_operation,
            )

        parent = self._restore_editing_timeline(
            context,
            timeline_version_ref=parent_ref,
        )
        parent_version = parent["timelineVersion"]
        parent_mapping = parent_version.as_dict()
        latest = parent["versionHistory"][-1].as_dict()
        if (
            parent_mapping["payloadDigest"] != parent_digest
            or latest["timelineVersionRef"] != parent_ref
            or latest["payloadDigest"] != parent_digest
        ):
            raise StaleInputError("Timeline edit parent is stale")
        next_number = parent_mapping["versionNumber"] + 1
        new_version_ref = (
            f"{parent_mapping['timelineRef']}-version-{next_number}"
        )
        created_at = self._clock()
        edit_command = EditingTimelineEditCommand.from_mapping(
            build_timeline_edit_command(
                {
                    "operationRef": operation_ref,
                    "idempotencyKey": client_key,
                    "parentTimelineVersionRef": parent_ref,
                    "parentTimelineVersionDigest": parent_digest,
                    "newTimelineVersionRef": new_version_ref,
                    "operation": edit_input["operation"],
                    "arguments": edit_input["arguments"],
                    "createdAt": created_at,
                }
            )
        )
        edit_mapping = edit_command.as_dict()
        if edit_mapping["operation"] == "SET_OUTPUT_PROFILES" and edit_mapping[
            "arguments"
        ]["outputProfileBindings"] != [
            self._server_output_profile(context["executableShotGraph"])
        ]:
            raise StaleInputError(
                "OutputProfileBinding is not resolvable from current ShotGraph"
            )
        edited = apply_timeline_edit(
            parent_version,
            parent["tracks"],
            parent["clips"],
            edit_command,
            existing_timeline_versions=parent["versionHistory"],
            timeline=parent["timeline"],
            source_resolver=self._timeline_source_resolver(
                context["snapshot"],
                authority_context=context,
                expected_script_version_ref=context["scriptVersionRef"],
                expected_script_version_digest=context["scriptVersionDigest"],
                expected_timeline_frame_rate=parent_mapping["frameRate"],
                expected_root_digest=context["run"]["payloadDigest"],
                expected_graph_version_ref=context["executableShotGraph"][
                    "executableShotGraphVersionRef"
                ],
                expected_graph_digest=context["executableShotGraph"][
                    "payloadDigest"
                ],
            ),
            expected_script={
                "scriptVersionRef": context["scriptVersionRef"],
                "scriptVersionDigest": context["scriptVersionDigest"],
            },
            expected_storyboard={
                "storyboardVersionRef": context["storyboardVersionRef"],
                "storyboardVersionDigest": context["storyboardVersionDigest"],
            },
        )
        records = [
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineEditOperation",
                record_ref=operation_ref,
                record_version=1,
                client_key=client_key,
                slot="edit-operation",
                request_digest=request_digest,
                created_at=created_at,
                payload=edited.edit_command.as_dict(),
            ),
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineVersion",
                record_ref=new_version_ref,
                record_version=next_number,
                client_key=client_key,
                slot="timeline-version",
                request_digest=request_digest,
                created_at=created_at,
                payload=edited.timeline_version.as_dict(),
            ),
        ]
        records.extend(
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineTrack",
                record_ref=item.as_dict()["trackRef"],
                record_version=next_number,
                client_key=client_key,
                slot=f"track:{index}",
                request_digest=request_digest,
                created_at=created_at,
                payload=item.as_dict(),
            )
            for index, item in enumerate(
                sorted(
                    edited.tracks,
                    key=lambda track: (
                        track.as_dict()["order"],
                        track.as_dict()["trackRef"],
                    ),
                )
            )
        )
        records.extend(
            self._timeline_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="TimelineClip",
                record_ref=item.as_dict()["clipRef"],
                record_version=next_number,
                client_key=client_key,
                slot=f"clip:{index}",
                request_digest=request_digest,
                created_at=created_at,
                payload=item.as_dict(),
            )
            for index, item in enumerate(
                sorted(
                    edited.clips,
                    key=lambda clip: clip.as_dict()["clipRef"],
                )
            )
        )
        journal_head = self._stable_record_head(
            workspace,
            run_ref,
            context["snapshot"].revisionToken,
        )
        _, replayed = self.evidence.append_records(
            records,
            expected_record_journal_head=journal_head,
        )
        result_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        result_context = {**context, "snapshot": result_snapshot}
        restored = self._restore_editing_timeline(
            result_context,
            timeline_version_ref=new_version_ref,
        )
        return self._editing_projection(
            restored,
            evidence_revision=result_snapshot.revisionToken,
            replayed=replayed,
            edit_operation=edited.edit_command.as_dict(),
        )

    def get_timeline(self, workspace_ref: str, run_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        context = self._timeline_authority_context(
            workspace,
            production_run,
            expected_run_version=None,
        )
        restored = self._restore_editing_timeline(context)
        return self._editing_projection(
            restored,
            evidence_revision=context["snapshot"].revisionToken,
            replayed=False,
        )

    def get_timeline_versions(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        context = self._timeline_authority_context(
            workspace,
            production_run,
            expected_run_version=None,
        )
        restored = self._restore_editing_timeline(context)
        return {
            "timeline": restored["timeline"].as_dict(),
            "versions": [
                item.as_dict() for item in restored["versionHistory"]
            ],
            "stale": False,
            "publicationAllowed": False,
            "evidenceRevision": context["snapshot"].revisionToken,
        }

    @staticmethod
    def _render_domain_record_idempotency_key(
        client_key: str,
        slot: str,
        *,
        domain_stage: str = "m13-r1a-composition-render-manifest",
    ) -> str:
        return _digest(
            {
                "clientIdempotencyKey": _idempotency_key(client_key),
                "stage": _required_ref(domain_stage, "render domain stage"),
                "slot": _required_ref(slot, "record slot"),
            }
        )

    @staticmethod
    def _render_domain_evidence_record(
        *,
        workspace: str,
        run_ref: str,
        record_kind: str,
        record_ref: str,
        record_version: int,
        client_key: str,
        slot: str,
        request_digest: str,
        created_at: str,
        payload: Mapping[str, Any],
        domain_stage: str = "m13-r1a-composition-render-manifest",
    ) -> EvidenceRecord:
        canonical = _immutable_payload(payload, record_kind)
        return EvidenceRecord(
            workspaceRef=_required_ref(workspace, "workspaceRef"),
            productionRunRef=_required_ref(run_ref, "productionRunRef"),
            recordKind=record_kind,
            recordRef=_required_ref(record_ref, "recordRef"),
            recordVersion=_positive_version(record_version, "recordVersion"),
            idempotencyKey=K2DeliveryService._render_domain_record_idempotency_key(
                client_key, slot, domain_stage=domain_stage
            ),
            requestDigest=request_digest,
            createdAt=created_at,
            payload=canonical,
            payloadDigest=canonical["payloadDigest"],
        )

    def _render_asset_version_index(
        self, context: Mapping[str, Any]
    ) -> dict[tuple[str, str], int]:
        """Index exact current AssetVersion identities without copying storage facts."""

        snapshot = context["snapshot"]
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        result: dict[tuple[str, str], int] = {}

        def observe(value: Any, *, envelope_version: int | None = None) -> None:
            if isinstance(value, Mapping):
                reference = value.get("assetVersionRef")
                digest = value.get("payloadDigest")
                version = value.get("version", envelope_version)
                if version is None and value.get("schemaVersion") in {
                    "v5.k2-real-image-asset-version.v1",
                    "v5.k2-real-video-asset-version.v1",
                }:
                    # These accepted M10/M11 immutable producer projections
                    # predate an explicit integer field.  Their v1 schema is
                    # the closed initial version; no later value can share the
                    # same immutable assetVersionRef/payloadDigest pair.
                    version = 1
                if (
                    isinstance(reference, str)
                    and _is_sha256(digest)
                    and isinstance(version, int)
                    and not isinstance(version, bool)
                    and version > 0
                ):
                    key = (reference, str(digest))
                    previous = result.setdefault(key, version)
                    if previous != version:
                        raise RepositoryUnavailableError(
                            "AssetVersion version authority is ambiguous"
                        )
                for item in value.values():
                    observe(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    observe(item)

        for record in snapshot.records:
            if not isinstance(record, Mapping):
                continue
            payload = record.get("payload")
            if isinstance(payload, Mapping):
                observe(
                    payload,
                    envelope_version=(
                        record.get("recordVersion")
                        if isinstance(record.get("recordVersion"), int)
                        else None
                    ),
                )
        for gate in snapshot.gates:
            for fact in gate.get("facts", []):
                if isinstance(fact, Mapping) and isinstance(
                    fact.get("payload"), Mapping
                ):
                    observe(
                        fact["payload"],
                        envelope_version=(
                            fact.get("factVersion")
                            if isinstance(fact.get("factVersion"), int)
                            else None
                        ),
                    )
        observe(
            self._current_glyph_video_assets(
                workspace,
                run_ref,
                evidence_snapshot=snapshot,
            )
        )
        if self.real_video_authority is not None:
            bundle = self.real_video_authority.get_revision_bundle(
                workspace,
                run_ref,
                evidence_snapshot=snapshot,
            )
            if not isinstance(bundle, Mapping):
                raise RepositoryUnavailableError(
                    "current real-media AssetVersion bundle is invalid"
                )
            observe(bundle)
        return result

    @staticmethod
    def _collect_asset_version_pairs(value: Any) -> set[tuple[str, str]]:
        result: set[tuple[str, str]] = set()
        if isinstance(value, Mapping):
            for field, selected in value.items():
                if (
                    field == "assetVersionRef"
                    or field.endswith("AssetVersionRef")
                ) and selected is not None:
                    digest_field = f"{field[:-3]}Digest"
                    if digest_field not in value:
                        # Some closed schedules repeat a ref whose exact
                        # digest is bound once in the enclosing Requirement.
                        # The Requirement validator has already proven that
                        # semantic equality; collect only identity pairs here.
                        continue
                    digest = value[digest_field]
                    if not isinstance(selected, str) or not _is_sha256(digest):
                        raise RepositoryUnavailableError(
                            "AssetVersion ref/digest binding is incomplete for "
                            f"{field}"
                        )
                    result.add((selected, str(digest)))
                result.update(
                    K2DeliveryService._collect_asset_version_pairs(selected)
                )
        elif isinstance(value, (list, tuple)):
            for item in value:
                result.update(
                    K2DeliveryService._collect_asset_version_pairs(item)
                )
        return result

    @staticmethod
    def _render_input_payloads(
        snapshot: Any, record_kind: str
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for record in snapshot.records:
            if record.get("recordKind") != record_kind:
                continue
            payload = _immutable_payload(record.get("payload"), record_kind)
            if record.get("payloadDigest") != payload["payloadDigest"]:
                raise RepositoryUnavailableError(
                    f"{record_kind} evidence digest is inconsistent"
                )
            result.append(payload)
        return result

    def _project_composition_version(
        self,
        *,
        context: Mapping[str, Any],
        restored: Mapping[str, Any],
        composition: Mapping[str, Any],
        composition_version_ref: str,
        version_number: int,
        predecessor: Mapping[str, Any] | None,
        created_at: str,
    ) -> dict[str, Any]:
        """Project only server-restored Timeline and current source authorities."""

        timeline = restored["timeline"].as_dict()
        timeline_version = restored["timelineVersion"].as_dict()
        tracks = [item.as_dict() for item in restored["tracks"]]
        clips = [item.as_dict() for item in restored["clips"]]
        tracks_by_ref = {item["trackRef"]: item for item in tracks}
        if len(tracks_by_ref) != len(tracks):
            raise RepositoryUnavailableError("Timeline Track identity is ambiguous")

        source_resolver = self._timeline_source_resolver(
            context["snapshot"],
            authority_context=context,
            expected_script_version_ref=context["scriptVersionRef"],
            expected_script_version_digest=context["scriptVersionDigest"],
            expected_timeline_frame_rate=timeline_version["frameRate"],
            expected_root_digest=context["run"]["payloadDigest"],
            expected_graph_version_ref=context["executableShotGraph"][
                "executableShotGraphVersionRef"
            ],
            expected_graph_digest=context["executableShotGraph"][
                "payloadDigest"
            ],
        )
        snapshot = context["snapshot"]
        audio_bindings = {
            item["assetVersionRef"]: validate_audio_input_binding(item).as_dict()
            for item in self._render_input_payloads(snapshot, "AudioInputBinding")
        }
        cues = {
            item["cueVersionRef"]: item
            for item in self._render_input_payloads(snapshot, "AudioCue")
        }
        stem_sets = self._render_input_payloads(snapshot, "AudioStemSet")
        asset_versions = self._render_asset_version_index(context)

        # FONT versions live behind their existing static-resource owner, not
        # a second render-domain authority.  Re-read the projection only for
        # a Nameplate Requirement that actually appears in this composition.
        for clip in clips:
            source = clip.get("sourceBinding")
            if (
                clip.get("clipKind") != "EFFECT"
                or not isinstance(source, Mapping)
                or source.get("effectKind") != "NAMEPLATE_TEXT"
            ):
                continue
            requirement = source_resolver(
                "EFFECT_REQUIREMENT", source["effectRequirementRef"]
            )
            if not isinstance(requirement, Mapping):
                raise UpstreamNotReadyError(
                    "Nameplate Requirement is not current"
                )
            projection = self._current_font_projection(
                context=context,
                asset_version_ref=requirement.get("fontAssetVersionRef"),
                asset_version_digest=requirement.get(
                    "fontAssetVersionDigest"
                ),
                required_text=requirement.get("resolvedText"),
            )
            font = projection["fontAssetVersion"]
            asset_versions[
                (font["assetVersionRef"], font["payloadDigest"])
            ] = _positive_version(font.get("version"), "FONT AssetVersion version")

        def stem_for_member(member_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
            matches = [
                (stem_set, member)
                for stem_set in stem_sets
                for member in stem_set.get("members", [])
                if isinstance(member, Mapping)
                and member.get("stemMemberRef") == member_ref
            ]
            if len(matches) != 1:
                raise UpstreamNotReadyError(
                    "exact Audio StemMember authority is unavailable"
                )
            return matches[0]

        def stem_for_cue(cue_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
            matches = [
                (stem_set, member)
                for stem_set in stem_sets
                for member in stem_set.get("members", [])
                if isinstance(member, Mapping)
                and member.get("sourceCueVersionRef") == cue_ref
            ]
            if len(matches) != 1:
                raise UpstreamNotReadyError(
                    "exact subtitle StemMember authority is unavailable"
                )
            return matches[0]

        def asset_bindings(
            pairs: set[tuple[str, str]],
        ) -> list[dict[str, Any]]:
            values: list[dict[str, Any]] = []
            for reference, digest in sorted(pairs):
                version = asset_versions.get((reference, digest))
                if version is None:
                    raise UpstreamNotReadyError(
                        "exact source AssetVersion version is unavailable"
                    )
                values.append(
                    {
                        "assetVersionRef": reference,
                        "version": version,
                        "assetVersionDigest": digest,
                    }
                )
            return values

        projected: dict[str, list[dict[str, Any]]] = {
            "VIDEO": [],
            "AUDIO": [],
            "SUBTITLE": [],
            "EFFECT": [],
        }
        for clip in sorted(
            clips,
            key=lambda item: (
                tracks_by_ref[item["trackRef"]]["order"],
                item["timelineStartFrameInclusive"],
                item["layer"],
                item["zOrder"],
                item["clipRef"],
            ),
        ):
            track = tracks_by_ref.get(clip["trackRef"])
            if not isinstance(track, Mapping) or track.get("trackKind") != clip.get(
                "clipKind"
            ):
                raise RepositoryUnavailableError(
                    "Timeline Track/Clip binding is invalid"
                )
            kind = str(clip["clipKind"])
            source = deepcopy(dict(clip["sourceBinding"]))
            pairs = self._collect_asset_version_pairs(source)
            pairs.update(self._collect_asset_version_pairs(clip["maskBindings"]))
            cue_binding = None
            stem_binding = None
            technical_binding = None
            effect_binding = None

            if kind == "AUDIO":
                binding = audio_bindings.get(source["audioAssetVersionRef"])
                if (
                    binding is None
                    or binding["assetVersionDigest"]
                    != source["audioAssetVersionDigest"]
                ):
                    raise UpstreamNotReadyError(
                        "exact AudioInputBinding is unavailable"
                    )
                stem_set, member = stem_for_member(source["stemMemberRef"])
                if (
                    member.get("sourceAssetVersionRef")
                    != source["audioAssetVersionRef"]
                    or member.get("sourceAssetVersionDigest")
                    != source["audioAssetVersionDigest"]
                ):
                    raise StaleInputError("Audio StemMember source is stale")
                validation = binding["technicalValidation"]
                stem_binding = {
                    "stemSetVersionRef": stem_set["stemSetVersionRef"],
                    "stemSetVersion": stem_set["version"],
                    "stemSetDigest": stem_set["payloadDigest"],
                    "stemMemberRef": member["stemMemberRef"],
                    "stemMemberDigest": member["payloadDigest"],
                }
                technical_binding = {
                    "validationRef": validation["validationRef"],
                    "validationVersionRef": validation["validationVersionRef"],
                    "version": validation["version"],
                    "validationDigest": validation["payloadDigest"],
                    "validationState": validation["validationState"],
                }
            elif kind == "SUBTITLE":
                cue = cues.get(source["audioCueRef"])
                if cue is None or cue["payloadDigest"] != source["audioCueDigest"]:
                    raise UpstreamNotReadyError(
                        "exact subtitle AudioCue is unavailable"
                    )
                stem_set, member = stem_for_cue(cue["cueVersionRef"])
                asset_ref = member.get("sourceAssetVersionRef")
                asset_digest = member.get("sourceAssetVersionDigest")
                binding = audio_bindings.get(asset_ref)
                if (
                    not isinstance(asset_ref, str)
                    or not _is_sha256(asset_digest)
                    or binding is None
                    or binding["assetVersionDigest"] != asset_digest
                ):
                    raise UpstreamNotReadyError(
                        "subtitle audio technical authority is unavailable"
                    )
                pairs.add((asset_ref, str(asset_digest)))
                validation = binding["technicalValidation"]
                cue_binding = {
                    "cueVersionRef": cue["cueVersionRef"],
                    "version": cue["version"],
                    "cueDigest": cue["payloadDigest"],
                }
                stem_binding = {
                    "stemSetVersionRef": stem_set["stemSetVersionRef"],
                    "stemSetVersion": stem_set["version"],
                    "stemSetDigest": stem_set["payloadDigest"],
                    "stemMemberRef": member["stemMemberRef"],
                    "stemMemberDigest": member["payloadDigest"],
                }
                technical_binding = {
                    "validationRef": validation["validationRef"],
                    "validationVersionRef": validation["validationVersionRef"],
                    "version": validation["version"],
                    "validationDigest": validation["payloadDigest"],
                    "validationState": validation["validationState"],
                }
            elif kind == "EFFECT":
                requirement = source_resolver(
                    "EFFECT_REQUIREMENT", source["effectRequirementRef"]
                )
                if (
                    not isinstance(requirement, Mapping)
                    or requirement.get("payloadDigest")
                    != source["effectRequirementDigest"]
                ):
                    raise UpstreamNotReadyError(
                        "exact Effect Requirement is unavailable"
                    )
                pairs.update(self._collect_asset_version_pairs(requirement))
                result_ref = source.get("effectResultRef")
                result_digest = source.get("effectResultDigest")
                if result_ref is not None:
                    result = source_resolver("EFFECT_RESULT", result_ref)
                    if (
                        not isinstance(result, Mapping)
                        or result.get("payloadDigest") != result_digest
                    ):
                        raise UpstreamNotReadyError(
                            "exact Effect Result is unavailable"
                        )
                effect_binding = {
                    "effectKind": source["effectKind"],
                    "requirementRef": source["effectRequirementRef"],
                    "requirementDigest": source["effectRequirementDigest"],
                    "resultRef": result_ref,
                    "resultDigest": result_digest,
                }

            projected[kind].append(
                seal_composition_track_binding(
                    {
                        "trackRef": track["trackRef"],
                        "trackDigest": track["payloadDigest"],
                        "trackKind": track["trackKind"],
                        "trackOrder": track["order"],
                        "trackEnabled": track["enabled"],
                        "lanePolicy": track["lanePolicy"],
                        "clipRef": clip["clipRef"],
                        "clipDigest": clip["payloadDigest"],
                        "clipKind": clip["clipKind"],
                        "timelineStartFrameInclusive": clip[
                            "timelineStartFrameInclusive"
                        ],
                        "timelineEndFrameExclusive": clip[
                            "timelineEndFrameExclusive"
                        ],
                        "enabled": clip["enabled"],
                        "layer": clip["layer"],
                        "zOrder": clip["zOrder"],
                        "opacity": clip["opacity"],
                        "blendMode": clip["blendMode"],
                        "sourceBinding": source,
                        "sourceAssetVersions": asset_bindings(pairs),
                        "audioCueBinding": cue_binding,
                        "stemBinding": stem_binding,
                        "technicalValidationBinding": technical_binding,
                        "effectBinding": effect_binding,
                        "transitionIn": deepcopy(clip["transitionIn"]),
                        "transitionOut": deepcopy(clip["transitionOut"]),
                        "speed": deepcopy(clip["speed"]),
                        "transform": deepcopy(clip["transform"]),
                        "maskBindings": deepcopy(clip["maskBindings"]),
                    }
                )
            )

        if set(projected) != {"VIDEO", "AUDIO", "SUBTITLE", "EFFECT"}:
            raise RepositoryUnavailableError("Composition Track set is invalid")
        plan_input = {
            "timelineRef": timeline["timelineRef"],
            "timelineVersionRef": timeline_version["timelineVersionRef"],
            "timelineVersionNumber": timeline_version["versionNumber"],
            "timelineVersionDigest": timeline_version["payloadDigest"],
            "videoTrackBindings": projected["VIDEO"],
            "audioTrackBindings": projected["AUDIO"],
            "subtitleTrackBindings": projected["SUBTITLE"],
            "effectTrackBindings": projected["EFFECT"],
        }
        plans = composition_plan_digests(plan_input)
        return build_composition_version(
            {
                "workspaceRef": timeline["workspaceRef"],
                "productionRunRef": timeline["productionRunRef"],
                "projectRef": timeline["projectRef"],
                "seriesRef": timeline["seriesRef"],
                "episodeRef": timeline["episodeRef"],
                "compositionRef": composition["compositionRef"],
                "compositionVersionRef": composition_version_ref,
                "versionNumber": version_number,
                "parentCompositionVersionRef": (
                    None
                    if predecessor is None
                    else predecessor["compositionVersionRef"]
                ),
                "parentCompositionVersionDigest": (
                    None if predecessor is None else predecessor["payloadDigest"]
                ),
                **plan_input,
                **plans,
                "createdAt": created_at,
                "provenance": COMPOSITION_PROVENANCE,
                "publicationAllowed": False,
            },
            predecessor=predecessor,
        )

    @staticmethod
    def _render_domain_payload_records(
        snapshot: Any,
        *,
        record_kind: str,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for gate in snapshot.gates:
            if any(
                isinstance(fact, Mapping)
                and fact.get("factKind") == record_kind
                for fact in gate.get("facts", [])
            ):
                raise RepositoryUnavailableError(
                    f"{record_kind} must use the evidence record journal"
                )
        for record in snapshot.records:
            if record.get("recordKind") != record_kind:
                continue
            payload = _immutable_payload(record.get("payload"), record_kind)
            if record.get("payloadDigest") != payload["payloadDigest"]:
                raise RepositoryUnavailableError(
                    f"{record_kind} evidence digest is inconsistent"
                )
            result.append((deepcopy(dict(record)), payload))
        return result

    def _restore_render_domain(
        self,
        context: Mapping[str, Any],
        *,
        render_manifest_ref: str | None = None,
        require_current_manifest: bool = True,
    ) -> dict[str, Any]:
        restored_timeline = self._restore_editing_timeline(context)
        timeline = restored_timeline["timeline"].as_dict()
        timeline_version = restored_timeline["timelineVersion"].as_dict()
        snapshot = context["snapshot"]

        root_records = self._render_domain_payload_records(
            snapshot, record_kind="Composition"
        )
        if len(root_records) != 1:
            if not root_records:
                raise UpstreamNotReadyError("Composition is not ready")
            raise RepositoryUnavailableError("Composition authority is ambiguous")
        root_record, root_payload = root_records[0]
        composition = validate_composition(root_payload).as_dict()
        run = context["run"]
        if (
            root_record.get("recordRef") != composition["compositionRef"]
            or root_record.get("recordVersion") != 1
            or root_record.get("createdAt") != composition["createdAt"]
            or composition["workspaceRef"] != run["workspaceRef"]
            or composition["productionRunRef"] != run["productionRunRef"]
            or composition["projectRef"] != run["projectRef"]
            or composition["seriesRef"] != run["seriesRef"]
            or composition["episodeRef"] != run["episodeRef"]
            or composition["timelineRef"] != timeline["timelineRef"]
        ):
            raise RepositoryUnavailableError("Composition authority is invalid")

        version_records = self._render_domain_payload_records(
            snapshot, record_kind="CompositionVersion"
        )
        version_records.sort(key=lambda item: item[1].get("versionNumber", -1))
        versions: list[dict[str, Any]] = []
        predecessor = None
        for expected_number, (record, payload) in enumerate(
            version_records, start=1
        ):
            wrapper = validate_composition_version(
                payload, predecessor=predecessor
            )
            value = wrapper.as_dict()
            if (
                value["versionNumber"] != expected_number
                or value["compositionRef"] != composition["compositionRef"]
                or record.get("recordRef") != value["compositionVersionRef"]
                or record.get("recordVersion") != expected_number
                or record.get("createdAt") != value["createdAt"]
                or value["workspaceRef"] != run["workspaceRef"]
                or value["productionRunRef"] != run["productionRunRef"]
            ):
                raise RepositoryUnavailableError(
                    "CompositionVersion journal is invalid"
                )
            versions.append(value)
            predecessor = value
        if not versions:
            raise UpstreamNotReadyError("CompositionVersion is not ready")
        current = versions[-1]
        if (
            current["timelineRef"] != timeline["timelineRef"]
            or current["timelineVersionRef"]
            != timeline_version["timelineVersionRef"]
            or current["timelineVersionNumber"] != timeline_version["versionNumber"]
            or current["timelineVersionDigest"] != timeline_version["payloadDigest"]
        ):
            raise StaleInputError("CompositionVersion Timeline authority is stale")
        expected = self._project_composition_version(
            context=context,
            restored=restored_timeline,
            composition=composition,
            composition_version_ref=current["compositionVersionRef"],
            version_number=current["versionNumber"],
            predecessor=(versions[-2] if len(versions) > 1 else None),
            created_at=current["createdAt"],
        )
        if expected != current:
            raise StaleInputError("CompositionVersion source authority is stale")

        manifest_records = self._render_domain_payload_records(
            snapshot, record_kind="RenderManifest"
        )
        manifests: list[dict[str, Any]] = []
        versions_by_ref = {
            item["compositionVersionRef"]: item for item in versions
        }
        for record, payload in manifest_records:
            manifest = validate_render_manifest(payload).as_dict()
            bound_version = versions_by_ref.get(
                manifest["compositionVersionRef"]
            )
            if (
                record.get("recordRef") != manifest["renderManifestRef"]
                or record.get("recordVersion") != 1
                or record.get("createdAt") != manifest["createdAt"]
                or manifest["workspaceRef"] != run["workspaceRef"]
                or manifest["productionRunRef"] != run["productionRunRef"]
                or not isinstance(bound_version, Mapping)
                or manifest["compositionVersionDigest"]
                != bound_version["payloadDigest"]
                or manifest["timelineVersionRef"]
                != bound_version["timelineVersionRef"]
                or manifest["timelineVersionDigest"]
                != bound_version["timelineVersionDigest"]
            ):
                raise RepositoryUnavailableError(
                    "RenderManifest evidence envelope is invalid"
                )
            manifests.append(manifest)
        if not manifests:
            raise UpstreamNotReadyError("RenderManifest is not ready")
        if len({item["renderManifestRef"] for item in manifests}) != len(manifests):
            raise RepositoryUnavailableError("RenderManifest identity is ambiguous")
        if render_manifest_ref is None:
            if len(manifests) != 1:
                raise RepositoryUnavailableError(
                    "multiple RenderManifests require an exact ref"
                )
            manifest = manifests[0]
        else:
            matches = [
                item
                for item in manifests
                if item["renderManifestRef"] == render_manifest_ref
            ]
            if len(matches) != 1:
                raise RecordNotFoundError("RenderManifest was not found")
            manifest = matches[0]
        if (
            manifest["timelineVersionRef"] != timeline_version["timelineVersionRef"]
            or manifest["timelineVersionDigest"] != timeline_version["payloadDigest"]
            or manifest["compositionVersionRef"] != current["compositionVersionRef"]
            or manifest["compositionVersionDigest"] != current["payloadDigest"]
        ):
            raise StaleInputError("RenderManifest input authority is stale")
        if require_current_manifest:
            if self.render_toolchain_identity is None:
                raise UpstreamNotReadyError(
                    "trusted deterministic render toolchain is not configured"
                )
            if any(
                manifest[field] != self.render_toolchain_identity[field]
                for field in self.render_toolchain_identity
            ):
                raise StaleInputError("RenderManifest toolchain identity is stale")
            if manifest["subtitleMode"] != "NONE":
                subtitle_cues = self._render_subtitle_cues(
                    context=context,
                    layout=self._editing_preview_layout(
                        restored_timeline,
                        allow_video_edits=True,
                    ),
                )
                if (
                    manifest["subtitleTimingDigest"]
                    != canonical_subtitle_timing_digest(subtitle_cues)
                ):
                    raise StaleInputError(
                        "RenderManifest subtitle timing authority is stale"
                    )
            if manifest["subtitleMode"] == "BURN_IN":
                script_text = self._current_script_text_projection(context=context)
                self._current_font_projection(
                    context=context,
                    asset_version_ref=manifest[
                        "subtitleFontAssetVersionRef"
                    ],
                    asset_version_digest=manifest[
                        "subtitleFontAssetVersionDigest"
                    ],
                    required_text=script_text["resolvedText"],
                )
        return {
            "timeline": restored_timeline,
            "composition": composition,
            "compositionVersion": current,
            "compositionVersionHistory": versions,
            "renderManifest": manifest,
            "renderManifestHistory": manifests,
        }

    @staticmethod
    def _render_domain_projection(
        restored: Mapping[str, Any],
        *,
        evidence_revision: str,
        replayed: bool,
    ) -> dict[str, Any]:
        timeline = restored["timeline"]
        return {
            "timeline": timeline["timeline"].as_dict(),
            "timelineVersion": timeline["timelineVersion"].as_dict(),
            "composition": deepcopy(restored["composition"]),
            "compositionVersion": deepcopy(restored["compositionVersion"]),
            "compositionVersionHistory": deepcopy(
                restored["compositionVersionHistory"]
            ),
            "renderManifest": deepcopy(restored["renderManifest"]),
            "renderManifestHistory": deepcopy(
                restored["renderManifestHistory"]
            ),
            "publicationAllowed": False,
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
            "evidenceRevision": evidence_revision,
            "idempotentReplay": replayed,
        }

    def create_composition_render_manifest(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Create immutable R1A facts without executing or publishing a render."""

        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "timelineVersionRef",
            "timelineVersionDigest",
            "renderProfile",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M13-R1A contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        operation_ref = _required_ref(command.get("operationRef"), "operationRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        expected_run_version = _positive_version(
            command.get("expectedRunVersion"), "expectedRunVersion"
        )
        timeline_version_ref = _required_ref(
            command.get("timelineVersionRef"), "timelineVersionRef"
        )
        timeline_version_digest = command.get("timelineVersionDigest")
        if not _is_sha256(timeline_version_digest):
            raise EpisodeProductionError("timelineVersionDigest is invalid")
        profile_fields = {
            "outputProfile",
            "videoEncoding",
            "colorMetadata",
            "audioEncoding",
            "subtitleMode",
            "subtitleFontAssetVersionRef",
            "subtitleFontAssetVersionDigest",
        }
        profile = command.get("renderProfile")
        if not isinstance(profile, Mapping) or set(profile) != profile_fields:
            raise EpisodeProductionError("renderProfile fields are invalid")
        profile = deepcopy(dict(profile))
        if self.render_toolchain_identity is None:
            raise UpstreamNotReadyError(
                "trusted deterministic render toolchain is not configured"
            )

        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        restored_timeline = self._restore_editing_timeline(context)
        timeline = restored_timeline["timeline"].as_dict()
        timeline_version = restored_timeline["timelineVersion"].as_dict()
        latest_timeline_version = restored_timeline["versionHistory"][-1].as_dict()
        if (
            timeline_version["timelineVersionRef"] != timeline_version_ref
            or timeline_version["payloadDigest"] != timeline_version_digest
            or latest_timeline_version["timelineVersionRef"] != timeline_version_ref
            or latest_timeline_version["payloadDigest"] != timeline_version_digest
        ):
            raise StaleInputError("Composition requires the current TimelineVersion")
        frame_rate = timeline_version["frameRate"]
        output_profile = profile.get("outputProfile")
        if (
            not isinstance(output_profile, Mapping)
            or output_profile.get("frameRateNumerator")
            != frame_rate["numerator"]
            or output_profile.get("frameRateDenominator")
            != frame_rate["denominator"]
        ):
            raise StaleInputError("RenderManifest frame rate differs from Timeline")
        audio_encoding = profile.get("audioEncoding")
        if not isinstance(audio_encoding, Mapping) or (
            audio_encoding.get("enabled") is True
            and (
                audio_encoding.get("sampleRate") != 48_000
                or audio_encoding.get("channelCount") != 2
            )
        ):
            raise EpisodeProductionError(
                "RenderManifest audio output must use canonical 48 kHz stereo"
            )

        root_identity = {
            "schemaVersion": "v5.m13-composition-identity.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "timelineRef": timeline["timelineRef"],
        }
        composition_ref = f"m13-composition-{_digest(root_identity)}"
        roots = self._render_domain_payload_records(
            context["snapshot"], record_kind="Composition"
        )
        versions_with_records = self._render_domain_payload_records(
            context["snapshot"], record_kind="CompositionVersion"
        )
        manifests_with_records = self._render_domain_payload_records(
            context["snapshot"], record_kind="RenderManifest"
        )
        if len(roots) > 1:
            raise RepositoryUnavailableError("Composition authority is ambiguous")
        if not roots and (versions_with_records or manifests_with_records):
            raise RepositoryUnavailableError(
                "Composition descendant evidence has no root"
            )
        if roots and not versions_with_records and manifests_with_records:
            raise RepositoryUnavailableError(
                "RenderManifest evidence has no CompositionVersion"
            )
        created_at = self._clock()
        if roots:
            root_record = roots[0][0]
            composition = validate_composition(roots[0][1]).as_dict()
            if (
                root_record.get("recordRef") != composition["compositionRef"]
                or root_record.get("recordVersion") != 1
                or root_record.get("createdAt") != composition["createdAt"]
                or composition["workspaceRef"] != workspace
                or composition["productionRunRef"] != run_ref
                or composition["projectRef"] != context["run"]["projectRef"]
                or composition["seriesRef"] != context["run"]["seriesRef"]
                or composition["episodeRef"] != context["run"]["episodeRef"]
                or composition["timelineRef"] != timeline["timelineRef"]
            ):
                raise RepositoryUnavailableError(
                    "Composition evidence envelope is invalid"
                )
            if composition["compositionRef"] != composition_ref:
                raise RepositoryUnavailableError(
                    "a second Composition authority is forbidden"
                )
        else:
            composition = build_composition(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "projectRef": context["run"]["projectRef"],
                    "seriesRef": context["run"]["seriesRef"],
                    "episodeRef": context["run"]["episodeRef"],
                    "compositionRef": composition_ref,
                    "timelineRef": timeline["timelineRef"],
                    "createdAt": created_at,
                    "provenance": COMPOSITION_PROVENANCE,
                    "publicationAllowed": False,
                }
            )

        versions_with_records.sort(
            key=lambda item: item[1].get("versionNumber", -1)
        )
        versions: list[dict[str, Any]] = []
        predecessor = None
        for expected_number, (record, payload) in enumerate(
            versions_with_records, start=1
        ):
            value = validate_composition_version(
                payload, predecessor=predecessor
            ).as_dict()
            if (
                value["versionNumber"] != expected_number
                or value["compositionRef"] != composition["compositionRef"]
                or value["timelineRef"] != timeline["timelineRef"]
                or value["workspaceRef"] != workspace
                or value["productionRunRef"] != run_ref
                or record.get("recordRef") != value["compositionVersionRef"]
                or record.get("recordVersion") != expected_number
                or record.get("createdAt") != value["createdAt"]
            ):
                raise RepositoryUnavailableError(
                    "CompositionVersion journal is invalid"
                )
            versions.append(value)
            predecessor = value
        validated_manifests: list[tuple[dict[str, Any], dict[str, Any]]] = []
        versions_by_ref = {
            item["compositionVersionRef"]: item for item in versions
        }
        for record, payload in manifests_with_records:
            value = validate_render_manifest(payload).as_dict()
            bound_version = versions_by_ref.get(value["compositionVersionRef"])
            if (
                record.get("recordRef") != value["renderManifestRef"]
                or record.get("recordVersion") != 1
                or record.get("createdAt") != value["createdAt"]
                or value["workspaceRef"] != workspace
                or value["productionRunRef"] != run_ref
                or not isinstance(bound_version, Mapping)
                or value["compositionVersionDigest"]
                != bound_version["payloadDigest"]
                or value["timelineVersionRef"]
                != bound_version["timelineVersionRef"]
                or value["timelineVersionDigest"]
                != bound_version["timelineVersionDigest"]
            ):
                raise RepositoryUnavailableError(
                    "RenderManifest evidence envelope is invalid"
                )
            validated_manifests.append((record, value))
        manifests_with_records = validated_manifests
        matching_versions = [
            item
            for item in versions
            if item["timelineVersionRef"] == timeline_version_ref
            and item["timelineVersionDigest"] == timeline_version_digest
        ]
        if len(matching_versions) > 1:
            raise RepositoryUnavailableError(
                "CompositionVersion Timeline binding is ambiguous"
            )
        new_version = False
        if matching_versions:
            composition_version = matching_versions[0]
            if composition_version != versions[-1]:
                raise StaleInputError("CompositionVersion history cannot regress")
            expected_composition_version = self._project_composition_version(
                context=context,
                restored=restored_timeline,
                composition=composition,
                composition_version_ref=composition_version[
                    "compositionVersionRef"
                ],
                version_number=composition_version["versionNumber"],
                predecessor=(versions[-2] if len(versions) > 1 else None),
                created_at=composition_version["createdAt"],
            )
            if expected_composition_version != composition_version:
                raise StaleInputError("CompositionVersion source authority is stale")
        else:
            version_number = len(versions) + 1
            composition_version_ref = (
                f"{composition_ref}-version-{version_number}"
            )
            composition_version = self._project_composition_version(
                context=context,
                restored=restored_timeline,
                composition=composition,
                composition_version_ref=composition_version_ref,
                version_number=version_number,
                predecessor=(versions[-1] if versions else None),
                created_at=created_at,
            )
            new_version = True

        if profile["subtitleMode"] == "BURN_IN":
            script_text = self._current_script_text_projection(context=context)
            self._current_font_projection(
                context=context,
                asset_version_ref=profile["subtitleFontAssetVersionRef"],
                asset_version_digest=profile[
                    "subtitleFontAssetVersionDigest"
                ],
                required_text=script_text["resolvedText"],
            )
        manifest_identity = {
            "schemaVersion": "v5.m13-render-manifest-identity.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "timelineVersionRef": timeline_version_ref,
            "timelineVersionDigest": timeline_version_digest,
            "compositionVersionRef": composition_version[
                "compositionVersionRef"
            ],
            "compositionVersionDigest": composition_version["payloadDigest"],
            "renderProfile": profile,
            "toolchain": self.render_toolchain_identity,
            "digestSpecs": render_manifest_digest_specs(),
        }
        manifest_ref = f"m13-render-manifest-{_digest(manifest_identity)}"
        manifest_matches = [
            (record, payload)
            for record, payload in manifests_with_records
            if payload.get("renderManifestRef") == manifest_ref
        ]
        if len(manifest_matches) > 1:
            raise RepositoryUnavailableError("RenderManifest identity is ambiguous")

        request_digest = _digest(
            {
                "schemaVersion": M13_RENDER_DOMAIN_REQUEST_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "operationRef": operation_ref,
                "idempotencyKey": client_key,
                "expectedRunVersion": expected_run_version,
                "timelineVersionRef": timeline_version_ref,
                "timelineVersionDigest": timeline_version_digest,
                "renderProfile": profile,
                "renderToolchainIdentity": self.render_toolchain_identity,
                "runDigest": context["run"]["payloadDigest"],
                "scriptVersionRef": context["scriptVersionRef"],
                "scriptVersionDigest": context["scriptVersionDigest"],
                "storyboardVersionRef": context["storyboardVersionRef"],
                "storyboardVersionDigest": context[
                    "storyboardVersionDigest"
                ],
                "compositionVersionDigest": composition_version[
                    "payloadDigest"
                ],
            }
        )
        replay_key = self._render_domain_record_idempotency_key(
            client_key, "render-manifest"
        )
        existing_replay = self.evidence.get_record_by_idempotency_key(
            workspace, run_ref, replay_key
        )
        if existing_replay is not None:
            if existing_replay.get("requestDigest") != request_digest:
                raise IdempotencyConflictError(
                    "M13-R1A idempotency content changed"
                )
            restored = self._restore_render_domain(
                context,
                render_manifest_ref=existing_replay.get("recordRef"),
            )
            return self._render_domain_projection(
                restored,
                evidence_revision=context["snapshot"].revisionToken,
                replayed=True,
            )
        if manifest_matches:
            existing_record, existing_payload = manifest_matches[0]
            if existing_record.get("idempotencyKey") != replay_key:
                raise IdempotencyConflictError(
                    "RenderManifest already exists under another idempotency key"
                )
            manifest = validate_render_manifest(existing_payload).as_dict()
            restored = self._restore_render_domain(
                context,
                render_manifest_ref=manifest["renderManifestRef"],
            )
            return self._render_domain_projection(
                restored,
                evidence_revision=context["snapshot"].revisionToken,
                replayed=True,
            )

        timing_digest = None
        if profile["subtitleMode"] != "NONE":
            subtitle_cues = self._render_subtitle_cues(
                context=context,
                layout=self._editing_preview_layout(
                    restored_timeline,
                    allow_video_edits=True,
                ),
            )
            timing_digest = canonical_subtitle_timing_digest(subtitle_cues)
        manifest = build_render_manifest(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "renderManifestRef": manifest_ref,
                "timelineVersionRef": timeline_version_ref,
                "timelineVersionDigest": timeline_version_digest,
                "compositionVersionRef": composition_version[
                    "compositionVersionRef"
                ],
                "compositionVersionDigest": composition_version["payloadDigest"],
                "outputProfile": profile["outputProfile"],
                "videoEncoding": profile["videoEncoding"],
                "colorMetadata": profile["colorMetadata"],
                "audioEncoding": profile["audioEncoding"],
                "subtitleMode": profile["subtitleMode"],
                "subtitleTimingDigest": timing_digest,
                "subtitleFontAssetVersionRef": profile[
                    "subtitleFontAssetVersionRef"
                ],
                "subtitleFontAssetVersionDigest": profile[
                    "subtitleFontAssetVersionDigest"
                ],
                **self.render_toolchain_identity,
                **render_manifest_digest_specs(),
                "publicationAllowed": False,
                "masterState": "NOT_CREATED",
                "exportState": "NOT_CREATED",
                "createdAt": created_at,
            }
        )
        records: list[EvidenceRecord] = []
        if not roots:
            records.append(
                self._render_domain_evidence_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="Composition",
                    record_ref=composition["compositionRef"],
                    record_version=1,
                    client_key=client_key,
                    slot="composition-root",
                    request_digest=request_digest,
                    created_at=composition["createdAt"],
                    payload=composition,
                )
            )
        if new_version:
            records.append(
                self._render_domain_evidence_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="CompositionVersion",
                    record_ref=composition_version["compositionVersionRef"],
                    record_version=composition_version["versionNumber"],
                    client_key=client_key,
                    slot="composition-version",
                    request_digest=request_digest,
                    created_at=composition_version["createdAt"],
                    payload=composition_version,
                )
            )
        records.append(
            self._render_domain_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind="RenderManifest",
                record_ref=manifest["renderManifestRef"],
                record_version=1,
                client_key=client_key,
                slot="render-manifest",
                request_digest=request_digest,
                created_at=manifest["createdAt"],
                payload=manifest,
            )
        )
        journal_head = self._stable_record_head(
            workspace,
            run_ref,
            context["snapshot"].revisionToken,
        )
        _, replayed = self.evidence.append_records(
            records,
            expected_record_journal_head=journal_head,
            expected_evidence_revision_token=context["snapshot"].revisionToken,
        )
        result_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        restored = self._restore_render_domain(
            result_context,
            render_manifest_ref=manifest["renderManifestRef"],
        )
        return self._render_domain_projection(
            restored,
            evidence_revision=result_context["snapshot"].revisionToken,
            replayed=replayed,
        )

    def get_composition_render_manifest(
        self,
        workspace_ref: str,
        run_ref: str,
        *,
        render_manifest_ref: str | None = None,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        selected_manifest_ref = (
            None
            if render_manifest_ref is None
            else _required_ref(render_manifest_ref, "renderManifestRef")
        )
        context = self._timeline_authority_context(
            workspace,
            production_run,
            expected_run_version=None,
        )
        restored = self._restore_render_domain(
            context,
            render_manifest_ref=selected_manifest_ref,
        )
        return self._render_domain_projection(
            restored,
            evidence_revision=context["snapshot"].revisionToken,
            replayed=False,
        )

    def require_current_render_manifest(
        self,
        workspace_ref: str,
        run_ref: str,
        *,
        render_manifest_ref: str,
        render_manifest_digest: str,
    ) -> dict[str, Any]:
        if not _is_sha256(render_manifest_digest):
            raise EpisodeProductionError("renderManifestDigest is invalid")
        result = self.get_composition_render_manifest(
            workspace_ref,
            run_ref,
            render_manifest_ref=render_manifest_ref,
        )
        if result["renderManifest"]["payloadDigest"] != render_manifest_digest:
            raise StaleInputError("RenderManifest digest is stale")
        return result

    @staticmethod
    def _render_candidate_record_envelope(
        *,
        record: Mapping[str, Any],
        payload: Mapping[str, Any],
        reference_field: str,
        label: str,
        workspace: str,
        run_ref: str,
    ) -> None:
        if (
            record.get("recordRef") != payload.get(reference_field)
            or record.get("recordVersion") != 1
            or record.get("createdAt") != payload.get("createdAt")
            or record.get("payloadDigest") != payload.get("payloadDigest")
            or payload.get("workspaceRef") != workspace
            or payload.get("productionRunRef") != run_ref
        ):
            raise RepositoryUnavailableError(f"{label} evidence envelope is invalid")

    def _restore_render_candidates(
        self,
        context: Mapping[str, Any],
        *,
        render_candidate_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Restore and freshly remeasure every selected technical candidate."""

        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        snapshot = context["snapshot"]

        def records(
            kind: str,
            wrapper,
            reference_field: str,
        ) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
            index: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
            for record, payload in self._render_domain_payload_records(
                snapshot, record_kind=kind
            ):
                value = wrapper.from_mapping(payload).as_dict()
                self._render_candidate_record_envelope(
                    record=record,
                    payload=value,
                    reference_field=reference_field,
                    label=kind,
                    workspace=workspace,
                    run_ref=run_ref,
                )
                reference = value[reference_field]
                if reference in index:
                    raise RepositoryUnavailableError(
                        f"{kind} evidence identity is ambiguous"
                    )
                index[reference] = (record, value)
            return index

        runtimes = records(
            "RenderRuntimeEvidence", RenderRuntimeEvidence, "runtimeEvidenceRef"
        )
        artifacts = records(
            "RenderArtifactEvidence", RenderArtifactEvidence, "artifactEvidenceRef"
        )
        results = records("RenderResult", RenderResult, "renderResultRef")
        candidates = records(
            "RenderCandidate", RenderCandidate, "renderCandidateRef"
        )
        execution_requests: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        for record, payload in self._render_domain_payload_records(
            snapshot, record_kind="RenderExecutionRequest"
        ):
            try:
                value = validate_render_execution_request(payload)
            except Exception as exc:
                raise RepositoryUnavailableError(
                    "RenderExecutionRequest evidence is invalid"
                ) from exc
            reference = value["executionRequestRef"]
            if (
                record.get("recordRef") != reference
                or record.get("recordVersion") != 1
                or record.get("payloadDigest") != value["payloadDigest"]
                or value["workspaceRef"] != workspace
                or value["productionRunRef"] != run_ref
                or reference in execution_requests
            ):
                raise RepositoryUnavailableError(
                    "RenderExecutionRequest evidence envelope is invalid"
                )
            execution_requests[reference] = (record, value)
        selected = [
            value
            for _, value in candidates.values()
            if render_candidate_ref is None
            or value["renderCandidateRef"] == render_candidate_ref
        ]
        if render_candidate_ref is not None and len(selected) != 1:
            raise RecordNotFoundError("RenderCandidate was not found")
        selected.sort(key=lambda item: (item["createdAt"], item["renderCandidateRef"]))
        if self.composition is None or not callable(
            getattr(self.composition, "inspect_render_candidate", None)
        ):
            if selected:
                raise WorkerUnavailableError(
                    "RenderCandidate verifier is not configured"
                )
            return []
        restored: list[dict[str, Any]] = []
        for candidate in selected:
            domain = self._restore_render_domain(
                context,
                render_manifest_ref=candidate["renderManifestRef"],
            )
            manifest = domain["renderManifest"]
            composition_version = domain["compositionVersion"]
            timeline_version = domain["timeline"]["timelineVersion"].as_dict()
            runtime_entry = runtimes.get(candidate["runtimeEvidenceRef"])
            artifact_entry = artifacts.get(candidate["artifactEvidenceRef"])
            result_entry = results.get(candidate["renderResultRef"])
            request_entry = execution_requests.get(
                candidate["executionRequestRef"]
            )
            if (
                runtime_entry is None
                or artifact_entry is None
                or result_entry is None
                or request_entry is None
            ):
                raise RepositoryUnavailableError(
                    "RenderCandidate evidence closure is incomplete"
                )
            runtime = runtime_entry[1]
            artifact = artifact_entry[1]
            render_result = result_entry[1]
            execution_request = request_entry[1]
            if (
                candidate["projectRef"] != context["run"]["projectRef"]
                or candidate["seriesRef"] != context["run"]["seriesRef"]
                or candidate["episodeRef"] != context["run"]["episodeRef"]
                or candidate["timelineVersionRef"]
                != timeline_version["timelineVersionRef"]
                or candidate["timelineVersionDigest"]
                != timeline_version["payloadDigest"]
                or candidate["compositionVersionRef"]
                != composition_version["compositionVersionRef"]
                or candidate["compositionVersionDigest"]
                != composition_version["payloadDigest"]
                or candidate["renderManifestDigest"] != manifest["payloadDigest"]
                or candidate["renderProfileRef"]
                != manifest["outputProfile"]["profileRef"]
                or candidate["executionRequestRef"]
                != runtime["executionRequestRef"]
                or candidate["executionRequestDigest"]
                != runtime["executionRequestDigest"]
                or candidate["executionRequestDigest"]
                != execution_request["payloadDigest"]
                or candidate["runtimeEvidenceDigest"] != runtime["payloadDigest"]
                or candidate["artifactEvidenceDigest"] != artifact["payloadDigest"]
                or candidate["renderResultDigest"] != render_result["payloadDigest"]
                or render_result["executionRequestRef"]
                != candidate["executionRequestRef"]
                or render_result["executionRequestDigest"]
                != candidate["executionRequestDigest"]
                or render_result["renderManifestRef"]
                != candidate["renderManifestRef"]
                or render_result["renderManifestDigest"]
                != candidate["renderManifestDigest"]
                or render_result["runtimeEvidenceRef"]
                != candidate["runtimeEvidenceRef"]
                or render_result["runtimeEvidenceDigest"]
                != candidate["runtimeEvidenceDigest"]
                or render_result["artifactEvidenceRef"]
                != candidate["artifactEvidenceRef"]
                or render_result["artifactEvidenceDigest"]
                != candidate["artifactEvidenceDigest"]
            ):
                raise StaleInputError("RenderCandidate lineage is stale")
            artifact_pairs = {
                "executionRequestRef": candidate["executionRequestRef"],
                "executionRequestDigest": candidate["executionRequestDigest"],
                "renderManifestRef": candidate["renderManifestRef"],
                "renderManifestDigest": candidate["renderManifestDigest"],
                "runtimeEvidenceRef": candidate["runtimeEvidenceRef"],
                "runtimeEvidenceDigest": candidate["runtimeEvidenceDigest"],
                "storageBindingRef": candidate["storageBindingRef"],
                "mediaType": candidate["mediaType"],
                "byteSize": candidate["byteSize"],
                "fileDigest": candidate["fileDigest"],
                "decodedFramePixelDigest": candidate[
                    "decodedFramePixelDigest"
                ],
                "decodedFramePixelDigestSpec": candidate[
                    "decodedFramePixelDigestSpec"
                ],
                "pcmContentDigest": candidate["pcmContentDigest"],
                "pcmContentDigestSpec": candidate["pcmContentDigestSpec"],
                "subtitleTimingDigest": candidate["subtitleTimingDigest"],
                "subtitleTimingDigestSpec": candidate[
                    "subtitleTimingDigestSpec"
                ],
                "mediaProbe": candidate["mediaProbe"],
            }
            if any(artifact.get(field) != value for field, value in artifact_pairs.items()):
                raise StaleInputError("RenderCandidate artifact binding is stale")
            if any(
                candidate[field] != runtime[field]
                for field in (
                    "rendererIdentity",
                    "rendererVersion",
                    "ffmpegBinaryDigest",
                    "ffprobeBinaryDigest",
                )
            ) or any(
                candidate[field] != manifest[field]
                for field in (
                    "rendererIdentity",
                    "rendererVersion",
                    "ffmpegBinaryDigest",
                    "ffprobeBinaryDigest",
                )
            ):
                raise StaleInputError("RenderCandidate runtime identity is stale")
            projection = self._editing_effect_preview_projection(
                context=context,
                restored=domain["timeline"],
                allow_video_edits=True,
            )
            subtitle_cues = (
                []
                if manifest["subtitleMode"] == "NONE"
                else self._render_subtitle_cues(
                    context=context,
                    layout=projection["layout"],
                )
            )
            timing_digest = canonical_subtitle_timing_digest(subtitle_cues)
            if candidate["subtitleTimingDigest"] != timing_digest:
                raise StaleInputError("RenderCandidate subtitle timing is stale")
            render_profile = {
                field: deepcopy(manifest[field])
                for field in (
                    "outputProfile",
                    "videoEncoding",
                    "colorMetadata",
                    "audioEncoding",
                    "subtitleMode",
                    "subtitleTimingDigest",
                    "subtitleFontAssetVersionRef",
                    "subtitleFontAssetVersionDigest",
                    "rendererIdentity",
                    "rendererVersion",
                    "ffmpegBinaryDigest",
                    "ffprobeBinaryDigest",
                )
            }
            expected_execution_request = build_render_execution_request(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "executionRequestRef": candidate["executionRequestRef"],
                    "timelineVersionRef": timeline_version[
                        "timelineVersionRef"
                    ],
                    "timelineVersionDigest": timeline_version["payloadDigest"],
                    "compositionVersionRef": composition_version[
                        "compositionVersionRef"
                    ],
                    "compositionVersionDigest": composition_version[
                        "payloadDigest"
                    ],
                    "renderManifestRef": manifest["renderManifestRef"],
                    "renderManifestDigest": manifest["payloadDigest"],
                    "allInputBindingsDigest": render_input_bindings_digest(
                        composition_version=composition_version,
                        composition_command=projection["compositionCommand"],
                        subtitle_cues=subtitle_cues,
                    ),
                    "compositionCommandDigest": composition_command_digest(
                        projection["compositionCommand"]
                    ),
                    "runtimeBindingDigest": runtime_binding_digest(
                        render_profile
                    ),
                    "outputArtifactBindingRef": candidate[
                        "storageBindingRef"
                    ],
                    "renderProfile": render_profile,
                    "publicationAllowed": False,
                }
            )
            if execution_request != expected_execution_request:
                raise StaleInputError(
                    "RenderCandidate sealed execution request is stale"
                )
            expected_artifact = {
                **deepcopy(artifact),
                "ffmpegBinaryDigest": candidate["ffmpegBinaryDigest"],
                "ffprobeBinaryDigest": candidate["ffprobeBinaryDigest"],
            }
            try:
                content = self.composition.inspect_render_candidate(
                    workspace_ref=workspace,
                    production_run_ref=run_ref,
                    storage_binding_ref=candidate["storageBindingRef"],
                    expected=expected_artifact,
                )
            except EpisodeProductionError:
                raise
            except Exception as exc:
                raise ArtifactRejectedError(
                    "RenderCandidate artifact verification failed"
                ) from exc
            restored.append(
                {
                    "executionRequest": deepcopy(execution_request),
                    "renderCandidate": deepcopy(candidate),
                    "runtimeEvidence": deepcopy(runtime),
                    "artifactEvidence": deepcopy(artifact),
                    "renderResult": deepcopy(render_result),
                    "content": content,
                }
            )
        return restored

    @staticmethod
    def _render_candidate_projection(
        restored: Sequence[Mapping[str, Any]],
        *,
        evidence_revision: str,
        replayed: bool,
        detail: bool,
    ) -> dict[str, Any]:
        if detail:
            if len(restored) != 1:
                raise RecordNotFoundError("RenderCandidate was not found")
            value = restored[0]
            return {
                "renderCandidate": deepcopy(value["renderCandidate"]),
                "runtimeEvidence": deepcopy(value["runtimeEvidence"]),
                "artifactEvidence": deepcopy(value["artifactEvidence"]),
                "renderResult": deepcopy(value["renderResult"]),
                "publicationAllowed": False,
                "masterState": "NOT_CREATED",
                "exportState": "NOT_CREATED",
                "assetAdmissionState": "NOT_ADMITTED",
                "evidenceRevision": evidence_revision,
                "idempotentReplay": replayed,
            }
        return {
            "renderCandidates": [
                deepcopy(item["renderCandidate"]) for item in restored
            ],
            "publicationAllowed": False,
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
            "assetAdmissionState": "NOT_ADMITTED",
            "evidenceRevision": evidence_revision,
            "idempotentReplay": replayed,
        }

    def create_render_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Execute one exact manifest without admission, QC, approval or export."""

        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "timelineVersionRef",
            "timelineVersionDigest",
            "compositionVersionRef",
            "compositionVersionDigest",
            "renderManifestRef",
            "renderManifestDigest",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M13-R1B contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        operation_ref = _required_ref(command.get("operationRef"), "operationRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        expected_run_version = _positive_version(
            command.get("expectedRunVersion"), "expectedRunVersion"
        )
        references = {}
        for field in (
            "timelineVersionRef",
            "compositionVersionRef",
            "renderManifestRef",
        ):
            references[field] = _required_ref(command.get(field), field)
        for field in (
            "timelineVersionDigest",
            "compositionVersionDigest",
            "renderManifestDigest",
        ):
            value = command.get(field)
            if not _is_sha256(value):
                raise EpisodeProductionError(f"{field} is invalid")
            references[field] = value
        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        domain = self._restore_render_domain(
            context,
            render_manifest_ref=references["renderManifestRef"],
        )
        timeline_version = domain["timeline"]["timelineVersion"].as_dict()
        composition_version = domain["compositionVersion"]
        manifest = domain["renderManifest"]
        if (
            references["timelineVersionRef"]
            != timeline_version["timelineVersionRef"]
            or references["timelineVersionDigest"]
            != timeline_version["payloadDigest"]
            or references["compositionVersionRef"]
            != composition_version["compositionVersionRef"]
            or references["compositionVersionDigest"]
            != composition_version["payloadDigest"]
            or references["renderManifestDigest"] != manifest["payloadDigest"]
        ):
            raise StaleInputError("RenderCandidate exact input authority is stale")
        request_digest = _digest(
            {
                "schemaVersion": "v5.m13-render-candidate-command.v1",
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "operationRef": operation_ref,
                "idempotencyKey": client_key,
                "expectedRunVersion": expected_run_version,
                **references,
                "runDigest": context["run"]["payloadDigest"],
                "renderToolchainIdentity": self.render_toolchain_identity,
            }
        )
        replay_key = self._render_domain_record_idempotency_key(
            client_key,
            "render-candidate",
            domain_stage="m13-r1b-render-candidate",
        )
        replay = self.evidence.get_record_by_idempotency_key(
            workspace, run_ref, replay_key
        )
        if replay is not None:
            if (
                replay.get("recordKind") != "RenderCandidate"
                or replay.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError(
                    "M13-R1B idempotency content changed"
                )
            restored = self._restore_render_candidates(
                context,
                render_candidate_ref=replay.get("recordRef"),
            )
            return self._render_candidate_projection(
                restored,
                evidence_revision=context["snapshot"].revisionToken,
                replayed=True,
                detail=True,
            )
        if (
            self.composition is None
            or not callable(getattr(self.composition, "render_candidate", None))
            or not callable(
                getattr(self.composition, "inspect_render_candidate", None)
            )
        ):
            raise WorkerUnavailableError("RenderCandidate executor is unavailable")
        preview_projection = self._editing_effect_preview_projection(
            context=context,
            restored=domain["timeline"],
            allow_video_edits=True,
        )
        subtitle_cues = (
            []
            if manifest["subtitleMode"] == "NONE"
            else self._render_subtitle_cues(
                context=context,
                layout=preview_projection["layout"],
            )
        )
        timing_digest = canonical_subtitle_timing_digest(subtitle_cues)
        if (
            manifest["subtitleMode"] != "NONE"
            and manifest["subtitleTimingDigest"] != timing_digest
        ):
            raise StaleInputError("RenderManifest subtitle timing is stale")
        font_projection = None
        font_required_text = None
        if manifest["subtitleMode"] == "BURN_IN":
            font_required_text = self._current_script_text_projection(
                context=context
            )["resolvedText"]
            font_projection = self._current_font_projection(
                context=context,
                asset_version_ref=manifest["subtitleFontAssetVersionRef"],
                asset_version_digest=manifest[
                    "subtitleFontAssetVersionDigest"
                ],
                required_text=font_required_text,
            )
        render_profile = {
            field: deepcopy(manifest[field])
            for field in (
                "outputProfile",
                "videoEncoding",
                "colorMetadata",
                "audioEncoding",
                "subtitleMode",
                "subtitleTimingDigest",
                "subtitleFontAssetVersionRef",
                "subtitleFontAssetVersionDigest",
                "rendererIdentity",
                "rendererVersion",
                "ffmpegBinaryDigest",
                "ffprobeBinaryDigest",
            )
        }
        input_digest = render_input_bindings_digest(
            composition_version=composition_version,
            composition_command=preview_projection["compositionCommand"],
            subtitle_cues=subtitle_cues,
        )
        execution_identity = {
            "schemaVersion": "v4.m13-render-execution-identity.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "operationRef": operation_ref,
            **references,
            "allInputBindingsDigest": input_digest,
            "compositionCommandDigest": composition_command_digest(
                preview_projection["compositionCommand"]
            ),
            "runtimeBindingDigest": runtime_binding_digest(render_profile),
            "renderProfile": render_profile,
        }
        execution_ref = "m13-render-execution-" + _digest(execution_identity)[:32]
        storage_binding_ref = "m13-render-storage-" + _digest(
            {
                "executionRequestRef": execution_ref,
                "renderManifestRef": manifest["renderManifestRef"],
                "renderManifestDigest": manifest["payloadDigest"],
            }
        )[:32]
        execution_request = build_render_execution_request(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "executionRequestRef": execution_ref,
                "timelineVersionRef": timeline_version["timelineVersionRef"],
                "timelineVersionDigest": timeline_version["payloadDigest"],
                "compositionVersionRef": composition_version[
                    "compositionVersionRef"
                ],
                "compositionVersionDigest": composition_version["payloadDigest"],
                "renderManifestRef": manifest["renderManifestRef"],
                "renderManifestDigest": manifest["payloadDigest"],
                "allInputBindingsDigest": input_digest,
                "compositionCommandDigest": composition_command_digest(
                    preview_projection["compositionCommand"]
                ),
                "runtimeBindingDigest": runtime_binding_digest(render_profile),
                "outputArtifactBindingRef": storage_binding_ref,
                "renderProfile": render_profile,
                "publicationAllowed": False,
            }
        )
        try:
            execution = self.composition.render_candidate(
                execution_request,
                composition_version=composition_version,
                composition_command=preview_projection["compositionCommand"],
                resolved_artifacts=preview_projection["resolvedArtifacts"],
                subtitle_cues=subtitle_cues,
                font_projection=font_projection,
                font_required_text=font_required_text,
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise ArtifactRejectedError(
                "deterministic RenderCandidate execution failed"
            ) from exc
        expected_execution_fields = {
            "schemaVersion": "v4.m13-render-execution-result.v1",
            "executionRequestRef": execution_ref,
            "executionRequestDigest": execution_request["payloadDigest"],
            "outputArtifactBindingRef": storage_binding_ref,
            "rendererIdentity": manifest["rendererIdentity"],
            "rendererVersion": manifest["rendererVersion"],
            "ffmpegBinaryDigest": manifest["ffmpegBinaryDigest"],
            "ffprobeBinaryDigest": manifest["ffprobeBinaryDigest"],
            "gpuUsed": False,
            "providerUsed": False,
            "publicationAllowed": False,
        }
        if not isinstance(execution, Mapping) or any(
            execution.get(field) != value
            for field, value in expected_execution_fields.items()
        ):
            raise ArtifactRejectedError("RenderCandidate execution result is stale")
        if (
            execution.get("subtitleTimingDigest") != timing_digest
            or execution.get("subtitleTimingDigestSpec")
            != manifest["subtitleTimingDigestSpec"]
            or not isinstance(execution.get("outputMediaProbe"), Mapping)
            or not isinstance(execution.get("outputByteSize"), int)
            or execution["outputByteSize"] < 1
        ):
            raise ArtifactRejectedError("RenderCandidate content result is invalid")

        # Close the render-to-journal race: every authority is freshly read
        # again immediately before the append-only CAS.
        fresh_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        fresh_domain = self._restore_render_domain(
            fresh_context,
            render_manifest_ref=manifest["renderManifestRef"],
        )
        fresh_preview_projection = self._editing_effect_preview_projection(
            context=fresh_context,
            restored=fresh_domain["timeline"],
            allow_video_edits=True,
        )
        fresh_subtitle_cues = (
            []
            if manifest["subtitleMode"] == "NONE"
            else self._render_subtitle_cues(
                context=fresh_context,
                layout=fresh_preview_projection["layout"],
            )
        )
        fresh_font_projection = None
        fresh_font_required_text = None
        if manifest["subtitleMode"] == "BURN_IN":
            fresh_font_required_text = self._current_script_text_projection(
                context=fresh_context
            )["resolvedText"]
            fresh_font_projection = self._current_font_projection(
                context=fresh_context,
                asset_version_ref=manifest["subtitleFontAssetVersionRef"],
                asset_version_digest=manifest[
                    "subtitleFontAssetVersionDigest"
                ],
                required_text=fresh_font_required_text,
            )
        if (
            fresh_domain["compositionVersion"] != composition_version
            or fresh_domain["renderManifest"] != manifest
            or fresh_preview_projection != preview_projection
            or fresh_subtitle_cues != subtitle_cues
            or fresh_font_projection != font_projection
            or fresh_font_required_text != font_required_text
        ):
            raise StaleInputError("RenderCandidate authority changed during execution")
        created_at = self._clock()
        runtime_ref = "m13-render-runtime-" + _digest(
            {
                "executionRequestDigest": execution_request["payloadDigest"],
                "ffmpegBinaryDigest": execution["ffmpegBinaryDigest"],
                "ffprobeBinaryDigest": execution["ffprobeBinaryDigest"],
            }
        )[:32]
        runtime = build_render_runtime_evidence(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "runtimeEvidenceRef": runtime_ref,
                "executionRequestRef": execution_ref,
                "executionRequestDigest": execution_request["payloadDigest"],
                "rendererIdentity": execution["rendererIdentity"],
                "rendererVersion": execution["rendererVersion"],
                "ffmpegBinaryDigest": execution["ffmpegBinaryDigest"],
                "ffprobeBinaryDigest": execution["ffprobeBinaryDigest"],
                "gpuUsed": False,
                "providerUsed": False,
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )
        artifact_ref = "m13-render-artifact-" + _digest(
            {
                "executionRequestDigest": execution_request["payloadDigest"],
                "fileDigest": execution["fileDigest"],
                "decodedFramePixelDigest": execution[
                    "decodedFramePixelDigest"
                ],
                "pcmContentDigest": execution["pcmContentDigest"],
                "subtitleTimingDigest": execution["subtitleTimingDigest"],
            }
        )[:32]
        sidecar = execution.get("subtitleSidecar")
        public_sidecar = (
            None
            if sidecar is None
            else {
                "mediaType": sidecar["mediaType"],
                "byteSize": sidecar["byteSize"],
                "fileDigest": sidecar["fileDigest"],
                "storageBindingRef": storage_binding_ref + "-subtitle",
            }
        )
        artifact = build_render_artifact_evidence(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "artifactEvidenceRef": artifact_ref,
                "executionRequestRef": execution_ref,
                "executionRequestDigest": execution_request["payloadDigest"],
                "renderManifestRef": manifest["renderManifestRef"],
                "renderManifestDigest": manifest["payloadDigest"],
                "runtimeEvidenceRef": runtime_ref,
                "runtimeEvidenceDigest": runtime["payloadDigest"],
                "storageBindingRef": storage_binding_ref,
                "mediaType": "video/mp4",
                "byteSize": execution["outputByteSize"],
                "fileDigest": execution["fileDigest"],
                "decodedFramePixelDigest": execution[
                    "decodedFramePixelDigest"
                ],
                "decodedFramePixelDigestSpec": execution[
                    "decodedFramePixelDigestSpec"
                ],
                "pcmContentDigest": execution["pcmContentDigest"],
                "pcmContentDigestSpec": execution["pcmContentDigestSpec"],
                "subtitleTimingDigest": execution["subtitleTimingDigest"],
                "subtitleTimingDigestSpec": execution[
                    "subtitleTimingDigestSpec"
                ],
                "mediaProbe": execution["outputMediaProbe"],
                "subtitleSidecar": public_sidecar,
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )
        try:
            self.composition.inspect_render_candidate(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                storage_binding_ref=storage_binding_ref,
                expected={
                    **artifact,
                    "ffmpegBinaryDigest": runtime["ffmpegBinaryDigest"],
                    "ffprobeBinaryDigest": runtime["ffprobeBinaryDigest"],
                },
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise ArtifactRejectedError(
                "RenderCandidate artifact changed before evidence append"
            ) from exc
        result_ref = "m13-render-result-" + _digest(
            {
                "executionRequestDigest": execution_request["payloadDigest"],
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "runtimeEvidenceDigest": runtime["payloadDigest"],
            }
        )[:32]
        render_result = build_render_result(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "renderResultRef": result_ref,
                "executionRequestRef": execution_ref,
                "executionRequestDigest": execution_request["payloadDigest"],
                "renderManifestRef": manifest["renderManifestRef"],
                "renderManifestDigest": manifest["payloadDigest"],
                "runtimeEvidenceRef": runtime_ref,
                "runtimeEvidenceDigest": runtime["payloadDigest"],
                "artifactEvidenceRef": artifact_ref,
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "state": "SUCCEEDED",
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )
        candidate_ref = "m13-render-candidate-" + _digest(
            {
                "renderResultDigest": render_result["payloadDigest"],
                "renderManifestDigest": manifest["payloadDigest"],
            }
        )[:32]
        candidate = build_render_candidate(
            {
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "projectRef": context["run"]["projectRef"],
                "seriesRef": context["run"]["seriesRef"],
                "episodeRef": context["run"]["episodeRef"],
                "renderCandidateRef": candidate_ref,
                "timelineVersionRef": timeline_version["timelineVersionRef"],
                "timelineVersionDigest": timeline_version["payloadDigest"],
                "compositionVersionRef": composition_version[
                    "compositionVersionRef"
                ],
                "compositionVersionDigest": composition_version["payloadDigest"],
                "renderManifestRef": manifest["renderManifestRef"],
                "renderManifestDigest": manifest["payloadDigest"],
                "executionRequestRef": execution_ref,
                "executionRequestDigest": execution_request["payloadDigest"],
                "runtimeEvidenceRef": runtime_ref,
                "runtimeEvidenceDigest": runtime["payloadDigest"],
                "artifactEvidenceRef": artifact_ref,
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "renderResultRef": result_ref,
                "renderResultDigest": render_result["payloadDigest"],
                "renderProfileRef": manifest["outputProfile"]["profileRef"],
                "storageBindingRef": storage_binding_ref,
                "mediaType": "video/mp4",
                "fileDigest": artifact["fileDigest"],
                "byteSize": artifact["byteSize"],
                "decodedFramePixelDigest": artifact[
                    "decodedFramePixelDigest"
                ],
                "decodedFramePixelDigestSpec": artifact[
                    "decodedFramePixelDigestSpec"
                ],
                "pcmContentDigest": artifact["pcmContentDigest"],
                "pcmContentDigestSpec": artifact["pcmContentDigestSpec"],
                "subtitleTimingDigest": artifact["subtitleTimingDigest"],
                "subtitleTimingDigestSpec": artifact[
                    "subtitleTimingDigestSpec"
                ],
                "mediaProbe": artifact["mediaProbe"],
                "rendererIdentity": runtime["rendererIdentity"],
                "rendererVersion": runtime["rendererVersion"],
                "ffmpegBinaryDigest": runtime["ffmpegBinaryDigest"],
                "ffprobeBinaryDigest": runtime["ffprobeBinaryDigest"],
                "state": "RENDERED_CANDIDATE",
                "technicalValidationState": "PASS",
                "qcState": "NOT_RUN",
                "approvalState": "NOT_REQUESTED",
                "assetAdmissionState": "NOT_ADMITTED",
                "masterState": "NOT_CREATED",
                "exportState": "NOT_CREATED",
                "publicationAllowed": False,
                "createdAt": created_at,
            }
        )
        record_payloads = (
            (
                "RenderExecutionRequest",
                execution_ref,
                "render-execution-request",
                execution_request,
            ),
            ("RenderRuntimeEvidence", runtime_ref, "render-runtime", runtime),
            ("RenderArtifactEvidence", artifact_ref, "render-artifact", artifact),
            ("RenderResult", result_ref, "render-result", render_result),
            ("RenderCandidate", candidate_ref, "render-candidate", candidate),
        )
        records = [
            self._render_domain_evidence_record(
                workspace=workspace,
                run_ref=run_ref,
                record_kind=kind,
                record_ref=reference,
                record_version=1,
                client_key=client_key,
                slot=slot,
                request_digest=request_digest,
                created_at=created_at,
                payload=payload,
                domain_stage="m13-r1b-render-candidate",
            )
            for kind, reference, slot, payload in record_payloads
        ]
        journal_head = self._stable_record_head(
            workspace,
            run_ref,
            fresh_context["snapshot"].revisionToken,
        )
        self.evidence.append_records(
            records,
            expected_record_journal_head=journal_head,
            expected_evidence_revision_token=fresh_context["snapshot"].revisionToken,
        )
        result_context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=expected_run_version,
        )
        restored = self._restore_render_candidates(
            result_context,
            render_candidate_ref=candidate_ref,
        )
        return self._render_candidate_projection(
            restored,
            evidence_revision=result_context["snapshot"].revisionToken,
            replayed=False,
            detail=True,
        )

    def list_render_candidates(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        context = self._timeline_authority_context(
            workspace, production_run, expected_run_version=None
        )
        restored = self._restore_render_candidates(context)
        return self._render_candidate_projection(
            restored,
            evidence_revision=context["snapshot"].revisionToken,
            replayed=False,
            detail=False,
        )

    def get_render_candidate(
        self,
        workspace_ref: str,
        run_ref: str,
        render_candidate_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        candidate_ref = _required_ref(
            render_candidate_ref, "renderCandidateRef"
        )
        context = self._timeline_authority_context(
            workspace, production_run, expected_run_version=None
        )
        restored = self._restore_render_candidates(
            context, render_candidate_ref=candidate_ref
        )
        return self._render_candidate_projection(
            restored,
            evidence_revision=context["snapshot"].revisionToken,
            replayed=False,
            detail=True,
        )

    def get_render_candidate_content(
        self,
        workspace_ref: str,
        run_ref: str,
        render_candidate_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        production_run = _required_ref(run_ref, "productionRunRef")
        candidate_ref = _required_ref(
            render_candidate_ref, "renderCandidateRef"
        )
        context = self._timeline_authority_context(
            workspace, production_run, expected_run_version=None
        )
        restored = self._restore_render_candidates(
            context, render_candidate_ref=candidate_ref
        )
        if len(restored) != 1:
            raise RecordNotFoundError("RenderCandidate was not found")
        content = deepcopy(dict(restored[0]["content"]))
        content.update(
            {
                "fileName": f"{candidate_ref}.mp4",
                "contentDisposition": "inline",
                "cacheControl": "no-store",
            }
        )
        return content

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

    def _current_script_text_projection(
        self, *, context: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Resolve the one frozen SCRIPT_TEXT source from the current reader."""

        if self.script_text_reader is None or not callable(
            getattr(self.script_text_reader, "get_workspace", None)
        ):
            raise UpstreamNotReadyError(
                "current SCRIPT_TEXT authority is not configured"
            )
        run = context.get("run")
        if not isinstance(run, Mapping):
            raise RepositoryUnavailableError("current run authority is invalid")
        workspace = _required_ref(run.get("workspaceRef"), "workspaceRef")
        series_ref = _required_ref(run.get("seriesRef"), "seriesRef")
        episode_ref = _required_ref(run.get("episodeRef"), "episodeRef")
        try:
            raw = self.script_text_reader.get_workspace(
                workspace, series_ref, episode_ref
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "current SCRIPT_TEXT authority is unavailable"
            ) from exc
        if not isinstance(raw, Mapping):
            raise RepositoryUnavailableError(
                "current SCRIPT_TEXT projection is invalid"
            )
        script = raw.get("script")
        versions = raw.get("versions")
        upstream = run.get("upstreamSnapshot")
        frozen = upstream.get("script") if isinstance(upstream, Mapping) else None
        confirmed_ref = (
            script.get("confirmedScriptVersionRef")
            if isinstance(script, Mapping)
            else None
        )
        matches = [
            deepcopy(dict(item))
            for item in versions or []
            if isinstance(item, Mapping)
            and item.get("scriptVersionRef") == confirmed_ref
        ]
        if (
            not isinstance(script, Mapping)
            or not isinstance(versions, list)
            or len(matches) != 1
            or not isinstance(frozen, Mapping)
            or confirmed_ref != context.get("scriptVersionRef")
            or script.get("scriptRef") != frozen.get("scriptRef")
        ):
            raise StaleInputError("current SCRIPT_TEXT authority is stale")
        version = matches[0]
        version_digest = _digest(version)
        title = version.get("title")
        if (
            version_digest != context.get("scriptVersionDigest")
            or frozen.get("versionDigest") != version_digest
            or not isinstance(title, str)
            or title != title.strip()
            or not title
        ):
            raise StaleInputError("current SCRIPT_TEXT version is stale")
        return {
            "textSourceKind": "SCRIPT_TEXT",
            "textSourceRef": _required_ref(script.get("scriptRef"), "textSourceRef"),
            "textSourceVersionRef": _required_ref(
                confirmed_ref, "textSourceVersionRef"
            ),
            "textSourceDigest": version_digest,
            "resolvedText": title,
            "resolvedTextDigest": _digest({"utf8": title}),
            "language": "und",
        }

    @staticmethod
    def _require_character_in_target_shot(
        *,
        context: Mapping[str, Any],
        target_shot_ref: str,
        target_shot_version_ref: str,
        target_shot_version_digest: str,
        character_ref: str,
    ) -> dict[str, Any]:
        graph = context.get("executableShotGraph")
        shots = graph.get("shots") if isinstance(graph, Mapping) else None
        matches = [
            deepcopy(dict(item))
            for item in shots or []
            if isinstance(item, Mapping)
            and item.get("creativeShotRef") == target_shot_ref
            and item.get("creativeShotVersionRef") == target_shot_version_ref
            and item.get("payloadDigest") == target_shot_version_digest
        ]
        if len(matches) != 1:
            raise StaleInputError("target ShotVersion is not current")
        locks = matches[0].get("requiredCharacterIdentityLocks")
        character_matches = [
            item
            for item in locks or []
            if isinstance(item, Mapping)
            and item.get("characterRef") == character_ref
        ]
        if not isinstance(locks, list) or len(character_matches) != 1:
            raise StaleInputError("character is not bound to the target ShotVersion")
        return matches[0]

    def _current_identity_reference_projection(
        self,
        *,
        context: Mapping[str, Any],
        character_ref: str,
        target_shot_ref: str,
        target_shot_version_ref: str,
        target_shot_version_digest: str,
    ) -> dict[str, Any]:
        self._require_character_in_target_shot(
            context=context,
            target_shot_ref=target_shot_ref,
            target_shot_version_ref=target_shot_version_ref,
            target_shot_version_digest=target_shot_version_digest,
            character_ref=character_ref,
        )
        reader = self.identity_reference_projection_reader
        if reader is None or not callable(
            getattr(reader, "require_current_identity_reference_projection", None)
        ):
            raise UpstreamNotReadyError(
                "current identity reference projection reader is not configured"
            )
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        try:
            raw = reader.require_current_identity_reference_projection(
                workspace, run_ref, character_ref
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "current identity reference projection is unavailable"
            ) from exc
        required = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "characterRef",
            "scriptCharacterName",
            "identityLockRef",
            "identityLockVersionRef",
            "identityLockDigest",
            "referenceRef",
            "referenceVersionRef",
            "contentDigest",
            "mediaType",
            "rightsState",
            "provenance",
            "approvalRef",
            "externalDecisionDigest",
            "projectionCheckedAt",
            "projectionDigest",
        }
        projection = deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
        if (
            set(projection) != required
            or projection.get("schemaVersion")
            != "v5.identity-reference-version-projection.v1"
            or projection.get("workspaceRef") != workspace
            or projection.get("productionRunRef") != run_ref
            or projection.get("characterRef") != character_ref
            or not _is_sha256(projection.get("projectionDigest"))
        ):
            raise RepositoryUnavailableError(
                "current identity reference projection is invalid"
            )
        projection_base = {
            key: value
            for key, value in projection.items()
            if key not in {"projectionCheckedAt", "projectionDigest"}
        }
        if _digest(projection_base) != projection["projectionDigest"]:
            raise StaleInputError(
                "current identity reference projection digest is stale"
            )
        return projection

    def _current_font_projection(
        self,
        *,
        context: Mapping[str, Any],
        asset_version_ref: str,
        asset_version_digest: str,
        required_text: str,
    ) -> dict[str, Any]:
        from .static_resources import (
            FONT_ASSET_VERSION_PROJECTION_SCHEMA_VERSION,
            FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION,
            RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION,
        )

        authority = self.font_asset_authority
        if authority is None or not callable(
            getattr(authority, "require_current_font_asset_projection", None)
        ):
            raise UpstreamNotReadyError(
                "current canonical FONT AssetVersion authority is not configured"
            )
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        try:
            value = authority.require_current_font_asset_projection(
                workspace,
                run_ref,
                asset_version_ref,
                asset_version_digest,
                required_text=required_text,
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "current canonical FONT AssetVersion authority is unavailable"
            ) from exc
        if not isinstance(value, Mapping):
            raise RepositoryUnavailableError(
                "current canonical FONT projection is invalid"
            )
        projection = deepcopy(dict(value))
        asset = projection.get("fontAssetVersion")
        validation = projection.get("fontTechnicalValidation")
        license_binding = projection.get("fontLicenseBindingVersion")
        projection_fields = {
            "fontAssetVersion",
            "fontTechnicalValidation",
            "fontLicenseBindingVersion",
            "storageBindingRef",
            "publicationAllowed",
        }
        asset_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "projectRef",
            "seriesRef",
            "episodeRef",
            "assetRef",
            "assetVersionRef",
            "version",
            "assetClass",
            "resourceKind",
            "candidateRef",
            "candidateDigest",
            "technicalValidationRef",
            "technicalValidationDigest",
            "licenseBindingVersionRef",
            "licenseBindingVersionDigest",
            "admissionDecisionRef",
            "admissionDecisionDigest",
            "mediaType",
            "fontFormat",
            "byteSize",
            "fileDigest",
            "state",
            "admissionState",
            "publicationAllowed",
            "createdAt",
            "payloadDigest",
        }
        validation_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "validationRef",
            "candidateRef",
            "candidateDigest",
            "fileDigest",
            "byteSize",
            "fontFormat",
            "sfntSignature",
            "fontFamily",
            "fontSubfamily",
            "postScriptName",
            "nameTableDigest",
            "variableFont",
            "variationAxesDigest",
            "rendererProbeRef",
            "rendererProbeDigest",
            "rendererIdentity",
            "rendererVersion",
            "ffmpegIdentity",
            "freetypeIdentity",
            "validationState",
            "failureReasons",
            "createdAt",
            "publicationAllowed",
            "payloadDigest",
        }
        license_fields = {
            "schemaVersion",
            "workspaceRef",
            "productionRunRef",
            "licenseBindingRef",
            "licenseBindingVersionRef",
            "versionNumber",
            "parentLicenseBindingVersionRef",
            "candidateRef",
            "candidateDigest",
            "fontFileDigest",
            "licenseSpdxId",
            "licenseTextDigest",
            "licenseEvidenceRef",
            "licenseEvidenceDigest",
            "decisionAuthorityRef",
            "decisionAuthorityDigest",
            "commercialUseAllowed",
            "technicalPreviewAllowed",
            "renderCandidateUseAllowed",
            "embeddingAllowed",
            "redistributionAllowed",
            "modificationAllowed",
            "attributionRequired",
            "reservedFontNames",
            "territories",
            "revocationState",
            "validFrom",
            "expiresAt",
            "createdAt",
            "publicationAllowed",
            "payloadDigest",
        }
        if (
            set(projection) != projection_fields
            or not isinstance(asset, Mapping)
            or not isinstance(validation, Mapping)
            or not isinstance(license_binding, Mapping)
            or set(asset) != asset_fields
            or set(validation) != validation_fields
            or set(license_binding) != license_fields
            or asset.get("assetVersionRef") != asset_version_ref
            or asset.get("payloadDigest") != asset_version_digest
            or asset.get("workspaceRef") != workspace
            or asset.get("productionRunRef") != run_ref
            or asset.get("schemaVersion")
            != FONT_ASSET_VERSION_PROJECTION_SCHEMA_VERSION
            or asset.get("assetClass") != "STATIC_RESOURCE"
            or asset.get("resourceKind") != "FONT"
            or asset.get("state") != "REGISTERED"
            or asset.get("admissionState") != "ADMITTED"
            or asset.get("publicationAllowed") is not False
            or projection.get("publicationAllowed") is not False
            or validation.get("schemaVersion")
            != FONT_TECHNICAL_VALIDATION_SCHEMA_VERSION
            or validation.get("workspaceRef") != workspace
            or validation.get("productionRunRef") != run_ref
            or validation.get("publicationAllowed") is not False
            or validation.get("validationState") != "PASS"
            or license_binding.get("schemaVersion")
            != RESOURCE_LICENSE_BINDING_VERSION_SCHEMA_VERSION
            or license_binding.get("workspaceRef") != workspace
            or license_binding.get("productionRunRef") != run_ref
            or license_binding.get("publicationAllowed") is not False
            or license_binding.get("revocationState") != "ACTIVE"
            or license_binding.get("technicalPreviewAllowed") is not True
            or license_binding.get("renderCandidateUseAllowed") is not True
        ):
            raise StaleInputError("current canonical FONT projection is stale")
        return projection

    def _current_mark_asset(
        self,
        *,
        context: Mapping[str, Any],
        asset_version_ref: str,
        asset_version_digest: str,
        target_shot_ref: str,
        target_shot_version_ref: str,
        target_shot_version_digest: str,
    ) -> dict[str, Any]:
        """Resolve and physically remeasure one current canonical M10 image."""

        if self.real_video_authority is None:
            raise UpstreamNotReadyError(
                "current canonical mark AssetVersion authority is unavailable"
            )
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        bundle = self.real_video_authority.get_revision_bundle(
            workspace,
            run_ref,
            evidence_snapshot=context["snapshot"],
        )
        assets = bundle.get("assetVersions") if isinstance(bundle, Mapping) else None
        matches = [
            deepcopy(dict(item))
            for item in assets or []
            if isinstance(item, Mapping)
            and item.get("assetVersionRef") == asset_version_ref
            and item.get("payloadDigest") == asset_version_digest
        ]
        if len(matches) != 1:
            raise StaleInputError(
                "mark AssetVersion is not current canonical image media"
            )
        asset = matches[0]
        if (
            asset.get("schemaVersion")
            != "v5.k2-real-image-asset-version.v1"
            or asset.get("workspaceRef") != workspace
            or asset.get("productionRunRef") != run_ref
            or asset.get("creativeShotRef") != target_shot_ref
            or asset.get("creativeShotVersionRef") != target_shot_version_ref
            or asset.get("creativeShotDigest") != target_shot_version_digest
            or str(asset.get("mediaKind", "")).lower() != "image"
            or asset.get("mediaType") != "image/png"
            or asset.get("state") != "REGISTERED"
            or asset.get("immutable") is not True
            or asset.get("publicationAllowed") is not False
            or not _is_sha256(asset.get("sha256"))
            or _contains_path_authority(asset)
        ):
            raise StaleInputError("mark AssetVersion authority is stale")
        inspect = (
            getattr(self.composition, "inspect_deterministic_overlay_image", None)
            if self.composition is not None
            else None
        )
        if not callable(inspect):
            raise WorkerUnavailableError(
                "digest-pinned mark image inspection is not configured"
            )
        resolved = {
            "assetVersionRef": asset_version_ref,
            "assetVersionDigest": asset_version_digest,
            "storageKey": asset.get("storageKey"),
            "fileDigest": f"sha256:{asset['sha256']}",
            "mediaType": "image/png",
            "byteSize": asset.get("byteSize"),
        }
        try:
            measured = inspect(resolved)
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise WorkerUnavailableError(
                "digest-pinned mark image inspection failed"
            ) from exc
        if not isinstance(measured, Mapping):
            raise RepositoryUnavailableError("mark image inspection is invalid")
        measurement_fields = {
            "assetVersionRef",
            "assetVersionDigest",
            "fileDigest",
            "pixelDigest",
            "pixelDigestSpec",
            "pixelMode",
            "width",
            "height",
        }
        if (
            set(measured) != measurement_fields
            or measured.get("assetVersionRef") != asset_version_ref
            or measured.get("assetVersionDigest") != asset_version_digest
            or measured.get("fileDigest") != resolved["fileDigest"]
            or not isinstance(measured.get("pixelDigest"), str)
            or not measured["pixelDigest"].startswith("sha256:")
            or measured.get("pixelMode") != "RGBA"
            or measured.get("pixelDigestSpec")
            != IMAGE_PIXEL_DIGEST_SPEC
            or isinstance(measured.get("width"), bool)
            or not isinstance(measured.get("width"), int)
            or measured["width"] < 1
            or isinstance(measured.get("height"), bool)
            or not isinstance(measured.get("height"), int)
            or measured["height"] < 1
        ):
            raise StaleInputError("mark image bytes or pixels are stale")
        return {
            **resolved,
            **{
                field: deepcopy(measured[field])
                for field in measurement_fields
            },
        }

    def _current_overlay_base(
        self,
        *,
        context: Mapping[str, Any],
        asset_version_ref: str,
        asset_version_digest: str,
        target_shot_ref: str,
        target_shot_version_ref: str,
        target_shot_version_digest: str,
        frame_range_end_exclusive: int,
    ) -> dict[str, Any]:
        """Resolve and physically remeasure one current canonical M11 video."""

        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        matches = [
            deepcopy(dict(item))
            for item in self._current_glyph_video_assets(
                workspace,
                run_ref,
                evidence_snapshot=context["snapshot"],
            )
            if item.get("assetVersionRef") == asset_version_ref
            and item.get("payloadDigest") == asset_version_digest
        ]
        if len(matches) != 1:
            raise StaleInputError(
                "overlay base AssetVersion is not current canonical video"
            )
        asset = matches[0]
        if (
            asset.get("schemaVersion")
            != "v5.k2-real-video-asset-version.v1"
            or asset.get("workspaceRef") != workspace
            or asset.get("productionRunRef") != run_ref
            or asset.get("creativeShotRef") != target_shot_ref
            or asset.get("creativeShotVersionRef") != target_shot_version_ref
            or asset.get("creativeShotDigest") != target_shot_version_digest
            or str(asset.get("mediaKind", "")).lower() != "video"
            or asset.get("mediaType") != "video/mp4"
            or asset.get("state") != "REGISTERED"
            or asset.get("immutable") is not True
            or asset.get("publicationAllowed") is not False
            or not _is_sha256(asset.get("sha256"))
            or isinstance(asset.get("byteSize"), bool)
            or not isinstance(asset.get("byteSize"), int)
            or asset["byteSize"] < 1
            or _contains_path_authority(asset)
        ):
            raise StaleInputError("overlay base AssetVersion authority is stale")
        inspect = (
            getattr(self.composition, "inspect_deterministic_overlay_video", None)
            if self.composition is not None
            else None
        )
        if not callable(inspect):
            raise WorkerUnavailableError(
                "digest-pinned overlay base video inspection is not configured"
            )
        resolved = {
            "assetVersionRef": asset_version_ref,
            "assetVersionDigest": asset_version_digest,
            "storageKey": asset.get("storageKey"),
            "fileDigest": f"sha256:{asset['sha256']}",
            "mediaType": "video/mp4",
            "byteSize": asset["byteSize"],
        }
        try:
            measured = inspect(resolved)
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise WorkerUnavailableError(
                "digest-pinned overlay base video inspection failed"
            ) from exc
        measurement_fields = {
            "assetVersionRef",
            "assetVersionDigest",
            "fileDigest",
            "pixelDigest",
            "pixelDigestSpec",
            "width",
            "height",
            "frameCount",
            "frameRate",
            "pixelFormat",
        }
        if (
            not isinstance(measured, Mapping)
            or set(measured) != measurement_fields
            or measured.get("assetVersionRef") != asset_version_ref
            or measured.get("assetVersionDigest") != asset_version_digest
            or measured.get("fileDigest") != resolved["fileDigest"]
            or not isinstance(measured.get("pixelDigest"), str)
            or not measured["pixelDigest"].startswith("sha256:")
            or measured.get("pixelDigestSpec")
            != DECODED_FRAME_PIXEL_DIGEST_SPEC
            or measured.get("pixelFormat") != "yuv420p"
            or any(
                isinstance(measured.get(field), bool)
                or not isinstance(measured.get(field), int)
                or measured[field] < 1
                for field in (
                    "width",
                    "height",
                    "frameCount",
                    "frameRate",
                )
            )
            or isinstance(frame_range_end_exclusive, bool)
            or not isinstance(frame_range_end_exclusive, int)
            or frame_range_end_exclusive < 1
            or frame_range_end_exclusive > measured["frameCount"]
        ):
            raise StaleInputError("overlay base video bytes or pixels are stale")
        return {
            "assetVersionRef": asset_version_ref,
            "assetVersionDigest": asset_version_digest,
            "storageKey": resolved["storageKey"],
            **{
                field: deepcopy(measured[field])
                for field in measurement_fields
                if field not in {"assetVersionRef", "assetVersionDigest"}
            },
        }

    def _resolved_overlay_authorities(
        self,
        *,
        context: Mapping[str, Any],
        requirement: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Freshly resolve every server-owned E3 input for execution/replay."""

        mode = requirement.get("effectMode")
        base = self._current_overlay_base(
            context=context,
            asset_version_ref=requirement.get("basePlateAssetVersionRef"),
            asset_version_digest=requirement.get(
                "basePlateAssetVersionDigest"
            ),
            target_shot_ref=requirement.get("targetShotRef"),
            target_shot_version_ref=requirement.get("targetShotVersionRef"),
            target_shot_version_digest=requirement.get(
                "targetShotVersionDigest"
            ),
            frame_range_end_exclusive=requirement.get(
                "frameRangeEndExclusive"
            ),
        )
        if (
            requirement.get("basePlateFileDigest") != base["fileDigest"]
            or requirement.get("basePlatePixelDigest") != base["pixelDigest"]
        ):
            raise StaleInputError("overlay base Requirement is stale")
        resolved: dict[str, dict[str, Any]] = {
            base["assetVersionRef"]: base
        }
        if mode == "NAMEPLATE_TEXT":
            text = self._current_script_text_projection(context=context)
            if any(
                requirement.get(field) != text[field]
                for field in (
                    "textSourceKind",
                    "textSourceRef",
                    "textSourceVersionRef",
                    "textSourceDigest",
                    "resolvedText",
                    "resolvedTextDigest",
                    "language",
                )
            ):
                raise StaleInputError("Nameplate SCRIPT_TEXT authority is stale")
            font = self._current_font_projection(
                context=context,
                asset_version_ref=requirement.get("fontAssetVersionRef"),
                asset_version_digest=requirement.get("fontAssetVersionDigest"),
                required_text=text["resolvedText"],
            )
            asset = font["fontAssetVersion"]
            validation = font["fontTechnicalValidation"]
            license_binding = font["fontLicenseBindingVersion"]
            if (
                requirement.get("fontFileDigest") != asset.get("fileDigest")
                or requirement.get("fontTechnicalValidationRef")
                != validation.get("validationRef")
                or requirement.get("fontTechnicalValidationDigest")
                != validation.get("payloadDigest")
                or requirement.get("fontLicenseBindingVersionRef")
                != license_binding.get("licenseBindingVersionRef")
                or requirement.get("fontLicenseBindingVersionDigest")
                != license_binding.get("payloadDigest")
            ):
                raise StaleInputError("Nameplate FONT authority is stale")
            resolved[asset["assetVersionRef"]] = {
                "assetVersionRef": asset["assetVersionRef"],
                "assetVersionDigest": asset["payloadDigest"],
                "storageBindingRef": font["storageBindingRef"],
                "fileDigest": asset["fileDigest"],
                "byteSize": asset["byteSize"],
                "mediaType": asset["mediaType"],
                "fontFormat": asset["fontFormat"],
                "validationRef": validation["validationRef"],
                "validationDigest": validation["payloadDigest"],
                "licenseBindingRef": license_binding[
                    "licenseBindingVersionRef"
                ],
                "licenseBindingDigest": license_binding["payloadDigest"],
            }
            return resolved
        if mode == "FACE_MARK_COMPENSATION":
            projection = self._current_identity_reference_projection(
                context=context,
                character_ref=requirement.get("characterRef"),
                target_shot_ref=requirement.get("targetShotRef"),
                target_shot_version_ref=requirement.get(
                    "targetShotVersionRef"
                ),
                target_shot_version_digest=requirement.get(
                    "targetShotVersionDigest"
                ),
            )
            expected_identity = {
                "identityReferenceRef": projection["referenceRef"],
                "identityReferenceVersionRef": projection[
                    "referenceVersionRef"
                ],
                "identityReferenceContentDigest": projection[
                    "contentDigest"
                ],
                "identityReferenceProjectionDigest": projection[
                    "projectionDigest"
                ],
                "identityLockRef": projection["identityLockRef"],
                "identityLockVersionRef": projection[
                    "identityLockVersionRef"
                ],
                "identityLockDigest": projection["identityLockDigest"],
            }
            if any(
                requirement.get(field) != expected
                for field, expected in expected_identity.items()
            ):
                raise StaleInputError(
                    "Face Mark identity reference projection is stale"
                )
            mark = self._current_mark_asset(
                context=context,
                asset_version_ref=requirement.get("markAssetVersionRef"),
                asset_version_digest=requirement.get("markAssetVersionDigest"),
                target_shot_ref=requirement.get("targetShotRef"),
                target_shot_version_ref=requirement.get(
                    "targetShotVersionRef"
                ),
                target_shot_version_digest=requirement.get(
                    "targetShotVersionDigest"
                ),
            )
            if (
                requirement.get("markFileDigest") != mark["fileDigest"]
                or requirement.get("markPixelDigest") != mark["pixelDigest"]
            ):
                raise StaleInputError("Face Mark AssetVersion is stale")
            resolved[mark["assetVersionRef"]] = {
                field: deepcopy(mark[field])
                for field in (
                    "assetVersionRef",
                    "assetVersionDigest",
                    "storageKey",
                    "fileDigest",
                    "pixelDigest",
                    "pixelDigestSpec",
                    "pixelMode",
                    "width",
                    "height",
                )
            }
            return resolved
        raise RepositoryUnavailableError(
            "deterministic overlay mode is unsupported"
        )

    def _resolved_distance_state_authorities(
        self,
        *,
        context: Mapping[str, Any],
        requirement: Mapping[str, Any],
        enforce_requirement_digests: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Freshly resolve every current input of one E4 Requirement.

        The Requirement carries immutable refs/digests and measured content
        facts, but it is never itself currentness authority.  This method is
        called at creation, immediately before execution, and while restoring
        Timeline/Preview projections so every canonical media dependency is
        re-read through its existing owner.
        """

        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        shot_args = {
            "target_shot_ref": requirement.get("targetShotRef"),
            "target_shot_version_ref": requirement.get(
                "targetShotVersionRef"
            ),
            "target_shot_version_digest": requirement.get(
                "targetShotVersionDigest"
            ),
        }
        base = self._current_overlay_base(
            context=context,
            asset_version_ref=requirement.get(
                "basePlateAssetVersionRef"
            ),
            asset_version_digest=requirement.get(
                "basePlateAssetVersionDigest"
            ),
            frame_range_end_exclusive=requirement.get(
                "frameRangeEndExclusive"
            ),
            **shot_args,
        )
        if enforce_requirement_digests and (
            requirement.get("basePlateFileDigest") != base["fileDigest"]
            or requirement.get("basePlatePixelDigest")
            != base["pixelDigest"]
        ):
            raise StaleInputError(
                "Distance/State base Requirement is stale"
            )
        resolved: dict[str, dict[str, Any]] = {
            base["assetVersionRef"]: base
        }

        if requirement.get("targetKind") == "FULL_FRAME":
            return resolved
        if requirement.get("targetKind") != "OVERLAY_LAYER":
            raise RepositoryUnavailableError(
                "Distance/State targetKind is unsupported"
            )

        image_fields = (
            "assetVersionRef",
            "assetVersionDigest",
            "storageKey",
            "fileDigest",
            "pixelDigest",
            "pixelDigestSpec",
            "pixelMode",
            "width",
            "height",
        )

        def current_layer(
            *, asset_ref: Any, asset_digest: Any, label: str
        ) -> dict[str, Any]:
            layer = self._current_mark_asset(
                context=context,
                asset_version_ref=asset_ref,
                asset_version_digest=asset_digest,
                **shot_args,
            )
            if layer.get("pixelMode") != "RGBA":
                raise StaleInputError(f"{label} is not an RGBA image")
            return {field: deepcopy(layer[field]) for field in image_fields}

        subject = current_layer(
            asset_ref=requirement.get("subjectLayerAssetVersionRef"),
            asset_digest=requirement.get(
                "subjectLayerAssetVersionDigest"
            ),
            label="Distance/State subject layer",
        )
        if enforce_requirement_digests and (
            requirement.get("subjectLayerFileDigest")
            != subject["fileDigest"]
            or requirement.get("subjectLayerPixelDigest")
            != subject["pixelDigest"]
        ):
            raise StaleInputError(
                "Distance/State subject Requirement is stale"
            )
        resolved[subject["assetVersionRef"]] = subject

        mask_ref = requirement.get("maskAssetVersionRef")
        mask_digest = requirement.get("maskAssetVersionDigest")
        if mask_ref is not None or mask_digest is not None:
            if not isinstance(mask_ref, str) or not isinstance(
                mask_digest, str
            ):
                raise StaleInputError(
                    "Distance/State mask binding is partial"
                )
            mask_payload = self._snapshot_record_payload(
                context["snapshot"],
                record_kind="MaskAssetVersion",
                record_ref=mask_ref,
            )
            file_digest = mask_payload.get("fileDigest")
            if file_digest is None and _is_sha256(mask_payload.get("sha256")):
                file_digest = f"sha256:{mask_payload['sha256']}"
            mask = self._resolved_effect_image_asset(
                snapshot=context["snapshot"],
                workspace=workspace,
                run_ref=run_ref,
                asset_version_ref=mask_ref,
                asset_version_digest=mask_digest,
                file_digest=file_digest,
                pixel_digest=mask_payload.get("pixelDigest"),
                label="Distance/State mask",
            )
            inspect_mask = (
                getattr(
                    self.composition,
                    "inspect_deterministic_overlay_image",
                    None,
                )
                if self.composition is not None
                else None
            )
            if not callable(inspect_mask):
                raise WorkerUnavailableError(
                    "digest-pinned Distance/State mask inspection is not configured"
                )
            try:
                measured_mask = inspect_mask(
                    {
                        "assetVersionRef": mask_ref,
                        "assetVersionDigest": mask_digest,
                        "storageKey": mask_payload.get("storageKey"),
                        "fileDigest": file_digest,
                        "mediaType": mask_payload.get("mediaType"),
                        "byteSize": mask_payload.get("byteSize"),
                    }
                )
            except EpisodeProductionError:
                raise
            except Exception as exc:
                raise WorkerUnavailableError(
                    "digest-pinned Distance/State mask inspection failed"
                ) from exc
            if not isinstance(measured_mask, Mapping) or any(
                measured_mask.get(field) != mask[field]
                for field in (
                    "assetVersionRef",
                    "assetVersionDigest",
                    "fileDigest",
                    "pixelDigest",
                    "pixelDigestSpec",
                    "pixelMode",
                    "width",
                    "height",
                )
            ):
                raise StaleInputError(
                    "Distance/State mask bytes or pixels are stale"
                )
            if (
                mask["width"] != subject["width"]
                or mask["height"] != subject["height"]
                or (
                    enforce_requirement_digests
                    and (
                        requirement.get("maskFileDigest")
                        != mask["fileDigest"]
                        or requirement.get("maskPixelDigest")
                        != mask["pixelDigest"]
                    )
                )
            ):
                raise StaleInputError(
                    "Distance/State mask Requirement is stale"
                )
            resolved[mask["assetVersionRef"]] = mask

        definitions = requirement.get("visualStateDefinitions")
        if not isinstance(definitions, list):
            raise RepositoryUnavailableError(
                "Distance/State visual states are invalid"
            )
        for index, definition in enumerate(definitions):
            if not isinstance(definition, Mapping):
                raise RepositoryUnavailableError(
                    "Distance/State visual state is invalid"
                )
            variant_ref = definition.get("variantAssetVersionRef")
            variant_digest = definition.get("variantAssetVersionDigest")
            if variant_ref is None and variant_digest is None:
                continue
            if not isinstance(variant_ref, str) or not isinstance(
                variant_digest, str
            ):
                raise StaleInputError(
                    "Distance/State variant binding is partial"
                )
            variant = current_layer(
                asset_ref=variant_ref,
                asset_digest=variant_digest,
                label=f"Distance/State variant {index}",
            )
            if (
                variant["width"] != subject["width"]
                or variant["height"] != subject["height"]
            ):
                raise StaleInputError(
                    "Distance/State variant dimensions are stale"
                )
            resolved[variant["assetVersionRef"]] = variant
        return resolved

    def _resolved_effect_image_asset(
        self,
        *,
        snapshot: Any,
        workspace: str,
        run_ref: str,
        asset_version_ref: str,
        asset_version_digest: str,
        file_digest: str,
        pixel_digest: str,
        label: str,
        allow_canonical_asset: bool = False,
    ) -> dict[str, Any]:
        """Resolve one exact RGBA AssetVersion without accepting path authority."""

        matches: list[dict[str, Any]] = []
        mask_records = [
            item
            for item in snapshot.records
            if item.get("recordKind") == "MaskAssetVersion"
            and item.get("recordRef") == asset_version_ref
        ]
        if len(mask_records) > 1:
            raise RepositoryUnavailableError(
                f"{label} AssetVersion authority is ambiguous"
            )
        if mask_records:
            matches.append(
                self._snapshot_record_payload(
                    snapshot,
                    record_kind="MaskAssetVersion",
                    record_ref=asset_version_ref,
                )
            )
        if allow_canonical_asset:
            canonical = {
                item["assetVersionRef"]: item
                for item in CanonicalAssetVersionAuthority(
                    self.evidence
                ).list_asset_versions(
                    workspace,
                    run_ref,
                    gates=snapshot.gates,
                    records=snapshot.records,
                )
            }.get(asset_version_ref)
            if canonical is not None:
                matches.append(deepcopy(canonical))
        if not matches:
            raise UpstreamNotReadyError(
                f"exact {label} AssetVersion evidence is not available"
            )
        authority = matches[0]
        if any(item != authority for item in matches[1:]):
            raise RepositoryUnavailableError(
                f"{label} AssetVersion authority is ambiguous"
            )
        authority_file_digest = authority.get("fileDigest")
        if authority_file_digest is None and _is_sha256(
            authority.get("sha256")
        ):
            authority_file_digest = f"sha256:{authority['sha256']}"
        if (
            authority.get("assetVersionRef") != asset_version_ref
            or authority.get("payloadDigest") != asset_version_digest
            or authority_file_digest != file_digest
            or authority.get("pixelDigest") != pixel_digest
            or authority.get("pixelMode") != "RGBA"
            or _contains_path_authority(authority)
        ):
            raise StaleInputError(f"{label} AssetVersion is stale")
        return {
            "assetVersionRef": asset_version_ref,
            "assetVersionDigest": asset_version_digest,
            "storageKey": authority["storageKey"],
            "fileDigest": authority_file_digest,
            "pixelDigest": pixel_digest,
            "pixelDigestSpec": authority["pixelDigestSpec"],
            "pixelMode": authority["pixelMode"],
            "width": authority["width"],
            "height": authority["height"],
        }

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
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path is None or ffprobe_path is None:
            raise ArtifactRejectedError(
                "pinned preview verification runtime is unavailable"
            )
        from services.v3_render_core.composition import (
            RenderArtifactError,
            _PinnedRegularFile,
            _PinnedRuntimeBinary,
            _fixed_environment,
        )

        try:
            with (
                _PinnedRegularFile(
                    path, label="stored timeline preview artifact"
                ) as pinned_artifact,
                _PinnedRuntimeBinary(
                    Path(os.path.realpath(ffmpeg_path)), label="FFmpeg"
                ) as ffmpeg,
                _PinnedRuntimeBinary(
                    Path(os.path.realpath(ffprobe_path)), label="FFprobe"
                ) as ffprobe,
            ):
                if (
                    pinned_artifact.descriptor is None
                    or os.fstat(pinned_artifact.descriptor).st_size
                    != result.get("outputByteSize")
                ):
                    raise ArtifactRejectedError(
                        "preview artifact byte size changed"
                    )
                pass_fds = tuple(
                    dict.fromkeys(
                        pinned_artifact.pass_fds
                        + ffmpeg.pass_fds
                        + ffprobe.pass_fds
                    )
                )
                completed = subprocess.run(
                    [
                        str(ffprobe.executable_path),
                        "-v",
                        "error",
                        "-count_frames",
                        "-show_streams",
                        "-show_format",
                        "-of",
                        "json",
                        str(pinned_artifact.descriptor_path),
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    timeout=60,
                    env=_fixed_environment(),
                    pass_fds=pass_fds,
                )
                payload = json.loads(completed.stdout)
                if not isinstance(payload, Mapping) or not isinstance(
                    payload.get("format"), Mapping
                ):
                    raise ArtifactRejectedError(
                        "preview artifact probe payload is malformed"
                    )
                streams = payload.get("streams")
                if not isinstance(streams, list) or not streams:
                    raise ArtifactRejectedError(
                        "preview artifact has no media stream"
                    )
                normalized_streams = []
                for stream in streams:
                    if not isinstance(stream, Mapping):
                        raise ArtifactRejectedError(
                            "preview artifact stream is malformed"
                        )
                    normalized_streams.append(
                        {
                            key: stream.get(key)
                            for key in (
                                "codec_type",
                                "codec_name",
                                "width",
                                "height",
                                "pix_fmt",
                                "avg_frame_rate",
                                "nb_frames",
                                "nb_read_frames",
                                "sample_rate",
                                "channels",
                                "duration",
                            )
                            if stream.get(key) is not None
                        }
                    )
                observed_probe = {
                    "streams": normalized_streams,
                    "formatName": payload.get("format", {}).get(
                        "format_name"
                    ),
                    "durationSeconds": payload.get("format", {}).get(
                        "duration"
                    ),
                }
                pixels = decoded_frame_pixel_digest_metadata(
                    pinned_artifact.descriptor_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
                pcm = canonical_pcm_digest_metadata(
                    path,
                    expected_sample_count=output_digest.get("sampleCount"),
                    allow_aac_frame_padding=True,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                    _input_descriptor=pinned_artifact.descriptor,
                )
                pinned_artifact.require_stable()
                ffmpeg.require_stable()
                ffprobe.require_stable()
        except ArtifactRejectedError:
            raise
        except (
            DigestError,
            RenderArtifactError,
            OSError,
            subprocess.SubprocessError,
            UnicodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ArtifactRejectedError(
                "preview artifact verification failed"
            ) from exc
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

    def _resolved_deterministic_effect_base(
        self,
        *,
        context: Mapping[str, Any],
        requirement: Mapping[str, Any],
    ) -> dict[str, Any]:
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        matches = [
            item
            for item in self._current_glyph_video_assets(
                workspace,
                run_ref,
                evidence_snapshot=context["snapshot"],
            )
            if item.get("assetVersionRef")
            == requirement["basePlateAssetVersionRef"]
        ]
        if len(matches) != 1:
            raise StaleInputError(
                "deterministic Effect base AssetVersion is not current"
            )
        base = matches[0]
        facts = self._base_video_facts(base)
        if (
            base.get("payloadDigest")
            != requirement["basePlateAssetVersionDigest"]
            or f"sha256:{base.get('sha256')}"
            != requirement["basePlateFileDigest"]
            or base.get("creativeShotRef") != requirement["targetShotRef"]
            or base.get("creativeShotVersionRef")
            != requirement["targetShotVersionRef"]
            or base.get("creativeShotDigest")
            != requirement["targetShotVersionDigest"]
            or requirement["frameRangeEndExclusive"] > facts["frameCount"]
            or _contains_path_authority(base)
        ):
            raise StaleInputError(
                "deterministic Effect base/Shot authority is stale"
            )
        return {
            "assetVersionRef": base["assetVersionRef"],
            "assetVersionDigest": base["payloadDigest"],
            "storageKey": base["storageKey"],
            "fileDigest": f"sha256:{base['sha256']}",
            "pixelDigest": requirement["basePlatePixelDigest"],
            "pixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC,
            "width": facts["width"],
            "height": facts["height"],
            "frameCount": facts["frameCount"],
            "frameRate": facts["frameRate"]["numerator"],
            "pixelFormat": facts["pixelFormat"],
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

        source_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        current_video_assets = self._current_glyph_video_assets(
            workspace,
            run_ref,
            evidence_snapshot=source_snapshot,
        )
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
            for item in current_video_assets
            if isinstance(item, Mapping)
            and item.get("assetVersionRef")
            == requirement.base_plate_asset_version_ref
        ]
        if len(base_matches) != 1:
            raise StaleInputError(
                "GlyphRevealRequirementV2 base plate is not current immutable real-video media"
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
        if (
            snapshot.currentState not in M13_PREVIEW_STATE_TRANSITIONS
            and not all(existing)
        ):
            raise UpstreamNotReadyError(
                "M12/M13 inputs require current video media"
            )
        if (
            snapshot.revisionToken != source_snapshot.revisionToken
            and not all(existing)
        ):
            raise StaleInputError(
                "current real-video authority changed during input validation"
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

    @staticmethod
    def _editing_timeline_preview_command(
        command: Mapping[str, Any],
    ) -> dict[str, Any]:
        fields = {
            "workspaceRef",
            "productionRunRef",
            "operationRef",
            "idempotencyKey",
            "expectedRunVersion",
            "expectedEvidenceRevision",
            "timelineVersionRef",
            "timelineVersionDigest",
        }
        if not isinstance(command, Mapping) or set(command) != fields:
            raise EpisodeProductionError(
                "command fields do not match the M13 effect Preview contract"
            )
        result = {
            "workspaceRef": _required_ref(
                command.get("workspaceRef"), "workspaceRef"
            ),
            "productionRunRef": _required_ref(
                command.get("productionRunRef"), "productionRunRef"
            ),
            "operationRef": _required_ref(
                command.get("operationRef"), "operationRef"
            ),
            "idempotencyKey": _idempotency_key(command.get("idempotencyKey")),
            "expectedRunVersion": _positive_version(
                command.get("expectedRunVersion"), "expectedRunVersion"
            ),
            "expectedEvidenceRevision": command.get("expectedEvidenceRevision"),
            "timelineVersionRef": _required_ref(
                command.get("timelineVersionRef"), "timelineVersionRef"
            ),
            "timelineVersionDigest": command.get("timelineVersionDigest"),
        }
        if not _is_sha256(result["expectedEvidenceRevision"]):
            raise EpisodeProductionError("expectedEvidenceRevision is invalid")
        if not _is_sha256(result["timelineVersionDigest"]):
            raise EpisodeProductionError("timelineVersionDigest is invalid")
        return result

    @staticmethod
    def _editing_preview_layout(
        restored: Mapping[str, Any],
        *,
        allow_video_edits: bool = False,
    ) -> dict[str, Any]:
        version = restored["timelineVersion"].as_dict()
        tracks = {
            item.as_dict()["trackRef"]: item.as_dict()
            for item in restored["tracks"]
        }
        if len(tracks) != len(restored["tracks"]):
            raise RepositoryUnavailableError("Timeline Track refs are ambiguous")
        active: dict[str, list[dict[str, Any]]] = {
            "VIDEO": [],
            "AUDIO": [],
            "SUBTITLE": [],
            "EFFECT": [],
        }
        for wrapper in restored["clips"]:
            clip = wrapper.as_dict()
            track = tracks.get(clip.get("trackRef"))
            if track is None or track.get("trackKind") != clip.get("clipKind"):
                raise RepositoryUnavailableError(
                    "Timeline Clip track lineage is invalid"
                )
            if clip.get("enabled") is True and track.get("enabled") is True:
                active[clip["clipKind"]].append(clip)
        for values in active.values():
            values.sort(
                key=lambda item: (
                    item["timelineStartFrameInclusive"],
                    item["layer"],
                    item["zOrder"],
                    item["clipRef"],
                )
            )
        identity_transform = {
            "positionXPixels": 0,
            "positionYPixels": 0,
            "scaleX": {"numerator": 1, "denominator": 1},
            "scaleY": {"numerator": 1, "denominator": 1},
            "rotationMilliDegrees": 0,
            "anchorXPixels": 0,
            "anchorYPixels": 0,
            "opacity": 1000,
            "perspectiveMode": "NONE",
            "perspectiveMatrix": None,
            "perspectiveCorners": None,
        }
        for clip_kind, clips in active.items():
            for clip in clips:
                transform = clip["transform"]
                if allow_video_edits and clip_kind == "VIDEO":
                    if (
                        clip["maskBindings"]
                        or clip["blendMode"] != "NORMAL"
                        or transform["perspectiveMode"] != "NONE"
                        or transform["perspectiveMatrix"] is not None
                        or transform["perspectiveCorners"] is not None
                    ):
                        raise UpstreamNotReadyError(
                            "editing Timeline video modifier is not supported by R1"
                        )
                    continue
                if (
                    clip["transitionIn"] is not None
                    or clip["transitionOut"] is not None
                    or clip["speed"]["numerator"] != 1
                    or clip["speed"]["denominator"] != 1
                    or clip["maskBindings"]
                    or clip["opacity"] != 1000
                    or any(
                        transform[field] != expected
                        for field, expected in identity_transform.items()
                    )
                    or (
                        clip_kind != "EFFECT"
                        and clip["blendMode"] != "NORMAL"
                    )
                ):
                    raise UpstreamNotReadyError(
                        "editing Timeline modifiers cannot be projected losslessly"
                    )
        effects = active["EFFECT"]
        deterministic = [
            item
            for item in effects
            if item["sourceBinding"].get("effectKind")
            in {
                "SCRATCH_REVEAL",
                "LIGHT_SWEEP",
                "LOCAL_EXPOSURE",
                "FLAME_EXTINGUISH",
                "SMOKE",
                "NAMEPLATE_TEXT",
                "FACE_MARK_COMPENSATION",
                "DISTANCE_STATE_TRANSITION",
            }
        ]
        glyphs = [
            item
            for item in effects
            if item["sourceBinding"].get("effectKind") == "GLYPH_REVEAL"
        ]
        if (
            (not active["VIDEO"] if allow_video_edits else len(active["VIDEO"]) != 1)
            or not active["AUDIO"]
            or not active["SUBTITLE"]
            or len(glyphs) != 1
            or len(effects) not in {3, 5, 7, 8}
            or len(deterministic) not in {2, 4, 6, 7}
            or len(effects) != len(deterministic) + 1
        ):
            raise UpstreamNotReadyError(
                "editing Timeline does not have exact Preview source coverage"
            )
        ranks = {
            "SCRATCH_REVEAL": 0,
            "LIGHT_SWEEP": 0,
            "LOCAL_EXPOSURE": 1,
            "FLAME_EXTINGUISH": 2,
            "SMOKE": 3,
            "NAMEPLATE_TEXT": 4,
            "FACE_MARK_COMPENSATION": 5,
            "DISTANCE_STATE_TRANSITION": 6,
        }
        deterministic.sort(
            key=lambda item: (
                ranks[item["sourceBinding"]["effectKind"]],
                item["layer"],
                item["zOrder"],
                item["clipRef"],
            )
        )
        profile = [
            ranks[item["sourceBinding"]["effectKind"]]
            for item in deterministic
        ]
        expected_profile = {
            2: [0, 1],
            4: [0, 1, 2, 3],
            6: [0, 1, 2, 3, 4, 5],
            7: [0, 1, 2, 3, 4, 5, 6],
        }[len(deterministic)]
        timeline_order = [
            (item["layer"], item["zOrder"]) for item in deterministic
        ]
        if (
            profile != expected_profile
            or timeline_order != sorted(timeline_order)
            or len(set(timeline_order)) != len(timeline_order)
        ):
            raise UpstreamNotReadyError(
                "editing Timeline effect stages are incomplete"
            )
        return {
            "timelineVersion": version,
            "video": active["VIDEO"][0],
            "videoClips": active["VIDEO"],
            "audio": active["AUDIO"],
            "subtitles": active["SUBTITLE"],
            "deterministicEffects": deterministic,
            "glyph": glyphs[0],
            "effectProfile": {
                2: "M13_E1",
                4: "M13_E2",
                6: "M13_E3",
                7: "M13_E4",
            }[len(deterministic)],
        }

    def _editing_preview_input_refs(
        self,
        *,
        snapshot: Any,
        layout: Mapping[str, Any],
    ) -> dict[str, Any]:
        audio_assets = {
            item["sourceBinding"]["audioAssetVersionRef"]
            for item in layout["audio"]
        }
        stem_members = {
            item["sourceBinding"]["stemMemberRef"]
            for item in layout["audio"]
        }
        bindings_by_asset: dict[str, list[dict[str, Any]]] = {}
        for record in snapshot.records:
            if record.get("recordKind") != "AudioInputBinding":
                continue
            payload = _immutable_payload(
                record.get("payload"), "AudioInputBinding"
            )
            binding = validate_audio_input_binding(payload).as_dict()
            if (
                record.get("recordRef") != binding["audioInputBindingRef"]
                or record.get("payloadDigest") != binding["payloadDigest"]
            ):
                raise RepositoryUnavailableError(
                    "AudioInputBinding evidence envelope is invalid"
                )
            if binding["assetVersionRef"] in audio_assets:
                bindings_by_asset.setdefault(
                    binding["assetVersionRef"], []
                ).append(binding)
        if set(bindings_by_asset) != audio_assets or any(
            len(items) != 1 for items in bindings_by_asset.values()
        ):
            raise RepositoryUnavailableError(
                "editing Timeline audio input authority is ambiguous"
            )

        stem_candidates: list[dict[str, Any]] = []
        for record in snapshot.records:
            if record.get("recordKind") != "AudioStemSet":
                continue
            payload = _immutable_payload(record.get("payload"), "AudioStemSet")
            members = payload.get("members")
            if not isinstance(members, list):
                raise RepositoryUnavailableError("AudioStemSet members are invalid")
            if {
                item.get("stemMemberRef")
                for item in members
                if isinstance(item, Mapping)
            } == stem_members:
                stem_candidates.append(payload)
        if len(stem_candidates) != 1:
            raise RepositoryUnavailableError(
                "editing Timeline AudioStemSet authority is ambiguous"
            )
        stem_set = stem_candidates[0]
        members = stem_set["members"]
        if {
            item.get("sourceAssetVersionRef")
            for item in members
            if isinstance(item, Mapping)
        } != audio_assets:
            raise StaleInputError("Timeline AudioStemSet asset closure is stale")
        cue_refs = sorted(
            {
                _required_ref(
                    item.get("sourceCueVersionRef"), "audioCueVersionRef"
                )
                for item in members
                if isinstance(item, Mapping)
                and item.get("sourceCueVersionRef") is not None
            }
        )
        subtitle_refs = {
            item["sourceBinding"]["audioCueRef"]
            for item in layout["subtitles"]
        }
        if not cue_refs or not subtitle_refs.issubset(set(cue_refs)):
            raise StaleInputError("Timeline subtitle Cue closure is stale")
        glyph_source = layout["glyph"]["sourceBinding"]
        return {
            "videoAssetVersionRef": layout["video"]["sourceBinding"][
                "assetVersionRef"
            ],
            "audioInputBindingRefs": sorted(
                items[0]["audioInputBindingRef"]
                for items in bindings_by_asset.values()
            ),
            "audioCueVersionRefs": cue_refs,
            "audioStemSetVersionRef": stem_set["stemSetVersionRef"],
            "glyphRevealRequirementRef": glyph_source[
                "effectRequirementRef"
            ],
        }

    @staticmethod
    def _editing_preview_audio_mix(
        *,
        layout: Mapping[str, Any],
        inputs: Mapping[str, Any],
    ) -> dict[str, Any]:
        version = layout["timelineVersion"]
        rate = version["frameRate"]
        duration_samples = map_frame_boundary_to_sample(
            version["durationFrames"],
            sample_rate=48_000,
            frame_rate_numerator=rate["numerator"],
            frame_rate_denominator=rate["denominator"],
        )
        bindings = {
            item["assetVersionRef"]: item
            for item in inputs["audioInputBindings"]
        }
        members = {
            item["stemMemberRef"]: item
            for item in inputs["audioStemMembers"]
        }
        if len(bindings) != len(inputs["audioInputBindings"]) or len(
            members
        ) != len(inputs["audioStemMembers"]):
            raise RepositoryUnavailableError(
                "editing Timeline audio authority is ambiguous"
            )
        clips: list[dict[str, Any]] = []
        for clip in layout["audio"]:
            source = clip["sourceBinding"]
            binding = bindings.get(source["audioAssetVersionRef"])
            member = members.get(source["stemMemberRef"])
            if binding is None or member is None:
                raise StaleInputError("Timeline audio source closure is stale")
            validation = binding.get("technicalValidation")
            if not isinstance(validation, Mapping):
                raise RepositoryUnavailableError(
                    "audio technical validation is invalid"
                )
            start_frame = clip["timelineStartFrameInclusive"]
            end_frame = clip["timelineEndFrameExclusive"]
            timeline_start_sample = map_frame_boundary_to_sample(
                start_frame,
                sample_rate=48_000,
                frame_rate_numerator=rate["numerator"],
                frame_rate_denominator=rate["denominator"],
            )
            timeline_end_sample = map_frame_boundary_to_sample(
                end_frame,
                sample_rate=48_000,
                frame_rate_numerator=rate["numerator"],
                frame_rate_denominator=rate["denominator"],
            )
            if (
                source["audioAssetVersionDigest"]
                != binding["assetVersionDigest"]
                or member.get("sourceAssetVersionRef")
                != binding["assetVersionRef"]
                or source["sampleRate"] != 48_000
                or source["pan"] != 0
                or source["sourceEndSampleExclusive"]
                - source["sourceStartSampleInclusive"]
                != timeline_end_sample - timeline_start_sample
            ):
                raise UpstreamNotReadyError(
                    "editing Timeline audio cannot be projected losslessly"
                )
            clips.append(
                {
                    "clipRef": clip["clipRef"],
                    "clipDigest": clip["payloadDigest"],
                    "stemMemberRef": member["stemMemberRef"],
                    "stemMemberDigest": member["payloadDigest"],
                    "audioRole": _audio_role_from_binding(binding),
                    "assetVersionRef": binding["assetVersionRef"],
                    "assetVersionType": binding["assetVersionType"],
                    "assetVersionDigest": binding["assetVersionDigest"],
                    "technicalValidationRef": validation[
                        "validationVersionRef"
                    ],
                    "technicalValidationDigest": validation["payloadDigest"],
                    "storageKey": validation["storageKey"],
                    "fileDigest": binding["fileDigest"],
                    "pcmContentDigest": binding["pcmContentDigest"],
                    "sampleRate": binding["sampleRate"],
                    "sourceChannelCount": binding["channelCount"],
                    "sourceSampleCount": binding["sampleCount"],
                    "sourceStartSample": source[
                        "sourceStartSampleInclusive"
                    ],
                    "sourceEndSampleExclusive": source[
                        "sourceEndSampleExclusive"
                    ],
                    "timelineStartFrame": start_frame,
                    "timelineEndFrameExclusive": end_frame,
                    "timelineStartSample": timeline_start_sample,
                    "timelineEndSampleExclusive": timeline_end_sample,
                    "gainDb": source["gainDb"],
                    "fadeInSamples": source["fadeInSamples"],
                    "fadeOutSamples": source["fadeOutSamples"],
                }
            )
        clips.sort(
            key=lambda item: (
                -TIMELINE_MIX_PARAMETERS["rolePriority"][item["audioRole"]],
                item["clipRef"],
            )
        )
        stem_set = inputs["audioStemSet"]
        mix_ref = "m13-editing-timeline-mix-" + _digest(
            {
                "timelineVersionRef": version["timelineVersionRef"],
                "timelineVersionDigest": version["payloadDigest"],
                "stemSetVersionRef": stem_set["stemSetVersionRef"],
                "stemSetDigest": stem_set["payloadDigest"],
            }
        )[:32]
        projection = {
            "mixRequestRef": mix_ref,
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "stemSetVersionRef": stem_set["stemSetVersionRef"],
            "stemSetDigest": stem_set["payloadDigest"],
            "sampleRate": 48_000,
            "channelCount": 2,
            "durationSamples": duration_samples,
            "roundingRule": "FLOOR_EACH_BOUNDARY",
            "mixParameters": deepcopy(TIMELINE_MIX_PARAMETERS),
            "mixParametersDigest": _digest(TIMELINE_MIX_PARAMETERS),
            "clips": clips,
        }
        return {
            "mixRequestDigest": _digest(
                {
                    "schemaVersion": "v5.m13-editing-timeline-mix.v1",
                    **projection,
                }
            ),
            **projection,
        }

    @staticmethod
    def _editing_preview_subtitle_manifest(
        *, layout: Mapping[str, Any]
    ) -> dict[str, str]:
        version = layout["timelineVersion"]
        clips = [
            {
                "clipRef": item["clipRef"],
                "clipDigest": item["payloadDigest"],
                "timelineStartFrameInclusive": item[
                    "timelineStartFrameInclusive"
                ],
                "timelineEndFrameExclusive": item[
                    "timelineEndFrameExclusive"
                ],
                "sourceBinding": deepcopy(item["sourceBinding"]),
            }
            for item in layout["subtitles"]
        ]
        digest = _digest(
            {
                "schemaVersion": "v5.m13-editing-subtitle-manifest.v1",
                "workspaceRef": version["workspaceRef"],
                "productionRunRef": version["productionRunRef"],
                "timelineVersionRef": version["timelineVersionRef"],
                "timelineVersionDigest": version["payloadDigest"],
                "clips": clips,
            }
        )
        return {
            "subtitleManifestRef": "m13-editing-subtitle-manifest-"
            + digest[:32],
            "subtitleManifestDigest": digest,
        }

    def _render_subtitle_cues(
        self,
        *,
        context: Mapping[str, Any],
        layout: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Project exact Script text into immutable frame-addressed cues."""

        cues: list[dict[str, Any]] = []
        for clip in layout["subtitles"]:
            source = clip["sourceBinding"]
            raw_cue = self._snapshot_record_payload(
                context["snapshot"],
                record_kind="AudioCue",
                record_ref=source["audioCueRef"],
            )
            cue = raw_cue
            subtitle = cue["subtitleTimingReference"]
            text = subtitle["text"]
            if (
                cue["cueVersionRef"] != source["audioCueRef"]
                or cue["payloadDigest"] != source["audioCueDigest"]
                or cue["scriptVersionRef"] != source["scriptVersionRef"]
                or cue["scriptVersionDigest"] != source["scriptVersionDigest"]
                or subtitle["textRangeStart"] != source["textStart"]
                or subtitle["textRangeEndExclusive"]
                != source["textEndExclusive"]
                or subtitle["textDigest"] != source["textDigest"]
                or subtitle["language"] != source["language"]
                or not text
                or sha256(text.encode("utf-8")).hexdigest()
                != source["textDigest"]
            ):
                raise StaleInputError("subtitle Script text authority is stale")
            authority_words = {
                item["wordRef"]: item for item in cue["wordTimings"]
            }
            words: list[dict[str, Any]] = []
            for word in source["wordTiming"]:
                authority_word = authority_words.get(word["wordRef"])
                word_text = (
                    authority_word.get("text")
                    if isinstance(authority_word, Mapping)
                    else None
                )
                if (
                    not isinstance(authority_word, Mapping)
                    or authority_word.get("textRangeStart")
                    != word["textStart"]
                    or authority_word.get("textRangeEndExclusive")
                    != word["textEndExclusive"]
                    or authority_word.get("textDigest") != word["textDigest"]
                    or not isinstance(word_text, str)
                    or not word_text
                    or sha256(word_text.encode("utf-8")).hexdigest()
                    != word["textDigest"]
                ):
                    raise StaleInputError("subtitle word text authority is stale")
                words.append(
                    {
                        "wordRef": word["wordRef"],
                        "timelineStartFrameInclusive": word[
                            "timelineStartFrameInclusive"
                        ],
                        "timelineEndFrameExclusive": word[
                            "timelineEndFrameExclusive"
                        ],
                        "text": word_text,
                        "textDigest": word["textDigest"],
                    }
                )
            cues.append(
                {
                    "cueRef": source["audioCueRef"],
                    "clipRef": clip["clipRef"],
                    "timelineStartFrameInclusive": clip[
                        "timelineStartFrameInclusive"
                    ],
                    "timelineEndFrameExclusive": clip[
                        "timelineEndFrameExclusive"
                    ],
                    "text": text,
                    "textDigest": source["textDigest"],
                    "language": source["language"],
                    "wordTiming": words,
                }
            )
        return canonical_subtitle_timing(cues)

    def _editing_effect_preview_projection(
        self,
        *,
        context: Mapping[str, Any],
        restored: Mapping[str, Any],
        allow_video_edits: bool = False,
    ) -> dict[str, Any]:
        workspace = context["run"]["workspaceRef"]
        run_ref = context["run"]["productionRunRef"]
        snapshot = context["snapshot"]
        layout = self._editing_preview_layout(
            restored,
            allow_video_edits=allow_video_edits,
        )
        version = layout["timelineVersion"]
        references = self._editing_preview_input_refs(
            snapshot=snapshot, layout=layout
        )
        inputs = self._resolve_registered_timeline_inputs(
            workspace=workspace,
            run_ref=run_ref,
            references=references,
            snapshot=snapshot,
        )
        base_asset = inputs["basePlateAssetVersion"]
        video_facts = deepcopy(inputs["baseVideoFacts"])
        video_sources = [
            clip["sourceBinding"] for clip in layout["videoClips"]
        ]
        if (
            any(
                source["assetVersionRef"] != base_asset["assetVersionRef"]
                or source["assetVersionDigest"] != base_asset["payloadDigest"]
                or source["sourceInFrameInclusive"] < 0
                or source["sourceOutFrameExclusive"]
                > video_facts["frameCount"]
                or source["sourceInFrameInclusive"]
                >= source["sourceOutFrameExclusive"]
                for source in video_sources
            )
            or (
                not allow_video_edits
                and (
                    video_sources[0]["sourceInFrameInclusive"] != 0
                    or video_sources[0]["sourceOutFrameExclusive"]
                    != video_facts["frameCount"]
                    or layout["video"]["timelineStartFrameInclusive"] != 0
                    or layout["video"]["timelineEndFrameExclusive"]
                    != version["durationFrames"]
                )
            )
            or version["durationFrames"] != video_facts["frameCount"]
            or version["canvasWidth"] != video_facts["width"]
            or version["canvasHeight"] != video_facts["height"]
            or version["frameRate"] != video_facts["frameRate"]
            or video_facts["frameRate"]["denominator"] != 1
            or video_facts["pixelFormat"] != "yuv420p"
        ):
            raise UpstreamNotReadyError(
                "editing Timeline base video cannot be projected losslessly"
            )

        effect_bindings: list[dict[str, Any]] = []
        effect_executions: dict[str, dict[str, Any]] = {}
        chains: list[dict[str, Any]] = []
        for clip in layout["deterministicEffects"]:
            source = clip["sourceBinding"]
            result_ref = source.get("effectResultRef")
            result_digest = source.get("effectResultDigest")
            if not isinstance(result_ref, str) or not _is_sha256(result_digest):
                raise UpstreamNotReadyError(
                    "editing Timeline effect Result is not bound"
                )
            chain = self._resolve_effect_result_chain(
                context=context,
                result_ref=result_ref,
                result_digest=result_digest,
            )
            requirement = chain["requirement"]
            request = chain["executionRequest"]
            artifact = chain["artifactEvidence"]
            runtime = chain["runtimeEvidence"]
            result = chain["result"]
            if (
                source["effectKind"] != requirement["effectMode"]
                or source["effectRequirementRef"]
                != requirement["requirementRef"]
                or source["effectRequirementDigest"]
                != requirement["payloadDigest"]
                or source["effectResultRef"] != result["resultRef"]
                or source["effectResultDigest"] != result["payloadDigest"]
                or clip["timelineStartFrameInclusive"]
                != requirement["frameRangeStartInclusive"]
                or clip["timelineEndFrameExclusive"]
                != requirement["frameRangeEndExclusive"]
                or requirement["basePlateAssetVersionRef"]
                != base_asset["assetVersionRef"]
                or requirement["basePlateAssetVersionDigest"]
                != base_asset["payloadDigest"]
                or requirement["basePlateFileDigest"]
                != f"sha256:{base_asset['sha256']}"
            ):
                raise StaleInputError(
                    "editing Timeline effect Result binding is stale"
                )
            binding = {
                "clipRef": clip["clipRef"],
                "clipDigest": clip["payloadDigest"],
                "effectMode": requirement["effectMode"],
                "requirementRef": requirement["requirementRef"],
                "requirementDigest": requirement["payloadDigest"],
                "resultRef": result["resultRef"],
                "resultDigest": result["payloadDigest"],
                "executionRequestRef": request["executionRequestRef"],
                "executionRequestDigest": request["payloadDigest"],
                "artifactEvidenceRef": artifact["artifactEvidenceRef"],
                "artifactEvidenceDigest": artifact["payloadDigest"],
                "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
                "runtimeEvidenceDigest": runtime["payloadDigest"],
                "frameRangeStartInclusive": requirement[
                    "frameRangeStartInclusive"
                ],
                "frameRangeEndExclusive": requirement[
                    "frameRangeEndExclusive"
                ],
            }
            effect_bindings.append(binding)
            chains.append(chain)

        pixel_digests = {
            chain["requirement"]["basePlatePixelDigest"] for chain in chains
        }
        if len(pixel_digests) != 1:
            raise StaleInputError("effect base pixel authority is ambiguous")
        base_pixel_digest = next(iter(pixel_digests))
        resolved_base = {
            "assetVersionRef": base_asset["assetVersionRef"],
            "assetVersionDigest": base_asset["payloadDigest"],
            "storageKey": base_asset["storageKey"],
            "fileDigest": f"sha256:{base_asset['sha256']}",
            "pixelDigest": base_pixel_digest,
            "pixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC,
            "width": video_facts["width"],
            "height": video_facts["height"],
            "frameCount": video_facts["frameCount"],
            "frameRate": video_facts["frameRate"]["numerator"],
            "pixelFormat": video_facts["pixelFormat"],
        }

        exposure_chains = {
            chain["requirement"]["requirementRef"]: chain
            for chain in chains
            if chain["requirement"]["effectMode"] == LOCAL_EXPOSURE
        }
        for chain in chains:
            flame = chain["requirement"]
            if flame["effectMode"] != FLAME_EXTINGUISH:
                continue
            exposure_chain = exposure_chains.get(
                flame["localExposureRequirementRef"]
            )
            if exposure_chain is None:
                raise StaleInputError(
                    "Flame Extinguish Preview requires the bound Local Exposure Result"
                )
            exposure = exposure_chain["requirement"]
            exposure_result = exposure_chain["result"]
            flame_request = chain["executionRequest"]
            if (
                exposure["payloadDigest"]
                != flame["localExposureRequirementDigest"]
                or flame_request.get("localExposureResultRef")
                != exposure_result["resultRef"]
                or flame_request.get("localExposureResultDigest")
                != exposure_result["payloadDigest"]
            ):
                raise StaleInputError(
                    "Flame Extinguish Local Exposure Preview binding is stale"
                )

        for binding, chain in zip(effect_bindings, chains, strict=True):
            requirement = chain["requirement"]
            artifact = chain["artifactEvidence"]
            result = chain["result"]
            mode = requirement["effectMode"]
            resolved_images: list[dict[str, Any]] = []
            if mode in {"SCRATCH_REVEAL", "LIGHT_SWEEP", LOCAL_EXPOSURE}:
                resolved_images.append(
                    self._resolved_effect_image_asset(
                        snapshot=snapshot,
                        workspace=workspace,
                        run_ref=run_ref,
                        asset_version_ref=requirement[
                            "maskAssetVersionRef"
                        ],
                        asset_version_digest=requirement[
                            "maskAssetVersionDigest"
                        ],
                        file_digest=requirement["maskFileDigest"],
                        pixel_digest=requirement["maskPixelDigest"],
                        label="effect mask",
                    )
                )
            elif mode == FLAME_EXTINGUISH:
                resolved_images.append(
                    self._resolved_effect_image_asset(
                        snapshot=snapshot,
                        workspace=workspace,
                        run_ref=run_ref,
                        asset_version_ref=requirement[
                            "flameMaskAssetVersionRef"
                        ],
                        asset_version_digest=requirement[
                            "flameMaskAssetVersionDigest"
                        ],
                        file_digest=requirement["flameMaskFileDigest"],
                        pixel_digest=requirement["flameMaskPixelDigest"],
                        label="flame mask",
                    )
                )
            elif mode == SMOKE:
                resolved_images.append(
                    self._resolved_effect_image_asset(
                        snapshot=snapshot,
                        workspace=workspace,
                        run_ref=run_ref,
                        asset_version_ref=requirement[
                            "emissionMaskAssetVersionRef"
                        ],
                        asset_version_digest=requirement[
                            "emissionMaskAssetVersionDigest"
                        ],
                        file_digest=requirement["emissionMaskFileDigest"],
                        pixel_digest=requirement[
                            "emissionMaskPixelDigest"
                        ],
                        label="smoke emission mask",
                    )
                )
                if requirement["smokeSourceKind"] == "PINNED_SMOKE_LAYER":
                    resolved_images.append(
                        self._resolved_effect_image_asset(
                            snapshot=snapshot,
                            workspace=workspace,
                            run_ref=run_ref,
                            asset_version_ref=requirement[
                                "smokeLayerAssetVersionRef"
                            ],
                            asset_version_digest=requirement[
                                "smokeLayerAssetVersionDigest"
                            ],
                            file_digest=requirement[
                                "smokeLayerFileDigest"
                            ],
                            pixel_digest=requirement[
                                "smokeLayerPixelDigest"
                            ],
                            label="pinned smoke layer",
                            allow_canonical_asset=True,
                        )
                    )
            elif mode in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}:
                current_overlay_assets = self._resolved_overlay_authorities(
                    context=context,
                    requirement=requirement,
                )
                resolved_images.extend(
                    deepcopy(item)
                    for reference, item in current_overlay_assets.items()
                    if reference != resolved_base["assetVersionRef"]
                )
            elif mode == "DISTANCE_STATE_TRANSITION":
                current_transition_assets = (
                    self._resolved_distance_state_authorities(
                        context=context,
                        requirement=requirement,
                    )
                )
                resolved_images.extend(
                    deepcopy(item)
                    for reference, item in current_transition_assets.items()
                    if reference != resolved_base["assetVersionRef"]
                )
            else:
                raise RepositoryUnavailableError(
                    "deterministic Effect mode is unsupported"
                )
            v3_digest = artifact["v3ExecutionRequestDigest"]
            workspace_hash = sha256(workspace.encode("utf-8")).hexdigest()[:20]
            run_hash = sha256(run_ref.encode("utf-8")).hexdigest()[:20]
            output = artifact["outputDigest"]
            probe = artifact["outputMediaProbe"]
            if mode in {
                FLAME_EXTINGUISH,
                SMOKE,
                "NAMEPLATE_TEXT",
                "FACE_MARK_COMPENSATION",
                "DISTANCE_STATE_TRANSITION",
            } and (
                result.get("outputFileDigest") != output["fileDigest"]
                or result.get("outputDecodedFramePixelDigest")
                != output["decodedFramePixelDigest"]
                or result.get("outputMediaProbe") != probe
            ):
                raise StaleInputError(
                    "deterministic Effect Result output binding is stale"
                )
            effect_executions[binding["resultRef"]] = {
                **deepcopy(chain),
                "assetVersions": {
                    resolved_base["assetVersionRef"]: deepcopy(resolved_base),
                    **{
                        item["assetVersionRef"]: item
                        for item in resolved_images
                    },
                },
                "artifactStorage": {
                    "artifactEvidenceRef": artifact["artifactEvidenceRef"],
                    "artifactEvidenceDigest": artifact["payloadDigest"],
                    "storageKey": (
                        (
                            f"{workspace_hash}/{run_hash}/distance-state/"
                            f"distance-state-{v3_digest}.mp4"
                        )
                        if mode == "DISTANCE_STATE_TRANSITION"
                        else (
                            f"{workspace_hash}/{run_hash}/deterministic-overlays/"
                            f"overlay-{v3_digest}.mp4"
                            if mode
                            in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}
                            else (
                            f"{workspace_hash}/{run_hash}/masked-surface/"
                            f"masked-surface-{v3_digest}.mp4"
                            )
                        )
                    ),
                    "fileDigest": output["fileDigest"],
                    "pixelDigest": output["decodedFramePixelDigest"],
                    "pixelDigestSpec": output[
                        "decodedFramePixelDigestSpec"
                    ],
                    "width": output["width"],
                    "height": output["height"],
                    "frameCount": output["frameCount"],
                    "frameRate": output["frameRate"],
                    "pixelFormat": probe["pixelFormat"],
                },
            }

        glyph_requirement = inputs["glyphRevealRequirement"]
        glyph_source = layout["glyph"]["sourceBinding"]
        if (
            glyph_source["effectRequirementRef"]
            != glyph_requirement.requirement_ref
            or glyph_source["effectRequirementDigest"]
            != glyph_requirement.payload_digest
            or glyph_source.get("effectResultRef") is not None
            or layout["glyph"]["timelineStartFrameInclusive"]
            != glyph_requirement.frame_range_start_inclusive
            or layout["glyph"]["timelineEndFrameExclusive"]
            != glyph_requirement.frame_range_end_exclusive
        ):
            raise StaleInputError("Glyph Requirement Timeline binding is stale")
        glyph_request = deepcopy(inputs["glyphRevealExecutionRequest"])
        glyph_binding = {
            "clipRef": layout["glyph"]["clipRef"],
            "clipDigest": layout["glyph"]["payloadDigest"],
            "requirementRef": glyph_requirement.requirement_ref,
            "requirementDigest": glyph_requirement.payload_digest,
        }
        glyph_assets: dict[str, dict[str, Any]] = {
            glyph_request["basePlate"]["assetVersionRef"]: deepcopy(
                glyph_request["basePlate"]
            )
        }
        glyph_assets.update(
            {
                item["assetVersionRef"]: deepcopy(item)
                for item in glyph_request["masks"]
            }
        )
        audio_mix = self._editing_preview_audio_mix(
            layout=layout, inputs=inputs
        )
        subtitle_manifest = self._editing_preview_subtitle_manifest(
            layout=layout
        )
        duration_samples = audio_mix["durationSamples"]
        command = {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "baseVideo": {
                **{
                    field: deepcopy(resolved_base[field])
                    for field in (
                        "assetVersionRef",
                        "assetVersionDigest",
                        "fileDigest",
                        "pixelDigest",
                        "width",
                        "height",
                        "frameCount",
                    )
                },
                "frameRate": deepcopy(version["frameRate"]),
            },
            "effectResultBindings": effect_bindings,
            "glyphRequirementBinding": glyph_binding,
            "audioMix": audio_mix,
            "subtitleManifest": subtitle_manifest,
            "output": {
                "width": version["canvasWidth"],
                "height": version["canvasHeight"],
                "frameRate": deepcopy(version["frameRate"]),
                "totalFrames": version["durationFrames"],
                "sampleRate": 48_000,
                "channelCount": 2,
                "durationSamples": duration_samples,
                "container": "mp4",
                "videoCodec": "h264",
                "pixelFormat": "yuv420p",
                "audioCodec": "aac",
                "audioBitRate": 128_000,
            },
        }
        return {
            "layout": layout,
            "inputs": inputs,
            "audioMix": audio_mix,
            "subtitleManifest": subtitle_manifest,
            "effectResultBindings": effect_bindings,
            "glyphRequirementBinding": glyph_binding,
            "compositionCommand": command,
            "resolvedArtifacts": {
                "baseVideo": resolved_base,
                "effectExecutions": effect_executions,
                "glyphExecution": {
                    "requirement": glyph_requirement.as_dict(),
                    "executionRequest": glyph_request,
                    "assetVersions": glyph_assets,
                },
            },
        }

    def _resolve_registered_timeline_inputs(
        self,
        *,
        workspace: str,
        run_ref: str,
        references: Mapping[str, Any],
        snapshot: Any,
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
        current_video_assets = self._current_glyph_video_assets(
            workspace,
            run_ref,
            evidence_snapshot=snapshot,
        )
        base_matches = [
            item
            for item in current_video_assets
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
        if self.glyph_inspection_adapter is None:
            raise UpstreamNotReadyError(
                "server-held glyph inspection evidence is not configured"
            )
        glyph_execution_request = build_glyph_reveal_execution_request_v2(
            requirement,
            base_plate_asset=base_plate,
            mask_assets=mask_assets,
            inspection_adapter=self.glyph_inspection_adapter,
        )
        glyph_output = glyph_execution_request["output"]
        base_video_facts = {
            "width": glyph_output["width"],
            "height": glyph_output["height"],
            "frameCount": glyph_output["totalFrames"],
            "frameRate": self._editing_frame_rate(
                glyph_output["frameRate"]
            ),
            # This is the closed Preview input contract.  V3 re-probes the
            # staged digest-pinned file and rejects any non-yuv420p source.
            "pixelFormat": "yuv420p",
        }
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
            "glyphRevealExecutionRequest": glyph_execution_request,
            "basePlateAssetVersion": base_plate,
            "baseVideoFacts": base_video_facts,
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
        video_facts = deepcopy(inputs["baseVideoFacts"])
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

    def _validated_stored_effect_timeline_preview(
        self,
        *,
        context: Mapping[str, Any],
        composition_gate: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Restore one v3 Preview without creating a second Timeline fact."""

        snapshot = context["snapshot"]
        preview_fact = _immutable_payload(
            _fact(composition_gate, "PreviewCandidate"), "PreviewCandidate"
        )
        if preview_fact.get("schemaVersion") != PREVIEW_CANDIDATE_SCHEMA_VERSION_V3:
            raise StaleInputError("stored Preview does not use the M13-E1 contract")
        preview_payload = self._snapshot_record_payload(
            snapshot,
            record_kind="PreviewCandidate",
            record_ref=_required_ref(
                preview_fact.get("previewCandidateVersionRef"),
                "previewCandidateVersionRef",
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
        if (
            preview_payload != preview_fact
            or composition_payload.get("schemaVersion")
            != EFFECT_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION
        ):
            raise RepositoryUnavailableError(
                "G6 v3 Preview fact and append-only records differ"
            )
        restored = self._restore_editing_timeline(
            context,
            timeline_version_ref=_required_ref(
                preview_payload.get("timelineVersionRef"),
                "timelineVersionRef",
            ),
        )
        timeline_version = restored["timelineVersion"]
        version_payload = timeline_version.as_dict()
        if (
            preview_payload.get("timelineVersionDigest")
            != version_payload["payloadDigest"]
        ):
            raise StaleInputError("Preview TimelineVersion lineage is stale")
        composition_result = validate_effect_preview_composition_result(
            composition_payload,
            timeline_version=timeline_version,
        )
        preview_candidate = validate_effect_preview_candidate(
            preview_payload,
            timeline_version=timeline_version,
            composition_result=composition_result,
        )
        projection = self._editing_effect_preview_projection(
            context=context,
            restored=restored,
        )
        composition_mapping = composition_result.as_dict()
        if (
            composition_mapping["effectResultBindings"]
            != projection["effectResultBindings"]
            or composition_mapping["glyphRequirementBinding"]
            != projection["glyphRequirementBinding"]
            or composition_mapping["mixRequestRef"]
            != projection["audioMix"]["mixRequestRef"]
            or composition_mapping["mixRequestDigest"]
            != projection["audioMix"]["mixRequestDigest"]
            or composition_mapping["subtitleManifestRef"]
            != projection["subtitleManifest"]["subtitleManifestRef"]
            or composition_mapping["subtitleManifestDigest"]
            != projection["subtitleManifest"]["subtitleManifestDigest"]
        ):
            raise StaleInputError("stored Preview input projection is stale")
        artifact_path = self._verify_timeline_composition_artifact(
            composition_mapping
        )
        return {
            "restoredTimeline": restored,
            "timelineVersion": timeline_version,
            "compositionResult": composition_result,
            "previewCandidate": preview_candidate,
            "projection": projection,
            "artifactPath": artifact_path,
        }

    def _validated_stored_timeline_preview(
        self,
        *,
        command: Mapping[str, Any],
        composition_gate: Mapping[str, Any],
        snapshot: Any,
    ) -> dict[str, Any]:
        """Rebuild authority wrappers from append-only evidence, then pin bytes."""

        workspace = command["workspaceRef"]
        run_ref = command["productionRunRef"]
        inputs = self._resolve_registered_timeline_inputs(
            workspace=workspace,
            run_ref=run_ref,
            references=command["timelineInputRefs"],
            snapshot=snapshot,
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

    def compose_editing_timeline_preview(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Compose the exact editing Timeline v3 through the additive V4 port."""

        normalized = self._editing_timeline_preview_command(command)
        workspace = normalized["workspaceRef"]
        run_ref = normalized["productionRunRef"]
        context = self._timeline_authority_context(
            workspace,
            run_ref,
            expected_run_version=normalized["expectedRunVersion"],
        )
        restored = self._restore_editing_timeline(
            context,
            timeline_version_ref=normalized["timelineVersionRef"],
        )
        version_payload = restored["timelineVersion"].as_dict()
        latest_payload = restored["versionHistory"][-1].as_dict()
        if (
            version_payload["payloadDigest"]
            != normalized["timelineVersionDigest"]
            or latest_payload["timelineVersionRef"]
            != normalized["timelineVersionRef"]
            or latest_payload["payloadDigest"]
            != normalized["timelineVersionDigest"]
        ):
            raise StaleInputError("editing Timeline Preview input is stale")
        if self.composition is None or not callable(
            getattr(self.composition, "compose_timeline_preview_v2", None)
        ):
            raise WorkerUnavailableError(
                "M13 effect Preview composition is not configured"
            )

        client_key = normalized["idempotencyKey"]
        operation_ref = normalized["operationRef"]
        effect_profile = self._editing_preview_layout(restored)[
            "effectProfile"
        ]
        composition_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "operationRef": operation_ref,
                "stage": {
                    "M13_E1": "m13-e1-editing-timeline-composition",
                    "M13_E2": "m13-e2-editing-timeline-composition",
                    "M13_E3": "m13-e3-editing-timeline-composition",
                    "M13_E4": "m13-e4-editing-timeline-composition",
                }[effect_profile],
            }
        )
        composition_request_digest = _digest(
            {
                "schemaVersion": {
                    "M13_E1": "v5.m13-effect-preview-command.v1",
                    "M13_E2": "v5.m13-effect-preview-command.v2",
                    "M13_E3": "v5.m13-effect-preview-command.v3",
                    "M13_E4": "v5.m13-effect-preview-command.v4",
                }[effect_profile],
                "command": normalized,
                "deliveryId": TIMELINE_PREVIEW_DELIVERY_ID,
            }
        )
        composition_gate = self._existing(
            workspace,
            run_ref,
            M13_EFFECT_COMPOSITION_GATE,
            composition_key,
            composition_request_digest,
        )
        composition_replay = composition_gate is not None

        if composition_gate is None:
            if context["snapshot"].revisionToken != normalized[
                "expectedEvidenceRevision"
            ]:
                raise StaleInputError("episode evidence revision changed")
            source_state = context["snapshot"].currentState
            if source_state not in M13_PREVIEW_STATE_TRANSITIONS:
                raise UpstreamNotReadyError(
                    "M13 effect Preview requires current video media"
                )
            preview_state = M13_PREVIEW_STATE_TRANSITIONS[source_state]
            projection = self._editing_effect_preview_projection(
                context=context,
                restored=restored,
            )
            now = self._clock()
            try:
                execution_result = self.composition.compose_timeline_preview_v2(
                    projection["compositionCommand"],
                    resolved_artifacts=projection["resolvedArtifacts"],
                )
            except CompositionExecutionError as exc:
                raise WorkerUnavailableError(
                    "M13 deterministic effect Preview composition failed"
                ) from exc

            # The generic evidence journal is not the sole currentness owner
            # for Root/Shot/current media.  Close the render window by reading
            # every authority again and rebuilding the exact projection before
            # the CompositionResult or PreviewCandidate becomes immutable.
            post_render_context = self._timeline_authority_context(
                workspace,
                run_ref,
                expected_run_version=normalized["expectedRunVersion"],
            )
            post_render_restored = self._restore_editing_timeline(
                post_render_context,
                timeline_version_ref=normalized["timelineVersionRef"],
            )
            post_render_projection = self._editing_effect_preview_projection(
                context=post_render_context,
                restored=post_render_restored,
            )
            if (
                post_render_context["snapshot"].revisionToken
                != normalized["expectedEvidenceRevision"]
                or post_render_context["snapshot"].revisionToken
                != context["snapshot"].revisionToken
                or post_render_context["snapshot"].currentState
                != source_state
                or post_render_projection != projection
            ):
                raise StaleInputError(
                    "M13 effect Preview authority changed during composition"
                )
            composition_result = validate_effect_preview_composition_result(
                build_effect_preview_composition_result(
                    {
                        "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                        "createdAt": now,
                    },
                    timeline_version=post_render_restored["timelineVersion"],
                    execution_result=execution_result,
                ),
                timeline_version=post_render_restored["timelineVersion"],
            )
            composition_payload = composition_result.as_dict()
            preview_ref = "m13-effect-preview-candidate-" + _digest(
                {
                    "timelineVersionRef": version_payload[
                        "timelineVersionRef"
                    ],
                    "timelineVersionDigest": version_payload["payloadDigest"],
                    "compositionResultRef": composition_payload[
                        "compositionResultRef"
                    ],
                    "compositionResultDigest": composition_payload[
                        "payloadDigest"
                    ],
                }
            )[:32]
            preview_candidate = validate_effect_preview_candidate(
                build_effect_preview_candidate(
                    {
                        "previewCandidateRef": preview_ref,
                        "previewCandidateVersionRef": f"{preview_ref}-version-1",
                        "version": 1,
                        "supersedesPreviewCandidateVersionRef": None,
                        "supersedesPreviewCandidateVersionDigest": None,
                        "createdBy": TIMELINE_PREVIEW_DELIVERY_ID,
                        "createdAt": now,
                    },
                    timeline_version=post_render_restored["timelineVersion"],
                    composition_result=composition_result,
                ),
                timeline_version=post_render_restored["timelineVersion"],
                composition_result=composition_result,
            )
            preview_payload = preview_candidate.as_dict()
            self._verify_timeline_composition_artifact(composition_payload)
            records = (
                self._composition_record(
                    workspace=workspace,
                    run_ref=run_ref,
                    record_kind="CompositionResult",
                    record_ref=composition_payload["compositionResultRef"],
                    record_version=1,
                    client_key=client_key,
                    operation_ref=operation_ref,
                    composition_request_digest=composition_request_digest,
                    slot="effect-composition-result",
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
                    slot="effect-preview-candidate",
                    created_at=now,
                    payload=preview_payload,
                ),
            )
            journal_head = self._stable_record_head(
                workspace,
                run_ref,
                post_render_context["snapshot"].revisionToken,
            )
            _, composition_gate, atomic_replay = (
                self.evidence.append_records_and_gate(
                    records,
                    GateAppend(
                        workspace,
                        run_ref,
                        M13_EFFECT_COMPOSITION_GATE,
                        composition_key,
                        context["run"]["payloadDigest"],
                        composition_request_digest,
                        source_state,
                        preview_state,
                        now,
                        (
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
            stored = {
                "timelineVersion": post_render_restored["timelineVersion"],
                "compositionResult": composition_result,
                "previewCandidate": preview_candidate,
                "projection": projection,
            }
        else:
            stored = self._validated_stored_effect_timeline_preview(
                context=context,
                composition_gate=composition_gate,
            )

        version_payload = stored["timelineVersion"].as_dict()
        composition_payload = stored["compositionResult"].as_dict()
        preview_payload = stored["previewCandidate"].as_dict()
        result_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        return {
            "state": composition_gate["toState"],
            "timelineVersion": version_payload,
            "compositionResult": composition_payload,
            "previewCandidate": preview_payload,
            "evidenceRevision": result_snapshot.revisionToken,
            "idempotentReplay": composition_replay,
        }

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
        authority_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        self._reject_legacy_timeline_write_if_editing_authority(
            authority_snapshot
        )
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
            "timelineVersionRef",
            "timelineVersionDigest",
        }:
            return self.compose_editing_timeline_preview(command)
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
        authority_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        self._reject_legacy_timeline_write_if_editing_authority(
            authority_snapshot
        )
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
        selected_preview_is_v3 = False
        composition = self.evidence.get_gate(
            workspace_ref, run_ref, M13_EFFECT_COMPOSITION_GATE
        ) or self.evidence.get_gate(workspace_ref, run_ref, COMPOSITION_GATE)
        qc = self.evidence.get_gate(workspace_ref, run_ref, QC_GATE)
        approvals = self.evidence.get_gate(workspace_ref, run_ref, APPROVAL_GATE)
        master = self.evidence.get_gate(workspace_ref, run_ref, MASTER_GATE)
        if composition is not None:
            preview = _fact(composition, "PreviewCandidate")
            if preview.get("schemaVersion") == PREVIEW_CANDIDATE_SCHEMA_VERSION_V3:
                selected_preview_is_v3 = True
                context = self._timeline_authority_context(
                    workspace_ref, run_ref, expected_run_version=None
                )
                stored = self._validated_stored_effect_timeline_preview(
                    context=context,
                    composition_gate=composition,
                )
                result.update(
                    {
                        "timelineVersion": stored[
                            "timelineVersion"
                        ].as_dict(),
                        "previewCandidate": stored[
                            "previewCandidate"
                        ].as_dict(),
                    }
                )
            else:
                result.update(
                    {
                        "timelineVersion": _fact(
                            composition, "TimelineVersion"
                        ),
                        "previewCandidate": preview,
                    }
                )
        if qc is not None and not selected_preview_is_v3:
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
            workspace, production_run_ref, M13_EFFECT_COMPOSITION_GATE
        ) or self.evidence.get_gate(
            workspace, production_run_ref, COMPOSITION_GATE
        )
        qc_gate = self.evidence.get_gate(
            workspace, production_run_ref, QC_GATE
        )
        if composition_gate is None:
            raise UpstreamNotReadyError("G6 preview is not ready")
        preview_fact = _immutable_payload(
            _fact(composition_gate, "PreviewCandidate"), "PreviewCandidate"
        )

        if preview_fact.get("schemaVersion") == PREVIEW_CANDIDATE_SCHEMA_VERSION_V3:
            context = self._timeline_authority_context(
                workspace,
                production_run_ref,
                expected_run_version=None,
            )
            stored = self._validated_stored_effect_timeline_preview(
                context=context,
                composition_gate=composition_gate,
            )
            timeline = stored["timelineVersion"].as_dict()
            preview = stored["previewCandidate"].as_dict()
            projection = stored["projection"]
            preview_fields = (
                "previewCandidateRef",
                "previewCandidateVersionRef",
                "version",
                "timelineRef",
                "timelineVersionRef",
                "timelineVersionDigest",
                "effectResultBindings",
                "glyphRequirementBinding",
                "effectBindingsDigest",
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
                "immutable",
                "publicationAllowed",
                "payloadDigest",
            )
            return {
                "state": composition_gate["toState"],
                "productionRunRef": production_run_ref,
                "timeline": {
                    key: deepcopy(timeline[key])
                    for key in (
                        "timelineRef",
                        "timelineVersionRef",
                        "versionNumber",
                        "parentTimelineVersionRef",
                        "parentTimelineVersionDigest",
                        "frameRate",
                        "canvasWidth",
                        "canvasHeight",
                        "durationFrames",
                        "trackRefs",
                        "outputProfileBindings",
                        "payloadDigest",
                    )
                },
                "preview": {
                    key: deepcopy(preview[key]) for key in preview_fields
                },
                "audio": {
                    "stemSetVersionRef": projection["audioMix"][
                        "stemSetVersionRef"
                    ],
                    "stemSetDigest": projection["audioMix"]["stemSetDigest"],
                    "mixRequestRef": projection["audioMix"]["mixRequestRef"],
                    "mixRequestDigest": projection["audioMix"][
                        "mixRequestDigest"
                    ],
                    "assetVersionRefs": sorted(
                        {
                            item["sourceBinding"]["audioAssetVersionRef"]
                            for item in projection["layout"]["audio"]
                        }
                    ),
                },
                "cues": [
                    {
                        "clipRef": item["clipRef"],
                        "clipDigest": item["payloadDigest"],
                        "timelineStartFrameInclusive": item[
                            "timelineStartFrameInclusive"
                        ],
                        "timelineEndFrameExclusive": item[
                            "timelineEndFrameExclusive"
                        ],
                        "audioCueRef": item["sourceBinding"]["audioCueRef"],
                        "audioCueDigest": item["sourceBinding"][
                            "audioCueDigest"
                        ],
                        "language": item["sourceBinding"]["language"],
                        "wordTiming": deepcopy(
                            item["sourceBinding"]["wordTiming"]
                        ),
                    }
                    for item in projection["layout"]["subtitles"]
                ],
                "effect": {
                    "executionOrder": [
                        *(
                            item["effectMode"]
                            for item in preview["effectResultBindings"]
                        ),
                        "GLYPH_REVEAL",
                    ],
                    "effectResultBindings": deepcopy(
                        preview["effectResultBindings"]
                    ),
                    "glyphRequirementBinding": deepcopy(
                        preview["glyphRequirementBinding"]
                    ),
                    "effectBindingsDigest": preview[
                        "effectBindingsDigest"
                    ],
                },
            }

        if qc_gate is None:
            raise UpstreamNotReadyError("G6 preview and QC are not ready")
        qc = _immutable_payload(_fact(qc_gate, "QCReport"), "QCReport")

        timeline_fact = _immutable_payload(
            _fact(composition_gate, "TimelineVersion"), "TimelineVersion"
        )

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
        stored = self._validated_stored_timeline_preview(
            command={
                "workspaceRef": workspace,
                "productionRunRef": production_run_ref,
                "timelineInputRefs": references,
            },
            composition_gate=composition_gate,
            snapshot=snapshot,
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
            workspace, production_run_ref, M13_EFFECT_COMPOSITION_GATE
        ) or self.evidence.get_gate(
            workspace, production_run_ref, COMPOSITION_GATE
        )
        qc_gate = self.evidence.get_gate(workspace, production_run_ref, QC_GATE)
        if composition_gate is None:
            raise UpstreamNotReadyError("G6 preview is not ready")
        preview = _fact(composition_gate, "PreviewCandidate")
        if preview.get("schemaVersion") == PREVIEW_CANDIDATE_SCHEMA_VERSION_V3:
            context = self._timeline_authority_context(
                workspace,
                production_run_ref,
                expected_run_version=None,
            )
            stored = self._validated_stored_effect_timeline_preview(
                context=context,
                composition_gate=composition_gate,
            )
            composition = stored["compositionResult"].as_dict()
            return {
                "path": stored["artifactPath"],
                "fileName": f"preview-{production_run_ref}.mp4",
                "mediaType": "video/mp4",
                "byteSize": composition["outputByteSize"],
                "sha256": composition["outputDigest"][
                    "fileDigest"
                ].removeprefix("sha256:"),
                "contentDisposition": "inline",
            }
        if qc_gate is None:
            raise UpstreamNotReadyError("G6 preview and QC are not ready")
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
            stored = self._validated_stored_timeline_preview(
                command={
                    "workspaceRef": workspace,
                    "productionRunRef": production_run_ref,
                    "timelineInputRefs": references,
                },
                composition_gate=composition_gate,
                snapshot=snapshot,
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
