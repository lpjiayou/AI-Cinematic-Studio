from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.v4_platform.audio import (
    AudioRequestValidationError,
    DeterministicPreliminaryMixAdapter,
    PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
    PRELIMINARY_MIX_ADAPTER_ID,
    PiperTtsAdapter,
    emotion_parameters,
)
from services.v5_core_os.episode_production.audio import (
    AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION,
    AUDIO_ROLES,
    K2AudioProductionService,
    LOCAL_PIPER_TTS_ADAPTER_ID,
    PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID,
    build_programmatic_audio_request,
    build_proposed_audio_asset_version,
    build_tts_execution_request,
    normalize_programmatic_audio_parameters,
    normalize_speech_parameters,
    validate_audio_asset_version_v2_contract,
)
from services.v5_core_os.episode_production.foundation import (
    EpisodeProductionError,
    StaleInputError,
    _digest,
)
from tests.contract.test_m12_audio_contract import (
    PROJECT,
    RUN,
    SERIES,
    WORKSPACE,
    ShotGraph,
    VoiceReader,
    fixture,
    sealed,
    voice_bundle,
)
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter


def dialogue_context(emotion_tag: str | None = None):
    voices = VoiceReader(
        {"character-lin": voice_bundle("character-lin", "voice-lin")}
    )
    service = K2AudioProductionService(
        ShotGraph(
            fixture(
                [{"speaker": "林澈", "text": "不要动。", "emotion": "克制"}]
            )
        ),
        voices,
    )
    with patch(
        "services.v5_core_os.episode_production.audio.require_legacy_executable_graph"
    ):
        request = service.plan_dialogue_requests(WORKSPACE, RUN)[
            "generationRequests"
        ][0]
    if emotion_tag is not None:
        unsigned = deepcopy(request)
        unsigned.pop("payloadDigest")
        unsigned["parameters"]["emotionTag"] = emotion_tag
        request = sealed(unsigned)
    bundle = voices.get_confirmed_voice_lock(
        WORKSPACE, PROJECT, SERIES, "character-lin"
    )
    return request, bundle


def programmatic_request(
    *, role="ambience", kind="rain", created_at="2026-08-29T00:00:00Z"
):
    return build_programmatic_audio_request(
        {
            "workspaceRef": WORKSPACE,
            "productionRunRef": RUN,
            "assetRequirementRef": "requirement-audio-cue-1",
            "assetRequirementDigest": "1" * 64,
            "creativeShotRef": "shot-1",
            "creativeShotVersionRef": "shot-version-1",
            "creativeShotDigest": "2" * 64,
            "scriptRef": "script-m12",
            "scriptVersionRef": "script-version-m12",
            "scriptVersionDigest": "3" * 64,
            "scriptSceneRef": "scene-1",
            "sourceCueRef": "scene-1-audio-cue-1",
            "sourceCueDigest": "4" * 64,
            "cueOrdinal": 1,
            "parameters": {
                "audioRole": role,
                "synthesisKind": "programmatic",
                "effectKind": kind,
                "durationSamples": 48_000,
                "sampleRate": 48_000,
                "channels": 1,
                "seed": 17,
            },
            "createdAt": created_at,
        }
    )


def artifact_bundle(request, *, storage_key, adapter_identity):
    lineage = {
        field: request[field]
        for field in (
            "workspaceRef",
            "productionRunRef",
            "assetRequirementRef",
            "assetRequirementDigest",
            "generationRequestRef",
            "generationRequestVersionRef",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "scriptRef",
            "scriptVersionRef",
            "scriptVersionDigest",
        )
    }
    generation_request_digest = request.get(
        "generationRequestDigest", request["payloadDigest"]
    )
    parameters = deepcopy(request["parameters"])
    effective_parameters = deepcopy(parameters)
    if parameters.get("speechSynthesis") is True:
        emotion_tag = parameters.get("emotionTag", "neutral")
        effective_parameters.setdefault("emotionTag", emotion_tag)
        effective_parameters["emotionParameters"] = emotion_parameters(emotion_tag)
    parameters_digest = _digest(parameters)
    effective_parameters_digest = _digest(effective_parameters)
    spec_digest = _digest(
        {
            "adapterIdentity": adapter_identity,
            "parameters": effective_parameters,
        }
    )
    artifact_sha = sha256(FIXED_WAV_BYTES).hexdigest()
    probe = {
        "sampleRate": 48_000,
        "channels": 1,
        "durationSeconds": 0.1,
        "durationSamples": 4_800,
        "codec": "pcm_s16le",
        "container": "wav",
    }
    evidence = sealed(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            **lineage,
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": request["payloadDigest"],
            "artifactEvidenceRef": "audio-evidence-1",
            "artifactRef": "audio-artifact-1",
            "storageKey": storage_key,
            "byteSize": len(FIXED_WAV_BYTES),
            "sha256": artifact_sha,
            "sampleRate": 48_000,
            "channels": 1,
            "probe": probe,
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": spec_digest,
            "adapterIdentity": adapter_identity,
            "audioRole": parameters["audioRole"],
            "provenance": "LOCAL_EVIDENCE",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )
    result = sealed(
        {
            "schemaVersion": "v4.audio-generation-result.v1",
            **lineage,
            "generationResultRef": "audio-generation-result-1",
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": request["payloadDigest"],
            "adapterIdentity": adapter_identity,
            "provenance": "LOCAL_EVIDENCE",
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": storage_key,
            "byteSize": len(FIXED_WAV_BYTES),
            "sha256": artifact_sha,
            "sampleRate": 48_000,
            "channels": 1,
            "probe": probe,
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": spec_digest,
            "audioRole": parameters["audioRole"],
            "state": "SUCCEEDED",
            "publicationAllowed": False,
        }
    )
    return sealed(
        {
            "schemaVersion": "v4.audio-artifact-result.v1",
            **lineage,
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": request["payloadDigest"],
            "generationResultRef": result["generationResultRef"],
            "generationResultDigest": result["payloadDigest"],
            "adapterIdentity": adapter_identity,
            "provenance": "LOCAL_EVIDENCE",
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": storage_key,
            "byteSize": len(FIXED_WAV_BYTES),
            "sha256": artifact_sha,
            "sampleRate": 48_000,
            "channels": 1,
            "probe": probe,
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": spec_digest,
            "audioRole": parameters["audioRole"],
            "generationResult": result,
            "artifactEvidence": evidence,
            "publicationAllowed": False,
        }
    )


class M12AudioExecutionContractTests(unittest.TestCase):
    def test_audio_roles_extend_without_enabling_bgm_for_speech(self):
        self.assertEqual(
            AUDIO_ROLES,
            {"dialogue", "narration", "ambience", "sfx", "music"},
        )
        request, voice = dialogue_context()
        parameters = deepcopy(request["parameters"])
        for role in ("ambience", "sfx", "bgm"):
            parameters["audioRole"] = role
            with self.subTest(role=role), self.assertRaises(EpisodeProductionError):
                normalize_speech_parameters(
                    parameters, confirmed_voice_lock=voice
                )

    def test_tts_bridge_consumes_normalized_parameters_and_voice_lineage(self):
        request, voice = dialogue_context("tense")
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        self.assertEqual(execution["parameters"], request["parameters"])
        self.assertEqual(
            execution["voiceLockDigest"],
            voice["voiceLockVersion"]["payloadDigest"],
        )
        self.assertEqual(
            execution["engine"]["voiceId"],
            voice["voiceLockVersion"]["voiceId"],
        )

    def test_tts_bridge_rejects_external_input_field_before_execution(self):
        request, voice = dialogue_context()
        unsigned = deepcopy(request)
        unsigned.pop("payloadDigest")
        unsigned["inputPath"] = "/tmp/external.wav"
        with self.assertRaises(EpisodeProductionError):
            build_tts_execution_request(
                sealed(unsigned), confirmed_voice_lock=voice
            )

    def test_unknown_emotion_is_rejected_before_any_adapter_call(self):
        request, voice = dialogue_context("unknown")
        adapter = FixedWavTtsAdapter()
        with self.assertRaises(EpisodeProductionError):
            build_tts_execution_request(request, confirmed_voice_lock=voice)
        self.assertEqual(adapter.calls, [])

    def test_piper_a_tier_is_exact_and_has_no_write_side_effect(self):
        request, voice = dialogue_context("neutral")
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        adapter = PiperTtsAdapter()
        self.assertEqual(adapter.adapter_identity, LOCAL_PIPER_TTS_ADAPTER_ID)
        self.assertEqual(adapter.provenance, "LOCAL_EVIDENCE")
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "not-created" / "speech.wav"
            with self.assertRaisesRegex(
                NotImplementedError, "^PIPER_RUNTIME_ABSENT$"
            ):
                adapter.generate(execution, candidate)
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_emotion_parameters_are_repeatable_and_caller_drift_is_rejected(self):
        for tag in ("neutral", "tense", "whisper", "weary"):
            with self.subTest(tag=tag):
                self.assertEqual(emotion_parameters(tag), emotion_parameters(tag))

        request, voice = dialogue_context("tense")
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        unsigned = deepcopy(execution)
        unsigned.pop("payloadDigest")
        unsigned["parameters"]["emotionParameters"] = {
            "pitch": 999.0,
            "rate": 0.1,
            "energy": 0.1,
        }
        drifted = sealed(unsigned)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "speech.wav"
            with self.assertRaises(AudioRequestValidationError):
                PiperTtsAdapter().generate(drifted, candidate)
            self.assertFalse(candidate.exists())

    def test_fixed_fake_engine_writes_only_deterministic_test_wav(self):
        request, voice = dialogue_context()
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        adapter = FixedWavTtsAdapter()
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "candidate.wav"
            self.assertEqual(adapter.generate(execution, candidate), candidate)
            self.assertEqual(candidate.read_bytes(), FIXED_WAV_BYTES)
            second = Path(directory) / "candidate-2.wav"
            adapter.generate(execution, second)
            self.assertEqual(candidate.read_bytes(), second.read_bytes())

    def test_legacy_programmatic_parameters_reject_external_audio_and_bgm(self):
        base = programmatic_request()["parameters"]
        for field, value in (
            ("inputPath", "/tmp/external.wav"),
            ("sourceUrl", "https://example.invalid/audio.wav"),
            ("audioBytes", b"external"),
        ):
            invalid = {**base, field: value}
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionError
            ):
                normalize_programmatic_audio_parameters(invalid)
        with self.assertRaises(EpisodeProductionError):
            normalize_programmatic_audio_parameters(
                {
                    **base,
                    "audioRole": "bgm",
                    "synthesisKind": "bgm",
                    "effectKind": "bgm",
                }
            )

    def test_legacy_bgm_mix_role_is_rejected_before_any_write(self):
        request = sealed(
            {
                "schemaVersion": PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
                "workspaceRef": WORKSPACE,
                "productionRunRef": RUN,
                "generationRequestRef": "mix-request-1",
                "generationRequestVersionRef": "mix-request-version-1",
                "assetRequirementRef": "mix-requirement-1",
                "assetRequirementDigest": "1" * 64,
                "creativeShotRef": "shot-1",
                "creativeShotVersionRef": "shot-version-1",
                "creativeShotDigest": "2" * 64,
                "scriptRef": "script-1",
                "scriptVersionRef": "script-version-1",
                "scriptVersionDigest": "3" * 64,
                "scriptSceneRef": "scene-1",
                "mediaKind": "audio",
                "mediaType": "audio/wav",
                "adapterCapability": PRELIMINARY_MIX_ADAPTER_ID,
                "parameters": {
                    "mixKind": "preliminary",
                    "sampleRate": 48_000,
                    "channels": 1,
                    "durationSamples": 4_800,
                    "tracks": [
                        {
                            "audioRole": "bgm",
                            "assetVersionRef": "bgm-version-1",
                            "assetVersionDigest": "4" * 64,
                            "storageKey": "asset-versions/audio/bgm.wav",
                            "sha256": "5" * 64,
                            "sampleRate": 48_000,
                            "channels": 1,
                            "durationSamples": 4_800,
                        }
                    ],
                },
                "state": "LOCAL_EXECUTION_REQUEST",
                "requestedProvenance": "LOCAL_EVIDENCE",
                "publicationAllowed": False,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "not-created" / "mix.wav"
            adapter = DeterministicPreliminaryMixAdapter(root)
            with self.assertRaises(AudioRequestValidationError):
                adapter.generate(request, candidate)
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_programmatic_request_is_deterministic_and_role_bound(self):
        first = programmatic_request()
        second = programmatic_request()
        self.assertEqual(first, second)
        later = programmatic_request(created_at="2026-08-29T00:00:01Z")
        self.assertNotEqual(
            first["generationRequestVersionRef"],
            later["generationRequestVersionRef"],
        )
        invalid = deepcopy(first["parameters"])
        invalid["audioRole"] = "sfx"
        with self.assertRaises(EpisodeProductionError):
            normalize_programmatic_audio_parameters(invalid)

    def test_dialogue_fake_artifact_builds_proposed_asset_version_only(self):
        request, voice = dialogue_context()
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        artifact = artifact_bundle(
            execution,
            storage_key="asset-versions/audio/shot-1/dialogue-1.wav",
            adapter_identity=LOCAL_PIPER_TTS_ADAPTER_ID,
        )
        asset = build_proposed_audio_asset_version(
            request,
            artifact,
            confirmed_voice_lock=voice,
            created_at="2026-08-29T00:00:01Z",
        )
        self.assertEqual(
            asset["schemaVersion"], AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION
        )
        self.assertEqual(asset["audioRole"], "dialogue")
        self.assertEqual(asset["voiceBinding"]["voiceLockDigest"], request["voiceLockDigest"])
        self.assertIsNone(asset["synthesisBinding"])
        self.assertEqual(asset["state"], "PROPOSED")
        self.assertNotIn("assetAdmissionRef", asset)
        self.assertFalse(asset["publicationAllowed"])

    def test_speech_effective_parameter_drift_is_rejected(self):
        request, voice = dialogue_context("tense")
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=voice
        )
        artifact = artifact_bundle(
            execution,
            storage_key="asset-versions/audio/shot-1/dialogue-drift.wav",
            adapter_identity=LOCAL_PIPER_TTS_ADAPTER_ID,
        )
        bad_effective_digest = "f" * 64
        bad_spec_digest = "e" * 64

        evidence_unsigned = deepcopy(artifact["artifactEvidence"])
        evidence_unsigned.pop("payloadDigest")
        evidence_unsigned["effectiveParametersDigest"] = bad_effective_digest
        evidence_unsigned["synthesisSpecDigest"] = bad_spec_digest
        evidence = sealed(evidence_unsigned)

        result_unsigned = deepcopy(artifact["generationResult"])
        result_unsigned.pop("payloadDigest")
        result_unsigned["effectiveParametersDigest"] = bad_effective_digest
        result_unsigned["synthesisSpecDigest"] = bad_spec_digest
        result_unsigned["artifactEvidenceDigest"] = evidence["payloadDigest"]
        result = sealed(result_unsigned)

        outer_unsigned = deepcopy(artifact)
        outer_unsigned.pop("payloadDigest")
        outer_unsigned["effectiveParametersDigest"] = bad_effective_digest
        outer_unsigned["synthesisSpecDigest"] = bad_spec_digest
        outer_unsigned["artifactEvidenceDigest"] = evidence["payloadDigest"]
        outer_unsigned["generationResultDigest"] = result["payloadDigest"]
        outer_unsigned["generationResult"] = result
        outer_unsigned["artifactEvidence"] = evidence
        tampered = sealed(outer_unsigned)

        with self.assertRaises(StaleInputError):
            build_proposed_audio_asset_version(
                request,
                tampered,
                confirmed_voice_lock=voice,
                created_at="2026-08-29T00:00:01Z",
            )

    def test_programmatic_artifact_builds_role_specific_asset_without_voice(self):
        request = programmatic_request()
        artifact = artifact_bundle(
            request,
            storage_key="asset-versions/audio/shot-1/rain-1.wav",
            adapter_identity=PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID,
        )
        asset = build_proposed_audio_asset_version(
            request,
            artifact,
            created_at="2026-08-29T00:00:01Z",
        )
        self.assertEqual(asset["audioRole"], "ambience")
        self.assertIsNone(asset["voiceBinding"])
        self.assertEqual(asset["sourceBinding"]["kind"], "audioCue")
        self.assertEqual(asset["synthesisBinding"]["synthesisKind"], "programmatic")
        self.assertEqual(asset["synthesisBinding"]["effectKind"], "rain")

    def test_programmatic_asset_rejects_adapter_or_sample_rate_drift(self):
        request = programmatic_request()
        artifact = artifact_bundle(
            request,
            storage_key="asset-versions/audio/shot-1/rain-drift.wav",
            adapter_identity=PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID,
        )
        asset = build_proposed_audio_asset_version(
            request,
            artifact,
            created_at="2026-08-29T00:00:01Z",
        )
        for field, value in (
            ("adapterIdentity", "v4.commercial-audio-provider.v1"),
            ("sampleRate", 44_100),
        ):
            unsigned = deepcopy(asset)
            unsigned.pop("payloadDigest")
            if field == "adapterIdentity":
                unsigned["synthesisBinding"][field] = value
            else:
                unsigned[field] = value
                unsigned["probe"][field] = value
                unsigned["probe"]["durationSamples"] = 4_410
            with self.subTest(field=field), self.assertRaises(
                EpisodeProductionError
            ):
                validate_audio_asset_version_v2_contract(sealed(unsigned))

    def test_legacy_asset_storage_path_is_rejected_by_proposed_output(self):
        request = programmatic_request()
        artifact = artifact_bundle(
            request,
            storage_key="jobs/request/audio.wav",
            adapter_identity=PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID,
        )
        with self.assertRaises(EpisodeProductionError):
            build_proposed_audio_asset_version(
                request,
                artifact,
                created_at="2026-08-29T00:00:01Z",
            )


if __name__ == "__main__":
    unittest.main()
