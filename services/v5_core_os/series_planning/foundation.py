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
SERIES_PLAN_VERSION_SCHEMA_VERSION_V2 = "v5.series-plan-version.v2"
SERIES_PLAN_CANDIDATE_SCHEMA_VERSION = "creator.series-plan.candidate.v1"
SERIES_PLAN_CANDIDATE_SCHEMA_VERSION_V2 = "creator.series-plan.candidate.v2"
SERIES_PLAN_WORKSPACE_SCHEMA_VERSION = "creator.series-planning.workspace.v1"
M6_BOOTSTRAP_SCHEMA_VERSION = "creator.series-plan.m6-bootstrap.v1"
M6_SOURCE_SNAPSHOT_SCHEMA_VERSION = "v5.series-plan.m6-source-snapshot.v1"
M6_SOURCE_SNAPSHOT_SCHEMA_VERSION_V2 = "v5.series-plan.m6-source-snapshot.v2"
SQLITE_SCHEMA_VERSION = 1

_SERIES_PLAN_CONTENT_FIELDS = frozenset({
    "seriesConcept", "premise", "logline", "mainNarrativeDirection", "mainArcs",
    "subArcs", "characterArcIntents", "episodePlanItems", "narrativeRhythm",
    "worldIntent", "continuityIntent", "foreshadowingContext", "productionAssumptions",
})
_BINDING_VERSION_COMMAND_FIELDS = frozenset({
    "workspaceRef", "projectRef", "seriesRef", "seriesPlanRef",
    "expectedPlanVersion", "episodePlanItemBindings",
})


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


class LifecycleUnavailableError(SeriesPlanningError):
    code = "lifecycle_unavailable"


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


def _is_canonical_ref(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= 200
        and value.isprintable()
        and not any(character.isspace() for character in value)
    )


def _is_canonical_timestamp(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and 0 < len(value) <= 100
        and value.isprintable()
    )


def _positive_int(value: Any, field: str, *, maximum: int = 100_000) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise SeriesPlanningError(f"{field} must be an integer")
    if value < 1 or value > maximum:
        raise SeriesPlanningError(f"{field} is out of range")
    return value


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
    def lifecycle_has_episode_binding_dependency(
        self, workspace_ref: str, series_ref: str, episode_ref: str
    ) -> bool: ...


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
        record = self._plans.get((workspace_ref, plan_ref)) if plan_ref else None
        if record is not None and (
            record.workspaceRef != workspace_ref
            or record.seriesPlanRef != plan_ref
        ):
            raise VersionConflictError("Series Plan storage identity is invalid")
        return record

    def get_plan_by_ref(self, workspace_ref, plan_ref):
        record = self._plans.get((workspace_ref, plan_ref))
        if record is not None and (
            record.workspaceRef != workspace_ref
            or record.seriesPlanRef != plan_ref
        ):
            raise VersionConflictError("Series Plan storage identity is invalid")
        return record

    def get_version(self, workspace_ref, plan_ref, version_ref):
        return self._versions.get((workspace_ref, plan_ref, version_ref))

    def list_versions(self, workspace_ref, plan_ref):
        items = []
        for key, item in self._versions.items():
            if key[0] != workspace_ref or key[1] != plan_ref:
                continue
            if (
                key != (item.workspaceRef, item.seriesPlanRef, item.seriesPlanVersionRef)
                or not isinstance(item.versionNumber, int)
                or isinstance(item.versionNumber, bool)
            ):
                raise VersionConflictError("Series Plan version storage identity is invalid")
            items.append(item)
        return sorted(items, key=lambda item: item.versionNumber)

    def lifecycle_has_episode_binding_dependency(self, workspace_ref, series_ref, episode_ref):
        with self._lock:
            indexed_plans = {
                plan_ref: project_ref
                for (indexed_workspace, project_ref, indexed_series), plan_ref
                in self._scope_index.items()
                if indexed_workspace == workspace_ref and indexed_series == series_ref
            }
            if any(
                (workspace_ref, plan_ref) not in self._plans
                for plan_ref in indexed_plans
            ):
                return True
            plans = {}
            for key, item in self._plans.items():
                storage_workspace, storage_plan_ref = key
                relevant = (
                    storage_workspace == workspace_ref
                    and (
                        item.seriesRef == series_ref
                        or storage_plan_ref in indexed_plans
                    )
                )
                if not relevant:
                    continue
                if (item.workspaceRef, item.seriesPlanRef) != key:
                    return True
                if storage_plan_ref in indexed_plans and (
                    item.seriesRef != series_ref
                    or item.projectRef != indexed_plans[storage_plan_ref]
                ):
                    return True
                plans[storage_plan_ref] = item
            versions = []
            for key, item in self._versions.items():
                relevant = (
                    key[0] == workspace_ref and key[1] in plans
                ) or (
                    item.workspaceRef == workspace_ref and item.seriesRef == series_ref
                )
                if not relevant:
                    continue
                if key != (item.workspaceRef, item.seriesPlanRef, item.seriesPlanVersionRef):
                    return True
                versions.append(item)
        for plan_ref, plan in plans.items():
            scoped = [item for item in versions if item.seriesPlanRef == plan_ref]
            if _history_depends_on_episode_or_is_uncertain(
                scoped,
                plan,
                episode_ref,
            ):
                return True
        return any(
            _version_depends_on_episode_or_is_uncertain(
                item,
                episode_ref,
                parent=None,
            )
            for item in versions
            if item.seriesPlanRef not in plans
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

    def lifecycle_has_episode_binding_dependency(self, workspace_ref, series_ref, episode_ref):
        try:
            with self._session() as connection:
                plan_rows = connection.execute(
                    "SELECT DISTINCT p.* FROM v5_series_plans p "
                    "LEFT JOIN v5_project_series_relationships target_relationship "
                    "ON p.workspace_ref = target_relationship.workspace_ref "
                    "AND p.project_ref = target_relationship.project_ref "
                    "AND target_relationship.series_ref = ? "
                    "LEFT JOIN v5_project_series_relationships own_relationship "
                    "ON p.workspace_ref = own_relationship.workspace_ref "
                    "AND p.project_ref = own_relationship.project_ref "
                    "AND p.series_ref = own_relationship.series_ref "
                    "WHERE p.workspace_ref = ? "
                    "AND (p.series_ref = ? OR (target_relationship.series_ref IS NOT NULL "
                    "AND own_relationship.series_ref IS NULL))",
                    (series_ref, workspace_ref, series_ref),
                ).fetchall()
                rows = connection.execute(
                    "SELECT v.*, p.schema_version AS parent_schema_version, "
                    "p.content_profile_ref AS parent_content_profile_ref, "
                    "p.project_ref AS parent_project_ref, p.series_ref AS parent_series_ref, "
                    "p.current_version_ref AS parent_current_version_ref, "
                    "p.confirmed_version_ref AS parent_confirmed_version_ref, "
                    "p.status AS parent_status, p.created_at AS parent_created_at, "
                    "p.updated_at AS parent_updated_at, p.version AS parent_version "
                    "FROM v5_series_plan_versions v LEFT JOIN v5_series_plans p "
                    "ON v.workspace_ref = p.workspace_ref "
                    "AND v.series_plan_ref = p.series_plan_ref "
                    "LEFT JOIN v5_project_series_relationships target_relationship "
                    "ON p.workspace_ref = target_relationship.workspace_ref "
                    "AND p.project_ref = target_relationship.project_ref "
                    "AND target_relationship.series_ref = ? "
                    "LEFT JOIN v5_project_series_relationships own_relationship "
                    "ON p.workspace_ref = own_relationship.workspace_ref "
                    "AND p.project_ref = own_relationship.project_ref "
                    "AND p.series_ref = own_relationship.series_ref "
                    "WHERE (v.workspace_ref = ? AND v.series_ref = ?) "
                    "OR (p.workspace_ref = ? AND (p.series_ref = ? "
                    "OR (target_relationship.series_ref IS NOT NULL "
                    "AND own_relationship.series_ref IS NULL))) "
                    "ORDER BY v.series_plan_ref, v.version_number",
                    (
                        series_ref,
                        workspace_ref,
                        series_ref,
                        workspace_ref,
                        series_ref,
                    ),
                ).fetchall()
        except sqlite3.DatabaseError:
            return True
        histories: dict[str, tuple[SeriesPlanRecord | None, list[SeriesPlanVersionRecord]]] = {
            row["series_plan_ref"]: (self._plan(row), [])
            for row in plan_rows
        }
        for row in rows:
            parent = None
            if row["parent_schema_version"] is not None:
                parent = SeriesPlanRecord(
                    row["parent_schema_version"],
                    row["workspace_ref"],
                    row["parent_content_profile_ref"],
                    row["parent_project_ref"],
                    row["parent_series_ref"],
                    row["series_plan_ref"],
                    row["parent_current_version_ref"],
                    row["parent_confirmed_version_ref"],
                    row["parent_status"],
                    row["parent_created_at"],
                    row["parent_updated_at"],
                    row["parent_version"],
                )
            entry = histories.setdefault(row["series_plan_ref"], (parent, []))
            if entry[0] != parent:
                return True
            entry[1].append(self._version(row))
        for parent, versions in histories.values():
            if _history_depends_on_episode_or_is_uncertain(
                versions,
                parent,
                episode_ref,
            ):
                return True
        return False


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
    allowed = _SERIES_PLAN_CONTENT_FIELDS | {"schemaVersion"}
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


def _reject_json_float(_value: str) -> float:
    raise SeriesPlanningError("Series Plan version JSON cannot contain floating-point values")


def _reject_json_constant(_value: str) -> None:
    raise SeriesPlanningError("Series Plan version JSON is not canonical JSON")


def _strict_json_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized_keys: set[str] = set()
    for key, value in pairs:
        normalized_key = unicodedata.normalize("NFC", key)
        if normalized_key in normalized_keys:
            raise SeriesPlanningError("Series Plan version JSON has duplicate normalized keys")
        normalized_keys.add(normalized_key)
        result[normalized_key] = value
    return result


def _load_strict_json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_strict_json_object_pairs,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise SeriesPlanningError("Series Plan version JSON is invalid") from exc
    if not isinstance(value, dict):
        raise SeriesPlanningError("Series Plan version content must be an object")
    return value


def _validate_stored_v1_content(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != _SERIES_PLAN_CONTENT_FIELDS:
        raise SeriesPlanningError("Series Plan version content fields are invalid")
    raw_items = _mapping_list(value.get("episodePlanItems"), "episodePlanItems")
    item_refs = [
        _required_ref(item.get("episodePlanItemRef"), "episodePlanItemRef")
        for item in raw_items
    ]
    if len(set(item_refs)) != len(item_refs):
        raise SeriesPlanningError("Episode Plan Item identities must be unique")
    candidate = {"schemaVersion": SERIES_PLAN_CANDIDATE_SCHEMA_VERSION, **dict(value)}
    normalized = _normalize_content(
        candidate,
        planned_count=len(raw_items),
        ref_factory=lambda _prefix: "",
        existing_item_refs=set(item_refs),
    )
    if normalized != value:
        raise SeriesPlanningError("Series Plan version content is not canonical")
    return normalized


def _normalize_episode_plan_item_bindings(
    value: Any,
    episode_plan_items: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    item_positions = {
        _required_ref(item.get("episodePlanItemRef"), "episodePlanItemRef"): position
        for position, item in enumerate(episode_plan_items)
    }
    if len(item_positions) != len(episode_plan_items):
        raise SeriesPlanningError("Episode Plan Item identities must be unique")
    bindings: list[dict[str, str]] = []
    episode_refs: set[str] = set()
    item_refs: set[str] = set()
    for index, item in enumerate(_mapping_list(value, "episodePlanItemBindings")):
        if set(item) != {"episodeRef", "episodePlanItemRef"}:
            raise SeriesPlanningError(f"episodePlanItemBindings[{index}] fields are invalid")
        episode_ref = _required_ref(item.get("episodeRef"), "episodeRef")
        item_ref = _required_ref(item.get("episodePlanItemRef"), "episodePlanItemRef")
        if episode_ref in episode_refs or item_ref in item_refs:
            raise SeriesPlanningError("Episode Plan Item binding identities must be unique")
        if item_ref not in item_positions:
            raise ScopeMismatchError("Episode Plan Item does not belong to current Series Plan version")
        episode_refs.add(episode_ref)
        item_refs.add(item_ref)
        bindings.append({"episodeRef": episode_ref, "episodePlanItemRef": item_ref})
    return sorted(
        bindings,
        key=lambda item: (item_positions[item["episodePlanItemRef"]], item["episodeRef"]),
    )


def _validated_version_content(record: SeriesPlanVersionRecord) -> dict[str, Any]:
    value = _load_strict_json_object(record.contentJson)
    if record.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION:
        return _validate_stored_v1_content(value)
    if record.schemaVersion != SERIES_PLAN_VERSION_SCHEMA_VERSION_V2:
        raise SeriesPlanningError("Series Plan version schemaVersion is unsupported")
    if json.dumps(value, ensure_ascii=False, sort_keys=True) != record.contentJson:
        raise SeriesPlanningError("Series Plan v2 content JSON is not canonical")
    if set(value) != _SERIES_PLAN_CONTENT_FIELDS | {"episodePlanItemBindings"}:
        raise SeriesPlanningError("Series Plan v2 content fields are invalid")
    base = {key: value[key] for key in _SERIES_PLAN_CONTENT_FIELDS}
    normalized_base = _validate_stored_v1_content(base)
    bindings = _normalize_episode_plan_item_bindings(
        value.get("episodePlanItemBindings"),
        normalized_base["episodePlanItems"],
    )
    if bindings != value.get("episodePlanItemBindings"):
        raise SeriesPlanningError("Episode Plan Item bindings are not canonically ordered")
    return {**normalized_base, "episodePlanItemBindings": bindings}


def _validate_version_lineage(
    record: SeriesPlanVersionRecord,
    plan: SeriesPlanRecord,
) -> None:
    if (
        not _is_canonical_ref(record.seriesPlanVersionRef)
        or not _is_canonical_ref(record.seriesPlanRef)
        or not _is_canonical_ref(record.workspaceRef)
        or not _is_canonical_ref(record.contentProfileRef)
        or not _is_canonical_ref(record.projectRef)
        or not _is_canonical_ref(record.seriesRef)
        or (
            record.parentSeriesPlanVersionRef is not None
            and not _is_canonical_ref(record.parentSeriesPlanVersionRef)
        )
        or not _is_canonical_timestamp(record.createdAt)
    ):
        raise VersionConflictError("Series Plan version identity lineage is invalid")
    if (
        record.workspaceRef != plan.workspaceRef
        or record.contentProfileRef != plan.contentProfileRef
        or record.projectRef != plan.projectRef
        or record.seriesRef != plan.seriesRef
        or record.seriesPlanRef != plan.seriesPlanRef
    ):
        raise ScopeMismatchError("Series Plan version scope lineage is invalid")
    if (
        not isinstance(record.versionNumber, int)
        or isinstance(record.versionNumber, bool)
        or record.versionNumber < 1
    ):
        raise VersionConflictError("Series Plan version number is invalid")


def _validate_plan_lineage(
    plan: SeriesPlanRecord,
    *,
    context: Mapping[str, Any] | None = None,
) -> None:
    if (
        plan.schemaVersion != SERIES_PLAN_SCHEMA_VERSION
        or not _is_canonical_ref(plan.workspaceRef)
        or not _is_canonical_ref(plan.contentProfileRef)
        or not _is_canonical_ref(plan.projectRef)
        or not _is_canonical_ref(plan.seriesRef)
        or not _is_canonical_ref(plan.seriesPlanRef)
        or not _is_canonical_ref(plan.currentSeriesPlanVersionRef)
        or (
            plan.confirmedSeriesPlanVersionRef is not None
            and not _is_canonical_ref(plan.confirmedSeriesPlanVersionRef)
        )
        or plan.status not in {"draft", "confirmed"}
        or not _is_canonical_timestamp(plan.createdAt)
        or not _is_canonical_timestamp(plan.updatedAt)
        or not isinstance(plan.version, int)
        or isinstance(plan.version, bool)
        or plan.version < 1
    ):
        raise VersionConflictError("Series Plan identity lineage is invalid")
    if context is not None and (
        plan.workspaceRef != context.get("workspaceRef")
        or plan.contentProfileRef != context.get("contentProfileRef")
        or plan.projectRef != context.get("projectRef")
        or plan.seriesRef != context.get("seriesRef")
    ):
        raise ScopeMismatchError("Series Plan does not match trusted Project context")


def _validate_current_version_lineage(
    record: SeriesPlanVersionRecord,
    plan: SeriesPlanRecord,
    versions: list[SeriesPlanVersionRecord],
) -> None:
    _validate_plan_lineage(plan)
    _validate_version_lineage(record, plan)
    if any(
        not isinstance(item.versionNumber, int)
        or isinstance(item.versionNumber, bool)
        or item.versionNumber < 1
        for item in versions
    ):
        raise VersionConflictError("Series Plan version number is invalid")
    ordered = sorted(versions, key=lambda item: item.versionNumber)
    seen_v2 = False
    for index, item in enumerate(ordered, start=1):
        _validate_version_lineage(item, plan)
        if item.versionNumber != index:
            raise VersionConflictError("Series Plan version sequence is invalid")
        if index == 1:
            if (
                item.parentSeriesPlanVersionRef is not None
                or item.schemaVersion != SERIES_PLAN_VERSION_SCHEMA_VERSION
                or item.changeKind != "ai-candidate-confirmed"
            ):
                raise VersionConflictError("Series Plan root version lineage is invalid")
        else:
            if item.parentSeriesPlanVersionRef != ordered[index - 2].seriesPlanVersionRef:
                raise VersionConflictError("Series Plan parent version lineage is invalid")
            if item.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION_V2:
                if item.changeKind != "episode-plan-item-binding":
                    raise VersionConflictError("Series Plan v2 operation lineage is invalid")
                seen_v2 = True
            elif item.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION:
                if seen_v2 or item.changeKind != "manual-edit":
                    raise VersionConflictError("Series Plan v1 operation lineage is invalid")
            else:
                raise VersionConflictError("Series Plan version schema lineage is invalid")
    refs = {item.seriesPlanVersionRef for item in ordered}
    if (
        not ordered
        or len(refs) != len(ordered)
        or any(
            not isinstance(item.seriesPlanVersionRef, str)
            or not item.seriesPlanVersionRef.strip()
            or len(item.seriesPlanVersionRef) > 200
            for item in ordered
        )
        or ordered[-1].seriesPlanVersionRef != plan.currentSeriesPlanVersionRef
        or record.seriesPlanVersionRef != plan.currentSeriesPlanVersionRef
        or record.versionNumber != len(ordered)
        or not isinstance(plan.version, int)
        or isinstance(plan.version, bool)
        or plan.version < len(ordered)
        or (
            plan.confirmedSeriesPlanVersionRef is not None
            and plan.confirmedSeriesPlanVersionRef not in refs
        )
    ):
        raise VersionConflictError("Series Plan current version lineage is invalid")


def _version_depends_on_episode_or_is_uncertain(
    record: SeriesPlanVersionRecord,
    episode_ref: str,
    *,
    parent: SeriesPlanRecord | None = None,
) -> bool:
    if parent is None:
        return True
    if (
        record.workspaceRef != parent.workspaceRef
        or record.contentProfileRef != parent.contentProfileRef
        or record.projectRef != parent.projectRef
        or record.seriesRef != parent.seriesRef
        or record.seriesPlanRef != parent.seriesPlanRef
    ):
        return True
    try:
        content = _validated_version_content(record)
    except (SeriesPlanningError, TypeError, ValueError):
        return True
    if record.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION:
        return False
    return any(
        binding["episodeRef"] == episode_ref
        for binding in content["episodePlanItemBindings"]
    )


def _history_depends_on_episode_or_is_uncertain(
    versions: list[SeriesPlanVersionRecord],
    parent: SeriesPlanRecord | None,
    episode_ref: str,
) -> bool:
    if parent is None or not versions:
        return True
    try:
        _validate_plan_lineage(parent)
    except (SeriesPlanningError, TypeError, ValueError):
        return True
    if any(
        not isinstance(record.versionNumber, int)
        or isinstance(record.versionNumber, bool)
        or record.versionNumber < 1
        for record in versions
    ):
        return True
    ordered = sorted(versions, key=lambda item: item.versionNumber)
    seen_v2 = False
    for index, record in enumerate(ordered, start=1):
        try:
            _validate_version_lineage(record, parent)
        except (SeriesPlanningError, TypeError, ValueError):
            return True
        if _version_depends_on_episode_or_is_uncertain(
            record,
            episode_ref,
            parent=parent,
        ):
            return True
        if record.versionNumber != index:
            return True
        if index == 1:
            if (
                record.parentSeriesPlanVersionRef is not None
                or record.schemaVersion != SERIES_PLAN_VERSION_SCHEMA_VERSION
                or record.changeKind != "ai-candidate-confirmed"
            ):
                return True
        else:
            previous = ordered[index - 2]
            if record.parentSeriesPlanVersionRef != previous.seriesPlanVersionRef:
                return True
            if record.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION_V2:
                if record.changeKind != "episode-plan-item-binding":
                    return True
                seen_v2 = True
            elif record.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION:
                if seen_v2 or record.changeKind != "manual-edit":
                    return True
            else:
                return True
    refs = {record.seriesPlanVersionRef for record in ordered}
    if (
        len(refs) != len(ordered)
        or any(
            not isinstance(record.seriesPlanVersionRef, str)
            or not record.seriesPlanVersionRef.strip()
            or len(record.seriesPlanVersionRef) > 200
            for record in ordered
        )
        or ordered[-1].seriesPlanVersionRef != parent.currentSeriesPlanVersionRef
        or not isinstance(parent.version, int)
        or isinstance(parent.version, bool)
        or parent.version < len(ordered)
        or (
            parent.confirmedSeriesPlanVersionRef is not None
            and parent.confirmedSeriesPlanVersionRef not in refs
        )
    ):
        return True
    return False


def _trusted_binding_context(
    reader: UpstreamProjectReader,
    workspace_ref: str,
    project_ref: str,
    series_ref: str,
    episode_ref: str | None = None,
) -> dict[str, Any]:
    try:
        context = reader.build_context(workspace_ref, project_ref, series_ref, episode_ref)
    except Exception as exc:
        code = str(getattr(exc, "code", ""))
        if code in {"not_found", "scope_mismatch"}:
            raise ScopeMismatchError("trusted Project, Series, or Episode scope does not match") from None
        raise LifecycleUnavailableError("trusted binding context is unavailable") from None
    if not isinstance(context, Mapping):
        raise LifecycleUnavailableError("trusted binding context is unavailable")
    project = context.get("project")
    series = context.get("series")
    episode = context.get("episode")
    series_refs = project.get("seriesRefs") if isinstance(project, Mapping) else None
    content_profile_ref = context.get("contentProfileRef")
    if (
        context.get("workspaceRef") != workspace_ref
        or context.get("projectRef") != project_ref
        or context.get("seriesRef") != series_ref
        or not isinstance(project, Mapping)
        or project.get("workspaceRef") != workspace_ref
        or project.get("projectRef") != project_ref
        or not isinstance(series_refs, (list, tuple))
        or series_ref not in series_refs
        or not isinstance(series, Mapping)
        or series.get("workspaceRef") != workspace_ref
        or series.get("seriesRef") != series_ref
        or not _is_canonical_ref(content_profile_ref)
        or project.get("contentProfileRef") != content_profile_ref
        or series.get("contentProfileRef") != content_profile_ref
    ):
        raise ScopeMismatchError("trusted Project-to-Series context does not match")
    if episode_ref is not None and (
        context.get("episodeRef") != episode_ref
        or not isinstance(episode, Mapping)
        or episode.get("workspaceRef") != workspace_ref
        or episode.get("seriesRef") != series_ref
        or episode.get("episodeRef") != episode_ref
    ):
        raise ScopeMismatchError("trusted Episode membership does not match")
    return dict(context)


class SeriesPlanningService:
    def __init__(
        self,
        repository: SeriesPlanningRepository,
        project_reader: UpstreamProjectReader,
        *,
        binding_context_reader: UpstreamProjectReader | None = None,
        ref_factory: Callable[[str], str] | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self.repository = repository
        self.project_reader = project_reader
        self.binding_context_reader = binding_context_reader
        self._lifecycle_token: object | None = None
        self._ref_factory = ref_factory or (lambda prefix: f"{prefix}-{uuid4().hex}")
        self._clock = clock

    def _bind_lifecycle_assembly(self) -> object:
        if self._lifecycle_token is not None:
            raise RuntimeError("planning service lifecycle assembly is already bound")
        self._lifecycle_token = object()
        return self._lifecycle_token

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
            **_validated_version_content(record),
            "changeKind": record.changeKind,
            "parentSeriesPlanVersionRef": record.parentSeriesPlanVersionRef,
            "createdAt": record.createdAt,
        }

    def get_workspace(self, workspace_ref: str, project_ref: str, series_ref: str) -> dict[str, Any]:
        command = {"workspaceRef": workspace_ref, "projectRef": project_ref, "seriesRef": series_ref}
        context = _project_context(self.project_reader, command)
        plan = self.repository.get_plan(workspace_ref, project_ref, series_ref)
        versions = self.repository.list_versions(workspace_ref, plan.seriesPlanRef) if plan else []
        if plan is not None:
            _validate_plan_lineage(plan, context=context)
            current = next(
                (
                    version for version in versions
                    if version.seriesPlanVersionRef == plan.currentSeriesPlanVersionRef
                ),
                None,
            )
            if current is None:
                raise VersionConflictError("current Series Plan version lineage is invalid")
            _validate_current_version_lineage(current, plan, versions)
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
        _validate_current_version_lineage(
            current,
            plan,
            self.repository.list_versions(context["workspaceRef"], plan.seriesPlanRef),
        )
        if current.schemaVersion != SERIES_PLAN_VERSION_SCHEMA_VERSION:
            raise VersionConflictError("manual versions require a current v1 Series Plan version")
        current_content = _validated_version_content(current)
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

    def create_episode_plan_item_binding_version(
        self,
        command: Mapping[str, Any],
        *,
        lifecycle_token: object | None = None,
    ) -> dict[str, Any]:
        if not isinstance(command, Mapping) or set(command) != _BINDING_VERSION_COMMAND_FIELDS:
            raise SeriesPlanningError("binding-version command fields do not match the accepted contract")
        if (
            self._lifecycle_token is None
            or lifecycle_token is not self._lifecycle_token
            or self.binding_context_reader is None
        ):
            raise LifecycleUnavailableError("lifecycle-bound binding context is required")
        workspace_ref = _required_ref(command.get("workspaceRef"), "workspaceRef")
        project_ref = _required_ref(command.get("projectRef"), "projectRef")
        series_ref = _required_ref(command.get("seriesRef"), "seriesRef")
        plan_ref = _required_ref(command.get("seriesPlanRef"), "seriesPlanRef")
        expected = _positive_int(command.get("expectedPlanVersion"), "expectedPlanVersion")
        context = _trusted_binding_context(
            self.binding_context_reader, workspace_ref, project_ref, series_ref
        )
        plan = self.repository.get_plan_by_ref(workspace_ref, plan_ref)
        if plan is None:
            raise RecordNotFoundError("Series Plan was not found")
        if (plan.projectRef, plan.seriesRef) != (project_ref, series_ref):
            raise ScopeMismatchError("Series Plan does not belong to Project and Series")
        if plan.contentProfileRef != context.get("contentProfileRef"):
            raise ScopeMismatchError("Series Plan content profile does not match trusted context")
        if plan.version != expected:
            raise VersionConflictError("Series Plan version changed")
        current = self.repository.get_version(
            workspace_ref, plan.seriesPlanRef, plan.currentSeriesPlanVersionRef
        )
        if current is None:
            raise RecordNotFoundError("current Series Plan version was not found")
        _validate_current_version_lineage(
            current,
            plan,
            self.repository.list_versions(workspace_ref, plan.seriesPlanRef),
        )
        if current.schemaVersion not in {
            SERIES_PLAN_VERSION_SCHEMA_VERSION,
            SERIES_PLAN_VERSION_SCHEMA_VERSION_V2,
        }:
            raise VersionConflictError("current Series Plan version schema is unsupported")
        current_content = _validated_version_content(current)
        bindings = _normalize_episode_plan_item_bindings(
            command.get("episodePlanItemBindings"), current_content["episodePlanItems"]
        )
        for binding in bindings:
            _trusted_binding_context(
                self.binding_context_reader,
                workspace_ref,
                project_ref,
                series_ref,
                binding["episodeRef"],
            )
        content = {
            key: current_content[key]
            for key in _SERIES_PLAN_CONTENT_FIELDS
        }
        content["episodePlanItemBindings"] = bindings
        now = self._clock()
        version_ref = self._ref_factory("series-plan-version")
        version = SeriesPlanVersionRecord(
            SERIES_PLAN_VERSION_SCHEMA_VERSION_V2,
            plan.workspaceRef, plan.contentProfileRef, plan.projectRef, plan.seriesRef,
            plan.seriesPlanRef, version_ref, current.versionNumber + 1,
            json.dumps(content, ensure_ascii=False, sort_keys=True),
            "episode-plan-item-binding", current.seriesPlanVersionRef, now,
        )
        updated = replace(
            plan,
            currentSeriesPlanVersionRef=version_ref,
            status="draft",
            updatedAt=now,
            version=plan.version + 1,
        )
        stored, stored_version = self.repository.append_version(updated, version, expected)
        return {"plan": self._plan_mapping(stored), "version": self._version_mapping(stored_version)}

    def confirm_version(
        self,
        command: Mapping[str, Any],
        *,
        lifecycle_token: object | None = None,
    ) -> dict[str, Any]:
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
        version = self.repository.get_version(workspace_ref, plan_ref, version_ref)
        if version is None:
            raise RecordNotFoundError("Series Plan version was not found")
        _validate_current_version_lineage(
            version,
            plan,
            self.repository.list_versions(workspace_ref, plan.seriesPlanRef),
        )
        if version.schemaVersion == SERIES_PLAN_VERSION_SCHEMA_VERSION_V2:
            if (
                self._lifecycle_token is None
                or lifecycle_token is not self._lifecycle_token
                or self.binding_context_reader is None
            ):
                raise LifecycleUnavailableError("lifecycle-bound binding context is required")
            content = _validated_version_content(version)
            context = _trusted_binding_context(
                self.binding_context_reader,
                plan.workspaceRef,
                plan.projectRef,
                plan.seriesRef,
            )
            if plan.contentProfileRef != context.get("contentProfileRef"):
                raise ScopeMismatchError("Series Plan content profile does not match trusted context")
            for binding in content["episodePlanItemBindings"]:
                _trusted_binding_context(
                    self.binding_context_reader,
                    plan.workspaceRef,
                    plan.projectRef,
                    plan.seriesRef,
                    binding["episodeRef"],
                )
        elif version.schemaVersion != SERIES_PLAN_VERSION_SCHEMA_VERSION:
            raise VersionConflictError("Series Plan version schema is unsupported")
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
        workspace = self.get_workspace(workspace_ref, project_ref, series_ref)
        plan = workspace["plan"]
        if not plan or not plan["confirmedSeriesPlanVersionRef"]:
            raise PlanNotConfirmedError("Series Plan has no confirmed version")
        version = next(
            (
                item for item in workspace["versions"]
                if item["seriesPlanVersionRef"]
                == plan["confirmedSeriesPlanVersionRef"]
            ),
            None,
        )
        if version is None:
            raise RecordNotFoundError("confirmed Series Plan version was not found")
        snapshot = {
            "schemaVersion": M6_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            "workspaceRef": workspace_ref,
            "contentProfileRef": plan["contentProfileRef"],
            "projectRef": project_ref,
            "seriesRef": series_ref,
            "seriesPlanRef": plan["seriesPlanRef"],
            "seriesPlanVersionRef": version["seriesPlanVersionRef"],
            "status": "confirmed",
            "mainArcs": version["mainArcs"],
            "episodePlanItems": version["episodePlanItems"],
            "characterArcIntents": version["characterArcIntents"],
            "worldIntent": version["worldIntent"],
            "continuityIntent": version["continuityIntent"],
            "foreshadowingContext": version["foreshadowingContext"],
        }
        if version["schemaVersion"] == SERIES_PLAN_VERSION_SCHEMA_VERSION_V2:
            snapshot["schemaVersion"] = M6_SOURCE_SNAPSHOT_SCHEMA_VERSION_V2
            snapshot["episodePlanItemBindings"] = version["episodePlanItemBindings"]
        elif version["schemaVersion"] != SERIES_PLAN_VERSION_SCHEMA_VERSION:
            raise SeriesPlanningError("Series Plan version schemaVersion is unsupported")
        # Digest ownership stays in M5. M6 is allowed only to compare this value.
        snapshot["seriesPlanVersionDigest"] = _m6_source_digest(snapshot)
        return json.loads(json.dumps(snapshot, ensure_ascii=False))
