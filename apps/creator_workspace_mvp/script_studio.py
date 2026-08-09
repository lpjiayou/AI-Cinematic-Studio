"""Creator Application orchestration for provider-neutral Script Studio candidates."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
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
SCRIPT_DURATION_MIN_RATIO = 0.8
SCRIPT_DURATION_MAX_RATIO = 1.2


@dataclass(frozen=True)
class ScriptCandidateValidationIssue:
    field: str
    rule: str
    category: str = "provider_schema_error"

    def message(self) -> str:
        return f"{self.field}: {self.rule}"


class ScriptGenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        diagnostic_category: str = "application_error",
        provider_status: int | None = None,
        exception_name: str = "ScriptGenerationError",
        validation_issues: tuple[tuple[str, str, str, str], ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostic_category = diagnostic_category
        self.provider_status = provider_status
        self.exception_name = exception_name
        self.validation_issues = validation_issues


class ScriptCandidateValidationError(ValueError):
    def __init__(self, issues: list[ScriptCandidateValidationIssue]) -> None:
        super().__init__("; ".join(issue.message() for issue in issues))
        self.issues = tuple(issues)
        self.errors = [issue.message() for issue in issues]


def _issue(
    issues: list[ScriptCandidateValidationIssue],
    field: str,
    rule: str,
    *,
    category: str = "provider_schema_error",
) -> None:
    issues.append(ScriptCandidateValidationIssue(field, rule, category))


def _log_validation_issues(
    issues: tuple[ScriptCandidateValidationIssue, ...],
    *,
    attempt: str,
) -> None:
    for issue in issues:
        print(
            "SCRIPT_STUDIO_SCHEMA_ERROR "
            f"attempt={attempt} "
            f"field={issue.field} "
            f"rule={issue.rule} "
            f"category={issue.category}",
            file=sys.stderr,
            flush=True,
        )


def _required_text(
    value: Any,
    field: str,
    issues: list[ScriptCandidateValidationIssue],
    *,
    limit: int = 6000,
) -> str:
    if value is None:
        _issue(issues, field, "required_field")
        return ""
    if not isinstance(value, str):
        _issue(issues, field, "invalid_type")
        return ""
    text = value.strip()
    if not text:
        _issue(issues, field, "required_field")
    elif len(text) > limit:
        _issue(issues, field, "max_length")
    return text


def _string_list(
    value: Any,
    field: str,
    issues: list[ScriptCandidateValidationIssue],
) -> list[str]:
    if value is None:
        _issue(issues, field, "required_field")
        return []
    if not isinstance(value, list):
        _issue(issues, field, "invalid_type")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        text = _required_text(item, f"{field}[{index}]", issues, limit=1000)
        if text:
            result.append(text)
    return result


def _number(
    value: Any,
    field: str,
    issues: list[ScriptCandidateValidationIssue],
) -> float:
    if value is None:
        _issue(issues, field, "required_field")
        return 0
    if isinstance(value, bool):
        _issue(issues, field, "invalid_type")
        return 0
    try:
        result = float(value)
    except (TypeError, ValueError):
        _issue(issues, field, "invalid_type")
        return 0
    if result <= 0 or result > 3600:
        _issue(issues, field, "out_of_range")
    return round(result, 3)


def _target_duration(bootstrap: Mapping[str, Any]) -> float:
    storyboard = bootstrap.get("storyboardPlan")
    if not isinstance(storyboard, list) or not storyboard:
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("bootstrap.storyboardPlan", "invalid_type", "application_contract_error")
        ])
    try:
        result = sum(float(item["durationSec"]) for item in storyboard)
    except (KeyError, TypeError, ValueError) as exc:
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("bootstrap.storyboardPlan.durationSec", "invalid_type", "application_contract_error")
        ]) from exc
    if result <= 0:
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("bootstrap.storyboardPlan.durationSec", "out_of_range", "application_contract_error")
        ])
    return round(result, 3)


def _normalize_dialogue(
    value: Any,
    field: str,
    issues: list[ScriptCandidateValidationIssue],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        _issue(issues, field, "invalid_type")
        return []
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {"speaker", "text", "emotion"}:
            _issue(issues, f"{field}[{index}]", "invalid_fields")
            continue
        result.append(
            {
                "speaker": _required_text(item.get("speaker"), f"{field}[{index}].speaker", issues, limit=120),
                "text": _required_text(item.get("text"), f"{field}[{index}].text", issues, limit=2000),
                "emotion": _required_text(item.get("emotion"), f"{field}[{index}].emotion", issues, limit=200),
            }
        )
    return result


def _normalize_scene(
    value: Any,
    *,
    index: int,
    issues: list[ScriptCandidateValidationIssue],
    include_ref: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _issue(issues, f"scenes[{index}]", "invalid_type")
        value = {}
    required = {
        "sceneNumber",
        "heading",
        "location",
        "timeOfDay",
        "characters",
        "action",
        "estimatedDurationSec",
        "scenePurpose",
    }
    optional_arrays = {"dialogue", "narration", "subtitleText", "continuityNotes", "productionNotes"}
    allowed = required | optional_arrays | ({"scriptSceneRef"} if include_ref else set())
    for field in sorted(set(value) - allowed):
        _issue(issues, f"scenes[{index}].{field}", "unsupported_field")
    raw_scene_number = value.get("sceneNumber")
    try:
        scene_number = int(raw_scene_number)
    except (TypeError, ValueError):
        scene_number = 0
    if raw_scene_number is None:
        _issue(issues, f"scenes[{index}].sceneNumber", "required_field")
    elif scene_number == 0:
        _issue(issues, f"scenes[{index}].sceneNumber", "invalid_type")
    elif scene_number != index + 1:
        _issue(issues, f"scenes[{index}].sceneNumber", "non_continuous")
    scene = {
        "sceneNumber": scene_number,
        "heading": _required_text(value.get("heading"), f"scenes[{index}].heading", issues, limit=300),
        "location": _required_text(value.get("location"), f"scenes[{index}].location", issues, limit=300),
        "timeOfDay": _required_text(value.get("timeOfDay"), f"scenes[{index}].timeOfDay", issues, limit=120),
        "characters": _string_list(value.get("characters"), f"scenes[{index}].characters", issues),
        "action": _required_text(value.get("action"), f"scenes[{index}].action", issues),
        "dialogue": _normalize_dialogue(value.get("dialogue", []), f"scenes[{index}].dialogue", issues),
        "narration": _string_list(value.get("narration", []), f"scenes[{index}].narration", issues),
        "subtitleText": _string_list(value.get("subtitleText", []), f"scenes[{index}].subtitleText", issues),
        "estimatedDurationSec": _number(value.get("estimatedDurationSec"), f"scenes[{index}].estimatedDurationSec", issues),
        "scenePurpose": _required_text(value.get("scenePurpose"), f"scenes[{index}].scenePurpose", issues, limit=1000),
        "continuityNotes": _string_list(value.get("continuityNotes", []), f"scenes[{index}].continuityNotes", issues),
        "productionNotes": _string_list(value.get("productionNotes", []), f"scenes[{index}].productionNotes", issues),
    }
    if include_ref:
        scene["scriptSceneRef"] = _required_text(
            value.get("scriptSceneRef"),
            f"scenes[{index}].scriptSceneRef",
            issues,
            limit=200,
        )
    return scene


def validate_script_candidate(value: Any, bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    issues: list[ScriptCandidateValidationIssue] = []
    if not isinstance(value, Mapping):
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("$", "invalid_type")
        ])
    expected = {
        "schemaVersion",
        "title",
        "logline",
        "synopsis",
        "targetDurationSec",
        "scenes",
    }
    for field in sorted(set(value) - expected):
        _issue(issues, field, "unsupported_field")
    if value.get("schemaVersion") is None:
        _issue(issues, "schemaVersion", "required_field")
    elif value.get("schemaVersion") != SCRIPT_CANDIDATE_SCHEMA_VERSION:
        _issue(issues, "schemaVersion", "invalid_value")
    target = _number(value.get("targetDurationSec"), "targetDurationSec", issues)
    expected_target = _target_duration(bootstrap)
    if target and abs(target - expected_target) > 0.001:
        _issue(issues, "targetDurationSec", "episode_target_mismatch")
    raw_scenes = value.get("scenes")
    if raw_scenes is None:
        _issue(issues, "scenes", "required_field")
        raw_scenes = []
    elif not isinstance(raw_scenes, list):
        _issue(issues, "scenes", "invalid_type")
        raw_scenes = []
    elif not raw_scenes:
        _issue(issues, "scenes", "non_empty_array")
        raw_scenes = []
    scenes = [
        _normalize_scene(item, index=index, issues=issues)
        for index, item in enumerate(raw_scenes)
    ]
    total = sum(scene["estimatedDurationSec"] for scene in scenes)
    if target and not target * SCRIPT_DURATION_MIN_RATIO <= total <= target * SCRIPT_DURATION_MAX_RATIO:
        _issue(issues, "scenes[].estimatedDurationSec", "duration_total_out_of_tolerance")
    result = {
        "title": _required_text(value.get("title"), "title", issues, limit=300),
        "logline": _required_text(value.get("logline"), "logline", issues, limit=1000),
        "synopsis": _required_text(value.get("synopsis"), "synopsis", issues),
        "targetDurationSec": target,
        "scenes": scenes,
    }
    if issues:
        raise ScriptCandidateValidationError(issues)
    return json.loads(json.dumps(result, ensure_ascii=False))


def validate_scene_rewrite(
    value: Any,
    *,
    source_scene: Mapping[str, Any],
) -> dict[str, Any]:
    issues: list[ScriptCandidateValidationIssue] = []
    if not isinstance(value, Mapping) or set(value) != {"schemaVersion", "scene"}:
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("$", "invalid_fields")
        ])
    if value.get("schemaVersion") != SCENE_REWRITE_SCHEMA_VERSION:
        _issue(issues, "schemaVersion", "invalid_value")
    scene_value = value.get("scene")
    if not isinstance(scene_value, Mapping):
        _issue(issues, "scene", "required_field")
        scene_value = {}
    scene = _normalize_scene(
        {key: item for key, item in scene_value.items() if key != "scriptSceneRef"},
        index=int(source_scene["sceneNumber"]) - 1,
        issues=issues,
    )
    scene["scriptSceneRef"] = source_scene["scriptSceneRef"]
    if scene["sceneNumber"] != source_scene["sceneNumber"]:
        _issue(issues, "scene.sceneNumber", "changed_authoritative_structure")
    if issues:
        raise ScriptCandidateValidationError(issues)
    return scene


def _candidate_contract(bootstrap: Mapping[str, Any]) -> dict[str, Any]:
    target = _target_duration(bootstrap)
    output_object = {
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
    return {
        "outputObject": output_object,
        "rules": {
            "requiredTopLevelFields": [
                "schemaVersion",
                "title",
                "logline",
                "synopsis",
                "targetDurationSec",
                "scenes",
            ],
            "requiredSceneFields": [
                "sceneNumber",
                "heading",
                "location",
                "timeOfDay",
                "characters",
                "action",
                "estimatedDurationSec",
                "scenePurpose",
            ],
            "optionalSceneArraysDefaultToEmpty": [
                "dialogue",
                "narration",
                "subtitleText",
                "continuityNotes",
                "productionNotes",
            ],
            "duration": {
                "targetDurationSecMustEqual": target,
                "sceneDurationTotalMin": round(target * SCRIPT_DURATION_MIN_RATIO, 3),
                "sceneDurationTotalMax": round(target * SCRIPT_DURATION_MAX_RATIO, 3),
            },
            "systemOwnedFieldsMustNotAppear": [
                "scriptRef",
                "scriptVersionRef",
                "scriptSceneRef",
            ],
        },
    }


def _generation_messages(bootstrap: Mapping[str, Any]) -> tuple[TextMessage, ...]:
    contract = _candidate_contract(bootstrap)
    return (
        TextMessage(
            "system",
            "You are the Script Studio writing engine. Return one JSON object only. "
            "Follow the supplied schema exactly. Preserve the confirmed plan, keep scene numbers continuous, "
            "use character names rather than invented IDs, and obey the explicit duration bounds. "
            "Do not return scriptRef, scriptVersionRef, or scriptSceneRef; the local system owns those references. "
            "Optional scene arrays may be omitted only when empty; do not omit required semantic fields. "
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


def _repair_messages(
    bootstrap: Mapping[str, Any],
    invalid_candidate: Any,
    issues: tuple[ScriptCandidateValidationIssue, ...],
) -> tuple[TextMessage, ...]:
    repair_input: dict[str, Any] = {
        "task": "Repair the Script Studio candidate once. Return a complete corrected JSON object only.",
        "requiredContract": _candidate_contract(bootstrap),
        "episodeContext": dict(bootstrap),
        "validationIssues": [
            {"field": issue.field, "rule": issue.rule}
            for issue in issues
        ],
    }
    if isinstance(invalid_candidate, Mapping):
        repair_input["invalidCandidate"] = dict(invalid_candidate)
    else:
        repair_input["invalidCandidate"] = "UNPARSEABLE_JSON_REGENERATE_FROM_CONTEXT"
    return (
        TextMessage(
            "system",
            "Perform exactly one schema repair for a Script Studio candidate. Return one JSON object only. "
            "Do not add system-owned references. Do not invent missing required semantic content; regenerate it "
            "from the confirmed Episode context. Obey every required field and duration rule.",
        ),
        TextMessage("user", json.dumps(repair_input, ensure_ascii=False)),
    )


def _parse_script_candidate(raw: str, bootstrap: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ScriptCandidateValidationError([
            ScriptCandidateValidationIssue("$", "invalid_json")
        ]) from exc
    return parsed, validate_script_candidate(parsed, bootstrap)


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
        first_error: ScriptCandidateValidationError | None = None
        try:
            _, result = _parse_script_candidate(raw, bootstrap)
            return result
        except ScriptCandidateValidationError as exc:
            first_error = exc
            _log_validation_issues(exc.issues, attempt="initial")
        assert first_error is not None
        try:
            parsed: Any
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            repaired_raw = self._call_provider(
                _repair_messages(bootstrap, parsed, first_error.issues),
                max_tokens=8000,
            )
            _, result = _parse_script_candidate(repaired_raw, bootstrap)
            return result
        except ScriptCandidateValidationError as repair_error:
            _log_validation_issues(repair_error.issues, attempt="repair")
            diagnostics = tuple(
                (attempt, issue.field, issue.rule, issue.category)
                for attempt, error in (("initial", first_error), ("repair", repair_error))
                for issue in error.issues
            )
            raise ScriptGenerationError(
                "invalid_provider_output",
                diagnostic_category="provider_schema_error",
                exception_name=type(repair_error).__name__,
                validation_issues=diagnostics,
            ) from repair_error

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
            raise ScriptCandidateValidationError([
                ScriptCandidateValidationIssue("instruction", "invalid_value", "application_contract_error")
            ])
        scenes = current_version.get("scenes")
        if not isinstance(scenes, list):
            raise ScriptCandidateValidationError([
                ScriptCandidateValidationIssue("currentVersion.scenes", "invalid_type", "application_contract_error")
            ])
        selected = next(
            (item for item in scenes if item.get("scriptSceneRef") == script_scene_ref),
            None,
        )
        if selected is None:
            raise ScriptCandidateValidationError([
                ScriptCandidateValidationIssue("scriptSceneRef", "not_found", "application_contract_error")
            ])
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
