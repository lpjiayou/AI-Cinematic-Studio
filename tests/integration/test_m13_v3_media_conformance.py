from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from services.v3_render_core.composition import (
    RenderArtifactError,
    _PinnedRuntimeBinary,
)
from services.v3_render_core.masked_surface import _probe_video, _validate_probe


WIDTH = 64
HEIGHT = 64
FRAME_RATE = 24
FRAME_COUNT = 49


def _run_ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", *arguments],
        check=True,
        capture_output=True,
        timeout=60,
    )


def _output_contract() -> dict[str, object]:
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "frameCount": FRAME_COUNT,
        "frameRate": FRAME_RATE,
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg and FFprobe are required",
)
class M13V3MediaConformanceTests(unittest.TestCase):
    def _probe(self, path: Path) -> dict[str, object]:
        runtime = Path(str(shutil.which("ffprobe"))).resolve()
        with _PinnedRuntimeBinary(runtime, label="FFprobe") as ffprobe:
            return _probe_video(path, ffprobe)

    def test_accepts_exact_constant_cadence_without_decimal_rounding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "constant.mp4"
            _run_ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FRAME_RATE}",
                "-frames:v",
                str(FRAME_COUNT),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-y",
                str(path),
            )

            probe = self._probe(path)
            _validate_probe(probe, _output_contract(), input_media=False)
            self.assertEqual(Fraction(FRAME_RATE, 1), probe["frameRate"])
            self.assertEqual(Fraction(FRAME_RATE, 1), probe["realFrameRate"])
            self.assertEqual(Fraction(FRAME_COUNT, FRAME_RATE), probe["duration"])

    def test_rejects_an_extra_audio_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audio-bearing.mp4"
            _run_ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={WIDTH}x{HEIGHT}:rate={FRAME_RATE}:duration=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=48000:duration=3",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-frames:v",
                str(FRAME_COUNT),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-y",
                str(path),
            )

            with self.assertRaisesRegex(
                RenderArtifactError, "exactly one video-only stream"
            ):
                self._probe(path)

    def test_rejects_vfr_even_when_average_rate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "variable.mp4"
            _run_ffmpeg(
                "-f",
                "lavfi",
                "-i",
                f"testsrc2=size={WIDTH}x{HEIGHT}:rate=48:duration=1",
                "-vf",
                (
                    "select='(eq(mod(n,4),0)+eq(mod(n,4),1))*"
                    "not(eq(n,45))+eq(n,47)'"
                ),
                "-fps_mode",
                "vfr",
                "-c:v",
                "libx264",
                "-x264-params",
                "bframes=0",
                "-pix_fmt",
                "yuv420p",
                "-video_track_timescale",
                "48000",
                "-y",
                str(path),
            )

            probe = self._probe(path)
            self.assertEqual(Fraction(FRAME_RATE, 1), probe["frameRate"])
            self.assertEqual(Fraction(48, 1), probe["realFrameRate"])
            with self.assertRaisesRegex(
                RenderArtifactError, "media facts do not match"
            ):
                _validate_probe(probe, _output_contract(), input_media=False)


if __name__ == "__main__":
    unittest.main()
