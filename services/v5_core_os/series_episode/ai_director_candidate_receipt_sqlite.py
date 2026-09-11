"""Optional Creator application recovery metadata in the shared SQLite file.

This storage adapter grants no Series/Episode or confirmed-plan authority.
Transactions reserve and finish commands; they never span generation calls.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


COMMAND_SCHEMA = "creator.ai-director-candidate-command.v1"
RECEIPT_SCHEMA = "creator.ai-director-candidate-receipt.v1"
CANDIDATE_SCHEMA = "creator.ai-director-candidate.v1"
IDENTITY_SCHEMA = "creator.ai-director-candidate-command-identity.v1"
SOURCE_IDENTITY_SCHEMA = "creator.ai-director-candidate-source-identity.v1"
REQUEST_SCHEMA = "creator.ai-director-candidate-request.v1"
MARKER_TABLE = "creator_ai_director_candidate_schema"
MARKER_COMPONENT = "ai_director_candidate_commands"
TABLE = "creator_ai_director_candidate_commands"
IDENTITY_INDEX = "ux_creator_ai_director_candidate_commands_identity"
SOURCE_REF_INDEX = "ux_creator_ai_director_candidate_commands_source_ref"
SQLITE_COMPONENT_SCHEMA_VERSION = 1
FAILURE_CODES = frozenset({
    "provider_timeout", "provider_unavailable", "invalid_provider_output",
    "application_error",
})
COMMAND_COLUMNS = (
    "schema_version", "command_ref", "workspace_ref", "identity_mode",
    "identity_digest", "request_digest", "brief_digest", "state",
    "source_plan_ref", "source_plan_version", "plan_digest", "candidate_digest",
    "candidate_json", "failure_code", "created_at", "completed_at", "version",
    "record_digest",
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")


class AiDirectorCandidateStorageError(RuntimeError):
    """Application command storage cannot be trusted or reached."""


@dataclass(frozen=True)
class AiDirectorCandidateCommand:
    schemaVersion: str
    commandRef: str
    workspaceRef: str
    identityMode: str
    identityDigest: str
    requestDigest: str
    briefDigest: str
    state: str
    sourcePlanRef: str
    sourcePlanVersion: int
    planDigest: str | None
    candidateDigest: str | None
    candidateJson: str | None
    failureCode: str | None
    createdAt: str
    completedAt: str | None
    version: int
    recordDigest: str = ""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def canonical_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def source_ref(workspace_ref: str, identity_digest: str) -> str:
    return "ai-director-candidate-" + canonical_digest({
        "schemaVersion": SOURCE_IDENTITY_SCHEMA,
        "workspaceRef": workspace_ref,
        "commandIdentityDigest": identity_digest,
    })


def seal_record(record: AiDirectorCandidateCommand) -> AiDirectorCandidateCommand:
    # A corruption checksum, not a credential or a claim of cryptographic signing.
    # It binds opaque requestDigest even though raw brief/key are never stored.
    value = asdict(record)
    value.pop("recordDigest")
    return replace(record, recordDigest=canonical_digest(value))


def marker_statement() -> str:
    return (f"CREATE TABLE {MARKER_TABLE} (component TEXT PRIMARY KEY, "
            "schema_version INTEGER NOT NULL)")


def table_statement() -> str:
    nullable = {"plan_digest", "candidate_digest", "candidate_json", "failure_code", "completed_at"}
    definitions = [
        f"{name} {'INTEGER' if name in {'source_plan_version', 'version'} else 'TEXT'}"
        + ("" if name in nullable else " NOT NULL")
        for name in COMMAND_COLUMNS
    ]
    return (f"CREATE TABLE {TABLE} (" + ", ".join(definitions)
            + ", PRIMARY KEY(workspace_ref, command_ref))")


def index_statements() -> tuple[str, str]:
    return (
        f"CREATE UNIQUE INDEX {IDENTITY_INDEX} ON {TABLE}(workspace_ref, identity_digest)",
        f"CREATE UNIQUE INDEX {SOURCE_REF_INDEX} ON {TABLE}(workspace_ref, source_plan_ref)",
    )


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate candidate field")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite candidate number")


def _no_raw_input(value):
    if isinstance(value, dict):
        if {"brief", "creativeInput", "idempotencyKey"} & set(value):
            raise ValueError("raw command input in candidate")
        for item in value.values():
            _no_raw_input(item)
    elif isinstance(value, list):
        for item in value:
            _no_raw_input(item)


def validate_command(record: AiDirectorCandidateCommand) -> dict | None:
    try:
        if (record.schemaVersion != COMMAND_SCHEMA
                or record.identityMode not in {"KEYED", "UNKEYED"}
                or record.state not in {"PENDING", "COMPLETED", "FAILED"}
                or type(record.sourcePlanVersion) is not int or record.sourcePlanVersion != 1
                or type(record.version) is not int or record.version != 1):
            raise ValueError("invalid command metadata")
        workspace = record.workspaceRef
        if (not isinstance(workspace, str) or not workspace or len(workspace) > 200
                or not workspace.isprintable() or any(c.isspace() for c in workspace)
                or "/" in workspace or "\\" in workspace or workspace in {".", ".."}):
            raise ValueError("invalid workspace")
        for digest in (record.identityDigest, record.requestDigest, record.briefDigest, record.recordDigest):
            if not isinstance(digest, str) or not _HEX.fullmatch(digest):
                raise ValueError("invalid command digest")
        if (record.commandRef != "ai-director-candidate-command-" + record.identityDigest
                or record.sourcePlanRef != source_ref(workspace, record.identityDigest)
                or seal_record(record).recordDigest != record.recordDigest):
            raise ValueError("inconsistent command identity or checksum")
        timestamps = [record.createdAt]
        if record.completedAt is not None:
            timestamps.append(record.completedAt)
        for timestamp in timestamps:
            if not isinstance(timestamp, str) or not _TIMESTAMP.fullmatch(timestamp):
                raise ValueError("invalid timestamp")
            datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        if record.completedAt is not None and record.completedAt < record.createdAt:
            raise ValueError("completion precedes creation")
        candidate_fields = (record.planDigest, record.candidateDigest, record.candidateJson)
        if record.state == "PENDING":
            if any(value is not None for value in (*candidate_fields, record.failureCode, record.completedAt)):
                raise ValueError("invalid pending fields")
            return None
        if record.completedAt is None:
            raise ValueError("terminal command has no completion timestamp")
        if record.state == "FAILED":
            if record.failureCode not in FAILURE_CODES or any(value is not None for value in candidate_fields):
                raise ValueError("invalid failed fields")
            return None
        if record.failureCode is not None:
            raise ValueError("completed command has a failure")
        candidate = json.loads(record.candidateJson, object_pairs_hook=_pairs, parse_constant=_nonfinite)
        if not isinstance(candidate, dict) or set(candidate) != {
            "schemaVersion", "sourcePlanRef", "sourcePlanVersion", "briefDigest", "planDigest", "plan",
        }:
            raise ValueError("invalid candidate fields")
        _no_raw_input(candidate)
        if (candidate["schemaVersion"] != CANDIDATE_SCHEMA
                or candidate["sourcePlanRef"] != record.sourcePlanRef
                or type(candidate["sourcePlanVersion"]) is not int or candidate["sourcePlanVersion"] != 1
                or candidate["briefDigest"] != record.briefDigest
                or candidate["planDigest"] != record.planDigest
                or not isinstance(candidate["plan"], dict)
                or candidate["plan"].get("schemaVersion") != "creator.ai-director.plan.v1"
                or canonical_json(candidate) != record.candidateJson
                or canonical_digest(candidate["plan"]) != record.planDigest
                or canonical_digest(candidate) != record.candidateDigest):
            raise ValueError("candidate content or digest mismatch")
        return candidate
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise AiDirectorCandidateStorageError("invalid AI Director candidate command") from exc


def _from_row(row) -> AiDirectorCandidateCommand:
    return AiDirectorCandidateCommand(*(row[column] for column in COMMAND_COLUMNS))


def _values(record):
    return tuple(getattr(record, field.name) for field in fields(record))


def _normalized_sql(value):
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def validate_ai_director_candidate_connection(connection: sqlite3.Connection) -> None:
    expected = {
        MARKER_TABLE: ("table", marker_statement()),
        TABLE: ("table", table_statement()),
        IDENTITY_INDEX: ("index", index_statements()[0]),
        SOURCE_REF_INDEX: ("index", index_statements()[1]),
    }
    for name, (kind, statement) in expected.items():
        row = connection.execute("SELECT type, sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if row is None or row[0] != kind or _normalized_sql(row[1]) != _normalized_sql(statement):
            raise AiDirectorCandidateStorageError("partial or unsupported AI Director command schema")
    # No extra indexes/triggers on either component table, including implicit
    # UNIQUE constraints (also rejected by the exact CREATE TABLE comparison).
    extras = connection.execute(
        "SELECT name FROM sqlite_master WHERE tbl_name IN (?, ?) "
        "AND type NOT IN ('table') AND sql IS NOT NULL", (TABLE, MARKER_TABLE),
    ).fetchall()
    if {row[0] for row in extras} != {IDENTITY_INDEX, SOURCE_REF_INDEX}:
        raise AiDirectorCandidateStorageError("unknown AI Director command schema object")
    columns = connection.execute(f"PRAGMA table_info({TABLE})").fetchall()
    if tuple(row[1] for row in columns) != COMMAND_COLUMNS:
        raise AiDirectorCandidateStorageError("invalid AI Director command columns")
    marker = connection.execute(f"SELECT component, schema_version FROM {MARKER_TABLE}").fetchall()
    if len(marker) != 1 or tuple(marker[0]) != (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION):
        raise AiDirectorCandidateStorageError("invalid AI Director command marker")
    identities, sources = set(), set()
    for row in connection.execute(f"SELECT {','.join(COMMAND_COLUMNS)} FROM {TABLE}"):
        record = _from_row(row)
        validate_command(record)
        identity = (record.workspaceRef, record.identityDigest)
        source = (record.workspaceRef, record.sourcePlanRef)
        if identity in identities or source in sources:
            raise AiDirectorCandidateStorageError("duplicate AI Director command identity")
        identities.add(identity)
        sources.add(source)


def validate_transition(pending, terminal) -> None:
    validate_command(pending)
    validate_command(terminal)
    mutable = {"state", "planDigest", "candidateDigest", "candidateJson", "failureCode", "completedAt", "recordDigest"}
    if (pending.state != "PENDING" or terminal.state not in {"COMPLETED", "FAILED"}
            or any(getattr(pending, f.name) != getattr(terminal, f.name)
                   for f in fields(pending) if f.name not in mutable)):
        raise AiDirectorCandidateStorageError("invalid AI Director command transition")


class SqliteAiDirectorCandidateCommandStore:
    """Operation-scoped connections; unique reservation works across processes."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        with self._session(write=True, validate=False) as connection:
            names = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE name IN (?, ?, ?, ?)",
                (TABLE, MARKER_TABLE, IDENTITY_INDEX, SOURCE_REF_INDEX),
            )}
            if not names:
                connection.execute(table_statement())
                connection.execute(marker_statement())
                for statement in index_statements():
                    connection.execute(statement)
                connection.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
                                   (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION))
            validate_ai_director_candidate_connection(connection)

    @contextmanager
    def _session(self, *, write=False, validate=True):
        connection = None
        try:
            from services.v4_platform.generation_dispatch_jobs import connect_storage
            connection = connect_storage(self.database_path, self, timeout=10, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 10000")
            if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                raise AiDirectorCandidateStorageError("foreign keys unavailable")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if validate:
                validate_ai_director_candidate_connection(connection)
            yield connection
            connection.commit()
        except (sqlite3.DatabaseError, OSError) as exc:
            raise AiDirectorCandidateStorageError("AI Director candidate storage unavailable") from exc
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def reserve(self, pending: AiDirectorCandidateCommand) -> tuple[AiDirectorCandidateCommand, bool]:
        validate_command(pending)
        if pending.state != "PENDING":
            raise AiDirectorCandidateStorageError("reservation must be pending")
        with self._session(write=True) as connection:
            row = connection.execute(
                f"SELECT * FROM {TABLE} WHERE workspace_ref=? AND identity_digest=?",
                (pending.workspaceRef, pending.identityDigest),
            ).fetchone()
            if row is not None:
                return _from_row(row), False
            connection.execute(f"INSERT INTO {TABLE} ({','.join(COMMAND_COLUMNS)}) "
                               f"VALUES ({','.join('?' for _ in COMMAND_COLUMNS)})", _values(pending))
            return pending, True

    def finish(self, pending: AiDirectorCandidateCommand, terminal: AiDirectorCandidateCommand) -> None:
        validate_transition(pending, terminal)
        with self._session(write=True) as connection:
            cursor = connection.execute(
                f"UPDATE {TABLE} SET " + ",".join(f"{column}=?" for column in COMMAND_COLUMNS)
                + " WHERE workspace_ref=? AND command_ref=? AND state='PENDING' AND record_digest=?",
                (*_values(terminal), pending.workspaceRef, pending.commandRef, pending.recordDigest),
            )
            if cursor.rowcount != 1:
                raise AiDirectorCandidateStorageError("AI Director candidate reservation changed")

    def get_by_source(self, workspace_ref: str, source_plan_ref: str) -> AiDirectorCandidateCommand | None:
        with self._session() as connection:
            row = connection.execute(f"SELECT * FROM {TABLE} WHERE workspace_ref=? AND source_plan_ref=?",
                                     (workspace_ref, source_plan_ref)).fetchone()
            return None if row is None else _from_row(row)

    def count(self) -> int:
        with self._session() as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]

    def close(self) -> None:
        """Connections close at the end of every operation."""
