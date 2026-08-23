"""Creator Application orchestration for provider-neutral Series Director candidates."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Mapping

from services.v5_core_os.text_generation import (
    TextGenerationCapability,
    TextGenerationCapabilityError,
    TextGenerationCommand,
    TextGenerationMessage,
    TextGenerationPurpose,
    TextGenerationTimeoutError,
)


SERIES_PLAN_CANDIDATE_SCHEMA_VERSION = "creator.series-plan.candidate.v1"


@dataclass(frozen=True)
class SeriesPlanValidationIssue:
    field: str
    rule: str
    category: str = "provider_schema_error"


class SeriesPlanCandidateError(ValueError):
    def __init__(self, issues: list[SeriesPlanValidationIssue]) -> None:
        super().__init__("; ".join(f"{item.field}: {item.rule}" for item in issues))
        self.issues = tuple(issues)


class SeriesDirectorGenerationError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        diagnostic_category: str = "application_error",
        provider_status: int | None = None,
        validation_issues: tuple[tuple[str, str, str], ...] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.diagnostic_category = diagnostic_category
        self.provider_status = provider_status
        self.validation_issues = validation_issues


def _issue(issues: list[SeriesPlanValidationIssue], field: str, rule: str) -> None:
    issues.append(SeriesPlanValidationIssue(field, rule))


def _text(value: Any, field: str, issues: list[SeriesPlanValidationIssue], *, limit: int = 4000) -> str:
    if not isinstance(value, str):
        _issue(issues, field, "invalid_type")
        return ""
    result = value.strip()
    if not result:
        _issue(issues, field, "required_field")
    elif len(result) > limit:
        _issue(issues, field, "max_length")
    return result


def _integer(
    value: Any,
    field: str,
    issues: list[SeriesPlanValidationIssue],
    *,
    minimum: int = 1,
    maximum: int = 10_000,
) -> int:
    if isinstance(value, bool):
        _issue(issues, field, "invalid_type")
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError):
        _issue(issues, field, "invalid_type")
        return 0
    if result < minimum or result > maximum:
        _issue(issues, field, "out_of_range")
    return result


def _text_list(value: Any, field: str, issues: list[SeriesPlanValidationIssue]) -> list[str]:
    if not isinstance(value, list):
        _issue(issues, field, "invalid_type")
        return []
    return [_text(item, f"{field}[{index}]", issues, limit=1200) for index, item in enumerate(value)]


def _object_list(value: Any, field: str, issues: list[SeriesPlanValidationIssue]) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        _issue(issues, field, "invalid_type")
        return []
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            _issue(issues, f"{field}[{index}]", "invalid_type")
        else:
            result.append(item)
    return result


def _require_fields(
    value: Mapping[str, Any],
    field: str,
    expected: set[str],
    issues: list[SeriesPlanValidationIssue],
) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    for name in sorted(missing):
        _issue(issues, f"{field}.{name}" if field else name, "required_field")
    for name in sorted(extra):
        _issue(issues, f"{field}.{name}" if field else name, "unsupported_field")


def validate_series_plan_candidate(value: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    """Validate provider output without accepting provider-owned structural identity."""
    issues: list[SeriesPlanValidationIssue] = []
    if not isinstance(value, Mapping):
        raise SeriesPlanCandidateError([SeriesPlanValidationIssue("$", "invalid_type")])
    expected_top = {
        "schemaVersion",
        "seriesConcept",
        "premise",
        "logline",
        "mainNarrativeDirection",
        "mainArcs",
        "subArcs",
        "characterArcIntents",
        "episodePlanItems",
        "narrativeRhythm",
        "worldIntent",
        "continuityIntent",
        "foreshadowingContext",
        "productionAssumptions",
    }
    _require_fields(value, "", expected_top, issues)
    if value.get("schemaVersion") != SERIES_PLAN_CANDIDATE_SCHEMA_VERSION:
        _issue(issues, "schemaVersion", "invalid_value")
    planned_count = _integer(context.get("plannedEpisodeCount"), "context.plannedEpisodeCount", issues, maximum=500)
    normalized: dict[str, Any] = {
        "schemaVersion": SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
        "seriesConcept": _text(value.get("seriesConcept"), "seriesConcept", issues),
        "premise": _text(value.get("premise"), "premise", issues),
        "logline": _text(value.get("logline"), "logline", issues),
        "mainNarrativeDirection": _text(value.get("mainNarrativeDirection"), "mainNarrativeDirection", issues),
        "narrativeRhythm": _text(value.get("narrativeRhythm"), "narrativeRhythm", issues),
        "worldIntent": _text(value.get("worldIntent"), "worldIntent", issues),
        "continuityIntent": _text_list(value.get("continuityIntent"), "continuityIntent", issues),
        "foreshadowingContext": _text_list(value.get("foreshadowingContext"), "foreshadowingContext", issues),
        "productionAssumptions": _text_list(value.get("productionAssumptions"), "productionAssumptions", issues),
    }

    arcs: list[dict[str, Any]] = []
    expected_arc_fields = {"arcNumber", "title", "episodeStart", "episodeEnd", "objective", "turningPoint"}
    for index, item in enumerate(_object_list(value.get("mainArcs"), "mainArcs", issues)):
        path = f"mainArcs[{index}]"
        _require_fields(item, path, expected_arc_fields, issues)
        arc = {
            "arcNumber": _integer(item.get("arcNumber"), f"{path}.arcNumber", issues, maximum=100),
            "title": _text(item.get("title"), f"{path}.title", issues, limit=300),
            "episodeStart": _integer(item.get("episodeStart"), f"{path}.episodeStart", issues, maximum=planned_count or 500),
            "episodeEnd": _integer(item.get("episodeEnd"), f"{path}.episodeEnd", issues, maximum=planned_count or 500),
            "objective": _text(item.get("objective"), f"{path}.objective", issues),
            "turningPoint": _text(item.get("turningPoint"), f"{path}.turningPoint", issues),
        }
        if arc["arcNumber"] != index + 1:
            _issue(issues, f"{path}.arcNumber", "non_continuous")
        if arc["episodeStart"] > arc["episodeEnd"]:
            _issue(issues, path, "invalid_episode_range")
        arcs.append(arc)
    if not arcs:
        _issue(issues, "mainArcs", "non_empty")
    normalized["mainArcs"] = arcs

    sub_arcs: list[dict[str, Any]] = []
    expected_sub_fields = {"title", "episodeStart", "episodeEnd", "purpose"}
    for index, item in enumerate(_object_list(value.get("subArcs"), "subArcs", issues)):
        path = f"subArcs[{index}]"
        _require_fields(item, path, expected_sub_fields, issues)
        sub_arc = {
            "title": _text(item.get("title"), f"{path}.title", issues, limit=300),
            "episodeStart": _integer(item.get("episodeStart"), f"{path}.episodeStart", issues, maximum=planned_count or 500),
            "episodeEnd": _integer(item.get("episodeEnd"), f"{path}.episodeEnd", issues, maximum=planned_count or 500),
            "purpose": _text(item.get("purpose"), f"{path}.purpose", issues),
        }
        if sub_arc["episodeStart"] > sub_arc["episodeEnd"]:
            _issue(issues, path, "invalid_episode_range")
        sub_arcs.append(sub_arc)
    normalized["subArcs"] = sub_arcs

    character_intents: list[dict[str, str]] = []
    expected_character_fields = {"roleLabel", "startingState", "developmentIntent", "destination"}
    for index, item in enumerate(_object_list(value.get("characterArcIntents"), "characterArcIntents", issues)):
        path = f"characterArcIntents[{index}]"
        _require_fields(item, path, expected_character_fields, issues)
        character_intents.append({
            "roleLabel": _text(item.get("roleLabel"), f"{path}.roleLabel", issues, limit=200),
            "startingState": _text(item.get("startingState"), f"{path}.startingState", issues),
            "developmentIntent": _text(item.get("developmentIntent"), f"{path}.developmentIntent", issues),
            "destination": _text(item.get("destination"), f"{path}.destination", issues),
        })
    if not character_intents:
        _issue(issues, "characterArcIntents", "non_empty")
    normalized["characterArcIntents"] = character_intents

    episodes: list[dict[str, Any]] = []
    expected_episode_fields = {
        "episodeNumber",
        "title",
        "logline",
        "arcNumber",
        "narrativePurpose",
        "continuityNotes",
        "foreshadowing",
    }
    for index, item in enumerate(_object_list(value.get("episodePlanItems"), "episodePlanItems", issues)):
        path = f"episodePlanItems[{index}]"
        _require_fields(item, path, expected_episode_fields, issues)
        episode = {
            "episodeNumber": _integer(item.get("episodeNumber"), f"{path}.episodeNumber", issues, maximum=planned_count or 500),
            "title": _text(item.get("title"), f"{path}.title", issues, limit=300),
            "logline": _text(item.get("logline"), f"{path}.logline", issues),
            "arcNumber": _integer(item.get("arcNumber"), f"{path}.arcNumber", issues, maximum=max(len(arcs), 1)),
            "narrativePurpose": _text(item.get("narrativePurpose"), f"{path}.narrativePurpose", issues),
            "continuityNotes": _text_list(item.get("continuityNotes"), f"{path}.continuityNotes", issues),
            "foreshadowing": _text_list(item.get("foreshadowing"), f"{path}.foreshadowing", issues),
        }
        if episode["episodeNumber"] != index + 1:
            _issue(issues, f"{path}.episodeNumber", "non_continuous")
        episodes.append(episode)
    if len(episodes) != planned_count:
        _issue(issues, "episodePlanItems", "count_must_match_project")
    normalized["episodePlanItems"] = episodes

    if arcs and planned_count:
        coverage = set()
        for arc in arcs:
            coverage.update(range(arc["episodeStart"], arc["episodeEnd"] + 1))
        if coverage != set(range(1, planned_count + 1)):
            _issue(issues, "mainArcs", "must_cover_all_planned_episodes")
        arc_numbers = {item["arcNumber"] for item in arcs}
        for index, episode in enumerate(episodes):
            if episode["arcNumber"] not in arc_numbers:
                _issue(issues, f"episodePlanItems[{index}].arcNumber", "unknown_arc")
    if issues:
        raise SeriesPlanCandidateError(issues)
    return normalized


def _candidate_contract(context: Mapping[str, Any]) -> dict[str, Any]:
    count = int(context["plannedEpisodeCount"])
    shape_example = {
        "schemaVersion": SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
        "seriesConcept": "系列核心概念",
        "premise": "系列故事前提",
        "logline": "系列一句话故事",
        "mainNarrativeDirection": "主叙事推进方向",
        "mainArcs": [{
            "arcNumber": 1,
            "title": "主弧线名称",
            "episodeStart": 1,
            "episodeEnd": count,
            "objective": "本弧线目标",
            "turningPoint": "本弧线转折",
        }],
        "subArcs": [{
            "title": "副弧线名称",
            "episodeStart": 1,
            "episodeEnd": count,
            "purpose": "副弧线作用",
        }],
        "characterArcIntents": [{
            "roleLabel": "角色名称或职责标签",
            "startingState": "起始状态",
            "developmentIntent": "成长意图",
            "destination": "目标状态",
        }],
        "episodePlanItems": [
            {
                "episodeNumber": index,
                "title": f"第{index}集标题",
                "logline": f"第{index}集一句话故事",
                "arcNumber": 1,
                "narrativePurpose": "本集叙事作用",
                "continuityNotes": ["连续性提示"],
                "foreshadowing": ["伏笔提示"],
            }
            for index in range(1, count + 1)
        ],
        "narrativeRhythm": "系列节奏设计",
        "worldIntent": "世界与空间意图",
        "continuityIntent": ["跨集连续性约束"],
        "foreshadowingContext": ["跨集伏笔上下文"],
        "productionAssumptions": ["制作假设"],
    }
    return {
        "schemaVersion": SERIES_PLAN_CANDIDATE_SCHEMA_VERSION,
        "plannedEpisodeCount": count,
        "requiredFields": [
            "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs", "subArcs",
            "characterArcIntents", "episodePlanItems", "narrativeRhythm", "worldIntent", "continuityIntent",
            "foreshadowingContext", "productionAssumptions",
        ],
        "mainArcFields": ["arcNumber", "title", "episodeStart", "episodeEnd", "objective", "turningPoint"],
        "subArcFields": ["title", "episodeStart", "episodeEnd", "purpose"],
        "characterArcFields": ["roleLabel", "startingState", "developmentIntent", "destination"],
        "episodeFields": ["episodeNumber", "title", "logline", "arcNumber", "narrativePurpose", "continuityNotes", "foreshadowing"],
        "completeJsonShapeExample": shape_example,
        "rules": [
            f"Return exactly {count} episodePlanItems numbered 1 through {count}.",
            "Main arcs must be contiguous, cover every planned episode, and use arcNumber starting at 1.",
            "Return Chinese creative content. Arrays must exist even when empty.",
            "Use exactly the keys and JSON value types shown in completeJsonShapeExample; replace example prose with project-specific content.",
            "Return a raw JSON object without Markdown code fences, commentary, prefixes, or suffixes.",
            "Do not return projectRef, seriesRef, seriesPlanRef, seriesPlanVersionRef, episodeRef, or characterRef.",
        ],
    }


def _generation_messages(
    context: Mapping[str, Any],
    creative_input: str,
) -> tuple[TextGenerationMessage, ...]:
    return (
        TextGenerationMessage(
            "system",
            "You are the Series Director planning engine. Return one JSON object only and follow the supplied "
            "contract exactly. The output is an unconfirmed candidate. Never create system-owned references, "
            "production Episodes, approval claims, or provider-owned identity. Use concise Chinese content.",
        ),
        TextGenerationMessage(
            "user",
            json.dumps({
                "task": "Generate a coherent long-form Series production plan candidate.",
                "requiredContract": _candidate_contract(context),
                "projectSeriesContext": dict(context),
                "creativeInput": creative_input,
            }, ensure_ascii=False),
        ),
    )


def _repair_messages(
    context: Mapping[str, Any],
    creative_input: str,
    invalid_candidate: Any,
    issues: tuple[SeriesPlanValidationIssue, ...],
) -> tuple[TextGenerationMessage, ...]:
    return (
        TextGenerationMessage(
            "system",
            "Repair the Series Plan candidate exactly once. Return one complete JSON object only. Do not add "
            "system-owned references or create production Episode facts.",
        ),
        TextGenerationMessage(
            "user",
            json.dumps({
                "task": "Repair the candidate against the contract.",
                "requiredContract": _candidate_contract(context),
                "projectSeriesContext": dict(context),
                "creativeInput": creative_input,
                "validationIssues": [{"field": item.field, "rule": item.rule} for item in issues],
                "invalidCandidate": invalid_candidate if isinstance(invalid_candidate, Mapping) else "UNPARSEABLE_JSON",
            }, ensure_ascii=False),
        ),
    )


class SeriesDirectorApplicationService:
    """Generate Series Plan candidates through V5 and validate them locally."""

    def __init__(self, text_generation: TextGenerationCapability) -> None:
        self._text_generation = text_generation

    def generate(self, context: Mapping[str, Any], creative_input: Any) -> dict[str, Any]:
        text = str(creative_input or "").strip()
        if not text or len(text) > 4000:
            raise SeriesPlanCandidateError([SeriesPlanValidationIssue("creativeInput", "invalid_value", "application_contract_error")])
        raw = self._call(_generation_messages(context, text))
        try:
            parsed = json.loads(raw)
            return validate_series_plan_candidate(parsed, context)
        except (json.JSONDecodeError, SeriesPlanCandidateError) as first_error:
            issues = (
                first_error.issues
                if isinstance(first_error, SeriesPlanCandidateError)
                else (SeriesPlanValidationIssue("$", "invalid_json"),)
            )
            self._log(issues, "initial")
            parsed = parsed if "parsed" in locals() and isinstance(parsed, Mapping) else None
            repaired = self._call(_repair_messages(context, text, parsed, issues))
            try:
                repaired_parsed = json.loads(repaired)
                return validate_series_plan_candidate(repaired_parsed, context)
            except (json.JSONDecodeError, SeriesPlanCandidateError) as repair_error:
                repair_issues = (
                    repair_error.issues
                    if isinstance(repair_error, SeriesPlanCandidateError)
                    else (SeriesPlanValidationIssue("$", "invalid_json"),)
                )
                self._log(repair_issues, "repair")
                raise SeriesDirectorGenerationError(
                    "invalid_provider_output",
                    diagnostic_category="provider_schema_error",
                    validation_issues=tuple((item.field, item.rule, item.category) for item in (*issues, *repair_issues)),
                ) from repair_error

    def _call(self, messages: tuple[TextGenerationMessage, ...]) -> str:
        try:
            return self._text_generation.generate(
                TextGenerationCommand(
                    purpose=TextGenerationPurpose.SERIES_PLAN_CANDIDATE,
                    messages=messages,
                )
            )
        except TextGenerationTimeoutError as exc:
            raise SeriesDirectorGenerationError(
                "provider_timeout", diagnostic_category=exc.category, provider_status=exc.status
            ) from exc
        except TextGenerationCapabilityError as exc:
            raise SeriesDirectorGenerationError(
                "provider_unavailable", diagnostic_category=exc.category, provider_status=exc.status
            ) from exc

    @staticmethod
    def _log(issues: tuple[SeriesPlanValidationIssue, ...], attempt: str) -> None:
        for item in issues:
            print(
                "SERIES_DIRECTOR_SCHEMA_ERROR "
                f"attempt={attempt} field={item.field} rule={item.rule} category={item.category}",
                file=sys.stderr,
                flush=True,
            )
