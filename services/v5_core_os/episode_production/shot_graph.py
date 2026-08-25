"""G3 confirmed ScriptVersion validation and executable K2 Shot Graph compiler."""

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
CREATIVE_SHOT_SCHEMA_VERSION_V2 = "v5.creative-shot-version.v2"
SHOT_GRAPH_SCHEMA_VERSION = "v5.executable-shot-graph.v1"
SHOT_GRAPH_SCHEMA_VERSION_V2 = "v5.executable-shot-graph.v2"
COMPILER_ID = "k2.deterministic-shot-compiler.v1"
COMPILER_ID_V2 = "k2.deterministic-shot-compiler.v2"


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
    if schema_version == SHOT_GRAPH_SCHEMA_VERSION_V2:
        if (
            graph.get("status") != "LOCAL_STRUCTURAL_REPRESENTATION"
            or graph.get("executionAuthorizationState")
            != "PREFLIGHT_ONLY_NOT_AUTHORIZED"
            or graph.get("dispatchAllowed") is not False
        ):
            raise StaleInputError("v2 shot graph safety boundary is inconsistent")
        raise ExecutionNotAuthorizedError(
            "v2 shot graph is preflight-only and not authorized for execution"
        )
    raise StaleInputError("shot graph schema is not execution-compatible")


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value["payloadDigest"] = _digest(value)
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValidationFailedError(f"{field} is invalid")
    return value


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


def _validate_output_profile_v2(output: Mapping[str, Any]) -> None:
    if output.get("schemaVersion") != OUTPUT_PROFILE_SCHEMA_VERSION_V2:
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


def validate_executable_shot_graph(graph: Mapping[str, Any]) -> None:
    if not isinstance(graph, Mapping):
        raise ValidationFailedError("Shot Graph must be an object")
    schema_version = graph.get("schemaVersion")
    if schema_version not in {SHOT_GRAPH_SCHEMA_VERSION, SHOT_GRAPH_SCHEMA_VERSION_V2}:
        raise ValidationFailedError("Shot Graph schema is unsupported")
    v2 = schema_version == SHOT_GRAPH_SCHEMA_VERSION_V2
    if v2:
        if (
            graph.get("shotPlanAuthorityState")
            != "LOCAL_STRUCTURAL_REPRESENTATION_ONLY"
            or graph.get("shotPlanApprovalState") != "NOT_VERIFIED"
            or graph.get("cameraContractState") != "UNVERIFIED_COMMAND_INPUT"
            or graph.get("executionAuthorizationState")
            != "PREFLIGHT_ONLY_NOT_AUTHORIZED"
            or graph.get("dispatchAllowed") is not False
        ):
            raise ValidationFailedError(
                "Shot Graph v2 execution authority is invalid"
            )
        _graph_ref(graph.get("identityLockRef"), "identityLockRef")
        _graph_ref(graph.get("identityLockVersionRef"), "identityLockVersionRef")
        _graph_digest(graph.get("identityLockDigest"), "identityLockDigest")
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
        shot_ref = _graph_ref(
            node.get("creativeShotRef"), f"shots[{index}].creativeShotRef"
        )
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
        if not v2:
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
            _validate_camera(
                node.get("cameraInstruction"), f"shots[{index}].cameraInstruction"
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
    if v2:
        _validate_output_profile_v2(output)
    chronological = set()
    adjacency: dict[str, set[str]] = {ref: set() for ref in refs}
    for index, edge in enumerate(edges):
        source = edge.get("fromShotRef")
        target = edge.get("toShotRef")
        edge_type = edge.get("edgeType")
        if source not in adjacency or target not in adjacency or source == target:
            raise ValidationFailedError(f"edges[{index}] has invalid endpoints")
        if edge_type not in {"chronology", "continuity"}:
            raise ValidationFailedError(f"edges[{index}] has invalid type")
        adjacency[source].add(target)
        if edge_type == "chronology":
            chronological.add((source, target))
    ordered_refs = [
        item["creativeShotRef"]
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
            CREATIVE_SHOT_SCHEMA_VERSION_V2 if v2 else CREATIVE_SHOT_SCHEMA_VERSION
        )
        shot_graph_schema = SHOT_GRAPH_SCHEMA_VERSION_V2 if v2 else SHOT_GRAPH_SCHEMA_VERSION
        compiler_id = COMPILER_ID_V2 if v2 else COMPILER_ID
        explicit_budgets = root["manifest"].get("shotBudgets") if v2 else None
        if v2 and (
            not isinstance(explicit_budgets, list)
            or not explicit_budgets
            or not all(isinstance(item, Mapping) for item in explicit_budgets)
        ):
            raise StaleInputError("frozen explicit shot budgets are malformed")
        storyboard_ref = _required_ref(
            self._ref_factory("storyboard"), "storyboardRef"
        )
        storyboard_version_ref = _required_ref(
            self._ref_factory("storyboard-version"), "storyboardVersionRef"
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
                self._ref_factory("storyboard-scene"), "storyboardSceneRef"
            )
            storyboard_scene_version_ref = _required_ref(
                self._ref_factory("storyboard-scene-version"),
                "storyboardSceneVersionRef",
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
                    self._ref_factory("creative-shot"), "creativeShotRef"
                )
                shot_version_ref = _required_ref(
                    self._ref_factory("creative-shot-version"),
                    "creativeShotVersionRef",
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
                    "creativeShotRef": shot_ref,
                    "creativeShotVersionRef": shot_version_ref,
                    "version": 1,
                    "storyboardRef": storyboard_ref,
                    "storyboardVersionRef": storyboard_version_ref,
                    "storyboardSceneRef": storyboard_scene_ref,
                    "storyboardSceneVersionRef": storyboard_scene_version_ref,
                    "scriptRef": root["scriptRef"],
                    "scriptVersionRef": root["scriptVersionRef"],
                    "scriptSceneRef": scene["scriptSceneRef"],
                    "sourceScriptSpans": source_spans,
                    "globalOrder": global_order,
                    "sceneOrder": scene_order,
                    "durationFrames": shot_spec["durationFrames"],
                    "frameRate": root["manifest"]["output"]["frameRate"],
                    "cameraInstruction": deepcopy(dict(shot_spec["camera"])),
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
                    "status": "COMPILED_LOCAL_EVIDENCE",
                    "approvalRequired": True,
                    "createdBy": compiler_id,
                    "createdAt": created_at,
                }
                if v2:
                    base.update(
                        {
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
                shots.append(_sealed(base))
            if v2 and (
                dialogue_cursor != len(scene["dialogue"])
                or narration_cursor != len(scene["narration"])
            ):
                raise StaleInputError(
                    "explicit shot dialogue does not cover the Script scene"
                )
            storyboard_scenes.append(
                {
                    "storyboardSceneRef": storyboard_scene_ref,
                    "storyboardSceneVersionRef": storyboard_scene_version_ref,
                    "scriptSceneRef": scene["scriptSceneRef"],
                    "sceneNumber": scene["sceneNumber"],
                    "heading": scene["heading"],
                    "locationRef": location["locationRef"],
                    "propRefs": [
                        prop["propRef"] for prop in scene["authorityBinding"]["props"]
                    ],
                    "durationFrames": scene["durationFrames"],
                    "creativeShotRefs": scene_shot_refs,
                }
            )
        storyboard = _sealed(
            {
                "schemaVersion": STORYBOARD_SCHEMA_VERSION,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "storyboardRef": storyboard_ref,
                "storyboardVersionRef": storyboard_version_ref,
                "version": 1,
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
                "status": "COMPILED_LOCAL_EVIDENCE",
                "approvalRequired": True,
                "createdBy": compiler_id,
                "createdAt": created_at,
            }
        )
        edges: list[dict[str, Any]] = []
        for previous, current in zip(shots, shots[1:]):
            edges.append(
                {
                    "edgeRef": _required_ref(
                        self._ref_factory("shot-edge"), "edgeRef"
                    ),
                    "edgeType": "chronology",
                    "fromShotRef": previous["creativeShotRef"],
                    "toShotRef": current["creativeShotRef"],
                }
            )
        last_by_character: dict[str, tuple[str, str | None]] = {}
        for shot in shots:
            for identity in shot["requiredCharacterIdentityLocks"]:
                character_ref = identity["characterRef"]
                previous = last_by_character.get(character_ref)
                if previous is not None:
                    previous_ref, previous_mode = previous
                    current_mode = identity.get("bindingMode") if v2 else None
                    edges.append(
                        {
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
                            "fromShotRef": previous_ref,
                            "toShotRef": shot["creativeShotRef"],
                        }
                    )
                last_by_character[character_ref] = (
                    shot["creativeShotRef"],
                    identity.get("bindingMode") if v2 else None,
                )
        graph = _sealed(
            {
                "schemaVersion": shot_graph_schema,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "executableShotGraphRef": _required_ref(
                    self._ref_factory("executable-shot-graph"),
                    "executableShotGraphRef",
                ),
                "executableShotGraphVersionRef": _required_ref(
                    self._ref_factory("executable-shot-graph-version"),
                    "executableShotGraphVersionRef",
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
                "consistencyValidationRef": validation[
                    "consistencyValidationRef"
                ],
                "consistencyValidationDigest": validation["payloadDigest"],
                "storyboardRef": storyboard_ref,
                "storyboardVersionRef": storyboard_version_ref,
                "storyboardDigest": storyboard["payloadDigest"],
                "shots": [
                    {
                        **{
                            key: shot[key]
                            for key in (
                                "creativeShotRef", "creativeShotVersionRef",
                                "payloadDigest", "scriptSceneRef", "globalOrder",
                                "sceneOrder", "durationFrames", "frameRate",
                                "cameraInstruction", "requiredCharacterIdentityLocks",
                                "assetRequirementSeeds", "continuityConstraints",
                            )
                        },
                        **(
                            {
                                "visibleIdentityMode": shot["visibleIdentityMode"],
                                "visibleCharacterRefs": shot["visibleCharacterRefs"],
                                "visibleIdentityBindings": shot[
                                    "visibleIdentityBindings"
                                ],
                                "actionBeat": shot["actionBeat"],
                                "dialogueSyncMode": shot["dialogueSyncMode"],
                                "dialogueRequirement": shot[
                                    "dialogueRequirement"
                                ],
                                "postprocessRequirements": shot[
                                    "postprocessRequirements"
                                ],
                            }
                            if v2
                            else {}
                        ),
                    }
                    for shot in shots
                ],
                "edges": edges,
                "output": {
                    **deepcopy(dict(root["manifest"]["output"])),
                    "totalFrames": sum(shot["durationFrames"] for shot in shots),
                },
                "executionMode": root["manifest"]["executionMode"],
                "publicationAllowed": False,
                **(
                    {
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
                        "status": "LOCAL_STRUCTURAL_REPRESENTATION",
                    }
                    if v2
                    else {"status": "EXECUTABLE_LOCAL_EVIDENCE"}
                ),
                "createdBy": compiler_id,
                "createdAt": created_at,
            }
        )
        validate_executable_shot_graph(graph)
        return storyboard, shots, graph

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
        compiler_id = (
            COMPILER_ID_V2
            if root["manifest"].get("schemaVersion") == MANIFEST_SCHEMA_VERSION_V2
            else COMPILER_ID
        )
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
        self.root_service.get_run(workspace_ref, production_run_ref)
        validation_gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, SCRIPT_VALIDATION_GATE
        )
        compile_gate = self.evidence.get_gate(
            workspace_ref, production_run_ref, SHOT_GRAPH_GATE
        )
        if validation_gate is None or compile_gate is None:
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
