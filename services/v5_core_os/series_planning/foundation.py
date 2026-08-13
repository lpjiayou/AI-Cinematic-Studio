"""V5-owned Series Planning facts, versioning, repository port, and adapters."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4
import unicodedata


SERIES_PLAN_SCHEMA_VERSION = "v5.series-plan.v1"
SERIES_PLAN_VERSION_SCHEMA_VERSION = "v5.series-plan-version.v1"
SERIES_PLAN_CANDIDATE_SCHEMA_VERSION = "creator.series-plan.candidate.v1"
SERIES_PLAN_WORKSPACE_SCHEMA_VERSION = "creator.series-planning.workspace.v1"
M6_BOOTSTRAP_SCHEMA_VERSION = "creator.series-plan.m6-bootstrap.v1"
M6_SOURCE_SNAPSHOT_SCHEMA_VERSION = "v5.series-plan.m6-source-snapshot.v1"
SQLITE_SCHEMA_VERSION = 1


class SeriesPlanningError(ValueError):
    code = "invalid_request"


class RecordNotFoundError(SeriesPlanningError):
    code = "not_found"


class DuplicateRecordError(SeriesPlanningError):
    code = "duplicate_record"


class ScopeMismatchError(SeriesPlanningError):
    code = "scope_mismatch"


class VersionConflictError(SeriesPlanningError):
    code = "version_conflict"


class PlanNotConfirmedError(SeriesPlanningError):
    code = "series_plan_not_confirmed"


def _canonical_m6_source(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise SeriesPlanningError("M6 source snapshot cannot contain floating-point values")
    if isinstance(value, list):
        return [_canonical_m6_source(item) for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = unicodedata.normalize("NFC", str(raw_key))
            if key in normalized:
                raise SeriesPlanningError("M6 source snapshot has duplicate normalized keys")
            normalized[key] = _canonical_m6_source(raw_value)
        return normalized
    raise SeriesPlanningError("M6 source snapshot is not canonical JSON")


def _m6_source_digest(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        _canonical_m6_source(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class UpstreamProjectReader(Protocol):
    def build_context(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str | None = None,
        episode_ref: str | None = None,
    ) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _required_text(value: Any, field: str, *, limit: int = 6000) -> str:
    text = str(value or "").strip()
    if not text:
        raise SeriesPlanningError(f"{field} is required")
    if len(text) > limit:
        raise SeriesPlanningError(f"{field} is too long")
    return text


def _required_ref(value: Any, field: str) -> str:
    text = _required_text(value, field, limit=200)
    if not text.isprintable() or any(character.isspace() for character in text):
        raise SeriesPlanningError(f"{field} is invalid")
    return text


def _positive_int(value: Any, field: str, *, maximum: int = 100_000) -> int:
    if isinstance(value, bool):
        raise SeriesPlanningError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SeriesPlanningError(f"{field} must be an integer") from exc
    if result < 1 or result > maximum:
        raise SeriesPlanningError(f"{field} is out of range")
    return result


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise SeriesPlanningError(f"{field} must be an array")
    return [_required_text(item, f"{field}[{index}]", limit=1200) for index, item in enumerate(value)]


def _mapping_list(value: Any, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise SeriesPlanningError(f"{field} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise SeriesPlanningError(f"{field} items must be objects")
    return list(value)


@dataclass(frozen=True)
class SeriesPlanRecord:
    schemaVersion: str
    workspaceRef: str
    contentProfileRef: str
    projectRef: str
    seriesRef: str
    seriesPlanRef: str
    currentSeriesPlanVersionRef: str
    confirmedSeriesPlanVersionRef: str | None
    status: str
    createdAt: str
    updatedAt: str
    version: int


@dataclass(frozen=True)
class SeriesPlanVersionRecord:
    schemaVersion: str
    workspaceRef: str
    contentProfileRef: str
    projectRef: str
    seriesRef: str
    seriesPlanRef: str
    seriesPlanVersionRef: str
    versionNumber: int
    contentJson: str
    changeKind: str
    parentSeriesPlanVersionRef: str | None
    createdAt: str


class SeriesPlanningRepository(Protocol):
    def create_plan_with_version(
        self, plan: SeriesPlanRecord, version: SeriesPlanVersionRecord
    ) -> tuple[SeriesPlanRecord, SeriesPlanVersionRecord]: ...

    def append_version(
        self,
        updated_plan: SeriesPlanRecord,
        version: SeriesPlanVersionRecord,
        expected_plan_version: int,
    ) -> tuple[SeriesPlanRecord, SeriesPlanVersionRecord]: ...

    def confirm_version(self, updated_plan: SeriesPlanRecord, expected_plan_version: int) -> SeriesPlanRecord: ...
    def get_plan(self, workspace_ref: str, project_ref: str, series_ref: str) -> SeriesPlanRecord | None: ...
    def get_plan_by_ref(self, workspace_ref: str, plan_ref: str) -> SeriesPlanRecord | None: ...
    def get_version(self, workspace_ref: str, plan_ref: str, version_ref: str) -> SeriesPlanVersionRecord | None: ...
    def list_versions(self, workspace_ref: str, plan_ref: str) -> list[SeriesPlanVersionRecord]: ...


class InMemorySeriesPlanningAdapter:
    def __init__(self) -> None:
        self._plans: dict[tuple[str, str], SeriesPlanRecord] = {}
        self._scope_index: dict[tuple[str, str, str], str] = {}
        self._versions: dict[tuple[str, str, str], SeriesPlanVersionRecord] = {}
        self._lock = RLock()

    def create_plan_with_version(self, plan, version):
        plan_key = (plan.workspaceRef, plan.seriesPlanRef)
        scope_key = (plan.workspaceRef, plan.projectRef, plan.seriesRef)
        version_key = (version.workspaceRef, version.seriesPlanRef, version.seriesPlanVersionRef)
        with self._lock:
            if plan_key in self._plans or scope_key in self._scope_index or version_key in self._versions:
                raise DuplicateRecordError("Series Plan already exists")
            self._plans[plan_key] = plan
            self._scope_index[scope_key] = plan.seriesPlanRef
            self._versions[version_key] = version
        return plan, version

    def append_version(self, updated_plan, version, expected_plan_version):
        plan_key = (updated_plan.workspaceRef, updated_plan.seriesPlanRef)
        version_key = (version.workspaceRef, version.seriesPlanRef, version.seriesPlanVersionRef)
        with self._lock:
            current = self._plans.get(plan_key)
            if current is None:
                raise RecordNotFoundError("Series Plan was not found")
            if current.version != expected_plan_version:
                raise VersionConflictError("Series Plan version changed")
            if version_key in self._versions:
                raise DuplicateRecordError("Series Plan version already exists")
            self._versions[version_key] = version
            self._plans[plan_key] = updated_plan
        return updated_plan, version

    def confirm_version(self, updated_plan, expected_plan_version):
        plan_key = (updated_plan.workspaceRef, updated_plan.seriesPlanRef)
        with self._lock:
            current = self._plans.get(plan_key)
            if current is None:
                raise RecordNotFoundError("Series Plan was not found")
            if current.version != expected_plan_version:
                raise VersionConflictError("Series Plan version changed")
            version_key = (
                updated_plan.workspaceRef,
                updated_plan.seriesPlanRef,
                updated_plan.confirmedSeriesPlanVersionRef,
            )
            if version_key not in self._versions:
                raise RecordNotFoundError("Series Plan version was not found")
            self._plans[plan_key] = updated_plan
        return updated_plan

    def get_plan(self, workspace_ref, project_ref, series_ref):
        plan_ref = self._scope_index.get((workspace_ref, project_ref, series_ref))
        return self._plans.get((workspace_ref, plan_ref)) if plan_ref else None

    def get_plan_by_ref(self, workspace_ref, plan_ref):
        return self._plans.get((workspace_ref, plan_ref))

    def get_version(self, workspace_ref, plan_ref, version_ref):
        return self._versions.get((workspace_ref, plan_ref, version_ref))

    def list_versions(self, workspace_ref, plan_ref):
        return sorted(
            (
                item for key, item in self._versions.items()
                if key[0] == workspace_ref and key[1] == plan_ref
            ),
            key=lambda item: item.versionNumber,
        )


class SqliteSeriesPlanningAdapter:
    """Durable local-development adapter sharing the Creator SQLite database."""

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
                CREATE TABLE IF NOT EXISTS v5_series_planning_schema (
                    component TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v5_series_plans (
                    workspace_ref TEXT NOT NULL,
                    series_plan_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_profile_ref TEXT NOT NULL,
                    project_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    current_version_ref TEXT NOT NULL,
                    confirmed_version_ref TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    PRIMARY KEY(workspace_ref, series_plan_ref),
                    UNIQUE(workspace_ref, project_ref, series_ref)
                );
                CREATE TABLE IF NOT EXISTS v5_series_plan_versions (
                    workspace_ref TEXT NOT NULL,
                    series_plan_ref TEXT NOT NULL,
                    series_plan_version_ref TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    content_profile_ref TEXT NOT NULL,
                    project_ref TEXT NOT NULL,
                    series_ref TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    change_kind TEXT NOT NULL,
                    parent_version_ref TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(workspace_ref, series_plan_ref, series_plan_version_ref),
                    UNIQUE(workspace_ref, series_plan_ref, version_number),
                    FOREIGN KEY(workspace_ref, series_plan_ref)
                        REFERENCES v5_series_plans(workspace_ref, series_plan_ref) ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO v5_series_planning_schema VALUES (?, ?)",
                ("series_planning", SQLITE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT schema_version FROM v5_series_planning_schema WHERE component = ?",
                ("series_planning",),
            ).fetchone()
            if row is None or row["schema_version"] not in {SQLITE_SCHEMA_VERSION, 2}:
                raise RuntimeError("unsupported Series Planning local-development schema version")

    @staticmethod
    def _plan(row: sqlite3.Row) -> SeriesPlanRecord:
        return SeriesPlanRecord(
            row["schema_version"], row["workspace_ref"], row["content_profile_ref"],
            row["project_ref"], row["series_ref"], row["series_plan_ref"],
            row["current_version_ref"], row["confirmed_version_ref"], row["status"],
            row["created_at"], row["updated_at"], row["version"],
        )

    @staticmethod
    def _version(row: sqlite3.Row) -> SeriesPlanVersionRecord:
        return SeriesPlanVersionRecord(
            row["schema_version"], row["workspace_ref"], row["content_profile_ref"],
            row["project_ref"], row["series_ref"], row["series_plan_ref"],
            row["series_plan_version_ref"], row["version_number"], row["content_json"],
            row["change_kind"], row["parent_version_ref"], row["created_at"],
        )

    def create_plan_with_version(self, plan, version):
        try:
            with self._lock, self._write_session() as connection:
                connection.execute(
                    "INSERT INTO v5_series_plans VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        plan.workspaceRef, plan.seriesPlanRef, plan.schemaVersion,
                        plan.contentProfileRef, plan.projectRef, plan.seriesRef,
                        plan.currentSeriesPlanVersionRef, plan.confirmedSeriesPlanVersionRef,
                        plan.status, plan.createdAt, plan.updatedAt, plan.version,
                    ),
                )
                connection.execute(
                    "INSERT INTO v5_series_plan_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        version.workspaceRef, version.seriesPlanRef, version.seriesPlanVersionRef,
                        version.schemaVersion, version.contentProfileRef, version.projectRef,
                        version.seriesRef, version.versionNumber, version.contentJson,
                        version.changeKind, version.parentSeriesPlanVersionRef, version.createdAt,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("Series Plan or version already exists") from exc
        return plan, version

    def append_version(self, updated_plan, version, expected_plan_version):
        try:
            with self._lock, self._write_session() as connection:
                current = connection.execute(
                    "SELECT version FROM v5_series_plans WHERE workspace_ref = ? AND series_plan_ref = ?",
                    (updated_plan.workspaceRef, updated_plan.seriesPlanRef),
                ).fetchone()
                if current is None:
                    raise RecordNotFoundError("Series Plan was not found")
                if current["version"] != expected_plan_version:
                    raise VersionConflictError("Series Plan version changed")
                connection.execute(
                    "INSERT INTO v5_series_plan_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        version.workspaceRef, version.seriesPlanRef, version.seriesPlanVersionRef,
                        version.schemaVersion, version.contentProfileRef, version.projectRef,
                        version.seriesRef, version.versionNumber, version.contentJson,
                        version.changeKind, version.parentSeriesPlanVersionRef, version.createdAt,
                    ),
                )
                cursor = connection.execute(
                    "UPDATE v5_series_plans SET current_version_ref = ?, updated_at = ?, version = ? "
                    "WHERE workspace_ref = ? AND series_plan_ref = ? AND version = ?",
                    (
                        updated_plan.currentSeriesPlanVersionRef, updated_plan.updatedAt,
                        updated_plan.version, updated_plan.workspaceRef, updated_plan.seriesPlanRef,
                        expected_plan_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise VersionConflictError("Series Plan version changed")
        except sqlite3.IntegrityError as exc:
            raise DuplicateRecordError("Series Plan version already exists") from exc
        return updated_plan, version

    def confirm_version(self, updated_plan, expected_plan_version):
        with self._lock, self._write_session() as connection:
            exists = connection.execute(
                "SELECT 1 FROM v5_series_plan_versions WHERE workspace_ref = ? AND series_plan_ref = ? AND series_plan_version_ref = ?",
                (
                    updated_plan.workspaceRef, updated_plan.seriesPlanRef,
                    updated_plan.confirmedSeriesPlanVersionRef,
                ),
            ).fetchone()
            if exists is None:
                raise RecordNotFoundError("Series Plan version was not found")
            cursor = connection.execute(
                "UPDATE v5_series_plans SET confirmed_version_ref = ?, status = ?, updated_at = ?, version = ? "
                "WHERE workspace_ref = ? AND series_plan_ref = ? AND version = ?",
                (
                    updated_plan.confirmedSeriesPlanVersionRef, updated_plan.status,
                    updated_plan.updatedAt, updated_plan.version, updated_plan.workspaceRef,
                    updated_plan.seriesPlanRef, expected_plan_version,
                ),
            )
            if cursor.rowcount != 1:
                raise VersionConflictError("Series Plan version changed")
        return updated_plan

    def get_plan(self, workspace_ref, project_ref, series_ref):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_series_plans WHERE workspace_ref = ? AND project_ref = ? AND series_ref = ?",
                (workspace_ref, project_ref, series_ref),
            ).fetchone()
        return self._plan(row) if row else None

    def get_plan_by_ref(self, workspace_ref, plan_ref):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_series_plans WHERE workspace_ref = ? AND series_plan_ref = ?",
                (workspace_ref, plan_ref),
            ).fetchone()
        return self._plan(row) if row else None

    def get_version(self, workspace_ref, plan_ref, version_ref):
        with self._session() as connection:
            row = connection.execute(
                "SELECT * FROM v5_series_plan_versions WHERE workspace_ref = ? AND series_plan_ref = ? AND series_plan_version_ref = ?",
                (workspace_ref, plan_ref, version_ref),
            ).fetchone()
        return self._version(row) if row else None

    def list_versions(self, workspace_ref, plan_ref):
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM v5_series_plan_versions WHERE workspace_ref = ? AND series_plan_ref = ? ORDER BY version_number",
                (workspace_ref, plan_ref),
            ).fetchall()
        return [self._version(row) for row in rows]


def _project_context(reader: UpstreamProjectReader, command: Mapping[str, Any]) -> dict[str, Any]:
    context = reader.build_context(
        _required_ref(command.get("workspaceRef"), "workspaceRef"),
        _required_ref(command.get("projectRef"), "projectRef"),
        _required_ref(command.get("seriesRef"), "seriesRef"),
    )
    if not context.get("series"):
        raise ScopeMismatchError("Project has no associated Series")
    return context


def _normalize_content(
    value: Any,
    *,
    planned_count: int,
    ref_factory: Callable[[str], str],
    existing_item_refs: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SeriesPlanningError("Series Plan content must be an object")
    allowed = {
        "schemaVersion", "seriesConcept", "premise", "logline", "mainNarrativeDirection",
        "mainArcs", "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
        "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
    }
    if set(value) != allowed:
        raise SeriesPlanningError("Series Plan content fields do not match the accepted contract")
    if value.get("schemaVersion") != SERIES_PLAN_CANDIDATE_SCHEMA_VERSION:
        raise SeriesPlanningError("Series Plan candidate schemaVersion is invalid")
    result: dict[str, Any] = {
        "seriesConcept": _required_text(value.get("seriesConcept"), "seriesConcept"),
        "premise": _required_text(value.get("premise"), "premise"),
        "logline": _required_text(value.get("logline"), "logline"),
        "mainNarrativeDirection": _required_text(value.get("mainNarrativeDirection"), "mainNarrativeDirection"),
        "narrativeRhythm": _required_text(value.get("narrativeRhythm"), "narrativeRhythm"),
        "worldIntent": _required_text(value.get("worldIntent"), "worldIntent"),
        "continuityIntent": _text_list(value.get("continuityIntent"), "continuityIntent"),
        "foreshadowingContext": _text_list(value.get("foreshadowingContext"), "foreshadowingContext"),
        "productionAssumptions": _text_list(value.get("productionAssumptions"), "productionAssumptions"),
    }
    arcs: list[dict[str, Any]] = []
    for index, item in enumerate(_mapping_list(value.get("mainArcs"), "mainArcs")):
        expected = {"arcNumber", "title", "episodeStart", "episodeEnd", "objective", "turningPoint"}
        if set(item) != expected:
            raise SeriesPlanningError(f"mainArcs[{index}] fields are invalid")
        arc = {
            "arcNumber": _positive_int(item.get("arcNumber"), "arcNumber", maximum=100),
            "title": _required_text(item.get("title"), "arc title", limit=300),
            "episodeStart": _positive_int(item.get("episodeStart"), "episodeStart", maximum=planned_count),
            "episodeEnd": _positive_int(item.get("episodeEnd"), "episodeEnd", maximum=planned_count),
            "objective": _required_text(item.get("objective"), "objective"),
            "turningPoint": _required_text(item.get("turningPoint"), "turningPoint"),
        }
        if arc["arcNumber"] != index + 1 or arc["episodeStart"] > arc["episodeEnd"]:
            raise SeriesPlanningError("main arc identity or range is invalid")
        arcs.append(arc)
    if not arcs:
        raise SeriesPlanningError("mainArcs must not be empty")
    result["mainArcs"] = arcs
    sub_arcs: list[dict[str, Any]] = []
    for index, item in enumerate(_mapping_list(value.get("subArcs"), "subArcs")):
        if set(item) != {"title", "episodeStart", "episodeEnd", "purpose"}:
            raise SeriesPlanningError(f"subArcs[{index}] fields are invalid")
        sub_arcs.append({
            "title": _required_text(item.get("title"), "sub arc title", limit=300),
            "episodeStart": _positive_int(item.get("episodeStart"), "episodeStart", maximum=planned_count),
            "episodeEnd": _positive_int(item.get("episodeEnd"), "episodeEnd", maximum=planned_count),
            "purpose": _required_text(item.get("purpose"), "purpose"),
        })
    result["subArcs"] = sub_arcs
    character_intents: list[dict[str, str]] = []
    for index, item in enumerate(_mapping_list(value.get("characterArcIntents"), "characterArcIntents")):
        if set(item) != {"roleLabel", "startingState", "developmentIntent", "destination"}:
            raise SeriesPlanningError(f"characterArcIntents[{index}] fields are invalid")
        character_intents.append({key: _required_text(item.get(key), key) for key in item})
    if not character_intents:
        raise SeriesPlanningError("characterArcIntents must not be empty")
    result["characterArcIntents"] = character_intents
    items: list[dict[str, Any]] = []
    raw_items = _mapping_list(value.get("episodePlanItems"), "episodePlanItems")
    if len(raw_items) != planned_count:
        raise SeriesPlanningError("Episode Plan Item count must match Project")
    for index, item in enumerate(raw_items):
        base_fields = {"episodeNumber", "title", "logline", "arcNumber", "narrativePurpose", "continuityNotes", "foreshadowing"}
        allowed_item_fields = base_fields | ({"episodePlanItemRef"} if existing_item_refs is not None else set())
        if set(item) != allowed_item_fields:
            raise SeriesPlanningError(f"episodePlanItems[{index}] fields are invalid")
        number = _positive_int(item.get("episodeNumber"), "episodeNumber", maximum=planned_count)
        if number != index + 1:
            raise SeriesPlanningError("Episode Plan Item numbers must be continuous")
        if existing_item_refs is None:
            item_ref = ref_factory("episode-plan-item")
        else:
            item_ref = _required_ref(item.get("episodePlanItemRef"), "episodePlanItemRef")
            if item_ref not in existing_item_refs:
                raise ScopeMismatchError("Episode Plan Item does not belong to current Series Plan")
        items.append({
            "episodePlanItemRef": item_ref,
            "episodeNumber": number,
            "title": _required_text(item.get("title"), "episode title", limit=300),
            "logline": _required_text(item.get("logline"), "episode logline"),
            "arcNumber": _positive_int(item.get("arcNumber"), "arcNumber", maximum=len(arcs)),
            "narrativePurpose": _required_text(item.get("narrativePurpose"), "narrativePurpose"),
            "continuityNotes": _text_list(item.get("continuityNotes"), "continuityNotes"),
            "foreshadowing": _text_list(item.get("foreshadowing"), "foreshadowing"),
        })
    result["episodePlanItems"] = items
    coverage = set()
    for arc in arcs:
        coverage.update(range(arc["episodeStart"], arc["episodeEnd"] + 1))
    if coverage != set(range(1, planned_count + 1)):
        raise SeriesPlanningError("mainArcs must cover all Episode Plan Items")
    return result


class SeriesPlanningService:
    def __init__(
        self,
        repository: SeriesPlanningRepository,
        project_reader: UpstreamProjectReader,
        *,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.project_reader = project_reader
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    @staticmethod
    def _plan_mapping(record: SeriesPlanRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "contentProfileRef": record.contentProfileRef,
            "projectRef": record.projectRef,
            "seriesRef": record.seriesRef,
            "seriesPlanRef": record.seriesPlanRef,
            "currentSeriesPlanVersionRef": record.currentSeriesPlanVersionRef,
            "confirmedSeriesPlanVersionRef": record.confirmedSeriesPlanVersionRef,
            "status": record.status,
            "createdAt": record.createdAt,
            "updatedAt": record.updatedAt,
            "version": record.version,
        }

    @staticmethod
    def _version_mapping(record: SeriesPlanVersionRecord) -> dict[str, Any]:
        return {
            "schemaVersion": record.schemaVersion,
            "workspaceRef": record.workspaceRef,
            "contentProfileRef": record.contentProfileRef,
            "projectRef": record.projectRef,
            "seriesRef": record.seriesRef,
            "seriesPlanRef": record.seriesPlanRef,
            "seriesPlanVersionRef": record.seriesPlanVersionRef,
            "versionNumber": record.versionNumber,
            **json.loads(record.contentJson),
            "changeKind": record.changeKind,
            "parentSeriesPlanVersionRef": record.parentSeriesPlanVersionRef,
            "createdAt": record.createdAt,
        }

    def get_workspace(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        command = {"workspaceRef": workspace_ref, "projectRef": project_ref, "seriesRef": series_ref}
        context = _project_context(self.project_reader, command)
        plan = self.repository.get_plan(workspace_ref, project_ref, series_ref)
        versions = self.repository.list_versions(workspace_ref, plan.seriesPlanRef) if plan else []
        return {
            "schemaVersion": SERIES_PLAN_WORKSPACE_SCHEMA_VERSION,
            "context": context,
            "plan": self._plan_mapping(plan) if plan else None,
            "versions": [self._version_mapping(item) for item in versions],
        }

    def confirm_candidate(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if command.get("humanConfirmed") is not True:
            raise PlanNotConfirmedError("explicit human confirmation is required")
        context = _project_context(self.project_reader, command)
        if self.repository.get_plan(context["workspaceRef"], context["projectRef"], context["seriesRef"]):
            raise DuplicateRecordError("Series Plan already exists; create a new version instead")
        content = _normalize_content(
            command.get("candidate"),
            planned_count=int(context["project"]["plannedEpisodeCount"]),
            ref_factory=self._ref_factory,
        )
        now = self._clock()
        plan_ref = self._ref_factory("series-plan")
        version_ref = self._ref_factory("series-plan-version")
        plan = SeriesPlanRecord(
            SERIES_PLAN_SCHEMA_VERSION,
            context["workspaceRef"], context["contentProfileRef"], context["projectRef"],
            context["seriesRef"], plan_ref, version_ref, version_ref, "confirmed", now, now, 1,
        )
        version = SeriesPlanVersionRecord(
            SERIES_PLAN_VERSION_SCHEMA_VERSION,
            context["workspaceRef"], context["contentProfileRef"], context["projectRef"],
            context["seriesRef"], plan_ref, version_ref, 1,
            json.dumps(content, ensure_ascii=False, sort_keys=True), "ai-candidate-confirmed", None, now,
        )
        stored_plan, stored_version = self.repository.create_plan_with_version(plan, version)
        return {"plan": self._plan_mapping(stored_plan), "version": self._version_mapping(stored_version)}

    def create_manual_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        context = _project_context(self.project_reader, command)
        plan_ref = _required_ref(command.get("seriesPlanRef"), "seriesPlanRef")
        plan = self.repository.get_plan_by_ref(context["workspaceRef"], plan_ref)
        if plan is None:
            raise RecordNotFoundError("Series Plan was not found")
        if (plan.projectRef, plan.seriesRef) != (context["projectRef"], context["seriesRef"]):
            raise ScopeMismatchError("Series Plan does not belong to Project and Series")
        expected_plan_version = _positive_int(command.get("expectedPlanVersion"), "expectedPlanVersion")
        current = self.repository.get_version(
            context["workspaceRef"], plan.seriesPlanRef, plan.currentSeriesPlanVersionRef
        )
        if current is None:
            raise RecordNotFoundError("current Series Plan version was not found")
        current_content = json.loads(current.contentJson)
        existing_refs = {item["episodePlanItemRef"] for item in current_content["episodePlanItems"]}
        candidate = dict(command.get("content") or {})
        candidate["schemaVersion"] = SERIES_PLAN_CANDIDATE_SCHEMA_VERSION
        content = _normalize_content(
            candidate,
            planned_count=int(context["project"]["plannedEpisodeCount"]),
            ref_factory=self._ref_factory,
            existing_item_refs=existing_refs,
        )
        now = self._clock()
        version_ref = self._ref_factory("series-plan-version")
        version = SeriesPlanVersionRecord(
            SERIES_PLAN_VERSION_SCHEMA_VERSION,
            plan.workspaceRef, plan.contentProfileRef, plan.projectRef, plan.seriesRef,
            plan.seriesPlanRef, version_ref, current.versionNumber + 1,
            json.dumps(content, ensure_ascii=False, sort_keys=True), "manual-edit",
            current.seriesPlanVersionRef, now,
        )
        updated = replace(
            plan,
            currentSeriesPlanVersionRef=version_ref,
            status="draft",
            updatedAt=now,
            version=plan.version + 1,
        )
        stored, stored_version = self.repository.append_version(updated, version, expected_plan_version)
        return {"plan": self._plan_mapping(stored), "version": self._version_mapping(stored_version)}

    def confirm_version(self, command: Mapping[str, Any]) -> dict[str, Any]:
        if command.get("humanConfirmed") is not True:
            raise PlanNotConfirmedError("explicit human confirmation is required")
        workspace_ref = _required_ref(command.get("workspaceRef"), "workspaceRef")
        plan_ref = _required_ref(command.get("seriesPlanRef"), "seriesPlanRef")
        version_ref = _required_ref(command.get("seriesPlanVersionRef"), "seriesPlanVersionRef")
        expected = _positive_int(command.get("expectedPlanVersion"), "expectedPlanVersion")
        plan = self.repository.get_plan_by_ref(workspace_ref, plan_ref)
        if plan is None:
            raise RecordNotFoundError("Series Plan was not found")
        if version_ref != plan.currentSeriesPlanVersionRef:
            raise VersionConflictError("only the current Series Plan version can be confirmed")
        if self.repository.get_version(workspace_ref, plan_ref, version_ref) is None:
            raise RecordNotFoundError("Series Plan version was not found")
        updated = replace(
            plan,
            confirmedSeriesPlanVersionRef=version_ref,
            status="confirmed",
            updatedAt=self._clock(),
            version=plan.version + 1,
        )
        return self._plan_mapping(self.repository.confirm_version(updated, expected))

    def build_m6_bootstrap(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        workspace = self.get_workspace(workspace_ref, project_ref, series_ref)
        plan = workspace["plan"]
        if not plan or not plan["confirmedSeriesPlanVersionRef"]:
            raise PlanNotConfirmedError("Series Plan has no confirmed version")
        version = next(
            item for item in workspace["versions"]
            if item["seriesPlanVersionRef"] == plan["confirmedSeriesPlanVersionRef"]
        )
        return {
            "schemaVersion": M6_BOOTSTRAP_SCHEMA_VERSION,
            "workspaceRef": workspace_ref,
            "contentProfileRef": plan["contentProfileRef"],
            "projectRef": project_ref,
            "seriesRef": series_ref,
            "seriesPlanRef": plan["seriesPlanRef"],
            "seriesPlanVersionRef": version["seriesPlanVersionRef"],
            "mainArcs": version["mainArcs"],
            "episodePlanItems": version["episodePlanItems"],
            "characterArcIntents": version["characterArcIntents"],
            "worldIntent": version["worldIntent"],
            "continuityIntent": version["continuityIntent"],
            "foreshadowingContext": version["foreshadowingContext"],
        }

    def get_confirmed_m6_source_snapshot(
        self, workspace_ref: str, project_ref: str, series_ref: str
    ) -> dict[str, Any]:
        """Return M5-owned, read-only confirmed input and its canonical digest."""
        bootstrap = self.build_m6_bootstrap(workspace_ref, project_ref, series_ref)
        snapshot = {
            "schemaVersion": M6_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "workspaceRef": bootstrap["workspaceRef"],
            "contentProfileRef": bootstrap["contentProfileRef"],
            "projectRef": bootstrap["projectRef"],
            "seriesRef": bootstrap["seriesRef"],
            "seriesPlanRef": bootstrap["seriesPlanRef"],
            "seriesPlanVersionRef": bootstrap["seriesPlanVersionRef"],
            "status": "confirmed",
            "mainArcs": bootstrap["mainArcs"],
            "episodePlanItems": bootstrap["episodePlanItems"],
            "characterArcIntents": bootstrap["characterArcIntents"],
            "worldIntent": bootstrap["worldIntent"],
            "continuityIntent": bootstrap["continuityIntent"],
            "foreshadowingContext": bootstrap["foreshadowingContext"],
        }
        # Digest ownership stays in M5. M6 is allowed only to compare this value.
        snapshot["seriesPlanVersionDigest"] = _m6_source_digest(snapshot)
        return json.loads(json.dumps(snapshot, ensure_ascii=False))
