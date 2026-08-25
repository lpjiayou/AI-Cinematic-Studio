import copy
from dataclasses import replace
import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from services.v5_core_os.episode_production import (
    EpisodeProductionPublicError,
    create_in_memory_boundary,
    create_local_development_boundary,
    validate_creative_shot_draft,
    validate_shot_plan_draft,
    validate_storyboard_draft,
)
from services.v5_core_os.episode_production.evidence import EvidenceFact
from services.v5_core_os.episode_production.foundation import (
    RepositoryUnavailableError,
    _output_profile_v2,
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
    / "experiments/k2-002-changan-preproduction/k2-002-changan-preproduction.v2.json"
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


def _reseal(value):
    result = copy.deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


def _replace_gate_payloads(evidence, gate_key, replacements):
    stored_gate = evidence._gates[gate_key]
    stored_facts = []
    for fact in stored_gate.facts:
        payload = replacements.get(fact.factKind)
        if payload is None:
            stored_facts.append(fact)
        else:
            stored_facts.append(
                EvidenceFact(
                    factKind=fact.factKind,
                    factRef=fact.factRef,
                    factVersion=fact.factVersion,
                    payload=payload,
                    payloadDigest=payload["payloadDigest"],
                )
            )
    evidence._gates[gate_key] = replace(
        stored_gate,
        facts=tuple(stored_facts),
    )


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
                "editorialShotSize": item["editorialShotSize"],
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

    def test_v2_represents_exact_ep01_as_non_executable_local_draft(self):
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
        draft = result["shotPlanDraft"]
        shots = result["creativeShotDrafts"]

        self.assertEqual(run["manifest"]["schemaVersion"], "k2.golden-episode.manifest.v2")
        self.assertEqual(run["manifest"]["expectedShotCount"], 12)
        self.assertEqual(
            run["manifest"]["shotPlanAuthorityState"],
            "LOCAL_STRUCTURAL_REPRESENTATION_ONLY",
        )
        self.assertEqual(run["manifest"]["shotPlanApprovalState"], "NOT_VERIFIED")
        self.assertEqual(
            run["manifest"]["cameraContractState"], "NOT_READY"
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

        self.assertEqual(
            draft["schemaVersion"],
            "v5.local-structural-shot-plan-draft.v1",
        )
        self.assertEqual(draft["status"], "LOCAL_STRUCTURAL_DRAFT")
        self.assertEqual(
            draft["executionAuthorizationState"],
            "PREFLIGHT_ONLY_NOT_AUTHORIZED",
        )
        self.assertFalse(draft["dispatchAllowed"])
        self.assertEqual(result["state"], "SCRIPT_VALIDATED")
        self.assertEqual(
            [shot["durationFrames"] for shot in shots],
            [60, 60, 48, 60, 60, 48, 60, 60, 48, 72, 72, 72],
        )
        expected_budgets = ep01_shot_budgets(self.generated["scriptVersion"])
        self.assertEqual(
            [shot["editorialShotSize"] for shot in shots],
            [item["editorialShotSize"] for item in package_shots],
        )
        self.assertTrue(all("cameraInstruction" not in shot for shot in shots))
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
        self.assertEqual(draft["output"]["totalFrames"], 720)
        self.assertEqual(draft["output"]["generationCanvas"], output["generationCanvas"])
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
        self.assertEqual(face_binding["identityLockRef"], draft["identityLockRef"])
        self.assertEqual(
            face_binding["identityLockVersionRef"], draft["identityLockVersionRef"]
        )
        self.assertEqual(face_binding["identityLockDigest"], draft["identityLockDigest"])
        self.assertNotIn("visibleCharacterNames", draft["shots"][3])
        self.assertEqual(draft["shots"][3]["visibleCharacterRefs"], ["character-lin"])
        self.assertEqual(
            draft["shots"][3]["visibleIdentityBindings"],
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
            draft["shots"][9]["dialogueRequirement"],
            {
                "speaker": None,
                "text": "一次克制吸气，无台词。",
                "sourceMode": "SFX_OR_SILENCE",
            },
        )
        self.assertEqual(draft["shots"][9]["dialogueSyncMode"], "NONE")
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
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in (
            "ExecutableShotGraph",
            "executableShotGraph",
            "CreativeShotVersion",
            "creativeShotVersion",
            "StoryboardVersion",
            "storyboardVersion",
            "cameraInstruction",
            "SHOTS_COMPILED",
        ):
            self.assertNotIn(forbidden, serialized)
        validate_shot_plan_draft(draft)

        shot_graph_service = boundary._EpisodeProductionPublicBoundary__shot_graph
        gates = shot_graph_service.evidence.list_gates(
            WORKSPACE, run["productionRunRef"]
        )
        self.assertEqual(
            [gate["gateName"] for gate in gates],
            ["G2_AUTHORITY_IDENTITY", "G3_SCRIPT_VALIDATION"],
        )
        self.assertEqual(
            shot_graph_service.evidence.current_state(
                WORKSPACE, run["productionRunRef"]
            ),
            "SCRIPT_VALIDATED",
        )
        projection = boundary.get_state_projection(
            WORKSPACE, run["productionRunRef"]
        )
        self.assertEqual(projection["productionState"], "SCRIPT_VALIDATED")
        self.assertEqual(projection["state"], "SCRIPT_VALIDATED")

    def test_v2_root_and_draft_replay_are_stable(self):
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
            compiled_replay["shotPlanDraft"], compiled["shotPlanDraft"]
        )

        changed = self.command()
        changed["shotBudgets"][0]["actionBeat"] += "。"
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.create_run(changed)
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (409, "idempotency_conflict"),
        )

    def test_v2_draft_survives_sqlite_restart_without_state_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "episode-production.sqlite3"
            evidence = Path(directory) / "episode-evidence.sqlite3"
            kwargs = {
                "project_boundary": PortraitProjectBoundary(
                    self.assembly.project_context
                ),
                "series_episode_boundary": self.assembly.series_episode,
                "series_planning_boundary": self.assembly.series_planning,
                "script_studio_boundary": self.assembly.script_studio,
                "evidence_database_path": evidence,
                "identity_reference_authority": k2_identity_authority(),
                "ref_factory": self.refs,
                "clock": lambda: "2026-08-25T00:00:00Z",
            }
            first = create_local_development_boundary(database, **kwargs)
            run = first.create_run(self.command(idempotencyKey="sqlite-draft-run"))
            first.authorize_and_lock(self.g2_command(run))
            prepared = first.compile_shot_graph(
                g3_command(run, idempotencyKey="sqlite-draft-g3")
            )

            restored = create_local_development_boundary(
                database,
                **{**kwargs, "initialize_if_missing": False},
            )
            bundle = restored.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            )
            self.assertEqual(bundle["shotPlanDraft"], prepared["shotPlanDraft"])
            self.assertEqual(bundle["state"], "SCRIPT_VALIDATED")
            service = restored._EpisodeProductionPublicBoundary__shot_graph
            self.assertEqual(
                service.evidence.current_state(WORKSPACE, run["productionRunRef"]),
                "SCRIPT_VALIDATED",
            )
            self.assertIsNone(
                service.evidence.get_gate(
                    WORKSPACE, run["productionRunRef"], "G3_SHOT_GRAPH"
                )
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
        dialogue_drift[10]["dialogueRequirement"]["text"] += "漂移"
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

        missing_editorial_shot_size = ep01_shot_budgets(
            self.generated["scriptVersion"]
        )
        missing_editorial_shot_size[0].pop("editorialShotSize")
        cases.append(missing_editorial_shot_size)

        fabricated_camera = ep01_shot_budgets(self.generated["scriptVersion"])
        fabricated_camera[0]["camera"] = {
            "shotSize": "ECU",
            "movement": "locked-off",
            "angle": "top-down",
            "lensMm": 65,
            "intent": "fabricated",
        }
        cases.append(fabricated_camera)

        camera_like_editorial_size = ep01_shot_budgets(
            self.generated["scriptVersion"]
        )
        camera_like_editorial_size[0]["editorialShotSize"] = (
            "ECU 65mm top-down dolly-in"
        )
        cases.append(camera_like_editorial_size)

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

        with self.assertRaises(EpisodeProductionPublicError) as caught:
            self.boundary(aspect_ratio="16:9").create_run(
                self.command(idempotencyKey="k2-002-landscape-explicit-budgets")
            )
        self.assertEqual(
            (caught.exception.status, caught.exception.code),
            (400, "invalid_request"),
        )

    def test_shot_plan_draft_validator_rejects_tampering(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        draft = compiled["shotPlanDraft"]
        storyboard = compiled["storyboardDraft"]
        creative_shots = compiled["creativeShotDrafts"]

        digest_tamper = copy.deepcopy(draft)
        digest_tamper["output"]["controlledExtensionAlgorithmDigest"] = "0" * 64
        digest_tamper = _reseal(digest_tamper)
        with self.assertRaisesRegex(Exception, "controlled extension"):
            validate_shot_plan_draft(digest_tamper)

        none_claims_lock = copy.deepcopy(draft)
        none_claims_lock["shots"][0]["requiredCharacterIdentityLocks"] = copy.deepcopy(
            none_claims_lock["shots"][3]["requiredCharacterIdentityLocks"]
        )
        none_claims_lock = _reseal(none_claims_lock)
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_shot_plan_draft(none_claims_lock)

        body_claims_face = copy.deepcopy(draft)
        body_claims_face["shots"][4]["requiredCharacterIdentityLocks"][0][
            "identityLockRef"
        ] = draft["identityLockRef"]
        body_claims_face = _reseal(body_claims_face)
        with self.assertRaisesRegex(Exception, "BODY_ONLY"):
            validate_shot_plan_draft(body_claims_face)

        face_lock_missing = copy.deepcopy(draft)
        face_lock_missing["shots"][3]["requiredCharacterIdentityLocks"] = []
        face_lock_missing = _reseal(face_lock_missing)
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_shot_plan_draft(face_lock_missing)

        action_drift = copy.deepcopy(draft)
        action_drift["shots"][0]["actionBeat"] = " "
        action_drift = _reseal(action_drift)
        with self.assertRaisesRegex(Exception, "action beat"):
            validate_shot_plan_draft(action_drift)

        dialogue_mode_drift = copy.deepcopy(draft)
        dialogue_mode_drift["shots"][10]["dialogueSyncMode"] = "NONE"
        dialogue_mode_drift = _reseal(dialogue_mode_drift)
        with self.assertRaisesRegex(Exception, "dialogue sync"):
            validate_shot_plan_draft(dialogue_mode_drift)

        mixed_binding_drift = copy.deepcopy(draft)
        mixed_binding_drift["shots"][9]["visibleIdentityBindings"][1][
            "bindingMode"
        ] = "FACE_LOCK"
        mixed_binding_drift = _reseal(mixed_binding_drift)
        with self.assertRaisesRegex(Exception, "visible character binding"):
            validate_shot_plan_draft(mixed_binding_drift)

        mixed_body_speaker_lip_sync = copy.deepcopy(draft)
        mixed_body_speaker_lip_sync["shots"][9][
            "dialogueSyncMode"
        ] = "VERIFIED_LIP_SYNC"
        mixed_body_speaker_lip_sync = _reseal(mixed_body_speaker_lip_sync)
        with self.assertRaisesRegex(Exception, "trusted evidence"):
            validate_shot_plan_draft(mixed_body_speaker_lip_sync)

        mixed_face_speaker_lip_sync = copy.deepcopy(draft)
        mixed_face_speaker_lip_sync["shots"][9][
            "dialogueSyncMode"
        ] = "VERIFIED_LIP_SYNC"
        mixed_face_speaker_lip_sync["shots"][9]["dialogueRequirement"][
            "speaker"
        ] = "沈知微"
        mixed_face_speaker_lip_sync = _reseal(mixed_face_speaker_lip_sync)
        with self.assertRaisesRegex(Exception, "trusted evidence"):
            validate_shot_plan_draft(mixed_face_speaker_lip_sync)

        camera_injection = copy.deepcopy(draft)
        camera_injection["shots"][0]["cameraInstruction"] = {
            "shotSize": "ECU",
            "movement": "locked-off",
            "angle": "top-down",
            "lensMm": 65,
            "intent": "fabricated",
        }
        camera_injection = _reseal(camera_injection)
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(camera_injection)

        canonical_ref_injection = copy.deepcopy(draft)
        canonical_ref_injection["shots"][0][
            "creativeShotVersionRef"
        ] = "forged-creative-shot-version"
        canonical_ref_injection = _reseal(canonical_ref_injection)
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(canonical_ref_injection)

        top_level_canonical_ref_injection = copy.deepcopy(draft)
        top_level_canonical_ref_injection[
            "creativeShotVersionRef"
        ] = "forged-creative-shot-version"
        top_level_canonical_ref_injection = _reseal(
            top_level_canonical_ref_injection
        )
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(top_level_canonical_ref_injection)

        production_camera_injection = copy.deepcopy(draft)
        production_camera_injection["shots"][0]["lensMm"] = 65
        production_camera_injection = _reseal(production_camera_injection)
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(production_camera_injection)

        editorial_camera_injection = copy.deepcopy(draft)
        editorial_camera_injection["shots"][0]["editorialShotSize"] = (
            "ECU 65mm top-down dolly-in"
        )
        editorial_camera_injection = _reseal(editorial_camera_injection)
        with self.assertRaisesRegex(Exception, "editorial shot size"):
            validate_shot_plan_draft(editorial_camera_injection)

        output_camera_injection = copy.deepcopy(draft)
        output_camera_injection["output"]["cameraInstruction"] = "fabricated"
        output_camera_injection = _reseal(output_camera_injection)
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(output_camera_injection)

        publication_injection = copy.deepcopy(draft)
        publication_injection["publicationAllowed"] = True
        publication_injection = _reseal(publication_injection)
        with self.assertRaisesRegex(Exception, "execution authority"):
            validate_shot_plan_draft(publication_injection)

        canonical_edge_injection = copy.deepcopy(draft)
        canonical_edge_injection["edges"][0]["fromShotRef"] = (
            canonical_edge_injection["edges"][0]["fromShotDraftRef"]
        )
        canonical_edge_injection = _reseal(canonical_edge_injection)
        with self.assertRaisesRegex(Exception, "canonical or camera"):
            validate_shot_plan_draft(canonical_edge_injection)

        creative_camera_injection = copy.deepcopy(creative_shots[0])
        creative_camera_injection["cameraInstruction"] = "fabricated"
        creative_camera_injection = _reseal(creative_camera_injection)
        with self.assertRaises(Exception):
            validate_creative_shot_draft(creative_camera_injection)

        creative_version_injection = copy.deepcopy(creative_shots[0])
        creative_version_injection["creativeShotVersionRef"] = "forged-version"
        creative_version_injection = _reseal(creative_version_injection)
        with self.assertRaises(Exception):
            validate_creative_shot_draft(creative_version_injection)

        creative_extra_injection = copy.deepcopy(creative_shots[0])
        creative_extra_injection["audioRequirements"]["unexpected"] = []
        creative_extra_injection = _reseal(creative_extra_injection)
        with self.assertRaises(Exception):
            validate_creative_shot_draft(creative_extra_injection)

        storyboard_version_injection = copy.deepcopy(storyboard)
        storyboard_version_injection["storyboardVersionRef"] = "forged-version"
        storyboard_version_injection = _reseal(storyboard_version_injection)
        with self.assertRaises(Exception):
            validate_storyboard_draft(storyboard_version_injection)

        storyboard_scene_camera_injection = copy.deepcopy(storyboard)
        storyboard_scene_camera_injection["scenes"][0][
            "cameraInstruction"
        ] = "fabricated"
        storyboard_scene_camera_injection["scenes"][0] = _reseal(
            storyboard_scene_camera_injection["scenes"][0]
        )
        storyboard_scene_camera_injection = _reseal(
            storyboard_scene_camera_injection
        )
        with self.assertRaises(Exception):
            validate_storyboard_draft(storyboard_scene_camera_injection)

        storyboard_scene_extra_injection = copy.deepcopy(storyboard)
        storyboard_scene_extra_injection["scenes"][0]["unexpected"] = False
        storyboard_scene_extra_injection["scenes"][0] = _reseal(
            storyboard_scene_extra_injection["scenes"][0]
        )
        storyboard_scene_extra_injection = _reseal(
            storyboard_scene_extra_injection
        )
        with self.assertRaises(Exception):
            validate_storyboard_draft(storyboard_scene_extra_injection)

        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        stored_gate = evidence._gates[gate_key]
        stored_facts = list(stored_gate.facts)
        for index, fact in enumerate(stored_facts):
            if fact.factKind == "CreativeShotDraft:0001":
                stored_facts[index] = EvidenceFact(
                    factKind=fact.factKind,
                    factRef=fact.factRef,
                    factVersion=fact.factVersion,
                    payload=creative_camera_injection,
                    payloadDigest=creative_camera_injection["payloadDigest"],
                )
                break
        evidence._gates[gate_key] = replace(
            stored_gate,
            facts=tuple(stored_facts),
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_shot_graph_bundle(WORKSPACE, run["productionRunRef"])
        self.assertEqual(caught.exception.status, 503)

    def test_resealed_consistency_validation_authority_injections_fail_closed(self):
        injections = (
            ("cameraInstruction", "fabricated"),
            ("publicationAllowed", True),
            ("unexpectedField", "forged"),
            ("sceneCheckRef", "forged-script-scene"),
        )
        for field, value in injections:
            with self.subTest(field=field):
                boundary = self.boundary()
                run = self.prepare(boundary)
                boundary.compile_shot_graph(g3_command(run))
                service = boundary._EpisodeProductionPublicBoundary__shot_graph
                evidence = service.evidence
                gate_key = (
                    WORKSPACE,
                    run["productionRunRef"],
                    "G3_SCRIPT_VALIDATION",
                )
                stored_gate = evidence._gates[gate_key]
                stored_facts = list(stored_gate.facts)
                consistency = next(
                    copy.deepcopy(dict(fact.payload))
                    for fact in stored_facts
                    if fact.factKind == "ConsistencyValidation"
                )
                draft = next(
                    copy.deepcopy(dict(fact.payload))
                    for fact in stored_facts
                    if fact.factKind == "ShotPlanDraft"
                )
                if field == "sceneCheckRef":
                    consistency["checks"][0]["scriptSceneRef"] = value
                else:
                    consistency[field] = value
                consistency = _reseal(consistency)
                draft["consistencyValidationDigest"] = consistency[
                    "payloadDigest"
                ]
                draft = _reseal(draft)
                for index, fact in enumerate(stored_facts):
                    if fact.factKind == "ConsistencyValidation":
                        stored_facts[index] = EvidenceFact(
                            factKind=fact.factKind,
                            factRef=fact.factRef,
                            factVersion=fact.factVersion,
                            payload=consistency,
                            payloadDigest=consistency["payloadDigest"],
                        )
                    elif fact.factKind == "ShotPlanDraft":
                        stored_facts[index] = EvidenceFact(
                            factKind=fact.factKind,
                            factRef=fact.factRef,
                            factVersion=fact.factVersion,
                            payload=draft,
                            payloadDigest=draft["payloadDigest"],
                        )
                evidence._gates[gate_key] = replace(
                    stored_gate,
                    facts=tuple(stored_facts),
                )
                with self.assertRaises(EpisodeProductionPublicError) as caught:
                    boundary.get_shot_graph_bundle(
                        WORKSPACE, run["productionRunRef"]
                    )
                self.assertEqual(caught.exception.status, 503)
                with self.assertRaises(RepositoryUnavailableError):
                    service.verify_shot_plan_draft_current(
                        WORKSPACE, run["productionRunRef"]
                    )
                self.assertEqual(
                    evidence.current_state(WORKSPACE, run["productionRunRef"]),
                    "SCRIPT_VALIDATED",
                )

    def test_coordinated_creative_and_plan_reseal_cannot_escape_root_budgets(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        stored_gate = evidence._gates[gate_key]
        stored_facts = list(stored_gate.facts)
        creative = next(
            copy.deepcopy(dict(fact.payload))
            for fact in stored_facts
            if fact.factKind == "CreativeShotDraft:0001"
        )
        draft = next(
            copy.deepcopy(dict(fact.payload))
            for fact in stored_facts
            if fact.factKind == "ShotPlanDraft"
        )
        creative["action"] = "协调重封后伪造的动作。"
        creative["actionBeat"] = creative["action"]
        creative = _reseal(creative)
        draft["shots"][0]["actionBeat"] = creative["actionBeat"]
        draft["shots"][0]["payloadDigest"] = creative["payloadDigest"]
        draft = _reseal(draft)
        for index, fact in enumerate(stored_facts):
            if fact.factKind == "CreativeShotDraft:0001":
                stored_facts[index] = EvidenceFact(
                    factKind=fact.factKind,
                    factRef=fact.factRef,
                    factVersion=fact.factVersion,
                    payload=creative,
                    payloadDigest=creative["payloadDigest"],
                )
            elif fact.factKind == "ShotPlanDraft":
                stored_facts[index] = EvidenceFact(
                    factKind=fact.factKind,
                    factRef=fact.factRef,
                    factVersion=fact.factVersion,
                    payload=draft,
                    payloadDigest=draft["payloadDigest"],
                )
        evidence._gates[gate_key] = replace(
            stored_gate,
            facts=tuple(stored_facts),
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_shot_graph_bundle(WORKSPACE, run["productionRunRef"])
        self.assertEqual(caught.exception.status, 503)
        with self.assertRaises(RepositoryUnavailableError):
            service.verify_shot_plan_draft_current(
                WORKSPACE, run["productionRunRef"]
            )
        self.assertEqual(
            evidence.current_state(WORKSPACE, run["productionRunRef"]),
            "SCRIPT_VALIDATED",
        )

    def test_storyboard_identity_reseal_fails_get_and_preflight(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        storyboard = copy.deepcopy(compiled["storyboardDraft"])
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        storyboard["identityLockRef"] = "forged-identity-lock"
        storyboard["identityLockVersionRef"] = "forged-identity-lock-version"
        storyboard["identityLockDigest"] = "f" * 64
        storyboard = _reseal(storyboard)
        draft["storyboardDigest"] = storyboard["payloadDigest"]
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {"StoryboardDraft": storyboard, "ShotPlanDraft": draft},
        )

        for operation in (
            lambda: boundary.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            ),
            lambda: boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            ),
        ):
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                operation()
            self.assertEqual(caught.exception.status, 503)
        self.assertEqual(
            evidence.current_state(WORKSPACE, run["productionRunRef"]),
            "SCRIPT_VALIDATED",
        )

    def test_landscape_output_reseal_cannot_escape_frozen_portrait_root(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        draft["output"] = {
            **_output_profile_v2(portrait=False),
            "totalFrames": draft["output"]["totalFrames"],
        }
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {"ShotPlanDraft": draft},
        )
        with self.assertRaises(EpisodeProductionPublicError) as caught:
            boundary.get_shot_graph_bundle(WORKSPACE, run["productionRunRef"])
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(
            evidence.current_state(WORKSPACE, run["productionRunRef"]),
            "SCRIPT_VALIDATED",
        )

    def test_forged_creative_identity_reseal_fails_get_and_preflight(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        creative = copy.deepcopy(compiled["creativeShotDrafts"][3])
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        forged_ref = "forged-character-ref"
        lock = creative["requiredCharacterIdentityLocks"][0]
        lock["characterRef"] = forged_ref
        creative["visibleCharacterRefs"] = [forged_ref]
        creative["visibleIdentityBindings"] = [
            {"characterRef": forged_ref, "bindingMode": "FACE_LOCK"}
        ]
        for seed in creative["assetRequirementSeeds"]:
            if seed["requirementType"] == "character-identity":
                seed["requirementKey"] = f"character:{forged_ref}"
                seed["authorityRef"] = forged_ref
        creative = _reseal(creative)
        node = draft["shots"][3]
        for field in (
            "requiredCharacterIdentityLocks",
            "assetRequirementSeeds",
            "visibleCharacterRefs",
            "visibleIdentityBindings",
        ):
            node[field] = copy.deepcopy(creative[field])
        node["payloadDigest"] = creative["payloadDigest"]
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {
                "CreativeShotDraft:0004": creative,
                "ShotPlanDraft": draft,
            },
        )

        for operation in (
            lambda: boundary.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            ),
            lambda: boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            ),
        ):
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                operation()
            self.assertEqual(caught.exception.status, 503)
        self.assertEqual(
            evidence.current_state(WORKSPACE, run["productionRunRef"]),
            "SCRIPT_VALIDATED",
        )

    def test_storyboard_scene_duration_reseal_is_bound_to_root_scene_budget(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        storyboard = copy.deepcopy(compiled["storyboardDraft"])
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        storyboard["scenes"][0]["durationFrames"] += 24
        storyboard["scenes"][0] = _reseal(storyboard["scenes"][0])
        storyboard = _reseal(storyboard)
        draft["storyboardDigest"] = storyboard["payloadDigest"]
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {"StoryboardDraft": storyboard, "ShotPlanDraft": draft},
        )
        snapshot = evidence.read_snapshot(WORKSPACE, run["productionRunRef"])

        for operation in (
            lambda: boundary.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            ),
            lambda: boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            ),
        ):
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                operation()
            self.assertEqual(caught.exception.status, 503)
        with self.assertRaises(RepositoryUnavailableError):
            service.verify_shot_plan_draft_current(
                WORKSPACE, run["productionRunRef"]
            )
        self.assertEqual(
            evidence.read_snapshot(WORKSPACE, run["productionRunRef"]),
            snapshot,
        )

    def test_asset_seed_reseal_is_bound_to_current_g2_identity_lock(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        creative = copy.deepcopy(compiled["creativeShotDrafts"][3])
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        identity_seed = next(
            item
            for item in creative["assetRequirementSeeds"]
            if item["requirementType"] == "character-identity"
        )
        identity_seed["authorityRef"] = "forged-character-ref"
        identity_seed["authorityVersionRef"] = "forged-reference-version"
        identity_seed["authorityDigest"] = "f" * 64
        creative = _reseal(creative)
        draft["shots"][3]["assetRequirementSeeds"] = copy.deepcopy(
            creative["assetRequirementSeeds"]
        )
        draft["shots"][3]["payloadDigest"] = creative["payloadDigest"]
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {
                "CreativeShotDraft:0004": creative,
                "ShotPlanDraft": draft,
            },
        )
        snapshot = evidence.read_snapshot(WORKSPACE, run["productionRunRef"])

        for operation in (
            lambda: boundary.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            ),
            lambda: boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            ),
        ):
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                operation()
            self.assertEqual(caught.exception.status, 503)
        with self.assertRaises(RepositoryUnavailableError):
            service.verify_shot_plan_draft_current(
                WORKSPACE, run["productionRunRef"]
            )
        self.assertEqual(
            evidence.read_snapshot(WORKSPACE, run["productionRunRef"]),
            snapshot,
        )

    def test_non_character_asset_seed_reseal_is_bound_to_current_m6_facts(self):
        boundary = self.boundary()
        run = self.prepare(boundary)
        compiled = boundary.compile_shot_graph(g3_command(run))
        service = boundary._EpisodeProductionPublicBoundary__shot_graph
        evidence = service.evidence
        gate_key = (
            WORKSPACE,
            run["productionRunRef"],
            "G3_SCRIPT_VALIDATION",
        )
        creative = copy.deepcopy(compiled["creativeShotDrafts"][0])
        draft = copy.deepcopy(compiled["shotPlanDraft"])
        style_seed = next(
            item
            for item in creative["assetRequirementSeeds"]
            if item["requirementType"] == "visual-style"
        )
        style_seed["authorityRef"] = "forged-visual-constraint"
        style_seed["requirementKey"] = "style:forged-visual-constraint"
        creative = _reseal(creative)
        draft["shots"][0]["assetRequirementSeeds"] = copy.deepcopy(
            creative["assetRequirementSeeds"]
        )
        draft["shots"][0]["payloadDigest"] = creative["payloadDigest"]
        draft = _reseal(draft)
        _replace_gate_payloads(
            evidence,
            gate_key,
            {
                "CreativeShotDraft:0001": creative,
                "ShotPlanDraft": draft,
            },
        )
        snapshot = evidence.read_snapshot(WORKSPACE, run["productionRunRef"])

        for operation in (
            lambda: boundary.get_shot_graph_bundle(
                WORKSPACE, run["productionRunRef"]
            ),
            lambda: boundary.preflight_dynamic_real_media_plan(
                {
                    "workspaceRef": WORKSPACE,
                    "productionRunRef": run["productionRunRef"],
                }
            ),
        ):
            with self.assertRaises(EpisodeProductionPublicError) as caught:
                operation()
            self.assertEqual(caught.exception.status, 503)
        with self.assertRaises(RepositoryUnavailableError):
            service.verify_shot_plan_draft_current(
                WORKSPACE, run["productionRunRef"]
            )
        self.assertEqual(
            evidence.read_snapshot(WORKSPACE, run["productionRunRef"]),
            snapshot,
        )

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
