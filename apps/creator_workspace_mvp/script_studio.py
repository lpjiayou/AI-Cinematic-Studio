"""Creator Application orchestration for provider-neutral Script Studio candidates."""

from __future__ import annotations

import json
from typing import Any, Mapping

from services.v4_platform import (
    ProviderTimeoutError,
    TextGenerationRequest,
    TextMessage,
    TextProvider,
    TextProviderError,
)


SCRIPT_CANDIDATE_SCHEMA_VERSION = "creator.script-studio.script-candidate.v1"
SCENE_REWRITE_SCHEMA_VERSION = "creator.script-studio.scene-rewrite.v1"


class ScriptGenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        diagnostic_category: str = "application_error",
        provider_status: int | None = None,
        exception_name: str = "ScriptGenerationError",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostic_category = diagnostic_category
        self.provider_status = provider_status
        self.exception_name = exception_name


class ScriptCandidateValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _required_text(value: Any, field: str, errors: list[str], *, limit: int = 6000) -> str:
    text = str(value or "").strip()
    if not text:
        errors.append(f"{field} is required")
    elif len(text) > limit:
        errors.append(f"{field} is too long")
    return text


def _string_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _required_text(item, f"{field}[{index}]", errors, limit=1000)
        if text:
            result.append(text)
    return result


def _number(value: Any, field: str, errors: list[str]) -> float:
    if isinstance(value, bool):
        errors.append(f"{field} must be a number")
        return 0
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a number")
        return 0
    if result <= 0 or result > 3600:
        errors.append(f"{field} is out of range")
    return round(result, 3)


def _target_duration(bootstrap: Mapping[str, Any]) -> float:
    storyboard = bootstrap.get("storyboardPlan")
    if not isinstance(storyboard, list) or not storyboard:
        raise ScriptCandidateValidationError(["bootstrap storyboardPlan is invalid"])
    try:
        result = sum(float(item["durationSec"]) for item in storyboard)
    except (KeyError, TypeError, ValueError) as exc:
        raise ScriptCandidateValidationError(["bootstrap duration is invalid"]) from exc
    if result <= 0:
        raise ScriptCandidateValidationError(["bootstrap duration is invalid"])
    return round(result, 3)


def _normalize_dialogue(value: Any, field: str, errors: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"speaker", "text", "emotion"}:
            errors.append(f"{field}[{index}] fields are invalid")
            continue
        result.append(
            {
                "speaker": _required_text(item.get("speaker"), f"{field}.speaker", errors, limit=120),
                "text": _required_text(item.get("text"), f"{field}.text", errors, limit=2000),
                "emotion": _required_text(item.get("emotion"), f"{field}.emotion", errors, limit=200),
            }
        )
    return result


def _normalize_scene(
    value: Any,
    *,
    index: int,
    errors: list[str],
    include_ref: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"scenes[{index}] must be an object")
        value = {}
    required = {
        "sceneNumber",
        "heading",
        "location",
        "timeOfDay",
        "characters",
        "action",
        "dialogue",
        "narration",
        "subtitleText",
        "estimatedDurationSec",
        "scenePurpose",
        "continuityNotes",
        "productionNotes",
    }
    allowed = required | ({"scriptSceneRef"} if include_ref else set())
    if set(value) != allowed:
        errors.append(f"scenes[{index}] fields are invalid")
    try:
        scene_number = int(value.get("sceneNumber"))
    except (TypeError, ValueError):
        scene_number = 0
    if scene_number != index + 1:
        errors.append("scene numbers must be continuous")
    scene = {
        "sceneNumber": scene_number,
        "heading": _required_text(value.get("heading"), "heading", errors, limit=300),
        "location": _required_text(value.get("location"), "location", errors, limit=300),
        "timeOfDay": _required_text(value.get("timeOfDay"), "timeOfDay", errors, limit=120),
        "characters": _string_list(value.get("characters"), "characters", errors),
        "action": _required_text(value.get("action"), "action", errors),
        "dialogue": _normalize_dialogue(value.get("dialogue"), "dialogue", errors),
        "narration": _string_list(value.get("narration"), "narration", errors),
        "subtitleText": _string_list(value.get("subtitleText"), "subtitleText", errors),
        "estimatedDurationSec": _number(value.get("estimatedDurationSec"), "estimatedDurationSec", errors),
        "scenePurpose": _required_text(value.get("scenePurpose"), "scenePurpose", errors, limit=1000),
        "continuityNotes": _string_list(value.get("continuityNotes"), "continuityNotes", errors),
        "productionNotes": _string_list(value.get("productionNotes"), "productionNotes", errors),
    }
    if include_ref:
        scene["scriptSceneRef"] = _required_text(
            value.get("scriptSceneRef"),
            "scriptSceneRef",
            errors,
            limit=200,
        )
    return scene


def validate_script_candidate(value: Any, bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, Mapping):
        raise ScriptCandidateValidationError(["provider output must be an object"])
    expected = {
        "schemaVersion",
        "title",
        "logline",
        "synopsis",
        "targetDurationSec",
        "scenes",
    }
    if set(value) != expected:
        errors.append("provider output fields are invalid")
    if value.get("schemaVersion") != SCRIPT_CANDIDATE_SCHEMA_VERSION:
        errors.append("schemaVersion is invalid")
    target = _number(value.get("targetDurationSec"), "targetDurationSec", errors)
    expected_target = _target_duration(bootstrap)
    if target and abs(target - expected_target) > 0.001:
        errors.append("targetDurationSec does not match Episode context")
    raw_scenes = value.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        errors.append("scenes must be a non-empty array")
        raw_scenes = []
    scenes = [
        _normalize_scene(item, index=index, errors=errors)
        for index, item in enumerate(raw_scenes)
    ]
    total = sum(scene["estimatedDurationSec"] for scene in scenes)
    if target and not target * 0.8 <= total <= target * 1.2:
        errors.append("scene duration total is inconsistent with target")
    result = {
        "title": _required_text(value.get("title"), "title", errors, limit=300),
        "logline": _required_text(value.get("logline"), "logline", errors, limit=1000),
        "synopsis": _required_text(value.get("synopsis"), "synopsis", errors),
        "targetDurationSec": target,
        "scenes": scenes,
    }
    if errors:
        raise ScriptCandidateValidationError(errors)
    return json.loads(json.dumps(result, ensure_ascii=False))


def validate_scene_rewrite(
    value: Any,
    *,
    source_scene: Mapping[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, Mapping) or set(value) != {"schemaVersion", "scene"}:
        raise ScriptCandidateValidationError(["scene rewrite fields are invalid"])
    if value.get("schemaVersion") != SCENE_REWRITE_SCHEMA_VERSION:
        errors.append("scene rewrite schemaVersion is invalid")
    scene_value = value.get("scene")
    if not isinstance(scene_value, Mapping):
        errors.append("scene is required")
        scene_value = {}
    scene = _normalize_scene(
        {key: item for key, item in scene_value.items() if key != "scriptSceneRef"},
        index=int(source_scene["sceneNumber"]) - 1,
        errors=errors,
    )
    scene["scriptSceneRef"] = source_scene["scriptSceneRef"]
    if scene["sceneNumber"] != source_scene["sceneNumber"]:
        errors.append("rewrite sceneNumber changed")
    if errors:
        raise ScriptCandidateValidationError(errors)
    return scene


def _generation_messages(bootstrap: Mapping[str, Any]) -> tuple[TextMessage, ...]:
    target = _target_duration(bootstrap)
    contract = {
        "schemaVersion": SCRIPT_CANDIDATE_SCHEMA_VERSION,
        "title": "string",
        "logline": "string",
        "synopsis": "string",
        "targetDurationSec": target,
        "scenes": [
            {
                "sceneNumber": 1,
                "heading": "string",
                "location": "string",
                "timeOfDay": "string",
                "characters": ["characterName"],
                "action": "string",
                "dialogue": [{"speaker": "string", "text": "string", "emotion": "string"}],
                "narration": ["string"],
                "subtitleText": ["string"],
                "estimatedDurationSec": target,
                "scenePurpose": "string",
                "continuityNotes": ["string"],
                "productionNotes": ["string"],
            }
        ],
    }
    return (
        TextMessage(
            "system",
            "You are the Script Studio writing engine. Return one JSON object only. "
            "Follow the supplied schema exactly. Preserve the confirmed plan, keep scene numbers continuous, "
            "use character names rather than invented IDs, and make scene duration totals reasonably match the target. "
            "Do not claim approval, rights clearance, storyboard production, or project lifecycle changes.",
        ),
        TextMessage(
            "user",
            json.dumps(
                {
                    "task": "Generate a production-usable short-form script candidate in Chinese.",
                    "requiredContract": contract,
                    "episodeContext": dict(bootstrap),
                },
                ensure_ascii=False,
            ),
        ),
    )


def _rewrite_messages(
    bootstrap: Mapping[str, Any],
    current_version: Mapping[str, Any],
    source_scene: Mapping[str, Any],
    instruction: str,
) -> tuple[TextMessage, ...]:
    return (
        TextMessage(
            "system",
            "Rewrite exactly one selected Script Studio scene. Return one JSON object only with schemaVersion "
            f"{SCENE_REWRITE_SCHEMA_VERSION} and a complete scene object. Preserve sceneNumber, Episode context, "
            "confirmed CreativePlan constraints, and characters. Do not rewrite other scenes or claim confirmation.",
        ),
        TextMessage(
            "user",
            json.dumps(
                {
                    "task": instruction,
                    "episodeContext": dict(bootstrap),
                    "scriptContext": {
                        "title": current_version.get("title"),
                        "logline": current_version.get("logline"),
                        "synopsis": current_version.get("synopsis"),
                        "targetDurationSec": current_version.get("targetDurationSec"),
                    },
                    "selectedScene": dict(source_scene),
                },
                ensure_ascii=False,
            ),
        ),
    )


class ScriptStudioApplicationService:
    """Call the accepted V4 provider port and return locally validated candidates."""

    def __init__(self, provider: TextProvider) -> None:
        self._provider = provider

    def generate(self, bootstrap: Mapping[str, Any]) -> dict[str, Any]:
        raw = self._call_provider(_generation_messages(bootstrap), max_tokens=8000)
        try:
            parsed = json.loads(raw)
            return validate_script_candidate(parsed, bootstrap)
        except (json.JSONDecodeError, TypeError, ScriptCandidateValidationError) as exc:
            raise ScriptGenerationError(
                "invalid_provider_output",
                diagnostic_category="provider_schema_error",
                exception_name=type(exc).__name__,
            ) from exc

    def rewrite_scene(
        self,
        *,
        bootstrap: Mapping[str, Any],
        current_version: Mapping[str, Any],
        script_scene_ref: str,
        instruction: str,
    ) -> dict[str, Any]:
        request_text = str(instruction or "").strip()
        if not request_text or len(request_text) > 1000:
            raise ScriptCandidateValidationError(["rewrite instruction is invalid"])
        scenes = current_version.get("scenes")
        if not isinstance(scenes, list):
            raise ScriptCandidateValidationError(["current ScriptVersion scenes are invalid"])
        selected = next(
            (item for item in scenes if item.get("scriptSceneRef") == script_scene_ref),
            None,
        )
        if selected is None:
            raise ScriptCandidateValidationError(["selected Scene was not found"])
        raw = self._call_provider(
            _rewrite_messages(bootstrap, current_version, selected, request_text),
            max_tokens=3500,
        )
        try:
            parsed = json.loads(raw)
            rewritten = validate_scene_rewrite(parsed, source_scene=selected)
        except (json.JSONDecodeError, TypeError, ScriptCandidateValidationError) as exc:
            raise ScriptGenerationError(
                "invalid_provider_output",
                diagnostic_category="provider_schema_error",
                exception_name=type(exc).__name__,
            ) from exc
        content = {
            "title": current_version["title"],
            "logline": current_version["logline"],
            "synopsis": current_version["synopsis"],
            "targetDurationSec": current_version["targetDurationSec"],
            "scenes": [
                rewritten if item["scriptSceneRef"] == script_scene_ref else json.loads(json.dumps(item, ensure_ascii=False))
                for item in scenes
            ],
        }
        return content

    def _call_provider(
        self,
        messages: tuple[TextMessage, ...],
        *,
        max_tokens: int,
    ) -> str:
        try:
            return self._provider.generate(
                TextGenerationRequest(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.35,
                    timeout_seconds=45,
                )
            )
        except ProviderTimeoutError as exc:
            raise ScriptGenerationError(
                "provider_timeout",
                diagnostic_category=exc.category,
                provider_status=exc.status,
                exception_name=type(exc).__name__,
            ) from exc
        except TextProviderError as exc:
            raise ScriptGenerationError(
                "provider_unavailable",
                diagnostic_category=exc.category,
                provider_status=exc.status,
                exception_name=type(exc).__name__,
            ) from exc
