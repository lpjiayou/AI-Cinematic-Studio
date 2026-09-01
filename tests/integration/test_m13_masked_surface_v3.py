from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

from services.v3_render_core.composition import (
    DeterministicFfmpegComposer,
    RenderArtifactError,
)
from services.v3_render_core.digests import (
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    file_sha256,
    image_digest_metadata,
)
from services.v3_render_core.masked_surface import (
    DeterministicMaskedSurfaceExecutor,
    MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
    MASKED_SURFACE_RENDERER_IDENTITY,
    MASKED_SURFACE_RENDERER_VERSION_CURRENT,
    MASKED_SURFACE_RENDERER_VERSION_V1,
    MASKED_SURFACE_RENDERER_VERSION_V2,
    _filter_graph,
    _filter_graph_v1,
    _masked_surface_roi,
    _masked_surface_v2_workload,
)


FRAME_RATE = 6
FRAME_COUNT = 12
WIDTH = 64
HEIGHT = 48


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return result


def _media_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def _rgba_frames(
    root: Path,
    *,
    request: dict[str, Any] | None = None,
    legacy: bool = False,
) -> bytes:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-xerror",
        "-nostdin",
        "-threads",
        "1",
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
        "-sws_flags",
        "bitexact+accurate_rnd+full_chroma_int",
        "-hwaccel",
        "none",
        "-noautorotate",
        "-i",
        str(root / "inputs/base.mp4"),
    ]
    if request is not None:
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(FRAME_RATE),
                "-i",
                str(root / "inputs/mask.png"),
                "-filter_complex",
                (_filter_graph_v1 if legacy else _filter_graph)(request),
                "-map",
                "[vout]",
            ]
        )
    command.extend(
        [
            "-frames:v",
            str(FRAME_COUNT),
            "-pix_fmt",
            "rgba",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    )
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=60,
    ).stdout


def _stage_inputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    input_root = root / "inputs"
    input_root.mkdir(parents=True)
    base_path = input_root / "base.mp4"
    mask_path = input_root / "mask.png"
    _media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FRAME_RATE}",
            "-frames:v",
            str(FRAME_COUNT),
            "-c:v",
            "libx264",
            "-crf",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-x264-params",
            (
                "threads=1:lookahead_threads=1:sliced_threads=0:"
                "sync-lookahead=0:rc-lookahead=0:scenecut=0"
            ),
            "-y",
            str(base_path),
        ]
    )
    _media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "color=black:size=16x12",
            "-vf",
            "drawbox=x=2:y=2:w=12:h=8:color=white:t=fill",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-threads:v",
            "1",
            "-y",
            str(mask_path),
        ]
    )
    base_digest = decoded_frame_pixel_digest_metadata(base_path)
    mask_digest = image_digest_metadata(mask_path)
    return (
        {
            "assetVersionRef": "asset-version:base",
            "assetVersionDigest": "4" * 64,
            "storageKey": "inputs/base.mp4",
            "fileDigest": file_digest(base_path),
            "pixelDigest": base_digest["decodedFramePixelDigest"],
            "pixelDigestSpec": base_digest["decodedFramePixelDigestSpec"],
            "width": WIDTH,
            "height": HEIGHT,
            "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE,
            "pixelFormat": "yuv420p",
        },
        {
            "assetVersionRef": "asset-version:mask",
            "assetVersionDigest": "5" * 64,
            "storageKey": "inputs/mask.png",
            "fileDigest": file_digest(mask_path),
            "pixelDigest": mask_digest["pixel_digest"],
            "pixelDigestSpec": mask_digest["pixel_digest_spec"],
            "pixelMode": mask_digest["pixel_mode"],
            "width": 16,
            "height": 12,
        },
    )


def _request(
    base: dict[str, Any],
    mask: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    schema = (
        "v5.m13-local-exposure-requirement.v1"
        if mode == "LOCAL_EXPOSURE"
        else "v5.m13-scratch-light-requirement.v1"
    )
    blend = {
        "SCRATCH_REVEAL": "SCREEN",
        "LIGHT_SWEEP": "ADD",
        "LOCAL_EXPOSURE": "NORMAL",
    }[mode]
    return _seal(
        {
            "schemaVersion": MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": f"m13-execution:{mode.lower()}",
            "v5ExecutionRequestDigest": "1" * 64,
            "workspaceRef": "workspace:m13-v3",
            "productionRunRef": "run:m13-v3",
            "requirementSchemaVersion": schema,
            "requirementRef": f"requirement:{mode.lower()}",
            "requirementDigest": "2" * 64,
            "effectMode": mode,
            "targetShot": {
                "shotRef": "shot:001",
                "shotVersionRef": "shot-version:001:v1",
                "shotVersionDigest": "3" * 64,
            },
            "basePlate": base,
            "mask": mask,
            "frameRangeStartInclusive": 2,
            "frameRangeEndExclusive": 10,
            "explicitSchedule": [
                {
                    "startFrameInclusive": 2,
                    "endFrameExclusive": 5,
                    "enabled": True,
                    "interpolation": "STEP",
                },
                {
                    "startFrameInclusive": 5,
                    "endFrameExclusive": 7,
                    "enabled": False,
                    "interpolation": "STEP",
                },
                {
                    "startFrameInclusive": 7,
                    "endFrameExclusive": 10,
                    "enabled": True,
                    "interpolation": "STEP",
                },
            ],
            "trajectoryKeyframes": [
                {
                    "frame": 2,
                    "xPermille": 100,
                    "yPermille": 100,
                    "interpolation": "EASE_IN_OUT",
                },
                {
                    "frame": 9,
                    "xPermille": 500,
                    "yPermille": 500,
                    "interpolation": "STEP",
                },
            ],
            "intensityCurve": [
                {"frame": 2, "valuePermille": 200, "interpolation": "LINEAR"},
                {"frame": 9, "valuePermille": 900, "interpolation": "STEP"},
            ],
            "exposureCurve": [
                {
                    "frame": 2,
                    "valueMilliStops": 250,
                    "interpolation": "EASE_OUT",
                },
                {
                    "frame": 9,
                    "valueMilliStops": 1000,
                    "interpolation": "STEP",
                },
            ],
            "position": {"xPermille": 100, "yPermille": 100},
            "scale": {"xPermille": 250, "yPermille": 250},
            "perspective": {"mode": "NONE", "quadPermille": []},
            "blendMode": blend,
            "layer": 10,
            "output": {
                "width": WIDTH,
                "height": HEIGHT,
                "frameCount": FRAME_COUNT,
                "frameRate": FRAME_RATE,
                "pixelFormat": "yuv420p",
                "container": "mp4",
                "videoCodec": "h264",
            },
            "publicationAllowed": False,
        }
    )


def _glyph_request(base: dict[str, Any], mask: dict[str, Any]) -> dict[str, Any]:
    requirement_ref = "requirement:glyph-preview"
    requirement_digest = "a" * 64
    inspection_digest = "b" * 64
    manifest_digest = "sha256:" + "c" * 64
    glyph_mask = {
        **mask,
        "glyphSlug": "test-glyph",
        "revealOrdinal": 1,
        "assetRole": "GLYPH_REVEAL_CUMULATIVE_MASK",
        "glyphManifestDigest": manifest_digest,
    }
    input_bindings = {
        "basePlate": {
            "assetVersionRef": base["assetVersionRef"],
            "assetVersionDigest": base["assetVersionDigest"],
            "fileDigest": base["fileDigest"],
        },
        "masks": [
            {
                field: glyph_mask[field]
                for field in (
                    "assetVersionRef",
                    "assetVersionDigest",
                    "fileDigest",
                    "pixelDigest",
                    "pixelDigestSpec",
                    "pixelMode",
                    "width",
                    "height",
                    "glyphSlug",
                    "revealOrdinal",
                    "assetRole",
                    "glyphManifestDigest",
                )
            }
        ],
        "basePlateInspection": {
            "inspectionRef": "inspection:glyph-base",
            "inspectionDigest": inspection_digest,
        },
    }
    input_digest = sha256(_canonical_json(input_bindings)).hexdigest()
    execution_ref = "m13-glyph-reveal-execution-" + sha256(
        _canonical_json(
            {
                "requirementRef": requirement_ref,
                "requirementDigest": requirement_digest,
                "inputBindingsDigest": input_digest,
                "basePlateInspectionDigest": inspection_digest,
            }
        )
    ).hexdigest()[:32]
    return _seal(
        {
            "schemaVersion": "v5.m13-glyph-reveal-execution-request.v2",
            "executionRequestRef": execution_ref,
            "workspaceRef": "workspace:m13-v3",
            "productionRunRef": "run:m13-v3",
            "requirementRef": requirement_ref,
            "requirementDigest": requirement_digest,
            "glyphSlug": "test-glyph",
            "targetShotRef": "shot:001",
            "frameRangeStartInclusive": 2,
            "frameRangeEndExclusive": 10,
            "revealSchedule": [
                {
                    "revealOrdinal": 1,
                    "maskAssetVersionRef": mask["assetVersionRef"],
                    "startFrameInclusive": 2,
                    "endFrameExclusive": 10,
                }
            ],
            "inputBindingsDigest": input_digest,
            "basePlate": {
                field: base[field]
                for field in (
                    "assetVersionRef",
                    "assetVersionDigest",
                    "storageKey",
                    "fileDigest",
                )
            },
            "masks": [glyph_mask],
            "basePlateInspectionRef": "inspection:glyph-base",
            "basePlateInspectionDigest": inspection_digest,
            "compositeParams": {
                "position": {"xPixels": 0, "yPixels": 0},
                "scale": {"widthPixels": 16, "heightPixels": 12},
                "perspective": {
                    "topLeft": [0, 0],
                    "topRight": [15, 0],
                    "bottomLeft": [0, 11],
                    "bottomRight": [15, 11],
                },
                "blendMode": "GRAZING_LIGHT_RELIEF",
            },
            "output": {
                "width": WIDTH,
                "height": HEIGHT,
                "frameRate": FRAME_RATE,
                "totalFrames": FRAME_COUNT,
            },
            "publicationAllowed": False,
        }
    )


def _stage_audio(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    audio_path = root / "inputs" / "audio.wav"
    duration_samples = FRAME_COUNT * 48_000 // FRAME_RATE
    _media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            str(FRAME_COUNT / FRAME_RATE),
            "-c:a",
            "pcm_s16le",
            "-y",
            str(audio_path),
        ]
    )
    pcm = canonical_pcm_digest_metadata(
        audio_path, expected_sample_count=duration_samples
    )
    from services.v3_render_core.composition import (
        _TIMELINE_PREVIEW_DUCKING,
        _TIMELINE_PREVIEW_LIMITER,
        _TIMELINE_PREVIEW_ROLE_GAIN_DB,
        _TIMELINE_PREVIEW_ROLE_PRIORITY,
    )

    parameters = {
        "rolePriority": _TIMELINE_PREVIEW_ROLE_PRIORITY,
        "roleGainDb": _TIMELINE_PREVIEW_ROLE_GAIN_DB,
        "ducking": _TIMELINE_PREVIEW_DUCKING,
        "limiter": _TIMELINE_PREVIEW_LIMITER,
    }
    audio_mix = {
        "mixRequestRef": "mix-request:preview-v2",
        "mixRequestDigest": "d" * 64,
        "timelineVersionRef": "timeline-version:preview-v2",
        "timelineVersionDigest": "e" * 64,
        "stemSetVersionRef": "stem-set:preview-v2",
        "stemSetDigest": "f" * 64,
        "sampleRate": 48_000,
        "channelCount": 2,
        "durationSamples": duration_samples,
        "roundingRule": "FLOOR_EACH_BOUNDARY",
        "mixParameters": parameters,
        "mixParametersDigest": sha256(_canonical_json(parameters)).hexdigest(),
        "clips": [
            {
                "clipRef": "audio-clip:preview-v2",
                "clipDigest": "1" * 64,
                "stemMemberRef": "stem-member:preview-v2",
                "stemMemberDigest": "2" * 64,
                "audioRole": "narration",
                "assetVersionRef": "asset-version:audio",
                "assetVersionType": "DialogueAssetVersion",
                "assetVersionDigest": "3" * 64,
                "technicalValidationRef": "audio-validation:preview-v2",
                "technicalValidationDigest": "4" * 64,
                "storageKey": "inputs/audio.wav",
                "fileDigest": file_sha256(audio_path),
                "pcmContentDigest": pcm["pcmContentDigest"],
                "sampleRate": 48_000,
                "sourceChannelCount": 2,
                "sourceSampleCount": duration_samples,
                "sourceStartSample": 0,
                "sourceEndSampleExclusive": duration_samples,
                "timelineStartFrame": 0,
                "timelineEndFrameExclusive": FRAME_COUNT,
                "timelineStartSample": 0,
                "timelineEndSampleExclusive": duration_samples,
                "gainDb": 0,
                "fadeInSamples": 0,
                "fadeOutSamples": 0,
            }
        ],
    }
    output = {
        "width": WIDTH,
        "height": HEIGHT,
        "frameRate": {"numerator": FRAME_RATE, "denominator": 1},
        "totalFrames": FRAME_COUNT,
        "sampleRate": 48_000,
        "channelCount": 2,
        "durationSamples": duration_samples,
        "container": "mp4",
        "videoCodec": "h264",
        "pixelFormat": "yuv420p",
        "audioCodec": "aac",
        "audioBitRate": 128_000,
    }
    return audio_mix, output


def _effect_binding(stage: dict[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "clipRef": f"effect-clip:{index}",
        "clipDigest": f"{index + 1:x}" * 64,
        "effectMode": stage["effectMode"],
        "requirementRef": stage["requirementRef"],
        "requirementDigest": stage["requirementDigest"],
        "resultRef": f"effect-result:{index}",
        "resultDigest": f"{index + 3:x}" * 64,
        "executionRequestRef": stage["v5ExecutionRequestRef"],
        "executionRequestDigest": stage["v5ExecutionRequestDigest"],
        "artifactEvidenceRef": f"artifact-evidence:{index}",
        "artifactEvidenceDigest": f"{index + 5:x}" * 64,
        "runtimeEvidenceRef": f"runtime-evidence:{index}",
        "runtimeEvidenceDigest": f"{index + 7:x}" * 64,
        "frameRangeStartInclusive": stage["frameRangeStartInclusive"],
        "frameRangeEndExclusive": stage["frameRangeEndExclusive"],
    }


def _combined_request(
    base: dict[str, Any],
    mask: dict[str, Any],
    audio_mix: dict[str, Any],
    output: dict[str, Any],
) -> dict[str, Any]:
    stages = [
        _request(base, mask, mode="LIGHT_SWEEP"),
        _request(base, mask, mode="LOCAL_EXPOSURE"),
    ]
    bindings = [_effect_binding(stage, index=index) for index, stage in enumerate(stages)]
    glyph = _glyph_request(base, mask)
    glyph_binding = {
        "clipRef": "effect-clip:glyph",
        "clipDigest": "9" * 64,
        "requirementRef": glyph["requirementRef"],
        "requirementDigest": glyph["requirementDigest"],
    }
    effect_digest = sha256(
        _canonical_json(
            {
                "schemaVersion": "v5.m13-effect-preview-bindings.v1",
                "effectResultBindings": bindings,
                "glyphRequirementBinding": glyph_binding,
            }
        )
    ).hexdigest()
    subtitle = {
        "subtitleManifestRef": "subtitle-manifest:preview-v2",
        "subtitleManifestDigest": "a" * 64,
    }
    input_digest = sha256(
        _canonical_json(
            {
                "baseVideo": base,
                "maskedSurfaceRequestDigests": [stage["payloadDigest"] for stage in stages],
                "glyphRevealRequestDigest": glyph["payloadDigest"],
                "effectResultBindings": bindings,
                "glyphRequirementBinding": glyph_binding,
                "audioMix": audio_mix,
                "subtitleManifest": subtitle,
            }
        )
    ).hexdigest()
    output_digest = sha256(_canonical_json(output)).hexdigest()
    execution_ref = "m13-effect-preview-execution-" + sha256(
        _canonical_json(
            {
                "timelineVersionRef": "timeline-version:preview-v2",
                "timelineVersionDigest": "e" * 64,
                "inputBindingsDigest": input_digest,
                "effectBindingsDigest": effect_digest,
                "outputContractDigest": output_digest,
            }
        )
    ).hexdigest()[:32]
    return _seal(
        {
            "schemaVersion": "v4.m13-effect-preview-execution-request.v2",
            "executionRequestRef": execution_ref,
            "workspaceRef": "workspace:m13-v3",
            "productionRunRef": "run:m13-v3",
            "timelineVersionRef": "timeline-version:preview-v2",
            "timelineVersionDigest": "e" * 64,
            "inputBindingsDigest": input_digest,
            "effectResultBindings": bindings,
            "glyphRequirementBinding": glyph_binding,
            "effectBindingsDigest": effect_digest,
            "baseVideo": base,
            "effectStages": stages,
            "glyphStage": glyph,
            "audioMix": audio_mix,
            "subtitleManifest": subtitle,
            "output": output,
            "publicationAllowed": False,
        }
    )
@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class MaskedSurfaceV3IntegrationTests(unittest.TestCase):
    def test_combined_preview_boundary_matches_v4_exact_constants(self) -> None:
        from services.v3_render_core import masked_surface as v3
        from services.v4_platform import masked_surface_effects as v4

        self.assertEqual(
            v4.EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION,
            v3.EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION,
        )
        self.assertEqual(
            v4.EFFECT_PREVIEW_RENDERER_IDENTITY,
            v3.EFFECT_PREVIEW_RENDERER_IDENTITY,
        )
        self.assertEqual(
            set(v4._EFFECT_PREVIEW_V3_REQUEST_FIELDS),
            set(v3._EFFECT_PREVIEW_FIELDS),
        )

    def test_combined_preview_replays_fixed_effect_glyph_order_then_audio_mux(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_inputs(root)
            audio_mix, output = _stage_audio(root)
            request = _combined_request(base, mask, audio_mix, output)
            executor = DeterministicMaskedSurfaceExecutor(root)
            with patch.object(
                DeterministicFfmpegComposer,
                "compose_timeline_preview_v1",
                side_effect=AssertionError("combined Preview repinned FFmpeg"),
            ):
                result = executor.compose_timeline_preview_v2(request)
                replay = executor.compose_timeline_preview_v2(request)
            self.assertEqual(
                "v3.deterministic-timeline-preview-ffmpeg",
                result["rendererIdentity"],
            )
            self.assertEqual("2", result["rendererVersion"])
            self.assertEqual(request["effectResultBindings"], result["effectResultBindings"])
            self.assertEqual(request["effectBindingsDigest"], result["effectBindingsDigest"])
            self.assertEqual(request["payloadDigest"], result["executionRequestDigest"])
            self.assertEqual(False, result["publicationAllowed"])
            self.assertEqual(FRAME_COUNT, result["outputDigest"]["frameCount"])
            self.assertEqual(96_000, result["outputDigest"]["sampleCount"])
            self.assertEqual(result["outputDigest"], replay["outputDigest"])
            self.assertEqual(result["outputStorageKey"], replay["outputStorageKey"])

    def test_real_ffmpeg_executes_all_modes_and_exact_replay_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_inputs(root)
            executor = DeterministicMaskedSurfaceExecutor(root)
            outputs: dict[str, dict[str, Any]] = {}
            for mode in ("SCRATCH_REVEAL", "LIGHT_SWEEP", "LOCAL_EXPOSURE"):
                request = _request(base, mask, mode=mode)
                if mode == "SCRATCH_REVEAL":
                    workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
                    run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
                    legacy_path = (
                        root
                        / workspace
                        / run
                        / "masked-surface"
                        / f"masked-surface-{request['payloadDigest']}.mp4"
                    )
                    legacy_path.parent.mkdir(parents=True, exist_ok=True)
                    legacy_path.write_bytes(b"historical-v1-artifact")
                result = executor.execute(request)
                self.assertEqual(MASKED_SURFACE_RENDERER_IDENTITY, result["rendererIdentity"])
                self.assertEqual(MASKED_SURFACE_RENDERER_VERSION_CURRENT, result["rendererVersion"])
                self.assertIn(
                    f"masked-surface-v2-{request['payloadDigest']}.mp4",
                    result["outputStorageKey"],
                )
                if mode == "SCRATCH_REVEAL":
                    self.assertEqual(b"historical-v1-artifact", legacy_path.read_bytes())
                    self.assertNotEqual(
                        str(legacy_path.relative_to(root)),
                        result["outputStorageKey"],
                    )
                self.assertEqual(mode, result["effectMode"])
                self.assertEqual(False, result["publicationAllowed"])
                self.assertEqual(request["payloadDigest"], result["v3ExecutionRequestDigest"])
                self.assertEqual(
                    (WIDTH, HEIGHT, FRAME_COUNT, FRAME_RATE),
                    (
                        result["outputDigest"]["width"],
                        result["outputDigest"]["height"],
                        result["outputDigest"]["frameCount"],
                        result["outputDigest"]["frameRate"],
                    ),
                )
                outputs[mode] = result

            replay_request = _request(base, mask, mode="SCRATCH_REVEAL")
            replay = executor.execute(replay_request)
            self.assertEqual(
                outputs["SCRATCH_REVEAL"]["outputDigest"], replay["outputDigest"]
            )
            self.assertEqual(
                outputs["SCRATCH_REVEAL"]["outputStorageKey"], replay["outputStorageKey"]
            )
            self.assertNotEqual(
                base["pixelDigest"],
                outputs["SCRATCH_REVEAL"]["outputDigest"]["decodedFramePixelDigest"],
            )

    def test_v2_temporal_roi_pixels_and_v1_effect_semantics_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_inputs(root)
            request = _request(base, mask, mode="SCRATCH_REVEAL")
            profile = _masked_surface_v2_workload(request)
            self.assertEqual(((2, 5), (7, 10)), profile["activeIntervals"])
            self.assertEqual(6, profile["activeFrameCount"])
            self.assertFalse(profile["roi"]["fullFrame"])
            self.assertEqual(
                profile["activeFrameCount"]
                * profile["roi"]["width"]
                * profile["roi"]["height"],
                profile["activeRoiPixelFrames"],
            )

            graph = _filter_graph(request)
            self.assertEqual(2, graph.count("format=gbrp"))
            self.assertEqual(2, graph.count("maskedmerge"))
            self.assertEqual(2, graph.count("blend=all_mode="))
            self.assertIn("trim=start_frame=0:end_frame=2", graph)
            self.assertIn("trim=start_frame=5:end_frame=7", graph)
            self.assertIn("trim=start_frame=10:end_frame=12", graph)

            base_frames = _rgba_frames(root)
            v2_frames = _rgba_frames(root, request=request)
            frame_bytes = WIDTH * HEIGHT * 4
            active_frames = {2, 3, 4, 7, 8, 9}
            roi = _masked_surface_roi(request)
            changed_inside_roi = 0
            for frame in range(FRAME_COUNT):
                start = frame * frame_bytes
                end = start + frame_bytes
                if frame not in active_frames:
                    self.assertEqual(base_frames[start:end], v2_frames[start:end])
                    continue
                for y in range(HEIGHT):
                    row_start = start + y * WIDTH * 4
                    for x in range(WIDTH):
                        pixel_start = row_start + x * 4
                        pixel_end = pixel_start + 4
                        changed = (
                            base_frames[pixel_start:pixel_end]
                            != v2_frames[pixel_start:pixel_end]
                        )
                        inside = (
                            roi["x"] <= x < roi["x"] + roi["width"]
                            and roi["y"] <= y < roi["y"] + roi["height"]
                        )
                        if changed and inside:
                            changed_inside_roi += 1
                        if not inside:
                            self.assertFalse(changed)
            self.assertGreater(changed_inside_roi, 0)

            full_frame = deepcopy(request)
            full_frame["position"] = {"xPermille": 0, "yPermille": 0}
            full_frame["scale"] = {"xPermille": 1000, "yPermille": 1000}
            for point in full_frame["trajectoryKeyframes"]:
                point["xPermille"] = 0
                point["yPermille"] = 0
            full_frame_roi = _masked_surface_roi(full_frame)
            self.assertTrue(full_frame_roi["fullFrame"])
            self.assertEqual(
                (0, 0, WIDTH, HEIGHT),
                (
                    full_frame_roi["x"],
                    full_frame_roi["y"],
                    full_frame_roi["width"],
                    full_frame_roi["height"],
                ),
            )

            zero_intensity = deepcopy(request)
            for point in zero_intensity["intensityCurve"]:
                point["valuePermille"] = 0
            v1_active = _rgba_frames(root, request=request, legacy=True)
            v1_control = _rgba_frames(root, request=zero_intensity, legacy=True)
            v2_control = _rgba_frames(root, request=zero_intensity)
            self.assertTrue(
                all(
                    active - control == current - current_control
                    for active, control, current, current_control in zip(
                        v1_active,
                        v1_control,
                        v2_frames,
                        v2_control,
                        strict=True,
                    )
                )
            )
            self.assertEqual(
                {MASKED_SURFACE_RENDERER_VERSION_V1, MASKED_SURFACE_RENDERER_VERSION_V2},
                {"1", MASKED_SURFACE_RENDERER_VERSION_CURRENT},
            )

    def test_v2_fixed_workload_budgets_reject_before_ffmpeg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_inputs(root)
            request = _request(base, mask, mode="SCRATCH_REVEAL")
            frame_count = 30_000
            request["basePlate"]["frameCount"] = frame_count
            request["output"]["frameCount"] = frame_count
            request["frameRangeStartInclusive"] = 0
            request["frameRangeEndExclusive"] = frame_count
            request["explicitSchedule"] = [
                {
                    "startFrameInclusive": 0,
                    "endFrameExclusive": frame_count,
                    "enabled": True,
                    "interpolation": "STEP",
                }
            ]
            request["trajectoryKeyframes"] = [
                {
                    "frame": 0,
                    "xPermille": 0,
                    "yPermille": 0,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": frame_count - 1,
                    "xPermille": 0,
                    "yPermille": 0,
                    "interpolation": "STEP",
                },
            ]
            request["intensityCurve"] = [
                {"frame": 0, "valuePermille": 1000, "interpolation": "LINEAR"},
                {
                    "frame": frame_count - 1,
                    "valuePermille": 1000,
                    "interpolation": "STEP",
                },
            ]
            request["exposureCurve"] = [
                {"frame": 0, "valueMilliStops": 0, "interpolation": "LINEAR"},
                {
                    "frame": frame_count - 1,
                    "valueMilliStops": 0,
                    "interpolation": "STEP",
                },
            ]
            request["position"] = {"xPermille": 0, "yPermille": 0}
            request["scale"] = {"xPermille": 1000, "yPermille": 1000}
            request = _seal(
                {key: value for key, value in request.items() if key != "payloadDigest"}
            )
            with patch("services.v3_render_core.masked_surface.subprocess.run") as run:
                with self.assertRaisesRegex(
                    RenderArtifactError,
                    "active ROI pixel-frame budget exceeded",
                ):
                    DeterministicMaskedSurfaceExecutor(root).execute(request)
                run.assert_not_called()

    def test_closed_request_rejects_caller_filter_and_out_of_bounds_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_inputs(root)
            executor = DeterministicMaskedSurfaceExecutor(root)
            request = _request(base, mask, mode="LIGHT_SWEEP")
            request["filter"] = "movie=/etc/passwd"
            with self.assertRaises(RenderArtifactError):
                executor.execute(request)

            request = _request(base, mask, mode="LIGHT_SWEEP")
            request["trajectoryKeyframes"][-1]["xPermille"] = 900
            request.pop("payloadDigest")
            request = _seal(request)
            with self.assertRaises(RenderArtifactError):
                executor.execute(request)


if __name__ == "__main__":
    unittest.main()
