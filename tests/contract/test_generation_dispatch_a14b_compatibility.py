"""Versioned compatibility and acyclic identity checks, using TEST_ONLY data."""
from copy import deepcopy
import unittest

from services.v4_platform.backend_registry import BackendValidationError, canonical, digest
from services.v4_platform.comfyui import ComfyUIConfigurationError, validate_runtime_attestation
from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
from services.v4_platform.generation_dispatch_a14b_profile import (
    A14B_COMPILER_IDENTITY, A14B_PROFILE_SCHEMA, validate_a14b_profile)
from services.v4_platform.generation_dispatch_compiler import compile_generation_dispatch_workflow
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_fixtures import make_package, SOURCE_TEXT
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_package, make_a14b_profile, make_a14b_runtime


class A14BCompatibilityTests(unittest.TestCase):
    @staticmethod
    def compiler_kwargs(package):
        plan, materials = package["plan"], package["materials"]
        return {"generation_request_ref": "generation-request-" + digest(c.request_identity(plan)),
            "source_text": SOURCE_TEXT, "camera_instruction": plan["subject"]["cameraInstruction"],
            "source_asset": {key: value for key, value in plan["subject"]["inputAsset"].items() if key != "inputRole"},
            "backend_profile": materials["backendProfile"], "output_constraints": plan["subject"]["outputConstraints"]}

    def test_legacy_profile_graph_identity_plan_and_attestation_bytes_stay_pinned(self):
        # Captured from BASE_MAIN ad7349ff, compiler blob c876164cf0c598f37489dab0e6bf1dcede841b00.
        package, attestation = make_package()
        plan, materials = package["plan"], package["materials"]
        self.assertEqual(digest(c.request_identity(plan)), "c5b884353da8609f7b64182710a989af89d5ffc1fff4e580ffb3b28b9c51a6b8")
        self.assertEqual(digest(materials["backendProfile"]), "64466a82e4cc417f16a163b4aa5283a209cbd368ffb4b75a42cc1f218ed7d3a5")
        self.assertEqual(digest(plan), "c5eefbd8ff1338dfdc5dd4e744232c47f678b930f378a97cf28c8019c572d66d")
        self.assertEqual(attestation["payloadDigest"], "77cb7e9c334745396119492387e2c7a4b32c3fd59303738afb2a34b168c34ed8")
        graph = compile_generation_dispatch_workflow(**self.compiler_kwargs(package))
        self.assertEqual(digest(graph), "cb6fe3df63010a6bea4d9706445ddbfe24be9827921e758fa7d099c952ab5839")
        self.assertEqual(canonical(graph), canonical(materials["workflow"]))
        self.assertEqual(c.validate_plan_package(package), package)
        self.assertEqual(validate_runtime_attestation(attestation), attestation["facts"])

    def test_legacy_and_a14b_schemas_cannot_be_relabeled_or_mixed(self):
        legacy, legacy_runtime = make_package()
        newer, new_runtime = make_a14b_package()
        for profile, schema in ((legacy["materials"]["backendProfile"], A14B_PROFILE_SCHEMA),
                (newer["materials"]["backendProfile"], "v4.comfyui-i2v-backend-profile.v1"),
                (newer["materials"]["backendProfile"], "v4.comfyui-a14b-i2v-backend-profile.v99")):
            changed = deepcopy(profile)
            changed["schemaVersion"] = schema
            with self.subTest(schema=schema), self.assertRaises(BackendValidationError):
                compile_generation_dispatch_workflow(**{**self.compiler_kwargs(newer), "backend_profile": changed})
        with self.assertRaises(BackendValidationError):
            validate_a14b_runtime_attestation(legacy_runtime, backend_profile=newer["materials"]["backendProfile"])
        with self.assertRaises(BackendValidationError):
            validate_a14b_runtime_attestation(new_runtime, backend_profile=legacy["materials"]["backendProfile"])
        changed = deepcopy(new_runtime)
        changed["schemaVersion"] = "v4.comfyui-runtime-attestation.v2"
        changed["capabilityMode"] = "IMAGE_TO_VIDEO"
        with self.assertRaises((BackendValidationError, ComfyUIConfigurationError)):
            validate_runtime_attestation(changed)

    def test_new_profile_compiler_and_runtime_are_explicitly_bound(self):
        package, attestation = make_a14b_package()
        plan, materials = package["plan"], package["materials"]
        self.assertEqual(c.request_identity(plan)["workflowCompilerRef"], A14B_COMPILER_IDENTITY)
        self.assertEqual(c.validate_plan_package(package), package)
        self.assertEqual(validate_runtime_attestation(attestation), attestation["facts"])
        validate_a14b_runtime_attestation(attestation, backend_profile=materials["backendProfile"],
            process_identity=materials["processIdentity"], execution_config=materials["executionConfig"])
        self.assertEqual(canonical(materials["workflow"]), canonical(compile_generation_dispatch_workflow(**self.compiler_kwargs(package))))

    def test_old_adapter_identity_cannot_authorize_new_profile(self):
        package, _ = make_a14b_package()
        decision = package["plan"]["executionBinding"]["backendDecision"]
        decision["adapterIdentity"] = "v4.comfyui-wan22-image-to-video.v1"
        package["plan"]["executionBinding"]["backendDecisionDigest"] = digest(decision)
        with self.assertRaises(c.DispatchError):
            c.validate_plan_package(package)

    def test_prompt_and_source_are_distinct_but_both_bound(self):
        package, _ = make_a14b_package()
        source = package["plan"]["subject"]["sourceAction"]
        self.assertEqual(source["sourceTextDigest"], __import__("hashlib").sha256(SOURCE_TEXT.encode()).hexdigest())
        self.assertNotEqual(package["materials"]["workflow"]["5"]["inputs"]["text"], SOURCE_TEXT)
        changed = deepcopy(package)
        changed["materials"]["workflow"]["5"]["inputs"]["text"] += "; framing: MEDIUM_CLOSE_UP; movement: LOCKED"
        changed["plan"]["executionBinding"]["workflowDigest"] = digest(changed["materials"]["workflow"])
        with self.assertRaises(c.DispatchError):
            c.validate_plan_package(changed)

    def test_approved_input_digests_change_identity_without_graph_approval_cycle(self):
        package, _ = make_a14b_package()
        plan = package["plan"]
        identity = c.request_identity(plan)
        self.assertNotIn("workflowDigest", identity)
        self.assertNotIn("approvedPlanDigest", identity)
        self.assertNotIn("generationDispatchGrantRef", identity)
        for field in ("seed", "positivePrompt", "negativePrompt"):
            changed = deepcopy(package)
            p = changed["materials"]["backendProfile"]["parameters"]
            p[field] = p[field] + (1 if field == "seed" else " changed")
            binding = changed["plan"]["executionBinding"]
            binding["executionProfile"]["digest"] = digest(changed["materials"]["backendProfile"])
            self.assertNotEqual(digest(c.request_identity(changed["plan"])), digest(identity))
        # A downstream workflow seal cannot feed back into the compiler request.
        changed_plan = deepcopy(plan)
        changed_plan["executionBinding"]["workflowDigest"] = digest("test-downstream-digest")
        self.assertEqual(c.request_identity(changed_plan), identity)

    def test_unknown_runtime_and_new_three_model_shapes_are_rejected(self):
        profile = make_a14b_profile()
        profile["modelFiles"] = profile["modelFiles"][:3]
        with self.assertRaises(BackendValidationError):
            validate_a14b_profile(profile)
        value = make_a14b_runtime(make_a14b_profile())
        value["schemaVersion"] = "v4.comfyui-a14b-runtime-attestation.v99"
        with self.assertRaises(ComfyUIConfigurationError):
            validate_runtime_attestation(value)


if __name__ == "__main__":
    unittest.main()
