from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, BinaryIO
import unittest

from services.v3_render_core import RenderArtifactError
from services.v3_render_core.digests import (
    file_digest,
    file_sha256,
    image_digest_metadata,
    video_digest_metadata,
)
from services.v4_platform.composition import (
    GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
    CompositionExecutionError,
    CompositionRequestValidationError,
    V4CompositionExecutor,
)
from services.v5_core_os.episode_production.glyph_reveal import (
    build_glyph_reveal_composition_result,
    build_glyph_reveal_execution_request,
    build_glyph_reveal_requirement,
)
from tests.contract.test_m13_glyph_reveal_contract import (
    FIXTURE_ROOT,
    base_plate_asset,
    inspection_port,
    mask_assets,
    requirement_command,
    resealed,
    source_manifest,
)


BASE_STORAGE_KEY = "asset-versions/video/ep01/sh15-base-plate.mp4"
MASK_STORAGE_PREFIX = "asset-versions/image/zhen"
FRAME_RATE = 24
FRAME_COUNT = 49
FRAME_RANGE_START = 12
FRAME_RANGE_END = 30
REVEAL_FRAME_COUNT = 6
FRAMES_PER_STAGE = 3

# The final two frozen masks differ in only eleven native pixels. Keeping the
# 1024-square masks at native scale prevents those facts from collapsing during
# resampling; the 32-pixel border supplies a real outside-ROI invariant.
MASK_WIDTH = 1024
MASK_HEIGHT = 1024
ROI_X = 32
ROI_Y = 32
CANVAS_WIDTH = ROI_X + MASK_WIDTH + 32
CANVAS_HEIGHT = ROI_Y + MASK_HEIGHT + 32


@dataclass
class _PreparedRun:
    root: Path
    requirement: Any
    base: dict
    masks: list[dict]
    inspection_port: Any
    execution: dict
    base_bytes: bytes
    mask_paths: list[Path]


@dataclass
class _CompletedRun:
    prepared: _PreparedRun
    artifact: dict
    result: dict


@dataclass
class _FrameEvidence:
    base_digests: list[str]
    output_digests: list[str]
    outside_roi_equal: list[bool]


def _run_media_command(command: list[str], *, timeout: int = 180) -> bytes:
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        timeout=timeout,
    )
    return completed.stdout


def _generate_base_plate(path: Path) -> bytes:
    """Generate a static, spatially textured M11-like 49-frame base."""

    path.parent.mkdir(parents=True, exist_ok=True)
    texture = (
        f"nullsrc=s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:r={FRAME_RATE},"
        "geq="
        "lum='96+24*sin(2*PI*X/97)+18*cos(2*PI*Y/83)"
        "+10*sin(2*PI*(X+Y)/61)':"
        "cb='116+8*sin(2*PI*Y/127)':"
        "cr='138+8*cos(2*PI*X/149)',"
        "format=yuv420p"
    )
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            texture,
            "-frames:v",
            str(FRAME_COUNT),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
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
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-metadata",
            "creation_time=1970-01-01T00:00:00Z",
            "-movflags",
            "+faststart",
            "-video_track_timescale",
            "12288",
            "-y",
            str(path),
        ]
    )
    return path.read_bytes()


def _generate_small_base_plate(path: Path) -> bytes:
    """Generate a cheap 64-square M11-like base for rejection-only cases."""

    path.parent.mkdir(parents=True, exist_ok=True)
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            f"color=c=gray:s=64x64:r={FRAME_RATE}",
            "-frames:v",
            str(FRAME_COUNT),
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-y",
            str(path),
        ]
    )
    return path.read_bytes()


def _write_small_gray_png(
    path: Path,
    covered_pixels: set[int],
    *,
    alpha: int = 255,
) -> None:
    """Encode one 8-square semantic-gray PNG from deterministic raw bytes."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if alpha == 255:
        pixel_format = "gray"
        pixels = bytes(
            255 if index in covered_pixels else 0 for index in range(8 * 8)
        )
    else:
        pixel_format = "rgba"
        pixels = b"".join(
            bytes((value, value, value, alpha))
            for index in range(8 * 8)
            for value in (255 if index in covered_pixels else 0,)
        )
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pixel_format",
            pixel_format,
            "-video_size",
            "8x8",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-pix_fmt",
            pixel_format,
            "-y",
            str(path),
        ],
        input=pixels,
        check=True,
        capture_output=True,
        timeout=60,
    )


def _probe_video_contract(path: Path) -> tuple[dict[str, int], str]:
    probe = json.loads(
        _run_media_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    streams = probe["streams"]
    video_streams = [
        stream for stream in streams if stream.get("codec_type") == "video"
    ]
    audio_streams = [
        stream for stream in streams if stream.get("codec_type") == "audio"
    ]
    if len(video_streams) != 1 or audio_streams or len(streams) != 1:
        raise AssertionError("base plate must contain exactly one video stream")
    stream = video_streams[0]
    average_rate = Fraction(str(stream["avg_frame_rate"]))
    nominal_rate = Fraction(str(stream["r_frame_rate"]))
    frame_count = int(stream.get("nb_read_frames") or stream["nb_frames"])
    if average_rate != nominal_rate or average_rate.denominator != 1:
        raise AssertionError("base plate must use an integral constant frame rate")
    return (
        {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "frameCount": frame_count,
            "frameRate": average_rate.numerator,
        },
        str(stream["pix_fmt"]),
    )


def _probe_image_pixel_format(path: Path) -> str:
    probe = json.loads(
        _run_media_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=pix_fmt",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    return str(probe["streams"][0]["pix_fmt"])


def _native_composite_params() -> dict:
    return {
        "position": {"xPixels": ROI_X, "yPixels": ROI_Y},
        "scale": {"widthPixels": MASK_WIDTH, "heightPixels": MASK_HEIGHT},
        "perspective": {
            "topLeft": [0, 0],
            "topRight": [MASK_WIDTH - 1, 0],
            "bottomLeft": [0, MASK_HEIGHT - 1],
            "bottomRight": [MASK_WIDTH - 1, MASK_HEIGHT - 1],
        },
        "blendMode": "GRAZING_LIGHT_RELIEF",
    }


def _rgb24_png_reencode(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-pix_fmt",
            "rgb24",
            "-compression_level",
            "9",
            "-pred",
            "mixed",
            "-y",
            str(destination),
        ]
    )


def _stage_inputs(
    root: Path,
    *,
    base_bytes: bytes | None = None,
    rgb24_mask_ordinal: int | None = None,
) -> _PreparedRun:
    base_path = root / BASE_STORAGE_KEY
    if base_bytes is None:
        base_bytes = _generate_base_plate(base_path)
    else:
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_bytes(base_bytes)

    media_probe, pixel_format = _probe_video_contract(base_path)
    if media_probe != {
        "width": CANVAS_WIDTH,
        "height": CANVAS_HEIGHT,
        "frameCount": FRAME_COUNT,
        "frameRate": FRAME_RATE,
    } or pixel_format != "yuv420p":
        raise AssertionError("generated base does not match the M11 media contract")

    manifest = source_manifest()
    templates = mask_assets(storage_prefix=MASK_STORAGE_PREFIX)
    staged_masks: list[dict] = []
    mask_paths: list[Path] = []
    for index, (record, template) in enumerate(
        zip(manifest["files"], templates, strict=True), start=1
    ):
        source = FIXTURE_ROOT / record["path"]
        destination = root / MASK_STORAGE_PREFIX / f"mask-{index:02d}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if index == rgb24_mask_ordinal:
            _rgb24_png_reencode(source, destination)
        else:
            shutil.copyfile(source, destination)
        measured = image_digest_metadata(destination)
        asset = deepcopy(template)
        asset.update(
            {
                "storageKey": str(destination.relative_to(root)),
                "byteSize": destination.stat().st_size,
                "sha256": file_sha256(destination),
                "pixelDigest": measured["pixel_digest"],
                "pixelDigestSpec": measured["pixel_digest_spec"],
                "pixelMode": measured["pixel_mode"],
                "width": measured["width"],
                "height": measured["height"],
            }
        )
        staged_masks.append(resealed(asset))
        mask_paths.append(destination)

    base = base_plate_asset(
        sha256=file_sha256(base_path),
        byte_size=base_path.stat().st_size,
        storage_key=BASE_STORAGE_KEY,
    )
    port = inspection_port(base, media_probe=media_probe)
    command = requirement_command(compositeParams=_native_composite_params())
    requirement = build_glyph_reveal_requirement(
        command,
        base_plate_asset=base,
        mask_assets=staged_masks,
        inspection_port=port,
    )
    execution = build_glyph_reveal_execution_request(
        requirement,
        base,
        staged_masks,
        port,
    )
    return _PreparedRun(
        root=root,
        requirement=requirement,
        base=base,
        masks=staged_masks,
        inspection_port=port,
        execution=execution,
        base_bytes=base_bytes,
        mask_paths=mask_paths,
    )


def _stage_small_fail_closed_inputs(root: Path) -> _PreparedRun:
    base_path = root / BASE_STORAGE_KEY
    base_bytes = _generate_small_base_plate(base_path)
    templates = mask_assets(storage_prefix=MASK_STORAGE_PREFIX)
    staged_masks: list[dict] = []
    mask_paths: list[Path] = []
    for index, template in enumerate(templates, start=1):
        path = root / MASK_STORAGE_PREFIX / f"mask-{index:02d}.png"
        _write_small_gray_png(path, set(range(index)))
        measured = image_digest_metadata(path)
        asset = deepcopy(template)
        asset.update(
            {
                "storageKey": str(path.relative_to(root)),
                "byteSize": path.stat().st_size,
                "sha256": file_sha256(path),
                "pixelDigest": measured["pixel_digest"],
                "pixelDigestSpec": measured["pixel_digest_spec"],
                "pixelMode": measured["pixel_mode"],
                "width": 8,
                "height": 8,
            }
        )
        staged_masks.append(resealed(asset))
        mask_paths.append(path)

    base = base_plate_asset(
        sha256=file_sha256(base_path),
        byte_size=base_path.stat().st_size,
        storage_key=BASE_STORAGE_KEY,
    )
    port = inspection_port(
        base,
        media_probe={
            "width": 64,
            "height": 64,
            "frameCount": FRAME_COUNT,
            "frameRate": FRAME_RATE,
        },
    )
    requirement = build_glyph_reveal_requirement(
        requirement_command(),
        base_plate_asset=base,
        mask_assets=staged_masks,
        inspection_port=port,
    )
    execution = build_glyph_reveal_execution_request(
        requirement,
        base,
        staged_masks,
        port,
    )
    return _PreparedRun(
        root=root,
        requirement=requirement,
        base=base,
        masks=staged_masks,
        inspection_port=port,
        execution=execution,
        base_bytes=base_bytes,
        mask_paths=mask_paths,
    )


def _reseal_execution_input_bindings(execution: dict) -> dict:
    bindings = {
        "basePlate": {
            "assetVersionRef": execution["basePlate"]["assetVersionRef"],
            "assetVersionDigest": execution["basePlate"]["assetVersionDigest"],
            "fileDigest": execution["basePlate"]["fileDigest"],
        },
        "masks": [
            {
                "assetVersionRef": mask["assetVersionRef"],
                "assetVersionDigest": mask["assetVersionDigest"],
                "fileDigest": mask["fileDigest"],
                "pixelDigest": mask["pixelDigest"],
            }
            for mask in execution["masks"]
        ],
    }
    execution["inputBindingsDigest"] = sha256(
        json.dumps(
            bindings,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return resealed(execution)


def _execute(
    root: Path,
    *,
    base_bytes: bytes | None = None,
    rgb24_mask_ordinal: int | None = None,
) -> _CompletedRun:
    prepared = _stage_inputs(
        root,
        base_bytes=base_bytes,
        rgb24_mask_ordinal=rgb24_mask_ordinal,
    )
    artifact = V4CompositionExecutor.from_artifact_root(
        root
    ).compose_glyph_reveal(prepared.execution)
    result = build_glyph_reveal_composition_result(
        prepared.requirement,
        prepared.execution,
        artifact,
    )
    return _CompletedRun(prepared=prepared, artifact=artifact, result=result)


def _lossless_video_reencode(source: Path, destination: Path) -> None:
    _run_media_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-g",
            "1",
            "-pix_fmt",
            "yuv420p",
            "-threads:v",
            "1",
            "-fflags",
            "+bitexact",
            "-flags:v",
            "+bitexact",
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            "-y",
            str(destination),
        ]
    )


def _rgba_decoder(path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _read_exact(stream: BinaryIO, byte_count: int) -> bytes:
    chunks: list[bytes] = []
    remaining = byte_count
    while remaining:
        block = stream.read(remaining)
        if not block:
            break
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _outside_roi_is_equal(base: bytes, output: bytes) -> bool:
    row_bytes = CANVAS_WIDTH * 4
    roi_start = ROI_X * 4
    roi_end = (ROI_X + MASK_WIDTH) * 4
    for row in range(CANVAS_HEIGHT):
        start = row * row_bytes
        end = start + row_bytes
        if ROI_Y <= row < ROI_Y + MASK_HEIGHT:
            if (
                base[start : start + roi_start]
                != output[start : start + roi_start]
                or base[start + roi_end : end] != output[start + roi_end : end]
            ):
                return False
        elif base[start:end] != output[start:end]:
            return False
    return True


def _decoded_frame_evidence(base_path: Path, output_path: Path) -> _FrameEvidence:
    frame_bytes = CANVAS_WIDTH * CANVAS_HEIGHT * 4
    base_decoder = _rgba_decoder(base_path)
    output_decoder = _rgba_decoder(output_path)
    if base_decoder.stdout is None or output_decoder.stdout is None:
        raise AssertionError("RGBA decoder stdout is unavailable")
    base_digests: list[str] = []
    output_digests: list[str] = []
    outside_roi_equal: list[bool] = []
    try:
        for frame_index in range(FRAME_COUNT):
            base = _read_exact(base_decoder.stdout, frame_bytes)
            output = _read_exact(output_decoder.stdout, frame_bytes)
            if len(base) != frame_bytes or len(output) != frame_bytes:
                raise AssertionError(
                    f"decoded RGBA frame {frame_index} is truncated"
                )
            base_digests.append(sha256(base).hexdigest())
            output_digests.append(sha256(output).hexdigest())
            outside_roi_equal.append(_outside_roi_is_equal(base, output))
        if base_decoder.stdout.read(1) or output_decoder.stdout.read(1):
            raise AssertionError("decoded RGBA stream has unexpected extra frames")
    finally:
        for decoder in (base_decoder, output_decoder):
            if decoder.stdout is not None:
                decoder.stdout.close()
            stderr = decoder.stderr.read() if decoder.stderr is not None else b""
            if decoder.stderr is not None:
                decoder.stderr.close()
            return_code = decoder.wait(timeout=30)
            if return_code:
                raise AssertionError(
                    "RGBA decoding failed: " + stderr.decode(errors="replace")
                )
    return _FrameEvidence(
        base_digests=base_digests,
        output_digests=output_digests,
        outside_roi_equal=outside_roi_equal,
    )


class M13GlyphRevealCompositionIntegrationTests(unittest.TestCase):
    def test_real_v5_v4_v3_composition_is_pixel_exact_and_representation_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _execute(root / "independent-run-a")
            second = _execute(
                root / "independent-run-b",
                base_bytes=first.prepared.base_bytes,
            )

            self.assertEqual(len(first.prepared.inspection_port.calls), 2)
            self.assertEqual(len(second.prepared.inspection_port.calls), 2)
            self.assertEqual(
                first.prepared.requirement.payload_digest,
                second.prepared.requirement.payload_digest,
            )
            self.assertEqual(
                first.prepared.execution["payloadDigest"],
                second.prepared.execution["payloadDigest"],
            )
            self.assertEqual(
                first.artifact["outputDigest"]["pixelDigest"],
                second.artifact["outputDigest"]["pixelDigest"],
            )
            self.assertEqual(
                first.artifact["outputDigest"]["fileDigest"],
                second.artifact["outputDigest"]["fileDigest"],
            )
            self.assertEqual(
                first.artifact["executionRequestDigest"],
                first.prepared.execution["payloadDigest"],
            )
            self.assertEqual(
                first.artifact["requirementDigest"],
                first.prepared.requirement.payload_digest,
            )

            self.assertEqual(
                first.artifact["schemaVersion"],
                GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            )
            self.assertEqual(
                first.result["artifactEvidenceDigest"],
                first.artifact["payloadDigest"],
            )
            self.assertNotIn("internalPath", first.artifact)
            first_output = first.prepared.root / first.artifact["storageKey"]
            second_output = second.prepared.root / second.artifact["storageKey"]
            self.assertTrue(first_output.is_relative_to(first.prepared.root))
            self.assertTrue(second_output.is_relative_to(second.prepared.root))
            self.assertNotEqual(first_output, second_output)
            self.assertTrue(first_output.is_file())
            self.assertTrue(second_output.is_file())
            self.assertEqual(
                first_output.name,
                "glyph-reveal-"
                f"{first.prepared.execution['payloadDigest']}.mp4",
            )

            probe, pixel_format = _probe_video_contract(first_output)
            self.assertEqual(
                probe,
                {
                    "width": CANVAS_WIDTH,
                    "height": CANVAS_HEIGHT,
                    "frameCount": FRAME_COUNT,
                    "frameRate": FRAME_RATE,
                },
            )
            self.assertEqual(pixel_format, "yuv420p")

            evidence = _decoded_frame_evidence(
                first.prepared.root / BASE_STORAGE_KEY,
                first_output,
            )
            self.assertEqual(len(set(evidence.base_digests)), 1)
            self.assertEqual(
                evidence.output_digests[:FRAME_RANGE_START],
                evidence.base_digests[:FRAME_RANGE_START],
            )
            stage_digests: list[str] = []
            for stage in range(REVEAL_FRAME_COUNT):
                start = FRAME_RANGE_START + stage * FRAMES_PER_STAGE
                group = evidence.output_digests[start : start + FRAMES_PER_STAGE]
                with self.subTest(stage=stage + 1):
                    self.assertEqual(len(group), FRAMES_PER_STAGE)
                    self.assertEqual(len(set(group)), 1)
                stage_digests.append(group[0])
            self.assertEqual(len(set(stage_digests)), REVEAL_FRAME_COUNT)
            self.assertEqual(
                evidence.output_digests[FRAME_RANGE_END:],
                [stage_digests[-1]] * (FRAME_COUNT - FRAME_RANGE_END),
            )
            self.assertNotEqual(stage_digests[-1], evidence.base_digests[0])
            self.assertEqual(evidence.outside_roi_equal, [True] * FRAME_COUNT)

            self.assertFalse(first.prepared.execution["publicationAllowed"])
            self.assertFalse(first.artifact["publicationAllowed"])
            self.assertFalse(first.result["publicationAllowed"])
            self.assertEqual(first.result["state"], "COMPOSED_CANDIDATE")
            self.assertEqual(
                first.result["executionRequestDigest"],
                first.prepared.execution["payloadDigest"],
            )
            self.assertEqual(
                first.result["outputDigest"], first.artifact["outputDigest"]
            )
            self.assertNotIn("assetAdmissionRef", first.result)

            # A physically RGB24 PNG remains admissible when the AssetVersion
            # file and canonical decoded-pixel evidence are updated together.
            rgb24_ordinal = 4
            rgb24 = _execute(
                root / "rgb24-lossless-mask-run",
                base_bytes=first.prepared.base_bytes,
                rgb24_mask_ordinal=rgb24_ordinal,
            )
            index = rgb24_ordinal - 1
            source_record = source_manifest()["files"][index]
            rgb24_asset = rgb24.prepared.masks[index]
            rgb24_path = rgb24.prepared.mask_paths[index]
            self.assertEqual(_probe_image_pixel_format(rgb24_path), "rgb24")
            self.assertNotEqual(
                file_digest(rgb24_path), source_record["fileDigest"]
            )
            self.assertEqual(rgb24_asset["byteSize"], rgb24_path.stat().st_size)
            self.assertEqual(rgb24_asset["sha256"], file_sha256(rgb24_path))
            self.assertEqual(
                rgb24_asset["pixelDigest"], source_record["pixelDigest"]
            )
            self.assertNotEqual(
                rgb24_asset["payloadDigest"],
                first.prepared.masks[index]["payloadDigest"],
            )
            self.assertEqual(rgb24.result["state"], "COMPOSED_CANDIDATE")
            self.assertEqual(
                rgb24.artifact["outputDigest"]["pixelDigest"],
                first.artifact["outputDigest"]["pixelDigest"],
            )

            reencoded = root / "lossless-reencoded.mkv"
            _lossless_video_reencode(first_output, reencoded)
            original_digest = video_digest_metadata(first_output)
            reencoded_digest = video_digest_metadata(reencoded)
            self.assertNotEqual(
                original_digest["fileDigest"], reencoded_digest["fileDigest"]
            )
            self.assertEqual(
                original_digest["pixelDigest"], reencoded_digest["pixelDigest"]
            )
            self.assertEqual(
                original_digest["pixelDigestSpec"],
                reencoded_digest["pixelDigestSpec"],
            )
            self.assertEqual(original_digest["frameCount"], FRAME_COUNT)
            self.assertEqual(reencoded_digest["frameCount"], FRAME_COUNT)

    def test_v4_rejects_tampering_and_path_escape_without_any_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepared = _stage_inputs(root)
            executor = V4CompositionExecutor.from_artifact_root(root)

            tampered = deepcopy(prepared.execution)
            tampered["compositeParams"]["position"]["xPixels"] += 1
            with self.subTest(case="sealed-request-tampering"):
                with self.assertRaises(CompositionRequestValidationError):
                    executor.compose_glyph_reveal(tampered)

            escaped = deepcopy(prepared.execution)
            escaped["basePlate"]["storageKey"] = "../outside.mp4"
            escaped = resealed(escaped)
            with self.subTest(case="resealed-path-escape"):
                with self.assertRaises(CompositionRequestValidationError):
                    executor.compose_glyph_reveal(escaped)

            self.assertEqual(list(root.rglob("glyph-reveal-*.mp4")), [])
            self.assertEqual(list(root.rglob(".glyph-reveal-work-*")), [])
            self.assertEqual(list(root.rglob("candidate.mp4")), [])
            self.assertEqual(list(root.rglob("*.part*")), [])

    def test_v3_rejects_mask_media_drift_and_non_cumulative_stages(self):
        cases = (
            (
                "declared-dimensions-drift",
                "glyph mask dimensions changed from the execution request",
            ),
            (
                "duplicate-gray-hidden-in-alpha",
                "glyph mask alpha must be fully opaque",
            ),
            (
                "gray-coverage-regression",
                "glyph cumulative mask coverage regressed",
            ),
        )
        for case, expected_message in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                prepared = _stage_small_fail_closed_inputs(root)
                execution = deepcopy(prepared.execution)
                if case == "declared-dimensions-drift":
                    for mask in execution["masks"]:
                        mask["width"] = 7
                        mask["height"] = 7
                    execution = resealed(execution)
                else:
                    second_path = prepared.mask_paths[1]
                    if case == "duplicate-gray-hidden-in-alpha":
                        _write_small_gray_png(
                            second_path,
                            {0},
                            alpha=254,
                        )
                    else:
                        _write_small_gray_png(second_path, {1, 2})
                    measured = image_digest_metadata(second_path)
                    execution["masks"][1].update(
                        {
                            "fileDigest": file_digest(second_path),
                            "pixelDigest": measured["pixel_digest"],
                            "pixelDigestSpec": measured["pixel_digest_spec"],
                            "width": measured["width"],
                            "height": measured["height"],
                        }
                    )
                    execution = _reseal_execution_input_bindings(execution)

                executor = V4CompositionExecutor.from_artifact_root(root)
                with self.assertRaises(CompositionExecutionError) as caught:
                    executor.compose_glyph_reveal(execution)
                self.assertIsInstance(caught.exception.__cause__, RenderArtifactError)
                self.assertEqual(str(caught.exception.__cause__), expected_message)
                self.assertEqual(list(root.rglob("glyph-reveal-*.mp4")), [])
                self.assertEqual(list(root.rglob("glyph-reveal")), [])
                self.assertEqual(list(root.rglob(".glyph-reveal-work-*")), [])
                self.assertEqual(list(root.rglob("candidate.mp4")), [])


if __name__ == "__main__":
    unittest.main()
