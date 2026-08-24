"""Image-first same-run revision planning for K2 real media.

This V5 service creates provider-neutral M10 shot-image requests from the current
G2 identity lock and G3 shot graph.  It deliberately does not execute ComfyUI,
select a candidate, create an AssetVersion, approve a preview or publish.  Those
are separate V4 execution and V5 admission operations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping, Protocol, Sequence

from services.v4_platform import RealImageCandidateEvidenceError
from services.v4_platform.real_video_candidates import (
    RealVideoCandidateEvidenceError,
)

from .delivery import QC_GATE
from .evidence import (
    EpisodeProductionEvidenceRepository,
    EvidenceFact,
    EvidenceRecord,
    EvidenceSnapshot,
    GateAppend,
)
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .media_candidate_review import (
    ASSET_ADMISSION,
    ASSET_VERSION,
    CANDIDATE,
    HUMAN_SELECTION,
    K2MediaCandidateReviewService,
    TECHNICAL_VALIDATION,
)
from .shot_graph import K2ShotGraphService


REAL_IMAGE_PLAN_GATE = "M10_REAL_IMAGE_PLAN"
REAL_IMAGE_ADMISSION_GATE = "M10_REAL_IMAGE_ADMISSION"
REAL_VIDEO_PLAN_GATE = "M11_REAL_VIDEO_PLAN"
REAL_VIDEO_ADMISSION_GATE = "M11_REAL_VIDEO_ADMISSION"
REAL_IMAGE_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-image-request.v1"
REAL_IMAGE_PLAN_SCHEMA_VERSION = "v5.k2-real-image-plan.v1"
REAL_IMAGE_CANDIDATE_SCHEMA_VERSION = "v5.k2-real-image-candidate.v1"
REAL_IMAGE_SELECTION_SCHEMA_VERSION = "v5.k2-media-selection-decision.v1"
REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-real-image-asset-version.v1"
REAL_IMAGE_ADMISSION_MANIFEST_SCHEMA_VERSION = (
    "v5.k2-real-image-admission-manifest.v1"
)
REAL_IMAGE_UNIFIED_ADMISSION_MANIFEST_SCHEMA_VERSION = (
    "v5.k2-real-image-admission-manifest.v2"
)
REAL_VIDEO_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-video-request.v1"
REAL_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-video-request.v2"
REAL_VIDEO_PLAN_SCHEMA_VERSION = "v5.k2-real-video-plan.v1"
REAL_VIDEO_ADMISSION_SCHEMA_VERSION = "v5.k2-real-video-admission-manifest.v1"
REAL_VIDEO_SUCCESSOR_ACTIVATION_SCHEMA_VERSION = (
    "v5.k2-real-video-batch-activation.v2"
)
REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-real-video-asset-version.v1"
REAL_IMAGE_PLANNER_ID = "v5.k2.real-image-planner.v1"
REAL_IMAGE_ADMISSION_ID = "v5.k2.real-image-admission.v1"
REAL_VIDEO_PLANNER_ID = "v5.k2.real-video-planner.v1"
REAL_VIDEO_SUCCESSOR_PLANNER_ID = "v5.k2.real-video-successor-planner.v1"
REAL_VIDEO_SUCCESSOR_REVISION_SCHEMA_VERSION = (
    "v5.k2-real-video-successor-revision.v1"
)
_REAL_VIDEO_SUCCESSOR_REVISION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "realVideoRevisionRef",
        "version",
        "isSuccessor",
        "sourceRealVideoPlanRef",
        "sourceRealVideoPlanDigest",
        "supersedesRealVideoRevisionRef",
        "supersedesRealVideoRevisionDigest",
        "sourceImageAssetVersionRefs",
        "sourceImageAssetVersionDigests",
        "generationRequestRefs",
        "generationRequestVersionRefs",
        "generationRequestDigests",
        "generationRequestCount",
        "generationRequests",
        "changedSlotRefs",
        "publicationAllowed",
        "payloadDigest",
    }
)
_REAL_VIDEO_SUCCESSOR_REQUEST_EXTENSION = frozenset(
    {
        "realVideoRevisionRef",
        "sourceRealVideoPlanRef",
        "sourceRealVideoPlanDigest",
        "supersedesGenerationRequestVersionRef",
        "supersedesGenerationRequestDigest",
    }
)
_REAL_VIDEO_INITIAL_ACTIVATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "realVideoAdmissionManifestRef",
        "version",
        "realVideoPlanRef",
        "realVideoPlanDigest",
        "revisionRef",
        "realVideoRevisionRef",
        "realVideoRevisionDigest",
        "selectionRequestDigest",
        "candidateRefs",
        "candidateDigests",
        "selectionRefs",
        "selectionDigests",
        "assetVersionRefs",
        "assetVersionDigests",
        "admittedCount",
        "state",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_REAL_VIDEO_SUCCESSOR_ACTIVATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "admissionRef",
        "version",
        "admissionState",
        "realVideoPlanRef",
        "realVideoPlanDigest",
        "realVideoRevisionRef",
        "realVideoRevisionDigest",
        "supersedesActivationRef",
        "supersedesActivationDigest",
        "operationIdempotencyKey",
        "selectionRequestDigest",
        "changedSlotRefs",
        "slotActivations",
        "assetVersionRefs",
        "assetVersionDigests",
        "newAdmissionRefs",
        "newAdmissionDigests",
        "newAdmissionCount",
        "reusedAdmissionCount",
        "state",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_REAL_VIDEO_ACTIVATION_SLOT_FIELDS = frozenset(
    {
        "ordinal",
        "slotRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "candidateRef",
        "candidateDigest",
        "semanticVisualQcRef",
        "semanticVisualQcDigest",
        "humanSelectionRef",
        "humanSelectionDigest",
        "assetAdmissionRef",
        "assetAdmissionDigest",
        "assetVersionRef",
        "assetVersionDigest",
        "activationSource",
    }
)
REAL_IMAGE_CAPABILITY = "self-hosted-multi-reference-shot-image-v1"
REAL_VIDEO_CAPABILITY = "self-hosted-wan22-image-to-video-v1"


class RealImageCandidateRejectedError(EpisodeProductionError):
    code = "real_image_candidate_evidence_rejected"


class RealVideoCandidateRejectedError(EpisodeProductionError):
    code = "real_video_candidate_evidence_rejected"


class RealImageCandidateEvidencePort(Protocol):
    def resolve_candidates(
        self,
        workspace_ref: str,
        production_run_ref: str,
        real_image_plan_ref: str,
        expected_requests: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]: ...


class RejectingRealImageCandidateEvidence:
    def resolve_candidates(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RealImageCandidateEvidenceError(
            "M10 candidate evidence is not configured"
        )


class RealVideoCandidateEvidencePort(Protocol):
    def resolve_candidates(
        self,
        workspace_ref: str,
        production_run_ref: str,
        real_video_plan_ref: str,
        expected_requests: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]: ...


class RejectingRealVideoCandidateEvidence:
    def resolve_candidates(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del args, kwargs
        raise RealVideoCandidateEvidenceError(
            "M11 candidate evidence is not configured"
        )


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _record(
    *,
    workspace_ref: str,
    production_run_ref: str,
    record_kind: str,
    record_ref: str,
    record_version: int,
    idempotency_key: str,
    created_at: str,
    payload: Mapping[str, Any],
) -> EvidenceRecord:
    payload_digest = _content_digest(payload.get("payloadDigest"), "payloadDigest")
    return EvidenceRecord(
        workspaceRef=workspace_ref,
        productionRunRef=production_run_ref,
        recordKind=record_kind,
        recordRef=record_ref,
        recordVersion=record_version,
        idempotencyKey=idempotency_key,
        requestDigest=_digest(
            {
                "recordKind": record_kind,
                "recordRef": record_ref,
                "recordVersion": record_version,
                "payloadDigest": payload_digest,
            }
        ),
        createdAt=created_at,
        payload=deepcopy(dict(payload)),
        payloadDigest=payload_digest,
    )


def _fact(gate: Mapping[str, Any], kind: str) -> dict[str, Any]:
    matches = [
        item
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and item.get("factKind") == kind
        and isinstance(item.get("payload"), Mapping)
    ]
    if len(matches) != 1:
        raise RepositoryUnavailableError("real image revision fact is inconsistent")
    return deepcopy(dict(matches[0]["payload"]))


def _request_facts(gate: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = [
        deepcopy(dict(item["payload"]))
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and str(item.get("factKind", "")).startswith("RealImageGenerationRequest:")
        and isinstance(item.get("payload"), Mapping)
    ]
    return sorted(values, key=lambda item: item["ordinal"])


def _facts(gate: Mapping[str, Any], prefix: str) -> list[dict[str, Any]]:
    values = [
        deepcopy(dict(item["payload"]))
        for item in gate.get("facts", [])
        if isinstance(item, Mapping)
        and str(item.get("factKind", "")).startswith(prefix)
        and isinstance(item.get("payload"), Mapping)
    ]
    return sorted(values, key=lambda item: item["ordinal"])


def _content_digest(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


class K2RealMediaRevisionService:
    """Owns M10/M11 domain planning without owning provider execution."""

    def __init__(
        self,
        shot_graph: K2ShotGraphService,
        evidence: EpisodeProductionEvidenceRepository,
        candidate_evidence: RealImageCandidateEvidencePort | None = None,
        video_candidate_evidence: RealVideoCandidateEvidencePort | None = None,
        candidate_review: K2MediaCandidateReviewService | None = None,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.shot_graph = shot_graph
        self.evidence = evidence
        self.candidate_evidence = (
            candidate_evidence or RejectingRealImageCandidateEvidence()
        )
        self.video_candidate_evidence = (
            video_candidate_evidence or RejectingRealVideoCandidateEvidence()
        )
        self.candidate_review = candidate_review or K2MediaCandidateReviewService(
            shot_graph.root_service,
            evidence,
            clock=clock,
        )
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _verified_qc(
        evidence: EpisodeProductionEvidenceRepository,
        workspace: str,
        run_ref: str,
    ) -> dict[str, Any]:
        gate = evidence.get_gate(workspace, run_ref, QC_GATE)
        if gate is None:
            raise UpstreamNotReadyError("G6 machine QC is required before M10")
        qc = _fact(gate, "QCReport")
        if (
            qc.get("result") != "PASS"
            or qc.get("machineVerified") is not True
            or qc.get("approvalStatus") != "UNAPPROVED"
            or qc.get("publicationAllowed") is not False
        ):
            raise StaleInputError("G6 QC evidence is not a valid M10 parent")
        return qc

    @staticmethod
    def _identity_inputs(
        shot: Mapping[str, Any], identity_lock: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        identities = identity_lock.get("identities")
        if not isinstance(identities, list) or not all(
            isinstance(item, Mapping) for item in identities
        ):
            raise StaleInputError("G2 identity lock entries are unavailable")
        by_character = {item.get("characterRef"): item for item in identities}
        if len(by_character) != len(identities) or None in by_character:
            raise StaleInputError("G2 identity lock entries are ambiguous")
        required = shot.get("requiredCharacterIdentityLocks")
        if not isinstance(required, list) or not required:
            raise StaleInputError("G3 shot has no identity lineage")
        result: list[dict[str, Any]] = []
        for binding in required:
            if not isinstance(binding, Mapping):
                raise StaleInputError("G3 shot identity binding is invalid")
            locked = by_character.get(binding.get("characterRef"))
            reference = locked.get("reference") if isinstance(locked, Mapping) else None
            if not isinstance(reference, Mapping):
                raise StaleInputError("G2 identity reference is unavailable")
            if (
                reference.get("mediaType") not in {"image", "identity-direction"}
                or binding.get("identityLockRef")
                != identity_lock.get("identityLockRef")
                or binding.get("identityLockVersionRef")
                != identity_lock.get("identityLockVersionRef")
                or binding.get("referenceVersionRef")
                != reference.get("referenceVersionRef")
                or binding.get("referenceDigest") != reference.get("contentDigest")
            ):
                raise StaleInputError("G2/G3 identity image lineage is inconsistent")
            result.append(
                {
                    "scriptCharacterName": locked["scriptCharacterName"],
                    "characterRef": locked["characterRef"],
                    "identityLockRef": identity_lock["identityLockRef"],
                    "identityLockVersionRef": identity_lock[
                        "identityLockVersionRef"
                    ],
                    "identityLockDigest": identity_lock["payloadDigest"],
                    "referenceRef": reference["referenceRef"],
                    "referenceVersionRef": reference["referenceVersionRef"],
                    "referenceContentDigest": reference["contentDigest"],
                    "referenceMediaType": reference["mediaType"],
                }
            )
        if len({item["characterRef"] for item in result}) != len(result):
            raise StaleInputError("G3 shot repeats an identity binding")
        return result

    def _build_requests(
        self,
        *,
        verified: Mapping[str, Any],
        qc: Mapping[str, Any],
        created_at: str,
    ) -> list[dict[str, Any]]:
        root = verified["root"]
        identity_lock = verified["identityLock"]
        graph = verified["executableShotGraph"]
        shots = verified["creativeShotVersions"]
        if len(shots) != 4 or graph.get("output", {}).get("totalFrames") != 720:
            raise StaleInputError("M10 is exact-scoped to the current four-shot K2 run")
        requests = []
        for shot in shots:
            identity_inputs = self._identity_inputs(shot, identity_lock)
            # The current K2 screenplay puts both locked characters in every
            # shot.  Record all references; do not collapse them to one image.
            if len(identity_inputs) != 2:
                raise StaleInputError(
                    "M10 requires both current K2 identity images for every shot"
                )
            request = _sealed(
                {
                    "schemaVersion": REAL_IMAGE_REQUEST_SCHEMA_VERSION,
                    "workspaceRef": root["workspaceRef"],
                    "productionRunRef": root["productionRunRef"],
                    "generationRequestRef": _required_ref(
                        self._ref_factory("real-image-generation-request"),
                        "generationRequestRef",
                    ),
                    "generationRequestVersionRef": _required_ref(
                        self._ref_factory("real-image-generation-request-version"),
                        "generationRequestVersionRef",
                    ),
                    "version": 1,
                    "ordinal": shot["globalOrder"],
                    "mediaKind": "image",
                    "mediaType": "image/png",
                    "creativeShotRef": shot["creativeShotRef"],
                    "creativeShotVersionRef": shot["creativeShotVersionRef"],
                    "creativeShotDigest": shot["payloadDigest"],
                    "executableShotGraphVersionRef": graph[
                        "executableShotGraphVersionRef"
                    ],
                    "executableShotGraphDigest": graph["payloadDigest"],
                    "identityLockRef": identity_lock["identityLockRef"],
                    "identityLockVersionRef": identity_lock[
                        "identityLockVersionRef"
                    ],
                    "identityLockDigest": identity_lock["payloadDigest"],
                    "identityInputs": identity_inputs,
                    "promptSpec": {
                        "cameraInstruction": deepcopy(
                            shot["cameraInstruction"]
                        ),
                        "action": shot["action"],
                        "continuityConstraints": deepcopy(
                            shot["continuityConstraints"]
                        ),
                    },
                    "parameters": {
                        "width": graph["output"]["width"],
                        "height": graph["output"]["height"],
                        "imageCount": 1,
                        "format": "png",
                    },
                    "adapterCapability": REAL_IMAGE_CAPABILITY,
                    "capabilityVerificationState": "PENDING_LIVE_PREFLIGHT",
                    "executionAuthorizationState": "NOT_GRANTED_BY_PLAN",
                    "requestedProvenance": "SELF_HOSTED_AI_GENERATED",
                    "rightsState": "NOT_REQUIRED_INTERNAL",
                    "providerPolicyState": "NOT_REQUIRED_SELF_HOSTED",
                    "budgetAuthorityState": "NOT_REQUIRED_INTERNAL",
                    "selectionRequired": True,
                    "publicationAllowed": False,
                    "sourceQcReportRef": qc["qcReportRef"],
                    "sourceQcReportDigest": qc["payloadDigest"],
                    "createdBy": REAL_IMAGE_PLANNER_ID,
                    "createdAt": created_at,
                }
            )
            requests.append(request)
        return requests

    def plan_images(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
        }:
            raise EpisodeProductionError("command fields do not match the M10 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        client_key = _idempotency_key(command.get("idempotencyKey"))
        verified = self.shot_graph.verify_shot_graph_current(workspace, run_ref)
        root = verified["root"]
        qc = self._verified_qc(self.evidence, workspace, run_ref)
        gate_key = _digest(
            {"clientIdempotencyKey": client_key, "stage": "m10-real-image-plan"}
        )
        existing = self.evidence.get_gate(workspace, run_ref, REAL_IMAGE_PLAN_GATE)
        if existing is not None:
            if existing.get("idempotencyKey") != gate_key:
                raise IdempotencyConflictError("M10 image plan command conflicts")
            bundle = self._bundle(existing)
            plan = bundle["realImagePlan"]
            if (
                plan.get("rootPayloadDigest") != root["payloadDigest"]
                or plan.get("identityLockDigest")
                != verified["identityLock"]["payloadDigest"]
                or plan.get("executableShotGraphDigest")
                != verified["executableShotGraph"]["payloadDigest"]
                or plan.get("sourceQcReportDigest") != qc["payloadDigest"]
                or plan.get("generationRequestDigests")
                != [
                    item["payloadDigest"]
                    for item in bundle["generationRequests"]
                ]
            ):
                raise StaleInputError("recorded M10 image plan lineage is stale")
            return {**bundle, "idempotentReplay": True}
        now = self._clock()
        requests = self._build_requests(verified=verified, qc=qc, created_at=now)
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "rootPayloadDigest": root["payloadDigest"],
                "identityLockDigest": verified["identityLock"]["payloadDigest"],
                "shotGraphDigest": verified["executableShotGraph"]["payloadDigest"],
                "sourceQcReportDigest": qc["payloadDigest"],
                "imageRequestDigests": [item["payloadDigest"] for item in requests],
                "plannerId": REAL_IMAGE_PLANNER_ID,
            }
        )
        plan = _sealed(
            {
                "schemaVersion": REAL_IMAGE_PLAN_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realImagePlanRef": _required_ref(
                    self._ref_factory("real-image-plan"), "realImagePlanRef"
                ),
                "realImagePlanVersionRef": _required_ref(
                    self._ref_factory("real-image-plan-version"),
                    "realImagePlanVersionRef",
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "identityLockRef": verified["identityLock"]["identityLockRef"],
                "identityLockVersionRef": verified["identityLock"][
                    "identityLockVersionRef"
                ],
                "identityLockDigest": verified["identityLock"]["payloadDigest"],
                "executableShotGraphVersionRef": verified[
                    "executableShotGraph"
                ]["executableShotGraphVersionRef"],
                "executableShotGraphDigest": verified[
                    "executableShotGraph"
                ]["payloadDigest"],
                "sourceQcReportRef": qc["qcReportRef"],
                "sourceQcReportDigest": qc["payloadDigest"],
                "generationRequestRefs": [
                    item["generationRequestRef"] for item in requests
                ],
                "generationRequestDigests": [
                    item["payloadDigest"] for item in requests
                ],
                "expectedRequestCount": 4,
                "requiredIdentityInputsPerRequest": 2,
                "capabilityVerificationState": "PENDING_LIVE_PREFLIGHT",
                "candidateSelectionState": "NOT_STARTED",
                "assetAdmissionState": "NOT_STARTED",
                "publicationAllowed": False,
                "createdBy": REAL_IMAGE_PLANNER_ID,
                "createdAt": now,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"RealImageGenerationRequest:{item['ordinal']:04d}",
                item["generationRequestRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in requests
        )
        try:
            gate, replay = self.evidence.append_gate(
                GateAppend(
                    workspace,
                    run_ref,
                    REAL_IMAGE_PLAN_GATE,
                    gate_key,
                    root["payloadDigest"],
                    request_digest,
                    "QC_READY",
                    "REAL_IMAGE_PLAN_READY",
                    now,
                    (
                        EvidenceFact(
                            "RealImagePlan",
                            plan["realImagePlanRef"],
                            1,
                            plan,
                            plan["payloadDigest"],
                        ),
                        *facts,
                    ),
                )
            )
        except IdempotencyConflictError:
            # Concurrent exact planners may create different ephemeral refs
            # before either observes the gate.  The committed gate is the
            # canonical winner when its operation key and immutable inputs are
            # identical; generated loser refs are not an idempotency conflict.
            winner = self.evidence.get_gate(
                workspace, run_ref, REAL_IMAGE_PLAN_GATE
            )
            if winner is None or winner.get("idempotencyKey") != gate_key:
                raise
            winner_bundle = self._bundle(winner)
            winner_plan = winner_bundle["realImagePlan"]
            if (
                winner_plan.get("rootPayloadDigest") != root["payloadDigest"]
                or winner_plan.get("identityLockDigest")
                != verified["identityLock"]["payloadDigest"]
                or winner_plan.get("executableShotGraphDigest")
                != verified["executableShotGraph"]["payloadDigest"]
                or winner_plan.get("sourceQcReportDigest")
                != qc["payloadDigest"]
            ):
                raise StaleInputError(
                    "concurrent M10 image plan lineage changed"
                )
            return {**winner_bundle, "idempotentReplay": True}
        return {**self._bundle(gate), "idempotentReplay": replay}

    def _verified_plan(
        self, workspace: str, run_ref: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        verified = self.shot_graph.verify_shot_graph_current(workspace, run_ref)
        qc = self._verified_qc(self.evidence, workspace, run_ref)
        gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_PLAN_GATE
        )
        if gate is None:
            raise UpstreamNotReadyError("M10 real image plan is not ready")
        bundle = self._bundle(gate)
        plan = bundle["realImagePlan"]
        requests = bundle["generationRequests"]
        if (
            plan.get("rootPayloadDigest") != verified["root"]["payloadDigest"]
            or plan.get("identityLockDigest")
            != verified["identityLock"]["payloadDigest"]
            or plan.get("executableShotGraphDigest")
            != verified["executableShotGraph"]["payloadDigest"]
            or plan.get("sourceQcReportDigest") != qc["payloadDigest"]
            or plan.get("generationRequestDigests")
            != [item["payloadDigest"] for item in requests]
            or plan.get("expectedRequestCount") != 4
            or len(requests) != 4
            or plan.get("publicationAllowed") is not False
        ):
            raise StaleInputError("recorded M10 image plan lineage is stale")
        return verified, bundle

    @staticmethod
    def _selection_items(value: object) -> list[dict[str, str]]:
        if not isinstance(value, list) or len(value) != 4:
            raise EpisodeProductionError(
                "exactly four M10 image selections are required"
            )
        result: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, Mapping) or set(item) != {
                "generationRequestRef",
                "candidateRef",
                "candidateContentDigest",
            }:
                raise EpisodeProductionError(
                    "selection fields do not match the M10 contract"
                )
            result.append(
                {
                    "generationRequestRef": _required_ref(
                        item.get("generationRequestRef"),
                        "generationRequestRef",
                    ),
                    "candidateRef": _required_ref(
                        item.get("candidateRef"), "candidateRef"
                    ),
                    "candidateContentDigest": _content_digest(
                        item.get("candidateContentDigest"),
                        "candidateContentDigest",
                    ),
                }
            )
        request_refs = [item["generationRequestRef"] for item in result]
        candidate_refs = [item["candidateRef"] for item in result]
        if (
            len(set(request_refs)) != 4
            or len(set(candidate_refs)) != 4
        ):
            raise EpisodeProductionError("M10 image selections are ambiguous")
        return sorted(result, key=lambda item: item["generationRequestRef"])

    def record_real_image_candidates(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Bridge exact V4 M10 bytes into Candidate + TechnicalValidation."""

        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
        }:
            raise EpisodeProductionError(
                "command fields do not match the M10 candidate handoff contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        self.shot_graph.root_service.get_run(workspace, run_ref)
        plan_gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_PLAN_GATE
        )
        if plan_gate is None:
            raise UpstreamNotReadyError("M10 real image plan is not ready")
        plan_bundle = self._bundle(plan_gate)
        plan = plan_bundle["realImagePlan"]
        requests = plan_bundle["generationRequests"]
        try:
            handoff = self.candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                plan["realImagePlanRef"],
                requests,
            )
        except RealImageCandidateEvidenceError as exc:
            raise RealImageCandidateRejectedError(
                "V4 rejected the M10 image candidate evidence"
            ) from exc
        raw_candidates = (
            handoff.get("candidates") if isinstance(handoff, Mapping) else None
        )
        if (
            not isinstance(handoff, Mapping)
            or handoff.get("publicationAllowed") is not False
            or not isinstance(raw_candidates, list)
            or len(raw_candidates) != 4
            or not all(isinstance(item, Mapping) for item in raw_candidates)
        ):
            raise RealImageCandidateRejectedError(
                "V4 returned an incomplete M10 candidate handoff"
            )
        requests_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        candidates_by_request = {
            item.get("generationRequestRef"): item for item in raw_candidates
        }
        if (
            len(candidates_by_request) != 4
            or set(candidates_by_request) != set(requests_by_ref)
        ):
            raise RealImageCandidateRejectedError(
                "M10 candidate handoff does not match the current requests"
            )
        existing_image_candidates: dict[str, dict[str, Any]] = {}
        for record in self.evidence.list_records(
            workspace, run_ref, record_kind=CANDIDATE
        ):
            payload = record.get("payload")
            if (
                isinstance(payload, Mapping)
                and payload.get("mediaKind") == "IMAGE"
            ):
                source_ref = payload.get("sourceCandidateRef") or payload.get(
                    "candidateRef"
                )
                if isinstance(source_ref, str):
                    existing_image_candidates[source_ref] = deepcopy(
                        dict(payload)
                    )
        exact_existing = bool(existing_image_candidates) and all(
            isinstance(existing_image_candidates.get(raw.get("candidateRef")), Mapping)
            and existing_image_candidates[raw.get("candidateRef")].get(
                "artifactDigest"
            )
            == (
                raw.get("artifact", {}).get("sha256")
                if isinstance(raw.get("artifact"), Mapping)
                else None
            )
            and existing_image_candidates[raw.get("candidateRef")].get(
                "sourceRequestDigest"
            )
            == raw.get("generationRequestDigest")
            for raw in raw_candidates
        )
        if exact_existing:
            revision_refs = {
                existing_image_candidates[raw.get("candidateRef")].get(
                    "revisionRef"
                )
                for raw in raw_candidates
            }
            if len(revision_refs) != 1:
                raise StaleInputError(
                    "M10 candidate handoff revision is ambiguous"
                )
            candidate_revision_ref = next(iter(revision_refs))
        elif not existing_image_candidates:
            candidate_revision_ref = plan["realImagePlanRef"]
        else:
            candidate_revision_ref = (
                "m10-image-revision-"
                + _digest(
                    {
                        "realImagePlanDigest": plan["payloadDigest"],
                        "candidateEvidenceDigest": handoff.get(
                            "candidateEvidenceDigest"
                        ),
                        "candidates": [
                            {
                                "candidateRef": raw.get("candidateRef"),
                                "generationRequestDigest": raw.get(
                                    "generationRequestDigest"
                                ),
                                "artifactDigest": (
                                    raw.get("artifact", {}).get("sha256")
                                    if isinstance(raw.get("artifact"), Mapping)
                                    else None
                                ),
                            }
                            for raw in sorted(
                                raw_candidates,
                                key=lambda value: value.get("ordinal", 0),
                            )
                        ],
                    }
                )[:32]
            )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        prepared: list[EvidenceRecord] = []
        for request in requests:
            raw = candidates_by_request[request["generationRequestRef"]]
            artifact = raw.get("artifact")
            if not isinstance(artifact, Mapping):
                raise RealImageCandidateRejectedError(
                    "M10 candidate artifact metadata is missing"
                )
            source_candidate_ref = _required_ref(
                raw.get("candidateRef"), "candidateRef"
            )
            artifact_digest = _content_digest(
                artifact.get("sha256"), "candidate artifact digest"
            )
            if (
                raw.get("ordinal") != request["ordinal"]
                or raw.get("generationRequestDigest") != request["payloadDigest"]
                or raw.get("creativeShotVersionRef")
                != request["creativeShotVersionRef"]
                or raw.get("state") != "TECHNICALLY_VERIFIED"
                or raw.get("provenance") != "SELF_HOSTED_AI_GENERATED"
                or raw.get("gpuUsed") is not True
                or raw.get("publicationAllowed") is not False
                or artifact.get("mediaType") != "image/png"
                or artifact.get("width") != request["parameters"]["width"]
                or artifact.get("height") != request["parameters"]["height"]
                or not isinstance(artifact.get("byteSize"), int)
                or artifact["byteSize"] <= 0
                or not isinstance(artifact.get("storageKey"), str)
                or not artifact["storageKey"]
            ):
                raise RealImageCandidateRejectedError(
                    "M10 candidate failed lineage verification"
                )
            candidate_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m10-candidate",
                    # Batch membership keys are derived only from immutable
                    # operation inputs.  Provider-owned candidate identity and
                    # bytes belong in the request digest, never in the key.
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "ordinal": request["ordinal"],
                }
            )[:48]
            candidate_ref = source_candidate_ref
            if exact_existing:
                candidate_ref = existing_image_candidates[
                    source_candidate_ref
                ]["candidateRef"]
            elif existing_image_candidates:
                candidate_ref = (
                    "m10-image-candidate-"
                    + _digest(
                        {
                            "revisionRef": candidate_revision_ref,
                            "sourceCandidateRef": source_candidate_ref,
                            "artifactDigest": artifact_digest,
                        }
                    )[:32]
                )
            candidate_record = self.candidate_review.prepare_candidate_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    # The first canonical record reserves the public operation
                    # key for the complete eight-record handoff batch.  Any
                    # changed member then produces either a changed first
                    # request digest or a forbidden partial replay.
                    "idempotencyKey": (
                        client_key
                        if request["ordinal"] == 1
                        else f"m10-candidate-{candidate_key}"
                    ),
                    "candidateRef": candidate_ref,
                    "candidateVersion": 1,
                    "revisionRef": candidate_revision_ref,
                    "mediaKind": "IMAGE",
                    "slotRef": request["creativeShotVersionRef"],
                    "sourceRequestRef": request["generationRequestRef"],
                    "sourceRequestDigest": request["payloadDigest"],
                    "artifactRef": f"v4-image-artifact:{artifact_digest[:32]}",
                    "artifactDigest": artifact_digest,
                    "artifactByteSize": artifact["byteSize"],
                    "sourceAssetVersions": [],
                    "storageKey": artifact["storageKey"],
                    "sourceCandidateRef": source_candidate_ref,
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                }
            )
            validation_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m10-technical-validation",
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "ordinal": request["ordinal"],
                }
            )[:48]
            validation_record = (
                self.candidate_review.prepare_technical_validation_record(
                    {
                        "workspaceRef": workspace,
                        "productionRunRef": run_ref,
                        "idempotencyKey": f"m10-technical-{validation_key}",
                        "candidateRef": candidate_ref,
                        "candidateVersion": 1,
                        "candidateDigest": candidate_record.payloadDigest,
                        "technicalValidationRef": (
                            f"m10-technical-validation-{candidate_ref}"
                        ),
                        "technicalValidationVersion": 1,
                        "validatorRef": "v4-m10-independent-verifier-v1",
                        "checks": [
                            {"check": "request-digest", "passed": True},
                            {"check": "artifact-sha256", "passed": True},
                            {"check": "image-dimensions", "passed": True},
                            {"check": "workflow-digest", "passed": True},
                        ],
                        "result": "PASS",
                    },
                    candidate_record=candidate_record,
                )
            )
            prepared.extend((candidate_record, validation_record))
        stored, replayed = self.evidence.append_records(
            prepared,
            expected_record_journal_head=expected_record_journal_head,
        )
        lifecycle = self.candidate_review.get_projection(workspace, run_ref)
        projection_service = getattr(self, "state_projection", None)
        if projection_service is not None:
            lifecycle = projection_service.get_projection(
                workspace, run_ref
            )["candidateLifecycle"]
        return {
            "state": self.evidence.current_state(workspace, run_ref),
            "candidates": [
                deepcopy(dict(item["payload"]))
                for item in stored
                if item.get("recordKind") == CANDIDATE
            ],
            "technicalValidations": [
                deepcopy(dict(item["payload"]))
                for item in stored
                if item.get("recordKind") == TECHNICAL_VALIDATION
            ],
            "candidateLifecycle": lifecycle,
            "idempotentReplay": replayed,
            "publicationAllowed": False,
        }

    def admit_real_images(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Atomically select and admit four PASS M10 image candidates."""

        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "selections",
        }:
            raise EpisodeProductionError(
                "command fields do not match the unified M10 admission contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        raw_selections = command.get("selections")
        if (
            not isinstance(raw_selections, list)
            or len(raw_selections) != 4
            or not all(isinstance(item, Mapping) for item in raw_selections)
        ):
            raise EpisodeProductionError("M10 requires four exact selections")
        fields = {
            "visualQcRef",
            "visualQcVersion",
            "visualQcDigest",
            "selectionRef",
            "selectionVersion",
            "approvalRef",
        }
        selections: list[dict[str, Any]] = []
        for item in raw_selections:
            if set(item) != fields:
                raise EpisodeProductionError(
                    "M10 selection fields do not match the contract"
                )
            qc_version = item.get("visualQcVersion")
            selection_version = item.get("selectionVersion")
            if (
                isinstance(qc_version, bool)
                or not isinstance(qc_version, int)
                or qc_version < 1
                or isinstance(selection_version, bool)
                or not isinstance(selection_version, int)
                or selection_version < 1
            ):
                raise EpisodeProductionError("M10 selection version is invalid")
            selections.append(
                {
                    "visualQcRef": _required_ref(
                        item.get("visualQcRef"), "visualQcRef"
                    ),
                    "visualQcVersion": qc_version,
                    "visualQcDigest": _content_digest(
                        item.get("visualQcDigest"), "visualQcDigest"
                    ),
                    "selectionRef": _required_ref(
                        item.get("selectionRef"), "selectionRef"
                    ),
                    "selectionVersion": selection_version,
                    "approvalRef": _required_ref(
                        item.get("approvalRef"), "approvalRef"
                    ),
                }
            )
        if len({item["selectionRef"] for item in selections}) != 4:
            raise EpisodeProductionError("M10 selection refs are ambiguous")
        selection_request_digest = _digest(
            {
                "selections": sorted(
                    selections, key=lambda item: item["selectionRef"]
                )
            }
        )
        plan_gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_PLAN_GATE
        )
        if plan_gate is None:
            raise UpstreamNotReadyError("M10 real image plan is not ready")
        plan_bundle = self._bundle(plan_gate)
        plan = plan_bundle["realImagePlan"]
        requests = plan_bundle["generationRequests"]
        gate_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "m10-unified-image-admission",
            }
        )
        existing = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
        )
        if existing is not None:
            manifest = _fact(existing, "RealImageAdmissionManifest")
            if (
                existing.get("idempotencyKey") != gate_key
                or manifest.get("selectionRequestDigest")
                != selection_request_digest
            ):
                raise IdempotencyConflictError(
                    "M10 image admission command conflicts"
                )
            return {**self._admission_bundle(existing), "idempotentReplay": True}
        if self.evidence.current_state(workspace, run_ref) != "REAL_IMAGE_PLAN_READY":
            raise StaleInputError("M10 admission state changed")
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        candidate_projection = self.candidate_review.get_projection(
            workspace, run_ref
        )
        active_candidate_revision_ref = candidate_projection.get(
            "latestCandidateRevisionRefs", {}
        ).get("IMAGE")
        if not isinstance(active_candidate_revision_ref, str):
            raise StaleInputError("M10 current image candidate revision is missing")
        requests_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        prepared: list[
            tuple[int, EvidenceRecord, dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = []
        now = self._clock()
        for item in selections:
            selection_key = _digest(
                {
                    "gateKey": gate_key,
                    "selectionRef": item["selectionRef"],
                    "selectionRequestDigest": selection_request_digest,
                }
            )[:48]
            record = self.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": f"m10-selected-{selection_key}",
                    **item,
                    "decision": "SELECTED",
                }
            )
            selection = deepcopy(dict(record.payload))
            candidate_record = self.evidence.get_record(
                workspace,
                run_ref,
                selection["candidateRef"],
                selection["candidateVersion"],
            )
            if (
                candidate_record is None
                or candidate_record.get("recordKind") != CANDIDATE
                or candidate_record.get("payloadDigest")
                != selection["candidateDigest"]
                or not isinstance(candidate_record.get("payload"), Mapping)
            ):
                raise StaleInputError("M10 selected candidate changed")
            candidate = deepcopy(dict(candidate_record["payload"]))
            request = requests_by_ref.get(candidate.get("sourceRequestRef"))
            if (
                not isinstance(request, Mapping)
                or candidate.get("mediaKind") != "IMAGE"
                or candidate.get("revisionRef") != active_candidate_revision_ref
                or candidate.get("slotRef")
                != request.get("creativeShotVersionRef")
                or candidate.get("sourceRequestDigest")
                != request.get("payloadDigest")
                or candidate.get("sourceAssetVersions") != []
                or candidate.get("artifactDigest")
                != selection.get("artifactDigest")
            ):
                raise StaleInputError("M10 candidate request lineage changed")
            ordinal = int(request["ordinal"])
            asset = _sealed(
                {
                    "schemaVersion": REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "assetRef": _required_ref(
                        self._ref_factory("real-image-asset"), "assetRef"
                    ),
                    "assetVersionRef": _required_ref(
                        self._ref_factory("real-image-asset-version"),
                        "assetVersionRef",
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "creativeShotRef": request["creativeShotRef"],
                    "creativeShotVersionRef": request[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": request["creativeShotDigest"],
                    "sourceCandidateRef": candidate["candidateRef"],
                    "sourceCandidateDigest": candidate["payloadDigest"],
                    "revisionRef": candidate["revisionRef"],
                    "sourceRuntimeCandidateRef": candidate.get(
                        "sourceCandidateRef", candidate["candidateRef"]
                    ),
                    "semanticVisualQcRef": selection["visualQcRef"],
                    "semanticVisualQcDigest": selection["visualQcDigest"],
                    "humanSelectionRef": record.recordRef,
                    "humanSelectionVersion": record.recordVersion,
                    "humanSelectionDigest": record.payloadDigest,
                    "mediaKind": "image",
                    "mediaType": "image/png",
                    "artifactRef": candidate["artifactRef"],
                    "storageKey": candidate.get("storageKey"),
                    "byteSize": candidate["artifactByteSize"],
                    "sha256": candidate["artifactDigest"],
                    "probe": {
                        "width": request["parameters"]["width"],
                        "height": request["parameters"]["height"],
                        "format": "png",
                    },
                    "provenance": candidate["provenance"],
                    "state": "REGISTERED",
                    "immutable": True,
                    "publicationAllowed": False,
                    "createdBy": "v5.k2.unified-image-admission.v1",
                    "createdAt": now,
                }
            )
            admission = _sealed(
                {
                    "schemaVersion": "v5.k2-asset-admission.v1",
                    "admissionRef": _required_ref(
                        self._ref_factory("real-image-admission"),
                        "admissionRef",
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
                    "selectionRef": record.recordRef,
                    "selectionVersion": record.recordVersion,
                    "selectionDigest": record.payloadDigest,
                    "assetVersionRef": asset["assetVersionRef"],
                    "assetVersionDigest": asset["payloadDigest"],
                    "admissionState": "ADMITTED",
                    "publicationAllowed": False,
                    "createdAt": now,
                }
            )
            prepared.append((ordinal, record, candidate, admission, asset))
        prepared.sort(key=lambda value: value[0])
        if (
            [value[0] for value in prepared] != [1, 2, 3, 4]
            or len({value[2]["candidateRef"] for value in prepared}) != 4
            or len(
                {
                    value[1].payload["authorityDecisionRef"]
                    for value in prepared
                }
            )
            != 4
            or len(
                {
                    value[1].payload["authorityDecisionDigest"]
                    for value in prepared
                }
            )
            != 4
        ):
            raise RealImageCandidateRejectedError(
                "M10 admission does not cover four unique timeline slots"
            )

        # Rehash/re-probe at the consumption boundary, after authority checks.
        try:
            live = self.candidate_evidence.resolve_candidates(
                workspace, run_ref, plan["realImagePlanRef"], requests
            )
        except RealImageCandidateEvidenceError as exc:
            raise RealImageCandidateRejectedError(
                "M10 selected artifact bytes are no longer verifiable"
            ) from exc
        live_items = live.get("candidates") if isinstance(live, Mapping) else None
        if not isinstance(live_items, list) or len(live_items) != 4:
            raise RealImageCandidateRejectedError(
                "M10 admission handoff is incomplete"
            )
        live_by_ref = {
            value.get("candidateRef"): value
            for value in live_items
            if isinstance(value, Mapping)
        }
        for _, _, candidate, _, asset in prepared:
            live_candidate = live_by_ref.get(
                asset.get("sourceRuntimeCandidateRef", candidate["candidateRef"])
            )
            artifact = (
                live_candidate.get("artifact")
                if isinstance(live_candidate, Mapping)
                else None
            )
            if (
                not isinstance(artifact, Mapping)
                or artifact.get("sha256") != asset["sha256"]
                or artifact.get("byteSize") != asset["byteSize"]
                or artifact.get("storageKey") != asset.get("storageKey")
                or live_candidate.get("generationRequestDigest")
                != asset["generationRequestDigest"]
                or live_candidate.get("creativeShotVersionRef")
                != asset["creativeShotVersionRef"]
            ):
                raise RealImageCandidateRejectedError(
                    "M10 selected artifact bytes or lineage changed"
                )
        selections_records = [value[1] for value in prepared]
        admissions = [value[3] for value in prepared]
        assets = [value[4] for value in prepared]
        manifest = _sealed(
            {
                "schemaVersion": (
                    REAL_IMAGE_UNIFIED_ADMISSION_MANIFEST_SCHEMA_VERSION
                ),
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realImageAdmissionManifestRef": _required_ref(
                    self._ref_factory("real-image-admission-manifest"),
                    "realImageAdmissionManifestRef",
                ),
                "version": 2,
                "rootPayloadDigest": plan_gate["rootPayloadDigest"],
                "realImagePlanRef": plan["realImagePlanRef"],
                "realImagePlanDigest": plan["payloadDigest"],
                "revisionRef": active_candidate_revision_ref,
                "selectionRequestDigest": selection_request_digest,
                "selectionRefs": [item.recordRef for item in selections_records],
                "selectionVersions": [
                    item.recordVersion for item in selections_records
                ],
                "selectionDigests": [
                    item.payloadDigest for item in selections_records
                ],
                "assetVersionRefs": [item["assetVersionRef"] for item in assets],
                "assetVersionDigests": [item["payloadDigest"] for item in assets],
                "admittedCount": 4,
                "state": "REAL_IMAGE_READY",
                "publicationAllowed": False,
                "createdAt": now,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"AssetAdmission:M10:{item['ordinal']:04d}",
                item["admissionRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in admissions
        ) + tuple(
            EvidenceFact(
                f"AssetVersion:M10:{item['ordinal']:04d}",
                item["assetVersionRef"],
                item["version"],
                item,
                item["payloadDigest"],
            )
            for item in assets
        ) + (
            EvidenceFact(
                "RealImageAdmissionManifest",
                manifest["realImageAdmissionManifestRef"],
                manifest["version"],
                manifest,
                manifest["payloadDigest"],
            ),
        )
        admission_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_ADMISSION,
                record_ref=item["admissionRef"],
                record_version=1,
                idempotency_key=(
                    "m10-admission-"
                    + _digest(
                        {"gateKey": gate_key, "admissionRef": item["admissionRef"]}
                    )[:48]
                ),
                created_at=now,
                payload=item,
            )
            for item in admissions
        ]
        asset_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_VERSION,
                record_ref=item["assetVersionRef"],
                record_version=item["version"],
                idempotency_key=(
                    "m10-asset-version-"
                    + _digest(
                        {
                            "gateKey": gate_key,
                            "assetVersionRef": item["assetVersionRef"],
                        }
                    )[:48]
                ),
                created_at=now,
                payload=item,
            )
            for item in assets
        ]
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "realImagePlanDigest": plan["payloadDigest"],
                "selectionDigests": [
                    item.payloadDigest for item in selections_records
                ],
                "assetVersionDigests": [item["payloadDigest"] for item in assets],
            }
        )
        gate_append = GateAppend(
            workspace,
            run_ref,
            REAL_IMAGE_ADMISSION_GATE,
            gate_key,
            plan_gate["rootPayloadDigest"],
            request_digest,
            "REAL_IMAGE_PLAN_READY",
            "REAL_IMAGE_READY",
            now,
            facts,
        )
        try:
            _, stored_gate, replayed = self.evidence.append_records_and_gate(
                (*selections_records, *admission_records, *asset_records),
                gate_append,
                expected_record_journal_head=expected_record_journal_head,
            )
        except IdempotencyConflictError:
            concurrent = self.evidence.get_gate(
                workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
            )
            if (
                concurrent is None
                or concurrent.get("idempotencyKey") != gate_key
                or _fact(concurrent, "RealImageAdmissionManifest").get(
                    "selectionRequestDigest"
                )
                != selection_request_digest
            ):
                raise
            stored_gate = concurrent
            replayed = True
        return {
            **self._admission_bundle(stored_gate),
            "idempotentReplay": replayed,
        }

    def select_and_admit_images(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Compatibility name for the unified, authority-backed M10 admission."""

        return self.admit_real_images(command)

    def admit_real_image_successor(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Atomically admit one post-M10 image successor without a state rewind."""

        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "selection",
        }:
            raise EpisodeProductionError(
                "command fields do not match the image successor contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        selection_input = command.get("selection")
        fields = {
            "visualQcRef",
            "visualQcVersion",
            "visualQcDigest",
            "selectionRef",
            "selectionVersion",
            "approvalRef",
        }
        if not isinstance(selection_input, Mapping) or set(selection_input) != fields:
            raise EpisodeProductionError(
                "image successor selection fields do not match the contract"
            )
        selection_command = {
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            # HumanSelectionDecision is the first durable fact of this
            # non-transitioning operation and therefore reserves the public
            # operation key without introducing a seventh record kind.
            "idempotencyKey": client_key,
            "visualQcRef": _required_ref(
                selection_input.get("visualQcRef"), "visualQcRef"
            ),
            "visualQcVersion": selection_input.get("visualQcVersion"),
            "visualQcDigest": _content_digest(
                selection_input.get("visualQcDigest"), "visualQcDigest"
            ),
            "selectionRef": _required_ref(
                selection_input.get("selectionRef"), "selectionRef"
            ),
            "selectionVersion": selection_input.get("selectionVersion"),
            "approvalRef": _required_ref(
                selection_input.get("approvalRef"), "approvalRef"
            ),
            "decision": "SELECTED",
        }
        for field in ("visualQcVersion", "selectionVersion"):
            value = selection_command[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise EpisodeProductionError(f"{field} is invalid")
        plan_gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_PLAN_GATE
        )
        admitted_gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
        )
        if plan_gate is None or admitted_gate is None:
            raise UpstreamNotReadyError(
                "an admitted M10 image baseline is required"
            )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        plan_bundle = self._bundle(plan_gate)
        plan = plan_bundle["realImagePlan"]
        requests = plan_bundle["generationRequests"]
        record = self.candidate_review.prepare_human_selection_record(
            selection_command
        )
        selection = deepcopy(dict(record.payload))
        existing_selection = self.evidence.get_record(
            workspace,
            run_ref,
            record.recordRef,
            record.recordVersion,
        )
        if existing_selection is not None:
            if (
                existing_selection.get("recordKind") != HUMAN_SELECTION
                or existing_selection.get("payloadDigest") != record.payloadDigest
            ):
                raise IdempotencyConflictError(
                    "image successor selection content changed"
                )
            admissions = [
                item
                for item in self.evidence.list_records(
                    workspace, run_ref, record_kind=ASSET_ADMISSION
                )
                if isinstance(item.get("payload"), Mapping)
                and item["payload"].get("selectionRef") == record.recordRef
                and item["payload"].get("selectionDigest")
                == record.payloadDigest
            ]
            if len(admissions) != 1:
                raise RepositoryUnavailableError(
                    "image successor replay is incomplete"
                )
            admission = deepcopy(dict(admissions[0]["payload"]))
            asset_record = self.evidence.get_record(
                workspace,
                run_ref,
                admission.get("assetVersionRef"),
                admission.get("assetVersionVersion"),
            )
            if (
                asset_record is None
                or asset_record.get("recordKind") != ASSET_VERSION
                or asset_record.get("payloadDigest")
                != admission.get("assetVersionDigest")
                or not isinstance(asset_record.get("payload"), Mapping)
            ):
                raise RepositoryUnavailableError(
                    "image successor replay AssetVersion is incomplete"
                )
            return {
                "state": self.evidence.current_state(workspace, run_ref),
                "humanSelection": deepcopy(dict(existing_selection["payload"])),
                "assetAdmission": admission,
                "assetVersion": deepcopy(dict(asset_record["payload"])),
                "idempotentReplay": True,
                "publicationAllowed": False,
            }
        candidate_record = self.evidence.get_record(
            workspace,
            run_ref,
            selection["candidateRef"],
            selection["candidateVersion"],
        )
        if (
            candidate_record is None
            or candidate_record.get("recordKind") != CANDIDATE
            or candidate_record.get("payloadDigest")
            != selection["candidateDigest"]
            or not isinstance(candidate_record.get("payload"), Mapping)
        ):
            raise StaleInputError("image successor candidate changed")
        candidate = deepcopy(dict(candidate_record["payload"]))
        requests_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        request = requests_by_ref.get(candidate.get("sourceRequestRef"))
        active_candidate_revision_ref = self.candidate_review.get_projection(
            workspace, run_ref
        ).get("latestCandidateRevisionRefs", {}).get("IMAGE")
        if (
            not isinstance(request, Mapping)
            or candidate.get("mediaKind") != "IMAGE"
            or candidate.get("revisionRef") != active_candidate_revision_ref
            or candidate.get("slotRef") != request.get("creativeShotVersionRef")
            or candidate.get("sourceRequestDigest")
            != request.get("payloadDigest")
            or candidate.get("artifactDigest")
            != selection.get("artifactDigest")
        ):
            raise StaleInputError("image successor lineage changed")
        predecessors = [
            item
            for item in self.candidate_review.asset_versions.list_asset_versions(
                workspace, run_ref
            )
            if str(item.get("mediaKind", "")).lower() == "image"
            and item.get("creativeShotVersionRef")
            == candidate.get("slotRef")
        ]
        if not predecessors:
            raise UpstreamNotReadyError(
                "image successor predecessor AssetVersion is unavailable"
            )
        predecessor = max(predecessors, key=lambda item: int(item.get("version", 0)))
        try:
            live = self.candidate_evidence.resolve_candidates(
                workspace, run_ref, plan["realImagePlanRef"], requests
            )
        except RealImageCandidateEvidenceError as exc:
            raise RealImageCandidateRejectedError(
                "image successor artifact bytes are no longer verifiable"
            ) from exc
        live_items = live.get("candidates") if isinstance(live, Mapping) else None
        live_candidate = next(
            (
                item
                for item in live_items or []
                if isinstance(item, Mapping)
                and item.get("candidateRef")
                == candidate.get("sourceCandidateRef", candidate["candidateRef"])
            ),
            None,
        )
        artifact = (
            live_candidate.get("artifact")
            if isinstance(live_candidate, Mapping)
            else None
        )
        if (
            not isinstance(artifact, Mapping)
            or artifact.get("sha256") != candidate["artifactDigest"]
            or artifact.get("byteSize") != candidate["artifactByteSize"]
            or artifact.get("storageKey") != candidate.get("storageKey")
        ):
            raise RealImageCandidateRejectedError(
                "image successor artifact bytes or lineage changed"
            )
        now = self._clock()
        asset = _sealed(
            {
                "schemaVersion": REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "assetRef": predecessor["assetRef"],
                "assetVersionRef": _required_ref(
                    self._ref_factory("real-image-asset-version"),
                    "assetVersionRef",
                ),
                "version": int(predecessor["version"]) + 1,
                "ordinal": request["ordinal"],
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestVersionRef": request[
                    "generationRequestVersionRef"
                ],
                "generationRequestDigest": request["payloadDigest"],
                "creativeShotRef": request["creativeShotRef"],
                "creativeShotVersionRef": request["creativeShotVersionRef"],
                "creativeShotDigest": request["creativeShotDigest"],
                "sourceCandidateRef": candidate["candidateRef"],
                "sourceCandidateDigest": candidate["payloadDigest"],
                "revisionRef": candidate["revisionRef"],
                "sourceRuntimeCandidateRef": candidate.get(
                    "sourceCandidateRef", candidate["candidateRef"]
                ),
                "semanticVisualQcRef": selection["visualQcRef"],
                "semanticVisualQcDigest": selection["visualQcDigest"],
                "humanSelectionRef": record.recordRef,
                "humanSelectionVersion": record.recordVersion,
                "humanSelectionDigest": record.payloadDigest,
                "supersedesAssetVersionRef": predecessor["assetVersionRef"],
                "supersedesAssetVersionDigest": predecessor["payloadDigest"],
                "mediaKind": "image",
                "mediaType": "image/png",
                "artifactRef": candidate["artifactRef"],
                "storageKey": candidate.get("storageKey"),
                "byteSize": candidate["artifactByteSize"],
                "sha256": candidate["artifactDigest"],
                "probe": {
                    "width": request["parameters"]["width"],
                    "height": request["parameters"]["height"],
                    "format": "png",
                },
                "provenance": candidate["provenance"],
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
                "createdBy": "v5.k2.image-successor-admission.v1",
                "createdAt": now,
            }
        )
        admission = _sealed(
            {
                "schemaVersion": "v5.k2-asset-admission.v1",
                "admissionRef": _required_ref(
                    self._ref_factory("real-image-successor-admission"),
                    "admissionRef",
                ),
                "version": 1,
                "ordinal": request["ordinal"],
                "candidateRef": candidate["candidateRef"],
                "candidateDigest": candidate["payloadDigest"],
                "selectionRef": record.recordRef,
                "selectionVersion": record.recordVersion,
                "selectionDigest": record.payloadDigest,
                "assetVersionRef": asset["assetVersionRef"],
                "assetVersionVersion": asset["version"],
                "assetVersionDigest": asset["payloadDigest"],
                "admissionState": "ADMITTED",
                "publicationAllowed": False,
                "createdAt": now,
            }
        )
        admission_record = _record(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            record_kind=ASSET_ADMISSION,
            record_ref=admission["admissionRef"],
            record_version=1,
            idempotency_key=(
                "m10-successor-admission-"
                + _digest(
                    {
                        "clientIdempotencyKey": client_key,
                        "selectionDigest": record.payloadDigest,
                    }
                )[:40]
            ),
            created_at=now,
            payload=admission,
        )
        asset_record = _record(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            record_kind=ASSET_VERSION,
            record_ref=asset["assetVersionRef"],
            record_version=asset["version"],
            idempotency_key=(
                "m10-successor-asset-"
                + _digest(
                    {
                        "clientIdempotencyKey": client_key,
                        "selectionDigest": record.payloadDigest,
                    }
                )[:40]
            ),
            created_at=now,
            payload=asset,
        )
        _, replayed = self.evidence.append_records(
            (record, admission_record, asset_record),
            expected_record_journal_head=expected_record_journal_head,
        )
        return {
            "state": self.evidence.current_state(workspace, run_ref),
            "humanSelection": selection,
            "assetAdmission": admission,
            "assetVersion": asset,
            "idempotentReplay": replayed,
            "publicationAllowed": False,
        }

    def _verified_image_admission(
        self, workspace: str, run_ref: str
    ) -> dict[str, Any]:
        verified, plan_bundle = self._verified_plan(workspace, run_ref)
        gate = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
        )
        if gate is None:
            raise UpstreamNotReadyError(
                "four exact M10 image selections are required before M11"
            )
        admission = self._admission_bundle(gate)
        manifest = admission["realImageAdmissionManifest"]
        plan = plan_bundle["realImagePlan"]
        requests = plan_bundle["generationRequests"]
        candidates = admission["candidates"]
        decisions = admission["selectionDecisions"]
        assets = admission["assetVersions"]
        if (
            manifest.get("schemaVersion")
            == REAL_IMAGE_UNIFIED_ADMISSION_MANIFEST_SCHEMA_VERSION
        ):
            asset_admissions = admission.get("assetAdmissions")
            if (
                manifest.get("rootPayloadDigest")
                != verified["root"]["payloadDigest"]
                or manifest.get("realImagePlanRef")
                != plan["realImagePlanRef"]
                or manifest.get("realImagePlanDigest")
                != plan["payloadDigest"]
                or manifest.get("selectionRefs")
                != [item["selectionRef"] for item in decisions]
                or manifest.get("selectionDigests")
                != [item["payloadDigest"] for item in decisions]
                or manifest.get("assetVersionRefs")
                != [item["assetVersionRef"] for item in assets]
                or manifest.get("assetVersionDigests")
                != [item["payloadDigest"] for item in assets]
                or manifest.get("admittedCount") != 4
                or manifest.get("state") != "REAL_IMAGE_READY"
                or manifest.get("publicationAllowed") is not False
                or not isinstance(asset_admissions, list)
                or len(candidates) != 4
                or len(decisions) != 4
                or len(asset_admissions) != 4
                or len(assets) != 4
            ):
                raise StaleInputError(
                    "unified M10 image admission manifest is stale"
                )
            request_by_ref = {
                item["generationRequestRef"]: item for item in requests
            }
            candidate_by_ref = {
                item["candidateRef"]: item for item in candidates
            }
            selection_by_ref = {
                item["selectionRef"]: item for item in decisions
            }
            admission_by_asset = {
                item["assetVersionRef"]: item for item in asset_admissions
            }
            for asset in assets:
                request = request_by_ref.get(asset.get("generationRequestRef"))
                candidate = candidate_by_ref.get(asset.get("sourceCandidateRef"))
                selection = selection_by_ref.get(asset.get("humanSelectionRef"))
                asset_admission = admission_by_asset.get(
                    asset.get("assetVersionRef")
                )
                if (
                    not isinstance(request, Mapping)
                    or not isinstance(candidate, Mapping)
                    or not isinstance(selection, Mapping)
                    or not isinstance(asset_admission, Mapping)
                    or asset.get("generationRequestDigest")
                    != request.get("payloadDigest")
                    or asset.get("creativeShotVersionRef")
                    != request.get("creativeShotVersionRef")
                    or asset.get("sourceCandidateDigest")
                    != candidate.get("payloadDigest")
                    or asset.get("humanSelectionDigest")
                    != selection.get("payloadDigest")
                    or selection.get("candidateDigest")
                    != candidate.get("payloadDigest")
                    or selection.get("decision") != "SELECTED"
                    or asset_admission.get("selectionDigest")
                    != selection.get("payloadDigest")
                    or asset_admission.get("assetVersionDigest")
                    != asset.get("payloadDigest")
                    or asset.get("mediaKind") != "image"
                    or asset.get("mediaType") != "image/png"
                    or asset.get("state") != "REGISTERED"
                    or asset.get("immutable") is not True
                    or asset.get("publicationAllowed") is not False
                ):
                    raise StaleInputError(
                        "unified M10 selected image lineage is stale"
                    )
            try:
                handoff = self.candidate_evidence.resolve_candidates(
                    workspace,
                    run_ref,
                    plan["realImagePlanRef"],
                    requests,
                )
            except RealImageCandidateEvidenceError as exc:
                raise RealImageCandidateRejectedError(
                    "V4 could not reverify admitted M10 image bytes"
                ) from exc
            live_items = (
                handoff.get("candidates")
                if isinstance(handoff, Mapping)
                else None
            )
            if not isinstance(live_items, list):
                raise RealImageCandidateRejectedError(
                    "V4 returned an invalid admitted-image handoff"
                )
            live_by_ref = {
                item.get("candidateRef"): item
                for item in live_items
                if isinstance(item, Mapping)
            }
            for asset in assets:
                live = live_by_ref.get(
                    asset.get(
                        "sourceRuntimeCandidateRef", asset["sourceCandidateRef"]
                    )
                )
                artifact = live.get("artifact") if isinstance(live, Mapping) else None
                if (
                    not isinstance(artifact, Mapping)
                    or artifact.get("storageKey") != asset.get("storageKey")
                    or artifact.get("sha256") != asset.get("sha256")
                    or artifact.get("byteSize") != asset.get("byteSize")
                ):
                    raise RealImageCandidateRejectedError(
                        "an admitted M10 image artifact is no longer current"
                    )
            return {**verified, **plan_bundle, **admission}
        if (
            manifest.get("rootPayloadDigest")
            != verified["root"]["payloadDigest"]
            or manifest.get("realImagePlanRef") != plan["realImagePlanRef"]
            or manifest.get("realImagePlanDigest") != plan["payloadDigest"]
            or manifest.get("candidateRefs")
            != [item["candidateRef"] for item in candidates]
            or manifest.get("candidateDigests")
            != [item["payloadDigest"] for item in candidates]
            or manifest.get("selectionDecisionRefs")
            != [item["selectionDecisionRef"] for item in decisions]
            or manifest.get("selectionDecisionDigests")
            != [item["payloadDigest"] for item in decisions]
            or manifest.get("assetVersionRefs")
            != [item["assetVersionRef"] for item in assets]
            or manifest.get("assetVersionDigests")
            != [item["payloadDigest"] for item in assets]
            or manifest.get("state") != "REAL_IMAGE_READY"
            or manifest.get("publicationAllowed") is not False
            or len(candidates) != 4
            or len(decisions) != 4
            or len(assets) != 4
        ):
            raise StaleInputError("M10 image admission manifest is stale")
        request_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        candidate_by_ref = {item["candidateRef"]: item for item in candidates}
        decision_by_ref = {
            item["selectionDecisionRef"]: item for item in decisions
        }
        if (
            len(request_by_ref) != 4
            or len(candidate_by_ref) != 4
            or len(decision_by_ref) != 4
        ):
            raise StaleInputError("M10 image admission lineage is ambiguous")
        for asset in assets:
            request = request_by_ref.get(asset.get("generationRequestRef"))
            candidate = candidate_by_ref.get(asset.get("candidateRef"))
            decision = decision_by_ref.get(asset.get("selectionDecisionRef"))
            if (
                not isinstance(request, Mapping)
                or not isinstance(candidate, Mapping)
                or not isinstance(decision, Mapping)
                or asset.get("generationRequestDigest")
                != request.get("payloadDigest")
                or asset.get("creativeShotVersionRef")
                != request.get("creativeShotVersionRef")
                or asset.get("candidateDigest")
                != candidate.get("payloadDigest")
                or asset.get("selectionDecisionDigest")
                != decision.get("payloadDigest")
                or decision.get("candidateDigest")
                != candidate.get("payloadDigest")
                or decision.get("decision") != "SELECT"
                or candidate.get("selectionState") != "SELECTED_BY_HUMAN"
                or candidate.get("admissionState") != "ADMITTED"
                or asset.get("mediaKind") != "image"
                or asset.get("mediaType") != "image/png"
                or asset.get("state") != "REGISTERED"
                or asset.get("immutable") is not True
                or asset.get("publicationAllowed") is not False
            ):
                raise StaleInputError("M10 selected image asset lineage is stale")
        try:
            handoff = self.candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                plan["realImagePlanRef"],
                requests,
            )
        except RealImageCandidateEvidenceError as exc:
            raise RealImageCandidateRejectedError(
                "V4 could not reverify the admitted M10 image bytes"
            ) from exc
        if not isinstance(handoff, Mapping) or not isinstance(
            handoff.get("candidates"), list
        ):
            raise RealImageCandidateRejectedError(
                "V4 returned an invalid admitted-image handoff"
            )
        live_by_ref = {
            item.get("candidateRef"): item
            for item in handoff["candidates"]
            if isinstance(item, Mapping)
        }
        for asset in assets:
            live = live_by_ref.get(asset["candidateRef"])
            artifact = live.get("artifact") if isinstance(live, Mapping) else None
            if (
                not isinstance(artifact, Mapping)
                or handoff.get("candidateEvidenceDigest")
                != manifest.get("candidateEvidenceDigest")
                or handoff.get("artifactStoreRef")
                != asset.get("artifactStoreRef")
                or artifact.get("storageKey") != asset.get("storageKey")
                or artifact.get("sha256") != asset.get("sha256")
                or artifact.get("byteSize") != asset.get("byteSize")
                or artifact.get("width") != asset.get("probe", {}).get("width")
                or artifact.get("height")
                != asset.get("probe", {}).get("height")
            ):
                raise RealImageCandidateRejectedError(
                    "an admitted M10 image artifact is no longer current"
                )
        return {
            **verified,
            **plan_bundle,
            **admission,
        }

    @staticmethod
    def _video_profile(
        graph: Mapping[str, Any],
        shot: Mapping[str, Any],
        asset: Mapping[str, Any],
    ) -> dict[str, Any]:
        output = graph.get("output")
        if not isinstance(output, Mapping):
            raise StaleInputError("shot graph output profile is unavailable")
        frame_rate = output.get("frameRate")
        duration = shot.get("durationFrames")
        if frame_rate != 24 or duration not in {168, 192}:
            raise StaleInputError("M11 shot timing is outside the exact K2 scope")
        width = 640
        source_width = int(output.get("width", 0))
        source_height = int(output.get("height", 0))
        if source_width <= 0 or source_height <= 0:
            raise StaleInputError("shot graph dimensions are invalid")
        height = max(
            32,
            int(round((width * source_height / source_width) / 32)) * 32,
        )
        return {
            "durationFrames": duration,
            "frameRate": frame_rate,
            "width": width,
            "height": height,
            "steps": 20,
            "cfg": 5.0,
            "samplerName": "uni_pc",
            "scheduler": "simple",
            "modelShift": 8.0,
            "seed": int(str(asset["sha256"])[:16], 16),
            "negativePrompt": (
                "text, watermark, logo, subtitles, malformed anatomy, "
                "duplicate subject, temporal flicker, abrupt camera jump"
            ),
        }

    def _current_image_assets_for_video(
        self,
        workspace: str,
        run_ref: str,
        baseline_assets: Sequence[Mapping[str, Any]],
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return one canonical latest image AssetVersion for every M11 slot."""

        canonical = [
            item
            for item in self.candidate_review.asset_versions.list_asset_versions(
                workspace,
                run_ref,
                records=records,
                gates=gates,
            )
            if str(item.get("mediaKind", "")).lower() == "image"
        ]
        result: list[dict[str, Any]] = []
        for baseline in baseline_assets:
            logical = [
                item
                for item in canonical
                if item.get("assetRef") == baseline.get("assetRef")
                and item.get("creativeShotVersionRef")
                == baseline.get("creativeShotVersionRef")
            ]
            if not logical:
                raise UpstreamNotReadyError(
                    "a canonical M10 image AssetVersion is unavailable"
                )
            latest_version = max(int(item.get("version", 0)) for item in logical)
            latest_matches = [
                item
                for item in logical
                if int(item.get("version", 0)) == latest_version
            ]
            if len(latest_matches) != 1:
                raise StaleInputError(
                    "canonical M10 image lineage has an ambiguous current version"
                )
            latest = latest_matches[0]
            if (
                latest.get("assetRef") != baseline.get("assetRef")
                or int(latest.get("version", 0)) < int(baseline.get("version", 0))
                or latest.get("state") != "REGISTERED"
                or latest.get("immutable") is not True
                or latest.get("publicationAllowed") is not False
            ):
                raise StaleInputError("canonical M10 image lineage is invalid")
            result.append(deepcopy(dict(latest)))
        result.sort(key=lambda item: int(item.get("ordinal", 0)))
        if (
            len(result) != 4
            or [item.get("ordinal") for item in result] != [1, 2, 3, 4]
            or len({item.get("creativeShotVersionRef") for item in result}) != 4
        ):
            raise StaleInputError(
                "canonical M10 image versions do not cover four exact slots"
            )
        return result

    @staticmethod
    def _assert_sealed_payload(value: Any, field: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise RepositoryUnavailableError(f"{field} is invalid")
        payload = deepcopy(dict(value))
        digest = payload.pop("payloadDigest", None)
        if not isinstance(digest, str) or digest != _digest(payload):
            raise RepositoryUnavailableError(f"{field} digest is invalid")
        payload["payloadDigest"] = digest
        return payload

    def _persisted_video_revision(
        self,
        workspace: str,
        run_ref: str,
        plan: Mapping[str, Any],
        baseline_requests: Sequence[Mapping[str, Any]],
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Read the latest server-sealed successor request set from Candidates."""

        baseline_by_slot = {
            item["creativeShotVersionRef"]: deepcopy(dict(item))
            for item in baseline_requests
        }
        if (
            len(baseline_by_slot) != 4
            or [item.get("ordinal") for item in baseline_requests]
            != [1, 2, 3, 4]
        ):
            raise RepositoryUnavailableError(
                "baseline M11 request coverage is invalid"
            )
        latest_revision: dict[str, Any] | None = None
        seen_revision_digests: set[str] = set()
        prior_requests = [deepcopy(dict(item)) for item in baseline_requests]
        candidate_records = (
            self.evidence.list_records(
                workspace, run_ref, record_kind=CANDIDATE
            )
            if records is None
            else [
                item for item in records if item.get("recordKind") == CANDIDATE
            ]
        )
        for record in candidate_records:
            payload = record.get("payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("mediaKind") != "VIDEO"
                or "consumedGenerationRequest" not in payload
                or "consumedRealVideoRevision" not in payload
            ):
                continue
            request = self._assert_sealed_payload(
                payload["consumedGenerationRequest"],
                "persisted successor video request",
            )
            revision = self._assert_sealed_payload(
                payload["consumedRealVideoRevision"],
                "persisted successor video revision",
            )
            requests = revision.get("generationRequests")
            if (
                revision.get("schemaVersion")
                != REAL_VIDEO_SUCCESSOR_REVISION_SCHEMA_VERSION
                or revision.get("workspaceRef") != workspace
                or revision.get("productionRunRef") != run_ref
                or revision.get("sourceRealVideoPlanRef")
                != plan.get("realVideoPlanRef")
                or revision.get("sourceRealVideoPlanDigest")
                != plan.get("payloadDigest")
                or not isinstance(requests, list)
                or len(requests) != 4
                or not all(isinstance(item, Mapping) for item in requests)
                or revision.get("generationRequestCount") != 4
                or [item.get("payloadDigest") for item in requests]
                != revision.get("generationRequestDigests")
                or [item.get("generationRequestVersionRef") for item in requests]
                != revision.get("generationRequestVersionRefs")
                or request.get("payloadDigest")
                not in revision.get("generationRequestDigests", [])
                or payload.get("revisionRef")
                != revision.get("realVideoRevisionRef")
                or payload.get("sourceRequestRef")
                != request.get("generationRequestRef")
                or payload.get("sourceRequestDigest")
                != request.get("payloadDigest")
                or payload.get("slotRef")
                != request.get("creativeShotVersionRef")
                or payload.get("sourceAssetVersions")
                != [
                    {
                        "assetVersionRef": request.get(
                            "sourceImageAssetVersionRef"
                        ),
                        "assetVersionDigest": request.get(
                            "sourceImageAssetVersionDigest"
                        ),
                    }
                ]
            ):
                raise RepositoryUnavailableError(
                    "persisted successor video consumption lineage is invalid"
                )
            normalized_requests = [
                self._assert_sealed_payload(item, "persisted successor request")
                for item in requests
            ]
            if (
                set(revision) != _REAL_VIDEO_SUCCESSOR_REVISION_FIELDS
                or [item.get("ordinal") for item in normalized_requests]
                != [1, 2, 3, 4]
                or {
                    item.get("creativeShotVersionRef")
                    for item in normalized_requests
                }
                != set(baseline_by_slot)
            ):
                raise RepositoryUnavailableError(
                    "persisted successor request coverage is invalid"
                )
            revision_digest = revision["payloadDigest"]
            if revision_digest in seen_revision_digests:
                if (
                    latest_revision is None
                    or revision_digest != latest_revision.get("payloadDigest")
                ):
                    raise RepositoryUnavailableError(
                        "a historical successor video revision was revisited"
                    )
                selected = next(
                    (
                        item
                        for item in normalized_requests
                        if item.get("creativeShotVersionRef")
                        == payload.get("slotRef")
                    ),
                    None,
                )
                if selected != request:
                    raise RepositoryUnavailableError(
                        "persisted successor candidate request changed"
                    )
                if payload.get("slotRef") not in revision.get(
                    "changedSlotRefs", []
                ):
                    raise RepositoryUnavailableError(
                        "persisted successor candidate did not consume a changed request"
                    )
                continue
            prior_by_slot = {
                item["creativeShotVersionRef"]: item for item in prior_requests
            }
            if latest_revision is None:
                if (
                    revision.get("version") != 2
                    or revision.get("supersedesRealVideoRevisionRef")
                    != plan.get("realVideoPlanRef")
                    or revision.get("supersedesRealVideoRevisionDigest")
                    != plan.get("payloadDigest")
                ):
                    raise RepositoryUnavailableError(
                        "first successor video revision does not supersede the plan"
                    )
            elif (
                revision.get("version") != int(latest_revision.get("version", 0)) + 1
                or revision.get("supersedesRealVideoRevisionRef")
                != latest_revision.get("realVideoRevisionRef")
                or revision.get("supersedesRealVideoRevisionDigest")
                != latest_revision.get("payloadDigest")
            ):
                raise RepositoryUnavailableError(
                    "successor video revision lineage is not immediate"
                )
            changed_slots: list[str] = []
            for current_request in normalized_requests:
                slot_ref = current_request.get("creativeShotVersionRef")
                prior_request = prior_by_slot.get(slot_ref)
                baseline_request = baseline_by_slot.get(slot_ref)
                if not isinstance(prior_request, Mapping) or not isinstance(
                    baseline_request, Mapping
                ):
                    raise RepositoryUnavailableError(
                        "successor video request slot is unknown"
                    )
                if (
                    current_request.get("workspaceRef") != workspace
                    or current_request.get("productionRunRef") != run_ref
                    or current_request.get("generationRequestRef")
                    != baseline_request.get("generationRequestRef")
                    or current_request.get("ordinal")
                    != baseline_request.get("ordinal")
                    or current_request.get("creativeShotVersionRef")
                    != baseline_request.get("creativeShotVersionRef")
                    or current_request.get("sourceImageAssetRef")
                    != baseline_request.get("sourceImageAssetRef")
                ):
                    raise RepositoryUnavailableError(
                        "successor video request immutable scope changed"
                    )
                if current_request == prior_request:
                    continue
                changed_slots.append(slot_ref)
                if (
                    set(current_request)
                    != set(baseline_request)
                    | _REAL_VIDEO_SUCCESSOR_REQUEST_EXTENSION
                    or current_request.get("schemaVersion")
                    != REAL_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION
                    or current_request.get("version")
                    != int(prior_request.get("version", 0)) + 1
                    or current_request.get(
                        "supersedesGenerationRequestVersionRef"
                    )
                    != prior_request.get("generationRequestVersionRef")
                    or current_request.get("supersedesGenerationRequestDigest")
                    != prior_request.get("payloadDigest")
                    or current_request.get("realVideoRevisionRef")
                    != revision.get("realVideoRevisionRef")
                    or current_request.get("sourceRealVideoPlanRef")
                    != plan.get("realVideoPlanRef")
                    or current_request.get("sourceRealVideoPlanDigest")
                    != plan.get("payloadDigest")
                    or (
                        current_request.get("sourceImageAssetVersionRef"),
                        current_request.get("sourceImageAssetVersionDigest"),
                    )
                    == (
                        prior_request.get("sourceImageAssetVersionRef"),
                        prior_request.get("sourceImageAssetVersionDigest"),
                    )
                ):
                    raise RepositoryUnavailableError(
                        "successor video request lineage is not immediate"
                    )
            if not changed_slots:
                raise RepositoryUnavailableError(
                    "successor video revision did not change a request"
                )
            if (
                revision.get("isSuccessor") is not True
                or revision.get("publicationAllowed") is not False
                or revision.get("generationRequestCount") != 4
                or revision.get("generationRequestRefs")
                != [item["generationRequestRef"] for item in normalized_requests]
                or revision.get("generationRequestVersionRefs")
                != [
                    item["generationRequestVersionRef"]
                    for item in normalized_requests
                ]
                or revision.get("generationRequestDigests")
                != [item["payloadDigest"] for item in normalized_requests]
                or revision.get("sourceImageAssetVersionRefs")
                != [
                    item["sourceImageAssetVersionRef"]
                    for item in normalized_requests
                ]
                or revision.get("sourceImageAssetVersionDigests")
                != [
                    item["sourceImageAssetVersionDigest"]
                    for item in normalized_requests
                ]
                or revision.get("changedSlotRefs") != sorted(changed_slots)
            ):
                raise RepositoryUnavailableError(
                    "successor video revision arrays are inconsistent"
                )
            selected = next(
                (
                    item
                    for item in normalized_requests
                    if item.get("creativeShotVersionRef")
                    == payload.get("slotRef")
                ),
                None,
            )
            if selected != request or payload.get("slotRef") not in changed_slots:
                raise RepositoryUnavailableError(
                    "persisted successor candidate did not consume a changed request"
                )
            seen_revision_digests.add(revision_digest)
            latest_revision = revision
            prior_requests = normalized_requests
        if latest_revision is None:
            return [deepcopy(dict(item)) for item in baseline_requests], None
        return [
            deepcopy(dict(item))
            for item in latest_revision["generationRequests"]
        ], latest_revision

    def _derive_video_request_for_asset(
        self,
        *,
        prior_request: Mapping[str, Any],
        current_asset: Mapping[str, Any],
        real_video_revision_ref: str,
        source_real_video_plan_ref: str,
        source_real_video_plan_digest: str,
    ) -> dict[str, Any]:
        """Derive one exact immediate successor of the persisted request."""

        if (
            current_asset.get("assetRef")
            != prior_request.get("sourceImageAssetRef")
            or current_asset.get("creativeShotVersionRef")
            != prior_request.get("creativeShotVersionRef")
            or current_asset.get("mediaKind") != "image"
            or current_asset.get("mediaType") != "image/png"
        ):
            raise StaleInputError("successor image AssetVersion scope changed")
        if (
            current_asset.get("assetVersionRef")
            == prior_request.get("sourceImageAssetVersionRef")
            and current_asset.get("payloadDigest")
            == prior_request.get("sourceImageAssetVersionDigest")
        ):
            return deepcopy(dict(prior_request))
        prior_version = int(prior_request.get("version", 0))
        if prior_version < 1:
            raise StaleInputError("prior video request version is invalid")
        request_version = prior_version + 1
        payload = deepcopy(dict(prior_request))
        payload.pop("payloadDigest", None)
        payload.update(
            {
                "schemaVersion": REAL_VIDEO_SUCCESSOR_REQUEST_SCHEMA_VERSION,
                "generationRequestVersionRef": (
                    f"{prior_request['generationRequestRef']}-v{request_version}-"
                    + _digest(
                        {
                            "priorGenerationRequestDigest": prior_request[
                                "payloadDigest"
                            ],
                            "sourceImageAssetVersionDigest": current_asset[
                                "payloadDigest"
                            ],
                            "realVideoRevisionRef": real_video_revision_ref,
                        }
                    )[:16]
                ),
                "version": request_version,
                "realVideoRevisionRef": real_video_revision_ref,
                "sourceRealVideoPlanRef": source_real_video_plan_ref,
                "sourceRealVideoPlanDigest": source_real_video_plan_digest,
                "supersedesGenerationRequestVersionRef": prior_request[
                    "generationRequestVersionRef"
                ],
                "supersedesGenerationRequestDigest": prior_request[
                    "payloadDigest"
                ],
                "sourceImageAssetVersionRef": current_asset["assetVersionRef"],
                "sourceImageAssetVersionDigest": current_asset["payloadDigest"],
                "sourceImageContentDigest": current_asset["sha256"],
                "sourceImageMediaType": current_asset["mediaType"],
                "sourceImageProbe": deepcopy(current_asset["probe"]),
                "parameters": self._video_profile(
                    {
                        "output": {
                            "width": prior_request["parameters"]["width"],
                            "height": prior_request["parameters"]["height"],
                            "frameRate": prior_request["parameters"][
                                "frameRate"
                            ],
                        }
                    },
                    {
                        "durationFrames": prior_request["parameters"][
                            "durationFrames"
                        ]
                    },
                    current_asset,
                ),
                "createdBy": REAL_VIDEO_SUCCESSOR_PLANNER_ID,
                "createdAt": current_asset.get("createdAt"),
            }
        )
        return _sealed(payload)

    def _current_video_request_set(
        self,
        workspace: str,
        run_ref: str,
        plan_bundle: Mapping[str, Any],
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        plan = plan_bundle["realVideoPlan"]
        baseline_requests = plan_bundle["generationRequests"]
        image_gate = (
            self.evidence.get_gate(
                workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
            )
            if gates is None
            else next(
                (
                    item
                    for item in gates
                    if item.get("gateName") == REAL_IMAGE_ADMISSION_GATE
                ),
                None,
            )
        )
        if image_gate is None:
            raise UpstreamNotReadyError("M10 image admission is required")
        baseline_assets = self._admission_bundle(
            image_gate, records=records
        )["assetVersions"]
        baseline_by_slot = {item["creativeShotVersionRef"]: item for item in baseline_assets}
        current_assets = self._current_image_assets_for_video(
            workspace,
            run_ref,
            baseline_assets,
            records=records,
            gates=gates,
        )
        current_by_slot = {
            item["creativeShotVersionRef"]: item for item in current_assets
        }
        prior_requests, prior_revision = self._persisted_video_revision(
            workspace,
            run_ref,
            plan,
            baseline_requests,
            records=records,
        )
        prior_by_slot = {
            item["creativeShotVersionRef"]: item for item in prior_requests
        }
        changed_slots = [
            slot_ref
            for slot_ref, current_asset in current_by_slot.items()
            if (
                prior_by_slot[slot_ref].get("sourceImageAssetVersionRef")
                != current_asset.get("assetVersionRef")
                or prior_by_slot[slot_ref].get("sourceImageAssetVersionDigest")
                != current_asset.get("payloadDigest")
            )
        ]
        if not changed_slots and prior_revision is not None:
            return prior_requests, deepcopy(prior_revision)
        if not changed_slots:
            revision_ref = plan["realVideoPlanRef"]
            revision_version = 1
            supersedes_ref = None
            supersedes_digest = None
            requests = prior_requests
        else:
            previous_revision_ref = (
                prior_revision["realVideoRevisionRef"]
                if prior_revision is not None
                else plan["realVideoPlanRef"]
            )
            previous_revision_digest = (
                prior_revision["payloadDigest"]
                if prior_revision is not None
                else plan["payloadDigest"]
            )
            revision_version = (
                int(prior_revision["version"]) + 1
                if prior_revision is not None
                else 2
            )
            revision_ref = (
                f"m11-video-revision-v{revision_version}-"
                + _digest(
                    {
                        "supersedesRealVideoRevisionDigest": previous_revision_digest,
                        "sourceImageAssetVersionDigests": [
                            item["payloadDigest"] for item in current_assets
                        ],
                    }
                )[:32]
            )
            supersedes_ref = previous_revision_ref
            supersedes_digest = previous_revision_digest
            requests = [
                self._derive_video_request_for_asset(
                    prior_request=prior_by_slot[item["creativeShotVersionRef"]],
                    current_asset=current_by_slot[item["creativeShotVersionRef"]],
                    real_video_revision_ref=revision_ref,
                    source_real_video_plan_ref=plan["realVideoPlanRef"],
                    source_real_video_plan_digest=plan["payloadDigest"],
                )
                for item in baseline_requests
            ]
        revision = _sealed(
            {
                "schemaVersion": REAL_VIDEO_SUCCESSOR_REVISION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realVideoRevisionRef": revision_ref,
                "version": revision_version,
                "isSuccessor": bool(changed_slots or prior_revision),
                "sourceRealVideoPlanRef": plan["realVideoPlanRef"],
                "sourceRealVideoPlanDigest": plan["payloadDigest"],
                "supersedesRealVideoRevisionRef": supersedes_ref,
                "supersedesRealVideoRevisionDigest": supersedes_digest,
                "sourceImageAssetVersionRefs": [
                    item["assetVersionRef"] for item in current_assets
                ],
                "sourceImageAssetVersionDigests": [
                    item["payloadDigest"] for item in current_assets
                ],
                "generationRequestRefs": [
                    item["generationRequestRef"] for item in requests
                ],
                "generationRequestVersionRefs": [
                    item["generationRequestVersionRef"] for item in requests
                ],
                "generationRequestDigests": [
                    item["payloadDigest"] for item in requests
                ],
                "generationRequestCount": 4,
                "generationRequests": deepcopy(requests),
                "changedSlotRefs": sorted(changed_slots),
                "publicationAllowed": False,
            }
        )
        return requests, revision

    def _active_video_admission(
        self,
        workspace: str,
        run_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the one strictly validated atomic four-slot VIDEO chain.

        Successor activations are ordinary ``AssetAdmission`` records under
        ADR-0013.  This validator is intentionally the sole interpreter of
        their typed payload.  It walks the append journal in order, so an
        activation cannot make a forward reference to a record later in the
        log, and it proves every NEW/REUSED slot against the immediately prior
        active four-slot set.
        """

        gate_values = (
            self.evidence.list_gates(workspace, run_ref)
            if gates is None
            else gates
        )
        gate = next(
            (
                item
                for item in gate_values
                if item.get("gateName") == REAL_VIDEO_ADMISSION_GATE
            ),
            None,
        )
        if gate is None:
            return None
        plan_gate = next(
            (
                item
                for item in gate_values
                if item.get("gateName") == REAL_VIDEO_PLAN_GATE
            ),
            None,
        )
        if plan_gate is None:
            raise RepositoryUnavailableError("M11 video plan evidence is missing")
        plan_bundle = self._video_bundle(plan_gate)
        plan = plan_bundle["realVideoPlan"]
        # This validates every persisted v2/v3 request/revision carrier, not
        # merely the latest one, before any activation payload is consumed.
        self._persisted_video_revision(
            workspace,
            run_ref,
            plan,
            plan_bundle["generationRequests"],
            records=records,
        )
        gate_bundle = self._video_admission_bundle(gate)
        manifest = self._assert_sealed_payload(
            gate_bundle["realVideoAdmissionManifest"],
            "initial M11 video activation",
        )
        admissions = [
            self._assert_sealed_payload(item, "initial M11 item admission")
            for item in gate_bundle["assetAdmissions"]
        ]
        assets = [
            self._assert_sealed_payload(item, "initial M11 AssetVersion")
            for item in gate_bundle["assetVersions"]
        ]
        if (
            set(manifest) != _REAL_VIDEO_INITIAL_ACTIVATION_FIELDS
            or manifest.get("schemaVersion") != REAL_VIDEO_ADMISSION_SCHEMA_VERSION
            or manifest.get("workspaceRef") != workspace
            or manifest.get("productionRunRef") != run_ref
            or manifest.get("version") != 1
            or manifest.get("realVideoPlanRef") != plan.get("realVideoPlanRef")
            or manifest.get("realVideoPlanDigest") != plan.get("payloadDigest")
            or manifest.get("admittedCount") != 4
            or manifest.get("state") != "REAL_VIDEO_ADMITTED"
            or manifest.get("publicationAllowed") is not False
            or len(assets) != 4
            or len(admissions) != 4
            or [item.get("ordinal") for item in assets] != [1, 2, 3, 4]
            or [item.get("ordinal") for item in admissions] != [1, 2, 3, 4]
            or manifest.get("candidateRefs")
            != [item.get("sourceCandidateRef") for item in assets]
            or manifest.get("candidateDigests")
            != [item.get("sourceCandidateDigest") for item in assets]
            or manifest.get("selectionRefs")
            != [item.get("humanSelectionRef") for item in assets]
            or manifest.get("selectionDigests")
            != [item.get("humanSelectionDigest") for item in assets]
            or manifest.get("assetVersionRefs")
            != [item.get("assetVersionRef") for item in assets]
            or manifest.get("assetVersionDigests")
            != [item.get("payloadDigest") for item in assets]
            or [item.get("assetVersionRef") for item in admissions]
            != [item.get("assetVersionRef") for item in assets]
            or [item.get("assetVersionDigest") for item in admissions]
            != [item.get("payloadDigest") for item in assets]
        ):
            raise RepositoryUnavailableError(
                "initial M11 video activation is inconsistent"
            )

        journal_records = (
            self.evidence.list_records(workspace, run_ref)
            if records is None
            else list(records)
        )
        positions = {
            id(record): index for index, record in enumerate(journal_records)
        }

        def sealed_record_payload(
            record: Mapping[str, Any], field: str
        ) -> dict[str, Any]:
            if (
                record.get("workspaceRef") != workspace
                or record.get("productionRunRef") != run_ref
                or not isinstance(record.get("payload"), Mapping)
            ):
                raise RepositoryUnavailableError(f"{field} scope is invalid")
            payload = self._assert_sealed_payload(record["payload"], field)
            if (
                record.get("payloadDigest") != payload.get("payloadDigest")
                or record.get("createdAt") is None
            ):
                raise RepositoryUnavailableError(f"{field} envelope is invalid")
            return payload

        full_index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for record in journal_records:
            payload = record.get("payload")
            digest = record.get("payloadDigest")
            if isinstance(payload, Mapping) and isinstance(digest, str):
                full_index.setdefault(
                    (str(record.get("recordKind")), str(record.get("recordRef")), digest),
                    [],
                ).append(record)

        def exact_record(
            index: Mapping[tuple[str, str, str], Sequence[dict[str, Any]]],
            kind: str,
            ref: Any,
            digest: Any,
            field: str,
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            matches = index.get((kind, str(ref), str(digest)), ())
            if len(matches) != 1:
                raise RepositoryUnavailableError(f"{field} is missing or ambiguous")
            record = matches[0]
            payload = sealed_record_payload(record, field)
            return record, payload

        def assert_record_identity(
            record: Mapping[str, Any],
            payload: Mapping[str, Any],
            *,
            kind: str,
            ref_field: str,
            version_field: str,
            field: str,
        ) -> None:
            if (
                record.get("recordKind") != kind
                or record.get("recordRef") != payload.get(ref_field)
                or record.get("recordVersion") != payload.get(version_field)
                or record.get("createdAt") != payload.get("createdAt", record.get("createdAt"))
            ):
                raise RepositoryUnavailableError(f"{field} identity is invalid")

        def applicable_qc(
            prior_records: Sequence[dict[str, Any]],
            candidate_ref: str,
            candidate_digest: str,
        ) -> tuple[dict[str, Any], dict[str, Any]] | None:
            decisions: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for item in prior_records:
                if item.get("recordKind") != "SemanticVisualQCDecision":
                    continue
                payload = sealed_record_payload(item, "M11 semantic visual QC")
                if (
                    payload.get("candidateRef") == candidate_ref
                    and payload.get("candidateDigest") == candidate_digest
                ):
                    decisions.append((item, payload))
            identities = {
                (item.get("recordRef"), item.get("recordVersion"), item.get("payloadDigest"))
                for item, _ in decisions
            }
            superseded: set[tuple[Any, Any, Any]] = set()
            for _, payload in decisions:
                prior = payload.get("supersedesVisualQc")
                if prior is None:
                    continue
                if not isinstance(prior, Mapping):
                    raise RepositoryUnavailableError("M11 QC supersession is invalid")
                identity = (
                    prior.get("visualQcRef"),
                    prior.get("visualQcVersion"),
                    prior.get("visualQcDigest"),
                )
                if identity not in identities:
                    raise RepositoryUnavailableError("M11 QC supersession is stale")
                superseded.add(identity)
            current = [
                (item, payload)
                for item, payload in decisions
                if (
                    item.get("recordRef"),
                    item.get("recordVersion"),
                    item.get("payloadDigest"),
                )
                not in superseded
            ]
            if len(current) > 1:
                raise RepositoryUnavailableError("M11 current QC is ambiguous")
            return current[0] if current else None

        def latest_candidate_by_slot(
            prior_records: Sequence[dict[str, Any]],
        ) -> dict[str, dict[str, Any]]:
            latest: dict[str, dict[str, Any]] = {}
            for item in prior_records:
                if item.get("recordKind") != CANDIDATE:
                    continue
                payload = sealed_record_payload(item, "M11 Candidate")
                if payload.get("mediaKind") == "VIDEO" and isinstance(
                    payload.get("slotRef"), str
                ):
                    latest[payload["slotRef"]] = item
            return latest

        def resolve_chain(
            slot: Mapping[str, Any],
            prior_records: Sequence[dict[str, Any]],
            prior_index: Mapping[tuple[str, str, str], Sequence[dict[str, Any]]],
            *,
            require_current: bool,
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
            candidate_record, candidate = exact_record(
                prior_index,
                CANDIDATE,
                slot.get("candidateRef"),
                slot.get("candidateDigest"),
                "M11 activation Candidate",
            )
            qc_record, qc = exact_record(
                prior_index,
                "SemanticVisualQCDecision",
                slot.get("semanticVisualQcRef"),
                slot.get("semanticVisualQcDigest"),
                "M11 activation semantic visual QC",
            )
            selection_record, selection = exact_record(
                prior_index,
                HUMAN_SELECTION,
                slot.get("humanSelectionRef"),
                slot.get("humanSelectionDigest"),
                "M11 activation HumanSelection",
            )
            admission_record, admission = exact_record(
                prior_index,
                ASSET_ADMISSION,
                slot.get("assetAdmissionRef"),
                slot.get("assetAdmissionDigest"),
                "M11 activation item admission",
            )
            asset_record, asset = exact_record(
                prior_index,
                ASSET_VERSION,
                slot.get("assetVersionRef"),
                slot.get("assetVersionDigest"),
                "M11 activation AssetVersion",
            )
            assert_record_identity(
                candidate_record,
                candidate,
                kind=CANDIDATE,
                ref_field="candidateRef",
                version_field="candidateVersion",
                field="M11 activation Candidate",
            )
            assert_record_identity(
                qc_record,
                qc,
                kind="SemanticVisualQCDecision",
                ref_field="visualQcRef",
                version_field="visualQcVersion",
                field="M11 activation semantic visual QC",
            )
            assert_record_identity(
                selection_record,
                selection,
                kind=HUMAN_SELECTION,
                ref_field="selectionRef",
                version_field="selectionVersion",
                field="M11 activation HumanSelection",
            )
            assert_record_identity(
                admission_record,
                admission,
                kind=ASSET_ADMISSION,
                ref_field="admissionRef",
                version_field="version",
                field="M11 activation item admission",
            )
            assert_record_identity(
                asset_record,
                asset,
                kind=ASSET_VERSION,
                ref_field="assetVersionRef",
                version_field="version",
                field="M11 activation AssetVersion",
            )
            validation_record, validation = exact_record(
                prior_index,
                TECHNICAL_VALIDATION,
                qc.get("technicalValidationRef"),
                qc.get("technicalValidationDigest"),
                "M11 activation TechnicalValidation",
            )
            assert_record_identity(
                validation_record,
                validation,
                kind=TECHNICAL_VALIDATION,
                ref_field="technicalValidationRef",
                version_field="technicalValidationVersion",
                field="M11 activation TechnicalValidation",
            )
            current_qc = applicable_qc(
                prior_records,
                str(slot.get("candidateRef")),
                str(slot.get("candidateDigest")),
            )
            latest_candidate = latest_candidate_by_slot(prior_records).get(
                str(slot.get("slotRef"))
            )
            if (
                candidate.get("mediaKind") != "VIDEO"
                or candidate.get("slotRef") != slot.get("slotRef")
                or candidate.get("sourceRequestRef")
                != slot.get("generationRequestRef")
                or candidate.get("sourceRequestDigest")
                != slot.get("generationRequestDigest")
                or candidate.get("sourceAssetVersions")
                != [
                    {
                        "assetVersionRef": asset.get(
                            "sourceImageAssetVersionRef"
                        ),
                        "assetVersionDigest": asset.get(
                            "sourceImageAssetVersionDigest"
                        ),
                    }
                ]
                or validation.get("candidateRef") != candidate.get("candidateRef")
                or validation.get("candidateDigest") != candidate.get("payloadDigest")
                or validation.get("result") != "PASS"
                or qc.get("candidateRef") != candidate.get("candidateRef")
                or qc.get("candidateDigest") != candidate.get("payloadDigest")
                or qc.get("technicalValidationRef")
                != validation.get("technicalValidationRef")
                or qc.get("technicalValidationDigest")
                != validation.get("payloadDigest")
                or qc.get("result") != "PASS"
                or selection.get("candidateRef") != candidate.get("candidateRef")
                or selection.get("candidateDigest") != candidate.get("payloadDigest")
                or selection.get("visualQcRef") != qc.get("visualQcRef")
                or selection.get("visualQcDigest") != qc.get("payloadDigest")
                or selection.get("decision") != "SELECTED"
                or admission.get("schemaVersion") != "v5.k2-asset-admission.v1"
                or admission.get("ordinal") != slot.get("ordinal")
                or admission.get("candidateRef") != candidate.get("candidateRef")
                or admission.get("candidateDigest") != candidate.get("payloadDigest")
                or admission.get("selectionRef") != selection.get("selectionRef")
                or admission.get("selectionDigest") != selection.get("payloadDigest")
                or admission.get("assetVersionRef") != asset.get("assetVersionRef")
                or admission.get("assetVersionDigest") != asset.get("payloadDigest")
                or admission.get("admissionState") != "ADMITTED"
                or admission.get("publicationAllowed") is not False
                or asset.get("schemaVersion") != REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION
                or asset.get("ordinal") != slot.get("ordinal")
                or asset.get("creativeShotVersionRef") != slot.get("slotRef")
                or asset.get("generationRequestRef")
                != slot.get("generationRequestRef")
                or asset.get("generationRequestVersionRef")
                != slot.get("generationRequestVersionRef")
                or asset.get("generationRequestDigest")
                != slot.get("generationRequestDigest")
                or asset.get("sourceCandidateRef") != candidate.get("candidateRef")
                or asset.get("sourceCandidateDigest") != candidate.get("payloadDigest")
                or asset.get("semanticVisualQcRef") != qc.get("visualQcRef")
                or asset.get("semanticVisualQcDigest") != qc.get("payloadDigest")
                or asset.get("humanSelectionRef") != selection.get("selectionRef")
                or asset.get("humanSelectionVersion")
                != selection.get("selectionVersion")
                or asset.get("humanSelectionDigest") != selection.get("payloadDigest")
                or asset.get("state") != "REGISTERED"
                or asset.get("immutable") is not True
                or asset.get("publicationAllowed") is not False
                or (
                    require_current
                    and (
                        latest_candidate is None
                        or latest_candidate.get("recordRef")
                        != candidate_record.get("recordRef")
                        or latest_candidate.get("recordVersion")
                        != candidate_record.get("recordVersion")
                        or latest_candidate.get("payloadDigest")
                        != candidate_record.get("payloadDigest")
                        or current_qc is None
                        or current_qc[0].get("recordRef") != qc_record.get("recordRef")
                        or current_qc[0].get("recordVersion")
                        != qc_record.get("recordVersion")
                        or current_qc[0].get("payloadDigest")
                        != qc_record.get("payloadDigest")
                    )
                )
            ):
                raise RepositoryUnavailableError(
                    "M11 activation Candidate-to-AssetVersion chain is invalid"
                )
            return deepcopy(admission), deepcopy(asset), deepcopy(candidate)

        # Locate the atomically appended initial item records and use their
        # last journal position as the gate's record cut.  Successor manifests
        # must occur strictly after this cut.
        initial_record_positions: list[int] = []
        initial_slots: list[dict[str, Any]] = []
        for admission, asset in zip(admissions, assets):
            admission_record, _ = exact_record(
                full_index,
                ASSET_ADMISSION,
                admission.get("admissionRef"),
                admission.get("payloadDigest"),
                "initial M11 item admission",
            )
            asset_record, _ = exact_record(
                full_index,
                ASSET_VERSION,
                asset.get("assetVersionRef"),
                asset.get("payloadDigest"),
                "initial M11 AssetVersion",
            )
            selection_record, _ = exact_record(
                full_index,
                HUMAN_SELECTION,
                asset.get("humanSelectionRef"),
                asset.get("humanSelectionDigest"),
                "initial M11 HumanSelection",
            )
            initial_record_positions.extend(
                [positions[id(admission_record)], positions[id(asset_record)], positions[id(selection_record)]]
            )
            initial_slots.append(
                {
                    "ordinal": asset.get("ordinal"),
                    "slotRef": asset.get("creativeShotVersionRef"),
                    "generationRequestRef": asset.get("generationRequestRef"),
                    "generationRequestVersionRef": asset.get(
                        "generationRequestVersionRef"
                    ),
                    "generationRequestDigest": asset.get("generationRequestDigest"),
                    "candidateRef": asset.get("sourceCandidateRef"),
                    "candidateDigest": asset.get("sourceCandidateDigest"),
                    "semanticVisualQcRef": asset.get("semanticVisualQcRef"),
                    "semanticVisualQcDigest": asset.get("semanticVisualQcDigest"),
                    "humanSelectionRef": asset.get("humanSelectionRef"),
                    "humanSelectionDigest": asset.get("humanSelectionDigest"),
                    "assetAdmissionRef": admission.get("admissionRef"),
                    "assetAdmissionDigest": admission.get("payloadDigest"),
                    "assetVersionRef": asset.get("assetVersionRef"),
                    "assetVersionDigest": asset.get("payloadDigest"),
                    "activationSource": "INITIAL_ADMISSION",
                }
            )
        if not initial_record_positions:
            raise RepositoryUnavailableError("initial M11 activation records are missing")
        initial_cut = max(initial_record_positions)

        def build_index(
            prior_records: Sequence[dict[str, Any]],
        ) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
            result: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for item in prior_records:
                if isinstance(item.get("payloadDigest"), str):
                    result.setdefault(
                        (
                            str(item.get("recordKind")),
                            str(item.get("recordRef")),
                            str(item.get("payloadDigest")),
                        ),
                        [],
                    ).append(item)
            return result

        prior_records = list(journal_records[: initial_cut + 1])
        prior_index = build_index(prior_records)
        initial_resolved: list[
            tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = [
            resolve_chain(slot, prior_records, prior_index, require_current=True)
            for slot in initial_slots
        ]
        if _digest(
            {
                "selections": sorted(
                    [
                        {
                            "visualQcRef": slot["semanticVisualQcRef"],
                            "visualQcVersion": exact_record(
                                prior_index,
                                "SemanticVisualQCDecision",
                                slot["semanticVisualQcRef"],
                                slot["semanticVisualQcDigest"],
                                "initial M11 semantic visual QC",
                            )[0]["recordVersion"],
                            "visualQcDigest": slot["semanticVisualQcDigest"],
                            "selectionRef": slot["humanSelectionRef"],
                            "selectionVersion": exact_record(
                                prior_index,
                                HUMAN_SELECTION,
                                slot["humanSelectionRef"],
                                slot["humanSelectionDigest"],
                                "initial M11 HumanSelection",
                            )[0]["recordVersion"],
                            "approvalRef": exact_record(
                                prior_index,
                                HUMAN_SELECTION,
                                slot["humanSelectionRef"],
                                slot["humanSelectionDigest"],
                                "initial M11 HumanSelection",
                            )[1].get("approvalRef"),
                        }
                        for slot in initial_slots
                    ],
                    key=lambda item: item["selectionRef"],
                )
            }
        ) != manifest.get("selectionRequestDigest"):
            raise RepositoryUnavailableError(
                "initial M11 selection request digest is invalid"
            )
        current = {
            "manifest": manifest,
            "admissions": [item[0] for item in initial_resolved],
            "assets": [item[1] for item in initial_resolved],
            "candidates": [item[2] for item in initial_resolved],
            "slots": deepcopy(initial_slots),
            "manifestRef": manifest["realVideoAdmissionManifestRef"],
            "manifestDigest": manifest["payloadDigest"],
            "revisionVersion": 1,
            "revisionSupersessionRef": plan["realVideoPlanRef"],
            "revisionSupersessionDigest": plan["payloadDigest"],
        }

        for record in journal_records[initial_cut + 1 :]:
            payload = record.get("payload")
            if (
                record.get("recordKind") == ASSET_ADMISSION
                and isinstance(payload, Mapping)
                and payload.get("schemaVersion")
                == REAL_VIDEO_SUCCESSOR_ACTIVATION_SCHEMA_VERSION
            ):
                activation = sealed_record_payload(
                    record, "successor M11 activation"
                )
                slots = activation.get("slotActivations")
                if (
                    set(activation) != _REAL_VIDEO_SUCCESSOR_ACTIVATION_FIELDS
                    or record.get("recordRef") != activation.get("admissionRef")
                    or record.get("recordVersion") != activation.get("version")
                    or record.get("createdAt") != activation.get("createdAt")
                    or activation.get("workspaceRef") != workspace
                    or activation.get("productionRunRef") != run_ref
                    or activation.get("version")
                    != int(current["manifest"].get("version", 0)) + 1
                    or activation.get("admissionState") != "ACTIVATED"
                    or activation.get("realVideoPlanRef")
                    != plan.get("realVideoPlanRef")
                    or activation.get("realVideoPlanDigest")
                    != plan.get("payloadDigest")
                    or activation.get("supersedesActivationRef")
                    != current["manifestRef"]
                    or activation.get("supersedesActivationDigest")
                    != current["manifestDigest"]
                    or not isinstance(slots, list)
                    or len(slots) != 4
                    or not all(isinstance(item, Mapping) for item in slots)
                    or any(
                        set(item) != _REAL_VIDEO_ACTIVATION_SLOT_FIELDS
                        for item in slots
                    )
                    or [item.get("ordinal") for item in slots] != [1, 2, 3, 4]
                    or len({item.get("slotRef") for item in slots}) != 4
                    or activation.get("assetVersionRefs")
                    != [item.get("assetVersionRef") for item in slots]
                    or activation.get("assetVersionDigests")
                    != [item.get("assetVersionDigest") for item in slots]
                    or activation.get("state") != "REAL_VIDEO_ADMITTED"
                    or activation.get("publicationAllowed") is not False
                ):
                    raise RepositoryUnavailableError(
                        "successor M11 activation manifest is invalid"
                    )
                prior_by_slot = {
                    item["slotRef"]: item for item in current["slots"]
                }
                resolved_admissions: list[dict[str, Any]] = []
                resolved_assets: list[dict[str, Any]] = []
                resolved_candidates: list[dict[str, Any]] = []
                new_slots: list[dict[str, Any]] = []
                for slot in slots:
                    prior_slot = prior_by_slot.get(slot.get("slotRef"))
                    if not isinstance(prior_slot, Mapping):
                        raise RepositoryUnavailableError(
                            "successor M11 activation slot is unknown"
                        )
                    if slot.get("activationSource") == "REUSED_CURRENT":
                        if any(
                            slot.get(field) != prior_slot.get(field)
                            for field in _REAL_VIDEO_ACTIVATION_SLOT_FIELDS
                            - {"activationSource"}
                        ):
                            raise RepositoryUnavailableError(
                                "successor M11 reused slot changed"
                            )
                        admission, asset, candidate = resolve_chain(
                            slot,
                            prior_records,
                            prior_index,
                            require_current=False,
                        )
                    elif slot.get("activationSource") == "NEW_ADMISSION":
                        admission, asset, candidate = resolve_chain(
                            slot,
                            prior_records,
                            prior_index,
                            require_current=True,
                        )
                        predecessor_asset = current["assets"][
                            int(slot["ordinal"]) - 1
                        ]
                        if (
                            asset.get("assetRef")
                            != predecessor_asset.get("assetRef")
                            or asset.get("version")
                            != int(predecessor_asset.get("version", 0)) + 1
                            or asset.get("supersedesAssetVersionRef")
                            != predecessor_asset.get("assetVersionRef")
                            or asset.get("supersedesAssetVersionDigest")
                            != predecessor_asset.get("payloadDigest")
                            or asset.get("revisionRef")
                            != activation.get("realVideoRevisionRef")
                        ):
                            raise RepositoryUnavailableError(
                                "successor M11 AssetVersion lineage is not immediate"
                            )
                        new_slots.append(dict(slot))
                    else:
                        raise RepositoryUnavailableError(
                            "successor M11 activation source is invalid"
                        )
                    resolved_admissions.append(admission)
                    resolved_assets.append(asset)
                    resolved_candidates.append(candidate)
                changed_slot_refs = sorted(item["slotRef"] for item in new_slots)
                if (
                    not new_slots
                    or activation.get("changedSlotRefs") != changed_slot_refs
                    or activation.get("newAdmissionCount") != len(new_slots)
                    or activation.get("reusedAdmissionCount") != 4 - len(new_slots)
                    or activation.get("newAdmissionRefs")
                    != [item["assetAdmissionRef"] for item in new_slots]
                    or activation.get("newAdmissionDigests")
                    != [item["assetAdmissionDigest"] for item in new_slots]
                ):
                    raise RepositoryUnavailableError(
                        "successor M11 activation counts are inconsistent"
                    )
                selection_inputs: list[dict[str, Any]] = []
                for slot in new_slots:
                    selection_record, selection = exact_record(
                        prior_index,
                        HUMAN_SELECTION,
                        slot["humanSelectionRef"],
                        slot["humanSelectionDigest"],
                        "successor M11 HumanSelection",
                    )
                    qc_record, _ = exact_record(
                        prior_index,
                        "SemanticVisualQCDecision",
                        slot["semanticVisualQcRef"],
                        slot["semanticVisualQcDigest"],
                        "successor M11 semantic visual QC",
                    )
                    selection_inputs.append(
                        {
                            "visualQcRef": slot["semanticVisualQcRef"],
                            "visualQcVersion": qc_record["recordVersion"],
                            "visualQcDigest": slot["semanticVisualQcDigest"],
                            "selectionRef": slot["humanSelectionRef"],
                            "selectionVersion": selection_record["recordVersion"],
                            "approvalRef": selection.get("approvalRef"),
                        }
                    )
                anchors = [
                    item
                    for item in prior_records
                    if item.get("idempotencyKey")
                    == activation.get("operationIdempotencyKey")
                ]
                if (
                    _digest(
                        {
                            "selections": sorted(
                                selection_inputs,
                                key=lambda item: item["selectionRef"],
                            )
                        }
                    )
                    != activation.get("selectionRequestDigest")
                    or len(anchors) != 1
                    or anchors[0].get("recordKind") != HUMAN_SELECTION
                    or not any(
                        anchors[0].get("recordRef") == item["humanSelectionRef"]
                        and anchors[0].get("payloadDigest")
                        == item["humanSelectionDigest"]
                        for item in new_slots
                    )
                ):
                    raise RepositoryUnavailableError(
                        "successor M11 operation anchor is invalid"
                    )
                revision_identity = (
                    activation.get("realVideoRevisionRef"),
                    activation.get("realVideoRevisionDigest"),
                )
                predecessor_revision_identity = (
                    current["manifest"].get(
                        "realVideoRevisionRef", current["manifest"].get("revisionRef")
                    ),
                    current["manifest"].get("realVideoRevisionDigest"),
                )
                if revision_identity != predecessor_revision_identity:
                    revision_carriers = []
                    for candidate in resolved_candidates:
                        value = candidate.get("consumedRealVideoRevision")
                        if isinstance(value, Mapping):
                            sealed_revision = self._assert_sealed_payload(
                                value, "successor M11 consumed revision"
                            )
                            if (
                                sealed_revision.get("realVideoRevisionRef"),
                                sealed_revision.get("payloadDigest"),
                            ) == revision_identity:
                                revision_carriers.append(sealed_revision)
                    if not revision_carriers or any(
                        item != revision_carriers[0] for item in revision_carriers
                    ):
                        raise RepositoryUnavailableError(
                            "successor M11 activation revision is not persisted"
                        )
                    sealed_revision = revision_carriers[0]
                    if (
                        set(sealed_revision)
                        != _REAL_VIDEO_SUCCESSOR_REVISION_FIELDS
                        or sealed_revision.get("schemaVersion")
                        != REAL_VIDEO_SUCCESSOR_REVISION_SCHEMA_VERSION
                        or sealed_revision.get("workspaceRef") != workspace
                        or sealed_revision.get("productionRunRef") != run_ref
                        or sealed_revision.get("version")
                        != int(current["revisionVersion"]) + 1
                        or sealed_revision.get("isSuccessor") is not True
                        or sealed_revision.get("sourceRealVideoPlanRef")
                        != plan.get("realVideoPlanRef")
                        or sealed_revision.get("sourceRealVideoPlanDigest")
                        != plan.get("payloadDigest")
                        or sealed_revision.get("supersedesRealVideoRevisionRef")
                        != current["revisionSupersessionRef"]
                        or sealed_revision.get(
                            "supersedesRealVideoRevisionDigest"
                        )
                        != current["revisionSupersessionDigest"]
                        or sealed_revision.get("publicationAllowed") is not False
                    ):
                        raise RepositoryUnavailableError(
                            "successor M11 activation revision is not immediate"
                        )
                    for slot, candidate in zip(slots, resolved_candidates):
                        if slot.get("activationSource") != "NEW_ADMISSION":
                            continue
                        request = candidate.get("consumedGenerationRequest")
                        if (
                            not isinstance(request, Mapping)
                            or candidate.get("consumedRealVideoRevision")
                            != revision_carriers[0]
                            or request.get("generationRequestRef")
                            != slot.get("generationRequestRef")
                            or request.get("generationRequestVersionRef")
                            != slot.get("generationRequestVersionRef")
                            or request.get("payloadDigest")
                            != slot.get("generationRequestDigest")
                        ):
                            raise RepositoryUnavailableError(
                                "successor M11 activation request is not sealed"
                            )
                current = {
                    "manifest": activation,
                    "admissions": resolved_admissions,
                    "assets": resolved_assets,
                    "candidates": resolved_candidates,
                    "slots": [deepcopy(dict(item)) for item in slots],
                    "manifestRef": activation["admissionRef"],
                    "manifestDigest": activation["payloadDigest"],
                    "revisionVersion": (
                        current["revisionVersion"]
                        if revision_identity == predecessor_revision_identity
                        else revision_carriers[0]["version"]
                    ),
                    "revisionSupersessionRef": (
                        current["revisionSupersessionRef"]
                        if revision_identity == predecessor_revision_identity
                        else revision_identity[0]
                    ),
                    "revisionSupersessionDigest": (
                        current["revisionSupersessionDigest"]
                        if revision_identity == predecessor_revision_identity
                        else revision_identity[1]
                    ),
                }
            prior_records.append(record)
            prior_index = build_index(prior_records)
        current["lineageCurrent"] = self._video_activation_is_current(
            workspace,
            run_ref,
            current,
            records=journal_records,
            gates=gate_values,
        )
        return current

    def _video_activation_is_current(
        self,
        workspace: str,
        run_ref: str,
        active: Mapping[str, Any],
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> bool:
        """Bind every active slot to the journal-current canonical chain."""

        slots = active.get("slots")
        assets = active.get("assets")
        if (
            not isinstance(slots, list)
            or not isinstance(assets, list)
            or len(slots) != 4
            or len(assets) != 4
        ):
            return False
        current_candidates = self._current_video_candidates_by_slot(
            workspace, run_ref, records=records
        )
        if len(current_candidates) != 4:
            return False
        selections = (
            self.evidence.list_records(
                workspace, run_ref, record_kind=HUMAN_SELECTION
            )
            if records is None
            else [
                item
                for item in records
                if item.get("recordKind") == HUMAN_SELECTION
            ]
        )
        latest_selection_by_candidate: dict[
            tuple[str, str], dict[str, Any]
        ] = {}
        for record in selections:
            payload = record.get("payload")
            if not isinstance(payload, Mapping):
                return False
            candidate_ref = payload.get("candidateRef")
            candidate_digest = payload.get("candidateDigest")
            if isinstance(candidate_ref, str) and isinstance(
                candidate_digest, str
            ):
                latest_selection_by_candidate[
                    (candidate_ref, candidate_digest)
                ] = record
        canonical = self.candidate_review.asset_versions.list_asset_versions(
            workspace,
            run_ref,
            records=records,
            gates=gates,
        )
        latest_asset_by_logical_ref: dict[str, dict[str, Any]] = {}
        for asset in canonical:
            if str(asset.get("mediaKind", "")).lower() != "video":
                continue
            logical_ref = asset.get("assetRef")
            if not isinstance(logical_ref, str):
                return False
            prior = latest_asset_by_logical_ref.get(logical_ref)
            if prior is None or int(asset.get("version", 0)) > int(
                prior.get("version", 0)
            ):
                latest_asset_by_logical_ref[logical_ref] = asset
            elif int(asset.get("version", 0)) == int(prior.get("version", 0)):
                return False
        for slot, asset in zip(slots, assets):
            slot_ref = slot.get("slotRef")
            candidate = current_candidates.get(slot_ref)
            if (
                not isinstance(candidate, Mapping)
                or candidate.get("candidateRef") != slot.get("candidateRef")
                or candidate.get("payloadDigest") != slot.get("candidateDigest")
            ):
                return False
            try:
                qc = self.candidate_review._applicable_visual_qc(
                    workspace,
                    run_ref,
                    str(slot.get("candidateRef")),
                    records=records,
                )
            except EpisodeProductionError:
                return False
            if (
                qc is None
                or qc[0].get("recordRef") != slot.get("semanticVisualQcRef")
                or qc[0].get("payloadDigest")
                != slot.get("semanticVisualQcDigest")
                or qc[1].get("result") != "PASS"
            ):
                return False
            current_selection = latest_selection_by_candidate.get(
                (str(slot.get("candidateRef")), str(slot.get("candidateDigest")))
            )
            if (
                current_selection is None
                or current_selection.get("recordRef")
                != slot.get("humanSelectionRef")
                or current_selection.get("payloadDigest")
                != slot.get("humanSelectionDigest")
                or not isinstance(current_selection.get("payload"), Mapping)
                or current_selection["payload"].get("decision") != "SELECTED"
            ):
                return False
            current_asset = latest_asset_by_logical_ref.get(asset.get("assetRef"))
            if (
                current_asset is None
                or current_asset.get("assetVersionRef")
                != slot.get("assetVersionRef")
                or current_asset.get("payloadDigest")
                != slot.get("assetVersionDigest")
            ):
                return False
        return True

    def get_video_activation_projection(
        self,
        workspace: str,
        run_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
        gates: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Expose only the result of the strict activation validator."""

        active = self._active_video_admission(
            workspace,
            run_ref,
            records=records,
            gates=gates,
        )
        if active is None:
            return None
        manifest = active["manifest"]
        slots = active["slots"]
        return {
            "manifestRef": active["manifestRef"],
            "manifestDigest": active["manifestDigest"],
            "revisionRef": manifest.get(
                "realVideoRevisionRef", manifest.get("revisionRef")
            ),
            "revisionDigest": manifest.get("realVideoRevisionDigest"),
            "candidateIdentities": [
                {
                    "slotRef": item["slotRef"],
                    "candidateRef": item["candidateRef"],
                    "candidateDigest": item["candidateDigest"],
                }
                for item in slots
            ],
            "lineageCurrent": active["lineageCurrent"],
            "mediaKind": "VIDEO",
        }

    def _current_video_candidates_by_slot(
        self,
        workspace: str,
        run_ref: str,
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        candidate_records = (
            self.evidence.list_records(
                workspace, run_ref, record_kind=CANDIDATE
            )
            if records is None
            else [
                item for item in records if item.get("recordKind") == CANDIDATE
            ]
        )
        for record in candidate_records:
            payload = record.get("payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("mediaKind") != "VIDEO"
                or self.candidate_review._current_candidate_record(
                    workspace,
                    run_ref,
                    str(payload.get("candidateRef", "")),
                    records=records,
                )
                is None
            ):
                continue
            slot_ref = payload.get("slotRef")
            if not isinstance(slot_ref, str) or slot_ref in current:
                raise RepositoryUnavailableError(
                    "current M11 candidate coverage is ambiguous"
                )
            current[slot_ref] = deepcopy(dict(payload))
        return current

    def plan_videos(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
        }:
            raise EpisodeProductionError(
                "command fields do not match the M11 video plan contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        verified = self._verified_image_admission(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        admission_manifest = verified["realImageAdmissionManifest"]
        assets = verified["assetVersions"]
        shots = verified["creativeShotVersions"]
        if (
            graph.get("output", {}).get("totalFrames") != 720
            or [item.get("durationFrames") for item in shots]
            != [168, 168, 192, 192]
            or [item.get("ordinal") for item in assets] != [1, 2, 3, 4]
        ):
            raise StaleInputError("M11 is exact-scoped to the current K2 timeline")
        gate_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "m11-real-video-plan",
            }
        )
        existing = self.evidence.get_gate(
            workspace, run_ref, REAL_VIDEO_PLAN_GATE
        )
        if existing is not None:
            if existing.get("idempotencyKey") != gate_key:
                raise IdempotencyConflictError("M11 video plan command conflicts")
            bundle = self._video_bundle(existing)
            plan = bundle["realVideoPlan"]
            if (
                plan.get("rootPayloadDigest") != root["payloadDigest"]
                or plan.get("realImageAdmissionManifestDigest")
                != admission_manifest["payloadDigest"]
                or plan.get("sourceImageAssetVersionDigests")
                != [item["payloadDigest"] for item in assets]
                or plan.get("generationRequestDigests")
                != [
                    item["payloadDigest"]
                    for item in bundle["generationRequests"]
                ]
            ):
                raise StaleInputError("recorded M11 video plan lineage is stale")
            return {**bundle, "idempotentReplay": True}
        now = self._clock()
        assets_by_shot = {
            item["creativeShotVersionRef"]: item for item in assets
        }
        if len(assets_by_shot) != 4:
            raise StaleInputError("M10 image assets do not cover four unique shots")
        requests: list[dict[str, Any]] = []
        for shot in shots:
            asset = assets_by_shot.get(shot["creativeShotVersionRef"])
            if not isinstance(asset, Mapping):
                raise StaleInputError("M11 source image asset is missing")
            request_item = _sealed(
                {
                    "schemaVersion": REAL_VIDEO_REQUEST_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "generationRequestRef": _required_ref(
                        self._ref_factory("real-video-generation-request"),
                        "generationRequestRef",
                    ),
                    "generationRequestVersionRef": _required_ref(
                        self._ref_factory(
                            "real-video-generation-request-version"
                        ),
                        "generationRequestVersionRef",
                    ),
                    "version": 1,
                    "ordinal": shot["globalOrder"],
                    "mediaKind": "video",
                    "mediaType": "video/mp4",
                    "creativeShotRef": shot["creativeShotRef"],
                    "creativeShotVersionRef": shot[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": shot["payloadDigest"],
                    "executableShotGraphVersionRef": graph[
                        "executableShotGraphVersionRef"
                    ],
                    "executableShotGraphDigest": graph["payloadDigest"],
                    "sourceImageAssetRef": asset["assetRef"],
                    "sourceImageAssetVersionRef": asset["assetVersionRef"],
                    "sourceImageAssetVersionDigest": asset["payloadDigest"],
                    "sourceImageContentDigest": asset["sha256"],
                    "sourceImageMediaType": asset["mediaType"],
                    "sourceImageProbe": deepcopy(asset["probe"]),
                    "startImageBindingState": "EXACT_ASSET_VERSION_BOUND",
                    "promptSpec": {
                        "cameraInstruction": deepcopy(
                            shot["cameraInstruction"]
                        ),
                        "action": shot["action"],
                        "continuityConstraints": deepcopy(
                            shot["continuityConstraints"]
                        ),
                    },
                    "parameters": self._video_profile(graph, shot, asset),
                    "adapterCapability": REAL_VIDEO_CAPABILITY,
                    "executionMode": "INTERNAL_SELF_HOSTED",
                    "executionAuthorizationState": "NOT_DISPATCHED_BY_PLAN",
                    "requestedProvenance": "SELF_HOSTED_AI_GENERATED",
                    "rightsState": "NOT_REQUIRED_INTERNAL",
                    "providerPolicyState": "NOT_REQUIRED_SELF_HOSTED",
                    "budgetAuthorityState": "NOT_REQUIRED_INTERNAL",
                    "selectionRequired": True,
                    "publicationAllowed": False,
                    "createdBy": REAL_VIDEO_PLANNER_ID,
                    "createdAt": now,
                }
            )
            requests.append(request_item)
        if sum(item["parameters"]["durationFrames"] for item in requests) != 720:
            raise StaleInputError("M11 request frame total is not 720")
        plan = _sealed(
            {
                "schemaVersion": REAL_VIDEO_PLAN_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realVideoPlanRef": _required_ref(
                    self._ref_factory("real-video-plan"), "realVideoPlanRef"
                ),
                "realVideoPlanVersionRef": _required_ref(
                    self._ref_factory("real-video-plan-version"),
                    "realVideoPlanVersionRef",
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "realImageAdmissionManifestRef": admission_manifest[
                    "realImageAdmissionManifestRef"
                ],
                "realImageAdmissionManifestDigest": admission_manifest[
                    "payloadDigest"
                ],
                "sourceImageAssetVersionRefs": [
                    item["assetVersionRef"] for item in assets
                ],
                "sourceImageAssetVersionDigests": [
                    item["payloadDigest"] for item in assets
                ],
                "generationRequestRefs": [
                    item["generationRequestRef"] for item in requests
                ],
                "generationRequestDigests": [
                    item["payloadDigest"] for item in requests
                ],
                "expectedRequestCount": 4,
                "frameCounts": [168, 168, 192, 192],
                "totalFrames": 720,
                "frameRate": 24,
                "executionProfile": {
                    "width": 640,
                    "height": 352,
                    "steps": 20,
                    "samplerName": "uni_pc",
                    "scheduler": "simple",
                    "modelShift": 8.0,
                },
                "candidateSelectionState": "NOT_STARTED",
                "assetAdmissionState": "NOT_STARTED",
                "publicationAllowed": False,
                "createdBy": REAL_VIDEO_PLANNER_ID,
                "createdAt": now,
            }
        )
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "rootPayloadDigest": root["payloadDigest"],
                "realImageAdmissionManifestDigest": admission_manifest[
                    "payloadDigest"
                ],
                "sourceImageAssetVersionDigests": [
                    item["payloadDigest"] for item in assets
                ],
                "generationRequestDigests": [
                    item["payloadDigest"] for item in requests
                ],
                "plannerId": REAL_VIDEO_PLANNER_ID,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"RealVideoGenerationRequest:{item['ordinal']:04d}",
                item["generationRequestRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in requests
        )
        try:
            gate, replay = self.evidence.append_gate(
                GateAppend(
                    workspace,
                    run_ref,
                    REAL_VIDEO_PLAN_GATE,
                    gate_key,
                    root["payloadDigest"],
                    request_digest,
                    "REAL_IMAGE_READY",
                    "REAL_VIDEO_PLAN_READY",
                    now,
                    (
                        EvidenceFact(
                            "RealVideoPlan",
                            plan["realVideoPlanRef"],
                            1,
                            plan,
                            plan["payloadDigest"],
                        ),
                        *facts,
                    ),
                )
            )
        except IdempotencyConflictError:
            winner = self.evidence.get_gate(
                workspace, run_ref, REAL_VIDEO_PLAN_GATE
            )
            if winner is None or winner.get("idempotencyKey") != gate_key:
                raise
            winner_bundle = self._video_bundle(winner)
            winner_plan = winner_bundle["realVideoPlan"]
            if (
                winner_plan.get("rootPayloadDigest") != root["payloadDigest"]
                or winner_plan.get("realImageAdmissionManifestDigest")
                != admission_manifest["payloadDigest"]
                or winner_plan.get("sourceImageAssetVersionDigests")
                != [item["payloadDigest"] for item in assets]
            ):
                raise StaleInputError(
                    "concurrent M11 video plan lineage changed"
                )
            return {**winner_bundle, "idempotentReplay": True}
        return {**self._video_bundle(gate), "idempotentReplay": replay}

    def record_real_video_candidates(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Bridge exact V4 SUCCEEDED M11 jobs into canonical V5 review records."""

        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
        }:
            raise EpisodeProductionError(
                "command fields do not match the M11 candidate handoff contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        self.shot_graph.root_service.get_run(workspace, run_ref)
        gate = self.evidence.get_gate(workspace, run_ref, REAL_VIDEO_PLAN_GATE)
        if gate is None or gate.get("toState") != "REAL_VIDEO_PLAN_READY":
            raise UpstreamNotReadyError("M11 real video plan is not ready")
        bundle = self._video_bundle(gate)
        plan = bundle["realVideoPlan"]
        requests, current_revision = self._current_video_request_set(
            workspace, run_ref, bundle
        )
        try:
            resolved = self.video_candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                current_revision["realVideoRevisionRef"],
                requests,
            )
        except RealVideoCandidateEvidenceError as exc:
            raise RealVideoCandidateRejectedError(
                "M11 candidate evidence failed independent verification"
            ) from exc
        candidates = resolved.get("candidates")
        handoff = resolved.get("handoff")
        if (
            not isinstance(candidates, list)
            or len(candidates) != 4
            or not all(isinstance(item, Mapping) for item in candidates)
            or not isinstance(handoff, Mapping)
            or handoff.get("candidateCount") != 4
        ):
            raise RealVideoCandidateRejectedError(
                "M11 candidate handoff is incomplete"
            )
        existing_video_candidates: dict[str, dict[str, Any]] = {}
        for record in self.evidence.list_records(
            workspace, run_ref, record_kind=CANDIDATE
        ):
            payload = record.get("payload")
            if (
                isinstance(payload, Mapping)
                and payload.get("mediaKind") == "VIDEO"
                and self.candidate_review._current_candidate_record(
                    workspace, run_ref, str(payload.get("candidateRef", ""))
                )
                is not None
            ):
                slot_ref = payload.get("slotRef")
                if isinstance(slot_ref, str):
                    existing_video_candidates[slot_ref] = deepcopy(dict(payload))
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        prepared_records: list[EvidenceRecord] = []
        reused_candidates: list[dict[str, Any]] = []
        requests_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        for item in sorted(candidates, key=lambda value: value.get("ordinal", 0)):
            request = requests_by_ref.get(item.get("sourceRequestRef"))
            if not isinstance(request, Mapping):
                raise RealVideoCandidateRejectedError(
                    "M11 candidate source request is not current"
                )
            source_candidate_ref = _required_ref(
                item.get("candidateRef"), "candidateRef"
            )
            existing = existing_video_candidates.get(item.get("slotRef"))
            if (
                isinstance(existing, Mapping)
                and existing.get("sourceRequestRef")
                == item.get("sourceRequestRef")
                and existing.get("sourceRequestDigest")
                == item.get("sourceRequestDigest")
                and existing.get("artifactRef") == item.get("artifactRef")
                and existing.get("artifactDigest") == item.get("artifactDigest")
                and existing.get("artifactByteSize")
                == item.get("artifactByteSize")
                and existing.get("storageKey") == item.get("storageKey")
                and existing.get("provenance") == item.get("provenance")
                and existing.get("sourceAssetVersions")
                == [
                    {
                        "assetVersionRef": request[
                            "sourceImageAssetVersionRef"
                        ],
                        "assetVersionDigest": request[
                            "sourceImageAssetVersionDigest"
                        ],
                    }
                ]
            ):
                reused_candidates.append(deepcopy(dict(existing)))
                continue
            candidate_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m11-candidate",
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "ordinal": request["ordinal"],
                }
            )[:48]
            candidate_ref = source_candidate_ref
            if existing_video_candidates or current_revision.get("isSuccessor"):
                candidate_ref = (
                    "m11-video-candidate-"
                    + _digest(
                        {
                            "revisionRef": current_revision[
                                "realVideoRevisionRef"
                            ],
                            "sourceCandidateRef": source_candidate_ref,
                            "sourceRequestDigest": item.get(
                                "sourceRequestDigest"
                            ),
                            "artifactDigest": item.get("artifactDigest"),
                        }
                    )[:32]
                )
            candidate_record = self.candidate_review.prepare_candidate_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": (
                        client_key
                        if not prepared_records
                        else f"m11-candidate-{candidate_key}"
                    ),
                    "candidateRef": candidate_ref,
                    "candidateVersion": item.get("candidateVersion", 1),
                    "revisionRef": current_revision[
                        "realVideoRevisionRef"
                    ],
                    "mediaKind": "VIDEO",
                    "slotRef": item.get("slotRef"),
                    "sourceRequestRef": item.get("sourceRequestRef"),
                    "sourceRequestDigest": item.get("sourceRequestDigest"),
                    "artifactRef": item.get("artifactRef"),
                    "artifactDigest": item.get("artifactDigest"),
                    "artifactByteSize": item.get("artifactByteSize"),
                    "sourceAssetVersions": [
                        {
                            "assetVersionRef": request[
                                "sourceImageAssetVersionRef"
                            ],
                            "assetVersionDigest": request[
                                "sourceImageAssetVersionDigest"
                            ],
                        }
                    ],
                    "storageKey": item.get("storageKey"),
                    "sourceCandidateRef": source_candidate_ref,
                    "provenance": item.get("provenance"),
                    **(
                        {
                            "consumedGenerationRequest": deepcopy(
                                dict(request)
                            ),
                            "consumedRealVideoRevision": deepcopy(
                                dict(current_revision)
                            ),
                        }
                        if current_revision.get("isSuccessor")
                        else {}
                    ),
                }
            )
            candidate = deepcopy(dict(candidate_record.payload))
            validation_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m11-technical-validation",
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestDigest": request["payloadDigest"],
                    "ordinal": request["ordinal"],
                }
            )[:48]
            validation_record = (
                self.candidate_review.prepare_technical_validation_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": f"m11-technical-{validation_key}",
                    "candidateRef": candidate["candidateRef"],
                    "candidateVersion": candidate["candidateVersion"],
                    "candidateDigest": candidate["payloadDigest"],
                    "technicalValidationRef": (
                        f"m11-technical-validation-{candidate['candidateRef']}"
                    ),
                    "technicalValidationVersion": 1,
                    "validatorRef": "v4-m11-independent-verifier-v1",
                    "checks": item.get("technicalChecks"),
                    "result": "PASS",
                },
                candidate_record=candidate_record,
                )
            )
            prepared_records.extend((candidate_record, validation_record))
        if prepared_records:
            stored, replayed = self.evidence.append_records(
                prepared_records,
                expected_record_journal_head=expected_record_journal_head,
            )
        else:
            stored = []
            replayed = True
        candidate_results = [
            deepcopy(dict(item["payload"]))
            for item in stored
            if item.get("recordKind") == CANDIDATE
        ]
        validation_results = [
            deepcopy(dict(item["payload"]))
            for item in stored
            if item.get("recordKind") == TECHNICAL_VALIDATION
        ]
        lifecycle = self.candidate_review.get_projection(workspace, run_ref)
        projection_service = getattr(self, "state_projection", None)
        if projection_service is not None:
            lifecycle = projection_service.get_projection(
                workspace, run_ref
            )["candidateLifecycle"]
        return {
            "state": self.evidence.current_state(workspace, run_ref),
            "candidateHandoff": deepcopy(dict(handoff)),
            "candidates": candidate_results,
            "reusedCandidates": sorted(
                reused_candidates, key=lambda item: item.get("slotRef", "")
            ),
            "technicalValidations": validation_results,
            "candidateLifecycle": lifecycle,
            "idempotentReplay": replayed,
            "publicationAllowed": False,
        }

    def admit_real_videos(self, command: Mapping[str, Any]) -> dict[str, Any]:
        """Select and admit one exact PASS candidate for every M11 slot atomically."""

        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "selections",
        }:
            raise EpisodeProductionError(
                "command fields do not match the M11 admission contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        selections = command.get("selections")
        if (
            not isinstance(selections, list)
            or not 1 <= len(selections) <= 4
            or not all(isinstance(item, Mapping) for item in selections)
        ):
            raise EpisodeProductionError(
                "M11 requires one to four exact selections"
            )
        selection_fields = {
            "visualQcRef",
            "visualQcVersion",
            "visualQcDigest",
            "selectionRef",
            "selectionVersion",
            "approvalRef",
        }
        normalized_selection_requests: list[dict[str, Any]] = []
        for item in selections:
            if set(item) != selection_fields:
                raise EpisodeProductionError(
                    "M11 selection fields do not match the contract"
                )
            version = item.get("visualQcVersion")
            selection_version = item.get("selectionVersion")
            if (
                isinstance(version, bool)
                or not isinstance(version, int)
                or version < 1
                or isinstance(selection_version, bool)
                or not isinstance(selection_version, int)
                or selection_version < 1
            ):
                raise EpisodeProductionError("M11 selection version is invalid")
            normalized_selection_requests.append(
                {
                    "visualQcRef": _required_ref(
                        item.get("visualQcRef"), "visualQcRef"
                    ),
                    "visualQcVersion": version,
                    "visualQcDigest": _content_digest(
                        item.get("visualQcDigest"), "visualQcDigest"
                    ),
                    "selectionRef": _required_ref(
                        item.get("selectionRef"), "selectionRef"
                    ),
                    "selectionVersion": selection_version,
                    "approvalRef": _required_ref(
                        item.get("approvalRef"), "approvalRef"
                    ),
                }
            )
        if len(
            {item["selectionRef"] for item in normalized_selection_requests}
        ) != len(normalized_selection_requests):
            raise EpisodeProductionError("M11 selection refs are ambiguous")
        selection_request_digest = _digest(
            {
                "selections": sorted(
                    normalized_selection_requests,
                    key=lambda item: item["selectionRef"],
                )
            }
        )
        plan_gate = self.evidence.get_gate(
            workspace, run_ref, REAL_VIDEO_PLAN_GATE
        )
        if plan_gate is None:
            raise UpstreamNotReadyError("M11 real video plan is not ready")
        plan_bundle = self._video_bundle(plan_gate)
        plan = plan_bundle["realVideoPlan"]
        requests, current_revision = self._current_video_request_set(
            workspace, run_ref, plan_bundle
        )
        gate_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "m11-real-video-admission",
            }
        )
        existing = self.evidence.get_gate(
            workspace, run_ref, REAL_VIDEO_ADMISSION_GATE
        )
        production_state = self.evidence.current_state(workspace, run_ref)
        if existing is not None and existing.get("idempotencyKey") == gate_key:
            replay_bundle = self._video_admission_bundle(existing)
            if (
                replay_bundle["realVideoAdmissionManifest"].get(
                    "selectionRequestDigest"
                )
                != selection_request_digest
            ):
                raise IdempotencyConflictError(
                    "M11 admission selection content changed"
                )
            return {**replay_bundle, "idempotentReplay": True}
        if production_state == "REAL_VIDEO_READY":
            return self._admit_real_video_successor(
                workspace=workspace,
                run_ref=run_ref,
                client_key=client_key,
                selections=normalized_selection_requests,
                selection_request_digest=selection_request_digest,
                plan=plan,
                requests=requests,
                current_revision=current_revision,
            )
        if existing is not None:
            raise IdempotencyConflictError("M11 admission command conflicts")
        if production_state != "REAL_VIDEO_PLAN_READY":
            raise StaleInputError("M11 admission state changed")
        if len(normalized_selection_requests) != 4:
            raise EpisodeProductionError(
                "initial M11 admission requires four exact selections"
            )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        requests_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        canonical_assets = self.candidate_review.asset_versions.list_asset_versions(
            workspace, run_ref
        )
        predecessor_by_shot: dict[str, dict[str, Any]] = {}
        for asset in canonical_assets:
            if str(asset.get("mediaKind", "")).lower() != "video":
                continue
            shot_ref = asset.get("creativeShotVersionRef")
            if not isinstance(shot_ref, str):
                continue
            current = predecessor_by_shot.get(shot_ref)
            if current is None or int(asset.get("version", 0)) > int(
                current.get("version", 0)
            ):
                predecessor_by_shot[shot_ref] = asset
        prepared: list[
            tuple[int, EvidenceRecord, dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = []
        now = self._clock()
        for item in normalized_selection_requests:
            selection_key = _digest(
                {
                    "gateKey": gate_key,
                    "selectionRef": item["selectionRef"],
                    "selectionRequestDigest": selection_request_digest,
                }
            )[:48]
            record = self.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": f"m11-selected-{selection_key}",
                    "visualQcRef": item["visualQcRef"],
                    "visualQcVersion": item["visualQcVersion"],
                    "visualQcDigest": item["visualQcDigest"],
                    "selectionRef": item["selectionRef"],
                    "selectionVersion": item["selectionVersion"],
                    "approvalRef": item["approvalRef"],
                    "decision": "SELECTED",
                }
            )
            selection = deepcopy(dict(record.payload))
            candidate_record = self.evidence.get_record(
                workspace,
                run_ref,
                selection["candidateRef"],
                selection["candidateVersion"],
            )
            if (
                candidate_record is None
                or candidate_record.get("recordKind") != "Candidate"
                or candidate_record.get("payloadDigest")
                != selection["candidateDigest"]
                or not isinstance(candidate_record.get("payload"), Mapping)
            ):
                raise StaleInputError("M11 selected candidate changed")
            candidate = deepcopy(dict(candidate_record["payload"]))
            current_candidate = self.candidate_review._current_candidate_record(
                workspace, run_ref, candidate["candidateRef"]
            )
            request = requests_by_ref.get(candidate.get("sourceRequestRef"))
            if (
                not isinstance(request, Mapping)
                or current_candidate is None
                or current_candidate.get("payloadDigest")
                != candidate.get("payloadDigest")
                or candidate.get("sourceRequestDigest")
                != request.get("payloadDigest")
                or candidate.get("slotRef")
                != request.get("creativeShotVersionRef")
                or candidate.get("artifactDigest")
                != selection.get("artifactDigest")
                or candidate.get("sourceAssetVersions")
                != [
                    {
                        "assetVersionRef": request.get(
                            "sourceImageAssetVersionRef"
                        ),
                        "assetVersionDigest": request.get(
                            "sourceImageAssetVersionDigest"
                        ),
                    }
                ]
            ):
                raise StaleInputError("M11 candidate request lineage changed")
            predecessor = predecessor_by_shot.get(
                request["creativeShotVersionRef"]
            )
            if predecessor is None:
                raise UpstreamNotReadyError(
                    "M11 predecessor video AssetVersion is unavailable"
                )
            ordinal = int(request["ordinal"])
            asset = _sealed(
                {
                    "schemaVersion": REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "assetRef": predecessor["assetRef"],
                    "assetVersionRef": _required_ref(
                        self._ref_factory("real-video-asset-version"),
                        "assetVersionRef",
                    ),
                    "version": int(predecessor["version"]) + 1,
                    "ordinal": ordinal,
                    "creativeShotRef": request["creativeShotRef"],
                    "creativeShotVersionRef": request[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": request["creativeShotDigest"],
                    "generationRequestRef": request[
                        "generationRequestRef"
                    ],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "sourceImageAssetVersionRef": request[
                        "sourceImageAssetVersionRef"
                    ],
                    "sourceImageAssetVersionDigest": request[
                        "sourceImageAssetVersionDigest"
                    ],
                    "sourceCandidateRef": candidate["candidateRef"],
                    "sourceCandidateDigest": candidate["payloadDigest"],
                    "revisionRef": candidate["revisionRef"],
                    "sourceRuntimeCandidateRef": candidate.get(
                        "sourceCandidateRef", candidate["candidateRef"]
                    ),
                    "semanticVisualQcRef": selection["visualQcRef"],
                    "semanticVisualQcDigest": selection["visualQcDigest"],
                    "humanSelectionRef": record.recordRef,
                    "humanSelectionVersion": record.recordVersion,
                    "humanSelectionDigest": record.payloadDigest,
                    "supersedesAssetVersionRef": predecessor[
                        "assetVersionRef"
                    ],
                    "supersedesAssetVersionDigest": predecessor[
                        "payloadDigest"
                    ],
                    "mediaKind": "video",
                    "mediaType": "video/mp4",
                    "artifactRef": candidate["artifactRef"],
                    "storageKey": candidate.get("storageKey"),
                    "byteSize": candidate["artifactByteSize"],
                    "sha256": candidate["artifactDigest"],
                    "provenance": candidate["provenance"],
                    "state": "REGISTERED",
                    "immutable": True,
                    "publicationAllowed": False,
                    "createdBy": "v5.k2.real-video-admission.v1",
                    "createdAt": now,
                }
            )
            admission = _sealed(
                {
                    "schemaVersion": "v5.k2-asset-admission.v1",
                    "admissionRef": _required_ref(
                        self._ref_factory("real-video-admission"),
                        "admissionRef",
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
                    "selectionRef": record.recordRef,
                    "selectionVersion": record.recordVersion,
                    "selectionDigest": record.payloadDigest,
                    "assetVersionRef": asset["assetVersionRef"],
                    "assetVersionDigest": asset["payloadDigest"],
                    "admissionState": "ADMITTED",
                    "publicationAllowed": False,
                    "createdAt": now,
                }
            )
            prepared.append((ordinal, record, selection, admission, asset))
        prepared.sort(key=lambda item: item[0])
        if (
            [item[0] for item in prepared] != [1, 2, 3, 4]
            or len({item[2]["candidateRef"] for item in prepared}) != 4
            or len(
                {
                    item[1].payload["authorityDecisionRef"]
                    for item in prepared
                }
            )
            != 4
            or len(
                {
                    item[1].payload["authorityDecisionDigest"]
                    for item in prepared
                }
            )
            != 4
        ):
            raise RealVideoCandidateRejectedError(
                "M11 admission does not cover four unique timeline slots"
            )

        # The Candidate record proves what was verified at handoff time; it
        # does not make mutable filesystem bytes authoritative.  Re-resolve
        # the V4 handoff at the admission consumption boundary so deletion,
        # replacement, changed probe output or changed execution lineage fails
        # before any HumanSelection/AssetAdmission/AssetVersion is appended.
        try:
            live_handoff = self.video_candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                current_revision["realVideoRevisionRef"],
                requests,
            )
        except RealVideoCandidateEvidenceError as exc:
            raise RealVideoCandidateRejectedError(
                "M11 selected artifact bytes are no longer verifiable"
            ) from exc
        if not isinstance(live_handoff, Mapping):
            raise RealVideoCandidateRejectedError(
                "M11 admission handoff is invalid"
            )
        live_candidates = live_handoff.get("candidates")
        if (
            not isinstance(live_candidates, list)
            or len(live_candidates) != 4
            or not all(isinstance(item, Mapping) for item in live_candidates)
        ):
            raise RealVideoCandidateRejectedError(
                "M11 admission handoff is incomplete"
            )
        live_by_ref = {
            item.get("candidateRef"): item for item in live_candidates
        }
        for _, _, _, _, candidate_asset in prepared:
            live = live_by_ref.get(
                candidate_asset.get(
                    "sourceRuntimeCandidateRef",
                    candidate_asset["sourceCandidateRef"],
                )
            )
            if (
                not isinstance(live, Mapping)
                or live.get("artifactDigest") != candidate_asset["sha256"]
                or live.get("artifactByteSize") != candidate_asset["byteSize"]
                or live.get("storageKey") != candidate_asset.get("storageKey")
                or live.get("artifactRef") != candidate_asset["artifactRef"]
                or live.get("sourceRequestRef")
                != candidate_asset["generationRequestRef"]
                or live.get("sourceRequestDigest")
                != candidate_asset["generationRequestDigest"]
                or live.get("slotRef")
                != candidate_asset["creativeShotVersionRef"]
                or live.get("provenance") != candidate_asset["provenance"]
            ):
                raise RealVideoCandidateRejectedError(
                    "M11 selected artifact bytes or lineage changed"
                )
        selection_records = [item[1] for item in prepared]
        admissions = [item[3] for item in prepared]
        admitted = [item[4] for item in prepared]
        manifest_revision_ref = (
            prepared[0][4]["revisionRef"]
            if len({item[4]["revisionRef"] for item in prepared}) == 1
            else (
                "m11-video-admission-revision-"
                + _digest(
                    {
                        "realVideoRevisionDigest": current_revision[
                            "payloadDigest"
                        ],
                        "candidateDigests": [
                            item[4]["sourceCandidateDigest"] for item in prepared
                        ],
                    }
                )[:32]
            )
        )
        manifest = _sealed(
            {
                "schemaVersion": REAL_VIDEO_ADMISSION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realVideoAdmissionManifestRef": _required_ref(
                    self._ref_factory("real-video-admission-manifest"),
                    "realVideoAdmissionManifestRef",
                ),
                "version": 1,
                "realVideoPlanRef": plan["realVideoPlanRef"],
                "realVideoPlanDigest": plan["payloadDigest"],
                "revisionRef": manifest_revision_ref,
                "realVideoRevisionRef": current_revision[
                    "realVideoRevisionRef"
                ],
                "realVideoRevisionDigest": current_revision["payloadDigest"],
                "selectionRequestDigest": selection_request_digest,
                "candidateRefs": [
                    item[4]["sourceCandidateRef"] for item in prepared
                ],
                "candidateDigests": [
                    item[4]["sourceCandidateDigest"] for item in prepared
                ],
                "selectionRefs": [item.recordRef for item in selection_records],
                "selectionDigests": [
                    item.payloadDigest for item in selection_records
                ],
                "assetVersionRefs": [item["assetVersionRef"] for item in admitted],
                "assetVersionDigests": [item["payloadDigest"] for item in admitted],
                "admittedCount": 4,
                "state": "REAL_VIDEO_ADMITTED",
                "publicationAllowed": False,
                "createdAt": now,
            }
        )
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "realVideoPlanDigest": plan["payloadDigest"],
                "realVideoRevisionDigest": current_revision["payloadDigest"],
                "selectionDigests": [
                    item.payloadDigest for item in selection_records
                ],
                "assetVersionDigests": [item["payloadDigest"] for item in admitted],
            }
        )
        facts = tuple(
            EvidenceFact(
                f"AssetAdmission:M11:{item['ordinal']:04d}",
                item["admissionRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in admissions
        ) + tuple(
            EvidenceFact(
                f"AssetVersion:M11:{item['ordinal']:04d}",
                item["assetVersionRef"],
                item["version"],
                item,
                item["payloadDigest"],
            )
            for item in admitted
        ) + (
            EvidenceFact(
                "RealVideoAdmissionManifest",
                manifest["realVideoAdmissionManifestRef"],
                1,
                manifest,
                manifest["payloadDigest"],
            ),
        )
        admission_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_ADMISSION,
                record_ref=item["admissionRef"],
                record_version=item["version"],
                idempotency_key=(
                    "m11-admission-"
                    + _digest(
                        {
                            "gateKey": gate_key,
                            "admissionRef": item["admissionRef"],
                        }
                    )[:48]
                ),
                created_at=now,
                payload=item,
            )
            for item in admissions
        ]
        asset_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_VERSION,
                record_ref=item["assetVersionRef"],
                record_version=item["version"],
                idempotency_key=(
                    "m11-asset-version-"
                    + _digest(
                        {
                            "gateKey": gate_key,
                            "assetVersionRef": item["assetVersionRef"],
                        }
                    )[:48]
                ),
                created_at=now,
                payload=item,
            )
            for item in admitted
        ]
        gate_append = GateAppend(
            workspace,
            run_ref,
            REAL_VIDEO_ADMISSION_GATE,
            gate_key,
            plan_gate["rootPayloadDigest"],
            request_digest,
            "REAL_VIDEO_PLAN_READY",
            "REAL_VIDEO_READY",
            now,
            facts,
        )
        try:
            _, gate, replayed = self.evidence.append_records_and_gate(
                (*selection_records, *admission_records, *asset_records),
                gate_append,
                expected_record_journal_head=expected_record_journal_head,
            )
        except IdempotencyConflictError:
            # A concurrent exact retry may win after the pre-read but before
            # BEGIN IMMEDIATE.  Only the same closed-world selection request is
            # a replay; any changed input remains a hard conflict.
            concurrent = self.evidence.get_gate(
                workspace, run_ref, REAL_VIDEO_ADMISSION_GATE
            )
            if (
                concurrent is None
                or concurrent.get("idempotencyKey") != gate_key
                or self._video_admission_bundle(concurrent)[
                    "realVideoAdmissionManifest"
                ].get("selectionRequestDigest")
                != selection_request_digest
            ):
                raise
            gate = concurrent
            replayed = True
        return {**self._video_admission_bundle(gate), "idempotentReplay": replayed}

    def _video_successor_replay(
        self,
        workspace: str,
        run_ref: str,
        client_key: str,
        selection_request_digest: str,
    ) -> dict[str, Any] | None:
        matches = [
            item
            for item in self.evidence.list_records(workspace, run_ref)
            if item.get("idempotencyKey") == client_key
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise RepositoryUnavailableError(
                "M11 successor operation idempotency is ambiguous"
            )
        operation_record = matches[0]
        activations = [
            item
            for item in self.evidence.list_records(
                workspace, run_ref, record_kind=ASSET_ADMISSION
            )
            if isinstance(item.get("payload"), Mapping)
            and item["payload"].get("schemaVersion")
            == REAL_VIDEO_SUCCESSOR_ACTIVATION_SCHEMA_VERSION
            and item["payload"].get("operationIdempotencyKey") == client_key
        ]
        if (
            operation_record.get("recordKind") != HUMAN_SELECTION
            or len(activations) != 1
            or activations[0]["payload"].get("selectionRequestDigest")
            != selection_request_digest
        ):
            raise IdempotencyConflictError(
                "M11 successor admission command conflicts"
            )
        payload = activations[0]["payload"]
        activation = self._assert_sealed_payload(
            payload, "M11 successor replay activation"
        )
        raw_payload = operation_record.get("payload")
        if (
            not isinstance(raw_payload, Mapping)
            or not any(
                item.get("humanSelectionRef")
                == operation_record.get("recordRef")
                and item.get("humanSelectionDigest")
                == operation_record.get("payloadDigest")
                for item in activation.get("slotActivations", [])
                if isinstance(item, Mapping)
            )
        ):
            raise RepositoryUnavailableError(
                "M11 successor operation anchor is not in the activation"
            )
        canonical = {
            item["assetVersionRef"]: item
            for item in self.candidate_review.asset_versions.list_asset_versions(
                workspace, run_ref
            )
            if str(item.get("mediaKind", "")).lower() == "video"
        }
        assets = [canonical.get(ref) for ref in activation["assetVersionRefs"]]
        if (
            any(not isinstance(item, Mapping) for item in assets)
            or [item.get("payloadDigest") for item in assets]
            != activation.get("assetVersionDigests")
        ):
            raise RepositoryUnavailableError(
                "M11 successor replay AssetVersions are incomplete"
            )
        active = self._active_video_admission(workspace, run_ref)
        if (
            active is None
            or active.get("manifestRef") != activation.get("admissionRef")
            or active.get("manifestDigest") != activation.get("payloadDigest")
        ):
            # Historical replay remains addressable after a later activation.
            admission_index: dict[str, dict[str, Any]] = {}
            gate = self.evidence.get_gate(
                workspace, run_ref, REAL_VIDEO_ADMISSION_GATE
            )
            if gate is not None:
                for item in self._video_admission_bundle(gate)["assetAdmissions"]:
                    admission_index[item["admissionRef"]] = item
            for item in self.evidence.list_records(
                workspace, run_ref, record_kind=ASSET_ADMISSION
            ):
                item_payload = item.get("payload")
                if (
                    isinstance(item_payload, Mapping)
                    and item_payload.get("schemaVersion")
                    == "v5.k2-asset-admission.v1"
                ):
                    admission_index[item_payload["admissionRef"]] = deepcopy(
                        dict(item_payload)
                    )
            item_admissions = [
                admission_index.get(item.get("assetAdmissionRef"))
                for item in activation.get("slotActivations", [])
            ]
        else:
            item_admissions = active["admissions"]
        if (
            len(item_admissions) != 4
            or any(not isinstance(item, Mapping) for item in item_admissions)
            or [item.get("payloadDigest") for item in item_admissions]
            != [
                item.get("assetAdmissionDigest")
                for item in activation.get("slotActivations", [])
            ]
        ):
            raise RepositoryUnavailableError(
                "M11 successor replay item admissions are incomplete"
            )
        return {
            "realVideoAdmissionManifest": activation,
            "assetAdmissions": [deepcopy(dict(item)) for item in item_admissions],
            "assetVersions": [deepcopy(dict(item)) for item in assets],
            "state": self.evidence.current_state(workspace, run_ref),
            "idempotentReplay": True,
            "publicationAllowed": False,
        }

    def _admit_real_video_successor(
        self,
        *,
        workspace: str,
        run_ref: str,
        client_key: str,
        selections: Sequence[Mapping[str, Any]],
        selection_request_digest: str,
        plan: Mapping[str, Any],
        requests: Sequence[Mapping[str, Any]],
        current_revision: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Atomically activate changed slots while reusing three current chains."""

        replay = self._video_successor_replay(
            workspace, run_ref, client_key, selection_request_digest
        )
        if replay is not None:
            return replay
        active = self._active_video_admission(workspace, run_ref)
        if active is None:
            raise UpstreamNotReadyError(
                "an admitted M11 video baseline is required"
            )
        active_by_slot = {
            item["creativeShotVersionRef"]: item for item in active["assets"]
        }
        requests_by_slot = {
            item["creativeShotVersionRef"]: item for item in requests
        }
        if len(active_by_slot) != 4 or len(requests_by_slot) != 4:
            raise RepositoryUnavailableError(
                "M11 active or requested slot coverage is invalid"
            )
        current_candidates_by_slot = self._current_video_candidates_by_slot(
            workspace, run_ref
        )
        changed_slots = {
            slot_ref
            for slot_ref, request in requests_by_slot.items()
            if (
                active_by_slot[slot_ref].get("generationRequestDigest")
                != request.get("payloadDigest")
                or active_by_slot[slot_ref].get("sourceImageAssetVersionRef")
                != request.get("sourceImageAssetVersionRef")
                or active_by_slot[slot_ref].get("sourceImageAssetVersionDigest")
                != request.get("sourceImageAssetVersionDigest")
                or not isinstance(current_candidates_by_slot.get(slot_ref), Mapping)
                or active_by_slot[slot_ref].get("sourceCandidateRef")
                != current_candidates_by_slot.get(slot_ref, {}).get("candidateRef")
                or active_by_slot[slot_ref].get("sourceCandidateDigest")
                != current_candidates_by_slot.get(slot_ref, {}).get("payloadDigest")
            )
        }
        if not changed_slots:
            raise IdempotencyConflictError(
                "M11 successor admission has no changed current slot"
            )
        if len(selections) != len(changed_slots):
            raise EpisodeProductionError(
                "M11 successor selections must cover exactly the changed slots"
            )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        now = self._clock()
        prepared: list[
            tuple[int, EvidenceRecord, dict[str, Any], dict[str, Any], dict[str, Any]]
        ] = []
        for selection_input in selections:
            selection_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m11-successor-selection",
                    "selectionRef": selection_input["selectionRef"],
                    "selectionRequestDigest": selection_request_digest,
                }
            )[:48]
            selection_record = self.candidate_review.prepare_human_selection_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": f"m11-successor-selected-{selection_key}",
                    **dict(selection_input),
                    "decision": "SELECTED",
                }
            )
            selection = deepcopy(dict(selection_record.payload))
            candidate_record = self.evidence.get_record(
                workspace,
                run_ref,
                selection["candidateRef"],
                selection["candidateVersion"],
            )
            if (
                candidate_record is None
                or candidate_record.get("recordKind") != CANDIDATE
                or candidate_record.get("payloadDigest")
                != selection.get("candidateDigest")
                or not isinstance(candidate_record.get("payload"), Mapping)
            ):
                raise StaleInputError("M11 successor candidate changed")
            candidate = deepcopy(dict(candidate_record["payload"]))
            slot_ref = candidate.get("slotRef")
            request = requests_by_slot.get(slot_ref)
            current_candidate = self.candidate_review._current_candidate_record(
                workspace, run_ref, candidate.get("candidateRef")
            )
            if (
                slot_ref not in changed_slots
                or not isinstance(request, Mapping)
                or current_candidate is None
                or current_candidate.get("payloadDigest")
                != candidate.get("payloadDigest")
                or candidate.get("revisionRef")
                != current_revision.get("realVideoRevisionRef")
                or candidate.get("sourceRequestRef")
                != request.get("generationRequestRef")
                or candidate.get("sourceRequestDigest")
                != request.get("payloadDigest")
                or candidate.get("sourceAssetVersions")
                != [
                    {
                        "assetVersionRef": request.get(
                            "sourceImageAssetVersionRef"
                        ),
                        "assetVersionDigest": request.get(
                            "sourceImageAssetVersionDigest"
                        ),
                    }
                ]
                or (
                    current_revision.get("isSuccessor") is True
                    and (
                        candidate.get("consumedGenerationRequest") != request
                        or candidate.get("consumedRealVideoRevision")
                        != current_revision
                    )
                )
                or (
                    current_revision.get("isSuccessor") is not True
                    and (
                        "consumedGenerationRequest" in candidate
                        or "consumedRealVideoRevision" in candidate
                    )
                )
            ):
                raise StaleInputError(
                    "M11 successor candidate request lineage changed"
                )
            predecessor = active_by_slot[slot_ref]
            ordinal = int(request["ordinal"])
            asset = _sealed(
                {
                    "schemaVersion": REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "assetRef": predecessor["assetRef"],
                    "assetVersionRef": _required_ref(
                        self._ref_factory("real-video-asset-version"),
                        "assetVersionRef",
                    ),
                    "version": int(predecessor["version"]) + 1,
                    "ordinal": ordinal,
                    "creativeShotRef": request["creativeShotRef"],
                    "creativeShotVersionRef": slot_ref,
                    "creativeShotDigest": request["creativeShotDigest"],
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "sourceImageAssetVersionRef": request[
                        "sourceImageAssetVersionRef"
                    ],
                    "sourceImageAssetVersionDigest": request[
                        "sourceImageAssetVersionDigest"
                    ],
                    "sourceCandidateRef": candidate["candidateRef"],
                    "sourceCandidateDigest": candidate["payloadDigest"],
                    "revisionRef": current_revision["realVideoRevisionRef"],
                    "sourceRuntimeCandidateRef": candidate.get(
                        "sourceCandidateRef", candidate["candidateRef"]
                    ),
                    "semanticVisualQcRef": selection["visualQcRef"],
                    "semanticVisualQcDigest": selection["visualQcDigest"],
                    "humanSelectionRef": selection_record.recordRef,
                    "humanSelectionVersion": selection_record.recordVersion,
                    "humanSelectionDigest": selection_record.payloadDigest,
                    "supersedesAssetVersionRef": predecessor[
                        "assetVersionRef"
                    ],
                    "supersedesAssetVersionDigest": predecessor[
                        "payloadDigest"
                    ],
                    "mediaKind": "video",
                    "mediaType": "video/mp4",
                    "artifactRef": candidate["artifactRef"],
                    "storageKey": candidate.get("storageKey"),
                    "byteSize": candidate["artifactByteSize"],
                    "sha256": candidate["artifactDigest"],
                    "provenance": candidate["provenance"],
                    "state": "REGISTERED",
                    "immutable": True,
                    "publicationAllowed": False,
                    "createdBy": "v5.k2.real-video-successor-admission.v2",
                    "createdAt": now,
                }
            )
            admission = _sealed(
                {
                    "schemaVersion": "v5.k2-asset-admission.v1",
                    "admissionRef": _required_ref(
                        self._ref_factory("real-video-successor-admission"),
                        "admissionRef",
                    ),
                    "version": 1,
                    "ordinal": ordinal,
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
                    "selectionRef": selection_record.recordRef,
                    "selectionVersion": selection_record.recordVersion,
                    "selectionDigest": selection_record.payloadDigest,
                    "assetVersionRef": asset["assetVersionRef"],
                    "assetVersionVersion": asset["version"],
                    "assetVersionDigest": asset["payloadDigest"],
                    "admissionState": "ADMITTED",
                    "publicationAllowed": False,
                    "createdAt": now,
                }
            )
            prepared.append(
                (ordinal, selection_record, candidate, admission, asset)
            )
        prepared.sort(key=lambda item: item[0])
        if {item[2]["slotRef"] for item in prepared} != changed_slots:
            raise RealVideoCandidateRejectedError(
                "M11 successor admission does not cover changed slots"
            )

        final_by_slot = {slot: deepcopy(asset) for slot, asset in active_by_slot.items()}
        active_admission_by_ordinal = {
            item["ordinal"]: item for item in active["admissions"]
        }
        final_admission_by_ordinal = {
            ordinal: deepcopy(item)
            for ordinal, item in active_admission_by_ordinal.items()
        }
        for _, _, candidate, _, asset in prepared:
            final_by_slot[candidate["slotRef"]] = asset
        for ordinal, _, _, admission, _ in prepared:
            final_admission_by_ordinal[ordinal] = admission
        final_assets = sorted(final_by_slot.values(), key=lambda item: item["ordinal"])
        final_admissions = [
            final_admission_by_ordinal[ordinal] for ordinal in (1, 2, 3, 4)
        ]

        # Every activated artifact, including the three reused chains, is
        # rehashed/re-probed by V4 immediately before the atomic V5 append.
        try:
            live_handoff = self.video_candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                current_revision["realVideoRevisionRef"],
                requests,
            )
        except RealVideoCandidateEvidenceError as exc:
            raise RealVideoCandidateRejectedError(
                "M11 successor artifact bytes are no longer verifiable"
            ) from exc
        live_candidates = (
            live_handoff.get("candidates")
            if isinstance(live_handoff, Mapping)
            else None
        )
        if (
            not isinstance(live_candidates, list)
            or len(live_candidates) != 4
            or not all(isinstance(item, Mapping) for item in live_candidates)
        ):
            raise RealVideoCandidateRejectedError(
                "M11 successor admission handoff is incomplete"
            )
        live_by_ref = {item.get("candidateRef"): item for item in live_candidates}
        for asset in final_assets:
            live = live_by_ref.get(
                asset.get(
                    "sourceRuntimeCandidateRef", asset["sourceCandidateRef"]
                )
            )
            if (
                not isinstance(live, Mapping)
                or live.get("artifactDigest") != asset.get("sha256")
                or live.get("artifactByteSize") != asset.get("byteSize")
                or live.get("storageKey") != asset.get("storageKey")
                or live.get("artifactRef") != asset.get("artifactRef")
                or live.get("sourceRequestRef")
                != asset.get("generationRequestRef")
                or live.get("sourceRequestDigest")
                != asset.get("generationRequestDigest")
                or live.get("slotRef")
                != asset.get("creativeShotVersionRef")
                or live.get("provenance") != asset.get("provenance")
            ):
                raise RealVideoCandidateRejectedError(
                    "M11 successor artifact bytes or lineage changed"
                )

        changed_by_slot = {item[2]["slotRef"]: item for item in prepared}
        admission_by_ordinal = {
            item["ordinal"]: item for item in final_admissions
        }
        slots: list[dict[str, Any]] = []
        for asset in final_assets:
            slot_ref = asset["creativeShotVersionRef"]
            request = requests_by_slot[slot_ref]
            slots.append(
                {
                    "ordinal": asset["ordinal"],
                    "slotRef": slot_ref,
                    "generationRequestRef": request["generationRequestRef"],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "candidateRef": asset["sourceCandidateRef"],
                    "candidateDigest": asset["sourceCandidateDigest"],
                    "semanticVisualQcRef": asset["semanticVisualQcRef"],
                    "semanticVisualQcDigest": asset[
                        "semanticVisualQcDigest"
                    ],
                    "humanSelectionRef": asset["humanSelectionRef"],
                    "humanSelectionDigest": asset["humanSelectionDigest"],
                    "assetAdmissionRef": admission_by_ordinal[
                        asset["ordinal"]
                    ]["admissionRef"],
                    "assetAdmissionDigest": admission_by_ordinal[
                        asset["ordinal"]
                    ]["payloadDigest"],
                    "assetVersionRef": asset["assetVersionRef"],
                    "assetVersionDigest": asset["payloadDigest"],
                    "activationSource": (
                        "NEW_ADMISSION"
                        if slot_ref in changed_by_slot
                        else "REUSED_CURRENT"
                    ),
                }
            )
        activation_version = int(active["manifest"].get("version", 1)) + 1
        activation = _sealed(
            {
                "schemaVersion": REAL_VIDEO_SUCCESSOR_ACTIVATION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "admissionRef": _required_ref(
                    self._ref_factory("real-video-batch-activation"),
                    "admissionRef",
                ),
                "version": activation_version,
                "admissionState": "ACTIVATED",
                "realVideoPlanRef": plan["realVideoPlanRef"],
                "realVideoPlanDigest": plan["payloadDigest"],
                "realVideoRevisionRef": current_revision[
                    "realVideoRevisionRef"
                ],
                "realVideoRevisionDigest": current_revision["payloadDigest"],
                "supersedesActivationRef": active["manifestRef"],
                "supersedesActivationDigest": active["manifestDigest"],
                "operationIdempotencyKey": client_key,
                "selectionRequestDigest": selection_request_digest,
                "changedSlotRefs": sorted(changed_slots),
                "slotActivations": slots,
                "assetVersionRefs": [
                    item["assetVersionRef"] for item in final_assets
                ],
                "assetVersionDigests": [
                    item["payloadDigest"] for item in final_assets
                ],
                "newAdmissionRefs": [item[3]["admissionRef"] for item in prepared],
                "newAdmissionDigests": [
                    item[3]["payloadDigest"] for item in prepared
                ],
                "newAdmissionCount": len(prepared),
                "reusedAdmissionCount": 4 - len(prepared),
                "state": "REAL_VIDEO_ADMITTED",
                "publicationAllowed": False,
                "createdAt": now,
            }
        )
        activation_record = _record(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            record_kind=ASSET_ADMISSION,
            record_ref=activation["admissionRef"],
            record_version=activation["version"],
            idempotency_key=(
                "m11-successor-activation-"
                + _digest(
                    {
                        "clientIdempotencyKey": client_key,
                        "activationDigest": activation["payloadDigest"],
                    }
                )[:40]
            ),
            created_at=now,
            payload=activation,
        )
        selection_records = [item[1] for item in prepared]
        first_selection = selection_records[0]
        selection_records[0] = _record(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            record_kind=HUMAN_SELECTION,
            record_ref=first_selection.recordRef,
            record_version=first_selection.recordVersion,
            idempotency_key=client_key,
            created_at=first_selection.createdAt,
            payload=first_selection.payload,
        )
        admission_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_ADMISSION,
                record_ref=item[3]["admissionRef"],
                record_version=item[3]["version"],
                idempotency_key=(
                    "m11-successor-admission-"
                    + _digest(
                        {
                            "clientIdempotencyKey": client_key,
                            "admissionDigest": item[3]["payloadDigest"],
                        }
                    )[:40]
                ),
                created_at=now,
                payload=item[3],
            )
            for item in prepared
        ]
        asset_records = [
            _record(
                workspace_ref=workspace,
                production_run_ref=run_ref,
                record_kind=ASSET_VERSION,
                record_ref=item[4]["assetVersionRef"],
                record_version=item[4]["version"],
                idempotency_key=(
                    "m11-successor-asset-"
                    + _digest(
                        {
                            "clientIdempotencyKey": client_key,
                            "assetVersionDigest": item[4]["payloadDigest"],
                        }
                    )[:40]
                ),
                created_at=now,
                payload=item[4],
            )
            for item in prepared
        ]
        try:
            _, replayed = self.evidence.append_records(
                (
                    *selection_records,
                    *admission_records,
                    *asset_records,
                    activation_record,
                ),
                expected_record_journal_head=expected_record_journal_head,
            )
        except (IdempotencyConflictError, StaleInputError):
            replay = self._video_successor_replay(
                workspace, run_ref, client_key, selection_request_digest
            )
            if replay is None:
                raise
            return replay
        return {
            "realVideoAdmissionManifest": activation,
            "assetAdmissions": final_admissions,
            "assetVersions": final_assets,
            "state": self.evidence.current_state(workspace, run_ref),
            "idempotentReplay": replayed,
            "publicationAllowed": False,
        }

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realImagePlan": _fact(gate, "RealImagePlan"),
            "generationRequests": _request_facts(gate),
            "state": gate["toState"],
        }

    def _admission_bundle(
        self,
        gate: Mapping[str, Any],
        *,
        records: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        manifest = _fact(gate, "RealImageAdmissionManifest")
        if (
            manifest.get("schemaVersion")
            != REAL_IMAGE_UNIFIED_ADMISSION_MANIFEST_SCHEMA_VERSION
        ):
            return {
                "realImageAdmissionManifest": manifest,
                "candidates": _facts(gate, "RealImageCandidate:"),
                "selectionDecisions": _facts(
                    gate, "MediaSelectionDecision:"
                ),
                "assetVersions": _facts(gate, "AssetVersion:M10:"),
                "state": gate["toState"],
            }
        refs = manifest.get("selectionRefs")
        versions = manifest.get("selectionVersions")
        digests = manifest.get("selectionDigests")
        if (
            not isinstance(refs, list)
            or not isinstance(versions, list)
            or not isinstance(digests, list)
            or len(refs) != 4
            or len(versions) != 4
            or len(digests) != 4
        ):
            raise RepositoryUnavailableError(
                "unified M10 selection manifest is invalid"
            )
        selections: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        record_index = (
            None
            if records is None
            else {
                (item.get("recordRef"), item.get("recordVersion")): item
                for item in records
            }
        )
        for ref, version, digest in zip(refs, versions, digests):
            record = (
                self.evidence.get_record(
                    gate["workspaceRef"],
                    gate["productionRunRef"],
                    ref,
                    version,
                )
                if record_index is None
                else record_index.get((ref, version))
            )
            if (
                record is None
                or record.get("recordKind") != HUMAN_SELECTION
                or record.get("payloadDigest") != digest
                or not isinstance(record.get("payload"), Mapping)
            ):
                raise RepositoryUnavailableError(
                    "unified M10 selection evidence is invalid"
                )
            selection = deepcopy(dict(record["payload"]))
            candidate_record = (
                self.evidence.get_record(
                    gate["workspaceRef"],
                    gate["productionRunRef"],
                    selection.get("candidateRef"),
                    selection.get("candidateVersion"),
                )
                if record_index is None
                else record_index.get(
                    (
                        selection.get("candidateRef"),
                        selection.get("candidateVersion"),
                    )
                )
            )
            if (
                candidate_record is None
                or candidate_record.get("recordKind") != CANDIDATE
                or candidate_record.get("payloadDigest")
                != selection.get("candidateDigest")
                or not isinstance(candidate_record.get("payload"), Mapping)
            ):
                raise RepositoryUnavailableError(
                    "unified M10 candidate evidence is invalid"
                )
            selections.append(selection)
            candidates.append(deepcopy(dict(candidate_record["payload"])))
        return {
            "realImageAdmissionManifest": manifest,
            "candidates": candidates,
            "selectionDecisions": selections,
            "assetAdmissions": _facts(gate, "AssetAdmission:M10:"),
            "assetVersions": _facts(gate, "AssetVersion:M10:"),
            "state": gate["toState"],
        }

    @staticmethod
    def _video_bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realVideoPlan": _fact(gate, "RealVideoPlan"),
            "generationRequests": _facts(
                gate, "RealVideoGenerationRequest:"
            ),
            "state": gate["toState"],
        }

    @staticmethod
    def _video_admission_bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realVideoAdmissionManifest": _fact(
                gate, "RealVideoAdmissionManifest"
            ),
            "assetAdmissions": _facts(gate, "AssetAdmission:M11:"),
            "assetVersions": _facts(gate, "AssetVersion:M11:"),
            "state": gate["toState"],
        }

    def get_revision_bundle(
        self,
        workspace_ref: str,
        production_run_ref: str,
        *,
        evidence_snapshot: EvidenceSnapshot | None = None,
    ) -> dict[str, Any]:
        self.shot_graph.root_service.get_run(workspace_ref, production_run_ref)
        snapshot = evidence_snapshot or self.evidence.read_snapshot(
            workspace_ref, production_run_ref
        )
        if (
            snapshot.workspaceRef != workspace_ref
            or snapshot.productionRunRef != production_run_ref
        ):
            raise RepositoryUnavailableError("evidence snapshot scope is invalid")
        gates = {item.get("gateName"): item for item in snapshot.gates}
        gate = gates.get(REAL_IMAGE_PLAN_GATE)
        if gate is None:
            raise UpstreamNotReadyError("M10 real image plan is not ready")
        plan_bundle = self._bundle(gate)
        admission = gates.get(REAL_IMAGE_ADMISSION_GATE)
        if admission is None:
            return {
                **plan_bundle,
                "evidenceRevisionToken": snapshot.revisionToken,
            }
        result = {
            **plan_bundle,
            **self._admission_bundle(admission, records=snapshot.records),
        }
        video_plan = gates.get(REAL_VIDEO_PLAN_GATE)
        if video_plan is not None:
            video_bundle = self._video_bundle(video_plan)
            current_video_requests, current_video_revision = (
                self._current_video_request_set(
                    workspace_ref,
                    production_run_ref,
                    video_bundle,
                    records=snapshot.records,
                    gates=snapshot.gates,
                )
            )
            result.update(
                {
                    "realVideoPlan": video_bundle["realVideoPlan"],
                    "realVideoRevision": current_video_revision,
                    "videoGenerationRequests": current_video_requests,
                    "state": video_bundle["state"],
                }
            )
        active_video_admission = self._active_video_admission(
            workspace_ref,
            production_run_ref,
            records=snapshot.records,
            gates=snapshot.gates,
        )
        if active_video_admission is not None:
            active_manifest = active_video_admission["manifest"]
            active_admissions = active_video_admission["admissions"]
            active_assets = active_video_admission["assets"]
            current_revision = result.get("realVideoRevision")
            current_video_candidates = self._current_video_candidates_by_slot(
                workspace_ref,
                production_run_ref,
                records=snapshot.records,
            )
            activation_is_current = (
                active_video_admission.get("lineageCurrent") is True
                and isinstance(current_revision, Mapping)
                and active_manifest.get("realVideoRevisionRef")
                == current_revision.get("realVideoRevisionRef")
                and active_manifest.get("realVideoRevisionDigest")
                == current_revision.get("payloadDigest")
                and active_manifest.get("assetVersionRefs")
                == [item.get("assetVersionRef") for item in active_assets]
                and active_manifest.get("assetVersionDigests")
                == [item.get("payloadDigest") for item in active_assets]
                and len(current_video_candidates) == 4
                and all(
                    isinstance(
                        current_video_candidates.get(
                            item.get("creativeShotVersionRef")
                        ),
                        Mapping,
                    )
                    and item.get("sourceCandidateRef")
                    == current_video_candidates[
                        item["creativeShotVersionRef"]
                    ].get("candidateRef")
                    and item.get("sourceCandidateDigest")
                    == current_video_candidates[
                        item["creativeShotVersionRef"]
                    ].get("payloadDigest")
                    for item in active_assets
                )
            )
            result.update(
                {
                    "realVideoAdmissionManifest": (
                        active_manifest if activation_is_current else None
                    ),
                    "videoAssetAdmissions": (
                        active_admissions if activation_is_current else []
                    ),
                    "videoAssetVersions": (
                        active_assets if activation_is_current else []
                    ),
                    "activeVideoAdmission": {
                        "realVideoAdmissionManifest": active_manifest,
                        "assetAdmissions": active_admissions,
                        "assetVersions": active_assets,
                    },
                    "videoLineageState": {
                        "state": (
                            "CURRENT" if activation_is_current else "STALE_BLOCKED"
                        ),
                        "requestedRevisionRef": (
                            current_revision.get("realVideoRevisionRef")
                            if isinstance(current_revision, Mapping)
                            else None
                        ),
                        "requestedRevisionDigest": (
                            current_revision.get("payloadDigest")
                            if isinstance(current_revision, Mapping)
                            else None
                        ),
                        "activeRevisionRef": active_manifest.get(
                            "realVideoRevisionRef",
                            active_manifest.get("revisionRef"),
                        ),
                        "activeActivationManifestRef": active_video_admission[
                            "manifestRef"
                        ],
                        "activeActivationManifestDigest": active_video_admission[
                            "manifestDigest"
                        ],
                        "publicationAllowed": False,
                    },
                    "state": snapshot.currentState,
                }
            )
        result["candidateLifecycle"] = self.candidate_review.get_projection(
            workspace_ref,
            production_run_ref,
            records=snapshot.records,
            gates=snapshot.gates,
        )
        result["evidenceRevisionToken"] = snapshot.revisionToken
        result["publicationAllowed"] = False
        return result
