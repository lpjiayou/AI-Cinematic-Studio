import copy
import json
from pathlib import Path
import tempfile
import unittest

from services.v4_platform import InMemoryMediaJobAdapter, MediaJobCoordinator
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    METHOD_CAPABILITY_REGISTRY,
    WAN_SINGLE_ANCHOR_CAPABILITY,
    resolve_video_method_capability,
)
from services.v5_core_os.episode_production.evidence import EvidenceRecord
from services.v5_core_os.episode_production.foundation import _digest
from services.v5_core_os.episode_production.media_candidate_review import (
    ASSET_ADMISSION,
    ASSET_VERSION,
    CANDIDATE,
    HUMAN_SELECTION,
    SEMANTIC_VISUAL_QC,
    TECHNICAL_VALIDATION,
    VISUAL_QC_PROFILE,
    VISUAL_QC_PROFILE_DIGEST,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    create_boundary,
    g2_command,
    g3_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)
from tests.unit.test_execution_method_planning_m8_m9 import (
    plan_command,
    seeded_plan,
)


class NoCallWanAdapter:
    adapter_identity = "v4.comfyui-wan22-image-to-video.v1"
    provenance = "SELF_HOSTED_AI_GENERATED"

    def __init__(self):
        self.generate_calls = 0

    def generate(self, request, candidate_path):
        del request, candidate_path
        self.generate_calls += 1
        raise AssertionError("method-aware planning must not execute the adapter")


def sealed(value):
    result = copy.deepcopy(value)
    result["payloadDigest"] = _digest(result)
    return result


def evidence_record(workspace, run_ref, kind, ref, payload, ordinal):
    value = sealed(payload)
    return EvidenceRecord(
        workspaceRef=workspace,
        productionRunRef=run_ref,
        recordKind=kind,
        recordRef=ref,
        recordVersion=1,
        idempotencyKey=f"neutral-admission-{ordinal}-{ref}",
        requestDigest=_digest(
            {"kind": kind, "ref": ref, "ordinal": ordinal}
        ),
        createdAt="2026-09-02T04:00:00Z",
        payload=value,
        payloadDigest=value["payloadDigest"],
    )


def method_service(boundary):
    return boundary._EpisodeProductionPublicBoundary__method_aware_media


def append_admitted_image(
    seed,
    execution_plan,
    *,
    suffix="v1",
    asset_ref="neutral-action-anchor",
    version=1,
):
    service = method_service(seed["boundary"])
    evidence = service.evidence_repository
    micro = next(
        item
        for item in execution_plan["visualExecutionRequirements"]
        if item["executionClass"] == "MICRO_MOTION"
    )
    candidate_ref = f"neutral-image-candidate-{suffix}"
    technical_ref = f"neutral-technical-validation-{suffix}"
    qc_ref = f"neutral-visual-qc-{suffix}"
    selection_ref = f"neutral-human-selection-{suffix}"
    admission_ref = f"neutral-asset-admission-{suffix}"
    asset_version_ref = f"neutral-asset-version-{suffix}"
    candidate = sealed(
        {
            "candidateRef": candidate_ref,
            "candidateVersion": 1,
            "mediaKind": "IMAGE",
            "revisionRef": f"neutral-revision-{suffix}",
            "slotRef": micro["creativeShotVersionRef"],
            "sourceAssetVersions": [],
            "publicationAllowed": False,
        }
    )
    records = (
        EvidenceRecord(
            workspaceRef=WORKSPACE,
            productionRunRef=seed["run"]["productionRunRef"],
            recordKind=CANDIDATE,
            recordRef=candidate_ref,
            recordVersion=1,
            idempotencyKey=f"neutral-candidate-{suffix}",
            requestDigest=_digest({"candidate": candidate_ref}),
            createdAt="2026-09-02T04:00:00Z",
            payload=candidate,
            payloadDigest=candidate["payloadDigest"],
        ),
        evidence_record(
            WORKSPACE,
            seed["run"]["productionRunRef"],
            TECHNICAL_VALIDATION,
            technical_ref,
            {
                "candidateRef": candidate_ref,
                "candidateVersion": 1,
                "candidateDigest": candidate["payloadDigest"],
                "lifecycleState": "TECHNICALLY_VERIFIED",
                "publicationAllowed": False,
            },
            2,
        ),
        evidence_record(
            WORKSPACE,
            seed["run"]["productionRunRef"],
            SEMANTIC_VISUAL_QC,
            qc_ref,
            {
                "candidateRef": candidate_ref,
                "candidateVersion": 1,
                "candidateDigest": candidate["payloadDigest"],
                "assessmentProfile": copy.deepcopy(VISUAL_QC_PROFILE),
                "assessmentProfileDigest": VISUAL_QC_PROFILE_DIGEST,
                "supersedesVisualQc": None,
                "lifecycleState": "SEMANTIC_QC_PASSED",
                "publicationAllowed": False,
            },
            3,
        ),
        evidence_record(
            WORKSPACE,
            seed["run"]["productionRunRef"],
            HUMAN_SELECTION,
            selection_ref,
            {
                "candidateRef": candidate_ref,
                "lifecycleState": "SELECTED_BY_HUMAN",
                "publicationAllowed": False,
            },
            4,
        ),
        evidence_record(
            WORKSPACE,
            seed["run"]["productionRunRef"],
            ASSET_ADMISSION,
            admission_ref,
            {
                "candidateRef": candidate_ref,
                "assetVersionRef": asset_version_ref,
                "admissionState": "ADMITTED",
                "publicationAllowed": False,
            },
            5,
        ),
        evidence_record(
            WORKSPACE,
            seed["run"]["productionRunRef"],
            ASSET_VERSION,
            asset_version_ref,
            {
                "schemaVersion": "v5.neutral-admitted-image-asset-version.v1",
                "workspaceRef": WORKSPACE,
                "productionRunRef": seed["run"]["productionRunRef"],
                "assetRef": asset_ref,
                "assetVersionRef": asset_version_ref,
                "version": version,
                "creativeShotVersionRef": micro["creativeShotVersionRef"],
                "sourceCandidateRef": candidate_ref,
                "mediaKind": "image",
                "mediaType": "image/png",
                "sha256": _digest({"neutral-image": suffix}),
                "state": "REGISTERED",
                "immutable": True,
                "publicationAllowed": False,
            },
            6,
        ),
    )
    evidence.append_records(records)
    asset = records[-1].payload
    return {
        "micro": micro,
        "asset": copy.deepcopy(dict(asset)),
        "binding": {
            "visualExecutionRequirementRef": micro[
                "visualExecutionRequirementRef"
            ],
            "inputRequirementKey": (
                "action-ready-anchor:"
                + micro["visualExecutionRequirementRef"]
            ),
            "inputRole": "ACTION_READY_ANCHOR",
            "assetVersionRef": asset["assetVersionRef"],
            "assetVersionDigest": asset["payloadDigest"],
        },
    }


def m10_command(seed, execution_plan, bindings=None, *, key="neutral-m10-v1"):
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": seed["project"]["projectRef"],
        "seriesRef": seed["series"]["seriesRef"],
        "episodeRef": seed["episode"]["episodeRef"],
        "productionRunRef": seed["run"]["productionRunRef"],
        "executionMethodPlanVersionRef": execution_plan[
            "executionMethodPlanVersionRef"
        ],
        "assetBindings": copy.deepcopy(bindings or []),
        "idempotencyKey": key,
    }


def m11_command(seed, input_plan, *, key="neutral-m11-v1"):
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": seed["project"]["projectRef"],
        "seriesRef": seed["series"]["seriesRef"],
        "episodeRef": seed["episode"]["episodeRef"],
        "productionRunRef": seed["run"]["productionRunRef"],
        "methodAwareInputPlanVersionRef": input_plan[
            "methodAwareInputPlanVersionRef"
        ],
        "idempotencyKey": key,
    }


class MethodAwareMediaTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.seed, validation = seeded_plan()
        self.adapter = NoCallWanAdapter()
        self.jobs = InMemoryMediaJobAdapter()
        self.coordinator = MediaJobCoordinator(
            self.jobs,
            self.adapter,
            Path(self.temporary.name) / "artifacts",
            ref_factory=lambda prefix: f"{prefix}-neutral",
            clock=lambda: "2026-09-02T04:00:00Z",
        )
        method_service(self.seed["boundary"]).media_jobs = self.coordinator
        self.execution_plan = self.seed["boundary"].create_execution_method_plan(
            plan_command(self.seed, validation, key="neutral-m8-m9")
        )

    def test_m10_emits_method_specific_inputs_without_exact_four_constraint(self):
        before = len(
            method_service(self.seed["boundary"]).evidence_repository.list_records(
                WORKSPACE,
                self.seed["run"]["productionRunRef"],
                record_kind=ASSET_VERSION,
            )
        )
        result = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan)
        )
        self.assertEqual(len(result["methodInputPlans"]), 7)
        self.assertNotEqual(len(result["methodInputPlans"]), 4)
        self.assertEqual(result["inputReadyCount"], 0)
        self.assertEqual(result["inputBlockedCount"], 7)

        by_method = {}
        for item in result["methodInputPlans"]:
            by_method.setdefault(item["executionMethod"], item)
        self.assertEqual(
            by_method["STATIC_PLATE_OR_REUSE"]["inputRequirements"][0][
                "acceptedInputRoles"
            ],
            ["STATIC_PLATE"],
        )
        self.assertEqual(
            by_method["SINGLE_ANCHOR_I2V"]["inputRequirements"][0][
                "acceptedInputRoles"
            ],
            ["ACTION_READY_ANCHOR"],
        )
        contact_roles = {
            role
            for requirement in by_method["CONTACT_CONDITIONED_VIDEO"][
                "inputRequirements"
            ]
            for role in requirement["acceptedInputRoles"]
        }
        self.assertEqual(
            contact_roles, {"SUBJECT_CONDITIONING", "TARGET_CONDITIONING"}
        )
        self.assertEqual(
            by_method["POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"][
                "inputRequirements"
            ][0]["acceptedInputRoles"],
            ["POSE_CONDITIONING", "TRAJECTORY_CONDITIONING"],
        )
        event = by_method["V3_DETERMINISTIC_COMPOSITION"]
        self.assertEqual(
            event["inputRequirements"][0]["acceptedInputRoles"],
            ["EVENT_FREE_BASE_PLATE"],
        )
        self.assertTrue(
            event["inputRequirements"][0]["inputRequirementKey"].startswith(
                "event-free-base:"
            )
        )
        after = len(
            method_service(self.seed["boundary"]).evidence_repository.list_records(
                WORKSPACE,
                self.seed["run"]["productionRunRef"],
                record_kind=ASSET_VERSION,
            )
        )
        self.assertEqual(after, before)
        self.assertEqual(self.adapter.generate_calls, 0)

    def test_micro_anchor_queues_existing_coordinator_without_execution(self):
        admitted = append_admitted_image(self.seed, self.execution_plan)
        evidence = method_service(self.seed["boundary"]).evidence_repository
        authority_counts = {
            kind: len(
                evidence.list_records(
                    WORKSPACE,
                    self.seed["run"]["productionRunRef"],
                    record_kind=kind,
                )
            )
            for kind in (
                CANDIDATE,
                TECHNICAL_VALIDATION,
                SEMANTIC_VISUAL_QC,
                HUMAN_SELECTION,
                ASSET_ADMISSION,
                ASSET_VERSION,
            )
        }
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan, [admitted["binding"]])
        )
        micro = next(
            item
            for item in input_plan["methodInputPlans"]
            if item["executionClass"] == "MICRO_MOTION"
        )
        self.assertEqual(micro["inputPlanningState"], "READY")
        route = self.seed["boundary"].route_method_aware_videos(
            m11_command(self.seed, input_plan)
        )

        self.assertEqual(route["videoGenerationRequestCount"], 1)
        self.assertEqual(route["queuedJobCount"], 1)
        self.assertFalse(route["wanFallbackUsed"])
        request = route["videoGenerationRequests"][0]
        self.assertEqual(request["executionClass"], "MICRO_MOTION")
        self.assertEqual(request["executionMethod"], "SINGLE_ANCHOR_I2V")
        self.assertEqual(request["adapterCapability"], WAN_SINGLE_ANCHOR_CAPABILITY)
        self.assertNotIn("prompt", json.dumps(request, sort_keys=True).lower())
        jobs = self.coordinator.list_jobs(
            WORKSPACE, self.seed["run"]["productionRunRef"]
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["state"], "QUEUED")
        self.assertEqual(self.adapter.generate_calls, 0)
        self.assertEqual(
            authority_counts,
            {
                kind: len(
                    evidence.list_records(
                        WORKSPACE,
                        self.seed["run"]["productionRunRef"],
                        record_kind=kind,
                    )
                )
                for kind in authority_counts
            },
        )

    def test_static_contact_gait_and_event_routes_fail_closed(self):
        admitted = append_admitted_image(self.seed, self.execution_plan)
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan, [admitted["binding"]])
        )
        route = self.seed["boundary"].route_method_aware_videos(
            m11_command(self.seed, input_plan)
        )
        states = {}
        for item in route["routes"]:
            states.setdefault(item["executionClass"], set()).add(
                item["routingState"]
            )
            self.assertFalse(item["fallbackUsed"])
        self.assertEqual(states["STATIC_HOLD"], {"BYPASSED_STATIC_PLATE"})
        self.assertEqual(states["MICRO_MOTION"], {"QUEUED_EXISTING_MEDIA_JOB"})
        self.assertEqual(states["CONTACT_ACTION"], {"CAPABILITY_UNAVAILABLE"})
        self.assertEqual(states["GAIT_LOCOMOTION"], {"CAPABILITY_UNAVAILABLE"})
        self.assertEqual(
            states["DETERMINISTIC_EVENT"],
            {"REJECTED_DETERMINISTIC_POSTPROCESS"},
        )
        event_route = next(
            item
            for item in route["routes"]
            if item["executionClass"] == "DETERMINISTIC_EVENT"
        )
        self.assertEqual(event_route["targetBoundary"], "M13_DETERMINISTIC_POSTPROCESS")
        self.assertIsNone(event_route["videoGenerationRequestRef"])
        self.assertEqual(self.adapter.generate_calls, 0)

    def test_micro_rejects_a_coordinator_bound_to_the_wrong_executor(self):
        admitted = append_admitted_image(self.seed, self.execution_plan)
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(
                self.seed,
                self.execution_plan,
                [admitted["binding"]],
                key="neutral-wrong-executor-m10",
            )
        )
        wrong_adapter = NoCallWanAdapter()
        wrong_adapter.adapter_identity = "v4.deterministic-local-ffmpeg.v1"
        wrong_jobs = InMemoryMediaJobAdapter()
        wrong_coordinator = MediaJobCoordinator(
            wrong_jobs,
            wrong_adapter,
            Path(self.temporary.name) / "wrong-executor-artifacts",
            ref_factory=lambda prefix: f"{prefix}-wrong-executor",
            clock=lambda: "2026-09-02T04:00:00Z",
        )
        method_service(self.seed["boundary"]).media_jobs = wrong_coordinator
        with self.assertRaises(EpisodeProductionPublicError) as rejected:
            self.seed["boundary"].route_method_aware_videos(
                m11_command(
                    self.seed,
                    input_plan,
                    key="neutral-wrong-executor-m11",
                )
            )
        self.assertEqual(rejected.exception.code, "worker_unavailable")
        self.assertEqual(
            wrong_coordinator.list_jobs(
                WORKSPACE, self.seed["run"]["productionRunRef"]
            ),
            [],
        )
        self.assertEqual(wrong_adapter.generate_calls, 0)

    def test_sh12_mechanism_regression_uses_neutral_fixture_and_no_fallback(self):
        neutral_case = {
            "fixtureRef": "neutral-technical-shot-12",
            "executionClass": "GAIT_LOCOMOTION",
            "executionMethod": "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
        }
        result = resolve_video_method_capability(
            neutral_case["executionClass"], neutral_case["executionMethod"]
        )
        self.assertEqual(result["capabilityState"], "CAPABILITY_UNAVAILABLE")
        self.assertIsNone(result["adapterCapability"])
        self.assertFalse(result["fallbackUsed"])
        self.assertEqual(
            METHOD_CAPABILITY_REGISTRY[
                ("GAIT_LOCOMOTION", "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO")
            ],
            None,
        )

    def test_exact_replay_changed_replay_and_capability_currentness(self):
        command = m10_command(self.seed, self.execution_plan)
        input_plan = self.seed["boundary"].create_method_aware_input_plan(command)
        replay = self.seed["boundary"].create_method_aware_input_plan(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["payloadDigest"], input_plan["payloadDigest"])

        route_command = m11_command(self.seed, input_plan)
        route = self.seed["boundary"].route_method_aware_videos(route_command)
        route_replay = self.seed["boundary"].route_method_aware_videos(route_command)
        self.assertTrue(route_replay["idempotentReplay"])
        self.assertEqual(route_replay["payloadDigest"], route["payloadDigest"])
        restored = self.seed["boundary"].get_method_aware_video_route(
            WORKSPACE,
            self.seed["project"]["projectRef"],
            self.seed["series"]["seriesRef"],
            self.seed["episode"]["episodeRef"],
            self.seed["run"]["productionRunRef"],
            route["videoMethodRouteVersionRef"],
        )
        self.assertEqual(restored["currentness"], "CURRENT")
        self.assertTrue(
            any(
                item["routingState"] == "CAPABILITY_UNAVAILABLE"
                for item in restored["routes"]
            )
        )

        admitted = append_admitted_image(self.seed, self.execution_plan)
        changed = copy.deepcopy(command)
        changed["assetBindings"] = [admitted["binding"]]
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            self.seed["boundary"].create_method_aware_input_plan(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

    def test_asset_successor_makes_bound_input_plan_stale(self):
        admitted = append_admitted_image(self.seed, self.execution_plan)
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan, [admitted["binding"]])
        )
        append_admitted_image(
            self.seed,
            self.execution_plan,
            suffix="v2",
            asset_ref=admitted["asset"]["assetRef"],
            version=2,
        )
        restored = self.seed["boundary"].get_method_aware_input_plan(
            WORKSPACE,
            self.seed["project"]["projectRef"],
            self.seed["series"]["seriesRef"],
            self.seed["episode"]["episodeRef"],
            self.seed["run"]["productionRunRef"],
            input_plan["methodAwareInputPlanVersionRef"],
        )
        self.assertEqual(restored["currentness"], "STALE")
        with self.assertRaises(EpisodeProductionPublicError) as blocked:
            self.seed["boundary"].route_method_aware_videos(
                m11_command(self.seed, input_plan, key="neutral-stale-route")
            )
        self.assertEqual(blocked.exception.code, "execution_not_authorized")

    def test_historical_k2_storyboard_v1_read_and_replay_remain_unchanged(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        boundary = create_boundary(
            assembly,
            refs,
            identity_reference_authority=k2_identity_authority(),
        )
        run = boundary.create_run(run_command(project, series, episode))
        boundary.authorize_and_lock(g2_command(run))
        first = boundary.compile_shot_graph(g3_command(run))
        replay = boundary.compile_shot_graph(g3_command(run))
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(
            first["storyboardVersion"]["schemaVersion"],
            "v5.storyboard-version.v1",
        )
        self.assertEqual(
            first["storyboardVersion"]["payloadDigest"],
            replay["storyboardVersion"]["payloadDigest"],
        )


if __name__ == "__main__":
    unittest.main()
