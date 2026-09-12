"""R3 original assembly, ephemeral SQLite, owned-loopback and real CPU encoding.

No source archive, GPU service, formal database or production Grant is consumed.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from services.v4_platform.generation_dispatch_live_result import encoder_tool_identity, process_native_frames
from services.v4_platform.generation_dispatch_live_contracts import validate_live_transport_request
from services.v4_platform.backend_registry import digest
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI
from tests.support.generation_dispatch_exact_fixtures import exact_fixture
from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png
from tests.integration import test_generation_dispatch_a14b_cpu as legacy


class ExactCpuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frames = tuple(synthetic_png(i) for i in range(49))
        cls.tools = encoder_tool_identity()

    def test_original_assembly_exact_graph_full_encoding_repeated_cpu_roundtrip(self):
        captured = []
        from services.v4_platform import generation_dispatch_live_result as module
        original = module.process_native_frames
        def observe(frames, native, request, **kwargs):
            captured.append((deepcopy(native), deepcopy(request)))
            return original(frames, native, request, **kwargs)
        # transport imports this function lazily, so interception observes the
        # real validated request after L1/L2 without replacing any authority.
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1) as server:
            fixture = exact_fixture(self, server.endpoint, self.tools)
            with patch.object(module, "process_native_frames", observe):
                saved = fixture.execute()
            self.assertEqual(saved["state"], "SUCCEEDED", saved.get("dispatchResult"))
            self.assertEqual(len(saved["attempts"]), 1)
            self.assertEqual(server.complete_post_count, 1)
            self.assertEqual(server.view_count, 49)
            self.assertIn("41", server.body["prompt"])
            self.assertNotIn("device", server.body["prompt"]["3"]["inputs"])
            self.assertIsNone(saved["artifactCommitIntent"])
            self.assertEqual(fixture.queues[1].get(saved["workspaceRef"], saved["productionRunRef"], saved["jobRef"]), saved)
            artifact = saved["artifact"]
            self.assertIsNone(artifact["providerExecution"]["gpuUsed"])
            self.assertIsNone(artifact["providerExecution"]["costMinor"])
            self.assertFalse(artifact["publicationAllowed"])
            self.assertEqual(saved["dispatchResult"]["derivation"]["encoding"]["crf"], 16)
            legacy.A14BCpuIntegrationTests.assert_original_recovery_no_resend(self, fixture, server)
            self.assertEqual(len(captured), 1)
            native, request = captured[0]
            altered=deepcopy(request)
            altered["postprocessBinding"]["crf"]=18
            altered["payloadDigest"]=digest({k:v for k,v in altered.items() if k != "payloadDigest"})
            with self.assertRaises(ValueError): validate_live_transport_request(altered)
            second, derivation = original(self.frames, native, request, deadline_monotonic=time.monotonic()+30)
            self.assertEqual(sha256(second).hexdigest(), artifact["sha256"])
            self.assertEqual(derivation["sourceToTemporaryToOutput"], [[i+1,i,i] for i in range(48)])
            self.assertEqual([n["sha256"] for n in native], [sha256(f).hexdigest() for f in self.frames])
            self.assertNotEqual(derivation["nativeSequenceDigest"], artifact["sha256"])
            # Decode the actual MP4 and check the visibly red dropped tail is absent.
            decoded = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", artifact["internalPath"],
                "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], check=True, capture_output=True).stdout
            self.assertEqual(len(decoded), 48*3)
            self.assertFalse(any(decoded[i] > 200 and decoded[i+1] < 70 and decoded[i+2] < 70 for i in range(0,len(decoded),3)))
            print("R3_VERTICAL="+json.dumps({"classification":"CPU_FIXTURE_ONLY", "posts":server.complete_post_count,
                "node":"41", "nativeCount":49, "frames":48, "fps":24, "duration":artifact["probe"]["durationSeconds"],
                "repeatEncodeEqual":True, "encodingDigest":digest(request["postprocessBinding"]),
                "tools":self.tools, "realGpu":False, "formalGrant":False},sort_keys=True))

    def test_actual_encoding_tool_drift_is_rejected_before_connection(self):
        from services.v4_platform import generation_dispatch_live_result as module
        with LoopbackComfyUI(output_node="41") as server:
            fixture=exact_fixture(self,server.endpoint,self.tools)
            with patch.object(module,"encoder_tool_identity",return_value={"ffmpegSha256":"c"*64,"ffprobeSha256":"d"*64}):
                saved=fixture.execute()
            self.assertEqual(saved["dispatchResult"]["requestWriteState"],"ZERO_BYTES_PROVEN")
            self.assertEqual(server.paths,[])
            self.assertEqual(server.complete_post_count,0)

    def test_exact_profile_and_encoder_selection_drift_at_l1_l2_no_post(self):
        for phase in ("L1","L2"):
            for fault in ("seed","encoding-tool","camera","runtime"):
                with self.subTest(phase=phase,fault=fault), LoopbackComfyUI(output_node="41") as server:
                    fixture=exact_fixture(self, server.endpoint, self.tools)
                    claimed, command=fixture.claim_command()
                    continuation=fixture.consumer.consume(command)["continuation"] if phase=="L2" else None
                    p=fixture.external.template["materials"]["backendProfile"]["parameters"]
                    if fault=="seed": p["seed"]+=1
                    if fault=="encoding-tool": p["postprocess"]["toolIdentity"]["ffmpegSha256"]="c"*64
                    if fault=="camera": p["positivePrompt"]+=" TEST_ONLY changed camera"
                    if fault=="runtime":
                        spec=fixture.external.proof_files[fixture.external.attestation["attestationRef"]]
                        spec["path"].write_bytes(spec["path"].read_bytes()+b" ")
                    else: fixture.external.write_originals()
                    with self.assertRaises(c.DispatchError):
                        continuation.send_once(fixture.transport) if continuation else fixture.consumer.consume(command)
                    self.assertEqual(server.complete_post_count,0)
                    self.assertEqual(server.paths,[])

    def test_candidate_cannot_be_promoted_by_test_runtime_or_existing_approval(self):
        with LoopbackComfyUI(output_node="41") as server:
            fixture=exact_fixture(self,server.endpoint,self.tools)
            p=fixture.external.template["materials"]["backendProfile"]["parameters"]
            p.update(evidenceClass="OFFLINE_SOURCE_CANDIDATE",cameraDisposition="PROPOSED_PENDING_OWNER_ACCEPTANCE")
            fixture.external.write_originals()
            with self.assertRaises(c.DispatchError): fixture.execute()
            self.assertEqual(server.paths,[])

    def test_redirect_and_lost_receipt_are_unknown_and_never_resent(self):
        for options in ({"status":307},{"status":308},{"receipt_raw":b"invalid-test-receipt"}):
            with self.subTest(options=options), LoopbackComfyUI(output_node="41",**options) as server:
                fixture=exact_fixture(self,server.endpoint,self.tools)
                saved=fixture.execute()
                self.assertEqual(saved["dispatchResult"]["outcome"],"UNKNOWN")
                self.assertEqual(server.complete_post_count,1)
                legacy.A14BCpuIntegrationTests.assert_original_recovery_no_resend(self,fixture,server)
