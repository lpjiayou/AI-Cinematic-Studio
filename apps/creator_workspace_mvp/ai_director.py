"""AI Director candidate-plan capability for the Creator application."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping

from services.v4_platform import (
    ProviderTimeoutError,
    TextGenerationRequest,
    TextMessage,
    TextProvider,
    TextProviderError,
)


AI_DIRECTOR_SCHEMA_VERSION = "creator.ai-director.plan.v1"
PROJECT_DRAFT_INPUT_SCHEMA_VERSION = "creator.project-draft-input.v1"


class BriefValidationError(ValueError):
    def __init__(self, field_errors: Mapping[str, str]) -> None:
        super().__init__("creative brief is invalid")
        self.field_errors = dict(field_errors)


class PlanValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("candidate plan is invalid")
        self.errors = tuple(errors)


class PlanGenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        diagnostic_category: str = "internal_adapter_error",
        provider_status: int | None = None,
        exception_name: str = "PlanGenerationError",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostic_category = diagnostic_category
        self.provider_status = provider_status
        self.exception_name = exception_name


class ProjectDraftInputError(ValueError):
    """The candidate plan is not eligible for a session-only project draft."""


@dataclass(frozen=True)
class CreativeBrief:
    topic: str
    theme: str
    audience: str
    duration_seconds: float
    platform: str
    style: str
    character: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CreativeBrief":
        if not isinstance(value, Mapping):
            raise BriefValidationError({"brief": "请输入完整创意简报"})
        errors: dict[str, str] = {}

        def required_text(key: str) -> str:
            raw = value.get(key, "")
            text = str(raw).strip() if raw is not None else ""
            if not text:
                errors[key] = "此项为必填"
            elif len(text) > 500:
                errors[key] = "内容过长"
            return text

        topic = required_text("topic")
        theme = required_text("theme")
        audience = required_text("audience")
        platform = required_text("platform")
        style = required_text("style")
        character = str(value.get("character", "") or "").strip()
        if len(character) > 500:
            errors["character"] = "内容过长"

        duration_text = str(value.get("duration", "") or "").strip()
        duration_match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(?:s|sec|seconds?|秒)?",
            duration_text,
            flags=re.IGNORECASE,
        )
        duration_seconds = float(duration_match.group(1)) if duration_match else 0.0
        if not duration_match or duration_seconds <= 0 or duration_seconds > 3600:
            errors["duration"] = "请输入 1–3600 秒的合理时长"
        if errors:
            raise BriefValidationError(errors)
        return cls(
            topic=topic,
            theme=theme,
            audience=audience,
            duration_seconds=duration_seconds,
            platform=platform,
            style=style,
            character=character,
        )

    def as_prompt_payload(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "theme": self.theme,
            "audience": self.audience,
            "durationSec": self.duration_seconds,
            "platform": self.platform,
            "style": self.style,
            "character": self.character,
        }


_PLAN_EXAMPLE = {
    "schemaVersion": AI_DIRECTOR_SCHEMA_VERSION,
    "creativeInterpretation": {
        "logline": "一句话故事",
        "coreTheme": "核心主题",
        "targetEmotion": "目标情绪",
        "narrativeArc": "叙事弧线",
    },
    "storyDirection": {
        "title": "片名候选",
        "synopsis": "故事梗概",
        "keyBeats": ["节拍一", "节拍二"],
    },
    "scriptDraft": {
        "opening": "开场",
        "development": "发展",
        "climax": "高潮",
        "ending": "结尾",
        "captionsOrDialogue": ["字幕或对白"],
    },
    "storyboardPlan": [
        {
            "shotNo": 1,
            "durationSec": 5,
            "shotSize": "中景",
            "cameraMovement": "固定",
            "visualDescription": "画面描述",
            "narrativePurpose": "叙事目的",
        }
    ],
    "visualStyle": {
        "lighting": "光线",
        "palette": "色彩",
        "composition": "构图",
        "atmosphere": "氛围",
        "continuityRules": ["连续性规则"],
    },
    "productionPlan": {
        "shotCount": 1,
        "characters": ["角色"],
        "scenes": ["场景"],
        "visualAssets": ["视觉资产"],
        "audioNeeds": ["声音需求"],
        "productionNotes": ["制作备注"],
    },
}


SYSTEM_PROMPT = f"""你是影视创作导演规划器，不是项目控制系统。
根据 Creative Brief 生成候选创意方案，包括故事方向、剧本草案、分镜规划、视觉风格和制作规划。
尊重目标时长、发布平台、角色设定和视觉连续性。
只输出一个合法 JSON object，严格匹配 schemaVersion {AI_DIRECTOR_SCHEMA_VERSION} 和给定 JSON 示例结构。
不得声称真实素材已经生成，不得声称 Rights 已通过，不得声称 Approval 已完成，不得创建任何系统 ID，
不得控制项目生命周期，不得指示系统直接发布、导出、渲染或进入生产。
JSON 示例：{json.dumps(_PLAN_EXAMPLE, ensure_ascii=False)}"""


def _build_messages(
    brief: CreativeBrief,
    *,
    invalid_output: str | None = None,
    validation_errors: tuple[str, ...] = (),
) -> tuple[TextMessage, ...]:
    brief_json = json.dumps(brief.as_prompt_payload(), ensure_ascii=False)
    if invalid_output is None:
        user_content = f"Creative Brief JSON：{brief_json}\n请生成严格 JSON 候选导演方案。"
    else:
        error_json = json.dumps(list(validation_errors), ensure_ascii=False)
        user_content = (
            f"Creative Brief JSON：{brief_json}\n"
            f"上一次 JSON 未通过本地验证：{error_json}\n"
            f"上一次输出：{invalid_output[:100_000]}\n"
            "只修复结构与约束，返回完整严格 JSON。"
        )
    return (
        TextMessage(role="system", content=SYSTEM_PROMPT),
        TextMessage(role="user", content=user_content),
    )


_TOP_LEVEL_KEYS = {
    "schemaVersion",
    "creativeInterpretation",
    "storyDirection",
    "scriptDraft",
    "storyboardPlan",
    "visualStyle",
    "productionPlan",
}
_FORBIDDEN_KEYS = {
    "projectid",
    "assetid",
    "shotgraph",
    "approval",
    "rights",
    "publication",
    "publish",
    "domainid",
}
_FORBIDDEN_INSTRUCTIONS = (
    "直接发布",
    "自动发布",
    "立即发布",
    "publish directly",
    "publish immediately",
)


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalized_key(key) in _FORBIDDEN_KEYS:
                errors.append(f"{path}.{key} is authoritative and forbidden")
            _scan_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        if any(item in lowered for item in _FORBIDDEN_INSTRUCTIONS):
            errors.append(f"{path} contains direct publication instruction")


def _require_object(
    value: Any,
    path: str,
    required_keys: set[str],
    errors: list[str],
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    actual_keys = set(value.keys())
    if actual_keys != required_keys:
        errors.append(f"{path} fields do not match contract")
    return value


def _require_text(value: Any, path: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be non-empty text")
        return ""
    if len(value) > 10_000:
        errors.append(f"{path} exceeds text limit")
    return value.strip()


def _require_text_array(value: Any, path: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    if len(value) > 100:
        errors.append(f"{path} exceeds item limit")
    return [_require_text(item, f"{path}[{index}]", errors) for index, item in enumerate(value)]


def validate_plan(value: Any, brief: CreativeBrief) -> dict[str, Any]:
    """Validate and detach the provider result before it can reach the UI."""

    errors: list[str] = []
    _scan_forbidden(value, "$", errors)
    plan = _require_object(value, "$", _TOP_LEVEL_KEYS, errors)
    if plan.get("schemaVersion") != AI_DIRECTOR_SCHEMA_VERSION:
        errors.append("schemaVersion is invalid")

    creative = _require_object(
        plan.get("creativeInterpretation"),
        "creativeInterpretation",
        {"logline", "coreTheme", "targetEmotion", "narrativeArc"},
        errors,
    )
    for key in ("logline", "coreTheme", "targetEmotion", "narrativeArc"):
        _require_text(creative.get(key), f"creativeInterpretation.{key}", errors)

    story = _require_object(
        plan.get("storyDirection"),
        "storyDirection",
        {"title", "synopsis", "keyBeats"},
        errors,
    )
    _require_text(story.get("title"), "storyDirection.title", errors)
    _require_text(story.get("synopsis"), "storyDirection.synopsis", errors)
    _require_text_array(story.get("keyBeats"), "storyDirection.keyBeats", errors)

    script = _require_object(
        plan.get("scriptDraft"),
        "scriptDraft",
        {"opening", "development", "climax", "ending", "captionsOrDialogue"},
        errors,
    )
    for key in ("opening", "development", "climax", "ending"):
        _require_text(script.get(key), f"scriptDraft.{key}", errors)
    _require_text_array(
        script.get("captionsOrDialogue"),
        "scriptDraft.captionsOrDialogue",
        errors,
    )

    storyboard = plan.get("storyboardPlan")
    if not isinstance(storyboard, list) or not storyboard:
        errors.append("storyboardPlan must be a non-empty array")
        storyboard = []
    if len(storyboard) > 100:
        errors.append("storyboardPlan exceeds item limit")
    total_duration = 0.0
    shot_keys = {
        "shotNo",
        "durationSec",
        "shotSize",
        "cameraMovement",
        "visualDescription",
        "narrativePurpose",
    }
    for index, item in enumerate(storyboard, start=1):
        shot = _require_object(item, f"storyboardPlan[{index - 1}]", shot_keys, errors)
        if shot.get("shotNo") != index:
            errors.append("storyboard shotNo must be contiguous from 1")
        duration = shot.get("durationSec")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            errors.append(f"storyboardPlan[{index - 1}].durationSec must be positive")
        else:
            total_duration += float(duration)
        for key in ("shotSize", "cameraMovement", "visualDescription", "narrativePurpose"):
            _require_text(shot.get(key), f"storyboardPlan[{index - 1}].{key}", errors)

    tolerance = max(2.0, brief.duration_seconds * 0.15)
    if abs(total_duration - brief.duration_seconds) > tolerance:
        errors.append("storyboard duration does not reasonably match the brief")

    visual = _require_object(
        plan.get("visualStyle"),
        "visualStyle",
        {"lighting", "palette", "composition", "atmosphere", "continuityRules"},
        errors,
    )
    for key in ("lighting", "palette", "composition", "atmosphere"):
        _require_text(visual.get(key), f"visualStyle.{key}", errors)
    _require_text_array(visual.get("continuityRules"), "visualStyle.continuityRules", errors)

    production = _require_object(
        plan.get("productionPlan"),
        "productionPlan",
        {"shotCount", "characters", "scenes", "visualAssets", "audioNeeds", "productionNotes"},
        errors,
    )
    shot_count = production.get("shotCount")
    if isinstance(shot_count, bool) or not isinstance(shot_count, int):
        errors.append("productionPlan.shotCount must be an integer")
    elif shot_count != len(storyboard):
        errors.append("productionPlan.shotCount must match storyboardPlan")
    for key in ("characters", "scenes", "visualAssets", "audioNeeds", "productionNotes"):
        _require_text_array(production.get(key), f"productionPlan.{key}", errors)

    if errors:
        raise PlanValidationError(errors)
    return json.loads(json.dumps(plan, ensure_ascii=False))


def build_session_project_draft_input(
    plan_value: Any,
    brief_value: Mapping[str, Any],
    *,
    plan_version: int,
    project_ref: str,
    confirmed: bool,
) -> dict[str, Any]:
    """Map one confirmed candidate plan into a structured session-only draft input."""

    if not confirmed:
        raise ProjectDraftInputError("human confirmation is required")
    if not isinstance(plan_version, int) or isinstance(plan_version, bool) or plan_version < 1:
        raise ProjectDraftInputError("plan version is invalid")
    if not isinstance(project_ref, str) or not project_ref.startswith("local-"):
        raise ProjectDraftInputError("projectRef must be a local UI navigation reference")

    brief = CreativeBrief.from_mapping(brief_value)
    plan = validate_plan(plan_value, brief)
    production = plan["productionPlan"]
    return {
        "schemaVersion": PROJECT_DRAFT_INPUT_SCHEMA_VERSION,
        "localKey": project_ref,
        "projectRef": project_ref,
        "sourcePlanRef": f"local-ai-director-plan-{plan_version}",
        "sourcePlanSchemaVersion": plan["schemaVersion"],
        "sourcePlanVersion": plan_version,
        "sourcePlan": plan,
        "persistence": "session-only",
        "domainFact": False,
        "story": {
            "creativeInterpretation": plan["creativeInterpretation"],
            "direction": plan["storyDirection"],
            "script": plan["scriptDraft"],
        },
        "characters": production["characters"],
        "scenes": production["scenes"],
        "storyboard": plan["storyboardPlan"],
        "visualStyle": plan["visualStyle"],
        "productionPlan": production,
    }


class AiDirectorService:
    """Construct prompts, call V4, validate locally, and repair at most once."""

    def __init__(self, provider: TextProvider) -> None:
        self._provider = provider

    def generate(self, brief_value: Mapping[str, Any]) -> dict[str, Any]:
        brief = CreativeBrief.from_mapping(brief_value)
        first_output = self._call_provider(_build_messages(brief))
        try:
            return self._parse_and_validate(first_output, brief)
        except PlanValidationError as first_error:
            repaired_output = self._call_provider(
                _build_messages(
                    brief,
                    invalid_output=first_output,
                    validation_errors=first_error.errors,
                )
            )
            try:
                return self._parse_and_validate(repaired_output, brief)
            except PlanValidationError as exc:
                raise PlanGenerationError(
                    "invalid_provider_output",
                    diagnostic_category="provider_schema_error",
                    exception_name=type(exc).__name__,
                ) from exc

    def _call_provider(self, messages: tuple[TextMessage, ...]) -> str:
        try:
            return self._provider.generate(TextGenerationRequest(messages=messages))
        except ProviderTimeoutError as exc:
            raise PlanGenerationError(
                "provider_timeout",
                diagnostic_category=exc.category,
                provider_status=exc.status,
                exception_name=type(exc).__name__,
            ) from exc
        except TextProviderError as exc:
            raise PlanGenerationError(
                "provider_unavailable",
                diagnostic_category=exc.category,
                provider_status=exc.status,
                exception_name=type(exc).__name__,
            ) from exc

    @staticmethod
    def _parse_and_validate(raw_output: str, brief: CreativeBrief) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_output)
        except (json.JSONDecodeError, TypeError) as exc:
            raise PlanValidationError(["provider output is not JSON"]) from exc
        return validate_plan(parsed, brief)
