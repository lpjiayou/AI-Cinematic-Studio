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

from .delivery import QC_GATE
from .evidence import EpisodeProductionEvidenceRepository, EvidenceFact, GateAppend
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
from .shot_graph import K2ShotGraphService


REAL_IMAGE_PLAN_GATE = "M10_REAL_IMAGE_PLAN"
REAL_IMAGE_ADMISSION_GATE = "M10_REAL_IMAGE_ADMISSION"
REAL_VIDEO_PLAN_GATE = "M11_REAL_VIDEO_PLAN"
REAL_IMAGE_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-image-request.v1"
REAL_IMAGE_PLAN_SCHEMA_VERSION = "v5.k2-real-image-plan.v1"
REAL_IMAGE_CANDIDATE_SCHEMA_VERSION = "v5.k2-real-image-candidate.v1"
REAL_IMAGE_SELECTION_SCHEMA_VERSION = "v5.k2-media-selection-decision.v1"
REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-real-image-asset-version.v1"
REAL_IMAGE_ADMISSION_MANIFEST_SCHEMA_VERSION = (
    "v5.k2-real-image-admission-manifest.v1"
)
REAL_VIDEO_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-video-request.v1"
REAL_VIDEO_PLAN_SCHEMA_VERSION = "v5.k2-real-video-plan.v1"
REAL_IMAGE_PLANNER_ID = "v5.k2.real-image-planner.v1"
REAL_IMAGE_ADMISSION_ID = "v5.k2.real-image-admission.v1"
REAL_VIDEO_PLANNER_ID = "v5.k2.real-video-planner.v1"
REAL_IMAGE_CAPABILITY = "self-hosted-multi-reference-shot-image-v1"
REAL_VIDEO_CAPABILITY = "self-hosted-wan22-image-to-video-v1"


class RealImageCandidateRejectedError(EpisodeProductionError):
    code = "real_image_candidate_evidence_rejected"


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


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


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
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.shot_graph = shot_graph
        self.evidence = evidence
        self.candidate_evidence = (
            candidate_evidence or RejectingRealImageCandidateEvidence()
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

    def select_and_admit_images(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "actorRef",
            "selections",
        }:
            raise EpisodeProductionError(
                "command fields do not match the M10 selection contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        client_key = _idempotency_key(command.get("idempotencyKey"))
        actor_ref = _required_ref(command.get("actorRef"), "actorRef")
        selections = self._selection_items(command.get("selections"))
        verified, plan_bundle = self._verified_plan(workspace, run_ref)
        root = verified["root"]
        plan = plan_bundle["realImagePlan"]
        requests = plan_bundle["generationRequests"]
        request_by_ref = {
            item["generationRequestRef"]: item for item in requests
        }
        if {item["generationRequestRef"] for item in selections} != set(
            request_by_ref
        ):
            raise StaleInputError(
                "M10 image selections do not cover the current plan"
            )
        gate_key = _digest(
            {
                "clientIdempotencyKey": client_key,
                "stage": "m10-real-image-admission",
            }
        )
        request_digest = _digest(
            {
                "clientIdempotencyKey": client_key,
                "actorRef": actor_ref,
                "rootPayloadDigest": root["payloadDigest"],
                "realImagePlanDigest": plan["payloadDigest"],
                "selections": selections,
                "admissionId": REAL_IMAGE_ADMISSION_ID,
            }
        )
        existing = self.evidence.get_gate(
            workspace, run_ref, REAL_IMAGE_ADMISSION_GATE
        )
        if existing is not None:
            if (
                existing.get("idempotencyKey") != gate_key
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError(
                    "M10 image selection command conflicts"
                )
            return {**self._admission_bundle(existing), "idempotentReplay": True}
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
        if (
            not isinstance(handoff, Mapping)
            or handoff.get("publicationAllowed") is not False
            or not isinstance(handoff.get("candidates"), list)
            or len(handoff["candidates"]) != 4
        ):
            raise RealImageCandidateRejectedError(
                "V4 returned an incomplete M10 candidate handoff"
            )
        candidate_by_request = {
            item.get("generationRequestRef"): item
            for item in handoff["candidates"]
            if isinstance(item, Mapping)
        }
        if len(candidate_by_request) != 4 or set(candidate_by_request) != set(
            request_by_ref
        ):
            raise RealImageCandidateRejectedError(
                "M10 candidate handoff does not match the current requests"
            )
        selection_by_request = {
            item["generationRequestRef"]: item for item in selections
        }
        now = self._clock()
        candidates: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        asset_versions: list[dict[str, Any]] = []
        artifact_store_ref = _required_ref(
            handoff.get("artifactStoreRef"), "artifactStoreRef"
        )
        evidence_ref = _required_ref(
            handoff.get("candidateEvidenceRef"), "candidateEvidenceRef"
        )
        evidence_digest = _content_digest(
            handoff.get("candidateEvidenceDigest"),
            "candidateEvidenceDigest",
        )
        model_set_digest = _content_digest(
            handoff.get("modelSetDigest"), "modelSetDigest"
        )
        adapter_identity = _required_ref(
            handoff.get("adapterIdentity"), "adapterIdentity"
        )
        for request in requests:
            raw = candidate_by_request[request["generationRequestRef"]]
            selected = selection_by_request[request["generationRequestRef"]]
            artifact = raw.get("artifact")
            if not isinstance(artifact, Mapping):
                raise RealImageCandidateRejectedError(
                    "M10 candidate artifact metadata is missing"
                )
            candidate_ref = _required_ref(
                raw.get("candidateRef"), "candidateRef"
            )
            artifact_digest = _content_digest(
                artifact.get("sha256"), "candidate artifact digest"
            )
            if (
                candidate_ref != selected["candidateRef"]
                or artifact_digest != selected["candidateContentDigest"]
                or raw.get("ordinal") != request["ordinal"]
                or raw.get("generationRequestDigest")
                != request["payloadDigest"]
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
                    "selected M10 candidate failed lineage verification"
                )
            candidate = _sealed(
                {
                    "schemaVersion": REAL_IMAGE_CANDIDATE_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "candidateRef": candidate_ref,
                    "candidateVersionRef": f"{candidate_ref}-v1",
                    "version": 1,
                    "ordinal": request["ordinal"],
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
                    "candidateEvidenceRef": evidence_ref,
                    "candidateEvidenceDigest": evidence_digest,
                    "adapterIdentity": adapter_identity,
                    "modelSetDigest": model_set_digest,
                    "workflowDigest": _content_digest(
                        raw.get("workflowDigest"), "workflowDigest"
                    ),
                    "artifactStoreRef": artifact_store_ref,
                    "artifactStorageKey": artifact["storageKey"],
                    "artifactSha256": artifact_digest,
                    "artifactByteSize": artifact["byteSize"],
                    "dimensions": {
                        "width": artifact["width"],
                        "height": artifact["height"],
                    },
                    "mediaKind": "image",
                    "mediaType": "image/png",
                    "validationState": "TECHNICALLY_VERIFIED",
                    "selectionState": "SELECTED_BY_HUMAN",
                    "admissionState": "ADMITTED",
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                    "gpuUsed": True,
                    "publicationAllowed": False,
                    "recordedBy": REAL_IMAGE_ADMISSION_ID,
                    "recordedAt": now,
                }
            )
            decision = _sealed(
                {
                    "schemaVersion": REAL_IMAGE_SELECTION_SCHEMA_VERSION,
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "selectionDecisionRef": _required_ref(
                        self._ref_factory("media-selection-decision"),
                        "selectionDecisionRef",
                    ),
                    "version": 1,
                    "ordinal": request["ordinal"],
                    "decision": "SELECT",
                    "actorRef": actor_ref,
                    "generationRequestRef": request[
                        "generationRequestRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
                    "candidateContentDigest": artifact_digest,
                    "decisionScope": "EXACT_FOUR_M10_IMAGE_CANDIDATES",
                    "publicationAllowed": False,
                    "decidedAt": now,
                }
            )
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
                    "ordinal": request["ordinal"],
                    "generationRequestRef": request[
                        "generationRequestRef"
                    ],
                    "generationRequestVersionRef": request[
                        "generationRequestVersionRef"
                    ],
                    "generationRequestDigest": request["payloadDigest"],
                    "candidateRef": candidate["candidateRef"],
                    "candidateDigest": candidate["payloadDigest"],
                    "selectionDecisionRef": decision[
                        "selectionDecisionRef"
                    ],
                    "selectionDecisionDigest": decision["payloadDigest"],
                    "creativeShotRef": request["creativeShotRef"],
                    "creativeShotVersionRef": request[
                        "creativeShotVersionRef"
                    ],
                    "creativeShotDigest": request["creativeShotDigest"],
                    "mediaKind": "image",
                    "mediaType": "image/png",
                    "artifactStoreRef": artifact_store_ref,
                    "storageKey": artifact["storageKey"],
                    "byteSize": artifact["byteSize"],
                    "sha256": artifact_digest,
                    "probe": {
                        "width": artifact["width"],
                        "height": artifact["height"],
                        "format": "png",
                    },
                    "adapterIdentity": adapter_identity,
                    "provenance": "SELF_HOSTED_AI_GENERATED",
                    "rightsState": "NOT_REQUIRED_INTERNAL",
                    "providerPolicyState": "NOT_REQUIRED_SELF_HOSTED",
                    "budgetAuthorityState": "NOT_REQUIRED_INTERNAL",
                    "state": "REGISTERED",
                    "immutable": True,
                    "publicationAllowed": False,
                    "createdBy": REAL_IMAGE_ADMISSION_ID,
                    "createdAt": now,
                }
            )
            candidates.append(candidate)
            decisions.append(decision)
            asset_versions.append(asset)
        manifest = _sealed(
            {
                "schemaVersion": REAL_IMAGE_ADMISSION_MANIFEST_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "realImageAdmissionManifestRef": _required_ref(
                    self._ref_factory("real-image-admission-manifest"),
                    "realImageAdmissionManifestRef",
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "realImagePlanRef": plan["realImagePlanRef"],
                "realImagePlanDigest": plan["payloadDigest"],
                "candidateEvidenceRef": evidence_ref,
                "candidateEvidenceDigest": evidence_digest,
                "candidateRefs": [item["candidateRef"] for item in candidates],
                "candidateDigests": [
                    item["payloadDigest"] for item in candidates
                ],
                "selectionDecisionRefs": [
                    item["selectionDecisionRef"] for item in decisions
                ],
                "selectionDecisionDigests": [
                    item["payloadDigest"] for item in decisions
                ],
                "assetVersionRefs": [
                    item["assetVersionRef"] for item in asset_versions
                ],
                "assetVersionDigests": [
                    item["payloadDigest"] for item in asset_versions
                ],
                "summary": {
                    "technicallyVerifiedCandidates": 4,
                    "humanSelections": 4,
                    "registeredImageAssets": 4,
                    "failed": 0,
                },
                "state": "REAL_IMAGE_READY",
                "rightsState": "NOT_REQUIRED_INTERNAL",
                "providerPolicyState": "NOT_REQUIRED_SELF_HOSTED",
                "budgetAuthorityState": "NOT_REQUIRED_INTERNAL",
                "publicationAllowed": False,
                "createdBy": REAL_IMAGE_ADMISSION_ID,
                "createdAt": now,
            }
        )
        facts = tuple(
            EvidenceFact(
                f"RealImageCandidate:{item['ordinal']:04d}",
                item["candidateRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in candidates
        ) + tuple(
            EvidenceFact(
                f"MediaSelectionDecision:{item['ordinal']:04d}",
                item["selectionDecisionRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in decisions
        ) + tuple(
            EvidenceFact(
                f"AssetVersion:M10:{item['ordinal']:04d}",
                item["assetVersionRef"],
                1,
                item,
                item["payloadDigest"],
            )
            for item in asset_versions
        ) + (
            EvidenceFact(
                "RealImageAdmissionManifest",
                manifest["realImageAdmissionManifestRef"],
                1,
                manifest,
                manifest["payloadDigest"],
            ),
        )
        gate, replay = self.evidence.append_gate(
            GateAppend(
                workspace,
                run_ref,
                REAL_IMAGE_ADMISSION_GATE,
                gate_key,
                root["payloadDigest"],
                request_digest,
                "REAL_IMAGE_PLAN_READY",
                "REAL_IMAGE_READY",
                now,
                facts,
            )
        )
        return {**self._admission_bundle(gate), "idempotentReplay": replay}

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

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realImagePlan": _fact(gate, "RealImagePlan"),
            "generationRequests": _request_facts(gate),
            "state": gate["toState"],
        }

    @staticmethod
    def _admission_bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realImageAdmissionManifest": _fact(
                gate, "RealImageAdmissionManifest"
            ),
            "candidates": _facts(gate, "RealImageCandidate:"),
            "selectionDecisions": _facts(
                gate, "MediaSelectionDecision:"
            ),
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
        return result
