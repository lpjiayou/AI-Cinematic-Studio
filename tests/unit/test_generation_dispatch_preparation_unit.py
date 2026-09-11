"""Closed prepare and original pure compiler parity, without source mocks."""
from copy import deepcopy
import unittest

from services.v4_platform.generation_dispatch_compiler import compile_generation_dispatch_workflow
from services.v4_platform.backend_registry import BackendValidationError
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_public import GenerationDispatchPublicBoundary
from tests.support.generation_dispatch_fixtures import make_package, SOURCE_TEXT, approval_for, read_set_for
from services.v5_core_os.episode_production.generation_dispatch_readers import (
    VerifiedOriginalObservation, VerifiedOwnerContribution, validate_material_proof_originals)


class GenerationDispatchPreparationUnitTests(unittest.TestCase):
    def setUp(self):
        self.package, _ = make_package()
        plan = self.package["plan"]
        self.command = {"workspaceRef": plan["scope"]["workspaceRef"], "productionRunRef": plan["scope"]["productionRunRef"],
            "methodAwareInputPlanVersionRef": plan["subject"]["methodAwareInputPlanVersion"]["ref"],
            "creativeShotVersionRef": plan["subject"]["creativeShotVersion"]["ref"],
            "beatRef": plan["subject"]["actionExecutionBeat"]["ref"], "inputAssetVersionRef": plan["subject"]["inputAsset"]["assetVersionRef"],
            "backendRef": "test-backend", "executionConfigRef": "test-config", "costBasisRef": "test-cost",
            "limits": deepcopy(plan["limits"])}

    def test_prepare_closed_fields_and_no_client_authority_inputs(self):
        self.assertEqual(c.validate_command("PREPARE", self.command), self.command)
        for key in self.command:
            value = deepcopy(self.command); value.pop(key)
            with self.subTest(missing=key), self.assertRaises(c.DispatchError):
                c.validate_command("PREPARE", value)
        for key in ("approved", "now", "coverage", "planPackage", "dispatchGrantBinding", "callback"):
            with self.subTest(extra=key), self.assertRaises(c.DispatchError):
                c.validate_command("PREPARE", {**self.command, key: True})

    def test_default_composition_refuses_without_writes_or_send(self):
        result = GenerationDispatchPublicBoundary().prepare(self.command)
        self.assertEqual((result["code"], result["writesCommitted"], result["sendPermission"]),
            ("CURRENTNESS_FENCE_UNAVAILABLE", 0, "NONE"))

    def test_full_graph_matches_original_adapter_pure_compiler(self):
        p, m = self.package["plan"], self.package["materials"]
        subject = p["subject"]
        actual = compile_generation_dispatch_workflow(
            generation_request_ref="generation-request-" + c.digest(c.request_identity(p)),
            source_text=SOURCE_TEXT, camera_instruction=subject["cameraInstruction"],
            source_asset={k: v for k, v in subject["inputAsset"].items() if k != "inputRole"},
            backend_profile=m["backendProfile"], output_constraints=subject["outputConstraints"])
        # make_package's workflow uses the original adapter method and all
        # original model/parameter/input/output values, with no adapter instance.
        self.assertEqual(actual, m["workflow"])
        self.assertEqual(c.digest(actual), p["executionBinding"]["workflowDigest"])

    def test_no_default_limits_or_bool_integer(self):
        for key in self.command["limits"]:
            changed = deepcopy(self.command); changed["limits"].pop(key)
            with self.subTest(missing=key), self.assertRaises(c.DispatchError):
                c.validate_command("PREPARE", changed)
        for key in ("maxCostMinor", "executionTimeoutSeconds", "maxAttempts"):
            changed = deepcopy(self.command); changed["limits"][key] = True
            with self.subTest(bool=key), self.assertRaises(c.DispatchError):
                c.validate_command("PREPARE", changed)


class GenerationDispatchProofCompletenessTests(unittest.TestCase):
    def fixture(self, phase="PREPARE"):
        package, attestation = make_package()
        cost = package["materials"]["costBasis"]
        originals = {
            "test-billing-a": {"TEST_ONLY": True, "currency": cost["currency"],
                               "fixedCostMinor": cost["fixedCostMinor"]},
            "test-billing-b": {"TEST_ONLY": True, "currency": cost["currency"],
                               "computeUnitSeconds": cost["computeUnitSeconds"],
                               "computeUnitCostMinor": cost["computeUnitCostMinor"]},
            "test-continuing-proof": {"TEST_ONLY": True,
                                      "powerStopOwnerRef": cost["billingResponsibility"]["powerStopOwnerRef"],
                                      "dataRetentionOwnerRef": cost["billingResponsibility"]["dataRetentionOwnerRef"]},
        }
        cost["sourceEvidence"] = [{"ref": ref, "digest": c.digest(originals[ref])}
                                  for ref in ("test-billing-a", "test-billing-b")]
        cost["billingResponsibility"]["continuingChargesEvidence"] = {
            "ref": "test-continuing-proof", "digest": c.digest(originals["test-continuing-proof"])}
        package["materials"]["costBasis"] = cost = c.sealed(cost)
        package["plan"]["executionBinding"]["costBasis"] = {"ref": cost["costBasisRef"], "digest": cost["payloadDigest"]}
        # Independent literal roles and digests from originals, not required_read_set_proofs.
        expected = [{"owner": "RUNTIME_PROCESS", "objectKind": "RuntimeAttestation",
                     "objectRef": attestation["attestationRef"], "objectDigest": attestation["payloadDigest"]}]
        expected.extend({"owner": "V4_BACKEND_CONFIG", "objectKind": "CostEvidence",
                         "objectRef": ref, "objectDigest": c.digest(original)}
                        for ref, original in originals.items())
        expected.sort(key=self.key)
        read_set = read_set_for(package, approval_for(package), c.digest("test-proof-epoch"), phase)
        read_set["objects"] = sorted(read_set["objects"] + deepcopy(expected), key=self.key)
        return package, attestation, originals, expected, read_set

    @staticmethod
    def key(obj):
        return obj["owner"], obj["objectKind"], obj["objectRef"]

    def assert_code(self, code, call, *args):
        with self.assertRaises(c.DispatchError) as error:
            call(*args)
        self.assertEqual(error.exception.code, code)

    def test_full_package_proofs_match_independent_originals_in_both_phases(self):
        for phase, count in (("PREPARE", 15), ("ISSUE", 16)):
            with self.subTest(phase=phase):
                package, _, _, expected, read_set = self.fixture(phase)
                before = deepcopy((package, read_set))
                self.assertEqual(c.required_read_set_proofs(package), expected)
                c.validate_read_set_proof_bindings(read_set, package)
                self.assertEqual(len(read_set["selectors"]), count)
                self.assertEqual((package, read_set), before)

    def test_each_required_proof_and_nonfirst_source_cannot_be_replaced_or_omitted(self):
        package, _, _, expected, read_set = self.fixture()
        for proof in expected:
            for fault in ("omit", "owner", "kind", "ref", "digest", "same_count_unrelated"):
                with self.subTest(proof=proof["objectRef"], fault=fault):
                    changed = deepcopy(read_set)
                    target = next(o for o in changed["objects"] if self.key(o) == self.key(proof))
                    if fault == "omit": changed["objects"].remove(target)
                    elif fault == "owner": target["owner"] = "V5_SCRIPT"
                    elif fault == "kind": target["objectKind"] = "UnrelatedKind"
                    elif fault in ("ref", "same_count_unrelated"): target["objectRef"] = "test-unrelated-original"
                    else: target["objectDigest"] = c.digest("test-wrong-digest")
                    changed["objects"].sort(key=self.key)
                    self.assert_code("SOURCE_CHANGED", c.validate_read_set_proof_bindings, changed, package)

    def test_duplicate_keys_bad_sort_and_conflicting_representation_reject(self):
        package, _, _, expected, read_set = self.fixture()
        duplicate = deepcopy(read_set)
        duplicate["objects"].append(deepcopy(expected[0]))
        duplicate["objects"].sort(key=self.key)
        self.assert_code("INVALID_CLOSED_SCHEMA", c.validate_read_set_proof_bindings, duplicate, package)
        unordered = deepcopy(read_set); unordered["objects"].reverse()
        self.assert_code("INVALID_CLOSED_SCHEMA", c.validate_read_set_proof_bindings, unordered, package)
        conflict = deepcopy(read_set)
        conflict["objects"].append({**expected[0], "objectKind": "OtherRepresentation", "objectDigest": c.digest("conflict")})
        conflict["objects"].sort(key=self.key)
        self.assert_code("SOURCE_CHANGED", c.validate_read_set_proof_bindings, conflict, package)

    def test_shared_cost_original_is_one_requirement_but_conflicting_pin_rejects(self):
        package, _, _, expected, read_set = self.fixture()
        cost = package["materials"]["costBasis"]
        cost["billingResponsibility"]["continuingChargesEvidence"] = deepcopy(cost["sourceEvidence"][1])
        package["materials"]["costBasis"] = cost = c.sealed(cost)
        package["plan"]["executionBinding"]["costBasis"]["digest"] = cost["payloadDigest"]
        # Old costBasis object belongs to the prior package; rebuild only that fixture row.
        for o in read_set["objects"]:
            if o["objectRef"] == cost["costBasisRef"]: o["objectDigest"] = cost["payloadDigest"]
        shared_expected = [o for o in expected if o["objectRef"] != "test-continuing-proof"]
        self.assertEqual(c.required_read_set_proofs(package), shared_expected)
        read_set["objects"] = [o for o in read_set["objects"] if o["objectRef"] != "test-continuing-proof"]
        c.validate_read_set_proof_bindings(read_set, package)
        cost["billingResponsibility"]["continuingChargesEvidence"]["digest"] = c.digest("contradictory")
        package["materials"]["costBasis"] = cost = c.sealed(cost)
        package["plan"]["executionBinding"]["costBasis"]["digest"] = cost["payloadDigest"]
        self.assert_code("SOURCE_CHANGED", c.required_read_set_proofs, package)

    def test_extra_valid_objects_preserved_and_historical_plan_check_stays_distinct(self):
        package, _, _, expected, read_set = self.fixture()
        read_set["objects"].append({"owner": "V4_BACKEND_CONFIG", "objectKind": "IndependentExtra",
                                    "objectRef": "test-extra", "objectDigest": c.digest({"TEST_ONLY": True})})
        read_set["objects"].sort(key=self.key)
        before = deepcopy(read_set)
        c.validate_read_set_proof_bindings(read_set, package)
        self.assertEqual(read_set, before)
        legacy = deepcopy(read_set)
        legacy["objects"] = [o for o in legacy["objects"] if o not in expected]
        c.validate_read_set_bindings(legacy, package["plan"], None)
        self.assert_code("SOURCE_CHANGED", c.validate_read_set_proof_bindings, legacy, package)

    def test_originals_required_and_attestation_payload_is_not_file_sha(self):
        package, attestation, originals, expected, read_set = self.fixture()
        observations = [VerifiedOriginalObservation("RUNTIME_PROCESS", "RuntimeAttestation",
                         attestation["attestationRef"], attestation, "payloadDigest")]
        observations.extend(VerifiedOriginalObservation("V4_BACKEND_CONFIG", "CostEvidence", ref, original)
                            for ref, original in originals.items())
        contribution = VerifiedOwnerContribution(tuple(observations), {})
        validate_material_proof_originals(contribution, package)
        file_sha = package["plan"]["executionBinding"]["runtimeBinding"]["attestationFileSha256"]
        self.assertNotEqual(file_sha, attestation["payloadDigest"])
        bad = deepcopy(read_set)
        next(o for o in bad["objects"] if o["objectKind"] == "RuntimeAttestation")["objectDigest"] = file_sha
        self.assert_code("SOURCE_CHANGED", c.validate_read_set_proof_bindings, bad, package)
        for fault in ("missing", "pin_only", "empty"):
            values = list(observations)
            original = values.pop()
            if fault != "missing":
                value = {} if fault == "empty" else {"ref": original.object_ref, "digest": original.as_object()["objectDigest"]}
                values.append(VerifiedOriginalObservation(original.owner, original.object_kind, original.object_ref, value))
            with self.subTest(fault=fault):
                self.assert_code("SOURCE_CHANGED", validate_material_proof_originals,
                                 VerifiedOwnerContribution(tuple(values), {}), package)
