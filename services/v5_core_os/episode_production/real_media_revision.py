"""Image-first same-run revision planning for K2 real media.

This V5 service creates provider-neutral M10 shot-image requests from the current
G2 identity lock and G3 shot graph.  It deliberately does not execute ComfyUI,
select a candidate, create an AssetVersion, approve a preview or publish.  Those
are separate V4 execution and V5 admission operations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Mapping

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
REAL_IMAGE_REQUEST_SCHEMA_VERSION = "v5.k2-real-shot-image-request.v1"
REAL_IMAGE_PLAN_SCHEMA_VERSION = "v5.k2-real-image-plan.v1"
REAL_IMAGE_PLANNER_ID = "v5.k2.real-image-planner.v1"
REAL_IMAGE_CAPABILITY = "self-hosted-multi-reference-shot-image-v1"


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


class K2RealMediaRevisionService:
    """Owns M10/M11 domain planning without owning provider execution."""

    def __init__(
        self,
        shot_graph: K2ShotGraphService,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.shot_graph = shot_graph
        self.evidence = evidence
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

    @staticmethod
    def _bundle(gate: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "realImagePlan": _fact(gate, "RealImagePlan"),
            "generationRequests": _request_facts(gate),
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
        return self._bundle(gate)
