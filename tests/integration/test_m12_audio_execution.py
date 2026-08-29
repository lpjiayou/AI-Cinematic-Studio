from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from services.v4_platform.audio import (
    PRELIMINARY_MIX_ADAPTER_ID,
    DeterministicPreliminaryMixAdapter,
    DeterministicProgrammaticAudioAdapter,
    audio_artifact_evidence,
    emotion_parameters,
)
from services.v5_core_os.episode_production.audio import (
    build_preliminary_mix_request,
    build_programmatic_audio_request,
    build_proposed_audio_asset_version,
    build_tts_execution_request,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.contract.test_m12_audio_execution_contract import dialogue_context
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter


SAMPLE_RATE = 48_000
SHORT_SAMPLES = 4_800


def _programmatic_request(effect_kind: str, *, ordinal: int) -> dict:
    role = "ambience" if effect_kind in {"rain", "wind"} else "sfx"
    dialogue_request, _ = dialogue_context()
    return build_programmatic_audio_request(
        {
            "workspaceRef": dialogue_request["workspaceRef"],
            "productionRunRef": dialogue_request["productionRunRef"],
            "assetRequirementRef": f"requirement-{effect_kind}",
            "assetRequirementDigest": _digest(
                {"requirement": effect_kind}
            ),
            "creativeShotRef": dialogue_request["creativeShotRef"],
            "creativeShotVersionRef": dialogue_request[
                "creativeShotVersionRef"
            ],
            "creativeShotDigest": dialogue_request["creativeShotDigest"],
            "scriptRef": dialogue_request["scriptRef"],
            "scriptVersionRef": dialogue_request["scriptVersionRef"],
            "scriptVersionDigest": dialogue_request["scriptVersionDigest"],
            "scriptSceneRef": dialogue_request["scriptSceneRef"],
            "sourceCueRef": f"scene-1-audio-cue-{ordinal}",
            "sourceCueDigest": _digest(
                {"effectKind": effect_kind, "ordinal": ordinal}
            ),
            "cueOrdinal": ordinal,
            "parameters": {
                "audioRole": role,
                "synthesisKind": "programmatic",
                "effectKind": effect_kind,
                "durationSamples": SHORT_SAMPLES,
                "sampleRate": SAMPLE_RATE,
                "channels": 1,
                "seed": 17 + ordinal,
            },
            "createdAt": "2026-08-29T00:00:00Z",
        }
    )


def _execute_dialogue(
    artifact_root: Path,
    *,
    storage_key: str,
) -> tuple[dict, dict, dict, dict, FixedWavTtsAdapter]:
    request, voice_lock = dialogue_context("whisper")
    execution = build_tts_execution_request(
        request, confirmed_voice_lock=voice_lock
    )
    runtime = FixedWavTtsAdapter()
    artifact = audio_artifact_evidence(
        execution,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=runtime,
    )
    proposed_asset = build_proposed_audio_asset_version(
        request,
        artifact,
        confirmed_voice_lock=voice_lock,
        created_at="2026-08-29T00:00:01Z",
    )
    return request, execution, artifact, proposed_asset, runtime


def _execute_programmatic(
    artifact_root: Path,
    *,
    effect_kind: str,
    ordinal: int,
    storage_key: str,
) -> tuple[dict, dict, dict]:
    request = _programmatic_request(effect_kind, ordinal=ordinal)
    artifact = audio_artifact_evidence(
        request,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=DeterministicProgrammaticAudioAdapter(),
    )
    proposed_asset = build_proposed_audio_asset_version(
        request,
        artifact,
        created_at="2026-08-29T00:00:01Z",
    )
    return request, artifact, proposed_asset


class M12AudioExecutionIntegrationTests(unittest.TestCase):
    def test_dialogue_flows_through_fake_piper_to_direct_proposed_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = "asset-versions/audio/shot-1/dialogue-1.wav"
            request, execution, artifact, asset, runtime = _execute_dialogue(
                root,
                storage_key=storage_key,
            )

            effective = deepcopy(execution["parameters"])
            effective["emotionParameters"] = emotion_parameters("whisper")
            self.assertNotEqual(request["payloadDigest"], execution["payloadDigest"])
            self.assertEqual(
                artifact["generationRequestDigest"], request["payloadDigest"]
            )
            self.assertEqual(
                artifact["executionRequestDigest"], execution["payloadDigest"]
            )
            self.assertEqual(
                artifact["parametersDigest"], _digest(execution["parameters"])
            )
            self.assertEqual(
                artifact["effectiveParametersDigest"], _digest(effective)
            )
            self.assertEqual(
                runtime.calls[0]["parameters"], execution["parameters"]
            )

            for field in (
                "assetRequirementRef",
                "assetRequirementDigest",
                "creativeShotRef",
                "creativeShotVersionRef",
                "creativeShotDigest",
                "scriptRef",
                "scriptVersionRef",
                "scriptVersionDigest",
                "scriptSceneRef",
            ):
                self.assertEqual(asset[field], request[field], field)
            self.assertEqual(
                asset["sourceBinding"],
                {
                    "kind": "scriptDialogue",
                    "sourceRef": request["sourceScriptSpan"],
                    "sourceDigest": request["dialogueSourceDigest"],
                    "ordinal": request["dialogueOrdinal"],
                },
            )
            self.assertEqual(
                asset["voiceBinding"]["voiceLockVersionRef"],
                request["voiceLockVersionRef"],
            )
            self.assertEqual(
                asset["voiceBinding"]["voiceLockDigest"],
                request["voiceLockDigest"],
            )
            self.assertEqual(
                asset["generationParametersDigest"],
                artifact["effectiveParametersDigest"],
            )
            for field in (
                "artifactEvidenceRef",
                "artifactEvidenceDigest",
                "artifactRef",
                "storageKey",
                "sha256",
                "sampleRate",
                "channels",
            ):
                self.assertEqual(asset[field], artifact[field], field)

            output = root / storage_key
            self.assertEqual(output.read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(list(root.rglob("*.wav")), [output])
            self.assertEqual(
                PurePosixPath(asset["storageKey"]).parts[:2],
                ("asset-versions", "audio"),
            )
            self.assertTrue(
                {"jobs", "legacy", "media"}.isdisjoint(
                    PurePosixPath(asset["storageKey"]).parts
                )
            )
            self.assertFalse(asset["publicationAllowed"])
            self.assertEqual(asset["state"], "PROPOSED")
            self.assertNotIn("assetAdmissionRef", asset)
            self.assertFalse(artifact["publicationAllowed"])
            self.assertFalse(artifact["generationResult"]["publicationAllowed"])
            self.assertFalse(artifact["artifactEvidence"]["publicationAllowed"])

    def test_rain_and_paper_are_deterministic_role_specific_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for ordinal, (effect_kind, expected_role) in enumerate(
                (("rain", "ambience"), ("paper", "sfx")), start=1
            ):
                with self.subTest(effect_kind=effect_kind):
                    request = _programmatic_request(effect_kind, ordinal=ordinal)
                    first = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=(
                            f"asset-versions/audio/shot-1/{effect_kind}-1.wav"
                        ),
                        adapter=DeterministicProgrammaticAudioAdapter(),
                    )
                    second = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=(
                            f"asset-versions/audio/shot-1/{effect_kind}-2.wav"
                        ),
                        adapter=DeterministicProgrammaticAudioAdapter(),
                    )
                    asset = build_proposed_audio_asset_version(
                        request,
                        first,
                        created_at="2026-08-29T00:00:01Z",
                    )

                    self.assertEqual(first["sha256"], second["sha256"])
                    self.assertEqual(first["probe"], second["probe"])
                    self.assertEqual(first["probe"]["durationSamples"], SHORT_SAMPLES)
                    self.assertEqual(asset["audioRole"], expected_role)
                    self.assertEqual(asset["sourceBinding"]["kind"], "audioCue")
                    self.assertEqual(
                        asset["sourceBinding"]["sourceRef"],
                        request["sourceCueRef"],
                    )
                    self.assertEqual(
                        asset["sourceBinding"]["sourceDigest"],
                        request["sourceCueDigest"],
                    )
                    self.assertIsNone(asset["voiceBinding"])
                    self.assertEqual(
                        asset["synthesisBinding"]["effectKind"], effect_kind
                    )
                    self.assertEqual(
                        asset["synthesisBinding"]["synthesisSpecDigest"],
                        first["synthesisSpecDigest"],
                    )
                    self.assertEqual(
                        asset["generationRequestDigest"], request["payloadDigest"]
                    )
                    self.assertEqual(
                        asset["generationParametersDigest"],
                        first["effectiveParametersDigest"],
                    )
                    self.assertFalse(asset["publicationAllowed"])

    def test_preliminary_mix_ducks_internal_tracks_and_canonicalizes_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, dialogue_asset, _ = _execute_dialogue(
                root,
                storage_key="asset-versions/audio/shot-1/dialogue-stem.wav",
            )
            _, _, ambience_asset = _execute_programmatic(
                root,
                effect_kind="rain",
                ordinal=1,
                storage_key="asset-versions/audio/shot-1/rain-stem.wav",
            )
            _, _, sfx_asset = _execute_programmatic(
                root,
                effect_kind="paper",
                ordinal=2,
                storage_key="asset-versions/audio/shot-1/paper-stem.wav",
            )
            assets = [dialogue_asset, sfx_asset, ambience_asset]
            first_request = build_preliminary_mix_request(assets)
            second_request = build_preliminary_mix_request(
                list(reversed(assets))
            )
            adapter = DeterministicPreliminaryMixAdapter(root)

            first = audio_artifact_evidence(
                first_request,
                artifact_root=root,
                storage_key="asset-versions/audio/shot-1/preliminary-mix-1.wav",
                adapter=adapter,
            )
            second = audio_artifact_evidence(
                second_request,
                artifact_root=root,
                storage_key="asset-versions/audio/shot-1/preliminary-mix-2.wav",
                adapter=adapter,
            )

            self.assertEqual(
                {
                    track["audioRole"]
                    for track in first_request["parameters"]["tracks"]
                },
                {"dialogue", "sfx", "ambience"},
            )
            self.assertEqual(first["audioRole"], "preliminary_mix")
            self.assertEqual(first["adapterIdentity"], PRELIMINARY_MIX_ADAPTER_ID)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["probe"], second["probe"])
            self.assertEqual(first["probe"]["durationSamples"], SHORT_SAMPLES)
            self.assertNotIn(
                first["sha256"], {asset["sha256"] for asset in (
                    dialogue_asset,
                    sfx_asset,
                    ambience_asset,
                )}
            )
            self.assertEqual(first["generationResult"]["state"], "SUCCEEDED")
            self.assertEqual(
                first["artifactEvidence"]["state"], "TECHNICALLY_VERIFIED"
            )
            self.assertFalse(first["publicationAllowed"])


if __name__ == "__main__":
    unittest.main()
