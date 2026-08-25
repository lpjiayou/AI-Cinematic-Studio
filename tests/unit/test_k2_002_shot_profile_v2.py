import copy
import json
from hashlib import sha256
from pathlib import Path
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    validate_executable_shot_graph,
)
from tests.unit.test_episode_production_k2 import (
    WORKSPACE,
    activate_k2_m6_baseline,
    g2_command as legacy_g2_command,
    g3_command,
    k2_identity_authority,
    run_command,
    seed_k2_roots,
)


PACKAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "experiments/k2-002-changan-preproduction/k2-002-changan-preproduction.v1.json"
)


def _ep01_package_shots():
    package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(package["episode01"]["shots"])


def _k2_002_script_content(*, script_scene_ref):
    shots = _ep01_package_shots()
    return {
        "title": "刮痕",
        "logline": "沈知微在残卷刮痕中认出贞字，远端油灯随之永久熄灭。",
        "synopsis": "沈知微以侧光检查残卷，进入贞观年间的校书房并再次见到裴昀。",
        "targetDurationSec": 30,
        "scenes": [
            {
                "scriptSceneRef": script_scene_ref,
                "sceneNumber": 1,
                "heading": "现代修复台至秘书省校书房",
                "location": "秘书省校书房",
                "timeOfDay": "冬夜",
                "characters": ["沈知微", "裴昀"],
                "action": "沈知微沿残卷刮痕追查被抹去的字，裴昀从西侧门出现。",
                "dialogue": [
                    {
                        "speaker": item["dialogueRequirement"]["speaker"],
                        "text": item["dialogueRequirement"]["text"],
                        "emotion": "克制",
                    }
                    for item in shots
                    if item["dialogueRequirement"]["sourceMode"] == "DIALOGUE"
                ],
                "narration": [
                    item["dialogueRequirement"]["text"]
                    for item in shots
                    if item["dialogueRequirement"]["sourceMode"] == "NARRATION"
                ],
                "subtitleText": [
                    item["dialogueRequirement"]["text"]
                    for item in shots
                    if item["dialogueRequirement"]["sourceMode"]
                    in {"DIALOGUE", "NARRATION"}
                ],
                "estimatedDurationSec": 30,
                "scenePurpose": "认出贞字并建立第一次不可逆世界变化",
                "continuityNotes": ["长案东端站位与西侧门方向保持固定"],
                "productionNotes": ["油灯熄灭只在第十二镜发生"],
            }
        ],
    }


def _digest(value):
    return sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class PortraitProjectBoundary:
    def __init__(self, delegate, *, aspect_ratio="9:16"):
        self.delegate = delegate
        self.aspect_ratio = aspect_ratio

    def build_context(self, workspace_ref, project_ref, series_ref, episode_ref):
        value = copy.deepcopy(
            self.delegate.build_context(
                workspace_ref, project_ref, series_ref, episode_ref
            )
        )
        value["project"]["aspectRatio"] = self.aspect_ratio
        return value


def _activate_k2_002_roots(assembly, project, series, episode, generated):
    activate_k2_m6_baseline(assembly, project, series)

    script = assembly.script_studio.create_version(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": generated["script"]["scriptRef"],
            "baseScriptVersionRef": generated["scriptVersion"]["scriptVersionRef"],
            "changeKind": "manual-edit",
            "content": _k2_002_script_content(
                script_scene_ref=generated["scriptVersion"]["scenes"][0][
                    "scriptSceneRef"
                ]
            ),
        }
    )
    assembly.script_studio.confirm_version(
        {
            "workspaceRef": WORKSPACE,
            "seriesRef": series["seriesRef"],
            "episodeRef": episode["episodeRef"],
            "scriptRef": script["script"]["scriptRef"],
            "scriptVersionRef": script["scriptVersion"]["scriptVersionRef"],
            "humanConfirmed": True,
        }
    )

    workspace = assembly.series_intelligence.get_workspace(
        WORKSPACE, project["projectRef"], series["seriesRef"]
    )
    current_root = workspace["characterContinuity"]
    current_version = workspace["characterContinuityVersions"][-1]
    character_content = copy.deepcopy(current_version["content"])
    replacements = {
        "character-lin": {
            "name": "沈知微",
            "background": "现代档案修复师与贞观校书记忆的同一意识链",
            "visualIdentityRules": ["38岁成熟脸", "深青袍", "右眼下痣"],
        },
        "character-gu": {
            "name": "裴昀",
            "background": "秘书省资深校书官，沈知微的老师",
            "visualIdentityRules": ["55岁", "深绯圆领袍", "黑革带银銙"],
        },
    }
    for character in character_content["characters"]:
        character.update(replacements[character["characterRef"]])

    context = {
        "workspaceRef": WORKSPACE,
        "projectRef": project["projectRef"],
        "seriesRef": series["seriesRef"],
    }

    def operation(operation_ref):
        return {
            **context,
            "operationRef": operation_ref,
            "idempotencyKey": operation_ref,
        }

    replacement = assembly.series_intelligence.create_character_version(
        {
            **operation("k2-002-character-create"),
            "characterContinuityRef": current_root["characterContinuityRef"],
            "expectedRevision": current_root["revision"],
            "candidate": True,
            "seriesBibleRef": workspace["activeBaseline"]["seriesBibleRef"],
            "seriesBibleVersionRef": workspace["activeBaseline"][
                "seriesBibleVersionRef"
            ],
            "content": character_content,
        }
    )
    replacement = assembly.series_intelligence.confirm_character_version(
        {
            **operation("k2-002-character-confirm"),
            "characterContinuityRef": replacement["root"][
                "characterContinuityRef"
            ],
            "characterContinuityVersionRef": replacement["version"][
                "characterContinuityVersionRef"
            ],
            "expectedRevision": replacement["root"]["revision"],
            "approvalRef": "approval-human",
        }
    )
    assembly.series_intelligence.activate_baseline(
        {
            **operation("k2-002-baseline-activate"),
            "seriesBibleRef": workspace["activeBaseline"]["seriesBibleRef"],
            "seriesBibleVersionRef": workspace["activeBaseline"][
                "seriesBibleVersionRef"
            ],
            "characterContinuityRef": replacement["root"][
                "characterContinuityRef"
            ],
            "characterContinuityVersionRef": replacement["version"][
                "characterContinuityVersionRef"
            ],
            "expectedActivationRevision": 1,
            "approvalRef": "approval-human",
        }
    )
    return script


SYNTHETIC_CAMERA_FIXTURE_INPUTS = [
    {
        "shotSize": size,
        "movement": movement,
        "angle": angle,
        "lensMm": lens_mm,
        "intent": f"synthetic-contract-fixture-shot-{index:02d}",
    }
    for index, (size, movement, angle, lens_mm) in enumerate(
        [
            ("ECU", "locked-off", "top-down", 65),
            ("ECU", "micro-slide", "top-down", 65),
            ("CU", "locked-off", "high-angle", 65),
            ("MCU", "locked-off", "eye-level", 40),
            ("CU", "locked-off", "high-angle", 65),
            ("CU", "locked-off", "eye-level", 65),
            ("MCU", "slow-tilt", "eye-level", 40),
            ("WS", "locked-off", "eye-level", 40),
            ("MS", "locked-off", "eye-level", 40),
            ("MCU", "locked-off", "eye-level", 40),
            ("ECU", "locked-off", "top-down", 65),
            ("CU", "locked-off", "eye-level", 65),
        ],
        start=1,
    )
]


def ep01_shot_budgets(script_version):
    scene_ref = script_version["scenes"][0]["scriptSceneRef"]
    result = []
    for item in _ep01_package_shots():
        global_order = item["globalOrder"]
        result.append(
            {
                "scriptSceneRef": scene_ref,
                "sceneOrder": global_order,
                "durationFrames": item["durationFrames"],
                # Synthetic command input for exercising the Core representation;
                # the reviewed package explicitly says its camera contract is NOT_READY.
                "camera": copy.deepcopy(
                    SYNTHETIC_CAMERA_FIXTURE_INPUTS[global_order - 1]
                ),
                "visibleIdentityBindings": copy.deepcopy(
                    item["visibleIdentityBindings"]
                ),
                "actionBeat": item["actionBeat"],
                "dialogueSyncMode": item["dialogueSyncMode"],
                "dialogueRequirement": copy.deepcopy(item["dialogueRequirement"]),
                "postprocessRequirements": copy.deepcopy(
                    item["postprocessRequirements"]
                ),
            }
        )
    return result


class K2002ShotProfileV2Tests(unittest.TestCase):
    def setUp(self):
        (
            self.assembly,
            self.refs,
            self.project,
            self.series,
            self.episode,
            self.generated,
        ) = seed_k2_roots(with_m6_authority=True)
        self.generated = _activate_k2_002_roots(
            self.assembly,
            self.project,
            self.series,
            self.episode,
            self.generated,
        )

    def boundary(self, *, aspect_ratio="9:16"):
        return create_in_memory_boundary(
            project_boundary=PortraitProjectBoundary(
                self.assembly.project_context, aspect_ratio=aspect_ratio
            ),
            series_episode_boundary=self.assembly.series_episode,
            series_planning_boundary=self.assembly.series_planning,
            script_studio_boundary=self.assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            ref_factory=self.refs,
            clock=lambda: "2026-08-25T00:00:00Z",
        )

    def command(self, **changes):
        value = {
            "workspaceRef": WORKSPACE,
            "projectRef": self.project["projectRef"],
            "seriesRef": self.series["seriesRef"],
            "episodeRef": self.episode["episodeRef"],
            "idempotencyKey": "k2-002-changan-ep01-preproduction-v2",
            "shotBudgets": ep01_shot_budgets(self.generated["scriptVersion"]),
        }
        value.update(changes)
        return value

    @staticmethod
    def g2_command(run):
        return {
            "workspaceRef": WORKSPACE,
            "productionRunRef": run["productionRunRef"],
            "idempotencyKey": "k2-002-authority-identity-v1",
            "characterMappings": [
                {
                    "scriptCharacterName": "沈知微",
                    "characterRef": "character-lin",
                },
                {
                    "scriptCharacterName": "裴昀",
                    "characterRef": "character-gu",
                },
            ],
        }

    def prepare(self, boundary):
        run = boundary.create_run(self.command())
        boundary.authorize_and_lock(self.g2_command(run))
        return run

    def test_v2_represents_exact_ep01_with_synthetic_camera_fixture(self):
        package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        package_shots = package["episode01"]["shots"]
        self.assertEqual(package["episode01"]["cameraContractState"], "NOT_READY")
        self.assertTrue(all("camera" not in item for item in package_shots))
        self.assertTrue(
            all(
                item["dialogueRequirement"]["speaker"]
                for item in package_shots
                if item["dialogueRequirement"]["sourceMode"] == "NARRATION"
            )
        )
        self.assertTrue(
            all(
                item["dialogueRequirement"]["speaker"] is None
                and bool(item["dialogueRequirement"]["text"])
                for item in package_shots
                if item["dialogueRequirement"]["sourceMode"]
                == "SFX_OR_SILENCE"
            )
        )
        boundary = self.boundary()
        run = self.prepare(boundary)
        result = boundary.compile_shot_graph(g3_command(run))
        graph = result["executableShotGraph"]
        shots = result["creativeShotVersions"]

        self.assertEqual(run["manifest"]["schemaVersion"], "k2.golden-episode.manifest.v2")
        self.assertEqual(run["manifest"]["expectedShotCount"], 12)
        self.assertEqual(
            run["manifest"]["shotPlanAuthorityState"],
            "LOCAL_STRUCTURAL_REPRESENTATION_ONLY",
        )
        self.assertEqual(run["manifest"]["shotPlanApprovalState"], "NOT_VERIFIED")
        self.assertEqual(
            run["manifest"]["cameraContractState"], "UNVERIFIED_COMMAND_INPUT"
        )
        self.assertFalse(run["manifest"]["dispatchAllowed"])
        output = run["manifest"]["output"]
        self.assertEqual(output["generationCanvas"], {"width": 704, "height": 1280, "aspectRatio": "11:20"})
        self.assertEqual(output["editMaster"], {"width": 720, "height": 1280, "aspectRatio": "9:16"})
        self.assertEqual(output["releaseMaster"], {"width": 1080, "height": 1920, "aspectRatio": "9:16"})
        self.assertEqual(output["controlledExtensionAlgorithm"]["leftExtensionPixels"], 8)
        self.assertEqual(output["controlledExtensionAlgorithm"]["rightExtensionPixels"], 8)
        self.assertFalse(output["controlledExtensionAlgorithm"]["cropAllowed"])
        self.assertFalse(output["controlledExtensionAlgorithm"]["stretchAllowed"])
        self.assertEqual(
            output["controlledExtensionAlgorithmDigest"],
            _digest(output["controlledExtensionAlgorithm"]),
        )

        self.assertEqual(graph["schemaVersion"], "v5.executable-shot-graph.v2")
        self.assertEqual(graph["status"], "LOCAL_STRUCTURAL_REPRESENTATION")
        self.assertEqual(
            graph["executionAuthorizationState"],
            "PREFLIGHT_ONLY_NOT_AUTHORIZED",
        )
        self.assertFalse(graph["dispatchAllowed"])
        self.assertEqual(
            [shot["durationFrames"] for shot in shots],
            [60, 60, 48, 60, 60, 48, 60, 60, 48, 72, 72, 72],
        )
        expected_budgets = ep01_shot_budgets(self.generated["scriptVersion"])
        self.assertEqual(
            [shot["cameraInstruction"] for shot in shots],
            SYNTHETIC_CAMERA_FIXTURE_INPUTS,
        )
        self.assertEqual(
            [shot["action"] for shot in shots],
            [item["actionBeat"] for item in expected_budgets],
        )
        self.assertEqual(
            [shot["actionBeat"] for shot in shots],
            [item["actionBeat"] for item in expected_budgets],
        )
        self.assertEqual(
            [shot["dialogueRequirement"] for shot in shots],
            [item["dialogueRequirement"] for item in expected_budgets],
        )
        self.assertEqual(
            shots[0]["sourceScriptSpans"],
            [
                "/manifest/shotBudgets/0/actionBeat",
                "/scenes/0/narration/0",
            ],
        )
        self.assertTrue(
            all(
                not any(span.endswith("/action") for span in shot["sourceScriptSpans"])
                for shot in shots
            )
        )
        self.assertEqual(graph["output"]["totalFrames"], 720)
        self.assertEqual(graph["output"]["generationCanvas"], output["generationCanvas"])
        self.assertEqual(shots[0]["requiredCharacterIdentityLocks"], [])
        self.assertEqual(shots[0]["visibleCharacterRefs"], [])

        body_binding = shots[4]["requiredCharacterIdentityLocks"][0]
        self.assertEqual(body_binding["bindingMode"], "BODY_ONLY")
        self.assertEqual(body_binding["characterRef"], "character-lin")
        self.assertFalse(
            {
                "identityLockRef", "identityLockVersionRef", "identityLockDigest",
                "referenceVersionRef", "referenceDigest",
            }.intersection(body_binding)
        )

        face_binding = shots[3]["requiredCharacterIdentityLocks"][0]
        self.assertEqual(face_binding["bindingMode"], "FACE_LOCK")
        self.assertEqual(face_binding["identityLockRef"], graph["identityLockRef"])
        self.assertEqual(
            face_binding["identityLockVersionRef"], graph["identityLockVersionRef"]
        )
        self.assertEqual(face_binding["identityLockDigest"], graph["identityLockDigest"])
        self.assertNotIn("visibleCharacterNames", graph["shots"][3])
        self.assertEqual(graph["shots"][3]["visibleCharacterRefs"], ["character-lin"])
        self.assertEqual(
            graph["shots"][3]["visibleIdentityBindings"],
            [{"characterRef": "character-lin", "bindingMode": "FACE_LOCK"}],
        )
        self.assertEqual(shots[9]["visibleIdentityMode"], "MIXED")
        self.assertEqual(
            shots[9]["visibleIdentityBindings"],
            [
                {"characterRef": "character-lin", "bindingMode": "FACE_LOCK"},
                {"characterRef": "character-gu", "bindingMode": "BODY_ONLY"},
            ],
        )
        self.assertEqual(
            [
                (item["characterRef"], item["bindingMode"])
                for item in shots[9]["requiredCharacterIdentityLocks"]
            ],
            [
                ("character-lin", "FACE_LOCK"),
                ("character-gu", "BODY_ONLY"),
            ],
        )
        self.assertNotIn(
            "identityLockRef", shots[9]["requiredCharacterIdentityLocks"][1]
        )
        self.assertEqual(
            graph["shots"][9]["dialogueRequirement"],
            {
                "speaker": "裴昀",
                "text": "你终于回来了。",
                "sourceMode": "DIALOGUE",
            },
        )
        self.assertEqual(
            shots[10]["postprocessRequirements"],
            [
                {
                    "requirementKey": "glyph-zhen-progressive-reveal",
                    "type": "TRACKED_GLYPH_COMPOSITE",
                    "inputAssetRequirementKeys": [
                        "glyph-zhen-v1",
                        "ep01-postprocess-manifest",
                    ],
                    "status": "NOT_READY",
                }
            ],
        )
        self.assertNotIn("assetVersionRef", shots[10]["postprocessRequirements"][0])
        validate_executable_shot_graph(graph)

    def test_v2_root_and_graph_replay_are_stable(self):
        boundary = self.boundary(aspect_ratio="portrait")
        first = boundary.create_run(self.command())
        replay = boundary.create_run(self.command())
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["payloadDigest"], first["payloadDigest"])

        boundary.authorize_and_lock(self.g2_command(first))
        compiled = boundary.compile_shot_graph(g3_command(first))
        compiled_replay = boundary.compile_shot_graph(g3_command(first))
        self.assertTrue(compiled_replay["idempotentReplay"])
        self.assertEqual(
            compiled_replay["executableShotGraph"], compiled["executableShotGraph"]
        )

        changed = self.command()
        changed["shotBudgets"][0]["actionBeat"] += "。"
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.create_run(changed)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "idempotency_conflict"),
        )

    def test_invalid_explicit_budget_and_identity_claims_fail_closed(self):
        cases = []
        invalid_duration = ep01_shot_budgets(self.generated["scriptVersion"])
        invalid_duration[0]["durationFrames"] = 59
        cases.append(invalid_duration)

        none_with_character = ep01_shot_budgets(self.generated["scriptVersion"])
        none_with_character[0]["visibleIdentityBindings"] = [
            {"characterName": "沈知微", "bindingMode": "NONE"}
        ]
        cases.append(none_with_character)

        face_without_character = ep01_shot_budgets(self.generated["scriptVersion"])
        face_without_character[3]["visibleIdentityBindings"] = [
            {"characterName": "沈知微", "bindingMode": "FACE_LOCK"},
            {"characterName": "沈知微", "bindingMode": "BODY_ONLY"},
        ]
        cases.append(face_without_character)

        unverified_postprocess = ep01_shot_budgets(self.generated["scriptVersion"])
        unverified_postprocess[10]["postprocessRequirements"][0]["assetVersionRef"] = "asset-version-invented"
        cases.append(unverified_postprocess)

        false_lip_sync = ep01_shot_budgets(self.generated["scriptVersion"])
        false_lip_sync[2]["dialogueSyncMode"] = "VERIFIED_LIP_SYNC"
        cases.append(false_lip_sync)

        missing_action = ep01_shot_budgets(self.generated["scriptVersion"])
        missing_action[0].pop("actionBeat")
        cases.append(missing_action)

        dialogue_drift = ep01_shot_budgets(self.generated["scriptVersion"])
        dialogue_drift[9]["dialogueRequirement"]["text"] += "漂移"
        cases.append(dialogue_drift)

        narration_without_speaker = ep01_shot_budgets(
            self.generated["scriptVersion"]
        )
        narration_without_speaker[0]["dialogueRequirement"]["speaker"] = None
        cases.append(narration_without_speaker)

        sfx_with_speaker = ep01_shot_budgets(self.generated["scriptVersion"])
        sfx_with_speaker[3]["dialogueRequirement"]["speaker"] = "沈知微"
        cases.append(sfx_with_speaker)

        empty_sfx = ep01_shot_budgets(self.generated["scriptVersion"])
        empty_sfx[6]["dialogueRequirement"]["text"] = ""
        cases.append(empty_sfx)

        missing_explicit_camera = ep01_shot_budgets(
            self.generated["scriptVersion"]
        )
        missing_explicit_camera[0].pop("camera")
        cases.append(missing_explicit_camera)

        for index, shot_budgets in enumerate(cases):
            with self.subTest(index=index):
                boundary = self.boundary()
                command = self.command(
                    idempotencyKey=f"k2-002-invalid-{index}",
                    shotBudgets=shot_budgets,
                )
                with self.assertRaises(EpisodeProductionPublicError) as caught:
                    boundary.create_run(command)
                self.assertEqual(
                    (caught.exception.status, caught.exception.code),
                    (400, "invalid_request"),
                )

    def test_v2_graph_validator_rejects_profile_and_identity_tampering(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        graph = boundary.compile_shot_graph(g3_command(run))["executableShotGraph"]

        digest_tamper = copy.deepcopy(graph)
        digest_tamper["output"]["controlledExtensionAlgorithmDigest"] = "0" * 64
        with self.assertRaisesRegex(Exception, "controlled extension"):
            validate_executable_shot_graph(digest_tamper)

        none_claims_lock = copy.deepcopy(graph)
        none_claims_lock["shots"][0]["requiredCharacterIdentityLocks"] = copy.deepcopy(
            none_claims_lock["shots"][3]["requiredCharacterIdentityLocks"]
        )
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_executable_shot_graph(none_claims_lock)

        body_claims_face = copy.deepcopy(graph)
        body_claims_face["shots"][4]["requiredCharacterIdentityLocks"][0][
            "identityLockRef"
        ] = graph["identityLockRef"]
        with self.assertRaisesRegex(Exception, "BODY_ONLY"):
            validate_executable_shot_graph(body_claims_face)

        face_lock_missing = copy.deepcopy(graph)
        face_lock_missing["shots"][3]["requiredCharacterIdentityLocks"] = []
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_executable_shot_graph(face_lock_missing)

        action_drift = copy.deepcopy(graph)
        action_drift["shots"][0]["actionBeat"] = " "
        with self.assertRaisesRegex(Exception, "action beat"):
            validate_executable_shot_graph(action_drift)

        dialogue_mode_drift = copy.deepcopy(graph)
        dialogue_mode_drift["shots"][9]["dialogueSyncMode"] = "NONE"
        with self.assertRaisesRegex(Exception, "dialogue sync"):
            validate_executable_shot_graph(dialogue_mode_drift)

        mixed_binding_drift = copy.deepcopy(graph)
        mixed_binding_drift["shots"][9]["visibleIdentityBindings"][1][
            "bindingMode"
        ] = "FACE_LOCK"
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_executable_shot_graph(mixed_binding_drift)

        mixed_body_speaker_lip_sync = copy.deepcopy(graph)
        mixed_body_speaker_lip_sync["shots"][9][
            "dialogueSyncMode"
        ] = "VERIFIED_LIP_SYNC"
        with self.assertRaisesRegex(Exception, "trusted evidence"):
            validate_executable_shot_graph(mixed_body_speaker_lip_sync)

        mixed_face_speaker_lip_sync = copy.deepcopy(graph)
        mixed_face_speaker_lip_sync["shots"][9][
            "dialogueSyncMode"
        ] = "VERIFIED_LIP_SYNC"
        mixed_face_speaker_lip_sync["shots"][9]["dialogueRequirement"][
            "speaker"
        ] = "沈知微"
        with self.assertRaisesRegex(Exception, "trusted evidence"):
            validate_executable_shot_graph(mixed_face_speaker_lip_sync)

    def test_k2_001_legacy_command_and_v1_graph_remain_compatible(self):
        assembly, refs, project, series, episode, _ = seed_k2_roots(
            with_m6_authority=True
        )
        activate_k2_m6_baseline(assembly, project, series)
        boundary = create_in_memory_boundary(
            project_boundary=assembly.project_context,
            series_episode_boundary=assembly.series_episode,
            series_planning_boundary=assembly.series_planning,
            script_studio_boundary=assembly.script_studio,
            identity_reference_authority=k2_identity_authority(),
            ref_factory=refs,
            clock=lambda: "2026-08-25T00:00:00Z",
        )
        run = boundary.create_run(run_command(project, series, episode))
        self.assertEqual(run["manifest"]["schemaVersion"], "k2.golden-episode.manifest.v1")
        self.assertEqual(
            run["manifest"]["output"],
            {
                "width": 1280,
                "height": 720,
                "frameRate": 24,
                "aspectRatio": "16:9",
                "container": "mp4",
            },
        )
        boundary.authorize_and_lock(legacy_g2_command(run))
        graph = boundary.compile_shot_graph(g3_command(run))["executableShotGraph"]
        self.assertEqual(graph["schemaVersion"], "v5.executable-shot-graph.v1")
        self.assertEqual(
            [shot["durationFrames"] for shot in graph["shots"]],
            [168, 168, 192, 192],
        )
        self.assertTrue(
            all(shot["requiredCharacterIdentityLocks"] for shot in graph["shots"])
        )


if __name__ == "__main__":
    unittest.main()
