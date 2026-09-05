"""Exact SQLite infrastructure for non-authoritative candidate receipts.

This module owns only the optional schema stored in the shared Creator SQLite
file.  Its physical location does not grant Series Plan or canonical authority.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any


CANDIDATE_RECEIPT_SCHEMA_VERSION = (
    "creator.series-plan-candidate-receipt.v1"
)
CANDIDATE_JSON_SCHEMA_VERSION = "creator.series-plan.candidate.v1"
SOURCE_CONTEXT_SCHEMA_VERSION = (
    "creator.series-plan-candidate-source-context.v1"
)
SOURCE_CONTEXT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "contentProfileRef",
        "projectRef",
        "projectTitle",
        "projectDescription",
        "targetPlatform",
        "aspectRatio",
        "plannedEpisodeCount",
        "seriesRef",
        "seriesTitle",
        "seriesDescription",
        "createdEpisodeCount",
        "projectVersion",
        "seriesVersion",
        "projectStatus",
        "seriesStatus",
    }
)
MARKER_TABLE = "creator_series_director_schema"
MARKER_COMPONENT = "series_plan_candidate_receipts"
TABLE = "creator_series_plan_candidate_receipts"
INDEX = "ux_creator_series_plan_candidate_receipts_exact_match"
SQLITE_COMPONENT_SCHEMA_VERSION = 1

RECEIPT_COLUMNS = (
    "schema_version",
    "candidate_ref",
    "workspace_ref",
    "content_profile_ref",
    "project_ref",
    "series_ref",
    "source_project_version",
    "source_series_version",
    "source_context_digest",
    "source_context_json",
    "creative_input_digest",
    "candidate_digest",
    "candidate_json",
    "created_at",
    "version",
)

_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)


class CandidateReceiptSqliteError(RuntimeError):
    """The optional receipt schema or a durable receipt is not trustworthy."""


@dataclass(frozen=True)
class SeriesPlanCandidateReceipt:
    schemaVersion: str
    candidateRef: str
    workspaceRef: str
    contentProfileRef: str
    projectRef: str
    seriesRef: str
    sourceProjectVersion: int
    sourceSeriesVersion: int
    sourceContextDigest: str
    sourceContextJson: str
    creativeInputDigest: str
    candidateDigest: str
    candidateJson: str
    createdAt: str
    version: int


def marker_statement() -> str:
    return (
        f"CREATE TABLE {MARKER_TABLE} ("
        "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
    )


def table_statement() -> str:
    return (
        f"CREATE TABLE {TABLE} ("
        "schema_version TEXT NOT NULL, "
        "candidate_ref TEXT NOT NULL, "
        "workspace_ref TEXT NOT NULL, "
        "content_profile_ref TEXT NOT NULL, "
        "project_ref TEXT NOT NULL, "
        "series_ref TEXT NOT NULL, "
        "source_project_version INTEGER NOT NULL, "
        "source_series_version INTEGER NOT NULL, "
        "source_context_digest TEXT NOT NULL, "
        "source_context_json TEXT NOT NULL, "
        "creative_input_digest TEXT NOT NULL, "
        "candidate_digest TEXT NOT NULL, "
        "candidate_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "version INTEGER NOT NULL, "
        "PRIMARY KEY(workspace_ref, candidate_ref))"
    )


def index_statement() -> str:
    return (
        f"CREATE UNIQUE INDEX {INDEX} ON {TABLE}("
        "workspace_ref, project_ref, series_ref, "
        "source_context_digest, candidate_digest)"
    )


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_json_digest(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


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


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CandidateReceiptSqliteError(
                "candidate receipt JSON contains duplicate keys"
            )
        value[key] = item
    return value


def _reject_float(_value: str) -> None:
    raise CandidateReceiptSqliteError(
        "candidate receipt JSON contains a floating-point value"
    )


def load_candidate_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise CandidateReceiptSqliteError("candidate receipt JSON is invalid")
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_strict_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except CandidateReceiptSqliteError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise CandidateReceiptSqliteError(
            "candidate receipt JSON is invalid"
        ) from exc
    if (
        not isinstance(parsed, dict)
        or parsed.get("schemaVersion") != CANDIDATE_JSON_SCHEMA_VERSION
        or "creativeInput" in parsed
        or canonical_json(parsed) != value
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt JSON is not canonical"
        )
    return parsed


def load_source_context_json(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        raise CandidateReceiptSqliteError(
            "candidate receipt source context JSON is invalid"
        )
    try:
        parsed = json.loads(
            value,
            object_pairs_hook=_strict_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except CandidateReceiptSqliteError:
        raise
    except (json.JSONDecodeError, TypeError, UnicodeError) as exc:
        raise CandidateReceiptSqliteError(
            "candidate receipt source context JSON is invalid"
        ) from exc
    if (
        not isinstance(parsed, dict)
        or parsed.get("schemaVersion") != SOURCE_CONTEXT_SCHEMA_VERSION
        or set(parsed) != SOURCE_CONTEXT_FIELDS
        or "creativeInput" in parsed
        or canonical_json(parsed) != value
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt source context JSON is not canonical"
        )
    return parsed


def _required_ref(value: Any) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > 200
        or not value.isprintable()
        or any(character.isspace() for character in value)
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt reference is invalid"
        )


def _required_digest(value: Any) -> None:
    if not isinstance(value, str) or _DIGEST_PATTERN.fullmatch(value) is None:
        raise CandidateReceiptSqliteError(
            "candidate receipt digest is invalid"
        )


def validate_candidate_receipt_record(
    receipt: SeriesPlanCandidateReceipt,
) -> dict[str, Any]:
    if (
        receipt.schemaVersion != CANDIDATE_RECEIPT_SCHEMA_VERSION
        or type(receipt.sourceProjectVersion) is not int
        or receipt.sourceProjectVersion < 1
        or type(receipt.sourceSeriesVersion) is not int
        or receipt.sourceSeriesVersion < 1
        or type(receipt.version) is not int
        or receipt.version != 1
        or not isinstance(receipt.createdAt, str)
        or _TIMESTAMP_PATTERN.fullmatch(receipt.createdAt) is None
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt metadata is invalid"
        )
    for reference in (
        receipt.candidateRef,
        receipt.workspaceRef,
        receipt.contentProfileRef,
        receipt.projectRef,
        receipt.seriesRef,
    ):
        _required_ref(reference)
    for digest in (
        receipt.sourceContextDigest,
        receipt.creativeInputDigest,
        receipt.candidateDigest,
    ):
        _required_digest(digest)
    source_context = load_source_context_json(receipt.sourceContextJson)
    for field in (
        "workspaceRef",
        "contentProfileRef",
        "projectRef",
        "seriesRef",
    ):
        _required_ref(source_context.get(field))
    for field in (
        "projectTitle",
        "projectDescription",
        "targetPlatform",
        "aspectRatio",
        "seriesTitle",
        "seriesDescription",
        "projectStatus",
        "seriesStatus",
    ):
        if not isinstance(source_context.get(field), str):
            raise CandidateReceiptSqliteError(
                "candidate receipt source context is invalid"
            )
    if (
        type(source_context.get("plannedEpisodeCount")) is not int
        or not 1 <= source_context["plannedEpisodeCount"] <= 500
        or type(source_context.get("createdEpisodeCount")) is not int
        or source_context["createdEpisodeCount"] < 0
        or type(source_context.get("projectVersion")) is not int
        or source_context["projectVersion"] < 1
        or type(source_context.get("seriesVersion")) is not int
        or source_context["seriesVersion"] < 1
        or source_context.get("workspaceRef") != receipt.workspaceRef
        or source_context.get("contentProfileRef") != receipt.contentProfileRef
        or source_context.get("projectRef") != receipt.projectRef
        or source_context.get("seriesRef") != receipt.seriesRef
        or source_context.get("projectVersion")
        != receipt.sourceProjectVersion
        or source_context.get("seriesVersion") != receipt.sourceSeriesVersion
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt source context is inconsistent"
        )
    if canonical_json_digest(source_context) != receipt.sourceContextDigest:
        raise CandidateReceiptSqliteError(
            "candidate receipt source context digest does not match"
        )
    candidate = load_candidate_json(receipt.candidateJson)
    if sha256(receipt.candidateJson.encode("utf-8")).hexdigest() != (
        receipt.candidateDigest
    ):
        raise CandidateReceiptSqliteError(
            "candidate receipt content digest does not match"
        )
    return candidate


def _receipt_from_row(row: sqlite3.Row) -> SeriesPlanCandidateReceipt:
    return SeriesPlanCandidateReceipt(
        row["schema_version"],
        row["candidate_ref"],
        row["workspace_ref"],
        row["content_profile_ref"],
        row["project_ref"],
        row["series_ref"],
        row["source_project_version"],
        row["source_series_version"],
        row["source_context_digest"],
        row["source_context_json"],
        row["creative_input_digest"],
        row["candidate_digest"],
        row["candidate_json"],
        row["created_at"],
        row["version"],
    )


def validate_candidate_receipt_connection(
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
        raise CandidateReceiptSqliteError(
            "partial candidate receipt schema"
        )
    if _normalized_sql(_stored_sql(connection, "table", TABLE)) != (
        _normalized_sql(table_statement())
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt table definition"
        )
    if _normalized_sql(_stored_sql(connection, "table", MARKER_TABLE)) != (
        _normalized_sql(marker_statement())
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt marker definition"
        )
    if _normalized_sql(_stored_sql(connection, "index", INDEX)) != (
        _normalized_sql(index_statement())
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt index definition"
        )

    columns = connection.execute(f"PRAGMA table_info({TABLE})").fetchall()
    if tuple(row[1] for row in columns) != RECEIPT_COLUMNS:
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt table columns"
        )
    expected_types = (
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "INTEGER",
        "INTEGER",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "TEXT",
        "INTEGER",
    )
    if (
        tuple(str(row[2]).upper() for row in columns) != expected_types
        or any(int(row[3]) != 1 for row in columns)
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt column constraints"
        )
    primary_key = tuple(
        row[1]
        for row in sorted(columns, key=lambda item: int(item[5]))
        if int(row[5]) > 0
    )
    if primary_key != ("workspace_ref", "candidate_ref"):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt primary key"
        )

    marker_columns = connection.execute(
        f"PRAGMA table_info({MARKER_TABLE})"
    ).fetchall()
    if tuple(row[1] for row in marker_columns) != (
        "component",
        "schema_version",
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt marker columns"
        )
    component_column, version_column = marker_columns
    if (
        str(component_column[2]).upper() != "TEXT"
        or int(component_column[5]) != 1
        or str(version_column[2]).upper() != "INTEGER"
        or int(version_column[3]) != 1
        or int(version_column[5]) != 0
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt marker constraints"
        )
    marker_rows = connection.execute(
        f"SELECT component, schema_version FROM {MARKER_TABLE} "
        "ORDER BY component"
    ).fetchall()
    if len(marker_rows) != 1 or tuple(marker_rows[0]) != (
        MARKER_COMPONENT,
        SQLITE_COMPONENT_SCHEMA_VERSION,
    ):
        raise CandidateReceiptSqliteError(
            "unsupported candidate receipt marker"
        )

    rows = connection.execute(
        f"SELECT {','.join(RECEIPT_COLUMNS)} FROM {TABLE} "
        "ORDER BY workspace_ref, candidate_ref"
    ).fetchall()
    for row in rows:
        validate_candidate_receipt_record(_receipt_from_row(row))


def _dedupe_key(receipt: SeriesPlanCandidateReceipt) -> tuple[str, ...]:
    return (
        receipt.workspaceRef,
        receipt.projectRef,
        receipt.seriesRef,
        receipt.sourceContextDigest,
        receipt.candidateDigest,
    )


class SqliteSeriesPlanCandidateReceiptStore:
    """Append-only optional component sharing the Creator SQLite file."""

    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            connection.close()
            raise CandidateReceiptSqliteError(
                "foreign key enforcement unavailable"
            )
        return connection

    @contextmanager
    def _session(self, *, write: bool = False):
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
    def _presence(
        connection: sqlite3.Connection,
    ) -> tuple[set[str], bool]:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name IN (?, ?)",
                (TABLE, MARKER_TABLE),
            )
        }
        index_present = (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (INDEX,),
            ).fetchone()
            is not None
        )
        return tables, index_present

    def _initialize(self) -> None:
        try:
            with self._lock, self._session(write=True) as connection:
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
                    raise CandidateReceiptSqliteError(
                        "partial candidate receipt schema"
                    )
                validate_candidate_receipt_connection(connection)
        except CandidateReceiptSqliteError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CandidateReceiptSqliteError(
                "candidate receipt storage is unavailable"
            ) from exc

    def issue(
        self, receipt: SeriesPlanCandidateReceipt
    ) -> tuple[SeriesPlanCandidateReceipt, bool]:
        validate_candidate_receipt_record(receipt)
        try:
            with self._lock, self._session(write=True) as connection:
                existing = connection.execute(
                    f"SELECT * FROM {TABLE} "
                    "WHERE workspace_ref = ? AND project_ref = ? "
                    "AND series_ref = ? AND source_context_digest = ? "
                    "AND candidate_digest = ?",
                    _dedupe_key(receipt),
                ).fetchone()
                if existing is not None:
                    stored = _receipt_from_row(existing)
                    validate_candidate_receipt_record(stored)
                    return stored, True
                connection.execute(
                    f"INSERT INTO {TABLE} ({','.join(RECEIPT_COLUMNS)}) "
                    f"VALUES ({','.join('?' for _ in RECEIPT_COLUMNS)})",
                    (
                        receipt.schemaVersion,
                        receipt.candidateRef,
                        receipt.workspaceRef,
                        receipt.contentProfileRef,
                        receipt.projectRef,
                        receipt.seriesRef,
                        receipt.sourceProjectVersion,
                        receipt.sourceSeriesVersion,
                        receipt.sourceContextDigest,
                        receipt.sourceContextJson,
                        receipt.creativeInputDigest,
                        receipt.candidateDigest,
                        receipt.candidateJson,
                        receipt.createdAt,
                        receipt.version,
                    ),
                )
            return receipt, False
        except CandidateReceiptSqliteError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CandidateReceiptSqliteError(
                "candidate receipt storage is unavailable"
            ) from exc

    def get(
        self, workspace_ref: str, candidate_ref: str
    ) -> SeriesPlanCandidateReceipt | None:
        try:
            with self._session() as connection:
                row = connection.execute(
                    f"SELECT * FROM {TABLE} "
                    "WHERE workspace_ref = ? AND candidate_ref = ?",
                    (workspace_ref, candidate_ref),
                ).fetchone()
            if row is None:
                return None
            receipt = _receipt_from_row(row)
            validate_candidate_receipt_record(receipt)
            return receipt
        except CandidateReceiptSqliteError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CandidateReceiptSqliteError(
                "candidate receipt storage is unavailable"
            ) from exc

    def find_exact(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        source_context_digest: str,
        candidate_digest: str,
    ) -> list[SeriesPlanCandidateReceipt]:
        try:
            with self._session() as connection:
                rows = connection.execute(
                    f"SELECT * FROM {TABLE} "
                    "WHERE workspace_ref = ? AND project_ref = ? "
                    "AND series_ref = ? AND source_context_digest = ? "
                    "AND candidate_digest = ?",
                    (
                        workspace_ref,
                        project_ref,
                        series_ref,
                        source_context_digest,
                        candidate_digest,
                    ),
                ).fetchall()
            receipts = [_receipt_from_row(row) for row in rows]
            for receipt in receipts:
                validate_candidate_receipt_record(receipt)
            return receipts
        except CandidateReceiptSqliteError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CandidateReceiptSqliteError(
                "candidate receipt storage is unavailable"
            ) from exc

    def count(self, workspace_ref: str | None = None) -> int:
        try:
            with self._session() as connection:
                if workspace_ref is None:
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {TABLE}"
                    ).fetchone()
                else:
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {TABLE} WHERE workspace_ref = ?",
                        (workspace_ref,),
                    ).fetchone()
            return int(row[0])
        except (OSError, sqlite3.DatabaseError) as exc:
            raise CandidateReceiptSqliteError(
                "candidate receipt storage is unavailable"
            ) from exc

    def close(self) -> None:
        """Connections are operation-scoped; closing the store is a no-op."""
