from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.v4_platform.audio import (
    AudioArtifactVerificationError,
    DeterministicPreliminaryMixAdapter,
    execute_piper_tts_evidence,
)
from services.v4_platform.audio_validation import (
    AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION,
)
from services.v5_core_os.episode_production.audio_authority import (
    AmbienceAssetVersion,
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
)
from services.v5_core_os.episode_production.narration_synthesis import (
    NARRATION_REQUIRED_RUNTIME_STATE,
    NARRATION_TEST_AUTHORITY_STATE,
    NARRATION_TEST_FIXTURE_MARKER,
    NARRATION_TEST_RUNTIME_IDENTITY,
    NarrationTestDialogueProjection,
    NarrationTestEvidenceProjection,
)
from tests.contract.test_m12_programmatic_audio_contract import (
    EXPECTED_EFFECT_ROLE,
    execute_programmatic_chain,
    execute_typed_narration_test_chain,
)
from tests.stub_tts_adapter import FIXED_WAV_BYTES, FixedWavTtsAdapter
from tests.unit.test_v4_audio import _mix_request, _track


REAL_SUBPROCESS_RUN = subprocess.run
ALL_EXECUTION_KINDS = (*EXPECTED_EFFECT_ROLE, "music")


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "pinned local FFmpeg/FFprobe runtimes are required",
)
class M12ProgrammaticAudioExecutionIntegrationTests(unittest.TestCase):
    def test_all_closed_recipes_are_seed_stable_within_one_runtime_and_typed(self):
        render_calls: list[tuple[list[str], dict[str, str]]] = []

        def observed_subprocess_run(command, *args, **kwargs):
            normalized = [str(item) for item in command]
            if "-protocol_whitelist" in normalized:
                render_calls.append(
                    (normalized, deepcopy(kwargs.get("env", {})))
                )
            return REAL_SUBPROCESS_RUN(command, *args, **kwargs)

        blocked_socket = unittest.mock.Mock(
            side_effect=AssertionError(
                "programmatic audio attempted a Python socket operation"
            )
        )
        blocked_connection = unittest.mock.Mock(
            side_effect=AssertionError(
                "programmatic audio attempted a Python network connection"
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("socket.socket", blocked_socket),
                patch("socket.create_connection", blocked_connection),
                patch(
                    "services.v4_platform.local_audio_runtime.subprocess.run",
                    side_effect=observed_subprocess_run,
                ),
            ):
                for ordinal, kind in enumerate(ALL_EXECUTION_KINDS, start=1):
                    seed = 1_000 + ordinal
                    executions = []
                    for label, selected_seed in (
                        ("same-a", seed),
                        ("same-b", seed),
                        ("different", seed + 10_000),
                    ):
                        storage_kind = kind.replace("_", "-")
                        storage_key = (
                            "asset-versions/audio/pr6/"
                            f"{storage_kind}-{label}.wav"
                        )
                        with self.subTest(
                            kind=kind, label=label, seed=selected_seed
                        ):
                            chain = execute_programmatic_chain(
                                kind,
                                seed=selected_seed,
                                storage_key=storage_key,
                                artifact_root=root,
                            )
                            executions.append(chain)
                            request = chain["generationRequest"].as_dict()
                            execution = chain["executionRequest"].as_dict()
                            evidence_wrapper = chain["executionEvidence"]
                            evidence = evidence_wrapper.as_dict()
                            analysis = (
                                evidence_wrapper.technical_analysis_evidence().as_dict()
                            )
                            record = chain["generationRecord"].as_dict()
                            asset_wrapper = chain["assetVersion"]
                            asset = asset_wrapper.as_dict()
                            output = root / storage_key

                            expected_type = (
                                MusicAssetVersion
                                if kind == "music"
                                else (
                                    AmbienceAssetVersion
                                    if EXPECTED_EFFECT_ROLE[kind] == "ambience"
                                    else SfxAssetVersion
                                )
                            )
                            self.assertIs(type(asset_wrapper), expected_type)
                            self.assertTrue(output.is_file())
                            self.assertEqual(
                                output.resolve().parent.parent.parent,
                                (root / "asset-versions").resolve(),
                            )
                            self.assertTrue(
                                asset["artifact"]["storageKey"].startswith(
                                    "asset-versions/audio/"
                                )
                            )
                            self.assertNotIn(
                                "legacy", asset["artifact"]["storageKey"].lower()
                            )
                            self.assertNotIn(
                                "/media/", asset["artifact"]["storageKey"].lower()
                            )
                            self.assertEqual(
                                analysis["schemaVersion"],
                                AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION,
                            )
                            self.assertEqual(analysis["validationState"], "PASSED")
                            self.assertEqual(analysis["failureReasons"], [])
                            self.assertFalse(analysis["clippingDetected"])
                            self.assertEqual(
                                analysis["sourceArtifactEvidenceDigest"],
                                evidence["artifactEvidence"]["payloadDigest"],
                            )
                            self.assertEqual(
                                record["pcmContentDigest"],
                                analysis["pcmContentDigest"],
                            )
                            self.assertEqual(
                                record["fileDigest"], analysis["fileDigest"]
                            )
                            self.assertEqual(
                                asset["artifact"]["fileDigest"],
                                analysis["fileDigest"],
                            )
                            self.assertEqual(
                                asset["generationResultRef"],
                                record["generationRecordRef"],
                            )
                            self.assertEqual(
                                asset["generationResultDigest"],
                                record["payloadDigest"],
                            )
                            self.assertEqual(
                                asset["rightsBinding"], request["rightsBinding"]
                            )
                            provenance_sources = {
                                (source["sourceRef"], source["sourceDigest"])
                                for source in asset["provenance"]["sourceRefs"]
                            }
                            self.assertIn(
                                (
                                    execution["executionRequestRef"],
                                    execution["payloadDigest"],
                                ),
                                provenance_sources,
                            )
                            self.assertIn(
                                (
                                    evidence["executionEvidenceRef"],
                                    evidence["payloadDigest"],
                                ),
                                provenance_sources,
                            )
                            runtime = evidence["runtime"]
                            self.assertEqual(
                                runtime["protocolWhitelist"], ["file", "pipe"]
                            )
                            self.assertEqual(
                                runtime["environment"],
                                {"LC_ALL": "C", "LANG": "C", "TZ": "UTC"},
                            )
                            self.assertEqual(
                                runtime["networkAccess"],
                                "DENIED_BY_CLOSED_RECIPE_AND_PROTOCOL_WHITELIST",
                            )
                            self.assertEqual(
                                record["seedProfile"]["rootSeed"], selected_seed
                            )
                            if kind == "music":
                                self.assertEqual(
                                    record["musicQualityApproval"],
                                    "HUMAN_REQUIRED",
                                )
                                self.assertEqual(
                                    record["stemRecipe"],
                                    chain["synthesisSpec"].as_dict()[
                                        "executionSpec"
                                    ]["stemRecipe"],
                                )
                                self.assertEqual(
                                    record["deterministicNoteSequence"],
                                    evidence["recipe"]["derivedNoteSequence"],
                                )
                                self.assertEqual(
                                    len(record["deterministicNoteSequence"]),
                                    16,
                                )
                            else:
                                self.assertIsNone(
                                    record["deterministicNoteSequence"]
                                )
                                self.assertIsNone(
                                    evidence["recipe"].get(
                                        "derivedNoteSequence"
                                    )
                                )

                    pcm_digests = [
                        chain["generationRecord"].as_dict()[
                            "pcmContentDigest"
                        ]
                        for chain in executions
                    ]
                    self.assertEqual(
                        pcm_digests[0],
                        pcm_digests[1],
                        f"same seed changed canonical PCM for {kind}",
                    )
                    self.assertNotEqual(
                        pcm_digests[0],
                        pcm_digests[2],
                        f"different seed did not change canonical PCM for {kind}",
                    )
                    note_sequences = [
                        chain["generationRecord"].as_dict()[
                            "deterministicNoteSequence"
                        ]
                        for chain in executions
                    ]
                    if kind == "music":
                        self.assertEqual(note_sequences[0], note_sequences[1])
                        self.assertNotEqual(
                            note_sequences[0], note_sequences[2]
                        )
                    else:
                        self.assertEqual(note_sequences, [None, None, None])

        blocked_socket.assert_not_called()
        blocked_connection.assert_not_called()
        self.assertEqual(len(render_calls), len(ALL_EXECUTION_KINDS) * 3)
        for command, environment in render_calls:
            whitelist_index = command.index("-protocol_whitelist")
            self.assertEqual(command[whitelist_index + 1], "file,pipe")
            self.assertEqual(
                environment,
                {"LC_ALL": "C", "LANG": "C", "TZ": "UTC"},
            )
            input_values = [
                command[index + 1]
                for index, token in enumerate(command[:-1])
                if token == "-i"
            ]
            self.assertTrue(input_values)
            self.assertTrue(
                all(
                    not value.lower().startswith(
                        ("http:", "https:", "tcp:", "udp:", "rtmp:")
                    )
                    for value in input_values
                )
            )


class M12TypedNarrationFixedWavIntegrationTests(unittest.TestCase):
    def test_fixed_wav_is_one_test_only_typed_narration_chain_not_real_tts(self):
        self.assertEqual(FixedWavTtsAdapter.__module__, "tests.stub_tts_adapter")
        self.assertIn("test-only", (FixedWavTtsAdapter.__doc__ or "").lower())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = (
                "asset-versions/audio/pr6/narration-integration-test.wav"
            )
            chain = execute_typed_narration_test_chain(
                artifact_root=root, storage_key=storage_key
            )
            execution = chain["executionRequest"]
            evidence_wrapper = chain["testEvidenceProjection"]
            dialogue_wrapper = chain["dialogueProjection"]
            evidence = evidence_wrapper.as_dict()
            dialogue = dialogue_wrapper.as_dict()

            self.assertIs(type(chain["adapter"]), FixedWavTtsAdapter)
            self.assertEqual(chain["adapter"].calls, [execution])
            self.assertEqual((root / storage_key).read_bytes(), FIXED_WAV_BYTES)
            self.assertIs(type(evidence_wrapper), NarrationTestEvidenceProjection)
            self.assertIs(type(dialogue_wrapper), NarrationTestDialogueProjection)
            self.assertNotIsInstance(dialogue_wrapper, DialogueAssetVersion)
            self.assertEqual(
                evidence["testFixtureOnly"], NARRATION_TEST_FIXTURE_MARKER
            )
            self.assertEqual(
                evidence["actualRuntimeIdentity"],
                NARRATION_TEST_RUNTIME_IDENTITY,
            )
            self.assertEqual(
                evidence["requiredRuntimeState"],
                NARRATION_REQUIRED_RUNTIME_STATE,
            )
            self.assertEqual(
                evidence["authorityState"], NARRATION_TEST_AUTHORITY_STATE
            )
            self.assertFalse(evidence["assetVersionAllowed"])
            self.assertFalse(evidence["publicationAllowed"])
            self.assertEqual(
                evidence["provenance"]["parametersDigest"],
                evidence["effectiveParametersDigest"],
            )
            self.assertEqual(
                dialogue["testFixtureOnly"], NARRATION_TEST_FIXTURE_MARKER
            )
            self.assertEqual(
                dialogue["authorityState"], NARRATION_TEST_AUTHORITY_STATE
            )
            self.assertFalse(dialogue["assetVersionAllowed"])
            self.assertFalse(dialogue["publicationAllowed"])
            self.assertEqual(dialogue["speechRole"], "narration")
            self.assertIsNone(dialogue["dialogueRef"])
            self.assertEqual(
                dialogue["narrationRef"],
                chain["generationRequest"].as_dict()["requestSpec"][
                    "narrationRef"
                ],
            )
            self.assertEqual(dialogue["sourceAudioCueRefs"], [])
            self.assertEqual(dialogue["provenance"], evidence["provenance"])
            for forbidden in (
                "assetRef",
                "assetVersionRef",
                "assetVersionType",
                "generationResultRef",
                "generationResultDigest",
                "runtime",
            ):
                self.assertNotIn(forbidden, dialogue)

            production_root = root / "production-piper"
            production_root.mkdir()
            with self.assertRaisesRegex(
                NotImplementedError, "PIPER_RUNTIME_ABSENT"
            ):
                execute_piper_tts_evidence(
                    execution,
                    artifact_root=production_root,
                    storage_key=(
                        "asset-versions/audio/pr6/"
                        "narration-production-piper.wav"
                    ),
                )
            self.assertEqual(list(production_root.iterdir()), [])


class M12ClosedInternalAudioProbeIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffprobe"), "local FFprobe is required")
    def test_wav_named_hls_playlist_cannot_make_probe_access_network(self):
        probe_calls: list[list[str]] = []

        def observed_subprocess_run(command, *args, **kwargs):
            normalized = [str(item) for item in command]
            if "-show_streams" in normalized:
                probe_calls.append(normalized)
            return REAL_SUBPROCESS_RUN(command, *args, **kwargs)

        blocked_socket = unittest.mock.Mock(
            side_effect=AssertionError("audio probe attempted a Python socket")
        )
        blocked_connection = unittest.mock.Mock(
            side_effect=AssertionError("audio probe attempted a Python network call")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage_key = "asset-versions/audio/pr6/playlist-disguised.wav"
            playlist = root / storage_key
            playlist.parent.mkdir(parents=True, exist_ok=True)
            playlist.write_text(
                "#EXTM3U\n"
                "#EXT-X-STREAM-INF:BANDWIDTH=128000\n"
                "https://network-forbidden.invalid/audio.wav\n",
                encoding="utf-8",
            )
            track = _track(
                "ambience",
                storage_key,
                sha256(playlist.read_bytes()).hexdigest(),
                suffix="hls-playlist",
            )
            request = _mix_request([track])
            candidate = root / "not-created" / "mix.wav"
            adapter = DeterministicPreliminaryMixAdapter(root)
            with (
                patch("socket.socket", blocked_socket),
                patch("socket.create_connection", blocked_connection),
                patch(
                    "services.v4_platform.audio.subprocess.run",
                    side_effect=observed_subprocess_run,
                ),
                self.assertRaises(AudioArtifactVerificationError),
            ):
                adapter.generate(request, candidate)

            self.assertFalse(candidate.exists())
            self.assertFalse(candidate.parent.exists())

        blocked_socket.assert_not_called()
        blocked_connection.assert_not_called()
        self.assertEqual(len(probe_calls), 1)
        probe = probe_calls[0]
        whitelist_index = probe.index("-protocol_whitelist")
        self.assertEqual(probe[whitelist_index + 1], "file,pipe")
        self.assertNotIn("https", probe[whitelist_index + 1])


if __name__ == "__main__":
    unittest.main()
