"""Fail-closed, zero-write image preflight for a current K2 shot-plan draft.

This module deliberately does not define a provider capability, executable
GenerationRequest, V4 adapter handoff, candidate intake, video plan, admission,
or publication path. It reads the current V5 authority chain and returns only
detached preview records whose dispatch state is unconditionally false.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .foundation import (
    EpisodeProductionError,
    LOCAL_EVIDENCE,
    UpstreamNotReadyError,
    _digest,
    _required_ref,
)
from .shot_graph import (
    validate_creative_shot_draft,
    validate_shot_plan_draft,
)


DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION = "v5.k2-dynamic-image-preflight.v1"
_IMAGE_PLAN_PREVIEW_SCHEMA_VERSION = "v5.k2-image-plan-preview.v1"
_IMAGE_REQUEST_PREVIEW_SCHEMA_VERSION = "v5.k2-shot-image-request-preview.v1"
_OUTPUT_PROFILE_SCHEMA_VERSION = "k2.episode-output-profile.v2"
_SHOT_PLAN_DRAFT_SCHEMA_VERSION = "v5.local-structural-shot-plan-draft.v1"
_CREATIVE_SHOT_DRAFT_SCHEMA_VERSION = "v5.creative-shot-draft.v1"
_PREFLIGHT_ONLY = "PREFLIGHT_ONLY_NOT_AUTHORIZED"
_OUTPUT_PROFILE_FIELDS = (
    "schemaVersion",
    "orientation",
    "targetAspectRatio",
    "width",
    "height",
    "aspectRatio",
    "frameRate",
    "container",
    "generationCanvas",
    "editMaster",
    "releaseMaster",
    "controlledExtensionAlgorithmRef",
    "controlledExtensionAlgorithmDigest",
    "controlledExtensionAlgorithm",
    "totalFrames",
)

_FIXED_DISPATCH_BLOCKER_TYPES = (
    "M10_CANONICAL_APPEND_NOT_IMPLEMENTED",
    "K2_002_REGISTRATION_PROVENANCE_NOT_VERIFIED_BY_PREFLIGHT",
    "SCRIPT_OWNER_ACCEPTANCE_NOT_VERIFIED_BY_PREFLIGHT",
    "SHOT_PLAN_APPROVAL_NOT_VERIFIED",
    "CAMERA_CONTRACT_NOT_READY",
    "INPUT_ASSET_ADMISSION_NOT_VERIFIED",
    "RIGHTS_AUTHORITY_NOT_VERIFIED",
    "PROVIDER_POLICY_NOT_VERIFIED",
    "BUDGET_AUTHORITY_NOT_VERIFIED",
    "RUNTIME_CAPABILITY_NOT_VERIFIED",
)


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result["payloadDigest"] = _digest(result)
    return result


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 4_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str, *, maximum: int = 16_384) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > maximum
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _verify_sealed(value: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(value))
    supplied = _sha256(payload.pop("payloadDigest", None), f"{field}.payloadDigest")
    if supplied != _digest(payload):
        raise EpisodeProductionError(f"{field} digest is invalid")
    return supplied


def _derived_identity_mode(bindings: Sequence[Mapping[str, Any]]) -> str:
    modes = {item.get("bindingMode") for item in bindings}
    if not modes:
        return "NONE"
    if modes == {"BODY_ONLY"}:
        return "BODY_ONLY"
    if modes == {"FACE_LOCK"}:
        return "FACE_LOCK"
    if modes == {"BODY_ONLY", "FACE_LOCK"}:
        return "MIXED"
    raise EpisodeProductionError("v2 shot identity bindings are invalid")


def _image_reference_media_type(value: Any) -> str:
    if value == "image/png":
        return value
    raise EpisodeProductionError(
        "FACE_LOCK identity reference must be an exact image/png authority"
    )


def _profile(draft: Mapping[str, Any]) -> dict[str, Any]:
    validate_shot_plan_draft(draft)
    output = draft.get("output")
    if (
        not isinstance(output, Mapping)
        or set(output) != set(_OUTPUT_PROFILE_FIELDS)
        or output.get("schemaVersion") != _OUTPUT_PROFILE_SCHEMA_VERSION
    ):
        raise EpisodeProductionError("shot plan draft output profile is invalid")
    generation = output.get("generationCanvas")
    edit_master = output.get("editMaster")
    release_master = output.get("releaseMaster")
    if not all(
        isinstance(item, Mapping)
        for item in (generation, edit_master, release_master)
    ):
        raise EpisodeProductionError("v2 output canvases are incomplete")
    width = _positive_int(generation.get("width"), "generationCanvas.width")
    height = _positive_int(generation.get("height"), "generationCanvas.height")
    if width % 32 or height % 32:
        raise EpisodeProductionError(
            "generation canvas dimensions must be divisible by 32"
        )
    frame_rate = _positive_int(
        output.get("frameRate"), "output.frameRate", maximum=240
    )
    draft_ref = _required_ref(
        draft.get("shotPlanDraftRef"),
        "shotPlanDraftRef",
    )
    profile_payload = {
        field: deepcopy(output[field]) for field in _OUTPUT_PROFILE_FIELDS
    }
    profile_digest = _digest(profile_payload)
    return {
        "productionProfilePreviewRef": _required_ref(
            f"{draft_ref}:output-profile-preview",
            "productionProfilePreviewRef",
        ),
        "productionProfileDigest": profile_digest,
        "outputProfile": profile_payload,
        "generationCanvas": {"width": width, "height": height},
        "editMaster": {
            "width": _positive_int(edit_master.get("width"), "editMaster.width"),
            "height": _positive_int(edit_master.get("height"), "editMaster.height"),
        },
        "releaseMaster": {
            "width": _positive_int(
                release_master.get("width"), "releaseMaster.width"
            ),
            "height": _positive_int(
                release_master.get("height"), "releaseMaster.height"
            ),
        },
        "frameRate": frame_rate,
    }


def _current_shots(
    draft: Mapping[str, Any],
    creative_shot_drafts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    validate_shot_plan_draft(draft)
    if draft.get("schemaVersion") != _SHOT_PLAN_DRAFT_SCHEMA_VERSION:
        raise EpisodeProductionError("image preflight requires a shot plan draft")
    _verify_sealed(draft, "shotPlanDraft")
    raw_shots = draft.get("shots")
    if (
        not isinstance(raw_shots, list)
        or not raw_shots
        or len(raw_shots) > 120
        or not all(isinstance(item, Mapping) for item in raw_shots)
        or not isinstance(creative_shot_drafts, Sequence)
        or isinstance(creative_shot_drafts, (str, bytes, bytearray))
        or len(creative_shot_drafts) != len(raw_shots)
        or not all(isinstance(item, Mapping) for item in creative_shot_drafts)
    ):
        raise EpisodeProductionError("current CreativeShotDraft coverage is incomplete")

    creative_by_ref: dict[str, Mapping[str, Any]] = {}
    for index, creative in enumerate(creative_shot_drafts):
        validate_creative_shot_draft(creative)
        draft_ref = _required_ref(
            creative.get("creativeShotDraftRef"),
            f"creativeShotDrafts[{index}].creativeShotDraftRef",
        )
        if draft_ref in creative_by_ref:
            raise EpisodeProductionError("CreativeShotDraft coverage is ambiguous")
        if (
            creative.get("schemaVersion") != _CREATIVE_SHOT_DRAFT_SCHEMA_VERSION
            or creative.get("workspaceRef") != draft.get("workspaceRef")
            or creative.get("productionRunRef") != draft.get("productionRunRef")
        ):
            raise EpisodeProductionError("CreativeShotDraft lineage is invalid")
        _verify_sealed(creative, f"creativeShotDrafts[{index}]")
        creative_by_ref[draft_ref] = creative

    shots = [deepcopy(dict(item)) for item in raw_shots]
    if [item.get("globalOrder") for item in shots] != list(
        range(1, len(shots) + 1)
    ):
        raise EpisodeProductionError("shot plan draft ordinals are not contiguous")

    frame_total = 0
    seen_slots: set[str] = set()
    for index, shot in enumerate(shots):
        slot_ref = _required_ref(
            shot.get("creativeShotDraftRef"),
            f"shots[{index}].creativeShotDraftRef",
        )
        if slot_ref in seen_slots:
            raise EpisodeProductionError("shot plan draft repeats a slot")
        seen_slots.add(slot_ref)
        shot_digest = _sha256(
            shot.get("payloadDigest"), f"shots[{index}].payloadDigest"
        )
        creative = creative_by_ref.get(slot_ref)
        compared_fields = (
            "creativeShotDraftRef",
            "globalOrder",
            "durationFrames",
            "frameRate",
            "editorialShotSize",
            "visibleIdentityMode",
            "visibleCharacterRefs",
            "visibleIdentityBindings",
            "requiredCharacterIdentityLocks",
            "continuityConstraints",
            "dialogueSyncMode",
            "dialogueRequirement",
            "postprocessRequirements",
            "actionBeat",
        )
        if (
            creative is None
            or creative.get("payloadDigest") != shot_digest
            or any(creative.get(field) != shot.get(field) for field in compared_fields)
            or creative.get("action") != shot.get("actionBeat")
        ):
            raise EpisodeProductionError(
                "CreativeShotDraft does not match the shot plan draft"
            )
        duration = _positive_int(
            shot.get("durationFrames"),
            f"shots[{index}].durationFrames",
            maximum=216_000,
        )
        frame_total += duration
        locks = shot.get("requiredCharacterIdentityLocks")
        visible_refs = shot.get("visibleCharacterRefs")
        visible_bindings = shot.get("visibleIdentityBindings")
        if (
            not isinstance(locks, list)
            or not all(isinstance(item, Mapping) for item in locks)
            or not isinstance(visible_refs, list)
            or not all(isinstance(item, str) and item for item in visible_refs)
            or len(visible_refs) != len(set(visible_refs))
            or [item.get("characterRef") for item in locks] != visible_refs
            or visible_bindings
            != [
                {
                    "characterRef": item.get("characterRef"),
                    "bindingMode": item.get("bindingMode"),
                }
                for item in locks
            ]
            or shot.get("visibleIdentityMode") != _derived_identity_mode(locks)
        ):
            raise EpisodeProductionError("v2 shot visible identity lineage is invalid")
        _text(shot.get("editorialShotSize"), f"shots[{index}].editorialShotSize")
        if "cameraInstruction" in shot:
            raise EpisodeProductionError("shot plan draft contains camera authority")
        _text(shot.get("actionBeat"), f"shots[{index}].actionBeat")
        continuity = shot.get("continuityConstraints")
        if not isinstance(continuity, list) or not continuity or not all(
            isinstance(item, str) and item.strip() for item in continuity
        ):
            raise EpisodeProductionError("v2 shot continuity is invalid")
        postprocess = shot.get("postprocessRequirements")
        if not isinstance(postprocess, list) or any(
            not isinstance(item, Mapping)
            or set(item)
            != {
                "requirementKey",
                "type",
                "inputAssetRequirementKeys",
                "status",
            }
            or not isinstance(item.get("inputAssetRequirementKeys"), list)
            or not item.get("inputAssetRequirementKeys")
            or not all(
                isinstance(key, str) and key
                for key in item.get("inputAssetRequirementKeys", [])
            )
            or len(item.get("inputAssetRequirementKeys", []))
            != len(set(item.get("inputAssetRequirementKeys", [])))
            or item.get("status") != "NOT_READY"
            for item in postprocess
        ):
            raise EpisodeProductionError("v2 shot postprocess requirements are invalid")
    if draft.get("output", {}).get("totalFrames") != frame_total:
        raise EpisodeProductionError("shot plan draft frame accounting is inconsistent")
    return shots


def _identity_inputs(
    shot: Mapping[str, Any], identity_lock: Mapping[str, Any]
) -> list[dict[str, Any]]:
    identities = identity_lock.get("identities")
    bindings = shot.get("requiredCharacterIdentityLocks")
    if not isinstance(identities, list) or not isinstance(bindings, list):
        raise EpisodeProductionError("identity lock entries are unavailable")
    by_character: dict[str, Mapping[str, Any]] = {}
    for item in identities:
        if not isinstance(item, Mapping):
            raise EpisodeProductionError("identity lock entry is invalid")
        character_ref = _required_ref(item.get("characterRef"), "characterRef")
        if character_ref in by_character:
            raise EpisodeProductionError("identity lock entries are ambiguous")
        by_character[character_ref] = item

    result: list[dict[str, Any]] = []
    for index, binding in enumerate(bindings):
        character_ref = _required_ref(
            binding.get("characterRef"), f"identityLocks[{index}].characterRef"
        )
        identity = by_character.get(character_ref)
        if identity is None:
            raise EpisodeProductionError("shot identity is absent from the identity lock")
        script_name = _text(
            identity.get("scriptCharacterName"),
            "scriptCharacterName",
            maximum=200,
        )
        if binding.get("bindingMode") == "BODY_ONLY":
            if binding.get("characterFactDigest") != identity.get(
                "characterFactDigest"
            ):
                raise EpisodeProductionError("BODY_ONLY identity binding is invalid")
            result.append(
                {
                    "bindingMode": "BODY_ONLY",
                    "characterRef": character_ref,
                    "scriptCharacterName": script_name,
                    "characterContinuityVersionRef": _required_ref(
                        binding.get("characterContinuityVersionRef"),
                        "characterContinuityVersionRef",
                    ),
                    "characterContinuityVersionDigest": _sha256(
                        binding.get("characterContinuityVersionDigest"),
                        "characterContinuityVersionDigest",
                    ),
                    "characterFactDigest": _sha256(
                        binding.get("characterFactDigest"), "characterFactDigest"
                    ),
                }
            )
            continue
        if binding.get("bindingMode") != "FACE_LOCK":
            raise EpisodeProductionError("identity binding mode is invalid")
        reference = identity.get("reference")
        if not isinstance(reference, Mapping):
            raise EpisodeProductionError("FACE_LOCK identity reference is unavailable")
        if (
            binding.get("identityLockRef") != identity_lock.get("identityLockRef")
            or binding.get("identityLockVersionRef")
            != identity_lock.get("identityLockVersionRef")
            or binding.get("identityLockDigest") != identity_lock.get("payloadDigest")
            or binding.get("referenceVersionRef")
            != reference.get("referenceVersionRef")
            or binding.get("referenceDigest") != reference.get("contentDigest")
        ):
            raise EpisodeProductionError("FACE_LOCK identity binding is stale")
        result.append(
            {
                "bindingMode": "FACE_LOCK",
                "characterRef": character_ref,
                "scriptCharacterName": script_name,
                "identityLockRef": _required_ref(
                    identity_lock.get("identityLockRef"), "identityLockRef"
                ),
                "identityLockVersionRef": _required_ref(
                    identity_lock.get("identityLockVersionRef"),
                    "identityLockVersionRef",
                ),
                "identityLockDigest": _sha256(
                    identity_lock.get("payloadDigest"), "identityLockDigest"
                ),
                "referenceRef": _required_ref(
                    reference.get("referenceRef"), "referenceRef"
                ),
                "referenceVersionRef": _required_ref(
                    reference.get("referenceVersionRef"), "referenceVersionRef"
                ),
                "referenceContentDigest": _sha256(
                    reference.get("contentDigest"), "referenceContentDigest"
                ),
                "referenceMediaType": _image_reference_media_type(
                    reference.get("mediaType")
                ),
            }
        )
    return result


def _fixed_blockers() -> list[dict[str, Any]]:
    return [
        {
            "blockerType": blocker_type,
            "scope": "K2_002_IMAGE_PREFLIGHT",
            "status": "BLOCKING",
        }
        for blocker_type in _FIXED_DISPATCH_BLOCKER_TYPES
    ]


def _postprocess_blockers(
    shots: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "blockerType": "POSTPROCESS_REQUIREMENT_NOT_READY",
            "scope": "K2_002_IMAGE_PREFLIGHT",
            "status": "BLOCKING",
            "ordinal": shot["globalOrder"],
            "requirementKey": requirement["requirementKey"],
            "requirementType": requirement["type"],
            "requirementStatus": requirement["status"],
        }
        for shot in shots
        for requirement in shot["postprocessRequirements"]
    ]


def _preview_ref(prefix: str, draft_digest: str, ordinal: int = 0) -> str:
    suffix = _digest(
        {
            "shotPlanDraftDigest": draft_digest,
            "previewKind": prefix,
            "ordinal": ordinal,
        }
    )[:32]
    return f"{prefix}-{suffix}"


def _build_image_preview(
    *,
    workspace_ref: str,
    production_run_ref: str,
    draft: Mapping[str, Any],
    creative_shot_drafts: Sequence[Mapping[str, Any]],
    identity_lock: Mapping[str, Any],
) -> dict[str, Any]:
    validate_shot_plan_draft(draft)
    draft_digest = _verify_sealed(draft, "shotPlanDraft")
    identity_digest = _verify_sealed(identity_lock, "identityLock")
    if (
        draft.get("workspaceRef") != workspace_ref
        or draft.get("productionRunRef") != production_run_ref
        or draft.get("identityLockRef") != identity_lock.get("identityLockRef")
        or draft.get("identityLockVersionRef")
        != identity_lock.get("identityLockVersionRef")
        or draft.get("identityLockDigest") != identity_digest
        or draft.get("shotPlanAuthorityState")
        != "LOCAL_STRUCTURAL_REPRESENTATION_ONLY"
        or draft.get("shotPlanApprovalState") != "NOT_VERIFIED"
        or draft.get("cameraContractState") != "NOT_READY"
        or draft.get("executionMode") != LOCAL_EVIDENCE
        or draft.get("executionAuthorizationState") != _PREFLIGHT_ONLY
        or draft.get("dispatchAllowed") is not False
        or draft.get("publicationAllowed") is not False
    ):
        raise EpisodeProductionError("image preflight authority lineage is stale")
    profile = _profile(draft)
    shots = _current_shots(draft, creative_shot_drafts)
    blockers = [*_fixed_blockers(), *_postprocess_blockers(shots)]
    created_at = _text(
        draft.get("createdAt"), "shotPlanDraft.createdAt", maximum=100
    )
    request_previews: list[dict[str, Any]] = []
    for shot in shots:
        ordinal = shot["globalOrder"]
        request_previews.append(
            _sealed(
                {
                    "schemaVersion": _IMAGE_REQUEST_PREVIEW_SCHEMA_VERSION,
                    "workspaceRef": workspace_ref,
                    "productionRunRef": production_run_ref,
                    "requestPreviewRef": _preview_ref(
                        "k2-image-request-preview", draft_digest, ordinal
                    ),
                    "ordinal": ordinal,
                    "mediaKind": "image",
                    "mediaType": "image/png",
                    "creativeShotDraftRef": shot["creativeShotDraftRef"],
                    "creativeShotDraftDigest": shot["payloadDigest"],
                    "shotPlanDraftRef": draft["shotPlanDraftRef"],
                    "shotPlanDraftDigest": draft_digest,
                    "productionProfilePreviewRef": profile[
                        "productionProfilePreviewRef"
                    ],
                    "productionProfileDigest": profile[
                        "productionProfileDigest"
                    ],
                    "generationCanvas": deepcopy(profile["generationCanvas"]),
                    "visibleIdentityMode": shot["visibleIdentityMode"],
                    "visibleCharacterRefs": deepcopy(shot["visibleCharacterRefs"]),
                    "visibleIdentityBindings": deepcopy(
                        shot["visibleIdentityBindings"]
                    ),
                    "identityInputs": _identity_inputs(shot, identity_lock),
                    "dialogueSyncMode": shot["dialogueSyncMode"],
                    "dialogueRequirement": deepcopy(
                        shot["dialogueRequirement"]
                    ),
                    "postprocessRequirements": deepcopy(
                        shot["postprocessRequirements"]
                    ),
                    "promptPreview": {
                        "cameraContractState": "NOT_READY",
                        "editorialShotSize": shot["editorialShotSize"],
                        "action": shot["actionBeat"],
                        "continuityConstraints": deepcopy(
                            shot["continuityConstraints"]
                        ),
                        "identityMode": shot["visibleIdentityMode"],
                        "identityBindings": deepcopy(
                            shot["visibleIdentityBindings"]
                        ),
                    },
                    "executionAuthorizationState": _PREFLIGHT_ONLY,
                    "canonicalFact": False,
                    "dispatchAllowed": False,
                    "candidateAdmissionAllowed": False,
                    "publicationAllowed": False,
                    "observedAt": created_at,
                }
            )
        )
    plan = _sealed(
        {
            "schemaVersion": _IMAGE_PLAN_PREVIEW_SCHEMA_VERSION,
            "workspaceRef": workspace_ref,
            "productionRunRef": production_run_ref,
            "imagePlanPreviewRef": _preview_ref(
                "k2-image-plan-preview", draft_digest
            ),
            "shotPlanDraftRef": draft["shotPlanDraftRef"],
            "shotPlanDraftDigest": draft_digest,
            "identityLockVersionRef": identity_lock["identityLockVersionRef"],
            "identityLockDigest": identity_digest,
            "productionProfilePreviewRef": profile[
                "productionProfilePreviewRef"
            ],
            "productionProfileDigest": profile["productionProfileDigest"],
            "outputProfile": profile["outputProfile"],
            "generationCanvas": profile["generationCanvas"],
            "editMaster": profile["editMaster"],
            "releaseMaster": profile["releaseMaster"],
            "expectedRequestPreviewCount": len(request_previews),
            "slotOrdinals": [item["ordinal"] for item in request_previews],
            "requestPreviewRefs": [
                item["requestPreviewRef"] for item in request_previews
            ],
            "requestPreviewDigests": [
                item["payloadDigest"] for item in request_previews
            ],
            "dispatchBlockers": blockers,
            "executionAuthorizationState": _PREFLIGHT_ONLY,
            "integrationState": "PREFLIGHT_ONLY_NOT_INTEGRATED",
            "canonicalMutation": False,
            "dispatchAllowed": False,
            "candidateAdmissionAllowed": False,
            "publicationAllowed": False,
            "observedAt": created_at,
        }
    )
    _validate_image_preview_set(plan, request_previews)
    return {"imagePlanPreview": plan, "imageRequestPreviews": request_previews}


def _validate_image_preview_set(
    plan: Mapping[str, Any], requests: Sequence[Mapping[str, Any]]
) -> None:
    plan_payload = deepcopy(dict(plan))
    plan_digest = plan_payload.pop("payloadDigest", None)
    count = plan.get("expectedRequestPreviewCount")
    if (
        plan.get("schemaVersion") != _IMAGE_PLAN_PREVIEW_SCHEMA_VERSION
        or plan_digest != _digest(plan_payload)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= 120
        or len(requests) != count
        or plan.get("executionAuthorizationState") != _PREFLIGHT_ONLY
        or plan.get("canonicalMutation") is not False
        or plan.get("dispatchAllowed") is not False
        or plan.get("candidateAdmissionAllowed") is not False
        or plan.get("publicationAllowed") is not False
    ):
        raise EpisodeProductionError("image preflight plan is invalid")
    refs: list[str] = []
    digests: list[str] = []
    ordinals: list[int] = []
    slots: set[str] = set()
    for request in requests:
        payload = deepcopy(dict(request))
        digest = payload.pop("payloadDigest", None)
        slot = _required_ref(
            request.get("creativeShotDraftRef"), "creativeShotDraftRef"
        )
        if (
            request.get("schemaVersion") != _IMAGE_REQUEST_PREVIEW_SCHEMA_VERSION
            or digest != _digest(payload)
            or request.get("workspaceRef") != plan.get("workspaceRef")
            or request.get("productionRunRef") != plan.get("productionRunRef")
            or request.get("shotPlanDraftRef")
            != plan.get("shotPlanDraftRef")
            or request.get("shotPlanDraftDigest")
            != plan.get("shotPlanDraftDigest")
            or request.get("executionAuthorizationState") != _PREFLIGHT_ONLY
            or request.get("canonicalFact") is not False
            or request.get("dispatchAllowed") is not False
            or request.get("candidateAdmissionAllowed") is not False
            or request.get("publicationAllowed") is not False
            or slot in slots
        ):
            raise EpisodeProductionError("image request preview is invalid")
        slots.add(slot)
        refs.append(
            _required_ref(request.get("requestPreviewRef"), "requestPreviewRef")
        )
        digests.append(str(digest))
        ordinals.append(request.get("ordinal"))
    if (
        ordinals != list(range(1, count + 1))
        or len(set(refs)) != count
        or plan.get("slotOrdinals") != ordinals
        or plan.get("requestPreviewRefs") != refs
        or plan.get("requestPreviewDigests") != digests
    ):
        raise EpisodeProductionError("image preview cardinality is inconsistent")


class K2DynamicMediaPreflightService:
    """Read current authority facts and return one deterministic zero-write preview."""

    def __init__(self, shot_graph: Any) -> None:
        self.shot_graph = shot_graph

    def preflight(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef",
            "productionRunRef",
        }:
            raise EpisodeProductionError(
                "command fields do not match the image preflight contract"
            )
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(
            command.get("productionRunRef"), "productionRunRef"
        )
        verified = self.shot_graph.verify_shot_plan_draft_current(
            workspace, run_ref
        )
        root = verified.get("root")
        draft = verified.get("shotPlanDraft")
        identity_lock = verified.get("identityLock")
        creative_shots = verified.get("creativeShotDrafts")
        if (
            not isinstance(root, Mapping)
            or root.get("manifest", {}).get("schemaVersion")
            != "k2.golden-episode.manifest.v2"
            or not isinstance(draft, Mapping)
            or draft.get("schemaVersion") != _SHOT_PLAN_DRAFT_SCHEMA_VERSION
            or not isinstance(identity_lock, Mapping)
            or not isinstance(creative_shots, list)
            or root.get("manifest", {}).get("expectedShotCount")
            != len(creative_shots)
        ):
            raise UpstreamNotReadyError(
                "image preflight requires current v2 authority facts"
            )
        preview = _build_image_preview(
            workspace_ref=workspace,
            production_run_ref=run_ref,
            draft=draft,
            creative_shot_drafts=creative_shots,
            identity_lock=identity_lock,
        )
        plan = preview["imagePlanPreview"]
        return _sealed(
            {
                "schemaVersion": DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "rootPayloadDigest": root["payloadDigest"],
                "shotPlanDraftRef": draft["shotPlanDraftRef"],
                "shotPlanDraftDigest": draft["payloadDigest"],
                "identityLockVersionRef": identity_lock[
                    "identityLockVersionRef"
                ],
                "identityLockDigest": identity_lock["payloadDigest"],
                "expectedShotCount": len(creative_shots),
                "imagePlanPreview": plan,
                "imageRequestPreviews": preview["imageRequestPreviews"],
                "dispatchBlockers": deepcopy(plan["dispatchBlockers"]),
                "observedCurrentFacts": {
                    "episodeProductionRun": "CURRENT",
                    "confirmedScriptVersion": "CURRENT",
                    "shotPlanDraft": "CURRENT_LOCAL_STRUCTURAL_DRAFT",
                    "explicitShotFields": "LOCAL_STRUCTURAL_REPRESENTATION",
                    "cameraContract": "NOT_READY",
                    "scriptOwnerAcceptance": "NOT_VERIFIED_BY_PREFLIGHT",
                    "shotPlanApproval": "NOT_VERIFIED_BY_PREFLIGHT",
                    "cameraApproval": "NOT_MODELED",
                },
                "shotPlanInputAuthority": (
                    "LOCAL_STRUCTURAL_REPRESENTATION / "
                    "NOT APPROVED INPUT AUTHORITY"
                ),
                "integrationState": "PREFLIGHT_ONLY_NOT_INTEGRATED",
                "executionAuthorizationState": _PREFLIGHT_ONLY,
                "canonicalMutation": False,
                "dispatchAllowed": False,
                "candidateAdmissionAllowed": False,
                "videoPlanState": "OUT_OF_SCOPE_NOT_BUILT",
                "audioPlanState": "OUT_OF_SCOPE_NOT_BUILT",
                "nextGate": "M10_REAL_IMAGE_PLAN_V2_CANONICAL_APPEND",
                "nextGateState": "BLOCKED",
                "providerExperimentPromotionAllowed": False,
                "publicationAllowed": False,
            }
        )


__all__ = [
    "DYNAMIC_MEDIA_PREFLIGHT_SCHEMA_VERSION",
    "K2DynamicMediaPreflightService",
]
