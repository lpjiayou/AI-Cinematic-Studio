"""E3G input-artifact and execution-configuration separation contract."""

import ast
import inspect
from pathlib import Path
import tempfile
import unittest

from apps.creator_workspace_mvp import public_contract, server
from services.v4_platform import backend_registry
from services.v4_platform import method_aware_input_artifacts as artifacts
from services.v4_platform import method_aware_worker as worker
from services.v5_core_os.episode_production import method_aware_input_assets as assets
from services.v5_core_os.episode_production import method_aware_media
from services.v5_core_os.episode_production import public


INPUT_CONFIGURATION_NAMES = frozenset(
    {
        "CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH",
        "CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_SHA256",
        "CREATOR_METHOD_AWARE_SOURCE_ROOT",
    }
)
EXECUTION_CONFIGURATION_NAMES = frozenset(
    {
        "CREATOR_METHOD_AWARE_BACKEND_REGISTRY",
        "CREATOR_METHOD_AWARE_BACKEND_REGISTRY_SHA256",
        "METHOD_AWARE_COMFYUI_BASE_URL",
        "METHOD_AWARE_COMFYUI_COST_MINOR_PER_ATTEMPT",
        "METHOD_AWARE_COMFYUI_RUNTIME_ATTESTATION",
        "METHOD_AWARE_COMFYUI_INPUT_ROOT",
        "METHOD_AWARE_COMFYUI_MODEL_ROOT",
    }
)


class InputArtifactExecutionSeparationContractTests(unittest.TestCase):
    def test_exact_existing_input_names_are_the_entire_exemption(self):
        self.assertEqual(frozenset(artifacts.CONFIG_NAMES), INPUT_CONFIGURATION_NAMES)
        self.assertEqual(
            worker._INPUT_ARTIFACT_CONFIGURATION_NAMES,
            INPUT_CONFIGURATION_NAMES,
        )

        tree = ast.parse(inspect.getsource(worker))
        related_literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (
                node.value.startswith("CREATOR_METHOD_AWARE_")
                or node.value.startswith("METHOD_AWARE_COMFYUI_")
            )
            and not node.value.endswith("_")
        }
        self.assertEqual(
            related_literals,
            INPUT_CONFIGURATION_NAMES | EXECUTION_CONFIGURATION_NAMES,
        )

    def test_environment_factory_keeps_input_validation_before_execution_factory(self):
        source = inspect.getsource(
            public.create_local_development_boundary_from_environment
        )
        self.assertLess(
            source.index("input_artifact_evidence_from_environment(values)"),
            source.index("create_method_aware_coordinator_from_environment("),
        )
        self.assertNotIn("except BackendValidationError", source)
        self.assertNotIn("CREATOR_METHOD_AWARE_INPUT_", source)

    def test_partial_input_configuration_still_fails_before_database_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "must-not-exist.sqlite3"
            with self.assertRaises(artifacts.MethodAwareInputArtifactError):
                public.create_local_development_boundary_from_environment(
                    project_boundary=None,
                    series_episode_boundary=None,
                    series_planning_boundary=None,
                    script_studio_boundary=None,
                    environ={
                        "CREATOR_METHOD_AWARE_INPUT_ARTIFACT_BUNDLE_PATH": "missing",
                        "CREATOR_EPISODE_PRODUCTION_DATA_PATH": str(database),
                    },
                )
            self.assertFalse(database.exists())

    def test_unavailable_and_configured_execution_paths_remain_closed(self):
        source = inspect.getsource(
            worker.create_method_aware_coordinator_from_environment
        )
        for required in (
            "UnavailableMethodAdapter()",
            "UnavailableBackendResolver()",
            "BackendRegistry.from_file(",
            "ComfyUIWan22ImageToVideoAdapter(",
            "max_attempts=1",
            'raise BackendValidationError("method-aware backend registry is missing")',
        ):
            self.assertIn(required, source)
        self.assertNotIn("DeterministicLocalFfmpegAdapter", source)
        self.assertNotIn("provider_experiment", source)

    def test_public_routes_requests_and_frozen_schemas_are_unchanged(self):
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
            artifacts.BUNDLE_SCHEMA,
            "v4.method-aware-input-artifact-authority-bundle.v1",
        )
        self.assertEqual(
            assets.ASSET_SCHEMA,
            "v5.method-aware-input-image-asset-version.v1",
        )
        self.assertEqual(
            method_aware_media.METHOD_AWARE_INPUT_PLAN_SCHEMA_VERSION,
            "v5.method-aware-input-plan.v1",
        )
        self.assertEqual(
            method_aware_media.METHOD_AWARE_VIDEO_REQUEST_SCHEMA_VERSION,
            "v5.method-aware-video-generation-request.v1",
        )
        self.assertEqual(
            backend_registry.BACKEND_REGISTRY_SCHEMA,
            "v4.video-execution-backend-registry.v1",
        )
        self.assertNotIn("CREATE TABLE", inspect.getsource(worker))


if __name__ == "__main__":
    unittest.main()
