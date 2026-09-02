"""V5-owned Script Studio facts, repository port, and local adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4


SCRIPT_SCHEMA_VERSION = "v5.script.v1"
SCRIPT_VERSION_SCHEMA_VERSION = "creator.script-studio.script-version.v1"
SCRIPT_VERSION_SCHEMA_VERSION_V2 = "creator.script-studio.script-version.v2"
SCRIPT_ACCEPTANCE_SCHEMA_VERSION = "v5.script-acceptance.v1"
SCRIPT_ACCEPTANCE_SUBJECT_SCHEMA_VERSION = "v5.script-acceptance-subject.v1"
STORYBOARD_BOOTSTRAP_SCHEMA_VERSION = "creator.storyboard.bootstrap-input.v1"
SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION = "creator.script-studio.bootstrap-input.v1"
SQLITE_SCHEMA_VERSION = 1

_SCRIPT_CONTENT_FIELDS = {
    "title",
    "logline",
    "synopsis",
    "targetDurationSec",
    "scenes",
}
_PERSISTED_SCRIPT_SCENE_FIELDS = {
    "scriptSceneRef",
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
_SCRIPT_CHANGE_KINDS = {
    "ai-generation",
    "manual-edit",
    "ai-scene-rewrite",
    "reviewed-import",
}
_M6_CONSUMER_BINDING_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "seriesPlanVersionRef",
    "seriesPlanVersionDigest",
    "m6BaselineSnapshotRef",
    "m6BaselineCanonicalDigest",
    "activationRevision",
    "seriesBibleVersionRef",
    "seriesBibleVersionDigest",
    "characterContinuityVersionRef",
    "characterContinuityVersionDigest",
)
_CLIENT_FORBIDDEN_M6_FIELDS = frozenset(
    {
        "m6ConsumerBinding",
        "seriesPlanVersionRef",
        "seriesPlanVersionDigest",
        "m6BaselineSnapshotRef",
        "m6BaselineCanonicalDigest",
        "activationRevision",
        "seriesBibleVersionRef",
        "seriesBibleVersionDigest",
        "characterContinuityVersionRef",
        "characterContinuityVersionDigest",
        "payloadDigest",
    }
)


class ScriptStudioError(ValueError):
    code = "invalid_request"


class RecordNotFoundError(ScriptStudioError):
    code = "not_found"


class DuplicateRecordError(ScriptStudioError):
    code = "duplicate_record"


class ScopeMismatchError(ScriptStudioError):
    code = "scope_mismatch"


class VersionConflictError(ScriptStudioError):
    code = "version_conflict"


class ScriptNotConfirmedError(ScriptStudioError):
    code = "script_not_confirmed"


class TrustedApprovalRequiredError(ScriptStudioError):
    code = "trusted_approval_required"


class RepositoryWriteError(ScriptStudioError):
    code = "application_error"


class M6ConsumerReadError(ScriptStudioError):
    """Preserve an upstream M6 fail-closed code at the Script boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UpstreamReader(Protocol):
    def build_script_studio_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str, *, limit: int = 4000) -> str:
    text = str(value or "").strip()
    if not text:
        raise ScriptStudioError(f"{field} is required")
    if len(text) > limit:
        raise ScriptStudioError(f"{field} is too long")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise ScriptStudioError(f"{field} is invalid")
    return text


def _sha256_digest(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=64).lower()
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise ScriptStudioError(f"{field} must be a SHA-256 digest")
    return text


def _canonical_digest(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ScriptStudioError("value cannot be canonicalized") from exc
    return hashlib.sha256(encoded).hexdigest()


def _reject_client_m6_fields(value: Any, *, path: str = "command") -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(set(value).intersection(_CLIENT_FORBIDDEN_M6_FIELDS))
        if forbidden:
            raise ScriptStudioError(
                f"{path} contains server-owned M6 field {forbidden[0]}"
            )
        for field, item in value.items():
            _reject_client_m6_fields(item, path=f"{path}.{field}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_client_m6_fields(item, path=f"{path}[{index}]")


def normalize_m6_consumer_binding(value: Any) -> dict[str, Any]:
    """Validate the closed Script-owned projection of one active M6 baseline."""

    expected = {*_M6_CONSUMER_BINDING_FIELDS, "payloadDigest"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ScriptStudioError("m6ConsumerBinding fields are invalid")
    normalized: dict[str, Any] = {}
    for field in _M6_CONSUMER_BINDING_FIELDS:
        raw = value.get(field)
        if field == "activationRevision":
            normalized[field] = _positive_int(raw, field)
        elif field.endswith("Digest"):
            normalized[field] = _sha256_digest(raw, field)
        else:
            normalized[field] = _required_ref(raw, field)
    normalized["payloadDigest"] = _sha256_digest(
        value.get("payloadDigest"), "payloadDigest"
    )
    if normalized["payloadDigest"] != _canonical_digest(
        {field: normalized[field] for field in _M6_CONSUMER_BINDING_FIELDS}
    ):
        raise ScriptStudioError("m6ConsumerBinding payloadDigest is invalid")
    return normalized


def build_m6_consumer_binding(
    baseline: Any,
    *,
    workspace_ref: str,
    project_ref: str,
    series_ref: str,
    episode_ref: str,
) -> dict[str, Any]:
    if not isinstance(baseline, Mapping) or baseline.get("compatibility") != "CURRENT":
        raise ScriptStudioError("current M6 Episode baseline is required")
    expected_scope = (workspace_ref, project_ref, series_ref, episode_ref)
    actual_scope = tuple(
        baseline.get(field)
        for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
    )
    if actual_scope != expected_scope:
        raise ScopeMismatchError("M6 Episode baseline scope does not match Script")
    payload = {
        field: baseline.get(field) for field in _M6_CONSUMER_BINDING_FIELDS
    }
    payload["payloadDigest"] = _canonical_digest(payload)
    return normalize_m6_consumer_binding(payload)


def _positive_int(value: Any, field: str, *, maximum: int = 100_000) -> int:
    if isinstance(value, bool):
        raise ScriptStudioError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ScriptStudioError(f"{field} must be an integer") from exc
    if result < 1 or result > maximum:
        raise ScriptStudioError(f"{field} is out of range")
    return result


def _positive_number(value: Any, field: str, *, maximum: float = 3600) -> float:
    if isinstance(value, bool):
        raise ScriptStudioError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ScriptStudioError(f"{field} must be a number") from exc
    if result <= 0 or result > maximum:
        raise ScriptStudioError(f"{field} is out of range")
    return round(result, 3)


def _text_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise ScriptStudioError(f"{field} must be an array")
    result = [_required_text(item, field, limit=1000) for item in value]
    if not allow_empty and not result:
        raise ScriptStudioError(f"{field} must not be empty")
    return result


def _dialogue(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ScriptStudioError(f"{field} must be an array")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ScriptStudioError(f"{field}[{index}] must be an object")
        if set(item) != {"speaker", "text", "emotion"}:
            raise ScriptStudioError(f"{field}[{index}] fields are invalid")
        result.append(
            {
                "speaker": _required_text(item.get("speaker"), f"{field}.speaker", limit=120),
                "text": _required_text(item.get("text"), f"{field}.text", limit=2000),
                "emotion": _required_text(item.get("emotion"), f"{field}.emotion", limit=200),
            }
        )
    return result


def _bootstrap_target_duration(bootstrap: Mapping[str, Any]) -> float:
    storyboard = bootstrap.get("storyboardPlan")
    if not isinstance(storyboard, list) or not storyboard:
        raise ScriptStudioError("bootstrap storyboardPlan is invalid")
    return round(
        sum(_positive_number(item.get("durationSec"), "storyboardPlan.durationSec") for item in storyboard if isinstance(item, Mapping)),
        3,
    )


def _validate_bootstrap(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScriptStudioError("bootstrap is invalid")
    if value.get("schemaVersion") != SCRIPT_STUDIO_BOOTSTRAP_SCHEMA_VERSION:
        raise ScriptStudioError("bootstrap schemaVersion is invalid")
    for field in (
        "workspaceRef",
        "seriesRef",
        "episodeRef",
        "sourcePlanRef",
        "sourcePlanSchemaVersion",
    ):
        _required_ref(value.get(field), field)
    _positive_int(value.get("sourcePlanVersion"), "sourcePlanVersion")
    for field in ("storyDirection", "scriptDraft", "visualStyle", "productionPlan"):
        if not isinstance(value.get(field), Mapping):
            raise ScriptStudioError(f"bootstrap {field} is invalid")
    _bootstrap_target_duration(value)
    return value


def _normalize_content(
    value: Any,
    *,
    bootstrap: Mapping[str, Any],
    ref_factory: Callable[[str], str],
    existing_scene_refs: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScriptStudioError("script content must be an object")
    expected = {"title", "logline", "synopsis", "targetDurationSec", "scenes"}
    if set(value) != expected:
        raise ScriptStudioError("script content fields do not match the accepted contract")
    target_duration = _positive_number(value.get("targetDurationSec"), "targetDurationSec")
    bootstrap_duration = _bootstrap_target_duration(bootstrap)
    if abs(target_duration - bootstrap_duration) > 0.001:
        raise ScriptStudioError("targetDurationSec does not match Episode context")
    scenes_value = value.get("scenes")
    if not isinstance(scenes_value, list) or not scenes_value:
        raise ScriptStudioError("scenes must be a non-empty array")
    scenes: list[dict[str, Any]] = []
    scene_refs: set[str] = set()
    expected_number = 1
    for index, raw in enumerate(scenes_value):
        if not isinstance(raw, Mapping):
            raise ScriptStudioError(f"scenes[{index}] must be an object")
        allowed = {
            "scriptSceneRef",
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
        if set(raw) - allowed:
            raise ScriptStudioError(f"scenes[{index}] contains unsupported fields")
        number = _positive_int(raw.get("sceneNumber"), f"scenes[{index}].sceneNumber", maximum=10_000)
        if number != expected_number:
            raise ScriptStudioError("scene numbers must be continuous")
        expected_number += 1
        supplied_ref = raw.get("scriptSceneRef")
        if existing_scene_refs is None:
            if "scriptSceneRef" in raw:
                raise ScriptStudioError(
                    "scriptSceneRef must be omitted from an initial ScriptVersion"
                )
            scene_ref = ref_factory("script-scene")
        else:
            if not supplied_ref:
                raise ScriptStudioError(
                    "scriptSceneRef is required for a derived version"
                )
            scene_ref = _required_ref(supplied_ref, "scriptSceneRef")
            if scene_ref not in existing_scene_refs:
                raise ScopeMismatchError(
                    "scriptSceneRef does not belong to the source ScriptVersion"
                )
        if scene_ref in scene_refs:
            raise ScriptStudioError("scriptSceneRef values must be unique")
        scene_refs.add(scene_ref)
        scenes.append(
            {
                "scriptSceneRef": scene_ref,
                "sceneNumber": number,
                "heading": _required_text(raw.get("heading"), "heading", limit=300),
                "location": _required_text(raw.get("location"), "location", limit=300),
                "timeOfDay": _required_text(raw.get("timeOfDay"), "timeOfDay", limit=120),
                "characters": _text_list(raw.get("characters"), "characters"),
                "action": _required_text(raw.get("action"), "action", limit=6000),
                "dialogue": _dialogue(raw.get("dialogue"), "dialogue"),
                "narration": _text_list(raw.get("narration"), "narration"),
                "subtitleText": _text_list(raw.get("subtitleText"), "subtitleText"),
                "estimatedDurationSec": _positive_number(raw.get("estimatedDurationSec"), "estimatedDurationSec"),
                "scenePurpose": _required_text(raw.get("scenePurpose"), "scenePurpose", limit=1000),
                "continuityNotes": _text_list(raw.get("continuityNotes"), "continuityNotes"),
                "productionNotes": _text_list(raw.get("productionNotes"), "productionNotes"),
            }
        )
    total_duration = round(sum(scene["estimatedDurationSec"] for scene in scenes), 3)
    minimum = target_duration * 0.8
    maximum = target_duration * 1.2
    if not minimum <= total_duration <= maximum:
        raise ScriptStudioError("scene duration total is inconsistent with the Episode target")
    return {
        "title": _required_text(value.get("title"), "title", limit=300),
        "logline": _required_text(value.get("logline"), "logline", limit=1000),
        "synopsis": _required_text(value.get("synopsis"), "synopsis", limit=6000),
        "targetDurationSec": target_duration,
        "scenes": scenes,
    }


def _normalize_persisted_content(
    value: Any,
    *,
    schema_version: str,
    reviewed_import: bool,
) -> dict[str, Any]:
    """Fail closed when immutable ScriptVersion content no longer matches storage shape."""

    expected = set(_SCRIPT_CONTENT_FIELDS)
    if reviewed_import:
        expected.add("importProvenance")
    if schema_version == SCRIPT_VERSION_SCHEMA_VERSION_V2:
        expected.add("m6ConsumerBinding")
    elif schema_version != SCRIPT_VERSION_SCHEMA_VERSION:
        raise RepositoryWriteError("persisted ScriptVersion schema is invalid")
    if not isinstance(value, Mapping) or set(value) != expected:
        raise RepositoryWriteError("persisted ScriptVersion content is invalid")

    try:
        target_duration = _positive_number(
            value.get("targetDurationSec"), "targetDurationSec"
        )
        scenes_value = value.get("scenes")
        if not isinstance(scenes_value, list) or not scenes_value:
            raise ScriptStudioError("scenes must be a non-empty array")
        scenes: list[dict[str, Any]] = []
        scene_refs: set[str] = set()
        for index, raw in enumerate(scenes_value):
            if not isinstance(raw, Mapping) or set(raw) != _PERSISTED_SCRIPT_SCENE_FIELDS:
                raise ScriptStudioError(
                    f"persisted scenes[{index}] fields are invalid"
                )
            number = _positive_int(
                raw.get("sceneNumber"),
                f"scenes[{index}].sceneNumber",
                maximum=10_000,
            )
            if number != index + 1:
                raise ScriptStudioError("scene numbers must be continuous")
            scene_ref = _required_ref(
                raw.get("scriptSceneRef"), f"scenes[{index}].scriptSceneRef"
            )
            if scene_ref in scene_refs:
                raise ScriptStudioError("scriptSceneRef values must be unique")
            scene_refs.add(scene_ref)
            scenes.append(
                {
                    "scriptSceneRef": scene_ref,
                    "sceneNumber": number,
                    "heading": _required_text(
                        raw.get("heading"), "heading", limit=300
                    ),
                    "location": _required_text(
                        raw.get("location"), "location", limit=300
                    ),
                    "timeOfDay": _required_text(
                        raw.get("timeOfDay"), "timeOfDay", limit=120
                    ),
                    "characters": _text_list(raw.get("characters"), "characters"),
                    "action": _required_text(
                        raw.get("action"), "action", limit=6000
                    ),
                    "dialogue": _dialogue(raw.get("dialogue"), "dialogue"),
                    "narration": _text_list(raw.get("narration"), "narration"),
                    "subtitleText": _text_list(
                        raw.get("subtitleText"), "subtitleText"
                    ),
                    "estimatedDurationSec": _positive_number(
                        raw.get("estimatedDurationSec"), "estimatedDurationSec"
                    ),
                    "scenePurpose": _required_text(
                        raw.get("scenePurpose"), "scenePurpose", limit=1000
                    ),
                    "continuityNotes": _text_list(
                        raw.get("continuityNotes"), "continuityNotes"
                    ),
                    "productionNotes": _text_list(
                        raw.get("productionNotes"), "productionNotes"
                    ),
                }
            )
        total_duration = round(
            sum(scene["estimatedDurationSec"] for scene in scenes), 3
        )
        if not target_duration * 0.8 <= total_duration <= target_duration * 1.2:
            raise ScriptStudioError(
                "scene duration total is inconsistent with the ScriptVersion target"
            )
        normalized = {
            "title": _required_text(value.get("title"), "title", limit=300),
            "logline": _required_text(value.get("logline"), "logline", limit=1000),
            "synopsis": _required_text(
                value.get("synopsis"), "synopsis", limit=6000
            ),
            "targetDurationSec": target_duration,
            "scenes": scenes,
        }
    except ScriptStudioError as exc:
        raise RepositoryWriteError("persisted ScriptVersion content is invalid") from exc

    stored_content = {field: value[field] for field in _SCRIPT_CONTENT_FIELDS}
    if normalized != stored_content:
        raise RepositoryWriteError("persisted ScriptVersion content is not normalized")
    if reviewed_import:
        normalized["importProvenance"] = value["importProvenance"]
    if schema_version == SCRIPT_VERSION_SCHEMA_VERSION_V2:
        try:
            normalized["m6ConsumerBinding"] = normalize_m6_consumer_binding(
                value["m6ConsumerBinding"]
            )
        except ScriptStudioError as exc:
            raise RepositoryWriteError(
                "persisted ScriptVersion M6 binding is invalid"
            ) from exc
    return normalized


@dataclass(frozen=True)
class ScriptRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    title: str
    currentScriptVersionRef: str
    confirmedScriptVersionRef: str | None
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class ScriptVersionRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    scriptVersionRef: str
    sourcePlanRef: str
    sourcePlanSchemaVersion: str
    sourcePlanVersion: int
    versionNumber: int
    contentJson: str
    changeKind: str
    parentScriptVersionRef: str | None
    createdAt: str


@dataclass(frozen=True)
class ScriptAcceptanceSubject:
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    scriptVersionRef: str
    uploadedSourceByteDigest: str
    normalizedSourceDocumentDigest: str
    reviewedDocumentDigest: str
    canonicalScriptContentDigest: str
    importProvenanceDigest: str

    @classmethod
    def create(cls, **value: Any) -> "ScriptAcceptanceSubject":
        return cls(
            *(
                _required_ref(value.get(field), field)
                for field in (
                    "workspaceRef",
                    "seriesRef",
                    "episodeRef",
                    "scriptRef",
                    "scriptVersionRef",
                )
            ),
            *(
                _sha256_digest(value.get(field), field)
                for field in (
                    "uploadedSourceByteDigest",
                    "normalizedSourceDocumentDigest",
                    "reviewedDocumentDigest",
                    "canonicalScriptContentDigest",
                    "importProvenanceDigest",
                )
            ),
        )

    def as_mapping(self) -> dict[str, str]:
        return {
            "schemaVersion": SCRIPT_ACCEPTANCE_SUBJECT_SCHEMA_VERSION,
            **{
                field: getattr(self, field)
                for field in (
                    "workspaceRef",
                    "seriesRef",
                    "episodeRef",
                    "scriptRef",
                    "scriptVersionRef",
                    "uploadedSourceByteDigest",
                    "normalizedSourceDocumentDigest",
                    "reviewedDocumentDigest",
                    "canonicalScriptContentDigest",
                    "importProvenanceDigest",
                )
            },
        }

    @property
    def subject_digest(self) -> str:
        return _canonical_digest(self.as_mapping())


@dataclass(frozen=True)
class VerifiedScriptAcceptance:
    authorityRef: str
    approvalRef: str
    actorRef: str
    actorKind: str
    decision: str
    authorityDecisionRef: str
    authorityDecisionDigest: str
    decidedAt: str
    governanceRecordRef: str
    subjectDigest: str

    @classmethod
    def create(cls, **value: Any) -> "VerifiedScriptAcceptance":
        actor_kind = _required_text(value.get("actorKind"), "actorKind", limit=40)
        decision = _required_text(value.get("decision"), "decision", limit=40)
        if actor_kind != "PROJECT_LEAD" or decision != "ACCEPTED":
            raise TrustedApprovalRequiredError(
                "trusted Script acceptance decision is invalid"
            )
        return cls(
            _required_ref(value.get("authorityRef"), "authorityRef"),
            _required_ref(value.get("approvalRef"), "approvalRef"),
            _required_ref(value.get("actorRef"), "actorRef"),
            actor_kind,
            decision,
            _required_ref(
                value.get("authorityDecisionRef"), "authorityDecisionRef"
            ),
            _sha256_digest(
                value.get("authorityDecisionDigest"),
                "authorityDecisionDigest",
            ),
            _required_text(value.get("decidedAt"), "decidedAt", limit=100),
            _required_ref(
                value.get("governanceRecordRef"), "governanceRecordRef"
            ),
            _sha256_digest(value.get("subjectDigest"), "subjectDigest"),
        )

    def matches(
        self,
        *,
        subject: ScriptAcceptanceSubject,
        approval_ref: str,
    ) -> bool:
        return (
            self.approvalRef == approval_ref
            and self.subjectDigest == subject.subject_digest
            and self.decision == "ACCEPTED"
            and self.actorKind == "PROJECT_LEAD"
        )


class ScriptAcceptanceAuthorityPort(Protocol):
    def verify(
        self,
        *,
        subject: ScriptAcceptanceSubject,
        approval_ref: str,
    ) -> VerifiedScriptAcceptance: ...


class RejectingScriptAcceptanceAuthority:
    def verify(self, **_: Any) -> VerifiedScriptAcceptance:
        raise TrustedApprovalRequiredError(
            "reviewed-import lineage requires a trusted approval resolver"
        )


@dataclass(frozen=True)
class ScriptAcceptanceRecord:
    schemaVersion: str
    workspaceRef: str
    seriesRef: str
    episodeRef: str
    scriptRef: str
    scriptVersionRef: str
    acceptanceRef: str
    approvalRef: str
    authorityDecisionRef: str
    idempotencyKey: str
    contentJson: str
    payloadDigest: str
    createdAt: str


def _same_acceptance_request(
    left: ScriptAcceptanceRecord,
    right: ScriptAcceptanceRecord,
) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in (
            "schemaVersion",
            "workspaceRef",
            "seriesRef",
            "episodeRef",
            "scriptRef",
            "scriptVersionRef",
            "approvalRef",
            "authorityDecisionRef",
            "idempotencyKey",
            "contentJson",
        )
    )


def _acceptance_mapping(record: ScriptAcceptanceRecord) -> dict[str, Any]:
    try:
        content = json.loads(record.contentJson)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RepositoryWriteError("persisted Script acceptance is invalid") from exc
    fields = {
        "uploadedSourceByteDigest",
        "normalizedSourceDocumentDigest",
        "reviewedDocumentDigest",
        "canonicalScriptContentDigest",
        "importProvenanceDigest",
        "subjectDigest",
        "authorityRef",
        "actorRef",
        "actorKind",
        "decision",
        "authorityDecisionDigest",
        "decidedAt",
        "governanceRecordRef",
        "publicationAllowed",
    }
    if record.schemaVersion != SCRIPT_ACCEPTANCE_SCHEMA_VERSION or not isinstance(
        content, Mapping
    ) or set(content) != fields:
        raise RepositoryWriteError("persisted Script acceptance is invalid")
    try:
        canonical_content_json = json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RepositoryWriteError(
            "persisted Script acceptance content is invalid"
        ) from exc
    if record.contentJson != canonical_content_json:
        raise RepositoryWriteError(
            "persisted Script acceptance content is not canonical"
        )
    try:
        subject = ScriptAcceptanceSubject.create(
            workspaceRef=record.workspaceRef,
            seriesRef=record.seriesRef,
            episodeRef=record.episodeRef,
            scriptRef=record.scriptRef,
            scriptVersionRef=record.scriptVersionRef,
            **{
                field: content.get(field)
                for field in (
                    "uploadedSourceByteDigest",
                    "normalizedSourceDocumentDigest",
                    "reviewedDocumentDigest",
                    "canonicalScriptContentDigest",
                    "importProvenanceDigest",
                )
            },
        )
        verified = VerifiedScriptAcceptance.create(
            authorityRef=content.get("authorityRef"),
            approvalRef=record.approvalRef,
            actorRef=content.get("actorRef"),
            actorKind=content.get("actorKind"),
            decision=content.get("decision"),
            authorityDecisionRef=record.authorityDecisionRef,
            authorityDecisionDigest=content.get("authorityDecisionDigest"),
            decidedAt=content.get("decidedAt"),
            governanceRecordRef=content.get("governanceRecordRef"),
            subjectDigest=content.get("subjectDigest"),
        )
        for field in (
            "acceptanceRef",
            "approvalRef",
            "authorityDecisionRef",
            "idempotencyKey",
        ):
            _required_ref(getattr(record, field), field)
        _required_text(record.createdAt, "createdAt", limit=100)
        _sha256_digest(record.payloadDigest, "payloadDigest")
    except ScriptStudioError as exc:
        raise RepositoryWriteError("persisted Script acceptance is invalid") from exc
    if (
        content.get("subjectDigest") != subject.subject_digest
        or not verified.matches(subject=subject, approval_ref=record.approvalRef)
        or content.get("publicationAllowed") is not False
    ):
        raise RepositoryWriteError("persisted Script acceptance is invalid")
    payload = {
        "schemaVersion": record.schemaVersion,
        "workspaceRef": record.workspaceRef,
        "seriesRef": record.seriesRef,
        "episodeRef": record.episodeRef,
        "scriptRef": record.scriptRef,
        "scriptVersionRef": record.scriptVersionRef,
        "acceptanceRef": record.acceptanceRef,
        "approvalRef": record.approvalRef,
        "authorityDecisionRef": record.authorityDecisionRef,
        "idempotencyKey": record.idempotencyKey,
        **dict(content),
        "createdAt": record.createdAt,
    }
    if _canonical_digest(payload) != record.payloadDigest:
        raise RepositoryWriteError("persisted Script acceptance digest is invalid")
    return {**payload, "payloadDigest": record.payloadDigest}


class ScriptStudioRepository(Protocol):
    def create_script_with_version(
        self,
        script: ScriptRecord,
        version: ScriptVersionRecord,
    ) -> tuple[ScriptRecord, ScriptVersionRecord]: ...

    def append_version(
        self,
        updated_script: ScriptRecord,
        version: ScriptVersionRecord,
        expected_script_version: int,
    ) -> tuple[ScriptRecord, ScriptVersionRecord]: ...

    def confirm_version(
        self,
        updated_script: ScriptRecord,
        expected_script_version: int,
    ) -> ScriptRecord: ...

    def accept_reviewed_import(
        self,
        updated_script: ScriptRecord,
        acceptance: ScriptAcceptanceRecord,
        expected_script_version: int,
    ) -> tuple[ScriptRecord, ScriptAcceptanceRecord, bool]: ...

    def get_script(self, workspace_ref: str, series_ref: str, episode_ref: str) -> ScriptRecord | None: ...
    def get_script_by_ref(self, workspace_ref: str, script_ref: str) -> ScriptRecord | None: ...
    def get_version(self, workspace_ref: str, script_ref: str, version_ref: str) -> ScriptVersionRecord | None: ...
    def list_versions(self, workspace_ref: str, script_ref: str) -> list[ScriptVersionRecord]: ...
    def get_acceptance(
        self, workspace_ref: str, script_ref: str, version_ref: str
    ) -> ScriptAcceptanceRecord | None: ...
    def get_acceptance_by_idempotency_key(
        self, workspace_ref: str, idempotency_key: str
    ) -> ScriptAcceptanceRecord | None: ...


class InMemoryScriptStudioAdapter:
    """Deterministic repository adapter for tests only."""

    def __init__(self) -> None:
        self._scripts: dict[tuple[str, str], ScriptRecord] = {}
        self._episode_index: dict[tuple[str, str, str], str] = {}
        self._versions: dict[tuple[str, str, str], ScriptVersionRecord] = {}
        self._acceptances: dict[
            tuple[str, str, str], ScriptAcceptanceRecord
        ] = {}
        self._acceptance_idempotency: dict[
            tuple[str, str], tuple[str, str, str]
        ] = {}
        self._acceptance_uniques: dict[
            tuple[str, str, str], tuple[str, str, str]
        ] = {}
        self._lock = RLock()

    def create_script_with_version(self, script, version):
        script_key = (script.workspaceRef, script.scriptRef)
        episode_key = (script.workspaceRef, script.seriesRef, script.episodeRef)
        version_key = (version.workspaceRef, version.scriptRef, version.scriptVersionRef)
        with self._lock:
            if script_key in self._scripts or episode_key in self._episode_index or version_key in self._versions:
                raise DuplicateRecordError("Script already exists for Episode")
            self._scripts[script_key] = script
            self._episode_index[episode_key] = script.scriptRef
            self._versions[version_key] = version
        return script, version

    def append_version(self, updated_script, version, expected_script_version):
        key = (updated_script.workspaceRef, updated_script.scriptRef)
        version_key = (version.workspaceRef, version.scriptRef, version.scriptVersionRef)
        with self._lock:
            current = self._scripts.get(key)
            if current is None:
                raise RecordNotFoundError("Script was not found")
            if current.version != expected_script_version:
                raise VersionConflictError("Script version changed")
            if version_key in self._versions:
                raise DuplicateRecordError("ScriptVersion already exists")
            self._versions[version_key] = version
            self._scripts[key] = updated_script
        return updated_script, version

    def confirm_version(self, updated_script, expected_script_version):
        key = (updated_script.workspaceRef, updated_script.scriptRef)
        with self._lock:
            current = self._scripts.get(key)
            if current is None:
                raise RecordNotFoundError("Script was not found")
            if current.version != expected_script_version:
                raise VersionConflictError("Script version changed")
            version_key = (
                updated_script.workspaceRef,
                updated_script.scriptRef,
                updated_script.confirmedScriptVersionRef,
            )
            if version_key not in self._versions:
                raise RecordNotFoundError("ScriptVersion was not found")
            self._scripts[key] = updated_script
        return updated_script

    def accept_reviewed_import(
        self, updated_script, acceptance, expected_script_version
    ):
        script_key = (updated_script.workspaceRef, updated_script.scriptRef)
        acceptance_key = (
            acceptance.workspaceRef,
            acceptance.scriptRef,
            acceptance.scriptVersionRef,
        )
        idempotency_key = (
            acceptance.workspaceRef,
            acceptance.idempotencyKey,
        )
        with self._lock:
            current = self._scripts.get(script_key)
            if current is None:
                raise RecordNotFoundError("Script was not found")
            existing_key = self._acceptance_idempotency.get(idempotency_key)
            existing = self._acceptances.get(acceptance_key)
            if existing is not None or existing_key is not None:
                replay = existing or self._acceptances.get(existing_key)
                if (
                    replay is None
                    or not _same_acceptance_request(replay, acceptance)
                    or current.confirmedScriptVersionRef
                    != acceptance.scriptVersionRef
                ):
                    raise VersionConflictError(
                        "Script acceptance idempotency content changed"
                    )
                return current, replay, True
            if current.version != expected_script_version:
                raise VersionConflictError("Script version changed")
            version_key = (
                acceptance.workspaceRef,
                acceptance.scriptRef,
                acceptance.scriptVersionRef,
            )
            if version_key not in self._versions:
                raise RecordNotFoundError("ScriptVersion was not found")
            unique_values = {
                "acceptanceRef": acceptance.acceptanceRef,
                "approvalRef": acceptance.approvalRef,
                "authorityDecisionRef": acceptance.authorityDecisionRef,
            }
            if any(
                (acceptance.workspaceRef, kind, value)
                in self._acceptance_uniques
                for kind, value in unique_values.items()
            ):
                raise VersionConflictError(
                    "Script acceptance identity already exists"
                )
            self._acceptances[acceptance_key] = acceptance
            self._acceptance_idempotency[idempotency_key] = acceptance_key
            for kind, value in unique_values.items():
                self._acceptance_uniques[
                    (acceptance.workspaceRef, kind, value)
                ] = acceptance_key
            self._scripts[script_key] = updated_script
        return updated_script, acceptance, False

    def get_script(self, workspace_ref, series_ref, episode_ref):
        script_ref = self._episode_index.get((workspace_ref, series_ref, episode_ref))
        return self._scripts.get((workspace_ref, script_ref)) if script_ref else None

    def get_script_by_ref(self, workspace_ref, script_ref):
        return self._scripts.get((workspace_ref, script_ref))

    def get_version(self, workspace_ref, script_ref, version_ref):
        return self._versions.get((workspace_ref, script_ref, version_ref))

    def list_versions(self, workspace_ref, script_ref):
        records = [
            item
            for (workspace, script, _), item in self._versions.items()
            if workspace == workspace_ref and script == script_ref
        ]
        return sorted(records, key=lambda item: item.versionNumber)

    def get_acceptance(self, workspace_ref, script_ref, version_ref):
        return self._acceptances.get((workspace_ref, script_ref, version_ref))

    def get_acceptance_by_idempotency_key(
        self, workspace_ref, idempotency_key
    ):
        key = self._acceptance_idempotency.get(
            (workspace_ref, idempotency_key)
        )
        return self._acceptances.get(key) if key is not None else None

    def lifecycle_has_episode_dependency(self, workspace_ref, series_ref, episode_ref):
        if (workspace_ref, series_ref, episode_ref) in self._episode_index:
            return True
        return any(
            record.workspaceRef == workspace_ref
            and record.seriesRef == series_ref
            and record.episodeRef == episode_ref
            for record in self._versions.values()
        )

    def lifecycle_has_series_dependency(self, workspace_ref, series_ref):
        if any(
            key[0] == workspace_ref and key[1] == series_ref
            for key in self._episode_index
        ):
            return True
        return any(
            record.workspaceRef == workspace_ref and record.seriesRef == series_ref
            for record in self._versions.values()
        )


class SqliteScriptStudioAdapter:
    """SQLite local-development durable adapter; not a production database."""

    def __init__(self, database_path: Path | str, *, lifecycle_state=None) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._lifecycle_state = lifecycle_state
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise RuntimeError("SQLite foreign key enforcement unavailable")
        return connection

    @contextmanager
    def _session(self):
        shared = self._lifecycle_state.connection_or_none() if self._lifecycle_state else None
        if shared is not None:
            yield shared
            return
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def _write_session(self):
        shared = self._lifecycle_state.connection_or_none() if self._lifecycle_state else None
        if shared is not None:
            yield shared
            return
        if self._lifecycle_state is not None:
            raise RuntimeError("valid lifecycle lease is required")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS v5_script_studio_schema (
                    component TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_scripts (
                    workspace_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    script_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    title TEXT NOT NULL,
                    current_script_version_ref TEXT NOT NULL,
                    confirmed_script_version_ref TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, script_ref),
                    UNIQUE(workspace_ref, series_ref, episode_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_script_versions (
                    workspace_ref TEXT NOT NULL,
                    script_ref TEXT NOT NULL,
                    script_version_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    episode_ref TEXT NOT NULL,
                    source_plan_ref TEXT NOT NULL,
                    source_plan_schema_version TEXT NOT NULL,
                    source_plan_version INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    change_kind TEXT NOT NULL,
                    parent_script_version_ref TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_ref, script_ref, script_version_ref),
                    UNIQUE(workspace_ref, script_ref, version_number),
                    FOREIGN KEY(workspace_ref, script_ref)
                        REFERENCES v5_scripts(workspace_ref, script_ref) ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO v5_script_studio_schema VALUES (?, ?)",
                ("script_studio", SQLITE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT schema_version FROM v5_script_studio_schema WHERE component = ?",
                ("script_studio",),
            ).fetchone()
            if row is None or row["schema_version"] not in {SQLITE_SCHEMA_VERSION, 2}:
                raise RuntimeError("unsupported Script Studio local-development schema version")

    @staticmethod
    def _script(row: sqlite3.Row) -> ScriptRecord:
        return ScriptRecord(
            row["schema_version"], row["workspace_ref"], row["series_ref"],
            row["episode_ref"], row["script_ref"], row["title"],
            row["current_script_version_ref"], row["confirmed_script_version_ref"],
            row["created_at"], row["updated_at"], row["version"],
        )

    @staticmethod
    def _version(row: sqlite3.Row) -> ScriptVersionRecord:
        return ScriptVersionRecord(
            row["schema_version"], row["workspace_ref"], row["series_ref"],
            row["episode_ref"], row["script_ref"], row["script_version_ref"],
            row["source_plan_ref"], row["source_plan_schema_version"],
            row["source_plan_version"], row["version_number"], row["content_json"],
            row["change_kind"], row["parent_script_version_ref"], row["created_at"],
        )

    @staticmethod
    def _acceptance(row: sqlite3.Row) -> ScriptAcceptanceRecord:
        return ScriptAcceptanceRecord(
            row["schema_version"],
            row["workspace_ref"],
            row["series_ref"],
            row["episode_ref"],
            row["script_ref"],
            row["script_version_ref"],
            row["acceptance_ref"],
            row["approval_ref"],
            row["authority_decision_ref"],
            row["idempotency_key"],
            row["content_json"],
            row["payload_digest"],
            row["created_at"],
        )

    @staticmethod
    def _script_values(record: ScriptRecord) -> tuple[Any, ...]:
        return (
            record.workspaceRef, record.seriesRef, record.episodeRef, record.scriptRef,
            record.schemaVersion, record.title, record.currentScriptVersionRef,
            record.confirmedScriptVersionRef, record.createdAt, record.updatedAt,
            record.version,
        )

    @staticmethod
    def _version_values(record: ScriptVersionRecord) -> tuple[Any, ...]:
        return (
            record.workspaceRef, record.scriptRef, record.scriptVersionRef,
            record.schemaVersion, record.seriesRef, record.episodeRef,
            record.sourcePlanRef, record.sourcePlanSchemaVersion, record.sourcePlanVersion,
            record.versionNumber, record.contentJson, record.changeKind,
            record.parentScriptVersionRef, record.createdAt,
        )

    @staticmethod
    def _acceptance_values(record: ScriptAcceptanceRecord) -> tuple[Any, ...]:
        return (
            record.workspaceRef,
            record.scriptRef,
            record.scriptVersionRef,
            record.acceptanceRef,
            record.schemaVersion,
            record.seriesRef,
            record.episodeRef,
            record.approvalRef,
            record.authorityDecisionRef,
            record.idempotencyKey,
            record.contentJson,
            record.payloadDigest,
            record.createdAt,
        )

    def create_script_with_version(self, script, version):
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    "INSERT INTO v5_scripts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._script_values(script),
                )
                connection.execute(
                    "INSERT INTO v5_script_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._version_values(version),
                )
        except sqlite3.IntegrityError as exc:
            if "FOREIGN KEY" in str(exc).upper():
                raise RecordNotFoundError("Episode was not found") from exc
            raise DuplicateRecordError("Script or ScriptVersion already exists") from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script write failed") from exc
        return script, version

    def append_version(self, updated_script, version, expected_script_version):
        try:
            with self._lock, self._write_session() as connection:
                row = connection.execute(
                    "SELECT version FROM v5_scripts WHERE workspace_ref = ? AND script_ref = ?",
                    (updated_script.workspaceRef, updated_script.scriptRef),
                ).fetchone()
                if row is None:
                    raise RecordNotFoundError("Script was not found")
                if row["version"] != expected_script_version:
                    raise VersionConflictError("Script version changed")
                connection.execute(
                    "INSERT INTO v5_script_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._version_values(version),
                )
                updated = connection.execute(
                    """
                    UPDATE v5_scripts
                    SET title = ?, current_script_version_ref = ?, updated_at = ?, version = ?
                    WHERE workspace_ref = ? AND script_ref = ? AND version = ?
                    """,
                    (
                        updated_script.title, updated_script.currentScriptVersionRef,
                        updated_script.updatedAt, updated_script.version,
                        updated_script.workspaceRef, updated_script.scriptRef,
                        expected_script_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError("Script version changed")
        except sqlite3.IntegrityError as exc:
            if "FOREIGN KEY" in str(exc).upper():
                raise RecordNotFoundError("Episode was not found") from exc
            raise DuplicateRecordError("ScriptVersion already exists") from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("ScriptVersion write failed") from exc
        return updated_script, version

    def confirm_version(self, updated_script, expected_script_version):
        try:
            with self._lock, self._write_session() as connection:
                version = connection.execute(
                    """
                    SELECT 1 FROM v5_script_versions
                    WHERE workspace_ref = ? AND script_ref = ? AND script_version_ref = ?
                    """,
                    (
                        updated_script.workspaceRef,
                        updated_script.scriptRef,
                        updated_script.confirmedScriptVersionRef,
                    ),
                ).fetchone()
                if version is None:
                    raise RecordNotFoundError("ScriptVersion was not found")
                updated = connection.execute(
                    """
                    UPDATE v5_scripts
                    SET confirmed_script_version_ref = ?, updated_at = ?, version = ?
                    WHERE workspace_ref = ? AND script_ref = ? AND version = ?
                    """,
                    (
                        updated_script.confirmedScriptVersionRef,
                        updated_script.updatedAt,
                        updated_script.version,
                        updated_script.workspaceRef,
                        updated_script.scriptRef,
                        expected_script_version,
                    ),
                )
                if updated.rowcount != 1:
                    raise VersionConflictError("Script version changed")
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script confirmation failed") from exc
        return updated_script

    def accept_reviewed_import(
        self, updated_script, acceptance, expected_script_version
    ):
        try:
            with self._lock, self._write_session() as connection:
                row = connection.execute(
                    "SELECT * FROM v5_scripts "
                    "WHERE workspace_ref=? AND script_ref=?",
                    (updated_script.workspaceRef, updated_script.scriptRef),
                ).fetchone()
                if row is None:
                    raise RecordNotFoundError("Script was not found")
                current = self._script(row)
                existing_row = connection.execute(
                    "SELECT * FROM v5_script_acceptances "
                    "WHERE workspace_ref=? AND script_ref=? "
                    "AND script_version_ref=?",
                    (
                        acceptance.workspaceRef,
                        acceptance.scriptRef,
                        acceptance.scriptVersionRef,
                    ),
                ).fetchone()
                idempotent_row = connection.execute(
                    "SELECT * FROM v5_script_acceptances "
                    "WHERE workspace_ref=? AND idempotency_key=?",
                    (acceptance.workspaceRef, acceptance.idempotencyKey),
                ).fetchone()
                if existing_row is not None or idempotent_row is not None:
                    replay = self._acceptance(existing_row or idempotent_row)
                    if (
                        not _same_acceptance_request(replay, acceptance)
                        or current.confirmedScriptVersionRef
                        != acceptance.scriptVersionRef
                    ):
                        raise VersionConflictError(
                            "Script acceptance idempotency content changed"
                        )
                    return current, replay, True
                if current.version != expected_script_version:
                    raise VersionConflictError("Script version changed")
                version = connection.execute(
                    "SELECT 1 FROM v5_script_versions "
                    "WHERE workspace_ref=? AND script_ref=? "
                    "AND script_version_ref=?",
                    (
                        acceptance.workspaceRef,
                        acceptance.scriptRef,
                        acceptance.scriptVersionRef,
                    ),
                ).fetchone()
                if version is None:
                    raise RecordNotFoundError("ScriptVersion was not found")
                connection.execute(
                    "INSERT INTO v5_script_acceptances VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    self._acceptance_values(acceptance),
                )
                changed = connection.execute(
                    "UPDATE v5_scripts SET confirmed_script_version_ref=?, "
                    "updated_at=?, version=? WHERE workspace_ref=? "
                    "AND script_ref=? AND version=?",
                    (
                        updated_script.confirmedScriptVersionRef,
                        updated_script.updatedAt,
                        updated_script.version,
                        updated_script.workspaceRef,
                        updated_script.scriptRef,
                        expected_script_version,
                    ),
                )
                if changed.rowcount != 1:
                    raise VersionConflictError("Script version changed")
        except sqlite3.IntegrityError as exc:
            raise VersionConflictError(
                "Script acceptance identity already exists"
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script acceptance write failed") from exc
        return updated_script, acceptance, False

    def lifecycle_has_episode_dependency(self, workspace_ref, series_ref, episode_ref):
        with self._session() as connection:
            return connection.execute(
                "SELECT 1 FROM v5_scripts WHERE workspace_ref=? AND series_ref=? AND episode_ref=? LIMIT 1",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone() is not None or connection.execute(
                "SELECT 1 FROM v5_script_versions WHERE workspace_ref=? AND series_ref=? AND episode_ref=? LIMIT 1",
                (workspace_ref, series_ref, episode_ref),
            ).fetchone() is not None

    def lifecycle_has_series_dependency(self, workspace_ref, series_ref):
        with self._session() as connection:
            return connection.execute(
                "SELECT 1 FROM v5_scripts WHERE workspace_ref=? AND series_ref=? LIMIT 1",
                (workspace_ref, series_ref),
            ).fetchone() is not None or connection.execute(
                "SELECT 1 FROM v5_script_versions WHERE workspace_ref=? AND series_ref=? LIMIT 1",
                (workspace_ref, series_ref),
            ).fetchone() is not None

    def get_script(self, workspace_ref, series_ref, episode_ref):
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT * FROM v5_scripts
                WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?
                """,
                (workspace_ref, series_ref, episode_ref),
            ).fetchone()
        return self._script(row) if row else None

    def get_script_by_ref(self, workspace_ref, script_ref):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_scripts WHERE workspace_ref = ? AND script_ref = ?",
                (workspace_ref, script_ref),
            ).fetchone()
        return self._script(row) if row else None

    def get_version(self, workspace_ref, script_ref, version_ref):
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT * FROM v5_script_versions
                WHERE workspace_ref = ? AND script_ref = ? AND script_version_ref = ?
                """,
                (workspace_ref, script_ref, version_ref),
            ).fetchone()
        return self._version(row) if row else None

    def list_versions(self, workspace_ref, script_ref):
        with self._session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM v5_script_versions
                WHERE workspace_ref = ? AND script_ref = ? ORDER BY version_number
                """,
                (workspace_ref, script_ref),
            ).fetchall()
        return [self._version(row) for row in rows]

    def get_acceptance(self, workspace_ref, script_ref, version_ref):
        try:
            with self._session() as connection:
                row = connection.execute(
                    "SELECT * FROM v5_script_acceptances "
                    "WHERE workspace_ref=? AND script_ref=? "
                    "AND script_version_ref=?",
                    (workspace_ref, script_ref, version_ref),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script acceptance read failed") from exc
        return self._acceptance(row) if row else None

    def get_acceptance_by_idempotency_key(
        self, workspace_ref, idempotency_key
    ):
        try:
            with self._session() as connection:
                row = connection.execute(
                    "SELECT * FROM v5_script_acceptances "
                    "WHERE workspace_ref=? AND idempotency_key=?",
                    (workspace_ref, idempotency_key),
                ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise RepositoryWriteError("Script acceptance read failed") from exc
        return self._acceptance(row) if row else None


class ScriptStudioService:
    """V5 owner for Script identity, immutable versions, and confirmation refs."""

    def __init__(
        self,
        repository: ScriptStudioRepository,
        upstream: UpstreamReader,
        *,
        acceptance_authority: ScriptAcceptanceAuthorityPort | None = None,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.upstream = upstream
        self.acceptance_authority = (
            acceptance_authority or RejectingScriptAcceptanceAuthority()
        )
        self._m6_episode_baseline_reader = None
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    def bind_m6_episode_baseline_reader(self, reader: Any) -> None:
        if self._m6_episode_baseline_reader is not None:
            raise RuntimeError("M6 Episode baseline reader is already bound")
        if reader is None or not callable(
            getattr(reader, "get_active_episode_baseline", None)
        ):
            raise RuntimeError("M6 Episode baseline reader is unavailable")
        self._m6_episode_baseline_reader = reader

    def resolve_current_m6_consumer_context(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        project = _required_ref(project_ref, "projectRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        if self._m6_episode_baseline_reader is None:
            raise M6ConsumerReadError("m6_consumer_authority_unavailable")
        try:
            baseline = self._m6_episode_baseline_reader.get_active_episode_baseline(
                workspace, project, series, episode
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            allowed = {
                "m6_baseline_not_available",
                "m6_episode_mapping_unavailable",
                "m6_baseline_stale",
                "m6_lineage_mismatch",
                "m6_consumer_authority_unavailable",
            }
            raise M6ConsumerReadError(
                code if code in allowed else "m6_consumer_internal_error"
            ) from None
        binding = build_m6_consumer_binding(
            baseline,
            workspace_ref=workspace,
            project_ref=project,
            series_ref=series,
            episode_ref=episode,
        )
        facts = baseline.get("applicableFacts")
        if not isinstance(facts, Mapping):
            raise M6ConsumerReadError("m6_lineage_mismatch")
        return {
            "m6ConsumerBinding": binding,
            "applicableFacts": json.loads(
                json.dumps(
                    facts,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            ),
        }

    def resolve_current_m6_consumer_binding(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        return self.resolve_current_m6_consumer_context(
            workspace_ref, project_ref, series_ref, episode_ref
        )["m6ConsumerBinding"]

    @staticmethod
    def _script_mapping(record: ScriptRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "seriesRef": record.seriesRef,
            "episodeRef": record.episodeRef,
            "scriptRef": record.scriptRef,
            "title": record.title,
            "currentScriptVersionRef": record.currentScriptVersionRef,
            "confirmedScriptVersionRef": record.confirmedScriptVersionRef,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    @staticmethod
    def _version_mapping(record: ScriptVersionRecord) -> dict[str, Any]:
        try:
            if record.schemaVersion not in {
                SCRIPT_VERSION_SCHEMA_VERSION,
                SCRIPT_VERSION_SCHEMA_VERSION_V2,
            }:
                raise ScriptStudioError("ScriptVersion schemaVersion is invalid")
            for field in (
                "workspaceRef",
                "seriesRef",
                "episodeRef",
                "scriptRef",
                "scriptVersionRef",
                "sourcePlanRef",
                "sourcePlanSchemaVersion",
            ):
                _required_ref(getattr(record, field), field)
            for field in ("sourcePlanVersion", "versionNumber"):
                value = getattr(record, field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ScriptStudioError(f"ScriptVersion {field} is invalid")
            if record.changeKind not in _SCRIPT_CHANGE_KINDS:
                raise ScriptStudioError("ScriptVersion changeKind is invalid")
            if record.versionNumber == 1:
                if (
                    record.parentScriptVersionRef is not None
                    or record.changeKind not in {"ai-generation", "reviewed-import"}
                ):
                    raise ScriptStudioError("initial ScriptVersion lineage is invalid")
            elif (
                record.changeKind in {"ai-generation", "reviewed-import"}
                or _required_ref(
                    record.parentScriptVersionRef, "parentScriptVersionRef"
                )
                == record.scriptVersionRef
            ):
                raise ScriptStudioError("derived ScriptVersion lineage is invalid")
            _required_text(record.createdAt, "createdAt", limit=100)
        except ScriptStudioError as exc:
            raise RepositoryWriteError(
                "persisted ScriptVersion envelope is invalid"
            ) from exc
        try:
            stored_content = json.loads(record.contentJson)
        except (TypeError, json.JSONDecodeError) as exc:
            raise RepositoryWriteError(
                "persisted ScriptVersion content is invalid"
            ) from exc
        content = _normalize_persisted_content(
            stored_content,
            schema_version=record.schemaVersion,
            reviewed_import=record.changeKind == "reviewed-import",
        )
        provenance = content.get("importProvenance")
        if record.changeKind == "reviewed-import":
            expected_provenance_fields = {
                "uploadedSourceByteDigest",
                "normalizedSourceDocumentDigest",
                "reviewedDocumentDigest",
                "importedByRef",
                "digestAssertionState",
                "reviewedDocumentToContentBindingState",
                "canonicalScriptContentDigest",
                "importProvenanceDigest",
            }
            if (
                not isinstance(provenance, Mapping)
                or set(provenance) != expected_provenance_fields
            ):
                raise RepositoryWriteError("reviewed import provenance is invalid")
            for field in (
                "uploadedSourceByteDigest",
                "normalizedSourceDocumentDigest",
                "reviewedDocumentDigest",
                "canonicalScriptContentDigest",
                "importProvenanceDigest",
            ):
                try:
                    _sha256_digest(provenance.get(field), field)
                except ScriptStudioError as exc:
                    raise RepositoryWriteError(
                        "reviewed import provenance is invalid"
                    ) from exc
            try:
                _required_ref(provenance.get("importedByRef"), "importedByRef")
            except ScriptStudioError as exc:
                raise RepositoryWriteError(
                    "reviewed import provenance is invalid"
                ) from exc
            canonical_content = {
                key: content[key]
                for key in (
                    "title",
                    "logline",
                    "synopsis",
                    "targetDurationSec",
                    "scenes",
                )
            }
            expected_digest = hashlib.sha256(
                json.dumps(
                    canonical_content,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            provenance_payload = {
                key: value
                for key, value in provenance.items()
                if key != "importProvenanceDigest"
            }
            expected_provenance_digest = hashlib.sha256(
                json.dumps(
                    provenance_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            if (
                provenance.get("canonicalScriptContentDigest") != expected_digest
                or provenance.get("importProvenanceDigest")
                != expected_provenance_digest
                or provenance.get("digestAssertionState")
                != "AUTHENTICATED_SERVICE_CREDENTIAL_DECLARATION_UNVERIFIED"
                or provenance.get("reviewedDocumentToContentBindingState")
                != "NOT_VERIFIED"
            ):
                raise RepositoryWriteError(
                    "reviewed import provenance verification failed"
                )
        elif "importProvenance" in content:
            raise RepositoryWriteError(
                "non-import ScriptVersion contains reviewed import provenance"
            )
        projection = {field: content[field] for field in _SCRIPT_CONTENT_FIELDS}
        if record.changeKind == "reviewed-import":
            projection["importProvenance"] = provenance
        if record.schemaVersion == SCRIPT_VERSION_SCHEMA_VERSION_V2:
            projection["m6ConsumerBinding"] = content["m6ConsumerBinding"]
        # Record-owned identity and scope are applied last and cannot be
        # overridden by contentJson, even if storage is externally corrupted.
        projection.update(
            {
                "schemaVersion": record.schemaVersion,
                "workspaceRef": record.workspaceRef,
                "seriesRef": record.seriesRef,
                "episodeRef": record.episodeRef,
                "scriptRef": record.scriptRef,
                "scriptVersionRef": record.scriptVersionRef,
                "sourcePlanRef": record.sourcePlanRef,
                "sourcePlanSchemaVersion": record.sourcePlanSchemaVersion,
                "sourcePlanVersion": record.sourcePlanVersion,
                "versionNumber": record.versionNumber,
                "changeKind": record.changeKind,
                "parentScriptVersionRef": record.parentScriptVersionRef,
                "createdAt": record.createdAt,
            }
        )
        return projection

    @classmethod
    def _lineage_version_mapping(
        cls,
        record: ScriptVersionRecord,
        *,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
        script_ref: str,
        bootstrap: Mapping[str, Any],
    ) -> dict[str, Any]:
        projection = cls._version_mapping(record)
        if (
            projection["workspaceRef"] != workspace_ref
            or projection["seriesRef"] != series_ref
            or projection["episodeRef"] != episode_ref
            or projection["scriptRef"] != script_ref
            or projection["sourcePlanRef"] != bootstrap.get("sourcePlanRef")
            or projection["sourcePlanSchemaVersion"]
            != bootstrap.get("sourcePlanSchemaVersion")
            or projection["sourcePlanVersion"] != bootstrap.get("sourcePlanVersion")
        ):
            raise RepositoryWriteError(
                "persisted ScriptVersion lineage does not match current Episode context"
            )
        return projection

    def _bootstrap(self, workspace: str, series: str, episode: str) -> Mapping[str, Any]:
        bootstrap = _validate_bootstrap(
            self.upstream.build_script_studio_bootstrap(workspace, series, episode)
        )
        if (
            bootstrap["workspaceRef"] != workspace
            or bootstrap["seriesRef"] != series
            or bootstrap["episodeRef"] != episode
        ):
            raise ScopeMismatchError("Script Studio bootstrap scope does not match")
        return bootstrap

    def get_workspace(self, workspace_ref: str, series_ref: str, episode_ref: str) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        bootstrap = dict(self._bootstrap(workspace, series, episode))
        script = self.repository.get_script(workspace, series, episode)
        if script is None:
            return {"bootstrap": bootstrap, "script": None, "versions": []}
        return {
            "bootstrap": bootstrap,
            "script": self._script_mapping(script),
            "versions": [
                self._lineage_version_mapping(
                    item,
                    workspace_ref=workspace,
                    series_ref=series,
                    episode_ref=episode,
                    script_ref=script.scriptRef,
                    bootstrap=bootstrap,
                )
                for item in self.repository.list_versions(workspace, script.scriptRef)
            ],
        }

    def create_version(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ScriptStudioError("version input must be an object")
        _reject_client_m6_fields(value)
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series = _required_ref(value.get("seriesRef"), "seriesRef")
        episode = _required_ref(value.get("episodeRef"), "episodeRef")
        project = (
            _required_ref(value.get("projectRef"), "projectRef")
            if value.get("projectRef") is not None
            else None
        )
        change_kind = _required_text(value.get("changeKind"), "changeKind", limit=40)
        if change_kind not in _SCRIPT_CHANGE_KINDS:
            raise ScriptStudioError("changeKind is invalid")
        bootstrap = self._bootstrap(workspace, series, episode)
        existing = self.repository.get_script(workspace, series, episode)
        now = self._clock()
        if existing is None:
            if change_kind not in {"ai-generation", "reviewed-import"}:
                raise RecordNotFoundError("Script must be generated before editing")
            import_provenance = None
            if change_kind == "reviewed-import":
                import_provenance = {
                    "uploadedSourceByteDigest": _sha256_digest(
                        value.get("uploadedSourceByteDigest"),
                        "uploadedSourceByteDigest",
                    ),
                    "normalizedSourceDocumentDigest": _sha256_digest(
                        value.get("normalizedSourceDocumentDigest"),
                        "normalizedSourceDocumentDigest",
                    ),
                    "reviewedDocumentDigest": _sha256_digest(
                        value.get("reviewedDocumentDigest"),
                        "reviewedDocumentDigest",
                    ),
                    "importedByRef": _required_ref(
                        value.get("importedByRef"), "importedByRef"
                    ),
                    "digestAssertionState": (
                        "AUTHENTICATED_SERVICE_CREDENTIAL_DECLARATION_UNVERIFIED"
                    ),
                    "reviewedDocumentToContentBindingState": "NOT_VERIFIED",
                }
            script_ref = self._ref_factory("script")
            version_ref = self._ref_factory("script-version")
            content = _normalize_content(
                value.get("content"),
                bootstrap=bootstrap,
                ref_factory=self._ref_factory,
            )
            schema_version = SCRIPT_VERSION_SCHEMA_VERSION
            if project is not None:
                content["m6ConsumerBinding"] = (
                    self.resolve_current_m6_consumer_binding(
                        workspace, project, series, episode
                    )
                )
                schema_version = SCRIPT_VERSION_SCHEMA_VERSION_V2
            if import_provenance is not None:
                import_provenance["canonicalScriptContentDigest"] = hashlib.sha256(
                    json.dumps(
                        {
                            field: content[field]
                            for field in _SCRIPT_CONTENT_FIELDS
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest()
                import_provenance["importProvenanceDigest"] = hashlib.sha256(
                    json.dumps(
                        import_provenance,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest()
                content["importProvenance"] = import_provenance
            script = ScriptRecord(
                SCRIPT_SCHEMA_VERSION,
                workspace,
                series,
                episode,
                script_ref,
                content["title"],
                version_ref,
                None,
                now,
                now,
                1,
            )
            version = ScriptVersionRecord(
                schema_version,
                workspace,
                series,
                episode,
                script_ref,
                version_ref,
                bootstrap["sourcePlanRef"],
                bootstrap["sourcePlanSchemaVersion"],
                bootstrap["sourcePlanVersion"],
                1,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                change_kind,
                None,
                now,
            )
            stored_script, stored_version = self.repository.create_script_with_version(script, version)
        else:
            if change_kind == "reviewed-import":
                raise DuplicateRecordError(
                    "reviewed import is allowed only for the first ScriptVersion"
                )
            supplied_script = _required_ref(value.get("scriptRef"), "scriptRef")
            if supplied_script != existing.scriptRef:
                raise ScopeMismatchError("scriptRef does not belong to Episode")
            parent_ref = _required_ref(value.get("baseScriptVersionRef"), "baseScriptVersionRef")
            parent = self.repository.get_version(workspace, existing.scriptRef, parent_ref)
            if parent is None:
                raise RecordNotFoundError("base ScriptVersion was not found")
            parent_mapping = self._lineage_version_mapping(
                parent,
                workspace_ref=workspace,
                series_ref=series,
                episode_ref=episode,
                script_ref=existing.scriptRef,
                bootstrap=bootstrap,
            )
            parent_binding = parent_mapping.get("m6ConsumerBinding")
            if parent_binding is not None and project is None:
                raise ScriptStudioError(
                    "projectRef is required when deriving an M6-bound ScriptVersion"
                )
            if (
                parent_binding is not None
                and parent_binding.get("projectRef") != project
            ):
                raise ScopeMismatchError(
                    "projectRef does not match the M6-bound Script lineage"
                )
            version_records = self.repository.list_versions(
                workspace, existing.scriptRef
            )
            version_mappings: dict[str, dict[str, Any]] = {}
            version_numbers: list[int] = []
            listed_parent: ScriptVersionRecord | None = None
            for record in version_records:
                mapping = self._lineage_version_mapping(
                    record,
                    workspace_ref=workspace,
                    series_ref=series,
                    episode_ref=episode,
                    script_ref=existing.scriptRef,
                    bootstrap=bootstrap,
                )
                version_ref = mapping["scriptVersionRef"]
                if version_ref in version_mappings:
                    raise RepositoryWriteError(
                        "persisted ScriptVersion identity is ambiguous"
                    )
                version_mappings[version_ref] = mapping
                version_numbers.append(mapping["versionNumber"])
                if version_ref == parent_ref:
                    listed_parent = record
            if (
                listed_parent != parent
                or version_mappings.get(parent_ref) != parent_mapping
                or sorted(version_numbers) != list(range(1, len(version_records) + 1))
                or existing.currentScriptVersionRef not in version_mappings
            ):
                raise RepositoryWriteError(
                    "persisted ScriptVersion lineage is incomplete"
                )
            refs = {
                scene["scriptSceneRef"] for scene in parent_mapping["scenes"]
            }
            content = _normalize_content(
                value.get("content"),
                bootstrap=bootstrap,
                ref_factory=self._ref_factory,
                existing_scene_refs=refs,
            )
            schema_version = SCRIPT_VERSION_SCHEMA_VERSION
            if project is not None:
                content["m6ConsumerBinding"] = (
                    self.resolve_current_m6_consumer_binding(
                        workspace, project, series, episode
                    )
                )
                schema_version = SCRIPT_VERSION_SCHEMA_VERSION_V2
            next_number = max(version_numbers) + 1
            version_ref = self._ref_factory("script-version")
            version = ScriptVersionRecord(
                schema_version,
                workspace,
                series,
                episode,
                existing.scriptRef,
                version_ref,
                bootstrap["sourcePlanRef"],
                bootstrap["sourcePlanSchemaVersion"],
                bootstrap["sourcePlanVersion"],
                next_number,
                json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                change_kind,
                parent_ref,
                now,
            )
            updated = replace(
                existing,
                title=content["title"],
                currentScriptVersionRef=version_ref,
                updatedAt=now,
                version=existing.version + 1,
            )
            stored_script, stored_version = self.repository.append_version(
                updated,
                version,
                existing.version,
            )
        return {
            "script": self._script_mapping(stored_script),
            "scriptVersion": self._lineage_version_mapping(
                stored_version,
                workspace_ref=workspace,
                series_ref=series,
                episode_ref=episode,
                script_ref=stored_script.scriptRef,
                bootstrap=bootstrap,
            ),
        }

    def confirm_version(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping) or value.get("humanConfirmed") is not True:
            raise ScriptStudioError("explicit human confirmation is required")
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series = _required_ref(value.get("seriesRef"), "seriesRef")
        episode = _required_ref(value.get("episodeRef"), "episodeRef")
        script_ref = _required_ref(value.get("scriptRef"), "scriptRef")
        version_ref = _required_ref(value.get("scriptVersionRef"), "scriptVersionRef")
        script = self.repository.get_script(workspace, series, episode)
        if script is None or script.scriptRef != script_ref:
            raise RecordNotFoundError("Script was not found")
        version = self.repository.get_version(workspace, script_ref, version_ref)
        if version is None or version.seriesRef != series or version.episodeRef != episode:
            raise RecordNotFoundError("ScriptVersion was not found")
        versions = self.repository.list_versions(workspace, script_ref)
        if versions and versions[0].changeKind == "reviewed-import":
            raise TrustedApprovalRequiredError(
                "reviewed-import lineage requires a trusted approval resolver"
            )
        updated = replace(
            script,
            confirmedScriptVersionRef=version_ref,
            updatedAt=self._clock(),
            version=script.version + 1,
        )
        stored = self.repository.confirm_version(updated, script.version)
        return {
            "script": self._script_mapping(stored),
            "confirmedVersion": self._version_mapping(version),
        }

    def accept_reviewed_import(self, value: Mapping[str, Any]) -> dict[str, Any]:
        fields = {
            "workspaceRef",
            "seriesRef",
            "episodeRef",
            "scriptRef",
            "scriptVersionRef",
            "idempotencyKey",
            "approvalRef",
        }
        if not isinstance(value, Mapping) or set(value) != fields:
            raise ScriptStudioError(
                "reviewed Script acceptance fields are invalid"
            )
        workspace = _required_ref(value.get("workspaceRef"), "workspaceRef")
        series = _required_ref(value.get("seriesRef"), "seriesRef")
        episode = _required_ref(value.get("episodeRef"), "episodeRef")
        script_ref = _required_ref(value.get("scriptRef"), "scriptRef")
        version_ref = _required_ref(
            value.get("scriptVersionRef"), "scriptVersionRef"
        )
        idempotency_key = _required_ref(
            value.get("idempotencyKey"), "idempotencyKey"
        )
        approval_ref = _required_ref(value.get("approvalRef"), "approvalRef")
        script = self.repository.get_script(workspace, series, episode)
        if script is None or script.scriptRef != script_ref:
            raise RecordNotFoundError("Script was not found")
        version = self.repository.get_version(workspace, script_ref, version_ref)
        if (
            version is None
            or version.seriesRef != series
            or version.episodeRef != episode
            or version.changeKind != "reviewed-import"
            or version.versionNumber != 1
            or version.parentScriptVersionRef is not None
        ):
            raise RecordNotFoundError(
                "reviewed-import ScriptVersion was not found"
            )
        version_mapping = self._version_mapping(version)
        provenance = version_mapping.get("importProvenance")
        if not isinstance(provenance, Mapping):
            raise RepositoryWriteError(
                "reviewed import provenance is unavailable"
            )
        subject = ScriptAcceptanceSubject.create(
            workspaceRef=workspace,
            seriesRef=series,
            episodeRef=episode,
            scriptRef=script_ref,
            scriptVersionRef=version_ref,
            uploadedSourceByteDigest=provenance.get(
                "uploadedSourceByteDigest"
            ),
            normalizedSourceDocumentDigest=provenance.get(
                "normalizedSourceDocumentDigest"
            ),
            reviewedDocumentDigest=provenance.get("reviewedDocumentDigest"),
            canonicalScriptContentDigest=provenance.get(
                "canonicalScriptContentDigest"
            ),
            importProvenanceDigest=provenance.get("importProvenanceDigest"),
        )
        by_subject = self.repository.get_acceptance(
            workspace, script_ref, version_ref
        )
        by_idempotency = self.repository.get_acceptance_by_idempotency_key(
            workspace, idempotency_key
        )
        if by_subject is not None or by_idempotency is not None:
            existing = by_subject or by_idempotency
            if by_subject is not None and by_idempotency is not None and (
                by_subject != by_idempotency
            ):
                raise VersionConflictError(
                    "Script acceptance idempotency content changed"
                )
            acceptance = _acceptance_mapping(existing)
            if (
                existing.scriptRef != script_ref
                or existing.scriptVersionRef != version_ref
                or existing.idempotencyKey != idempotency_key
                or existing.approvalRef != approval_ref
                or acceptance.get("subjectDigest") != subject.subject_digest
                or script.confirmedScriptVersionRef != version_ref
            ):
                raise VersionConflictError(
                    "Script acceptance idempotency content changed"
                )
            return {
                "script": self._script_mapping(script),
                "confirmedVersion": version_mapping,
                "scriptAcceptance": acceptance,
                "idempotentReplay": True,
            }
        if script.confirmedScriptVersionRef is not None:
            raise VersionConflictError("Script already has a confirmed version")
        approval = self.acceptance_authority.verify(
            subject=subject,
            approval_ref=approval_ref,
        )
        if not isinstance(approval, VerifiedScriptAcceptance) or not approval.matches(
            subject=subject,
            approval_ref=approval_ref,
        ):
            raise TrustedApprovalRequiredError(
                "reviewed Script acceptance was not resolved for the exact subject"
            )
        now = self._clock()
        content = {
            "uploadedSourceByteDigest": subject.uploadedSourceByteDigest,
            "normalizedSourceDocumentDigest": (
                subject.normalizedSourceDocumentDigest
            ),
            "reviewedDocumentDigest": subject.reviewedDocumentDigest,
            "canonicalScriptContentDigest": (
                subject.canonicalScriptContentDigest
            ),
            "importProvenanceDigest": subject.importProvenanceDigest,
            "subjectDigest": subject.subject_digest,
            "authorityRef": approval.authorityRef,
            "actorRef": approval.actorRef,
            "actorKind": approval.actorKind,
            "decision": approval.decision,
            "authorityDecisionDigest": approval.authorityDecisionDigest,
            "decidedAt": approval.decidedAt,
            "governanceRecordRef": approval.governanceRecordRef,
            "publicationAllowed": False,
        }
        envelope = {
            "schemaVersion": SCRIPT_ACCEPTANCE_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "seriesRef": series,
            "episodeRef": episode,
            "scriptRef": script_ref,
            "scriptVersionRef": version_ref,
            "acceptanceRef": _required_ref(
                self._ref_factory("script-acceptance"), "acceptanceRef"
            ),
            "approvalRef": approval.approvalRef,
            "authorityDecisionRef": approval.authorityDecisionRef,
            "idempotencyKey": idempotency_key,
            **content,
            "createdAt": now,
        }
        record = ScriptAcceptanceRecord(
            SCRIPT_ACCEPTANCE_SCHEMA_VERSION,
            workspace,
            series,
            episode,
            script_ref,
            version_ref,
            envelope["acceptanceRef"],
            approval.approvalRef,
            approval.authorityDecisionRef,
            idempotency_key,
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            _canonical_digest(envelope),
            now,
        )
        _acceptance_mapping(record)
        updated = replace(
            script,
            confirmedScriptVersionRef=version_ref,
            updatedAt=now,
            version=script.version + 1,
        )
        stored_script, stored_acceptance, replayed = (
            self.repository.accept_reviewed_import(
                updated,
                record,
                script.version,
            )
        )
        return {
            "script": self._script_mapping(stored_script),
            "confirmedVersion": version_mapping,
            "scriptAcceptance": _acceptance_mapping(stored_acceptance),
            "idempotentReplay": replayed,
        }

    def build_storyboard_bootstrap(
        self,
        workspace_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        series = _required_ref(series_ref, "seriesRef")
        episode = _required_ref(episode_ref, "episodeRef")
        script = self.repository.get_script(workspace, series, episode)
        if script is None:
            raise RecordNotFoundError("Script was not found")
        if script.confirmedScriptVersionRef is None:
            raise ScriptNotConfirmedError("confirmed ScriptVersion is required")
        version = self.repository.get_version(
            workspace,
            script.scriptRef,
            script.confirmedScriptVersionRef,
        )
        if version is None:
            raise RecordNotFoundError("confirmed ScriptVersion was not found")
        content = self._version_mapping(version)
        return {
            "schemaVersion": STORYBOARD_BOOTSTRAP_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "seriesRef": series,
            "episodeRef": episode,
            "scriptRef": script.scriptRef,
            "scriptVersionRef": version.scriptVersionRef,
            "sourcePlanRef": version.sourcePlanRef,
            "sourcePlanSchemaVersion": version.sourcePlanSchemaVersion,
            "sourcePlanVersion": version.sourcePlanVersion,
            "title": content["title"],
            "logline": content["logline"],
            "synopsis": content["synopsis"],
            "targetDurationSec": content["targetDurationSec"],
            "scenes": content["scenes"],
            "nextGate": "m4-ip-character-binding-required",
            "storyboardProductionAuthorized": False,
        }
