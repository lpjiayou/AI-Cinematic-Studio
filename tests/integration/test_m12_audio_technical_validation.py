from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

from services.v4_platform.audio import (
    PROGRAMMATIC_AUDIO_ADAPTER_ID,
    audio_artifact_evidence,
)
from services.v4_platform.audio_validation import (
    CLIPPING_FAILURE_REASON,
    PCM_CLIPPING_THRESHOLD,
    PCM_CONTENT_DIGEST_SPEC,
    VALIDATION_STATE_FAILED,
    analyze_audio_artifact,
)
from services.v5_core_os.episode_production.audio_validation import (
    AUDIO_TECHNICAL_FAILURE_REASON,
    build_audio_technical_validation,
)
from services.v5_core_os.episode_production.foundation import _digest
from tests.contract.test_m12_audio_contract import PROJECT, SERIES
from tests.integration.test_m12_audio_execution import (
    _programmatic_request,
    _typed_sfx_asset_version,
)


SAMPLE_RATE = 48_000
SAMPLE_COUNT = 48_000
CREATED_AT = "2026-08-29T13:30:00Z"


class _FramesWavAdapter:
    adapter_identity = PROGRAMMATIC_AUDIO_ADAPTER_ID
    provenance = "LOCAL_EVIDENCE"

    def __init__(self, samples: list[int]):
        self._samples = list(samples)

    def generate(self, request: dict, candidate_path: Path) -> Path:
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(candidate_path), "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(SAMPLE_RATE)
            writer.writeframes(
                struct.pack(f"<{len(self._samples)}h", *self._samples)
            )
        return candidate_path


class _MetadataOnlyWavAdapter:
    adapter_identity = PROGRAMMATIC_AUDIO_ADAPTER_ID
    provenance = "LOCAL_EVIDENCE"

    def __init__(self, source: Path):
        self._source = source

    def generate(self, request: dict, candidate_path: Path) -> Path:
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(self._source),
                "-map",
                "0:a:0",
                "-c:a",
                "copy",
                "-map_metadata",
                "-1",
                "-metadata",
                "comment=m12-pr5-container-variant",
                "-y",
                str(candidate_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return candidate_path


def _square_wave(*, peak: int = 4_000) -> list[int]:
    return [
        peak if index % 48 < 24 else -peak
        for index in range(SAMPLE_COUNT)
    ]


def _execute_fixture(
    root: Path,
    *,
    ordinal: int,
    storage_key: str,
    adapter,
) -> tuple[dict, dict]:
    request = deepcopy(_programmatic_request("paper", ordinal=ordinal))
    request.pop("payloadDigest")
    request["parameters"]["durationSamples"] = SAMPLE_COUNT
    request["payloadDigest"] = _digest(request)
    result = audio_artifact_evidence(
        request,
        artifact_root=root,
        storage_key=storage_key,
        adapter=adapter,
    )
    return request, result


def _validation_command(suffix: str) -> dict:
    return {
        "validationRef": f"audio-technical-validation-{suffix}",
        "validationVersionRef": f"audio-technical-validation-{suffix}-v1",
        "version": 1,
        "supersedesValidationVersionRef": None,
        "supersedesValidationVersionDigest": None,
        "createdBy": "v5.m12.audio-technical.integration-test",
        "createdAt": CREATED_AT,
    }


class M12AudioTechnicalValidationIntegrationTests(unittest.TestCase):
    def test_pcm_digest_distinguishes_container_identity_from_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            samples = _square_wave()
            _, base_result = _execute_fixture(
                root,
                ordinal=11,
                storage_key="asset-versions/audio/pr5/base.wav",
                adapter=_FramesWavAdapter(samples),
            )
            base_path = root / base_result["storageKey"]
            _, metadata_result = _execute_fixture(
                root,
                ordinal=12,
                storage_key="asset-versions/audio/pr5/metadata.wav",
                adapter=_MetadataOnlyWavAdapter(base_path),
            )
            changed = list(samples)
            changed[len(changed) // 2] += 1
            _, changed_result = _execute_fixture(
                root,
                ordinal=13,
                storage_key="asset-versions/audio/pr5/changed.wav",
                adapter=_FramesWavAdapter(changed),
            )

            base_evidence = analyze_audio_artifact(
                base_result["artifactEvidence"], artifact_root=root
            )
            metadata_evidence = analyze_audio_artifact(
                metadata_result["artifactEvidence"], artifact_root=root
            )
            changed_evidence = analyze_audio_artifact(
                changed_result["artifactEvidence"], artifact_root=root
            )
            base = base_evidence.as_dict()
            metadata = metadata_evidence.as_dict()
            sample_changed = changed_evidence.as_dict()

            self.assertNotEqual(base["fileDigest"], metadata["fileDigest"])
            self.assertEqual(
                base["pcmContentDigest"], metadata["pcmContentDigest"]
            )
            self.assertEqual(base["pcmDigestSpec"], PCM_CONTENT_DIGEST_SPEC)
            self.assertEqual(metadata["pcmDigestSpec"], PCM_CONTENT_DIGEST_SPEC)
            self.assertNotEqual(
                base["pcmContentDigest"], sample_changed["pcmContentDigest"]
            )
            self.assertEqual(base["sampleCount"], SAMPLE_COUNT)
            self.assertEqual(metadata["sampleCount"], SAMPLE_COUNT)
            self.assertEqual(sample_changed["sampleCount"], SAMPLE_COUNT)

    def test_real_full_scale_pcm_fails_closed_as_clipping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clipping_magnitude = PCM_CLIPPING_THRESHOLD["absoluteMagnitude"]
            clipped_samples = [
                clipping_magnitude if index % 48 < 24 else -32_768
                for index in range(SAMPLE_COUNT)
            ]
            request, result = _execute_fixture(
                root,
                ordinal=21,
                storage_key="asset-versions/audio/pr5/full-scale.wav",
                adapter=_FramesWavAdapter(clipped_samples),
            )
            analysis = analyze_audio_artifact(
                result["artifactEvidence"], artifact_root=root
            )
            analysis_value = analysis.as_dict()

            self.assertEqual(analysis_value["maxSamplePeak"], 32_768)
            self.assertGreater(analysis_value["clippedSampleCount"], 0)
            self.assertTrue(analysis_value["clippingDetected"])
            self.assertEqual(
                analysis_value["clippingThreshold"], PCM_CLIPPING_THRESHOLD
            )
            self.assertEqual(
                analysis_value["validationState"], VALIDATION_STATE_FAILED
            )
            self.assertEqual(
                analysis_value["failureReasons"], [CLIPPING_FAILURE_REASON]
            )
            self.assertEqual(
                CLIPPING_FAILURE_REASON, AUDIO_TECHNICAL_FAILURE_REASON
            )

            source_asset = _typed_sfx_asset_version(
                request,
                result,
                project_ref=PROJECT,
                series_ref=SERIES,
            )
            validation = build_audio_technical_validation(
                _validation_command("full-scale"),
                source_asset_version=source_asset,
                source_artifact_evidence=result["artifactEvidence"],
                v4_analysis_evidence=analysis,
            )
            self.assertTrue(validation["clippingDetected"])
            self.assertEqual(
                validation["validationState"], VALIDATION_STATE_FAILED
            )
            self.assertEqual(
                validation["failureReasons"], [AUDIO_TECHNICAL_FAILURE_REASON]
            )
            self.assertEqual(
                validation["pcmContentDigest"],
                analysis_value["pcmContentDigest"],
            )
            self.assertFalse(validation["publicationAllowed"])


if __name__ == "__main__":
    unittest.main()
