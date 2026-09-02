from hashlib import sha256
import json
import unittest

from services.v5_core_os.episode_production import EpisodeProductionPublicError
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.unit.test_execution_method_planning_m8_m9 import (
    plan_command,
    seeded_plan,
)


def canonical_digest(value):
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def assert_sealed(testcase, value):
    payload = dict(value)
    digest = payload.pop("payloadDigest")
    testcase.assertEqual(digest, canonical_digest(payload))


class CreatorExecutionMethodPlanningContractTests(unittest.TestCase):
    def test_additive_v2_contracts_are_closed_and_digest_bound(self):
        seed, validation = seeded_plan()
        result = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )
        self.assertEqual(
            set(result),
            {
                "schemaVersion",
                "executionMethodPlanRef",
                "executionMethodPlanVersionRef",
                "planningVersion",
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "productionRunRef",
                "consistencyValidationVersionRef",
                "consistencyValidationDigest",
                "scriptVersionRef",
                "scriptVersionDigest",
                "storyboardVersion",
                "creativeShotVersions",
                "visualExecutionRequirements",
                "audioRequirements",
                "postprocessRequirements",
                "payloadDigest",
                "currentness",
                "idempotentReplay",
            },
        )
        self.assertEqual(result["schemaVersion"], "v5.execution-method-plan.v2")
        sealed_result = {
            key: value
            for key, value in result.items()
            if key not in {"currentness", "idempotentReplay"}
        }
        assert_sealed(self, sealed_result)

        storyboard = result["storyboardVersion"]
        self.assertEqual(storyboard["schemaVersion"], "v5.storyboard-version.v2")
        assert_sealed(self, storyboard)
        for shot in result["creativeShotVersions"]:
            self.assertEqual(shot["schemaVersion"], "v5.creative-shot-version.v2")
            self.assertEqual(
                shot["storyboardVersionDigest"], storyboard["payloadDigest"]
            )
            assert_sealed(self, shot)
            for beat in shot["actionExecutionBeats"]:
                assert_sealed(self, beat)
                source = seed["bound"]["scriptVersion"]["scenes"][
                    beat["sourceSpan"]["scriptSceneRef"]
                    != seed["bound"]["scriptVersion"]["scenes"][0][
                        "scriptSceneRef"
                    ]
                ]["action"]
                span = beat["sourceSpan"]
                selected = source[
                    span["startOffsetInclusive"] : span["endOffsetExclusive"]
                ]
                self.assertEqual(
                    beat["sourceTextDigest"],
                    sha256(selected.encode("utf-8")).hexdigest(),
                )

        shot_by_ref = {
            item["creativeShotVersionRef"]: item
            for item in result["creativeShotVersions"]
        }
        for collection_name in (
            "visualExecutionRequirements",
            "audioRequirements",
            "postprocessRequirements",
        ):
            for requirement in result[collection_name]:
                assert_sealed(self, requirement)
                shot = shot_by_ref[requirement["creativeShotVersionRef"]]
                beat = next(
                    item
                    for item in shot["actionExecutionBeats"]
                    if item["beatRef"] == requirement["beatRef"]
                )
                self.assertEqual(
                    requirement["creativeShotVersionDigest"],
                    shot["payloadDigest"],
                )
                self.assertEqual(requirement["beatDigest"], beat["payloadDigest"])
                self.assertEqual(
                    requirement["storyboardVersionDigest"],
                    storyboard["payloadDigest"],
                )

    def test_foreign_workspace_and_cross_scope_are_not_found(self):
        seed, validation = seeded_plan()
        created = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )
        args = (
            "foreign-workspace",
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            created["executionMethodPlanVersionRef"],
        )
        with self.assertRaises(EpisodeProductionPublicError) as hidden:
            seed["boundary"].get_execution_method_plan(*args)
        self.assertEqual((hidden.exception.status, hidden.exception.code), (404, "not_found"))

        cross_scope = (
            WORKSPACE,
            "different-project",
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            created["executionMethodPlanVersionRef"],
        )
        with self.assertRaises(EpisodeProductionPublicError) as hidden:
            seed["boundary"].get_execution_method_plan(*cross_scope)
        self.assertEqual((hidden.exception.status, hidden.exception.code), (404, "not_found"))

    def test_planning_output_has_no_provider_dispatch_contract(self):
        seed, validation = seeded_plan()
        result = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            "generationRequest",
            "providerRequest",
            "mediaJob",
            "prompt",
            "comfyui",
            "cuda",
        ):
            self.assertNotIn(forbidden.lower(), raw.lower())


if __name__ == "__main__":
    unittest.main()
