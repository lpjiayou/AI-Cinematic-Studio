"""R3 version separation, source preimages and closed request/result contracts."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest
from services.v4_platform.backend_registry import digest, canonical
from services.v4_platform.comfyui_a14b_sources import historical_digest_map
from services.v4_platform.generation_dispatch_a14b_exact import (
    EXACT_REQUEST_SCHEMA, EXACT_DERIVATION_SCHEMA, validate_exact_derivation, validate_exact_request_binding)
from tests.support.generation_dispatch_exact_fixtures import exact_profile


class ExactContractTests(unittest.TestCase):
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
