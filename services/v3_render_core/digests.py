"""Byte and decoded-pixel digests for deterministic V3 render artifacts.

The frozen image surface in this module is deliberately narrow: one lossless,
single-frame PNG decoded to RGBA8 row-major bytes.  It reproduces the PNG
portion of the final-assets v1.2 digest contract without claiming general JPEG
or EXIF-normalisation compatibility.  Video digests extend the RGBA8 rule by
hashing display-oriented frames in presentation order.
"""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, BinaryIO, Mapping


DIGEST_ALGORITHM = "sha256"
IMAGE_PIXEL_DIGEST_SPEC = "RGBA8/exif-transposed/row-major/v1"
VIDEO_PIXEL_DIGEST_SPEC = "RGBA8/display-transposed/frame-major/row-major/v1"
PIXEL_DIGEST_SPEC = IMAGE_PIXEL_DIGEST_SPEC


class DigestError(RuntimeError):
    """Raised when a file cannot be measured under the frozen digest contract."""


def _fixed_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    return environment


def _executable(name_or_path: Path | str) -> Path:
    value = str(name_or_path)
    candidate = shutil.which(value)
    if candidate is None:
        raise DigestError(f"{Path(value).name} runtime is unavailable")
    resolved = Path(candidate).resolve()
    if not resolved.is_file():
        raise DigestError(f"{Path(value).name} runtime is unavailable")
    return resolved


def _require_file(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_file():
        raise DigestError("digest input is not a regular file")
    return candidate


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = sha256()
    byte_count = 0
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
        byte_count += len(block)
    return digest.hexdigest(), byte_count


def file_sha256(path: Path | str) -> str:
    """Return the unprefixed SHA-256 of the exact file bytes."""

    candidate = _require_file(path)
    with candidate.open("rb") as stream:
        result, _ = _hash_stream(stream)
    return result


def file_digest(path: Path | str) -> str:
    """Return the frozen, algorithm-prefixed byte digest."""

    return f"{DIGEST_ALGORITHM}:{file_sha256(path)}"


def _probe_video_stream(
    path: Path,
    *,
    ffprobe_path: Path | str = "ffprobe",
) -> dict[str, Any]:
    executable = _executable(ffprobe_path)
    command = [
        str(executable),
        "-v", "error",
        "-count_frames",
        "-select_streams", "v",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,width,height,nb_frames,"
            "nb_read_frames:format=format_name"
        ),
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=_fixed_environment(),
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise DigestError("pixel digest probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise DigestError("pixel digest input must contain exactly one video stream")
    stream = streams[0]
    if not isinstance(stream, Mapping):
        raise DigestError("pixel digest stream metadata is invalid")
    try:
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DigestError("pixel digest dimensions are invalid") from exc
    if width <= 0 or height <= 0:
        raise DigestError("pixel digest dimensions are invalid")
    frame_value = stream.get("nb_read_frames") or stream.get("nb_frames")
    try:
        frame_count = int(frame_value)
    except (TypeError, ValueError) as exc:
        raise DigestError("pixel digest frame count is unavailable") from exc
    if frame_count <= 0:
        raise DigestError("pixel digest frame count is invalid")
    format_value = payload.get("format")
    if not isinstance(format_value, Mapping):
        raise DigestError("pixel digest format metadata is invalid")
    return {
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "codecName": stream.get("codec_name"),
        "formatName": format_value.get("format_name"),
    }


def _decoded_rgba_sha256(
    path: Path,
    *,
    frame_count: int,
    ffmpeg_path: Path | str = "ffmpeg",
) -> tuple[str, int]:
    executable = _executable(ffmpeg_path)
    command = [
        str(executable),
        "-hide_banner",
        "-loglevel", "error",
        "-xerror",
        "-nostdin",
        "-threads", "1",
        "-filter_threads", "1",
        "-filter_complex_threads", "1",
        "-fflags", "+bitexact",
        "-sws_flags", "bitexact+accurate_rnd+full_chroma_int",
        "-hwaccel", "none",
        "-autorotate", "1",
        "-i", str(path),
        "-map", "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-frames:v", str(frame_count),
        "-c:v", "rawvideo",
        "-flags:v", "+bitexact",
        "-fps_mode", "passthrough",
        "-f", "rawvideo",
        "-pix_fmt", "rgba",
        "pipe:1",
    ]
    # Raw RGBA can be hundreds of megabytes even for a short clip.  Anonymous
    # temporary files keep memory bounded while subprocess.run enforces a real
    # wall-clock deadline; reading a PIPE before wait(timeout=...) would allow a
    # decoder that never reaches EOF to hang forever.
    try:
        with tempfile.TemporaryFile(mode="w+b") as raw_output:
            with tempfile.TemporaryFile(mode="w+b") as error_output:
                try:
                    completed = subprocess.run(
                        command,
                        stdout=raw_output,
                        stderr=error_output,
                        check=False,
                        timeout=180,
                        env=_fixed_environment(),
                    )
                except subprocess.SubprocessError as exc:
                    raise DigestError("pixel digest decode failed") from exc
                if completed.returncode != 0:
                    error_output.seek(0)
                    message = error_output.read(8192).decode(
                        "utf-8", "replace"
                    ).strip()
                    raise DigestError(
                        "pixel digest decode failed"
                        + (f": {message}" if message else "")
                    )
                raw_output.seek(0)
                return _hash_stream(raw_output)
    except DigestError:
        raise
    except OSError as exc:
        raise DigestError("pixel digest decode failed") from exc


def image_digest_metadata(
    path: Path | str,
    *,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
) -> dict[str, object]:
    """Measure one single-frame PNG under the frozen RGBA8 pixel contract."""

    candidate = _require_file(path)
    if candidate.suffix.lower() != ".png":
        raise DigestError("image pixel digest input must be a PNG file")
    probe = _probe_video_stream(candidate, ffprobe_path=ffprobe_path)
    if (
        probe["codecName"] != "png"
        or probe["formatName"] != "png_pipe"
        or probe["frameCount"] != 1
    ):
        raise DigestError("image pixel digest input must be a single-frame PNG")
    pixel_hex, byte_count = _decoded_rgba_sha256(
        candidate,
        frame_count=1,
        ffmpeg_path=ffmpeg_path,
    )
    expected_bytes = probe["width"] * probe["height"] * 4
    if byte_count != expected_bytes:
        raise DigestError("image pixel digest decoded byte count is invalid")
    return {
        "width": probe["width"],
        "height": probe["height"],
        "source_mode": None,
        "pixel_mode": "RGBA",
        "pixel_digest": f"{DIGEST_ALGORITHM}:{pixel_hex}",
        "pixel_digest_spec": IMAGE_PIXEL_DIGEST_SPEC,
    }


def pixel_sha256(
    path: Path | str,
    *,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
) -> str:
    """Return the unprefixed canonical RGBA8 digest of one PNG image."""

    metadata = image_digest_metadata(
        path,
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
    )
    return str(metadata["pixel_digest"]).removeprefix(f"{DIGEST_ALGORITHM}:")


def digest_metadata(
    path: Path | str,
    *,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
) -> dict[str, object]:
    """Return byte metadata, adding frozen pixel metadata only for PNG files.

    JPEG and other formats intentionally remain file-digest-only here.  Call
    :func:`image_digest_metadata` when a canonical image pixel digest is
    required; that API rejects every representation except single-frame PNG.
    """

    candidate = _require_file(path)
    record: dict[str, object] = {
        "file_digest": file_digest(candidate),
        "file_digest_algorithm": DIGEST_ALGORITHM,
        "pixel_digest": None,
        "pixel_digest_spec": None,
    }
    if candidate.suffix.lower() == ".png":
        record.update(
            image_digest_metadata(
                candidate,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
            )
        )
    return record


def video_digest_metadata(
    path: Path | str,
    *,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
) -> dict[str, object]:
    """Return exact-file and decoded-pixel identity for one video stream."""

    candidate = _require_file(path)
    probe = _probe_video_stream(candidate, ffprobe_path=ffprobe_path)
    pixel_hex, byte_count = _decoded_rgba_sha256(
        candidate,
        frame_count=probe["frameCount"],
        ffmpeg_path=ffmpeg_path,
    )
    expected_bytes = (
        probe["width"] * probe["height"] * 4 * probe["frameCount"]
    )
    if byte_count != expected_bytes:
        raise DigestError("video pixel digest decoded byte count is invalid")
    return {
        "fileDigest": file_digest(candidate),
        "fileDigestAlgorithm": DIGEST_ALGORITHM,
        "pixelDigest": f"{DIGEST_ALGORITHM}:{pixel_hex}",
        "pixelDigestSpec": VIDEO_PIXEL_DIGEST_SPEC,
        "pixelMode": "RGBA",
        "width": probe["width"],
        "height": probe["height"],
        "frameCount": probe["frameCount"],
    }
