"""Atomic additive SQLite component for immutable Script acceptance facts."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Callable

from .foundation import (
    ScriptAcceptanceRecord,
    ScriptStudioService,
    ScriptVersionRecord,
    _acceptance_mapping,
)


MARKER_TABLE = "v5_script_acceptance_schema"
MARKER_COMPONENT = "script_acceptance"
TABLE = "v5_script_acceptances"
SCHEMA_VERSION = 1
INDEX = "ix_script_acceptance_episode_parent"


class ScriptAcceptanceMigrationError(RuntimeError):
    code = "script_acceptance_migration_error"


def table_statement() -> str:
    return f"""CREATE TABLE {TABLE} (
        workspace_ref TEXT NOT NULL,
        script_ref TEXT NOT NULL,
        script_version_ref TEXT NOT NULL,
        acceptance_ref TEXT NOT NULL,
        schema_version TEXT NOT NULL,
        series_ref TEXT NOT NULL,
        episode_ref TEXT NOT NULL,
        approval_ref TEXT NOT NULL,
        authority_decision_ref TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        content_json TEXT NOT NULL,
        payload_digest TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(workspace_ref, script_ref, script_version_ref),
        UNIQUE(workspace_ref, acceptance_ref),
        UNIQUE(workspace_ref, approval_ref),
        UNIQUE(workspace_ref, authority_decision_ref),
        UNIQUE(workspace_ref, idempotency_key),
        FOREIGN KEY(workspace_ref, script_ref, script_version_ref)
            REFERENCES v5_script_versions(
                workspace_ref, script_ref, script_version_ref
            ) ON DELETE RESTRICT
    )"""


def index_statement() -> str:
    return (
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE}"
        "(workspace_ref, series_ref, episode_ref)"
    )


def marker_statement() -> str:
    return (
        f"CREATE TABLE {MARKER_TABLE} ("
        "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )


def _normalized_sql(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def _stored_sql(
    connection: sqlite3.Connection, kind: str, name: str
) -> str | None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type=? AND name=?", (kind, name)
    ).fetchone()
    return None if row is None else row[0]


def _present(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN (?,?)",
            (TABLE, MARKER_TABLE),
        )
    }


def _record(row: sqlite3.Row) -> ScriptAcceptanceRecord:
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


def _version_record(row: sqlite3.Row) -> ScriptVersionRecord:
    return ScriptVersionRecord(
        row["schema_version"],
        row["workspace_ref"],
        row["series_ref"],
        row["episode_ref"],
        row["script_ref"],
        row["script_version_ref"],
        row["source_plan_ref"],
        row["source_plan_schema_version"],
        row["source_plan_version"],
        row["version_number"],
        row["content_json"],
        row["change_kind"],
        row["parent_script_version_ref"],
        row["created_at"],
    )


def _validate_script_acceptance_connection(
    connection: sqlite3.Connection,
) -> None:
    if _present(connection) != {TABLE, MARKER_TABLE}:
        raise ScriptAcceptanceMigrationError(
            "partial or missing Script acceptance schema"
        )
    if _normalized_sql(_stored_sql(connection, "table", TABLE)) != _normalized_sql(
        table_statement()
    ):
        raise ScriptAcceptanceMigrationError(
            "unsupported Script acceptance table definition"
        )
    columns = tuple(
        row[1] for row in connection.execute(f"PRAGMA table_info({MARKER_TABLE})")
    )
    rows = connection.execute(
        f"SELECT component,schema_version FROM {MARKER_TABLE} ORDER BY component"
    ).fetchall()
    if (
        columns != ("component", "schema_version")
        or _normalized_sql(
            _stored_sql(connection, "table", MARKER_TABLE)
        )
        != _normalized_sql(marker_statement())
        or len(rows) != 1
        or tuple(rows[0]) != (MARKER_COMPONENT, SCHEMA_VERSION)
    ):
        raise ScriptAcceptanceMigrationError(
            "unsupported Script acceptance marker"
        )
    expected_index = _normalized_sql(index_statement()).replace(
        "ifnotexists", ""
    )
    actual_index = _normalized_sql(
        _stored_sql(connection, "index", INDEX)
    ).replace("ifnotexists", "")
    if actual_index != expected_index:
        raise ScriptAcceptanceMigrationError(
            "unsupported Script acceptance index"
        )
    inconsistent_parent = connection.execute(
        f"SELECT 1 FROM {TABLE} a LEFT JOIN v5_script_versions v ON "
        "a.workspace_ref=v.workspace_ref AND a.script_ref=v.script_ref "
        "AND a.script_version_ref=v.script_version_ref "
        "LEFT JOIN v5_scripts s ON a.workspace_ref=s.workspace_ref "
        "AND a.script_ref=s.script_ref "
        "WHERE v.rowid IS NULL OR s.rowid IS NULL "
        "OR a.series_ref<>v.series_ref OR a.episode_ref<>v.episode_ref "
        "OR a.series_ref<>s.series_ref OR a.episode_ref<>s.episode_ref "
        "OR s.confirmed_script_version_ref IS NULL "
        "OR s.confirmed_script_version_ref<>a.script_version_ref LIMIT 1"
    ).fetchone()
    if inconsistent_parent is not None or connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchone() is not None:
        raise ScriptAcceptanceMigrationError(
            "Script acceptance foreign-key validation failed"
        )
    try:
        for row in connection.execute(f"SELECT * FROM {TABLE} ORDER BY rowid"):
            acceptance = _acceptance_mapping(_record(row))
            parent_row = connection.execute(
                "SELECT * FROM v5_script_versions WHERE workspace_ref=? "
                "AND script_ref=? AND script_version_ref=?",
                (
                    row["workspace_ref"],
                    row["script_ref"],
                    row["script_version_ref"],
                ),
            ).fetchone()
            if parent_row is None:
                raise ScriptAcceptanceMigrationError(
                    "Script acceptance parent is unavailable"
                )
            parent = ScriptStudioService._version_mapping(
                _version_record(parent_row)
            )
            provenance = parent.get("importProvenance")
            digest_fields = (
                "uploadedSourceByteDigest",
                "normalizedSourceDocumentDigest",
                "reviewedDocumentDigest",
                "canonicalScriptContentDigest",
                "importProvenanceDigest",
            )
            if (
                parent.get("changeKind") != "reviewed-import"
                or parent.get("versionNumber") != 1
                or parent.get("parentScriptVersionRef") is not None
                or not isinstance(provenance, dict)
                or any(
                    acceptance[field] != provenance.get(field)
                    for field in digest_fields
                )
            ):
                raise ScriptAcceptanceMigrationError(
                    "Script acceptance does not match reviewed-import parent"
                )
    except Exception as exc:
        raise ScriptAcceptanceMigrationError(
            "Script acceptance durable row validation failed"
        ) from exc


def _migrate_script_acceptance_connection(
    connection: sqlite3.Connection,
    *,
    fault: Callable[[str], None],
) -> str:
    present = _present(connection)
    if present == {TABLE, MARKER_TABLE}:
        _validate_script_acceptance_connection(connection)
        return "no-op"
    if present:
        raise ScriptAcceptanceMigrationError(
            "partial Script acceptance schema"
        )
    parent = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='v5_script_versions'"
    ).fetchone()
    if parent is None:
        raise ScriptAcceptanceMigrationError(
            "Script Studio lifecycle parent is unavailable"
        )
    connection.execute(table_statement())
    connection.execute(index_statement())
    fault("after-copy")
    connection.execute(marker_statement())
    fault("before-marker-update")
    connection.execute(
        f"INSERT INTO {MARKER_TABLE} VALUES (?,?)",
        (MARKER_COMPONENT, SCHEMA_VERSION),
    )
    fault("before-verify")
    _validate_script_acceptance_connection(connection)
    return "upgrade"


def validate_script_acceptance_database(database_path: Path | str) -> None:
    path = Path(database_path).resolve()
    if not path.exists():
        raise ScriptAcceptanceMigrationError(
            "database initialization required"
        )
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        _validate_script_acceptance_connection(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ScriptAcceptanceMigrationError("integrity check failed")
    finally:
        connection.close()


__all__ = [
    "INDEX",
    "MARKER_TABLE",
    "TABLE",
    "ScriptAcceptanceMigrationError",
    "validate_script_acceptance_database",
]
