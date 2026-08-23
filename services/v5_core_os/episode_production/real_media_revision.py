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
REAL_VIDEO_PLAN_SCHEMA_VERSION = "v5.k2-real-video-plan.v1"
REAL_VIDEO_ADMISSION_SCHEMA_VERSION = "v5.k2-real-video-admission-manifest.v1"
REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-real-video-asset-version.v1"
REAL_IMAGE_PLANNER_ID = "v5.k2.real-image-planner.v1"
REAL_IMAGE_ADMISSION_ID = "v5.k2.real-image-admission.v1"
REAL_VIDEO_PLANNER_ID = "v5.k2.real-video-planner.v1"
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
                    "candidateRef": source_candidate_ref,
                    "artifactDigest": artifact_digest,
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
                    "idempotencyKey": f"m10-candidate-{candidate_key}",
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
                    "candidateRef": candidate_ref,
                    "candidateDigest": candidate_record.payloadDigest,
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
            "idempotencyKey": (
                "m10-successor-selection-"
                + _digest(
                    {
                        "clientIdempotencyKey": client_key,
                        "selectionRef": selection_input.get("selectionRef"),
                    }
                )[:40]
            ),
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
        requests = bundle["generationRequests"]
        try:
            resolved = self.video_candidate_evidence.resolve_candidates(
                workspace,
                run_ref,
                plan["realVideoPlanRef"],
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
            ):
                source_ref = payload.get("sourceCandidateRef") or payload.get(
                    "candidateRef"
                )
                if isinstance(source_ref, str):
                    existing_video_candidates[source_ref] = deepcopy(
                        dict(payload)
                    )
        exact_existing = bool(existing_video_candidates) and all(
            isinstance(existing_video_candidates.get(item.get("candidateRef")), Mapping)
            and existing_video_candidates[item.get("candidateRef")].get(
                "artifactDigest"
            )
            == item.get("artifactDigest")
            and existing_video_candidates[item.get("candidateRef")].get(
                "sourceRequestDigest"
            )
            == item.get("sourceRequestDigest")
            for item in candidates
        )
        if exact_existing:
            revision_refs = {
                existing_video_candidates[item.get("candidateRef")].get(
                    "revisionRef"
                )
                for item in candidates
            }
            if len(revision_refs) != 1:
                raise StaleInputError(
                    "M11 candidate handoff revision is ambiguous"
                )
            candidate_revision_ref = next(iter(revision_refs))
        elif not existing_video_candidates:
            candidate_revision_ref = plan["realVideoPlanRef"]
        else:
            candidate_revision_ref = (
                "m11-video-revision-"
                + _digest(
                    {
                        "realVideoPlanDigest": plan["payloadDigest"],
                        "handoffDigest": handoff.get("payloadDigest"),
                        "candidates": [
                            {
                                "candidateRef": item.get("candidateRef"),
                                "sourceRequestDigest": item.get(
                                    "sourceRequestDigest"
                                ),
                                "artifactDigest": item.get("artifactDigest"),
                            }
                            for item in sorted(
                                candidates,
                                key=lambda value: value.get("ordinal", 0),
                            )
                        ],
                    }
                )[:32]
            )
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        prepared_records: list[EvidenceRecord] = []
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
            candidate_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m11-candidate",
                    "candidateRef": source_candidate_ref,
                }
            )[:48]
            candidate_ref = source_candidate_ref
            if exact_existing:
                candidate_ref = existing_video_candidates[
                    source_candidate_ref
                ]["candidateRef"]
            elif existing_video_candidates:
                candidate_ref = (
                    "m11-video-candidate-"
                    + _digest(
                        {
                            "revisionRef": candidate_revision_ref,
                            "sourceCandidateRef": source_candidate_ref,
                            "artifactDigest": item.get("artifactDigest"),
                        }
                    )[:32]
                )
            candidate_record = self.candidate_review.prepare_candidate_record(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "idempotencyKey": f"m11-candidate-{candidate_key}",
                    "candidateRef": candidate_ref,
                    "candidateVersion": item.get("candidateVersion", 1),
                    "revisionRef": candidate_revision_ref,
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
                }
            )
            candidate = deepcopy(dict(candidate_record.payload))
            validation_key = _digest(
                {
                    "clientIdempotencyKey": client_key,
                    "stage": "m11-technical-validation",
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
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
        stored, replayed = self.evidence.append_records(
            prepared_records,
            expected_record_journal_head=expected_record_journal_head,
        )
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
            or len(selections) != 4
            or not all(isinstance(item, Mapping) for item in selections)
        ):
            raise EpisodeProductionError("M11 requires four exact selections")
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
        ) != 4:
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
        requests = plan_bundle["generationRequests"]
        gate_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "m11-real-video-admission",
            }
        )
        existing = self.evidence.get_gate(
            workspace, run_ref, REAL_VIDEO_ADMISSION_GATE
        )
        if existing is not None:
            if existing.get("idempotencyKey") != gate_key:
                raise IdempotencyConflictError("M11 admission command conflicts")
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
        if self.evidence.current_state(workspace, run_ref) != "REAL_VIDEO_PLAN_READY":
            raise StaleInputError("M11 admission state changed")
        expected_record_journal_head = self.evidence.record_journal_head(
            workspace, run_ref
        )
        active_candidate_revision_ref = self.candidate_review.get_projection(
            workspace, run_ref
        ).get("latestCandidateRevisionRefs", {}).get("VIDEO")
        if not isinstance(active_candidate_revision_ref, str):
            raise StaleInputError("M11 current video candidate revision is missing")
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
            request = requests_by_ref.get(candidate.get("sourceRequestRef"))
            if (
                not isinstance(request, Mapping)
                or candidate.get("sourceRequestDigest")
                != request.get("payloadDigest")
                or candidate.get("slotRef")
                != request.get("creativeShotVersionRef")
                or candidate.get("revisionRef") != active_candidate_revision_ref
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
                plan["realVideoPlanRef"],
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
                "revisionRef": active_candidate_revision_ref,
                "selectionRequestDigest": selection_request_digest,
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

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realImagePlan": _fact(gate, "RealImagePlan"),
            "generationRequests": _request_facts(gate),
            "state": gate["toState"],
        }

    def _admission_bundle(self, gate: Mapping[str, Any]) -> dict[str, Any]:
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
        for ref, version, digest in zip(refs, versions, digests):
            record = self.evidence.get_record(
                gate["workspaceRef"],
                gate["productionRunRef"],
                ref,
                version,
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
            candidate_record = self.evidence.get_record(
                gate["workspaceRef"],
                gate["productionRunRef"],
                selection.get("candidateRef"),
                selection.get("candidateVersion"),
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
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        self.shot_graph.root_service.get_run(workspace_ref, production_run_ref)
        gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, REAL_IMAGE_PLAN_GATE
        )
        if gate is None:
            raise UpstreamNotReadyError("M10 real image plan is not ready")
        plan_bundle = self._bundle(gate)
        admission = self.evidence.get_gate(
            workspace_ref,
            production_run_ref,
            REAL_IMAGE_ADMISSION_GATE,
        )
        if admission is None:
            return plan_bundle
        result = {**plan_bundle, **self._admission_bundle(admission)}
        video_plan = self.evidence.get_gate(
            workspace_ref,
            production_run_ref,
            REAL_VIDEO_PLAN_GATE,
        )
        if video_plan is not None:
            video_bundle = self._video_bundle(video_plan)
            result.update(
                {
                    "realVideoPlan": video_bundle["realVideoPlan"],
                    "videoGenerationRequests": video_bundle[
                        "generationRequests"
                    ],
                    "state": video_bundle["state"],
                }
            )
        video_admission = self.evidence.get_gate(
            workspace_ref,
            production_run_ref,
            REAL_VIDEO_ADMISSION_GATE,
        )
        if video_admission is not None:
            admission_bundle = self._video_admission_bundle(video_admission)
            result.update(
                {
                    "realVideoAdmissionManifest": admission_bundle[
                        "realVideoAdmissionManifest"
                    ],
                    "videoAssetAdmissions": admission_bundle[
                        "assetAdmissions"
                    ],
                    "videoAssetVersions": admission_bundle["assetVersions"],
                    "state": admission_bundle["state"],
                }
            )
        result["candidateLifecycle"] = self.candidate_review.get_projection(
            workspace_ref, production_run_ref
        )
        result["publicationAllowed"] = False
        return result
