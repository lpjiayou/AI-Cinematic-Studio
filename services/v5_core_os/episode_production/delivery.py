"""G6 deterministic composition, QC, explicit decisions and immutable master."""

from __future__ import annotations

from copy import deepcopy
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
APPROVAL_SCHEMA_VERSION = "v5.approval-decision.v1"
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


class ApprovalAuthorityPort(Protocol):
    def verify(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        kind: str,
        approval_ref: str,
        actor_ref: str,
    ) -> Mapping[str, Any]: ...


class RejectingApprovalAuthority:
    def verify(self, **kwargs: Any) -> Mapping[str, Any]:
        del kwargs
        raise ApprovalRequiredError("an external approval authority is required")


class StaticApprovalAuthority:
    """Explicit test/local integration authority; never configured implicitly."""

    def __init__(self, approvals: Mapping[str, Mapping[str, Any]]) -> None:
        self._approvals = deepcopy(dict(approvals))

    def verify(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        kind: str,
        approval_ref: str,
        actor_ref: str,
    ) -> Mapping[str, Any]:
        value = self._approvals.get(approval_ref)
        if (
            not isinstance(value, Mapping)
            or value.get("workspaceRef") != workspace_ref
            or value.get("productionRunRef") != production_run_ref
            or value.get("kind") != kind
            or value.get("actorRef") != actor_ref
            or value.get("authorityType") not in {"HUMAN", "EXTERNAL_POLICY"}
        ):
            raise ApprovalRequiredError("approval authority rejected evidence")
        return deepcopy(dict(value))


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
        if self.composition is None:
            raise WorkerUnavailableError("composition execution is not configured")
        verified = self.media.verify_media_current(workspace, run_ref)
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
            by_kind[kind] = item
        if set(by_kind) != set(APPROVAL_KINDS):
            raise ValidationFailedError("approval decision coverage is incomplete")
        verified, timeline, preview, qc = self._verified_preview_qc(workspace, run_ref)
        root = verified["root"]
        now = self._clock()
        normalized = [deepcopy(dict(by_kind[kind])) for kind in APPROVAL_KINDS]
        approval_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "approvals"}
        )
        approval_request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "previewDigest": preview["payloadDigest"],
                "qcDigest": qc["payloadDigest"],
                "decisions": normalized,
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
                approval_ref = _required_ref(item["approvalRef"], "approvalRef")
                actor_ref = _required_ref(item["actorRef"], "actorRef")
                authority = self.approval_authority.verify(
                    workspace_ref=workspace,
                    production_run_ref=run_ref,
                    kind=item["kind"],
                    approval_ref=approval_ref,
                    actor_ref=actor_ref,
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
                            "authorityType": authority["authorityType"],
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
        if (
            [item["kind"] for item in decisions] != list(APPROVAL_KINDS)
            or any(item["decision"] != "ACCEPT" for item in decisions)
            or any(item["previewCandidateDigest"] != preview["payloadDigest"] for item in decisions)
            or any(item["qcReportDigest"] != qc["payloadDigest"] for item in decisions)
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
