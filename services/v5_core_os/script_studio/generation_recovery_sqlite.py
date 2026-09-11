"""Exact optional Script generation component on the shared Creator connection."""

from pathlib import Path
from contextlib import closing
import re
import sqlite3

from .foundation import SqliteScriptStudioAdapter
from .generation_recovery import (
    GenerationStorageError, GenerationRecoveryError, canonical, strict_json,
    validate_record, validate_transition, validate_domain_association,
)


MARKER_TABLE = "creator_script_generation_schema"
TABLE = "creator_script_generation_commands"
INDEX = "ux_creator_script_generation_episode_pending"
COMPONENT = "script_generation_recovery"
COLUMNS = ("workspace_ref", "identity_digest", "series_ref", "episode_ref", "state", "record_json")


def statements():
    return {
        MARKER_TABLE: f"CREATE TABLE {MARKER_TABLE} (component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)",
        TABLE: f"CREATE TABLE {TABLE} (workspace_ref TEXT NOT NULL, identity_digest TEXT NOT NULL, "
               "series_ref TEXT NOT NULL, episode_ref TEXT NOT NULL, state TEXT NOT NULL "
               "CHECK(state IN ('PENDING','RESULT_READY','COMPLETED','FAILED')), record_json TEXT NOT NULL, "
               "PRIMARY KEY(workspace_ref, identity_digest))",
        INDEX: f"CREATE UNIQUE INDEX {INDEX} ON {TABLE}(workspace_ref, series_ref, episode_ref) "
               "WHERE state IN ('PENDING','RESULT_READY')",
    }


def _normalized(sql):
    return re.sub(r"\s+", "", sql or "").replace('"', "").lower()


def _record(row):
    try:
        value = validate_record(strict_json(row[5]))
        if (canonical(value) != row[5] or tuple(value[k] for k in
                ("workspaceRef", "identityDigest", "seriesRef", "episodeRef", "state")) != tuple(row[:5])):
            raise ValueError("indexed fields differ")
        return value
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise GenerationStorageError() from exc


def _association(connection, record):
    if record["state"] != "COMPLETED":
        return
    version = record["response"]["scriptVersion"]
    script_row = connection.execute(
        "SELECT * FROM v5_scripts WHERE workspace_ref=? AND script_ref=?",
        (record["workspaceRef"], version["scriptRef"])).fetchone()
    version_row = connection.execute(
        "SELECT * FROM v5_script_versions WHERE workspace_ref=? AND script_ref=? AND script_version_ref=?",
        (record["workspaceRef"], version["scriptRef"], version["scriptVersionRef"])).fetchone()
    validate_domain_association(record,
        SqliteScriptStudioAdapter._script(script_row) if script_row is not None else None,
        SqliteScriptStudioAdapter._version(version_row) if version_row is not None else None)


def validate_generation_connection(connection):
    try:
        expected = statements()
        for name, sql in expected.items():
            row = connection.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if (row is None or row[0] != ("index" if name == INDEX else "table")
                    or _normalized(row[1]) != _normalized(sql)):
                raise GenerationStorageError()
        objects = connection.execute(
            "SELECT name FROM sqlite_master WHERE tbl_name IN (?,?) AND type!='table' AND sql IS NOT NULL",
            (TABLE, MARKER_TABLE)).fetchall()
        if {row[0] for row in objects} != {INDEX}:
            raise GenerationStorageError()
        marker = connection.execute(f"SELECT component,schema_version FROM {MARKER_TABLE}").fetchall()
        if len(marker) != 1 or tuple(marker[0]) != (COMPONENT, 1):
            raise GenerationStorageError()
        if tuple(r[1] for r in connection.execute(f"PRAGMA table_info({TABLE})")) != COLUMNS:
            raise GenerationStorageError()
        identities, pending = set(), set()
        for row in connection.execute(f"SELECT {','.join(COLUMNS)} FROM {TABLE}"):
            record = _record(row)
            key = (record["workspaceRef"], record["identityDigest"])
            episode = (record["workspaceRef"], record["seriesRef"], record["episodeRef"])
            if key in identities or (record["state"] in {"PENDING", "RESULT_READY"} and episode in pending):
                raise GenerationStorageError()
            identities.add(key)
            if record["state"] in {"PENDING", "RESULT_READY"}:
                pending.add(episode)
            _association(connection, record)
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError) as exc:
        raise GenerationStorageError() from exc


class SqliteGenerationStore:
    def __init__(self, database_path, *, lifecycle_state):
        self.database_path = Path(database_path)
        from services.v4_platform.generation_dispatch_jobs import connect_storage
        self._state = lifecycle_state
        try:
            with closing(connect_storage(self.database_path, self, timeout=10, isolation_level=None)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                names = connection.execute("SELECT name FROM sqlite_master WHERE name IN (?,?,?)",
                                           (MARKER_TABLE, TABLE, INDEX)).fetchall()
                try:
                    if not names:
                        for sql in statements().values():
                            connection.execute(sql)
                        connection.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?,?)", (COMPONENT, 1))
                    validate_generation_connection(connection)
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except (sqlite3.DatabaseError, OSError) as exc:
            raise GenerationStorageError() from exc

    def _connection(self):
        connection = self._state.connection_or_none()
        if connection is None:
            raise GenerationStorageError()
        validate_generation_connection(connection)
        return connection

    def get(self, workspace, identity):
        try:
            row = self._connection().execute(
                f"SELECT {','.join(COLUMNS)} FROM {TABLE} WHERE workspace_ref=? AND identity_digest=?",
                (workspace, identity)).fetchone()
            return None if row is None else _record(row)
        except sqlite3.DatabaseError as exc:
            raise GenerationStorageError() from exc

    def pending(self, scope):
        try:
            row = self._connection().execute(
                f"SELECT {','.join(COLUMNS)} FROM {TABLE} WHERE workspace_ref=? AND series_ref=? AND episode_ref=? "
                "AND state IN ('PENDING','RESULT_READY')",
                tuple(scope[k] for k in ("workspaceRef", "seriesRef", "episodeRef"))).fetchone()
            return None if row is None else _record(row)
        except sqlite3.DatabaseError as exc:
            raise GenerationStorageError() from exc

    def save(self, record):
        old = self.get(record["workspaceRef"], record["identityDigest"])
        validate_transition(old, record)
        values = tuple(record[k] for k in ("workspaceRef", "identityDigest", "seriesRef", "episodeRef", "state"))
        try:
            connection = self._connection()
            if old is None:
                connection.execute(f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?)", (*values, canonical(record)))
            else:
                cursor = connection.execute(
                    f"UPDATE {TABLE} SET state=?,record_json=? WHERE workspace_ref=? AND identity_digest=? AND record_json=?",
                    (record["state"], canonical(record), record["workspaceRef"], record["identityDigest"], canonical(old)))
                if cursor.rowcount != 1:
                    raise GenerationStorageError()
            _association(connection, record)
        except sqlite3.IntegrityError as exc:
            raise GenerationRecoveryError("script_generation_pending") from exc
        except sqlite3.DatabaseError as exc:
            raise GenerationStorageError() from exc
