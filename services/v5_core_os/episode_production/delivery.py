"""G6 deterministic composition, QC, explicit decisions and immutable master."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from services.v4_platform import CompositionExecutionError, probe_media

from .evidence import EpisodeProductionEvidenceRepository, EvidenceFact, GateAppend
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
from .shot_graph import ValidationFailedError


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
    ) -> None:
        self.media = media
        self.evidence = evidence
        self.composition = composition
        self.approval_authority = approval_authority
        self._ref_factory = ref_factory
        self._clock = clock

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

    def get_preview_file(
        self, workspace_ref: str, run_ref: str
    ) -> dict[str, Any]:
        _, _, preview, _ = self._verified_preview_qc(workspace_ref, run_ref)
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
