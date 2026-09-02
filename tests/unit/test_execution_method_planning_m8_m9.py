import copy
import unittest

from services.v5_core_os.episode_production import (
    AUDIO_TYPES,
    EXECUTION_CLASSES,
    EXECUTION_METHOD_BY_CLASS,
    REQUIREMENT_DISPOSITIONS,
    EpisodeProductionPublicError,
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
from tests.unit.test_narrative_currentness_m7 import (
    advance_m6,
    seed_m7,
    validation_command,
)


def source_span(scene, source_field, source_index=0):
    if source_field == "ACTION":
        text = scene["action"]
    elif source_field == "DIALOGUE":
        text = scene["dialogue"][source_index]["text"]
    elif source_field == "NARRATION":
        text = scene["narration"][source_index]
    else:
        text = scene["subtitleText"][source_index]
    return {
        "scriptSceneRef": scene["scriptSceneRef"],
        "sourceField": source_field,
        "sourceIndex": source_index,
        "startOffsetInclusive": 0,
        "endOffsetExclusive": len(text),
    }


def beat(
    scene,
    beat_ref,
    order,
    start,
    end,
    execution_class,
    *,
    subject="character-lin",
    targets=None,
):
    value = {
        "beatRef": beat_ref,
        "beatOrder": order,
        "sourceSpan": source_span(scene, "ACTION"),
        "subjectRefs": [subject],
        "targetRefs": list(targets or []),
        "frameRangeStartInclusive": start,
        "frameRangeEndExclusive": end,
        "executionClass": execution_class,
    }
    if execution_class == "DETERMINISTIC_EVENT":
        value["postprocessRequirementKey"] = "event-memory-chip-glow"
    return value


def plan_command(seed, validation, *, key="m8-m9-plan-v1"):
    first, second = seed["bound"]["scriptVersion"]["scenes"]
    return {
        "workspaceRef": WORKSPACE,
        "projectRef": seed["project"]["projectRef"],
        "seriesRef": seed["series"]["seriesRef"],
        "episodeRef": seed["episode"]["episodeRef"],
        "productionRunRef": seed["run"]["productionRunRef"],
        "consistencyValidationVersionRef": validation[
            "consistencyValidationVersionRef"
        ],
        "shots": [
            {
                "shotOrder": 1,
                "shotFrameCount": 50,
                "cameraInstruction": {
                    "framing": "MEDIUM",
                    "movement": "DOLLY_IN",
                },
                "actionExecutionBeats": [
                    beat(first, "beat-static", 1, 0, 10, "STATIC_HOLD"),
                    beat(first, "beat-micro", 2, 10, 20, "MICRO_MOTION"),
                    beat(
                        first,
                        "beat-contact",
                        3,
                        20,
                        30,
                        "CONTACT_ACTION",
                        targets=["character-gu"],
                    ),
                    beat(first, "beat-gait", 4, 30, 40, "GAIT_LOCOMOTION"),
                    beat(
                        first,
                        "beat-event",
                        5,
                        40,
                        50,
                        "DETERMINISTIC_EVENT",
                    ),
                ],
                "audioIntents": [
                    {
                        "audioType": "DIALOGUE",
                        "beatRef": "beat-static",
                        "sourceSpan": source_span(first, "DIALOGUE"),
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 10,
                        },
                    },
                    {
                        "audioType": "NARRATION",
                        "beatRef": "beat-static",
                        "sourceSpan": source_span(first, "NARRATION"),
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 10,
                        },
                    },
                    {
                        "audioType": "AMBIENCE",
                        "beatRef": "beat-static",
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 50,
                        },
                    },
                    {
                        "audioType": "SFX",
                        "beatRef": "beat-contact",
                        "timingReference": {
                            "startFrameInclusive": 20,
                            "endFrameExclusive": 30,
                        },
                    },
                    {
                        "audioType": "MUSIC",
                        "beatRef": "beat-micro",
                        "timingReference": {
                            "startFrameInclusive": 10,
                            "endFrameExclusive": 20,
                        },
                    },
                ],
            },
            {
                "shotOrder": 2,
                "shotFrameCount": 24,
                "cameraInstruction": {
                    "framing": "WIDE",
                    "movement": "LOCKED",
                },
                "actionExecutionBeats": [
                    beat(second, "beat-gait-only", 1, 0, 24, "GAIT_LOCOMOTION")
                ],
                "audioIntents": [],
            },
            {
                "shotOrder": 3,
                "shotFrameCount": 20,
                "cameraInstruction": {
                    "framing": "CLOSE_UP",
                    "movement": "PAN_LEFT",
                },
                "actionExecutionBeats": [
                    beat(second, "beat-silence", 1, 0, 20, "STATIC_HOLD")
                ],
                "audioIntents": [
                    {
                        "audioType": "SILENCE",
                        "beatRef": "beat-silence",
                        "timingReference": {
                            "startFrameInclusive": 0,
                            "endFrameExclusive": 20,
                        },
                    }
                ],
            },
        ],
        "idempotencyKey": key,
    }


def seeded_plan():
    seed = seed_m7()
    validation = seed["boundary"].create_narrative_validation(
        validation_command(seed)
    )
    return seed, validation


class ExecutionMethodPlanningTests(unittest.TestCase):
    def test_five_classes_three_axes_and_camera_action_separation(self):
        seed, validation = seeded_plan()
        created = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )

        self.assertEqual(created["currentness"], "CURRENT")
        self.assertEqual(
            {item["executionClass"] for item in created["visualExecutionRequirements"]},
            EXECUTION_CLASSES,
        )
        self.assertEqual(
            {
                item["executionClass"]: item["executionMethod"]
                for item in created["visualExecutionRequirements"]
            },
            EXECUTION_METHOD_BY_CLASS,
        )
        self.assertEqual(len(created["creativeShotVersions"]), 3)
        first = created["creativeShotVersions"][0]
        self.assertEqual(len(first["actionExecutionBeats"]), 5)
        self.assertEqual(first["cameraInstruction"]["movement"], "DOLLY_IN")
        self.assertEqual(
            first["actionExecutionBeats"][0]["executionClass"], "STATIC_HOLD"
        )
        self.assertEqual(
            [item["audioType"] for item in created["audioRequirements"]],
            ["DIALOGUE", "NARRATION", "AMBIENCE", "SFX", "MUSIC", "SILENCE"],
        )
        self.assertEqual(
            created["audioRequirements"][0]["speakerCharacterRef"],
            "character-gu",
        )
        self.assertNotIn("sourceSpan", created["audioRequirements"][2])
        self.assertEqual(
            created["audioRequirements"][-1]["disposition"], "NO_ASSET_REQUIRED"
        )
        self.assertEqual(
            {item["audioType"] for item in created["audioRequirements"]}
            <= AUDIO_TYPES,
            True,
        )
        self.assertTrue(
            all(
                item["disposition"] in REQUIREMENT_DISPOSITIONS
                for collection in (
                    created["visualExecutionRequirements"],
                    created["audioRequirements"],
                    created["postprocessRequirements"],
                )
                for item in collection
            )
        )
        self.assertEqual(len(created["postprocessRequirements"]), 1)
        post = created["postprocessRequirements"][0]
        self.assertEqual(post["beatRef"], "beat-event")
        self.assertEqual(
            post["executionMethod"], "V3_DETERMINISTIC_COMPOSITION"
        )
        serialized = repr(created)
        self.assertNotIn("GenerationRequest", serialized)
        self.assertNotIn("generationRequest", serialized)

    def test_exact_replay_and_changed_replay_conflict(self):
        seed, validation = seeded_plan()
        command = plan_command(seed, validation)
        created = seed["boundary"].create_execution_method_plan(command)
        replay = seed["boundary"].create_execution_method_plan(command)
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["payloadDigest"], created["payloadDigest"])

        changed = copy.deepcopy(command)
        changed["shots"][0]["cameraInstruction"]["movement"] = "LOCKED"
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            seed["boundary"].create_execution_method_plan(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

    def test_overlap_and_missing_static_hold_coverage_fail_closed(self):
        seed, validation = seeded_plan()
        overlap = plan_command(seed, validation, key="m8-overlap")
        overlap["shots"][0]["actionExecutionBeats"][1][
            "frameRangeStartInclusive"
        ] = 5
        with self.assertRaises(EpisodeProductionPublicError) as rejected:
            seed["boundary"].create_execution_method_plan(overlap)
        self.assertEqual(rejected.exception.code, "invalid_request")

        gap = plan_command(seed, validation, key="m8-gap")
        gap["shots"][0]["actionExecutionBeats"][0][
            "frameRangeStartInclusive"
        ] = 1
        with self.assertRaises(EpisodeProductionPublicError) as rejected:
            seed["boundary"].create_execution_method_plan(gap)
        self.assertEqual(rejected.exception.code, "invalid_request")

    def test_deterministic_key_rules_fail_closed(self):
        seed, validation = seeded_plan()
        missing = plan_command(seed, validation, key="m8-event-missing-key")
        missing["shots"][0]["actionExecutionBeats"][4].pop(
            "postprocessRequirementKey"
        )
        with self.assertRaises(EpisodeProductionPublicError):
            seed["boundary"].create_execution_method_plan(missing)

        forbidden = plan_command(seed, validation, key="m8-forbidden-key")
        forbidden["shots"][0]["actionExecutionBeats"][1][
            "postprocessRequirementKey"
        ] = "not-an-event"
        with self.assertRaises(EpisodeProductionPublicError):
            seed["boundary"].create_execution_method_plan(forbidden)

    def test_unresolved_refs_and_non_explicit_audio_fail_closed(self):
        seed, validation = seeded_plan()
        unresolved = plan_command(seed, validation, key="m8-unresolved-subject")
        unresolved["shots"][0]["actionExecutionBeats"][0]["subjectRefs"] = [
            "display-name-only"
        ]
        with self.assertRaises(EpisodeProductionPublicError):
            seed["boundary"].create_execution_method_plan(unresolved)

        invented_source = plan_command(seed, validation, key="m9-invented-source")
        invented_source["shots"][0]["audioIntents"][2]["sourceSpan"] = (
            source_span(seed["bound"]["scriptVersion"]["scenes"][0], "ACTION")
        )
        with self.assertRaises(EpisodeProductionPublicError):
            seed["boundary"].create_execution_method_plan(invented_source)

    def test_newer_validation_makes_prior_plan_stale(self):
        seed, validation = seeded_plan()
        created = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )
        newer = seed["boundary"].create_narrative_validation(
            validation_command(seed, key="m7-pass-newer")
        )
        restored = seed["boundary"].get_execution_method_plan(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            created["executionMethodPlanVersionRef"],
        )
        self.assertEqual(restored["currentness"], "STALE")
        stale_command = plan_command(seed, validation, key="m8-old-validation")
        with self.assertRaises(EpisodeProductionPublicError) as rejected:
            seed["boundary"].create_execution_method_plan(stale_command)
        self.assertEqual(rejected.exception.code, "execution_not_authorized")
        self.assertEqual(newer["currentness"], "CURRENT")

    def test_m6_drift_makes_plan_stale_and_blocks_consumption(self):
        seed, validation = seeded_plan()
        created = seed["boundary"].create_execution_method_plan(
            plan_command(seed, validation)
        )
        advance_m6(seed)
        restored = seed["boundary"].get_execution_method_plan(
            WORKSPACE,
            seed["project"]["projectRef"],
            seed["series"]["seriesRef"],
            seed["episode"]["episodeRef"],
            seed["run"]["productionRunRef"],
            created["executionMethodPlanVersionRef"],
        )
        self.assertEqual(restored["currentness"], "STALE")
        with self.assertRaises(EpisodeProductionPublicError) as blocked:
            seed["boundary"].require_current_execution_method_plan(
                WORKSPACE,
                seed["project"]["projectRef"],
                seed["series"]["seriesRef"],
                seed["episode"]["episodeRef"],
                seed["run"]["productionRunRef"],
                created["executionMethodPlanVersionRef"],
            )
        self.assertEqual(blocked.exception.code, "execution_not_authorized")

    def test_historical_storyboard_and_creative_shot_v1_remain_readable(self):
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
        created = boundary.compile_shot_graph(g3_command(run))
        replay = boundary.compile_shot_graph(g3_command(run))
        restored = boundary.get_shot_graph_bundle(WORKSPACE, run["productionRunRef"])
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(created["storyboardVersion"], restored["storyboardVersion"])
        self.assertEqual(
            restored["storyboardVersion"]["schemaVersion"],
            "v5.storyboard-version.v1",
        )
        self.assertTrue(
            all(
                item["schemaVersion"] == "v5.creative-shot-version.v1"
                for item in restored["creativeShotVersions"]
            )
        )


if __name__ == "__main__":
    unittest.main()
