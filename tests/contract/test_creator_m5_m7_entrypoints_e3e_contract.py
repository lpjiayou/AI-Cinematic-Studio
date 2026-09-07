"""E3E public resource inventory and controlled operator ownership contract."""

import ast
import inspect
from pathlib import Path
import unittest

from apps.creator_workspace_mvp import episode_plan_binding_operator as operator
from apps.creator_workspace_mvp import public_contract, server
from scripts.run_ci_fast_path import audit_integration_shard_files


REPO = Path(__file__).resolve().parents[2]
LEGACY_SUBRESOURCES = {
    "authority-identity", "production-readiness", "provider-experiments", "shot-graph",
    "assets", "media", "deterministic-effects", "timeline", "timeline-versions", "timeline-edits",
    "render-candidates", "preview", "finalize", "delivery", "real-media-revision", "dynamic-media-preflight",
    "real-image-candidates", "real-image-selection", "real-image-admission", "real-image-successor-admission",
    "real-video-revision", "real-video-candidates", "semantic-visual-qc", "media-selection", "real-video-admission",
    "state-projection", "execution-method-plan", "method-aware-input-plan", "method-aware-video-route",
    "method-aware-video-jobs", "method-aware-video-candidates", "method-aware-input-candidates",
    "method-aware-input-admission", "explicit-audio-requirement-route",
}


class CreatorM5M7EntrypointsContractTests(unittest.TestCase):
    def test_one_m7_resource_preserves_exact_previous_inventory_and_method_aware_set(self):
        self.assertEqual(34, len(LEGACY_SUBRESOURCES))
        self.assertEqual(LEGACY_SUBRESOURCES | {"narrative-validation"}, server.EPISODE_PRODUCTION_SUBRESOURCES)
        self.assertEqual(35, len(server.EPISODE_PRODUCTION_SUBRESOURCES))
        self.assertEqual("narrative-validation", public_contract.PUBLIC_NARRATIVE_VALIDATION_RESOURCE)
        self.assertEqual({"execution-method-plan", "method-aware-input-plan", "method-aware-video-route",
                          "method-aware-video-jobs", "method-aware-video-candidates", "method-aware-input-candidates",
                          "method-aware-input-admission", "explicit-audio-requirement-route"},
                         set(public_contract.PUBLIC_METHOD_AWARE_RESOURCES))
        capabilities = {item["id"]: item for item in public_contract.capability_payload()["capabilities"]}
        self.assertEqual(["episode-production-runs/shot-graph", "episode-production-runs/narrative-validation"],
                         capabilities["M7"]["publicResources"])
        self.assertEqual(["series-planning-workspaces", "series-plan-candidates", "series-plan-versions"],
                         capabilities["M5"]["publicResources"])
        for resource in server.EPISODE_PRODUCTION_SUBRESOURCES:
            path = "/creator/api/v1/episode-production-runs/run/" + resource
            self.assertEqual(("run", resource), server._episode_production_subresource(path))
        for resource in ("unknown", "binding-versions", "comfyui", "ffmpeg"):
            self.assertIsNone(server._episode_production_subresource(
                "/creator/api/v1/episode-production-runs/run/" + resource))

    def test_operator_has_no_private_storage_sql_or_confirmation_access(self):
        tree = ast.parse(inspect.getsource(operator))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertFalse(any(name and (name.startswith("tests") or "sqlite" in name or "foundation" in name) for name in imports))
        names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertFalse(names & {"repository", "coordinator", "state", "lease", "confirm_version", "activate_baseline",
                                 "cursor", "executescript", "sqlite_from_environment", "_lifecycle_assembly_or_none"})
        self.assertIn("create_episode_plan_item_binding_version", names)
        self.assertIn("get_workspace", names)
        self.assertIn("build_context", names)
        self.assertIs(False, inspect.signature(operator.EpisodePlanBindingOperator.execute).parameters["apply"].default)
        source = inspect.getsource(operator)
        for forbidden in ("CREATE TABLE", "SELECT ", "INSERT INTO", "UPDATE ", "Path.home", "canonical_bootstrap"):
            self.assertNotIn(forbidden, source)

    def test_integration_shard_and_module_names_are_exact(self):
        audit = audit_integration_shard_files()
        self.assertEqual((), audit["missing"])
        self.assertEqual((), audit["extra"])
        self.assertEqual(0, audit["duplicateCount"])
        self.assertEqual(1, list(audit["assigned"]).count("tests/integration/test_creator_m5_m7_entrypoints_e3e_http.py"))
        unit = {path.name for path in (REPO / "tests/unit").glob("test_*.py")}
        integration = {path.name for path in (REPO / "tests/integration").glob("test_*.py")}
        self.assertEqual(set(), unit & integration)

    def test_document_states_actual_entrypoints_recovery_and_existing_m7_projection(self):
        document = (REPO / "docs/04-interface-contract/creator-public-http-v1.md").read_text()
        for literal in ("episode_plan_item_binding.py", "sourceContentDigest", "operationAuthorizationRef",
                        "BINDING_RESULT_RECOVERED_BY_AUTHORITATIVE_READBACK", "BINDING_VERSION_CONFIRMED",
                        "/narrative-validation", "create_narrative_validation", "get_narrative_validation",
                        "ConsistencyValidationVersion", "consistencyValidationVersionRef",
                        "validationProfileVersion", "NOT_READY_PENDING_DISPOSITION", "upstream_not_confirmed"):
            with self.subTest(literal=literal):
                self.assertIn(literal, document)


if __name__ == "__main__":
    unittest.main()
