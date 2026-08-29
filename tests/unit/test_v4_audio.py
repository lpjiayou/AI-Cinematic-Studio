from __future__ import annotations

from array import array
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import wave

from services.v4_platform.audio import (
    PIPER_TTS_ADAPTER_ID,
    PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
    PRELIMINARY_MIX_ADAPTER_ID,
    PROGRAMMATIC_AUDIO_ADAPTER_ID,
    PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION,
    TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
    AudioArtifactVerificationError,
    AudioRequestValidationError,
    AudioRuntimeUnavailableError,
    DeterministicPreliminaryMixAdapter,
    DeterministicProgrammaticAudioAdapter,
    PiperTtsAdapter,
    audio_artifact_evidence,
    emotion_parameters,
)
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter


SAMPLE_RATE = 48_000
SHORT_SAMPLES = 4_800
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64


def _seal(value: dict) -> dict:
    result = deepcopy(value)
    payload = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    result["payloadDigest"] = sha256(payload).hexdigest()
    return result


def _reseal(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    return _seal(result)


def _common_request(
    parameters: dict,
    *,
    schema_version: str,
    adapter_identity: str,
    state: str,
) -> dict:
    return {
        "schemaVersion": schema_version,
        "workspaceRef": "workspace-test",
        "productionRunRef": "production-run-test",
        "assetRequirementRef": "asset-requirement-test",
        "assetRequirementDigest": SHA_A,
        "generationRequestRef": "generation-request-test",
        "generationRequestVersionRef": "generation-request-version-test",
        "creativeShotRef": "creative-shot-test",
        "creativeShotVersionRef": "creative-shot-version-test",
        "creativeShotDigest": SHA_B,
        "scriptRef": "script-test",
        "scriptVersionRef": "script-version-test",
        "scriptVersionDigest": SHA_C,
        "mediaKind": "audio",
        "mediaType": "audio/wav",
        "adapterCapability": adapter_identity,
        "parameters": parameters,
        "state": state,
        "requestedProvenance": "LOCAL_EVIDENCE",
        "publicationAllowed": False,
    }


def _speech_request(*, emotion_tag: str = "neutral") -> dict:
    parameters = {
            "speechSynthesis": True,
            "text": "M12 deterministic test line.",
            "voiceRef": "voice-version-test",
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "audioRole": "dialogue",
            "emotionTag": emotion_tag,
    }
    return _seal(
        {
            **_common_request(
                parameters,
                schema_version=TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
                adapter_identity=PIPER_TTS_ADAPTER_ID,
                state="LOCAL_EXECUTION_REQUEST",
            ),
            "generationRequestDigest": SHA_D,
            "scriptSceneRef": "script-scene-test",
            "sourceScriptSpan": "scene-1.dialogue-1",
            "dialogueOrdinal": 1,
            "dialogueSourceDigest": SHA_E,
            "characterRef": "character-test",
            "voiceRef": "voice-version-test",
            "voiceLockVersionRef": "voice-lock-version-test",
            "voiceLockDigest": SHA_F,
            "engine": {
                "engineFamily": "piper",
                "voiceId": "piper-voice-test",
                "languageCode": "zh-CN",
                "basePitchSemitones": 0.0,
                "baseRateScale": 1.0,
            },
        }
    )


def _effect_request(effect_kind: str, *, seed: int = 17) -> dict:
    role = "ambience" if effect_kind in {"rain", "wind"} else "sfx"
    duration_samples = 2_400 if effect_kind == "paper" else SHORT_SAMPLES
    parameters = {
            "synthesisKind": "programmatic",
            "effectKind": effect_kind,
            "audioRole": role,
            "durationSamples": duration_samples,
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "seed": seed,
    }
    return _seal(
        {
            **_common_request(
                parameters,
                schema_version=PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION,
                adapter_identity=PROGRAMMATIC_AUDIO_ADAPTER_ID,
                state="CONTRACT_ONLY_ADAPTER_REQUIRED",
            ),
            "version": 1,
            "scriptSceneRef": "script-scene-test",
            "sourceCueRef": "source-cue-test",
            "sourceCueDigest": SHA_D,
            "cueOrdinal": 1,
            "createdBy": "m12-unit-test",
            "createdAt": "2026-08-29T00:00:00Z",
        }
    )


def _write_test_stem(path: Path, *, samples: int = SHORT_SAMPLES) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = array("h", (4_000 if index % 2 == 0 else -4_000 for index in range(samples)))
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(frames.tobytes())
    return sha256(path.read_bytes()).hexdigest()


def _track(role: str, storage_key: str, artifact_sha: str, *, suffix: str) -> dict:
    return {
        "audioRole": role,
        "assetVersionRef": f"asset-version-{suffix}",
        "assetVersionDigest": sha256(f"asset-version-{suffix}".encode()).hexdigest(),
        "storageKey": storage_key,
        "sha256": artifact_sha,
        "sampleRate": SAMPLE_RATE,
        "channels": 1,
        "durationSamples": SHORT_SAMPLES,
    }


def _mix_request(tracks: list[dict]) -> dict:
    parameters = {
            "mixKind": "preliminary",
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "durationSamples": SHORT_SAMPLES,
            "tracks": tracks,
    }
    return _seal(
        {
            **_common_request(
                parameters,
                schema_version=PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
                adapter_identity=PRELIMINARY_MIX_ADAPTER_ID,
                state="LOCAL_EXECUTION_REQUEST",
            ),
            "scriptSceneRef": "script-scene-test",
        }
    )


def _peak(path: Path) -> int:
    with wave.open(str(path), "rb") as reader:
        samples = array("h")
        samples.frombytes(reader.readframes(reader.getnframes()))
    return max(abs(value) for value in samples)


class V4EmotionAndPiperTests(unittest.TestCase):
    def test_emotion_mapping_is_exact_detached_and_fail_closed(self):
        expected = {
            "neutral": {"pitch": 0.0, "rate": 1.0, "energy": 1.0},
            "tense": {"pitch": 1.5, "rate": 1.08, "energy": 1.12},
            "whisper": {"pitch": -1.0, "rate": 0.90, "energy": 0.58},
            "weary": {"pitch": -2.0, "rate": 0.86, "energy": 0.72},
        }
        for tag, parameters in expected.items():
            with self.subTest(tag=tag):
                first = emotion_parameters(tag)
                second = emotion_parameters(tag)
                self.assertEqual(first, parameters)
                self.assertEqual(second, parameters)
                self.assertIsNot(first, second)
                first["pitch"] = 999.0
                self.assertEqual(emotion_parameters(tag), parameters)

        for invalid in ("unknown", "NEUTRAL", "", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(AudioRequestValidationError):
                    emotion_parameters(invalid)  # type: ignore[arg-type]

    def test_absent_piper_runtime_is_exact_and_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "not-created" / "speech.wav"
            with self.assertRaises(NotImplementedError) as caught:
                PiperTtsAdapter().generate(_speech_request(), candidate)

            self.assertEqual(caught.exception.args, ("PIPER_RUNTIME_ABSENT",))
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_test_only_fixed_wav_adapter_satisfies_the_generation_port(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = FixedWavTtsAdapter()
            candidate = Path(directory) / "speech.wav"

            produced = adapter.generate(_speech_request(emotion_tag="whisper"), candidate)

            self.assertEqual(produced, candidate)
            self.assertEqual(candidate.read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(len(adapter.calls), 1)

    def test_test_tts_evidence_pins_piper_identity_and_emotion_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter = FixedWavTtsAdapter()
            request = _speech_request(emotion_tag="whisper")
            storage_key = "asset-versions/audio/dialogue/line-1.wav"

            result = audio_artifact_evidence(
                request,
                artifact_root=root,
                storage_key=storage_key,
                adapter=adapter,
            )

            output = root / storage_key
            requested_digest = sha256(
                json.dumps(
                    request["parameters"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            effective = {
                **request["parameters"],
                "emotionParameters": {
                    "pitch": -1.0,
                    "rate": 0.90,
                    "energy": 0.58,
                },
            }
            effective_digest = sha256(
                json.dumps(
                    effective,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(output.read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(result["adapterIdentity"], PIPER_TTS_ADAPTER_ID)
            self.assertEqual(
                result["artifactEvidence"]["adapterIdentity"],
                PIPER_TTS_ADAPTER_ID,
            )
            self.assertEqual(result["adapterIdentity"], adapter.adapter_identity)
            self.assertEqual(result["parametersDigest"], requested_digest)
            self.assertEqual(
                result["effectiveParametersDigest"], effective_digest
            )
            self.assertNotEqual(
                result["parametersDigest"], result["effectiveParametersDigest"]
            )

    def test_existing_wav_cannot_be_retroactively_signed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = "asset-versions/audio/dialogue/existing.wav"
            existing = root / storage_key
            existing.parent.mkdir(parents=True)
            existing.write_bytes(FIXED_WAV_BYTES)
            adapter = FixedWavTtsAdapter()

            with self.assertRaises(AudioRequestValidationError):
                audio_artifact_evidence(
                    _speech_request(),
                    artifact_root=root,
                    storage_key=storage_key,
                    adapter=adapter,
                )

            self.assertEqual(existing.read_bytes(), FIXED_WAV_BYTES)
            self.assertEqual(adapter.calls, [])


class V4ProgrammaticAudioTests(unittest.TestCase):
    def test_probe_runtime_failure_removes_unverified_candidate(self):
        adapter = DeterministicProgrammaticAudioAdapter()
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "rain.wav"
            with mock.patch(
                "services.v4_platform.audio._probe_wav",
                side_effect=AudioRuntimeUnavailableError("ffprobe unavailable"),
            ):
                with self.assertRaises(AudioRuntimeUnavailableError):
                    adapter.generate(_effect_request("rain"), candidate)
            self.assertFalse(candidate.exists())

    def test_each_effect_is_deterministic_and_has_exact_probe_contract(self):
        adapter = DeterministicProgrammaticAudioAdapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for effect in ("rain", "wind", "fire_crackle", "paper"):
                with self.subTest(effect=effect):
                    request = _effect_request(effect)
                    first_key = f"asset-versions/audio/{effect}-first.wav"
                    second_key = f"asset-versions/audio/{effect}-second.wav"
                    first_evidence = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=first_key,
                        adapter=adapter,
                    )
                    second_evidence = audio_artifact_evidence(
                        request,
                        artifact_root=root,
                        storage_key=second_key,
                        adapter=adapter,
                    )
                    first = root / first_key
                    second = root / second_key
                    first_sha = sha256(first.read_bytes()).hexdigest()
                    self.assertEqual(first_sha, sha256(second.read_bytes()).hexdigest())
                    self.assertEqual(first_evidence["sha256"], second_evidence["sha256"])
                    expected_samples = 2_400 if effect == "paper" else SHORT_SAMPLES
                    self.assertEqual(first_evidence["sha256"], first_sha)
                    self.assertEqual(first_evidence["sampleRate"], SAMPLE_RATE)
                    self.assertEqual(first_evidence["channels"], 1)
                    self.assertEqual(
                        first_evidence["probe"]["durationSamples"], expected_samples
                    )
                    self.assertAlmostEqual(
                        first_evidence["probe"]["durationSeconds"],
                        expected_samples / SAMPLE_RATE,
                        places=6,
                    )
                    self.assertEqual(
                        first_evidence["probe"]["codec"], "pcm_s16le"
                    )
                    self.assertEqual(first_evidence["probe"]["container"], "wav")
                    self.assertEqual(
                        first_evidence["parametersDigest"],
                        first_evidence["effectiveParametersDigest"],
                    )

    def test_external_audio_input_is_rejected_before_subprocess_or_write(self):
        adapter = DeterministicProgrammaticAudioAdapter()
        request = _effect_request("rain")
        request["parameters"] = {
            **request["parameters"],
            "sourcePath": "/tmp/caller-selected.wav",
        }
        request = _reseal(request)
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "not-created" / "rain.wav"
            with mock.patch("services.v4_platform.audio.subprocess.run") as run:
                with self.assertRaisesRegex(
                    AudioRequestValidationError,
                    "^external audio input is forbidden$",
                ):
                    adapter.generate(request, candidate)
            run.assert_not_called()
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_evidence_rejects_legacy_and_noncanonical_storage_before_write(self):
        adapter = DeterministicProgrammaticAudioAdapter()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for storage_key in (
                "jobs/generation-request/audio.wav",
                "asset-versions/audio//rain.wav",
            ):
                with self.subTest(storage_key=storage_key):
                    with mock.patch(
                        "services.v4_platform.audio.subprocess.run"
                    ) as run:
                        with self.assertRaises(AudioRequestValidationError):
                            audio_artifact_evidence(
                                _effect_request("rain"),
                                artifact_root=root,
                                storage_key=storage_key,
                                adapter=adapter,
                            )
                    run.assert_not_called()
            self.assertEqual(list(root.rglob("*.wav")), [])


class V4PreliminaryMixTests(unittest.TestCase):
    def _one_internal_stem(self, root: Path) -> tuple[str, str]:
        storage_key = "asset-versions/audio/stem.wav"
        artifact_sha = _write_test_stem(root / storage_key)
        return storage_key, artifact_sha

    def test_bgm_is_not_implemented_and_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key, artifact_sha = self._one_internal_stem(root)
            adapter = DeterministicPreliminaryMixAdapter(root)
            request = _mix_request(
                [_track("bgm", storage_key, artifact_sha, suffix="bgm")]
            )
            candidate = root / "not-created" / "mix.wav"

            with self.assertRaises(NotImplementedError) as caught:
                adapter.generate(request, candidate)

            self.assertEqual(caught.exception.args, ("BGM_NOT_IMPLEMENTED",))
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_internal_digest_pinned_mix_is_role_ordered_and_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key, artifact_sha = self._one_internal_stem(root)
            adapter = DeterministicPreliminaryMixAdapter(root)
            tracks = [
                _track("ambience", storage_key, artifact_sha, suffix="ambience"),
                _track("dialogue", storage_key, artifact_sha, suffix="dialogue"),
                _track("sfx", storage_key, artifact_sha, suffix="sfx"),
            ]
            first = root / "mix-first.wav"
            second = root / "mix-second.wav"
            adapter.generate(_mix_request(tracks), first)
            adapter.generate(_mix_request(list(reversed(tracks))), second)

            self.assertEqual(
                sha256(first.read_bytes()).hexdigest(),
                sha256(second.read_bytes()).hexdigest(),
            )

            role_peaks = {}
            for role in ("dialogue", "sfx", "ambience"):
                candidate = root / f"mix-{role}.wav"
                adapter.generate(
                    _mix_request(
                        [_track(role, storage_key, artifact_sha, suffix=f"only-{role}")]
                    ),
                    candidate,
                )
                role_peaks[role] = _peak(candidate)
            self.assertGreater(role_peaks["dialogue"], role_peaks["sfx"])
            self.assertGreater(role_peaks["sfx"], role_peaks["ambience"])

    def test_mix_filtergraph_freezes_levels_and_dialogue_ducking(self):
        from services.v4_platform.audio import _mix_filtergraph, _mix_parameters

        request = _mix_request(
            [
                _track(
                    "ambience",
                    "asset-versions/audio/ambience.wav",
                    "1" * 64,
                    suffix="ambience",
                ),
                _track(
                    "dialogue",
                    "asset-versions/audio/dialogue.wav",
                    "2" * 64,
                    suffix="dialogue",
                ),
                _track(
                    "sfx",
                    "asset-versions/audio/sfx.wav",
                    "3" * 64,
                    suffix="sfx",
                ),
            ]
        )
        _, parameters = _mix_parameters(request)
        graph = _mix_filtergraph(parameters)
        self.assertIn("volume=0dB", graph)
        self.assertIn("volume=-6dB", graph)
        self.assertIn("volume=-12dB", graph)
        self.assertIn(
            "sidechaincompress=threshold=0.125:ratio=8:attack=5:release=180:"
            "makeup=1:knee=2:link=maximum:detection=rms:level_sc=1:mix=1",
            graph,
        )

    def test_raw_external_path_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key, artifact_sha = self._one_internal_stem(root)
            adapter = DeterministicPreliminaryMixAdapter(root)
            raw_track = _track("dialogue", storage_key, artifact_sha, suffix="raw")
            raw_track["path"] = "/tmp/external.wav"
            candidate = root / "not-created" / "mix.wav"
            with mock.patch("services.v4_platform.audio.subprocess.run") as run:
                with self.assertRaises(AudioRequestValidationError):
                    adapter.generate(_mix_request([raw_track]), candidate)
            run.assert_not_called()
            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

    def test_storage_escape_and_digest_mismatch_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key, artifact_sha = self._one_internal_stem(root)
            adapter = DeterministicPreliminaryMixAdapter(root)

            escaped = _track("dialogue", storage_key, artifact_sha, suffix="escaped")
            escaped["storageKey"] = "/tmp/external.wav"
            escaped_candidate = root / "escaped-mix.wav"
            with self.assertRaises(AudioRequestValidationError):
                adapter.generate(_mix_request([escaped]), escaped_candidate)
            self.assertFalse(escaped_candidate.exists())

            mismatched = _track("dialogue", storage_key, "0" * 64, suffix="mismatch")
            mismatch_candidate = root / "mismatch-mix.wav"
            with self.assertRaises(AudioArtifactVerificationError):
                adapter.generate(_mix_request([mismatched]), mismatch_candidate)
            self.assertFalse(mismatch_candidate.exists())


if __name__ == "__main__":
    unittest.main()
