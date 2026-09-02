from __future__ import annotations

from copy import deepcopy
import unittest

from services.v5_core_os.episode_production import (
    AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
    AUDIO_REQUIREMENT_ROUTE_RECORD_KIND,
    EpisodeProductionPublicError,
    build_voice_asset_version,
)
from tests.contract.test_m12_audio_authority_contract import (
    rights_binding,
    voice_asset_command,
)
from tests.unit.test_episode_production_k2 import WORKSPACE
from tests.unit.test_execution_method_planning_m8_m9 import (
    plan_command,
    seeded_plan,
)
from tests.unit.test_narrative_currentness_m7 import validation_command


def explicit_audio_service(boundary):
    return boundary._EpisodeProductionPublicBoundary__explicit_audio_bridge


def confirm_fixed_voice(seed, character_ref, suffix):
    boundary = seed["boundary"]
    created = boundary.create_voice_lock(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": seed["project"]["projectRef"],
            "seriesRef": seed["series"]["seriesRef"],
            "characterRef": character_ref,
            "engineFamily": "local-neural-tts-v1",
            "voiceId": f"fixed-voice-{suffix}",
            "gender": "male" if character_ref.endswith("gu") else "female",
            "apparentAge": 36,
            "pitchSemitones": 0.0,
            "rateScale": 1.0,
            "timbreDescriptor": "stable-neutral-register",
            "languageCode": "zh-CN",
            "idempotencyKey": f"m9-m12-voice-create-{suffix}",
        }
    )
    return boundary.confirm_voice_lock(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": seed["project"]["projectRef"],
            "seriesRef": seed["series"]["seriesRef"],
            "voiceRef": created["voiceLock"]["voiceRef"],
            "voiceLockVersionRef": created["voiceLockVersion"][
                "voiceLockVersionRef"
            ],
            "voiceLockDigest": created["voiceLockVersion"]["payloadDigest"],
            "expectedRevision": created["voiceLock"]["revision"],
            "idempotencyKey": f"m9-m12-voice-confirm-{suffix}",
        }
    )


def fixed_voice_asset(seed, confirmed, suffix):
    command = voice_asset_command(confirmed)
    command.update(
        {
            "workspaceRef": WORKSPACE,
            "projectRef": seed["project"]["projectRef"],
            "seriesRef": seed["series"]["seriesRef"],
            "episodeRef": seed["episode"]["episodeRef"],
            "productionRunRef": seed["run"]["productionRunRef"],
            "assetRef": f"fixed-voice-asset-{suffix}",
            "assetVersionRef": f"fixed-voice-asset-version-{suffix}",
            "createdBy": "v5.m9-m12.bridge-test",
        }
    )
    return build_voice_asset_version(
        command, confirmed_voice_lock=confirmed
    )


def route_command(seed, plan, requirement, *, key, voices):
    command = {
        "workspaceRef": WORKSPACE,
        "projectRef": seed["project"]["projectRef"],
        "seriesRef": seed["series"]["seriesRef"],
        "episodeRef": seed["episode"]["episodeRef"],
        "productionRunRef": seed["run"]["productionRunRef"],
        "executionMethodPlanVersionRef": plan[
            "executionMethodPlanVersionRef"
        ],
        "audioRequirementRef": requirement["audioRequirementRef"],
        "idempotencyKey": key,
    }
    audio_type = requirement["audioType"]
    if audio_type not in {"SILENCE", "MUSIC"}:
        command["rightsBinding"] = rights_binding(
            asset_requirement_ref=requirement["audioRequirementRef"],
            asset_requirement_digest=requirement["payloadDigest"],
        )
    if audio_type == "DIALOGUE":
        command["voiceAssetVersion"] = voices["character-gu"]
    elif audio_type == "NARRATION":
        command["voiceAssetVersion"] = voices["character-lin"]
    return command


class ExplicitAudioBridgeM9M12Tests(unittest.TestCase):
    def setUp(self):
        self.seed, validation = seeded_plan()
        self.plan = self.seed["boundary"].create_execution_method_plan(
            plan_command(self.seed, validation)
        )
        self.confirmed = {
            character: confirm_fixed_voice(self.seed, character, suffix)
            for character, suffix in (
                ("character-gu", "gu"),
                ("character-lin", "lin"),
            )
        }
        self.voices = {
            character: fixed_voice_asset(
                self.seed,
                self.confirmed[character],
                "gu" if character.endswith("gu") else "lin",
            )
            for character in self.confirmed
        }

    def create(self, requirement, *, key=None):
        return self.seed["boundary"].create_explicit_audio_generation_request(
            route_command(
                self.seed,
                self.plan,
                requirement,
                key=key or f"route-{requirement['audioType'].lower()}",
                voices=self.voices,
            )
        )

    def test_every_explicit_requirement_routes_by_closed_audio_type(self):
        created = {
            requirement["audioType"]: self.create(requirement)
            for requirement in self.plan["audioRequirements"]
        }

        for audio_type in ("DIALOGUE", "NARRATION", "SFX", "AMBIENCE"):
            route = created[audio_type]
            request = route["audioGenerationRequest"]
            requirement = next(
                item
                for item in self.plan["audioRequirements"]
                if item["audioType"] == audio_type
            )
            self.assertEqual(route["routeDisposition"], "REQUEST_CREATED")
            self.assertEqual(
                request["schemaVersion"],
                AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
            )
            self.assertEqual(
                (request["audioRequirementRef"], request["audioRequirementDigest"]),
                (
                    requirement["audioRequirementRef"],
                    requirement["payloadDigest"],
                ),
            )
            self.assertEqual(request["timingReference"], requirement["timingReference"])
            self.assertEqual(
                route["audioCueTimingBinding"]["timingReference"],
                requirement["timingReference"],
            )
            self.assertFalse(route["m12RuntimeInstalled"])
            self.assertEqual(
                route["m12RuntimeState"], "NOT_INSTALLED_G0_NOT_COMPLETE"
            )
            self.assertFalse(route["publicationAllowed"])

        dialogue = created["DIALOGUE"]["audioGenerationRequest"]
        self.assertEqual(dialogue["speakerCharacterRef"], "character-gu")
        self.assertEqual(
            dialogue["requestSpec"]["normalizedSpeechParameters"]["text"],
            "从现在起，只相信我们亲眼看到的。",
        )
        self.assertEqual(
            dialogue["sourceTextDigest"],
            next(
                item["sourceTextDigest"]
                for item in self.plan["audioRequirements"]
                if item["audioType"] == "DIALOGUE"
            ),
        )
        narration = created["NARRATION"]["audioGenerationRequest"]
        self.assertNotIn("speakerCharacterRef", narration)
        self.assertEqual(
            narration["requestSpec"]["normalizedSpeechParameters"]["text"],
            "档案仍在低鸣。",
        )
        self.assertEqual(
            created["SFX"]["audioGenerationRequest"]["requestKind"],
            "SFX_GENERATION",
        )
        self.assertEqual(
            created["AMBIENCE"]["audioGenerationRequest"]["requestKind"],
            "AMBIENCE_GENERATION",
        )
        self.assertNotIn(
            "normalizedSpeechParameters",
            created["SFX"]["audioGenerationRequest"]["requestSpec"],
        )
        self.assertNotIn(
            "normalizedSpeechParameters",
            created["AMBIENCE"]["audioGenerationRequest"]["requestSpec"],
        )

        for audio_type, disposition in (
            ("SILENCE", "NO_REQUEST_SILENCE"),
            ("MUSIC", "MUSIC_NOT_IMPLEMENTED"),
        ):
            route = created[audio_type]
            self.assertEqual(route["routeDisposition"], disposition)
            self.assertIsNone(route["audioGenerationRequest"])
            self.assertIsNone(route["audioCueTimingBinding"])
            self.assertIsNone(route["voiceAssetVersionSnapshot"])

        service = explicit_audio_service(self.seed["boundary"])
        records = service.evidence_repository.list_records(
            WORKSPACE, self.seed["run"]["productionRunRef"]
        )
        kinds = [record["recordKind"] for record in records]
        self.assertEqual(
            kinds.count(AUDIO_REQUIREMENT_ROUTE_RECORD_KIND),
            len(self.plan["audioRequirements"]),
        )
        self.assertNotIn("GenerationRequest", kinds)
        self.assertNotIn("AudioGenerationRequest", kinds)
        self.assertNotIn("MediaJob", kinds)
        self.assertNotIn("storageKey", repr(created))

    def test_replay_conflict_foreign_scope_and_stale_m9_fail_closed(self):
        requirement = self.plan["audioRequirements"][0]
        command = route_command(
            self.seed,
            self.plan,
            requirement,
            key="m9-m12-exact-replay",
            voices=self.voices,
        )
        created = self.seed["boundary"].create_explicit_audio_generation_request(
            command
        )
        replay = self.seed["boundary"].create_explicit_audio_generation_request(
            command
        )
        self.assertTrue(replay["idempotentReplay"])
        self.assertEqual(replay["payloadDigest"], created["payloadDigest"])

        changed = deepcopy(command)
        changed["rightsBinding"] = rights_binding(
            asset_requirement_ref=requirement["audioRequirementRef"],
            asset_requirement_digest=requirement["payloadDigest"],
            source_refs=[
                {"sourceRef": "extra-rights-proof", "sourceDigest": "f" * 64}
            ],
        )
        with self.assertRaises(EpisodeProductionPublicError) as conflict:
            self.seed["boundary"].create_explicit_audio_generation_request(changed)
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

        with self.assertRaises(EpisodeProductionPublicError) as foreign:
            self.seed["boundary"].get_explicit_audio_requirement_route(
                "foreign-workspace",
                self.seed["project"]["projectRef"],
                self.seed["series"]["seriesRef"],
                self.seed["episode"]["episodeRef"],
                self.seed["run"]["productionRunRef"],
                created["audioRequirementRouteVersionRef"],
            )
        self.assertEqual(foreign.exception.code, "not_found")

        self.seed["boundary"].create_narrative_validation(
            validation_command(self.seed, key="newer-m9-source-validation")
        )
        restored = self.seed["boundary"].get_explicit_audio_requirement_route(
            WORKSPACE,
            self.seed["project"]["projectRef"],
            self.seed["series"]["seriesRef"],
            self.seed["episode"]["episodeRef"],
            self.seed["run"]["productionRunRef"],
            created["audioRequirementRouteVersionRef"],
        )
        self.assertEqual(restored["currentness"], "STALE")
        with self.assertRaises(EpisodeProductionPublicError) as stale:
            self.seed["boundary"].create_explicit_audio_generation_request(
                {
                    **command,
                    "idempotencyKey": "route-against-stale-m9",
                }
            )
        self.assertEqual(stale.exception.code, "execution_not_authorized")

    def test_confirmed_voice_lock_successor_makes_stored_route_stale(self):
        requirement = self.plan["audioRequirements"][0]
        created = self.create(requirement, key="route-before-voice-drift")
        confirmed = self.confirmed["character-gu"]
        successor = self.seed["boundary"].create_voice_lock_version(
            {
                "workspaceRef": WORKSPACE,
                "projectRef": self.seed["project"]["projectRef"],
                "seriesRef": self.seed["series"]["seriesRef"],
                "voiceRef": confirmed["voiceLock"]["voiceRef"],
                "baseVoiceLockVersionRef": confirmed["voiceLockVersion"][
                    "voiceLockVersionRef"
                ],
                "baseVoiceLockDigest": confirmed["voiceLockVersion"][
                    "payloadDigest"
                ],
                "expectedRevision": confirmed["voiceLock"]["revision"],
                "engineFamily": "local-neural-tts-v1",
                "voiceId": "fixed-voice-gu-successor",
                "gender": "male",
                "apparentAge": 38,
                "pitchSemitones": -0.5,
                "rateScale": 0.98,
                "timbreDescriptor": "stable-neutral-register-successor",
                "languageCode": "zh-CN",
                "idempotencyKey": "m9-m12-voice-gu-successor",
            }
        )
        self.seed["boundary"].confirm_voice_lock(
            {
                "workspaceRef": WORKSPACE,
                "projectRef": self.seed["project"]["projectRef"],
                "seriesRef": self.seed["series"]["seriesRef"],
                "voiceRef": successor["voiceLock"]["voiceRef"],
                "voiceLockVersionRef": successor["voiceLockVersion"][
                    "voiceLockVersionRef"
                ],
                "voiceLockDigest": successor["voiceLockVersion"]["payloadDigest"],
                "expectedRevision": successor["voiceLock"]["revision"],
                "idempotencyKey": "m9-m12-voice-gu-successor-confirm",
            }
        )
        restored = self.seed["boundary"].get_explicit_audio_requirement_route(
            WORKSPACE,
            self.seed["project"]["projectRef"],
            self.seed["series"]["seriesRef"],
            self.seed["episode"]["episodeRef"],
            self.seed["run"]["productionRunRef"],
            created["audioRequirementRouteVersionRef"],
        )
        self.assertEqual(restored["currentness"], "STALE")


if __name__ == "__main__":
    unittest.main()
