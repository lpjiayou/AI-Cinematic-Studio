"""M7 narrative-currentness validation on the existing evidence journal."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
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
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
    _utc_now,
)


CONSISTENCY_VALIDATION_RECORD_KIND = "ConsistencyValidationVersion"
SCRIPT_VERSION_SCHEMA_VERSION_V2 = "creator.script-studio.script-version.v2"
DEFAULT_VALIDATION_PROFILE_REF = "m7.narrative-currentness"
DEFAULT_VALIDATION_PROFILE_VERSION = 1

FINDING_CATEGORIES = frozenset(
    {
        "WORLD_RULE_CONFLICT",
        "TIMELINE_CONFLICT",
        "LOCATION_CONFLICT",
        "PROP_STATE_CONFLICT",
        "CHARACTER_STATE_CONFLICT",
        "RELATIONSHIP_CONFLICT",
        "FORBIDDEN_BEHAVIOR",
        "DIALOGUE_RULE_CONFLICT",
        "UNRESOLVED_REFERENCE",
        "SOURCE_BINDING_STALE",
    }
)
FINDING_SEVERITIES = frozenset({"WARN", "BLOCK"})
SOURCE_FIELDS = frozenset(
    {"ACTION", "DIALOGUE", "NARRATION", "SUBTITLE_TEXT"}
)
RESULT_READINESS = {
    "PASS": "READY_FOR_M8",
    "WARN": "NOT_READY_PENDING_DISPOSITION",
    "BLOCK": "NOT_READY",
}

_SOURCE_SPAN_FIELDS = frozenset(
    {
        "scriptSceneRef",
        "sourceField",
        "sourceIndex",
        "startOffsetInclusive",
        "endOffsetExclusive",
    }
)
_FINDING_FIELDS = frozenset(
    {
        "findingRef",
        "findingOrder",
        "category",
        "severity",
        "sourceSpan",
        "sourceTextDigest",
        "ruleSourceRef",
        "ruleSourceDigest",
        "evidence",
        "payloadDigest",
    }
)
_VALIDATION_FIELDS = frozenset(
    {
        "consistencyValidationRef",
        "consistencyValidationVersionRef",
        "validationVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "m6ConsumerBindingDigest",
        "m6BaselineSnapshotRef",
        "m6BaselineCanonicalDigest",
        "activationRevision",
        "seriesPlanVersionRef",
        "seriesPlanVersionDigest",
        "seriesBibleVersionRef",
        "seriesBibleVersionDigest",
        "characterContinuityVersionRef",
        "characterContinuityVersionDigest",
        "validationProfileRef",
        "validationProfileVersion",
        "validationProfileDigest",
        "result",
        "m8Readiness",
        "findings",
        "payloadDigest",
    }
)
_CREATE_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
        "validationProfileRef",
        "validationProfileVersion",
        "idempotencyKey",
    }
)
_DIGEST_FIELDS = frozenset(
    {
        "scriptVersionDigest",
        "m6ConsumerBindingDigest",
        "m6BaselineCanonicalDigest",
        "seriesPlanVersionDigest",
        "seriesBibleVersionDigest",
        "characterContinuityVersionDigest",
        "validationProfileDigest",
        "payloadDigest",
    }
)
_BINDING_PROJECTION_FIELDS = (
    "m6BaselineSnapshotRef",
    "m6BaselineCanonicalDigest",
    "activationRevision",
    "seriesPlanVersionRef",
    "seriesPlanVersionDigest",
    "seriesBibleVersionRef",
    "seriesBibleVersionDigest",
    "characterContinuityVersionRef",
    "characterContinuityVersionDigest",
)
_CHARACTER_RULE_SOURCE = {
    "ruleSourceRef": "m7.rule.m6-character-reference.v1",
    "category": "UNRESOLVED_REFERENCE",
    "severity": "BLOCK",
    "sourceFields": ["ACTION", "DIALOGUE"],
    "evidenceKind": "M6_CHARACTER_REFERENCE",
}
_CHARACTER_RULE_SOURCE_DIGEST = _digest(_CHARACTER_RULE_SOURCE)


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest_value(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


@dataclass(frozen=True, slots=True)
class NarrativeValidationRule:
    rule_source_ref: str
    category: str
    severity: str
    source_field: str
    match_text: str
    evidence: Mapping[str, Any]

    def source_mapping(self) -> dict[str, Any]:
        rule_ref = _required_ref(self.rule_source_ref, "ruleSourceRef")
        if self.category not in FINDING_CATEGORIES:
            raise EpisodeProductionError("validation rule category is invalid")
        if self.severity not in FINDING_SEVERITIES:
            raise EpisodeProductionError("validation rule severity is invalid")
        if self.source_field not in SOURCE_FIELDS:
            raise EpisodeProductionError("validation rule sourceField is invalid")
        if (
            not isinstance(self.match_text, str)
            or self.match_text != self.match_text.strip()
            or not self.match_text
        ):
            raise EpisodeProductionError("validation rule matchText is invalid")
        if not isinstance(self.evidence, Mapping):
            raise EpisodeProductionError("validation rule evidence is invalid")
        result = {
            "ruleSourceRef": rule_ref,
            "category": self.category,
            "severity": self.severity,
            "sourceField": self.source_field,
            "matchText": self.match_text,
            "evidence": deepcopy(dict(self.evidence)),
        }
        _digest(result)
        return result

    @property
    def source_digest(self) -> str:
        return _digest(self.source_mapping())


@dataclass(frozen=True, slots=True)
class NarrativeValidationProfile:
    validation_profile_ref: str
    validation_profile_version: int
    rules: Sequence[NarrativeValidationRule] = ()

    def mapping(self) -> dict[str, Any]:
        profile_ref = _required_ref(
            self.validation_profile_ref, "validationProfileRef"
        )
        profile_version = _positive_int(
            self.validation_profile_version, "validationProfileVersion"
        )
        rule_sources = [rule.source_mapping() for rule in self.rules]
        identities = [item["ruleSourceRef"] for item in rule_sources]
        if len(identities) != len(set(identities)):
            raise EpisodeProductionError("validation profile rule refs are ambiguous")
        return {
            "validationProfileRef": profile_ref,
            "validationProfileVersion": profile_version,
            "builtInChecks": ["M6_CHARACTER_REFERENCE"],
            "rules": [
                {**source, "ruleSourceDigest": _digest(source)}
                for source in rule_sources
            ],
        }

    @property
    def payload_digest(self) -> str:
        return _digest(self.mapping())


class NarrativeValidationProfileRegistry:
    """Immutable, code-defined validation profiles; never caller-owned facts."""

    def __init__(
        self, profiles: Sequence[NarrativeValidationProfile] | None = None
    ) -> None:
        selected = tuple(profiles) if profiles is not None else (
            NarrativeValidationProfile(
                DEFAULT_VALIDATION_PROFILE_REF,
                DEFAULT_VALIDATION_PROFILE_VERSION,
            ),
        )
        resolved: dict[tuple[str, int], NarrativeValidationProfile] = {}
        for profile in selected:
            mapping = profile.mapping()
            key = (
                mapping["validationProfileRef"],
                mapping["validationProfileVersion"],
            )
            if key in resolved:
                raise EpisodeProductionError("validation profile is ambiguous")
            resolved[key] = profile
        self.__profiles = resolved

    def resolve(
        self, profile_ref: str, profile_version: int
    ) -> NarrativeValidationProfile:
        key = (
            _required_ref(profile_ref, "validationProfileRef"),
            _positive_int(profile_version, "validationProfileVersion"),
        )
        profile = self.__profiles.get(key)
        if profile is None:
            raise UpstreamNotReadyError("validation profile is unavailable")
        return profile


@dataclass(frozen=True, slots=True)
class _SourceText:
    script_scene_ref: str
    source_field: str
    source_index: int
    text: str

    def span(self, start: int, end: int) -> dict[str, Any]:
        if not 0 <= start < end <= len(self.text):
            raise EpisodeProductionError("Script source span is invalid")
        return {
            "scriptSceneRef": self.script_scene_ref,
            "sourceField": self.source_field,
            "sourceIndex": self.source_index,
            "startOffsetInclusive": start,
            "endOffsetExclusive": end,
        }


def _script_sources(script_version: Mapping[str, Any]) -> list[_SourceText]:
    scenes = script_version.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise RepositoryUnavailableError("confirmed ScriptVersion scenes are unavailable")
    result: list[_SourceText] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            raise RepositoryUnavailableError("confirmed ScriptVersion scene is invalid")
        scene_ref = _required_ref(
            scene.get("scriptSceneRef"), f"scenes[{scene_index}].scriptSceneRef"
        )
        action = scene.get("action")
        if not isinstance(action, str) or not action:
            raise RepositoryUnavailableError("confirmed Script action is invalid")
        result.append(_SourceText(scene_ref, "ACTION", 0, action))
        dialogue = scene.get("dialogue")
        narration = scene.get("narration")
        subtitles = scene.get("subtitleText")
        if not isinstance(dialogue, list) or not isinstance(narration, list) or not isinstance(subtitles, list):
            raise RepositoryUnavailableError("confirmed Script source arrays are invalid")
        for index, line in enumerate(dialogue):
            text = line.get("text") if isinstance(line, Mapping) else None
            if not isinstance(text, str) or not text:
                raise RepositoryUnavailableError("confirmed Script dialogue is invalid")
            result.append(_SourceText(scene_ref, "DIALOGUE", index, text))
        for source_field, values in (
            ("NARRATION", narration),
            ("SUBTITLE_TEXT", subtitles),
        ):
            for index, text in enumerate(values):
                if not isinstance(text, str) or not text:
                    raise RepositoryUnavailableError(
                        "confirmed Script source text is invalid"
                    )
                result.append(_SourceText(scene_ref, source_field, index, text))
    return result


def _source_index(
    script_version: Mapping[str, Any]
) -> dict[tuple[str, str, int], _SourceText]:
    values = _script_sources(script_version)
    index = {
        (item.script_scene_ref, item.source_field, item.source_index): item
        for item in values
    }
    if len(index) != len(values):
        raise RepositoryUnavailableError("confirmed Script source identity is ambiguous")
    return index


class M7NarrativeValidationService:
    def __init__(
        self,
        run_service: EpisodeProductionService,
        evidence_repository: EpisodeProductionEvidenceRepository,
        *,
        script_reader: Any,
        profiles: NarrativeValidationProfileRegistry | None = None,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.run_service = run_service
        self.evidence_repository = evidence_repository
        self.script_reader = script_reader
        self.profiles = profiles or NarrativeValidationProfileRegistry()
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _not_found_scope(run: Mapping[str, Any], scope: Mapping[str, str]) -> None:
        if any(run.get(field) != scope[field] for field in scope):
            raise RecordNotFoundError("narrative validation scope was not found")

    def _run_for_scope(
        self,
        workspace: str,
        project: str,
        series: str,
        episode: str,
        run_ref: str,
    ) -> dict[str, Any]:
        run = self.run_service.get_run(workspace, run_ref)
        self._not_found_scope(
            run,
            {
                "workspaceRef": workspace,
                "projectRef": project,
                "seriesRef": series,
                "episodeRef": episode,
            },
        )
        return run

    @staticmethod
    def _read_script_workspace(operation: Callable[[], Any]) -> Mapping[str, Any]:
        try:
            workspace = operation()
        except Exception as exc:
            if getattr(exc, "status", None) == 404 or getattr(exc, "code", None) == "not_found":
                raise RecordNotFoundError("confirmed ScriptVersion was not found") from None
            raise RepositoryUnavailableError(
                "confirmed ScriptVersion could not be read"
            ) from None
        if not isinstance(workspace, Mapping):
            raise RepositoryUnavailableError("confirmed ScriptVersion is unavailable")
        return workspace

    def _fresh_m6_context(
        self, workspace: str, project: str, series: str, episode: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            context = self.script_reader.resolve_current_m6_consumer_context(
                workspace, project, series, episode
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            if code in {
                "m6_baseline_not_available",
                "m6_episode_mapping_unavailable",
                "m6_baseline_stale",
                "m6_lineage_mismatch",
            }:
                raise StaleInputError("M6 consumer binding is stale") from None
            if getattr(exc, "status", None) == 404:
                raise StaleInputError("M6 consumer binding is unavailable") from None
            raise RepositoryUnavailableError(
                "M6 consumer binding could not be resolved"
            ) from None
        binding = context.get("m6ConsumerBinding") if isinstance(context, Mapping) else None
        facts = context.get("applicableFacts") if isinstance(context, Mapping) else None
        if not isinstance(binding, Mapping) or not isinstance(facts, Mapping):
            raise RepositoryUnavailableError("M6 consumer context is unavailable")
        return deepcopy(dict(binding)), deepcopy(dict(facts))

    def _resolve_current(
        self,
        workspace: str,
        project: str,
        series: str,
        episode: str,
        run_ref: str,
    ) -> dict[str, Any]:
        run = self._run_for_scope(workspace, project, series, episode, run_ref)
        self.run_service.verify_run_current(workspace, run_ref)
        script_workspace = self._read_script_workspace(
            lambda: self.script_reader.get_workspace(workspace, series, episode)
        )
        script = script_workspace.get("script")
        versions = script_workspace.get("versions")
        if not isinstance(script, Mapping) or not isinstance(versions, list):
            raise StaleInputError("confirmed ScriptVersion is unavailable")
        version_ref = run.get("scriptVersionRef")
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
        if version.get("schemaVersion") != SCRIPT_VERSION_SCHEMA_VERSION_V2:
            raise UpstreamNotReadyError(
                "M6-bound ScriptVersion v2 is required for M7 validation"
            )
        binding = version.get("m6ConsumerBinding")
        if not isinstance(binding, Mapping):
            raise RepositoryUnavailableError("ScriptVersion M6 binding is invalid")
        expected_scope = {
            "workspaceRef": workspace,
            "projectRef": project,
            "seriesRef": series,
            "episodeRef": episode,
        }
        if any(binding.get(field) != value for field, value in expected_scope.items()):
            raise StaleInputError("ScriptVersion M6 binding scope changed")
        fresh_binding, applicable_facts = self._fresh_m6_context(
            workspace, project, series, episode
        )
        if dict(binding) != fresh_binding:
            raise StaleInputError("ScriptVersion M6 binding is stale")
        script_digest = _digest(dict(version))
        upstream = run.get("upstreamSnapshot")
        run_script = upstream.get("script") if isinstance(upstream, Mapping) else None
        if (
            not isinstance(run_script, Mapping)
            or run_script.get("scriptVersionRef") != version_ref
            or run_script.get("versionDigest") != script_digest
        ):
            raise StaleInputError("frozen ScriptVersion binding changed")
        return {
            "run": run,
            "scriptVersion": deepcopy(dict(version)),
            "scriptVersionDigest": script_digest,
            "m6ConsumerBinding": fresh_binding,
            "m6ApplicableFacts": applicable_facts,
        }

    @staticmethod
    def _base_finding(
        *,
        category: str,
        severity: str,
        source: _SourceText,
        start: int,
        end: int,
        rule_source_ref: str,
        rule_source_digest: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "category": category,
            "severity": severity,
            "sourceSpan": source.span(start, end),
            "sourceTextDigest": _digest_text(source.text[start:end]),
            "ruleSourceRef": rule_source_ref,
            "ruleSourceDigest": rule_source_digest,
            "evidence": deepcopy(dict(evidence)),
        }

    def _profile_findings(
        self,
        profile: NarrativeValidationProfile,
        sources: Sequence[_SourceText],
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for rule in profile.rules:
            source_mapping = rule.source_mapping()
            for source in sources:
                if source.source_field != rule.source_field:
                    continue
                start = 0
                while True:
                    start = source.text.find(rule.match_text, start)
                    if start < 0:
                        break
                    end = start + len(rule.match_text)
                    result.append(
                        self._base_finding(
                            category=rule.category,
                            severity=rule.severity,
                            source=source,
                            start=start,
                            end=end,
                            rule_source_ref=source_mapping["ruleSourceRef"],
                            rule_source_digest=rule.source_digest,
                            evidence={
                                "evidenceKind": "PROFILE_RULE_MATCH",
                                "matchTextDigest": _digest_text(rule.match_text),
                                "ruleEvidence": source_mapping["evidence"],
                            },
                        )
                    )
                    start = end
        return result

    def _character_findings(
        self,
        script_version: Mapping[str, Any],
        applicable_facts: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        characters = applicable_facts.get("characters")
        if not isinstance(characters, list):
            raise RepositoryUnavailableError("M6 character facts are unavailable")
        known_names = {
            item.get("name")
            for item in characters
            if isinstance(item, Mapping) and isinstance(item.get("name"), str)
        }
        sources_by_scene: dict[str, list[_SourceText]] = {}
        for source in _script_sources(script_version):
            sources_by_scene.setdefault(source.script_scene_ref, []).append(source)
        findings: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int, str]] = set()
        for scene in script_version["scenes"]:
            scene_ref = scene["scriptSceneRef"]
            scene_sources = sources_by_scene[scene_ref]
            action = next(item for item in scene_sources if item.source_field == "ACTION")
            for name in scene.get("characters", []):
                if name in known_names:
                    continue
                start = action.text.find(name)
                start = start if start >= 0 else 0
                end = start + len(name) if name and name in action.text else len(action.text)
                identity = (scene_ref, "ACTION", 0, str(name))
                if identity in seen:
                    continue
                seen.add(identity)
                findings.append(
                    self._base_finding(
                        category="UNRESOLVED_REFERENCE",
                        severity="BLOCK",
                        source=action,
                        start=start,
                        end=end,
                        rule_source_ref=_CHARACTER_RULE_SOURCE["ruleSourceRef"],
                        rule_source_digest=_CHARACTER_RULE_SOURCE_DIGEST,
                        evidence={
                            "evidenceKind": "UNRESOLVED_SCENE_CHARACTER",
                            "characterNameDigest": _digest_text(str(name)),
                        },
                    )
                )
            for index, line in enumerate(scene.get("dialogue", [])):
                speaker = line.get("speaker") if isinstance(line, Mapping) else None
                if speaker in known_names:
                    continue
                source = next(
                    item
                    for item in scene_sources
                    if item.source_field == "DIALOGUE" and item.source_index == index
                )
                identity = (scene_ref, "DIALOGUE", index, str(speaker))
                if identity in seen:
                    continue
                seen.add(identity)
                findings.append(
                    self._base_finding(
                        category="UNRESOLVED_REFERENCE",
                        severity="BLOCK",
                        source=source,
                        start=0,
                        end=len(source.text),
                        rule_source_ref=_CHARACTER_RULE_SOURCE["ruleSourceRef"],
                        rule_source_digest=_CHARACTER_RULE_SOURCE_DIGEST,
                        evidence={
                            "evidenceKind": "UNRESOLVED_DIALOGUE_SPEAKER",
                            "characterNameDigest": _digest_text(str(speaker)),
                        },
                    )
                )
        return findings

    def _findings(
        self,
        resolution: Mapping[str, Any],
        profile: NarrativeValidationProfile,
    ) -> list[dict[str, Any]]:
        script_version = resolution["scriptVersion"]
        sources = _script_sources(script_version)
        findings = self._profile_findings(profile, sources)
        findings.extend(
            self._character_findings(
                script_version, resolution["m6ApplicableFacts"]
            )
        )
        result: list[dict[str, Any]] = []
        for order, finding in enumerate(findings, start=1):
            payload = {
                "findingRef": _required_ref(
                    self._ref_factory("consistency-finding"), "findingRef"
                ),
                "findingOrder": order,
                **finding,
            }
            payload["payloadDigest"] = _digest(payload)
            result.append(payload)
        return result

    @staticmethod
    def _result(findings: Sequence[Mapping[str, Any]]) -> str:
        if any(item.get("severity") == "BLOCK" for item in findings):
            return "BLOCK"
        if findings:
            return "WARN"
        return "PASS"

    @staticmethod
    def _request_digest(
        scope: Mapping[str, str],
        run_ref: str,
        resolution: Mapping[str, Any],
        profile: NarrativeValidationProfile,
    ) -> str:
        run = resolution["run"]
        binding = resolution["m6ConsumerBinding"]
        return _digest(
            {
                "schemaVersion": "v5.consistency-validation-request.v1",
                **scope,
                "productionRunRef": run_ref,
                "productionRunPayloadDigest": run["payloadDigest"],
                "scriptVersionRef": resolution["scriptVersion"]["scriptVersionRef"],
                "scriptVersionDigest": resolution["scriptVersionDigest"],
                "m6ConsumerBindingDigest": binding["payloadDigest"],
                "validationProfileRef": profile.validation_profile_ref,
                "validationProfileVersion": profile.validation_profile_version,
                "validationProfileDigest": profile.payload_digest,
            }
        )

    @staticmethod
    def _validate_source_span(
        value: Any,
        sources: Mapping[tuple[str, str, int], _SourceText] | None,
    ) -> tuple[_SourceText, int, int] | None:
        if not isinstance(value, Mapping) or set(value) != _SOURCE_SPAN_FIELDS:
            raise RepositoryUnavailableError("stored Finding sourceSpan is invalid")
        scene_ref = _required_ref(value.get("scriptSceneRef"), "scriptSceneRef")
        source_field = value.get("sourceField")
        source_index = value.get("sourceIndex")
        start = value.get("startOffsetInclusive")
        end = value.get("endOffsetExclusive")
        if source_field not in SOURCE_FIELDS:
            raise RepositoryUnavailableError("stored Finding sourceField is invalid")
        if (
            isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or source_index < 0
            or (source_field == "ACTION" and source_index != 0)
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
        ):
            raise RepositoryUnavailableError("stored Finding offsets are invalid")
        if sources is None:
            if not 0 <= start < end:
                raise RepositoryUnavailableError("stored Finding source span is invalid")
            return None
        source = sources.get((scene_ref, source_field, source_index))
        if source is None or not 0 <= start < end <= len(source.text):
            raise RepositoryUnavailableError("stored Finding source is unresolved")
        return source, start, end

    def _validate_payload(
        self,
        payload: Any,
        *,
        script_version: Mapping[str, Any] | None = None,
        profile: NarrativeValidationProfile | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping) or set(payload) != _VALIDATION_FIELDS:
            raise RepositoryUnavailableError(
                "stored ConsistencyValidationVersion fields are invalid"
            )
        value = deepcopy(dict(payload))
        for field in (
            "consistencyValidationRef",
            "consistencyValidationVersionRef",
            "workspaceRef",
            "projectRef",
            "seriesRef",
            "episodeRef",
            "scriptVersionRef",
            "m6BaselineSnapshotRef",
            "seriesPlanVersionRef",
            "seriesBibleVersionRef",
            "characterContinuityVersionRef",
            "validationProfileRef",
        ):
            _required_ref(value.get(field), field)
        _positive_int(value.get("validationVersion"), "validationVersion")
        _positive_int(value.get("activationRevision"), "activationRevision")
        _positive_int(
            value.get("validationProfileVersion"), "validationProfileVersion"
        )
        for field in _DIGEST_FIELDS:
            _digest_value(value.get(field), field)
        findings = value.get("findings")
        if not isinstance(findings, list):
            raise RepositoryUnavailableError("stored Findings are invalid")
        source_values = _source_index(script_version) if script_version is not None else None
        finding_refs: set[str] = set()
        allowed_rule_sources: set[tuple[str, str]] | None = None
        if profile is not None:
            allowed_rule_sources = {
                (_CHARACTER_RULE_SOURCE["ruleSourceRef"], _CHARACTER_RULE_SOURCE_DIGEST),
                *(
                    (rule.rule_source_ref, rule.source_digest)
                    for rule in profile.rules
                ),
            }
        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, Mapping) or set(finding) != _FINDING_FIELDS:
                raise RepositoryUnavailableError("stored Finding fields are invalid")
            finding_ref = _required_ref(finding.get("findingRef"), "findingRef")
            if finding_ref in finding_refs:
                raise RepositoryUnavailableError("stored Finding identity is ambiguous")
            finding_refs.add(finding_ref)
            if finding.get("findingOrder") != index:
                raise RepositoryUnavailableError("stored Finding order is invalid")
            if finding.get("category") not in FINDING_CATEGORIES:
                raise RepositoryUnavailableError("stored Finding category is invalid")
            if finding.get("severity") not in FINDING_SEVERITIES:
                raise RepositoryUnavailableError("stored Finding severity is invalid")
            rule_identity = (
                _required_ref(finding.get("ruleSourceRef"), "ruleSourceRef"),
                _digest_value(finding.get("ruleSourceDigest"), "ruleSourceDigest"),
            )
            if allowed_rule_sources is not None and rule_identity not in allowed_rule_sources:
                raise RepositoryUnavailableError("stored Finding rule source is stale")
            if not isinstance(finding.get("evidence"), Mapping):
                raise RepositoryUnavailableError("stored Finding evidence is invalid")
            _digest_value(finding.get("sourceTextDigest"), "sourceTextDigest")
            resolved_source = self._validate_source_span(
                finding.get("sourceSpan"), source_values
            )
            if resolved_source is not None:
                source, start, end = resolved_source
                if finding["sourceTextDigest"] != _digest_text(source.text[start:end]):
                    raise RepositoryUnavailableError(
                        "stored Finding source text digest is invalid"
                    )
            embedded = dict(finding)
            finding_digest = embedded.pop("payloadDigest")
            if finding_digest != _digest(embedded):
                raise RepositoryUnavailableError("stored Finding digest is invalid")
        result = self._result(findings)
        if value.get("result") != result or value.get("m8Readiness") != RESULT_READINESS[result]:
            raise RepositoryUnavailableError("stored M8 readiness is invalid")
        embedded = dict(value)
        payload_digest = embedded.pop("payloadDigest")
        if payload_digest != _digest(embedded):
            raise RepositoryUnavailableError(
                "stored ConsistencyValidationVersion digest is invalid"
            )
        return value

    def _validated_records(
        self, workspace: str, run_ref: str
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        records = self.evidence_repository.list_records(
            workspace, run_ref, record_kind=CONSISTENCY_VALIDATION_RECORD_KIND
        )
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        root_ref: str | None = None
        version_refs: set[str] = set()
        for expected_version, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                raise RepositoryUnavailableError("stored M7 evidence is invalid")
            payload = self._validate_payload(record.get("payload"))
            if (
                record.get("recordKind") != CONSISTENCY_VALIDATION_RECORD_KIND
                or record.get("recordRef") != payload["consistencyValidationRef"]
                or record.get("recordVersion") != payload["validationVersion"]
                or record.get("payloadDigest") != payload["payloadDigest"]
                or payload["validationVersion"] != expected_version
            ):
                raise RepositoryUnavailableError("stored M7 evidence envelope is invalid")
            if root_ref is None:
                root_ref = payload["consistencyValidationRef"]
            if payload["consistencyValidationRef"] != root_ref:
                raise RepositoryUnavailableError("stored M7 validation root is ambiguous")
            version_ref = payload["consistencyValidationVersionRef"]
            if version_ref in version_refs:
                raise RepositoryUnavailableError("stored M7 version identity is ambiguous")
            version_refs.add(version_ref)
            result.append((dict(record), payload))
        return result

    @staticmethod
    def _payload_matches_current(
        payload: Mapping[str, Any],
        scope: Mapping[str, str],
        resolution: Mapping[str, Any],
        profile: NarrativeValidationProfile,
    ) -> bool:
        binding = resolution["m6ConsumerBinding"]
        expected = {
            **scope,
            "scriptVersionRef": resolution["scriptVersion"]["scriptVersionRef"],
            "scriptVersionDigest": resolution["scriptVersionDigest"],
            "m6ConsumerBindingDigest": binding["payloadDigest"],
            **{field: binding[field] for field in _BINDING_PROJECTION_FIELDS},
            "validationProfileRef": profile.validation_profile_ref,
            "validationProfileVersion": profile.validation_profile_version,
            "validationProfileDigest": profile.payload_digest,
        }
        return all(payload.get(field) == value for field, value in expected.items())

    def create_validation(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != _CREATE_FIELDS:
            raise EpisodeProductionError(
                "command fields do not match the M7 validation contract"
            )
        scope = {
            field: _required_ref(command.get(field), field)
            for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
        }
        run_ref = _required_ref(command.get("productionRunRef"), "productionRunRef")
        key = _idempotency_key(command.get("idempotencyKey"))
        profile = self.profiles.resolve(
            command.get("validationProfileRef"),
            command.get("validationProfileVersion"),
        )
        resolution = self._resolve_current(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
        )
        request_digest = self._request_digest(scope, run_ref, resolution, profile)
        existing = self.evidence_repository.get_record_by_idempotency_key(
            scope["workspaceRef"], run_ref, key
        )
        if existing is not None:
            if (
                existing.get("recordKind") != CONSISTENCY_VALIDATION_RECORD_KIND
                or existing.get("requestDigest") != request_digest
            ):
                raise IdempotencyConflictError(
                    "M7 validation idempotency content changed"
                )
            payload = self._validate_payload(
                existing.get("payload"),
                script_version=resolution["scriptVersion"],
                profile=profile,
            )
            if not self._payload_matches_current(payload, scope, resolution, profile):
                raise IdempotencyConflictError(
                    "M7 validation replay no longer matches current inputs"
                )
            return {**payload, "currentness": "CURRENT", "idempotentReplay": True}

        journal_head = self.evidence_repository.record_journal_head(
            scope["workspaceRef"], run_ref
        )
        previous = self._validated_records(scope["workspaceRef"], run_ref)
        validation_version = len(previous) + 1
        consistency_ref = (
            previous[0][1]["consistencyValidationRef"]
            if previous
            else _required_ref(
                self._ref_factory("consistency-validation"),
                "consistencyValidationRef",
            )
        )
        findings = self._findings(resolution, profile)
        result = self._result(findings)
        binding = resolution["m6ConsumerBinding"]
        payload = {
            "consistencyValidationRef": consistency_ref,
            "consistencyValidationVersionRef": _required_ref(
                self._ref_factory("consistency-validation-version"),
                "consistencyValidationVersionRef",
            ),
            "validationVersion": validation_version,
            **scope,
            "scriptVersionRef": resolution["scriptVersion"]["scriptVersionRef"],
            "scriptVersionDigest": resolution["scriptVersionDigest"],
            "m6ConsumerBindingDigest": binding["payloadDigest"],
            **{field: binding[field] for field in _BINDING_PROJECTION_FIELDS},
            "validationProfileRef": profile.validation_profile_ref,
            "validationProfileVersion": profile.validation_profile_version,
            "validationProfileDigest": profile.payload_digest,
            "result": result,
            "m8Readiness": RESULT_READINESS[result],
            "findings": findings,
        }
        payload["payloadDigest"] = _digest(payload)
        self._validate_payload(
            payload,
            script_version=resolution["scriptVersion"],
            profile=profile,
        )
        record = EvidenceRecord(
            workspaceRef=scope["workspaceRef"],
            productionRunRef=run_ref,
            recordKind=CONSISTENCY_VALIDATION_RECORD_KIND,
            recordRef=consistency_ref,
            recordVersion=validation_version,
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
                or concurrent.get("recordKind")
                != CONSISTENCY_VALIDATION_RECORD_KIND
                or concurrent.get("requestDigest") != request_digest
            ):
                raise
            concurrent_payload = self._validate_payload(
                concurrent.get("payload"),
                script_version=resolution["scriptVersion"],
                profile=profile,
            )
            if not self._payload_matches_current(
                concurrent_payload, scope, resolution, profile
            ):
                raise IdempotencyConflictError(
                    "M7 validation replay no longer matches current inputs"
                )
            return {
                **concurrent_payload,
                "currentness": "CURRENT",
                "idempotentReplay": True,
            }
        stored = stored_records[0]
        stored_payload = self._validate_payload(
            stored.get("payload"),
            script_version=resolution["scriptVersion"],
            profile=profile,
        )
        return {
            **stored_payload,
            "currentness": "CURRENT",
            "idempotentReplay": replayed,
        }

    def get_validation(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        consistency_validation_version_ref: str | None = None,
    ) -> dict[str, Any]:
        scope = {
            "workspaceRef": _required_ref(workspace_ref, "workspaceRef"),
            "projectRef": _required_ref(project_ref, "projectRef"),
            "seriesRef": _required_ref(series_ref, "seriesRef"),
            "episodeRef": _required_ref(episode_ref, "episodeRef"),
        }
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        self._run_for_scope(
            scope["workspaceRef"],
            scope["projectRef"],
            scope["seriesRef"],
            scope["episodeRef"],
            run_ref,
        )
        records = self._validated_records(scope["workspaceRef"], run_ref)
        selected = None
        if consistency_validation_version_ref is None:
            selected = records[-1] if records else None
        else:
            version_ref = _required_ref(
                consistency_validation_version_ref,
                "consistencyValidationVersionRef",
            )
            selected = next(
                (item for item in records if item[1]["consistencyValidationVersionRef"] == version_ref),
                None,
            )
        if selected is None:
            raise RecordNotFoundError("ConsistencyValidationVersion was not found")
        payload = selected[1]
        if any(payload.get(field) != value for field, value in scope.items()):
            raise RecordNotFoundError("ConsistencyValidationVersion was not found")
        try:
            profile = self.profiles.resolve(
                payload["validationProfileRef"], payload["validationProfileVersion"]
            )
            resolution = self._resolve_current(
                scope["workspaceRef"],
                scope["projectRef"],
                scope["seriesRef"],
                scope["episodeRef"],
                run_ref,
            )
            payload = self._validate_payload(
                payload,
                script_version=resolution["scriptVersion"],
                profile=profile,
            )
            current = self._payload_matches_current(
                payload, scope, resolution, profile
            )
        except (StaleInputError, UpstreamNotReadyError, RepositoryUnavailableError):
            current = False
        return {
            **payload,
            "currentness": "CURRENT" if current else "STALE",
            "idempotentReplay": False,
        }

    def require_m8_ready_validation(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
        production_run_ref: str,
        consistency_validation_version_ref: str,
    ) -> dict[str, Any]:
        result = self.get_validation(
            workspace_ref,
            project_ref,
            series_ref,
            episode_ref,
            production_run_ref,
            consistency_validation_version_ref,
        )
        if (
            result["currentness"] != "CURRENT"
            or result["result"] != "PASS"
            or result["m8Readiness"] != "READY_FOR_M8"
        ):
            raise ExecutionNotAuthorizedError(
                "current READY_FOR_M8 validation is required"
            )
        return result
