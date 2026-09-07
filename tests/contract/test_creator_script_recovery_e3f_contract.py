"""Closed public requests, single authority and exact additive component inventory."""

import ast
from pathlib import Path
import sqlite3
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract
from apps.creator_workspace_mvp.ai_director import AiDirectorService
from apps.creator_workspace_mvp.server import create_server
from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.series_planning.candidate_receipt_sqlite import SqliteSeriesPlanCandidateReceiptStore
from services.v5_core_os.text_generation.testing import FakeTextGenerationCapability


REPO = Path(__file__).resolve().parents[2]
BASE_ASSEMBLY_TABLES = frozenset({
    "creator_project_foundation_commands", "creator_project_foundation_schema",
    "v5_canonical_registration_schema", "v5_canonical_registrations",
    "v5_confirmed_creative_plans", "v5_episode_plan_bindings", "v5_episode_projects",
    "v5_m6_baseline_snapshots", "v5_m6_character_continuities", "v5_m6_character_continuity_versions",
    "v5_m6_operations", "v5_m6_outbox", "v5_m6_series_bible_versions", "v5_m6_series_bibles",
    "v5_project_schema", "v5_project_series_relationships", "v5_projects",
    "v5_script_acceptance_schema", "v5_script_acceptances", "v5_script_studio_schema",
    "v5_script_versions", "v5_scripts", "v5_series", "v5_series_episode_schema",
    "v5_series_intelligence_schema", "v5_series_plan_versions", "v5_series_planning_schema", "v5_series_plans",
})
RECOVERY_TABLES = {"creator_script_generation_schema", "creator_script_generation_commands"}
SERVER_COMMAND_TABLES = {"creator_ai_director_candidate_schema", "creator_ai_director_candidate_commands",
    "creator_series_plan_candidate_command_schema", "creator_series_plan_candidate_commands"}


def tables(path):
    with sqlite3.connect(path) as connection:
        return {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


class ScriptRecoveryPublicContractTests(unittest.TestCase):
    def test_exact_generate_and_confirmation_field_sets(self):
        self.assertEqual({"seriesRef", "episodeRef"}, public_contract.SCRIPT_GENERATION_REQUIRED_FIELDS)
        self.assertEqual({"projectRef", "idempotencyKey"}, public_contract.SCRIPT_GENERATION_OPTIONAL_FIELDS)
        self.assertEqual({"seriesRef", "episodeRef", "scriptRef", "scriptVersionRef", "humanConfirmed"},
                         public_contract.SCRIPT_CONFIRMATION_REQUIRED_FIELDS)
        self.assertEqual({"projectRef", "expectedScriptVersion"}, public_contract.SCRIPT_CONFIRMATION_OPTIONAL_FIELDS)
        self.assertEqual("/creator/api/v1/script-versions/generate", public_contract.PUBLIC_SCRIPT_GENERATE_ENDPOINT)
        self.assertEqual("/creator/api/v1/script-versions/confirm", public_contract.PUBLIC_SCRIPT_CONFIRM_ENDPOINT)

    def test_recovery_application_has_no_sql_private_adapter_or_transaction_callback(self):
        source = (REPO / "apps/creator_workspace_mvp/script_generation_recovery.py").read_text()
        tree = ast.parse(source)
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual({"script_studio", "services.v5_core_os.script_studio"}, imports)
        for forbidden in ("sqlite3", "connection", "repository", "lifecycle_state", "CREATE TABLE", "INSERT INTO", "services.v4_platform"):
            self.assertNotIn(forbidden, source)
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Attribute)
                 and node.func.value.attr == "boundary"}
        self.assertEqual({"reserve_generation", "save_generation_result", "complete_generation", "fail_generation"}, calls)

    def test_exact_creator_table_inventory_with_optional_historical_v1_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "creator.sqlite3"
            assembly = LifecycleAssembly.sqlite(path, initialize_or_upgrade=True)
            self.assertEqual(BASE_ASSEMBLY_TABLES | RECOVERY_TABLES, tables(path))
            server = create_server(("127.0.0.1", 0), AiDirectorService(FakeTextGenerationCapability([])),
                series_episode_boundary=assembly.series_episode, script_studio_boundary=assembly.script_studio)
            server.server_close()
            self.assertEqual(BASE_ASSEMBLY_TABLES | RECOVERY_TABLES | SERVER_COMMAND_TABLES, tables(path))
            SqliteSeriesPlanCandidateReceiptStore(path)
            self.assertEqual(BASE_ASSEMBLY_TABLES | RECOVERY_TABLES | SERVER_COMMAND_TABLES |
                {"creator_series_director_schema", "creator_series_plan_candidate_receipts"}, tables(path))
            LifecycleAssembly.sqlite(path)
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE unrecognized_recovery_object(value TEXT)")
            from services.v5_core_os.series_intelligence.migration import SeriesIntelligenceMigrationError
            with self.assertRaises(SeriesIntelligenceMigrationError):
                LifecycleAssembly.sqlite(path)

    def test_document_preserves_recovery_limits_and_unmodified_m5_privacy_literals(self):
        document = (REPO / "docs/04-interface-contract/creator-public-http-v1.md").read_text()
        for literal in ("SCRIPT_GENERATION", "RESULT_READY", "script_generation_pending",
                        "recoveredFromResultReady=true", "expectedScriptVersion", "ScriptVersion.versionNumber",
                        "script_confirmation_precondition_required", "version_conflict", "maximum-one schema repair",
                        "creator.script-studio.script-version.v1", "creator.script-studio.script-version.v2",
                        "creator.series-plan-candidate-receipt.v1", "creator.series-plan-candidate-receipt.v2",
                        "raw `creativeInput`", "Frontend CAS wiring", "same transaction"):
            with self.subTest(literal=literal):
                self.assertIn(literal, document)


if __name__ == "__main__":
    unittest.main()
