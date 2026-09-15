"""Technical input v1 → original queue v5, entirely CPU and temporary stores."""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from uuid import uuid4

from services.v4_platform.backend_registry import BackendValidationError, digest
from services.v4_platform.image_video_execution import (
    OUTPUT, USER_IMAGE_VIDEO_ENVELOPE_SCHEMA, USER_IMAGE_VIDEO_JOB_SCHEMA,
    USER_IMAGE_VIDEO_REQUEST_SCHEMA, build_user_image_video_envelope,
    build_user_image_video_request, validate_user_image_video_request,
)
from services.v4_platform.generation_dispatch_jobs import create_generation_dispatch_job
from services.v4_platform.generation_dispatch_execution import MediaJobGenerationDispatchPort
from services.v4_platform.generation_dispatch_live_result import GenerationDispatchLiveResultBoundary
from services.v4_platform.media_jobs import (DeterministicLocalFfmpegAdapter,
    InMemoryMediaJobAdapter, SqliteMediaJobAdapter, MediaJobCoordinator,
    MediaJobError, MediaJobStateError, _validate_job)
from services.v4_platform.method_aware_execution import validate_envelope
from tests.support.generation_dispatch_fixtures import make_package, NOW
from tests.support.generation_dispatch_execution_fixtures import TestWorkerExecutionContext


def technical_package_and_approval():
    """Explicit synthetic originals, never runtime or human-approval evidence."""
    from services.v5_core_os.episode_production import generation_dispatch_contracts as c
    from services.v5_core_os.episode_production import image_video_contracts as ic
    from services.v4_platform.generation_dispatch_a14b_live import (LIVE_ADAPTER_IDENTITY,
        LIVE_CAPABILITY, LIVE_ENDPOINT_CLASS)
    from tests.unit.test_generation_dispatch_d1_live import live_profile, live_runtime
    from tests.support.generation_dispatch_fixtures import approval_for, pin
    package, _ = make_package()
    plan, materials = package["plan"], package["materials"]
    plan["subject"] = technical_grant()["subject"]
    plan["permissions"] = deepcopy(ic.PERMISSIONS)
    profile = live_profile(plan["subject"]["inputImage"]["contentDigest"])
    profile["parameters"]["positivePrompt"] = plan["subject"]["description"]
    materials["backendProfile"] = profile
    materials["processIdentity"]["comfyuiCommit"] = profile["parameters"]["comfyuiCommit"]
    attestation = live_runtime(profile, materials["processIdentity"], materials["executionConfig"])
    old_review = materials["prerequisiteEvidence"]["costReview"]
    materials["prerequisiteEvidence"] = {"inputConsent": {"ref": plan["subject"]["generationRef"],
        "digest": plan["subject"]["inputDigest"]}, "executionPolicy": pin("technical-ui-policy"), "costReview": old_review}
    binding = plan["executionBinding"]
    decision = binding["backendDecision"]
    decision.update(adapterIdentity=LIVE_ADAPTER_IDENTITY, adapterCapability=LIVE_CAPABILITY,
        endpointClass=LIVE_ENDPOINT_CLASS, backendProfileDigest=digest(profile),
        runtimeAttestationRef=attestation["attestationRef"], runtimeAttestationDigest=attestation["payloadDigest"])
    binding.update(backendDecisionDigest=digest(decision),
        executionProfile={"ref": decision["backendProfileRef"], "digest": digest(profile)},
        prerequisiteEvidenceDigest=digest(materials["prerequisiteEvidence"]))
    binding["executionCode"]["comfyuiCommit"] = profile["parameters"]["comfyuiCommit"]
    binding["runtimeBinding"].update(processIdentityDigest=digest(materials["processIdentity"]),
        attestationFileSha256=digest(attestation))
    materials["workflow"] = ic.compile_workflow(plan, materials)
    binding["workflowDigest"] = digest(materials["workflow"])
    approval = approval_for(package)
    approval.update(actorRole="AUTHORIZED_CREATOR", approvalKind="USER_IMAGE_VIDEO_EXECUTION",
        approvalEvidenceRef=materials["prerequisiteEvidence"]["executionPolicy"]["ref"],
        approvalEvidenceDigest=materials["prerequisiteEvidence"]["executionPolicy"]["digest"])
    approval = c.sealed(approval, "authorityDecisionDigest")
    return package, approval


def technical_read_set(package, approval, *, phase="ISSUE"):
    from services.v5_core_os.episode_production import image_video_contracts as ic
    plan, materials = package["plan"], package["materials"]
    selected = {key: {"ref": plan["scope"][field], "digest": digest(plan["scope"][field])}
        for key, field in (("CURRENT_PROJECT", "projectRef"), ("CURRENT_SERIES", "seriesRef"), ("CURRENT_EPISODE", "episodeRef"))}
    selected.update(CURRENT_INPUT_PLAN={"ref": plan["subject"]["generationRef"], "digest": plan["subject"]["inputDigest"]},
        CURRENT_BACKEND_CONFIG={"ref": materials["executionConfig"]["configRef"], "digest": digest(materials["executionConfig"])},
        CURRENT_RUNTIME_PROCESS={"ref": materials["processIdentity"]["instanceRef"], "digest": digest(materials["processIdentity"])},
        CURRENT_OWNER_APPROVAL={"ref": approval["authorityDecisionRef"], "digest": approval["authorityDecisionDigest"]})
    objects, selectors = [], []
    for kind, (owner, scope_key) in ic.SELECTORS.items():
        if phase == "PREPARE" and kind == "CURRENT_OWNER_APPROVAL":
            continue
        value = selected[kind]
        objects.append({"owner": owner, "objectKind": kind, "objectRef": value["ref"], "objectDigest": value["digest"]})
        selectors.append({"owner": owner, "selectorKind": kind, "scopeRef": plan["scope"][scope_key],
            "selectedRef": value["ref"], "selectedDigest": value["digest"], "coordinationRevision": 0})
    for kind in ("executionProfile", "costBasis"):
        pin = plan["executionBinding"][kind]
        objects.append({"owner": "V4_BACKEND_CONFIG", "objectKind": kind, "objectRef": pin["ref"], "objectDigest": pin["digest"]})
    if phase != "PREPARE":
        objects.append({"owner": "OWNER_APPROVAL", "objectKind": "ExecutionPolicy",
            "objectRef": approval["approvalEvidenceRef"], "objectDigest": approval["approvalEvidenceDigest"]})
    return {"schemaVersion": ic.READ_SET_SCHEMA, "scope": deepcopy(plan["scope"]), "phase": phase,
        "coordinationEpoch": digest("test-only-epoch"),
        "objects": sorted(objects, key=lambda x: (x["owner"], x["objectKind"], x["objectRef"])),
        "selectors": sorted(selectors, key=lambda x: (x["owner"], x["selectorKind"], x["scopeRef"]))}


def technical_grant():
    package, _ = make_package()
    description = "A person turns toward the window."
    subject = {"schemaVersion": "v5.user-image-video-subject.v1", "generationRef": "user-generation-test",
        "inputDigest": digest("test-only-input-record"),
        "inputImage": {"inputRef": "user-image-input-test", "contentDigest": digest("test-only-image-bytes"),
            "mediaType": "image/png", "byteSize": 400, "width": 704, "height": 1280},
        "description": description, "descriptionDigest": sha256(description.encode()).hexdigest(),
        "cameraInstruction": {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"},
        "outputConstraints": deepcopy(OUTPUT), "executionClass": "MICRO_MOTION", "executionMethod": "SINGLE_ANCHOR_I2V"}
    return {**package["plan"]["scope"], "subject": subject,
        "generationDispatchGrantRef": "generation-dispatch-grant-" + "a" * 64,
        "payloadDigest": digest("test-only-verified-grant"), "subjectDigest": digest(subject),
        "approval": {"approvedPlanDigest": digest("test-only-approved-plan")},
        "executionBinding": deepcopy(package["plan"]["executionBinding"]), "createdAt": NOW}


class _CpuCoordination:
    """No production side effects; claim/read_current only exercise V4 gates."""
    @contextmanager
    def critical_section(self, workspace_ref):
        yield SimpleNamespace(epoch=digest(workspace_ref), assert_held=lambda: None)


class UserImageVideoExecutionTests(unittest.TestCase):
    def setUp(self):
        self.grant = technical_grant()
        self.request = build_user_image_video_request(self.grant)
        self.envelope = build_user_image_video_envelope(self.request,
            self.grant["executionBinding"]["backendDecision"])

    def queue(self, root, sqlite=False):
        repository = SqliteMediaJobAdapter(Path(root) / "jobs.sqlite3") if sqlite else InMemoryMediaJobAdapter()
        return MediaJobCoordinator(repository, DeterministicLocalFfmpegAdapter(), Path(root) / "artifacts",
            ref_factory=lambda prefix: prefix + "-" + uuid4().hex, clock=lambda: NOW)

    def create(self, queue):
        return create_generation_dispatch_job(queue, verified_grant=self.grant,
            request=self.request, envelope=self.envelope)

    def test_request_and_envelope_have_technical_identity_not_fabricated_production_facts(self):
        self.assertEqual(self.request["schemaVersion"], USER_IMAGE_VIDEO_REQUEST_SCHEMA)
        self.assertEqual(self.envelope["schemaVersion"], USER_IMAGE_VIDEO_ENVELOPE_SCHEMA)
        self.assertEqual(validate_envelope(self.envelope, self.request), self.envelope)
        for forbidden in ("creativeShotVersionRef", "beatRef", "scriptVersion", "m6Binding",
                "sourceAsset", "sourceImageAssetVersionRef", "methodAwareInputPlanVersionRef"):
            self.assertNotIn(forbidden, self.request)
            self.assertNotIn(forbidden, self.envelope)
        self.assertEqual(self.envelope["inputImage"]["inputRef"], "user-image-input-test")

    def test_closed_shape_description_seal_and_scope_are_checked(self):
        for key, value in (("description", "tampered"), ("publicationAllowed", True),
                ("version", True), ("creativeShotVersionRef", "fake-shot"),
                ("generationRequestVersionRef", "wrong-version")):
            changed = deepcopy(self.request)
            changed[key] = value
            changed["payloadDigest"] = digest({k: v for k, v in changed.items() if k != "payloadDigest"})
            with self.subTest(key=key), self.assertRaises(BackendValidationError):
                validate_user_image_video_request(changed)
        changed = deepcopy(self.envelope)
        changed["workspaceRef"] = "other-workspace"
        changed["envelopeDigest"] = digest({k: v for k, v in changed.items() if k != "envelopeDigest"})
        with self.assertRaises(BackendValidationError):
            validate_envelope(changed, self.request)

    def test_original_memory_queue_is_idempotent_and_no_generic_worker_bypass(self):
        with TemporaryDirectory() as root:
            queue = self.queue(root)
            job, replay = self.create(queue)
            second, second_replay = self.create(queue)
            self.assertFalse(replay)
            self.assertTrue(second_replay)
            self.assertEqual(job, second)
            self.assertEqual(job["schemaVersion"], USER_IMAGE_VIDEO_JOB_SCHEMA)
            _validate_job(job)
            self.assertIsNone(queue.lease_next(job["workspaceRef"], job["productionRunRef"], "legacy-worker"))
            with self.assertRaises(MediaJobError):
                queue.dispatch(self.request, idempotency_key="bypass")
            with self.assertRaises(MediaJobStateError):
                queue.run_leased(job, "legacy-worker")
            self.assertEqual(queue.repository.list(job["workspaceRef"], job["productionRunRef"]), [job])

    def test_existing_sqlite_table_restart_and_scope_isolation(self):
        with TemporaryDirectory() as root:
            queue = self.queue(root, sqlite=True)
            job, _ = self.create(queue)
            reopened = SqliteMediaJobAdapter(Path(root) / "jobs.sqlite3", initialize_if_missing=False)
            self.assertEqual(reopened.get(job["workspaceRef"], job["productionRunRef"], job["jobRef"]), job)
            self.assertIsNone(reopened.get("other-workspace", job["productionRunRef"], job["jobRef"]))
            self.assertEqual(reopened.list(job["workspaceRef"], "other-run"), [])

    def test_request_must_match_verified_technical_subject(self):
        with TemporaryDirectory() as root:
            changed = deepcopy(self.grant)
            changed["subject"]["inputImage"]["inputRef"] = "another-upload"
            with self.assertRaises(BackendValidationError):
                create_generation_dispatch_job(self.queue(root), verified_grant=changed,
                    request=self.request, envelope=self.envelope)

    def test_job_version_cannot_project_new_input_into_old_dispatch_schema(self):
        with TemporaryDirectory() as root:
            job, _ = self.create(self.queue(root))
            changed = deepcopy(job)
            changed["schemaVersion"] = "v4.media-job.v4"
            with self.assertRaises(MediaJobError):
                _validate_job(changed)
            changed = deepcopy(self.envelope)
            changed["schemaVersion"] = "v4.method-aware-media-execution-envelope.v2"
            changed["envelopeDigest"] = digest({k: v for k, v in changed.items() if k != "envelopeDigest"})
            with self.assertRaises(BackendValidationError):
                validate_envelope(changed, self.request)

    def test_two_generations_are_independent_jobs_not_overwritten_history(self):
        with TemporaryDirectory() as root:
            queue = self.queue(root)
            first, _ = self.create(queue)
            second_grant = deepcopy(self.grant)
            second_grant["subject"]["generationRef"] = "user-generation-second"
            second_grant["generationDispatchGrantRef"] = "generation-dispatch-grant-" + "b" * 64
            second_grant["payloadDigest"] = digest("second-test-only-grant")
            second_grant["subjectDigest"] = digest(second_grant["subject"])
            second_request = build_user_image_video_request(second_grant)
            second_envelope = build_user_image_video_envelope(second_request, second_grant["executionBinding"]["backendDecision"])
            second, replay = create_generation_dispatch_job(queue, verified_grant=second_grant,
                request=second_request, envelope=second_envelope)
            self.assertFalse(replay)
            self.assertNotEqual(first["jobRef"], second["jobRef"])
            self.assertEqual(queue.repository.get(first["workspaceRef"], first["productionRunRef"], first["jobRef"]), first)
            self.assertEqual(len(queue.repository.list(first["workspaceRef"], first["productionRunRef"])), 2)

    def test_original_claim_attempt_and_lease_fence_are_reused(self):
        with TemporaryDirectory() as root:
            queue = self.queue(root)
            job, _ = self.create(queue)
            clock = SimpleNamespace(now=lambda: NOW)
            port = MediaJobGenerationDispatchPort(coordinator=queue, coordination=_CpuCoordination(), clock=clock)
            worker = TestWorkerExecutionContext("test-only-worker").current()
            active = port.claim(job["workspaceRef"], job["productionRunRef"], job["jobRef"], worker)
            self.assertEqual(active["state"], "RUNNING")
            self.assertEqual(len(active["attempts"]), 1)
            with self.assertRaises(MediaJobStateError):
                port.claim(job["workspaceRef"], job["productionRunRef"], job["jobRef"], worker)
            command = {"workspaceRef": job["workspaceRef"], "productionRunRef": job["productionRunRef"],
                "mediaJobRef": job["jobRef"], "attemptRef": active["attempts"][0]["attemptRef"],
                "workerRef": worker["workerRef"], "expectedJobRevision": active["revision"],
                "expectedLeaseTokenDigest": digest(active["lease"]["leaseToken"])}
            lease = SimpleNamespace(assert_held=lambda: None)
            observed = port.read_current(command, self.grant, worker, NOW, lease, phase="CONSUME")
            self.assertEqual(observed.job, active)
            self.assertEqual(queue.recover_expired(job["workspaceRef"], job["productionRunRef"]), [])


class UserImageVideoContractTests(unittest.TestCase):
    def test_new_plan_and_bundle_bind_actual_policy_and_not_old_camera_permission(self):
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        package, approval = technical_package_and_approval()
        self.assertEqual(c.validate_plan_package(package), package)
        bundle = {"schemaVersion": c.APPROVAL_SCHEMA, "authorityRef": approval["authorityRef"],
            "approvals": [{"planPackage": package, "approval": approval}]}
        self.assertEqual(c.validate_bundle(bundle), bundle)
        wrong = deepcopy(bundle)
        wrong["approvals"][0]["approval"]["approvalEvidenceDigest"] = digest("another-policy")
        wrong["approvals"][0]["approval"] = c.sealed(wrong["approvals"][0]["approval"], "authorityDecisionDigest")
        with self.assertRaises(c.DispatchError) as stopped:
            c.validate_bundle(wrong)
        self.assertEqual(stopped.exception.code, "APPROVAL_UNAVAILABLE")
        wrong = deepcopy(package["plan"])
        wrong["permissions"] = deepcopy(c.PERMISSIONS)
        with self.assertRaises(c.DispatchError):
            c.validate_plan(wrong)

    def test_readset_v2_has_seven_explicit_selectors_not_fabricated_m1_to_m9(self):
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        package, approval = technical_package_and_approval()
        observed = technical_read_set(package, approval)
        self.assertEqual(len(observed["selectors"]), 7)
        self.assertEqual(c.validate_read_set(observed), observed)
        c.validate_read_set_bindings(observed, package["plan"], approval)
        wrong = deepcopy(observed)
        wrong["schemaVersion"] = c.PREFIX + "read-set.v1"
        with self.assertRaises(c.DispatchError):
            c.validate_read_set(wrong)
        wrong = deepcopy(observed)
        wrong["selectors"].pop()
        with self.assertRaises(c.DispatchError):
            c.validate_read_set(wrong)

    def test_grant_v3_cannot_be_downgraded_or_reuse_a_sh09_slot(self):
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        from services.v5_core_os.episode_production import image_video_contracts as ic
        package, approval = technical_package_and_approval()
        plan = package["plan"]
        read_set = technical_read_set(package, approval)
        grant = c.sealed({"schemaVersion": ic.GRANT_SCHEMA, **plan["scope"],
            "generationDispatchGrantRef": c.grant_ref(plan), "version": 1,
            **{key: deepcopy(plan[key]) for key in ("subject", "executionBinding", "permissions", "limits")},
            "subjectDigest": c.subject_digest(plan), "approval": approval,
            "issuanceEvidence": {"issuerServiceRef": "test-ui-issuer",
                "requestDigest": c.issue_request_digest(ic.issue_command_identity(plan, approval), approval),
                "approvalBundleSha256": digest("test-only-bundle"),
                "snapshotTokens": {key: digest(key) for key in c.TOKEN_FIELDS},
                "currentSubjectReadSet": read_set, "currentSubjectReadSetDigest": digest(read_set)},
            "publicationAllowed": False, "createdAt": NOW})
        self.assertEqual(c.validate_grant(grant), grant)
        wrong = c.sealed({**grant, "schemaVersion": c.GRANT_SCHEMA})
        with self.assertRaises(c.DispatchError):
            c.validate_grant(wrong)
        other = deepcopy(plan)
        other["subject"]["generationRef"] = "another-generation"
        self.assertNotEqual(c.grant_ref(other), c.grant_ref(plan))
        # Changing an immutable input must never buy another same-generation slot.
        other = deepcopy(plan)
        other["subject"]["inputDigest"] = digest("changed-input")
        self.assertEqual(c.grant_ref(other), c.grant_ref(plan))

    def test_old_grant_and_new_ui_approval_cannot_be_confused(self):
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        package, approval = technical_package_and_approval()
        old_package, _ = make_package()
        with self.assertRaises(c.DispatchError):
            c.validate_approval(approval, plan=old_package["plan"])
        wrong = c.sealed({**approval, "actorRole": "PROJECT_LEAD"}, "authorityDecisionDigest")
        with self.assertRaises(c.DispatchError):
            c.validate_approval(wrong, plan=package["plan"])

    def test_prompt_and_image_profile_changes_fail_exact_workflow_binding(self):
        from services.v5_core_os.episode_production import generation_dispatch_contracts as c
        from services.v5_core_os.episode_production import image_video_contracts as ic
        package, _ = technical_package_and_approval()
        for field in ("positivePrompt", "input"):
            wrong = deepcopy(package)
            if field == "positivePrompt":
                wrong["materials"]["backendProfile"]["parameters"][field] = "another prompt"
            else:
                wrong["materials"]["backendProfile"]["parameters"][field]["contentDigest"] = digest("another-image")
            with self.subTest(field=field), self.assertRaises(c.DispatchError) as stopped:
                ic.compile_workflow(wrong["plan"], wrong["materials"])
            self.assertEqual(stopped.exception.code, "SOURCE_CHANGED")

    def test_unknown_result_stays_original_non_retryable_attempt(self):
        fixture = UserImageVideoExecutionTests()
        fixture.setUp()
        with TemporaryDirectory() as root:
            queue = fixture.queue(root, sqlite=True)
            job, _ = fixture.create(queue)
            clock = SimpleNamespace(now=lambda: NOW)
            port = MediaJobGenerationDispatchPort(coordinator=queue, coordination=_CpuCoordination(), clock=clock)
            worker = TestWorkerExecutionContext("test-only-worker").current()
            active = port.claim(job["workspaceRef"], job["productionRunRef"], job["jobRef"], worker)
            failed = GenerationDispatchLiveResultBoundary(queue, clock=clock).record_failure(active,
                workflow_digest=digest("test-only-workflow"), code="TRANSPORT_RESPONSE_UNAVAILABLE",
                phase="SUBMISSION_OUTCOME_UNKNOWN", submission=None,
                request_write_state="MAY_HAVE_BEEN_SENT")
            self.assertEqual(failed["state"], "FAILED")
            self.assertEqual(failed["dispatchResult"]["outcome"], "UNKNOWN")
            self.assertEqual(len(failed["attempts"]), 1)
            self.assertTrue(failed["attempts"][0]["nonRetryable"])
            with self.assertRaises(MediaJobStateError):
                queue.retry(job["workspaceRef"], job["productionRunRef"], job["jobRef"])
            self.assertEqual(queue.recover_expired(job["workspaceRef"], job["productionRunRef"]), [])


if __name__ == "__main__":
    unittest.main()
