"""Atomic additive migration for durable canonical registration receipts."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Callable

from services.v5_core_os.lifecycle_integrity.contracts import BackendKind

from .foundation import (
    CanonicalRegistrationRecord,
    canonical_target_digest,
    registration_record_mapping,
)
from .sqlite_schema import (
    INDEX,
    MARKER_COMPONENT,
    MARKER_TABLE,
    SCHEMA_VERSION,
    TABLE,
    index_statement,
    marker_statement,
    table_statement,
)


class CanonicalRegistrationMigrationError(RuntimeError):
    code = "canonical_registration_migration_error"


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


def _record(row: sqlite3.Row) -> CanonicalRegistrationRecord:
    return CanonicalRegistrationRecord(
        row["schema_version"],
        row["workspace_ref"],
        row["registration_ref"],
        row["canonical_target_ref"],
        row["canonical_target_digest"],
        row["registration_key"],
        row["idempotency_key"],
        row["package_digest"],
        row["request_json"],
        row["request_digest"],
        row["project_ref"],
        row["series_ref"],
        row["episode_ref"],
        row["creative_plan_ref"],
        row["script_ref"],
        row["script_version_ref"],
        row["acceptance_ref"],
        row["result_json"],
        row["result_digest"],
        row["receipt_digest"],
        row["registered_at"],
        bool(row["publication_allowed"]),
    )


def _main_storage_identity(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT file FROM pragma_database_list WHERE name='main'"
    ).fetchone()
    file_name = str(row[0] if row is not None else "").strip()
    if not file_name:
        raise CanonicalRegistrationMigrationError(
            "canonical registration storage identity is unavailable"
        )
    return f"sqlite:{Path(file_name).resolve()}"


def _parent_row(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[str, ...],
) -> sqlite3.Row:
    row = connection.execute(query, parameters).fetchone()
    if row is None:
        raise CanonicalRegistrationMigrationError(
            "canonical registration parent is unavailable"
        )
    return row


def _trimmed(value, *, limit: int | None = None) -> str:
    result = str(value or "").strip()
    return result if limit is None else result[:limit]


def _validate_parent_facts(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    registration: dict,
) -> None:
    request = json.loads(row["request_json"])
    workspace = row["workspace_ref"]
    series = _parent_row(
        connection,
        "SELECT * FROM v5_series WHERE workspace_ref=? AND series_ref=?",
        (workspace, row["series_ref"]),
    )
    if (
        series["schema_version"] != "v5.series.v1"
        or series["content_profile_ref"] != request["contentProfileRef"]
        or series["title"] != _trimmed(request["series"]["title"])
        or series["description"]
        != _trimmed(request["series"]["description"], limit=2000)
        or series["status"] != "active"
        or series["planned_episode_count"]
        != int(request["series"]["plannedEpisodeCount"])
        or series["version"] != 1
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration Series parent changed"
        )
    project = _parent_row(
        connection,
        "SELECT * FROM v5_projects WHERE workspace_ref=? AND project_ref=?",
        (workspace, row["project_ref"]),
    )
    expected_project = request["project"]
    if (
        project["schema_version"] != "v5.project.v1"
        or project["content_profile_ref"] != request["contentProfileRef"]
        or project["project_type"] != "series"
        or project["title"] != _trimmed(expected_project["title"])
        or project["description"]
        != _trimmed(expected_project["description"], limit=2000)
        or project["target_platform"]
        != _trimmed(expected_project["targetPlatform"], limit=200)
        or project["aspect_ratio"]
        != _trimmed(expected_project["aspectRatio"])
        or project["default_duration_sec"]
        != int(expected_project["defaultDurationSec"])
        or project["planned_episode_count"]
        != int(expected_project["plannedEpisodeCount"])
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration Project parent changed"
        )
    plan = _parent_row(
        connection,
        "SELECT * FROM v5_confirmed_creative_plans "
        "WHERE workspace_ref=? AND creative_plan_ref=?",
        (workspace, row["creative_plan_ref"]),
    )
    expected_plan = request["creativePlan"]
    if (
        plan["schema_version"] != "v5.confirmed-creative-plan.v1"
        or plan["source_plan_ref"] != expected_plan["sourcePlanRef"]
        or plan["source_plan_schema_version"]
        != expected_plan["sourcePlanSchemaVersion"]
        or plan["source_plan_version"]
        != int(expected_plan["sourcePlanVersion"])
        or json.loads(plan["brief_json"]) != expected_plan["brief"]
        or json.loads(plan["source_plan_json"])
        != expected_plan["sourcePlan"]
        or plan["confirmation_status"] != "confirmed"
        or plan["version"] != 1
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration creative-plan parent changed"
        )
    episode = _parent_row(
        connection,
        "SELECT * FROM v5_episode_projects WHERE workspace_ref=? "
        "AND series_ref=? AND episode_ref=?",
        (workspace, row["series_ref"], row["episode_ref"]),
    )
    expected_episode = request["episode"]
    if (
        episode["schema_version"] != "v5.episode.v1"
        or episode["episode_number"]
        != int(expected_episode["episodeNumber"])
        or episode["season_number"]
        != int(expected_episode["seasonNumber"])
        or episode["volume_number"]
        != int(expected_episode["volumeNumber"])
        or episode["title"] != _trimmed(expected_episode["title"])
        or episode["status"] != "draft"
        or episode["canonical_project_ref"] is not None
        or episode["creative_plan_ref"] != row["creative_plan_ref"]
        or episode["version"] != 1
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration Episode parent changed"
        )
    binding = _parent_row(
        connection,
        "SELECT * FROM v5_episode_plan_bindings WHERE workspace_ref=? "
        "AND series_ref=? AND episode_ref=?",
        (workspace, row["series_ref"], row["episode_ref"]),
    )
    if (
        binding["creative_plan_ref"] != row["creative_plan_ref"]
        or binding["source_plan_ref"] != expected_plan["sourcePlanRef"]
        or binding["source_plan_schema_version"]
        != expected_plan["sourcePlanSchemaVersion"]
        or binding["source_plan_version"]
        != int(expected_plan["sourcePlanVersion"])
        or json.loads(binding["brief_json"]) != expected_plan["brief"]
        or json.loads(binding["source_plan_json"])
        != expected_plan["sourcePlan"]
        or binding["version"] != 1
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration Episode plan binding changed"
        )
    version = _parent_row(
        connection,
        "SELECT * FROM v5_script_versions WHERE workspace_ref=? "
        "AND script_ref=? AND script_version_ref=?",
        (workspace, row["script_ref"], row["script_version_ref"]),
    )
    content = json.loads(version["content_json"])
    provenance = content.get("importProvenance", {})
    reviewed = request["reviewedScript"]
    if (
        version["series_ref"] != row["series_ref"]
        or version["episode_ref"] != row["episode_ref"]
        or version["source_plan_ref"] != expected_plan["sourcePlanRef"]
        or version["source_plan_schema_version"]
        != expected_plan["sourcePlanSchemaVersion"]
        or version["source_plan_version"]
        != int(expected_plan["sourcePlanVersion"])
        or version["version_number"] != 1
        or version["change_kind"] != "reviewed-import"
        or version["parent_script_version_ref"] is not None
        or provenance.get("uploadedSourceByteDigest")
        != reviewed["uploadedSourceByteDigest"]
        or provenance.get("normalizedSourceDocumentDigest")
        != reviewed["normalizedSourceDocumentDigest"]
        or provenance.get("reviewedDocumentDigest")
        != reviewed["reviewedDocumentDigest"]
        or provenance.get("importedByRef") != request["importedByRef"]
        or provenance.get("canonicalScriptContentDigest")
        != registration["canonicalScriptContentDigest"]
        or registration["reviewedDocumentDigest"]
        != reviewed["reviewedDocumentDigest"]
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration ScriptVersion parent changed"
        )
    acceptance = _parent_row(
        connection,
        "SELECT * FROM v5_script_acceptances WHERE workspace_ref=? "
        "AND script_ref=? AND script_version_ref=?",
        (workspace, row["script_ref"], row["script_version_ref"]),
    )
    acceptance_content = json.loads(acceptance["content_json"])
    if (
        acceptance["acceptance_ref"] != row["acceptance_ref"]
        or acceptance["series_ref"] != row["series_ref"]
        or acceptance["episode_ref"] != row["episode_ref"]
        or acceptance["approval_ref"]
        != request["acceptance"]["approvalRef"]
        or acceptance["idempotency_key"]
        != request["acceptance"]["idempotencyKey"]
        or acceptance["payload_digest"]
        != registration["scriptAcceptancePayloadDigest"]
        or acceptance_content.get("decision") != "ACCEPTED"
        or acceptance_content.get("publicationAllowed") is not False
        or acceptance_content.get("canonicalScriptContentDigest")
        != registration["canonicalScriptContentDigest"]
        or acceptance_content.get("reviewedDocumentDigest")
        != registration["reviewedDocumentDigest"]
    ):
        raise CanonicalRegistrationMigrationError(
            "canonical registration Script acceptance parent changed"
        )


def _validate_canonical_registration_connection(
    connection: sqlite3.Connection,
) -> None:
    if _present(connection) != {TABLE, MARKER_TABLE}:
        raise CanonicalRegistrationMigrationError(
            "partial or missing canonical registration schema"
        )
    if _normalized_sql(_stored_sql(connection, "table", TABLE)) != _normalized_sql(
        table_statement()
    ):
        raise CanonicalRegistrationMigrationError(
            "unsupported canonical registration table definition"
        )
    columns = tuple(
        row[1] for row in connection.execute(f"PRAGMA table_info({MARKER_TABLE})")
    )
    rows = connection.execute(
        f"SELECT component,schema_version FROM {MARKER_TABLE} ORDER BY component"
    ).fetchall()
    if (
        columns != ("component", "schema_version")
        or _normalized_sql(_stored_sql(connection, "table", MARKER_TABLE))
        != _normalized_sql(marker_statement())
        or len(rows) != 1
        or tuple(rows[0]) != (MARKER_COMPONENT, SCHEMA_VERSION)
    ):
        raise CanonicalRegistrationMigrationError(
            "unsupported canonical registration marker"
        )
    expected_index = _normalized_sql(index_statement()).replace(
        "ifnotexists", ""
    )
    actual_index = _normalized_sql(
        _stored_sql(connection, "index", INDEX)
    ).replace("ifnotexists", "")
    if actual_index != expected_index:
        raise CanonicalRegistrationMigrationError(
            "unsupported canonical registration index"
        )
    inconsistent_parent = connection.execute(
        f"SELECT 1 FROM {TABLE} r "
        "LEFT JOIN v5_project_series_relationships p ON "
        "r.workspace_ref=p.workspace_ref AND r.project_ref=p.project_ref "
        "AND r.series_ref=p.series_ref "
        "LEFT JOIN v5_episode_projects e ON "
        "r.workspace_ref=e.workspace_ref AND r.series_ref=e.series_ref "
        "AND r.episode_ref=e.episode_ref "
        "LEFT JOIN v5_confirmed_creative_plans c ON "
        "r.workspace_ref=c.workspace_ref "
        "AND r.creative_plan_ref=c.creative_plan_ref "
        "LEFT JOIN v5_script_acceptances a ON "
        "r.workspace_ref=a.workspace_ref AND r.script_ref=a.script_ref "
        "AND r.script_version_ref=a.script_version_ref "
        "WHERE p.rowid IS NULL OR e.rowid IS NULL OR c.rowid IS NULL "
        "OR a.rowid IS NULL OR e.creative_plan_ref<>r.creative_plan_ref "
        "OR a.acceptance_ref<>r.acceptance_ref "
        "OR a.series_ref<>r.series_ref OR a.episode_ref<>r.episode_ref "
        "LIMIT 1"
    ).fetchone()
    if inconsistent_parent is not None or connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchone() is not None:
        raise CanonicalRegistrationMigrationError(
            "canonical registration foreign-key validation failed"
        )
    try:
        target_bindings = {
            (row[0], row[1])
            for row in connection.execute(
                f"SELECT DISTINCT canonical_target_ref,"
                f"canonical_target_digest FROM {TABLE}"
            )
        }
        if len(target_bindings) > 1:
            raise CanonicalRegistrationMigrationError(
                "canonical registration target identity is ambiguous"
            )
        if target_bindings:
            target_ref, target_digest = next(iter(target_bindings))
            expected_target_digest = canonical_target_digest(
                backend_kind=BackendKind.SQLITE_LOCAL,
                canonical_target_ref=target_ref,
                storage_identity=_main_storage_identity(connection),
            )
            if target_digest != expected_target_digest:
                raise CanonicalRegistrationMigrationError(
                    "canonical registration physical target changed"
                )
        for row in connection.execute(f"SELECT * FROM {TABLE} ORDER BY rowid"):
            mapping = registration_record_mapping(_record(row))
            _validate_parent_facts(connection, row, mapping["registration"])
    except CanonicalRegistrationMigrationError:
        raise
    except Exception as exc:
        raise CanonicalRegistrationMigrationError(
            "canonical registration durable row validation failed"
        ) from exc


def _migrate_canonical_registration_connection(
    connection: sqlite3.Connection,
    *,
    fault: Callable[[str], None],
) -> str:
    present = _present(connection)
    if present == {TABLE, MARKER_TABLE}:
        _validate_canonical_registration_connection(connection)
        return "no-op"
    if present:
        raise CanonicalRegistrationMigrationError(
            "partial canonical registration schema"
        )
    parents = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('v5_project_series_relationships','v5_episode_projects',"
            "'v5_confirmed_creative_plans','v5_script_acceptances')"
        )
    }
    if parents != {
        "v5_project_series_relationships",
        "v5_episode_projects",
        "v5_confirmed_creative_plans",
        "v5_script_acceptances",
    }:
        raise CanonicalRegistrationMigrationError(
            "canonical registration lifecycle parents are unavailable"
        )
    connection.execute(table_statement())
    connection.execute(index_statement())
    fault("after-canonical-registration-table")
    connection.execute(marker_statement())
    fault("before-canonical-registration-marker")
    connection.execute(
        f"INSERT INTO {MARKER_TABLE} VALUES (?,?)",
        (MARKER_COMPONENT, SCHEMA_VERSION),
    )
    fault("before-canonical-registration-verify")
    _validate_canonical_registration_connection(connection)
    return "upgrade"


def validate_canonical_registration_database(database_path: Path | str) -> None:
    path = Path(database_path).resolve()
    if not path.exists():
        raise CanonicalRegistrationMigrationError(
            "database initialization required"
        )
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        _validate_canonical_registration_connection(connection)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise CanonicalRegistrationMigrationError("integrity check failed")
    finally:
        connection.close()


__all__ = [
    "CanonicalRegistrationMigrationError",
    "validate_canonical_registration_database",
]
