"""R3 pure original-topology, candidate/version and hostile source-byte gates."""
from copy import deepcopy
from hashlib import sha256
import io
import json
import stat
import unittest
import zipfile
from unittest.mock import patch
from services.v4_platform.backend_registry import digest
from services.v4_platform.generation_dispatch_a14b_exact import (
    compile_exact_workflow, validate_exact_profile, validate_exact_workflow,
    encoding_profile, exact_readiness)
from services.v4_platform.generation_dispatch_a14b_profile import validate_a14b_profile, A14B_FINAL_OUTPUT
from services.v4_platform.comfyui_a14b_runtime import validate_a14b_runtime_attestation
from services.v4_platform.comfyui_a14b_sources import strict_json, archive_bytes, verify_hash_list, camera_candidate
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_source
from tests.support.generation_dispatch_exact_fixtures import exact_profile, exact_runtime


class ExactProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = exact_profile()
        self.inputs = dict(generation_request_ref="test-request", source_asset=make_a14b_source(),
            backend_profile=self.profile, output_constraints=A14B_FINAL_OUTPUT)

    def test_six_models_full_16_node_graph_and_absent_device(self):
        graph = compile_exact_workflow(**self.inputs)
        self.assertEqual(set(graph), {"1","2","3","4","5","10","11","12","13","20","21","22","30","31","40","41"})
        self.assertNotIn("device", graph["3"]["inputs"])
        self.assertEqual(graph["31"]["inputs"]["latent_image"], ["30", 0])
        self.assertEqual(validate_exact_workflow(graph, **self.inputs), graph)

    def test_recorded_gpu_byte_capacity_is_not_test_only_integer_cap(self):
        self.profile["parameters"]["resourceRequirements"]["minimumVramBytes"] = 96*1024**3
        self.assertEqual(validate_exact_profile(self.profile),self.profile)
        for value in (0, True, 10**12+1):
            self.profile["parameters"]["resourceRequirements"]["minimumVramBytes"] = value
            with self.assertRaises(ValueError): validate_exact_profile(self.profile)

    def test_unknown_missing_node_links_output_and_device_rejected(self):
        original = compile_exact_workflow(**self.inputs)
        for fault in ("extra", "missing", "link", "output", "device"):
            graph = deepcopy(original)
            if fault == "extra": graph["99"] = graph["1"]
            if fault == "missing": del graph["10"]
            if fault == "link": graph["31"]["inputs"]["latent_image"] = ["22", 2]
            if fault == "output": graph["16"] = graph.pop("41")
            if fault == "device": graph["3"]["inputs"]["device"] = "default"
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                validate_exact_workflow(graph, **self.inputs)

    def test_models_pairs_sizes_and_all_sampling_drift(self):
        faults = [lambda p: p["modelFiles"].pop(), lambda p: p["modelFiles"][0].update(sizeBytes=0),
            lambda p: p["modelFiles"][0].update(sha256="f" * 64),
            lambda p: p["parameters"].update(steps=8), lambda p: p["parameters"].update(cfg=2),
            lambda p: p["parameters"].update(samplerName="uni_pc"), lambda p: p["parameters"].update(scheduler="normal")]
        for key, val in (("modelShift",5), ("strengthModel",2), ("startAtStep",1), ("endAtStep",3),
                         ("addNoise","disable"), ("returnWithLeftoverNoise","disable"), ("loraRole","LOW_NOISE_LORA")):
            faults.append(lambda p, key=key, val=val: p["parameters"]["modelPairs"][0].update({key:val}))
        for fault in faults:
            changed = deepcopy(self.profile); fault(changed)
            with self.assertRaises(ValueError): validate_exact_profile(changed)

    def test_complete_encoding_and_old_profile_remain_disjoint(self):
        with self.assertRaises(ValueError): validate_a14b_profile(self.profile)
        for field, val in (("crf",18), ("preset","fast"), ("movflags","+faststart"), ("threads",2),
                           ("sourceStartNumber",0), ("dropIndices",[0]), ("toolIdentity",{})):
            changed = deepcopy(self.profile); changed["parameters"]["postprocess"][field] = val
            with self.subTest(field=field), self.assertRaises(ValueError): validate_exact_profile(changed)
        changed = deepcopy(self.profile); changed["parameters"]["postprocess"]["toolIdentity"]["ffmpegSha256"] = "c" * 64
        self.assertNotEqual(digest(changed), digest(self.profile))

    def test_candidate_readiness_never_approval_or_runtime_currentness(self):
        self.assertFalse(exact_readiness(self.profile)["ready"])
        self.profile["parameters"].update(evidenceClass="OFFLINE_SOURCE_CANDIDATE", cameraDisposition="PROPOSED_PENDING_OWNER_ACCEPTANCE")
        self.assertEqual(exact_readiness(self.profile)["reason"], "CAMERA_PROMPT_APPROVAL_PENDING")
        with self.assertRaises(ValueError): validate_a14b_runtime_attestation(exact_runtime(self.profile), backend_profile=self.profile)

    def test_runtime_version_commit_and_schema_cannot_be_interchanged(self):
        value = exact_runtime(self.profile)
        self.assertEqual(validate_a14b_runtime_attestation(value, backend_profile=self.profile)["comfyuiVersion"], "0.35.0")
        for field in ("comfyuiVersion", "compilerIdentity", "templateRef", "evidenceClass"):
            changed = deepcopy(value); changed["facts"][field] = "invalid"
            changed["factsDigest"] = digest(changed["facts"])
            changed["payloadDigest"] = digest({k:v for k,v in changed.items() if k != "payloadDigest"})
            with self.assertRaises(ValueError): validate_a14b_runtime_attestation(changed, backend_profile=self.profile)

    def test_camera_changes_one_pointer_only(self):
        graph = compile_exact_workflow(**self.inputs)
        graph["20"]["inputs"]["text"] = "TEST_ONLY. Camera: arc. Environment: rain."
        candidate = camera_candidate(graph, "Camera: arc.", "Camera: locked.")
        candidate["20"]["inputs"]["text"] = graph["20"]["inputs"]["text"]
        self.assertEqual(candidate, graph)
        with self.assertRaises(ValueError): camera_candidate(graph, "Camera: missing.", "Camera: locked.")

    def test_local_tool_preflight_cannot_extend_absolute_send_or_execution_deadline(self):
        from services.v4_platform.generation_dispatch_a14b_exact import EXACT_REQUEST_SCHEMA
        from services.v4_platform import comfyui_staged_transport as staged
        from tests.support.comfyui_loopback_fixtures import make_loopback_client
        transport,request=make_loopback_client("http://127.0.0.1:49157/",native_frames=True)
        graph=compile_exact_workflow(**self.inputs)
        request.update(schemaVersion=EXACT_REQUEST_SCHEMA,workflow=graph,workflowDigest=digest(graph),
            postprocessBinding=deepcopy(self.profile["parameters"]["postprocess"]))
        folder,_,prefix=graph["41"]["inputs"]["filename_prefix"].rpartition("/")
        request["outputBinding"].update(nodeId="41",filenamePrefix=prefix,subfolder=folder)
        request["payloadDigest"]=digest({k:v for k,v in request.items() if k!="payloadDigest"})
        for execution,send in ((104,120),(120,104)):
            clock=[100.0]
            def observe():
                clock[0]=105.0
                return request["postprocessBinding"]["toolIdentity"]
            with patch.object(staged.time,"monotonic",side_effect=lambda:clock[0]), \
                 patch("services.v4_platform.generation_dispatch_live_result.encoder_tool_identity",side_effect=observe), \
                 patch("socket.socket",side_effect=AssertionError("socket")), \
                 patch("socket.getaddrinfo",side_effect=AssertionError("DNS")), \
                 patch("threading.Thread.start",side_effect=AssertionError("thread")):
                with self.subTest(execution=execution,send=send),self.assertRaises(TimeoutError):
                    transport.open_exchange(request,deadline_monotonic=execution,send_deadline_monotonic=send)
            self.assertEqual(len(transport._exchanges),0)


class SourceBytesTests(unittest.TestCase):
    @staticmethod
    def archive(name="input.json", raw=b"{}", mode=stat.S_IFREG):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            entry = zipfile.ZipInfo(name); entry.external_attr = (mode | 0o600) << 16
            z.writestr(entry, raw)
        return stream.getvalue()

    def test_zip_hash_traversal_symlink_duplicate_and_missing_fail_closed(self):
        for name,mode in (("../input",stat.S_IFREG), ("/input",stat.S_IFREG), ("input",stat.S_IFLNK), ("C:/input",stat.S_IFREG)):
            raw=self.archive(name,mode=mode)
            with self.assertRaises(ValueError): archive_bytes(raw,sha256(raw).hexdigest())
        raw=self.archive()
        with self.assertRaises(ValueError): archive_bytes(raw,"0"*64)
        with self.assertRaises(ValueError): verify_hash_list(archive_bytes(raw,sha256(raw).hexdigest()))
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z:
            z.writestr("FILE.json",b"{}"); z.writestr("file.json",b"{}")
        raw=stream.getvalue()
        with self.assertRaises(ValueError): archive_bytes(raw,sha256(raw).hexdigest())

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}'):
            with self.assertRaises(ValueError): strict_json(raw)

    def test_hash_list_requires_complete_coverage(self):
        members={"input.json":b"{}", "SHA256SUMS.txt":(sha256(b"{}").hexdigest()+"  input.json\n").encode()}
        self.assertEqual(verify_hash_list(members),["input.json"])
        members["extra.py"]=b"raise AssertionError('never execute')"
        with self.assertRaises(ValueError): verify_hash_list(members)
