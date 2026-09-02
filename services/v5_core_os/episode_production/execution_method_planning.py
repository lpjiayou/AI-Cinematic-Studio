"""Generic M8/M9 execution-method planning on the existing evidence journal."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .foundation import (
    EpisodeProductionError,
    EpisodeProductionService,
    ExecutionNotAuthorizedError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
    _utc_now,
)
from .narrative_validation import M7NarrativeValidationService, _source_index


EXECUTION_METHOD_PLAN_RECORD_KIND = "ExecutionMethodPlanVersion"
EXECUTION_METHOD_PLAN_SCHEMA_VERSION = "v5.execution-method-plan.v2"
STORYBOARD_SCHEMA_VERSION_V2 = "v5.storyboard-version.v2"
CREATIVE_SHOT_SCHEMA_VERSION_V2 = "v5.creative-shot-version.v2"
ACTION_EXECUTION_BEAT_SCHEMA_VERSION = "v5.action-execution-beat.v1"
VISUAL_EXECUTION_REQUIREMENT_SCHEMA_VERSION = (
    "v5.visual-execution-requirement.v1"
)
AUDIO_REQUIREMENT_SCHEMA_VERSION = "v5.audio-requirement.v1"
POSTPROCESS_REQUIREMENT_SCHEMA_VERSION = "v5.postprocess-requirement.v1"

EXECUTION_CLASSES = frozenset(
    {
        "STATIC_HOLD",
        "MICRO_MOTION",
        "CONTACT_ACTION",
        "GAIT_LOCOMOTION",
        "DETERMINISTIC_EVENT",
    }
)
VISUAL_EXECUTION_METHODS = frozenset(
    {
        "STATIC_PLATE_OR_REUSE",
        "SINGLE_ANCHOR_I2V",
        "CONTACT_CONDITIONED_VIDEO",
        "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
        "V3_DETERMINISTIC_COMPOSITION",
    }
)
EXECUTION_METHOD_BY_CLASS = {
    "STATIC_HOLD": "STATIC_PLATE_OR_REUSE",
    "MICRO_MOTION": "SINGLE_ANCHOR_I2V",
    "CONTACT_ACTION": "CONTACT_CONDITIONED_VIDEO",
    "GAIT_LOCOMOTION": "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
    "DETERMINISTIC_EVENT": "V3_DETERMINISTIC_COMPOSITION",
}
REQUIREMENT_DISPOSITIONS = frozenset(
    {
        "REUSE_EXISTING_ASSET",
        "GENERATE_NEW_ASSET",
        "DERIVE_DETERMINISTIC_POSTPROCESS",
        "CAPABILITY_UNAVAILABLE",
        "NO_ASSET_REQUIRED",
    }
)
VISUAL_DISPOSITION_BY_CLASS = {
    "STATIC_HOLD": "NO_ASSET_REQUIRED",
    "MICRO_MOTION": "GENERATE_NEW_ASSET",
    "CONTACT_ACTION": "GENERATE_NEW_ASSET",
    "GAIT_LOCOMOTION": "GENERATE_NEW_ASSET",
    "DETERMINISTIC_EVENT": "DERIVE_DETERMINISTIC_POSTPROCESS",
}
AUDIO_TYPES = frozenset(
    {"DIALOGUE", "NARRATION", "AMBIENCE", "SFX", "MUSIC", "SILENCE"}
)
AUDIO_DISPOSITION_BY_TYPE = {
    "DIALOGUE": "GENERATE_NEW_ASSET",
    "NARRATION": "GENERATE_NEW_ASSET",
    "AMBIENCE": "GENERATE_NEW_ASSET",
    "SFX": "GENERATE_NEW_ASSET",
    "MUSIC": "CAPABILITY_UNAVAILABLE",
    "SILENCE": "NO_ASSET_REQUIRED",
}

_SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
_SOURCE_SPAN_FIELDS = frozenset(
    {
        "scriptSceneRef",
        "sourceField",
        "sourceIndex",
        "startOffsetInclusive",
        "endOffsetExclusive",
    }
)
_SOURCE_FIELDS = frozenset(
    {"ACTION", "DIALOGUE", "NARRATION", "SUBTITLE_TEXT"}
)
_CREATE_FIELDS = frozenset(
    {
        *_SCOPE_FIELDS,
        "productionRunRef",
        "consistencyValidationVersionRef",
        "shots",
        "idempotencyKey",
    }
)
_SHOT_INPUT_FIELDS = frozenset(
    {
        "shotOrder",
        "shotFrameCount",
        "cameraInstruction",
        "actionExecutionBeats",
        "audioIntents",
    }
)
_CAMERA_FIELDS = frozenset({"framing", "movement"})
_BEAT_INPUT_FIELDS = frozenset(
    {
        "beatRef",
        "beatOrder",
        "sourceSpan",
        "subjectRefs",
        "targetRefs",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "executionClass",
    }
)
_AUDIO_INTENT_FIELDS = frozenset(
    {"audioType", "beatRef", "timingReference"}
)
_TIMING_FIELDS = frozenset(
    {"startFrameInclusive", "endFrameExclusive"}
)
_PLAN_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionMethodPlanRef",
        "executionMethodPlanVersionRef",
        "planningVersion",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "consistencyValidationVersionRef",
        "consistencyValidationDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "storyboardVersion",
        "creativeShotVersions",
        "visualExecutionRequirements",
        "audioRequirements",
        "postprocessRequirements",
        "payloadDigest",
    }
)
_STORYBOARD_FIELDS = frozenset(
    {
        "schemaVersion",
        "storyboardRef",
        "storyboardVersionRef",
        "storyboardVersion",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "consistencyValidationVersionRef",
        "consistencyValidationDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "creativeShotVersionRefs",
        "payloadDigest",
    }
)
_CREATIVE_SHOT_FIELDS = frozenset(
    {
        "schemaVersion",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotVersion",
        "shotOrder",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "storyboardRef",
        "storyboardVersionRef",
        "storyboardVersionDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRefs",
        "shotFrameCount",
        "cameraInstruction",
        "actionExecutionBeats",
        "payloadDigest",
    }
)
_BEAT_FIELDS = frozenset(
    {
        "schemaVersion",
        *_BEAT_INPUT_FIELDS,
        "sourceTextDigest",
        "payloadDigest",
    }
)
_VISUAL_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "visualExecutionRequirementRef",
        "requirementOrder",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "storyboardVersionRef",
        "storyboardVersionDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "beatRef",
        "beatDigest",
        "executionClass",
        "executionMethod",
        "disposition",
        "payloadDigest",
    }
)
_AUDIO_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "audioRequirementRef",
        "requirementOrder",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "storyboardVersionRef",
        "storyboardVersionDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "beatRef",
        "beatDigest",
        "audioType",
        "timingReference",
        "disposition",
        "payloadDigest",
    }
)
_POSTPROCESS_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "postprocessRequirementRef",
        "requirementOrder",
        *_SCOPE_FIELDS,
        "productionRunRef",
        "storyboardVersionRef",
        "storyboardVersionDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "beatRef",
        "beatDigest",
        "postprocessRequirementKey",
        "executionMethod",
        "eventFreeBaseMediaRequirementKey",
        "maskAssetRequirementKeys",
        "resourceAssetRequirementKeys",
        "staticAssetRequirementKeys",
        "disposition",
        "payloadDigest",
    }
)
_M6_REF_COLLECTIONS = {
    "characters": "characterRef",
    "locations": "locationRef",
    "props": "propRef",
    "factions": "factionRef",
    "timelineEvents": "timelineEventRef",
}


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _digest_value(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RepositoryUnavailableError(f"stored {field} is invalid")
    return value


def _text_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _seal(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any,
    fields: frozenset[str],
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RepositoryUnavailableError(f"stored {field} fields are invalid")
    result = deepcopy(dict(value))
    digest = _digest_value(result.pop("payloadDigest"), f"{field}.payloadDigest")
    if digest != _digest(result):
        raise RepositoryUnavailableError(f"stored {field} digest is invalid")
    result["payloadDigest"] = digest
    return result


class M8M9ExecutionMethodPlanningService:
    """Own additive M8 shot versions and M9 planning facts without dispatch."""

    def __init__(
        self,
        run_service: EpisodeProductionService,
        evidence_repository: EpisodeProductionEvidenceRepository,
        *,
        narrative_validation: M7NarrativeValidationService,
        script_reader: Any,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.run_service = run_service
        self.evidence_repository = evidence_repository
        self.narrative_validation = narrative_validation
        self.script_reader = script_reader
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _not_found_scope(run: Mapping[str, Any], scope: Mapping[str, str]) -> None:
        if any(run.get(field) != value for field, value in scope.items()):
            raise RecordNotFoundError("execution method plan scope was not found")

    def _run_for_scope(
        self,
        scope: Mapping[str, str],
        run_ref: str,
    ) -> dict[str, Any]:
        run = self.run_service.get_run(scope["workspaceRef"], run_ref)
        self._not_found_scope(run, scope)
        return run

    @staticmethod
    def _read_script_workspace(operation: Callable[[], Any]) -> Mapping[str, Any]:
        try:
            workspace = operation()
        except Exception as exc:
            if (
                getattr(exc, "status", None) == 404
                or getattr(exc, "code", None) == "not_found"
            ):
                raise RecordNotFoundError(
                    "confirmed ScriptVersion was not found"
                ) from None
            raise RepositoryUnavailableError(
                "confirmed ScriptVersion could not be read"
            ) from None
        if not isinstance(workspace, Mapping):
            raise RepositoryUnavailableError("confirmed ScriptVersion is unavailable")
        return workspace

    def _current_resolution(
        self,
        scope: Mapping[str, str],
        run_ref: str,
        validation_version_ref: str,
    ) -> dict[str, Any]:
        run = self._run_for_scope(scope, run_ref)
        self.run_service.verify_run_current(scope["workspaceRef"], run_ref)
        validation = self.narrative_validation.require_m8_ready_validation(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
            validation_version_ref,
        )
        latest = self.narrative_validation.get_validation(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
        )
        if (
            latest.get("consistencyValidationVersionRef")
            != validation.get("consistencyValidationVersionRef")
        ):
            raise ExecutionNotAuthorizedError(
                "latest current READY_FOR_M8 validation is required"
            )
        script_workspace = self._read_script_workspace(
            lambda: self.script_reader.get_workspace(
                scope["workspaceRef"], scope["seriesRef"], scope["episodeRef"]
            )
        )
        script = script_workspace.get("script")
        versions = script_workspace.get("versions")
        if not isinstance(script, Mapping) or not isinstance(versions, list):
            raise StaleInputError("confirmed ScriptVersion is unavailable")
        version_ref = validation.get("scriptVersionRef")
        if script.get("confirmedScriptVersionRef") != version_ref:
            raise StaleInputError("confirmed ScriptVersion changed")
        version = next(
            (
                item
                for item in versions
                if isinstance(item, Mapping)
                and item.get("scriptVersionRef") == version_ref
            ),
            None,
        )
        if not isinstance(version, Mapping):
            raise StaleInputError("confirmed ScriptVersion is unavailable")
        script_digest = _digest(dict(version))
        if script_digest != validation.get("scriptVersionDigest"):
            raise StaleInputError("confirmed ScriptVersion digest changed")
        try:
            m6_context = self.script_reader.resolve_current_m6_consumer_context(
                scope["workspaceRef"],
                scope["projectRef"],
                scope["seriesRef"],
                scope["episodeRef"],
            )
        except Exception:
            raise StaleInputError("current M6 consumer context is unavailable") from None
        binding = (
            m6_context.get("m6ConsumerBinding")
            if isinstance(m6_context, Mapping)
            else None
        )
        facts = (
            m6_context.get("applicableFacts")
            if isinstance(m6_context, Mapping)
            else None
        )
        if not isinstance(binding, Mapping) or not isinstance(facts, Mapping):
            raise RepositoryUnavailableError("current M6 consumer context is invalid")
        if binding.get("payloadDigest") != validation.get("m6ConsumerBindingDigest"):
            raise StaleInputError("M7 M6 consumer binding is stale")
        return {
            "run": run,
            "validation": deepcopy(dict(validation)),
            "scriptVersion": deepcopy(dict(version)),
            "scriptVersionDigest": script_digest,
            "m6ApplicableFacts": deepcopy(dict(facts)),
        }

    @staticmethod
    def _m6_refs(
        facts: Mapping[str, Any],
    ) -> tuple[set[str], dict[str, str]]:
        refs: set[str] = set()
        character_names: dict[str, str] = {}
        for collection, ref_field in _M6_REF_COLLECTIONS.items():
            values = facts.get(collection, [])
            if not isinstance(values, list):
                raise RepositoryUnavailableError(
                    f"current M6 {collection} facts are invalid"
                )
            for index, item in enumerate(values):
                if not isinstance(item, Mapping):
                    raise RepositoryUnavailableError(
                        f"current M6 {collection} fact is invalid"
                    )
                ref = _required_ref(
                    item.get(ref_field), f"{collection}[{index}].{ref_field}"
                )
                if ref in refs:
                    raise RepositoryUnavailableError(
                        "current M6 reference identity is ambiguous"
                    )
                refs.add(ref)
                if collection == "characters":
                    name = _required_text(
                        item.get("name"), f"characters[{index}].name"
                    )
                    if name in character_names:
                        raise RepositoryUnavailableError(
                            "current M6 character name is ambiguous"
                        )
                    character_names[name] = ref
        if not character_names:
            raise RepositoryUnavailableError("current M6 character facts are empty")
        return refs, character_names

    @staticmethod
    def _normalize_refs(value: Any, field: str, *, nonempty: bool) -> list[str]:
        if not isinstance(value, list) or (nonempty and not value):
            raise EpisodeProductionError(f"{field} is invalid")
        refs = [
            _required_ref(item, f"{field}[{index}]")
            for index, item in enumerate(value)
        ]
        if len(refs) != len(set(refs)):
            raise EpisodeProductionError(f"{field} contains duplicate refs")
        return sorted(refs)

    @staticmethod
    def _resolve_source_span(
        value: Any,
        sources: Mapping[tuple[str, str, int], Any],
        field: str,
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(value, Mapping) or set(value) != _SOURCE_SPAN_FIELDS:
            raise EpisodeProductionError(f"{field} fields are invalid")
        scene_ref = _required_ref(value.get("scriptSceneRef"), f"{field}.scriptSceneRef")
        source_field = value.get("sourceField")
        source_index = _nonnegative_int(value.get("sourceIndex"), f"{field}.sourceIndex")
        start = _nonnegative_int(
            value.get("startOffsetInclusive"), f"{field}.startOffsetInclusive"
        )
        end = _positive_int(
            value.get("endOffsetExclusive"), f"{field}.endOffsetExclusive"
        )
        if source_field not in _SOURCE_FIELDS or (
            source_field == "ACTION" and source_index != 0
        ):
            raise EpisodeProductionError(f"{field}.sourceField is invalid")
        source = sources.get((scene_ref, source_field, source_index))
        if source is None or not 0 <= start < end <= len(source.text):
            raise EpisodeProductionError(f"{field} is unresolved")
        span = {
            "scriptSceneRef": scene_ref,
            "sourceField": source_field,
            "sourceIndex": source_index,
            "startOffsetInclusive": start,
            "endOffsetExclusive": end,
        }
        return span, _text_digest(source.text[start:end])

    @staticmethod
    def _dialogue_speaker(
        script_version: Mapping[str, Any],
        source_span: Mapping[str, Any],
    ) -> str:
        scene_ref = source_span["scriptSceneRef"]
        source_index = source_span["sourceIndex"]
        scenes = script_version.get("scenes")
        if not isinstance(scenes, list):
            raise RepositoryUnavailableError("confirmed Script scenes are invalid")
        scene = next(
            (
                item
                for item in scenes
                if isinstance(item, Mapping)
                and item.get("scriptSceneRef") == scene_ref
            ),
            None,
        )
        dialogue = scene.get("dialogue") if isinstance(scene, Mapping) else None
        if (
            not isinstance(dialogue, list)
            or source_index >= len(dialogue)
            or not isinstance(dialogue[source_index], Mapping)
        ):
            raise RepositoryUnavailableError("confirmed Script dialogue is invalid")
        return _required_text(
            dialogue[source_index].get("speaker"), "dialogue.speaker"
        )

    def _normalize_shots(
        self,
        value: Any,
        *,
        script_version: Mapping[str, Any],
        m6_facts: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not value:
            raise EpisodeProductionError("shots are invalid")
        sources = _source_index(script_version)
        allowed_refs, character_names = self._m6_refs(m6_facts)
        result: list[dict[str, Any]] = []
        plan_beat_refs: set[str] = set()
        for shot_order, raw_shot in enumerate(value, start=1):
            shot_field = f"shots[{shot_order - 1}]"
            if not isinstance(raw_shot, Mapping) or set(raw_shot) != _SHOT_INPUT_FIELDS:
                raise EpisodeProductionError(f"{shot_field} fields are invalid")
            if raw_shot.get("shotOrder") != shot_order:
                raise EpisodeProductionError("shotOrder must be contiguous from 1")
            frame_count = _positive_int(
                raw_shot.get("shotFrameCount"), f"{shot_field}.shotFrameCount"
            )
            camera = raw_shot.get("cameraInstruction")
            if not isinstance(camera, Mapping) or set(camera) != _CAMERA_FIELDS:
                raise EpisodeProductionError(
                    f"{shot_field}.cameraInstruction fields are invalid"
                )
            normalized_camera = {
                "framing": _required_text(
                    camera.get("framing"), f"{shot_field}.cameraInstruction.framing"
                ),
                "movement": _required_text(
                    camera.get("movement"), f"{shot_field}.cameraInstruction.movement"
                ),
            }
            raw_beats = raw_shot.get("actionExecutionBeats")
            if not isinstance(raw_beats, list) or not raw_beats:
                raise EpisodeProductionError(
                    f"{shot_field}.actionExecutionBeats are invalid"
                )
            beats: list[dict[str, Any]] = []
            ranges_by_subject: dict[str, list[tuple[int, int]]] = {}
            for beat_order, raw_beat in enumerate(raw_beats, start=1):
                beat_field = f"{shot_field}.actionExecutionBeats[{beat_order - 1}]"
                if not isinstance(raw_beat, Mapping):
                    raise EpisodeProductionError(f"{beat_field} is invalid")
                execution_class = raw_beat.get("executionClass")
                expected_fields = set(_BEAT_INPUT_FIELDS)
                if execution_class == "DETERMINISTIC_EVENT":
                    expected_fields.add("postprocessRequirementKey")
                if set(raw_beat) != expected_fields:
                    raise EpisodeProductionError(f"{beat_field} fields are invalid")
                if execution_class not in EXECUTION_CLASSES:
                    raise EpisodeProductionError(
                        f"{beat_field}.executionClass is invalid"
                    )
                if raw_beat.get("beatOrder") != beat_order:
                    raise EpisodeProductionError(
                        "beatOrder must be contiguous from 1"
                    )
                beat_ref = _required_ref(raw_beat.get("beatRef"), f"{beat_field}.beatRef")
                if beat_ref in plan_beat_refs:
                    raise EpisodeProductionError("beatRef must be unique in the plan")
                plan_beat_refs.add(beat_ref)
                subjects = self._normalize_refs(
                    raw_beat.get("subjectRefs"),
                    f"{beat_field}.subjectRefs",
                    nonempty=True,
                )
                targets = self._normalize_refs(
                    raw_beat.get("targetRefs"),
                    f"{beat_field}.targetRefs",
                    nonempty=False,
                )
                if any(ref not in allowed_refs for ref in (*subjects, *targets)):
                    raise EpisodeProductionError(
                        f"{beat_field} contains an unresolved M6 ref"
                    )
                start = _nonnegative_int(
                    raw_beat.get("frameRangeStartInclusive"),
                    f"{beat_field}.frameRangeStartInclusive",
                )
                end = _positive_int(
                    raw_beat.get("frameRangeEndExclusive"),
                    f"{beat_field}.frameRangeEndExclusive",
                )
                if not start < end <= frame_count:
                    raise EpisodeProductionError(
                        f"{beat_field} frame range is outside its Shot"
                    )
                span, source_digest = self._resolve_source_span(
                    raw_beat.get("sourceSpan"), sources, f"{beat_field}.sourceSpan"
                )
                beat_payload: dict[str, Any] = {
                    "schemaVersion": ACTION_EXECUTION_BEAT_SCHEMA_VERSION,
                    "beatRef": beat_ref,
                    "beatOrder": beat_order,
                    "sourceSpan": span,
                    "sourceTextDigest": source_digest,
                    "subjectRefs": subjects,
                    "targetRefs": targets,
                    "frameRangeStartInclusive": start,
                    "frameRangeEndExclusive": end,
                    "executionClass": execution_class,
                }
                if execution_class == "DETERMINISTIC_EVENT":
                    beat_payload["postprocessRequirementKey"] = _required_ref(
                        raw_beat.get("postprocessRequirementKey"),
                        f"{beat_field}.postprocessRequirementKey",
                    )
                beats.append(_seal(beat_payload))
                for subject in subjects:
                    ranges_by_subject.setdefault(subject, []).append((start, end))
            for ranges in ranges_by_subject.values():
                previous_end = -1
                for start, end in sorted(ranges):
                    if start < previous_end:
                        raise EpisodeProductionError(
                            "beats for one subject may not overlap"
                        )
                    previous_end = end
            coverage_end = 0
            for start, end in sorted(
                (
                    (
                        beat["frameRangeStartInclusive"],
                        beat["frameRangeEndExclusive"],
                    )
                    for beat in beats
                )
            ):
                if start > coverage_end:
                    raise EpisodeProductionError(
                        "uncovered Shot frames require an explicit STATIC_HOLD beat"
                    )
                coverage_end = max(coverage_end, end)
            if coverage_end != frame_count:
                raise EpisodeProductionError(
                    "uncovered Shot frames require an explicit STATIC_HOLD beat"
                )
            beat_by_ref = {beat["beatRef"]: beat for beat in beats}
            raw_audio = raw_shot.get("audioIntents")
            if not isinstance(raw_audio, list):
                raise EpisodeProductionError(f"{shot_field}.audioIntents are invalid")
            audio_intents: list[dict[str, Any]] = []
            for audio_index, raw_intent in enumerate(raw_audio):
                audio_field = f"{shot_field}.audioIntents[{audio_index}]"
                if not isinstance(raw_intent, Mapping):
                    raise EpisodeProductionError(f"{audio_field} is invalid")
                audio_type = raw_intent.get("audioType")
                expected_audio_fields = set(_AUDIO_INTENT_FIELDS)
                if audio_type in {"DIALOGUE", "NARRATION"}:
                    expected_audio_fields.add("sourceSpan")
                if set(raw_intent) != expected_audio_fields or audio_type not in AUDIO_TYPES:
                    raise EpisodeProductionError(f"{audio_field} fields are invalid")
                beat_ref = _required_ref(
                    raw_intent.get("beatRef"), f"{audio_field}.beatRef"
                )
                if beat_ref not in beat_by_ref:
                    raise EpisodeProductionError(
                        f"{audio_field}.beatRef is not in the Shot"
                    )
                timing = raw_intent.get("timingReference")
                if not isinstance(timing, Mapping) or set(timing) != _TIMING_FIELDS:
                    raise EpisodeProductionError(
                        f"{audio_field}.timingReference fields are invalid"
                    )
                timing_start = _nonnegative_int(
                    timing.get("startFrameInclusive"),
                    f"{audio_field}.timingReference.startFrameInclusive",
                )
                timing_end = _positive_int(
                    timing.get("endFrameExclusive"),
                    f"{audio_field}.timingReference.endFrameExclusive",
                )
                if not timing_start < timing_end <= frame_count:
                    raise EpisodeProductionError(
                        f"{audio_field}.timingReference is outside its Shot"
                    )
                normalized_intent: dict[str, Any] = {
                    "audioType": audio_type,
                    "beatRef": beat_ref,
                    "timingReference": {
                        "startFrameInclusive": timing_start,
                        "endFrameExclusive": timing_end,
                    },
                }
                if audio_type in {"DIALOGUE", "NARRATION"}:
                    span, source_digest = self._resolve_source_span(
                        raw_intent.get("sourceSpan"),
                        sources,
                        f"{audio_field}.sourceSpan",
                    )
                    expected_source_field = (
                        "DIALOGUE" if audio_type == "DIALOGUE" else "NARRATION"
                    )
                    if span["sourceField"] != expected_source_field:
                        raise EpisodeProductionError(
                            f"{audio_field}.sourceSpan has the wrong sourceField"
                        )
                    normalized_intent["sourceSpan"] = span
                    normalized_intent["sourceTextDigest"] = source_digest
                    if audio_type == "DIALOGUE":
                        speaker = self._dialogue_speaker(script_version, span)
                        speaker_ref = character_names.get(speaker)
                        if speaker_ref is None:
                            raise EpisodeProductionError(
                                f"{audio_field} speaker is unresolved in current M6"
                            )
                        normalized_intent["speakerCharacterRef"] = speaker_ref
                audio_intents.append(normalized_intent)
            result.append(
                {
                    "shotOrder": shot_order,
                    "shotFrameCount": frame_count,
                    "cameraInstruction": normalized_camera,
                    "scriptSceneRefs": sorted(
                        {beat["sourceSpan"]["scriptSceneRef"] for beat in beats}
                    ),
                    "actionExecutionBeats": beats,
                    "audioIntents": audio_intents,
                }
            )
        return result

    @staticmethod
    def _request_digest(
        scope: Mapping[str, str],
        run_ref: str,
        resolution: Mapping[str, Any],
        shots: Sequence[Mapping[str, Any]],
    ) -> str:
        return _digest(
            {
                "schemaVersion": "v5.execution-method-plan-request.v2",
                **scope,
                "productionRunRef": run_ref,
                "productionRunPayloadDigest": resolution["run"]["payloadDigest"],
                "consistencyValidationVersionRef": resolution["validation"][
                    "consistencyValidationVersionRef"
                ],
                "consistencyValidationDigest": resolution["validation"][
                    "payloadDigest"
                ],
                "scriptVersionRef": resolution["scriptVersion"][
                    "scriptVersionRef"
                ],
                "scriptVersionDigest": resolution["scriptVersionDigest"],
                "shots": list(shots),
            }
        )

    def _build_payload(
        self,
        *,
        scope: Mapping[str, str],
        run_ref: str,
        resolution: Mapping[str, Any],
        shots: Sequence[Mapping[str, Any]],
        previous: Sequence[tuple[dict[str, Any], dict[str, Any]]],
    ) -> dict[str, Any]:
        planning_version = len(previous) + 1
        latest = previous[-1][1] if previous else None
        plan_ref = (
            latest["executionMethodPlanRef"]
            if latest is not None
            else _required_ref(
                self._ref_factory("execution-method-plan"),
                "executionMethodPlanRef",
            )
        )
        storyboard_ref = (
            latest["storyboardVersion"]["storyboardRef"]
            if latest is not None
            else _required_ref(self._ref_factory("storyboard"), "storyboardRef")
        )
        previous_shot_refs = {
            item["shotOrder"]: item["creativeShotRef"]
            for item in (
                latest.get("creativeShotVersions", []) if latest is not None else []
            )
        }
        shot_identities = []
        for shot in shots:
            order = shot["shotOrder"]
            shot_identities.append(
                {
                    "creativeShotRef": previous_shot_refs.get(order)
                    or _required_ref(
                        self._ref_factory("creative-shot"), "creativeShotRef"
                    ),
                    "creativeShotVersionRef": _required_ref(
                        self._ref_factory("creative-shot-version"),
                        "creativeShotVersionRef",
                    ),
                }
            )
        validation = resolution["validation"]
        script_version = resolution["scriptVersion"]
        storyboard = _seal(
            {
                "schemaVersion": STORYBOARD_SCHEMA_VERSION_V2,
                "storyboardRef": storyboard_ref,
                "storyboardVersionRef": _required_ref(
                    self._ref_factory("storyboard-version"),
                    "storyboardVersionRef",
                ),
                "storyboardVersion": planning_version,
                **scope,
                "productionRunRef": run_ref,
                "consistencyValidationVersionRef": validation[
                    "consistencyValidationVersionRef"
                ],
                "consistencyValidationDigest": validation["payloadDigest"],
                "scriptVersionRef": script_version["scriptVersionRef"],
                "scriptVersionDigest": resolution["scriptVersionDigest"],
                "creativeShotVersionRefs": [
                    item["creativeShotVersionRef"] for item in shot_identities
                ],
            }
        )
        creative_shots: list[dict[str, Any]] = []
        for shot, identity in zip(shots, shot_identities):
            creative_shots.append(
                _seal(
                    {
                        "schemaVersion": CREATIVE_SHOT_SCHEMA_VERSION_V2,
                        **identity,
                        "creativeShotVersion": planning_version,
                        "shotOrder": shot["shotOrder"],
                        **scope,
                        "productionRunRef": run_ref,
                        "storyboardRef": storyboard_ref,
                        "storyboardVersionRef": storyboard["storyboardVersionRef"],
                        "storyboardVersionDigest": storyboard["payloadDigest"],
                        "scriptVersionRef": script_version["scriptVersionRef"],
                        "scriptVersionDigest": resolution["scriptVersionDigest"],
                        "scriptSceneRefs": shot["scriptSceneRefs"],
                        "shotFrameCount": shot["shotFrameCount"],
                        "cameraInstruction": shot["cameraInstruction"],
                        "actionExecutionBeats": shot["actionExecutionBeats"],
                    }
                )
            )
        visual_requirements: list[dict[str, Any]] = []
        audio_requirements: list[dict[str, Any]] = []
        postprocess_requirements: list[dict[str, Any]] = []
        for creative, normalized in zip(creative_shots, shots):
            beat_by_ref = {
                beat["beatRef"]: beat
                for beat in creative["actionExecutionBeats"]
            }
            for beat in creative["actionExecutionBeats"]:
                execution_class = beat["executionClass"]
                visual_requirements.append(
                    _seal(
                        {
                            "schemaVersion": VISUAL_EXECUTION_REQUIREMENT_SCHEMA_VERSION,
                            "visualExecutionRequirementRef": _required_ref(
                                self._ref_factory("visual-execution-requirement"),
                                "visualExecutionRequirementRef",
                            ),
                            "requirementOrder": len(visual_requirements) + 1,
                            **scope,
                            "productionRunRef": run_ref,
                            "storyboardVersionRef": storyboard[
                                "storyboardVersionRef"
                            ],
                            "storyboardVersionDigest": storyboard["payloadDigest"],
                            "creativeShotVersionRef": creative[
                                "creativeShotVersionRef"
                            ],
                            "creativeShotVersionDigest": creative["payloadDigest"],
                            "beatRef": beat["beatRef"],
                            "beatDigest": beat["payloadDigest"],
                            "executionClass": execution_class,
                            "executionMethod": EXECUTION_METHOD_BY_CLASS[
                                execution_class
                            ],
                            "disposition": VISUAL_DISPOSITION_BY_CLASS[
                                execution_class
                            ],
                        }
                    )
                )
                if execution_class == "DETERMINISTIC_EVENT":
                    event_key = beat["postprocessRequirementKey"]
                    postprocess_requirements.append(
                        _seal(
                            {
                                "schemaVersion": POSTPROCESS_REQUIREMENT_SCHEMA_VERSION,
                                "postprocessRequirementRef": _required_ref(
                                    self._ref_factory("postprocess-requirement"),
                                    "postprocessRequirementRef",
                                ),
                                "requirementOrder": len(postprocess_requirements) + 1,
                                **scope,
                                "productionRunRef": run_ref,
                                "storyboardVersionRef": storyboard[
                                    "storyboardVersionRef"
                                ],
                                "storyboardVersionDigest": storyboard[
                                    "payloadDigest"
                                ],
                                "creativeShotVersionRef": creative[
                                    "creativeShotVersionRef"
                                ],
                                "creativeShotVersionDigest": creative[
                                    "payloadDigest"
                                ],
                                "beatRef": beat["beatRef"],
                                "beatDigest": beat["payloadDigest"],
                                "postprocessRequirementKey": event_key,
                                "executionMethod": "V3_DETERMINISTIC_COMPOSITION",
                                "eventFreeBaseMediaRequirementKey": (
                                    "event-free-base:"
                                    + sha256(event_key.encode("utf-8")).hexdigest()
                                ),
                                "maskAssetRequirementKeys": [],
                                "resourceAssetRequirementKeys": [],
                                "staticAssetRequirementKeys": [],
                                "disposition": "DERIVE_DETERMINISTIC_POSTPROCESS",
                            }
                        )
                    )
            for intent in normalized["audioIntents"]:
                beat = beat_by_ref[intent["beatRef"]]
                audio_payload: dict[str, Any] = {
                    "schemaVersion": AUDIO_REQUIREMENT_SCHEMA_VERSION,
                    "audioRequirementRef": _required_ref(
                        self._ref_factory("audio-requirement"),
                        "audioRequirementRef",
                    ),
                    "requirementOrder": len(audio_requirements) + 1,
                    **scope,
                    "productionRunRef": run_ref,
                    "scriptVersionRef": script_version["scriptVersionRef"],
                    "scriptVersionDigest": resolution["scriptVersionDigest"],
                    "storyboardVersionRef": storyboard["storyboardVersionRef"],
                    "storyboardVersionDigest": storyboard["payloadDigest"],
                    "creativeShotVersionRef": creative["creativeShotVersionRef"],
                    "creativeShotVersionDigest": creative["payloadDigest"],
                    "beatRef": beat["beatRef"],
                    "beatDigest": beat["payloadDigest"],
                    "audioType": intent["audioType"],
                    "timingReference": intent["timingReference"],
                    "disposition": AUDIO_DISPOSITION_BY_TYPE[intent["audioType"]],
                }
                for optional in (
                    "sourceSpan",
                    "sourceTextDigest",
                    "speakerCharacterRef",
                ):
                    if optional in intent:
                        audio_payload[optional] = intent[optional]
                audio_requirements.append(_seal(audio_payload))
        return _seal(
            {
                "schemaVersion": EXECUTION_METHOD_PLAN_SCHEMA_VERSION,
                "executionMethodPlanRef": plan_ref,
                "executionMethodPlanVersionRef": _required_ref(
                    self._ref_factory("execution-method-plan-version"),
                    "executionMethodPlanVersionRef",
                ),
                "planningVersion": planning_version,
                **scope,
                "productionRunRef": run_ref,
                "consistencyValidationVersionRef": validation[
                    "consistencyValidationVersionRef"
                ],
                "consistencyValidationDigest": validation["payloadDigest"],
                "scriptVersionRef": script_version["scriptVersionRef"],
                "scriptVersionDigest": resolution["scriptVersionDigest"],
                "storyboardVersion": storyboard,
                "creativeShotVersions": creative_shots,
                "visualExecutionRequirements": visual_requirements,
                "audioRequirements": audio_requirements,
                "postprocessRequirements": postprocess_requirements,
            }
        )

    @staticmethod
    def _validate_scope_fields(
        value: Mapping[str, Any], scope: Mapping[str, str], field: str
    ) -> None:
        if any(value.get(name) != expected for name, expected in scope.items()):
            raise RepositoryUnavailableError(f"stored {field} scope is invalid")

    @staticmethod
    def _validate_stored_source_span(
        value: Any,
        digest: Any,
        *,
        sources: Mapping[tuple[str, str, int], Any] | None,
        expected_field: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != _SOURCE_SPAN_FIELDS:
            raise RepositoryUnavailableError("stored sourceSpan fields are invalid")
        scene_ref = _required_ref(value.get("scriptSceneRef"), "scriptSceneRef")
        source_field = value.get("sourceField")
        source_index = value.get("sourceIndex")
        start = value.get("startOffsetInclusive")
        end = value.get("endOffsetExclusive")
        if (
            source_field not in _SOURCE_FIELDS
            or (expected_field is not None and source_field != expected_field)
            or isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or source_index < 0
            or (source_field == "ACTION" and source_index != 0)
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or not 0 <= start < end
        ):
            raise RepositoryUnavailableError("stored sourceSpan is invalid")
        source_digest = _digest_value(digest, "sourceTextDigest")
        if sources is not None:
            source = sources.get((scene_ref, source_field, source_index))
            if source is None or end > len(source.text):
                raise RepositoryUnavailableError("stored sourceSpan is unresolved")
            if source_digest != _text_digest(source.text[start:end]):
                raise RepositoryUnavailableError(
                    "stored sourceTextDigest is stale"
                )
        return deepcopy(dict(value))

    def _validate_payload(
        self,
        payload: Any,
        *,
        script_version: Mapping[str, Any] | None = None,
        m6_facts: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        value = _verify_sealed(payload, _PLAN_FIELDS, "ExecutionMethodPlanVersion")
        if value.get("schemaVersion") != EXECUTION_METHOD_PLAN_SCHEMA_VERSION:
            raise RepositoryUnavailableError("stored plan schemaVersion is invalid")
        for field in (
            "executionMethodPlanRef",
            "executionMethodPlanVersionRef",
            *_SCOPE_FIELDS,
            "productionRunRef",
            "consistencyValidationVersionRef",
            "scriptVersionRef",
        ):
            _required_ref(value.get(field), field)
        _positive_int(value.get("planningVersion"), "planningVersion")
        for field in (
            "consistencyValidationDigest",
            "scriptVersionDigest",
            "payloadDigest",
        ):
            _digest_value(value.get(field), field)
        scope = {field: value[field] for field in _SCOPE_FIELDS}
        run_ref = value["productionRunRef"]
        sources = _source_index(script_version) if script_version is not None else None
        allowed_refs: set[str] | None = None
        character_names: dict[str, str] | None = None
        if m6_facts is not None:
            allowed_refs, character_names = self._m6_refs(m6_facts)
        storyboard = _verify_sealed(
            value.get("storyboardVersion"), _STORYBOARD_FIELDS, "StoryboardVersion"
        )
        if (
            storyboard.get("schemaVersion") != STORYBOARD_SCHEMA_VERSION_V2
            or storyboard.get("storyboardVersion") != value["planningVersion"]
            or storyboard.get("productionRunRef") != run_ref
            or storyboard.get("consistencyValidationVersionRef")
            != value["consistencyValidationVersionRef"]
            or storyboard.get("consistencyValidationDigest")
            != value["consistencyValidationDigest"]
            or storyboard.get("scriptVersionRef") != value["scriptVersionRef"]
            or storyboard.get("scriptVersionDigest") != value["scriptVersionDigest"]
        ):
            raise RepositoryUnavailableError("stored StoryboardVersion lineage is invalid")
        self._validate_scope_fields(storyboard, scope, "StoryboardVersion")
        for field in ("storyboardRef", "storyboardVersionRef"):
            _required_ref(storyboard.get(field), field)
        shot_version_refs = storyboard.get("creativeShotVersionRefs")
        if (
            not isinstance(shot_version_refs, list)
            or not shot_version_refs
            or len(shot_version_refs) != len(set(shot_version_refs))
        ):
            raise RepositoryUnavailableError(
                "stored StoryboardVersion shot refs are invalid"
            )
        for ref in shot_version_refs:
            _required_ref(ref, "creativeShotVersionRef")
        raw_shots = value.get("creativeShotVersions")
        if not isinstance(raw_shots, list) or len(raw_shots) != len(shot_version_refs):
            raise RepositoryUnavailableError("stored CreativeShotVersions are invalid")
        creative_shots: list[dict[str, Any]] = []
        beat_index: dict[tuple[str, str], dict[str, Any]] = {}
        creative_by_ref: dict[str, dict[str, Any]] = {}
        plan_beat_refs: set[str] = set()
        deterministic_beats: set[tuple[str, str]] = set()
        for shot_order, raw_shot in enumerate(raw_shots, start=1):
            shot = _verify_sealed(
                raw_shot, _CREATIVE_SHOT_FIELDS, "CreativeShotVersion"
            )
            if (
                shot.get("schemaVersion") != CREATIVE_SHOT_SCHEMA_VERSION_V2
                or shot.get("creativeShotVersion") != value["planningVersion"]
                or shot.get("shotOrder") != shot_order
                or shot.get("productionRunRef") != run_ref
                or shot.get("storyboardRef") != storyboard["storyboardRef"]
                or shot.get("storyboardVersionRef")
                != storyboard["storyboardVersionRef"]
                or shot.get("storyboardVersionDigest")
                != storyboard["payloadDigest"]
                or shot.get("scriptVersionRef") != value["scriptVersionRef"]
                or shot.get("scriptVersionDigest") != value["scriptVersionDigest"]
                or shot.get("creativeShotVersionRef")
                != shot_version_refs[shot_order - 1]
            ):
                raise RepositoryUnavailableError(
                    "stored CreativeShotVersion lineage is invalid"
                )
            self._validate_scope_fields(shot, scope, "CreativeShotVersion")
            for field in ("creativeShotRef", "creativeShotVersionRef"):
                _required_ref(shot.get(field), field)
            frame_count = _positive_int(shot.get("shotFrameCount"), "shotFrameCount")
            camera = shot.get("cameraInstruction")
            if not isinstance(camera, Mapping) or set(camera) != _CAMERA_FIELDS:
                raise RepositoryUnavailableError(
                    "stored cameraInstruction fields are invalid"
                )
            _required_text(camera.get("framing"), "cameraInstruction.framing")
            _required_text(camera.get("movement"), "cameraInstruction.movement")
            scene_refs = shot.get("scriptSceneRefs")
            if (
                not isinstance(scene_refs, list)
                or not scene_refs
                or scene_refs != sorted(scene_refs)
                or len(scene_refs) != len(set(scene_refs))
            ):
                raise RepositoryUnavailableError("stored scriptSceneRefs are invalid")
            for ref in scene_refs:
                _required_ref(ref, "scriptSceneRef")
            raw_beats = shot.get("actionExecutionBeats")
            if not isinstance(raw_beats, list) or not raw_beats:
                raise RepositoryUnavailableError(
                    "stored actionExecutionBeats are invalid"
                )
            ranges_by_subject: dict[str, list[tuple[int, int]]] = {}
            resolved_scene_refs: set[str] = set()
            for beat_order, raw_beat in enumerate(raw_beats, start=1):
                if not isinstance(raw_beat, Mapping):
                    raise RepositoryUnavailableError("stored ActionExecutionBeat is invalid")
                execution_class = raw_beat.get("executionClass")
                beat_fields = set(_BEAT_FIELDS)
                if execution_class == "DETERMINISTIC_EVENT":
                    beat_fields.add("postprocessRequirementKey")
                beat = _verify_sealed(
                    raw_beat,
                    frozenset(beat_fields),
                    "ActionExecutionBeat",
                )
                if (
                    beat.get("schemaVersion") != ACTION_EXECUTION_BEAT_SCHEMA_VERSION
                    or beat.get("beatOrder") != beat_order
                    or execution_class not in EXECUTION_CLASSES
                ):
                    raise RepositoryUnavailableError(
                        "stored ActionExecutionBeat classification is invalid"
                    )
                beat_ref = _required_ref(beat.get("beatRef"), "beatRef")
                if beat_ref in plan_beat_refs:
                    raise RepositoryUnavailableError(
                        "stored ActionExecutionBeat identity is ambiguous"
                    )
                plan_beat_refs.add(beat_ref)
                if execution_class == "DETERMINISTIC_EVENT":
                    _required_ref(
                        beat.get("postprocessRequirementKey"),
                        "postprocessRequirementKey",
                    )
                    deterministic_beats.add(
                        (shot["creativeShotVersionRef"], beat_ref)
                    )
                subjects = beat.get("subjectRefs")
                targets = beat.get("targetRefs")
                if (
                    not isinstance(subjects, list)
                    or not subjects
                    or subjects != sorted(subjects)
                    or len(subjects) != len(set(subjects))
                    or not isinstance(targets, list)
                    or targets != sorted(targets)
                    or len(targets) != len(set(targets))
                ):
                    raise RepositoryUnavailableError(
                        "stored ActionExecutionBeat refs are invalid"
                    )
                for ref in (*subjects, *targets):
                    _required_ref(ref, "subjectOrTargetRef")
                    if allowed_refs is not None and ref not in allowed_refs:
                        raise RepositoryUnavailableError(
                            "stored ActionExecutionBeat M6 ref is stale"
                        )
                start = _nonnegative_int(
                    beat.get("frameRangeStartInclusive"),
                    "frameRangeStartInclusive",
                )
                end = _positive_int(
                    beat.get("frameRangeEndExclusive"),
                    "frameRangeEndExclusive",
                )
                if not start < end <= frame_count:
                    raise RepositoryUnavailableError(
                        "stored ActionExecutionBeat frame range is invalid"
                    )
                span = self._validate_stored_source_span(
                    beat.get("sourceSpan"),
                    beat.get("sourceTextDigest"),
                    sources=sources,
                )
                resolved_scene_refs.add(span["scriptSceneRef"])
                for subject in subjects:
                    ranges_by_subject.setdefault(subject, []).append((start, end))
                beat_index[(shot["creativeShotVersionRef"], beat_ref)] = beat
            if sorted(resolved_scene_refs) != scene_refs:
                raise RepositoryUnavailableError(
                    "stored CreativeShotVersion source scenes are invalid"
                )
            for ranges in ranges_by_subject.values():
                previous_end = -1
                for start, end in sorted(ranges):
                    if start < previous_end:
                        raise RepositoryUnavailableError(
                            "stored ActionExecutionBeats overlap"
                        )
                    previous_end = end
            coverage_end = 0
            for start, end in sorted(
                (
                    (
                        beat["frameRangeStartInclusive"],
                        beat["frameRangeEndExclusive"],
                    )
                    for beat in raw_beats
                )
            ):
                if start > coverage_end:
                    raise RepositoryUnavailableError(
                        "stored ActionExecutionBeat coverage is incomplete"
                    )
                coverage_end = max(coverage_end, end)
            if coverage_end != frame_count:
                raise RepositoryUnavailableError(
                    "stored ActionExecutionBeat coverage is incomplete"
                )
            creative_by_ref[shot["creativeShotVersionRef"]] = shot
            creative_shots.append(shot)
        raw_visual = value.get("visualExecutionRequirements")
        if not isinstance(raw_visual, list) or len(raw_visual) != len(beat_index):
            raise RepositoryUnavailableError(
                "stored VisualExecutionRequirements are invalid"
            )
        visual_keys: set[tuple[str, str]] = set()
        for order, raw_requirement in enumerate(raw_visual, start=1):
            requirement = _verify_sealed(
                raw_requirement,
                _VISUAL_REQUIREMENT_FIELDS,
                "VisualExecutionRequirement",
            )
            key = (
                requirement.get("creativeShotVersionRef"),
                requirement.get("beatRef"),
            )
            beat = beat_index.get(key)
            creative = creative_by_ref.get(str(key[0]))
            execution_class = beat.get("executionClass") if beat is not None else None
            if (
                requirement.get("schemaVersion")
                != VISUAL_EXECUTION_REQUIREMENT_SCHEMA_VERSION
                or requirement.get("requirementOrder") != order
                or requirement.get("productionRunRef") != run_ref
                or requirement.get("storyboardVersionRef")
                != storyboard["storyboardVersionRef"]
                or requirement.get("storyboardVersionDigest")
                != storyboard["payloadDigest"]
                or beat is None
                or creative is None
                or requirement.get("creativeShotVersionDigest")
                != creative["payloadDigest"]
                or requirement.get("beatDigest") != beat["payloadDigest"]
                or requirement.get("executionClass") != execution_class
                or requirement.get("executionMethod")
                != EXECUTION_METHOD_BY_CLASS.get(str(execution_class))
                or requirement.get("disposition")
                != VISUAL_DISPOSITION_BY_CLASS.get(str(execution_class))
                or key in visual_keys
            ):
                raise RepositoryUnavailableError(
                    "stored VisualExecutionRequirement lineage is invalid"
                )
            visual_keys.add(key)
            self._validate_scope_fields(
                requirement, scope, "VisualExecutionRequirement"
            )
            _required_ref(
                requirement.get("visualExecutionRequirementRef"),
                "visualExecutionRequirementRef",
            )
        if visual_keys != set(beat_index):
            raise RepositoryUnavailableError(
                "stored VisualExecutionRequirement coverage is invalid"
            )
        raw_audio = value.get("audioRequirements")
        if not isinstance(raw_audio, list):
            raise RepositoryUnavailableError("stored AudioRequirements are invalid")
        audio_refs: set[str] = set()
        for order, raw_requirement in enumerate(raw_audio, start=1):
            if not isinstance(raw_requirement, Mapping):
                raise RepositoryUnavailableError("stored AudioRequirement is invalid")
            audio_type = raw_requirement.get("audioType")
            fields = set(_AUDIO_REQUIREMENT_FIELDS)
            if audio_type in {"DIALOGUE", "NARRATION"}:
                fields.update({"sourceSpan", "sourceTextDigest"})
            if audio_type == "DIALOGUE":
                fields.add("speakerCharacterRef")
            requirement = _verify_sealed(
                raw_requirement, frozenset(fields), "AudioRequirement"
            )
            key = (
                requirement.get("creativeShotVersionRef"),
                requirement.get("beatRef"),
            )
            beat = beat_index.get(key)
            creative = creative_by_ref.get(str(key[0]))
            audio_ref = _required_ref(
                requirement.get("audioRequirementRef"), "audioRequirementRef"
            )
            if (
                requirement.get("schemaVersion") != AUDIO_REQUIREMENT_SCHEMA_VERSION
                or requirement.get("requirementOrder") != order
                or audio_type not in AUDIO_TYPES
                or requirement.get("disposition")
                != AUDIO_DISPOSITION_BY_TYPE.get(str(audio_type))
                or requirement.get("productionRunRef") != run_ref
                or requirement.get("scriptVersionRef") != value["scriptVersionRef"]
                or requirement.get("scriptVersionDigest")
                != value["scriptVersionDigest"]
                or requirement.get("storyboardVersionRef")
                != storyboard["storyboardVersionRef"]
                or requirement.get("storyboardVersionDigest")
                != storyboard["payloadDigest"]
                or beat is None
                or creative is None
                or requirement.get("creativeShotVersionDigest")
                != creative["payloadDigest"]
                or requirement.get("beatDigest") != beat["payloadDigest"]
                or audio_ref in audio_refs
            ):
                raise RepositoryUnavailableError(
                    "stored AudioRequirement lineage is invalid"
                )
            audio_refs.add(audio_ref)
            self._validate_scope_fields(requirement, scope, "AudioRequirement")
            timing = requirement.get("timingReference")
            if not isinstance(timing, Mapping) or set(timing) != _TIMING_FIELDS:
                raise RepositoryUnavailableError(
                    "stored AudioRequirement timing is invalid"
                )
            timing_start = _nonnegative_int(
                timing.get("startFrameInclusive"), "startFrameInclusive"
            )
            timing_end = _positive_int(
                timing.get("endFrameExclusive"), "endFrameExclusive"
            )
            if not timing_start < timing_end <= creative["shotFrameCount"]:
                raise RepositoryUnavailableError(
                    "stored AudioRequirement timing is outside its Shot"
                )
            if audio_type in {"DIALOGUE", "NARRATION"}:
                span = self._validate_stored_source_span(
                    requirement.get("sourceSpan"),
                    requirement.get("sourceTextDigest"),
                    sources=sources,
                    expected_field=(
                        "DIALOGUE" if audio_type == "DIALOGUE" else "NARRATION"
                    ),
                )
                if audio_type == "DIALOGUE":
                    speaker_ref = _required_ref(
                        requirement.get("speakerCharacterRef"),
                        "speakerCharacterRef",
                    )
                    if script_version is not None and character_names is not None:
                        speaker = self._dialogue_speaker(script_version, span)
                        if character_names.get(speaker) != speaker_ref:
                            raise RepositoryUnavailableError(
                                "stored AudioRequirement speaker is stale"
                            )
        raw_postprocess = value.get("postprocessRequirements")
        if not isinstance(raw_postprocess, list):
            raise RepositoryUnavailableError(
                "stored PostprocessRequirements are invalid"
            )
        postprocess_keys: set[tuple[str, str]] = set()
        for order, raw_requirement in enumerate(raw_postprocess, start=1):
            requirement = _verify_sealed(
                raw_requirement,
                _POSTPROCESS_REQUIREMENT_FIELDS,
                "PostprocessRequirement",
            )
            key = (
                requirement.get("creativeShotVersionRef"),
                requirement.get("beatRef"),
            )
            beat = beat_index.get(key)
            creative = creative_by_ref.get(str(key[0]))
            event_key = (
                beat.get("postprocessRequirementKey") if beat is not None else None
            )
            expected_base_key = (
                "event-free-base:"
                + sha256(str(event_key).encode("utf-8")).hexdigest()
            )
            if (
                requirement.get("schemaVersion")
                != POSTPROCESS_REQUIREMENT_SCHEMA_VERSION
                or requirement.get("requirementOrder") != order
                or requirement.get("productionRunRef") != run_ref
                or requirement.get("storyboardVersionRef")
                != storyboard["storyboardVersionRef"]
                or requirement.get("storyboardVersionDigest")
                != storyboard["payloadDigest"]
                or beat is None
                or creative is None
                or beat.get("executionClass") != "DETERMINISTIC_EVENT"
                or requirement.get("creativeShotVersionDigest")
                != creative["payloadDigest"]
                or requirement.get("beatDigest") != beat["payloadDigest"]
                or requirement.get("postprocessRequirementKey") != event_key
                or requirement.get("executionMethod")
                != "V3_DETERMINISTIC_COMPOSITION"
                or requirement.get("eventFreeBaseMediaRequirementKey")
                != expected_base_key
                or requirement.get("disposition")
                != "DERIVE_DETERMINISTIC_POSTPROCESS"
                or key in postprocess_keys
            ):
                raise RepositoryUnavailableError(
                    "stored PostprocessRequirement lineage is invalid"
                )
            for list_field in (
                "maskAssetRequirementKeys",
                "resourceAssetRequirementKeys",
                "staticAssetRequirementKeys",
            ):
                if requirement.get(list_field) != []:
                    raise RepositoryUnavailableError(
                        "stored PostprocessRequirement inputs are invalid"
                    )
            postprocess_keys.add(key)
            self._validate_scope_fields(
                requirement, scope, "PostprocessRequirement"
            )
            _required_ref(
                requirement.get("postprocessRequirementRef"),
                "postprocessRequirementRef",
            )
            _required_ref(
                requirement.get("eventFreeBaseMediaRequirementKey"),
                "eventFreeBaseMediaRequirementKey",
            )
        if postprocess_keys != deterministic_beats:
            raise RepositoryUnavailableError(
                "stored PostprocessRequirement coverage is invalid"
            )
        return value

    def _validated_records(
        self, workspace: str, run_ref: str
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        records = self.evidence_repository.list_records(
            workspace, run_ref, record_kind=EXECUTION_METHOD_PLAN_RECORD_KIND
        )
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        plan_ref: str | None = None
        storyboard_ref: str | None = None
        version_refs: set[str] = set()
        storyboard_version_refs: set[str] = set()
        for expected_version, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                raise RepositoryUnavailableError("stored M8/M9 evidence is invalid")
            payload = self._validate_payload(record.get("payload"))
            if (
                record.get("recordKind") != EXECUTION_METHOD_PLAN_RECORD_KIND
                or record.get("recordRef") != payload["executionMethodPlanRef"]
                or record.get("recordVersion") != payload["planningVersion"]
                or record.get("payloadDigest") != payload["payloadDigest"]
                or payload["planningVersion"] != expected_version
            ):
                raise RepositoryUnavailableError(
                    "stored M8/M9 evidence envelope is invalid"
                )
            current_plan_ref = payload["executionMethodPlanRef"]
            current_storyboard_ref = payload["storyboardVersion"]["storyboardRef"]
            plan_ref = plan_ref or current_plan_ref
            storyboard_ref = storyboard_ref or current_storyboard_ref
            if current_plan_ref != plan_ref or current_storyboard_ref != storyboard_ref:
                raise RepositoryUnavailableError(
                    "stored M8/M9 root identity is ambiguous"
                )
            version_ref = payload["executionMethodPlanVersionRef"]
            storyboard_version_ref = payload["storyboardVersion"][
                "storyboardVersionRef"
            ]
            if (
                version_ref in version_refs
                or storyboard_version_ref in storyboard_version_refs
            ):
                raise RepositoryUnavailableError(
                    "stored M8/M9 version identity is ambiguous"
                )
            version_refs.add(version_ref)
            storyboard_version_refs.add(storyboard_version_ref)
            result.append((deepcopy(dict(record)), payload))
        return result

    @staticmethod
    def _payload_matches_resolution(
        payload: Mapping[str, Any], resolution: Mapping[str, Any]
    ) -> bool:
        validation = resolution["validation"]
        script = resolution["scriptVersion"]
        return (
            payload.get("consistencyValidationVersionRef")
            == validation.get("consistencyValidationVersionRef")
            and payload.get("consistencyValidationDigest")
            == validation.get("payloadDigest")
            and payload.get("scriptVersionRef") == script.get("scriptVersionRef")
            and payload.get("scriptVersionDigest")
            == resolution.get("scriptVersionDigest")
        )

    def create_plan(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != _CREATE_FIELDS:
            raise EpisodeProductionError(
                "command fields do not match the M8/M9 planning contract"
            )
        scope = {
            field: _required_ref(command.get(field), field) for field in _SCOPE_FIELDS
        }
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        validation_ref = _required_ref(
            command.get("consistencyValidationVersionRef"),
            "consistencyValidationVersionRef",
        )
        key = _idempotency_key(command.get("idempotencyKey"))
        resolution = self._current_resolution(scope, run_ref, validation_ref)
        shots = self._normalize_shots(
            command.get("shots"),
            script_version=resolution["scriptVersion"],
            m6_facts=resolution["m6ApplicableFacts"],
        )
        request_digest = self._request_digest(scope, run_ref, resolution, shots)
        existing = self.evidence_repository.get_record_by_idempotency_key(
            scope["workspaceRef"], run_ref, key
        )
        records = self._validated_records(scope["workspaceRef"], run_ref)
        if existing is not None:
            if (
                existing.get("recordKind") != EXECUTION_METHOD_PLAN_RECORD_KIND
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError(
                    "M8/M9 plan idempotency content changed"
                )
            payload = self._validate_payload(
                existing.get("payload"),
                script_version=resolution["scriptVersion"],
                m6_facts=resolution["m6ApplicableFacts"],
            )
            current = (
                bool(records)
                and records[-1][1]["executionMethodPlanVersionRef"]
                == payload["executionMethodPlanVersionRef"]
                and self._payload_matches_resolution(payload, resolution)
            )
            return {
                **payload,
                "currentness": "CURRENT" if current else "STALE",
                "idempotentReplay": True,
            }
        journal_head = self.evidence_repository.record_journal_head(
            scope["workspaceRef"], run_ref
        )
        payload = self._build_payload(
            scope=scope,
            run_ref=run_ref,
            resolution=resolution,
            shots=shots,
            previous=records,
        )
        payload = self._validate_payload(
            payload,
            script_version=resolution["scriptVersion"],
            m6_facts=resolution["m6ApplicableFacts"],
        )
        record = EvidenceRecord(
            workspaceRef=scope["workspaceRef"],
            productionRunRef=run_ref,
            recordKind=EXECUTION_METHOD_PLAN_RECORD_KIND,
            recordRef=payload["executionMethodPlanRef"],
            recordVersion=payload["planningVersion"],
            idempotencyKey=key,
            requestDigest=request_digest,
            createdAt=self._clock(),
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        try:
            stored_records, replayed = self.evidence_repository.append_records(
                (record,), expected_record_journal_head=journal_head
            )
        except IdempotencyConflictError:
            concurrent = self.evidence_repository.get_record_by_idempotency_key(
                scope["workspaceRef"], run_ref, key
            )
            if (
                not isinstance(concurrent, Mapping)
                or concurrent.get("recordKind") != EXECUTION_METHOD_PLAN_RECORD_KIND
                or concurrent.get("requestDigest") != request_digest
            ):
                raise
            concurrent_payload = self._validate_payload(
                concurrent.get("payload"),
                script_version=resolution["scriptVersion"],
                m6_facts=resolution["m6ApplicableFacts"],
            )
            return {
                **concurrent_payload,
                "currentness": "CURRENT",
                "idempotentReplay": True,
            }
        stored = self._validate_payload(
            stored_records[0].get("payload"),
            script_version=resolution["scriptVersion"],
            m6_facts=resolution["m6ApplicableFacts"],
        )
        return {
            **stored,
            "currentness": "CURRENT",
            "idempotentReplay": replayed,
        }

    def get_plan(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        execution_method_plan_version_ref: str | None = None,
    ) -> dict[str, Any]:
        scope = {
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "projectRef": _required_ref(project_ref, "projectRef"),
            "seriesRef": _required_ref(series_ref, "seriesRef"),
            "episodeRef": _required_ref(episode_ref, "episodeRef"),
        }
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        self._run_for_scope(scope, run_ref)
        records = self._validated_records(scope["workspaceRef"], run_ref)
        selected = None
        if execution_method_plan_version_ref is None:
            selected = records[-1] if records else None
        else:
            version_ref = _required_ref(
                execution_method_plan_version_ref,
                "executionMethodPlanVersionRef",
            )
            selected = next(
                (
                    item
                    for item in records
                    if item[1]["executionMethodPlanVersionRef"] == version_ref
                ),
                None,
            )
        if selected is None:
            raise RecordNotFoundError("ExecutionMethodPlanVersion was not found")
        payload = selected[1]
        if any(payload.get(field) != value for field, value in scope.items()):
            raise RecordNotFoundError("ExecutionMethodPlanVersion was not found")
        current = False
        try:
            resolution = self._current_resolution(
                scope,
                run_ref,
                payload["consistencyValidationVersionRef"],
            )
            payload = self._validate_payload(
                payload,
                script_version=resolution["scriptVersion"],
                m6_facts=resolution["m6ApplicableFacts"],
            )
            current = (
                selected is records[-1]
                and self._payload_matches_resolution(payload, resolution)
            )
        except (
            ExecutionNotAuthorizedError,
            StaleInputError,
            RepositoryUnavailableError,
        ):
            current = False
        return {
            **payload,
            "currentness": "CURRENT" if current else "STALE",
            "idempotentReplay": False,
        }

    def require_current_plan(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        execution_method_plan_version_ref: str,
    ) -> dict[str, Any]:
        plan = self.get_plan(
            workspace_ref,
            project_ref,
            series_ref,
            episode_ref,
            production_run_ref,
            execution_method_plan_version_ref,
        )
        if plan["currentness"] != "CURRENT":
            raise ExecutionNotAuthorizedError(
                "current execution method plan is required"
            )
        return plan

    def resolve_current_audio_requirement(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        execution_method_plan_version_ref: str,
        audio_requirement_ref: str,
    ) -> dict[str, Any]:
        """Resolve one current M9 audio requirement and its authoritative text.

        The returned ``sourceText`` is present only for speech requirements and
        is sliced from the freshly re-read confirmed ScriptVersion.  Callers do
        not provide source text, speaker identity, timing or requirement
        digests to this boundary.
        """

        plan = self.require_current_plan(
            workspace_ref,
            project_ref,
            series_ref,
            episode_ref,
            production_run_ref,
            execution_method_plan_version_ref,
        )
        selected_ref = _required_ref(
            audio_requirement_ref, "audioRequirementRef"
        )
        requirement = next(
            (
                item
                for item in plan["audioRequirements"]
                if item["audioRequirementRef"] == selected_ref
            ),
            None,
        )
        if requirement is None:
            raise RecordNotFoundError("AudioRequirement was not found")

        source_text: str | None = None
        if requirement["audioType"] in {"DIALOGUE", "NARRATION"}:
            scope = {
                "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
                "projectRef": _required_ref(project_ref, "projectRef"),
                "seriesRef": _required_ref(series_ref, "seriesRef"),
                "episodeRef": _required_ref(episode_ref, "episodeRef"),
            }
            resolution = self._current_resolution(
                scope,
                _required_ref(production_run_ref, "productionRunRef"),
                plan["consistencyValidationVersionRef"],
            )
            sources = _source_index(resolution["scriptVersion"])
            span = self._validate_stored_source_span(
                requirement["sourceSpan"],
                requirement["sourceTextDigest"],
                sources=sources,
                expected_field=requirement["audioType"],
            )
            source = sources.get(
                (
                    span["scriptSceneRef"],
                    span["sourceField"],
                    span["sourceIndex"],
                )
            )
            if source is None:
                raise RepositoryUnavailableError(
                    "AudioRequirement source text is unavailable"
                )
            source_text = source.text[
                span["startOffsetInclusive"] : span["endOffsetExclusive"]
            ]
            if _text_digest(source_text) != requirement["sourceTextDigest"]:
                raise StaleInputError("AudioRequirement source text changed")

        return {
            "executionMethodPlan": deepcopy(dict(plan)),
            "audioRequirement": deepcopy(dict(requirement)),
            "sourceText": source_text,
        }
