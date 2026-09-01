from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from services.v3_render_core import (
    PCM_CONTENT_DIGEST_SPEC,
    RenderArtifactError,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
    file_sha256,
)
from services.v3_render_core.render_candidate import (
    DeterministicRenderCandidateExecutor,
    RENDERER_IDENTITY,
    RENDERER_VERSION,
    build_render_core_request,
    build_video_composition_plan,
    render_candidate_storage_key,
)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13R1BRenderCandidateV3SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "inputs" / "source.mp4"
        source.parent.mkdir(mode=0o700)
        subprocess.run(
            [
                str(shutil.which("ffmpeg")),
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=0x204060:s=64x64:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000:duration=1",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-frames:v",
                "24",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-threads:v",
                "1",
                "-c:a",
                "aac",
                "-b:a",
                "128000",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-metadata",
                "creation_time=1970-01-01T00:00:00Z",
                "-y",
                str(source),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        pixels = decoded_frame_pixel_digest_metadata(source)
        pcm = canonical_pcm_digest_metadata(
            source,
            expected_sample_count=48_000,
            allow_aac_frame_padding=True,
        )
        self.source = source
        self.command = {
            "executionRequestRef": "execution-security-1",
            "executionRequestDigest": "a" * 64,
            "workspaceRef": "workspace-security-1",
            "productionRunRef": "run-security-1",
            "outputArtifactBindingRef": "binding-security-1",
            "sourceArtifact": {
                "storageKey": str(source.relative_to(self.root)),
                "byteSize": source.stat().st_size,
                "fileDigest": pixels["fileDigest"],
                "decodedFramePixelDigest": pixels[
                    "decodedFramePixelDigest"
                ],
                "decodedFramePixelDigestSpec": pixels[
                    "decodedFramePixelDigestSpec"
                ],
                "pcmContentDigest": pcm["pcmContentDigest"],
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
                    "maskLayerPlanDigest": "b" * 64,
                    "clips": [
                        {
                            "clipRef": "clip-security-1",
                            "clipDigest": "c" * 64,
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
                                "scaleX": {
                                    "numerator": 1,
                                    "denominator": 1,
                                },
                                "scaleY": {
                                    "numerator": 1,
                                    "denominator": 1,
                                },
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
                    "profileRef": "profile-security-1",
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
                "rendererIdentity": RENDERER_IDENTITY,
                "rendererVersion": RENDERER_VERSION,
                "ffmpegBinaryDigest": file_sha256(
                    Path(str(shutil.which("ffmpeg"))).resolve()
                ),
                "ffprobeBinaryDigest": file_sha256(
                    Path(str(shutil.which("ffprobe"))).resolve()
                ),
            },
            "subtitleCues": [],
            "subtitleFont": None,
            "publicationAllowed": False,
        }
        self.executor = DeterministicRenderCandidateExecutor(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _expected(result: dict) -> dict:
        return {
            "byteSize": result["outputByteSize"],
            "mediaType": "video/mp4",
            "mediaProbe": result["outputMediaProbe"],
            "fileDigest": result["fileDigest"],
            "decodedFramePixelDigest": result["decodedFramePixelDigest"],
            "decodedFramePixelDigestSpec": result[
                "decodedFramePixelDigestSpec"
            ],
            "pcmContentDigest": result["pcmContentDigest"],
            "pcmContentDigestSpec": result["pcmContentDigestSpec"],
            "subtitleSidecar": result["subtitleSidecar"],
            "ffmpegBinaryDigest": result["ffmpegBinaryDigest"],
            "ffprobeBinaryDigest": result["ffprobeBinaryDigest"],
        }

    def test_real_render_exact_replay_reuses_identical_output(self) -> None:
        request = build_render_core_request(self.command)
        first = self.executor.render(request)
        path = Path(first["internalPath"])
        identity = (path.stat().st_dev, path.stat().st_ino)
        second = self.executor.render(request)
        self.assertEqual(first["fileDigest"], second["fileDigest"])
        self.assertEqual(identity, (path.stat().st_dev, path.stat().st_ino))

    def test_two_clips_apply_trim_move_speed_transition_transform_and_layers(self) -> None:
        command = deepcopy(self.command)
        command["executionRequestRef"] = "execution-security-two-clips"
        command["outputArtifactBindingRef"] = "binding-security-two-clips"
        identity_transform = {
            "positionXPixels": 0,
            "positionYPixels": 0,
            "scaleX": {"numerator": 1, "denominator": 1},
            "scaleY": {"numerator": 1, "denominator": 1},
            "rotationMilliDegrees": 0,
            "anchorXPixels": 0,
            "anchorYPixels": 0,
            "opacity": 1000,
        }
        transition_out = {
            "kind": "CROSSFADE",
            "durationFrames": 4,
            "curve": "LINEAR",
            "alignment": "END",
        }
        transition_in = {
            "kind": "CROSSFADE",
            "durationFrames": 4,
            "curve": "LINEAR",
            "alignment": "START",
        }
        command["videoCompositionPlan"] = build_video_composition_plan(
            {
                "canvasWidth": 64,
                "canvasHeight": 64,
                "frameRate": {"numerator": 24, "denominator": 1},
                "totalFrames": 24,
                "maskLayerPlanDigest": "d" * 64,
                "clips": [
                    {
                        "clipRef": "clip-security-fast",
                        "clipDigest": "e" * 64,
                        "timelineStartFrameInclusive": 0,
                        "timelineEndFrameExclusive": 8,
                        "sourceInFrameInclusive": 0,
                        "sourceOutFrameExclusive": 16,
                        "layer": 0,
                        "zOrder": 0,
                        "opacity": 1000,
                        "blendMode": "NORMAL",
                        "transitionIn": None,
                        "transitionOut": transition_out,
                        "speed": {"numerator": 2, "denominator": 1},
                        "transform": identity_transform,
                        "maskBindingDigests": [],
                    },
                    {
                        "clipRef": "clip-security-transformed",
                        "clipDigest": "f" * 64,
                        "timelineStartFrameInclusive": 7,
                        "timelineEndFrameExclusive": 23,
                        "sourceInFrameInclusive": 8,
                        "sourceOutFrameExclusive": 24,
                        "layer": 1,
                        "zOrder": 1,
                        "opacity": 800,
                        "blendMode": "NORMAL",
                        "transitionIn": transition_in,
                        "transitionOut": None,
                        "speed": {"numerator": 1, "denominator": 1},
                        "transform": {
                            **identity_transform,
                            "positionXPixels": 16,
                            "positionYPixels": 16,
                            "scaleX": {"numerator": 1, "denominator": 2},
                            "scaleY": {"numerator": 1, "denominator": 2},
                        },
                        "maskBindingDigests": [],
                    },
                ],
            }
        )
        result = self.executor.render(build_render_core_request(command))
        self.assertEqual(result["outputMediaProbe"]["frameCount"], 24)
        self.assertEqual(result["outputMediaProbe"]["width"], 64)
        self.assertTrue(Path(result["internalPath"]).is_file())

    def test_symlink_input_is_rejected(self) -> None:
        link = self.root / "inputs" / "source-link.mp4"
        link.symlink_to(self.source.name)
        command = deepcopy(self.command)
        command["sourceArtifact"]["storageKey"] = str(
            link.relative_to(self.root)
        )
        with self.assertRaises(RenderArtifactError):
            self.executor.render(build_render_core_request(command))

    def test_existing_different_output_is_not_overwritten(self) -> None:
        key = render_candidate_storage_key(
            self.command["workspaceRef"],
            self.command["productionRunRef"],
            self.command["outputArtifactBindingRef"],
        )
        destination = self.root / key
        destination.parent.mkdir(parents=True, mode=0o700)
        destination.write_bytes(b"existing-different-output")
        with self.assertRaises(RenderArtifactError):
            self.executor.render(build_render_core_request(self.command))
        self.assertEqual(destination.read_bytes(), b"existing-different-output")

    def test_inspection_rejects_content_probe_and_runtime_drift(self) -> None:
        result = self.executor.render(build_render_core_request(self.command))
        mutations = {
            "pixels": ("decodedFramePixelDigest", "b" * 64),
            "pcm": ("pcmContentDigest", "b" * 64),
            "runtime": ("ffmpegBinaryDigest", "b" * 64),
        }
        for label, (field, value) in mutations.items():
            expected = self._expected(result)
            expected[field] = value
            with self.subTest(label=label), self.assertRaises(
                RenderArtifactError
            ):
                self.executor.inspect(
                    workspace_ref=self.command["workspaceRef"],
                    production_run_ref=self.command["productionRunRef"],
                    storage_binding_ref=self.command[
                        "outputArtifactBindingRef"
                    ],
                    expected=expected,
                )
        expected = self._expected(result)
        expected["mediaProbe"] = deepcopy(expected["mediaProbe"])
        expected["mediaProbe"]["width"] += 2
        with self.assertRaises(RenderArtifactError):
            self.executor.inspect(
                workspace_ref=self.command["workspaceRef"],
                production_run_ref=self.command["productionRunRef"],
                storage_binding_ref=self.command["outputArtifactBindingRef"],
                expected=expected,
            )

    def test_post_publication_tamper_is_rejected(self) -> None:
        result = self.executor.render(build_render_core_request(self.command))
        with Path(result["internalPath"]).open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaises(RenderArtifactError):
            self.executor.inspect(
                workspace_ref=self.command["workspaceRef"],
                production_run_ref=self.command["productionRunRef"],
                storage_binding_ref=self.command["outputArtifactBindingRef"],
                expected=self._expected(result),
            )


if __name__ == "__main__":
    unittest.main()
