"""Synthetic trusted-port originals only; no live host or GPU observations."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import struct
import unittest
from unittest.mock import patch
import zlib

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_live_sources import (
    LiveRuntimeCurrentReader, OriginalFile,
)
from services.v5_core_os.episode_production.generation_dispatch_readers import VerifiedOriginalObservation
from services.v5_core_os.episode_production.image_video_materials import (
    ImageVideoMaterials, create_image_video_installation,
)
from services.v4_platform.image_video_execution import OUTPUT
from services.v4_platform.generation_dispatch_a14b_live import (
    LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS,
)
from tests.support.generation_dispatch_fixtures import make_package, START, TEST_SCOPE
from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime


def test_png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00" + b"\x55\x66\x77" * 2 + b"\x00" + b"\x55\x66\x77" * 2)) + chunk(b"IEND", b"")


class ImageVideoMaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="image-video-materials-test-")
        self.addCleanup(self.temp.cleanup)
        self.png = test_png()
        package, _ = make_package()
        self.scope = deepcopy(TEST_SCOPE)
        self.limits = deepcopy(package["plan"]["limits"])
        profile = live_profile()
        runtime = live_runtime(profile)
        self.configuration = {
            "backendProfile": profile,
            "processIdentity": runtime["facts"]["processIdentity"],
            "executionConfig": deepcopy(package["materials"]["executionConfig"]),
            "executionCode": deepcopy(package["plan"]["executionBinding"]["executionCode"]),
            "backendDecision": deepcopy(package["plan"]["executionBinding"]["backendDecision"]),
        }
        self.configuration["executionCode"]["comfyuiCommit"] = runtime["facts"]["comfyuiCommit"]
        self.configuration["backendDecision"].update(
            adapterIdentity=LIVE_ADAPTER_IDENTITY, adapterCapability=LIVE_CAPABILITY,
            endpointClass=LIVE_ENDPOINT_CLASS, modelId="test-a14b-model",
            backendProfileDigest=c.digest(profile),
        )
        self.file = self.original("template.json", self.configuration)
        text = "A synthetic subject turns toward the window."
        self.subject = {"schemaVersion": "v5.user-image-video-subject.v1",
            "generationRef": "test-user-generation", "inputDigest": c.digest("synthetic-input"),
            "inputImage": {"inputRef": "test-input-image", "contentDigest": sha256(self.png).hexdigest(),
                "mediaType": "image/png", "byteSize": len(self.png), "width": 2, "height": 2},
            "description": text, "descriptionDigest": sha256(text.encode()).hexdigest(),
            "cameraInstruction": {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"},
            "outputConstraints": deepcopy(OUTPUT), "executionClass": "MICRO_MOTION",
            "executionMethod": "SINGLE_ANCHOR_I2V"}
        self.cost = deepcopy(package["materials"]["costBasis"])
        self.proof_values = {"test-billing": {"testOnly": True, "rate": 5},
            "test-continuing": {"testOnly": True, "storage": 2}}
        self.cost["sourceEvidence"] = [{"ref": "test-billing", "digest": c.digest(self.proof_values["test-billing"])}]
        self.cost["billingResponsibility"]["continuingChargesEvidence"] = {
            "ref": "test-continuing", "digest": c.digest(self.proof_values["test-continuing"])}
        self.cost = c.sealed(self.cost)
        self.stages, self.observations = [], []
        self.input_observations = 0
        self.output_absent, self.runtime_changed, self.tools_changed = True, False, False
        self.held = True
        self.lease = SimpleNamespace(assert_held=self.assert_held)
        self.reader = LiveRuntimeCurrentReader(
            host_observer=self.observe, input_observer=self.input_observe,
            tool_observer=lambda: ({"ffmpegSha256": "f" * 64, "ffprobeSha256": "e" * 64}
                if self.tools_changed else deepcopy(profile["parameters"]["postprocess"]["toolIdentity"])),
        )
        self.cost_owner = SimpleNamespace(read_current=lambda package, lease: deepcopy(self.cost),
            proof_originals=lambda package, lease: tuple(VerifiedOriginalObservation(
                "V4_BACKEND_CONFIG", "CostEvidence", ref, deepcopy(value))
                for ref, value in sorted(self.proof_values.items())))
        self.materials = self.new_materials()

    def original(self, name, value):
        path = Path(self.temp.name) / name
        raw = c.canonical(value)
        path.write_bytes(raw)
        return OriginalFile(path, sha256(raw).hexdigest())

    def assert_held(self):
        c.require(self.held, "CURRENTNESS_FENCE_UNAVAILABLE")

    def observe(self, configuration, lease):
        self.assert_held()
        self.observations.append(deepcopy(configuration))
        result = live_runtime(configuration["backendProfile"], configuration["processIdentity"], configuration["executionConfig"])
        if self.runtime_changed:
            result["facts"]["objectInfoDigest"] = c.digest("changed-test-nodes")
            result = c.sealed({**result, "factsDigest": c.digest(result["facts"])})
        return result

    def input_observe(self, configuration, lease):
        self.input_observations += 1
        source = configuration["backendProfile"]["parameters"]["input"]
        return {"inputName": source["imageName"], "contentDigest": source["contentDigest"],
            "inputRootDigest": configuration["executionConfig"]["inputRoot"]["absolutePathDigest"],
            "outputRootDigest": configuration["executionConfig"]["artifactRoot"]["absolutePathDigest"],
            "outputPrefixAbsent": self.output_absent}

    def stage(self, configuration, raw, lease):
        self.assert_held()
        self.stages.append((deepcopy(configuration), raw))
        return {"inputName": configuration["backendProfile"]["parameters"]["input"]["imageName"],
            "contentDigest": sha256(raw).hexdigest(), "mediaType": "image/png", "byteSize": len(raw)}

    def new_materials(self):
        return ImageVideoMaterials(configuration=self.file, runtime_current=self.reader,
            cost_owner=self.cost_owner, stage_input=self.stage, clock=lambda: START)

    def installation_arguments(self):
        policy = c.sealed({"schemaVersion": "v5.user-image-video-policy.v1",
            "policyRef": "test-installed-policy", "authorityRef": "test-installation-owner",
            "scope": deepcopy(self.scope), "credentialActors": {"test-credential": "test-actor"},
            "limits": deepcopy(self.limits), "maxTotalCostMinor": self.limits["maxCostMinor"] * 2,
            "maxGenerations": 2})
        runtime = self.original("installed-runtime.json", live_runtime(
            self.configuration["backendProfile"], self.configuration["processIdentity"],
            self.configuration["executionConfig"]))
        return {"policy": policy, "configuration": self.file, "runtime_original": runtime,
            "runtime_current": self.reader, "cost_owner": self.cost_owner,
            "endpoint_url": "http://127.0.0.1:19091/", "clock": lambda: START}

    def prepare(self):
        return self.materials.prepare_input(self.scope, self.subject, self.png, self.limits, self.lease)

    def test_constructor_has_no_file_network_or_staging_io(self):
        with patch("builtins.open", side_effect=AssertionError("file I/O")), \
                patch("socket.socket", side_effect=AssertionError("network I/O")), \
                patch.object(OriginalFile, "read", side_effect=AssertionError("original read")):
            self.new_materials()
        self.assertEqual((self.stages, self.observations), ([], []))

    def test_read_environment_returns_only_sanitized_current_runtime_facts(self):
        result = self.materials.read_environment(self.lease)
        self.assertEqual(result, {
            "observedAt": START,
            "evidenceClass": "CURRENT_RUNTIME_OBSERVATION",
            "gpuCount": 1,
            "deviceType": "cuda",
            "comfyuiVersion": "0.35.0",
        })
        self.assertEqual(len(self.observations), 1)
        self.assertEqual(self.input_observations, 0)
        self.assertEqual(self.stages, [])
        self.assertNotIn("endpoint", result)
        self.assertNotIn("modelFiles", result)

    def test_typed_host_installation_builder_is_inert_and_has_no_default_policy(self):
        from services.v5_core_os.episode_production.image_video import ImageVideoInstallation
        arguments = self.installation_arguments()
        with patch.object(OriginalFile, "read", side_effect=AssertionError("original read")), \
                patch("socket.socket", side_effect=AssertionError("network I/O")):
            result = create_image_video_installation(**arguments)
            self.assertIs(type(result), ImageVideoInstallation)
            result.validate()
            with self.assertRaises(c.DispatchError):
                create_image_video_installation(**{**arguments, "policy": {}})
        self.assertEqual((self.stages, self.observations), ([], []))

    def test_host_stager_reuses_existing_transport_with_actual_original_file_pin(self):
        arguments = self.installation_arguments()
        self.materials = create_image_video_installation(**arguments).materials
        calls = []

        def upload(raw, digest, *, deadline_monotonic, authorize):
            import time
            self.assertGreater(deadline_monotonic, time.monotonic())
            self.assertEqual(digest, sha256(self.png).hexdigest())
            self.assertEqual(raw, self.png)
            self.assertEqual(len(self.observations), 1)
            self.assertEqual(self.observations[0], self.configuration)
            for phase in ("INPUT_CONNECT", "INPUT_WRITE", "INPUT_VERIFY", "INPUT_VERIFIED"):
                authorize(phase)
            calls.append(digest)
            return {"inputName": "acs-user-image-video/" + digest + ".png",
                "contentDigest": digest, "mediaType": "image/png", "byteSize": len(raw)}

        with patch("services.v4_platform.comfyui_staged_transport._bind_staged_transport",
                return_value=SimpleNamespace(upload_input_png=upload)) as bind:
            result = self.prepare()
        self.assertEqual(calls, [sha256(self.png).hexdigest()])
        self.assertEqual(bind.call_args.args, (arguments["endpoint_url"],))
        self.assertEqual(bind.call_args.kwargs["runtime_binding"], {
            "instanceRef": self.configuration["processIdentity"]["instanceRef"],
            "processIdentityDigest": c.digest(self.configuration["processIdentity"]),
            "attestationFileSha256": arguments["runtime_original"].file_sha256})
        self.assertEqual(bind.call_args.kwargs["execution_config"], self.configuration["executionConfig"])
        self.assertNotEqual(result["runtime"]["attestation_file_sha256"], arguments["runtime_original"].file_sha256)
        self.assertEqual(len(self.observations), 2)

    def test_host_stager_rejects_current_runtime_drift_and_unreadable_original_before_binding(self):
        arguments = self.installation_arguments()
        self.materials = create_image_video_installation(**arguments).materials
        with patch("services.v4_platform.comfyui_staged_transport._bind_staged_transport") as bind:
            self.runtime_changed = True
            with self.assertRaises(c.DispatchError):
                self.prepare()
            self.runtime_changed = False
            arguments["runtime_original"].path.write_bytes(b"{}")
            with self.assertRaises(c.DispatchError):
                self.prepare()
            bind.assert_not_called()

    def test_host_stager_rechecks_window_at_input_write_and_rejects_retargeted_endpoint(self):
        arguments = self.installation_arguments()
        now = [START]
        arguments["clock"] = lambda: now[0]
        self.materials = create_image_video_installation(**arguments).materials

        def upload(raw, digest, *, deadline_monotonic, authorize):
            now[0] = self.limits["expiresAt"]
            authorize("INPUT_WRITE")
            self.fail("expired policy must not write input")

        with patch("services.v4_platform.comfyui_staged_transport._bind_staged_transport",
                return_value=SimpleNamespace(upload_input_png=upload)):
            with self.assertRaises(c.DispatchError) as caught:
                self.prepare()
            self.assertEqual(caught.exception.code, "OUTSIDE_VALIDITY_WINDOW")
        now[0] = START
        with patch("socket.socket", side_effect=AssertionError("network I/O")):
            with self.assertRaises(ValueError):
                self.prepare()

    def test_precise_subject_profile_snapshot_preserves_template_and_json_roundtrip(self):
        original_bytes = self.file.path.read_bytes()
        result = self.prepare()
        profile = result["backend"]["profile"]
        expected = deepcopy(self.configuration["backendProfile"])
        expected["parameters"]["positivePrompt"] = self.subject["description"]
        expected["parameters"]["input"] = {"imageName": "acs-user-image-video/" + sha256(self.png).hexdigest() + ".png", "contentDigest": sha256(self.png).hexdigest()}
        expected["parameters"]["nativeOutput"]["filenamePrefix"] = "acs-user-image-video/test-user-generation"
        self.assertEqual(profile, expected)
        self.assertEqual(result["backend"]["execution_config"], self.configuration["executionConfig"])
        self.assertEqual(result["backend"]["execution_code"], self.configuration["executionCode"])
        self.assertEqual(self.file.path.read_bytes(), original_bytes)
        self.assertEqual(c.strict_json(c.canonical(result)), result)
        self.assertEqual(len(result["proofOriginals"]), 7)
        self.assertEqual(len(self.stages), 1)

    def test_verify_current_rereads_authorities_but_never_restages(self):
        result = self.prepare()
        self.assertEqual(self.materials.verify_current(result, self.scope, self.subject, self.limits, self.lease), result)
        self.assertEqual(len(self.stages), 1)
        self.assertEqual(len(self.observations), 2)

    def test_bad_input_digest_and_released_lease_reject_before_staging(self):
        with self.assertRaises(c.DispatchError):
            self.materials.prepare_input(self.scope, self.subject, self.png + b"x", self.limits, self.lease)
        self.held = False
        with self.assertRaises(c.DispatchError):
            self.prepare()
        self.assertEqual(self.stages, [])

    def test_cost_proof_and_budget_failure_precede_input_upload(self):
        self.cost["fixedCostMinor"] = self.limits["maxCostMinor"] + 1
        self.cost = c.sealed(self.cost)
        with self.assertRaises(c.DispatchError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "COST_BOUND_UNVERIFIED")
        self.assertEqual(self.stages, [])

    def test_missing_cost_original_fails_before_staging(self):
        self.proof_values.pop("test-continuing")
        with self.assertRaises(c.DispatchError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.code, "COST_BOUND_UNVERIFIED")
        self.assertEqual(self.stages, [])

    def test_expired_or_not_yet_valid_window_rejects_before_staging(self):
        for now in ("2029-12-31T23:59:59.000000Z", self.limits["expiresAt"]):
            with self.subTest(now=now):
                self.materials._clock = lambda: now
                with self.assertRaises(c.DispatchError) as caught:
                    self.prepare()
                self.assertEqual(caught.exception.code, "OUTSIDE_VALIDITY_WINDOW")
                self.assertEqual(self.stages, [])

    def test_runtime_node_or_encoding_tool_drift_rejects_verification(self):
        result = self.prepare()
        self.runtime_changed = True
        with self.assertRaises(c.DispatchError) as caught:
            self.materials.verify_current(result, self.scope, self.subject, self.limits, self.lease)
        self.assertEqual(caught.exception.code, "RUNTIME_CHANGED")
        self.runtime_changed, self.tools_changed = False, True
        with self.assertRaises(c.DispatchError) as caught:
            self.materials.verify_current(result, self.scope, self.subject, self.limits, self.lease)
        self.assertEqual(caught.exception.code, "RUNTIME_CHANGED")
        self.assertEqual(len(self.stages), 1)

    def test_output_collision_or_changed_template_is_closed(self):
        result = self.prepare()
        self.output_absent = False
        with self.assertRaises(c.DispatchError) as caught:
            self.materials.verify_current(result, self.scope, self.subject, self.limits, self.lease)
        self.assertEqual(caught.exception.code, "SOURCE_CHANGED")
        self.output_absent = True
        self.file.path.write_bytes(b'{}')
        with self.assertRaises(c.DispatchError):
            self.materials.verify_current(result, self.scope, self.subject, self.limits, self.lease)
        self.assertEqual(len(self.stages), 1)

    def test_snapshot_tamper_and_different_subject_do_not_rebind_original(self):
        result = self.prepare()
        tampered = deepcopy(result)
        tampered["runtime"]["attestation_file_sha256"] = "0" * 64
        with self.assertRaises(c.DispatchError):
            self.materials.verify_current(tampered, self.scope, self.subject, self.limits, self.lease)
        changed = {**self.subject, "generationRef": "different-generation"}
        with self.assertRaises(c.DispatchError):
            self.materials.verify_current(result, self.scope, changed, self.limits, self.lease)
        self.assertEqual(len(self.stages), 1)


if __name__ == "__main__":
    unittest.main()
