"""CPU-only fixed-template tests. These are not SH09 exact-binding tests."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from services.v4_platform.backend_registry import BackendValidationError, canonical, digest
from services.v4_platform.generation_dispatch_a14b_profile import (
    A14B_FINAL_OUTPUT, A14B_MODEL_ROLES, compile_a14b_workflow,
    validate_a14b_profile, validate_a14b_workflow)
from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
from services.v4_platform.generation_dispatch_compiler import compile_generation_dispatch_workflow
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_profile, make_a14b_runtime, make_a14b_source


class A14BProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = make_a14b_profile()
        self.kwargs = {"generation_request_ref": "test-generation-request", "source_asset": make_a14b_source(),
            "backend_profile": self.profile, "output_constraints": deepcopy(A14B_FINAL_OUTPUT)}

    def test_six_distinct_roles_are_ordered_and_complete(self):
        result = validate_a14b_profile(self.profile)
        self.assertEqual(tuple(model["role"] for model in result["modelFiles"]), A14B_MODEL_ROLES)
        result["modelFiles"].clear()
        self.assertEqual(len(self.profile["modelFiles"]), 6)

    def test_three_five_seven_missing_and_duplicate_roles_rejected(self):
        for count in (3, 5, 7):
            changed = deepcopy(self.profile)
            changed["modelFiles"] = (changed["modelFiles"] * 2)[:count]
            with self.subTest(count=count), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)
        for index in range(6):
            changed = deepcopy(self.profile)
            changed["modelFiles"][index]["role"] = "UNET" if index == 0 else A14B_MODEL_ROLES[0]
            with self.subTest(role=index), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_expert_originals_or_loras_cannot_be_swapped(self):
        for first, second in ((0, 1), (4, 5)):
            changed = deepcopy(self.profile)
            for field in ("name", "sha256", "sizeBytes"):
                changed["modelFiles"][first][field], changed["modelFiles"][second][field] = (
                    changed["modelFiles"][second][field], changed["modelFiles"][first][field])
            with self.subTest(pair=(first, second)), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_unknown_keys_rejected_at_every_profile_level(self):
        paths = [(), ("parameters",), ("parameters", "input"), ("parameters", "nativeOutput"),
            ("parameters", "postprocess"), ("parameters", "resourceRequirements"),
            ("parameters", "modelPairs", 0), ("modelFiles", 0)]
        for path in paths:
            changed = deepcopy(self.profile)
            target = changed
            for key in path:
                target = target[key]
            target["unapproved"] = 1
            with self.subTest(path=path), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_invalid_number_and_boolean_values_rejected(self):
        for field, values in (("seed", (True, -1, 2**64)), ("steps", (True, 0, 101)), ("cfg", (True, 0, float("nan"), float("inf")))):
            for value in values:
                changed = deepcopy(self.profile)
                changed["parameters"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(BackendValidationError):
                    validate_a14b_profile(changed)

    def test_unsafe_input_output_and_model_names_rejected(self):
        for name in ("../escape.png", "/abs.png", "C:/escape.png", "a\\b.png", "a/%date%.png", "a.png?x=1", "a..png"):
            for key in ("input", "nativeOutput"):
                changed = deepcopy(self.profile)
                changed["parameters"][key]["imageName" if key == "input" else "filenamePrefix"] = name
                with self.subTest(name=name, key=key), self.assertRaises(BackendValidationError):
                    validate_a14b_profile(changed)

    def test_segment_partition_noise_and_pairing_are_closed(self):
        cases = [(0, "startAtStep", 1), (0, "endAtStep", 5), (1, "startAtStep", 3), (1, "endAtStep", 7),
            (0, "addNoise", "disable"), (0, "returnWithLeftoverNoise", "disable"),
            (1, "addNoise", "enable"), (1, "returnWithLeftoverNoise", "enable"),
            (0, "strengthModel", 0), (0, "modelShift", True), (0, "loraRole", "LOW_NOISE_LORA")]
        for index, field, value in cases:
            changed = deepcopy(self.profile)
            changed["parameters"]["modelPairs"][index][field] = value
            with self.subTest(index=index, field=field), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_graph_is_full_dual_expert_and_native_png(self):
        graph = compile_a14b_workflow(**self.kwargs)
        self.assertEqual(set(graph), {str(index) for index in range(1, 17)})
        self.assertEqual(graph["13"]["inputs"]["latent_image"], ["7", 2])
        self.assertEqual(graph["14"]["inputs"]["latent_image"], ["13", 0])
        self.assertEqual(graph["13"]["inputs"]["positive"], ["7", 0])
        self.assertEqual(graph["14"]["inputs"]["negative"], ["7", 1])
        self.assertEqual(graph["8"]["inputs"]["model"], ["1", 0])
        self.assertEqual(graph["9"]["inputs"]["model"], ["4", 0])
        self.assertEqual(graph["16"]["class_type"], "SaveImage")
        self.assertEqual(graph["7"]["inputs"]["length"], 49)
        self.assertNotIn("SaveVideo", [node["class_type"] for node in graph.values()])

    def test_exact_prompt_not_source_or_legacy_suffix(self):
        graph = compile_generation_dispatch_workflow(**self.kwargs, source_text="原始剧本动作。",
            camera_instruction={"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"})
        self.assertEqual(graph["5"]["inputs"]["text"], self.profile["parameters"]["positivePrompt"])
        self.assertEqual(graph["6"]["inputs"]["text"], self.profile["parameters"]["negativePrompt"])
        self.assertNotIn("framing:", graph["5"]["inputs"]["text"])

    def test_every_graph_node_and_input_is_compared_not_merely_hashed(self):
        graph = compile_a14b_workflow(**self.kwargs)
        self.assertEqual(validate_a14b_workflow(graph, **self.kwargs), graph)
        for node_id, node in graph.items():
            for field in node["inputs"]:
                changed = deepcopy(graph)
                changed[node_id]["inputs"][field] = "tampered"
                with self.subTest(node=node_id, field=field), self.assertRaises(BackendValidationError):
                    validate_a14b_workflow(changed, **self.kwargs)
            for mutation in ("class", "extra-input", "extra-node", "missing-node"):
                changed = deepcopy(graph)
                if mutation == "class":
                    changed[node_id]["class_type"] = "UnknownNode"
                elif mutation == "extra-input":
                    changed[node_id]["inputs"]["extra"] = 1
                elif mutation == "extra-node":
                    changed["99"] = deepcopy(node)
                else:
                    del changed[node_id]
                with self.subTest(node=node_id, mutation=mutation), self.assertRaises(BackendValidationError):
                    validate_a14b_workflow(changed, **self.kwargs)

    def test_graph_does_not_depend_on_request_or_grant_or_approval_digest(self):
        original = compile_a14b_workflow(**self.kwargs)
        other = compile_a14b_workflow(**{**self.kwargs, "generation_request_ref": "test-other-request"})
        self.assertEqual(canonical(original), canonical(other))
        self.assertNotIn(b"approvedPlanDigest", canonical(original))
        self.assertNotIn(b"generationDispatchGrantRef", canonical(original))

    def test_original_source_and_output_mismatch_fail_closed(self):
        changed_source = deepcopy(self.kwargs["source_asset"])
        changed_source["contentDigest"] = digest("changed input")
        with self.assertRaises(BackendValidationError):
            compile_a14b_workflow(**{**self.kwargs, "source_asset": changed_source})
        for field, value in (("width", 704.0), ("durationFrames", 49), ("frameRate", 25), ("height", 704)):
            output = {**A14B_FINAL_OUTPUT, field: value}
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                compile_a14b_workflow(**{**self.kwargs, "output_constraints": output})

    def test_postprocess_is_bound_before_execution_and_cannot_be_altered(self):
        for field, value in (("keptZeroBasedIndices", list(range(1, 49))), ("droppedZeroBasedIndices", [0]),
                ("durationFrames", 49), ("frameRate", 25), ("profileId", "test-unapproved")):
            changed = deepcopy(self.profile)
            changed["parameters"]["postprocess"][field] = value
            self.assertNotEqual(digest(changed), digest(self.profile))
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_synthetic_template_cannot_claim_original_frozen_evidence(self):
        for field, value in (("evidenceClass", "PRODUCTION_APPROVED"), ("templateRef", "SH09_FROZEN"),
                ("compilerIdentity", "comfyui-i2v-api-graph-v1"), ("comfyuiCommit", "a" * 40)):
            changed = deepcopy(self.profile)
            changed["parameters"][field] = value
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                validate_a14b_profile(changed)

    def test_compiler_and_runtime_validation_are_pure_without_file_process_or_network_io(self):
        runtime = make_a14b_runtime(self.profile)
        def forbidden(*args, **kwargs):
            raise AssertionError("pure A14B validation attempted external I/O")
        with patch("socket.socket", forbidden), patch("socket.getaddrinfo", forbidden), \
                patch("subprocess.Popen", forbidden), patch("pathlib.Path.read_bytes", forbidden), \
                patch("pathlib.Path.write_bytes", forbidden), patch("builtins.open", forbidden):
            graph = compile_a14b_workflow(**self.kwargs)
            self.assertEqual(validate_a14b_workflow(graph, **self.kwargs), graph)
            validate_a14b_runtime_attestation(runtime, backend_profile=self.profile)


class A14BRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.profile = make_a14b_profile()
        self.runtime = make_a14b_runtime(self.profile)

    @staticmethod
    def reseal(value):
        value["factsDigest"] = digest(value["facts"])
        value["payloadDigest"] = digest({key: item for key, item in value.items() if key != "payloadDigest"})

    def test_exact_runtime_profile_process_and_launch_pair(self):
        facts = self.runtime["facts"]
        actual = validate_a14b_runtime_attestation(self.runtime, backend_profile=self.profile,
            process_identity=facts["processIdentity"], execution_config={"launchConfiguration": facts["launchConfiguration"],
                "launchConfigDigest": facts["launchConfigDigest"]})
        self.assertEqual(actual, facts)
        self.assertEqual(actual["evidenceClass"], "TEST_ONLY")

    def test_profile_or_original_mutation_rejected_even_after_runtime_reseal(self):
        for field, value in (("name", "test-replaced.bin"), ("sha256", digest("replacement")), ("sizeBytes", 999)):
            changed = deepcopy(self.runtime)
            changed["facts"]["modelFiles"][0][field] = value
            self.reseal(changed)
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(changed, backend_profile=self.profile)
        changed_profile = deepcopy(self.profile)
        changed_profile["parameters"]["seed"] += 1
        with self.assertRaises(BackendValidationError):
            validate_a14b_runtime_attestation(self.runtime, backend_profile=changed_profile)

    def test_runtime_process_and_launch_drift_rejected(self):
        facts = self.runtime["facts"]
        for field, value in (("comfyuiPid", 18), ("processStartTicks", "124"), ("hostBootIdDigest", digest("reboot"))):
            process = {**facts["processIdentity"], field: value}
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(self.runtime, process_identity=process)
        changed = {"launchConfiguration": {**facts["launchConfiguration"], "argv": ["test-changed-launch"]},
            "launchConfigDigest": facts["launchConfigDigest"]}
        with self.assertRaises(BackendValidationError):
            validate_a14b_runtime_attestation(self.runtime, execution_config=changed)

    def test_runtime_code_nodes_device_and_resources_are_not_strings_only(self):
        cases = [("comfyuiCommit", "b" * 40), ("requiredNodes", []), ("nodeInputContracts", {}),
            ("gpuCount", 2), ("gpuCount", True), ("deviceType", "cpu"), ("vramTotalBytes", 1),
            ("endpointClass", "PRODUCTION"), ("compilerIdentity", "unknown"), ("templateRef", "unknown")]
        for field, value in cases:
            changed = deepcopy(self.runtime)
            changed["facts"][field] = value
            self.reseal(changed)
            with self.subTest(field=field), self.assertRaises(BackendValidationError):
                validate_a14b_runtime_attestation(changed, backend_profile=self.profile)

    def test_missing_unknown_fields_and_resealed_publication_are_rejected(self):
        for section in (None, "facts"):
            for mutation in ("add", "remove"):
                changed = deepcopy(self.runtime)
                target = changed if section is None else changed[section]
                if mutation == "add":
                    target["unknown"] = 1
                else:
                    del target["attestationRef" if section is None else "objectInfoDigest"]
                with self.subTest(section=section, mutation=mutation), self.assertRaises(BackendValidationError):
                    validate_a14b_runtime_attestation(changed)
        changed = deepcopy(self.runtime)
        changed["publicationAllowed"] = True
        self.reseal(changed)
        with self.assertRaises(BackendValidationError):
            validate_a14b_runtime_attestation(changed)


if __name__ == "__main__":
    unittest.main()
