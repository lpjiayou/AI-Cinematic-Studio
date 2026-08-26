import ast
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

from services.v5_core_os.lifecycle_integrity import (
    LifecycleAssembly,
    migrate_lifecycle_database,
    validate_lifecycle_database,
)
from services.v5_core_os.series_intelligence import M6Scope
from services.v5_core_os.series_intelligence.migration import (
    migrate_series_intelligence_database,
    validate_series_intelligence_database,
)
from services.v5_core_os.series_intelligence.public import (
    SeriesIntelligencePublicBoundary,
    SeriesIntelligencePublicError,
)


ROOT = Path(__file__).resolve().parents[2]
COMPLETE_SCOPE_COLUMNS = {
    "business_domain",
    "tenant_id",
    "workspace_ref",
    "project_ref",
    "series_ref",
}
M6_TABLES = {
    "v5_m6_series_bibles",
    "v5_m6_series_bible_versions",
    "v5_m6_character_continuities",
    "v5_m6_character_continuity_versions",
    "v5_m6_baseline_snapshots",
    "v5_m6_operations",
    "v5_m6_outbox",
}


class ScopeAuthority:
    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope(
            "series-production",
            "tenant-contract",
            workspace_ref,
            project_ref,
            series_ref,
        )


def open_fk(path):
    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


class SeriesIntelligenceSqliteContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "m6-contract.sqlite3"
        migrate_lifecycle_database(self.path, allow_upgrade=True)
        migrate_series_intelligence_database(self.path)

    def test_domain_and_public_boundary_remain_sqlite_neutral(self):
        neutral_files = (
            "canonical.py",
            "contracts.py",
            "errors.py",
            "foundation.py",
            "public.py",
        )
        module = ROOT / "services/v5_core_os/series_intelligence"
        for name in neutral_files:
            path = module / name
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            with self.subTest(path=name):
                self.assertNotIn("sqlite3", imports)

    def test_sqlite_assembly_exposes_the_same_bounded_m6_boundary(self):
        assembly = LifecycleAssembly.sqlite(
            self.path,
            m6_scope_authority=ScopeAuthority(),
        )
        self.assertIsInstance(
            assembly.series_intelligence, SeriesIntelligencePublicBoundary
        )
        for method in (
            "create_bible_version",
            "submit_bible_candidate",
            "confirm_bible_version",
            "create_character_version",
            "submit_character_candidate",
            "confirm_character_version",
            "activate_baseline",
            "get_workspace",
            "get_outbox",
        ):
            with self.subTest(method=method):
                self.assertTrue(callable(getattr(assembly.series_intelligence, method)))

    def test_sqlite_default_authorities_fail_closed(self):
        assembly = LifecycleAssembly.sqlite(self.path)
        with self.assertRaises(SeriesIntelligencePublicError) as error:
            assembly.series_intelligence.get_workspace("workspace", "project", "series")
        self.assertEqual(
            (error.exception.code, error.exception.status),
            ("authority_unavailable", 403),
        )
        with self.assertRaises(SeriesIntelligencePublicError) as unscoped:
            assembly.series_intelligence.get_outbox()
        self.assertEqual(
            (unscoped.exception.code, unscoped.exception.status),
            ("invalid_request", 400),
        )

    def test_every_m6_table_carries_the_complete_scope(self):
        connection = open_fk(self.path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertTrue(M6_TABLES.issubset(tables))
            for table in sorted(M6_TABLES):
                columns = {
                    row["name"]
                    for row in connection.execute(f"PRAGMA table_info({table})")
                }
                with self.subTest(table=table):
                    self.assertTrue(COMPLETE_SCOPE_COLUMNS.issubset(columns))
        finally:
            connection.close()

    def test_every_complete_scope_column_is_database_constrained_nonempty(self):
        connection = open_fk(self.path)
        try:
            for table in sorted(M6_TABLES):
                schema = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()[0]
                normalized = re.sub(r"\s+", "", str(schema).lower())
                for column in sorted(COMPLETE_SCOPE_COLUMNS):
                    accepted_checks = (
                        f"check(length(trim({column}))>0)",
                        f"check(trim({column})<>'')",
                        f"check({column}<>'')",
                        f"check(length({column})>0)",
                    )
                    with self.subTest(table=table, column=column):
                        self.assertTrue(
                            any(item in normalized for item in accepted_checks),
                            f"{table}.{column} has no non-empty CHECK constraint",
                        )
        finally:
            connection.close()

    def test_m6_marker_is_additive_and_lifecycle_markers_remain_v2(self):
        connection = open_fk(self.path)
        try:
            row = connection.execute(
                "SELECT component, schema_version "
                "FROM v5_series_intelligence_schema"
            ).fetchone()
            self.assertEqual(tuple(row), ("series_intelligence", 1))
            for marker in (
                "v5_series_episode_schema",
                "v5_project_schema",
                "v5_script_studio_schema",
                "v5_series_planning_schema",
            ):
                with self.subTest(marker=marker):
                    self.assertEqual(
                        connection.execute(
                            f"SELECT schema_version FROM {marker}"
                        ).fetchone()[0],
                        2,
                    )
        finally:
            connection.close()

    def test_b1_reuses_exact_sqlite_schema_and_existing_content_json(self):
        connection = open_fk(self.path)
        try:
            objects = [
                tuple(row)
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                )
            ]
            columns = tuple(
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(v5_series_plan_versions)"
                )
            )
        finally:
            connection.close()
        schema_bytes = json.dumps(objects, separators=(",", ":")).encode("utf-8")
        self.assertEqual(len(objects), 35)
        self.assertEqual(
            hashlib.sha256(schema_bytes).hexdigest(),
            "13eb56af5e0f5f2bb1cb187ff9d00ce3cd16136b2798a34ed11bfda76a4361d2",
        )
        self.assertIn("schema_version", columns)
        self.assertIn("content_json", columns)
        self.assertNotIn("episode_plan_item_bindings", columns)

    def test_all_marker_constraint_tampering_fails_closed_without_repair(self):
        markers = {
            "v5_series_episode_schema": ("series_episode", 2),
            "v5_project_schema": ("project_context", 2),
            "v5_script_studio_schema": ("script_studio", 2),
            "v5_series_planning_schema": ("series_planning", 2),
            "v5_series_intelligence_schema": ("series_intelligence", 1),
            "v5_script_acceptance_schema": ("script_acceptance", 1),
            "v5_canonical_registration_schema": (
                "canonical_registration",
                1,
            ),
        }
        for marker, (component, version) in markers.items():
            with self.subTest(marker=marker):
                path = Path(self.temp.name) / f"tampered-{marker}.sqlite3"
                migrate_lifecycle_database(path, allow_upgrade=True)
                connection = open_fk(path)
                try:
                    connection.execute(f"DROP TABLE {marker}")
                    connection.execute(
                        f"CREATE TABLE {marker} (component TEXT, schema_version INTEGER)"
                    )
                    connection.execute(
                        f"INSERT INTO {marker} VALUES (?, ?)",
                        (component, version),
                    )
                    before_sql = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (marker,),
                    ).fetchone()[0]
                    before_rows = connection.execute(
                        f"SELECT component, schema_version FROM {marker}"
                    ).fetchall()
                finally:
                    connection.close()

                for validator in (
                    validate_lifecycle_database,
                    validate_series_intelligence_database,
                ):
                    with self.subTest(marker=marker, validator=validator.__name__):
                        with self.assertRaises(RuntimeError):
                            validator(path)
                with self.assertRaises(RuntimeError):
                    migrate_lifecycle_database(path, allow_upgrade=True)

                connection = open_fk(path)
                try:
                    after_sql = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (marker,),
                    ).fetchone()[0]
                    after_rows = connection.execute(
                        f"SELECT component, schema_version FROM {marker}"
                    ).fetchall()
                    self.assertEqual(after_sql, before_sql)
                    self.assertEqual(
                        [tuple(row) for row in after_rows],
                        [tuple(row) for row in before_rows],
                    )
                finally:
                    connection.close()

    def test_schema_freezes_composite_m5_parent_and_restrictive_lineage(self):
        connection = open_fk(self.path)
        try:
            indexes = connection.execute(
                "PRAGMA index_list(v5_series_plan_versions)"
            ).fetchall()
            unique_column_sets = []
            for index in indexes:
                if index["unique"]:
                    unique_column_sets.append(
                        tuple(
                            row["name"]
                            for row in connection.execute(
                                f"PRAGMA index_info({index['name']})"
                            )
                        )
                    )
            self.assertIn(
                (
                    "workspace_ref",
                    "project_ref",
                    "series_ref",
                    "series_plan_ref",
                    "series_plan_version_ref",
                ),
                unique_column_sets,
            )

            for table in (
                "v5_m6_series_bible_versions",
                "v5_m6_character_continuity_versions",
                "v5_m6_baseline_snapshots",
            ):
                foreign_keys = connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
                with self.subTest(table=table):
                    self.assertTrue(foreign_keys)
                    self.assertTrue(
                        all(row["on_delete"].upper() in {"RESTRICT", "NO ACTION"}
                            for row in foreign_keys)
                    )
                    self.assertTrue(
                        all(row["on_delete"].upper() != "CASCADE"
                            for row in foreign_keys)
                    )
        finally:
            connection.close()

    def test_version_root_and_parent_lineage_are_exact_full_scope_foreign_keys(self):
        connection = open_fk(self.path)
        try:
            def groups(table):
                result = {}
                for row in connection.execute(f"PRAGMA foreign_key_list({table})"):
                    group = result.setdefault(
                        row["id"],
                        {
                            "table": row["table"],
                            "from": [],
                            "to": [],
                            "on_delete": row["on_delete"].upper(),
                        },
                    )
                    group["from"].append((row["seq"], row["from"]))
                    group["to"].append((row["seq"], row["to"]))
                return {
                    (
                        group["table"],
                        tuple(item for _seq, item in sorted(group["from"])),
                        tuple(item for _seq, item in sorted(group["to"])),
                        group["on_delete"],
                    )
                    for group in result.values()
                }

            scope = (
                "business_domain",
                "tenant_id",
                "workspace_ref",
                "project_ref",
                "series_ref",
            )
            cases = (
                (
                    "v5_m6_series_bible_versions",
                    "v5_m6_series_bibles",
                    (*scope, "series_bible_ref"),
                    (*scope, "series_bible_ref"),
                ),
                (
                    "v5_m6_series_bible_versions",
                    "v5_m6_series_bible_versions",
                    (*scope, "series_bible_ref", "parent_series_bible_version_ref"),
                    (*scope, "series_bible_ref", "series_bible_version_ref"),
                ),
                (
                    "v5_m6_character_continuity_versions",
                    "v5_m6_character_continuities",
                    (*scope, "character_continuity_ref"),
                    (*scope, "character_continuity_ref"),
                ),
                (
                    "v5_m6_character_continuity_versions",
                    "v5_m6_character_continuity_versions",
                    (
                        *scope,
                        "character_continuity_ref",
                        "parent_character_continuity_version_ref",
                    ),
                    (
                        *scope,
                        "character_continuity_ref",
                        "character_continuity_version_ref",
                    ),
                ),
            )
            for child, parent, source, target in cases:
                with self.subTest(child=child, parent=parent, source=source[-1]):
                    self.assertIn((parent, source, target, "RESTRICT"), groups(child))
        finally:
            connection.close()

    def test_baseline_component_digests_are_separately_queryable_columns(self):
        connection = open_fk(self.path)
        try:
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(v5_m6_baseline_snapshots)"
                )
            }
            self.assertTrue(
                {
                    "series_plan_version_digest",
                    "series_bible_version_digest",
                    "character_continuity_version_digest",
                    "content_digest",
                }.issubset(columns)
            )
        finally:
            connection.close()

    def test_active_baseline_uniqueness_and_global_outbox_order_are_database_constraints(self):
        connection = open_fk(self.path)
        try:
            active_indexes = connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='index' AND tbl_name='v5_m6_baseline_snapshots' "
                "AND sql IS NOT NULL"
            ).fetchall()
            normalized = " ".join(
                str(row[0]).replace("\n", " ").upper() for row in active_indexes
            )
            self.assertIn("UNIQUE", normalized)
            self.assertIn("WHERE", normalized)
            self.assertIn("ACTIVE", normalized)

            outbox = {
                row["name"]: row
                for row in connection.execute("PRAGMA table_info(v5_m6_outbox)")
            }
            self.assertIn("position", outbox)
            self.assertEqual(outbox["position"]["pk"], 1)
        finally:
            connection.close()

    def test_m6_p2_does_not_add_http_or_destructive_public_operations(self):
        server = (ROOT / "apps/creator_workspace_mvp/server.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("series-intelligence", server)
        self.assertNotIn("series-bible", server)
        public_methods = set(SeriesIntelligencePublicBoundary.__dict__)
        self.assertFalse(
            public_methods
            & {
                "delete_bible",
                "delete_character_continuity",
                "delete_baseline",
                "dispatch_outbox",
                "acknowledge_outbox",
            }
        )


if __name__ == "__main__":
    unittest.main()
