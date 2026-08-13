"""Atomic additive migration for the bounded M6 SQLite component."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Callable

from services.v5_core_os.lifecycle_integrity.sqlite_schema import (
    MARKERS as LIFECYCLE_MARKERS,
    SQLITE_LIFECYCLE_SCHEMA_VERSION,
    TABLE_ORDER as LIFECYCLE_TABLES,
    index_statements as lifecycle_index_statements,
    table_statements as lifecycle_table_statements,
)

from .sqlite_schema import (
    MARKER_COMPONENT,
    MARKER_TABLE,
    M6_TABLE_COLUMNS,
    M6_TABLES,
    SQLITE_SERIES_INTELLIGENCE_SCHEMA_VERSION,
    index_statements,
    table_statements,
)
from .record_integrity import validate_durable_rows


class SeriesIntelligenceMigrationError(RuntimeError):
    code = "series_intelligence_migration_error"


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise SeriesIntelligenceMigrationError("foreign key enforcement unavailable")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _normalized_sql(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def _stored_sql(connection: sqlite3.Connection, kind: str, name: str) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = ? AND name = ?", (kind, name)
    ).fetchone()
    return None if row is None else row[0]


def _index_name(statement: str) -> str:
    tokens = statement.replace("IF NOT EXISTS ", "").split()
    return tokens[tokens.index("INDEX") + 1]


def _index_sql(value: str | None) -> str:
    return _normalized_sql(value).replace("ifnotexists", "")


def _exact_marker(
    connection: sqlite3.Connection,
    table: str,
    component: str,
    version: int,
) -> bool:
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    if tuple(row[1] for row in columns) != ("component", "schema_version"):
        return False
    # SQLite reports an explicitly declared PRIMARY KEY as non-nullable through
    # ``pk`` even though older versions leave the ``notnull`` flag at zero.
    component_column, version_column = columns
    if (
        str(component_column[2]).upper() != "TEXT"
        or int(component_column[5]) != 1
        or str(version_column[2]).upper() != "INTEGER"
        or int(version_column[3]) != 1
        or int(version_column[5]) != 0
    ):
        return False
    rows = connection.execute(
        f"SELECT component, schema_version FROM {table} ORDER BY component"
    ).fetchall()
    return len(rows) == 1 and tuple(rows[0]) == (component, version)


def _validate_schema_allowlist(
    connection: sqlite3.Connection, *, allow_m6: bool
) -> None:
    expected_tables = set(LIFECYCLE_TABLES) | set(LIFECYCLE_MARKERS)
    expected_indexes = {_index_name(item) for item in lifecycle_index_statements()}
    if allow_m6:
        expected_tables |= set(M6_TABLES) | {MARKER_TABLE}
        expected_indexes |= {_index_name(item) for item in index_statements()}
    if _tables(connection) != expected_tables:
        raise SeriesIntelligenceMigrationError("undeclared SQLite table")
    forbidden = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1"
    ).fetchone()
    if forbidden is not None:
        raise SeriesIntelligenceMigrationError("undeclared SQLite schema object")
    explicit_indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
        )
    }
    if explicit_indexes != expected_indexes:
        raise SeriesIntelligenceMigrationError("undeclared SQLite index")


def _validate_lifecycle_v2_connection(
    connection: sqlite3.Connection, *, allow_m6: bool = False
) -> None:
    """Require the exact accepted Lifecycle V2 before adding M6."""

    tables = _tables(connection)
    required = set(LIFECYCLE_TABLES) | set(LIFECYCLE_MARKERS)
    if required - tables:
        raise SeriesIntelligenceMigrationError("accepted Lifecycle V2 schema is required")
    for name, expected in zip(LIFECYCLE_TABLES, lifecycle_table_statements()):
        if _normalized_sql(_stored_sql(connection, "table", name)) != _normalized_sql(expected):
            raise SeriesIntelligenceMigrationError("unsupported Lifecycle V2 table definition")
    for table, component in LIFECYCLE_MARKERS.items():
        if not _exact_marker(
            connection, table, component, SQLITE_LIFECYCLE_SCHEMA_VERSION
        ):
            raise SeriesIntelligenceMigrationError("unsupported Lifecycle V2 marker")
    for expected in lifecycle_index_statements():
        name = _index_name(expected)
        if _index_sql(_stored_sql(connection, "index", name)) != _index_sql(expected):
            raise SeriesIntelligenceMigrationError("unsupported Lifecycle V2 index")
    _validate_schema_allowlist(connection, allow_m6=allow_m6)
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise SeriesIntelligenceMigrationError("Lifecycle V2 foreign key validation failed")


def _is_complete(connection: sqlite3.Connection, tables: set[str]) -> bool:
    if MARKER_TABLE not in tables or set(M6_TABLES) - tables:
        return False
    try:
        return _exact_marker(
            connection,
            MARKER_TABLE,
            MARKER_COMPONENT,
            SQLITE_SERIES_INTELLIGENCE_SCHEMA_VERSION,
        )
    except sqlite3.DatabaseError:
        return False


def _validate_series_intelligence_connection(connection: sqlite3.Connection) -> None:
    tables = _tables(connection)
    if not _is_complete(connection, tables):
        raise SeriesIntelligenceMigrationError("partial or unsupported M6 schema")
    for name, expected in zip(M6_TABLES, table_statements()):
        columns = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({name})"))
        if columns != M6_TABLE_COLUMNS[name]:
            raise SeriesIntelligenceMigrationError("unsupported M6 table columns")
        if _normalized_sql(_stored_sql(connection, "table", name)) != _normalized_sql(expected):
            raise SeriesIntelligenceMigrationError("unsupported M6 table definition")
    for expected in index_statements():
        name = _index_name(expected)
        if _index_sql(_stored_sql(connection, "index", name)) != _index_sql(expected):
            raise SeriesIntelligenceMigrationError("unsupported M6 index")
    _validate_schema_allowlist(connection, allow_m6=True)
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise SeriesIntelligenceMigrationError("foreign key validation failed")
    validate_durable_rows(connection)


def validate_series_intelligence_database(database_path: Path | str) -> None:
    path = Path(database_path).resolve()
    if not path.exists():
        raise SeriesIntelligenceMigrationError("database initialization required")
    connection = _connect(path)
    try:
        _validate_lifecycle_v2_connection(connection, allow_m6=True)
        _validate_series_intelligence_connection(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SeriesIntelligenceMigrationError("integrity validation failed")
    finally:
        connection.close()


def _migrate_series_intelligence_connection(
    connection: sqlite3.Connection,
    *,
    fault: Callable[[str], None],
) -> str:
    """Add M6 using the caller's already-active atomic migration transaction."""

    tables = _tables(connection)
    present = set(M6_TABLES) & tables
    if _is_complete(connection, tables):
        _validate_lifecycle_v2_connection(connection, allow_m6=True)
        _validate_series_intelligence_connection(connection)
        return "no-op"
    if present or MARKER_TABLE in tables:
        raise SeriesIntelligenceMigrationError("partial M6 schema")
    _validate_lifecycle_v2_connection(connection, allow_m6=False)
    for statement in table_statements():
        connection.execute(statement)
    for statement in index_statements():
        connection.execute(statement)
    fault("after-copy")
    connection.execute(
        f"CREATE TABLE {MARKER_TABLE} ("
        "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )
    fault("before-marker-update")
    connection.execute(
        f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
        (MARKER_COMPONENT, SQLITE_SERIES_INTELLIGENCE_SCHEMA_VERSION),
    )
    fault("before-verify")
    _validate_series_intelligence_connection(connection)
    fault("before-commit")
    return "upgrade"


def migrate_series_intelligence_database(
    database_path: Path | str,
    *,
    fault: Callable[[str], None] | None = None,
) -> str:
    path = Path(database_path).resolve()
    if not path.exists():
        raise SeriesIntelligenceMigrationError("accepted Lifecycle V2 database is required")
    connection = _connect(path)
    try:
        tables = _tables(connection)
        if _is_complete(connection, tables):
            _validate_lifecycle_v2_connection(connection, allow_m6=True)
            _validate_series_intelligence_connection(connection)
            return "no-op"
        if set(M6_TABLES) & tables or MARKER_TABLE in tables:
            raise SeriesIntelligenceMigrationError("partial M6 schema")
        _validate_lifecycle_v2_connection(connection, allow_m6=False)
        connection.execute("BEGIN IMMEDIATE")
        try:
            result = _migrate_series_intelligence_connection(
                connection, fault=fault or (lambda _point: None)
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    finally:
        connection.close()
    validate_series_intelligence_database(path)
    return result
