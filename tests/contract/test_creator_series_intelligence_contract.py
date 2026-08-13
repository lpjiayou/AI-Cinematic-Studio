import ast
from pathlib import Path
import unittest

from services.v5_core_os.lifecycle_integrity import LifecycleAssembly
from services.v5_core_os.lifecycle_integrity.contracts import LifecycleOperation
from services.v5_core_os.series_intelligence import M6Scope
from services.v5_core_os.series_intelligence.public import SeriesIntelligencePublicError
from tests.unit.test_series_intelligence_m6 import confirmed_components, seed_assembly


ROOT = Path(__file__).resolve().parents[2]


class ScopeAuthority:
    def resolve_scope(self, workspace_ref, project_ref, series_ref):
        return M6Scope("series", "tenant", workspace_ref, project_ref, series_ref)


class SeriesIntelligenceContractTests(unittest.TestCase):
    def test_m6_lifecycle_operations_are_explicit_and_bounded(self):
        expected = {
            "create-series-bible-version", "submit-series-bible-candidate",
            "confirm-series-bible-version", "create-character-continuity-version",
            "submit-character-continuity-candidate", "confirm-character-continuity-version",
            "activate-m6-baseline",
        }
        self.assertTrue(expected.issubset({item.value for item in LifecycleOperation}))

    def test_sqlite_is_absent_from_m6_module_and_no_m6_http_endpoint_exists(self):
        m6_files = sorted((ROOT / "services/v5_core_os/series_intelligence").glob("*.py"))
        self.assertGreaterEqual(len(m6_files), 8)
        for path in m6_files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = {
                alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names
            } | {
                node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            }
            self.assertNotIn("sqlite3", imports)
        server = (ROOT / "apps/creator_workspace_mvp/server.py").read_text(encoding="utf-8")
        self.assertNotIn("series-intelligence", server)
        self.assertNotIn("series-bible", server)

    def test_default_composition_is_fail_closed_not_mock_authorized(self):
        assembly = LifecycleAssembly.in_memory()
        with self.assertRaises(SeriesIntelligencePublicError) as error:
            assembly.series_intelligence.get_workspace("w", "p", "s")
        self.assertEqual((error.exception.code, error.exception.status), ("authority_unavailable", 403))

    def test_m6_participant_is_registered_in_same_lifecycle_state(self):
        assembly = LifecycleAssembly.in_memory(m6_scope_authority=ScopeAuthority())
        diagnostics = assembly.diagnostic_snapshot()
        self.assertIn("series-intelligence", diagnostics["registeredResources"])
        self.assertIsNotNone(assembly.series_intelligence)

    def test_m5_bridge_is_internal_python_boundary_not_http(self):
        assembly = LifecycleAssembly.in_memory()
        self.assertTrue(callable(assembly.series_planning.get_confirmed_m6_source_snapshot))
        server = (ROOT / "apps/creator_workspace_mvp/server.py").read_text(encoding="utf-8")
        self.assertNotIn("m6-source-snapshot", server)

    def test_governance_keeps_p2_m7_frontend_and_formal_database_out(self):
        adr = (ROOT / "governance/ADR-0003-m6-series-intelligence-baseline.md").read_text(encoding="utf-8")
        self.assertIn("M6-P1 InMemory only", adr)
        self.assertIn("M6-P2+ and M7-M19 remain", adr)
        self.assertIn("formal 8765 data", adr)

    def test_workspace_contract_projects_immutable_bible_and_character_version_history(self):
        assembly, context = seed_assembly()
        bible, characters = confirmed_components(assembly, context)
        workspace = assembly.series_intelligence.get_workspace(
            context["workspaceRef"], context["projectRef"], context["seriesRef"]
        )
        self.assertEqual(
            workspace["seriesBibleVersions"][0]["seriesBibleVersionRef"],
            bible["version"]["seriesBibleVersionRef"],
        )
        self.assertEqual(
            workspace["characterContinuityVersions"][0]["characterContinuityVersionRef"],
            characters["version"]["characterContinuityVersionRef"],
        )
        self.assertEqual(workspace["seriesBibleVersions"][0]["status"], "CONFIRMED")
        self.assertEqual(workspace["characterContinuityVersions"][0]["status"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
