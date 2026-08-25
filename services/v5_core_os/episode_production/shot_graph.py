"""G3 Script validation, legacy graph compilation, and local draft preparation."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Sequence

from .authority import K2AuthorityIdentityService
from .evidence import EpisodeProductionEvidenceRepository, EvidenceFact, GateAppend
from .foundation import (
    CONTROLLED_EXTENSION_ALGORITHM,
    CONTROLLED_EXTENSION_ALGORITHM_REF,
    DIALOGUE_SOURCE_MODES,
    DIALOGUE_SYNC_MODES,
    EpisodeProductionError,
    EpisodeProductionService,
    ExecutionNotAuthorizedError,
    K2_002_EDITORIAL_SHOT_SIZE_CODES,
    LOCAL_EVIDENCE,
    MANIFEST_SCHEMA_VERSION_V2,
    OUTPUT_PROFILE_SCHEMA_VERSION_V2,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    VISIBLE_IDENTITY_MODES,
    _digest,
    _idempotency_key,
    _read_upstream,
    _required_ref,
)


SCRIPT_VALIDATION_GATE = "G3_SCRIPT_VALIDATION"
SHOT_GRAPH_GATE = "G3_SHOT_GRAPH"
CONSISTENCY_VALIDATION_SCHEMA_VERSION = "v5.consistency-validation.v1"
STORYBOARD_SCHEMA_VERSION = "v5.storyboard-version.v1"
CREATIVE_SHOT_SCHEMA_VERSION = "v5.creative-shot-version.v1"
STORYBOARD_DRAFT_SCHEMA_VERSION = "v5.storyboard-draft.v1"
STORYBOARD_SCENE_DRAFT_SCHEMA_VERSION = "v5.storyboard-scene-draft.v1"
CREATIVE_SHOT_DRAFT_SCHEMA_VERSION = "v5.creative-shot-draft.v1"
SHOT_GRAPH_SCHEMA_VERSION = "v5.executable-shot-graph.v1"
SHOT_PLAN_DRAFT_SCHEMA_VERSION = "v5.local-structural-shot-plan-draft.v1"
COMPILER_ID = "k2.deterministic-shot-compiler.v1"
DRAFT_PREPARER_ID = "k2.local-structural-shot-draft-preparer.v1"

_DRAFT_CONSISTENCY_VALIDATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "consistencyValidationRef",
        "version",
        "rootPayloadDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "identityLockRef",
        "identityLockVersionRef",
        "identityLockDigest",
        "checks",
        "totalFrames",
        "frameRate",
        "result",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)

_SHOT_PLAN_DRAFT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "shotPlanDraftRef",
        "revision",
        "rootPayloadDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "authorityDecisionRef",
        "authorityDecisionDigest",
        "identityLockRef",
        "identityLockVersionRef",
        "identityLockDigest",
        "consistencyValidationRef",
        "consistencyValidationDigest",
        "storyboardDraftRef",
        "storyboardDigest",
        "shots",
        "edges",
        "output",
        "executionMode",
        "publicationAllowed",
        "shotPlanAuthorityState",
        "shotPlanApprovalState",
        "cameraContractState",
        "executionAuthorizationState",
        "dispatchAllowed",
        "status",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_SHOT_PLAN_DRAFT_NODE_FIELDS = frozenset(
    {
        "creativeShotDraftRef",
        "payloadDigest",
        "scriptSceneRef",
        "globalOrder",
        "sceneOrder",
        "durationFrames",
        "frameRate",
        "editorialShotSize",
        "requiredCharacterIdentityLocks",
        "assetRequirementSeeds",
        "continuityConstraints",
        "visibleIdentityMode",
        "visibleCharacterRefs",
        "visibleIdentityBindings",
        "actionBeat",
        "dialogueSyncMode",
        "dialogueRequirement",
        "postprocessRequirements",
    }
)
_OUTPUT_PROFILE_V2_FIELDS = frozenset(
    {
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
    }
)
_STORYBOARD_SCENE_DRAFT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "storyboardDraftRef",
        "storyboardSceneDraftRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "revision",
        "sceneNumber",
        "heading",
        "locationRef",
        "propRefs",
        "durationFrames",
        "creativeShotDraftRefs",
        "status",
        "approvalRequired",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_STORYBOARD_DRAFT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "storyboardDraftRef",
        "revision",
        "rootPayloadDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "consistencyValidationRef",
        "identityLockRef",
        "identityLockVersionRef",
        "identityLockDigest",
        "scenes",
        "status",
        "approvalRequired",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_CREATIVE_SHOT_DRAFT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "creativeShotDraftRef",
        "revision",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "storyboardDraftRef",
        "storyboardSceneDraftRef",
        "sourceScriptSpans",
        "globalOrder",
        "sceneOrder",
        "durationFrames",
        "frameRate",
        "editorialShotSize",
        "action",
        "actionBeat",
        "dialogueRequirements",
        "dialogueSyncMode",
        "dialogueRequirement",
        "audioRequirements",
        "requiredCharacterIdentityLocks",
        "visibleIdentityMode",
        "visibleCharacterRefs",
        "visibleIdentityBindings",
        "assetRequirementSeeds",
        "continuityConstraints",
        "postprocessRequirements",
        "executionMode",
        "status",
        "approvalRequired",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_DRAFT_FORBIDDEN_FIELD_NAMES = frozenset(
    {
        "camera",
        "cameraInstruction",
        "lens",
        "lensMm",
        "movement",
        "angle",
        "shotSize",
        "version",
        "executableShotGraph",
        "executableShotGraphRef",
        "executableShotGraphVersionRef",
        "executableShotGraphDigest",
        "storyboardRef",
        "storyboardVersionRef",
        "storyboardSceneRef",
        "storyboardSceneVersionRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "fromShotRef",
        "toShotRef",
    }
)


class ValidationFailedError(EpisodeProductionError):
    code = "validation_failed"


def require_legacy_executable_graph(graph: Mapping[str, Any]) -> None:
    """Reject preflight-only graphs at legacy execution boundaries."""

    schema_version = graph.get("schemaVersion")
    if schema_version == SHOT_GRAPH_SCHEMA_VERSION:
        if (
            "executionAuthorizationState" in graph
            or "dispatchAllowed" in graph
        ):
            raise StaleInputError(
                "legacy shot graph carries unsupported execution authority"
            )
        return
    if schema_version == SHOT_PLAN_DRAFT_SCHEMA_VERSION:
        if (
            graph.get("status") != "LOCAL_STRUCTURAL_DRAFT"
            or graph.get("executionAuthorizationState")
            != "PREFLIGHT_ONLY_NOT_AUTHORIZED"
            or graph.get("dispatchAllowed") is not False
        ):
            raise StaleInputError("shot plan draft safety boundary is inconsistent")
        raise ExecutionNotAuthorizedError(
            "shot plan draft is preflight-only and not authorized for execution"
        )
    raise StaleInputError("shot graph schema is not execution-compatible")


def require_executable_graph_from_bundle(
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a verified legacy graph or reject a local draft explicitly."""

    draft = bundle.get("shotPlanDraft")
    if isinstance(draft, Mapping):
        validate_shot_plan_draft(draft)
        raise ExecutionNotAuthorizedError(
            "local structural shot plan draft is not executable"
        )
    graph = bundle.get("executableShotGraph")
    if not isinstance(graph, Mapping):
        raise StaleInputError("executable shot graph is unavailable")
    require_legacy_executable_graph(graph)
    return deepcopy(dict(graph))


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value["payloadDigest"] = _digest(value)
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValidationFailedError(f"{field} is invalid")
    return value


def _editorial_shot_size(value: Any, field: str) -> str:
    normalized = _text(value, field)
    if normalized not in K2_002_EDITORIAL_SHOT_SIZE_CODES:
        raise ValidationFailedError(f"{field} is not a K2-002 editorial shot size")
    return normalized


def _strings(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item == item.strip() and item
        for item in value
    ):
        raise ValidationFailedError(f"{field} is invalid")
    return list(value)


def _frames(value: Any, frame_rate: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationFailedError(f"{field} is invalid")
    try:
        frames = Decimal(str(value)) * Decimal(frame_rate)
    except (InvalidOperation, ValueError):
        raise ValidationFailedError(f"{field} is invalid") from None
    integral = frames.to_integral_value()
    if frames != integral or integral <= 0:
        raise ValidationFailedError(f"{field} must align to whole frames")
    return int(integral)


def _graph_ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError:
        raise ValidationFailedError(f"{field} is invalid") from None


def _graph_digest(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationFailedError(f"{field} is invalid")
    return value


def _validate_sealed_payload(value: Mapping[str, Any], field: str) -> str:
    payload = deepcopy(dict(value))
    supplied = _graph_digest(payload.pop("payloadDigest", None), f"{field}.payloadDigest")
    if supplied != _digest(payload):
        raise ValidationFailedError(f"{field} payload digest is invalid")
    return supplied


def _reject_draft_authority_fields(value: Any, field: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _DRAFT_FORBIDDEN_FIELD_NAMES:
                raise ValidationFailedError(
                    f"{field} contains a canonical or camera authority field"
                )
            _reject_draft_authority_fields(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_draft_authority_fields(item, f"{field}[{index}]")


def _camera(global_order: int, scene_order: int, scene_shot_count: int) -> dict[str, Any]:
    if scene_order == 1:
        return {
            "shotSize": "wide",
            "movement": "slow-dolly-in",
            "angle": "eye-level",
            "lensMm": 28,
            "intent": "establish-space-and-character-blocking",
        }
    if scene_order == scene_shot_count:
        return {
            "shotSize": "medium-close-up",
            "movement": "locked-off",
            "angle": "eye-level",
            "lensMm": 50,
            "intent": "hold-performance-and-story-turn",
        }
    cycle = (
        ("medium", "lateral-track", 40, "follow-action"),
        ("close-up", "subtle-push-in", 65, "isolate-decision"),
        ("medium-wide", "pan", 35, "connect-character-and-space"),
    )
    shot_size, movement, lens, intent = cycle[(global_order - 1) % len(cycle)]
    return {
        "shotSize": shot_size,
        "movement": movement,
        "angle": "eye-level",
        "lensMm": lens,
        "intent": intent,
    }


def _validate_camera(value: Any, field: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "shotSize", "movement", "angle", "lensMm", "intent"
    }:
        raise ValidationFailedError(f"{field} is invalid")
    if any(
        not isinstance(value.get(key), str)
        or value.get(key) != value.get(key).strip()
        or not value.get(key)
        for key in ("shotSize", "movement", "angle", "intent")
    ):
        raise ValidationFailedError(f"{field} is invalid")
    lens = value.get("lensMm")
    if isinstance(lens, bool) or not isinstance(lens, int) or lens < 1 or lens > 500:
        raise ValidationFailedError(f"{field} is invalid")


def _validate_postprocess_requirements(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise ValidationFailedError(f"{field} is invalid")
    keys: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {
            "requirementKey", "type", "inputAssetRequirementKeys", "status"
        }:
            raise ValidationFailedError(f"{field}[{index}] is invalid")
        _graph_ref(item.get("requirementKey"), f"{field}[{index}].requirementKey")
        _graph_ref(item.get("type"), f"{field}[{index}].type")
        input_keys = item.get("inputAssetRequirementKeys")
        if (
            not isinstance(input_keys, list)
            or not input_keys
            or any(
                not isinstance(key, str)
                or not key
                for key in input_keys
            )
            or len(input_keys) != len(set(input_keys))
            or item.get("status") != "NOT_READY"
        ):
            raise ValidationFailedError(f"{field}[{index}] is invalid")
        for key_index, key in enumerate(input_keys):
            _graph_ref(
                key,
                f"{field}[{index}].inputAssetRequirementKeys[{key_index}]",
            )
        keys.append(item["requirementKey"])
    if len(keys) != len(set(keys)):
        raise ValidationFailedError(f"{field} has duplicate requirement keys")


def _validate_dialogue_requirement(
    value: Any,
    field: str,
    *,
    dialogue_sync_mode: str,
    visible_identity_mode: str,
    identity_bindings: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "speaker", "text", "sourceMode"
    }:
        raise ValidationFailedError(f"{field} is invalid")
    source_mode = value.get("sourceMode")
    speaker = value.get("speaker")
    text = value.get("text")
    if source_mode not in DIALOGUE_SOURCE_MODES:
        raise ValidationFailedError(f"{field}.sourceMode is invalid")
    if speaker is not None and (
        not isinstance(speaker, str) or speaker != speaker.strip() or not speaker
    ):
        raise ValidationFailedError(f"{field}.speaker is invalid")
    if (
        not isinstance(text, str)
        or text != text.strip()
        or not text
    ):
        raise ValidationFailedError(f"{field}.text is invalid")
    if source_mode == "DIALOGUE":
        if speaker is None or dialogue_sync_mode == "NONE":
            raise ValidationFailedError(f"{field} dialogue sync is invalid")
        if dialogue_sync_mode == "VERIFIED_LIP_SYNC":
            face_names = {
                item.get("scriptCharacterName")
                for item in identity_bindings
                if item.get("bindingMode") == "FACE_LOCK"
            }
            if (
                visible_identity_mode not in {"FACE_LOCK", "MIXED"}
                or speaker not in face_names
            ):
                raise ValidationFailedError(
                    f"{field} verified lip sync speaker is not face locked"
                )
    elif source_mode == "NARRATION":
        if (
            speaker is None
            or dialogue_sync_mode != "OFF_CAMERA_OR_NON_VISIBLE_MOUTH"
        ):
            raise ValidationFailedError(f"{field} narration sync is invalid")
    elif speaker is not None or dialogue_sync_mode != "NONE":
        raise ValidationFailedError(f"{field} SFX/silence sync is invalid")


def validate_draft_consistency_validation(
    validation: Mapping[str, Any],
) -> None:
    """Validate sealed v2 draft-only G3 consistency evidence exactly."""

    if (
        not isinstance(validation, Mapping)
        or set(validation) != _DRAFT_CONSISTENCY_VALIDATION_FIELDS
    ):
        raise ValidationFailedError("ConsistencyValidation fields are invalid")
    _validate_sealed_payload(validation, "ConsistencyValidation")
    if (
        validation.get("schemaVersion")
        != CONSISTENCY_VALIDATION_SCHEMA_VERSION
        or validation.get("version") != 1
        or validation.get("result") != "PASSED"
        or validation.get("createdBy") != DRAFT_PREPARER_ID
    ):
        raise ValidationFailedError("ConsistencyValidation authority is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "consistencyValidationRef",
        "scriptVersionRef",
        "authorityDecisionRef",
        "identityLockRef",
        "identityLockVersionRef",
    ):
        _graph_ref(validation.get(field), f"ConsistencyValidation.{field}")
    for field in (
        "rootPayloadDigest",
        "scriptVersionDigest",
        "authorityDecisionDigest",
        "identityLockDigest",
    ):
        _graph_digest(validation.get(field), f"ConsistencyValidation.{field}")
    total_frames = validation.get("totalFrames")
    frame_rate = validation.get("frameRate")
    if (
        isinstance(total_frames, bool)
        or not isinstance(total_frames, int)
        or total_frames < 1
        or isinstance(frame_rate, bool)
        or not isinstance(frame_rate, int)
        or not 1 <= frame_rate <= 240
    ):
        raise ValidationFailedError("ConsistencyValidation frame accounting is invalid")
    _text(validation.get("createdAt"), "ConsistencyValidation.createdAt")
    checks = validation.get("checks")
    if not isinstance(checks, list) or len(checks) < 4 or not all(
        isinstance(item, Mapping) for item in checks
    ):
        raise ValidationFailedError("ConsistencyValidation checks are invalid")
    scene_checks = checks[:-3]
    if not scene_checks:
        raise ValidationFailedError("ConsistencyValidation scene checks are missing")
    scene_refs: list[str] = []
    for scene_number, check in enumerate(scene_checks, start=1):
        if (
            set(check) != {"checkId", "status", "scriptSceneRef"}
            or check.get("checkId")
            != f"scene-{scene_number}-identity-and-authority"
            or check.get("status") != "PASSED"
        ):
            raise ValidationFailedError(
                "ConsistencyValidation scene check is invalid"
            )
        scene_refs.append(
            _graph_ref(
                check.get("scriptSceneRef"),
                f"ConsistencyValidation.checks[{scene_number - 1}]"
                ".scriptSceneRef",
            )
        )
    if len(scene_refs) != len(set(scene_refs)):
        raise ValidationFailedError("ConsistencyValidation scene coverage is ambiguous")
    script_check, frame_check, identity_check = checks[-3:]
    if (
        set(script_check) != {"checkId", "status", "scriptVersionRef"}
        or script_check.get("checkId") != "script-version-digest-current"
        or script_check.get("status") != "PASSED"
        or script_check.get("scriptVersionRef")
        != validation.get("scriptVersionRef")
        or set(frame_check)
        != {"checkId", "status", "totalFrames", "frameRate"}
        or frame_check.get("checkId") != "frame-accounting-exact"
        or frame_check.get("status") != "PASSED"
        or frame_check.get("totalFrames") != total_frames
        or frame_check.get("frameRate") != frame_rate
        or set(identity_check)
        != {"checkId", "status", "identityLockVersionRef"}
        or identity_check.get("checkId") != "identity-lock-complete"
        or identity_check.get("status") != "PASSED"
        or identity_check.get("identityLockVersionRef")
        != validation.get("identityLockVersionRef")
    ):
        raise ValidationFailedError("ConsistencyValidation fixed checks are invalid")


def validate_storyboard_scene_draft(scene: Mapping[str, Any]) -> None:
    """Validate one sealed, non-canonical storyboard scene draft."""

    if not isinstance(scene, Mapping) or set(scene) != _STORYBOARD_SCENE_DRAFT_FIELDS:
        raise ValidationFailedError("StoryboardSceneDraft fields are invalid")
    _reject_draft_authority_fields(scene, "StoryboardSceneDraft")
    _validate_sealed_payload(scene, "StoryboardSceneDraft")
    if (
        scene.get("schemaVersion") != STORYBOARD_SCENE_DRAFT_SCHEMA_VERSION
        or scene.get("revision") != 1
        or scene.get("status") != "LOCAL_STRUCTURAL_DRAFT"
        or scene.get("approvalRequired") is not True
        or scene.get("createdBy") != DRAFT_PREPARER_ID
    ):
        raise ValidationFailedError("StoryboardSceneDraft authority is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "storyboardDraftRef",
        "storyboardSceneDraftRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "locationRef",
    ):
        _graph_ref(scene.get(field), f"StoryboardSceneDraft.{field}")
    scene_number = scene.get("sceneNumber")
    duration = scene.get("durationFrames")
    if (
        isinstance(scene_number, bool)
        or not isinstance(scene_number, int)
        or scene_number < 1
        or isinstance(duration, bool)
        or not isinstance(duration, int)
        or duration < 1
    ):
        raise ValidationFailedError("StoryboardSceneDraft timing is invalid")
    _text(scene.get("heading"), "StoryboardSceneDraft.heading")
    _text(scene.get("createdAt"), "StoryboardSceneDraft.createdAt")
    prop_refs = _strings(scene.get("propRefs"), "StoryboardSceneDraft.propRefs")
    shot_refs = _strings(
        scene.get("creativeShotDraftRefs"),
        "StoryboardSceneDraft.creativeShotDraftRefs",
    )
    if (
        len(prop_refs) != len(set(prop_refs))
        or not shot_refs
        or len(shot_refs) != len(set(shot_refs))
    ):
        raise ValidationFailedError("StoryboardSceneDraft references are invalid")
    for index, ref in enumerate(prop_refs):
        _graph_ref(ref, f"StoryboardSceneDraft.propRefs[{index}]")
    for index, ref in enumerate(shot_refs):
        _graph_ref(ref, f"StoryboardSceneDraft.creativeShotDraftRefs[{index}]")


def validate_storyboard_draft(storyboard: Mapping[str, Any]) -> None:
    """Validate one sealed storyboard draft and every sealed scene draft."""

    if not isinstance(storyboard, Mapping) or set(storyboard) != _STORYBOARD_DRAFT_FIELDS:
        raise ValidationFailedError("StoryboardDraft fields are invalid")
    _reject_draft_authority_fields(storyboard, "StoryboardDraft")
    _validate_sealed_payload(storyboard, "StoryboardDraft")
    if (
        storyboard.get("schemaVersion") != STORYBOARD_DRAFT_SCHEMA_VERSION
        or storyboard.get("revision") != 1
        or storyboard.get("status") != "LOCAL_STRUCTURAL_DRAFT"
        or storyboard.get("approvalRequired") is not True
        or storyboard.get("createdBy") != DRAFT_PREPARER_ID
    ):
        raise ValidationFailedError("StoryboardDraft authority is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "storyboardDraftRef",
        "scriptRef",
        "scriptVersionRef",
        "consistencyValidationRef",
        "identityLockRef",
        "identityLockVersionRef",
    ):
        _graph_ref(storyboard.get(field), f"StoryboardDraft.{field}")
    for field in (
        "rootPayloadDigest",
        "scriptVersionDigest",
        "identityLockDigest",
    ):
        _graph_digest(storyboard.get(field), f"StoryboardDraft.{field}")
    _text(storyboard.get("createdAt"), "StoryboardDraft.createdAt")
    scenes = storyboard.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValidationFailedError("StoryboardDraft scenes are invalid")
    refs: set[str] = set()
    script_scene_refs: set[str] = set()
    for index, scene in enumerate(scenes, start=1):
        validate_storyboard_scene_draft(scene)
        if (
            scene.get("workspaceRef") != storyboard.get("workspaceRef")
            or scene.get("productionRunRef") != storyboard.get("productionRunRef")
            or scene.get("storyboardDraftRef") != storyboard.get("storyboardDraftRef")
            or scene.get("scriptVersionRef") != storyboard.get("scriptVersionRef")
            or scene.get("sceneNumber") != index
            or scene.get("createdAt") != storyboard.get("createdAt")
            or scene.get("storyboardSceneDraftRef") in refs
            or scene.get("scriptSceneRef") in script_scene_refs
        ):
            raise ValidationFailedError("StoryboardSceneDraft lineage is invalid")
        refs.add(scene["storyboardSceneDraftRef"])
        script_scene_refs.add(scene["scriptSceneRef"])


def validate_creative_shot_draft(creative: Mapping[str, Any]) -> None:
    """Validate one sealed, non-executable creative shot draft."""

    if not isinstance(creative, Mapping) or set(creative) != _CREATIVE_SHOT_DRAFT_FIELDS:
        raise ValidationFailedError("CreativeShotDraft fields are invalid")
    _reject_draft_authority_fields(creative, "CreativeShotDraft")
    _validate_sealed_payload(creative, "CreativeShotDraft")
    if (
        creative.get("schemaVersion") != CREATIVE_SHOT_DRAFT_SCHEMA_VERSION
        or creative.get("revision") != 1
        or creative.get("executionMode") != LOCAL_EVIDENCE
        or creative.get("status") != "LOCAL_STRUCTURAL_DRAFT"
        or creative.get("approvalRequired") is not True
        or creative.get("createdBy") != DRAFT_PREPARER_ID
    ):
        raise ValidationFailedError("CreativeShotDraft authority is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "creativeShotDraftRef",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "storyboardDraftRef",
        "storyboardSceneDraftRef",
    ):
        _graph_ref(creative.get(field), f"CreativeShotDraft.{field}")
    for field in ("globalOrder", "sceneOrder", "durationFrames", "frameRate"):
        value = creative.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValidationFailedError(f"CreativeShotDraft.{field} is invalid")
    _editorial_shot_size(
        creative.get("editorialShotSize"),
        "CreativeShotDraft.editorialShotSize",
    )
    action = _text(creative.get("action"), "CreativeShotDraft.action")
    if action != _text(creative.get("actionBeat"), "CreativeShotDraft.actionBeat"):
        raise ValidationFailedError("CreativeShotDraft action lineage is invalid")
    _text(creative.get("createdAt"), "CreativeShotDraft.createdAt")
    source_spans = _strings(
        creative.get("sourceScriptSpans"),
        "CreativeShotDraft.sourceScriptSpans",
    )
    continuity = _strings(
        creative.get("continuityConstraints"),
        "CreativeShotDraft.continuityConstraints",
    )
    if (
        not source_spans
        or len(source_spans) != len(set(source_spans))
        or not continuity
        or len(continuity) != len(set(continuity))
    ):
        raise ValidationFailedError("CreativeShotDraft source lineage is invalid")
    identities = creative.get("requiredCharacterIdentityLocks")
    visible_refs = creative.get("visibleCharacterRefs")
    visible_bindings = creative.get("visibleIdentityBindings")
    visible_mode = creative.get("visibleIdentityMode")
    if (
        not isinstance(identities, list)
        or not all(isinstance(item, Mapping) for item in identities)
        or not isinstance(visible_refs, list)
        or not isinstance(visible_bindings, list)
        or visible_mode not in VISIBLE_IDENTITY_MODES
        or not all(
            isinstance(item, Mapping)
            and set(item) == {"characterRef", "bindingMode"}
            for item in visible_bindings
        )
        or [item.get("characterRef") for item in identities] != visible_refs
        or [
            {
                "characterRef": item.get("characterRef"),
                "bindingMode": item.get("bindingMode"),
            }
            for item in identities
        ]
        != visible_bindings
    ):
        raise ValidationFailedError("CreativeShotDraft identity lineage is invalid")
    identity_modes: set[str] = set()
    for index, identity in enumerate(identities):
        mode = identity.get("bindingMode")
        identity_modes.add(str(mode))
        expected_fields = (
            {
                "bindingMode",
                "scriptCharacterName",
                "characterRef",
                "characterContinuityVersionRef",
                "characterContinuityVersionDigest",
                "characterFactDigest",
            }
            if mode == "BODY_ONLY"
            else {
                "bindingMode",
                "scriptCharacterName",
                "characterRef",
                "identityLockRef",
                "identityLockVersionRef",
                "identityLockDigest",
                "referenceVersionRef",
                "referenceDigest",
            }
            if mode == "FACE_LOCK"
            else set()
        )
        if set(identity) != expected_fields:
            raise ValidationFailedError(
                f"CreativeShotDraft.requiredCharacterIdentityLocks[{index}] is invalid"
            )
        _text(
            identity.get("scriptCharacterName"),
            f"CreativeShotDraft.requiredCharacterIdentityLocks[{index}]"
            ".scriptCharacterName",
        )
        for field in expected_fields - {
            "bindingMode",
            "scriptCharacterName",
            "characterContinuityVersionDigest",
            "characterFactDigest",
            "identityLockDigest",
            "referenceDigest",
        }:
            _graph_ref(
                identity.get(field),
                f"CreativeShotDraft.requiredCharacterIdentityLocks[{index}].{field}",
            )
        for field in expected_fields & {
            "characterContinuityVersionDigest",
            "characterFactDigest",
            "identityLockDigest",
            "referenceDigest",
        }:
            _graph_digest(
                identity.get(field),
                f"CreativeShotDraft.requiredCharacterIdentityLocks[{index}].{field}",
            )
    derived_mode = (
        "NONE"
        if not identity_modes
        else next(iter(identity_modes))
        if len(identity_modes) == 1
        else "MIXED"
    )
    if (
        len(visible_refs) != len(set(visible_refs))
        or derived_mode != visible_mode
        or any(
            item.get("bindingMode") not in {"BODY_ONLY", "FACE_LOCK"}
            for item in visible_bindings
        )
    ):
        raise ValidationFailedError("CreativeShotDraft identity mode is invalid")

    asset_seeds = creative.get("assetRequirementSeeds")
    if not isinstance(asset_seeds, list) or not asset_seeds:
        raise ValidationFailedError("CreativeShotDraft asset requirements are invalid")
    requirement_keys: list[str] = []
    for index, seed in enumerate(asset_seeds):
        if not isinstance(seed, Mapping) or set(seed) != {
            "requirementKey",
            "requirementType",
            "authorityRef",
            "authorityVersionRef",
            "authorityDigest",
            "required",
        } or seed.get("required") is not True:
            raise ValidationFailedError(
                f"CreativeShotDraft.assetRequirementSeeds[{index}] is invalid"
            )
        for field in (
            "requirementKey",
            "requirementType",
            "authorityRef",
            "authorityVersionRef",
        ):
            _graph_ref(
                seed.get(field),
                f"CreativeShotDraft.assetRequirementSeeds[{index}].{field}",
            )
        _graph_digest(
            seed.get("authorityDigest"),
            f"CreativeShotDraft.assetRequirementSeeds[{index}].authorityDigest",
        )
        requirement_keys.append(seed["requirementKey"])
    if len(requirement_keys) != len(set(requirement_keys)):
        raise ValidationFailedError("CreativeShotDraft asset requirements are ambiguous")

    audio = creative.get("audioRequirements")
    dialogue_requirements = creative.get("dialogueRequirements")
    if (
        not isinstance(audio, Mapping)
        or set(audio) != {"dialogue", "narration", "subtitleText", "ambience"}
        or not isinstance(dialogue_requirements, list)
        or audio.get("dialogue") != dialogue_requirements
        or not isinstance(audio.get("narration"), list)
        or not isinstance(audio.get("subtitleText"), list)
        or not all(
            isinstance(item, Mapping)
            and set(item) == {"speaker", "text", "emotion"}
            and all(isinstance(item.get(field), str) and item.get(field)
                    for field in ("speaker", "text", "emotion"))
            for item in dialogue_requirements
        )
    ):
        raise ValidationFailedError("CreativeShotDraft audio requirements are invalid")
    _strings(
        audio.get("narration"),
        "CreativeShotDraft.audioRequirements.narration",
    )
    _strings(
        audio.get("subtitleText"),
        "CreativeShotDraft.audioRequirements.subtitleText",
    )
    _text(audio.get("ambience"), "CreativeShotDraft.audioRequirements.ambience")
    dialogue_sync_mode = creative.get("dialogueSyncMode")
    if dialogue_sync_mode not in DIALOGUE_SYNC_MODES:
        raise ValidationFailedError("CreativeShotDraft dialogue sync mode is invalid")
    _validate_dialogue_requirement(
        creative.get("dialogueRequirement"),
        "CreativeShotDraft.dialogueRequirement",
        dialogue_sync_mode=dialogue_sync_mode,
        visible_identity_mode=visible_mode,
        identity_bindings=identities,
    )
    _validate_postprocess_requirements(
        creative.get("postprocessRequirements"),
        "CreativeShotDraft.postprocessRequirements",
    )


def _validate_draft_identities_against_lock(
    shots: Sequence[Mapping[str, Any]],
    identity_lock: Mapping[str, Any],
) -> None:
    current_identities = identity_lock.get("identities")
    if not isinstance(current_identities, list) or not all(
        isinstance(item, Mapping) for item in current_identities
    ):
        raise ValidationFailedError("current IdentityLock mapping is malformed")
    identity_by_name = {
        item.get("scriptCharacterName"): item for item in current_identities
    }
    if len(identity_by_name) != len(current_identities):
        raise ValidationFailedError("current IdentityLock mapping is ambiguous")
    for shot in shots:
        locks = shot.get("requiredCharacterIdentityLocks")
        if not isinstance(locks, list):
            raise ValidationFailedError("CreativeShotDraft identity mapping is malformed")
        for lock in locks:
            current = identity_by_name.get(lock.get("scriptCharacterName"))
            if (
                not isinstance(current, Mapping)
                or lock.get("characterRef") != current.get("characterRef")
            ):
                raise ValidationFailedError(
                    "CreativeShotDraft identity mapping is stale"
                )
            if lock.get("bindingMode") == "FACE_LOCK":
                reference = current.get("reference")
                if (
                    not isinstance(reference, Mapping)
                    or lock.get("identityLockRef")
                    != identity_lock.get("identityLockRef")
                    or lock.get("identityLockVersionRef")
                    != identity_lock.get("identityLockVersionRef")
                    or lock.get("identityLockDigest")
                    != identity_lock.get("payloadDigest")
                    or lock.get("referenceVersionRef")
                    != reference.get("referenceVersionRef")
                    or lock.get("referenceDigest")
                    != reference.get("contentDigest")
                ):
                    raise ValidationFailedError(
                        "CreativeShotDraft face identity mapping is stale"
                    )
            elif lock.get("bindingMode") == "BODY_ONLY":
                if (
                    lock.get("characterFactDigest")
                    != current.get("characterFactDigest")
                    or lock.get("characterContinuityVersionRef")
                    != identity_lock.get("characterContinuityVersionRef")
                    or lock.get("characterContinuityVersionDigest")
                    != identity_lock.get("characterContinuityVersionDigest")
                ):
                    raise ValidationFailedError(
                        "CreativeShotDraft body identity mapping is stale"
                    )
            else:
                raise ValidationFailedError(
                    "CreativeShotDraft identity binding mode is stale"
                )


def _validate_output_profile_v2(output: Mapping[str, Any]) -> None:
    if (
        set(output) != _OUTPUT_PROFILE_V2_FIELDS
        or output.get("schemaVersion") != OUTPUT_PROFILE_SCHEMA_VERSION_V2
    ):
        raise ValidationFailedError("Shot Graph output v2 schema is invalid")
    orientation = output.get("orientation")
    generation = output.get("generationCanvas")
    edit = output.get("editMaster")
    release = output.get("releaseMaster")
    if not all(isinstance(item, Mapping) for item in (generation, edit, release)):
        raise ValidationFailedError("Shot Graph output profiles are incomplete")
    if orientation == "PORTRAIT":
        if (
            dict(generation) != {"width": 704, "height": 1280, "aspectRatio": "11:20"}
            or dict(edit) != {"width": 720, "height": 1280, "aspectRatio": "9:16"}
            or dict(release) != {"width": 1080, "height": 1920, "aspectRatio": "9:16"}
            or output.get("targetAspectRatio") != "9:16"
            or output.get("width") != 704
            or output.get("height") != 1280
            or output.get("aspectRatio") != "11:20"
        ):
            raise ValidationFailedError("Shot Graph portrait output profiles are invalid")
        algorithm = output.get("controlledExtensionAlgorithm")
        if (
            not isinstance(algorithm, Mapping)
            or dict(algorithm) != CONTROLLED_EXTENSION_ALGORITHM
            or output.get("controlledExtensionAlgorithmRef")
            != CONTROLLED_EXTENSION_ALGORITHM_REF
            or output.get("controlledExtensionAlgorithmDigest")
            != _digest(dict(algorithm))
        ):
            raise ValidationFailedError(
                "Shot Graph controlled extension contract is invalid"
            )
    elif orientation == "LANDSCAPE":
        if (
            dict(generation) != {"width": 1280, "height": 720, "aspectRatio": "16:9"}
            or dict(edit) != {"width": 1280, "height": 720, "aspectRatio": "16:9"}
            or dict(release) != {"width": 1920, "height": 1080, "aspectRatio": "16:9"}
            or output.get("targetAspectRatio") != "16:9"
            or output.get("controlledExtensionAlgorithmRef") is not None
            or output.get("controlledExtensionAlgorithmDigest") is not None
            or output.get("controlledExtensionAlgorithm") is not None
        ):
            raise ValidationFailedError("Shot Graph landscape output profiles are invalid")
    else:
        raise ValidationFailedError("Shot Graph output orientation is invalid")
    if output.get("frameRate") != 24 or output.get("container") != "mp4":
        raise ValidationFailedError("Shot Graph output encoding profile is invalid")


def _validate_shot_structure(
    graph: Mapping[str, Any], *, draft: bool
) -> None:
    if not isinstance(graph, Mapping):
        raise ValidationFailedError("shot structure must be an object")
    schema_version = graph.get("schemaVersion")
    expected_schema = (
        SHOT_PLAN_DRAFT_SCHEMA_VERSION if draft else SHOT_GRAPH_SCHEMA_VERSION
    )
    if schema_version != expected_schema:
        raise ValidationFailedError("shot structure schema is unsupported")
    if draft:
        _reject_draft_authority_fields(graph, "ShotPlanDraft")
        _validate_sealed_payload(graph, "ShotPlanDraft")
        if (
            set(graph) != _SHOT_PLAN_DRAFT_FIELDS
            or graph.get("revision") != 1
            or graph.get("executionMode") != LOCAL_EVIDENCE
            or graph.get("publicationAllowed") is not False
            or graph.get("createdBy") != DRAFT_PREPARER_ID
            or graph.get("shotPlanAuthorityState")
            != "LOCAL_STRUCTURAL_REPRESENTATION_ONLY"
            or graph.get("shotPlanApprovalState") != "NOT_VERIFIED"
            or graph.get("cameraContractState") != "NOT_READY"
            or graph.get("executionAuthorizationState")
            != "PREFLIGHT_ONLY_NOT_AUTHORIZED"
            or graph.get("dispatchAllowed") is not False
            or graph.get("status") != "LOCAL_STRUCTURAL_DRAFT"
            or any(
                key in graph
                for key in (
                    "executableShotGraphRef",
                    "executableShotGraphVersionRef",
                    "storyboardRef",
                    "storyboardVersionRef",
                    "version",
                )
            )
        ):
            raise ValidationFailedError(
                "shot plan draft execution authority is invalid"
            )
        _graph_ref(graph.get("shotPlanDraftRef"), "shotPlanDraftRef")
        for field in (
            "workspaceRef",
            "productionRunRef",
            "scriptVersionRef",
            "authorityDecisionRef",
            "identityLockRef",
            "identityLockVersionRef",
            "consistencyValidationRef",
            "storyboardDraftRef",
        ):
            _graph_ref(graph.get(field), field)
        for field in (
            "rootPayloadDigest",
            "scriptVersionDigest",
            "authorityDecisionDigest",
            "identityLockDigest",
            "consistencyValidationDigest",
            "storyboardDigest",
        ):
            _graph_digest(graph.get(field), field)
        _text(graph.get("createdAt"), "ShotPlanDraft.createdAt")
    nodes = graph.get("shots")
    edges = graph.get("edges")
    output = graph.get("output")
    if (
        not isinstance(nodes, list)
        or not nodes
        or not all(isinstance(item, Mapping) for item in nodes)
        or not isinstance(edges, list)
        or not all(isinstance(item, Mapping) for item in edges)
        or not isinstance(output, Mapping)
    ):
        raise ValidationFailedError("Shot Graph collections are invalid")
    refs: list[str] = []
    orders: list[int] = []
    frame_total = 0
    for index, node in enumerate(nodes):
        if draft and set(node) != _SHOT_PLAN_DRAFT_NODE_FIELDS:
            raise ValidationFailedError(
                "shot plan draft contains a canonical or executable field"
            )
        ref_field = "creativeShotDraftRef" if draft else "creativeShotRef"
        shot_ref = _graph_ref(node.get(ref_field), f"shots[{index}].{ref_field}")
        if shot_ref in refs:
            raise ValidationFailedError("Shot Graph has duplicate shot refs")
        refs.append(shot_ref)
        order = node.get("globalOrder")
        duration = node.get("durationFrames")
        if isinstance(order, bool) or not isinstance(order, int):
            raise ValidationFailedError("Shot Graph order is invalid")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise ValidationFailedError("Shot Graph duration is invalid")
        identities = node.get("requiredCharacterIdentityLocks")
        requirements = node.get("assetRequirementSeeds")
        if not isinstance(identities, list) or not all(
            isinstance(item, Mapping) for item in identities
        ):
            raise ValidationFailedError("Shot Graph has an unresolved character identity")
        if not draft:
            if not identities or not all(
                isinstance(item.get("characterRef"), str)
                and isinstance(item.get("identityLockVersionRef"), str)
                and isinstance(item.get("referenceVersionRef"), str)
                for item in identities
            ):
                raise ValidationFailedError(
                    "Shot Graph has an unresolved character identity"
                )
        else:
            visible_mode = node.get("visibleIdentityMode")
            visible_refs = node.get("visibleCharacterRefs")
            visible_bindings = node.get("visibleIdentityBindings")
            dialogue_sync_mode = node.get("dialogueSyncMode")
            if visible_mode not in VISIBLE_IDENTITY_MODES:
                raise ValidationFailedError("Shot Graph visible identity mode is invalid")
            if (
                not isinstance(visible_refs, list)
                or not all(isinstance(ref, str) for ref in visible_refs)
                or len(visible_refs) != len(set(visible_refs))
            ):
                raise ValidationFailedError("Shot Graph visible character refs are invalid")
            if not isinstance(visible_bindings, list):
                raise ValidationFailedError(
                    "Shot Graph visible identity bindings are invalid"
                )
            normalized_visible_bindings: list[dict[str, str]] = []
            for binding_index, binding in enumerate(visible_bindings):
                if not isinstance(binding, Mapping) or set(binding) != {
                    "characterRef", "bindingMode"
                }:
                    raise ValidationFailedError(
                        "Shot Graph visible identity bindings are invalid"
                    )
                normalized_visible_bindings.append(
                    {
                        "characterRef": _graph_ref(
                            binding.get("characterRef"),
                            (
                                f"shots[{index}].visibleIdentityBindings"
                                f"[{binding_index}].characterRef"
                            ),
                        ),
                        "bindingMode": binding.get("bindingMode"),
                    }
                )
            if any(
                item["bindingMode"] not in {"BODY_ONLY", "FACE_LOCK"}
                for item in normalized_visible_bindings
            ):
                raise ValidationFailedError(
                    "Shot Graph visible identity bindings are invalid"
                )
            if dialogue_sync_mode not in DIALOGUE_SYNC_MODES:
                raise ValidationFailedError("Shot Graph dialogue sync mode is invalid")
            if dialogue_sync_mode == "VERIFIED_LIP_SYNC":
                raise ValidationFailedError(
                    "Shot Graph verified lip sync has no trusted evidence contract"
                )
            _editorial_shot_size(
                node.get("editorialShotSize"),
                f"shots[{index}].editorialShotSize",
            )
            _validate_postprocess_requirements(
                node.get("postprocessRequirements"),
                f"shots[{index}].postprocessRequirements",
            )
            action_beat = node.get("actionBeat")
            if (
                not isinstance(action_beat, str)
                or action_beat != action_beat.strip()
                or not action_beat
            ):
                raise ValidationFailedError("Shot Graph action beat is invalid")
            bound_refs = [item.get("characterRef") for item in identities]
            expected_visible_bindings = [
                {
                    "characterRef": item.get("characterRef"),
                    "bindingMode": item.get("bindingMode"),
                }
                for item in identities
            ]
            if (
                len(bound_refs) != len(set(bound_refs))
                or bound_refs != visible_refs
                or expected_visible_bindings != normalized_visible_bindings
            ):
                raise ValidationFailedError(
                    "Shot Graph visible character binding is inconsistent"
                )
            if visible_mode == "NONE":
                if visible_refs or visible_bindings or identities:
                    raise ValidationFailedError(
                        "Shot Graph NONE identity mode must not claim an identity lock"
                    )
            else:
                if not visible_refs or not identities:
                    raise ValidationFailedError(
                        "Shot Graph visible character identity is unresolved"
                    )
                binding_modes = {item.get("bindingMode") for item in identities}
                derived_mode = (
                    next(iter(binding_modes))
                    if len(binding_modes) == 1
                    else "MIXED"
                )
                if (
                    not binding_modes <= {"BODY_ONLY", "FACE_LOCK"}
                    or visible_mode != derived_mode
                ):
                    raise ValidationFailedError(
                        "Shot Graph visible identity mode does not match its bindings"
                    )
                forbidden_face_fields = {
                    "identityLockRef", "identityLockVersionRef",
                    "identityLockDigest", "referenceVersionRef", "referenceDigest",
                }
                for identity in identities:
                    if identity.get("bindingMode") == "BODY_ONLY":
                        if (
                            not isinstance(identity.get("characterRef"), str)
                            or not isinstance(
                                identity.get("characterContinuityVersionRef"), str
                            )
                            or forbidden_face_fields.intersection(identity)
                        ):
                            raise ValidationFailedError(
                                "Shot Graph BODY_ONLY binding improperly claims face identity"
                            )
                        _graph_digest(
                            identity.get("characterContinuityVersionDigest"),
                            "characterContinuityVersionDigest",
                        )
                        _graph_digest(
                            identity.get("characterFactDigest"),
                            "characterFactDigest",
                        )
                    elif (
                        not isinstance(identity.get("characterRef"), str)
                        or identity.get("identityLockRef")
                        != graph.get("identityLockRef")
                        or identity.get("identityLockVersionRef")
                        != graph.get("identityLockVersionRef")
                        or identity.get("identityLockDigest")
                        != graph.get("identityLockDigest")
                        or not isinstance(identity.get("referenceVersionRef"), str)
                    ):
                        raise ValidationFailedError(
                            "Shot Graph FACE_LOCK binding is not exact"
                        )
                    else:
                        _graph_digest(
                            identity.get("referenceDigest"), "referenceDigest"
                        )
            _validate_dialogue_requirement(
                node.get("dialogueRequirement"),
                f"shots[{index}].dialogueRequirement",
                dialogue_sync_mode=dialogue_sync_mode,
                visible_identity_mode=visible_mode,
                identity_bindings=identities,
            )
        if (
            not isinstance(requirements, list)
            or not requirements
            or not all(
                isinstance(item, Mapping)
                and item.get("required") is True
                and isinstance(item.get("requirementKey"), str)
                and item.get("authorityRef")
                for item in requirements
            )
            or len({item["requirementKey"] for item in requirements})
            != len(requirements)
        ):
            raise ValidationFailedError("Shot Graph has an unresolved asset requirement")
        orders.append(order)
        frame_total += duration
    if sorted(orders) != list(range(1, len(nodes) + 1)):
        raise ValidationFailedError("Shot Graph order must be contiguous")
    if output.get("totalFrames") != frame_total:
        raise ValidationFailedError("Shot Graph frame accounting is inconsistent")
    if draft:
        _validate_output_profile_v2(output)
    chronological = set()
    adjacency: dict[str, set[str]] = {ref: set() for ref in refs}
    for index, edge in enumerate(edges):
        source_field = "fromShotDraftRef" if draft else "fromShotRef"
        target_field = "toShotDraftRef" if draft else "toShotRef"
        source = edge.get(source_field)
        target = edge.get(target_field)
        edge_type = edge.get("edgeType")
        if draft:
            expected_edge_fields = {
                "edgeRef",
                "edgeType",
                "fromShotDraftRef",
                "toShotDraftRef",
            }
            if edge_type == "continuity":
                expected_edge_fields.update({"continuityKind", "characterRef"})
            if set(edge) != expected_edge_fields:
                raise ValidationFailedError(
                    f"edges[{index}] contains a canonical or unsupported field"
                )
            _graph_ref(edge.get("edgeRef"), f"edges[{index}].edgeRef")
            if edge_type == "continuity":
                if edge.get("continuityKind") not in {
                    "character-face-identity",
                    "character-non-face-continuity",
                }:
                    raise ValidationFailedError(
                        f"edges[{index}] has invalid continuity kind"
                    )
                _graph_ref(
                    edge.get("characterRef"), f"edges[{index}].characterRef"
                )
        if source not in adjacency or target not in adjacency or source == target:
            raise ValidationFailedError(f"edges[{index}] has invalid endpoints")
        if edge_type not in {"chronology", "continuity"}:
            raise ValidationFailedError(f"edges[{index}] has invalid type")
        adjacency[source].add(target)
        if edge_type == "chronology":
            chronological.add((source, target))
    ordered_refs = [
        item["creativeShotDraftRef" if draft else "creativeShotRef"]
        for item in sorted(nodes, key=lambda value: value["globalOrder"])
    ]
    if chronological != set(zip(ordered_refs, ordered_refs[1:])):
        raise ValidationFailedError("Shot Graph chronology is incomplete")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_ref: str) -> None:
        if node_ref in visiting:
            raise ValidationFailedError("Shot Graph contains a cycle")
        if node_ref in visited:
            return
        visiting.add(node_ref)
        for target in adjacency[node_ref]:
            visit(target)
        visiting.remove(node_ref)
        visited.add(node_ref)

    for ref in refs:
        visit(ref)


def validate_executable_shot_graph(graph: Mapping[str, Any]) -> None:
    """Validate only a true legacy executable graph."""

    _validate_shot_structure(graph, draft=False)


def validate_shot_plan_draft(draft: Mapping[str, Any]) -> None:
    """Validate a non-executable, unapproved local structural draft."""

    _validate_shot_structure(draft, draft=True)


class K2ShotGraphService:
    def __init__(
        self,
        root_service: EpisodeProductionService,
        authority_identity: K2AuthorityIdentityService,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        script_reader: Any,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.root_service = root_service
        self.authority_identity = authority_identity
        self.evidence = evidence
        self.script_reader = script_reader
        self._ref_factory = ref_factory
        self._clock = clock

    @staticmethod
    def _fact(gate: Mapping[str, Any], fact_kind: str) -> dict[str, Any]:
        matches = [
            fact for fact in gate.get("facts", [])
            if isinstance(fact, Mapping) and fact.get("factKind") == fact_kind
        ]
        if len(matches) != 1 or not isinstance(matches[0].get("payload"), Mapping):
            raise RepositoryUnavailableError("G3 evidence fact is inconsistent")
        return deepcopy(dict(matches[0]["payload"]))

    @staticmethod
    def _validated_draft_fact(
        fact: Mapping[str, Any],
        *,
        fact_kind: str,
        ref_field: str,
    ) -> dict[str, Any]:
        if not isinstance(fact, Mapping) or set(fact) != {
            "factKind",
            "factRef",
            "factVersion",
            "payload",
            "payloadDigest",
        }:
            raise RepositoryUnavailableError("G3 draft evidence fact is malformed")
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            raise RepositoryUnavailableError("G3 draft evidence payload is malformed")
        value = deepcopy(dict(payload))
        try:
            sealed_digest = _validate_sealed_payload(value, fact_kind)
        except EpisodeProductionError as exc:
            raise RepositoryUnavailableError(
                "G3 draft evidence payload seal is invalid"
            ) from exc
        if (
            fact.get("factKind") != fact_kind
            or fact.get("factVersion") != 1
            or fact.get("factRef") != value.get(ref_field)
            or fact.get("payloadDigest") != sealed_digest
        ):
            raise RepositoryUnavailableError("G3 draft evidence envelope is invalid")
        return value

    def _validated_draft_bundle(
        self,
        root: Mapping[str, Any],
        validation_gate: Mapping[str, Any],
        authority_bundle: Mapping[str, Any],
    ) -> dict[str, Any]:
        expected_count = root.get("manifest", {}).get("expectedShotCount")
        authority = authority_bundle.get("authorityDecision")
        identity_lock = authority_bundle.get("identityLock")
        current_root = authority_bundle.get("root")
        baseline = authority_bundle.get("m6Baseline")
        applicable_facts = (
            baseline.get("applicableFacts")
            if isinstance(baseline, Mapping)
            else None
        )
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count < 1
            or validation_gate.get("workspaceRef") != root.get("workspaceRef")
            or validation_gate.get("productionRunRef")
            != root.get("productionRunRef")
            or validation_gate.get("gateName") != SCRIPT_VALIDATION_GATE
            or validation_gate.get("rootPayloadDigest") != root.get("payloadDigest")
            or validation_gate.get("fromState") != "AUTHORITY_READY"
            or validation_gate.get("toState") != "SCRIPT_VALIDATED"
        ):
            raise RepositoryUnavailableError(
                "local structural draft evidence state is inconsistent"
            )
        if not isinstance(authority, Mapping) or not isinstance(
            identity_lock, Mapping
        ) or not isinstance(current_root, Mapping) or not isinstance(
            baseline, Mapping
        ) or not isinstance(applicable_facts, Mapping):
            raise RepositoryUnavailableError("G2 authority evidence is malformed")
        if (
            current_root.get("payloadDigest") != root.get("payloadDigest")
            or baseline.get("seriesBibleVersionRef")
            != authority.get("seriesBibleVersionRef")
            or baseline.get("seriesBibleVersionDigest")
            != authority.get("seriesBibleVersionDigest")
            or baseline.get("m6BaselineCanonicalDigest")
            != authority.get("m6BaselineCanonicalDigest")
        ):
            raise RepositoryUnavailableError("current M6 authority lineage is inconsistent")
        try:
            _validate_sealed_payload(authority, "M6AuthorityDecision")
            _validate_sealed_payload(identity_lock, "IdentityLock")
        except EpisodeProductionError as exc:
            raise RepositoryUnavailableError("G2 authority evidence seal is invalid") from exc
        facts = validation_gate.get("facts")
        if not isinstance(facts, list) or not all(
            isinstance(item, Mapping) for item in facts
        ):
            raise RepositoryUnavailableError("G3 draft evidence facts are malformed")
        expected_kinds = {
            "ConsistencyValidation",
            "StoryboardDraft",
            "ShotPlanDraft",
            *{
                f"CreativeShotDraft:{ordinal:04d}"
                for ordinal in range(1, expected_count + 1)
            },
        }
        by_kind = {item.get("factKind"): item for item in facts}
        if len(by_kind) != len(facts) or set(by_kind) != expected_kinds:
            raise RepositoryUnavailableError(
                "G3 draft evidence fact coverage is inconsistent"
            )
        validation = self._validated_draft_fact(
            by_kind["ConsistencyValidation"],
            fact_kind="ConsistencyValidation",
            ref_field="consistencyValidationRef",
        )
        storyboard = self._validated_draft_fact(
            by_kind["StoryboardDraft"],
            fact_kind="StoryboardDraft",
            ref_field="storyboardDraftRef",
        )
        draft = self._validated_draft_fact(
            by_kind["ShotPlanDraft"],
            fact_kind="ShotPlanDraft",
            ref_field="shotPlanDraftRef",
        )
        shots: list[dict[str, Any]] = []
        for ordinal in range(1, expected_count + 1):
            fact_kind = f"CreativeShotDraft:{ordinal:04d}"
            shot = self._validated_draft_fact(
                by_kind[fact_kind],
                fact_kind=fact_kind,
                ref_field="creativeShotDraftRef",
            )
            if shot.get("globalOrder") != ordinal:
                raise RepositoryUnavailableError(
                    "CreativeShotDraft evidence ordinal is inconsistent"
                )
            shots.append(shot)
        try:
            validate_draft_consistency_validation(validation)
            validate_storyboard_draft(storyboard)
            for shot in shots:
                validate_creative_shot_draft(shot)
            _validate_draft_identities_against_lock(shots, identity_lock)
            validate_shot_plan_draft(draft)
        except EpisodeProductionError as exc:
            raise RepositoryUnavailableError(
                "G3 draft evidence semantics are invalid"
            ) from exc

        root_workspace = root.get("workspaceRef")
        root_run = root.get("productionRunRef")
        script_ref = root.get("scriptRef")
        script_version_ref = root.get("scriptVersionRef")
        script_digest = root.get("upstreamSnapshot", {}).get("script", {}).get(
            "versionDigest"
        )
        manifest = root.get("manifest")
        expected_scene_count = (
            manifest.get("expectedSceneCount")
            if isinstance(manifest, Mapping)
            else None
        )
        scene_budgets = (
            manifest.get("sceneBudgets") if isinstance(manifest, Mapping) else None
        )
        root_output = (
            manifest.get("output") if isinstance(manifest, Mapping) else None
        )
        draft_output = draft.get("output")
        if (
            isinstance(expected_scene_count, bool)
            or not isinstance(expected_scene_count, int)
            or expected_scene_count < 1
            or not isinstance(scene_budgets, list)
            or len(scene_budgets) != expected_scene_count
            or not all(isinstance(item, Mapping) for item in scene_budgets)
            or not isinstance(root_output, Mapping)
        ):
            raise RepositoryUnavailableError("G3 draft root manifest is inconsistent")
        expected_scene_refs = [
            item.get("scriptSceneRef") for item in scene_budgets
        ]
        validation_scene_refs = [
            item.get("scriptSceneRef")
            for item in validation.get("checks", [])[:-3]
            if isinstance(item, Mapping)
        ]
        if (
            validation.get("workspaceRef") != root_workspace
            or validation.get("productionRunRef") != root_run
            or validation.get("rootPayloadDigest") != root.get("payloadDigest")
            or validation.get("scriptVersionRef") != script_version_ref
            or validation.get("scriptVersionDigest") != script_digest
            or validation.get("result") != "PASSED"
            or validation.get("createdBy") != DRAFT_PREPARER_ID
            or len(validation.get("checks", [])) != expected_scene_count + 3
            or validation.get("authorityDecisionRef")
            != authority.get("authorityDecisionRef")
            or validation.get("authorityDecisionDigest")
            != authority.get("payloadDigest")
            or validation.get("identityLockRef")
            != identity_lock.get("identityLockRef")
            or validation.get("identityLockVersionRef")
            != identity_lock.get("identityLockVersionRef")
            or validation.get("identityLockDigest")
            != identity_lock.get("payloadDigest")
            or validation_scene_refs != expected_scene_refs
        ):
            raise RepositoryUnavailableError("G3 draft lineage is inconsistent")
        if (
            not isinstance(draft_output, Mapping)
            or validation.get("frameRate") != draft_output.get("frameRate")
            or validation.get("totalFrames") != draft_output.get("totalFrames")
            or validation.get("authorityDecisionRef")
            != draft.get("authorityDecisionRef")
            or validation.get("authorityDecisionDigest")
            != draft.get("authorityDecisionDigest")
            or validation.get("identityLockRef") != draft.get("identityLockRef")
            or validation.get("identityLockVersionRef")
            != draft.get("identityLockVersionRef")
            or validation.get("identityLockDigest")
            != draft.get("identityLockDigest")
            or storyboard.get("identityLockRef")
            != identity_lock.get("identityLockRef")
            or storyboard.get("identityLockVersionRef")
            != identity_lock.get("identityLockVersionRef")
            or storyboard.get("identityLockDigest")
            != identity_lock.get("payloadDigest")
            or storyboard.get("identityLockRef")
            != validation.get("identityLockRef")
            or storyboard.get("identityLockVersionRef")
            != validation.get("identityLockVersionRef")
            or storyboard.get("identityLockDigest")
            != validation.get("identityLockDigest")
            or draft.get("consistencyValidationRef")
            != validation.get("consistencyValidationRef")
            or draft.get("consistencyValidationDigest")
            != validation.get("payloadDigest")
            or storyboard.get("workspaceRef") != root_workspace
            or storyboard.get("productionRunRef") != root_run
            or storyboard.get("rootPayloadDigest") != root.get("payloadDigest")
            or storyboard.get("scriptRef") != script_ref
            or storyboard.get("scriptVersionRef") != script_version_ref
            or storyboard.get("scriptVersionDigest") != script_digest
            or storyboard.get("consistencyValidationRef")
            != validation.get("consistencyValidationRef")
            or draft.get("workspaceRef") != root_workspace
            or draft.get("productionRunRef") != root_run
            or draft.get("rootPayloadDigest") != root.get("payloadDigest")
            or draft.get("scriptVersionRef") != script_version_ref
            or draft.get("scriptVersionDigest") != script_digest
            or draft.get("storyboardDraftRef")
            != storyboard.get("storyboardDraftRef")
            or draft.get("storyboardDigest") != storyboard.get("payloadDigest")
        ):
            raise RepositoryUnavailableError("G3 draft lineage is inconsistent")

        storyboard_scenes = storyboard.get("scenes", [])
        shot_budgets = manifest.get("shotBudgets")
        if (
            not isinstance(storyboard_scenes, list)
            or len(storyboard_scenes) != len(scene_budgets)
            or not isinstance(shot_budgets, list)
            or len(shot_budgets) != len(shots)
            or not all(isinstance(item, Mapping) for item in shot_budgets)
        ):
            raise RepositoryUnavailableError(
                "G3 draft storyboard coverage is inconsistent"
            )
        for scene, scene_budget in zip(storyboard_scenes, scene_budgets):
            scene_duration = scene_budget.get("durationFrames")
            if (
                not isinstance(scene, Mapping)
                or isinstance(scene_duration, bool)
                or not isinstance(scene_duration, int)
                or scene_duration < 1
                or scene.get("scriptSceneRef")
                != scene_budget.get("scriptSceneRef")
                or scene.get("sceneNumber") != scene_budget.get("sceneNumber")
                or scene.get("durationFrames") != scene_duration
                or sum(
                    item.get("durationFrames", 0)
                    for item in shot_budgets
                    if item.get("scriptSceneRef")
                    == scene_budget.get("scriptSceneRef")
                )
                != scene_duration
            ):
                raise RepositoryUnavailableError(
                    "G3 StoryboardSceneDraft timing lineage is inconsistent"
                )
        scene_by_ref = {
            item.get("storyboardSceneDraftRef"): item
            for item in storyboard_scenes
            if isinstance(item, Mapping)
        }
        storyboard_shot_refs = [
            shot_ref
            for scene in storyboard_scenes
            for shot_ref in scene.get("creativeShotDraftRefs", [])
        ]
        shot_refs = [shot.get("creativeShotDraftRef") for shot in shots]
        draft_nodes = draft.get("shots", [])
        draft_refs = [item.get("creativeShotDraftRef") for item in draft_nodes]
        if (
            len(scene_by_ref) != len(storyboard_scenes)
            or storyboard_shot_refs != shot_refs
            or draft_refs != shot_refs
        ):
            raise RepositoryUnavailableError(
                "G3 draft storyboard coverage is inconsistent"
            )
        expected_total_frames = sum(
            item.get("durationFrames", 0) for item in shot_budgets
        )
        expected_output = {
            **deepcopy(dict(root_output)),
            "totalFrames": expected_total_frames,
        }
        if (
            draft_output != expected_output
            or validation.get("totalFrames") != expected_total_frames
        ):
            raise RepositoryUnavailableError(
                "G3 draft output lineage is inconsistent"
            )
        node_fields = _SHOT_PLAN_DRAFT_NODE_FIELDS - {
            "creativeShotDraftRef",
            "payloadDigest",
        }
        budget_fields = {
            "scriptSceneRef",
            "sceneOrder",
            "durationFrames",
            "editorialShotSize",
            "visibleIdentityBindings",
            "actionBeat",
            "dialogueSyncMode",
            "dialogueRequirement",
            "postprocessRequirements",
        }
        if (
            authority.get("seriesBibleVersionRef")
            != identity_lock.get("seriesBibleVersionRef")
            or authority.get("seriesBibleVersionDigest")
            != identity_lock.get("seriesBibleVersionDigest")
        ):
            raise RepositoryUnavailableError(
                "G2 asset authority lineage is inconsistent"
            )
        current_identities = identity_lock.get("identities", [])
        identity_by_name = {
            item.get("scriptCharacterName"): item
            for item in current_identities
            if isinstance(item, Mapping)
        }
        locations = applicable_facts.get("locations")
        props = applicable_facts.get("props")
        visual_constraints = applicable_facts.get("visualConstraints")
        if not all(
            isinstance(items, list)
            and all(isinstance(item, Mapping) for item in items)
            for items in (locations, props, visual_constraints)
        ):
            raise RepositoryUnavailableError("current M6 asset facts are malformed")
        location_refs = [item.get("locationRef") for item in locations]
        prop_refs = [item.get("propRef") for item in props]
        visual_constraint_refs = [
            item.get("visualConstraintRef") for item in visual_constraints
        ]
        if (
            any(not isinstance(ref, str) or not ref for ref in location_refs)
            or any(not isinstance(ref, str) or not ref for ref in prop_refs)
            or any(
                not isinstance(ref, str) or not ref
                for ref in visual_constraint_refs
            )
            or len(location_refs) != len(set(location_refs))
            or len(prop_refs) != len(set(prop_refs))
            or len(visual_constraint_refs) != len(set(visual_constraint_refs))
        ):
            raise RepositoryUnavailableError("current M6 asset facts are ambiguous")
        for shot, node, budget in zip(shots, draft_nodes, shot_budgets):
            scene = scene_by_ref.get(shot.get("storyboardSceneDraftRef"))
            if not isinstance(scene, Mapping):
                raise RepositoryUnavailableError(
                    "G3 CreativeShotDraft storyboard lineage is inconsistent"
                )
            locks = shot.get("requiredCharacterIdentityLocks")
            root_visible_bindings = budget.get("visibleIdentityBindings")
            expected_visible_bindings = (
                [
                    {
                        "characterName": item.get("scriptCharacterName"),
                        "bindingMode": item.get("bindingMode"),
                    }
                    for item in locks
                ]
                if isinstance(locks, list)
                else None
            )
            expected_character_seeds: list[dict[str, Any]] = []
            if isinstance(locks, list):
                for lock in locks:
                    current_identity = identity_by_name.get(
                        lock.get("scriptCharacterName")
                    )
                    if not isinstance(current_identity, Mapping):
                        raise RepositoryUnavailableError(
                            "G3 CreativeShotDraft asset identity is inconsistent"
                        )
                    character_ref = current_identity.get("characterRef")
                    if lock.get("bindingMode") == "BODY_ONLY":
                        expected_character_seeds.append(
                            {
                                "requirementKey": f"character:{character_ref}",
                                "requirementType": "character-continuity",
                                "authorityRef": character_ref,
                                "authorityVersionRef": identity_lock.get(
                                    "characterContinuityVersionRef"
                                ),
                                "authorityDigest": identity_lock.get(
                                    "characterContinuityVersionDigest"
                                ),
                                "required": True,
                            }
                        )
                    elif lock.get("bindingMode") == "FACE_LOCK":
                        reference = current_identity.get("reference")
                        if not isinstance(reference, Mapping):
                            raise RepositoryUnavailableError(
                                "G3 CreativeShotDraft asset identity is inconsistent"
                            )
                        expected_character_seeds.append(
                            {
                                "requirementKey": f"character:{character_ref}",
                                "requirementType": "character-identity",
                                "authorityRef": character_ref,
                                "authorityVersionRef": reference.get(
                                    "referenceVersionRef"
                                ),
                                "authorityDigest": reference.get("contentDigest"),
                                "required": True,
                            }
                        )
            series_bible_ref = authority.get("seriesBibleVersionRef")
            series_bible_digest = authority.get("seriesBibleVersionDigest")
            expected_scene_seeds = [
                {
                    "requirementKey": f"location:{scene.get('locationRef')}",
                    "requirementType": "location",
                    "authorityRef": scene.get("locationRef"),
                    "authorityVersionRef": series_bible_ref,
                    "authorityDigest": series_bible_digest,
                    "required": True,
                },
                *[
                    {
                        "requirementKey": f"prop:{prop_ref}",
                        "requirementType": "prop",
                        "authorityRef": prop_ref,
                        "authorityVersionRef": series_bible_ref,
                        "authorityDigest": series_bible_digest,
                        "required": True,
                    }
                    for prop_ref in scene.get("propRefs", [])
                ],
            ]
            if (
                scene.get("locationRef") not in location_refs
                or any(ref not in prop_refs for ref in scene.get("propRefs", []))
            ):
                raise RepositoryUnavailableError(
                    "G3 StoryboardSceneDraft asset authority is stale"
                )
            asset_seeds = shot.get("assetRequirementSeeds")
            expected_style_seeds = [
                {
                    "requirementKey": f"style:{constraint_ref}",
                    "requirementType": "visual-style",
                    "authorityRef": constraint_ref,
                    "authorityVersionRef": series_bible_ref,
                    "authorityDigest": series_bible_digest,
                    "required": True,
                }
                for constraint_ref in visual_constraint_refs
            ]
            expected_asset_seeds = [
                *expected_character_seeds,
                *expected_scene_seeds,
                *expected_style_seeds,
            ]
            if (
                scene is None
                or set(budget) != budget_fields
                or shot.get("workspaceRef") != root_workspace
                or shot.get("productionRunRef") != root_run
                or shot.get("scriptRef") != script_ref
                or shot.get("scriptVersionRef") != script_version_ref
                or shot.get("storyboardDraftRef")
                != storyboard.get("storyboardDraftRef")
                or shot.get("scriptSceneRef") != scene.get("scriptSceneRef")
                or shot.get("creativeShotDraftRef")
                not in scene.get("creativeShotDraftRefs", [])
                or node.get("payloadDigest") != shot.get("payloadDigest")
                or any(node.get(field) != shot.get(field) for field in node_fields)
                or shot.get("scriptSceneRef") != budget.get("scriptSceneRef")
                or shot.get("sceneOrder") != budget.get("sceneOrder")
                or shot.get("durationFrames") != budget.get("durationFrames")
                or shot.get("frameRate") != root_output.get("frameRate")
                or node.get("frameRate") != root_output.get("frameRate")
                or shot.get("editorialShotSize")
                != budget.get("editorialShotSize")
                or shot.get("action") != budget.get("actionBeat")
                or shot.get("actionBeat") != budget.get("actionBeat")
                or shot.get("dialogueSyncMode")
                != budget.get("dialogueSyncMode")
                or shot.get("dialogueRequirement")
                != budget.get("dialogueRequirement")
                or shot.get("postprocessRequirements")
                != budget.get("postprocessRequirements")
                or root_visible_bindings != expected_visible_bindings
                or asset_seeds != expected_asset_seeds
            ):
                raise RepositoryUnavailableError(
                    "G3 CreativeShotDraft lineage is inconsistent"
                )
        return {
            "consistencyValidation": validation,
            "storyboardDraft": storyboard,
            "creativeShotDrafts": shots,
            "shotPlanDraft": draft,
            "state": "SCRIPT_VALIDATED",
        }

    def _script_version(self, root: Mapping[str, Any]) -> dict[str, Any]:
        workspace = _read_upstream(
            lambda: self.script_reader.get_workspace(
                root["workspaceRef"], root["seriesRef"], root["episodeRef"]
            )
        )
        script = workspace.get("script")
        versions = workspace.get("versions")
        if not isinstance(script, Mapping) or not isinstance(versions, list):
            raise UpstreamNotReadyError("confirmed ScriptVersion is unavailable")
        if script.get("confirmedScriptVersionRef") != root["scriptVersionRef"]:
            raise StaleInputError("confirmed ScriptVersion changed after G1")
        version = next(
            (
                item for item in versions
                if isinstance(item, Mapping)
                and item.get("scriptVersionRef") == root["scriptVersionRef"]
            ),
            None,
        )
        if not isinstance(version, Mapping):
            raise StaleInputError("frozen ScriptVersion is unavailable")
        expected_digest = root["upstreamSnapshot"]["script"]["versionDigest"]
        if _digest(dict(version)) != expected_digest:
            raise StaleInputError("frozen ScriptVersion digest changed")
        return deepcopy(dict(version))

    @staticmethod
    def _bindings(
        value: Any,
        scenes: Sequence[Mapping[str, Any]],
        m6_facts: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(value, list) or len(value) != len(scenes):
            raise ValidationFailedError("sceneBindings must cover every Script scene")
        locations = m6_facts.get("locations")
        props = m6_facts.get("props")
        if not isinstance(locations, list) or not isinstance(props, list):
            raise StaleInputError("M6 location and prop facts are unavailable")
        locations_by_ref = {
            item.get("locationRef"): item
            for item in locations
            if isinstance(item, Mapping) and isinstance(item.get("locationRef"), str)
        }
        props_by_ref = {
            item.get("propRef"): item
            for item in props
            if isinstance(item, Mapping) and isinstance(item.get("propRef"), str)
        }
        if len(locations_by_ref) != len(locations) or len(props_by_ref) != len(props):
            raise StaleInputError("M6 location or prop identity is ambiguous")
        result: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(value):
            if not isinstance(item, Mapping) or set(item) != {
                "scriptSceneRef", "locationRef", "propRefs"
            }:
                raise ValidationFailedError(f"sceneBindings[{index}] is invalid")
            scene_ref = _required_ref(
                item.get("scriptSceneRef"), f"sceneBindings[{index}].scriptSceneRef"
            )
            location_ref = _required_ref(
                item.get("locationRef"), f"sceneBindings[{index}].locationRef"
            )
            prop_refs = item.get("propRefs")
            if (
                scene_ref in result
                or location_ref not in locations_by_ref
                or not isinstance(prop_refs, list)
                or not all(isinstance(ref, str) for ref in prop_refs)
                or len(prop_refs) != len(set(prop_refs))
                or any(ref not in props_by_ref for ref in prop_refs)
            ):
                raise ValidationFailedError(
                    f"sceneBindings[{index}] contains an unresolved authority ref"
                )
            result[scene_ref] = {
                "scriptSceneRef": scene_ref,
                "location": deepcopy(dict(locations_by_ref[location_ref])),
                "props": [deepcopy(dict(props_by_ref[ref])) for ref in prop_refs],
            }
        expected = {scene.get("scriptSceneRef") for scene in scenes}
        if set(result) != expected:
            raise ValidationFailedError("sceneBindings do not match frozen Script scenes")
        return result

    @staticmethod
    def _validate_script(
        root: Mapping[str, Any],
        script: Mapping[str, Any],
        identity_lock: Mapping[str, Any],
        scene_bindings: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
        output = root["manifest"].get("output")
        frame_rate = output.get("frameRate") if isinstance(output, Mapping) else None
        if isinstance(frame_rate, bool) or not isinstance(frame_rate, int) or frame_rate <= 0:
            raise StaleInputError("frozen frame rate is invalid")
        scenes = script.get("scenes")
        budgets = root["manifest"].get("sceneBudgets")
        identities = identity_lock.get("identities")
        if not all(isinstance(value, list) for value in (scenes, budgets, identities)):
            raise StaleInputError("G3 inputs are incomplete")
        if len(scenes) != len(budgets) or len(scenes) != len(scene_bindings):
            raise ValidationFailedError("Script scene count changed")
        identity_by_name: dict[str, Mapping[str, Any]] = {}
        for identity in identities:
            if not isinstance(identity, Mapping):
                raise StaleInputError("Identity Lock is malformed")
            name = identity.get("scriptCharacterName")
            if not isinstance(name, str) or name in identity_by_name:
                raise StaleInputError("Identity Lock character mapping is ambiguous")
            identity_by_name[name] = identity
        normalized: list[dict[str, Any]] = []
        total_frames = 0
        checks: list[dict[str, Any]] = []
        seen_scene_refs: set[str] = set()
        for index, (scene, budget) in enumerate(zip(scenes, budgets)):
            if not isinstance(scene, Mapping) or not isinstance(budget, Mapping):
                raise ValidationFailedError(f"scenes[{index}] is invalid")
            scene_ref = _required_ref(
                scene.get("scriptSceneRef"), f"scenes[{index}].scriptSceneRef"
            )
            if scene_ref in seen_scene_refs or scene_ref != budget.get("scriptSceneRef"):
                raise ValidationFailedError("Script scene identity is inconsistent")
            seen_scene_refs.add(scene_ref)
            scene_number = scene.get("sceneNumber")
            if scene_number != index + 1 or scene_number != budget.get("sceneNumber"):
                raise ValidationFailedError("Script scene order is not deterministic")
            characters = _strings(scene.get("characters"), f"scenes[{index}].characters")
            if len(characters) != len(set(characters)) or any(
                name not in identity_by_name for name in characters
            ):
                raise ValidationFailedError("Script scene has an unresolved identity")
            dialogue = scene.get("dialogue")
            narration = scene.get("narration")
            if not isinstance(dialogue, list) or not isinstance(narration, list):
                raise ValidationFailedError("Script audio requirements are invalid")
            normalized_dialogue = []
            for dialogue_index, line in enumerate(dialogue):
                if not isinstance(line, Mapping):
                    raise ValidationFailedError("Script dialogue is invalid")
                speaker = _text(
                    line.get("speaker"),
                    f"scenes[{index}].dialogue[{dialogue_index}].speaker",
                )
                if speaker not in characters or speaker not in identity_by_name:
                    raise ValidationFailedError("Script dialogue speaker is unresolved")
                normalized_dialogue.append(deepcopy(dict(line)))
            scene_frames = _frames(
                scene.get("estimatedDurationSec"),
                frame_rate,
                f"scenes[{index}].estimatedDurationSec",
            )
            shot_count = budget.get("shotCount")
            if (
                isinstance(shot_count, bool)
                or not isinstance(shot_count, int)
                or shot_count <= 0
                or scene_frames < shot_count
            ):
                raise ValidationFailedError("scene shot budget is invalid")
            total_frames += scene_frames
            normalized.append(
                {
                    "scriptSceneRef": scene_ref,
                    "sceneNumber": scene_number,
                    "heading": _text(scene.get("heading"), f"scenes[{index}].heading"),
                    "location": _text(scene.get("location"), f"scenes[{index}].location"),
                    "timeOfDay": _text(scene.get("timeOfDay"), f"scenes[{index}].timeOfDay"),
                    "characters": characters,
                    "action": _text(scene.get("action"), f"scenes[{index}].action"),
                    "dialogue": normalized_dialogue,
                    "narration": deepcopy(narration),
                    "subtitleText": _strings(
                        scene.get("subtitleText"), f"scenes[{index}].subtitleText"
                    ),
                    "scenePurpose": _text(
                        scene.get("scenePurpose"), f"scenes[{index}].scenePurpose"
                    ),
                    "continuityNotes": _strings(
                        scene.get("continuityNotes"),
                        f"scenes[{index}].continuityNotes",
                    ),
                    "productionNotes": _strings(
                        scene.get("productionNotes"),
                        f"scenes[{index}].productionNotes",
                    ),
                    "durationFrames": scene_frames,
                    "shotCount": shot_count,
                    "authorityBinding": deepcopy(dict(scene_bindings[scene_ref])),
                }
            )
            checks.append(
                {
                    "checkId": f"scene-{scene_number}-identity-and-authority",
                    "status": "PASSED",
                    "scriptSceneRef": scene_ref,
                }
            )
        target_frames = _frames(
            script.get("targetDurationSec"), frame_rate, "targetDurationSec"
        )
        if total_frames != target_frames:
            raise ValidationFailedError("Script scene duration does not equal target duration")
        expected_frames = _frames(
            root["manifest"].get("targetDurationSec"), frame_rate, "manifest.targetDurationSec"
        )
        if total_frames != expected_frames:
            raise StaleInputError("Script duration no longer matches the frozen manifest")
        checks.extend(
            (
                {
                    "checkId": "script-version-digest-current",
                    "status": "PASSED",
                    "scriptVersionRef": root["scriptVersionRef"],
                },
                {
                    "checkId": "frame-accounting-exact",
                    "status": "PASSED",
                    "totalFrames": total_frames,
                    "frameRate": frame_rate,
                },
                {
                    "checkId": "identity-lock-complete",
                    "status": "PASSED",
                    "identityLockVersionRef": identity_lock["identityLockVersionRef"],
                },
            )
        )
        return normalized, total_frames, checks

    def _compile(
        self,
        *,
        root: Mapping[str, Any],
        script: Mapping[str, Any],
        authority: Mapping[str, Any],
        identity_lock: Mapping[str, Any],
        m6_facts: Mapping[str, Any],
        scenes: Sequence[Mapping[str, Any]],
        validation: Mapping[str, Any],
        created_at: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        v2 = root["manifest"].get("schemaVersion") == MANIFEST_SCHEMA_VERSION_V2
        creative_shot_schema = (
            CREATIVE_SHOT_DRAFT_SCHEMA_VERSION
            if v2
            else CREATIVE_SHOT_SCHEMA_VERSION
        )
        shot_structure_schema = (
            SHOT_PLAN_DRAFT_SCHEMA_VERSION if v2 else SHOT_GRAPH_SCHEMA_VERSION
        )
        compiler_id = DRAFT_PREPARER_ID if v2 else COMPILER_ID
        explicit_budgets = root["manifest"].get("shotBudgets") if v2 else None
        if v2 and (
            not isinstance(explicit_budgets, list)
            or not explicit_budgets
            or not all(isinstance(item, Mapping) for item in explicit_budgets)
        ):
            raise StaleInputError("frozen explicit shot budgets are malformed")
        storyboard_ref = _required_ref(
            self._ref_factory("storyboard-draft" if v2 else "storyboard"),
            "storyboardDraftRef" if v2 else "storyboardRef",
        )
        storyboard_version_ref = (
            None
            if v2
            else _required_ref(
                self._ref_factory("storyboard-version"), "storyboardVersionRef"
            )
        )
        identity_by_name = {
            item["scriptCharacterName"]: item
            for item in identity_lock["identities"]
        }
        visual_constraints = m6_facts.get("visualConstraints")
        if not isinstance(visual_constraints, list):
            raise StaleInputError("M6 visual constraints are unavailable")
        shots: list[dict[str, Any]] = []
        storyboard_scenes: list[dict[str, Any]] = []
        global_order = 0
        for scene_index, scene in enumerate(scenes):
            storyboard_scene_ref = _required_ref(
                self._ref_factory(
                    "storyboard-scene-draft" if v2 else "storyboard-scene"
                ),
                "storyboardSceneDraftRef" if v2 else "storyboardSceneRef",
            )
            storyboard_scene_version_ref = (
                None
                if v2
                else _required_ref(
                    self._ref_factory("storyboard-scene-version"),
                    "storyboardSceneVersionRef",
                )
            )
            if explicit_budgets is None:
                base_frames, remainder = divmod(
                    scene["durationFrames"], scene["shotCount"]
                )
                shot_specs = [
                    {
                        "scriptSceneRef": scene["scriptSceneRef"],
                        "sceneOrder": scene_order,
                        "durationFrames": base_frames
                        + (1 if scene_order <= remainder else 0),
                        "camera": _camera(
                            global_order + scene_order,
                            scene_order,
                            scene["shotCount"],
                        ),
                        "visibleIdentityMode": "FACE_LOCK",
                        "visibleCharacterNames": list(scene["characters"]),
                        "dialogueSyncMode": "NONE",
                        "postprocessRequirements": [],
                    }
                    for scene_order in range(1, scene["shotCount"] + 1)
                ]
            else:
                shot_specs = [
                    deepcopy(dict(item))
                    for item in explicit_budgets
                    if item.get("scriptSceneRef") == scene["scriptSceneRef"]
                ]
                if (
                    len(shot_specs) != scene["shotCount"]
                    or [item.get("sceneOrder") for item in shot_specs]
                    != list(range(1, scene["shotCount"] + 1))
                    or sum(item.get("durationFrames", 0) for item in shot_specs)
                    != scene["durationFrames"]
                ):
                    raise StaleInputError(
                        "frozen explicit shot budgets do not match the Script scene"
                    )
            scene_shot_refs = []
            dialogue_cursor = 0
            narration_cursor = 0
            for shot_spec in shot_specs:
                scene_order = shot_spec["sceneOrder"]
                global_order += 1
                shot_ref = _required_ref(
                    self._ref_factory(
                        "creative-shot-draft" if v2 else "creative-shot"
                    ),
                    "creativeShotDraftRef" if v2 else "creativeShotRef",
                )
                shot_version_ref = (
                    None
                    if v2
                    else _required_ref(
                        self._ref_factory("creative-shot-version"),
                        "creativeShotVersionRef",
                    )
                )
                scene_shot_refs.append(shot_ref)
                dialogue_source_span = None
                if v2:
                    requirement = shot_spec["dialogueRequirement"]
                    source_mode = requirement["sourceMode"]
                    if source_mode == "DIALOGUE":
                        if dialogue_cursor >= len(scene["dialogue"]):
                            raise StaleInputError(
                                "explicit shot dialogue exceeds the Script scene"
                            )
                        line = scene["dialogue"][dialogue_cursor]
                        expected = {
                            "speaker": line.get("speaker"),
                            "text": line.get("text"),
                            "sourceMode": "DIALOGUE",
                        }
                        if requirement != expected:
                            raise StaleInputError(
                                "explicit shot dialogue drifted from the Script scene"
                            )
                        assigned_dialogue = [deepcopy(dict(line))]
                        assigned_narration = []
                        dialogue_source_span = (
                            f"/scenes/{scene_index}/dialogue/{dialogue_cursor}"
                        )
                        dialogue_cursor += 1
                    elif source_mode == "NARRATION":
                        if (
                            narration_cursor >= len(scene["narration"])
                            or requirement["text"]
                            != scene["narration"][narration_cursor]
                        ):
                            raise StaleInputError(
                                "explicit shot narration drifted from the Script scene"
                            )
                        assigned_dialogue = []
                        assigned_narration = [requirement["text"]]
                        dialogue_source_span = (
                            f"/scenes/{scene_index}/narration/{narration_cursor}"
                        )
                        narration_cursor += 1
                    else:
                        assigned_dialogue = []
                        assigned_narration = []
                else:
                    assigned_dialogue = [
                        deepcopy(line)
                        for line_index, line in enumerate(scene["dialogue"])
                        if line_index % scene["shotCount"] == scene_order - 1
                    ]
                    assigned_narration = [
                        deepcopy(line)
                        for line_index, line in enumerate(scene["narration"])
                        if line_index % scene["shotCount"] == scene_order - 1
                    ]
                if v2:
                    visible_bindings = shot_spec["visibleIdentityBindings"]
                    binding_modes = {
                        item["bindingMode"] for item in visible_bindings
                    }
                    visible_mode = (
                        "NONE"
                        if not binding_modes
                        else (
                            next(iter(binding_modes))
                            if len(binding_modes) == 1
                            else "MIXED"
                        )
                    )
                else:
                    visible_mode = shot_spec["visibleIdentityMode"]
                    visible_bindings = [
                        {"characterName": name, "bindingMode": "FACE_LOCK"}
                        for name in shot_spec["visibleCharacterNames"]
                    ]
                locked_characters = []
                asset_seeds = []
                for visible_binding in visible_bindings:
                    name = visible_binding["characterName"]
                    binding_mode = visible_binding["bindingMode"]
                    locked = identity_by_name[name]
                    if binding_mode == "BODY_ONLY":
                        locked_characters.append(
                            {
                                "bindingMode": "BODY_ONLY",
                                "scriptCharacterName": name,
                                "characterRef": locked["characterRef"],
                                "characterContinuityVersionRef": authority[
                                    "characterContinuityVersionRef"
                                ],
                                "characterContinuityVersionDigest": authority[
                                    "characterContinuityVersionDigest"
                                ],
                                "characterFactDigest": locked["characterFactDigest"],
                            }
                        )
                        asset_seeds.append(
                            {
                                "requirementKey": f"character:{locked['characterRef']}",
                                "requirementType": "character-continuity",
                                "authorityRef": locked["characterRef"],
                                "authorityVersionRef": authority[
                                    "characterContinuityVersionRef"
                                ],
                                "authorityDigest": authority[
                                    "characterContinuityVersionDigest"
                                ],
                                "required": True,
                            }
                        )
                    elif binding_mode == "FACE_LOCK":
                        reference = locked["reference"]
                        locked_characters.append(
                            {
                                "bindingMode": "FACE_LOCK" if v2 else None,
                                "scriptCharacterName": name,
                                "characterRef": locked["characterRef"],
                                "identityLockRef": identity_lock["identityLockRef"],
                                "identityLockVersionRef": identity_lock[
                                    "identityLockVersionRef"
                                ],
                                "identityLockDigest": (
                                    identity_lock["payloadDigest"] if v2 else None
                                ),
                                "referenceVersionRef": reference["referenceVersionRef"],
                                "referenceDigest": reference["contentDigest"],
                            }
                        )
                        if not v2:
                            locked_characters[-1].pop("bindingMode")
                            locked_characters[-1].pop("identityLockDigest")
                        asset_seeds.append(
                            {
                                "requirementKey": f"character:{locked['characterRef']}",
                                "requirementType": "character-identity",
                                "authorityRef": locked["characterRef"],
                                "authorityVersionRef": reference["referenceVersionRef"],
                                "authorityDigest": reference["contentDigest"],
                                "required": True,
                            }
                        )
                location = scene["authorityBinding"]["location"]
                asset_seeds.append(
                    {
                        "requirementKey": f"location:{location['locationRef']}",
                        "requirementType": "location",
                        "authorityRef": location["locationRef"],
                        "authorityVersionRef": authority["seriesBibleVersionRef"],
                        "authorityDigest": authority["seriesBibleVersionDigest"],
                        "required": True,
                    }
                )
                for prop in scene["authorityBinding"]["props"]:
                    asset_seeds.append(
                        {
                            "requirementKey": f"prop:{prop['propRef']}",
                            "requirementType": "prop",
                            "authorityRef": prop["propRef"],
                            "authorityVersionRef": authority["seriesBibleVersionRef"],
                            "authorityDigest": authority["seriesBibleVersionDigest"],
                            "required": True,
                        }
                    )
                for constraint in visual_constraints:
                    if not isinstance(constraint, Mapping):
                        raise StaleInputError("M6 visual constraint is malformed")
                    asset_seeds.append(
                        {
                            "requirementKey": (
                                f"style:{constraint.get('visualConstraintRef')}"
                            ),
                            "requirementType": "visual-style",
                            "authorityRef": _required_ref(
                                constraint.get("visualConstraintRef"),
                                "visualConstraintRef",
                            ),
                            "authorityVersionRef": authority["seriesBibleVersionRef"],
                            "authorityDigest": authority["seriesBibleVersionDigest"],
                            "required": True,
                        }
                    )
                source_spans = (
                    [
                        f"/manifest/shotBudgets/{global_order - 1}/actionBeat",
                        *([dialogue_source_span] if dialogue_source_span else []),
                    ]
                    if v2
                    else [f"/scenes/{scene_index}/action"]
                    + [
                        f"/scenes/{scene_index}/dialogue/{line_index}"
                        for line_index, _ in enumerate(scene["dialogue"])
                        if line_index % scene["shotCount"] == scene_order - 1
                    ]
                )
                base = {
                    "schemaVersion": creative_shot_schema,
                    "workspaceRef": root["workspaceRef"],
                    "productionRunRef": root["productionRunRef"],
                    "scriptRef": root["scriptRef"],
                    "scriptVersionRef": root["scriptVersionRef"],
                    "scriptSceneRef": scene["scriptSceneRef"],
                    "sourceScriptSpans": source_spans,
                    "globalOrder": global_order,
                    "sceneOrder": scene_order,
                    "durationFrames": shot_spec["durationFrames"],
                    "frameRate": root["manifest"]["output"]["frameRate"],
                    "action": (
                        shot_spec["actionBeat"] if v2 else scene["action"]
                    ),
                    "actionBeat": (
                        shot_spec["actionBeat"]
                        if v2
                        else {
                            "index": scene_order,
                            "count": scene["shotCount"],
                            "scenePurpose": scene["scenePurpose"],
                        }
                    ),
                    "dialogueRequirements": assigned_dialogue,
                    "audioRequirements": {
                        "dialogue": assigned_dialogue,
                        "narration": assigned_narration,
                        "subtitleText": scene["subtitleText"],
                        "ambience": f"{scene['location']} · {scene['timeOfDay']}",
                    },
                    "requiredCharacterIdentityLocks": locked_characters,
                    "assetRequirementSeeds": asset_seeds,
                    "continuityConstraints": (
                        scene["continuityNotes"]
                        + scene["productionNotes"]
                        + [
                            rule
                            for identity in locked_characters
                            for rule in identity_by_name[
                                identity["scriptCharacterName"]
                            ].get("visualIdentityRules", [])
                        ]
                    ),
                    "executionMode": root["manifest"]["executionMode"],
                    "status": (
                        "LOCAL_STRUCTURAL_DRAFT"
                        if v2
                        else "COMPILED_LOCAL_EVIDENCE"
                    ),
                    "approvalRequired": True,
                    "createdBy": compiler_id,
                    "createdAt": created_at,
                }
                if v2:
                    base.update(
                        {
                            "creativeShotDraftRef": shot_ref,
                            "revision": 1,
                            "storyboardDraftRef": storyboard_ref,
                            "storyboardSceneDraftRef": storyboard_scene_ref,
                            "editorialShotSize": shot_spec[
                                "editorialShotSize"
                            ],
                            "visibleIdentityMode": visible_mode,
                            "visibleCharacterRefs": [
                                identity["characterRef"] for identity in locked_characters
                            ],
                            "visibleIdentityBindings": [
                                {
                                    "characterRef": identity["characterRef"],
                                    "bindingMode": identity["bindingMode"],
                                }
                                for identity in locked_characters
                            ],
                            "dialogueSyncMode": shot_spec["dialogueSyncMode"],
                            "dialogueRequirement": deepcopy(
                                shot_spec["dialogueRequirement"]
                            ),
                            "postprocessRequirements": deepcopy(
                                shot_spec["postprocessRequirements"]
                            ),
                        }
                    )
                else:
                    base.update(
                        {
                            "creativeShotRef": shot_ref,
                            "creativeShotVersionRef": shot_version_ref,
                            "version": 1,
                            "storyboardRef": storyboard_ref,
                            "storyboardVersionRef": storyboard_version_ref,
                            "storyboardSceneRef": storyboard_scene_ref,
                            "storyboardSceneVersionRef": (
                                storyboard_scene_version_ref
                            ),
                            "cameraInstruction": deepcopy(
                                dict(shot_spec["camera"])
                            ),
                        }
                    )
                shot = _sealed(base)
                if v2:
                    validate_creative_shot_draft(shot)
                shots.append(shot)
            if v2 and (
                dialogue_cursor != len(scene["dialogue"])
                or narration_cursor != len(scene["narration"])
            ):
                raise StaleInputError(
                    "explicit shot dialogue does not cover the Script scene"
                )
            storyboard_scene = {
                "scriptSceneRef": scene["scriptSceneRef"],
                "sceneNumber": scene["sceneNumber"],
                "heading": scene["heading"],
                "locationRef": location["locationRef"],
                "propRefs": [
                    prop["propRef"] for prop in scene["authorityBinding"]["props"]
                ],
                "durationFrames": scene["durationFrames"],
            }
            if v2:
                storyboard_scene.update(
                    {
                        "schemaVersion": STORYBOARD_SCENE_DRAFT_SCHEMA_VERSION,
                        "workspaceRef": root["workspaceRef"],
                        "productionRunRef": root["productionRunRef"],
                        "storyboardDraftRef": storyboard_ref,
                        "storyboardSceneDraftRef": storyboard_scene_ref,
                        "scriptVersionRef": root["scriptVersionRef"],
                        "revision": 1,
                        "creativeShotDraftRefs": scene_shot_refs,
                        "status": "LOCAL_STRUCTURAL_DRAFT",
                        "approvalRequired": True,
                        "createdBy": compiler_id,
                        "createdAt": created_at,
                    }
                )
                storyboard_scene = _sealed(storyboard_scene)
                validate_storyboard_scene_draft(storyboard_scene)
            else:
                storyboard_scene.update(
                    {
                        "storyboardSceneRef": storyboard_scene_ref,
                        "storyboardSceneVersionRef": storyboard_scene_version_ref,
                        "creativeShotRefs": scene_shot_refs,
                    }
                )
            storyboard_scenes.append(storyboard_scene)
        storyboard_payload = {
                "schemaVersion": (
                    STORYBOARD_DRAFT_SCHEMA_VERSION
                    if v2
                    else STORYBOARD_SCHEMA_VERSION
                ),
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "rootPayloadDigest": root["payloadDigest"],
                "scriptRef": root["scriptRef"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "consistencyValidationRef": validation[
                    "consistencyValidationRef"
                ],
                "identityLockRef": identity_lock["identityLockRef"],
                "identityLockVersionRef": identity_lock["identityLockVersionRef"],
                "identityLockDigest": identity_lock["payloadDigest"],
                "scenes": storyboard_scenes,
                "status": (
                    "LOCAL_STRUCTURAL_DRAFT"
                    if v2
                    else "COMPILED_LOCAL_EVIDENCE"
                ),
                "approvalRequired": True,
                "createdBy": compiler_id,
                "createdAt": created_at,
            }
        if v2:
            storyboard_payload.update(
                {"storyboardDraftRef": storyboard_ref, "revision": 1}
            )
        else:
            storyboard_payload.update(
                {
                    "storyboardRef": storyboard_ref,
                    "storyboardVersionRef": storyboard_version_ref,
                    "version": 1,
                }
            )
        storyboard = _sealed(storyboard_payload)
        if v2:
            validate_storyboard_draft(storyboard)
        edges: list[dict[str, Any]] = []
        for previous, current in zip(shots, shots[1:]):
            edge = {
                    "edgeRef": _required_ref(
                        self._ref_factory("shot-edge"), "edgeRef"
                    ),
                    "edgeType": "chronology",
            }
            if v2:
                edge.update(
                    {
                        "fromShotDraftRef": previous["creativeShotDraftRef"],
                        "toShotDraftRef": current["creativeShotDraftRef"],
                    }
                )
            else:
                edge.update(
                    {
                        "fromShotRef": previous["creativeShotRef"],
                        "toShotRef": current["creativeShotRef"],
                    }
                )
            edges.append(edge)
        last_by_character: dict[str, tuple[str, str | None]] = {}
        for shot in shots:
            for identity in shot["requiredCharacterIdentityLocks"]:
                character_ref = identity["characterRef"]
                previous = last_by_character.get(character_ref)
                if previous is not None:
                    previous_ref, previous_mode = previous
                    current_mode = identity.get("bindingMode") if v2 else None
                    edge = {
                            "edgeRef": _required_ref(
                                self._ref_factory("shot-edge"), "edgeRef"
                            ),
                            "edgeType": "continuity",
                            "continuityKind": (
                                "character-face-identity"
                                if v2
                                and previous_mode == "FACE_LOCK"
                                and current_mode == "FACE_LOCK"
                                else (
                                    "character-non-face-continuity"
                                    if v2
                                    else "character-identity"
                                )
                            ),
                            "characterRef": character_ref,
                    }
                    if v2:
                        edge.update(
                            {
                                "fromShotDraftRef": previous_ref,
                                "toShotDraftRef": shot["creativeShotDraftRef"],
                            }
                        )
                    else:
                        edge.update(
                            {
                                "fromShotRef": previous_ref,
                                "toShotRef": shot["creativeShotRef"],
                            }
                        )
                    edges.append(edge)
                last_by_character[character_ref] = (
                    shot[
                        "creativeShotDraftRef" if v2 else "creativeShotRef"
                    ],
                    identity.get("bindingMode") if v2 else None,
                )
        structure_payload = {
                "schemaVersion": shot_structure_schema,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "rootPayloadDigest": root["payloadDigest"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "authorityDecisionRef": authority["authorityDecisionRef"],
                "authorityDecisionDigest": authority["payloadDigest"],
                "identityLockRef": identity_lock["identityLockRef"],
                "identityLockVersionRef": identity_lock["identityLockVersionRef"],
                "identityLockDigest": identity_lock["payloadDigest"],
                "consistencyValidationRef": validation[
                    "consistencyValidationRef"
                ],
                "consistencyValidationDigest": validation["payloadDigest"],
                "storyboardDigest": storyboard["payloadDigest"],
                "edges": edges,
                "output": {
                    **deepcopy(dict(root["manifest"]["output"])),
                    "totalFrames": sum(shot["durationFrames"] for shot in shots),
                },
                "executionMode": root["manifest"]["executionMode"],
                "publicationAllowed": False,
                "createdBy": compiler_id,
                "createdAt": created_at,
            }
        if v2:
            structure_payload.update(
                {
                    "shotPlanDraftRef": _required_ref(
                        self._ref_factory("shot-plan-draft"),
                        "shotPlanDraftRef",
                    ),
                    "revision": 1,
                    "storyboardDraftRef": storyboard_ref,
                    "shots": [
                        {
                            key: shot[key]
                            for key in (
                                "creativeShotDraftRef",
                                "payloadDigest",
                                "scriptSceneRef",
                                "globalOrder",
                                "sceneOrder",
                                "durationFrames",
                                "frameRate",
                                "editorialShotSize",
                                "requiredCharacterIdentityLocks",
                                "assetRequirementSeeds",
                                "continuityConstraints",
                                "visibleIdentityMode",
                                "visibleCharacterRefs",
                                "visibleIdentityBindings",
                                "actionBeat",
                                "dialogueSyncMode",
                                "dialogueRequirement",
                                "postprocessRequirements",
                            )
                        }
                        for shot in shots
                    ],
                    "shotPlanAuthorityState": root["manifest"][
                        "shotPlanAuthorityState"
                    ],
                    "shotPlanApprovalState": root["manifest"][
                        "shotPlanApprovalState"
                    ],
                    "cameraContractState": root["manifest"][
                        "cameraContractState"
                    ],
                    "executionAuthorizationState": (
                        "PREFLIGHT_ONLY_NOT_AUTHORIZED"
                    ),
                    "dispatchAllowed": False,
                    "status": "LOCAL_STRUCTURAL_DRAFT",
                }
            )
        else:
            structure_payload.update(
                {
                    "executableShotGraphRef": _required_ref(
                        self._ref_factory("executable-shot-graph"),
                        "executableShotGraphRef",
                    ),
                    "executableShotGraphVersionRef": _required_ref(
                        self._ref_factory("executable-shot-graph-version"),
                        "executableShotGraphVersionRef",
                    ),
                    "version": 1,
                    "storyboardRef": storyboard_ref,
                    "storyboardVersionRef": storyboard_version_ref,
                    "shots": [
                        {
                            key: shot[key]
                            for key in (
                                "creativeShotRef",
                                "creativeShotVersionRef",
                                "payloadDigest",
                                "scriptSceneRef",
                                "globalOrder",
                                "sceneOrder",
                                "durationFrames",
                                "frameRate",
                                "cameraInstruction",
                                "requiredCharacterIdentityLocks",
                                "assetRequirementSeeds",
                                "continuityConstraints",
                            )
                        }
                        for shot in shots
                    ],
                    "status": "EXECUTABLE_LOCAL_EVIDENCE",
                }
            )
        structure = _sealed(structure_payload)
        if v2:
            for shot in shots:
                validate_creative_shot_draft(shot)
            validate_storyboard_draft(storyboard)
            validate_shot_plan_draft(structure)
        else:
            validate_executable_shot_graph(structure)
        return storyboard, shots, structure

    def compile_shot_graph(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != {
            "workspaceRef", "productionRunRef", "idempotencyKey", "sceneBindings"
        }:
            raise EpisodeProductionError("command fields do not match the G3 contract")
        workspace = _required_ref(command.get("workspaceRef"), "workspaceRef")
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        idempotency_key = _idempotency_key(command.get("idempotencyKey"))
        verified = self.authority_identity.verify_authority_identity_current(
            workspace, run_ref
        )
        root = verified["root"]
        authority = verified["authorityDecision"]
        identity_lock = verified["identityLock"]
        baseline = verified["m6Baseline"]
        m6_facts = baseline.get("applicableFacts")
        if not isinstance(m6_facts, Mapping):
            raise StaleInputError("M6 episode facts are unavailable")
        script = self._script_version(root)
        raw_scenes = script.get("scenes")
        if not isinstance(raw_scenes, list) or not all(
            isinstance(item, Mapping) for item in raw_scenes
        ):
            raise ValidationFailedError("confirmed ScriptVersion has no valid scenes")
        scene_bindings = self._bindings(
            command.get("sceneBindings"), raw_scenes, m6_facts
        )
        scenes, total_frames, checks = self._validate_script(
            root, script, identity_lock, scene_bindings
        )
        draft_mode = (
            root["manifest"].get("schemaVersion") == MANIFEST_SCHEMA_VERSION_V2
        )
        compiler_id = DRAFT_PREPARER_ID if draft_mode else COMPILER_ID
        now = self._clock()
        validation_request_digest = _digest(
            {
                "clientIdempotencyKey": idempotency_key,
                "rootPayloadDigest": root["payloadDigest"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "authorityDecisionDigest": authority["payloadDigest"],
                "identityLockDigest": identity_lock["payloadDigest"],
                "sceneBindings": [
                    deepcopy(dict(item)) for item in command["sceneBindings"]
                ],
                "compilerId": compiler_id,
            }
        )
        validation = _sealed(
            {
                "schemaVersion": CONSISTENCY_VALIDATION_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "consistencyValidationRef": _required_ref(
                    self._ref_factory("consistency-validation"),
                    "consistencyValidationRef",
                ),
                "version": 1,
                "rootPayloadDigest": root["payloadDigest"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "authorityDecisionRef": authority["authorityDecisionRef"],
                "authorityDecisionDigest": authority["payloadDigest"],
                "identityLockRef": identity_lock["identityLockRef"],
                "identityLockVersionRef": identity_lock["identityLockVersionRef"],
                "identityLockDigest": identity_lock["payloadDigest"],
                "checks": checks,
                "totalFrames": total_frames,
                "frameRate": root["manifest"]["output"]["frameRate"],
                "result": "PASSED",
                "createdBy": compiler_id,
                "createdAt": now,
            }
        )
        if draft_mode:
            validate_draft_consistency_validation(validation)
        if draft_mode:
            storyboard, shots, draft = self._compile(
                root=root,
                script=script,
                authority=authority,
                identity_lock=identity_lock,
                m6_facts=m6_facts,
                scenes=scenes,
                validation=validation,
                created_at=now,
            )
            draft_facts = tuple(
                EvidenceFact(
                    f"CreativeShotDraft:{shot['globalOrder']:04d}",
                    shot["creativeShotDraftRef"],
                    1,
                    shot,
                    shot["payloadDigest"],
                )
                for shot in shots
            )
            validation_gate, replayed = self.evidence.append_gate(
                GateAppend(
                    workspace,
                    run_ref,
                    SCRIPT_VALIDATION_GATE,
                    _digest(
                        {
                            "clientIdempotencyKey": idempotency_key,
                            "stage": "validate-and-prepare-local-draft",
                        }
                    ),
                    root["payloadDigest"],
                    validation_request_digest,
                    "AUTHORITY_READY",
                    "SCRIPT_VALIDATED",
                    now,
                    (
                        EvidenceFact(
                            "ConsistencyValidation",
                            validation["consistencyValidationRef"],
                            1,
                            validation,
                            validation["payloadDigest"],
                        ),
                        EvidenceFact(
                            "StoryboardDraft",
                            storyboard["storyboardDraftRef"],
                            1,
                            storyboard,
                            storyboard["payloadDigest"],
                        ),
                        *draft_facts,
                        EvidenceFact(
                            "ShotPlanDraft",
                            draft["shotPlanDraftRef"],
                            1,
                            draft,
                            draft["payloadDigest"],
                        ),
                    ),
                )
            )
            return {
                **self._validated_draft_bundle(
                    root,
                    validation_gate,
                    verified,
                ),
                "idempotentReplay": replayed,
            }
        validation_gate, validation_replay = self.evidence.append_gate(
            GateAppend(
                workspace,
                run_ref,
                SCRIPT_VALIDATION_GATE,
                _digest({"clientIdempotencyKey": idempotency_key, "stage": "validate"}),
                root["payloadDigest"],
                validation_request_digest,
                "AUTHORITY_READY",
                "SCRIPT_VALIDATED",
                now,
                (
                    EvidenceFact(
                        "ConsistencyValidation",
                        validation["consistencyValidationRef"],
                        1,
                        validation,
                        validation["payloadDigest"],
                    ),
                ),
            )
        )
        validation = self._fact(validation_gate, "ConsistencyValidation")
        storyboard, shots, graph = self._compile(
            root=root,
            script=script,
            authority=authority,
            identity_lock=identity_lock,
            m6_facts=m6_facts,
            scenes=scenes,
            validation=validation,
            created_at=now,
        )
        compile_request_digest = _digest(
            {
                "clientIdempotencyKey": idempotency_key,
                "validationRequestDigest": validation_request_digest,
                "rootPayloadDigest": root["payloadDigest"],
                "compilerId": compiler_id,
            }
        )
        shot_facts = tuple(
            EvidenceFact(
                f"CreativeShotVersion:{shot['globalOrder']:04d}",
                shot["creativeShotVersionRef"],
                1,
                shot,
                shot["payloadDigest"],
            )
            for shot in shots
        )
        compile_gate, compile_replay = self.evidence.append_gate(
            GateAppend(
                workspace,
                run_ref,
                SHOT_GRAPH_GATE,
                _digest({"clientIdempotencyKey": idempotency_key, "stage": "compile"}),
                root["payloadDigest"],
                compile_request_digest,
                "SCRIPT_VALIDATED",
                "SHOTS_COMPILED",
                now,
                (
                    EvidenceFact(
                        "StoryboardVersion",
                        storyboard["storyboardVersionRef"],
                        1,
                        storyboard,
                        storyboard["payloadDigest"],
                    ),
                    *shot_facts,
                    EvidenceFact(
                        "ExecutableShotGraph",
                        graph["executableShotGraphVersionRef"],
                        1,
                        graph,
                        graph["payloadDigest"],
                    ),
                ),
            )
        )
        return {
            "consistencyValidation": validation,
            "storyboardVersion": self._fact(compile_gate, "StoryboardVersion"),
            "creativeShotVersions": sorted(
                (
                    deepcopy(dict(fact["payload"]))
                    for fact in compile_gate["facts"]
                    if str(fact.get("factKind", "")).startswith(
                        "CreativeShotVersion:"
                    )
                ),
                key=lambda item: item["globalOrder"],
            ),
            "executableShotGraph": self._fact(
                compile_gate, "ExecutableShotGraph"
            ),
            "state": compile_gate["toState"],
            "idempotentReplay": validation_replay and compile_replay,
        }

    def get_shot_graph_bundle(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        root = self.root_service.get_run(workspace_ref, production_run_ref)
        validation_gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, SCRIPT_VALIDATION_GATE
        )
        compile_gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, SHOT_GRAPH_GATE
        )
        if validation_gate is None:
            raise UpstreamNotReadyError("G3 Shot Graph is not ready")
        if root["manifest"].get("schemaVersion") == MANIFEST_SCHEMA_VERSION_V2:
            if compile_gate is not None or validation_gate.get("toState") != "SCRIPT_VALIDATED":
                raise RepositoryUnavailableError(
                    "local structural draft evidence state is inconsistent"
                )
            return self._validated_draft_bundle(
                root,
                validation_gate,
                self.authority_identity.verify_authority_identity_current(
                    workspace_ref, production_run_ref
                ),
            )
        if compile_gate is None:
            raise UpstreamNotReadyError("G3 Shot Graph is not ready")
        return {
            "consistencyValidation": self._fact(
                validation_gate, "ConsistencyValidation"
            ),
            "storyboardVersion": self._fact(compile_gate, "StoryboardVersion"),
            "creativeShotVersions": sorted(
                (
                    deepcopy(dict(fact["payload"]))
                    for fact in compile_gate["facts"]
                    if str(fact.get("factKind", "")).startswith(
                        "CreativeShotVersion:"
                    )
                ),
                key=lambda item: item["globalOrder"],
            ),
            "executableShotGraph": self._fact(
                compile_gate, "ExecutableShotGraph"
            ),
            "state": compile_gate["toState"],
        }

    def verify_shot_graph_current(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        verified = self.authority_identity.verify_authority_identity_current(
            workspace_ref, production_run_ref
        )
        root = verified["root"]
        if root["manifest"].get("schemaVersion") == MANIFEST_SCHEMA_VERSION_V2:
            raise ExecutionNotAuthorizedError(
                "local structural shot plan draft is not an executable graph"
            )
        self._script_version(root)
        bundle = self.get_shot_graph_bundle(workspace_ref, production_run_ref)
        validation = bundle["consistencyValidation"]
        storyboard = bundle["storyboardVersion"]
        shots = bundle["creativeShotVersions"]
        graph = bundle["executableShotGraph"]
        if (
            graph.get("rootPayloadDigest") != root["payloadDigest"]
            or graph.get("scriptVersionRef") != root["scriptVersionRef"]
            or graph.get("authorityDecisionDigest")
            != verified["authorityDecision"]["payloadDigest"]
            or graph.get("identityLockDigest")
            != verified["identityLock"]["payloadDigest"]
            or graph.get("consistencyValidationDigest")
            != validation.get("payloadDigest")
            or graph.get("storyboardDigest") != storyboard.get("payloadDigest")
            or len(shots) != root["manifest"]["expectedShotCount"]
        ):
            raise StaleInputError("G3 Shot Graph lineage is stale")
        shot_digests = {
            shot.get("creativeShotVersionRef"): shot.get("payloadDigest")
            for shot in shots
        }
        if len(shot_digests) != len(shots) or any(
            shot_digests.get(node.get("creativeShotVersionRef"))
            != node.get("payloadDigest")
            for node in graph.get("shots", [])
        ):
            raise StaleInputError("G3 CreativeShot lineage is stale")
        validate_executable_shot_graph(graph)
        return {**verified, **bundle}

    def verify_shot_plan_draft_current(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        verified = self.authority_identity.verify_authority_identity_current(
            workspace_ref, production_run_ref
        )
        root = verified["root"]
        if root["manifest"].get("schemaVersion") != MANIFEST_SCHEMA_VERSION_V2:
            raise UpstreamNotReadyError("local structural shot plan draft is unavailable")
        self._script_version(root)
        bundle = self.get_shot_graph_bundle(workspace_ref, production_run_ref)
        validation = bundle["consistencyValidation"]
        storyboard = bundle["storyboardDraft"]
        shots = bundle["creativeShotDrafts"]
        draft = bundle["shotPlanDraft"]
        if (
            bundle.get("state") != "SCRIPT_VALIDATED"
            or validation.get("workspaceRef") != workspace_ref
            or validation.get("productionRunRef") != production_run_ref
            or validation.get("rootPayloadDigest") != root["payloadDigest"]
            or validation.get("scriptVersionRef") != root["scriptVersionRef"]
            or validation.get("scriptVersionDigest")
            != root["upstreamSnapshot"]["script"]["versionDigest"]
            or validation.get("authorityDecisionRef")
            != verified["authorityDecision"]["authorityDecisionRef"]
            or validation.get("authorityDecisionDigest")
            != verified["authorityDecision"]["payloadDigest"]
            or validation.get("identityLockRef")
            != verified["identityLock"]["identityLockRef"]
            or validation.get("identityLockVersionRef")
            != verified["identityLock"]["identityLockVersionRef"]
            or validation.get("identityLockDigest")
            != verified["identityLock"]["payloadDigest"]
            or draft.get("workspaceRef") != workspace_ref
            or draft.get("productionRunRef") != production_run_ref
            or draft.get("rootPayloadDigest") != root["payloadDigest"]
            or draft.get("scriptVersionRef") != root["scriptVersionRef"]
            or draft.get("scriptVersionDigest")
            != root["upstreamSnapshot"]["script"]["versionDigest"]
            or draft.get("authorityDecisionRef")
            != verified["authorityDecision"]["authorityDecisionRef"]
            or draft.get("authorityDecisionDigest")
            != verified["authorityDecision"]["payloadDigest"]
            or draft.get("identityLockRef")
            != verified["identityLock"]["identityLockRef"]
            or draft.get("identityLockVersionRef")
            != verified["identityLock"]["identityLockVersionRef"]
            or draft.get("identityLockDigest")
            != verified["identityLock"]["payloadDigest"]
            or draft.get("consistencyValidationRef")
            != validation.get("consistencyValidationRef")
            or draft.get("consistencyValidationDigest")
            != validation.get("payloadDigest")
            or draft.get("storyboardDraftRef")
            != storyboard.get("storyboardDraftRef")
            or draft.get("storyboardDigest") != storyboard.get("payloadDigest")
            or len(shots) != root["manifest"]["expectedShotCount"]
            or not isinstance(draft.get("shots"), list)
            or len(draft["shots"]) != len(shots)
        ):
            raise StaleInputError("local structural shot plan draft lineage is stale")
        shot_digests = {
            shot.get("creativeShotDraftRef"): shot.get("payloadDigest")
            for shot in shots
        }
        if len(shot_digests) != len(shots) or any(
            shot_digests.get(node.get("creativeShotDraftRef"))
            != node.get("payloadDigest")
            for node in draft.get("shots", [])
        ):
            raise StaleInputError("CreativeShotDraft lineage is stale")
        current_identities = verified["identityLock"].get("identities")
        if not isinstance(current_identities, list) or not all(
            isinstance(item, Mapping) for item in current_identities
        ):
            raise StaleInputError("current IdentityLock mapping is malformed")
        identity_by_name = {
            item.get("scriptCharacterName"): item for item in current_identities
        }
        if len(identity_by_name) != len(current_identities):
            raise StaleInputError("current IdentityLock mapping is ambiguous")
        for shot in shots:
            locks = shot.get("requiredCharacterIdentityLocks")
            if not isinstance(locks, list):
                raise StaleInputError("CreativeShotDraft identity mapping is malformed")
            for lock in locks:
                current = identity_by_name.get(lock.get("scriptCharacterName"))
                if (
                    not isinstance(current, Mapping)
                    or lock.get("characterRef") != current.get("characterRef")
                ):
                    raise StaleInputError(
                        "CreativeShotDraft identity mapping is stale"
                    )
                if lock.get("bindingMode") == "FACE_LOCK":
                    reference = current.get("reference")
                    if (
                        not isinstance(reference, Mapping)
                        or lock.get("identityLockRef")
                        != verified["identityLock"].get("identityLockRef")
                        or lock.get("identityLockVersionRef")
                        != verified["identityLock"].get("identityLockVersionRef")
                        or lock.get("identityLockDigest")
                        != verified["identityLock"].get("payloadDigest")
                        or lock.get("referenceVersionRef")
                        != reference.get("referenceVersionRef")
                        or lock.get("referenceDigest")
                        != reference.get("contentDigest")
                    ):
                        raise StaleInputError(
                            "CreativeShotDraft face identity mapping is stale"
                        )
                elif lock.get("bindingMode") == "BODY_ONLY":
                    if (
                        lock.get("characterFactDigest")
                        != current.get("characterFactDigest")
                        or lock.get("characterContinuityVersionRef")
                        != verified["identityLock"].get(
                            "characterContinuityVersionRef"
                        )
                        or lock.get("characterContinuityVersionDigest")
                        != verified["identityLock"].get(
                            "characterContinuityVersionDigest"
                        )
                    ):
                        raise StaleInputError(
                            "CreativeShotDraft body identity mapping is stale"
                        )
                else:
                    raise StaleInputError(
                        "CreativeShotDraft identity binding mode is stale"
                    )
        validate_shot_plan_draft(draft)
        return {**verified, **bundle}
