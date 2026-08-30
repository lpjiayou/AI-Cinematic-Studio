from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.v4_platform import isolated_speech_runtime as runtime
from services.v4_platform.audio_validation import AudioTechnicalAnalysisEvidence
from services.v4_platform.isolated_speech_runtime import (
    COSYVOICE_BUILD_VOICE_PROFILE,
    COSYVOICE_RUNTIME_KIND,
    COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    IsolatedSpeechArtifactError,
    IsolatedSpeechContractError,
    IsolatedSpeechExecutionError,
    IsolatedSpeechRuntimeEvidence,
    KOKORO_RUNTIME_KIND,
    KOKORO_SYNTHESIZE_FIXED_VOICE,
    TestOnlyIsolatedRuntimeEvidence,
    TestOnlyIsolatedRuntimeHarness,
    build_runtime_request,
    build_test_runtime_manifest,
    hash_test_executable,
)
from services.v5_core_os.episode_production.audio_authority import (
    DialogueAssetVersion,
    VoiceAssetVersion,
)
from services.v5_core_os.episode_production.foundation import UpstreamNotReadyError
from services.v5_core_os.episode_production.isolated_speech import (
    build_isolated_clone_dialogue_asset_version,
    build_isolated_speech_audio_technical_validation,
    build_isolated_voice_profile_technical_validation,
)
from services.v5_core_os.episode_production.voice_profile import VoiceProfileVersion


STUB_EXECUTABLE = Path(__file__).parents[1] / "stub_isolated_speech_runtime.py"
PRIVATE_TRANSCRIPT = "Private source recording transcript: do not persist this text."


def _digest(label: str) -> str:
    return sha256(label.encode("utf-8")).hexdigest()


def _production_lineage() -> dict[str, str]:
    return {
        "workspaceRef": "workspace-m12-c2-integration",
        "projectRef": "project-m12-c2-integration",
        "seriesRef": "series-m12-c2-integration",
        "episodeRef": "episode-m12-c2-integration",
        "productionRunRef": "production-run-m12-c2-integration",
        "creativeShotRef": "creative-shot-m12-c2-integration",
        "creativeShotVersionRef": "creative-shot-m12-c2-integration-v1",
        "creativeShotDigest": _digest("creative-shot-version"),
        "assetRequirementRef": "audio-requirement-m12-c2-integration",
        "assetRequirementDigest": _digest("audio-requirement"),
        "generationRequestRef": "audio-generation-request-m12-c2-integration",
        "generationRequestVersionRef": (
            "audio-generation-request-m12-c2-integration-v1"
        ),
        "generationRequestDigest": _digest("audio-generation-request"),
        "scriptRef": "script-m12-c2-integration",
        "scriptVersionRef": "script-m12-c2-integration-v1",
        "scriptVersionDigest": _digest("script-version"),
    }


def _fixed_lineage() -> dict[str, str]:
    return {
        **_production_lineage(),
        "voiceLockRef": "fixed-voice-lock-m12-c2-integration",
        "voiceLockVersionRef": "fixed-voice-lock-m12-c2-integration-v1",
        "voiceLockVersionDigest": _digest("fixed-voice-lock-version-v1"),
        "voiceLockConfirmationRef": "fixed-voice-lock-confirmation",
        "voiceLockConfirmationDigest": _digest("fixed-voice-lock-confirmation"),
    }


def _profile_lineage(
    *, source_file_digest: str, source_pcm_digest: str
) -> dict[str, str]:
    return {
        "workspaceRef": "workspace-m12-c2-integration",
        "projectRef": "project-m12-c2-integration",
        "seriesRef": "series-m12-c2-integration",
        "productionRunRef": "production-run-m12-c2-integration",
        "sourceRecordingBindingRef": "source-recording-binding-m12-c2",
        "sourceRecordingBindingDigest": _digest("source-recording-binding"),
        "canonicalAssetVersionRef": "source-audio-asset-version-v1",
        "canonicalAssetVersionDigest": _digest("source-audio-asset-version"),
        "audioFileDigest": source_file_digest,
        "audioPcmContentDigest": source_pcm_digest,
        "transcriptVersionRef": "source-transcript-version-v1",
        "transcriptVersionDigest": _digest("source-transcript-version"),
        "transcriptTextDigest": sha256(PRIVATE_TRANSCRIPT.encode("utf-8")).hexdigest(),
        "consentGrantVersionRef": "consent-grant-version-v2",
        "consentGrantVersionDigest": _digest("consent-grant-version-v2"),
        "voiceLockRef": "clone-voice-lock-m12-c2-integration",
        "voiceLockVersionRef": "clone-voice-lock-m12-c2-integration-v2",
        "voiceLockVersionDigest": _digest("clone-voice-lock-version-v2"),
        "voiceLockConfirmationRef": "clone-voice-lock-confirmation",
        "voiceLockConfirmationDigest": _digest("clone-voice-lock-confirmation"),
        "rightsBindingRef": "voice-clone-rights-binding",
        "rightsBindingDigest": _digest("voice-clone-rights-binding"),
        "voiceIdentityRef": "voice-identity-m12-c2",
        "voiceIdentityVersionRef": "voice-identity-m12-c2-v1",
        "voiceIdentityDigest": _digest("voice-identity-version"),
    }


def _dialogue_lineage(
    *, profile_file_digest: str, profile_content_digest: str
) -> dict[str, str]:
    return {
        **_production_lineage(),
        "voiceProfileRef": "voice-profile-m12-c2-integration",
        "voiceProfileVersionRef": "voice-profile-m12-c2-integration-v1",
        "voiceProfileVersionDigest": _digest("voice-profile-version"),
        "voiceProfilePackageFileDigest": profile_file_digest,
        "voiceProfilePackageContentDigest": profile_content_digest,
        "voiceLockVersionRef": "clone-voice-lock-m12-c2-integration-v2",
        "voiceLockVersionDigest": _digest("clone-voice-lock-version-v2"),
        "sourceRecordingBindingRef": "source-recording-binding-m12-c2",
        "sourceRecordingBindingDigest": _digest("source-recording-binding"),
        "consentGrantVersionRef": "consent-grant-version-v2",
        "consentGrantVersionDigest": _digest("consent-grant-version-v2"),
        "rightsBindingRef": "voice-clone-rights-binding",
        "rightsBindingDigest": _digest("voice-clone-rights-binding"),
        "voiceAssetVersionRef": "voice-asset-version-m12-c2-v1",
        "voiceAssetVersionDigest": _digest("voice-asset-version"),
    }


def _request(
    *,
    operation: str,
    manifest: dict,
    lineage: dict[str, str],
    output_binding: str,
) -> dict:
    if operation == KOKORO_SYNTHESIZE_FIXED_VOICE:
        voice_id = "af_heart"
        voice_profile_version_ref = None
        parameters = {
            "rateScale": 1,
            "pitchSemitones": 0,
            "emotionTag": "neutral",
        }
        text = "A fixed-voice integration sentence."
    elif operation == COSYVOICE_BUILD_VOICE_PROFILE:
        voice_id = None
        voice_profile_version_ref = None
        parameters = {}
        text = PRIVATE_TRANSCRIPT
    else:
        voice_id = None
        voice_profile_version_ref = lineage["voiceProfileVersionRef"]
        parameters = {
            "rateScale": 1,
            "pitchSemitones": 0,
            "emotionTag": "neutral",
        }
        text = "A cloned-dialogue integration sentence."
    return build_runtime_request(
        operation_kind=operation,
        request_ref=f"request-{operation.lower()}-{output_binding}",
        input_lineage_refs_and_digests=lineage,
        text=text,
        language="en-US",
        voice_id=voice_id,
        voice_profile_version_ref=voice_profile_version_ref,
        effective_speech_parameters=parameters,
        sample_rate=48_000,
        channel_count=1,
        runtime_manifest_ref=manifest["runtimeManifestRef"],
        runtime_manifest_digest=manifest["payloadDigest"],
        output_artifact_binding_ref=output_binding,
    )


@unittest.skipUnless(
    os.name == "posix"
    and Path("/proc/self/fd").is_dir()
    and shutil.which("ffmpeg") is not None
    and shutil.which("ffprobe") is not None,
    "the isolated FD transport and pinned FFmpeg/FFprobe are required",
)
class M12IsolatedSpeechRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        executable_digest = hash_test_executable(STUB_EXECUTABLE)
        cls.kokoro_manifest = build_test_runtime_manifest(
            runtime_kind=KOKORO_RUNTIME_KIND,
            executable_digest=executable_digest,
            fixture_ref="test-kokoro-runtime-manifest",
        )
        cls.cosyvoice_manifest = build_test_runtime_manifest(
            runtime_kind=COSYVOICE_RUNTIME_KIND,
            executable_digest=executable_digest,
            fixture_ref="test-cosyvoice-runtime-manifest",
        )
        cls.kokoro = TestOnlyIsolatedRuntimeHarness(
            executable=STUB_EXECUTABLE,
            manifest=cls.kokoro_manifest,
        )
        cls.cosyvoice = TestOnlyIsolatedRuntimeHarness(
            executable=STUB_EXECUTABLE,
            manifest=cls.cosyvoice_manifest,
        )

    def _fixed_request(self, mode: str = "pass") -> dict:
        return _request(
            operation=KOKORO_SYNTHESIZE_FIXED_VOICE,
            manifest=self.kokoro_manifest,
            lineage=_fixed_lineage(),
            output_binding=f"test-output-{mode}",
        )

    def assert_output_fail_closed(self, path: Path) -> None:
        """A failed run leaves no bytes, or only its zero-byte no-retry tombstone."""

        if path.exists():
            self.assertEqual(path.stat().st_size, 0)

    def _run_profile(
        self,
        root: Path,
        *,
        source_path: Path,
        source_pcm_digest: str,
        source_audio_analysis: AudioTechnicalAnalysisEvidence,
        mode: str = "pass",
    ) -> tuple[Path, TestOnlyIsolatedRuntimeEvidence, dict]:
        source_digest = sha256(source_path.read_bytes()).hexdigest()
        request = _request(
            operation=COSYVOICE_BUILD_VOICE_PROFILE,
            manifest=self.cosyvoice_manifest,
            lineage=_profile_lineage(
                source_file_digest=source_digest,
                source_pcm_digest=source_pcm_digest,
            ),
            output_binding=f"test-output-{mode}",
        )
        output = (
            root
            / "asset-versions"
            / "audio"
            / f"profile-{mode}.voicepkg"
        )
        evidence = self.cosyvoice.execute(
            request,
            output_path=output,
            source_path=source_path,
            artifact_root=root,
            source_audio_analysis=source_audio_analysis,
        )
        return output, evidence, request

    def test_three_operations_round_trip_through_all_four_fd_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixed_output = root / "asset-versions" / "audio" / "fixed.wav"
            fixed_evidence = self.kokoro.execute(
                self._fixed_request(),
                output_path=fixed_output,
                artifact_root=root,
            )
            profile_output, profile_evidence, profile_request = self._run_profile(
                root,
                source_path=fixed_output,
                source_pcm_digest=fixed_evidence.as_dict()["response"][
                    "outputPcmContentDigest"
                ],
                source_audio_analysis=fixed_evidence.independent_audio_analysis(),
            )
            profile_response = profile_evidence.as_dict()["response"]
            dialogue_request = _request(
                operation=COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
                manifest=self.cosyvoice_manifest,
                lineage=_dialogue_lineage(
                    profile_file_digest=profile_response[
                        "profilePackageFileDigest"
                    ],
                    profile_content_digest=profile_response[
                        "profilePackageContentDigest"
                    ],
                ),
                output_binding="test-output-pass",
            )
            dialogue_output = (
                root / "asset-versions" / "audio" / "dialogue.wav"
            )
            dialogue_evidence = self.cosyvoice.execute(
                dialogue_request,
                output_path=dialogue_output,
                voice_profile_package_path=profile_output,
                artifact_root=root,
            )

            executions = (
                (fixed_output, fixed_evidence, KOKORO_SYNTHESIZE_FIXED_VOICE),
                (profile_output, profile_evidence, COSYVOICE_BUILD_VOICE_PROFILE),
                (
                    dialogue_output,
                    dialogue_evidence,
                    COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
                ),
            )
            for output, evidence, operation in executions:
                with self.subTest(operation=operation):
                    value = evidence.as_dict()
                    self.assertIs(type(evidence), TestOnlyIsolatedRuntimeEvidence)
                    self.assertNotIsInstance(evidence, IsolatedSpeechRuntimeEvidence)
                    self.assertNotIsInstance(
                        evidence,
                        (VoiceProfileVersion, VoiceAssetVersion, DialogueAssetVersion),
                    )
                    self.assertTrue(output.is_file())
                    self.assertGreater(output.stat().st_size, 44)
                    self.assertEqual(value["state"], "TEST_FIXTURE_ONLY")
                    self.assertEqual(value["authorityState"], "NOT_AUTHORITY")
                    self.assertEqual(value["admissionState"], "NOT_ADMITTED")
                    self.assertFalse(value["publicationAllowed"])
                    self.assertEqual(value["response"]["operationKind"], operation)
                    self.assertEqual(
                        value["independentAudioAnalysis"]["validationState"],
                        "PASSED",
                    )
                    self.assertEqual(
                        value["independentAudioAnalysis"]["pcmContentDigest"],
                        value["response"]["outputPcmContentDigest"],
                    )

            with self.assertRaises(UpstreamNotReadyError):
                build_isolated_speech_audio_technical_validation(
                    {},
                    runtime_request=self._fixed_request(),
                    runtime_evidence=fixed_evidence,
                    generation_result={},
                    artifact_evidence={},
                    v4_analysis_evidence=(
                        fixed_evidence.independent_audio_analysis()
                    ),
                )
            with self.assertRaises(UpstreamNotReadyError):
                build_isolated_voice_profile_technical_validation(
                    {"technicalValidationRef": "must-not-mint-profile-validation"},
                    runtime_request=profile_request,
                    runtime_evidence=profile_evidence,
                    runtime_manifest=self.cosyvoice_manifest,
                )
            with self.assertRaises(UpstreamNotReadyError):
                build_isolated_clone_dialogue_asset_version(
                    {},
                    runtime_request=dialogue_request,
                    runtime_evidence=dialogue_evidence,
                    v4_analysis_evidence=None,
                    audio_technical_validation=None,
                    voice_asset_version=None,
                    audio_generation_request=None,
                    generation_result={},
                    artifact_evidence={},
                    current_voice_profile_authority=None,
                )

    def test_profile_source_and_evidence_are_private_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = (
                root
                / "asset-versions"
                / "audio"
                / "private-source-recording-do-not-log.wav"
            )
            fixed_evidence = self.kokoro.execute(
                self._fixed_request(),
                output_path=source,
                artifact_root=root,
            )
            _, evidence, _ = self._run_profile(
                root,
                source_path=source,
                source_pcm_digest=fixed_evidence.as_dict()["response"][
                    "outputPcmContentDigest"
                ],
                source_audio_analysis=fixed_evidence.independent_audio_analysis(),
            )
            serialized = json.dumps(
                evidence.as_dict(), ensure_ascii=False, sort_keys=True
            )
            serialized_analysis = evidence.as_dict()[
                "independentAudioAnalysis"
            ]

            self.assertNotIn(PRIVATE_TRANSCRIPT, serialized)
            self.assertNotIn(str(source), serialized)
            self.assertNotIn(source.name, serialized)
            self.assertNotIn(source.relative_to(root).as_posix(), serialized)
            self.assertNotIn(source.read_bytes().hex(), serialized)
            for locator_field in (
                "storageKey",
                "artifactRef",
                "sourceArtifactEvidenceRef",
                "sourceArtifactEvidenceDigest",
            ):
                self.assertNotIn(locator_field, serialized_analysis)

    def test_profile_source_digest_is_verified_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.wav"
            source.write_bytes(b"server-resolved-source")
            request = _request(
                operation=COSYVOICE_BUILD_VOICE_PROFILE,
                manifest=self.cosyvoice_manifest,
                lineage=_profile_lineage(
                    source_file_digest="0" * 64,
                    source_pcm_digest=_digest("canonical-source-pcm"),
                ),
                output_binding="test-output-pass",
            )
            output = (
                root
                / "asset-versions"
                / "audio"
                / "must-not-exist.voicepkg"
            )
            real_popen = subprocess.Popen
            attempts = 0

            def counting_popen(*args, **kwargs):
                nonlocal attempts
                attempts += 1
                return real_popen(*args, **kwargs)

            with patch.object(runtime.subprocess, "Popen", side_effect=counting_popen):
                with self.assertRaises(IsolatedSpeechContractError):
                    self.cosyvoice.execute(
                        request,
                        output_path=output,
                        artifact_root=root,
                    )
                with self.assertRaises(IsolatedSpeechArtifactError):
                    self.cosyvoice.execute(
                        request,
                        output_path=output,
                        source_path=source,
                        artifact_root=root,
                    )

            self.assertEqual(attempts, 0)
            self.assertFalse(output.exists())

    def test_request_digest_is_rejected_before_spawn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "asset-versions" / "audio" / "invalid.wav"
            request = self._fixed_request()
            request["payloadDigest"] = "0" * 64
            real_popen = subprocess.Popen
            attempts = 0

            def counting_popen(*args, **kwargs):
                nonlocal attempts
                attempts += 1
                return real_popen(*args, **kwargs)

            with patch.object(runtime.subprocess, "Popen", side_effect=counting_popen):
                with self.assertRaises(IsolatedSpeechContractError):
                    self.kokoro.execute(
                        request,
                        output_path=output,
                        artifact_root=root,
                    )

            self.assertEqual(attempts, 0)
            self.assertFalse(output.exists())

    def test_clone_dialogue_requires_exact_profile_package_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = (
                root / "asset-versions" / "audio" / "profile.voicepkg"
            )
            profile.parent.mkdir(parents=True)
            profile.write_bytes(b"immutable-profile-package")
            inconsistent_request = _request(
                operation=COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
                manifest=self.cosyvoice_manifest,
                lineage=_dialogue_lineage(
                    profile_file_digest="0" * 64,
                    profile_content_digest=_digest("profile-package-content"),
                ),
                output_binding="test-output-pass",
            )
            output = root / "asset-versions" / "audio" / "dialogue.wav"

            with self.assertRaises(IsolatedSpeechContractError):
                self.cosyvoice.execute(
                    inconsistent_request,
                    output_path=output,
                    voice_profile_package_path=profile,
                    artifact_root=root,
                )
            self.assertFalse(output.exists())

            wrong_byte_digest_request = _request(
                operation=COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
                manifest=self.cosyvoice_manifest,
                lineage=_dialogue_lineage(
                    profile_file_digest="0" * 64,
                    profile_content_digest="0" * 64,
                ),
                output_binding="test-output-pass",
            )
            with self.assertRaises(IsolatedSpeechArtifactError):
                self.cosyvoice.execute(
                    wrong_byte_digest_request,
                    output_path=output,
                    voice_profile_package_path=profile,
                    artifact_root=root,
                )
            self.assertFalse(output.exists())

    def test_timeout_executes_exactly_once_and_nonzero_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_popen = subprocess.Popen
            attempts = 0

            def counting_popen(*args, **kwargs):
                nonlocal attempts
                attempts += 1
                return real_popen(*args, **kwargs)

            timeout_output = (
                root / "asset-versions" / "audio" / "timeout.wav"
            )
            with patch.object(runtime.subprocess, "Popen", side_effect=counting_popen):
                with self.assertRaises(IsolatedSpeechExecutionError):
                    self.kokoro.execute(
                        self._fixed_request("timeout"),
                        output_path=timeout_output,
                        artifact_root=root,
                        timeout_seconds=0.05,
                    )
            self.assertEqual(attempts, 1)
            self.assert_output_fail_closed(timeout_output)

            nonzero_output = (
                root / "asset-versions" / "audio" / "nonzero.wav"
            )
            with self.assertRaises(IsolatedSpeechExecutionError):
                self.kokoro.execute(
                    self._fixed_request("nonzero"),
                    output_path=nonzero_output,
                    artifact_root=root,
                )
            self.assert_output_fail_closed(nonzero_output)

    def test_extra_stdout_and_network_claim_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ("extra-stdout", IsolatedSpeechExecutionError),
                ("network", IsolatedSpeechContractError),
            )
            for mode, error in cases:
                with self.subTest(mode=mode):
                    output = root / "asset-versions" / "audio" / f"{mode}.wav"
                    with self.assertRaises(error):
                        self.kokoro.execute(
                            self._fixed_request(mode),
                            output_path=output,
                            artifact_root=root,
                        )
                    self.assert_output_fail_closed(output)

    def test_runtime_and_independent_artifact_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = (
                ("response-digest", IsolatedSpeechContractError),
                ("engine-drift", IsolatedSpeechContractError),
                ("model-drift", IsolatedSpeechContractError),
                ("dependency-drift", IsolatedSpeechContractError),
                ("runtime-drift", IsolatedSpeechContractError),
                ("file-digest-drift", IsolatedSpeechArtifactError),
                ("pcm-digest-drift", IsolatedSpeechArtifactError),
                ("probe-drift", IsolatedSpeechArtifactError),
                ("clipping", IsolatedSpeechArtifactError),
            )
            for mode, error in cases:
                with self.subTest(mode=mode):
                    output = root / "asset-versions" / "audio" / f"{mode}.wav"
                    with self.assertRaises(error):
                        self.kokoro.execute(
                            self._fixed_request(mode),
                            output_path=output,
                            artifact_root=root,
                        )
                    self.assert_output_fail_closed(output)

    def test_replaced_output_inode_is_rejected_without_deleting_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "asset-versions" / "audio" / "replace.wav"
            replacement = b"untrusted-race-replacement"
            real_verify = runtime._verify_visible_output

            def replace_before_verification(
                parent_descriptor, name, descriptor, original
            ):
                output.unlink()
                output.write_bytes(replacement)
                return real_verify(
                    parent_descriptor,
                    name,
                    descriptor,
                    original,
                )

            with patch.object(
                runtime,
                "_verify_visible_output",
                side_effect=replace_before_verification,
            ):
                with self.assertRaises(IsolatedSpeechArtifactError):
                    self.kokoro.execute(
                        self._fixed_request(),
                        output_path=output,
                        artifact_root=root,
                    )

            self.assertEqual(output.read_bytes(), replacement)


if __name__ == "__main__":
    unittest.main()
