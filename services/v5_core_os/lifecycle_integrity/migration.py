"""Atomic fresh/upgrade migration for temporary or explicitly authorized SQLite files."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable

from .sqlite_schema import (
    DROP_ORDER,
    MARKERS,
    SQLITE_LIFECYCLE_SCHEMA_VERSION,
    TABLE_COLUMNS,
    TABLE_ORDER,
    index_statements,
    table_statements,
)


class LifecycleMigrationError(RuntimeError):
    code = "lifecycle_migration_error"


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        connection.close()
        raise LifecycleMigrationError("foreign key enforcement unavailable")
    return connection


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _marker_versions(connection: sqlite3.Connection, tables: set[str]) -> dict[str, int]:
    result = {}
    for table, component in MARKERS.items():
        if table in tables:
            row = connection.execute(
                f"SELECT schema_version FROM {table} WHERE component = ?", (component,)
            ).fetchone()
            if row is not None:
                result[table] = int(row[0])
    return result


def _validate_no_orphans(connection: sqlite3.Connection, tables: set[str]) -> None:
    checks = (
        ("v5_project_series_relationships", "v5_projects", "r.workspace_ref=p.workspace_ref AND r.project_ref=p.project_ref"),
        ("v5_project_series_relationships", "v5_series", "r.workspace_ref=p.workspace_ref AND r.series_ref=p.series_ref"),
        ("v5_episode_projects", "v5_series", "r.workspace_ref=p.workspace_ref AND r.series_ref=p.series_ref"),
        ("v5_scripts", "v5_episode_projects", "r.workspace_ref=p.workspace_ref AND r.series_ref=p.series_ref AND r.episode_ref=p.episode_ref"),
        ("v5_script_versions", "v5_scripts", "r.workspace_ref=p.workspace_ref AND r.script_ref=p.script_ref AND r.series_ref=p.series_ref AND r.episode_ref=p.episode_ref"),
        ("v5_script_versions", "v5_episode_projects", "r.workspace_ref=p.workspace_ref AND r.series_ref=p.series_ref AND r.episode_ref=p.episode_ref"),
        ("v5_series_plans", "v5_project_series_relationships", "r.workspace_ref=p.workspace_ref AND r.project_ref=p.project_ref AND r.series_ref=p.series_ref"),
    )
    for child, parent, predicate in checks:
        if child in tables and parent in tables:
            row = connection.execute(
                f"SELECT 1 FROM {child} r LEFT JOIN {parent} p ON {predicate} WHERE p.rowid IS NULL LIMIT 1"
            ).fetchone()
            if row is not None:
                raise LifecycleMigrationError(f"orphan data blocks migration: {child}")
        elif child in tables:
            count = connection.execute(f"SELECT COUNT(*) FROM {child}").fetchone()[0]
            if count:
                raise LifecycleMigrationError(f"missing parent table blocks migration: {parent}")


def validate_lifecycle_database(database_path: Path | str) -> None:
    path = Path(database_path).resolve()
    if not path.exists():
        raise LifecycleMigrationError("database initialization required")
    connection = _connect(path)
    try:
        tables = _tables(connection)
        versions = _marker_versions(connection, tables)
        if set(TABLE_ORDER) - tables or set(MARKERS) - tables:
            raise LifecycleMigrationError("partial lifecycle schema")
        if set(versions.values()) != {SQLITE_LIFECYCLE_SCHEMA_VERSION}:
            raise LifecycleMigrationError("lifecycle migration required")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LifecycleMigrationError("foreign key validation failed")
    finally:
        connection.close()


def migrate_lifecycle_database(
    database_path: Path | str,
    *,
    allow_upgrade: bool,
    fault: Callable[[str], None] | None = None,
) -> str:
    path = Path(database_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists() and path.stat().st_size > 0
    connection = _connect(path)
    fault = fault or (lambda _point: None)
    try:
        tables = _tables(connection)
        versions = _marker_versions(connection, tables)
        if tables and set(TABLE_ORDER).issubset(tables) and set(MARKERS).issubset(tables) and set(versions.values()) == {SQLITE_LIFECYCLE_SCHEMA_VERSION}:
            validate_lifecycle_database(path)
            return "no-op"
        is_empty = not tables
        if not is_empty and (not versions or set(versions.values()) != {1}):
            raise LifecycleMigrationError("unsupported or partial lifecycle schema")
        if not is_empty and not allow_upgrade:
            raise LifecycleMigrationError("lifecycle migration required")
        _validate_no_orphans(connection, tables)
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in TABLE_ORDER if table in tables
        }
        connection.execute("BEGIN IMMEDIATE")
        try:
            if is_empty:
                for statement in table_statements():
                    connection.execute(statement)
                for marker, component in MARKERS.items():
                    connection.execute(
                        f"CREATE TABLE {marker} (component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
                    )
                    connection.execute(
                        f"INSERT INTO {marker} VALUES (?, ?)",
                        (component, SQLITE_LIFECYCLE_SCHEMA_VERSION),
                    )
                result = "fresh"
            else:
                shadow = {table: f"__lifecycle_v2_{table}" for table in TABLE_ORDER}
                for statement in table_statements(shadow):
                    connection.execute(statement)
                for table in TABLE_ORDER:
                    if table in tables:
                        columns = TABLE_COLUMNS[table]
                        connection.execute(
                            f"INSERT INTO {shadow[table]} ({columns}) SELECT {columns} FROM {table}"
                        )
                fault("after-copy")
                for table, count in before.items():
                    copied = connection.execute(
                        f"SELECT COUNT(*) FROM {shadow[table]}"
                    ).fetchone()[0]
                    if copied != count:
                        raise LifecycleMigrationError(f"row count changed for {table}")
                for table in DROP_ORDER:
                    if table in tables:
                        connection.execute(f"DROP TABLE {table}")
                for table in TABLE_ORDER:
                    connection.execute(f"ALTER TABLE {shadow[table]} RENAME TO {table}")
                for marker, component in MARKERS.items():
                    if marker not in tables:
                        connection.execute(
                            f"CREATE TABLE {marker} (component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
                        )
                fault("before-marker-update")
                for marker, component in MARKERS.items():
                    connection.execute(
                        f"INSERT INTO {marker}(component,schema_version) VALUES (?,?) ON CONFLICT(component) DO UPDATE SET schema_version=excluded.schema_version",
                        (component, SQLITE_LIFECYCLE_SCHEMA_VERSION),
                    )
                result = "upgrade"
            for statement in index_statements():
                connection.execute(statement)
            fault("before-verify")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise LifecycleMigrationError("foreign key validation failed")
            fault("before-commit")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    except BaseException:
        if not existed and path.exists() and path.stat().st_size == 0:
            path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    validate_lifecycle_database(path)
    check = _connect(path)
    try:
        if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise LifecycleMigrationError("integrity check failed")
    finally:
        check.close()
    return result
