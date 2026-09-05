import copy
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp.series_plan_candidate_receipts import (
    CANDIDATE_RECEIPT_SCHEMA_VERSION,
    SOURCE_CONTEXT_SCHEMA_VERSION,
    SQLITE_MARKER_TABLE,
    SQLITE_RECEIPT_TABLE,
    InMemorySeriesPlanCandidateReceiptStore,
    SeriesPlanCandidateReceiptError,
    SeriesPlanCandidateReceiptService,
    SqliteSeriesPlanCandidateReceiptStore,
    build_series_plan_candidate_context,
    canonical_json_digest,
    create_local_development_receipt_service,
    create_local_development_receipt_service_from_environment,
)
from services.v5_core_os.series_planning.candidate_receipt_sqlite import (
    INDEX as SQLITE_RECEIPT_INDEX,
    MARKER_COMPONENT as SQLITE_MARKER_COMPONENT,
    SQLITE_COMPONENT_SCHEMA_VERSION,
    CandidateReceiptSqliteError,
    index_statement as receipt_index_statement,
    marker_statement as receipt_marker_statement,
    table_statement as receipt_table_statement,
)
from services.v5_core_os.series_intelligence.migration import (
    SeriesIntelligenceMigrationError,
    validate_series_intelligence_database,
)
from services.v5_core_os.script_studio.acceptance_sqlite import (
    INDEX as SCRIPT_ACCEPTANCE_INDEX,
    MARKER_TABLE as SCRIPT_ACCEPTANCE_MARKER_TABLE,
    TABLE as SCRIPT_ACCEPTANCE_TABLE,
)
from services.v5_core_os.canonical_registration.sqlite_schema import (
    INDEX as CANONICAL_REGISTRATION_INDEX,
    MARKER_TABLE as CANONICAL_REGISTRATION_MARKER_TABLE,
    TABLE as CANONICAL_REGISTRATION_TABLE,
)
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from tests.unit.test_series_planning_m5 import valid_candidate


WORKSPACE = "workspace-receipt-unit"
PROFILE = "profile-receipt-unit"


def create_scope(assembly: LifecycleAssembly, suffix: str = "A"):
    series = assembly.series_episode.create_series(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "title": f"Series {suffix}",
            "description": f"Series description {suffix}",
            "plannedEpisodeCount": 4,
        }
    )
    project = assembly.project_context.create_project(
        {
            "workspaceRef": WORKSPACE,
            "contentProfileRef": PROFILE,
            "projectType": "series",
            "seriesRef": series["seriesRef"],
            "title": f"Project {suffix}",
            "description": f"Project description {suffix}",
            "targetPlatform": "streaming",
            "aspectRatio": "16:9",
            "plannedEpisodeCount": 4,
        }
    )
    trusted = assembly.project_context.build_context(
        WORKSPACE, project["projectRef"], series["seriesRef"]
    )
    return series, project, build_series_plan_candidate_context(trusted)


class CandidateReceiptServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assembly = LifecycleAssembly.in_memory()
        self.series_a, self.project_a, self.context_a = create_scope(
            self.assembly, "A"
        )
        self.series_b, self.project_b, self.context_b = create_scope(
            self.assembly, "B"
        )
        self.store = InMemorySeriesPlanCandidateReceiptStore()
        self.service = SeriesPlanCandidateReceiptService(
            self.store,
            ref_factory=lambda prefix: f"{prefix}-server-only",
            clock=lambda: "2026-09-05T00:00:00.000Z",
        )

    def assert_receipt_error(self, code, operation, status=409):
        with self.assertRaises(SeriesPlanCandidateReceiptError) as caught:
            operation()
        self.assertEqual((code, status), (caught.exception.code, caught.exception.status))

    def test_issue_binds_trusted_context_and_persists_only_creative_input_digest(self):
        creative_input = "raw secret creative direction"
        receipt, replay = self.service.issue(
            self.context_a, creative_input, valid_candidate()
        )
        source = self.context_a["sourceContext"]
        self.assertFalse(replay)
        self.assertEqual(CANDIDATE_RECEIPT_SCHEMA_VERSION, receipt.schemaVersion)
        self.assertEqual(SOURCE_CONTEXT_SCHEMA_VERSION, source["schemaVersion"])
        self.assertEqual("series-plan-candidate-server-only", receipt.candidateRef)
        self.assertEqual(self.project_a["projectRef"], receipt.projectRef)
        self.assertEqual(self.series_a["seriesRef"], receipt.seriesRef)
        self.assertEqual(self.project_a["version"], receipt.sourceProjectVersion)
        self.assertEqual(self.series_a["version"], receipt.sourceSeriesVersion)
        self.assertEqual(canonical_json_digest(source), receipt.sourceContextDigest)
        self.assertEqual(
            source,
            json.loads(receipt.sourceContextJson),
        )
        self.assertEqual(
            sha256(creative_input.encode("utf-8")).hexdigest(),
            receipt.creativeInputDigest,
        )
        self.assertEqual(canonical_json_digest(valid_candidate()), receipt.candidateDigest)
        self.assertNotIn(creative_input, receipt.candidateJson)
        self.assertEqual(1, self.store.count())

    def test_repeated_issue_reuses_receipt_and_both_confirmation_shapes_resolve(self):
        receipt, first_replay = self.service.issue(
            self.context_a, "first input", valid_candidate()
        )
        repeated, second_replay = self.service.issue(
            self.context_a, "different input", valid_candidate()
        )
        self.assertFalse(first_replay)
        self.assertTrue(second_replay)
        self.assertEqual(receipt, repeated)
        self.assertEqual(1, self.store.count())
        self.assertEqual(
            valid_candidate(),
            self.service.resolve(
                self.context_a,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )
        self.assertEqual(
            valid_candidate(),
            self.service.resolve(self.context_a, valid_candidate()),
        )

    def test_unissued_cross_scope_changed_and_stale_candidates_fail_closed(self):
        receipt, _ = self.service.issue(
            self.context_a, "Series A direction", valid_candidate()
        )
        self.assert_receipt_error(
            "series_plan_candidate_not_issued",
            lambda: self.service.resolve(self.context_b, valid_candidate()),
        )
        self.assert_receipt_error(
            "series_plan_candidate_scope_mismatch",
            lambda: self.service.resolve(
                self.context_b,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )
        cross_project = copy.deepcopy(self.context_a)
        cross_project["generationContext"]["projectRef"] = "project-foreign"
        cross_project["sourceContext"]["projectRef"] = "project-foreign"
        self.assert_receipt_error(
            "series_plan_candidate_scope_mismatch",
            lambda: self.service.resolve(
                cross_project,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )
        cross_series = copy.deepcopy(self.context_a)
        cross_series["generationContext"]["seriesRef"] = "series-foreign"
        cross_series["sourceContext"]["seriesRef"] = "series-foreign"
        self.assert_receipt_error(
            "series_plan_candidate_scope_mismatch",
            lambda: self.service.resolve(
                cross_series,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )
        foreign_workspace = copy.deepcopy(self.context_a)
        foreign_workspace["generationContext"]["workspaceRef"] = (
            "workspace-foreign"
        )
        foreign_workspace["sourceContext"]["workspaceRef"] = (
            "workspace-foreign"
        )
        self.assert_receipt_error(
            "series_plan_candidate_not_issued",
            lambda: self.service.resolve(
                foreign_workspace,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )
        changed = valid_candidate()
        changed["premise"] = "Changed after issuance."
        self.assert_receipt_error(
            "series_plan_candidate_content_mismatch",
            lambda: self.service.resolve(
                self.context_a, changed, candidate_ref=receipt.candidateRef
            ),
        )
        self.assert_receipt_error(
            "series_plan_candidate_not_issued",
            lambda: self.service.resolve(
                self.context_a,
                valid_candidate(),
                candidate_ref="series-plan-candidate-unknown",
            ),
        )
        stale = copy.deepcopy(self.context_a)
        stale["sourceContext"]["projectVersion"] += 1
        self.assert_receipt_error(
            "series_plan_candidate_stale",
            lambda: self.service.resolve(
                stale, valid_candidate(), candidate_ref=receipt.candidateRef
            ),
        )
        stale_series = copy.deepcopy(self.context_a)
        stale_series["sourceContext"]["seriesVersion"] += 1
        self.assert_receipt_error(
            "series_plan_candidate_stale",
            lambda: self.service.resolve(
                stale_series,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            ),
        )

    def test_generation_context_drift_is_bound_even_without_version_change(self):
        receipt, _ = self.service.issue(
            self.context_a, "Series A direction", valid_candidate()
        )
        drifted = copy.deepcopy(self.context_a)
        drifted["generationContext"]["projectTitle"] = "Changed title"
        drifted["sourceContext"]["projectTitle"] = "Changed title"
        self.assert_receipt_error(
            "series_plan_candidate_stale",
            lambda: self.service.resolve(
                drifted, valid_candidate(), candidate_ref=receipt.candidateRef
            ),
        )

    def test_ambiguous_compatibility_lookup_and_store_failure_are_stable(self):
        class AmbiguousStore(InMemorySeriesPlanCandidateReceiptStore):
            def find_exact(self, *args):
                matches = super().find_exact(*args)
                return matches + matches

        ambiguous_store = AmbiguousStore()
        ambiguous = SeriesPlanCandidateReceiptService(
            ambiguous_store,
            ref_factory=lambda prefix: f"{prefix}-ambiguous",
        )
        ambiguous.issue(self.context_a, "direction", valid_candidate())
        self.assert_receipt_error(
            "series_plan_candidate_receipt_ambiguous",
            lambda: ambiguous.resolve(self.context_a, valid_candidate()),
        )

        class FailingStore(InMemorySeriesPlanCandidateReceiptStore):
            def issue(self, receipt):
                raise RuntimeError("storage failed")

        failing = SeriesPlanCandidateReceiptService(FailingStore())
        self.assert_receipt_error(
            "series_plan_candidate_receipt_unavailable",
            lambda: failing.issue(self.context_a, "direction", valid_candidate()),
            status=503,
        )


class CandidateReceiptSqliteTests(unittest.TestCase):
    @staticmethod
    def core_row_counts(path: Path):
        with sqlite3.connect(path) as connection:
            tables = [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name LIKE 'v5_%' ORDER BY name"
                )
            ]
            return {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in tables
            }

    def test_receipt_survives_restart_without_changing_lifecycle_or_v5_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            assembly = LifecycleAssembly.sqlite(
                path, initialize_or_upgrade=True
            )
            series, project, context = create_scope(assembly)
            before = self.core_row_counts(path)
            service = create_local_development_receipt_service(path)
            raw_input = "do not persist this raw creative input"
            receipt, replay = service.issue(context, raw_input, valid_candidate())
            self.assertFalse(replay)
            self.assertEqual(before, self.core_row_counts(path))

            with sqlite3.connect(path) as connection:
                lifecycle_version = connection.execute(
                    "SELECT schema_version FROM v5_series_planning_schema "
                    "WHERE component='series_planning'"
                ).fetchone()[0]
                marker = connection.execute(
                    f"SELECT component, schema_version FROM {SQLITE_MARKER_TABLE}"
                ).fetchone()
                row = connection.execute(
                    f"SELECT * FROM {SQLITE_RECEIPT_TABLE}"
                ).fetchone()
            self.assertEqual(2, lifecycle_version)
            self.assertEqual(("series_plan_candidate_receipts", 1), marker)
            self.assertNotIn(raw_input, "|".join(str(value) for value in row))

            restarted_assembly = LifecycleAssembly.sqlite(path)
            restarted_service = create_local_development_receipt_service(path)
            restarted_context = build_series_plan_candidate_context(
                restarted_assembly.project_context.build_context(
                    WORKSPACE, project["projectRef"], series["seriesRef"]
                )
            )
            stored = restarted_service.resolve(
                restarted_context,
                valid_candidate(),
                candidate_ref=receipt.candidateRef,
            )
            confirmed = restarted_assembly.series_planning.confirm_candidate(
                {
                    "workspaceRef": WORKSPACE,
                    "projectRef": project["projectRef"],
                    "seriesRef": series["seriesRef"],
                    "humanConfirmed": True,
                    "candidate": stored,
                }
            )
            self.assertEqual(
                confirmed["plan"]["confirmedSeriesPlanVersionRef"],
                confirmed["version"]["seriesPlanVersionRef"],
            )

    def test_environment_factory_uses_the_shared_creator_data_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            LifecycleAssembly.sqlite(path, initialize_or_upgrade=True)
            service = create_local_development_receipt_service_from_environment(
                {"CREATOR_DATA_PATH": str(path)}
            )
            self.assertEqual(path.resolve(), service.store.database_path)

    def test_digest_and_candidate_json_tampering_fail_closed(self):
        for column, value in (
            ("candidate_digest", "0" * 64),
            ("candidate_json", "{}"),
        ):
            with self.subTest(column=column), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "creator.sqlite3"
                assembly = LifecycleAssembly.sqlite(
                    path, initialize_or_upgrade=True
                )
                _, _, context = create_scope(assembly)
                service = create_local_development_receipt_service(path)
                receipt, _ = service.issue(
                    context, "tamper test", valid_candidate()
                )
                with sqlite3.connect(path) as connection:
                    connection.execute(
                        f"UPDATE {SQLITE_RECEIPT_TABLE} SET {column} = ? "
                        "WHERE workspace_ref = ? AND candidate_ref = ?",
                        (value, WORKSPACE, receipt.candidateRef),
                    )
                with self.assertRaises(SeriesPlanCandidateReceiptError) as caught:
                    service.resolve(
                        context,
                        valid_candidate(),
                        candidate_ref=receipt.candidateRef,
                    )
                self.assertEqual(
                    (
                        "series_plan_candidate_receipt_unavailable",
                        503,
                    ),
                    (caught.exception.code, caught.exception.status),
                )

    def test_partial_application_receipt_schema_is_not_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    f"CREATE TABLE {SQLITE_MARKER_TABLE} ("
                    "component TEXT PRIMARY KEY, schema_version INTEGER NOT NULL)"
                )
            with self.assertRaises(CandidateReceiptSqliteError) as caught:
                SqliteSeriesPlanCandidateReceiptStore(path)
            self.assertEqual("partial candidate receipt schema", str(caught.exception))
            with sqlite3.connect(path) as connection:
                receipt_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (SQLITE_RECEIPT_TABLE,),
                ).fetchone()
            self.assertIsNone(receipt_table)

    def test_schema_creation_failure_rolls_back_table_and_index_before_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    f"CREATE VIEW {SQLITE_MARKER_TABLE} AS SELECT 1 AS value"
                )
            with self.assertRaises(CandidateReceiptSqliteError):
                SqliteSeriesPlanCandidateReceiptStore(path)
            with sqlite3.connect(path) as connection:
                objects = connection.execute(
                    "SELECT type, name FROM sqlite_master "
                    "WHERE name IN (?, ?, ?) ORDER BY type, name",
                    (
                        SQLITE_MARKER_TABLE,
                        SQLITE_RECEIPT_TABLE,
                        SQLITE_RECEIPT_INDEX,
                    ),
                ).fetchall()
            self.assertEqual([("view", SQLITE_MARKER_TABLE)], objects)


class CandidateReceiptSchemaRegistrationTests(unittest.TestCase):
    @staticmethod
    def _new_database(path: Path) -> None:
        LifecycleAssembly.sqlite(path, initialize_or_upgrade=True)

    @staticmethod
    def _drop_optional_components(
        path: Path,
        *,
        keep_script_acceptance: bool,
        keep_canonical_registration: bool,
    ) -> None:
        if keep_canonical_registration and not keep_script_acceptance:
            raise AssertionError(
                "canonical registration requires Script Acceptance"
            )
        with sqlite3.connect(path) as connection:
            if not keep_canonical_registration:
                connection.execute(
                    f"DROP INDEX IF EXISTS {CANONICAL_REGISTRATION_INDEX}"
                )
                connection.execute(
                    f"DROP TABLE IF EXISTS {CANONICAL_REGISTRATION_TABLE}"
                )
                connection.execute(
                    f"DROP TABLE IF EXISTS {CANONICAL_REGISTRATION_MARKER_TABLE}"
                )
            if not keep_script_acceptance:
                connection.execute(
                    f"DROP INDEX IF EXISTS {SCRIPT_ACCEPTANCE_INDEX}"
                )
                connection.execute(
                    f"DROP TABLE IF EXISTS {SCRIPT_ACCEPTANCE_TABLE}"
                )
                connection.execute(
                    f"DROP TABLE IF EXISTS {SCRIPT_ACCEPTANCE_MARKER_TABLE}"
                )

    @staticmethod
    def _install_empty_receipt_schema(
        path: Path,
        *,
        table_sql: str | None = None,
        index_sql: str | None = None,
        marker_version: int = SQLITE_COMPONENT_SCHEMA_VERSION,
    ) -> None:
        with sqlite3.connect(path) as connection:
            connection.execute(table_sql or receipt_table_statement())
            connection.execute(index_sql or receipt_index_statement())
            connection.execute(receipt_marker_statement())
            connection.execute(
                f"INSERT INTO {SQLITE_MARKER_TABLE} VALUES (?, ?)",
                (SQLITE_MARKER_COMPONENT, marker_version),
            )

    def _base_without_optionals(self, directory: str, name: str) -> Path:
        path = Path(directory) / f"{name}.sqlite3"
        self._new_database(path)
        self._drop_optional_components(
            path,
            keep_script_acceptance=False,
            keep_canonical_registration=False,
        )
        return path

    def _assert_invalid(self, path: Path) -> None:
        with self.assertRaises(SeriesIntelligenceMigrationError):
            validate_series_intelligence_database(path)

    def _issued_receipt(self, directory: str, name: str):
        path = Path(directory) / f"{name}.sqlite3"
        self._new_database(path)
        assembly = LifecycleAssembly.sqlite(path)
        _, _, context = create_scope(assembly, name)
        service = create_local_development_receipt_service(path)
        receipt, _ = service.issue(
            context,
            "raw creative input must remain digest-only",
            valid_candidate(),
        )
        return path, receipt

    def test_all_supported_optional_component_combinations_validate(self):
        configurations = (
            ("none", False, False),
            ("script-acceptance", True, False),
            ("script-and-canonical", True, True),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, keep_script, keep_canonical in configurations:
                with self.subTest(receipt=False, configuration=name):
                    path = Path(directory) / f"without-receipt-{name}.sqlite3"
                    self._new_database(path)
                    self._drop_optional_components(
                        path,
                        keep_script_acceptance=keep_script,
                        keep_canonical_registration=keep_canonical,
                    )
                    validate_series_intelligence_database(path)

                with self.subTest(receipt=True, configuration=name):
                    path = Path(directory) / f"with-receipt-{name}.sqlite3"
                    self._new_database(path)
                    self._drop_optional_components(
                        path,
                        keep_script_acceptance=keep_script,
                        keep_canonical_registration=keep_canonical,
                    )
                    SqliteSeriesPlanCandidateReceiptStore(path)
                    validate_series_intelligence_database(path)

    def test_partial_receipt_schema_states_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            table_only = self._base_without_optionals(directory, "table-only")
            with sqlite3.connect(table_only) as connection:
                connection.execute(receipt_table_statement())
            self._assert_invalid(table_only)

            marker_only = self._base_without_optionals(directory, "marker-only")
            with sqlite3.connect(marker_only) as connection:
                connection.execute(receipt_marker_statement())
                connection.execute(
                    f"INSERT INTO {SQLITE_MARKER_TABLE} VALUES (?, ?)",
                    (SQLITE_MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
                )
            self._assert_invalid(marker_only)

            missing_index = self._base_without_optionals(
                directory, "missing-index"
            )
            with sqlite3.connect(missing_index) as connection:
                connection.execute(receipt_table_statement())
                connection.execute(receipt_marker_statement())
                connection.execute(
                    f"INSERT INTO {SQLITE_MARKER_TABLE} VALUES (?, ?)",
                    (SQLITE_MARKER_COMPONENT, SQLITE_COMPONENT_SCHEMA_VERSION),
                )
            self._assert_invalid(missing_index)

    def test_receipt_ddl_columns_index_and_marker_are_exact(self):
        cases = {
            "modified-ddl": receipt_table_statement().replace(
                "created_at TEXT NOT NULL, ",
                "created_at TEXT NOT NULL CHECK(length(created_at) > 0), ",
            ),
            "extra-column": receipt_table_statement().replace(
                "version INTEGER NOT NULL, PRIMARY KEY",
                "version INTEGER NOT NULL, unexpected TEXT, PRIMARY KEY",
            ),
            "missing-column": receipt_table_statement().replace(
                "creative_input_digest TEXT NOT NULL, ", ""
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for name, table_sql in cases.items():
                with self.subTest(case=name):
                    path = self._base_without_optionals(directory, name)
                    self._install_empty_receipt_schema(
                        path, table_sql=table_sql
                    )
                    self._assert_invalid(path)

            wrong_index = self._base_without_optionals(
                directory, "wrong-index"
            )
            self._install_empty_receipt_schema(
                wrong_index,
                index_sql=(
                    f"CREATE UNIQUE INDEX {SQLITE_RECEIPT_INDEX} "
                    f"ON {SQLITE_RECEIPT_TABLE}(workspace_ref, candidate_ref)"
                ),
            )
            self._assert_invalid(wrong_index)

            wrong_marker = self._base_without_optionals(
                directory, "wrong-marker-version"
            )
            self._install_empty_receipt_schema(
                wrong_marker,
                marker_version=SQLITE_COMPONENT_SCHEMA_VERSION + 1,
            )
            self._assert_invalid(wrong_marker)

            extra_marker = self._base_without_optionals(
                directory, "extra-marker"
            )
            self._install_empty_receipt_schema(extra_marker)
            with sqlite3.connect(extra_marker) as connection:
                connection.execute(
                    f"INSERT INTO {SQLITE_MARKER_TABLE} VALUES (?, ?)",
                    ("unexpected_component", 1),
                )
            self._assert_invalid(extra_marker)

    def test_durable_receipt_digest_json_and_raw_input_tampering_fail(self):
        mutations = {}

        def candidate_digest(connection, receipt):
            connection.execute(
                f"UPDATE {SQLITE_RECEIPT_TABLE} SET candidate_digest = ? "
                "WHERE candidate_ref = ?",
                ("0" * 64, receipt.candidateRef),
            )

        mutations["candidate-digest"] = candidate_digest

        def source_digest(connection, receipt):
            connection.execute(
                f"UPDATE {SQLITE_RECEIPT_TABLE} SET source_context_digest = ? "
                "WHERE candidate_ref = ?",
                ("0" * 64, receipt.candidateRef),
            )

        mutations["source-context-digest"] = source_digest

        def candidate_json(connection, receipt):
            malformed = "{"
            connection.execute(
                f"UPDATE {SQLITE_RECEIPT_TABLE} "
                "SET candidate_json = ?, candidate_digest = ? "
                "WHERE candidate_ref = ?",
                (
                    malformed,
                    sha256(malformed.encode("utf-8")).hexdigest(),
                    receipt.candidateRef,
                ),
            )

        mutations["malformed-json"] = candidate_json

        def noncanonical_json(connection, receipt):
            value = json.dumps(valid_candidate(), ensure_ascii=False, indent=2)
            connection.execute(
                f"UPDATE {SQLITE_RECEIPT_TABLE} "
                "SET candidate_json = ?, candidate_digest = ? "
                "WHERE candidate_ref = ?",
                (
                    value,
                    sha256(value.encode("utf-8")).hexdigest(),
                    receipt.candidateRef,
                ),
            )

        mutations["noncanonical-json"] = noncanonical_json

        def raw_input(connection, receipt):
            value = valid_candidate()
            value["creativeInput"] = "raw creative input must not persist"
            serialized = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            connection.execute(
                f"UPDATE {SQLITE_RECEIPT_TABLE} "
                "SET candidate_json = ?, candidate_digest = ? "
                "WHERE candidate_ref = ?",
                (
                    serialized,
                    sha256(serialized.encode("utf-8")).hexdigest(),
                    receipt.candidateRef,
                ),
            )

        mutations["raw-creative-input"] = raw_input

        for constant in ("NaN", "Infinity"):
            def nonstandard_number(connection, receipt, value=constant):
                serialized = (
                    '{"schemaVersion":"creator.series-plan.candidate.v1",'
                    f'"unexpected":{value}' + "}"
                )
                connection.execute(
                    f"UPDATE {SQLITE_RECEIPT_TABLE} "
                    "SET candidate_json = ?, candidate_digest = ? "
                    "WHERE candidate_ref = ?",
                    (
                        serialized,
                        sha256(serialized.encode("utf-8")).hexdigest(),
                        receipt.candidateRef,
                    ),
                )

            mutations[f"nonstandard-{constant.lower()}"] = nonstandard_number

        with tempfile.TemporaryDirectory() as directory:
            for name, mutate in mutations.items():
                with self.subTest(case=name):
                    path, receipt = self._issued_receipt(directory, name)
                    with sqlite3.connect(path) as connection:
                        mutate(connection, receipt)
                    self._assert_invalid(path)

    def test_unknown_tables_indexes_views_and_triggers_remain_rejected(self):
        statements = {
            "table": "CREATE TABLE fourth_party_table (value TEXT)",
            "index": "CREATE INDEX fourth_party_index ON v5_series(title)",
            "view": "CREATE VIEW fourth_party_view AS SELECT * FROM v5_series",
            "trigger": (
                "CREATE TRIGGER fourth_party_trigger AFTER INSERT ON v5_series "
                "BEGIN SELECT 1; END"
            ),
        }
        with tempfile.TemporaryDirectory() as directory:
            for kind, statement in statements.items():
                with self.subTest(kind=kind):
                    path = Path(directory) / f"unknown-{kind}.sqlite3"
                    self._new_database(path)
                    with sqlite3.connect(path) as connection:
                        connection.execute(statement)
                    self._assert_invalid(path)

    def test_complete_receipt_schema_preserves_foreign_key_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self._issued_receipt(directory, "foreign-keys")
            validate_series_intelligence_database(path)
            with sqlite3.connect(path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                self.assertEqual(1, connection.execute(
                    "PRAGMA foreign_keys"
                ).fetchone()[0])
                self.assertEqual(
                    [], connection.execute("PRAGMA foreign_key_check").fetchall()
                )


if __name__ == "__main__":
    unittest.main()
