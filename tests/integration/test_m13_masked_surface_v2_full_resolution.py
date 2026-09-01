from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from typing import Any
import unittest

from services.v3_render_core.digests import (
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)
from services.v3_render_core.masked_surface import (
    DeterministicMaskedSurfaceExecutor,
    MASKED_SURFACE_ENCODER_PRESET,
    MASKED_SURFACE_ENCODER_THREAD_COUNT,
    MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
    MASKED_SURFACE_FILTER_THREAD_COUNT,
    MASKED_SURFACE_RENDERER_VERSION_CURRENT,
    MASKED_SURFACE_SUBPROCESS_TIMEOUT_SECONDS,
    _masked_surface_roi,
    _masked_surface_v2_workload,
)


WIDTH = 704
HEIGHT = 1280
FRAME_COUNT = 720
FRAME_RATE = 24
ACTIVE_FRAMES = frozenset(range(10, 14))
PERFORMANCE_LIMIT_SECONDS = 240.0


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(value)
    result["payloadDigest"] = sha256(_canonical(result)).hexdigest()
    return result


def _run_media(
    command: list[str],
    *,
    input_bytes: bytes | None = None,
    timeout: int = 180,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        input=input_bytes,
        check=True,
        capture_output=True,
        timeout=timeout,
    )


def _stage_fixture(root: Path) -> tuple[Path, Path]:
    inputs = root / "inputs"
    inputs.mkdir()
    base = inputs / "base.mp4"
    mask = inputs / "mask.png"
    _run_media(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x485868:size={WIDTH}x{HEIGHT}:rate={FRAME_RATE}",
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
            "-y",
            str(base),
        ]
    )
    mask_pixels = bytes([255, *([0] * 63)])
    _run_media(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-f",
            "rawvideo",
            "-pixel_format",
            "gray",
            "-video_size",
            "8x8",
            "-i",
            "pipe:0",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            "-threads:v",
            "1",
            "-y",
            str(mask),
        ],
        input_bytes=mask_pixels,
    )
    return base, mask


def _request(root: Path, base: Path, mask: Path) -> dict[str, Any]:
    base_pixels = decoded_frame_pixel_digest_metadata(base)
    mask_pixels = image_digest_metadata(mask)
    return _seal(
        {
            "schemaVersion": MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": "m13-execution:full-resolution-c1",
            "v5ExecutionRequestDigest": "1" * 64,
            "workspaceRef": "workspace:m13-c1",
            "productionRunRef": "run:m13-c1",
            "requirementSchemaVersion": "v5.m13-scratch-light-requirement.v1",
            "requirementRef": "requirement:full-resolution-c1",
            "requirementDigest": "2" * 64,
            "effectMode": "SCRATCH_REVEAL",
            "targetShot": {
                "shotRef": "shot:full-resolution-c1",
                "shotVersionRef": "shot-version:full-resolution-c1:v1",
                "shotVersionDigest": "3" * 64,
            },
            "basePlate": {
                "assetVersionRef": "asset-version:full-resolution-base",
                "assetVersionDigest": "4" * 64,
                "storageKey": str(base.relative_to(root)),
                "fileDigest": file_digest(base),
                "pixelDigest": base_pixels["decodedFramePixelDigest"],
                "pixelDigestSpec": base_pixels["decodedFramePixelDigestSpec"],
                "width": WIDTH,
                "height": HEIGHT,
                "frameCount": FRAME_COUNT,
                "frameRate": FRAME_RATE,
                "pixelFormat": "yuv420p",
            },
            "mask": {
                "assetVersionRef": "asset-version:full-resolution-mask",
                "assetVersionDigest": "5" * 64,
                "storageKey": str(mask.relative_to(root)),
                "fileDigest": file_digest(mask),
                "pixelDigest": mask_pixels["pixel_digest"],
                "pixelDigestSpec": mask_pixels["pixel_digest_spec"],
                "pixelMode": mask_pixels["pixel_mode"],
                "width": 8,
                "height": 8,
            },
            "frameRangeStartInclusive": 10,
            "frameRangeEndExclusive": 14,
            "explicitSchedule": [
                {
                    "startFrameInclusive": 10,
                    "endFrameExclusive": 12,
                    "enabled": True,
                    "interpolation": "STEP",
                },
                {
                    "startFrameInclusive": 12,
                    "endFrameExclusive": 14,
                    "enabled": True,
                    "interpolation": "STEP",
                },
            ],
            "trajectoryKeyframes": [
                {
                    "frame": 10,
                    "xPermille": 250,
                    "yPermille": 300,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 13,
                    "xPermille": 750,
                    "yPermille": 300,
                    "interpolation": "EASE_IN_OUT",
                },
            ],
            "intensityCurve": [
                {"frame": 10, "valuePermille": 0, "interpolation": "LINEAR"},
                {
                    "frame": 13,
                    "valuePermille": 900,
                    "interpolation": "EASE_OUT",
                },
            ],
            "exposureCurve": [
                {
                    "frame": 10,
                    "valueMilliStops": 0,
                    "interpolation": "LINEAR",
                },
                {
                    "frame": 13,
                    "valueMilliStops": 500,
                    "interpolation": "EASE_OUT",
                },
            ],
            "position": {"xPermille": 250, "yPermille": 300},
            "scale": {"xPermille": 200, "yPermille": 400},
            "perspective": {"mode": "NONE", "quadPermille": []},
            "blendMode": "SCREEN",
            "layer": 4,
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


def _frame_hashes(path: Path) -> list[bytes]:
    completed = _run_media(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-vf",
            "format=rgba",
            "-f",
            "framemd5",
            "pipe:1",
        ]
    )
    return [
        line.rsplit(b",", 1)[-1].strip()
        for line in completed.stdout.splitlines()
        if line and not line.startswith(b"#")
    ]


def _active_rgba(path: Path) -> bytes:
    return _run_media(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-vf",
            "select='between(n,10,13)',format=rgba",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
    ).stdout


def _frame_timestamps(path: Path) -> list[int]:
    completed = _run_media(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return [int(line) for line in completed.stdout.splitlines() if line]


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class MaskedSurfaceV2FullResolutionTests(unittest.TestCase):
    def test_failed_r2_fixture_completes_twice_with_exact_sparse_roi_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, mask = _stage_fixture(root)
            request = _request(root, base, mask)
            profile = _masked_surface_v2_workload(request)
            self.assertEqual(648_806_400, profile["outputPixelFrames"])
            self.assertEqual(((10, 14),), profile["activeIntervals"])
            self.assertEqual(4, profile["activeFrameCount"])
            self.assertEqual(1_040_000, profile["activeRoiPixelFrames"])
            self.assertEqual(
                {"x": 172, "y": 380, "width": 500, "height": 520},
                {
                    key: profile["roi"][key]
                    for key in ("x", "y", "width", "height")
                },
            )
            self.assertFalse(profile["roi"]["fullFrame"])
            self.assertEqual("medium", MASKED_SURFACE_ENCODER_PRESET)
            self.assertEqual(1, MASKED_SURFACE_ENCODER_THREAD_COUNT)
            self.assertEqual(1, MASKED_SURFACE_FILTER_THREAD_COUNT)
            self.assertEqual(300, MASKED_SURFACE_SUBPROCESS_TIMEOUT_SECONDS)

            workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
            run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
            artifact_directory = root / workspace / run / "masked-surface"
            artifact_directory.mkdir(parents=True)
            legacy = artifact_directory / f"masked-surface-{request['payloadDigest']}.mp4"
            legacy.write_bytes(b"historical-v1-artifact")
            legacy_v2 = (
                artifact_directory
                / f"masked-surface-v2-{request['payloadDigest']}.mp4"
            )
            legacy_v2.write_bytes(b"historical-v2-artifact")

            executor = DeterministicMaskedSurfaceExecutor(root)
            results: list[dict[str, Any]] = []
            elapsed: list[float] = []
            for _ in range(2):
                started = time.monotonic()
                results.append(executor.execute(request))
                elapsed.append(time.monotonic() - started)
            for duration in elapsed:
                self.assertLessEqual(duration, PERFORMANCE_LIMIT_SECONDS)
            first, second = results
            self.assertEqual("3", MASKED_SURFACE_RENDERER_VERSION_CURRENT)
            self.assertEqual("3", first["rendererVersion"])
            self.assertEqual(first["outputStorageKey"], second["outputStorageKey"])
            self.assertIn(
                f"masked-surface-v3-{request['payloadDigest']}.mp4",
                first["outputStorageKey"],
            )
            self.assertEqual(
                first["outputDigest"]["decodedFramePixelDigest"],
                second["outputDigest"]["decodedFramePixelDigest"],
            )
            self.assertEqual(
                first["outputDigest"]["fileDigest"],
                second["outputDigest"]["fileDigest"],
            )
            self.assertEqual(
                (WIDTH, HEIGHT, FRAME_COUNT, FRAME_RATE),
                (
                    first["outputDigest"]["width"],
                    first["outputDigest"]["height"],
                    first["outputDigest"]["frameCount"],
                    first["outputDigest"]["frameRate"],
                ),
            )
            self.assertEqual(b"historical-v1-artifact", legacy.read_bytes())
            self.assertEqual(
                b"historical-v2-artifact", legacy_v2.read_bytes()
            )
            self.assertNotEqual(
                str(legacy_v2.relative_to(root)), first["outputStorageKey"]
            )

            output = root / first["outputStorageKey"]
            self.assertEqual(
                [frame * 512 for frame in range(FRAME_COUNT)],
                _frame_timestamps(output),
            )
            base_hashes = _frame_hashes(base)
            output_hashes = _frame_hashes(output)
            self.assertEqual(FRAME_COUNT, len(base_hashes))
            self.assertEqual(FRAME_COUNT, len(output_hashes))
            self.assertTrue(
                all(
                    base_hashes[frame] == output_hashes[frame]
                    for frame in range(FRAME_COUNT)
                    if frame not in ACTIVE_FRAMES
                )
            )

            base_active = _active_rgba(base)
            output_active = _active_rgba(output)
            frame_bytes = WIDTH * HEIGHT * 4
            self.assertEqual(len(ACTIVE_FRAMES) * frame_bytes, len(base_active))
            self.assertEqual(len(base_active), len(output_active))
            roi = _masked_surface_roi(request)
            changed_inside = 0
            for frame in range(len(ACTIVE_FRAMES)):
                frame_start = frame * frame_bytes
                for y in range(HEIGHT):
                    row_start = frame_start + y * WIDTH * 4
                    row_end = row_start + WIDTH * 4
                    if y < roi["y"] or y >= roi["y"] + roi["height"]:
                        self.assertEqual(
                            base_active[row_start:row_end],
                            output_active[row_start:row_end],
                        )
                        continue
                    left_end = row_start + roi["x"] * 4
                    right_start = left_end + roi["width"] * 4
                    self.assertEqual(
                        base_active[row_start:left_end],
                        output_active[row_start:left_end],
                    )
                    self.assertEqual(
                        base_active[right_start:row_end],
                        output_active[right_start:row_end],
                    )
                    changed_inside += sum(
                        source != rendered
                        for source, rendered in zip(
                            base_active[left_end:right_start],
                            output_active[left_end:right_start],
                            strict=True,
                        )
                    )
            self.assertGreater(changed_inside, 0)


if __name__ == "__main__":
    unittest.main()
