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

    def test_live_presend_failure_records_zero_bytes_on_original_attempt(self):
        from services.v5_core_os.episode_production.generation_dispatch_consumption import GenerationDispatchConsumer
        with LoopbackComfyUI(output_node="41") as server:
            f = self.fixture(server)
            with patch.object(GenerationDispatchConsumer, "consume", side_effect=c.DispatchError("RUNTIME_CHANGED")):
                with self.assertRaises(c.DispatchError) as stopped:
                    execute_command(f.operator, "execute-one", f.job["jobRef"])
            self.assertEqual(stopped.exception.code, "RUNTIME_CHANGED")
            saved = f.jobs()[0]
            self.assertEqual(saved["state"], "FAILED")
            self.assertEqual(saved["dispatchResult"]["requestWriteState"], "ZERO_BYTES_PROVEN")
            self.assertEqual(saved["dispatchResult"]["phase"], "CONNECT_NOT_STARTED")
            self.assertEqual(saved["dispatchResult"]["failureCode"], "RUNTIME_CHANGED")
            self.assertIsNone(saved["dispatchResult"]["providerPromptId"])
            self.assertEqual(len(saved["attempts"]), 1)
            self.assertTrue(saved["attempts"][0]["nonRetryable"])
            recovered = execute_command(f.operator, "recover", saved["jobRef"])
            self.assertEqual(recovered["job"], saved)
            self.assertIsNone(recovered["consumption"])
            self.assertEqual(server.paths, [])

    def test_live_expired_cleanup_preserves_job_identity_and_readonly_recover(self):
        from services.v4_platform.media_jobs import MediaJobStateError
        with LoopbackComfyUI(output_node="41") as server:
            f = self.fixture(server)
            claimed, _ = f.claim_command()
            f.clock.value = "2030-01-01T00:01:20.000000Z"
            before = execute_command(f.operator, "recover", claimed["jobRef"])
            self.assertEqual(before["job"], claimed)
            self.assertEqual(f.jobs()[0], claimed)
            saved = f.operator.finalize_unconsumed_expired(claimed["jobRef"])
            self.assertEqual(saved["state"], "FAILED")
            self.assertEqual(saved["dispatchResult"]["requestWriteState"], "ZERO_BYTES_PROVEN")
            self.assertEqual(saved["dispatchResult"]["failureCode"], "PRE_CONSUMPTION_LEASE_EXPIRED")
            self.assertEqual(saved["attempts"][0]["attemptRef"], claimed["attempts"][0]["attemptRef"])
            self.assertEqual(saved["attempts"][0]["workerProcessIdentityDigest"],
                claimed["attempts"][0]["workerProcessIdentityDigest"])
            self.assertEqual(saved["dispatchGrantBinding"], claimed["dispatchGrantBinding"])
            self.assertEqual(f.operator.finalize_unconsumed_expired(saved["jobRef"]), saved)
            with self.assertRaises(MediaJobStateError):
                execute_command(f.operator, "execute-one", saved["jobRef"])
            self.assertEqual(server.paths, [])

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

    def test_zero_send_replacement_original_operator_one_post_no_third_grant(self):
        self._replacement_vertical(renew_window=False)

    def test_expired_zero_send_replacement_new_window_original_operator_one_post(self):
        self._standing_terms_vertical(restart_service=False)

    def test_restarted_service_and_new_window_same_operator_one_post_original_preserved(self):
        self._standing_terms_vertical(restart_service=True)

    def _standing_terms_vertical(self, *, restart_service):
        from tests.support.generation_dispatch_binding_fixtures import TestOnlyExternalOwners
        original = TestOnlyExternalOwners._cost_original
        def standing_terms(owner, reference, cost):
            # This scenario has independently pinned standing rates, like the
            # selected host's terms. The old scenario remains window-specific.
            result = original(owner, reference, cost)
            result.pop("validFrom")
            result.pop("validUntil")
            result["schemaVersion"] = "test-only.standing-cost-evidence.v1"
            return result
        with patch.object(TestOnlyExternalOwners, "_cost_original", standing_terms):
            self._replacement_vertical(renew_window=True, restart_service=restart_service)

    def _replacement_vertical(self, *, renew_window, restart_service=False):
        from dataclasses import replace
        from hashlib import sha256
        from types import SimpleNamespace
        from services.v5_core_os.episode_production.generation_dispatch_authority import PinnedApprovalReader
        from services.v5_core_os.episode_production.generation_dispatch_consumption import GenerationDispatchConsumer
        from services.v4_platform.generation_dispatch_execution import MediaJobGenerationDispatchPort
        from services.v4_platform.media_jobs import MediaJobStateError
        from tests.support.generation_dispatch_fixtures import approval_for
        with LoopbackComfyUI(frames=self.frames, output_node="41", start_number=1) as server:
            f = self.fixture(server)
            with patch.object(GenerationDispatchConsumer, "consume", side_effect=c.DispatchError("RUNTIME_CHANGED")):
                with self.assertRaises(c.DispatchError):
                    f.operator.execute_one(f.job["jobRef"])
            original_job = f.jobs()[0]
            self.assertEqual(server.complete_post_count, 0)
            foundation = f.dispatch.boundary._foundation
            # Direct original queue-reader rejection matrix, without modifying
            # enrolled writers or persisting artificial corrupt rows.
            for fault in ("active", "unknown", "prompt", "bytes", "lease", "binding", "artifact"):
                bad = deepcopy(original_job)
                if fault == "active":
                    bad["state"] = "RUNNING"
                elif fault == "unknown":
                    bad["dispatchResult"]["outcome"] = "UNKNOWN"
                elif fault == "prompt":
                    bad["dispatchResult"]["providerPromptId"] = "unproven-prompt"
                elif fault == "bytes":
                    bad["dispatchResult"]["requestWriteState"] = "BYTES_MAY_HAVE_BEEN_SENT"
                elif fault == "lease":
                    bad["lease"] = {"unexpected": True}
                elif fault == "binding":
                    bad["dispatchGrantBinding"]["generationDispatchGrantDigest"] = "0" * 64
                else:
                    bad["artifact"] = {"unexpected": True}
                port = MediaJobGenerationDispatchPort(coordinator=SimpleNamespace(
                    repository=SimpleNamespace(get=lambda *args, row=bad: deepcopy(row))),
                    coordination=f.dispatch.coordination, clock=f.clock)
                with self.subTest(fault=fault), f.dispatch.coordination.critical_section(f.scope["workspaceRef"]) as lease:
                    with self.assertRaises(c.DispatchError) as rejected:
                        port.read_zero_send_failure(f.scope["workspaceRef"], f.scope["productionRunRef"],
                            original_job["jobRef"], f.grant, lease)
                    self.assertEqual(rejected.exception.code, "ATTEMPT_OR_LEASE_CHANGED")
            package = f.operator._selected().plan_package
            if renew_window:
                original_path = f.root / "test-original-window-approval.json"
                original_path.write_bytes((f.root / "test-generation-approval.json").read_bytes())
                original_reader = PinnedApprovalReader(original_path,
                    sha256(original_path.read_bytes()).hexdigest(), original=f.originals)
                if restart_service:
                    from services.v5_core_os.episode_production.generation_dispatch_live_sources import OriginalFile
                    materials = f.external.template["materials"]
                    process = materials["processIdentity"]
                    process.update(comfyuiPid=777, processStartTicks=str(int(process["processStartTicks"]) + 100))
                    runtime = live_runtime(materials["backendProfile"], process, materials["executionConfig"])
                    runtime = c.sealed({**runtime, "attestationRef": "test-runtime-after-service-restart"})
                    f.external.attestation = runtime
                    f.external._store_proof("restart-attestation", runtime["attestationRef"], runtime,
                        "RUNTIME_PROCESS", "RuntimeAttestation", runtime["payloadDigest"])
                    proof = f.external.proof_files[runtime["attestationRef"]]
                    binding = f.external.template["plan"]["executionBinding"]
                    binding["runtimeBinding"].update(processIdentityDigest=c.digest(process), attestationFileSha256=proof["sha256"])
                    binding["backendDecision"].update(runtimeAttestationRef=runtime["attestationRef"], runtimeAttestationDigest=runtime["payloadDigest"])
                    binding["backendDecisionDigest"] = c.digest(binding["backendDecision"])
                    configuration = {**{k: materials[k] for k in ("backendProfile", "executionConfig", "processIdentity")},
                        **{k: binding[k] for k in ("backendDecision", "executionCode")}}
                    path = f.root / "test-restarted-independent-config.json"
                    path.write_bytes(c.canonical(configuration))
                    # Test-only host installation of new immutable originals;
                    # original Grant/bundle and old runtime file are preserved.
                    f.live_materials._configuration = OriginalFile(path, sha256(path.read_bytes()).hexdigest())
                    f.live_materials._runtime_file = OriginalFile(proof["path"], proof["sha256"])
                limits = {**package["plan"]["limits"], "notBefore": "2030-01-02T00:00:00.000000Z",
                    "expiresAt": "2030-01-02T01:00:00.000000Z"}
                f.external.template["plan"]["limits"] = limits
                cost = f.external.template["materials"]["costBasis"]
                cost.update(validFrom=limits["notBefore"], validUntil=limits["expiresAt"])
                f.external.template["materials"]["costBasis"] = c.sealed(cost)
                f.external.write_originals()
                f.clock.value = "2030-01-02T00:00:10.000000Z"
                f.operator._selection = replace(f.operator._selection, prepare_command=f.prepare_command())
                prepared = f.operator.prepare()
                self.assertIn("planPackage", prepared, prepared)
                package = prepared["planPackage"]
            with patch("tests.support.generation_dispatch_binding_fixtures.approval_for",
                    side_effect=lambda value: approval_for(value, decision_ref="test-new-exact-approval")):
                f.approve_package(package)
            if renew_window:
                current_reader = f.dispatch.selections["approval"]._port
                f.dispatch.selections["approval"].select_port(SimpleNamespace(resolve=lambda ref: (
                    original_reader if ref == f.grant["approval"]["authorityDecisionRef"] else current_reader).resolve(ref)))
            f.operator._selection = replace(f.operator._selection,
                approved_plan_digest=c.digest(package["plan"]),
                authority_decision_ref=f.approval["authorityDecisionRef"],
                issue_idempotency_key="test-one-replacement", route_idempotency_key="test-replacement-route")
            revoke = approval_for(grant_digest=f.grant["payloadDigest"])
            f.originals.register(revoke)
            path = f.root / "test-replacement-revocation.json"
            raw = c.canonical({"schemaVersion": c.REVOCATION_SCHEMA, "authorityRef": revoke["authorityRef"], "revocations": [revoke]})
            path.write_bytes(raw)
            foundation.revocation_reader = PinnedApprovalReader(path, sha256(raw).hexdigest(), original=f.originals, revocation=True)
            result = f.operator.replace_unconsumed_failure(original_job["jobRef"],
                revocation_decision_ref=revoke["authorityDecisionRef"])
            child = result["grant"]
            self.assertEqual(child["schemaVersion"], c.REPLACEMENT_GRANT_SCHEMA)
            self.assertEqual(child["limits"], package["plan"]["limits"])
            if restart_service:
                self.assertNotEqual(child["executionBinding"]["runtimeBinding"], f.grant["executionBinding"]["runtimeBinding"])
                self.assertEqual(child["executionBinding"]["runtimeBinding"], package["plan"]["executionBinding"]["runtimeBinding"])
            self.assertEqual(child["replacementOf"]["jobDigest"], c.digest(original_job))
            self.assertEqual(foundation._terminal(f.grant)["kind"], "REVOKED")
            self.assertEqual(server.complete_post_count, 0)
            self.assertEqual(f.jobs(), [original_job])
            f.operator.route(child["generationDispatchGrantRef"])
            new_job = next(job for job in f.jobs() if job["jobRef"] != original_job["jobRef"])
            saved = f.operator.execute_one(new_job["jobRef"])
            self.assertEqual(saved["state"], "SUCCEEDED", saved.get("dispatchResult"))
            self.assertEqual(server.complete_post_count, 1)
            self.assertEqual(saved["dispatchResult"]["derivation"]["frameCount"], 48)
            self.assertEqual(saved["dispatchResult"]["derivation"]["frameRate"], 24)
            self.assertEqual(f.queues[0].get(f.scope["workspaceRef"], f.scope["productionRunRef"], original_job["jobRef"]), original_job)
            with self.assertRaises(MediaJobStateError):
                f.operator.execute_one(new_job["jobRef"])
            f.operator._selection = replace(f.operator._selection, issue_idempotency_key="test-third-forbidden")
            with self.assertRaises(c.DispatchError) as stopped:
                f.operator.replace_unconsumed_failure(original_job["jobRef"], revocation_decision_ref=revoke["authorityDecisionRef"])
            self.assertEqual(stopped.exception.code, "GRANT_SUBJECT_ALREADY_RECORDED")
            self.assertEqual(len(f.jobs()), 2)
            self.assertEqual(server.complete_post_count, 1)
            print("ZERO_SEND_REPLACEMENT_VERTICAL=old_failed_preserved;old_revoked;one_child;one_post;48_frames;24fps;CPU_FIXTURE_ONLY")

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
