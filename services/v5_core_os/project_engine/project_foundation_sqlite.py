"""Exact SQLite store for non-authoritative Project foundation commands."""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation

from .project_foundation import (
    ProjectFoundationRecord,
    ProjectFoundationStorageError,
    ProjectFoundationValidationError,
    canonical_json,
    validate_project_foundation_record,
)


MARKER_TABLE = "creator_project_foundation_schema"
MARKER_COMPONENT = "project_foundation_commands"
TABLE = "creator_project_foundation_commands"
INDEX = "ux_creator_project_foundation_commands_idempotency"
SQLITE_COMPONENT_SCHEMA_VERSION = 1
RECORD_COLUMNS = (
    "schema_version",
    "workspace_ref",
    "foundation_ref",
    "idempotency_key",
    "request_digest",
    "request_json",
    "state",
    "result_digest",
    "result_json",
    "created_at",
    "updated_at",
    "version",
)


def marker_statement() -> str:
    return (
        f"CREATE TABLE {MARKER_TABLE} ("
        "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )


def table_statement() -> str:
    return (
        f"CREATE TABLE {TABLE} ("
        "schema_version TEXT NOT NULL, "
        "workspace_ref TEXT NOT NULL, "
        "foundation_ref TEXT NOT NULL, "
        "idempotency_key TEXT NOT NULL, "
        "request_digest TEXT NOT NULL, "
        "request_json TEXT NOT NULL, "
        "state TEXT NOT NULL CHECK(state IN ('PENDING','COMPLETED')), "
        "result_digest TEXT, "
        "result_json TEXT, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, "
        "version INTEGER NOT NULL, "
        "PRIMARY KEY(workspace_ref, foundation_ref), "
        "CHECK((state = 'PENDING' AND result_digest IS NULL "
        "AND result_json IS NULL AND version = 1) OR "
        "(state = 'COMPLETED' AND result_digest IS NOT NULL "
        "AND result_json IS NOT NULL AND version = 2)))"
    )


def index_statement() -> str:
    return (
        f"CREATE UNIQUE INDEX {INDEX} ON {TABLE}("
        "workspace_ref, idempotency_key)"
    )


def _normalized_sql(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def _stored_sql(
    connection: sqlite3.Connection, kind: str, name: str
) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?",
        (kind, name),
    ).fetchone()
    return None if row is None else row[0]


def _record_from_row(row: sqlite3.Row) -> ProjectFoundationRecord:
    return ProjectFoundationRecord(
        row["schema_version"],
        row["workspace_ref"],
        row["foundation_ref"],
        row["idempotency_key"],
        row["request_digest"],
        row["request_json"],
        row["state"],
        row["result_digest"],
        row["result_json"],
        row["created_at"],
        row["updated_at"],
        row["version"],
    )


def _validate_completed_authority(
    connection: sqlite3.Connection,
    record: ProjectFoundationRecord,
    request_value: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    project = result["project"]
    project_row = connection.execute(
        "SELECT * FROM v5_projects WHERE workspace_ref = ? AND project_ref = ?",
        (record.workspaceRef, project.get("projectRef")),
    ).fetchone()
    if project_row is None or (
        project_row["project_ref"] != project.get("projectRef")
        or project_row["schema_version"] != project.get("schemaVersion")
        or project_row["created_at"] != project.get("createdAt")
        or project_row["content_profile_ref"] != request_value["contentProfileRef"]
        or project_row["project_type"] != request_value["project"]["projectType"]
        or project_row["title"] != request_value["project"]["title"]
        or project_row["description"] != request_value["project"]["description"]
        or project_row["target_platform"] != request_value["project"]["targetPlatform"]
        or project_row["aspect_ratio"] != request_value["project"]["aspectRatio"]
        or project_row["default_duration_sec"]
        != request_value["project"]["defaultDurationSec"]
        or project_row["planned_episode_count"]
        != request_value["project"]["plannedEpisodeCount"]
    ):
        raise ProjectFoundationValidationError(
            "completed project foundation Project authority is inconsistent"
        )

    requested_series = request_value.get("series")
    series = result.get("series")
    if requested_series is None:
        relationship = connection.execute(
            "SELECT 1 FROM v5_project_series_relationships "
            "WHERE workspace_ref = ? AND project_ref = ? LIMIT 1",
            (record.workspaceRef, project.get("projectRef")),
        ).fetchone()
        if relationship is not None:
            raise ProjectFoundationValidationError(
                "completed project foundation relationship is inconsistent"
            )
    else:
        series_row = connection.execute(
            "SELECT * FROM v5_series WHERE workspace_ref = ? AND series_ref = ?",
            (record.workspaceRef, series.get("seriesRef")),
        ).fetchone()
        relationship = connection.execute(
            "SELECT 1 FROM v5_project_series_relationships "
            "WHERE workspace_ref = ? AND project_ref = ? AND series_ref = ?",
            (
                record.workspaceRef,
                project.get("projectRef"),
                series.get("seriesRef"),
            ),
        ).fetchone()
        if series_row is None or relationship is None or (
            series_row["series_ref"] != series.get("seriesRef")
            or series_row["schema_version"] != series.get("schemaVersion")
            or series_row["created_at"] != series.get("createdAt")
            or series_row["content_profile_ref"] != request_value["contentProfileRef"]
            or series_row["title"] != requested_series["title"]
            or series_row["description"] != requested_series["description"]
            or series_row["planned_episode_count"]
            != request_value["project"]["plannedEpisodeCount"]
        ):
            raise ProjectFoundationValidationError(
                "completed project foundation Series authority is inconsistent"
            )

    requested_episode = request_value.get("episode")
    episode = result.get("episode")
    if requested_episode is not None:
        episode_row = connection.execute(
            "SELECT * FROM v5_episode_projects "
            "WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ?",
            (
                record.workspaceRef,
                series.get("seriesRef"),
                episode.get("episodeRef"),
            ),
        ).fetchone()
        binding = connection.execute(
            "SELECT * FROM v5_episode_plan_bindings "
            "WHERE workspace_ref = ? AND series_ref = ? AND episode_ref = ? "
            "AND creative_plan_ref = ?",
            (
                record.workspaceRef,
                series.get("seriesRef"),
                episode.get("episodeRef"),
                requested_episode["creativePlanRef"],
            ),
        ).fetchone()
        if episode_row is None or binding is None or (
            episode_row["episode_ref"] != episode.get("episodeRef")
            or episode_row["schema_version"] != episode.get("schemaVersion")
            or episode_row["created_at"] != episode.get("createdAt")
            or episode_row["creative_plan_ref"] != requested_episode["creativePlanRef"]
            or episode_row["episode_number"] != requested_episode["episodeNumber"]
            or episode_row["season_number"] != requested_episode["seasonNumber"]
            or episode_row["volume_number"] != requested_episode["volumeNumber"]
            or episode_row["title"] != requested_episode["title"]
            or binding["source_plan_ref"] != episode.get("sourcePlanRef")
            or binding["source_plan_schema_version"]
            != episode.get("sourcePlanSchemaVersion")
            or binding["source_plan_version"] != episode.get("sourcePlanVersion")
        ):
            raise ProjectFoundationValidationError(
                "completed project foundation Episode authority is inconsistent"
            )


def validate_project_foundation_connection(
    connection: sqlite3.Connection,
) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?)",
            (TABLE, MARKER_TABLE),
        )
    }
    if tables != {TABLE, MARKER_TABLE}:
        raise ProjectFoundationStorageError(
            "partial project foundation command schema"
        )
    if _normalized_sql(_stored_sql(connection, "table", TABLE)) != _normalized_sql(
        table_statement()
    ):
        raise ProjectFoundationStorageError(
            "unsupported project foundation command table definition"
        )
    if _normalized_sql(_stored_sql(connection, "table", MARKER_TABLE)) != _normalized_sql(
        marker_statement()
    ):
        raise ProjectFoundationStorageError(
            "unsupported project foundation marker definition"
        )
    if _normalized_sql(_stored_sql(connection, "index", INDEX)) != _normalized_sql(
        index_statement()
    ):
        raise ProjectFoundationStorageError(
            "unsupported project foundation command index definition"
        )

    columns = connection.execute(f"PRAGMA table_info({TABLE})").fetchall()
    if tuple(row[1] for row in columns) != RECORD_COLUMNS:
        raise ProjectFoundationStorageError(
            "unsupported project foundation command columns"
        )
    expected_types = (
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "INTEGER",
    )
    if tuple(str(row[2]).upper() for row in columns) != expected_types:
        raise ProjectFoundationStorageError(
            "unsupported project foundation command column types"
        )
    if any(int(row[3]) != 1 for row in columns if row[1] not in {"result_digest", "result_json"}):
        raise ProjectFoundationStorageError(
            "unsupported project foundation command column constraints"
        )
    if any(int(row[3]) != 0 for row in columns if row[1] in {"result_digest", "result_json"}):
        raise ProjectFoundationStorageError(
            "unsupported project foundation result column constraints"
        )
    primary_key = tuple(
        row[1]
        for row in sorted(columns, key=lambda item: int(item[5]))
        if int(row[5]) > 0
    )
    if primary_key != ("workspace_ref", "foundation_ref"):
        raise ProjectFoundationStorageError(
            "unsupported project foundation command primary key"
        )

    marker_columns = connection.execute(
        f"PRAGMA table_info({MARKER_TABLE})"
    ).fetchall()
    marker_rows = connection.execute(
        f"SELECT component, schema_version FROM {MARKER_TABLE} ORDER BY component"
    ).fetchall()
    if (
        tuple(row[1] for row in marker_columns)
        != ("component", "schema_version")
        or str(marker_columns[0][2]).upper() != "TEXT"
        or int(marker_columns[0][5]) != 1
        or str(marker_columns[1][2]).upper() != "INTEGER"
        or int(marker_columns[1][3]) != 1
        or int(marker_columns[1][5]) != 0
        or len(marker_rows) != 1
        or tuple(marker_rows[0])
        != (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION)
    ):
        raise ProjectFoundationStorageError(
            "unsupported project foundation command marker"
        )

    rows = connection.execute(
        f"SELECT {','.join(RECORD_COLUMNS)} FROM {TABLE} "
        "ORDER BY workspace_ref, foundation_ref"
    ).fetchall()
    seen_keys: set[tuple[str, str]] = set()
    for row in rows:
        record = _record_from_row(row)
        request_value, result = validate_project_foundation_record(record)
        key = (record.workspaceRef, record.idempotencyKey)
        if key in seen_keys:
            raise ProjectFoundationStorageError(
                "duplicate project foundation idempotency key"
            )
        seen_keys.add(key)
        if result is not None:
            _validate_completed_authority(
                connection,
                record,
                request_value,
                result,
            )


class SqliteProjectFoundationStore:
    """Durable store sharing the Lifecycle SQLite connection during Phase B."""

    def __init__(self, database_path: Path | str, *, lifecycle_state=None) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lifecycle_state = lifecycle_state
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise ProjectFoundationStorageError(
                "foreign key enforcement unavailable"
            )
        return connection

    @contextmanager
    def _session(self, *, write: bool = False, shared: bool = True):
        connection = None
        if shared and self._lifecycle_state is not None:
            connection = self._lifecycle_state.connection_or_none()
        if connection is not None:
            yield connection
            return
        connection = self._connect()
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _presence(connection: sqlite3.Connection) -> tuple[set[str], bool]:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name IN (?, ?)",
                (TABLE, MARKER_TABLE),
            )
        }
        index_present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (INDEX,),
        ).fetchone() is not None
        return tables, index_present

    def _initialize(self) -> None:
        try:
            with self._session(write=True, shared=False) as connection:
                tables, index_present = self._presence(connection)
                if not tables and not index_present:
                    connection.execute(table_statement())
                    connection.execute(index_statement())
                    connection.execute(marker_statement())
                    connection.execute(
                        f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
                        (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
                    )
                elif tables != {TABLE, MARKER_TABLE} or not index_present:
                    raise ProjectFoundationStorageError(
                        "partial project foundation command schema"
                    )
                validate_project_foundation_connection(connection)
        except (ProjectFoundationStorageError, ProjectFoundationValidationError):
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    @staticmethod
    def _record_values(record: ProjectFoundationRecord) -> tuple[Any, ...]:
        return (
            record.schemaVersion,
            record.workspaceRef,
            record.foundationRef,
            record.idempotencyKey,
            record.requestDigest,
            record.requestJson,
            record.state,
            record.resultDigest,
            record.resultJson,
            record.createdAt,
            record.updatedAt,
            record.version,
        )

    def reserve(
        self,
        record: ProjectFoundationRecord,
    ) -> tuple[ProjectFoundationRecord, bool]:
        validate_project_foundation_record(record)
        try:
            with self._session(write=True, shared=False) as connection:
                existing = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref = ? "
                    "AND idempotency_key = ?",
                    (record.workspaceRef, record.idempotencyKey),
                ).fetchone()
                if existing is not None:
                    stored = _record_from_row(existing)
                    validate_project_foundation_record(stored)
                    return stored, False
                connection.execute(
                    f"INSERT INTO {TABLE} ({','.join(RECORD_COLUMNS)}) "
                    f"VALUES ({','.join('?' for _ in RECORD_COLUMNS)})",
                    self._record_values(record),
                )
            return record, True
        except sqlite3.IntegrityError:
            # A competing process may have reserved the same workspace/key
            # between the read and INSERT. Re-read and validate that exact row.
            existing = self.get_by_key(record.workspaceRef, record.idempotencyKey)
            if existing is not None:
                return existing, False
            raise ProjectFoundationStorageError(
                "project foundation storage conflict is unavailable"
            ) from None
        except (ProjectFoundationStorageError, ProjectFoundationValidationError):
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    def get_by_key(
        self, workspace_ref: str, idempotency_key: str
    ) -> ProjectFoundationRecord | None:
        try:
            with self._session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref = ? "
                    "AND idempotency_key = ?",
                    (workspace_ref, idempotency_key),
                ).fetchone()
            if row is None:
                return None
            record = _record_from_row(row)
            validate_project_foundation_record(record)
            return record
        except (ProjectFoundationStorageError, ProjectFoundationValidationError):
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    def get_by_ref(
        self, workspace_ref: str, foundation_ref: str
    ) -> ProjectFoundationRecord | None:
        try:
            with self._session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref = ? "
                    "AND foundation_ref = ?",
                    (workspace_ref, foundation_ref),
                ).fetchone()
            if row is None:
                return None
            record = _record_from_row(row)
            validate_project_foundation_record(record)
            return record
        except (ProjectFoundationStorageError, ProjectFoundationValidationError):
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    def complete(
        self,
        lease: object,
        record: ProjectFoundationRecord,
        result: Mapping[str, Any],
        completed_at: str,
    ) -> ProjectFoundationRecord:
        if self._lifecycle_state is None:
            raise ProjectFoundationStorageError(
                "project foundation lifecycle state is unavailable"
            )
        self._lifecycle_state.validate_lease(
            lease,
            workspace_ref=record.workspaceRef,
            allowed_operations=frozenset(
                {LifecycleOperation.CREATE_PROJECT_FOUNDATION}
            ),
        )
        try:
            with self._session(write=True) as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref = ? "
                    "AND foundation_ref = ?",
                    (record.workspaceRef, record.foundationRef),
                ).fetchone()
                if row is None or _record_from_row(row) != record or record.state != "PENDING":
                    raise ProjectFoundationStorageError(
                        "project foundation state transition is invalid"
                    )
                result_json = canonical_json(dict(result))
                result_digest = sha256(result_json.encode("utf-8")).hexdigest()
                connection.execute(
                    f"UPDATE {TABLE} SET state = 'COMPLETED', "
                    "result_digest = ?, result_json = ?, updated_at = ?, version = 2 "
                    "WHERE workspace_ref = ? AND foundation_ref = ? AND state = 'PENDING'",
                    (
                        result_digest,
                        result_json,
                        completed_at,
                        record.workspaceRef,
                        record.foundationRef,
                    ),
                )
                completed_row = connection.execute(
                    f"SELECT * FROM {TABLE} WHERE workspace_ref = ? "
                    "AND foundation_ref = ?",
                    (record.workspaceRef, record.foundationRef),
                ).fetchone()
                completed = _record_from_row(completed_row)
                validate_project_foundation_record(completed)
                return completed
        except (ProjectFoundationStorageError, ProjectFoundationValidationError):
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    def count(self, workspace_ref: str | None = None) -> int:
        try:
            with self._session() as connection:
                if workspace_ref is None:
                    row = connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()
                else:
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {TABLE} WHERE workspace_ref = ?",
                        (workspace_ref,),
                    ).fetchone()
            return int(row[0])
        except (OSError, sqlite3.DatabaseError) as exc:
            raise ProjectFoundationStorageError(
                "project foundation storage is unavailable"
            ) from exc

    def close(self) -> None:
        return None
