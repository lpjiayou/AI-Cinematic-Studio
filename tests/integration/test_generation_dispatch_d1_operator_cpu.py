"""Same application Operator, real original stores and fixture-owned loopback.

All model/process/Owner facts below are synthetic external I/O. They are not
SH09 binding, current hardware evidence, or authorization of any real action.
"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from apps.creator_workspace_mvp.generation_dispatch_operator import execute_command
from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v4_platform.generation_dispatch_live_result import encoder_tool_identity
from services.v4_platform.generation_dispatch_a14b_live import LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS, LIVE_REQUEST_SCHEMA
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_execution_fixture
from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime
from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png


class D1OperatorCpuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = encoder_tool_identity()
        cls.frames = tuple(synthetic_png(i) for i in range(49))

    def fixture(self, server):
        return make_a14b_execution_fixture(self, server.endpoint,
            profile_factory=lambda source: live_profile(source, self.tools), runtime_factory=live_runtime,
            adapter_identity=LIVE_ADAPTER_IDENTITY, adapter_capability=LIVE_CAPABILITY,
            endpoint_class=LIVE_ENDPOINT_CLASS, use_operator=True)

    def test_application_operator_live_version_one_post_and_original_result(self):
        from services.v4_platform import generation_dispatch_live_result as result_module
        requests = []
        original = result_module.process_native_frames
        def record(frames, native, request, **kwargs):
            requests.append(deepcopy(request))
            return original(frames, native, request, **kwargs)
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1) as server:
            f = self.fixture(server)
            with patch.object(result_module, "process_native_frames", record):
                saved = execute_command(f.operator, "execute-one", f.job["jobRef"])
            self.assertEqual(saved["state"], "SUCCEEDED", saved.get("dispatchResult"))
            self.assertEqual(server.complete_post_count, 1)
            self.assertEqual(server.view_count, 49)
            self.assertEqual(requests[0]["schemaVersion"], LIVE_REQUEST_SCHEMA)
            self.assertEqual(len(saved["attempts"]), 1)
            self.assertIsNone(saved["artifactCommitIntent"])
            self.assertEqual(saved["dispatchResult"]["derivation"]["frameCount"], 48)
            self.assertEqual(saved["dispatchResult"]["derivation"]["frameRate"], 24)
            self.assertEqual(saved["dispatchResult"]["derivation"]["width"], 704)
            self.assertEqual(saved["dispatchResult"]["derivation"]["height"], 1280)
            self.assertIsNone(saved["artifact"]["providerExecution"]["costMinor"])
            self.assertIsNone(saved["artifact"]["providerExecution"]["gpuUsed"])
            self.assertFalse(saved["artifact"]["publicationAllowed"])
            recovered = execute_command(f.operator, "recover", f.job["jobRef"])
            self.assertEqual(recovered["job"], saved)
            self.assertIsNone(recovered["continuation"])
            self.assertFalse(recovered["sendAttempted"])
            from services.v4_platform.media_jobs import MediaJobStateError
            with self.assertRaises(MediaJobStateError):
                execute_command(f.operator, "execute-one", f.job["jobRef"])
            self.assertEqual(server.complete_post_count, 1)
            print("D1_OPERATOR_VERTICAL=" + json.dumps({"classification": "CPU_FIXTURE_ONLY",
                "requestSchema": requests[0]["schemaVersion"], "posts": 1, "nativeFrames": 49,
                "encodedFrames": 48, "frameRate": 24, "size": [704, 1280],
                "gpuObserved": False, "formalGrant": False, "sameJobRecovery": True}))

    def test_operator_rejects_missing_approval_and_scope_before_network(self):
        from services.v5_core_os.episode_production.generation_dispatch_authority import RejectingApprovalReader
        for failure in ("approval", "scope"):
            with self.subTest(failure=failure), LoopbackComfyUI(output_node="41") as server:
                f = self.fixture(server)
                if failure == "approval":
                    f.dispatch.selections["approval"].select_port(RejectingApprovalReader())
                else:
                    # The trusted host selects one target; a CLI ref cannot replace it.
                    from dataclasses import replace
                    f.operator._selection = replace(f.operator._selection,
                        prepare_command={**f.prepare_command(), "workspaceRef": "wrong-workspace"})
                with self.assertRaises(c.DispatchError) as stopped:
                    execute_command(f.operator, "execute-one", f.job["jobRef"])
                self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE" if failure == "approval" else "SCOPE_MISMATCH")
                self.assertEqual(server.paths, [])

    def test_unknown_known_prompt_recovers_get_only_without_new_attempt(self):
        from services.v4_platform import generation_dispatch_live_result as results
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1) as server:
            f = self.fixture(server)
            with patch.object(results, "process_native_frames", side_effect=ValueError("test-only encoder interruption")):
                saved = execute_command(f.operator, "execute-one", f.job["jobRef"])
            self.assertEqual(saved["dispatchResult"]["outcome"], "UNKNOWN")
            self.assertIsNotNone(saved["dispatchResult"]["providerPromptId"])
            recovered = execute_command(f.operator, "recover", f.job["jobRef"])
            observation = recovered["recoveryObservation"]
            self.assertEqual(observation["derivation"]["frameCount"], 48)
            self.assertEqual(len(observation["nativeArtifacts"]), 49)
            self.assertFalse(observation["sendAttempted"])
            self.assertEqual(server.complete_post_count, 1)
            self.assertEqual(f.jobs()[0], saved)
            self.assertEqual(len(saved["attempts"]), 1)
            # The immutable prior UNKNOWN observation is not relabelled success.
            self.assertEqual(observation["classification"], "READ_ONLY_OBSERVATION_NOT_DURABLE_JOB_SUCCESS")
            f.clock.value = "2031-01-01T00:00:00.000000Z"
            before = list(server.paths)
            with self.assertRaises(c.DispatchError) as expired:
                execute_command(f.operator, "recover", f.job["jobRef"])
            self.assertEqual(expired.exception.code, "OUTSIDE_VALIDITY_WINDOW")
            self.assertEqual(server.paths, before)

    def test_live_operator_current_source_drift_refuses_no_post(self):
        for field in ("positivePrompt", "negativePrompt", "seed"):
            with self.subTest(field=field), LoopbackComfyUI(output_node="41") as server:
                f = self.fixture(server)
                p = f.external.template["materials"]["backendProfile"]["parameters"]
                p[field] = p[field] + 1 if field == "seed" else p[field] + " changed"
                f.external.write_originals()
                with self.assertRaises(c.DispatchError):
                    execute_command(f.operator, "execute-one", f.job["jobRef"])
                self.assertEqual(server.paths, [])

    def test_unknown_original_job_is_inspectable_but_never_resent(self):
        with LoopbackComfyUI(output_node="41", receipt_raw=b"invalid-receipt") as server:
            f = self.fixture(server)
            saved = execute_command(f.operator, "execute-one", f.job["jobRef"])
            self.assertEqual(saved["dispatchResult"]["outcome"], "UNKNOWN")
            recovered = execute_command(f.operator, "recover", f.job["jobRef"])
            self.assertEqual(recovered["job"]["jobRef"], saved["jobRef"])
            self.assertIsNone(recovered["continuation"])
            self.assertEqual(server.complete_post_count, 1)

    def test_two_operator_callers_compete_for_one_original_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from services.v4_platform.media_jobs import MediaJobStateError
        with LoopbackComfyUI(output_node="41", receipt_raw=b"invalid-receipt") as server:
            f = self.fixture(server)
            ready = Barrier(2)
            def execute():
                ready.wait(timeout=10)
                try:
                    return execute_command(f.operator, "execute-one", f.job["jobRef"])
                except MediaJobStateError:
                    return "NOT_CLAIMABLE"
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: execute(), range(2)))
            self.assertEqual(outcomes.count("NOT_CLAIMABLE"), 1)
            job = f.jobs()[0]
            self.assertEqual(len(job["attempts"]), 1)
            self.assertEqual(job["dispatchResult"]["outcome"], "UNKNOWN")
            self.assertEqual(server.complete_post_count, 1)

    def test_host_main_reopens_original_stores_and_cannot_resend(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from apps.creator_workspace_mvp.generation_dispatch_operator import main
        from services.v4_platform.media_jobs import MediaJobStateError
        with LoopbackComfyUI(output_node="41", receipt_raw=b"invalid-receipt") as server:
            f = self.fixture(server)
            saved = execute_command(f.operator, "execute-one", f.job["jobRef"])
            f.operator_context.__exit__(None, None, None)
            output = StringIO()
            with redirect_stdout(output):
                code = main(["recover", "--target-ref", saved["jobRef"]], deployment=f.deployment)
            self.assertEqual(code, 0)
            recovered = json.loads(output.getvalue())
            self.assertEqual(recovered["job"], saved)
            self.assertEqual(len(recovered["job"]["attempts"]), 1)
            self.assertIsNone(recovered["continuation"])
            self.assertFalse(recovered["sendAttempted"])
            with self.assertRaises(MediaJobStateError):
                main(["execute-one", "--target-ref", saved["jobRef"]], deployment=f.deployment)
            self.assertEqual(server.complete_post_count, 1)
