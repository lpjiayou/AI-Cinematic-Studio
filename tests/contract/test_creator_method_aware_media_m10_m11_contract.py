import copy
import json
from pathlib import Path
import tempfile
import unittest

from services.v4_platform import (
    InMemoryMediaJobAdapter,
    MediaJobCoordinator,
    MediaJobError,
)
from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    METHOD_CAPABILITY_REGISTRY,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.unit.test_execution_method_planning_m8_m9 import (
    plan_command,
    seeded_plan,
)
from tests.unit.test_method_aware_media_m10_m11 import (
    NoCallWanAdapter,
    append_admitted_image,
    m10_command,
    m11_command,
    method_service,
)


def assert_sealed(testcase, value):
    payload = copy.deepcopy(dict(value))
    digest = payload.pop("payloadDigest")
    testcase.assertEqual(digest, _digest(payload))


class CreatorMethodAwareMediaContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.seed, validation = seeded_plan()
        self.adapter = NoCallWanAdapter()
        self.coordinator = MediaJobCoordinator(
            InMemoryMediaJobAdapter(),
            self.adapter,
            Path(self.temporary.name) / "artifacts",
            ref_factory=lambda prefix: f"{prefix}-contract",
            clock=lambda: "2026-09-02T05:00:00Z",
        )
        method_service(self.seed["boundary"]).media_jobs = self.coordinator
        self.execution_plan = self.seed["boundary"].create_execution_method_plan(
            plan_command(self.seed, validation, key="contract-m8-m9")
        )

    def test_m10_and_m11_public_dtos_are_sealed_and_path_free(self):
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan, key="contract-m10")
        )
        assert_sealed(
            self,
            {
                key: value
                for key, value in input_plan.items()
                if key not in {"currentness", "idempotentReplay"}
            },
        )
        self.assertEqual(input_plan["schemaVersion"], "v5.method-aware-input-plan.v1")
        for item in input_plan["methodInputPlans"]:
            assert_sealed(self, item)
            for requirement in item["inputRequirements"]:
                assert_sealed(self, requirement)

        route = self.seed["boundary"].route_method_aware_videos(
            m11_command(self.seed, input_plan, key="contract-m11")
        )
        assert_sealed(
            self,
            {
                key: value
                for key, value in route.items()
                if key not in {"currentness", "idempotentReplay"}
            },
        )
        self.assertEqual(route["schemaVersion"], "v5.video-method-route-plan.v1")
        for item in route["routes"]:
            assert_sealed(self, item)
        raw = json.dumps({"input": input_plan, "route": route}, sort_keys=True)
        for forbidden in (
            "storageKey",
            "internalPath",
            "providerSelection",
            '"prompt"',
            "/prompt",
            "cuda",
        ):
            self.assertNotIn(forbidden.lower(), raw.lower())
        self.assertEqual(self.adapter.generate_calls, 0)

    def test_closed_registry_and_wan_validator_reject_non_micro_methods(self):
        self.assertEqual(
            set(METHOD_CAPABILITY_REGISTRY),
            {
                ("MICRO_MOTION", "SINGLE_ANCHOR_I2V"),
                ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"),
                (
                    "GAIT_LOCOMOTION",
                    "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO",
                ),
            },
        )
        admitted = append_admitted_image(self.seed, self.execution_plan)
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(
                self.seed,
                self.execution_plan,
                [admitted["binding"]],
                key="contract-positive-m10",
            )
        )
        route = self.seed["boundary"].route_method_aware_videos(
            m11_command(self.seed, input_plan, key="contract-positive-m11")
        )
        request = route["videoGenerationRequests"][0]
        rejected_pairs = (
            ("CONTACT_ACTION", "CONTACT_CONDITIONED_VIDEO"),
            ("GAIT_LOCOMOTION", "POSE_OR_TRAJECTORY_CONDITIONED_VIDEO"),
            ("DETERMINISTIC_EVENT", "V3_DETERMINISTIC_COMPOSITION"),
        )
        for index, (execution_class, method) in enumerate(rejected_pairs, start=1):
            spoofed = copy.deepcopy(request)
            spoofed["executionClass"] = execution_class
            spoofed["executionMethod"] = method
            spoofed["payloadDigest"] = _digest(
                {
                    key: value
                    for key, value in spoofed.items()
                    if key != "payloadDigest"
                }
            )
            with self.assertRaises(MediaJobError):
                self.coordinator.dispatch(
                    spoofed, idempotency_key=f"contract-rejected-{index}"
                )
        self.assertEqual(self.adapter.generate_calls, 0)

    def test_foreign_scope_is_hidden_and_changed_route_replay_conflicts(self):
        input_plan = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(self.seed, self.execution_plan, key="contract-scope-m10")
        )
        route_command = m11_command(
            self.seed, input_plan, key="contract-scope-m11"
        )
        route = self.seed["boundary"].route_method_aware_videos(route_command)

        with self.assertRaises(EpisodeProductionPublicError) as hidden:
            self.seed["boundary"].get_method_aware_input_plan(
                "foreign-workspace",
                self.seed["project"]["projectRef"],
                self.seed["series"]["seriesRef"],
                self.seed["episode"]["episodeRef"],
                self.seed["run"]["productionRunRef"],
                input_plan["methodAwareInputPlanVersionRef"],
            )
        self.assertEqual((hidden.exception.status, hidden.exception.code), (404, "not_found"))

        with self.assertRaises(EpisodeProductionPublicError) as hidden:
            self.seed["boundary"].get_method_aware_video_route(
                WORKSPACE,
                "foreign-project",
                self.seed["series"]["seriesRef"],
                self.seed["episode"]["episodeRef"],
                self.seed["run"]["productionRunRef"],
                route["videoMethodRouteVersionRef"],
            )
        self.assertEqual((hidden.exception.status, hidden.exception.code), (404, "not_found"))

        successor_input = self.seed["boundary"].create_method_aware_input_plan(
            m10_command(
                self.seed,
                self.execution_plan,
                key="contract-scope-m10-successor",
            )
        )
        changed = copy.deepcopy(route_command)
        changed["methodAwareInputPlanVersionRef"] = successor_input[
            "methodAwareInputPlanVersionRef"
        ]
        with self.assertRaises(EpisodeProductionPublicError) as rejected:
            self.seed["boundary"].route_method_aware_videos(changed)
        self.assertEqual(rejected.exception.code, "idempotency_conflict")


if __name__ == "__main__":
    unittest.main()
