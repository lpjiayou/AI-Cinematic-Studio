"""Byte and decoded-pixel digests for deterministic V3 render artifacts.

The frozen image surface in this module is deliberately narrow: one lossless,
single-frame PNG decoded to RGBA8 row-major bytes.  It reproduces the PNG
portion of the final-assets v1.2 digest contract without claiming general JPEG
or EXIF-normalisation compatibility.  Video digests extend the RGBA8 rule by
hashing display-oriented frames in presentation order.
"""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, BinaryIO, Mapping


DIGEST_ALGORITHM = "sha256"
IMAGE_PIXEL_DIGEST_SPEC = "RGBA8/exif-transposed/row-major/v1"
VIDEO_PIXEL_DIGEST_SPEC = "RGBA8/display-transposed/frame-major/row-major/v1"
DECODED_FRAME_PIXEL_DIGEST_SPEC_V2 = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)
CANONICAL_PCM_SAMPLE_RATE = 48_000
CANONICAL_PCM_CHANNEL_COUNT = 2
MAX_CANONICAL_PCM_SAMPLE_COUNT = 28_800_000
_AAC_FRAME_SAMPLE_COUNT = 1024
_PCM_CONTENT_DIGEST_SPEC_TEMPLATE = {
    "schemaVersion": "v4.pcm-content-digest-spec.v1",
    "algorithm": "SHA-256",
    "decoder": "FFMPEG",
    "sampleFormat": "s16le",
    "sampleRate": CANONICAL_PCM_SAMPLE_RATE,
    "channelLayout": "stereo",
    "channelOrder": ["FL", "FR"],
    "interleaving": "INTERLEAVED",
    "sampleOrder": "FRAME_MAJOR_CHANNEL_ORDER",
    "endianness": "LITTLE_ENDIAN",
    "containerMetadataIncluded": False,
    "monoExpansion": "DUPLICATE_TO_FL_FR",
}

# Keep the public contract inspectable without letting an in-process caller
# mutate the template used to measure artifacts.
PCM_CONTENT_DIGEST_SPEC = {
    **_PCM_CONTENT_DIGEST_SPEC_TEMPLATE,
    "channelOrder": list(_PCM_CONTENT_DIGEST_SPEC_TEMPLATE["channelOrder"]),
}
PIXEL_DIGEST_SPEC = IMAGE_PIXEL_DIGEST_SPEC


class DigestError(RuntimeError):
    """Raised when a file cannot be measured under the frozen digest contract."""


def _fixed_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    return environment


def _executable(name_or_path: Path | str) -> Path:
    value = str(name_or_path)
    if re.fullmatch(r"/proc/self/fd/[0-9]+", value) is not None:
        candidate = Path(value)
        if not candidate.is_file():
            raise DigestError(f"{candidate.name} runtime is unavailable")
        return candidate
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


def _probe_identity_video_stream(
    path: Path,
    *,
    ffprobe_path: Path | str = "ffprobe",
    pass_fds: tuple[int, ...] = (),
) -> dict[str, Any]:
    """Probe one video while rejecting every non-identity display transform."""

    executable = _executable(ffprobe_path)
    command = [
        str(executable),
        "-v", "error",
        "-count_frames",
        "-select_streams", "v",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,width,height,nb_frames,"
            "nb_read_frames:stream_tags=rotate:"
            "stream_side_data=side_data_type,rotation:format=format_name"
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
            pass_fds=pass_fds,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise DigestError("decoded-frame pixel digest probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise DigestError(
            "decoded-frame pixel digest input must contain exactly one video stream"
        )
    stream = streams[0]
    if not isinstance(stream, Mapping):
        raise DigestError("decoded-frame pixel digest stream metadata is invalid")
    tags = stream.get("tags")
    if isinstance(tags, Mapping) and "rotate" in tags:
        try:
            tag_rotation = int(str(tags["rotate"])) % 360
        except (TypeError, ValueError) as exc:
            raise DigestError(
                "decoded-frame pixel digest display transform is invalid"
            ) from exc
        if tag_rotation != 0:
            raise DigestError(
                "decoded-frame pixel digest requires identity display transform"
            )
    side_data = stream.get("side_data_list")
    if side_data is not None:
        if not isinstance(side_data, list) or any(
            not isinstance(item, Mapping) for item in side_data
        ):
            raise DigestError(
                "decoded-frame pixel digest display transform is invalid"
            )
        if any(
            item.get("side_data_type") == "Display Matrix" or "rotation" in item
            for item in side_data
        ):
            raise DigestError(
                "decoded-frame pixel digest requires identity display transform"
            )
    try:
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DigestError(
            "decoded-frame pixel digest dimensions are invalid"
        ) from exc
    if width <= 0 or height <= 0:
        raise DigestError("decoded-frame pixel digest dimensions are invalid")
    frame_value = stream.get("nb_read_frames") or stream.get("nb_frames")
    try:
        frame_count = int(frame_value)
    except (TypeError, ValueError) as exc:
        raise DigestError(
            "decoded-frame pixel digest frame count is unavailable"
        ) from exc
    if frame_count <= 0:
        raise DigestError("decoded-frame pixel digest frame count is invalid")
    format_value = payload.get("format")
    if not isinstance(format_value, Mapping):
        raise DigestError("decoded-frame pixel digest format metadata is invalid")
    return {
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "codecName": stream.get("codec_name"),
        "formatName": format_value.get("format_name"),
    }


def _probe_audio_stream(
    path: Path,
    *,
    ffprobe_path: Path | str = "ffprobe",
    pass_fds: tuple[int, ...] = (),
) -> dict[str, Any]:
    """Probe exactly one audible stream for the canonical PCM projection."""

    executable = _executable(ffprobe_path)
    command = [
        str(executable),
        "-v", "error",
        "-select_streams", "a",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,sample_rate,channels,"
            "channel_layout,duration_ts,time_base"
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
            pass_fds=pass_fds,
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise DigestError("PCM content digest probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise DigestError(
            "PCM content digest input must contain exactly one audio stream"
        )
    stream = streams[0]
    if not isinstance(stream, Mapping) or stream.get("codec_type") != "audio":
        raise DigestError("PCM content digest stream metadata is invalid")
    try:
        sample_rate = int(stream["sample_rate"])
        source_channel_count = int(stream["channels"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DigestError("PCM content digest stream metadata is invalid") from exc
    if (
        sample_rate != CANONICAL_PCM_SAMPLE_RATE
        or source_channel_count not in {1, 2}
    ):
        raise DigestError("PCM content digest source format is unsupported")
    try:
        duration_ticks = int(stream["duration_ts"])
        time_base = Fraction(str(stream["time_base"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise DigestError("PCM content digest duration is unavailable") from exc
    if duration_ticks <= 0 or time_base != Fraction(1, sample_rate):
        raise DigestError("PCM content digest duration is invalid")
    return {
        "codecName": stream.get("codec_name"),
        "sampleRate": sample_rate,
        "sourceChannelCount": source_channel_count,
        "sourceChannelLayout": stream.get("channel_layout"),
        "durationSamples": duration_ticks,
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


def _decoded_rgba_sha256_v2(
    path: Path,
    *,
    width: int,
    height: int,
    frame_count: int,
    ffmpeg_path: Path | str = "ffmpeg",
    pass_fds: tuple[int, ...] = (),
) -> tuple[str, int]:
    """Hash identity-oriented RGBA8 frames with a dimension/count-bound header."""

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
        "-noautorotate",
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
    header = json.dumps(
        {
            "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
            "frameCount": frame_count,
            "height": height,
            "pixelMode": "RGBA",
            "width": width,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = sha256()
    digest.update(header)
    digest.update(b"\0")
    byte_count = 0
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
                        pass_fds=pass_fds,
                    )
                except subprocess.SubprocessError as exc:
                    raise DigestError(
                        "decoded-frame pixel digest decode failed"
                    ) from exc
                if completed.returncode != 0:
                    error_output.seek(0)
                    message = error_output.read(8192).decode(
                        "utf-8", "replace"
                    ).strip()
                    raise DigestError(
                        "decoded-frame pixel digest decode failed"
                        + (f": {message}" if message else "")
                    )
                raw_output.seek(0)
                for block in iter(lambda: raw_output.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_count += len(block)
    except DigestError:
        raise
    except OSError as exc:
        raise DigestError("decoded-frame pixel digest decode failed") from exc
    return digest.hexdigest(), byte_count


def _decoded_canonical_pcm_sha256(
    path: Path,
    *,
    source_channel_count: int,
    expected_sample_count: int,
    ffmpeg_path: Path | str = "ffmpeg",
    pass_fds: tuple[int, ...] = (),
) -> tuple[str, int]:
    """Hash headerless 48 kHz stereo s16le under the frozen M12 profile."""

    if (
        isinstance(expected_sample_count, bool)
        or not isinstance(expected_sample_count, int)
        or not 1 <= expected_sample_count <= MAX_CANONICAL_PCM_SAMPLE_COUNT
    ):
        raise DigestError("PCM content digest sample count is invalid")
    if source_channel_count not in {1, 2}:
        raise DigestError("PCM content digest channel count is invalid")
    executable = _executable(ffmpeg_path)
    canonical_filter = (
        "pan=stereo|c0=c0|c1=c0,"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
        if source_channel_count == 1
        else "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
    )
    canonical_filter += f",atrim=end_sample={expected_sample_count}"
    expected_bytes = (
        expected_sample_count * CANONICAL_PCM_CHANNEL_COUNT * 2
    )
    command = [
        str(executable),
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-xerror",
        "-threads", "1",
        "-filter_threads", "1",
        "-filter_complex_threads", "1",
        "-i", str(path),
        "-map", "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af", canonical_filter,
        "-ar", str(CANONICAL_PCM_SAMPLE_RATE),
        "-ac", str(CANONICAL_PCM_CHANNEL_COUNT),
        "-c:a", "pcm_s16le",
        "-fflags", "+bitexact",
        "-flags:a", "+bitexact",
        "-map_metadata", "-1",
        "-fs", str(expected_bytes + CANONICAL_PCM_CHANNEL_COUNT * 2),
        "-f", "s16le",
        "pipe:1",
    ]
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
                        pass_fds=pass_fds,
                    )
                except subprocess.SubprocessError as exc:
                    raise DigestError("PCM content digest decode failed") from exc
                if completed.returncode != 0:
                    error_output.seek(0)
                    message = error_output.read(8192).decode(
                        "utf-8", "replace"
                    ).strip()
                    raise DigestError(
                        "PCM content digest decode failed"
                        + (f": {message}" if message else "")
                    )
                raw_output.seek(0)
                digest_hex, byte_count = _hash_stream(raw_output)
    except DigestError:
        raise
    except OSError as exc:
        raise DigestError("PCM content digest decode failed") from exc
    if byte_count != expected_bytes:
        raise DigestError("PCM content digest decoded byte count is invalid")
    return digest_hex, byte_count


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


def decoded_frame_pixel_digest_metadata(
    path: Path | str,
    *,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
    pass_fds: tuple[int, ...] = (),
) -> dict[str, object]:
    """Return v2 file and decoded-frame identity for one transform-free video."""

    candidate = _require_file(path)
    probe = _probe_identity_video_stream(
        candidate,
        ffprobe_path=ffprobe_path,
        pass_fds=pass_fds,
    )
    pixel_hex, byte_count = _decoded_rgba_sha256_v2(
        candidate,
        width=probe["width"],
        height=probe["height"],
        frame_count=probe["frameCount"],
        ffmpeg_path=ffmpeg_path,
        pass_fds=pass_fds,
    )
    expected_bytes = (
        probe["width"] * probe["height"] * 4 * probe["frameCount"]
    )
    if byte_count != expected_bytes:
        raise DigestError(
            "decoded-frame pixel digest decoded byte count is invalid"
        )
    return {
        "fileDigest": file_digest(candidate),
        "fileDigestAlgorithm": DIGEST_ALGORITHM,
        "decodedFramePixelDigest": f"{DIGEST_ALGORITHM}:{pixel_hex}",
        "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
        "pixelMode": "RGBA",
        "width": probe["width"],
        "height": probe["height"],
        "frameCount": probe["frameCount"],
    }


def canonical_pcm_digest_metadata(
    path: Path | str,
    *,
    expected_sample_count: int,
    allow_aac_frame_padding: bool = False,
    ffmpeg_path: Path | str = "ffmpeg",
    ffprobe_path: Path | str = "ffprobe",
    pass_fds: tuple[int, ...] = (),
    _input_descriptor: int | None = None,
) -> dict[str, object]:
    """Return frozen M12-compatible PCM identity for one audible stream.

    The digest is intentionally the unprefixed hexadecimal form already owned
    by ``pcmContentDigest``.  The accompanying closed spec removes any
    ambiguity about rate, layout, sample order, or container metadata.  The
    explicit AAC opt-in tolerates at most one codec frame of container-level
    duration padding; the decoded projection is still trimmed and byte-counted
    to exactly ``expected_sample_count`` samples.
    """

    if (
        isinstance(expected_sample_count, bool)
        or not isinstance(expected_sample_count, int)
        or not 1 <= expected_sample_count <= MAX_CANONICAL_PCM_SAMPLE_COUNT
        or type(allow_aac_frame_padding) is not bool
        or (
            _input_descriptor is not None
            and (
                isinstance(_input_descriptor, bool)
                or not isinstance(_input_descriptor, int)
                or _input_descriptor < 0
            )
        )
    ):
        raise DigestError("PCM content digest request is invalid")
    candidate = Path(path)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise DigestError("PCM content digest no-follow support is unavailable")
    flags = os.O_RDONLY | no_follow
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    descriptor: int | None = None
    identity_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    try:
        descriptor = (
            os.dup(_input_descriptor)
            if _input_descriptor is not None
            else os.open(candidate, flags)
        )
        before = os.fstat(descriptor)
        entry_before = os.stat(candidate, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or any(
                getattr(before, field) != getattr(entry_before, field)
                for field in identity_fields
            )
        ):
            raise DigestError("PCM content digest input is not a stable regular file")
        descriptor_path = Path(f"/proc/self/fd/{descriptor}")
        if not descriptor_path.exists():
            raise DigestError(
                "PCM content digest descriptor projection is unavailable"
            )
        inherited = tuple(dict.fromkeys((descriptor, *pass_fds)))
        probe = _probe_audio_stream(
            descriptor_path,
            ffprobe_path=ffprobe_path,
            pass_fds=inherited,
        )
        duration_delta = abs(probe["durationSamples"] - expected_sample_count)
        if duration_delta != 0 and not (
            allow_aac_frame_padding
            and probe["codecName"] == "aac"
            and duration_delta <= _AAC_FRAME_SAMPLE_COUNT
        ):
            raise DigestError("PCM content digest duration does not match request")
        digest_hex, byte_count = _decoded_canonical_pcm_sha256(
            descriptor_path,
            source_channel_count=probe["sourceChannelCount"],
            expected_sample_count=expected_sample_count,
            ffmpeg_path=ffmpeg_path,
            pass_fds=inherited,
        )
        after = os.fstat(descriptor)
        entry_after = os.stat(candidate, follow_symlinks=False)
        if any(
            getattr(before, field) != getattr(after, field)
            or getattr(before, field) != getattr(entry_after, field)
            for field in identity_fields
        ):
            raise DigestError("PCM content digest input changed while measuring")
    except DigestError:
        raise
    except OSError as exc:
        raise DigestError("PCM content digest input is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return {
        "pcmContentDigest": digest_hex,
        "pcmDigestSpec": json.loads(
            json.dumps(
                _PCM_CONTENT_DIGEST_SPEC_TEMPLATE,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
        "sampleRate": CANONICAL_PCM_SAMPLE_RATE,
        "channelCount": CANONICAL_PCM_CHANNEL_COUNT,
        "sampleCount": expected_sample_count,
        "decodedByteCount": byte_count,
        "sourceCodecName": probe["codecName"],
        "sourceChannelCount": probe["sourceChannelCount"],
    }
