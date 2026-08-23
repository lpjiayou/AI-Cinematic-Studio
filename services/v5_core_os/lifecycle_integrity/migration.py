"""Atomic fresh/upgrade migration for temporary or explicitly authorized SQLite files."""

from __future__ import annotations

import re
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


_V1_COMPONENT_TABLES = {
    "v5_series_episode_schema": (
        "v5_series",
        "v5_confirmed_creative_plans",
        "v5_episode_projects",
        "v5_episode_plan_bindings",
    ),
    "v5_project_schema": (
        "v5_projects",
        "v5_project_series_relationships",
    ),
    "v5_script_studio_schema": (
        "v5_scripts",
        "v5_script_versions",
    ),
    "v5_series_planning_schema": (
        "v5_series_plans",
        "v5_series_plan_versions",
    ),
}


def _normalized_sql(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def _v1_table_sql() -> dict[str, str]:
    """Return canonical table definitions emitted by the accepted V1 adapters."""

    result = dict(zip(TABLE_ORDER, table_statements()))
    result.update(
        {
            "v5_project_series_relationships": """CREATE TABLE v5_project_series_relationships (
                workspace_ref TEXT NOT NULL, project_ref TEXT NOT NULL,
                series_ref TEXT NOT NULL, schema_version TEXT NOT NULL,
                linked_at TEXT NOT NULL, version INTEGER NOT NULL,
                PRIMARY KEY(workspace_ref, project_ref, series_ref),
                UNIQUE(workspace_ref, series_ref),
                FOREIGN KEY(workspace_ref, project_ref)
                    REFERENCES v5_projects(workspace_ref, project_ref) ON DELETE RESTRICT
            )""",
            "v5_scripts": """CREATE TABLE v5_scripts (
                workspace_ref TEXT NOT NULL, series_ref TEXT NOT NULL,
                episode_ref TEXT NOT NULL, script_ref TEXT NOT NULL,
                schema_version TEXT NOT NULL, title TEXT NOT NULL,
                current_script_version_ref TEXT NOT NULL,
                confirmed_script_version_ref TEXT, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, version INTEGER NOT NULL,
                PRIMARY KEY(workspace_ref, script_ref),
                UNIQUE(workspace_ref, series_ref, episode_ref)
            )""",
            "v5_script_versions": """CREATE TABLE v5_script_versions (
                workspace_ref TEXT NOT NULL, script_ref TEXT NOT NULL,
                script_version_ref TEXT NOT NULL, schema_version TEXT NOT NULL,
                series_ref TEXT NOT NULL, episode_ref TEXT NOT NULL,
                source_plan_ref TEXT NOT NULL,
                source_plan_schema_version TEXT NOT NULL,
                source_plan_version INTEGER NOT NULL,
                version_number INTEGER NOT NULL, content_json TEXT NOT NULL,
                change_kind TEXT NOT NULL, parent_script_version_ref TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(workspace_ref, script_ref, script_version_ref),
                UNIQUE(workspace_ref, script_ref, version_number),
                FOREIGN KEY(workspace_ref, script_ref)
                    REFERENCES v5_scripts(workspace_ref, script_ref) ON DELETE RESTRICT
            )""",
            "v5_series_plans": """CREATE TABLE v5_series_plans (
                workspace_ref TEXT NOT NULL, series_plan_ref TEXT NOT NULL,
                schema_version TEXT NOT NULL, content_profile_ref TEXT NOT NULL,
                project_ref TEXT NOT NULL, series_ref TEXT NOT NULL,
                current_version_ref TEXT NOT NULL, confirmed_version_ref TEXT,
                status TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, version INTEGER NOT NULL,
                PRIMARY KEY(workspace_ref, series_plan_ref),
                UNIQUE(workspace_ref, project_ref, series_ref)
            )""",
        }
    )
    return result


def _validate_v1_components(
    connection: sqlite3.Connection, tables: set[str]
) -> None:
    """Accept any complete V1 component combination and reject partial repair."""

    selected: set[str] = set()
    expected_tables: set[str] = set()
    for marker, owned in _V1_COMPONENT_TABLES.items():
        present_owned = set(owned) & tables
        marker_present = marker in tables
        if marker_present != bool(present_owned) or (
            marker_present and present_owned != set(owned)
        ):
            raise LifecycleMigrationError("partial Lifecycle V1 component")
        if not marker_present:
            continue
        selected.add(marker)
        expected_tables.update(owned)
        columns = connection.execute(f"PRAGMA table_info({marker})").fetchall()
        if tuple(row[1] for row in columns) != ("component", "schema_version"):
            raise LifecycleMigrationError("unsupported Lifecycle V1 marker")
        component_column, version_column = columns
        if (
            str(component_column[2]).upper() != "TEXT"
            or int(component_column[5]) != 1
            or str(version_column[2]).upper() != "INTEGER"
            or int(version_column[3]) != 1
            or int(version_column[5]) != 0
        ):
            raise LifecycleMigrationError("unsupported Lifecycle V1 marker")
        rows = connection.execute(
            f"SELECT component,schema_version FROM {marker} ORDER BY component"
        ).fetchall()
        if len(rows) != 1 or tuple(rows[0]) != (MARKERS[marker], 1):
            raise LifecycleMigrationError("unsupported Lifecycle V1 marker")

    if not selected or tables != selected | expected_tables:
        raise LifecycleMigrationError("unsupported Lifecycle V1 schema objects")
    forbidden = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1"
    ).fetchone()
    explicit_index = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND sql IS NOT NULL "
        "AND name NOT LIKE 'sqlite_%' LIMIT 1"
    ).fetchone()
    if forbidden is not None or explicit_index is not None:
        raise LifecycleMigrationError("unsupported Lifecycle V1 schema objects")
    canonical = _v1_table_sql()
    for table in expected_tables:
        stored = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if stored is None or _normalized_sql(stored[0]) != _normalized_sql(
            canonical[table]
        ):
            raise LifecycleMigrationError("unsupported Lifecycle V1 table definition")


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
        if set(versions) != set(MARKERS) or any(
            versions[table] != SQLITE_LIFECYCLE_SCHEMA_VERSION for table in MARKERS
        ):
            raise LifecycleMigrationError("lifecycle migration required")
        for table, component in MARKERS.items():
            rows = connection.execute(
                f"SELECT component, schema_version FROM {table} ORDER BY component"
            ).fetchall()
            if len(rows) != 1 or tuple(rows[0]) != (
                component,
                SQLITE_LIFECYCLE_SCHEMA_VERSION,
            ):
                raise LifecycleMigrationError("unsupported lifecycle marker")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LifecycleMigrationError("foreign key validation failed")
    finally:
        connection.close()
    from services.v5_core_os.series_intelligence.migration import (
        validate_series_intelligence_database,
    )

    validate_series_intelligence_database(path)


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
        if (
            tables
            and set(TABLE_ORDER).issubset(tables)
            and set(MARKERS).issubset(tables)
            and set(versions) == set(MARKERS)
            and all(
                versions[table] == SQLITE_LIFECYCLE_SCHEMA_VERSION
                for table in MARKERS
            )
        ):
            from services.v5_core_os.series_intelligence.migration import (
                _migrate_series_intelligence_connection,
            )
            from services.v5_core_os.series_intelligence.sqlite_schema import (
                MARKER_TABLE as M6_MARKER_TABLE,
                M6_TABLES,
            )

            # An accepted Lifecycle V2 database without M6 is an upgrade path,
            # not a validated no-op.  Honour the caller's explicit upgrade gate
            # before opening a write transaction or changing any schema object.
            required_m6_objects = set(M6_TABLES) | {M6_MARKER_TABLE}
            if not required_m6_objects.issubset(tables) and not allow_upgrade:
                raise LifecycleMigrationError("M6 lifecycle migration required")

            connection.execute("BEGIN IMMEDIATE")
            try:
                m6_result = _migrate_series_intelligence_connection(
                    connection, fault=fault
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            validate_lifecycle_database(path)
            return "no-op" if m6_result == "no-op" else "upgrade"
        is_empty = not tables
        if not is_empty and (not versions or set(versions.values()) != {1}):
            raise LifecycleMigrationError("unsupported or partial lifecycle schema")
        if not is_empty and not allow_upgrade:
            raise LifecycleMigrationError("lifecycle migration required")
        if not is_empty:
            _validate_v1_components(connection, tables)
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
            from services.v5_core_os.series_intelligence.migration import (
                _migrate_series_intelligence_connection,
            )

            _migrate_series_intelligence_connection(connection, fault=fault)
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
