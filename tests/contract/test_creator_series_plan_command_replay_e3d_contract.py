"""Optional M5 SQLite command component integrity and persistence contracts."""

from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.creator_workspace_mvp.series_plan_candidate_commands import new_pending_command
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_intelligence.migration import SeriesIntelligenceMigrationError, validate_series_intelligence_database
from services.v5_core_os.series_planning.candidate_command_sqlite import (
    CANDIDATE_REF_INDEX, COMMAND_COLUMNS, COMPONENT_SCHEMA_VERSION, IDENTITY_INDEX,
    MARKER_COMPONENT, MARKER_TABLE, TABLE, SeriesPlanCandidateCommandStorageError,
    SqliteSeriesPlanCandidateCommandStore, completed_projection, marker_statement,
    seal_record, validate_candidate_command_connection,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import (
    INDEX as V1_INDEX, MARKER_TABLE as V1_MARKER, TABLE as V1_TABLE,
    SqliteSeriesPlanCandidateReceiptStore,
)
from tests.unit.test_series_plan_command_idempotency_e3d import NOW, completed_command, source_context


class CandidateCommandSqliteContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "creator.sqlite3"
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=True)
        self.before = self.schema()
        self.pending = new_pending_command(source_context(), "sensitive raw creative input sentinel", "raw key sentinel", clock=lambda: NOW)

    def connect(self, path=None):
        connection = sqlite3.connect(path or self.path)
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def schema(self, path=None):
        with sqlite3.connect(path or self.path) as connection:
            return connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()

    def copy_database(self, label):
        path = self.root / (label + ".sqlite3")
        path.write_bytes(self.path.read_bytes())
        return path

    def test_optional_component_adds_exactly_two_tables_and_two_indexes(self):
        validate_series_intelligence_database(self.path)
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        after = self.schema()
        old = {row[1]: row for row in self.before}
        new = {row[1]: row for row in after}
        self.assertEqual(set(new) - set(old), {TABLE, MARKER_TABLE, IDENTITY_INDEX, CANDIDATE_REF_INDEX})
        self.assertEqual({name: new[name] for name in old}, old)
        con = self.connect()
        self.assertEqual(tuple(row[1] for row in con.execute(f"PRAGMA table_info({TABLE})")), COMMAND_COLUMNS)
        self.assertEqual([tuple(row) for row in con.execute(f"SELECT * FROM {MARKER_TABLE}")], [(MARKER_COMPONENT, COMPONENT_SCHEMA_VERSION)])
        validate_candidate_command_connection(con)
        validate_series_intelligence_database(self.path)
        LifecycleAssembly.sqlite(self.path, initialize_or_upgrade=False)
        self.assertEqual(store.count(), 0)
        self.assertEqual(after, self.schema())

    def test_reservation_transition_restart_and_exact_replay_preserve_bytes(self):
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        self.assertEqual(store.reserve(self.pending), (self.pending, True))
        before = self.path.read_bytes()
        self.assertEqual(store.reserve(self.pending), (self.pending, False))
        self.assertEqual(before, self.path.read_bytes())
        completed = completed_command(self.pending)
        store.finish(self.pending, completed)
        before = self.path.read_bytes()
        restarted = SqliteSeriesPlanCandidateCommandStore(self.path)
        self.assertEqual(restarted.reserve(self.pending), (completed, False))
        self.assertEqual(restarted.get_by_candidate(completed.workspaceRef, completed.candidateRef), completed)
        self.assertEqual(completed_projection(completed).schemaVersion, "creator.series-plan-candidate-receipt.v2")
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(restarted.count(), 1)
        for row in self.connect().execute(f"SELECT * FROM {TABLE}"):
            for value in row:
                if isinstance(value, str):
                    self.assertNotIn("raw key sentinel", value)
                    self.assertNotIn("sensitive raw creative input sentinel", value)
        con = self.connect()
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_initializing_keyed_commands_does_not_touch_v1_ddl_or_receipts(self):
        SqliteSeriesPlanCandidateReceiptStore(self.path)
        con = self.connect()
        def old_objects():
            return [tuple(row) for row in con.execute("SELECT type,name,sql FROM sqlite_master WHERE name IN (?,?,?) ORDER BY name", (V1_TABLE, V1_MARKER, V1_INDEX))]
        before = old_objects()
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        store.reserve(self.pending)
        store.finish(self.pending, completed_command(self.pending))
        self.assertEqual(before, old_objects())
        self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {V1_TABLE}").fetchone()[0], 0)

    def test_marker_only_and_every_missing_component_object_fail_closed_without_repair(self):
        path = self.copy_database("marker-only")
        with self.connect(path) as con:
            con.execute(marker_statement())
            con.execute(f"INSERT INTO {MARKER_TABLE} VALUES (?,?)", (MARKER_COMPONENT, COMPONENT_SCHEMA_VERSION))
        before = path.read_bytes()
        with self.assertRaises(SeriesPlanCandidateCommandStorageError):
            SqliteSeriesPlanCandidateCommandStore(path)
        self.assertEqual(before, path.read_bytes())
        SqliteSeriesPlanCandidateCommandStore(self.path)
        for kind, name in (("TABLE", MARKER_TABLE), ("TABLE", TABLE), ("INDEX", IDENTITY_INDEX), ("INDEX", CANDIDATE_REF_INDEX)):
            with self.subTest(name=name):
                path = self.copy_database(name)
                with self.connect(path) as con:
                    con.execute(f"DROP {kind} {name}")
                before = path.read_bytes()
                with self.assertRaises(SeriesPlanCandidateCommandStorageError):
                    SqliteSeriesPlanCandidateCommandStore(path)
                self.assertEqual(before, path.read_bytes())
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    validate_series_intelligence_database(path)

    def test_altered_table_index_marker_and_unknown_objects_are_rejected(self):
        SqliteSeriesPlanCandidateCommandStore(self.path)
        mutations = {
            "column": [f"ALTER TABLE {TABLE} ADD COLUMN unknown TEXT"],
            "nonunique": [f"DROP INDEX {IDENTITY_INDEX}", f"CREATE INDEX {IDENTITY_INDEX} ON {TABLE}(workspace_ref,identity_digest)"],
            "wrongindex": [f"DROP INDEX {CANDIDATE_REF_INDEX}", f"CREATE UNIQUE INDEX {CANDIDATE_REF_INDEX} ON {TABLE}(candidate_ref,workspace_ref)"],
            "marker": [f"UPDATE {MARKER_TABLE} SET schema_version=2"],
            "markermember": [f"INSERT INTO {MARKER_TABLE} VALUES ('unknown',1)"],
            "extraindex": [f"CREATE INDEX unknown_m5_index ON {TABLE}(state)"],
            "trigger": [f"CREATE TRIGGER unknown_m5_trigger AFTER INSERT ON {TABLE} BEGIN SELECT 1; END"],
        }
        for label, statements in mutations.items():
            with self.subTest(label=label):
                path = self.copy_database(label)
                with self.connect(path) as con:
                    for sql in statements:
                        con.execute(sql)
                before = path.read_bytes()
                with self.assertRaises(SeriesPlanCandidateCommandStorageError):
                    SqliteSeriesPlanCandidateCommandStore(path)
                self.assertEqual(before, path.read_bytes())
        path = self.copy_database("third-table")
        with self.connect(path) as con:
            con.execute("CREATE TABLE unknown_third_creator_component (id TEXT)")
        with self.assertRaisesRegex(SeriesIntelligenceMigrationError, "undeclared SQLite table"):
            validate_series_intelligence_database(path)

    def test_both_unique_indexes_reject_duplicates(self):
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        store.reserve(self.pending)
        con = self.connect()
        values = list(con.execute(f"SELECT * FROM {TABLE}").fetchone())
        for column, change in (("candidate_ref", "another-candidate"), ("identity_digest", "0" * 64)):
            with self.subTest(column=column):
                duplicate = values.copy()
                duplicate[COMMAND_COLUMNS.index("command_ref")] = "another-command"
                duplicate[COMMAND_COLUMNS.index(column)] = change
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute(f"INSERT INTO {TABLE} VALUES ({','.join('?' for _ in COMMAND_COLUMNS)})", duplicate)
                con.rollback()
        self.assertEqual(store.count(), 1)

    def test_row_candidate_state_and_source_corruption_are_detected_on_every_access(self):
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        store.reserve(self.pending)
        store.finish(self.pending, completed_command(self.pending))
        for column, value in (("row_digest", "0" * 64), ("candidate_json", "{}"), ("state", "RETRY"),
                              ("source_context_json", "{}"), ("failure_code", "provider_timeout"), ("version", 2)):
            with self.subTest(column=column):
                path = self.copy_database(column)
                with self.connect(path) as con:
                    con.execute(f"UPDATE {TABLE} SET {column}=?", (value,))
                with self.assertRaises(SeriesPlanCandidateCommandStorageError):
                    SqliteSeriesPlanCandidateCommandStore(path)
                with self.assertRaises(SeriesIntelligenceMigrationError):
                    validate_series_intelligence_database(path)

    def test_failed_reservation_is_not_overwritten_or_retried(self):
        store = SqliteSeriesPlanCandidateCommandStore(self.path)
        store.reserve(self.pending)
        failed = seal_record(replace(self.pending, state="FAILED", failureCode="provider_unavailable", completedAt=NOW))
        store.finish(self.pending, failed)
        before = self.path.read_bytes()
        self.assertEqual(store.reserve(self.pending), (failed, False))
        with self.assertRaises(SeriesPlanCandidateCommandStorageError):
            store.finish(self.pending, completed_command(self.pending))
        self.assertEqual(before, self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
