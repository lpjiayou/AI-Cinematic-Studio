"""Durable local-development SQLite repository for M6 Series Intelligence.

The accepted M6 service uses dictionary-shaped repositories.  These mapping
adapters preserve that persistence-neutral service contract while executing every
write through the connection owned by the active lifecycle lease.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
import unicodedata
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from .canonical import normalize
from .errors import (
    DuplicateRecordError,
    IdempotencyConflictError,
    InvalidReferenceError,
    SeriesIntelligenceError,
    VersionConflictError,
)
from .record_integrity import (
    DurableRecordIntegrityError,
    validate_durable_event,
    validate_durable_operation,
    validate_durable_record,
)


_SCOPE_COLUMNS = (
    "business_domain",
    "tenant_id",
    "workspace_ref",
    "project_ref",
    "series_ref",
)

_ROOT_MUTABLE_FIELDS = {
    "v5_m6_series_bibles": frozenset(
        {
            "currentSeriesBibleVersionRef",
            "confirmedSeriesBibleVersionRef",
            "revision",
            "updatedAt",
        }
    ),
    "v5_m6_character_continuities": frozenset(
        {
            "currentCharacterContinuityVersionRef",
            "confirmedCharacterContinuityVersionRef",
            "revision",
            "updatedAt",
        }
    ),
}
_ROOT_VERSION_FIELDS = {
    "v5_m6_series_bibles": (
        "currentSeriesBibleVersionRef",
        "confirmedSeriesBibleVersionRef",
    ),
    "v5_m6_character_continuities": (
        "currentCharacterContinuityVersionRef",
        "confirmedCharacterContinuityVersionRef",
    ),
}
_VERSION_TABLES = frozenset(
    {
        "v5_m6_series_bible_versions",
        "v5_m6_character_continuity_versions",
    }
)
_VERSION_MUTABLE_FIELDS = frozenset({"status", "confirmedAt", "approvalRef"})
_SNAPSHOT_TABLE = "v5_m6_baseline_snapshots"
_SNAPSHOT_MUTABLE_FIELDS = frozenset({"status", "supersededAt"})


def _json_dump(value: Any) -> str:
    return json.dumps(
        normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_json_number(_value: str) -> float:
    raise ValueError("floating-point JSON is not canonical")


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON is not canonical")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _json_load(value: str) -> Any:
    return json.loads(
        value,
        parse_float=_reject_json_number,
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )


def _same_projection(left: Any, right: Any) -> bool:
    """Compare SQLite scalars to JSON projections without bool/int coercion."""

    return type(left) is type(right) and left == right


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _camel(column: str) -> str:
    parts = column.split("_")
    return parts[0] + "".join(item[:1].upper() + item[1:] for item in parts[1:])


def _database_error(exc: sqlite3.DatabaseError, *, conflict: bool = False) -> BaseException:
    """Translate adapter failures without leaking SQL identifiers or engine text."""

    if isinstance(exc, sqlite3.IntegrityError):
        if "foreign key" in str(exc).lower():
            return InvalidReferenceError("M6 lineage reference is invalid")
        if conflict:
            return VersionConflictError("M6 durable state changed")
        return DuplicateRecordError("M6 durable identity already exists")
    return SeriesIntelligenceError("M6 durable persistence failed")


def _read_error() -> SeriesIntelligenceError:
    """Return one stable, detail-free error for durable read/parse failures."""

    return SeriesIntelligenceError("M6 durable persistence failed")


class _SqliteJsonMapping(MutableMapping[tuple[str, ...], dict[str, Any]]):
    def __init__(
        self,
        repository: "SqliteSeriesIntelligenceRepository",
        table: str,
        key_columns: tuple[str, ...],
        *,
        conflict_on_integrity: bool = False,
    ) -> None:
        self._repository = repository
        self._table = table
        self._key_columns = key_columns
        self._conflict_on_integrity = conflict_on_integrity

    def _key(self, raw: tuple[str, ...]) -> tuple[str, ...]:
        key = tuple(raw)
        if len(key) != len(self._key_columns):
            raise KeyError(raw)
        if any(
            not isinstance(item, str)
            or item != unicodedata.normalize("NFC", item)
            for item in key
        ):
            raise InvalidReferenceError("canonical M6 durable key is required")
        return key

    @property
    def _where(self) -> str:
        return " AND ".join(f"{column} = ?" for column in self._key_columns)

    def __getitem__(self, raw_key: tuple[str, ...]) -> dict[str, Any]:
        key = self._key(raw_key)
        try:
            with self._repository._read_session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {self._table} WHERE {self._where}", key
                ).fetchone()
                if row is None:
                    raise KeyError(raw_key)
                return self._repository._validated_record(
                    connection, row, self._table
                )
        except sqlite3.DatabaseError:
            raise _read_error() from None

    @staticmethod
    def _without(record: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if key not in fields}

    def _validate_root_update(
        self, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> None:
        mutable = _ROOT_MUTABLE_FIELDS[self._table]
        if self._without(existing, mutable) != self._without(incoming, mutable):
            raise VersionConflictError("M6 root identity or creation facts are immutable")
        old_revision = existing.get("revision")
        new_revision = incoming.get("revision")
        if (
            isinstance(old_revision, bool)
            or isinstance(new_revision, bool)
            or not isinstance(old_revision, int)
            or not isinstance(new_revision, int)
            or new_revision != old_revision + 1
        ):
            raise VersionConflictError("M6 root revision changed")
        current_field, confirmed_field = _ROOT_VERSION_FIELDS[self._table]
        old_current_ref = existing.get(current_field)
        current_ref = incoming.get(current_field)
        if not isinstance(current_ref, str) or not current_ref:
            raise InvalidReferenceError("current M6 version reference is invalid")
        old_confirmed = existing.get(confirmed_field)
        new_confirmed = incoming.get(confirmed_field)
        if current_ref != old_current_ref:
            if new_confirmed != old_confirmed:
                raise VersionConflictError(
                    "new current M6 version cannot be implicitly confirmed"
                )
        elif new_confirmed not in {old_confirmed, current_ref}:
            raise VersionConflictError("confirmed M6 version is not current")

    def _validate_version_update(
        self, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> None:
        if self._without(existing, _VERSION_MUTABLE_FIELDS) != self._without(
            incoming, _VERSION_MUTABLE_FIELDS
        ):
            # An existing immutable version key with different facts is a generated
            # Ref collision, never an update target.
            raise DuplicateRecordError("M6 immutable version identity already exists")
        transition = (existing.get("status"), incoming.get("status"))
        if transition == ("DRAFT", "CANDIDATE"):
            if (
                incoming.get("confirmedAt") != existing.get("confirmedAt")
                or incoming.get("approvalRef") != existing.get("approvalRef")
            ):
                raise VersionConflictError("candidate transition changed confirmation facts")
            return
        if transition == ("CANDIDATE", "CONFIRMED"):
            if (
                existing.get("confirmedAt") is not None
                or existing.get("approvalRef") is not None
                or not incoming.get("confirmedAt")
                or not incoming.get("approvalRef")
            ):
                raise VersionConflictError("confirmed transition metadata is invalid")
            return
        raise VersionConflictError("immutable M6 version cannot be overwritten")

    def _validate_snapshot_update(
        self, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> None:
        if self._without(existing, _SNAPSHOT_MUTABLE_FIELDS) != self._without(
            incoming, _SNAPSHOT_MUTABLE_FIELDS
        ):
            raise DuplicateRecordError("M6 immutable snapshot identity already exists")
        if (
            existing.get("status") != "ACTIVE"
            or incoming.get("status") != "SUPERSEDED"
            or existing.get("supersededAt") is not None
            or not incoming.get("supersededAt")
        ):
            raise VersionConflictError("immutable M6 snapshot cannot be overwritten")

    def _validate_existing_update(
        self, existing: dict[str, Any], incoming: dict[str, Any]
    ) -> None:
        if self._table in _ROOT_MUTABLE_FIELDS:
            self._validate_root_update(existing, incoming)
            return
        if self._table in _VERSION_TABLES:
            self._validate_version_update(existing, incoming)
            return
        if self._table == _SNAPSHOT_TABLE:
            self._validate_snapshot_update(existing, incoming)
            return
        raise DuplicateRecordError("M6 durable identity already exists")

    def __setitem__(self, raw_key: tuple[str, ...], value: dict[str, Any]) -> None:
        key = self._key(raw_key)
        if not isinstance(value, dict):
            raise TypeError("M6 repository values must be records")
        connection = self._repository._write_connection()
        columns = self._repository._columns(connection, self._table)
        values = self._repository._record_columns(columns, value)
        for column, item in zip(self._key_columns, key):
            if values.get(column) not in (None, item):
                raise InvalidReferenceError("M6 durable key does not match record")
            values[column] = item
        values["record_json"] = _json_dump(value)
        try:
            existing_row = connection.execute(
                f"SELECT * FROM {self._table} WHERE {self._where}", key
            ).fetchone()
            if existing_row is None:
                insert_columns = tuple(values)
                connection.execute(
                    f"INSERT INTO {self._table} ({','.join(insert_columns)}) "
                    f"VALUES ({','.join('?' for _ in insert_columns)})",
                    tuple(values[column] for column in insert_columns),
                )
            else:
                existing = self._repository._validated_record(
                    connection, existing_row, self._table
                )
                self._validate_existing_update(existing, value)
                update_columns = tuple(
                    column for column in values if column not in self._key_columns
                )
                connection.execute(
                    f"UPDATE {self._table} SET "
                    + ",".join(f"{column} = ?" for column in update_columns)
                    + f" WHERE {self._where}",
                    tuple(values[column] for column in update_columns) + key,
                )
            self._repository._fault(f"after-{self._table}-write")
        except sqlite3.DatabaseError as exc:
            raise _database_error(
                exc, conflict=self._conflict_on_integrity
            ) from None

    def __delitem__(self, key: tuple[str, ...]) -> None:
        raise TypeError("M6 immutable history has no physical-delete operation")

    def __iter__(self) -> Iterator[tuple[str, ...]]:
        try:
            with self._repository._read_session() as connection:
                rows = connection.execute(
                    f"SELECT {','.join(self._key_columns)} FROM {self._table} "
                    f"ORDER BY {','.join(self._key_columns)}"
                ).fetchall()
        except sqlite3.DatabaseError:
            raise _read_error() from None
        return iter(tuple(row[column] for column in self._key_columns) for row in rows)

    def __len__(self) -> int:
        try:
            with self._repository._read_session() as connection:
                return int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {self._table}"
                    ).fetchone()[0]
                )
        except sqlite3.DatabaseError:
            raise _read_error() from None


class _ActiveSnapshotMapping(MutableMapping[tuple[str, ...], str]):
    """Projection over the partial-unique ACTIVE snapshot invariant."""

    def __init__(self, repository: "SqliteSeriesIntelligenceRepository") -> None:
        self._repository = repository

    def _key(self, raw: tuple[str, ...]) -> tuple[str, ...]:
        key = tuple(raw)
        if len(key) != len(_SCOPE_COLUMNS):
            raise KeyError(raw)
        return key

    @property
    def _where(self) -> str:
        return " AND ".join(f"{column} = ?" for column in _SCOPE_COLUMNS)

    def __getitem__(self, raw_key: tuple[str, ...]) -> str:
        key = self._key(raw_key)
        try:
            with self._repository._read_session() as connection:
                row = connection.execute(
                    "SELECT m6_baseline_snapshot_ref FROM v5_m6_baseline_snapshots "
                    f"WHERE {self._where} AND status = 'ACTIVE'",
                    key,
                ).fetchone()
        except sqlite3.DatabaseError:
            raise _read_error() from None
        if row is None:
            raise KeyError(raw_key)
        return str(row[0])

    def __setitem__(self, raw_key: tuple[str, ...], snapshot_ref: str) -> None:
        key = self._key(raw_key)
        connection = self._repository._write_connection()
        try:
            row = connection.execute(
                "SELECT 1 FROM v5_m6_baseline_snapshots "
                f"WHERE {self._where} AND m6_baseline_snapshot_ref = ? "
                "AND status = 'ACTIVE'",
                (*key, str(snapshot_ref)),
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise _database_error(exc) from None
        if row is None:
            raise InvalidReferenceError("active M6 baseline snapshot is invalid")

    def __delitem__(self, key: tuple[str, ...]) -> None:
        raise TypeError("M6 active baseline has no physical-delete operation")

    def __iter__(self) -> Iterator[tuple[str, ...]]:
        try:
            with self._repository._read_session() as connection:
                rows = connection.execute(
                    f"SELECT {','.join(_SCOPE_COLUMNS)} "
                    "FROM v5_m6_baseline_snapshots WHERE status = 'ACTIVE' "
                    "ORDER BY " + ",".join(_SCOPE_COLUMNS)
                ).fetchall()
        except sqlite3.DatabaseError:
            raise _read_error() from None
        return iter(tuple(row[column] for column in _SCOPE_COLUMNS) for row in rows)

    def __len__(self) -> int:
        try:
            with self._repository._read_session() as connection:
                return int(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_m6_baseline_snapshots "
                        "WHERE status = 'ACTIVE'"
                    ).fetchone()[0]
                )
        except sqlite3.DatabaseError:
            raise _read_error() from None


class SqliteSeriesIntelligenceRepository:
    """M6 facts, idempotency and Outbox on the accepted lifecycle connection."""

    _TABLES = (
        "v5_m6_series_bibles",
        "v5_m6_series_bible_versions",
        "v5_m6_character_continuities",
        "v5_m6_character_continuity_versions",
        "v5_m6_baseline_snapshots",
        "v5_m6_operations",
        "v5_m6_outbox",
    )

    def __init__(
        self,
        database_path: Path | str,
        *,
        lifecycle_state,
        fault_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.database_path = Path(database_path).resolve()
        self._state = lifecycle_state
        self._lock = RLock()
        self._fault = fault_hook or (lambda _point: None)
        self._column_cache: dict[str, tuple[str, ...]] = {}
        self._validate_schema()
        self.bibles = _SqliteJsonMapping(
            self, "v5_m6_series_bibles", _SCOPE_COLUMNS
        )
        self.bible_versions = _SqliteJsonMapping(
            self,
            "v5_m6_series_bible_versions",
            (*_SCOPE_COLUMNS, "series_bible_ref", "series_bible_version_ref"),
        )
        self.characters = _SqliteJsonMapping(
            self, "v5_m6_character_continuities", _SCOPE_COLUMNS
        )
        self.character_versions = _SqliteJsonMapping(
            self,
            "v5_m6_character_continuity_versions",
            (
                *_SCOPE_COLUMNS,
                "character_continuity_ref",
                "character_continuity_version_ref",
            ),
        )
        self.snapshots = _SqliteJsonMapping(
            self,
            "v5_m6_baseline_snapshots",
            (*_SCOPE_COLUMNS, "m6_baseline_snapshot_ref"),
            conflict_on_integrity=True,
        )
        self.active_snapshots = _ActiveSnapshotMapping(self)

    def _connect(self) -> sqlite3.Connection:
        connection = None
        try:
            connection = sqlite3.connect(
                self.database_path, timeout=10, isolation_level=None
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                connection.close()
                connection = None
                raise SeriesIntelligenceError(
                    "M6 durable foreign-key enforcement unavailable"
                )
            return connection
        except sqlite3.DatabaseError:
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.DatabaseError:
                    pass
            raise _read_error() from None

    @contextmanager
    def _read_session(self):
        shared = (
            self._state.read_connection_or_none()
            if hasattr(self._state, "read_connection_or_none")
            else self._state.connection_or_none()
        )
        if shared is not None:
            yield shared
            return
        connection = self._connect()
        try:
            yield connection
        finally:
            try:
                connection.close()
            except sqlite3.DatabaseError:
                raise _read_error() from None

    def _write_connection(self) -> sqlite3.Connection:
        connection = self._state.connection_or_none()
        if connection is None:
            raise SeriesIntelligenceError("valid lifecycle lease is required for M6 writes")
        return connection

    def _validate_schema(self) -> None:
        try:
            with self._read_session() as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                if (
                    set(self._TABLES) - tables
                    or "v5_series_intelligence_schema" not in tables
                ):
                    raise SeriesIntelligenceError(
                        "M6 durable schema initialization required"
                    )
                marker = connection.execute(
                    "SELECT schema_version FROM v5_series_intelligence_schema "
                    "WHERE component = 'series_intelligence'"
                ).fetchone()
                if marker is None or int(marker[0]) != 1:
                    raise SeriesIntelligenceError(
                        "unsupported M6 durable schema version"
                    )
        except sqlite3.DatabaseError:
            raise _read_error() from None
        except (TypeError, ValueError):
            raise SeriesIntelligenceError(
                "unsupported M6 durable schema version"
            ) from None

    def _columns(self, connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
        columns = self._column_cache.get(table)
        if columns is None:
            try:
                columns = tuple(
                    row[1]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                )
            except sqlite3.DatabaseError:
                raise _read_error() from None
            if not columns:
                raise SeriesIntelligenceError("M6 durable schema is unavailable")
            self._column_cache[table] = columns
        return columns

    @staticmethod
    def _record_columns(columns: tuple[str, ...], record: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for column in columns:
            if column == "record_json":
                continue
            if column == "content_json":
                result[column] = _json_dump(record.get("content"))
                continue
            field = _camel(column)
            result[column] = record.get(field)
            if result[column] is None and column in _SCOPE_COLUMNS:
                scope = record.get("scope")
                if isinstance(scope, dict):
                    result[column] = scope.get(field)
        return result

    def _validated_record(
        self, connection: sqlite3.Connection, row: sqlite3.Row, table: str
    ) -> dict[str, Any]:
        """Fail closed on one fact's projection, digest and accepted lineage."""
        try:
            return validate_durable_record(connection, table, row)
        except (
            DurableRecordIntegrityError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            RecursionError,
            sqlite3.DatabaseError,
        ):
            raise SeriesIntelligenceError(
                "M6 durable record failed integrity validation"
            ) from None

    @staticmethod
    def _columns_from_row(row: sqlite3.Row) -> tuple[str, ...]:
        return tuple(row.keys())

    @staticmethod
    def _scope(scope_key: tuple[str, ...]) -> tuple[str, str, str, str, str]:
        values = tuple(scope_key)
        if len(values) != 5 or any(
            not isinstance(item, str)
            or not item
            or item != unicodedata.normalize("NFC", item)
            for item in values
        ):
            raise InvalidReferenceError("complete M6 Scope is required")
        return values  # type: ignore[return-value]

    def replay(
        self,
        scope_key: tuple[str, ...],
        key: str,
        payload_digest: str,
        *,
        operation_type: str,
    ) -> Any | None:
        scope = self._scope(scope_key)
        try:
            with self._read_session() as connection:
                row = connection.execute(
                    "SELECT * "
                    "FROM v5_m6_operations WHERE "
                    + " AND ".join(f"{column} = ?" for column in _SCOPE_COLUMNS)
                    + " AND idempotency_key = ?",
                    (*scope, str(key)),
                ).fetchone()
                if row is None:
                    return None
                if (
                    row["operation_type"] != operation_type
                    or row["input_digest"] != payload_digest
                ):
                    raise IdempotencyConflictError()
                try:
                    return validate_durable_operation(connection, row)
                except DurableRecordIntegrityError:
                    raise SeriesIntelligenceError(
                        "M6 durable operation result failed integrity validation"
                    ) from None
        except sqlite3.DatabaseError:
            raise _read_error() from None

    def record_operation(
        self,
        scope_key: tuple[str, ...],
        key: str,
        payload_digest: str,
        result: Any,
        *,
        operation_ref: str,
        operation_type: str,
    ) -> Any:
        scope = self._scope(scope_key)
        connection = self._write_connection()
        columns = self._columns(connection, "v5_m6_operations")
        values: dict[str, Any] = dict(zip(_SCOPE_COLUMNS, scope))
        values.update(
            {
                "idempotency_key": str(key),
                "operation_ref": str(operation_ref),
                "operation_type": str(operation_type),
                "input_digest": str(payload_digest),
                "result_json": _json_dump(result),
                "created_at": _utc_now(),
            }
        )
        selected = tuple(column for column in columns if column in values)
        try:
            connection.execute(
                f"INSERT INTO v5_m6_operations ({','.join(selected)}) "
                f"VALUES ({','.join('?' for _ in selected)})",
                tuple(values[column] for column in selected),
            )
            self._fault("after-operation-write")
        except sqlite3.IntegrityError:
            replay = self.replay(
                scope,
                str(key),
                str(payload_digest),
                operation_type=str(operation_type),
            )
            if replay is not None:
                return replay
            raise IdempotencyConflictError() from None
        except sqlite3.DatabaseError as exc:
            raise _database_error(exc) from None
        return deepcopy(result)

    def append_event(self, event: dict[str, Any]) -> None:
        connection = self._write_connection()
        scope = (
            event.get("businessDomain"),
            event.get("tenantId"),
            event.get("workspaceId"),
            event.get("projectRef"),
            event.get("seriesRef"),
        )
        self._scope(scope)
        columns = self._columns(connection, "v5_m6_outbox")
        values = {
            **dict(zip(_SCOPE_COLUMNS, scope)),
            "event_id": event.get("eventId"),
            "event_type": event.get("eventType"),
            "event_version": event.get("eventVersion"),
            "aggregate_type": event.get("aggregateType"),
            "aggregate_ref": event.get("aggregateRef"),
            "operation_ref": event.get("operationRef"),
            "correlation_id": event.get("correlationId"),
            "causation_id": event.get("causationId"),
            "occurred_at": event.get("occurredAt"),
            "event_json": _json_dump(event),
        }
        selected = tuple(
            column for column in columns if column != "position" and column in values
        )
        try:
            connection.execute(
                f"INSERT INTO v5_m6_outbox ({','.join(selected)}) "
                f"VALUES ({','.join('?' for _ in selected)})",
                tuple(values[column] for column in selected),
            )
            self._fault("after-outbox-write")
        except sqlite3.DatabaseError as exc:
            raise _database_error(exc) from None

    def list_outbox(self, scope_key: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        try:
            with self._read_session() as connection:
                where = ""
                parameters: tuple[str, ...] = ()
                if scope_key is not None:
                    scope = self._scope(scope_key)
                    where = " WHERE " + " AND ".join(
                        f"{column} = ?" for column in _SCOPE_COLUMNS
                    )
                    parameters = scope
                rows = connection.execute(
                    "SELECT * FROM v5_m6_outbox" + where + " ORDER BY position",
                    parameters,
                ).fetchall()
                try:
                    return [
                        validate_durable_event(connection, row) for row in rows
                    ]
                except DurableRecordIntegrityError:
                    raise SeriesIntelligenceError(
                        "M6 durable outbox failed integrity validation"
                    ) from None
        except sqlite3.DatabaseError:
            raise _read_error() from None

    def _list_scoped_records(
        self, table: str, scope_key: tuple[str, ...], order_by: str
    ) -> list[dict[str, Any]]:
        scope = self._scope(scope_key)
        try:
            with self._read_session() as connection:
                rows = connection.execute(
                    f"SELECT * FROM {table} WHERE "
                    + " AND ".join(f"{column} = ?" for column in _SCOPE_COLUMNS)
                    + f" ORDER BY {order_by}",
                    scope,
                ).fetchall()
                return [
                    self._validated_record(connection, row, table)
                    for row in rows
                ]
        except SeriesIntelligenceError:
            raise
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise SeriesIntelligenceError("M6 durable persistence failed") from None

    def list_bible_versions(self, scope_key: tuple[str, ...]) -> list[dict[str, Any]]:
        return self._list_scoped_records(
            "v5_m6_series_bible_versions", scope_key, "version_number"
        )

    def list_character_versions(self, scope_key: tuple[str, ...]) -> list[dict[str, Any]]:
        return self._list_scoped_records(
            "v5_m6_character_continuity_versions", scope_key, "version_number"
        )

    def list_snapshots(self, scope_key: tuple[str, ...]) -> list[dict[str, Any]]:
        return self._list_scoped_records(
            "v5_m6_baseline_snapshots", scope_key, "activation_revision"
        )

    def lifecycle_has_series_dependency(self, workspace_ref: str, series_ref: str) -> bool:
        predicates = "workspace_ref = ? AND series_ref = ?"
        try:
            with self._read_session() as connection:
                return any(
                    connection.execute(
                        f"SELECT 1 FROM {table} WHERE {predicates} LIMIT 1",
                        (str(workspace_ref), str(series_ref)),
                    ).fetchone()
                    is not None
                    for table in self._TABLES[:5]
                )
        except sqlite3.DatabaseError:
            raise _read_error() from None

    def diagnostic(self) -> dict[str, int]:
        queries = {
            "bibleCount": "v5_m6_series_bibles",
            "bibleVersionCount": "v5_m6_series_bible_versions",
            "characterCount": "v5_m6_character_continuities",
            "characterVersionCount": "v5_m6_character_continuity_versions",
            "snapshotCount": "v5_m6_baseline_snapshots",
            "operationCount": "v5_m6_operations",
            "outboxCount": "v5_m6_outbox",
        }
        try:
            with self._read_session() as connection:
                result = {
                    name: int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                    )
                    for name, table in queries.items()
                }
                result["activeSnapshotCount"] = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM v5_m6_baseline_snapshots "
                        "WHERE status = 'ACTIVE'"
                    ).fetchone()[0]
                )
        except sqlite3.DatabaseError:
            raise _read_error() from None
        return result
