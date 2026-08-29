"""Deterministic FFmpeg timeline composition owned by V3 Render Core."""

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
from typing import Any, Mapping

from .digests import (
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    file_digest,
    image_digest_metadata,
    video_digest_metadata,
)


class RenderArtifactError(RuntimeError):
    pass


_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GLYPH_COMPOSER_IDENTITY = "v3.deterministic-glyph-reveal-ffmpeg.v1"
_GLYPH_BLEND_MODE = "GRAZING_LIGHT_RELIEF"
_SUPPORTED_GLYPH_BASE_PIXEL_FORMATS = {"yuv420p", "yuv422p", "yuv444p"}


def _scope_path(root: Path, workspace_ref: str, run_ref: str) -> Path:
    workspace_hash = sha256(workspace_ref.encode()).hexdigest()[:20]
    run_hash = sha256(run_ref.encode()).hexdigest()[:20]
    result = (root / workspace_hash / run_hash).resolve()
    if root not in result.parents:
        raise RenderArtifactError("composition scope escaped artifact root")
    return result


def _glyph_scope_path(root: Path, workspace_ref: str, run_ref: str) -> Path:
    """Return a lexical glyph scope so symlink components remain observable."""

    workspace_hash = sha256(workspace_ref.encode()).hexdigest()[:20]
    run_hash = sha256(run_ref.encode()).hexdigest()[:20]
    return root / workspace_hash / run_hash


def _scope_root(root: Path, workspace_ref: str, run_ref: str) -> Path:
    result = _scope_path(root, workspace_ref, run_ref)
    result.mkdir(parents=True, exist_ok=True)
    return result


def _safe_input(root: Path, storage_key: str) -> Path:
    if not isinstance(storage_key, str) or not storage_key:
        raise RenderArtifactError("composition input storage key is invalid")
    path = (root / storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise RenderArtifactError("composition input escaped artifact root")
    return path


def _probe(
    path: Path,
    *,
    ffprobe_path: Path | str = "ffprobe",
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                str(ffprobe_path), "-v", "error", "-count_frames", "-show_streams",
                "-show_format", "-of", "json", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise RenderArtifactError("composed artifact probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        raise RenderArtifactError("composed artifact has no streams")
    return {
        "streams": [
            {
                key: stream.get(key)
                for key in (
                    "codec_type", "codec_name", "width", "height", "pix_fmt",
                    "avg_frame_rate", "nb_frames", "nb_read_frames", "sample_rate",
                    "channels", "duration",
                )
                if stream.get(key) is not None
            }
            for stream in streams
            if isinstance(stream, Mapping)
        ],
        "formatName": payload.get("format", {}).get("format_name"),
        "durationSeconds": payload.get("format", {}).get("duration"),
    }


def _fixed_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update({"LANG": "C", "LC_ALL": "C", "TZ": "UTC"})
    return environment


def _runtime_path(name: str) -> Path:
    candidate = shutil.which(name)
    if candidate is None:
        raise RenderArtifactError(f"{name} runtime is unavailable")
    resolved = Path(candidate).resolve()
    if not resolved.is_file():
        raise RenderArtifactError(f"{name} runtime is unavailable")
    return resolved


def _runtime_version(executable: Path) -> str:
    try:
        result = subprocess.run(
            [str(executable), "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=_fixed_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RenderArtifactError("FFmpeg runtime identity is unavailable") from exc
    first_line = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
    if not first_line:
        raise RenderArtifactError("FFmpeg runtime identity is unavailable")
    return first_line


def _closed_mapping(
    value: object,
    expected_keys: set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise RenderArtifactError(f"{label} contract is invalid")
    if not all(isinstance(key, str) for key in value):
        raise RenderArtifactError(f"{label} contract is invalid")
    return value


def _integer(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _point(value: object, *, label: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise RenderArtifactError(f"{label} is invalid")
    return (
        _integer(value[0], label=f"{label} x"),
        _integer(value[1], label=f"{label} y"),
    )


def _safe_glyph_input(root: Path, storage_key: object) -> Path:
    if (
        not isinstance(storage_key, str)
        or not storage_key
        or storage_key != storage_key.strip()
        or "\\" in storage_key
    ):
        raise RenderArtifactError("glyph input storage key is invalid")
    relative = Path(storage_key)
    if relative.is_absolute() or ".." in relative.parts:
        raise RenderArtifactError("glyph input escaped artifact root")
    unresolved = root / relative
    current = root
    try:
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RenderArtifactError("glyph input symlinks are forbidden")
        resolved = unresolved.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RenderArtifactError("glyph input is unavailable") from exc
    if root not in resolved.parents:
        raise RenderArtifactError("glyph input escaped artifact root")
    try:
        mode = resolved.stat().st_mode
    except OSError as exc:
        raise RenderArtifactError("glyph input is unavailable") from exc
    if not stat.S_ISREG(mode):
        raise RenderArtifactError("glyph input is not a regular file")
    return resolved


def _file_state(path: Path) -> tuple[int, int, int, int, int]:
    try:
        value = path.stat()
    except OSError as exc:
        raise RenderArtifactError("glyph input is unavailable") from exc
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
    )


def _stage_digest_pinned_input(
    source: Path,
    destination: Path,
    expected_digest: object,
) -> None:
    """Copy one pinned regular file through an already-open no-follow handle."""

    if not isinstance(expected_digest, str) or (
        _PREFIXED_DIGEST.fullmatch(expected_digest) is None
    ):
        raise RenderArtifactError("glyph input file digest is invalid")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RenderArtifactError("glyph input no-follow support is unavailable")
    source_flags = os.O_RDONLY | no_follow
    destination_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow
    if hasattr(os, "O_CLOEXEC"):
        source_flags |= os.O_CLOEXEC
        destination_flags |= os.O_CLOEXEC
    try:
        source_descriptor = os.open(source, source_flags)
    except OSError as exc:
        raise RenderArtifactError("glyph input could not be opened safely") from exc
    destination_descriptor: int | None = None
    try:
        source_state = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_state.st_mode):
            raise RenderArtifactError("glyph input is not a regular file")
        destination_descriptor = os.open(
            destination,
            destination_flags,
            0o600,
        )
        digest = sha256()
        byte_count = 0
        with os.fdopen(source_descriptor, "rb", closefd=False) as source_stream:
            with os.fdopen(
                destination_descriptor, "wb", closefd=False
            ) as destination_stream:
                for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_count += len(block)
                    destination_stream.write(block)
                destination_stream.flush()
                os.fsync(destination_descriptor)
        after = os.fstat(source_descriptor)
        if (
            source_state.st_dev,
            source_state.st_ino,
            source_state.st_mode,
            source_state.st_size,
            source_state.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise RenderArtifactError("glyph input changed while staging")
        actual_digest = f"sha256:{digest.hexdigest()}"
        if byte_count != source_state.st_size or actual_digest != expected_digest:
            raise RenderArtifactError("glyph input file digest changed")
        try:
            copied_digest = file_digest(destination)
        except DigestError as exc:
            raise RenderArtifactError("staged glyph input digest failed") from exc
        if copied_digest != expected_digest:
            raise RenderArtifactError("staged glyph input digest changed")
    except OSError as exc:
        raise RenderArtifactError("glyph input staging failed") from exc
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        os.close(source_descriptor)


def _secure_output_directory(root: Path, directory: Path) -> Path:
    """Create a scoped directory while rejecting symlink path components."""

    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise RenderArtifactError("glyph output escaped artifact root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        try:
            mode = current.lstat().st_mode
        except OSError as exc:
            raise RenderArtifactError("glyph output directory is unavailable") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise RenderArtifactError("glyph output directory symlinks are forbidden")
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RenderArtifactError("glyph output directory is unavailable") from exc
    if resolved != directory or root not in resolved.parents:
        raise RenderArtifactError("glyph output escaped artifact root")
    return resolved


def _decoded_opaque_grayscale_png_pixels(
    path: Path,
    *,
    ffmpeg_path: Path,
    width: int,
    height: int,
) -> bytes:
    """Return the exact gray plane used by V3 after rejecting hidden alpha.

    The compositor converts masks with FFmpeg's ``format=gray`` filter, so the
    cumulative contract must be checked against that same decoded gray signal.
    Requiring opaque alpha prevents distinct RGBA digests from masquerading as
    distinct reveal stages while producing identical gray input to the filter.
    """

    def decode(pixel_format: str, *, gray_filter: bool = False) -> bytes:
        command = [
            str(ffmpeg_path),
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
        ]
        if gray_filter:
            command.extend(["-vf", "format=gray"])
        command.extend(
            [
                "-frames:v", "1",
                "-c:v", "rawvideo",
                "-flags:v", "+bitexact",
                "-fps_mode", "passthrough",
                "-f", "rawvideo",
                "-pix_fmt", pixel_format,
                "pipe:1",
            ]
        )
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=180,
                env=_fixed_environment(),
            ).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            raise RenderArtifactError("glyph mask pixel decode failed") from exc

    pixels = decode("rgba")
    if len(pixels) != width * height * 4:
        raise RenderArtifactError("glyph mask decoded byte count is invalid")
    red = pixels[0::4]
    if red != pixels[1::4] or red != pixels[2::4]:
        raise RenderArtifactError("glyph mask pixels are not grayscale")
    if pixels[3::4] != b"\xff" * (width * height):
        raise RenderArtifactError("glyph mask alpha must be fully opaque")
    gray = decode("gray", gray_filter=True)
    if len(gray) != width * height:
        raise RenderArtifactError("glyph mask gray byte count is invalid")
    return gray


def _validate_cumulative_gray_stage(
    previous: bytes | None,
    current: bytes,
) -> None:
    """Reject duplicate or regressing decoded cumulative-mask stages."""

    if previous is None:
        return
    increased = False
    for before, after in zip(previous, current, strict=True):
        if after < before:
            raise RenderArtifactError("glyph cumulative mask coverage regressed")
        if after > before:
            increased = True
    if not increased:
        raise RenderArtifactError("glyph cumulative mask stage did not advance")


def _glyph_probe(path: Path, ffprobe_path: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                str(ffprobe_path),
                "-v", "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of", "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
            env=_fixed_environment(),
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise RenderArtifactError("glyph input probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or not all(
        isinstance(stream, Mapping) for stream in streams
    ):
        raise RenderArtifactError("glyph input stream metadata is invalid")
    format_value = payload.get("format")
    if not isinstance(format_value, Mapping):
        raise RenderArtifactError("glyph input format metadata is invalid")
    return {"streams": streams, "format": format_value}


def _one_video_stream(probe: Mapping[str, Any], *, label: str) -> Mapping[str, Any]:
    streams = probe.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise RenderArtifactError(f"{label} must contain exactly one video stream")
    stream = streams[0]
    if not isinstance(stream, Mapping) or stream.get("codec_type") != "video":
        raise RenderArtifactError(f"{label} must contain exactly one video stream")
    return stream


def _stream_integer(stream: Mapping[str, Any], key: str, *, label: str) -> int:
    try:
        result = int(stream[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RenderArtifactError(f"{label} is unavailable") from exc
    if result <= 0:
        raise RenderArtifactError(f"{label} is invalid")
    return result


def _stream_frame_count(stream: Mapping[str, Any], *, label: str) -> int:
    value = stream.get("nb_read_frames") or stream.get("nb_frames")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError(f"{label} frame count is unavailable") from exc
    if result <= 0:
        raise RenderArtifactError(f"{label} frame count is invalid")
    return result


def _stream_frame_rate(stream: Mapping[str, Any], *, label: str) -> Fraction:
    try:
        average = Fraction(str(stream["avg_frame_rate"]))
        nominal = Fraction(str(stream["r_frame_rate"]))
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise RenderArtifactError(f"{label} frame rate is unavailable") from exc
    if average <= 0 or nominal <= 0 or average != nominal:
        raise RenderArtifactError(f"{label} must use a constant frame rate")
    return average


def _validate_composite_params(
    value: object,
    *,
    canvas_width: int,
    canvas_height: int,
) -> dict[str, Any]:
    params = _closed_mapping(
        value,
        {"position", "scale", "perspective", "blendMode"},
        label="glyph composite parameters",
    )
    if params["blendMode"] != _GLYPH_BLEND_MODE:
        raise RenderArtifactError("glyph blend mode is invalid")
    position = _closed_mapping(
        params["position"], {"xPixels", "yPixels"}, label="glyph position"
    )
    scale = _closed_mapping(
        params["scale"], {"widthPixels", "heightPixels"}, label="glyph scale"
    )
    perspective = _closed_mapping(
        params["perspective"],
        {"topLeft", "topRight", "bottomLeft", "bottomRight"},
        label="glyph perspective",
    )
    x = _integer(position["xPixels"], label="glyph x position")
    y = _integer(position["yPixels"], label="glyph y position")
    width = _integer(scale["widthPixels"], label="glyph width", minimum=2)
    height = _integer(scale["heightPixels"], label="glyph height", minimum=2)
    if x + width > canvas_width or y + height > canvas_height:
        raise RenderArtifactError("glyph scale escaped base plate canvas")
    points = {
        key: _point(perspective[key], label=f"glyph perspective {key}")
        for key in ("topLeft", "topRight", "bottomLeft", "bottomRight")
    }
    for point_x, point_y in points.values():
        if point_x >= width or point_y >= height:
            raise RenderArtifactError("glyph perspective escaped scaled canvas")
        if x + point_x > canvas_width or y + point_y > canvas_height:
            raise RenderArtifactError("glyph perspective escaped base plate canvas")
    top_left = points["topLeft"]
    top_right = points["topRight"]
    bottom_left = points["bottomLeft"]
    bottom_right = points["bottomRight"]
    if not (
        top_left[0] < top_right[0]
        and bottom_left[0] < bottom_right[0]
        and top_left[1] < bottom_left[1]
        and top_right[1] < bottom_right[1]
    ):
        raise RenderArtifactError("glyph perspective corner ordering is invalid")
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "points": points,
    }


def _stage_ranges(start: int, end: int, count: int) -> list[tuple[int, int | None]]:
    length = end - start
    result: list[tuple[int, int | None]] = []
    for index in range(count):
        stage_start = start + (index * length + count - 1) // count
        if index == count - 1:
            result.append((stage_start, None))
        else:
            stage_end = start + ((index + 1) * length + count - 1) // count
            result.append((stage_start, stage_end - 1))
    return result


def _glyph_filter_graph(
    *,
    stage_count: int,
    stage_ranges: list[tuple[int, int | None]],
    frame_rate: int,
    canvas_width: int,
    canvas_height: int,
    base_pixel_format: str,
    geometry: Mapping[str, Any],
) -> str:
    width = geometry["width"]
    height = geometry["height"]
    x = geometry["x"]
    y = geometry["y"]
    points = geometry["points"]
    perspective_options = ":".join(
        (
            f"x0={points['topLeft'][0]}",
            f"y0={points['topLeft'][1]}",
            f"x1={points['topRight'][0]}",
            f"y1={points['topRight'][1]}",
            f"x2={points['bottomLeft'][0]}",
            f"y2={points['bottomLeft'][1]}",
            f"x3={points['bottomRight'][0]}",
            f"y3={points['bottomRight'][1]}",
            "sense=destination",
            "interpolation=linear",
            "eval=init",
        )
    )
    # A zero-sum, fixed upper-left/lower-right kernel turns the cumulative
    # binary mask into a neutral-gray relief map.  grainmerge then changes
    # local plate luminance instead of painting colored glyph pixels.
    relief_kernel = "-1 -1 0 -1 0 1 0 1 1"
    filters = [f"[0:v]settb=expr=1/{frame_rate},setpts=N[base0]"]
    for index in range(stage_count):
        filters.append(
            f"[{index + 1}:v]"
            f"settb=expr=1/{frame_rate},setpts=N,"
            "format=gray,"
            f"scale={width}:{height}:flags=neighbor:"
            "in_range=full:out_range=full,"
            f"perspective={perspective_options},"
            f"convolution=0m='{relief_kernel}':0rdiv=1:0bias=128,"
            f"pad={canvas_width}:{canvas_height}:{x}:{y}:color=0x808080,"
            f"format={base_pixel_format}[stage{index}]"
        )
    previous = "base0"
    roi_expression = (
        f"if(between(X,{x},{x + width - 1})*"
        f"between(Y,{y},{y + height - 1}),A+B-128,A)"
    )
    for index, (stage_start, stage_end) in enumerate(stage_ranges):
        output_label = f"blend{index}"
        if stage_end is None:
            enable = f"gte(n,{stage_start})"
        else:
            enable = f"between(n,{stage_start},{stage_end})"
        filters.append(
            f"[{previous}][stage{index}]"
            f"blend=c0_expr='{roi_expression}':c1_expr='A':c2_expr='A':"
            f"enable='{enable}'[{output_label}]"
        )
        previous = output_label
    filters.append(f"[{previous}]format={base_pixel_format}[vout]")
    return ";".join(filters)


def _validate_glyph_output(
    path: Path,
    *,
    ffprobe_path: Path,
    width: int,
    height: int,
    frame_rate: int,
    frame_count: int,
    pixel_format: str,
) -> None:
    stream = _one_video_stream(
        _glyph_probe(path, ffprobe_path), label="glyph output"
    )
    if stream.get("codec_name") != "h264":
        raise RenderArtifactError("glyph output codec is invalid")
    if (
        _stream_integer(stream, "width", label="glyph output width") != width
        or _stream_integer(stream, "height", label="glyph output height") != height
        or _stream_frame_count(stream, label="glyph output") != frame_count
        or _stream_frame_rate(stream, label="glyph output") != Fraction(frame_rate, 1)
        or stream.get("pix_fmt") != pixel_format
    ):
        raise RenderArtifactError("glyph output media contract is invalid")


class DeterministicFfmpegComposer:
    composer_identity = "v3.deterministic-ffmpeg-composer.v1"

    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _artifact(self, path: Path) -> dict[str, Any]:
        content = path.read_bytes()
        return {
            "internalPath": str(path),
            "storageKey": str(path.relative_to(self.artifact_root)),
            "byteSize": len(content),
            "sha256": sha256(content).hexdigest(),
            "probe": _probe(path),
            "composerIdentity": self.composer_identity,
        }

    def _glyph_artifact(
        self,
        path: Path,
        *,
        requirement_digest: str,
        execution_request_digest: str,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        ffmpeg_version: str,
        ffprobe_version: str,
        width: int,
        height: int,
        frame_rate: int,
        frame_count: int,
        pixel_format: str,
    ) -> dict[str, Any]:
        _validate_glyph_output(
            path,
            ffprobe_path=ffprobe_path,
            width=width,
            height=height,
            frame_rate=frame_rate,
            frame_count=frame_count,
            pixel_format=pixel_format,
        )
        before = _file_state(path)
        try:
            output_digest = video_digest_metadata(
                path,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
            )
        except DigestError as exc:
            raise RenderArtifactError("glyph output digest failed") from exc
        if _file_state(path) != before:
            raise RenderArtifactError("glyph output changed during digest")
        file_value = output_digest["fileDigest"]
        if not isinstance(file_value, str) or not file_value.startswith("sha256:"):
            raise RenderArtifactError("glyph output file digest is invalid")
        if (
            output_digest.get("width") != width
            or output_digest.get("height") != height
            or output_digest.get("frameCount") != frame_count
        ):
            raise RenderArtifactError("glyph output digest media contract is invalid")
        runtime_payload = json.dumps(
            {
                "ffmpegVersion": ffmpeg_version,
                "ffprobeVersion": ffprobe_version,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        runtime_identity = (
            "sha256:" + sha256(runtime_payload.encode("utf-8")).hexdigest()
        )
        return {
            "internalPath": str(path),
            "storageKey": str(path.relative_to(self.artifact_root)),
            "byteSize": path.stat().st_size,
            "sha256": file_value.removeprefix("sha256:"),
            "probe": _probe(path, ffprobe_path=ffprobe_path),
            "composerIdentity": _GLYPH_COMPOSER_IDENTITY,
            "requirementDigest": requirement_digest,
            "executionRequestDigest": execution_request_digest,
            "runtimeIdentity": runtime_identity,
            "ffmpegVersion": ffmpeg_version,
            "ffprobeVersion": ffprobe_version,
            "publicationAllowed": False,
            "outputDigest": output_digest,
        }

    def compose_glyph_reveal(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        requirement_digest: str,
        execution_request_digest: str,
        base_plate: Mapping[str, Any],
        masks: list[Mapping[str, Any]],
        frame_range_start: int,
        frame_range_end: int,
        reveal_frame_count: int,
        composite_params: Mapping[str, Any],
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Composite a digest-pinned, progressive no-pigment glyph relief.

        ``frame_range_end`` is exclusive.  The reveal stages partition that
        interval deterministically; the final cumulative mask remains active
        for all later frames in the base plate.
        """

        if not isinstance(workspace_ref, str) or not workspace_ref:
            raise RenderArtifactError("glyph workspace reference is invalid")
        if not isinstance(run_ref, str) or not run_ref:
            raise RenderArtifactError("glyph run reference is invalid")
        if (
            not isinstance(requirement_digest, str)
            or _HEX_DIGEST.fullmatch(requirement_digest) is None
        ):
            raise RenderArtifactError("glyph requirement digest is invalid")
        if (
            not isinstance(execution_request_digest, str)
            or _HEX_DIGEST.fullmatch(execution_request_digest) is None
        ):
            raise RenderArtifactError("glyph execution request digest is invalid")
        count = _integer(
            reveal_frame_count, label="glyph reveal frame count", minimum=1
        )
        if not isinstance(masks, list) or len(masks) != count:
            raise RenderArtifactError("glyph mask count does not match reveal count")
        start = _integer(frame_range_start, label="glyph frame range start")
        end = _integer(frame_range_end, label="glyph frame range end", minimum=1)
        if end <= start or end - start < count:
            raise RenderArtifactError("glyph frame range is invalid")

        base_record = _closed_mapping(
            base_plate,
            {"storageKey", "fileDigest"},
            label="glyph base plate",
        )
        output_record = _closed_mapping(
            output,
            {"width", "height", "frameRate", "totalFrames"},
            label="glyph output",
        )
        ffmpeg_path = _runtime_path("ffmpeg")
        ffprobe_path = _runtime_path("ffprobe")
        ffmpeg_version = _runtime_version(ffmpeg_path)
        ffprobe_version = _runtime_version(ffprobe_path)

        base_source = _safe_glyph_input(
            self.artifact_root, base_record["storageKey"]
        )
        frame_rate = _integer(
            output_record["frameRate"], label="glyph output frame rate", minimum=1
        )
        output_width = _integer(
            output_record["width"], label="glyph output width", minimum=1
        )
        output_height = _integer(
            output_record["height"], label="glyph output height", minimum=1
        )
        output_frames = _integer(
            output_record["totalFrames"],
            label="glyph output frame count",
            minimum=1,
        )

        root = _glyph_scope_path(self.artifact_root, workspace_ref, run_ref)
        output_name = f"glyph-reveal-{execution_request_digest}.mp4"
        with tempfile.TemporaryDirectory(
            prefix=".glyph-reveal-work-",
            dir=self.artifact_root,
            ignore_cleanup_errors=True,
        ) as temporary_directory:
            work_root = Path(temporary_directory)
            work_root.chmod(0o700)
            input_root = work_root / "inputs"
            input_root.mkdir(mode=0o700)
            base_path = input_root / "base-plate.media"
            _stage_digest_pinned_input(
                base_source,
                base_path,
                base_record["fileDigest"],
            )
            base_probe = _glyph_probe(base_path, ffprobe_path)
            base_stream = _one_video_stream(base_probe, label="glyph base plate")
            if base_stream.get("side_data_list") or (
                isinstance(base_stream.get("tags"), Mapping)
                and str(base_stream["tags"].get("rotate", "0")) != "0"
            ):
                raise RenderArtifactError(
                    "glyph base plate display transform is unsupported"
                )
            base_pixel_format = base_stream.get("pix_fmt")
            if base_pixel_format not in _SUPPORTED_GLYPH_BASE_PIXEL_FORMATS:
                raise RenderArtifactError(
                    "glyph base plate pixel format is unsupported"
                )
            base_width = _stream_integer(
                base_stream, "width", label="glyph base plate width"
            )
            base_height = _stream_integer(
                base_stream, "height", label="glyph base plate height"
            )
            base_frames = _stream_frame_count(base_stream, label="glyph base plate")
            base_rate = _stream_frame_rate(base_stream, label="glyph base plate")
            if base_rate.denominator != 1:
                raise RenderArtifactError(
                    "glyph base plate frame rate must be integral"
                )
            if (
                output_width != base_width
                or output_height != base_height
                or output_frames != base_frames
                or Fraction(frame_rate, 1) != base_rate
            ):
                raise RenderArtifactError(
                    "glyph output does not match base plate media"
                )
            if end > base_frames:
                raise RenderArtifactError("glyph frame range exceeds base plate")

            geometry = _validate_composite_params(
                composite_params,
                canvas_width=base_width,
                canvas_height=base_height,
            )
            mask_paths: list[Path] = []
            mask_dimensions: tuple[int, int] | None = None
            seen_pixel_digests: set[str] = set()
            seen_gray_stages: set[bytes] = set()
            previous_gray_stage: bytes | None = None
            for index, mask in enumerate(masks):
                mask_record = _closed_mapping(
                    mask,
                    {
                        "storageKey",
                        "fileDigest",
                        "pixelDigest",
                        "pixelDigestSpec",
                        "width",
                        "height",
                    },
                    label=f"glyph mask {index}",
                )
                if mask_record["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC:
                    raise RenderArtifactError(
                        "glyph mask pixel digest spec is invalid"
                    )
                expected_pixel = mask_record["pixelDigest"]
                if (
                    not isinstance(expected_pixel, str)
                    or _PREFIXED_DIGEST.fullmatch(expected_pixel) is None
                ):
                    raise RenderArtifactError("glyph mask pixel digest is invalid")
                declared_dimensions = (
                    _integer(
                        mask_record["width"],
                        label=f"glyph mask {index} declared width",
                        minimum=1,
                    ),
                    _integer(
                        mask_record["height"],
                        label=f"glyph mask {index} declared height",
                        minimum=1,
                    ),
                )
                storage_key = mask_record["storageKey"]
                if (
                    not isinstance(storage_key, str)
                    or Path(storage_key).suffix.lower() != ".png"
                ):
                    raise RenderArtifactError("glyph mask must use PNG storage")
                mask_source = _safe_glyph_input(
                    self.artifact_root, storage_key
                )
                mask_path = input_root / f"mask-{index + 1:04d}.png"
                _stage_digest_pinned_input(
                    mask_source,
                    mask_path,
                    mask_record["fileDigest"],
                )
                mask_probe = _glyph_probe(mask_path, ffprobe_path)
                mask_stream = _one_video_stream(mask_probe, label="glyph mask")
                if (
                    mask_stream.get("codec_name") != "png"
                    or mask_probe["format"].get("format_name") != "png_pipe"
                    or _stream_frame_count(mask_stream, label="glyph mask") != 1
                ):
                    raise RenderArtifactError(
                        "glyph mask must be a one-frame PNG image"
                    )
                dimensions = (
                    _stream_integer(
                        mask_stream, "width", label="glyph mask width"
                    ),
                    _stream_integer(
                        mask_stream, "height", label="glyph mask height"
                    ),
                )
                if dimensions != declared_dimensions:
                    raise RenderArtifactError(
                        "glyph mask dimensions changed from the execution request"
                    )
                if mask_dimensions is None:
                    mask_dimensions = dimensions
                elif dimensions != mask_dimensions:
                    raise RenderArtifactError(
                        "glyph mask dimensions do not match"
                    )
                try:
                    pixel_metadata = image_digest_metadata(
                        mask_path,
                        ffmpeg_path=ffmpeg_path,
                        ffprobe_path=ffprobe_path,
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        "glyph mask pixel digest failed"
                    ) from exc
                if (
                    pixel_metadata["pixel_digest"] != expected_pixel
                    or pixel_metadata["pixel_digest_spec"]
                    != IMAGE_PIXEL_DIGEST_SPEC
                    or (
                        pixel_metadata["width"], pixel_metadata["height"]
                    )
                    != dimensions
                ):
                    raise RenderArtifactError("glyph mask pixel digest changed")
                actual_pixel_digest = str(pixel_metadata["pixel_digest"])
                if actual_pixel_digest in seen_pixel_digests:
                    raise RenderArtifactError(
                        "glyph mask pixel digests must be unique"
                    )
                gray_stage = _decoded_opaque_grayscale_png_pixels(
                    mask_path,
                    ffmpeg_path=ffmpeg_path,
                    width=dimensions[0],
                    height=dimensions[1],
                )
                if gray_stage in seen_gray_stages:
                    raise RenderArtifactError(
                        "glyph decoded gray stages must be unique"
                    )
                _validate_cumulative_gray_stage(previous_gray_stage, gray_stage)
                seen_pixel_digests.add(actual_pixel_digest)
                seen_gray_stages.add(gray_stage)
                previous_gray_stage = gray_stage
                mask_paths.append(mask_path)

            stage_ranges = _stage_ranges(start, end, count)
            filter_graph = _glyph_filter_graph(
                stage_count=count,
                stage_ranges=stage_ranges,
                frame_rate=frame_rate,
                canvas_width=base_width,
                canvas_height=base_height,
                base_pixel_format=base_pixel_format,
                geometry=geometry,
            )
            candidate = work_root / "candidate.mp4"
            command = [
                str(ffmpeg_path),
                "-hide_banner",
                "-loglevel", "error",
                "-xerror",
                "-nostdin",
                "-threads", "1",
                "-filter_threads", "1",
                "-filter_complex_threads", "1",
                "-sws_flags", "bitexact+accurate_rnd+full_chroma_int",
                "-hwaccel", "none",
                "-autorotate", "1",
                "-i", str(base_path),
            ]
            for mask_path in mask_paths:
                command.extend(
                    [
                        "-loop", "1",
                        "-framerate", str(frame_rate),
                        "-i", str(mask_path),
                    ]
                )
            command.extend(
                [
                    "-filter_complex", filter_graph,
                    "-map", "[vout]",
                    "-an",
                    "-frames:v", str(base_frames),
                    "-fps_mode", "passthrough",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "0",
                    "-pix_fmt", base_pixel_format,
                    "-threads:v", "1",
                    "-x264-params",
                    (
                        "threads=1:lookahead_threads=1:sliced_threads=0:"
                        "sync-lookahead=0:rc-lookahead=0:scenecut=0"
                    ),
                    "-fflags", "+bitexact",
                    "-flags:v", "+bitexact",
                    "-map_metadata", "-1",
                    "-map_chapters", "-1",
                    "-metadata", "creation_time=1970-01-01T00:00:00Z",
                    "-movflags", "+faststart",
                    "-video_track_timescale", str(frame_rate * 512),
                    "-n", str(candidate),
                ]
            )
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    timeout=300,
                    env=_fixed_environment(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RenderArtifactError(
                    "FFmpeg glyph reveal composition failed"
                ) from exc
            artifact = self._glyph_artifact(
                candidate,
                requirement_digest=requirement_digest,
                execution_request_digest=execution_request_digest,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                ffmpeg_version=ffmpeg_version,
                ffprobe_version=ffprobe_version,
                width=base_width,
                height=base_height,
                frame_rate=frame_rate,
                frame_count=base_frames,
                pixel_format=base_pixel_format,
            )
            output_directory = _secure_output_directory(
                self.artifact_root, root / "glyph-reveal"
            )
            destination = output_directory / output_name
            try:
                destination.lstat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise RenderArtifactError(
                    "glyph output path is unavailable"
                ) from exc
            else:
                raise RenderArtifactError("glyph output already exists")
            try:
                os.link(candidate, destination, follow_symlinks=False)
            except FileExistsError as exc:
                raise RenderArtifactError("glyph output already exists") from exc
            except OSError as exc:
                raise RenderArtifactError(
                    "glyph output could not be published atomically"
                ) from exc
            artifact["internalPath"] = str(destination)
            artifact["storageKey"] = str(
                destination.relative_to(self.artifact_root)
            )
            return artifact

    def compose(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        timeline_digest: str,
        items: list[Mapping[str, Any]],
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not items:
            raise RenderArtifactError("timeline has no composition items")
        root = _scope_root(self.artifact_root, workspace_ref, run_ref)
        destination = root / "composition" / f"preview-{timeline_digest}.mp4"
        if destination.is_file():
            return self._artifact(destination)
        videos: list[Path] = []
        audios: list[Path] = []
        for item in items:
            videos.append(_safe_input(self.artifact_root, item["videoStorageKey"]))
            audios.append(_safe_input(self.artifact_root, item["audioStorageKey"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.stem}.part.mp4")
        command = ["ffmpeg", "-v", "error"]
        for video, audio in zip(videos, audios):
            command.extend(["-i", str(video), "-i", str(audio)])
        concat_inputs = "".join(
            f"[{index * 2}:v:0][{index * 2 + 1}:a:0]"
            for index in range(len(items))
        )
        command.extend(
            [
                "-filter_complex",
                f"{concat_inputs}concat=n={len(items)}:v=1:a=1[outv][outa]",
                "-map", "[outv]", "-map", "[outa]", "-r",
                str(output["frameRate"]), "-c:v", "libx264", "-preset",
                "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a",
                "128k", "-movflags", "+faststart", "-y", str(temporary),
            ]
        )
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=180)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            if temporary.exists():
                temporary.unlink()
            raise RenderArtifactError("FFmpeg timeline composition failed") from exc
        probe = _probe(temporary)
        video_streams = [
            stream for stream in probe["streams"] if stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream for stream in probe["streams"] if stream.get("codec_type") == "audio"
        ]
        if len(video_streams) != 1 or len(audio_streams) != 1:
            temporary.unlink(missing_ok=True)
            raise RenderArtifactError("preview stream layout is invalid")
        video = video_streams[0]
        frame_count = video.get("nb_read_frames") or video.get("nb_frames")
        try:
            actual_frames = int(frame_count)
        except (TypeError, ValueError):
            actual_frames = -1
        if (
            video.get("width") != output["width"]
            or video.get("height") != output["height"]
            or actual_frames != output["totalFrames"]
        ):
            temporary.unlink(missing_ok=True)
            raise RenderArtifactError("preview frame contract is invalid")
        temporary.replace(destination)
        return self._artifact(destination)

    def finalize(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        preview_storage_key: str,
        master_key: str,
    ) -> dict[str, Any]:
        source = _safe_input(self.artifact_root, preview_storage_key)
        root = _scope_root(self.artifact_root, workspace_ref, run_ref)
        if not isinstance(master_key, str) or len(master_key) != 64:
            raise RenderArtifactError("master key is invalid")
        destination = root / "masters" / f"episode-master-{master_key}.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(f"{destination.stem}.part.mp4")
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        return self._artifact(destination)
