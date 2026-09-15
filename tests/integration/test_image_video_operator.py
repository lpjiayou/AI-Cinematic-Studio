"""New user input -> original D1 Operator -> fixture-owned loopback -> playback.

Only external process/model/cost facts and input staging are synthetic trusted
ports. The runtime, materials validators, compiler, original Operator, Grant,
queue, attempt, SQLite evidence and 49-to-48 encoder are production code. No
GPU, real ComfyUI, formal database or paid execution is used by these tests.
"""
import base64
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Thread
from types import SimpleNamespace
from uuid import uuid4
import unittest

from services.v5_core_os.episode_production import generation_dispatch_contracts as c
from services.v5_core_os.episode_production.generation_dispatch_live_sources import LiveRuntimeCurrentReader, OriginalFile
from services.v5_core_os.episode_production.generation_dispatch_readers import VerifiedOriginalObservation
from services.v5_core_os.episode_production.generation_workspace import GenerationWorkspaceError
from services.v5_core_os.episode_production.image_video import ImageVideoInstallation
from services.v5_core_os.episode_production.image_video_materials import ImageVideoMaterials
from services.v4_platform.generation_dispatch_a14b_live import LIVE_ADAPTER_IDENTITY, LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS
from services.v4_platform.generation_dispatch_live_result import encoder_tool_identity
from tests.integration.test_generation_dispatch_live_result_cpu import synthetic_png
from tests.support.comfyui_loopback_fixtures import LoopbackComfyUI
from tests.support.generation_dispatch_a14b_fixtures import make_a14b_execution_fixture
from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime
from tests.unit.test_image_video_materials import test_png


class ImageVideoOperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = encoder_tool_identity()
        cls.frames = tuple(synthetic_png(index) for index in range(49))

    def fixture(self, server, *, stage_failure=False, max_generations=4, total_cost=4000, stage_events=None):
        temporary = TemporaryDirectory(prefix="test-image-video-material-port-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        staged, observed = [], []
        self.staged, self.observed = staged, observed

        def installation(scope, template, clock):
            configuration = {**{key: deepcopy(template["materials"][key]) for key in
                ("backendProfile", "processIdentity", "executionConfig")},
                **{key: deepcopy(template["plan"]["executionBinding"][key]) for key in
                    ("backendDecision", "executionCode")}}
            configuration["executionConfig"]["sourceRoot"]["absolutePathDigest"] = c.digest(str(root))
            configuration["executionConfig"]["inputRoot"]["absolutePathDigest"] = c.digest(str(root))
            config_file = root / "test-user-image-video-config.json"
            config_file.write_bytes(c.canonical(configuration))
            cost = deepcopy(template["materials"]["costBasis"])
            proof_values = {"test-user-input-billing": {"testOnly": True, "computeRate": 5},
                "test-user-input-continuing": {"testOnly": True, "storageBound": 2}}
            cost["sourceEvidence"] = [{"ref": "test-user-input-billing", "digest": c.digest(proof_values["test-user-input-billing"])}]
            cost["billingResponsibility"]["continuingChargesEvidence"] = {
                "ref": "test-user-input-continuing", "digest": c.digest(proof_values["test-user-input-continuing"])}
            cost = c.sealed(cost)

            def stage(config, raw, lease):
                lease.assert_held()
                if stage_events is not None:
                    entered, release = stage_events
                    entered.set()
                    if not release.wait(10):
                        raise AssertionError("fixture staging release was not signalled")
                if stage_failure:
                    raise c.DispatchError("SOURCE_CHANGED")
                name = config["backendProfile"]["parameters"]["input"]["imageName"]
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                staged.append((name, sha256(raw).hexdigest()))
                return {"inputName": name, "contentDigest": sha256(raw).hexdigest(), "mediaType": "image/png", "byteSize": len(raw)}

            def observe(config, lease):
                lease.assert_held()
                observed.append(deepcopy(config))
                return live_runtime(config["backendProfile"], config["processIdentity"], config["executionConfig"])

            def observe_input(config, lease):
                lease.assert_held()
                item = config["backendProfile"]["parameters"]["input"]
                return {"inputName": item["imageName"], "contentDigest": sha256((root / item["imageName"]).read_bytes()).hexdigest(),
                    "inputRootDigest": config["executionConfig"]["inputRoot"]["absolutePathDigest"],
                    "outputRootDigest": config["executionConfig"]["artifactRoot"]["absolutePathDigest"], "outputPrefixAbsent": True}

            material = ImageVideoMaterials(configuration=OriginalFile(config_file, sha256(config_file.read_bytes()).hexdigest()),
                runtime_current=LiveRuntimeCurrentReader(host_observer=observe, input_observer=observe_input,
                    tool_observer=encoder_tool_identity),
                cost_owner=SimpleNamespace(read_current=lambda package, lease: deepcopy(cost),
                    proof_originals=lambda package, lease: tuple(VerifiedOriginalObservation(
                        "V4_BACKEND_CONFIG", "CostEvidence", ref, deepcopy(value)) for ref, value in sorted(proof_values.items()))),
                stage_input=stage, clock=clock.now)
            policy = c.sealed({"schemaVersion": "v5.user-image-video-policy.v1", "policyRef": "test-finite-image-video-policy",
                "authorityRef": "test-owner", "scope": deepcopy(scope), "credentialActors": {"test-ui-writer": "test-human-lead"},
                "limits": deepcopy(template["plan"]["limits"]), "maxTotalCostMinor": total_cost, "maxGenerations": max_generations})
            return ImageVideoInstallation(policy, material)

        fixture = make_a14b_execution_fixture(self, server.endpoint,
            profile_factory=lambda source: live_profile(source, self.tools), runtime_factory=live_runtime,
            adapter_identity=LIVE_ADAPTER_IDENTITY, adapter_capability=LIVE_CAPABILITY,
            endpoint_class=LIVE_ENDPOINT_CLASS, use_operator=True, image_video_factory=installation)
        self.addCleanup(fixture.operator.image_video_boundary().close)
        return fixture

    @staticmethod
    def command(runtime, *, key=None, raw=None):
        return {"description": "A synthetic subject turns toward the window.",
            "imageBase64": base64.b64encode(test_png() if raw is None else raw).decode(), "imageMediaType": "image/png",
            "idempotencyKey": key or str(uuid4()), "expectedPolicyDigest": runtime.policy["payloadDigest"]}

    def finish(self, fixture, created):
        runtime = fixture.operator.image_video_boundary()
        runtime.close()
        return runtime.get(fixture.scope, "test-ui-writer", created["generationRef"])

    def test_real_original_operator_independent_job_one_prompt_49_to_48_and_restart_playback(self):
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1) as server:
            fixture = self.fixture(server)
            runtime = fixture.operator.image_video_boundary()
            old_job = deepcopy(fixture.job)
            original_package = deepcopy(fixture.operator._selected().plan_package)
            environment = runtime.environment(fixture.scope, "test-ui-writer")
            self.assertEqual((environment["core"], environment["operator"],
                environment["gpu"], environment["comfyui"]),
                ("CONNECTED", "READY", "CONNECTED", "CONNECTED"))
            self.assertEqual(environment["queue"], {
                "state": "IDLE", "runningCount": 0, "pendingCount": 0})
            self.assertTrue(environment["readOnly"])
            self.assertEqual(server.complete_post_count, 0)
            command = self.command(runtime)
            created = runtime.create(fixture.scope, "test-ui-writer", command)
            result = self.finish(fixture, created)
            self.assertEqual(result["state"], "SUCCEEDED", result)
            self.assertNotEqual(result["mediaJobRef"], old_job["jobRef"])
            self.assertEqual(result["attemptCount"], 1)
            self.assertEqual((server.complete_post_count, server.view_count), (1, 49))
            self.assertEqual(result["artifact"]["durationFrames"], 48)
            self.assertEqual(result["artifact"]["frameRate"], 24)
            self.assertEqual((result["artifact"]["width"], result["artifact"]["height"]), (704, 1280))
            content = runtime.content(fixture.scope, "test-ui-writer", result["generationRef"], result["artifact"]["sha256"])
            self.assertEqual(sha256(content["content"]).hexdigest(), result["artifact"]["sha256"])
            self.assertEqual(fixture.operator._coordinator.repository.get(fixture.scope["workspaceRef"], fixture.scope["productionRunRef"], old_job["jobRef"]), old_job)
            self.assertEqual(fixture.operator._selected().plan_package, original_package)
            self.assertEqual(len(self.staged), 1)
            self.assertEqual(runtime.create(fixture.scope, "test-ui-writer", command), result)
            self.assertEqual(server.complete_post_count, 1)
            fixture.operator_context.__exit__(None, None, None)
            with fixture.deployment.open() as reopened:
                history = reopened.image_video_boundary().workspace(fixture.scope, "test-ui-writer")
                self.assertEqual(history["generations"], [result])
                self.assertEqual(reopened.image_video_boundary().content(fixture.scope, "test-ui-writer", result["generationRef"], result["artifact"]["sha256"]), content)
                self.assertEqual(reopened._coordinator.repository.get(fixture.scope["workspaceRef"], fixture.scope["productionRunRef"], old_job["jobRef"]), old_job)
            self.assertEqual(server.complete_post_count, 1)
            print("IMAGE_VIDEO_OPERATOR_CPU: independent_job=PASS original_job_unchanged=PASS prompt=1 native=49 encoded=48 fps=24 restart_history=PASS content_digest=PASS")

    def test_deterministic_double_click_is_one_durable_input_and_one_prompt(self):
        with LoopbackComfyUI(receipt_raw=b"unparseable-receipt", output_node="41") as server:
            fixture = self.fixture(server); runtime = fixture.operator.image_video_boundary()
            command = self.command(runtime); barrier = Barrier(3); results, failures = [], []
            def submit():
                barrier.wait(timeout=10)
                try:
                    results.append(runtime.create(fixture.scope, "test-ui-writer", deepcopy(command)))
                except Exception as error:
                    failures.append(error)
            workers = [Thread(target=submit) for _ in range(2)]
            for worker in workers:
                worker.start()
            barrier.wait(timeout=10)
            for worker in workers:
                worker.join(20); self.assertFalse(worker.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]["generationRef"], results[1]["generationRef"])
            result = self.finish(fixture, results[0])
            self.assertEqual(result["state"], "UNKNOWN", result)
            self.assertEqual(len(runtime.workspace(fixture.scope, "test-ui-writer")["generations"]), 1)
            self.assertEqual(server.complete_post_count, 1)

    def test_progress_reads_during_blocked_prepare_and_send_then_return_durable_terminal(self):
        entered, release = Event(), Event()
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1,
                block_response=True) as server:
            fixture = self.fixture(server, stage_events=(entered, release))
            runtime = fixture.operator.image_video_boundary()
            old_job = deepcopy(fixture.job)
            results, failures = [], []

            def read_progress():
                done = Event()
                def read():
                    try:
                        results.append((runtime.get(fixture.scope, "test-ui-writer", created["generationRef"]),
                            runtime.workspace(fixture.scope, "test-ui-writer")))
                    except Exception as exc:
                        failures.append(exc)
                    finally:
                        done.set()
                reader = Thread(target=read)
                reader.start()
                try:
                    self.assertTrue(done.wait(1), "progress read waited for slow external preparation/execution")
                finally:
                    if not done.is_set():
                        release.set()
                        server.release_response.set()
                    reader.join(10)
                self.assertFalse(reader.is_alive())
                self.assertEqual(failures, [])
                view, workspace = results[-1]
                self.assertFalse(workspace["available"])
                self.assertEqual(workspace["reason"], "generation_already_active")
                self.assertEqual(workspace["generations"], [view])
                return view

            try:
                created = runtime.create(fixture.scope, "test-ui-writer", self.command(runtime))
                self.assertTrue(entered.wait(10))
                self.assertEqual(read_progress(), created)
                self.assertFalse(release.is_set())
                release.set()
                self.assertTrue(server.accepted.wait(20), "original Operator must reach its single fixture-owned submission")
                routed = read_progress()
                self.assertEqual(routed["state"], "QUEUED")
                self.assertIsNotNone(routed["mediaJobRef"])
                self.assertNotEqual(routed["mediaJobRef"], old_job["jobRef"])
                self.assertEqual(server.complete_post_count, 1)
            finally:
                release.set()
                server.release_response.set()
                runtime.close()
            final = runtime.get(fixture.scope, "test-ui-writer", created["generationRef"])
            self.assertEqual((final["state"], final["attemptCount"]), ("SUCCEEDED", 1), final)
            self.assertEqual(final["mediaJobRef"], routed["mediaJobRef"])
            self.assertEqual(runtime.workspace(fixture.scope, "test-ui-writer")["generations"], [final])
            self.assertEqual((server.complete_post_count, server.view_count), (1, 49))
            self.assertEqual(len(runtime._inputs()), 1)
            self.assertEqual(fixture.operator._coordinator.repository.get(fixture.scope["workspaceRef"],
                fixture.scope["productionRunRef"], old_job["jobRef"]), old_job)
            print("IMAGE_VIDEO_PROGRESS_CPU: prepare_event=PASS send_event=PASS nonblocking_reads=PASS durable_terminal=PASS original_job_unchanged=PASS prompt=1")

    def test_same_key_different_image_conflicts_without_second_attempt(self):
        with LoopbackComfyUI(output_node="41") as server:
            fixture = self.fixture(server, stage_failure=True); runtime = fixture.operator.image_video_boundary()
            command = self.command(runtime)
            result = self.finish(fixture, runtime.create(fixture.scope, "test-ui-writer", command))
            self.assertEqual(result["state"], "FAILED", result)
            changed = {**command, "imageBase64": base64.b64encode(synthetic_png(1)).decode()}
            with self.assertRaises(GenerationWorkspaceError) as rejected:
                runtime.create(fixture.scope, "test-ui-writer", changed)
            self.assertEqual((rejected.exception.status, rejected.exception.code), (409, "idempotency_conflict"))
            self.assertEqual(runtime.create(fixture.scope, "test-ui-writer", command), result)
            self.assertEqual((server.complete_post_count, result["attemptCount"]), (0, 0))

    def test_unknown_refresh_replay_restart_cannot_send_again_or_create_replacement(self):
        with LoopbackComfyUI(receipt_raw=b"unparseable-receipt", output_node="41") as server:
            fixture = self.fixture(server); runtime = fixture.operator.image_video_boundary()
            command = self.command(runtime)
            result = self.finish(fixture, runtime.create(fixture.scope, "test-ui-writer", command))
            self.assertEqual(result["state"], "UNKNOWN", result)
            self.assertEqual(runtime.create(fixture.scope, "test-ui-writer", command), result)
            for attempt in range(2):
                self.assertEqual(runtime.get(fixture.scope, "test-ui-writer", result["generationRef"]), result)
                with self.assertRaises(GenerationWorkspaceError) as rejected:
                    runtime.create(fixture.scope, "test-ui-writer", self.command(runtime))
                self.assertEqual(rejected.exception.code, "generation_already_active")
            fixture.operator_context.__exit__(None, None, None)
            with fixture.deployment.open() as reopened:
                current = reopened.image_video_boundary()
                self.assertEqual(current.workspace(fixture.scope, "test-ui-writer")["generations"], [result])
                self.assertEqual(current.create(fixture.scope, "test-ui-writer", command), result)
            self.assertEqual(server.complete_post_count, 1)

    def test_failed_prepare_stays_failed_and_budget_reservation_is_not_refunded(self):
        with LoopbackComfyUI(output_node="41") as server:
            fixture = self.fixture(server, stage_failure=True, max_generations=2, total_cost=1000)
            runtime = fixture.operator.image_video_boundary(); command = self.command(runtime)
            result = self.finish(fixture, runtime.create(fixture.scope, "test-ui-writer", command))
            self.assertEqual((result["state"], result["attemptCount"]), ("FAILED", 0), result)
            self.assertEqual(runtime.create(fixture.scope, "test-ui-writer", command), result)
            status = runtime.workspace(fixture.scope, "test-ui-writer")
            self.assertFalse(status["available"])
            self.assertEqual(status["reason"], "generation_budget_exhausted")
            with self.assertRaises(GenerationWorkspaceError) as rejected:
                runtime.create(fixture.scope, "test-ui-writer", self.command(runtime))
            self.assertEqual((rejected.exception.status, rejected.exception.code), (409, "generation_budget_exhausted"))
            self.assertEqual(server.paths, [])
            self.assertEqual(len(fixture.jobs()), 1)

    def test_wrong_credential_scope_and_policy_are_closed_before_material_or_prompt(self):
        with LoopbackComfyUI(output_node="41") as server:
            fixture = self.fixture(server); runtime = fixture.operator.image_video_boundary()
            for credential, scope, status in (("other-credential", fixture.scope, 403),
                    ("test-ui-writer", {**fixture.scope, "workspaceRef": "other"}, 404),
                    ("test-ui-writer", {**fixture.scope, "projectRef": "other"}, 404)):
                with self.subTest(credential=credential, scope=scope), self.assertRaises(GenerationWorkspaceError) as rejected:
                    runtime.create(scope, credential, self.command(runtime))
                self.assertEqual(rejected.exception.status, status)
            with self.assertRaises(GenerationWorkspaceError) as rejected:
                runtime.create(fixture.scope, "test-ui-writer", {**self.command(runtime), "expectedPolicyDigest": "0" * 64})
            self.assertEqual(rejected.exception.code, "generation_policy_changed")
            self.assertEqual(runtime.workspace(fixture.scope, "test-ui-writer")["generations"], [])
            self.assertEqual((self.staged, self.observed, server.paths), ([], [], []))


if __name__ == "__main__":
    unittest.main()
