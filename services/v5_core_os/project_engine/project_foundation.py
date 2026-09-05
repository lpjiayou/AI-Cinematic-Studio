"""Non-authoritative records and validation for recoverable Project foundations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
from threading import RLock
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation


PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION = (
    "creator.project-foundation-command.v1"
)
PROJECT_FOUNDATION_RESULT_SCHEMA_VERSION = (
    "creator.project-foundation-result.v1"
)
PROJECT_FOUNDATION_RECORD_SCHEMA_VERSION = (
    "creator.project-foundation-record.v1"
)
PROJECT_FOUNDATION_STATES = frozenset({"PENDING", "COMPLETED"})
PROJECT_FOUNDATION_PROJECT_TYPES = frozenset(
    {"series", "standalone", "brand-film"}
)

COMMAND_FIELDS = frozenset(
    {
        "schemaVersion",
        "idempotencyKey",
        "contentProfileRef",
        "series",
        "project",
        "episode",
    }
)
CANONICAL_REQUEST_FIELDS = frozenset(COMMAND_FIELDS - {"idempotencyKey"})
SERIES_FIELDS = frozenset({"title", "description"})
PROJECT_FIELDS = frozenset(
    {
        "projectType",
        "title",
        "description",
        "targetPlatform",
        "aspectRatio",
        "defaultDurationSec",
        "plannedEpisodeCount",
    }
)
EPISODE_FIELDS = frozenset(
    {
        "creativePlanRef",
        "episodeNumber",
        "seasonNumber",
        "volumeNumber",
        "title",
    }
)
RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "foundationRef",
        "workspaceRef",
        "contentProfileRef",
        "state",
        "series",
        "project",
        "episode",
        "createdAt",
        "completedAt",
        "version",
    }
)
RESULT_SERIES_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "seriesRef",
        "contentProfileRef",
        "title",
        "description",
        "status",
        "plannedEpisodeCount",
        "createdAt",
        "updatedAt",
        "version",
    }
)
RESULT_PROJECT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "contentProfileRef",
        "projectType",
        "title",
        "description",
        "targetPlatform",
        "aspectRatio",
        "defaultDurationSec",
        "plannedEpisodeCount",
        "status",
        "seriesRefs",
        "createdAt",
        "updatedAt",
        "version",
    }
)
RESULT_EPISODE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "seriesRef",
        "episodeRef",
        "episodeNumber",
        "seasonNumber",
        "volumeNumber",
        "title",
        "status",
        "canonicalProjectRef",
        "creativePlanRef",
        "createdAt",
        "updatedAt",
        "version",
        "sourcePlanRef",
        "sourcePlanSchemaVersion",
        "sourcePlanVersion",
    }
)

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)


class ProjectFoundationValidationError(ValueError):
    """The command or durable receipt is not trustworthy."""


class ProjectFoundationStorageError(RuntimeError):
    """The command store cannot safely serve the requested operation."""


@dataclass(frozen=True, slots=True)
class ProjectFoundationRecord:
    schemaVersion: str
    workspaceRef: str
    foundationRef: str
    idempotencyKey: str
    requestDigest: str
    requestJson: str
    state: str
    resultDigest: str | None
    resultJson: str | None
    createdAt: str
    updatedAt: str
    version: int


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectFoundationValidationError(
            "project foundation value is not canonical JSON"
        ) from exc


def canonical_json_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectFoundationValidationError(
                "project foundation JSON contains duplicate keys"
            )
        result[key] = value
    return result


def _reject_float(_value: str) -> None:
    raise ProjectFoundationValidationError(
        "project foundation JSON contains a floating-point value"
    )


def load_canonical_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise ProjectFoundationValidationError(
            "project foundation JSON is invalid"
        )
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_strict_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except ProjectFoundationValidationError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise ProjectFoundationValidationError(
            "project foundation JSON is invalid"
        ) from exc
    if not isinstance(parsed, dict) or canonical_json(parsed) != value:
        raise ProjectFoundationValidationError(
            "project foundation JSON is not canonical"
        )
    return parsed


def _required_ref(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 200
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise ProjectFoundationValidationError(f"{field} is invalid")
    return value


def _idempotency_key(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 200
        or not value.isprintable()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise ProjectFoundationValidationError("idempotencyKey is invalid")
    return value


def _required_text(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ProjectFoundationValidationError(f"{field} must be text")
    result = value.strip()
    if not result or len(result) > maximum:
        raise ProjectFoundationValidationError(f"{field} is invalid")
    return result


def _optional_text(value: Any, field: str, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise ProjectFoundationValidationError(f"{field} must be text")
    result = value.strip()
    if len(result) > maximum:
        raise ProjectFoundationValidationError(f"{field} is invalid")
    return result


def _positive_int(value: Any, field: str, *, maximum: int) -> int:
    if type(value) is not int or value < 1 or value > maximum:
        raise ProjectFoundationValidationError(f"{field} is invalid")
    return value


def normalize_project_foundation_command(
    value: Mapping[str, Any] | Any,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != COMMAND_FIELDS:
        raise ProjectFoundationValidationError(
            "project foundation command fields are invalid"
        )
    if value.get("schemaVersion") != PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION:
        raise ProjectFoundationValidationError(
            "project foundation command schema is invalid"
        )
    idempotency_key = _idempotency_key(value.get("idempotencyKey"))
    content_profile_ref = _required_ref(
        value.get("contentProfileRef"), "contentProfileRef"
    )

    raw_series = value.get("series")
    if raw_series is None:
        series = None
    elif isinstance(raw_series, Mapping) and set(raw_series) == SERIES_FIELDS:
        series = {
            "title": _required_text(raw_series.get("title"), "series.title", maximum=500),
            "description": _optional_text(
                raw_series.get("description"),
                "series.description",
                maximum=2_000,
            ),
        }
    else:
        raise ProjectFoundationValidationError("series is invalid")

    raw_project = value.get("project")
    if not isinstance(raw_project, Mapping) or set(raw_project) != PROJECT_FIELDS:
        raise ProjectFoundationValidationError("project is invalid")
    project_type = raw_project.get("projectType")
    if project_type not in PROJECT_FOUNDATION_PROJECT_TYPES:
        raise ProjectFoundationValidationError("project.projectType is invalid")
    project = {
        "projectType": project_type,
        "title": _required_text(raw_project.get("title"), "project.title", maximum=500),
        "description": _optional_text(
            raw_project.get("description"),
            "project.description",
            maximum=2_000,
        ),
        "targetPlatform": _required_text(
            raw_project.get("targetPlatform"),
            "project.targetPlatform",
            maximum=200,
        ),
        "aspectRatio": _required_text(
            raw_project.get("aspectRatio"),
            "project.aspectRatio",
            maximum=20,
        ),
        "defaultDurationSec": _positive_int(
            raw_project.get("defaultDurationSec"),
            "project.defaultDurationSec",
            maximum=86_400,
        ),
        "plannedEpisodeCount": _positive_int(
            raw_project.get("plannedEpisodeCount"),
            "project.plannedEpisodeCount",
            maximum=10_000,
        ),
    }

    raw_episode = value.get("episode")
    if raw_episode is None:
        episode = None
    elif isinstance(raw_episode, Mapping) and set(raw_episode) == EPISODE_FIELDS:
        episode = {
            "creativePlanRef": _required_ref(
                raw_episode.get("creativePlanRef"),
                "episode.creativePlanRef",
            ),
            "episodeNumber": _positive_int(
                raw_episode.get("episodeNumber"),
                "episode.episodeNumber",
                maximum=100_000,
            ),
            "seasonNumber": _positive_int(
                raw_episode.get("seasonNumber"),
                "episode.seasonNumber",
                maximum=100_000,
            ),
            "volumeNumber": _positive_int(
                raw_episode.get("volumeNumber"),
                "episode.volumeNumber",
                maximum=100_000,
            ),
            "title": _required_text(
                raw_episode.get("title"),
                "episode.title",
                maximum=500,
            ),
        }
    else:
        raise ProjectFoundationValidationError("episode is invalid")

    if project_type == "series" and series is None:
        raise ProjectFoundationValidationError(
            "series is required for a series project"
        )
    if episode is not None and series is None:
        raise ProjectFoundationValidationError(
            "episode requires a series"
        )

    return idempotency_key, {
        "schemaVersion": PROJECT_FOUNDATION_COMMAND_SCHEMA_VERSION,
        "contentProfileRef": content_profile_ref,
        "series": series,
        "project": project,
        "episode": episode,
    }


def _validate_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or _TIMESTAMP_PATTERN.fullmatch(value) is None:
        raise ProjectFoundationValidationError(f"{field} is invalid")
    return value


def validate_project_foundation_result(
    result: Mapping[str, Any] | Any,
    *,
    record: ProjectFoundationRecord,
    request_value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, Mapping) or set(result) != RESULT_FIELDS:
        raise ProjectFoundationValidationError(
            "project foundation result fields are invalid"
        )
    detached = dict(result)
    if (
        detached.get("schemaVersion") != PROJECT_FOUNDATION_RESULT_SCHEMA_VERSION
        or detached.get("foundationRef") != record.foundationRef
        or detached.get("workspaceRef") != record.workspaceRef
        or detached.get("contentProfileRef") != request_value.get("contentProfileRef")
        or detached.get("state") != "COMPLETED"
        or type(detached.get("version")) is not int
        or detached.get("version") != 1
        or detached.get("createdAt") != record.createdAt
    ):
        raise ProjectFoundationValidationError(
            "project foundation result metadata is inconsistent"
        )
    _validate_timestamp(detached.get("createdAt"), "createdAt")
    _validate_timestamp(detached.get("completedAt"), "completedAt")
    if not isinstance(detached.get("project"), Mapping):
        raise ProjectFoundationValidationError(
            "project foundation result project is invalid"
        )
    expected_series = request_value.get("series")
    expected_episode = request_value.get("episode")
    if (detached.get("series") is None) != (expected_series is None):
        raise ProjectFoundationValidationError(
            "project foundation result series is inconsistent"
        )
    if (detached.get("episode") is None) != (expected_episode is None):
        raise ProjectFoundationValidationError(
            "project foundation result episode is inconsistent"
        )
    for name in ("project", "series", "episode"):
        item = detached.get(name)
        if item is not None and not isinstance(item, Mapping):
            raise ProjectFoundationValidationError(
                f"project foundation result {name} is invalid"
            )
    project = detached["project"]
    if (
        set(project) != RESULT_PROJECT_FIELDS
        or project.get("workspaceRef") != record.workspaceRef
        or project.get("schemaVersion") != "v5.project.v1"
        or project.get("contentProfileRef") != request_value.get("contentProfileRef")
        or project.get("projectType") != request_value["project"]["projectType"]
        or project.get("title") != request_value["project"]["title"]
        or project.get("description") != request_value["project"]["description"]
        or project.get("targetPlatform") != request_value["project"]["targetPlatform"]
        or project.get("aspectRatio") != request_value["project"]["aspectRatio"]
        or project.get("defaultDurationSec")
        != request_value["project"]["defaultDurationSec"]
        or project.get("plannedEpisodeCount")
        != request_value["project"]["plannedEpisodeCount"]
        or project.get("status") != "active"
        or type(project.get("version")) is not int
        or project.get("version") != 1
        or project.get("updatedAt") != project.get("createdAt")
    ):
        raise ProjectFoundationValidationError(
            "project foundation result project scope is inconsistent"
        )
    series = detached.get("series")
    if series is not None and (
        set(series) != RESULT_SERIES_FIELDS
        or series.get("workspaceRef") != record.workspaceRef
        or series.get("schemaVersion") != "v5.series.v1"
        or series.get("contentProfileRef") != request_value.get("contentProfileRef")
        or project.get("seriesRefs") != [series.get("seriesRef")]
        or series.get("title") != expected_series.get("title")
        or series.get("description") != expected_series.get("description")
        or series.get("plannedEpisodeCount")
        != request_value["project"]["plannedEpisodeCount"]
        or series.get("status") != "active"
        or type(series.get("version")) is not int
        or series.get("version") != 1
        or series.get("updatedAt") != series.get("createdAt")
    ):
        raise ProjectFoundationValidationError(
            "project foundation result series scope is inconsistent"
        )
    episode = detached.get("episode")
    if episode is not None and (
        set(episode) != RESULT_EPISODE_FIELDS
        or series is None
        or episode.get("schemaVersion") != "v5.episode.v1"
        or episode.get("workspaceRef") != record.workspaceRef
        or episode.get("seriesRef") != series.get("seriesRef")
        or episode.get("creativePlanRef") != expected_episode.get("creativePlanRef")
        or episode.get("episodeNumber") != expected_episode.get("episodeNumber")
        or episode.get("seasonNumber") != expected_episode.get("seasonNumber")
        or episode.get("volumeNumber") != expected_episode.get("volumeNumber")
        or episode.get("title") != expected_episode.get("title")
        or episode.get("status") != "draft"
        or episode.get("canonicalProjectRef") is not None
        or type(episode.get("sourcePlanVersion")) is not int
        or episode.get("sourcePlanVersion") < 1
        or type(episode.get("version")) is not int
        or episode.get("version") != 1
        or episode.get("updatedAt") != episode.get("createdAt")
    ):
        raise ProjectFoundationValidationError(
            "project foundation result episode scope is inconsistent"
        )
    if series is None and project.get("seriesRefs") != []:
        raise ProjectFoundationValidationError(
            "project foundation result relationship is inconsistent"
        )
    for reference in (
        project.get("projectRef"),
        *(tuple() if series is None else (series.get("seriesRef"),)),
        *(
            tuple()
            if episode is None
            else (
                episode.get("episodeRef"),
                episode.get("sourcePlanRef"),
                episode.get("sourcePlanSchemaVersion"),
            )
        ),
    ):
        _required_ref(reference, "result reference")
    for item in (project, series, episode):
        if item is not None:
            _validate_timestamp(item.get("createdAt"), "result.createdAt")
            _validate_timestamp(item.get("updatedAt"), "result.updatedAt")
    return detached


def validate_project_foundation_record(
    record: ProjectFoundationRecord,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if (
        not isinstance(record, ProjectFoundationRecord)
        or record.schemaVersion != PROJECT_FOUNDATION_RECORD_SCHEMA_VERSION
        or record.state not in PROJECT_FOUNDATION_STATES
        or type(record.version) is not int
        or record.version not in {1, 2}
    ):
        raise ProjectFoundationValidationError(
            "project foundation record metadata is invalid"
        )
    _required_ref(record.workspaceRef, "workspaceRef")
    _required_ref(record.foundationRef, "foundationRef")
    _idempotency_key(record.idempotencyKey)
    _validate_timestamp(record.createdAt, "createdAt")
    _validate_timestamp(record.updatedAt, "updatedAt")
    if not isinstance(record.requestDigest, str) or not _DIGEST_PATTERN.fullmatch(
        record.requestDigest
    ):
        raise ProjectFoundationValidationError(
            "project foundation request digest is invalid"
        )
    request_value = load_canonical_json(record.requestJson)
    if set(request_value) != CANONICAL_REQUEST_FIELDS:
        raise ProjectFoundationValidationError(
            "project foundation request JSON fields are invalid"
        )
    key, normalized = normalize_project_foundation_command(
        {**request_value, "idempotencyKey": record.idempotencyKey}
    )
    if key != record.idempotencyKey or normalized != request_value:
        raise ProjectFoundationValidationError(
            "project foundation request JSON is inconsistent"
        )
    if sha256(record.requestJson.encode("utf-8")).hexdigest() != record.requestDigest:
        raise ProjectFoundationValidationError(
            "project foundation request digest does not match"
        )

    if record.state == "PENDING":
        if (
            record.resultDigest is not None
            or record.resultJson is not None
            or record.version != 1
            or record.updatedAt != record.createdAt
        ):
            raise ProjectFoundationValidationError(
                "pending project foundation record is inconsistent"
            )
        return normalized, None

    if (
        record.resultDigest is None
        or record.resultJson is None
        or record.version != 2
        or not isinstance(record.resultDigest, str)
        or _DIGEST_PATTERN.fullmatch(record.resultDigest) is None
    ):
        raise ProjectFoundationValidationError(
            "completed project foundation record is inconsistent"
        )
    result = load_canonical_json(record.resultJson)
    if sha256(record.resultJson.encode("utf-8")).hexdigest() != record.resultDigest:
        raise ProjectFoundationValidationError(
            "project foundation result digest does not match"
        )
    return normalized, validate_project_foundation_result(
        result,
        record=record,
        request_value=normalized,
    )


class InMemoryProjectFoundationStore:
    """Thread-safe command store participating in in-memory lifecycle rollback."""

    def __init__(self, *, lifecycle_state=None) -> None:
        self._records: dict[tuple[str, str], ProjectFoundationRecord] = {}
        self._keys: dict[tuple[str, str], str] = {}
        self._lock = RLock()
        self._lifecycle_state = lifecycle_state

    def reserve(
        self,
        record: ProjectFoundationRecord,
    ) -> tuple[ProjectFoundationRecord, bool]:
        validate_project_foundation_record(record)
        foundation_key = (record.workspaceRef, record.foundationRef)
        idempotency_key = (record.workspaceRef, record.idempotencyKey)
        with self._lock:
            existing_ref = self._keys.get(idempotency_key)
            if existing_ref is not None:
                existing = self._records[(record.workspaceRef, existing_ref)]
                validate_project_foundation_record(existing)
                return existing, False
            if foundation_key in self._records:
                raise ProjectFoundationStorageError(
                    "project foundation reference collision"
                )
            self._records[foundation_key] = record
            self._keys[idempotency_key] = record.foundationRef
            return record, True

    def get_by_key(
        self, workspace_ref: str, idempotency_key: str
    ) -> ProjectFoundationRecord | None:
        with self._lock:
            foundation_ref = self._keys.get((workspace_ref, idempotency_key))
            if foundation_ref is None:
                return None
            record = self._records[(workspace_ref, foundation_ref)]
            validate_project_foundation_record(record)
            return record

    def get_by_ref(
        self, workspace_ref: str, foundation_ref: str
    ) -> ProjectFoundationRecord | None:
        with self._lock:
            record = self._records.get((workspace_ref, foundation_ref))
            if record is not None:
                validate_project_foundation_record(record)
            return record

    def complete(
        self,
        lease: object,
        record: ProjectFoundationRecord,
        result: Mapping[str, Any],
        completed_at: str,
    ) -> ProjectFoundationRecord:
        if self._lifecycle_state is not None:
            self._lifecycle_state.validate_lease(
                lease,
                workspace_ref=record.workspaceRef,
                allowed_operations=frozenset(
                    {LifecycleOperation.CREATE_PROJECT_FOUNDATION}
                ),
            )
        _validate_timestamp(completed_at, "completedAt")
        with self._lock:
            current = self._records.get(
                (record.workspaceRef, record.foundationRef)
            )
            if current != record or current.state != "PENDING":
                raise ProjectFoundationStorageError(
                    "project foundation state transition is invalid"
                )
            result_json = canonical_json(dict(result))
            completed = replace(
                current,
                state="COMPLETED",
                resultDigest=sha256(result_json.encode("utf-8")).hexdigest(),
                resultJson=result_json,
                updatedAt=completed_at,
                version=2,
            )
            validate_project_foundation_record(completed)
            self._records[(completed.workspaceRef, completed.foundationRef)] = completed
            return completed

    def count(self, workspace_ref: str | None = None) -> int:
        with self._lock:
            if workspace_ref is None:
                return len(self._records)
            return sum(key[0] == workspace_ref for key in self._records)

    def close(self) -> None:
        return None
