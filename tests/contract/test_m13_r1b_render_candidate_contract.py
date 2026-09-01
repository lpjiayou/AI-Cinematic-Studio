from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from services.v3_render_core.digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    PCM_CONTENT_DIGEST_SPEC,
)
from services.v3_render_core import RenderArtifactError
from services.v3_render_core.render_candidate import (
    build_render_core_request,
    build_video_composition_plan,
)
from services.v4_platform.render_candidate import (
    RenderExecutionRequestError,
    build_render_execution_request,
    runtime_binding_digest,
)
from services.v5_core_os.episode_production.rendering import (
    SUBTITLE_TIMING_DIGEST_SPEC,
    RenderDomainContractError,
    RenderDomainStaleInputError,
    build_render_artifact_evidence,
    build_render_candidate,
    build_render_result,
    build_render_runtime_evidence,
    canonical_subtitle_timing_digest,
    validate_render_candidate,
)


DIGEST = "a" * 64
CREATED_AT = "2026-09-01T00:00:00Z"


def _media_probe() -> dict:
    return {
        "container": "mp4",
        "videoCodec": "h264",
        "width": 64,
        "height": 64,
        "frameRate": {"numerator": 24, "denominator": 1},
        "frameCount": 24,
        "pixelFormat": "yuv420p",
        "colorMetadata": {
            "colorPrimaries": "BT709",
            "colorTransfer": "BT709",
            "colorSpace": "BT709",
            "colorRange": "TV",
        },
        "audioCodec": "aac",
        "audioSampleRate": 48_000,
        "audioChannels": 2,
        "audioSampleCount": 48_000,
        "duration": {"samples": 48_000, "sampleRate": 48_000},
    }


def _candidate_chain() -> tuple[dict, dict, dict, dict]:
    runtime = build_render_runtime_evidence(
        {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "runtimeEvidenceRef": "runtime-1",
            "executionRequestRef": "execution-1",
            "executionRequestDigest": DIGEST,
            "rendererIdentity": "v3-deterministic-render-core",
            "rendererVersion": "1",
            "ffmpegBinaryDigest": DIGEST,
            "ffprobeBinaryDigest": DIGEST,
            "gpuUsed": False,
            "providerUsed": False,
            "publicationAllowed": False,
            "createdAt": CREATED_AT,
        }
    )
    artifact = build_render_artifact_evidence(
        {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "artifactEvidenceRef": "artifact-1",
            "executionRequestRef": "execution-1",
            "executionRequestDigest": DIGEST,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": DIGEST,
            "runtimeEvidenceRef": "runtime-1",
            "runtimeEvidenceDigest": runtime["payloadDigest"],
            "storageBindingRef": "binding-1",
            "mediaType": "video/mp4",
            "byteSize": 1024,
            "fileDigest": DIGEST,
            "decodedFramePixelDigest": DIGEST,
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
            "pcmContentDigest": DIGEST,
            "pcmContentDigestSpec": PCM_CONTENT_DIGEST_SPEC,
            "subtitleTimingDigest": DIGEST,
            "subtitleTimingDigestSpec": SUBTITLE_TIMING_DIGEST_SPEC,
            "mediaProbe": _media_probe(),
            "subtitleSidecar": {
                "mediaType": "text/vtt",
                "byteSize": 64,
                "fileDigest": DIGEST,
                "storageBindingRef": "binding-1-subtitle",
            },
            "publicationAllowed": False,
            "createdAt": CREATED_AT,
        }
    )
    result = build_render_result(
        {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "renderResultRef": "result-1",
            "executionRequestRef": "execution-1",
            "executionRequestDigest": DIGEST,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": DIGEST,
            "runtimeEvidenceRef": "runtime-1",
            "runtimeEvidenceDigest": runtime["payloadDigest"],
            "artifactEvidenceRef": "artifact-1",
            "artifactEvidenceDigest": artifact["payloadDigest"],
            "state": "SUCCEEDED",
            "publicationAllowed": False,
            "createdAt": CREATED_AT,
        }
    )
    candidate = build_render_candidate(
        {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "projectRef": "project-1",
            "seriesRef": "series-1",
            "episodeRef": "episode-1",
            "renderCandidateRef": "candidate-1",
            "timelineVersionRef": "timeline-version-1",
            "timelineVersionDigest": DIGEST,
            "compositionVersionRef": "composition-version-1",
            "compositionVersionDigest": DIGEST,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": DIGEST,
            "executionRequestRef": "execution-1",
            "executionRequestDigest": DIGEST,
            "runtimeEvidenceRef": "runtime-1",
            "runtimeEvidenceDigest": runtime["payloadDigest"],
            "artifactEvidenceRef": "artifact-1",
            "artifactEvidenceDigest": artifact["payloadDigest"],
            "renderResultRef": "result-1",
            "renderResultDigest": result["payloadDigest"],
            "renderProfileRef": "profile-1",
            "storageBindingRef": "binding-1",
            "mediaType": "video/mp4",
            "fileDigest": DIGEST,
            "byteSize": 1024,
            "decodedFramePixelDigest": DIGEST,
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
            "pcmContentDigest": DIGEST,
            "pcmContentDigestSpec": PCM_CONTENT_DIGEST_SPEC,
            "subtitleTimingDigest": DIGEST,
            "subtitleTimingDigestSpec": SUBTITLE_TIMING_DIGEST_SPEC,
            "mediaProbe": _media_probe(),
            "rendererIdentity": "v3-deterministic-render-core",
            "rendererVersion": "1",
            "ffmpegBinaryDigest": DIGEST,
            "ffprobeBinaryDigest": DIGEST,
            "state": "RENDERED_CANDIDATE",
            "technicalValidationState": "PASS",
            "qcState": "NOT_RUN",
            "approvalState": "NOT_REQUESTED",
            "assetAdmissionState": "NOT_ADMITTED",
            "masterState": "NOT_CREATED",
            "exportState": "NOT_CREATED",
            "publicationAllowed": False,
            "createdAt": CREATED_AT,
        }
    )
    return runtime, artifact, result, candidate


def _v4_profile() -> dict:
    return {
        "outputProfile": {"profileRef": "profile-1"},
        "videoEncoding": {"codec": "H264"},
        "colorMetadata": {"colorPrimaries": "BT709"},
        "audioEncoding": {"codec": "AAC"},
        "subtitleMode": "SIDECAR",
        "subtitleTimingDigest": DIGEST,
        "subtitleFontAssetVersionRef": None,
        "subtitleFontAssetVersionDigest": None,
        "rendererIdentity": "v3-deterministic-render-core",
        "rendererVersion": "1",
        "ffmpegBinaryDigest": DIGEST,
        "ffprobeBinaryDigest": DIGEST,
    }


def _v3_command() -> dict:
    return {
        "executionRequestRef": "execution-1",
        "executionRequestDigest": DIGEST,
        "workspaceRef": "workspace-1",
        "productionRunRef": "run-1",
        "outputArtifactBindingRef": "binding-1",
        "sourceArtifact": {
            "storageKey": "inputs/preview.mp4",
            "byteSize": 1024,
            "fileDigest": f"sha256:{DIGEST}",
            "decodedFramePixelDigest": f"sha256:{DIGEST}",
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
            "pcmContentDigest": f"sha256:{DIGEST}",
            "pcmContentDigestSpec": PCM_CONTENT_DIGEST_SPEC,
            "mediaProbe": {
                "container": "mp4",
                "videoCodec": "h264",
                "pixelFormat": "yuv420p",
                "width": 64,
                "height": 64,
                "frameRate": {"numerator": 24, "denominator": 1},
                "frameCount": 24,
                "audioCodec": "aac",
                "sampleRate": 48_000,
                "channelCount": 2,
                "sampleCount": 48_000,
            },
        },
        "videoCompositionPlan": build_video_composition_plan(
            {
                "canvasWidth": 64,
                "canvasHeight": 64,
                "frameRate": {"numerator": 24, "denominator": 1},
                "totalFrames": 24,
                "maskLayerPlanDigest": DIGEST,
                "clips": [
                    {
                        "clipRef": "clip-video-1",
                        "clipDigest": DIGEST,
                        "timelineStartFrameInclusive": 0,
                        "timelineEndFrameExclusive": 24,
                        "sourceInFrameInclusive": 0,
                        "sourceOutFrameExclusive": 24,
                        "layer": 0,
                        "zOrder": 0,
                        "opacity": 1000,
                        "blendMode": "NORMAL",
                        "transitionIn": None,
                        "transitionOut": None,
                        "speed": {"numerator": 1, "denominator": 1},
                        "transform": {
                            "positionXPixels": 0,
                            "positionYPixels": 0,
                            "scaleX": {"numerator": 1, "denominator": 1},
                            "scaleY": {"numerator": 1, "denominator": 1},
                            "rotationMilliDegrees": 0,
                            "anchorXPixels": 0,
                            "anchorYPixels": 0,
                            "opacity": 1000,
                        },
                        "maskBindingDigests": [],
                    }
                ],
            }
        ),
        "renderProfile": {
            "outputProfile": {
                "profileRef": "profile-1",
                "width": 64,
                "height": 64,
                "frameRateNumerator": 24,
                "frameRateDenominator": 1,
                "pixelAspectRatioNumerator": 1,
                "pixelAspectRatioDenominator": 1,
                "resizeMode": "EXACT",
                "backgroundPolicy": "BLACK",
                "safeArea": {
                    "leftPixels": 0,
                    "topPixels": 0,
                    "rightPixels": 0,
                    "bottomPixels": 0,
                },
            },
            "videoEncoding": {
                "codec": "H264",
                "pixelFormat": "YUV420P",
                "qualityMode": "CRF",
                "qualityValue": 18,
                "profile": "HIGH",
                "level": "4.1",
                "gopFrames": 24,
                "deterministicThreadPolicy": "SINGLE_THREAD",
            },
            "colorMetadata": {
                "colorPrimaries": "BT709",
                "colorTransfer": "BT709",
                "colorSpace": "BT709",
                "colorRange": "TV",
            },
            "audioEncoding": {
                "enabled": True,
                "codec": "AAC",
                "sampleRate": 48_000,
                "channelCount": 2,
                "bitrate": 128_000,
            },
            "subtitleMode": "NONE",
            "subtitleTimingDigest": None,
            "rendererIdentity": "v3-deterministic-render-core",
            "rendererVersion": "1",
            "ffmpegBinaryDigest": DIGEST,
            "ffprobeBinaryDigest": DIGEST,
        },
        "subtitleCues": [],
        "subtitleFont": None,
        "publicationAllowed": False,
    }


class M13R1BRenderCandidateContractTests(unittest.TestCase):
    def test_candidate_chain_is_closed_immutable_and_non_publishing(self) -> None:
        _, _, _, candidate = _candidate_chain()
        wrapper = validate_render_candidate(candidate)
        detached = wrapper.as_dict()
        detached["state"] = "MASTER_READY"
        self.assertEqual(wrapper.as_dict(), candidate)
        for field in (
            "publicationAllowed",
            "masterState",
            "exportState",
            "assetAdmissionState",
            "qcState",
            "approvalState",
        ):
            self.assertIn(field, candidate)

    def test_candidate_rejects_master_export_approval_and_admission_claims(self) -> None:
        _, _, _, candidate = _candidate_chain()
        mutations = {
            "publicationAllowed": True,
            "masterState": "CREATED",
            "exportState": "CREATED",
            "assetAdmissionState": "ADMITTED",
            "qcState": "PASS",
            "approvalState": "APPROVED",
        }
        for field, value in mutations.items():
            changed = deepcopy(candidate)
            changed[field] = value
            changed.pop("payloadDigest")
            changed["payloadDigest"] = sha256(
                json.dumps(
                    changed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            with self.subTest(field=field), self.assertRaises(
                RenderDomainContractError
            ):
                validate_render_candidate(changed)

    def test_candidate_rejects_open_or_inconsistent_media_probe(self) -> None:
        _, _, _, candidate = _candidate_chain()
        for mutation in ("extra", "duration"):
            changed = deepcopy(candidate)
            if mutation == "extra":
                changed["mediaProbe"]["frameRate"]["floatRate"] = 24.0
            else:
                changed["mediaProbe"]["duration"]["samples"] += 1
            changed.pop("payloadDigest")
            changed["payloadDigest"] = sha256(
                json.dumps(
                    changed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            with self.subTest(mutation=mutation), self.assertRaises(
                RenderDomainContractError
            ):
                validate_render_candidate(changed)

    def test_v4_request_is_sealed_path_free_and_cpu_only(self) -> None:
        profile = _v4_profile()
        request = build_render_execution_request(
            {
                "workspaceRef": "workspace-1",
                "productionRunRef": "run-1",
                "executionRequestRef": "execution-1",
                "timelineVersionRef": "timeline-version-1",
                "timelineVersionDigest": DIGEST,
                "compositionVersionRef": "composition-version-1",
                "compositionVersionDigest": DIGEST,
                "renderManifestRef": "manifest-1",
                "renderManifestDigest": DIGEST,
                "allInputBindingsDigest": DIGEST,
                "compositionCommandDigest": DIGEST,
                "runtimeBindingDigest": runtime_binding_digest(profile),
                "outputArtifactBindingRef": "binding-1",
                "renderProfile": profile,
                "publicationAllowed": False,
            }
        )
        rendered = str(request).lower()
        for forbidden in ("storagekey", "absolutepath", "filter", "argv", "shellcommand"):
            self.assertNotIn(forbidden, rendered)
        changed = deepcopy(request)
        changed["outputPath"] = "/tmp/out.mp4"
        with self.assertRaises(RenderExecutionRequestError):
            build_render_execution_request(changed)

    def test_v4_request_rejects_runtime_binding_drift(self) -> None:
        profile = _v4_profile()
        command = {
            "workspaceRef": "workspace-1",
            "productionRunRef": "run-1",
            "executionRequestRef": "execution-1",
            "timelineVersionRef": "timeline-version-1",
            "timelineVersionDigest": DIGEST,
            "compositionVersionRef": "composition-version-1",
            "compositionVersionDigest": DIGEST,
            "renderManifestRef": "manifest-1",
            "renderManifestDigest": DIGEST,
            "allInputBindingsDigest": DIGEST,
            "compositionCommandDigest": DIGEST,
            "runtimeBindingDigest": runtime_binding_digest(profile),
            "outputArtifactBindingRef": "binding-1",
            "renderProfile": profile,
            "publicationAllowed": False,
        }
        command["renderProfile"]["ffmpegBinaryDigest"] = "b" * 64
        with self.assertRaises(RenderExecutionRequestError):
            build_render_execution_request(command)

    def test_v3_request_rejects_unsupported_output_profile(self) -> None:
        command = _v3_command()
        command["renderProfile"]["outputProfile"]["resizeMode"] = "FREEFORM"
        with self.assertRaises(RenderArtifactError):
            build_render_core_request(command)

    def test_v3_request_is_closed_cpu_only_and_non_publishing(self) -> None:
        request = build_render_core_request(_v3_command())
        self.assertFalse(request["publicationAllowed"])
        self.assertEqual(
            request["renderProfile"]["videoEncoding"][
                "deterministicThreadPolicy"
            ],
            "SINGLE_THREAD",
        )

    def test_v3_request_rejects_frame_count_duration_mismatch(self) -> None:
        command = _v3_command()
        command["sourceArtifact"]["mediaProbe"]["frameCount"] = 25
        with self.assertRaises(RenderArtifactError):
            build_render_core_request(command)

    def test_v3_request_rejects_audio_sample_rate_mismatch(self) -> None:
        command = _v3_command()
        command["sourceArtifact"]["mediaProbe"]["sampleRate"] = 44_100
        with self.assertRaises(RenderArtifactError):
            build_render_core_request(command)

    def test_v3_request_rejects_subtitle_timing_digest_mismatch(self) -> None:
        command = _v3_command()
        text = "subtitle"
        command["renderProfile"]["subtitleMode"] = "SIDECAR"
        command["renderProfile"]["subtitleTimingDigest"] = DIGEST
        command["subtitleCues"] = [
            {
                "cueRef": "cue-1",
                "clipRef": "clip-1",
                "timelineStartFrameInclusive": 0,
                "timelineEndFrameExclusive": 12,
                "text": text,
                "textDigest": sha256(text.encode()).hexdigest(),
                "language": "en",
                "wordTiming": [],
            }
        ]
        with self.assertRaises(RenderArtifactError):
            build_render_core_request(command)

    def test_v3_request_rejects_output_escape_and_open_probe(self) -> None:
        for mutation in ("escape", "open-probe"):
            command = _v3_command()
            if mutation == "escape":
                command["outputArtifactBindingRef"] = "../escape"
            else:
                command["sourceArtifact"]["mediaProbe"]["path"] = "/private"
            with self.subTest(mutation=mutation), self.assertRaises(
                RenderArtifactError
            ):
                build_render_core_request(command)

    def test_subtitle_timing_digest_binds_text_and_frame_ranges(self) -> None:
        text = "hello"
        cue = {
            "cueRef": "cue-1",
            "clipRef": "clip-1",
            "timelineStartFrameInclusive": 2,
            "timelineEndFrameExclusive": 20,
            "text": text,
            "textDigest": sha256(text.encode()).hexdigest(),
            "language": "en",
            "wordTiming": [],
        }
        first = canonical_subtitle_timing_digest([cue])
        shifted = deepcopy(cue)
        shifted["timelineStartFrameInclusive"] = 3
        self.assertNotEqual(first, canonical_subtitle_timing_digest([shifted]))
        stale = deepcopy(cue)
        stale["text"] = "changed"
        with self.assertRaises(RenderDomainStaleInputError):
            canonical_subtitle_timing_digest([stale])


if __name__ == "__main__":
    unittest.main()
