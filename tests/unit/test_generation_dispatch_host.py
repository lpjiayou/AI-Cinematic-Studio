"""D1 host configuration checks are offline, explicit and fail closed."""
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from apps.creator_workspace_mvp.generation_dispatch_operator import main
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_host import D1OperatorHost
from services.v5_core_os.episode_production.generation_dispatch_live_sources import OriginalFile, PinnedCostOriginal
from services.v4_platform.generation_dispatch_a14b_live import LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS
from tests.support.generation_dispatch_fixtures import make_package
from tests.unit.test_generation_dispatch_d1_live import live_profile


class HostBindingTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        # Header inspection only: this fixture is not an actual render or decoder test.
        image = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (704).to_bytes(4, "big") + (1280).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"\x00" * 4
        self.image = self.file("test.png", image)
        package, _ = make_package()
        self.config = {k: package["materials"][k] for k in ("executionConfig", "processIdentity")}
        self.config.update({k: package["plan"]["executionBinding"][k] for k in ("executionCode", "backendDecision")})
        self.config["backendProfile"] = live_profile(self.image.file_sha256)
        self.config["backendDecision"].update(adapterIdentity=LIVE_ADAPTER_IDENTITY, adapterCapability=LIVE_CAPABILITY,
            endpointClass=LIVE_ENDPOINT_CLASS, backendProfileDigest=c.digest(self.config["backendProfile"]))
        self.configuration = self.file("config.json", c.canonical(self.config))

    def file(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        return OriginalFile(path, sha256(raw).hexdigest())

    def host(self, **kwargs):
        return D1OperatorHost(configuration=self.configuration, input_image=self.image, **kwargs)

    def test_construct_help_and_check_offline_have_no_file_network_or_store_io(self):
        with patch.object(OriginalFile, "read", side_effect=AssertionError("file IO forbidden")), \
                patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("sqlite3.connect", side_effect=AssertionError("stores forbidden")), redirect_stdout(StringIO()):
            host = self.host()
            self.assertEqual(main(["check-offline"], host=host), 0)
            with self.assertRaises(SystemExit) as stopped:
                main(["--help"], host=host)
            self.assertEqual(stopped.exception.code, 0)

    def test_explicit_input_check_reports_exact_missing_ports_without_fabricating_plan(self):
        host = self.host()
        with patch("socket.socket", side_effect=AssertionError("network forbidden")), \
                patch("sqlite3.connect", side_effect=AssertionError("stores forbidden")):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["check-inputs"], host=host), 0)
            result = json.loads(output.getvalue())
            self.assertTrue(result["inputBytesMatched"])
            self.assertEqual(result["inputContentDigest"], self.image.file_sha256)
            self.assertEqual(result["modelRoleCount"], 6)
            self.assertEqual(result["sendPermission"], "NONE")
            self.assertNotIn("planPackage", result)
            self.assertIn("runtime_current", result["missingBindings"])
            for kind in c.PREREQUISITES:
                self.assertIn("prerequisite_original:" + kind, result["missingBindings"])
            with self.assertRaises(c.DispatchError) as stopped:
                host.deployment()
            self.assertEqual(stopped.exception.code, "CURRENTNESS_FENCE_UNAVAILABLE")

    def test_wrong_pin_invalid_header_and_profile_input_mismatch_are_rejected(self):
        cases = []
        cases.append(OriginalFile(self.image.path, "f" * 64))
        raw = self.image.path.read_bytes()
        for image in cases:
            with self.subTest(image=image.path.name), self.assertRaises(c.DispatchError) as stopped:
                D1OperatorHost(configuration=self.configuration, input_image=image).check_inputs()
            self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
        for image in (self.file("zero-dimension.png", raw[:16] + (0).to_bytes(4, "big") + raw[20:]),
                self.file("not-png.png", b"not a png")):
            config = deepcopy(self.config)
            config["backendProfile"]["parameters"]["input"]["contentDigest"] = image.file_sha256
            config["backendDecision"]["backendProfileDigest"] = c.digest(config["backendProfile"])
            with self.subTest(image=image.path.name), self.assertRaises(c.DispatchError) as stopped:
                D1OperatorHost(configuration=self.file("invalid-header.json", c.canonical(config)), input_image=image).check_inputs()
            self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")
        config = deepcopy(self.config)
        config["backendProfile"]["parameters"]["input"]["contentDigest"] = "e" * 64
        config["backendDecision"]["backendProfileDigest"] = c.digest(config["backendProfile"])
        with self.assertRaises(c.DispatchError) as stopped:
            D1OperatorHost(configuration=self.file("wrong-input.json", c.canonical(config)), input_image=self.image).check_inputs()
        self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")

    def test_bound_input_size_is_not_confused_with_model_output_size(self):
        raw = self.image.path.read_bytes()
        image = self.file("resizable.png", raw[:16] + (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + raw[24:])
        config = deepcopy(self.config)
        config["backendProfile"]["parameters"]["input"]["contentDigest"] = image.file_sha256
        config["backendDecision"]["backendProfileDigest"] = c.digest(config["backendProfile"])
        result = D1OperatorHost(configuration=self.file("resizable.json", c.canonical(config)), input_image=image).check_inputs()
        self.assertEqual((result["inputWidth"], result["inputHeight"]), (1, 1))
        self.assertEqual((result["outputWidth"], result["outputHeight"]), (704, 1280))

    def test_symlink_or_replaced_input_is_rejected(self):
        alias = self.root / "alias.png"
        alias.symlink_to(self.image.path)
        with self.assertRaises(c.DispatchError):
            D1OperatorHost(configuration=self.configuration, input_image=OriginalFile(alias, self.image.file_sha256)).check_inputs()
        self.image.path.write_bytes(b"replacement")
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["check-inputs"], host=self.host()), 2)
        self.assertEqual(json.loads(output.getvalue())["reason"], "PINNED_INPUT_VALIDATION_FAILED")

    def test_cli_has_no_host_file_factory_or_endpoint_arguments(self):
        from contextlib import redirect_stderr
        for argument in ("--host", "--factory", "--endpoint", "--approved"):
            with self.subTest(argument=argument), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["prepare", argument, "untrusted"])
        with redirect_stdout(StringIO()):
            self.assertEqual(main(["prepare"], host={}, deployment=Mock()), 2)


class CostOriginalTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        package, _ = make_package()
        self.cost = deepcopy(package["materials"]["costBasis"])
        self.proof_values = {"test-billing": {"testOnly": True, "rate": 698},
            "test-continuing": {"testOnly": True, "storageDaily": 300, "continuesAfterShutdown": True}}
        self.cost["sourceEvidence"] = [{"ref": "test-billing", "digest": c.digest(self.proof_values["test-billing"])}]
        self.cost["billingResponsibility"]["continuingChargesEvidence"] = {
            "ref": "test-continuing", "digest": c.digest(self.proof_values["test-continuing"])}
        self.cost = c.sealed(self.cost)
        self.basis = self.file("basis.json", self.cost)
        self.proofs = {ref: self.file(ref + ".json", value) for ref, value in self.proof_values.items()}
        self.lease = SimpleNamespace(assert_held=Mock())

    def file(self, name, value):
        raw = c.canonical(value)
        path = self.root / name
        path.write_bytes(raw)
        return OriginalFile(path, sha256(raw).hexdigest())

    def reader(self, verifier=None, proofs=None, basis=None):
        return PinnedCostOriginal(basis=basis or self.basis, proofs=self.proofs if proofs is None else proofs,
            verifier=verifier or (lambda cost, proofs, package, lease: deepcopy(self.cost)))

    def test_complete_originals_and_owner_are_rechecked_in_existing_cost_evidence_shape(self):
        verifier = Mock(side_effect=lambda cost, proofs, package, lease: deepcopy(self.cost))
        with patch.object(OriginalFile, "read", side_effect=AssertionError("constructor IO")):
            reader = self.reader(verifier=verifier)
        self.assertEqual(reader.read_current({}, self.lease), self.cost)
        observations = reader.proof_originals({}, self.lease)
        self.assertEqual({o.object_kind for o in observations}, {"CostEvidence"})
        self.assertEqual({o.object_ref: o.original for o in observations}, self.proof_values)
        self.assertEqual(verifier.call_count, 2)
        self.proofs["test-billing"].path.write_bytes(b"{}")
        with self.assertRaises(c.DispatchError):
            reader.read_current({}, self.lease)

    def test_missing_continuing_charge_proof_wrong_proof_and_boolean_approval_are_rejected(self):
        readers = [self.reader(proofs={"test-billing": self.proofs["test-billing"]}),
            self.reader(proofs={**self.proofs, "test-billing": self.file("wrong.json", {})}),
            self.reader(verifier=lambda *args: True)]
        for reader in readers:
            with self.subTest(reader=reader), self.assertRaises(c.DispatchError) as stopped:
                reader.read_current({}, self.lease)
            self.assertEqual(stopped.exception.code, "COST_BOUND_UNVERIFIED")

    def test_partial_fee_data_is_not_defaulted_to_zero_and_lease_is_required(self):
        partial = deepcopy(self.cost)
        del partial["transferBoundMinor"]
        with self.assertRaises(c.DispatchError):
            self.reader(basis=self.file("partial.json", c.sealed(partial))).read_current({}, self.lease)
        with patch.object(OriginalFile, "read", side_effect=AssertionError("must refuse before reading")):
            with self.assertRaises(RuntimeError):
                self.reader().read_current({}, SimpleNamespace(assert_held=Mock(side_effect=RuntimeError("lease ended"))))
