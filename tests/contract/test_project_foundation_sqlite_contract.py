import ast
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract
from apps.creator_workspace_mvp.project_foundation import (
    ProjectFoundationApplicationService,
)
from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    LifecycleOperation,
    migrate_lifecycle_database,
    validate_lifecycle_database,
)
from services.v5_core_os.project_engine.project_foundation_sqlite import (
    INDEX,
    MARKER_COMPONENT,
    MARKER_TABLE,
    SQLITE_COMPONENT_SCHEMA_VERSION,
    TABLE,
    SqliteProjectFoundationStore,
    index_statement,
    marker_statement,
    table_statement,
    validate_project_foundation_connection,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import (
    SqliteSeriesPlanCandidateReceiptStore,
)
from tests.unit.test_project_foundation import PROFILE, WORKSPACE, valid_command


ROOT = Path(__file__).resolve().parents[2]


class ProjectFoundationSqliteContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.counter = 0

    def path(self, name="foundation"):
        self.counter += 1
        return Path(self.directory.name) / f"{name}-{self.counter}.sqlite3"

    @staticmethod
    def connect(path):
        connection = sqlite3.connect(path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def base(self, name="foundation"):
        path = self.path(name)
        migrate_lifecycle_database(path, allow_upgrade=True)
        return path

    def completed(self, name="completed"):
        path = self.path(name)
        assembly = LifecycleAssembly.sqlite(path, initialize_or_upgrade=True)
        service = ProjectFoundationApplicationService(
            assembly.project_foundation_store,
            assembly.coordinator,
            assembly.series_episode,
            assembly.project_context,
        )
        service.execute(WORKSPACE, valid_command())
        return path

    def assert_validation_fails(self, path):
        with self.assertRaises(RuntimeError):
            validate_lifecycle_database(path)

    def test_optional_component_may_be_absent_or_exactly_complete(self):
        absent = self.base("absent")
        validate_lifecycle_database(absent)
        with self.connect(absent) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)
                ).fetchone()
            )

        complete = self.base("complete")
        SqliteProjectFoundationStore(complete)
        validate_lifecycle_database(complete)
        with self.connect(complete) as connection:
            validate_project_foundation_connection(connection)
            marker = connection.execute(
                f"SELECT component,schema_version FROM {MARKER_TABLE}"
            ).fetchone()
            self.assertEqual(
                (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
                tuple(marker),
            )
            for lifecycle_marker in (
                "v5_series_episode_schema",
                "v5_project_schema",
                "v5_script_studio_schema",
                "v5_series_planning_schema",
            ):
                self.assertEqual(
                    2,
                    connection.execute(
                        f"SELECT schema_version FROM {lifecycle_marker}"
                    ).fetchone()[0],
                )

    def test_every_partial_or_tampered_schema_fails_closed_without_repair(self):
        cases = {}

        marker_only = self.base("marker-only")
        with self.connect(marker_only) as connection:
            connection.execute(marker_statement())
            connection.execute(
                f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
                (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
            )
        cases["marker-only"] = marker_only

        table_only = self.base("table-only")
        with self.connect(table_only) as connection:
            connection.execute(table_statement())
        cases["table-only"] = table_only

        missing_index = self.base("missing-index")
        with self.connect(missing_index) as connection:
            connection.execute(table_statement())
            connection.execute(marker_statement())
            connection.execute(
                f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
                (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
            )
        cases["missing-index"] = missing_index

        wrong_ddl = self.base("wrong-ddl")
        with self.connect(wrong_ddl) as connection:
            connection.execute(
                table_statement().replace(
                    "updated_at TEXT NOT NULL",
                    "updated_at BLOB NOT NULL",
                )
            )
            connection.execute(index_statement())
            connection.execute(marker_statement())
            connection.execute(
                f"INSERT INTO {MARKER_TABLE} VALUES (?, ?)",
                (MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
            )
        cases["wrong-ddl"] = wrong_ddl

        wrong_marker = self.base("wrong-marker")
        SqliteProjectFoundationStore(wrong_marker)
        with self.connect(wrong_marker) as connection:
            connection.execute(
                f"UPDATE {MARKER_TABLE} SET schema_version=99"
            )
        cases["wrong-marker"] = wrong_marker

        extra_column = self.base("extra-column")
        SqliteProjectFoundationStore(extra_column)
        with self.connect(extra_column) as connection:
            connection.execute(f"ALTER TABLE {TABLE} ADD COLUMN extra TEXT")
        cases["extra-column"] = extra_column

        for name, path in cases.items():
            with self.subTest(case=name):
                before = path.read_bytes()
                self.assert_validation_fails(path)
                self.assertEqual(before, path.read_bytes())

    def test_every_corrupt_durable_record_fails_closed(self):
        mutations = {
            "malformed-request": ("request_json = ?", ("{",)),
            "request-digest-mismatch": ("request_digest = ?", ("0" * 64,)),
            "malformed-result": ("result_json = ?", ("{",)),
            "result-digest-mismatch": ("result_digest = ?", ("0" * 64,)),
            "invalid-state": ("state = ?", ("UNKNOWN",)),
        }
        duplicate_json = (
            '{"schemaVersion":"creator.project-foundation-command.v1",'
            '"schemaVersion":"creator.project-foundation-command.v1"}'
        )
        mutations["duplicate-request-key"] = (
            "request_json = ?, request_digest = ?",
            (duplicate_json, sha256(duplicate_json.encode()).hexdigest()),
        )
        nonstandard_json = (
            '{"contentProfileRef":"profile-project-foundation-unit",'
            '"episode":null,"project":{"aspectRatio":"16:9",'
            '"defaultDurationSec":NaN,"description":"A recoverable Project foundation",'
            '"plannedEpisodeCount":4,"projectType":"series",'
            '"targetPlatform":"streaming","title":"Wanlight Project"},'
            '"schemaVersion":"creator.project-foundation-command.v1",'
            '"series":{"description":"A recoverable Series foundation",'
            '"title":"Wanlight"}}'
        )
        mutations["nonstandard-number"] = (
            "request_json = ?, request_digest = ?",
            (nonstandard_json, sha256(nonstandard_json.encode()).hexdigest()),
        )

        for name, (assignment, parameters) in mutations.items():
            with self.subTest(case=name):
                path = self.completed(name)
                with self.connect(path) as connection:
                    connection.execute("PRAGMA ignore_check_constraints=ON")
                    connection.execute(
                        f"UPDATE {TABLE} SET {assignment}", parameters
                    )
                self.assert_validation_fails(path)

        path = self.completed("changed-result-ref")
        with self.connect(path) as connection:
            raw_result = connection.execute(
                f"SELECT result_json FROM {TABLE}"
            ).fetchone()[0]
            changed_result = json.loads(raw_result)
            changed_result["project"]["projectRef"] = "project-forged"
            changed_json = json.dumps(
                changed_result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            connection.execute(
                f"UPDATE {TABLE} SET result_json = ?, result_digest = ?",
                (changed_json, sha256(changed_json.encode()).hexdigest()),
            )
        self.assert_validation_fails(path)

    def test_unknown_table_index_view_and_trigger_remain_rejected(self):
        statements = {
            "table": "CREATE TABLE undeclared_component(value TEXT)",
            "index": f"CREATE INDEX undeclared_index ON {TABLE}(foundation_ref)",
            "view": f"CREATE VIEW undeclared_view AS SELECT * FROM {TABLE}",
            "trigger": (
                f"CREATE TRIGGER undeclared_trigger AFTER UPDATE ON {TABLE} "
                "BEGIN SELECT 1; END"
            ),
        }
        for name, statement in statements.items():
            with self.subTest(kind=name):
                path = self.base(name)
                SqliteProjectFoundationStore(path)
                with self.connect(path) as connection:
                    connection.execute(statement)
                self.assert_validation_fails(path)

    def test_foundation_coexists_with_candidate_and_all_existing_components(self):
        path = self.base("coexist")
        foundation_store = SqliteProjectFoundationStore(path)
        candidate_store = SqliteSeriesPlanCandidateReceiptStore(path)
        self.addCleanup(foundation_store.close)
        self.addCleanup(candidate_store.close)
        validate_lifecycle_database(path)
        with self.connect(path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn(TABLE, tables)
        self.assertIn("creator_series_plan_candidate_receipts", tables)
        self.assertIn("v5_script_acceptances", tables)
        self.assertIn("v5_canonical_registrations", tables)

    def test_phase_b_uses_one_lifecycle_lease_and_does_not_leak_connection(self):
        operations = []
        path = self.path("one-lease")
        assembly = LifecycleAssembly.sqlite(
            path,
            initialize_or_upgrade=True,
            transaction_hook=operations.append,
        )
        service = ProjectFoundationApplicationService(
            assembly.project_foundation_store,
            assembly.coordinator,
            assembly.series_episode,
            assembly.project_context,
        )
        service.execute(WORKSPACE, valid_command())
        self.assertEqual(
            [LifecycleOperation.CREATE_PROJECT_FOUNDATION], operations
        )
        self.assertIsNone(assembly.state.connection_or_none())
        service.execute(
            WORKSPACE,
            valid_command(key="subsequent-foundation"),
        )
        self.assertEqual(2, assembly.project_foundation_store.count(WORKSPACE))

    def test_public_resource_belongs_to_m4_and_has_no_internal_alias(self):
        self.assertEqual(
            "/creator/api/v1/project-foundations",
            public_contract.PUBLIC_PROJECT_FOUNDATIONS_ENDPOINT,
        )
        m4 = next(
            item for item in public_contract.CAPABILITY_PROJECTION if item["id"] == "M4"
        )
        self.assertIn("project-foundations", m4["publicResources"])

        server_source = (
            ROOT / "apps/creator_workspace_mvp/server.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('/creator/internal/project-foundations', server_source)

    def test_new_infrastructure_never_writes_v5_authority_or_imports_apps(self):
        new_sources = (
            ROOT / "services/v5_core_os/project_engine/project_foundation.py",
            ROOT / "services/v5_core_os/project_engine/project_foundation_sqlite.py",
        )
        for path in new_sources:
            source = path.read_text(encoding="utf-8")
            lowered = source.lower()
            for verb in ("insert into v5_", "update v5_", "delete from v5_"):
                with self.subTest(path=path.name, verb=verb):
                    self.assertNotIn(verb, lowered)
            tree = ast.parse(source, filename=str(path))
            imports = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            self.assertFalse(any(name.startswith("apps.") for name in imports))


if __name__ == "__main__":
    unittest.main()
