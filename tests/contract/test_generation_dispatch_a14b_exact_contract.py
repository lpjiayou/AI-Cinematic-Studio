"""R3 version separation, source preimages and closed request/result contracts."""
from copy import deepcopy
from hashlib import sha256
import ast
import json
from pathlib import Path
import unittest
from services.v4_platform.backend_registry import digest, canonical
from services.v4_platform.comfyui_a14b_sources import historical_digest_map
from services.v4_platform.generation_dispatch_a14b_exact import (
    EXACT_REQUEST_SCHEMA, EXACT_DERIVATION_SCHEMA, EXACT_ADAPTER_IDENTITY,
    EXACT_CAPABILITY, compile_exact_workflow, validate_exact_derivation,
    validate_exact_request_binding)
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.generation_dispatch_exact_fixtures import exact_profile, exact_runtime
from tests.support.generation_dispatch_fixtures import make_package


def _exact_plan_package(*, offline_candidate=False, endpoint_class="TEST_ONLY_LOOPBACK"):
    """Pure synthetic package: no adapter, listener, approval or Grant execution."""
    package, _ = make_package()
    plan, materials = package["plan"], package["materials"]
    binding = plan["executionBinding"]
    profile = exact_profile(plan["subject"]["inputAsset"]["contentDigest"])
    if offline_candidate:
        profile["parameters"].update(evidenceClass="OFFLINE_SOURCE_CANDIDATE",
            cameraDisposition="PROPOSED_PENDING_OWNER_ACCEPTANCE")
    materials["backendProfile"] = profile
    process = materials["processIdentity"]
    process["comfyuiCommit"] = profile["parameters"]["comfyuiCommit"]
    attestation = exact_runtime(profile, process, materials["executionConfig"])
    attestation["facts"]["endpointClass"] = endpoint_class
    attestation["factsDigest"] = digest(attestation["facts"])
    attestation["payloadDigest"] = digest({k: v for k, v in attestation.items() if k != "payloadDigest"})
    decision = binding["backendDecision"]
    decision.update(adapterIdentity=EXACT_ADAPTER_IDENTITY, adapterCapability=EXACT_CAPABILITY,
        endpointClass=endpoint_class, backendProfileRef="test-exact-profile",
        backendProfileDigest=digest(profile), runtimeAttestationRef=attestation["attestationRef"],
        runtimeAttestationDigest=attestation["payloadDigest"])
    binding.update(backendDecisionDigest=digest(decision),
        executionProfile={"ref": decision["backendProfileRef"], "digest": digest(profile)},
        runtimeBinding={"instanceRef": process["instanceRef"], "processIdentityDigest": digest(process),
            "attestationFileSha256": sha256(canonical(attestation)).hexdigest()})
    binding["executionCode"]["comfyuiCommit"] = process["comfyuiCommit"]
    materials["workflow"] = compile_exact_workflow(
        generation_request_ref="generation-request-" + digest(c.request_identity(plan)),
        source_asset={k: v for k, v in plan["subject"]["inputAsset"].items() if k != "inputRole"},
        backend_profile=profile, output_constraints=plan["subject"]["outputConstraints"])
    binding["workflowDigest"] = digest(materials["workflow"])
    return package


class ExactContractTests(unittest.TestCase):
    def test_real_validator_accepts_complete_test_only_v2_package(self):
        package = _exact_plan_package()
        result = c.validate_plan_package(package)
        self.assertEqual(result, package)
        self.assertIsNot(result, package)
        self.assertEqual(package["materials"]["backendProfile"]["parameters"]["evidenceClass"], "TEST_ONLY")

    def test_real_validator_rejects_offline_candidate_with_dispatch_approval_error(self):
        package = _exact_plan_package(offline_candidate=True)
        params = package["materials"]["backendProfile"]["parameters"]
        self.assertEqual((params["evidenceClass"], params["cameraDisposition"]),
            ("OFFLINE_SOURCE_CANDIDATE", "PROPOSED_PENDING_OWNER_ACCEPTANCE"))
        before = deepcopy(package)
        with self.assertRaises(c.DispatchError) as caught:
            c.validate_plan_package(package)
        self.assertIs(type(caught.exception), c.DispatchError)
        self.assertEqual(caught.exception.code, "APPROVAL_UNAVAILABLE")
        self.assertEqual(package, before)

    def test_real_validator_rejects_non_test_endpoint_with_dispatch_approval_error(self):
        package = _exact_plan_package(endpoint_class="TEST_SYNTHETIC_NON_LOOPBACK")
        self.assertEqual(package["materials"]["backendProfile"]["parameters"]["evidenceClass"], "TEST_ONLY")
        before = deepcopy(package)
        with self.assertRaises(c.DispatchError) as caught:
            c.validate_plan_package(package)
        self.assertIs(type(caught.exception), c.DispatchError)
        self.assertEqual(caught.exception.code, "APPROVAL_UNAVAILABLE")
        self.assertEqual(package, before)

    def test_all_literal_require_error_codes_are_registered(self):
        tree = ast.parse(Path(c.__file__).read_text(encoding="utf-8-sig"))
        codes = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "require":
                continue
            arguments = list(node.args[1:2]) + [kw.value for kw in node.keywords if kw.arg == "code"]
            for code in arguments:
                if isinstance(code, ast.Constant) and isinstance(code.value, str):
                    codes.append((node.lineno, code.value))
        self.assertTrue(codes, "The scan must inspect actual production require calls")
        self.assertEqual([(line, code) for line, code in codes if code not in c.ERROR_CODES], [])

    def test_historical_argv_and_ordered_models_keep_separate_preimages(self):
        profile=exact_profile(); models=[]; roles=[]
        for index,m in enumerate(profile["modelFiles"]):
            role="source-role-"+str(index)
            models.append({"MODEL_ROLE":role,"FILE_SHA256":m["sha256"],"FILE_SIZE_BYTES":m["sizeBytes"],"COMFYUI_PATH":"models/"+m["name"]})
            roles.append({"runtimeManifestRole":role,"engineeringRole":m["role"],"name":m["name"],"sha256":m["sha256"],"sizeBytesAsRecorded":m["sizeBytes"]})
        ordered=[{k:m[k] for k in ("MODEL_ROLE","FILE_SHA256","FILE_SIZE_BYTES")} for m in models]
        runtime={"CANONICAL_LAUNCH_ARGV":["test-python","test-main"],"LAUNCH_CONFIG_DIGEST":sha256(b"test-python\x1ftest-main").hexdigest(),
            "COMFYUI_COMMIT":"test-historical-commit","INSTANCE_REF":"test-historical-instance","HOST_BOOT_ID_DIGEST":"a"*64,
            "PID_NAMESPACE_ID_DIGEST":"b"*64,"COMFYUI_PID":1,"PROCESS_START_TICKS":"1","CANONICAL_VENV":None,
            "CANONICAL_VENV_NOTE":"test no independent venv","CANONICAL_PYTHON":"test-python"}
        literal=json.dumps({"TEST_ONLY":"synthetic"},sort_keys=True,separators=(",",":"))
        preimages={"STRUCTURED_DIGESTS":[{"digest":"CANONICAL_ENVIRONMENT_PROJECTION.PROJECTION_DIGEST",
            "preimageLiteral":literal,"recordedValue":sha256(literal.encode()).hexdigest()}]}
        model_manifest={"models":models,"MODEL_SET_DIGEST":digest(ordered)}
        args=(canonical(runtime),canonical(preimages),canonical(model_manifest),roles)
        result=historical_digest_map(*args)
        self.assertNotEqual(result["sourceLaunchDigest"],result["contractLaunchDigest"])
        self.assertNotEqual(result["sourceModelSetDigest"],result["contractModelSetDigest"])
        self.assertFalse(result["isRuntimeAttestation"])
        self.assertFalse(result["modelBytesVerifiedLocally"])
        self.assertEqual(result["currentness"],"NOT_OBSERVED")
        model_manifest["models"].reverse()
        with self.assertRaises(ValueError): historical_digest_map(args[0],args[1],canonical(model_manifest),roles)
        with self.assertRaises(ValueError): historical_digest_map(args[0],canonical({"STRUCTURED_DIGESTS":[]}),args[2],roles)

    def test_complete_encoding_derivation_tampering_and_downgrade_rejected(self):
        config=exact_profile()["parameters"]["postprocess"]
        native=[{"testIndex":i} for i in range(49)]
        value={"schemaVersion":EXACT_DERIVATION_SCHEMA,"profileId":config["profileId"],"nativeSequenceDigest":digest(native),
            "keptIndices":list(range(48)),"droppedIndices":[48],"frameRate":24,"width":704,"height":1280,"frameCount":48,
            "outputSha256":"c"*64,"encoding":config,"encodingDigest":digest(config),
            "sourceToTemporaryToOutput":[[i+1,i,i] for i in range(48)]}
        self.assertEqual(validate_exact_derivation(value,native,"c"*64),value)
        for key,val in (("encodingDigest","d"*64),("sourceToTemporaryToOutput",[]),("schemaVersion","v4.generation-dispatch-frame-derivation.v1")):
            changed=deepcopy(value);changed[key]=val
            with self.assertRaises(ValueError):validate_exact_derivation(changed,native,"c"*64)
