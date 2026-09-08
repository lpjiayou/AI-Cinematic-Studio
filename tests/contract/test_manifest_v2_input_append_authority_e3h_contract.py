"""E3H bounded manifest-v2 technical-input append contract pins."""

import ast
import inspect
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract, server
from scripts import method_aware_input_append_authority as operator
from scripts.run_ci_fast_path import audit_integration_shard_files
from services.v4_platform import method_aware_worker
from services.v5_core_os.episode_production import evidence
from services.v5_core_os.episode_production import input_append_authority as authority
from services.v5_core_os.episode_production import media_candidate_review
from services.v5_core_os.episode_production import method_aware_input_assets as assets
from services.v5_core_os.episode_production import method_aware_media
from services.v5_core_os.episode_production import method_aware_result_intake
from services.v5_core_os.episode_production import public


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT = (
    REPOSITORY_ROOT
    / "architecture/M10_MANIFEST_V2_TECHNICAL_INPUT_APPEND_AUTHORITY_CONTRACT.md"
)
ADR = (
    REPOSITORY_ROOT
    / "governance/ADR-0021-manifest-v2-technical-input-append-authority.md"
)


class ManifestV2InputAppendAuthorityE3HContractTests(unittest.TestCase):
    def test_exact_schemas_operations_and_one_additive_record_kind(self):
        self.assertEqual(
            authority.CONFIG_NAMES,
            (
                "CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_PATH",
                "CREATOR_M10_INPUT_APPEND_AUTHORITY_BUNDLE_SHA256",
            ),
        )
        self.assertEqual(
            authority.BUNDLE_SCHEMA,
            "v5.m10-input-append-authority-bundle.v1",
        )
        self.assertEqual(
            authority.GRANT_SCHEMA,
            "v5.m10-input-append-authority-grant.v1",
        )
        self.assertEqual(
            authority.SUBJECT_SCHEMA,
            "v5.m10-input-append-authority-subject.v1",
        )
        self.assertEqual(
            authority.EVIDENCE_SCHEMA,
            "v5.method-aware-input-append-authority-decision.v1",
        )
        self.assertEqual(
            authority.ALLOWED_OPERATIONS,
            (
                "TECHNICAL_INPUT_INTAKE",
                "SEMANTIC_VISUAL_QC",
                "HUMAN_SELECTION",
                "INPUT_ADMISSION",
                "METHOD_AWARE_INPUT_PLAN",
            ),
        )
        self.assertEqual(
            authority.EXCLUDED_OPERATIONS,
            (
                "PROVIDER_PROCESSING",
                "MEDIA_GENERATION",
                "VIDEO_RESULT_INTAKE",
                "OUTPUT_SELECTION",
                "OUTPUT_ADMISSION",
                "EXECUTION_DISPATCH",
                "MASTER_OR_EXPORT",
                "PUBLICATION",
            ),
        )
        self.assertEqual(
            authority.EVIDENCE_RECORD_KIND,
            "MethodAwareInputAppendAuthority",
        )
        self.assertIn(
            authority.EVIDENCE_RECORD_KIND,
            evidence.ALLOWED_EVIDENCE_RECORD_KINDS,
        )
        self.assertEqual(
            inspect.getsource(evidence).count('"MethodAwareInputAppendAuthority"'),
            1,
        )

    def test_v1_receipt_and_default_v2_review_rejection_remain_explicit(self):
        self.assertEqual(
            assets.RECEIPT_SCHEMA,
            "v5.method-aware-input-artifact-receipt.v1",
        )
        self.assertEqual(
            assets.RECEIPT_SCHEMA_V2,
            "v5.method-aware-input-artifact-receipt.v2",
        )
        self.assertEqual(
            assets.RECEIPT_V2_FIELDS - assets.RECEIPT_FIELDS,
            {"inputAppendAuthorityRef", "inputAppendAuthorityDigest"},
        )
        scope_source = inspect.getsource(media_candidate_review.K2MediaCandidateReviewService._scope)
        self.assertIn("VerifiedInputAppendAuthority", scope_source)
        self.assertIn("v2 production run is preflight-only", scope_source)
        self.assertNotIn("allow_v2", scope_source)
        self.assertNotIn("skip_execution_check", scope_source)
        self.assertNotIn("authority", assets.INTAKE_FIELDS)
        self.assertNotIn("allowV2", assets.INTAKE_FIELDS)

    def test_authority_config_is_loaded_before_any_database_or_execution_factory(self):
        source = inspect.getsource(
            public.create_local_development_boundary_from_environment
        )
        self.assertLess(
            source.index("input_append_authority_from_environment(values)"),
            source.index("create_method_aware_coordinator_from_environment("),
        )
        self.assertFalse(
            set(authority.CONFIG_NAMES)
            & method_aware_worker._INPUT_ARTIFACT_CONFIGURATION_NAMES
        )
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "must-not-exist.sqlite3"
            with self.assertRaises(
                authority.InputAppendAuthorityConfigurationError
            ):
                public.create_local_development_boundary_from_environment(
                    project_boundary=None,
                    series_episode_boundary=None,
                    series_planning_boundary=None,
                    script_studio_boundary=None,
                    environ={
                        authority.CONFIG_NAMES[0]: str(Path(temporary) / "missing"),
                        "CREATOR_EPISODE_PRODUCTION_DATA_PATH": str(database),
                    },
                )
            self.assertFalse(database.exists())

    def test_public_route_inventory_and_existing_manifest_contract_do_not_expand(self):
        self.assertEqual(
            set(public_contract.PUBLIC_METHOD_AWARE_RESOURCES),
            {
                "execution-method-plan",
                "method-aware-input-plan",
                "method-aware-video-route",
                "method-aware-video-jobs",
                "method-aware-video-candidates",
                "explicit-audio-requirement-route",
                "method-aware-input-candidates",
                "method-aware-input-admission",
            },
        )
        self.assertEqual(len(server.EPISODE_PRODUCTION_SUBRESOURCES), 35)
        self.assertEqual(
            method_aware_media.METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION,
            "v5.method-aware-input-plan.v1",
        )
        self.assertEqual(
            method_aware_media.METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION,
            "v5.method-aware-video-generation-request.v1",
        )
        route_source = inspect.getsource(
            method_aware_media.M10M11MethodAwareMediaService.route_video_methods
        )
        self.assertLess(
            route_source.index("MANIFEST_SCHEMA_VERSION_V2"),
            route_source.index("require_current_input_plan("),
        )
        self.assertIn("does not authorize video routing", route_source)

    def test_authority_and_operator_are_not_journal_or_execution_owners(self):
        authority_source = inspect.getsource(authority)
        operator_source = inspect.getsource(operator)
        result_source = inspect.getsource(method_aware_result_intake)
        for source in (authority_source, operator_source):
            for forbidden in (
                "sqlite3",
                "CREATE TABLE",
                "INSERT INTO",
                "MediaJobCoordinator",
                "ComfyUI",
                "/prompt",
                "provider_experiment",
            ):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, source)
        operator_tree = ast.parse(operator_source)
        called_attributes = {
            node.attr
            for node in ast.walk(operator_tree)
            if isinstance(node, ast.Attribute)
        }
        self.assertFalse(
            called_attributes
            & {
                "append_record",
                "append_records",
                "dispatch",
                "generate",
                "run_one",
            }
        )
        self.assertNotIn("input_append_authority", result_source)

    def test_normative_contract_and_accepted_scope_relationship_are_explicit(self):
        contract = CONTRACT.read_text(encoding="utf-8")
        adr = ADR.read_text(encoding="utf-8")
        for literal in (
            "ACCEPTED NORMATIVE CONTRACT",
            "MethodAwareInputAppendAuthority",
            "v5.method-aware-input-artifact-receipt.v2",
            "LOCAL_STRUCTURAL_REPRESENTATION_ONLY",
            "input-append authority is not a HumanSelection approval",
            "real fresh-process readback/replay",
            "does not issue authority for, mutate or resume any preserved R6",
        ):
            with self.subTest(literal=literal):
                self.assertIn(literal, contract)
        for literal in (
            "Status | `Accepted`",
            "Amends scope | `ADR-0014`",
            "Extends | `ADR-0019`",
            "does not migrate or authorize an existing v2 run",
        ):
            with self.subTest(literal=literal):
                self.assertIn(literal, adr)

    def test_integration_shard_and_cross_level_module_names_are_exact(self):
        audit = audit_integration_shard_files()
        self.assertEqual(audit["missing"], ())
        self.assertEqual(audit["extra"], ())
        self.assertEqual(audit["duplicateCount"], 0)
        self.assertEqual(
            list(audit["assigned"]).count(
                "tests/integration/"
                "test_creator_manifest_v2_input_append_authority_e3h.py"
            ),
            1,
        )
        unit = {
            path.name for path in (REPOSITORY_ROOT / "tests/unit").glob("test_*.py")
        }
        contract = {
            path.name
            for path in (REPOSITORY_ROOT / "tests/contract").glob("test_*.py")
        }
        integration = {
            path.name
            for path in (REPOSITORY_ROOT / "tests/integration").glob("test_*.py")
        }
        self.assertEqual(unit & contract, set())
        self.assertEqual(unit & integration, set())
        self.assertEqual(contract & integration, set())


if __name__ == "__main__":
    unittest.main()
