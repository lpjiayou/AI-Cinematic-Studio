from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import unittest

from services.v4_platform.audio_synthesis import (
    SOURCE_AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
)
from services.v5_core_os.episode_production import (
    AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
    AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
    LegacyAudioTargetError,
    validate_audio_generation_request,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    StaleInputError,
    _digest,
)
from tests.unit.test_explicit_audio_bridge_m9_m12 import (
    confirm_fixed_voice,
    fixed_voice_asset,
    route_command,
)
from tests.unit.test_execution_method_planning_m8_m9 import (
    plan_command,
    seeded_plan,
)


def resealed(value):
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result["payloadDigest"] = _digest(result)
    return result


class M9M12ExplicitAudioBridgeContractTests(unittest.TestCase):
    def setUp(self):
        self.seed, validation = seeded_plan()
        self.plan = self.seed["boundary"].create_execution_method_plan(
            plan_command(self.seed, validation)
        )
        self.requirement = self.plan["audioRequirements"][0]
        self.confirmed = confirm_fixed_voice(
            self.seed, "character-gu", "contract-gu"
        )
        self.voice = fixed_voice_asset(
            self.seed, self.confirmed, "contract-gu"
        )
        command = route_command(
            self.seed,
            self.plan,
            self.requirement,
            key="m9-m12-contract-route",
            voices={"character-gu": self.voice},
        )
        self.request = self.seed[
            "boundary"
        ].create_explicit_audio_generation_request(command)[
            "audioGenerationRequest"
        ]

    def validate(self, value):
        return validate_audio_generation_request(
            value,
            confirmed_voice_lock=self.confirmed,
            voice_asset_version=self.voice,
            audio_requirement=self.requirement,
            execution_method_plan=self.plan,
        ).as_dict()

    def test_v2_adds_exact_m9_authority_without_changing_v1_runtime_protocol(self):
        self.assertEqual(
            self.request["schemaVersion"],
            AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
        )
        self.assertEqual(self.validate(self.request), self.request)
        self.assertEqual(
            SOURCE_AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
            AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
        )
        self.assertNotEqual(
            SOURCE_AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
            AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
        )

        unknown = deepcopy(self.request)
        unknown["runtimeDispatch"] = True
        unknown = resealed(unknown)
        with self.assertRaises(EpisodeProductionError):
            self.validate(unknown)

        legacy_target = deepcopy(self.request)
        legacy_target["outputTarget"] = "LEGACY_MEDIA_FILE"
        legacy_target = resealed(legacy_target)
        with self.assertRaises(LegacyAudioTargetError):
            self.validate(legacy_target)

    def test_span_text_script_and_speaker_drift_are_rejected(self):
        cases = []

        changed = deepcopy(self.request)
        changed["sourceSpan"]["endOffsetExclusive"] -= 1
        cases.append(("source-span", resealed(changed)))

        changed = deepcopy(self.request)
        changed["sourceTextDigest"] = "f" * 64
        cases.append(("source-text-digest", resealed(changed)))

        changed = deepcopy(self.request)
        changed["requestSpec"]["normalizedSpeechParameters"]["text"] = (
            "从现在起，只相信未经确认的文本。"
        )
        cases.append(("source-text", resealed(changed)))

        changed = deepcopy(self.request)
        changed["requestSpec"]["scriptVersionDigest"] = "e" * 64
        cases.append(("nested-script", resealed(changed)))

        changed = deepcopy(self.request)
        changed["speakerCharacterRef"] = "character-lin"
        cases.append(("speaker", resealed(changed)))

        for name, invalid in cases:
            with self.subTest(drift=name), self.assertRaises(StaleInputError):
                self.validate(invalid)

        text = self.request["requestSpec"]["normalizedSpeechParameters"]["text"]
        self.assertEqual(
            sha256(text.encode("utf-8")).hexdigest(),
            self.request["sourceTextDigest"],
        )

    def test_voice_lineage_cannot_be_claimed_by_a_fixed_voice(self):
        invalid = deepcopy(self.request)
        invalid["voiceLineage"] = {
            "consentGrantRef": "forged-consent",
            "consentGrantVersionRef": "forged-consent-version",
            "consentGrantVersionDigest": "a" * 64,
            "voiceLockVersionRef": "forged-lock-version",
            "voiceLockVersionDigest": "b" * 64,
            "voiceProfileRef": "forged-profile",
            "voiceProfileVersionRef": "forged-profile-version",
            "voiceProfileVersionDigest": "c" * 64,
        }
        invalid = resealed(invalid)
        with self.assertRaises(EpisodeProductionError):
            self.validate(invalid)


if __name__ == "__main__":
    unittest.main()
