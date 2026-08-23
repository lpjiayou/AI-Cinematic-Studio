"""V5-owned M6 Series Intelligence domain model and service."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from .canonical import digest, normalize
from .contracts import (
    ApprovalAuthorityPort,
    ConfirmedM6SourceReader,
    IdentityAuthorizationPort,
    M6ConsumerContextReader,
    M6Scope,
    M6ScopeAuthorityPort,
    SeriesIntelligenceRepository,
)
from .errors import (
    ConfirmationRequiredError,
    DuplicateRecordError,
    InvalidReferenceError,
    IdentityBindingDeniedError,
    M6BaselineNotAvailableError,
    M6BaselineStaleError,
    M6ConsumerAuthorityUnavailableError,
    M6EpisodeMappingUnavailableError,
    M6LineageMismatchError,
    RecordNotFoundError,
    ScopeMismatchError,
    SeriesIntelligenceError,
    StaleSourceError,
    VersionConflictError,
)
SERIES_BIBLE_SCHEMA_VERSION = "v5.series-bible.v1"
SERIES_BIBLE_VERSION_SCHEMA_VERSION = "v5.series-bible-version.v1"
CHARACTER_CONTINUITY_SCHEMA_VERSION = "v5.character-continuity.v1"
CHARACTER_CONTINUITY_VERSION_SCHEMA_VERSION = "v5.character-continuity-version.v1"
M6_BASELINE_SCHEMA_VERSION = "v5.m6-baseline-snapshot.v1"
M6_EVENT_SCHEMA_VERSION = "v5.m6-series-intelligence-event.v1"
M6_EPISODE_BASELINE_SCHEMA_VERSION = "v5.m6-episode-baseline-input.v1"
CANONICAL_SCHEMA_VERSION = "canonical-json-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _text(value: Any, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    result = str(value or "").strip()
    normalized = normalize(result)
    if not isinstance(normalized, str):
        raise SeriesIntelligenceError(f"{field} is invalid")
    result = normalized
    if not result:
        if optional:
            return None
        raise SeriesIntelligenceError(f"{field} is required")
    if len(result) > 8000:
        raise SeriesIntelligenceError(f"{field} is too long")
    return result


def _ref(value: Any, field: str) -> str:
    result = _text(value, field)
    assert isinstance(result, str)
    if len(result) > 240 or not result.isprintable() or any(item.isspace() for item in result):
        raise SeriesIntelligenceError(f"{field} is invalid")
    return result


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise SeriesIntelligenceError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SeriesIntelligenceError(f"{field} must be an integer") from exc
    if result < 1:
        raise SeriesIntelligenceError(f"{field} must be positive")
    return result


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise SeriesIntelligenceError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SeriesIntelligenceError(f"{field} must be an integer") from exc
    if result < 0:
        raise SeriesIntelligenceError(f"{field} must not be negative")
    return result


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SeriesIntelligenceError(f"{field} must be an object")
    return dict(value)


def _mapping_list(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise SeriesIntelligenceError(f"{field} must be an object array")
    return [dict(item) for item in value]


def _operation(command: Mapping[str, Any]) -> tuple[str, str]:
    return _ref(command.get("operationRef"), "operationRef"), _ref(
        command.get("idempotencyKey"), "idempotencyKey"
    )


def _payload_digest(command: Mapping[str, Any]) -> str:
    return digest({
        key: value for key, value in command.items()
        if key not in {
            "operationRef", "idempotencyKey", "actorRef", "actorRole",
            "approvedBy", "humanConfirmed", "confirmedAt", "createdAt",
        }
    })


_BIBLE_COLLECTIONS = {
    "worldRules": "worldRuleRef",
    "glossaryTerms": "glossaryTermRef",
    "locations": "locationRef",
    "factions": "factionRef",
    "props": "propRef",
    "timelineEvents": "timelineEventRef",
    "visualConstraints": "visualConstraintRef",
    "prohibitedNarrativePatterns": "prohibitedNarrativePatternRef",
}


def _normalize_fact_sets(content: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"schemaVersion": "v5.series-bible-content.v1"}
    refs: dict[str, set[str]] = {}
    for field, ref_field in _BIBLE_COLLECTIONS.items():
        items = _mapping_list(content.get(field), field)
        seen: set[str] = set()
        normalized_items = []
        for index, item in enumerate(items):
            item_ref = _ref(item.get(ref_field), f"{field}[{index}].{ref_field}")
            if item_ref in seen:
                raise DuplicateRecordError(f"duplicate {ref_field}")
            seen.add(item_ref)
            normalized_items.append(normalize({**item, ref_field: item_ref}))
        normalized_items.sort(key=lambda item: item[ref_field])
        result[field] = normalized_items
        refs[field] = seen
    if not any(result[field] for field in _BIBLE_COLLECTIONS):
        raise SeriesIntelligenceError("SeriesBible requires structured facts")
    for event in result["timelineEvents"]:
        location_ref = event.get("locationRef")
        if location_ref is not None and location_ref not in refs["locations"]:
            raise InvalidReferenceError("timeline event location is unknown")
        for relation_field, target_field in (("factionRefs", "factions"), ("propRefs", "props")):
            values = event.get(relation_field, [])
            if not isinstance(values, list) or any(value not in refs[target_field] for value in values):
                raise InvalidReferenceError(f"timeline event {relation_field} is invalid")
    return result


def _normalize_character_content(
    content: Mapping[str, Any], *, bible_content: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = {"schemaVersion": "v5.character-continuity-content.v1"}
    definitions = _mapping_list(content.get("characters"), "characters")
    character_refs: set[str] = set()
    normalized_definitions = []
    for index, item in enumerate(definitions):
        character_ref = _ref(item.get("characterRef"), f"characters[{index}].characterRef")
        if character_ref in character_refs:
            raise DuplicateRecordError("duplicate characterRef")
        character_refs.add(character_ref)
        normalized_definitions.append(normalize({**item, "characterRef": character_ref}))
    normalized_definitions.sort(key=lambda item: item["characterRef"])
    if not normalized_definitions:
        raise SeriesIntelligenceError("CharacterContinuity requires CharacterDefinition facts")
    result["characters"] = normalized_definitions

    episode_refs = [item["episodePlanItemRef"] for item in source["episodePlanItems"]]
    positions = {item: index for index, item in enumerate(episode_refs)}
    locations = {item["locationRef"] for item in bible_content["locations"]}
    props = {item["propRef"] for item in bible_content["props"]}
    timeline_events = {item["timelineEventRef"] for item in bible_content["timelineEvents"]}
    for definition in normalized_definitions:
        for field, allowed in (
            ("locationRefs", locations), ("propRefs", props),
            ("timelineEventRefs", timeline_events),
        ):
            values = definition.get(field, [])
            if not isinstance(values, list) or any(value not in allowed for value in values):
                raise InvalidReferenceError(f"character {field} is invalid")
    intervals = _mapping_list(content.get("stateIntervals"), "stateIntervals")
    normalized_intervals = []
    interval_refs: set[str] = set()
    exclusive: dict[tuple[str, str], list[tuple[int, int]]] = {}
    exclusive_categories = {"Location", "Health", "Appearance", "PrimaryGoal"}
    for index, item in enumerate(intervals):
        interval_ref = _ref(item.get("intervalRef"), f"stateIntervals[{index}].intervalRef")
        if interval_ref in interval_refs:
            raise DuplicateRecordError("duplicate intervalRef")
        interval_refs.add(interval_ref)
        character_ref = _ref(item.get("characterRef"), f"stateIntervals[{index}].characterRef")
        if character_ref not in character_refs:
            raise InvalidReferenceError("state interval character is unknown")
        category = _text(item.get("category"), f"stateIntervals[{index}].category")
        start = _ref(item.get("startEpisodePlanItemRef"), "startEpisodePlanItemRef")
        end_value = item.get("endEpisodePlanItemRef")
        end = _ref(end_value, "endEpisodePlanItemRef") if end_value else None
        if start not in positions or (end is not None and end not in positions):
            raise InvalidReferenceError("state interval EpisodePlanItem is unknown")
        start_index, end_index = positions[start], positions[end] if end else len(episode_refs)
        if start_index >= end_index:
            raise SeriesIntelligenceError("state interval must be start-inclusive/end-exclusive")
        if category == "Location" and item.get("valueRef") not in locations:
            raise InvalidReferenceError("state interval location is unknown")
        if category in exclusive_categories:
            existing = exclusive.setdefault((character_ref, str(category)), [])
            if any(start_index < old_end and old_start < end_index for old_start, old_end in existing):
                raise VersionConflictError("exclusive CharacterState intervals overlap")
            existing.append((start_index, end_index))
        normalized_intervals.append(normalize({
            **item,
            "intervalRef": interval_ref,
            "characterRef": character_ref,
            "category": category,
            "startEpisodePlanItemRef": start,
            "endEpisodePlanItemRef": end,
        }))
    normalized_intervals.sort(key=lambda item: item["intervalRef"])
    result["stateIntervals"] = normalized_intervals

    relationships = _mapping_list(content.get("relationships"), "relationships")
    normalized_relationships = []
    relationship_refs: set[str] = set()
    for index, item in enumerate(relationships):
        relationship_ref = _ref(item.get("relationshipRef"), f"relationships[{index}].relationshipRef")
        if relationship_ref in relationship_refs:
            raise DuplicateRecordError("duplicate relationshipRef")
        relationship_refs.add(relationship_ref)
        source_ref = _ref(item.get("fromCharacterRef"), "fromCharacterRef")
        target_ref = _ref(item.get("toCharacterRef"), "toCharacterRef")
        if source_ref not in character_refs or target_ref not in character_refs:
            raise InvalidReferenceError("relationship endpoint is unknown")
        if source_ref == target_ref:
            raise InvalidReferenceError("relationship must be directed between distinct characters")
        start_value = item.get("startEpisodePlanItemRef")
        end_value = item.get("endEpisodePlanItemRef")
        start_ref = _ref(start_value, "startEpisodePlanItemRef") if start_value else episode_refs[0]
        end_ref = _ref(end_value, "endEpisodePlanItemRef") if end_value else None
        if start_ref not in positions or (end_ref is not None and end_ref not in positions):
            raise InvalidReferenceError("relationship EpisodePlanItem is unknown")
        if positions[start_ref] >= (positions[end_ref] if end_ref else len(episode_refs)):
            raise SeriesIntelligenceError("relationship interval is invalid")
        normalized_relationships.append(normalize({
            **item,
            "relationshipRef": relationship_ref,
            "fromCharacterRef": source_ref,
            "toCharacterRef": target_ref,
            "startEpisodePlanItemRef": start_ref,
            "endEpisodePlanItemRef": end_ref,
        }))
    normalized_relationships.sort(key=lambda item: item["relationshipRef"])
    result["relationships"] = normalized_relationships
    bindings = _mapping_list(content.get("identityBindings"), "identityBindings")
    normalized_bindings = []
    allowed_binding_fields = {
        "identityBindingRef", "identityRef", "identityVersionRef", "identityDigest",
        "rightsGrantRef",
    }
    for index, item in enumerate(bindings):
        if set(item) - allowed_binding_fields:
            raise SeriesIntelligenceError("IdentityBinding stores only Ref, Version, Digest and RightsGrantRef")
        binding = {key: _ref(value, f"identityBindings[{index}].{key}") for key, value in item.items()}
        binding["identityBindingRef"] = _ref(
            item.get("identityBindingRef"), f"identityBindings[{index}].identityBindingRef"
        )
        normalized_bindings.append(normalize(binding))
    result["identityBindings"] = sorted(
        normalized_bindings, key=lambda item: item["identityBindingRef"]
    )
    return result


class SeriesIntelligenceService:
    def __init__(
        self,
        repository: SeriesIntelligenceRepository,
        source_reader: ConfirmedM6SourceReader,
        scope_authority: M6ScopeAuthorityPort,
        approval_authority: ApprovalAuthorityPort,
        identity_authority: IdentityAuthorizationPort,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.source_reader = source_reader
        self.scope_authority = scope_authority
        self.approval_authority = approval_authority
        self.identity_authority = identity_authority
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    def resolve_scope(self, command: Mapping[str, Any]) -> M6Scope:
        for untrusted in ("businessDomain", "tenantId", "ipUniverseRef"):
            if command.get(untrusted) not in (None, ""):
                raise ScopeMismatchError(f"{untrusted} must come from trusted authority")
        scope = self.scope_authority.resolve_scope(
            _ref(command.get("workspaceRef"), "workspaceRef"),
            _ref(command.get("projectRef"), "projectRef"),
            _ref(command.get("seriesRef"), "seriesRef"),
        )
        for value, field in (
            (scope.business_domain, "businessDomain"), (scope.tenant_id, "tenantId"),
            (scope.workspace_ref, "workspaceRef"), (scope.project_ref, "projectRef"),
            (scope.series_ref, "seriesRef"),
        ):
            _ref(value, field)
        if (
            scope.workspace_ref, scope.project_ref, scope.series_ref
        ) != (
            str(command.get("workspaceRef")), str(command.get("projectRef")),
            str(command.get("seriesRef")),
        ):
            raise ScopeMismatchError("trusted scope does not match requested scope")
        if scope.ip_universe_ref:
            raise ScopeMismatchError("ipUniverseRef is not accepted in M6-P1")
        return scope

    def source_for(self, scope: M6Scope) -> dict[str, Any]:
        try:
            source = self.source_reader.get_confirmed_m6_source_snapshot(
                scope.workspace_ref, scope.project_ref, scope.series_ref
            )
        except Exception as exc:
            if getattr(exc, "code", "") == "series_plan_not_confirmed":
                raise ConfirmationRequiredError("M5 source is not confirmed") from None
            raise ScopeMismatchError("confirmed M5 source is unavailable for trusted scope") from None
        if source.get("status") != "confirmed":
            raise ConfirmationRequiredError("M5 source is not confirmed")
        if (
            source.get("workspaceRef"), source.get("projectRef"), source.get("seriesRef")
        ) != (scope.workspace_ref, scope.project_ref, scope.series_ref):
            raise ScopeMismatchError("M5 source scope does not match trusted scope")
        return source

    def trusted_approval(self, scope: M6Scope, command: Mapping[str, Any], action: str):
        approval = self.approval_authority.verify_approval(
            scope=scope,
            approval_ref=_ref(command.get("approvalRef"), "approvalRef"),
            action=action,
        )
        if approval.actor_kind.strip().lower() in {
            "ai", "model", "provider", "ai-provider", "automation-provider"
        }:
            raise ConfirmationRequiredError("AI or Provider actors cannot confirm M6 facts")
        _ref(approval.actor_ref, "verified actorRef")
        return approval

    @staticmethod
    def _root_key(scope: M6Scope) -> tuple[str, ...]:
        return scope.key

    @staticmethod
    def _version_key(scope: M6Scope, root_ref: str, version_ref: str) -> tuple[str, ...]:
        return (*scope.key, root_ref, version_ref)

    def _idempotent(
        self,
        scope: M6Scope,
        command: Mapping[str, Any],
        operation_type: str,
        action: Callable[[], Any],
    ) -> Any:
        operation_ref, key = _operation(command)
        payload = _payload_digest(command)
        replay = self.repository.replay(
            scope.key, key, payload, operation_type=operation_type
        )
        if replay is not None:
            return replay
        return self.repository.record_operation(
            scope.key,
            key,
            payload,
            action(),
            operation_ref=operation_ref,
            operation_type=operation_type,
        )

    def create_bible_version(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "create-series-bible-version",
            lambda: self._create_bible(scope, command),
        )

    def _create_bible(self, scope, command):
        source = self.source_for(scope)
        content = _normalize_fact_sets(_mapping(command.get("content"), "content"))
        root_ref_value = command.get("seriesBibleRef")
        root_ref = _ref(root_ref_value, "seriesBibleRef") if root_ref_value else self._ref_factory("series-bible")
        return self._store_bible(scope, source, root_ref, content, command)

    def _store_bible(self, scope, source, root_ref, content, command):
        root_key = self._root_key(scope)
        root = self.repository.bibles.get(root_key)
        now = self._clock()
        if root is None:
            if command.get("seriesBibleRef"):
                raise RecordNotFoundError("SeriesBible was not found")
            version_number, parent_ref, revision = 1, None, 1
            created_at = now
        else:
            if root["seriesBibleRef"] != root_ref:
                raise DuplicateRecordError("SeriesBible already exists in scope")
            expected = _positive_int(command.get("expectedRevision"), "expectedRevision")
            if expected != root["revision"]:
                raise VersionConflictError()
            current = self.repository.bible_versions[
                self._version_key(scope, root_ref, root["currentSeriesBibleVersionRef"])
            ]
            requested_parent = command.get("baseSeriesBibleVersionRef")
            parent_ref = _ref(requested_parent, "baseSeriesBibleVersionRef") if requested_parent else current["seriesBibleVersionRef"]
            if self.repository.bible_versions.get(self._version_key(scope, root_ref, parent_ref)) is None:
                raise RecordNotFoundError("base SeriesBibleVersion was not found")
            version_number, revision = current["versionNumber"] + 1, expected + 1
            created_at = root["createdAt"]
        version_ref = self._ref_factory("series-bible-version")
        content_digest = digest({
            "schemaVersion": SERIES_BIBLE_VERSION_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "content": content,
        })
        version = {
            "schemaVersion": SERIES_BIBLE_VERSION_SCHEMA_VERSION,
            **scope.mapping(),
            "seriesBibleRef": root_ref,
            "seriesBibleVersionRef": version_ref,
            "versionNumber": version_number,
            "parentSeriesBibleVersionRef": parent_ref,
            "seriesPlanRef": source["seriesPlanRef"],
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "sourceSeriesPlanVersionRef": source["seriesPlanVersionRef"],
            "sourceSeriesPlanDigest": source["seriesPlanVersionDigest"],
            "canonicalSchemaVersion": CANONICAL_SCHEMA_VERSION,
            "contentDigest": content_digest,
            "canonicalDigest": content_digest,
            "content": content,
            "status": "CANDIDATE" if command.get("candidate") is True or command.get("baseSeriesBibleVersionRef") else "DRAFT",
            "createdAt": now,
            "confirmedAt": None,
            "approvalRef": None,
        }
        root = {
            "schemaVersion": SERIES_BIBLE_SCHEMA_VERSION,
            **scope.mapping(),
            "seriesBibleRef": root_ref,
            "currentSeriesBibleVersionRef": version_ref,
            "confirmedSeriesBibleVersionRef": root.get("confirmedSeriesBibleVersionRef") if root else None,
            "revision": revision,
            "createdAt": created_at,
            "updatedAt": now,
        }
        self.repository.bibles[root_key] = root
        self.repository.bible_versions[self._version_key(scope, root_ref, version_ref)] = version
        return {"root": deepcopy(root), "version": deepcopy(version)}

    def submit_bible_candidate(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "submit-series-bible-candidate",
            lambda: self._set_bible_status(scope, command, "CANDIDATE"),
        )

    def confirm_bible_version(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "confirm-series-bible-version",
            lambda: self._confirm_bible(scope, command),
        )

    def _set_bible_status(self, scope, command, status):
        root = self._bible_root(scope, command)
        expected = _positive_int(command.get("expectedRevision"), "expectedRevision")
        if root["revision"] != expected:
            raise VersionConflictError()
        version_ref = _ref(command.get("seriesBibleVersionRef"), "seriesBibleVersionRef")
        if version_ref != root["currentSeriesBibleVersionRef"]:
            raise VersionConflictError("only current Bible version can change status")
        key = self._version_key(scope, root["seriesBibleRef"], version_ref)
        version = self.repository.bible_versions[key]
        if version["status"] == "CONFIRMED" or (status == "CANDIDATE" and version["status"] != "DRAFT"):
            raise VersionConflictError("invalid Bible lifecycle transition")
        updated_version = {**version, "status": status}
        updated_root = {**root, "revision": expected + 1, "updatedAt": self._clock()}
        self.repository.bible_versions[key] = updated_version
        self.repository.bibles[scope.key] = updated_root
        return {"root": deepcopy(updated_root), "version": deepcopy(updated_version)}

    def _confirm_bible(self, scope, command):
        root = self._bible_root(scope, command)
        expected = _positive_int(command.get("expectedRevision"), "expectedRevision")
        if root["revision"] != expected:
            raise VersionConflictError()
        version_ref = _ref(command.get("seriesBibleVersionRef"), "seriesBibleVersionRef")
        key = self._version_key(scope, root["seriesBibleRef"], version_ref)
        version = self.repository.bible_versions.get(key)
        if version is None:
            raise RecordNotFoundError("SeriesBibleVersion was not found")
        if version_ref != root["currentSeriesBibleVersionRef"] or version["status"] != "CANDIDATE":
            raise ConfirmationRequiredError("only current candidate Bible version can be confirmed")
        source = self.source_for(scope)
        if (
            version["seriesPlanVersionRef"], version["seriesPlanVersionDigest"]
        ) != (source["seriesPlanVersionRef"], source["seriesPlanVersionDigest"]):
            raise StaleSourceError()
        approval = self.trusted_approval(scope, command, "confirm-series-bible-version")
        now = self._clock()
        updated_version = {
            **version, "status": "CONFIRMED", "confirmedAt": now,
            "approvalRef": approval.approval_ref,
        }
        updated_root = {
            **root, "confirmedSeriesBibleVersionRef": version_ref,
            "revision": expected + 1, "updatedAt": now,
        }
        self.repository.bible_versions[key] = updated_version
        self.repository.bibles[scope.key] = updated_root
        return {"root": deepcopy(updated_root), "version": deepcopy(updated_version)}

    def _bible_root(self, scope, command):
        root = self.repository.bibles.get(scope.key)
        if root is None or root["seriesBibleRef"] != _ref(command.get("seriesBibleRef"), "seriesBibleRef"):
            raise RecordNotFoundError("SeriesBible was not found")
        return root

    def create_character_version(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "create-character-continuity-version",
            lambda: self._create_character(scope, command),
        )

    def _create_character(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        source = self.source_for(scope)
        bible_ref = _ref(command.get("seriesBibleRef"), "seriesBibleRef")
        bible_version_ref = _ref(command.get("seriesBibleVersionRef"), "seriesBibleVersionRef")
        bible = self.repository.bible_versions.get(self._version_key(scope, bible_ref, bible_version_ref))
        if bible is None or bible["status"] != "CONFIRMED":
            raise ConfirmationRequiredError("CharacterContinuity requires a confirmed Bible version")
        if (
            bible["seriesPlanVersionRef"], bible["seriesPlanVersionDigest"]
        ) != (source["seriesPlanVersionRef"], source["seriesPlanVersionDigest"]):
            raise StaleSourceError()
        content = _normalize_character_content(
            _mapping(command.get("content"), "content"), bible_content=bible["content"], source=source
        )
        self.identity_authority.authorize_bindings(scope=scope, bindings=content["identityBindings"])
        if content["identityBindings"]:
            raise IdentityBindingDeniedError(
                "non-empty IdentityBinding is not authorized in bounded M6-P1"
            )
        root_ref_value = command.get("characterContinuityRef")
        root_ref = _ref(root_ref_value, "characterContinuityRef") if root_ref_value else self._ref_factory("character-continuity")
        return self._store_character(scope, source, bible, root_ref, content, command)

    def _store_character(self, scope, source, bible, root_ref, content, command):
        root = self.repository.characters.get(scope.key)
        now = self._clock()
        if root is None:
            if command.get("characterContinuityRef"):
                raise RecordNotFoundError("CharacterContinuity was not found")
            version_number, parent_ref, revision, created_at = 1, None, 1, now
        else:
            if root["characterContinuityRef"] != root_ref:
                raise DuplicateRecordError("CharacterContinuity already exists in scope")
            expected = _positive_int(command.get("expectedRevision"), "expectedRevision")
            if root["revision"] != expected:
                raise VersionConflictError()
            current = self.repository.character_versions[
                self._version_key(scope, root_ref, root["currentCharacterContinuityVersionRef"])
            ]
            requested_parent = command.get("baseCharacterContinuityVersionRef")
            parent_ref = _ref(requested_parent, "baseCharacterContinuityVersionRef") if requested_parent else current["characterContinuityVersionRef"]
            if self.repository.character_versions.get(self._version_key(scope, root_ref, parent_ref)) is None:
                raise RecordNotFoundError("base CharacterContinuityVersion was not found")
            previous_refs = {item["characterRef"] for item in current["content"]["characters"]}
            current_refs = {item["characterRef"] for item in content["characters"]}
            if previous_refs != current_refs:
                raise VersionConflictError("CharacterRef set must remain stable across versions")
            version_number, parent_ref, revision, created_at = (
                current["versionNumber"] + 1,
                parent_ref,
                expected + 1,
                root["createdAt"],
            )
        version_ref = self._ref_factory("character-continuity-version")
        content_digest = digest({
            "schemaVersion": CHARACTER_CONTINUITY_VERSION_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "seriesBibleVersionRef": bible["seriesBibleVersionRef"],
            "seriesBibleVersionDigest": bible["contentDigest"],
            "content": content,
        })
        version = {
            "schemaVersion": CHARACTER_CONTINUITY_VERSION_SCHEMA_VERSION,
            **scope.mapping(),
            "characterContinuityRef": root_ref,
            "characterContinuityVersionRef": version_ref,
            "versionNumber": version_number,
            "parentCharacterContinuityVersionRef": parent_ref,
            "seriesPlanRef": source["seriesPlanRef"],
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "sourceSeriesPlanVersionRef": source["seriesPlanVersionRef"],
            "sourceSeriesPlanDigest": source["seriesPlanVersionDigest"],
            "seriesBibleRef": bible["seriesBibleRef"],
            "seriesBibleVersionRef": bible["seriesBibleVersionRef"],
            "seriesBibleVersionDigest": bible["contentDigest"],
            "sourceSeriesBibleVersionRef": bible["seriesBibleVersionRef"],
            "sourceSeriesBibleVersionDigest": bible["contentDigest"],
            "canonicalSchemaVersion": CANONICAL_SCHEMA_VERSION,
            "contentDigest": content_digest,
            "canonicalDigest": content_digest,
            "content": content,
            "status": "CANDIDATE" if command.get("candidate") is True or command.get("baseCharacterContinuityVersionRef") else "DRAFT",
            "createdAt": now,
            "confirmedAt": None,
            "approvalRef": None,
        }
        root_record = {
            "schemaVersion": CHARACTER_CONTINUITY_SCHEMA_VERSION,
            **scope.mapping(),
            "characterContinuityRef": root_ref,
            "currentCharacterContinuityVersionRef": version_ref,
            "confirmedCharacterContinuityVersionRef": root.get("confirmedCharacterContinuityVersionRef") if root else None,
            "revision": revision,
            "createdAt": created_at,
            "updatedAt": now,
        }
        self.repository.characters[scope.key] = root_record
        self.repository.character_versions[self._version_key(scope, root_ref, version_ref)] = version
        return {"root": deepcopy(root_record), "version": deepcopy(version)}

    def submit_character_candidate(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "submit-character-continuity-candidate",
            lambda: self._set_character_status(scope, command, False),
        )

    def confirm_character_version(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "confirm-character-continuity-version",
            lambda: self._set_character_status(scope, command, True),
        )

    def _set_character_status(self, scope, command, confirm):
        root = self.repository.characters.get(scope.key)
        root_ref = _ref(command.get("characterContinuityRef"), "characterContinuityRef")
        if root is None or root["characterContinuityRef"] != root_ref:
            raise RecordNotFoundError("CharacterContinuity was not found")
        expected = _positive_int(command.get("expectedRevision"), "expectedRevision")
        if root["revision"] != expected:
            raise VersionConflictError()
        version_ref = _ref(command.get("characterContinuityVersionRef"), "characterContinuityVersionRef")
        if version_ref != root["currentCharacterContinuityVersionRef"]:
            raise VersionConflictError("only current CharacterContinuity version can change status")
        key = self._version_key(scope, root_ref, version_ref)
        version = self.repository.character_versions[key]
        now = self._clock()
        if confirm:
            if version["status"] != "CANDIDATE":
                raise ConfirmationRequiredError("only candidate CharacterContinuity can be confirmed")
            source = self.source_for(scope)
            if (
                version["seriesPlanVersionRef"], version["seriesPlanVersionDigest"]
            ) != (source["seriesPlanVersionRef"], source["seriesPlanVersionDigest"]):
                raise StaleSourceError()
            approval = self.trusted_approval(scope, command, "confirm-character-continuity-version")
            version = {**version, "status": "CONFIRMED", "confirmedAt": now, "approvalRef": approval.approval_ref}
            root = {**root, "confirmedCharacterContinuityVersionRef": version_ref}
        else:
            if version["status"] != "DRAFT":
                raise VersionConflictError("invalid CharacterContinuity lifecycle transition")
            version = {**version, "status": "CANDIDATE"}
        root = {**root, "revision": expected + 1, "updatedAt": now}
        self.repository.character_versions[key] = version
        self.repository.characters[scope.key] = root
        return {"root": deepcopy(root), "version": deepcopy(version)}

    def activate_baseline(self, scope: M6Scope, command: Mapping[str, Any]) -> dict[str, Any]:
        return self._idempotent(
            scope,
            command,
            "activate-m6-baseline",
            lambda: self._activate(scope, command),
        )

    def _activate(self, scope, command):
        source = self.source_for(scope)
        expected_activation_revision = _nonnegative_int(
            command.get("expectedActivationRevision"), "expectedActivationRevision"
        )
        bible_ref = _ref(command.get("seriesBibleRef"), "seriesBibleRef")
        bible_version_ref = _ref(command.get("seriesBibleVersionRef"), "seriesBibleVersionRef")
        character_ref = _ref(command.get("characterContinuityRef"), "characterContinuityRef")
        character_version_ref = _ref(command.get("characterContinuityVersionRef"), "characterContinuityVersionRef")
        bible = self.repository.bible_versions.get(self._version_key(scope, bible_ref, bible_version_ref))
        character = self.repository.character_versions.get(
            self._version_key(scope, character_ref, character_version_ref)
        )
        if bible is None or character is None:
            raise RecordNotFoundError("M6 baseline component was not found")
        if bible["status"] != "CONFIRMED" or character["status"] != "CONFIRMED":
            raise ConfirmationRequiredError("M6 baseline components must be confirmed")
        if (
            bible["seriesPlanVersionRef"], bible["seriesPlanVersionDigest"],
            character["seriesPlanVersionRef"], character["seriesPlanVersionDigest"],
        ) != (
            source["seriesPlanVersionRef"], source["seriesPlanVersionDigest"],
            source["seriesPlanVersionRef"], source["seriesPlanVersionDigest"],
        ):
            raise StaleSourceError()
        if (
            character["seriesBibleVersionRef"] != bible_version_ref
            or character["seriesBibleVersionDigest"] != bible["contentDigest"]
        ):
            raise StaleSourceError("CharacterContinuity does not lock selected Bible")
        approval = self.trusted_approval(scope, command, "activate-m6-baseline")
        current_ref = self.repository.active_snapshots.get(scope.key)
        current = self.repository.snapshots.get((*scope.key, current_ref)) if current_ref else None
        if expected_activation_revision != (current["activationRevision"] if current else 0):
            raise VersionConflictError("active M6 baseline revision changed")
        revision = (current["activationRevision"] + 1) if current else 1
        selected = {
            "schemaVersion": M6_BASELINE_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanRef": source["seriesPlanRef"],
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "sourceSeriesPlanVersionRef": source["seriesPlanVersionRef"],
            "sourceSeriesPlanDigest": source["seriesPlanVersionDigest"],
            "seriesBibleRef": bible_ref,
            "seriesBibleVersionRef": bible_version_ref,
            "seriesBibleVersionDigest": bible["contentDigest"],
            "characterContinuityRef": character_ref,
            "characterContinuityVersionRef": character_version_ref,
            "characterContinuityVersionDigest": character["contentDigest"],
        }
        baseline_digest = digest(selected)
        if current and current["contentDigest"] == baseline_digest:
            return deepcopy(current)
        now = self._clock()
        snapshot_ref = self._ref_factory("m6-baseline")
        if current:
            superseded = {**current, "status": "SUPERSEDED", "supersededAt": now}
            self.repository.snapshots[(*scope.key, current_ref)] = superseded
            self._event(scope, command, "M6BaselineSuperseded", current_ref, {
                "supersededSnapshotRef": current_ref,
                "replacementSnapshotRef": snapshot_ref,
            })
        snapshot = {
            **selected,
            "m6BaselineSnapshotRef": snapshot_ref,
            "activationRevision": revision,
            "canonicalSchemaVersion": CANONICAL_SCHEMA_VERSION,
            "contentDigest": baseline_digest,
            "canonicalDigest": baseline_digest,
            "status": "ACTIVE",
            "approvalRef": approval.approval_ref,
            "confirmedByActorRef": approval.actor_ref,
            "confirmedBy": approval.actor_ref,
            "confirmedAt": now,
            "supersededAt": None,
        }
        self.repository.snapshots[(*scope.key, snapshot_ref)] = snapshot
        self.repository.active_snapshots[scope.key] = snapshot_ref
        self._event(scope, command, "M6BaselineConfirmed", snapshot_ref, {
            "m6BaselineSnapshotRef": snapshot_ref,
            "activationRevision": revision,
            "contentDigest": baseline_digest,
        })
        return deepcopy(snapshot)

    def _event(self, scope, command, event_type, aggregate_ref, payload):
        correlation_id = _ref(
            command.get("correlationId") or command.get("operationRef"),
            "correlationId",
        )
        causation_value = command.get("causationId")
        causation_id = (
            _ref(causation_value, "causationId") if causation_value is not None else None
        )
        self.repository.append_event({
            "schemaVersion": M6_EVENT_SCHEMA_VERSION,
            "eventId": self._ref_factory("m6-event"),
            "eventType": event_type,
            "eventVersion": 1,
            "aggregateType": "M6BaselineSnapshot",
            "aggregateRef": aggregate_ref,
            "businessDomain": scope.business_domain,
            "tenantId": scope.tenant_id,
            "workspaceId": scope.workspace_ref,
            "projectRef": scope.project_ref,
            "seriesRef": scope.series_ref,
            "operationRef": _ref(command.get("operationRef"), "operationRef"),
            "correlationId": correlation_id,
            "causationId": causation_id,
            "occurredAt": self._clock(),
            "payload": normalize(payload),
        })

    def get_workspace(self, scope: M6Scope) -> dict[str, Any]:
        bible = self.repository.bibles.get(scope.key)
        character = self.repository.characters.get(scope.key)
        active_ref = self.repository.active_snapshots.get(scope.key)
        current_source = self.source_for(scope)
        active = deepcopy(
            self.repository.snapshots.get((*scope.key, active_ref)) if active_ref else None
        )
        compatibility = "NO_ACTIVE_BASELINE"
        if active:
            compatibility = (
                "CURRENT" if (
                    active["seriesPlanVersionRef"], active["seriesPlanVersionDigest"]
                ) == (
                    current_source["seriesPlanVersionRef"],
                    current_source["seriesPlanVersionDigest"],
                ) else "STALE"
            )
        return {
            "schemaVersion": "v5.series-intelligence.workspace.v1",
            "scope": scope.mapping(),
            "seriesBible": deepcopy(bible),
            "seriesBibleVersions": sorted(
                self.repository.list_bible_versions(scope.key),
                key=lambda item: item["versionNumber"],
            ),
            "characterContinuity": deepcopy(character),
            "characterContinuityVersions": sorted(
                self.repository.list_character_versions(scope.key),
                key=lambda item: item["versionNumber"],
            ),
            "activeBaseline": active,
            "baselineHistory": sorted(
                self.repository.list_snapshots(scope.key),
                key=lambda item: item["activationRevision"],
            ),
            "sourceCompatibility": compatibility,
        }


class ActiveM6BaselineReader:
    """Resolve one coherent, read-only M6 input for an exact trusted Episode."""

    def __init__(
        self,
        service: SeriesIntelligenceService,
        context_reader: M6ConsumerContextReader,
    ) -> None:
        self.__service = service
        self.__context_reader = context_reader

    @staticmethod
    def _lineage_digest(value: Mapping[str, Any]) -> str:
        try:
            return digest(value)
        except Exception:
            raise M6LineageMismatchError("canonical lineage cannot be verified") from None

    @staticmethod
    def _consumer_scope(
        service: SeriesIntelligenceService,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
    ) -> M6Scope:
        try:
            return service.resolve_scope({
                "workspaceRef": workspace_ref,
                "projectRef": project_ref,
                "seriesRef": series_ref,
            })
        except SeriesIntelligenceError:
            raise M6ConsumerAuthorityUnavailableError() from None

    def _trusted_context(
        self,
        scope: M6Scope,
        episode_ref: str,
    ) -> dict[str, Any]:
        try:
            context = self.__context_reader.build_context(
                scope.workspace_ref,
                scope.project_ref,
                scope.series_ref,
                episode_ref,
            )
        except Exception:
            raise M6ConsumerAuthorityUnavailableError() from None
        if not isinstance(context, Mapping):
            raise M6ConsumerAuthorityUnavailableError()
        expected = (
            scope.workspace_ref,
            scope.project_ref,
            scope.series_ref,
            episode_ref,
        )
        actual = tuple(
            context.get(field)
            for field in ("workspaceRef", "projectRef", "seriesRef", "episodeRef")
        )
        episode = context.get("episode")
        series = context.get("series")
        project = context.get("project")
        project_series_refs = (
            project.get("seriesRefs") if isinstance(project, Mapping) else None
        )
        if (
            actual != expected
            or not isinstance(project, Mapping)
            or not isinstance(series, Mapping)
            or not isinstance(episode, Mapping)
            or not isinstance(project_series_refs, list)
            or project.get("workspaceRef") != scope.workspace_ref
            or project.get("projectRef") != scope.project_ref
            or scope.series_ref not in project_series_refs
            or series.get("workspaceRef") != scope.workspace_ref
            or series.get("seriesRef") != scope.series_ref
            or episode.get("workspaceRef") != scope.workspace_ref
            or episode.get("seriesRef") != scope.series_ref
            or episode.get("episodeRef") != episode_ref
        ):
            raise M6ConsumerAuthorityUnavailableError()
        return dict(context)

    def _bound_source(
        self,
        scope: M6Scope,
        episode_ref: str,
    ) -> tuple[dict[str, Any], dict[str, Any], int, dict[str, int]]:
        try:
            source = self.__service.source_reader.get_confirmed_m6_source_snapshot(
                scope.workspace_ref,
                scope.project_ref,
                scope.series_ref,
            )
        except Exception:
            raise M6EpisodeMappingUnavailableError() from None
        if not isinstance(source, Mapping):
            raise M6EpisodeMappingUnavailableError()
        source = dict(source)
        if (
            source.get("status") != "confirmed"
            or source.get("workspaceRef") != scope.workspace_ref
            or source.get("projectRef") != scope.project_ref
            or source.get("seriesRef") != scope.series_ref
        ):
            raise M6LineageMismatchError("M5 source scope is inconsistent")
        if source.get("schemaVersion") != "v5.series-plan.m6-source-snapshot.v2":
            raise M6EpisodeMappingUnavailableError("confirmed M5 source is unbound")
        source_digest = source.get("seriesPlanVersionDigest")
        if not all(
            isinstance(source.get(field), str) and source.get(field)
            for field in ("seriesPlanRef", "seriesPlanVersionRef")
        ):
            raise M6LineageMismatchError("M5 source identity is inconsistent")
        if (
            not isinstance(source_digest, str)
            or not source_digest
            or self._lineage_digest({
                key: value
                for key, value in source.items()
                if key != "seriesPlanVersionDigest"
            }) != source_digest
        ):
            raise M6LineageMismatchError("M5 source digest is inconsistent")
        items = source.get("episodePlanItems")
        bindings = source.get("episodePlanItemBindings")
        if (
            not isinstance(items, list)
            or not all(isinstance(item, Mapping) for item in items)
            or not isinstance(bindings, list)
            or not all(isinstance(item, Mapping) for item in bindings)
        ):
            raise M6LineageMismatchError("M5 source binding shape is inconsistent")
        positions: dict[str, int] = {}
        normalized_items: list[dict[str, Any]] = []
        for index, raw in enumerate(items):
            item = dict(raw)
            item_ref = item.get("episodePlanItemRef")
            if not isinstance(item_ref, str) or not item_ref or item_ref in positions:
                raise M6LineageMismatchError("M5 EpisodePlanItem identity is inconsistent")
            positions[item_ref] = index
            normalized_items.append(item)
        seen_episode_refs: set[str] = set()
        seen_item_refs: set[str] = set()
        for raw in bindings:
            binding = dict(raw)
            if set(binding) != {"episodeRef", "episodePlanItemRef"}:
                raise M6LineageMismatchError("M5 binding is not closed-world")
            bound_episode_ref = binding.get("episodeRef")
            bound_item_ref = binding.get("episodePlanItemRef")
            if (
                not isinstance(bound_episode_ref, str)
                or not bound_episode_ref
                or not isinstance(bound_item_ref, str)
                or bound_item_ref not in positions
                or bound_episode_ref in seen_episode_refs
                or bound_item_ref in seen_item_refs
            ):
                raise M6LineageMismatchError("M5 binding identity is inconsistent")
            seen_episode_refs.add(bound_episode_ref)
            seen_item_refs.add(bound_item_ref)
        matches = [dict(item) for item in bindings if item.get("episodeRef") == episode_ref]
        if len(matches) != 1:
            raise M6EpisodeMappingUnavailableError()
        item_ref = matches[0].get("episodePlanItemRef")
        if not isinstance(item_ref, str) or item_ref not in positions:
            raise M6EpisodeMappingUnavailableError()
        bound_item = normalized_items[positions[item_ref]]
        return source, bound_item, positions[item_ref], positions

    def _active_components(
        self,
        scope: M6Scope,
        source: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        repository = self.__service.repository
        active_ref = repository.active_snapshots.get(scope.key)
        if not active_ref:
            raise M6BaselineNotAvailableError()
        snapshot = repository.snapshots.get((*scope.key, active_ref))
        if snapshot is None:
            raise M6LineageMismatchError("active M6 baseline pointer is inconsistent")
        snapshot = dict(snapshot)
        if (
            snapshot.get("m6BaselineSnapshotRef") != active_ref
            or snapshot.get("status") != "ACTIVE"
            or snapshot.get("scope") != scope.mapping()
            or snapshot.get("canonicalDigest") != snapshot.get("contentDigest")
            or not isinstance(snapshot.get("activationRevision"), int)
            or isinstance(snapshot.get("activationRevision"), bool)
            or snapshot.get("activationRevision", 0) < 1
        ):
            raise M6LineageMismatchError("active M6 baseline is inconsistent")
        if (
            snapshot.get("sourceSeriesPlanVersionRef")
            != snapshot.get("seriesPlanVersionRef")
            or snapshot.get("sourceSeriesPlanDigest")
            != snapshot.get("seriesPlanVersionDigest")
        ):
            raise M6LineageMismatchError("active M6 source lineage is inconsistent")
        if (
            snapshot.get("seriesPlanRef") != source.get("seriesPlanRef")
            or (
                snapshot.get("seriesPlanVersionRef"),
                snapshot.get("seriesPlanVersionDigest"),
            ) != (
                source.get("seriesPlanVersionRef"),
                source.get("seriesPlanVersionDigest"),
            )
        ):
            raise M6BaselineStaleError()
        bible_ref = snapshot.get("seriesBibleRef")
        bible_version_ref = snapshot.get("seriesBibleVersionRef")
        character_ref = snapshot.get("characterContinuityRef")
        character_version_ref = snapshot.get("characterContinuityVersionRef")
        if not all(
            isinstance(value, str) and value
            for value in (bible_ref, bible_version_ref, character_ref, character_version_ref)
        ):
            raise M6LineageMismatchError("active M6 component identity is inconsistent")
        bible = repository.bible_versions.get(
            self.__service._version_key(scope, bible_ref, bible_version_ref)
        )
        character = repository.character_versions.get(
            self.__service._version_key(scope, character_ref, character_version_ref)
        )
        if bible is None or character is None:
            raise M6LineageMismatchError("active M6 component is unavailable")
        bible = dict(bible)
        character = dict(character)
        source_lineage = (
            source.get("seriesPlanVersionRef"),
            source.get("seriesPlanVersionDigest"),
        )
        if (
            bible.get("status") != "CONFIRMED"
            or character.get("status") != "CONFIRMED"
            or bible.get("seriesBibleRef") != bible_ref
            or bible.get("seriesBibleVersionRef") != bible_version_ref
            or character.get("characterContinuityRef") != character_ref
            or character.get("characterContinuityVersionRef") != character_version_ref
            or any(
                record.get(field) != value
                for record in (bible, character)
                for field, value in scope.mapping().items()
            )
            or (bible.get("seriesPlanVersionRef"), bible.get("seriesPlanVersionDigest"))
            != source_lineage
            or (character.get("seriesPlanVersionRef"), character.get("seriesPlanVersionDigest"))
            != source_lineage
            or bible.get("contentDigest") != snapshot.get("seriesBibleVersionDigest")
            or character.get("contentDigest")
            != snapshot.get("characterContinuityVersionDigest")
            or character.get("seriesBibleVersionRef") != bible_version_ref
            or character.get("seriesBibleVersionDigest") != bible.get("contentDigest")
        ):
            raise M6LineageMismatchError("active M6 component lineage is inconsistent")
        bible_content = bible.get("content")
        character_content = character.get("content")
        if not isinstance(bible_content, Mapping) or not isinstance(character_content, Mapping):
            raise M6LineageMismatchError("active M6 content is inconsistent")
        expected_bible_digest = self._lineage_digest({
            "schemaVersion": SERIES_BIBLE_VERSION_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "content": bible_content,
        })
        expected_character_digest = self._lineage_digest({
            "schemaVersion": CHARACTER_CONTINUITY_VERSION_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "seriesBibleVersionRef": bible_version_ref,
            "seriesBibleVersionDigest": expected_bible_digest,
            "content": character_content,
        })
        expected_snapshot_digest = self._lineage_digest({
            "schemaVersion": M6_BASELINE_SCHEMA_VERSION,
            "scope": scope.mapping(),
            "seriesPlanRef": source["seriesPlanRef"],
            "seriesPlanVersionRef": source["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": source["seriesPlanVersionDigest"],
            "sourceSeriesPlanVersionRef": source["seriesPlanVersionRef"],
            "sourceSeriesPlanDigest": source["seriesPlanVersionDigest"],
            "seriesBibleRef": bible_ref,
            "seriesBibleVersionRef": bible_version_ref,
            "seriesBibleVersionDigest": expected_bible_digest,
            "characterContinuityRef": character_ref,
            "characterContinuityVersionRef": character_version_ref,
            "characterContinuityVersionDigest": expected_character_digest,
        })
        if (
            bible.get("contentDigest") != expected_bible_digest
            or bible.get("canonicalDigest") != expected_bible_digest
            or character.get("contentDigest") != expected_character_digest
            or character.get("canonicalDigest") != expected_character_digest
            or snapshot.get("canonicalDigest") != expected_snapshot_digest
        ):
            raise M6LineageMismatchError("active M6 canonical lineage is inconsistent")
        return snapshot, bible, character

    @staticmethod
    def _applies(
        item: Mapping[str, Any],
        position: int,
        positions: Mapping[str, int],
    ) -> bool:
        start_ref = item.get("startEpisodePlanItemRef")
        end_ref = item.get("endEpisodePlanItemRef")
        if start_ref not in positions or (end_ref is not None and end_ref not in positions):
            raise M6LineageMismatchError("M6 applicability lineage is inconsistent")
        return positions[start_ref] <= position and (
            end_ref is None or positions[end_ref] > position
        )

    @staticmethod
    def _stable_ref_facts(
        values: Sequence[Mapping[str, Any]],
        ref_field: str,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            item = dict(value)
            item_ref = item.get(ref_field)
            if not isinstance(item_ref, str) or not item_ref or item_ref in seen:
                raise M6LineageMismatchError("M6 fact identity is inconsistent")
            seen.add(item_ref)
            result.append(deepcopy(item))
        return sorted(result, key=lambda item: item[ref_field])

    def get_active_episode_baseline(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        episode_ref: str,
    ) -> dict[str, Any]:
        scope = self._consumer_scope(
            self.__service,
            workspace_ref,
            project_ref,
            series_ref,
        )
        self._trusted_context(scope, episode_ref)
        source, bound_item, position, positions = self._bound_source(scope, episode_ref)
        snapshot, bible, character = self._active_components(scope, source)
        bible_content = bible.get("content")
        character_content = character.get("content")
        if not isinstance(bible_content, Mapping) or not isinstance(character_content, Mapping):
            raise M6LineageMismatchError("active M6 content is inconsistent")
        facts: dict[str, Any] = {"episodePlanItem": deepcopy(bound_item)}
        for field in _BIBLE_COLLECTIONS:
            values = bible_content.get(field)
            if not isinstance(values, list) or not all(isinstance(item, Mapping) for item in values):
                raise M6LineageMismatchError("SeriesBible facts are inconsistent")
            facts[field] = self._stable_ref_facts(values, _BIBLE_COLLECTIONS[field])
        characters = character_content.get("characters")
        intervals = character_content.get("stateIntervals")
        relationships = character_content.get("relationships")
        if not all(
            isinstance(values, list) and all(isinstance(item, Mapping) for item in values)
            for values in (characters, intervals, relationships)
        ):
            raise M6LineageMismatchError("CharacterContinuity facts are inconsistent")
        facts["characters"] = self._stable_ref_facts(characters, "characterRef")
        facts["stateIntervals"] = self._stable_ref_facts(
            [item for item in intervals if self._applies(item, position, positions)],
            "intervalRef",
        )
        facts["relationships"] = self._stable_ref_facts(
            [item for item in relationships if self._applies(item, position, positions)],
            "relationshipRef",
        )
        result = {
            "schemaVersion": M6_EPISODE_BASELINE_SCHEMA_VERSION,
            **scope.mapping(),
            "episodeRef": episode_ref,
            "episodePlanItemRef": bound_item["episodePlanItemRef"],
            "m6BaselineSnapshotRef": snapshot["m6BaselineSnapshotRef"],
            "activationRevision": snapshot["activationRevision"],
            "m6BaselineCanonicalDigest": snapshot["canonicalDigest"],
            "seriesPlanVersionRef": snapshot["seriesPlanVersionRef"],
            "seriesPlanVersionDigest": snapshot["seriesPlanVersionDigest"],
            "seriesBibleVersionRef": snapshot["seriesBibleVersionRef"],
            "seriesBibleVersionDigest": snapshot["seriesBibleVersionDigest"],
            "characterContinuityVersionRef": snapshot[
                "characterContinuityVersionRef"
            ],
            "characterContinuityVersionDigest": snapshot[
                "characterContinuityVersionDigest"
            ],
            "compatibility": "CURRENT",
            "applicableFacts": facts,
        }
        return deepcopy(result)
