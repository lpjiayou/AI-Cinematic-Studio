"""Optional M5 application command recovery metadata in the Creator database.

Reservations and terminal results use short, independent transactions. This
component issues candidate receipts; it creates no Series Planning domain facts.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path
import re
import sqlite3

from .candidate_receipt_sqlite import (
    CANDIDATE_RECEIPT_SCHEMA_VERSION, CandidateReceiptSqliteError,
    SeriesPlanCandidateReceipt, canonical_json, canonical_json_digest,
    load_source_context_json, validate_candidate_receipt_record,
)
from .foundation import _normalize_content


COMMAND_SCHEMA = "creator.series-plan-candidate-command.v1"
COMPLETED_RECEIPT_SCHEMA = "creator.series-plan-candidate-receipt.v2"
IDENTITY_SCHEMA = "creator.series-plan-candidate-command-identity.v1"
SOURCE_IDENTITY_SCHEMA = "creator.series-plan-candidate-source-identity.v1"
REQUEST_SCHEMA = "creator.series-plan-candidate-request.v1"
MARKER_TABLE = "creator_series_plan_candidate_command_schema"
MARKER_COMPONENT = "series_plan_candidate_commands"
TABLE = "creator_series_plan_candidate_commands"
IDENTITY_INDEX = "ux_creator_series_plan_candidate_commands_identity"
CANDIDATE_REF_INDEX = "ux_creator_series_plan_candidate_commands_candidate_ref"
COMPONENT_SCHEMA_VERSION = 1
FAILURE_CODES = frozenset({"provider_timeout", "provider_unavailable", "invalid_provider_output", "application_error"})
COMMAND_COLUMNS = (
    "schema_version", "command_ref", "workspace_ref", "project_ref", "series_ref",
    "identity_digest", "request_digest", "source_context_digest", "source_context_json",
    "creative_input_digest", "state", "candidate_ref", "candidate_digest", "candidate_json",
    "failure_code", "created_at", "completed_at", "version", "row_digest",
)
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


class SeriesPlanCandidateCommandStorageError(RuntimeError):
    """The application command component is unavailable or cannot be trusted."""


@dataclass(frozen=True)
class SeriesPlanCandidateCommand:
    schemaVersion: str
    commandRef: str
    workspaceRef: str
    projectRef: str
    seriesRef: str
    identityDigest: str
    requestDigest: str
    sourceContextDigest: str
    sourceContextJson: str
    creativeInputDigest: str
    state: str
    candidateRef: str
    candidateDigest: str | None
    candidateJson: str | None
    failureCode: str | None
    createdAt: str
    completedAt: str | None
    version: int
    rowDigest: str = ""


def candidate_ref(workspace_ref, identity_digest):
    return "series-plan-candidate-" + canonical_json_digest({
        "schemaVersion": SOURCE_IDENTITY_SCHEMA,
        "workspaceRef": workspace_ref, "commandIdentityDigest": identity_digest,
    })


def request_digest(project_ref, series_ref, source_context_digest, creative_input_digest):
    return canonical_json_digest({
        "schemaVersion": REQUEST_SCHEMA, "projectRef": project_ref, "seriesRef": series_ref,
        "sourceContextDigest": source_context_digest, "creativeInputDigest": creative_input_digest,
    })


def seal_record(record):
    value = asdict(record)
    value.pop("rowDigest")
    return replace(record, rowDigest=canonical_json_digest(value))


def _ref(value):
    if (not isinstance(value, str) or not 0 < len(value) <= 200
            or not value.isprintable() or any(c.isspace() for c in value)):
        raise ValueError("invalid source reference")


def _source(record):
    source = load_source_context_json(record.sourceContextJson)
    for name in ("workspaceRef", "contentProfileRef", "projectRef", "seriesRef"):
        _ref(source[name])
    for name in ("projectTitle", "projectDescription", "targetPlatform", "aspectRatio",
                 "seriesTitle", "seriesDescription", "projectStatus", "seriesStatus"):
        if not isinstance(source[name], str):
            raise ValueError("invalid source text")
    for name in ("projectVersion", "seriesVersion", "plannedEpisodeCount", "createdEpisodeCount"):
        if type(source[name]) is not int:
            raise ValueError("invalid source integer")
    if (source["projectVersion"] < 1 or source["seriesVersion"] < 1
            or not 1 <= source["plannedEpisodeCount"] <= 500 or source["createdEpisodeCount"] < 0
            or any(source[name] != getattr(record, name) for name in ("workspaceRef", "projectRef", "seriesRef"))
            or canonical_json_digest(source) != record.sourceContextDigest):
        raise ValueError("inconsistent source context")
    return source


def completed_projection(record):
    """One v2 receipt projection, without inserting or rewriting a v1 receipt."""
    validate_command(record)
    if record.state != "COMPLETED":
        raise SeriesPlanCandidateCommandStorageError("candidate is not completed")
    return _projection(record, _source(record), COMPLETED_RECEIPT_SCHEMA)


def _projection(record, source, schema):
    return SeriesPlanCandidateReceipt(
        schema, record.candidateRef, record.workspaceRef, source["contentProfileRef"],
        record.projectRef, record.seriesRef, source["projectVersion"], source["seriesVersion"],
        record.sourceContextDigest, record.sourceContextJson, record.creativeInputDigest,
        record.candidateDigest, record.candidateJson, record.createdAt, 1,
    )


def validate_command(record):
    try:
        if (record.schemaVersion != COMMAND_SCHEMA or type(record.version) is not int or record.version != 1
                or record.state not in {"PENDING", "COMPLETED", "FAILED"}):
            raise ValueError("invalid command metadata")
        for digest in (record.identityDigest, record.requestDigest, record.sourceContextDigest,
                       record.creativeInputDigest, record.rowDigest):
            if not isinstance(digest, str) or not _HEX.fullmatch(digest):
                raise ValueError("invalid digest")
        source = _source(record)
        if (record.commandRef != "series-plan-candidate-command-" + record.identityDigest
                or record.candidateRef != candidate_ref(record.workspaceRef, record.identityDigest)
                or record.requestDigest != request_digest(record.projectRef, record.seriesRef,
                                                         record.sourceContextDigest, record.creativeInputDigest)
                or record.rowDigest != seal_record(record).rowDigest):
            raise ValueError("inconsistent identity, request or row digest")
        for timestamp in [record.createdAt] + ([record.completedAt] if record.completedAt is not None else []):
            if not isinstance(timestamp, str) or not _TIMESTAMP.fullmatch(timestamp):
                raise ValueError("invalid timestamp")
            datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        if record.completedAt is not None and record.completedAt < record.createdAt:
            raise ValueError("completion precedes reservation")
        if record.state == "PENDING":
            if any(value is not None for value in (record.candidateDigest, record.candidateJson, record.failureCode, record.completedAt)):
                raise ValueError("invalid pending fields")
            return None
        if record.completedAt is None:
            raise ValueError("missing completion timestamp")
        if record.state == "FAILED":
            if record.failureCode not in FAILURE_CODES or record.candidateDigest is not None or record.candidateJson is not None:
                raise ValueError("invalid failed fields")
            return None
        if record.failureCode is not None:
            raise ValueError("completed command contains a failure")
        # Reuse the existing receipt/source integrity rules without changing its
        # v1 DDL or writing a v1 row. Domain normalization checks closed content.
        candidate = validate_candidate_receipt_record(_projection(record, source, CANDIDATE_RECEIPT_SCHEMA_VERSION))
        content = _normalize_content(candidate, planned_count=source["plannedEpisodeCount"],
                                     ref_factory=lambda _prefix: "validation-only-item")
        for item in content["episodePlanItems"]:
            item.pop("episodePlanItemRef")
        if canonical_json({"schemaVersion": candidate["schemaVersion"], **content}) != record.candidateJson:
            raise ValueError("noncanonical candidate content")
        return candidate
    except (ValueError, TypeError, KeyError, AttributeError, CandidateReceiptSqliteError,
            UnicodeError, RecursionError, OverflowError) as exc:
        raise SeriesPlanCandidateCommandStorageError("invalid M5 candidate command") from exc


def marker_statement():
    return f"CREATE TABLE {MARKER_TABLE} (component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"


def table_statement():
    nullable = {"candidate_digest", "candidate_json", "failure_code", "completed_at"}
    definitions = [f"{name} {'INTEGER' if name == 'version' else 'TEXT'}"
                   + ("" if name in nullable else " NOT NULL") for name in COMMAND_COLUMNS]
    return f"CREATE TABLE {TABLE} (" + ", ".join(definitions) + ", PRIMARY KEY(workspace_ref, command_ref))"


def index_statements():
    return (
        f"CREATE UNIQUE INDEX {IDENTITY_INDEX} ON {TABLE}(workspace_ref, identity_digest)",
        f"CREATE UNIQUE INDEX {CANDIDATE_REF_INDEX} ON {TABLE}(workspace_ref, candidate_ref)",
    )


def _from_row(row):
    return SeriesPlanCandidateCommand(*(row[column] for column in COMMAND_COLUMNS))


def _values(record):
    return tuple(getattr(record, field.name) for field in fields(record))


def _normalized_sql(value):
    return re.sub(r"\s+", "", str(value or "")).replace('"', "").lower()


def validate_candidate_command_connection(connection):
    expected = {MARKER_TABLE: ("table", marker_statement()), TABLE: ("table", table_statement()),
                IDENTITY_INDEX: ("index", index_statements()[0]), CANDIDATE_REF_INDEX: ("index", index_statements()[1])}
    for name, (kind, sql) in expected.items():
        row = connection.execute("SELECT type, sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if row is None or row[0] != kind or _normalized_sql(row[1]) != _normalized_sql(sql):
            raise SeriesPlanCandidateCommandStorageError("partial or altered M5 candidate command schema")
    objects = connection.execute(
        "SELECT name FROM sqlite_master WHERE tbl_name IN (?, ?) AND type != 'table' AND sql IS NOT NULL",
        (TABLE, MARKER_TABLE),
    ).fetchall()
    if {row[0] for row in objects} != {IDENTITY_INDEX, CANDIDATE_REF_INDEX}:
        raise SeriesPlanCandidateCommandStorageError("unknown M5 candidate command object")
    columns = connection.execute(f"PRAGMA table_info({TABLE})").fetchall()
    if tuple(row[1] for row in columns) != COMMAND_COLUMNS:
        raise SeriesPlanCandidateCommandStorageError("invalid M5 candidate command columns")
    marker = connection.execute(f"SELECT component, schema_version FROM {MARKER_TABLE}").fetchall()
    if len(marker) != 1 or tuple(marker[0]) != (MARKER_COMPONENT, COMPONENT_SCHEMA_VERSION):
        raise SeriesPlanCandidateCommandStorageError("invalid M5 candidate command marker")
    identities, candidates = set(), set()
    for row in connection.execute(f"SELECT {','.join(COMMAND_COLUMNS)} FROM {TABLE}"):
        record = _from_row(row)
        validate_command(record)
        identity = (record.workspaceRef, record.identityDigest)
        candidate = (record.workspaceRef, record.candidateRef)
        if identity in identities or candidate in candidates:
            raise SeriesPlanCandidateCommandStorageError("duplicate M5 command identity")
        identities.add(identity)
        candidates.add(candidate)


def validate_transition(pending, terminal):
    validate_command(pending)
    validate_command(terminal)
    mutable = {"state", "candidateDigest", "candidateJson", "failureCode", "completedAt", "rowDigest"}
    if (pending.state != "PENDING" or terminal.state not in {"COMPLETED", "FAILED"}
            or any(getattr(pending, f.name) != getattr(terminal, f.name)
                   for f in fields(pending) if f.name not in mutable)):
        raise SeriesPlanCandidateCommandStorageError("invalid M5 command transition")


class SqliteSeriesPlanCandidateCommandStore:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path).resolve()
        with self._session(write=True, validate=False) as connection:
            names = connection.execute("SELECT name FROM sqlite_master WHERE name IN (?, ?, ?, ?)",
                                       (TABLE, MARKER_TABLE, IDENTITY_INDEX, CANDIDATE_REF_INDEX)).fetchall()
            if not names:
                connection.execute(table_statement())
                connection.execute(marker_statement())
                for sql in index_statements():
                    connection.execute(sql)
                connection.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)", (MARKER_COMPONENT, COMPONENT_SCHEMA_VERSION))
            validate_candidate_command_connection(connection)

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
                raise SeriesPlanCandidateCommandStorageError("foreign keys unavailable")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if validate:
                validate_candidate_command_connection(connection)
            yield connection
            connection.commit()
        except (sqlite3.DatabaseError, OSError) as exc:
            raise SeriesPlanCandidateCommandStorageError("M5 candidate command storage unavailable") from exc
        finally:
            if connection is not None:
                if connection.in_transaction:
                    connection.rollback()
                connection.close()

    def reserve(self, pending):
        validate_command(pending)
        if pending.state != "PENDING":
            raise SeriesPlanCandidateCommandStorageError("reservation must be pending")
        with self._session(write=True) as connection:
            row = connection.execute(f"SELECT * FROM {TABLE} WHERE workspace_ref=? AND identity_digest=?",
                                     (pending.workspaceRef, pending.identityDigest)).fetchone()
            if row is not None:
                return _from_row(row), False
            connection.execute(f"INSERT INTO {TABLE} ({','.join(COMMAND_COLUMNS)}) VALUES ({','.join('?' for _ in COMMAND_COLUMNS)})", _values(pending))
            return pending, True

    def finish(self, pending, terminal):
        validate_transition(pending, terminal)
        with self._session(write=True) as connection:
            cursor = connection.execute(
                f"UPDATE {TABLE} SET " + ",".join(f"{column}=?" for column in COMMAND_COLUMNS)
                + " WHERE workspace_ref=? AND command_ref=? AND state='PENDING' AND row_digest=?",
                (*_values(terminal), pending.workspaceRef, pending.commandRef, pending.rowDigest),
            )
            if cursor.rowcount != 1:
                raise SeriesPlanCandidateCommandStorageError("M5 reservation changed")

    def get_by_candidate(self, workspace_ref, candidate_ref):
        with self._session() as connection:
            row = connection.execute(f"SELECT * FROM {TABLE} WHERE workspace_ref=? AND candidate_ref=?",
                                     (workspace_ref, candidate_ref)).fetchone()
            return None if row is None else _from_row(row)

    def find_exact(self, workspace_ref, project_ref, series_ref, source_digest, candidate_digest):
        with self._session() as connection:
            return [_from_row(row) for row in connection.execute(
                f"SELECT * FROM {TABLE} WHERE workspace_ref=? AND project_ref=? AND series_ref=? "
                "AND source_context_digest=? AND candidate_digest=? AND state='COMPLETED'",
                (workspace_ref, project_ref, series_ref, source_digest, candidate_digest),
            )]

    def count(self):
        with self._session() as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]

    def close(self):
        """Connections are scoped to each operation."""
