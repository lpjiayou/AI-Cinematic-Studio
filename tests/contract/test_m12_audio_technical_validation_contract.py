from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction
import unittest

from services.v4_platform.audio_validation import (
    AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST,
    AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
    AUDIO_TECHNICAL_VALIDATOR_VERSION,
    PCM_CLIPPING_THRESHOLD,
    PCM_CONTENT_DIGEST_SPEC,
    AudioTechnicalAnalysisEvidence,
    AudioTechnicalArtifactError,
    AudioTechnicalEvidenceValidationError,
    _parse_loudness,
)
from services.v5_core_os.episode_production.audio_timing import (
    AudioCue,
    build_source_audio_timing_evidence,
    validate_audio_cue,
)
from services.v5_core_os.episode_production.audio_authority import (
    validate_sfx_asset_version,
)
from services.v5_core_os.episode_production.audio_validation import (
    AUDIO_TECHNICAL_FAILURE_REASON,
    AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
    AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION,
    AUDIO_TECHNICAL_VALIDATION_STATE,
    V4_AUDIO_TECHNICAL_ANALYSIS_SCHEMA_VERSION,
    AudioTechnicalCueBindingError,
    AudioTechnicalEvidenceBindingError,
    AudioTechnicalValidationError,
    build_audio_technical_validation,
    validate_audio_technical_validation,
)
from services.v5_core_os.episode_production.foundation import (
    UpstreamNotReadyError,
    _digest,
)
from tests.contract.test_m12_audio_timing_contract import (
    SCRIPT_VERSION_DIGEST,
    SCRIPT_VERSION_REF,
    build_cue,
    explicit_source_assets,
    sealed,
)


CREATED_AT = "2026-08-29T13:00:00Z"


def technical_source() -> dict:
    source = explicit_source_assets()["sources"]["sfx"]
    evidence = deepcopy(source["v4Evidence"])
    evidence.pop("payloadDigest")
    evidence["artifactRef"] = "audio-artifact-" + evidence["sha256"][:32]
    evidence["artifactEvidenceRef"] = (
        "audio-artifact-evidence-"
        + _digest(
            {
                "generationRequestDigest": evidence[
                    "generationRequestDigest"
                ],
                "executionRequestDigest": evidence[
                    "executionRequestDigest"
                ],
                "storageKey": evidence["storageKey"],
                "sha256": evidence["sha256"],
            }
        )[:32]
    )
    evidence = sealed(evidence)

    asset = deepcopy(source["asset"])
    asset.pop("payloadDigest")
    asset["artifact"].update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
        }
    )
    provenance = deepcopy(asset["provenance"])
    provenance.pop("payloadDigest")
    provenance.update(
        {
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
        }
    )
    asset["provenance"] = sealed(provenance)
    asset = sealed(asset)
    asset_contract = validate_sfx_asset_version(asset)
    timing = build_source_audio_timing_evidence(
        evidence,
        source_asset_version=asset_contract,
    )
    return {
        "asset": asset,
        "assetContract": asset_contract,
        "v4Evidence": evidence,
        "timingEvidence": timing,
    }


def seal_analysis(value: dict) -> dict:
    result = deepcopy(value)
    result.pop("payloadDigest", None)
    result.pop("analysisEvidenceRef", None)
    result["analysisEvidenceRef"] = (
        "audio-technical-analysis-evidence-"
        + _digest(result)[:32]
    )
    return sealed(result)


def analysis_evidence(
    source: dict, *, clipping: bool = False
) -> AudioTechnicalAnalysisEvidence:
    evidence = source["v4Evidence"]
    sample_count = evidence["probe"]["durationSamples"]
    sample_rate = evidence["sampleRate"]
    duration = Fraction(sample_count, sample_rate)
    return AudioTechnicalAnalysisEvidence._from_analyzer(
        seal_analysis(
            {
                "schemaVersion": V4_AUDIO_TECHNICAL_ANALYSIS_SCHEMA_VERSION,
                "sourceArtifactEvidenceRef": evidence[
                    "artifactEvidenceRef"
                ],
                "sourceArtifactEvidenceDigest": evidence["payloadDigest"],
                "artifactRef": evidence["artifactRef"],
                "storageKey": evidence["storageKey"],
                "byteSize": evidence["byteSize"],
                "fileDigest": evidence["sha256"],
                "codec": evidence["probe"]["codec"],
                "container": evidence["probe"]["container"],
                "sampleRate": sample_rate,
                "channelCount": evidence["channels"],
                "channelLayout": "mono",
                "sampleCount": sample_count,
                "duration": {
                    "numerator": duration.numerator,
                    "denominator": duration.denominator,
                    "unit": "SECONDS",
                },
                "integratedLufs": "-24.000",
                "loudnessRangeLra": "0.000",
                "truePeakDbtp": "-18.000",
                "maxSamplePeak": 32_767 if clipping else 4_000,
                "silenceRanges": [],
                "clippedSampleCount": 2 if clipping else 0,
                "clippingThreshold": deepcopy(PCM_CLIPPING_THRESHOLD),
                "clippingDetected": clipping,
                "dcOffset": "0.000000000",
                "pcmContentDigest": _digest(
                    {"canonicalPcmFixture": "sfx", "clipping": clipping}
                ),
                "pcmDigestSpec": deepcopy(PCM_CONTENT_DIGEST_SPEC),
                "analysisParametersDigest": (
                    AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST
                ),
                "validatorIdentity": AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
                "validatorVersion": AUDIO_TECHNICAL_VALIDATOR_VERSION,
                "ffmpegVersion": (
                    "ffmpeg version 6.1.1 contract-fixture | sha256:"
                    + "a" * 64
                ),
                "ffprobeVersion": (
                    "ffprobe version 6.1.1 contract-fixture | sha256:"
                    + "b" * 64
                ),
                "validationState": "FAILED" if clipping else "PASSED",
                "failureReasons": (
                    [AUDIO_TECHNICAL_FAILURE_REASON] if clipping else []
                ),
                "state": "TECHNICAL_ANALYSIS_COMPLETE",
                "publicationAllowed": False,
            }
        )
    )


def validation_command(suffix: str = "1") -> dict:
    return {
        "validationRef": "audio-technical-validation-sfx",
        "validationVersionRef": f"audio-technical-validation-sfx-v{suffix}",
        "version": 1,
        "supersedesValidationVersionRef": None,
        "supersedesValidationVersionDigest": None,
        "createdBy": "v5.m12.audio-technical.contract-test",
        "createdAt": CREATED_AT,
    }


def validated_partial_cue(source: dict) -> AudioCue:
    cue = build_cue(
        source,
        "sfx",
        sourceStartSample=1_200,
        sourceEndSample=4_800,
    )
    return validate_audio_cue(
        cue,
        source_asset_version=source["assetContract"],
        source_artifact_evidence=source["v4Evidence"],
        source_timing_evidence=source["timingEvidence"],
        expected_script_version_ref=SCRIPT_VERSION_REF,
        expected_script_version_digest=SCRIPT_VERSION_DIGEST,
    )


class M12AudioTechnicalValidationContractTests(unittest.TestCase):
    def test_valid_analysis_builds_closed_immutable_validation(self):
        source = technical_source()
        analysis = analysis_evidence(source)
        analysis_value = analysis.as_dict()
        command = validation_command()

        result = build_audio_technical_validation(
            command,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        wrapper = validate_audio_technical_validation(
            result,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )

        self.assertEqual(wrapper.as_dict(), result)
        self.assertEqual(
            result["schemaVersion"],
            AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION,
        )
        self.assertEqual(result["state"], AUDIO_TECHNICAL_VALIDATION_STATE)
        self.assertEqual(
            result["authorityState"],
            AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
        )
        self.assertTrue(result["immutable"])
        self.assertFalse(result["publicationAllowed"])
        self.assertEqual(
            result["analysisEvidenceDigest"], analysis_value["payloadDigest"]
        )
        self.assertEqual(result["sourceTimingEvidence"], source["timingEvidence"])
        self.assertEqual(result["validationState"], "PASSED")
        self.assertEqual(result["failureReasons"], [])

        with self.assertRaises(FrozenInstanceError):
            wrapper._payload_json = "{}"
        detached = wrapper.as_dict()
        detached["validationState"] = "FAILED"
        self.assertEqual(wrapper.as_dict()["validationState"], "PASSED")

        unexpected = deepcopy(command)
        unexpected["timelineVersionRef"] = "timeline-version-forbidden"
        with self.assertRaises(AudioTechnicalValidationError):
            build_audio_technical_validation(
                unexpected,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                v4_analysis_evidence=analysis,
            )

    def test_missing_unparseable_or_nonfinite_lufs_fails_closed(self):
        source = technical_source()
        valid_wrapper = analysis_evidence(source)
        valid = valid_wrapper.as_dict()

        with self.assertRaises(UpstreamNotReadyError):
            build_audio_technical_validation(
                validation_command(),
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                v4_analysis_evidence=valid,
            )

        cases = {
            "missing": None,
            "garbage": "not-a-number",
            "nan": "NaN",
            "positive_infinity": "+Inf",
            "negative_infinity": "-Inf",
        }

        for label, replacement in cases.items():
            malformed = deepcopy(valid)
            malformed.pop("payloadDigest")
            if replacement is None:
                malformed.pop("integratedLufs")
            else:
                malformed["integratedLufs"] = replacement
            malformed = seal_analysis(malformed)
            with self.subTest(label=label), self.assertRaises(
                AudioTechnicalEvidenceValidationError
            ):
                AudioTechnicalAnalysisEvidence._from_analyzer(malformed)

        malformed_runtime_outputs = (
            "{}",
            '{"input_i":"-24.0","input_lra":"0.0"}',
            '{"input_i":"garbage","input_lra":"0.0","input_tp":"-1.0"}',
            '{"input_i":"-inf","input_lra":"0.0","input_tp":"-1.0"}',
            '{"input_i":"-24.0","input_lra":"0.0","input_tp":"-1.0"',
            (
                '{"input_i":"-24.0","input_lra":"0.0","input_tp":"-1.0"}'
                '{"input_i":"-24.0","input_lra":"0.0","input_tp":"-1.0"}'
            ),
        )
        for output in malformed_runtime_outputs:
            with self.subTest(runtime_output=output), self.assertRaises(
                AudioTechnicalArtifactError
            ):
                _parse_loudness(output)

    def test_clipping_is_preserved_as_a_failed_technical_record(self):
        source = technical_source()
        analysis = analysis_evidence(source, clipping=True)

        result = build_audio_technical_validation(
            validation_command(),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )

        self.assertTrue(result["clippingDetected"])
        self.assertGreater(result["clippedSampleCount"], 0)
        self.assertEqual(result["validationState"], "FAILED")
        self.assertEqual(
            result["failureReasons"], [AUDIO_TECHNICAL_FAILURE_REASON]
        )
        self.assertEqual(result["state"], AUDIO_TECHNICAL_VALIDATION_STATE)
        self.assertFalse(result["publicationAllowed"])

    def test_cue_extent_mismatch_is_rejected_but_partial_cue_is_valid(self):
        source = technical_source()
        analysis = analysis_evidence(source)
        partial = validated_partial_cue(source)

        accepted = build_audio_technical_validation(
            validation_command(),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
            audio_cues=[partial],
        )
        self.assertLess(
            partial.as_dict()["sourceEndSample"], accepted["sampleCount"]
        )
        self.assertEqual(
            accepted["audioCueBindings"][0]["cueVersionRef"],
            partial.as_dict()["cueVersionRef"],
        )

        mismatched_analysis = analysis.as_dict()
        mismatched_analysis.pop("payloadDigest")
        mismatched_analysis["sampleCount"] += 1
        mismatched_duration = Fraction(
            mismatched_analysis["sampleCount"],
            mismatched_analysis["sampleRate"],
        )
        mismatched_analysis["duration"] = {
            "numerator": mismatched_duration.numerator,
            "denominator": mismatched_duration.denominator,
            "unit": "SECONDS",
        }
        mismatched_analysis = AudioTechnicalAnalysisEvidence._from_analyzer(
            seal_analysis(mismatched_analysis)
        )
        with self.assertRaises(AudioTechnicalEvidenceBindingError):
            build_audio_technical_validation(
                validation_command(),
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                v4_analysis_evidence=mismatched_analysis,
                audio_cues=[partial],
            )

        forged_mapping = partial.as_dict()
        forged_mapping["sourceEndSample"] = (
            source["timingEvidence"]["sampleCount"] + 1
        )
        forged_end = Fraction(
            forged_mapping["sourceEndSample"],
            source["timingEvidence"]["sampleRate"],
        )
        forged_mapping["sourceEndTime"] = {
            "numerator": forged_end.numerator,
            "denominator": forged_end.denominator,
        }
        forged_mapping.pop("payloadDigest")
        forged = AudioCue._from_validated(sealed(forged_mapping))

        with self.assertRaises(AudioTechnicalCueBindingError):
            build_audio_technical_validation(
                validation_command(),
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                v4_analysis_evidence=analysis,
                audio_cues=[forged],
            )

    def test_versioned_validation_requires_exact_predecessor_wrapper(self):
        source = technical_source()
        analysis = analysis_evidence(source)
        missing_predecessor = validation_command("2")
        missing_predecessor.update(
            {
                "version": 2,
                "supersedesValidationVersionRef": (
                    "audio-technical-validation-sfx-v1"
                ),
                "supersedesValidationVersionDigest": "c" * 64,
            }
        )

        with self.assertRaises(UpstreamNotReadyError):
            build_audio_technical_validation(
                missing_predecessor,
                source_asset_version=source["assetContract"],
                source_artifact_evidence=source["v4Evidence"],
                v4_analysis_evidence=analysis,
            )

        first_value = build_audio_technical_validation(
            validation_command("1"),
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        first = validate_audio_technical_validation(
            first_value,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
        )
        second_command = validation_command("2")
        second_command.update(
            {
                "version": 2,
                "supersedesValidationVersionRef": first_value[
                    "validationVersionRef"
                ],
                "supersedesValidationVersionDigest": first_value[
                    "payloadDigest"
                ],
            }
        )
        second = build_audio_technical_validation(
            second_command,
            source_asset_version=source["assetContract"],
            source_artifact_evidence=source["v4Evidence"],
            v4_analysis_evidence=analysis,
            predecessor_validation=first,
        )
        self.assertEqual(second["version"], 2)
        self.assertEqual(
            second["supersedesValidationVersionDigest"],
            first_value["payloadDigest"],
        )

        stale_commands = {
            "root": {"validationRef": "another-validation-root"},
            "version": {"version": 3},
            "parent_ref": {
                "supersedesValidationVersionRef": "unrelated-validation-v1"
            },
            "parent_digest": {
                "supersedesValidationVersionDigest": "d" * 64
            },
        }
        for label, changes in stale_commands.items():
            stale = deepcopy(second_command)
            stale.update(changes)
            with self.subTest(label=label), self.assertRaises(
                AudioTechnicalEvidenceBindingError
            ):
                build_audio_technical_validation(
                    stale,
                    source_asset_version=source["assetContract"],
                    source_artifact_evidence=source["v4Evidence"],
                    v4_analysis_evidence=analysis,
                    predecessor_validation=first,
                )


if __name__ == "__main__":
    unittest.main()
