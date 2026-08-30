"""Deterministic FFmpeg timeline composition owned by V3 Render Core."""

from __future__ import annotations

import ctypes
import errno
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping

from .digests import (
    CANONICAL_PCM_CHANNEL_COUNT,
    CANONICAL_PCM_SAMPLE_RATE,
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    PCM_CONTENT_DIGEST_SPEC,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
    video_digest_metadata,
)


class RenderArtifactError(RuntimeError):
    pass


_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_GLYPH_COMPOSER_IDENTITY = "v3.deterministic-glyph-reveal-ffmpeg.v1"
_GLYPH_RENDERER_IDENTITY_V2 = "v3.deterministic-glyph-reveal-ffmpeg"
_GLYPH_RENDERER_VERSION_V2 = "2"
_GLYPH_BLEND_MODE = "GRAZING_LIGHT_RELIEF"
_SUPPORTED_GLYPH_BASE_PIXEL_FORMATS = {"yuv420p", "yuv422p", "yuv444p"}
_TIMELINE_PREVIEW_RENDERER_IDENTITY = "v3.deterministic-timeline-preview-ffmpeg"
_TIMELINE_PREVIEW_RENDERER_VERSION = "1"
_TIMELINE_PREVIEW_REQUEST_SCHEMA_VERSION = (
    "v4.m13-composition-execution-request.v1"
)
_TIMELINE_PREVIEW_ROLE_PRIORITY = {
    "dialogue": 3,
    "narration": 3,
    "sfx": 2,
    "ambience": 1,
    "music": 0,
}
_TIMELINE_PREVIEW_ROLE_GAIN_DB = {
    "dialogue": 0,
    "narration": 0,
    "sfx": -6,
    "ambience": -12,
    "music": -18,
}
_TIMELINE_PREVIEW_DUCKING = {
    "threshold": "0.125",
    "ratio": "8",
    "attackMilliseconds": 5,
    "releaseMilliseconds": 180,
    "makeup": "1",
    "knee": "2",
    "link": "maximum",
    "detection": "rms",
    "levelSc": "1",
    "mix": "1",
}
_TIMELINE_PREVIEW_LIMITER = {
    "limit": "0.95",
    "attackMilliseconds": 5,
    "releaseMilliseconds": 50,
    "level": False,
    "latency": True,
}
_MAX_TIMELINE_PREVIEW_INPUT_BYTES = 4_000_000_000
_STABLE_FILE_IDENTITY_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


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


def _runtime_binary_identity(path: Path, *, label: str) -> tuple[Any, ...]:
    """Measure one no-follow executable and reject an unstable path entry."""

    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RenderArtifactError(
            f"{label} runtime no-follow support is unavailable"
        )
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
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        entry_before = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_mode & 0o111 == 0
            or any(
                getattr(before, field) != getattr(entry_before, field)
                for field in identity_fields
            )
        ):
            raise RenderArtifactError(f"{label} runtime is not a stable executable")
        digest = sha256()
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        after = os.fstat(descriptor)
        entry_after = os.stat(path, follow_symlinks=False)
        if any(
            getattr(before, field) != getattr(after, field)
            or getattr(before, field) != getattr(entry_after, field)
            for field in identity_fields
        ):
            raise RenderArtifactError(f"{label} runtime changed while measuring")
        return (
            str(path),
            *(getattr(after, field) for field in identity_fields),
            digest.hexdigest(),
        )
    except RenderArtifactError:
        raise
    except OSError as exc:
        raise RenderArtifactError(f"{label} runtime is unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _require_stable_runtime_binary(
    path: Path,
    expected_identity: tuple[Any, ...],
    *,
    label: str,
) -> None:
    if _runtime_binary_identity(path, label=label) != expected_identity:
        raise RenderArtifactError(f"{label} runtime changed during composition")


def _stable_file_identity(value: os.stat_result) -> tuple[int, ...]:
    return tuple(
        getattr(value, field) for field in _STABLE_FILE_IDENTITY_FIELDS
    )


def _descriptor_sha256(
    descriptor: int,
    *,
    label: str,
    require_executable: bool = False,
) -> tuple[str, int, tuple[int, ...]]:
    if not hasattr(os, "pread"):
        raise RenderArtifactError(f"{label} descriptor hashing is unavailable")
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or (require_executable and before.st_mode & 0o111 == 0)
        ):
            raise RenderArtifactError(f"{label} is not a regular file")
        digest = sha256()
        byte_count = 0
        offset = 0
        while True:
            block = os.pread(descriptor, 1024 * 1024, offset)
            if not block:
                break
            digest.update(block)
            byte_count += len(block)
            offset += len(block)
        after = os.fstat(descriptor)
    except RenderArtifactError:
        raise
    except OSError as exc:
        raise RenderArtifactError(f"{label} could not be hashed") from exc
    if (
        _stable_file_identity(before) != _stable_file_identity(after)
        or byte_count != before.st_size
    ):
        raise RenderArtifactError(f"{label} changed while hashing")
    return digest.hexdigest(), byte_count, _stable_file_identity(after)


class _PinnedRuntimeBinary:
    """Execute one measured runtime through its held descriptor only."""

    def __init__(self, path: Path, *, label: str) -> None:
        self.source_path = path
        self.label = label
        self.descriptor: int | None = None
        self.binary_digest = ""
        self.identity: tuple[int, ...] = ()

    def __enter__(self) -> "_PinnedRuntimeBinary":
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise RenderArtifactError(
                f"{self.label} runtime no-follow support is unavailable"
            )
        flags = os.O_RDONLY | no_follow
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        try:
            self.descriptor = os.open(self.source_path, flags)
            entry = os.stat(self.source_path, follow_symlinks=False)
            self.binary_digest, _, self.identity = _descriptor_sha256(
                self.descriptor,
                label=f"{self.label} runtime",
                require_executable=True,
            )
            if _stable_file_identity(entry) != self.identity:
                raise RenderArtifactError(
                    f"{self.label} runtime path is not stable"
                )
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    @property
    def executable_path(self) -> Path:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} runtime is not pinned")
        return Path(f"/proc/self/fd/{self.descriptor}")

    @property
    def pass_fds(self) -> tuple[int, ...]:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} runtime is not pinned")
        return (self.descriptor,)

    def version_identity(self) -> str:
        try:
            result = subprocess.run(
                [str(self.executable_path), "-version"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
                env=_fixed_environment(),
                pass_fds=self.pass_fds,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise RenderArtifactError(
                f"{self.label} runtime identity is unavailable"
            ) from exc
        lines = result.stdout.splitlines()
        first_line = lines[0].strip() if lines else ""
        if (
            not first_line
            or len(first_line) > 400
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in first_line
            )
        ):
            raise RenderArtifactError(
                f"{self.label} runtime identity is invalid"
            )
        return f"{first_line} | sha256:{self.binary_digest}"

    def require_stable(self) -> None:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} runtime is not pinned")
        digest, _, identity = _descriptor_sha256(
            self.descriptor,
            label=f"{self.label} runtime",
            require_executable=True,
        )
        try:
            entry = os.stat(self.source_path, follow_symlinks=False)
        except OSError as exc:
            raise RenderArtifactError(
                f"{self.label} runtime path changed during composition"
            ) from exc
        if (
            identity != self.identity
            or digest != self.binary_digest
            or _stable_file_identity(entry) != self.identity
        ):
            raise RenderArtifactError(
                f"{self.label} runtime changed during composition"
            )


class _PinnedRegularFile:
    """Retain one rendered candidate from digest through publication."""

    def __init__(self, path: Path, *, label: str) -> None:
        self.source_path = path
        self.label = label
        self.descriptor: int | None = None
        self.identity: tuple[int, ...] = ()

    def __enter__(self) -> "_PinnedRegularFile":
        no_follow = getattr(os, "O_NOFOLLOW", None)
        if no_follow is None:
            raise RenderArtifactError(
                f"{self.label} no-follow support is unavailable"
            )
        flags = os.O_RDONLY | no_follow
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        try:
            self.descriptor = os.open(self.source_path, flags)
            before = os.fstat(self.descriptor)
            entry = os.stat(self.source_path, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size <= 0
                or _stable_file_identity(before)
                != _stable_file_identity(entry)
            ):
                raise RenderArtifactError(f"{self.label} is not stable")
            self.identity = _stable_file_identity(before)
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None

    @property
    def descriptor_path(self) -> Path:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} is not pinned")
        return Path(f"/proc/self/fd/{self.descriptor}")

    @property
    def pass_fds(self) -> tuple[int, ...]:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} is not pinned")
        return (self.descriptor,)

    def require_stable(self) -> None:
        if self.descriptor is None:
            raise RenderArtifactError(f"{self.label} is not pinned")
        try:
            descriptor_identity = _stable_file_identity(
                os.fstat(self.descriptor)
            )
            entry_identity = _stable_file_identity(
                os.stat(self.source_path, follow_symlinks=False)
            )
        except OSError as exc:
            raise RenderArtifactError(
                f"{self.label} changed while pinned"
            ) from exc
        if descriptor_identity != self.identity or entry_identity != self.identity:
            raise RenderArtifactError(f"{self.label} changed while pinned")


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


def _reuse_identical_published_output(
    *,
    directory_descriptor: int,
    source: Path,
    output_name: str,
    no_follow: int,
) -> None:
    """Reuse one stable regular output only when its bytes are identical."""

    file_flags = os.O_RDONLY | no_follow
    if hasattr(os, "O_CLOEXEC"):
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK
    source_descriptor: int | None = None
    output_descriptor: int | None = None
    try:
        source_descriptor = os.open(source, file_flags)
        output_descriptor = os.open(
            output_name,
            file_flags,
            dir_fd=directory_descriptor,
        )
        source_before = os.fstat(source_descriptor)
        output_before = os.fstat(output_descriptor)
        if (
            not stat.S_ISREG(source_before.st_mode)
            or not stat.S_ISREG(output_before.st_mode)
            or source_before.st_size <= 0
            or output_before.st_size <= 0
        ):
            raise RenderArtifactError(
                "existing deterministic output is not a regular file"
            )

        source_digest = sha256()
        output_digest = sha256()
        byte_identical = True
        with os.fdopen(os.dup(source_descriptor), "rb") as source_stream:
            with os.fdopen(os.dup(output_descriptor), "rb") as output_stream:
                while True:
                    source_block = source_stream.read(1024 * 1024)
                    output_block = output_stream.read(1024 * 1024)
                    source_digest.update(source_block)
                    output_digest.update(output_block)
                    if source_block != output_block:
                        byte_identical = False
                    if not source_block and not output_block:
                        break

        source_after = os.fstat(source_descriptor)
        output_after = os.fstat(output_descriptor)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(source_before, field) != getattr(source_after, field)
            or getattr(output_before, field) != getattr(output_after, field)
            for field in identity_fields
        ):
            raise RenderArtifactError(
                "deterministic output changed while checking exact replay"
            )
        directory_entry = os.stat(
            output_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(directory_entry.st_mode)
            or any(
                getattr(directory_entry, field) != getattr(output_after, field)
                for field in identity_fields
            )
            or not byte_identical
            or source_before.st_size != output_before.st_size
            or source_digest.digest() != output_digest.digest()
        ):
            raise RenderArtifactError(
                "deterministic output already exists with different content"
            )
    except RenderArtifactError:
        raise
    except OSError as exc:
        raise RenderArtifactError(
            "existing deterministic output could not be verified"
        ) from exc
    finally:
        if output_descriptor is not None:
            os.close(output_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)


def _publish_glyph_output_v2(
    *,
    root: Path,
    directory: Path,
    source: Path,
    output_name: str,
) -> Path:
    """Publish through held directory descriptors without reopening path parts."""

    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise RenderArtifactError("glyph output escaped artifact root") from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or not output_name
        or Path(output_name).name != output_name
        or output_name in {".", ".."}
    ):
        raise RenderArtifactError("glyph output path is invalid")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        raise RenderArtifactError(
            "glyph output no-follow directory support is unavailable"
        )
    flags = os.O_RDONLY | no_follow | directory_flag
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptors: list[int] = []
    try:
        current_descriptor = os.open(root, flags)
        descriptors.append(current_descriptor)
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                part,
                flags,
                dir_fd=current_descriptor,
            )
            descriptors.append(next_descriptor)
            current_descriptor = next_descriptor
        try:
            os.link(
                source,
                output_name,
                dst_dir_fd=current_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError:
            _reuse_identical_published_output(
                directory_descriptor=current_descriptor,
                source=source,
                output_name=output_name,
                no_follow=no_follow,
            )
    except RenderArtifactError:
        raise
    except (OSError, TypeError, NotImplementedError) as exc:
        raise RenderArtifactError(
            "glyph output could not be published atomically"
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
    return directory / output_name


def _reuse_identical_published_descriptor_output(
    *,
    directory_descriptor: int,
    source: _PinnedRegularFile,
    expected_file_digest: str,
    output_name: str,
    no_follow: int,
) -> None:
    """Verify an exact replay against the already pinned rendered bytes."""

    if _PREFIXED_DIGEST.fullmatch(expected_file_digest) is None:
        raise RenderArtifactError("deterministic output digest is invalid")
    source.require_stable()
    if source.descriptor is None:
        raise RenderArtifactError("deterministic output source is not pinned")
    file_flags = os.O_RDONLY | no_follow
    if hasattr(os, "O_CLOEXEC"):
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK
    output_descriptor: int | None = None
    try:
        output_descriptor = os.open(
            output_name,
            file_flags,
            dir_fd=directory_descriptor,
        )
        output_before = os.fstat(output_descriptor)
        if not stat.S_ISREG(output_before.st_mode) or output_before.st_size <= 0:
            raise RenderArtifactError(
                "existing deterministic output is not a regular file"
            )
        source_hex, source_size, source_identity = _descriptor_sha256(
            source.descriptor,
            label="deterministic output source",
        )
        output_hex, output_size, output_identity = _descriptor_sha256(
            output_descriptor,
            label="existing deterministic output",
        )
        byte_identical = True
        offset = 0
        while True:
            source_block = os.pread(
                source.descriptor,
                1024 * 1024,
                offset,
            )
            output_block = os.pread(
                output_descriptor,
                1024 * 1024,
                offset,
            )
            if source_block != output_block:
                byte_identical = False
            if not source_block and not output_block:
                break
            offset += max(len(source_block), len(output_block))
        directory_entry = os.stat(
            output_name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        source.require_stable()
        if (
            source_identity != source.identity
            or _stable_file_identity(directory_entry) != output_identity
            or source_size != output_size
            or source_hex != output_hex
            or not byte_identical
            or f"sha256:{source_hex}" != expected_file_digest
        ):
            raise RenderArtifactError(
                "deterministic output already exists with different content"
            )
    except RenderArtifactError:
        raise
    except OSError as exc:
        raise RenderArtifactError(
            "existing deterministic output could not be verified"
        ) from exc
    finally:
        if output_descriptor is not None:
            os.close(output_descriptor)


def _link_anonymous_descriptor_no_replace(
    *,
    source_descriptor: int,
    directory_descriptor: int,
    output_name: str,
) -> None:
    """Atomically link one O_TMPFILE inode without reopening a source name."""

    at_empty_path = 0x1000
    try:
        linkat = ctypes.CDLL(None, use_errno=True).linkat
        linkat.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        )
        linkat.restype = ctypes.c_int
        ctypes.set_errno(0)
        result = linkat(
            source_descriptor,
            b"",
            directory_descriptor,
            os.fsencode(output_name),
            at_empty_path,
        )
    except (AttributeError, OSError, TypeError) as exc:
        raise RenderArtifactError(
            "timeline output descriptor linking is unavailable"
        ) from exc
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), output_name)
    raise OSError(error_number, os.strerror(error_number), output_name)


def _publish_timeline_output_v1(
    *,
    root: Path,
    directory: Path,
    source: _PinnedRegularFile,
    expected_file_digest: str,
    output_name: str,
) -> Path:
    """Copy one held candidate, then atomically link or exact-reuse it."""

    try:
        relative = directory.relative_to(root)
    except ValueError as exc:
        raise RenderArtifactError("timeline output escaped artifact root") from exc
    if (
        not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or not output_name
        or Path(output_name).name != output_name
        or output_name in {".", ".."}
        or _PREFIXED_DIGEST.fullmatch(expected_file_digest) is None
    ):
        raise RenderArtifactError("timeline output path is invalid")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    temporary_flag = getattr(os, "O_TMPFILE", None)
    if no_follow is None or directory_flag is None or temporary_flag is None:
        raise RenderArtifactError(
            "timeline output no-follow directory support is unavailable"
        )
    if source.descriptor is None:
        raise RenderArtifactError("timeline output source is not pinned")
    directory_flags = os.O_RDONLY | no_follow | directory_flag
    output_flags = os.O_RDWR | temporary_flag | no_follow
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        output_flags |= os.O_CLOEXEC
    descriptors: list[int] = []
    temporary_descriptor: int | None = None
    try:
        current_descriptor = os.open(root, directory_flags)
        descriptors.append(current_descriptor)
        for part in relative.parts:
            try:
                os.mkdir(part, mode=0o700, dir_fd=current_descriptor)
            except FileExistsError:
                pass
            next_descriptor = os.open(
                part,
                directory_flags,
                dir_fd=current_descriptor,
            )
            descriptors.append(next_descriptor)
            current_descriptor = next_descriptor

        source.require_stable()
        source_before = os.fstat(source.descriptor)
        temporary_descriptor = os.open(
            ".",
            output_flags,
            0o600,
            dir_fd=current_descriptor,
        )

        digest = sha256()
        byte_count = 0
        offset = 0
        while True:
            block = os.pread(source.descriptor, 1024 * 1024, offset)
            if not block:
                break
            digest.update(block)
            byte_count += len(block)
            offset += len(block)
            view = memoryview(block)
            while view:
                written = os.write(temporary_descriptor, view)
                if written <= 0:
                    raise RenderArtifactError(
                        "timeline output staging write failed"
                    )
                view = view[written:]
        os.fsync(temporary_descriptor)
        staged = os.fstat(temporary_descriptor)
        source_after = os.fstat(source.descriptor)
        source.require_stable()
        if (
            _stable_file_identity(source_before)
            != _stable_file_identity(source_after)
            or not stat.S_ISREG(staged.st_mode)
            or byte_count != source_before.st_size
            or staged.st_size != byte_count
            or f"sha256:{digest.hexdigest()}" != expected_file_digest
        ):
            raise RenderArtifactError(
                "timeline output source changed before publication"
            )

        try:
            _link_anonymous_descriptor_no_replace(
                source_descriptor=temporary_descriptor,
                directory_descriptor=current_descriptor,
                output_name=output_name,
            )
        except FileExistsError:
            _reuse_identical_published_descriptor_output(
                directory_descriptor=current_descriptor,
                source=source,
                expected_file_digest=expected_file_digest,
                output_name=output_name,
                no_follow=no_follow,
            )
        os.fsync(current_descriptor)
    except RenderArtifactError:
        raise
    except (OSError, TypeError, NotImplementedError) as exc:
        raise RenderArtifactError(
            "timeline output could not be published atomically"
        ) from exc
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
    return directory / output_name


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


def _glyph_probe(
    path: Path,
    ffprobe_path: Path,
    *,
    pass_fds: tuple[int, ...] = (),
) -> dict[str, Any]:
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
            pass_fds=pass_fds,
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


def _explicit_stage_ranges_v2(
    value: object,
    *,
    masks: list[Mapping[str, Any]],
    frame_range_start: int,
    frame_range_end: int,
) -> list[tuple[int, int | None]]:
    """Validate a zero-based, end-exclusive schedule without deriving durations."""

    if (
        not isinstance(value, list)
        or not value
        or not isinstance(masks, list)
        or len(value) != len(masks)
        or any(not isinstance(mask, Mapping) for mask in masks)
    ):
        raise RenderArtifactError("glyph reveal schedule count is invalid")
    ranges: list[tuple[int, int | None]] = []
    previous_end = frame_range_start
    for index, raw_entry in enumerate(value):
        entry = _closed_mapping(
            raw_entry,
            {
                "revealOrdinal",
                "maskAssetVersionRef",
                "startFrameInclusive",
                "endFrameExclusive",
            },
            label=f"glyph reveal schedule {index}",
        )
        ordinal = _integer(
            entry["revealOrdinal"],
            label=f"glyph reveal schedule {index} ordinal",
            minimum=1,
        )
        if ordinal != index + 1:
            raise RenderArtifactError("glyph reveal schedule ordinals are invalid")
        mask_ref = entry["maskAssetVersionRef"]
        mask_ordinal = _integer(
            masks[index].get("revealOrdinal"),
            label=f"glyph mask {index} reveal ordinal",
            minimum=1,
        )
        if (
            not isinstance(mask_ref, str)
            or not mask_ref
            or mask_ref != masks[index].get("assetVersionRef")
            or mask_ordinal != ordinal
        ):
            raise RenderArtifactError("glyph reveal schedule mask binding is invalid")
        start = _integer(
            entry["startFrameInclusive"],
            label=f"glyph reveal schedule {index} start",
        )
        end = _integer(
            entry["endFrameExclusive"],
            label=f"glyph reveal schedule {index} end",
            minimum=1,
        )
        if start != previous_end or end <= start or end > frame_range_end:
            raise RenderArtifactError("glyph reveal schedule intervals are invalid")
        previous_end = end
        ranges.append((start, None if index == len(value) - 1 else end - 1))
    if previous_end != frame_range_end:
        raise RenderArtifactError("glyph reveal schedule does not cover frame range")
    return ranges


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


def _timeline_preview_canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError(
            "timeline preview request is not canonical JSON"
        ) from exc


def _timeline_preview_ref(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 200
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value) is None
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _timeline_preview_raw_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _HEX_DIGEST.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _timeline_preview_prefixed_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _PREFIXED_DIGEST.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _timeline_preview_storage_key(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or "//" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise RenderArtifactError(f"{label} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _timeline_preview_signed_integer(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _timeline_preview_frame_rate(
    value: object,
    *,
    label: str,
) -> Fraction:
    record = _closed_mapping(
        value,
        {"numerator", "denominator"},
        label=label,
    )
    numerator = _integer(
        record["numerator"], label=f"{label} numerator", minimum=1
    )
    denominator = _integer(
        record["denominator"], label=f"{label} denominator", minimum=1
    )
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        raise RenderArtifactError(f"{label} must be reduced")
    return result


def _timeline_preview_frame_to_sample(frame: int, frame_rate: Fraction) -> int:
    return (
        frame
        * CANONICAL_PCM_SAMPLE_RATE
        * frame_rate.denominator
        // frame_rate.numerator
    )


def _stage_timeline_preview_input(
    *,
    root: Path,
    storage_key: object,
    expected_digest: object,
    destination: Path,
    prefixed_digest: bool,
) -> None:
    """Stage one server-resolved input through a no-follow descriptor walk."""

    safe_key = _timeline_preview_storage_key(
        storage_key, label="timeline preview input storage key"
    )
    expected = (
        _timeline_preview_prefixed_digest(
            expected_digest, label="timeline preview input file digest"
        )
        if prefixed_digest
        else _timeline_preview_raw_digest(
            expected_digest, label="timeline preview input file digest"
        )
    )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if no_follow is None or directory_flag is None:
        raise RenderArtifactError(
            "timeline preview no-follow input support is unavailable"
        )
    directory_flags = os.O_RDONLY | no_follow | directory_flag
    file_flags = os.O_RDONLY | no_follow
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        file_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK
    descriptors: list[int] = []
    source_descriptor: int | None = None
    destination_descriptor: int | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        parts = PurePosixPath(safe_key).parts
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        source_descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        before = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > _MAX_TIMELINE_PREVIEW_INPUT_BYTES
        ):
            raise RenderArtifactError(
                "timeline preview input is not an allowed regular file"
            )
        destination_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | no_follow,
            0o600,
        )
        digest = sha256()
        byte_count = 0
        with os.fdopen(os.dup(source_descriptor), "rb") as source_stream:
            with os.fdopen(
                os.dup(destination_descriptor), "wb"
            ) as destination_stream:
                for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                    digest.update(block)
                    byte_count += len(block)
                    destination_stream.write(block)
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
        after = os.fstat(source_descriptor)
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(getattr(before, field) != getattr(after, field) for field in identity_fields)
            or byte_count != before.st_size
        ):
            raise RenderArtifactError("timeline preview input changed while staging")
        actual = f"sha256:{digest.hexdigest()}" if prefixed_digest else digest.hexdigest()
        if actual != expected:
            raise RenderArtifactError("timeline preview input file digest changed")
    except RenderArtifactError:
        raise
    except OSError as exc:
        raise RenderArtifactError("timeline preview input staging failed") from exc
    finally:
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _timeline_preview_bus(
    graph: list[str], labels: list[str], bus_name: str
) -> str | None:
    if not labels:
        return None
    if len(labels) == 1:
        return labels[0]
    output = f"{bus_name}-bus"
    weights = " ".join("1" for _ in labels)
    graph.append(
        "".join(f"[{label}]" for label in labels)
        + f"amix=inputs={len(labels)}:weights='{weights}':normalize=false:"
        f"duration=longest:dropout_transition=0[{output}]"
    )
    return output


def _timeline_preview_mix_filter_graph(audio_mix: Mapping[str, Any]) -> str:
    duration_samples = audio_mix["durationSamples"]
    graph: list[str] = []
    roles: dict[str, list[str]] = {
        role: [] for role in _TIMELINE_PREVIEW_ROLE_PRIORITY
    }
    for index, clip in enumerate(audio_mix["clips"]):
        role = clip["audioRole"]
        label = f"timeline-track-{index}"
        roles[role].append(label)
        source_length = (
            clip["sourceEndSampleExclusive"] - clip["sourceStartSample"]
        )
        filters = [
            (
                f"[{index + 1}:a:0]atrim=start_sample="
                f"{clip['sourceStartSample']}:end_sample="
                f"{clip['sourceEndSampleExclusive']}"
            ),
            "asetpts=N/SR/TB",
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        ]
        if clip["fadeInSamples"]:
            filters.append(
                f"afade=t=in:ss=0:ns={clip['fadeInSamples']}"
            )
        if clip["fadeOutSamples"]:
            filters.append(
                "afade=t=out:ss="
                f"{source_length - clip['fadeOutSamples']}:"
                f"ns={clip['fadeOutSamples']}"
            )
        gain = _TIMELINE_PREVIEW_ROLE_GAIN_DB[role] + clip["gainDb"]
        filters.extend(
            [
                f"volume={gain}dB",
                f"adelay=delays={clip['timelineStartSample']}S:all=1",
                f"apad=whole_len={duration_samples}",
                f"atrim=end_sample={duration_samples}",
                "asetpts=N/SR/TB",
            ]
        )
        graph.append(",".join(filters) + f"[{label}]")
    dialogue = _timeline_preview_bus(
        graph, roles["dialogue"] + roles["narration"], "dialogue"
    )
    sfx = _timeline_preview_bus(graph, roles["sfx"], "sfx")
    ambience = _timeline_preview_bus(graph, roles["ambience"], "ambience")
    music = _timeline_preview_bus(graph, roles["music"], "music")
    bed = _timeline_preview_bus(
        graph,
        [label for label in (sfx, ambience, music) if label is not None],
        "bed",
    )
    if dialogue is not None and bed is not None:
        ducking = _TIMELINE_PREVIEW_DUCKING
        graph.append(f"[{dialogue}]asplit=2[dialogue-final][dialogue-key]")
        graph.append(
            f"[{bed}][dialogue-key]sidechaincompress="
            f"threshold={ducking['threshold']}:ratio={ducking['ratio']}:"
            f"attack={ducking['attackMilliseconds']}:"
            f"release={ducking['releaseMilliseconds']}:"
            f"makeup={ducking['makeup']}:knee={ducking['knee']}:"
            f"link={ducking['link']}:detection={ducking['detection']}:"
            f"level_sc={ducking['levelSc']}:mix={ducking['mix']}[ducked-bed]"
        )
        graph.append(
            "[dialogue-final][ducked-bed]amix=inputs=2:weights='1 1':"
            "normalize=false:duration=longest:dropout_transition=0[timeline-mix]"
        )
        source = "timeline-mix"
    elif dialogue is not None:
        source = dialogue
    elif bed is not None:
        source = bed
    else:
        raise RenderArtifactError("timeline preview mix has no usable clips")
    limiter = _TIMELINE_PREVIEW_LIMITER
    graph.append(
        f"[{source}]alimiter=limit={limiter['limit']}:"
        f"attack={limiter['attackMilliseconds']}:"
        f"release={limiter['releaseMilliseconds']}:"
        f"level={'true' if limiter['level'] else 'false'}:"
        f"latency={'true' if limiter['latency'] else 'false'},"
        f"atrim=end_sample={duration_samples},asetpts=N/SR/TB,"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo[aout]"
    )
    return ";".join(graph)


def _validate_timeline_preview_execution_request(
    value: object,
) -> dict[str, Any]:
    request = _closed_mapping(
        value,
        {
            "schemaVersion",
            "executionRequestRef",
            "workspaceRef",
            "productionRunRef",
            "timelineVersionRef",
            "timelineVersionDigest",
            "inputBindingsDigest",
            "videoInput",
            "audioMix",
            "subtitleManifest",
            "output",
            "publicationAllowed",
            "payloadDigest",
        },
        label="timeline preview execution request",
    )
    # Snapshot the sealed request into JSON primitives before inspecting any
    # nested binding.  A shallow copy would leave caller-owned lists and maps
    # mutable after payload verification.
    try:
        result = json.loads(_timeline_preview_canonical_json(request))
    except json.JSONDecodeError as exc:
        raise RenderArtifactError(
            "timeline preview request snapshot is invalid"
        ) from exc
    if not isinstance(result, dict):
        raise RenderArtifactError("timeline preview request snapshot is invalid")
    claimed_digest = result.pop("payloadDigest")
    _timeline_preview_raw_digest(
        claimed_digest, label="timeline preview execution request digest"
    )
    actual_digest = sha256(_timeline_preview_canonical_json(result)).hexdigest()
    if claimed_digest != actual_digest:
        raise RenderArtifactError(
            "timeline preview execution request digest is invalid"
        )
    result["payloadDigest"] = claimed_digest
    if (
        result.get("schemaVersion") != _TIMELINE_PREVIEW_REQUEST_SCHEMA_VERSION
        or result.get("publicationAllowed") is not False
    ):
        raise RenderArtifactError("timeline preview execution boundary is invalid")
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
    ):
        _timeline_preview_ref(result.get(field), label=field)
    _timeline_preview_raw_digest(
        result.get("timelineVersionDigest"), label="timelineVersionDigest"
    )
    _timeline_preview_raw_digest(
        result.get("inputBindingsDigest"), label="inputBindingsDigest"
    )

    video = _closed_mapping(
        result.get("videoInput"),
        {
            "glyphRevealRequirementRef",
            "glyphRevealRequirementDigest",
            "glyphRevealExecutionRequestRef",
            "glyphRevealExecutionRequestDigest",
            "glyphRevealArtifactEvidenceRef",
            "glyphRevealArtifactEvidenceDigest",
            "storageKey",
            "fileDigest",
            "decodedFramePixelDigest",
            "decodedFramePixelDigestSpec",
            "codec",
            "pixelFormat",
            "width",
            "height",
            "frameCount",
            "frameRate",
        },
        label="timeline preview video input",
    )
    for field in (
        "glyphRevealRequirementRef",
        "glyphRevealExecutionRequestRef",
        "glyphRevealArtifactEvidenceRef",
    ):
        _timeline_preview_ref(video[field], label=f"videoInput.{field}")
    for field in (
        "glyphRevealRequirementDigest",
        "glyphRevealExecutionRequestDigest",
        "glyphRevealArtifactEvidenceDigest",
    ):
        _timeline_preview_raw_digest(video[field], label=f"videoInput.{field}")
    _timeline_preview_storage_key(
        video["storageKey"], label="videoInput.storageKey"
    )
    _timeline_preview_prefixed_digest(
        video["fileDigest"], label="videoInput.fileDigest"
    )
    _timeline_preview_prefixed_digest(
        video["decodedFramePixelDigest"],
        label="videoInput.decodedFramePixelDigest",
    )
    if (
        video["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or video["codec"] != "h264"
        or video["pixelFormat"] not in _SUPPORTED_GLYPH_BASE_PIXEL_FORMATS
    ):
        raise RenderArtifactError("timeline preview video content contract is invalid")
    video_width = _integer(
        video["width"], label="timeline preview video width", minimum=1
    )
    video_height = _integer(
        video["height"], label="timeline preview video height", minimum=1
    )
    video_frames = _integer(
        video["frameCount"], label="timeline preview video frame count", minimum=1
    )
    video_rate = _timeline_preview_frame_rate(
        video["frameRate"], label="timeline preview video frame rate"
    )
    if video_rate.denominator != 1:
        raise RenderArtifactError(
            "timeline preview vertical slice requires an integral frame rate"
        )

    output = _closed_mapping(
        result.get("output"),
        {
            "width",
            "height",
            "frameRate",
            "totalFrames",
            "sampleRate",
            "channelCount",
            "durationSamples",
            "container",
            "videoCodec",
            "pixelFormat",
            "audioCodec",
            "audioBitRate",
        },
        label="timeline preview output",
    )
    output_rate = _timeline_preview_frame_rate(
        output["frameRate"], label="timeline preview output frame rate"
    )
    total_frames = _integer(
        output["totalFrames"], label="timeline preview total frames", minimum=1
    )
    duration_samples = _integer(
        output["durationSamples"],
        label="timeline preview duration samples",
        minimum=1,
    )
    output_sample_rate = _integer(
        output["sampleRate"], label="timeline preview output sample rate", minimum=1
    )
    output_channel_count = _integer(
        output["channelCount"],
        label="timeline preview output channel count",
        minimum=1,
    )
    output_audio_bit_rate = _integer(
        output["audioBitRate"],
        label="timeline preview output audio bit rate",
        minimum=1,
    )
    if (
        _integer(output["width"], label="timeline preview output width", minimum=1)
        != video_width
        or _integer(
            output["height"], label="timeline preview output height", minimum=1
        )
        != video_height
        or total_frames != video_frames
        or output_rate != video_rate
        or output_sample_rate != CANONICAL_PCM_SAMPLE_RATE
        or output_channel_count != CANONICAL_PCM_CHANNEL_COUNT
        or duration_samples
        != _timeline_preview_frame_to_sample(total_frames, output_rate)
        or output.get("container") != "mp4"
        or output.get("videoCodec") != "h264"
        or output.get("pixelFormat") != video["pixelFormat"]
        or output.get("audioCodec") != "aac"
        or output_audio_bit_rate != 128_000
    ):
        raise RenderArtifactError("timeline preview output contract is invalid")

    subtitle = _closed_mapping(
        result.get("subtitleManifest"),
        {"subtitleManifestRef", "subtitleManifestDigest"},
        label="timeline preview subtitle manifest",
    )
    _timeline_preview_ref(
        subtitle["subtitleManifestRef"], label="subtitleManifestRef"
    )
    _timeline_preview_raw_digest(
        subtitle["subtitleManifestDigest"], label="subtitleManifestDigest"
    )

    audio_mix = _closed_mapping(
        result.get("audioMix"),
        {
            "mixRequestRef",
            "mixRequestDigest",
            "timelineVersionRef",
            "timelineVersionDigest",
            "stemSetVersionRef",
            "stemSetDigest",
            "sampleRate",
            "channelCount",
            "durationSamples",
            "roundingRule",
            "mixParameters",
            "mixParametersDigest",
            "clips",
        },
        label="timeline preview audio mix",
    )
    for field in ("mixRequestRef", "timelineVersionRef", "stemSetVersionRef"):
        _timeline_preview_ref(audio_mix[field], label=f"audioMix.{field}")
    for field in (
        "mixRequestDigest",
        "timelineVersionDigest",
        "stemSetDigest",
        "mixParametersDigest",
    ):
        _timeline_preview_raw_digest(audio_mix[field], label=f"audioMix.{field}")
    expected_mix_parameters = {
        "rolePriority": _TIMELINE_PREVIEW_ROLE_PRIORITY,
        "roleGainDb": _TIMELINE_PREVIEW_ROLE_GAIN_DB,
        "ducking": _TIMELINE_PREVIEW_DUCKING,
        "limiter": _TIMELINE_PREVIEW_LIMITER,
    }
    mix_sample_rate = _integer(
        audio_mix["sampleRate"],
        label="timeline preview audio mix sample rate",
        minimum=1,
    )
    mix_channel_count = _integer(
        audio_mix["channelCount"],
        label="timeline preview audio mix channel count",
        minimum=1,
    )
    mix_duration_samples = _integer(
        audio_mix["durationSamples"],
        label="timeline preview audio mix duration samples",
        minimum=1,
    )
    if (
        audio_mix["timelineVersionRef"] != result["timelineVersionRef"]
        or audio_mix["timelineVersionDigest"] != result["timelineVersionDigest"]
        or mix_sample_rate != CANONICAL_PCM_SAMPLE_RATE
        or mix_channel_count != CANONICAL_PCM_CHANNEL_COUNT
        or mix_duration_samples != duration_samples
        or audio_mix["roundingRule"] != "FLOOR_EACH_BOUNDARY"
        or audio_mix["mixParameters"] != expected_mix_parameters
        or audio_mix["mixParametersDigest"]
        != sha256(
            _timeline_preview_canonical_json(expected_mix_parameters)
        ).hexdigest()
    ):
        raise RenderArtifactError("timeline preview audio mix contract is invalid")
    clips = audio_mix["clips"]
    if not isinstance(clips, list) or not clips or len(clips) > 64:
        raise RenderArtifactError("timeline preview audio clips are invalid")
    role_asset_types = {
        "dialogue": "DialogueAssetVersion",
        "narration": "DialogueAssetVersion",
        "sfx": "SfxAssetVersion",
        "ambience": "AmbienceAssetVersion",
        "music": "MusicAssetVersion",
    }
    clip_fields = {
        "clipRef",
        "clipDigest",
        "stemMemberRef",
        "stemMemberDigest",
        "audioRole",
        "assetVersionRef",
        "assetVersionType",
        "assetVersionDigest",
        "technicalValidationRef",
        "technicalValidationDigest",
        "storageKey",
        "fileDigest",
        "pcmContentDigest",
        "sampleRate",
        "sourceChannelCount",
        "sourceSampleCount",
        "sourceStartSample",
        "sourceEndSampleExclusive",
        "timelineStartFrame",
        "timelineEndFrameExclusive",
        "timelineStartSample",
        "timelineEndSampleExclusive",
        "gainDb",
        "fadeInSamples",
        "fadeOutSamples",
    }
    seen_clip_refs: set[str] = set()
    seen_stem_refs: set[str] = set()
    normalized_clips: list[Mapping[str, Any]] = []
    for index, raw_clip in enumerate(clips):
        clip = _closed_mapping(
            raw_clip, clip_fields, label=f"timeline preview audio clip {index}"
        )
        clip_ref = _timeline_preview_ref(
            clip["clipRef"], label=f"audioMix.clips[{index}].clipRef"
        )
        stem_ref = _timeline_preview_ref(
            clip["stemMemberRef"],
            label=f"audioMix.clips[{index}].stemMemberRef",
        )
        if clip_ref in seen_clip_refs or stem_ref in seen_stem_refs:
            raise RenderArtifactError("timeline preview audio clip is duplicated")
        seen_clip_refs.add(clip_ref)
        seen_stem_refs.add(stem_ref)
        for field in (
            "assetVersionRef",
            "technicalValidationRef",
        ):
            _timeline_preview_ref(
                clip[field], label=f"audioMix.clips[{index}].{field}"
            )
        for field in (
            "clipDigest",
            "stemMemberDigest",
            "assetVersionDigest",
            "technicalValidationDigest",
            "fileDigest",
            "pcmContentDigest",
        ):
            _timeline_preview_raw_digest(
                clip[field], label=f"audioMix.clips[{index}].{field}"
            )
        _timeline_preview_storage_key(
            clip["storageKey"],
            label=f"audioMix.clips[{index}].storageKey",
        )
        role = clip["audioRole"]
        clip_sample_rate = _integer(
            clip["sampleRate"],
            label=f"audioMix.clips[{index}].sampleRate",
            minimum=1,
        )
        source_channel_count = _integer(
            clip["sourceChannelCount"],
            label=f"audioMix.clips[{index}].sourceChannelCount",
            minimum=1,
        )
        if (
            role not in role_asset_types
            or clip["assetVersionType"] != role_asset_types[role]
            or clip_sample_rate != CANONICAL_PCM_SAMPLE_RATE
            or source_channel_count not in {1, 2}
        ):
            raise RenderArtifactError(
                "timeline preview audio role or source format is invalid"
            )
        source_count = _integer(
            clip["sourceSampleCount"],
            label=f"audioMix.clips[{index}].sourceSampleCount",
            minimum=1,
        )
        source_start = _integer(
            clip["sourceStartSample"],
            label=f"audioMix.clips[{index}].sourceStartSample",
        )
        source_end = _integer(
            clip["sourceEndSampleExclusive"],
            label=f"audioMix.clips[{index}].sourceEndSampleExclusive",
            minimum=1,
        )
        timeline_start_frame = _integer(
            clip["timelineStartFrame"],
            label=f"audioMix.clips[{index}].timelineStartFrame",
        )
        timeline_end_frame = _integer(
            clip["timelineEndFrameExclusive"],
            label=f"audioMix.clips[{index}].timelineEndFrameExclusive",
            minimum=1,
        )
        timeline_start_sample = _integer(
            clip["timelineStartSample"],
            label=f"audioMix.clips[{index}].timelineStartSample",
        )
        timeline_end_sample = _integer(
            clip["timelineEndSampleExclusive"],
            label=f"audioMix.clips[{index}].timelineEndSampleExclusive",
            minimum=1,
        )
        gain_db = _timeline_preview_signed_integer(
            clip["gainDb"],
            label=f"audioMix.clips[{index}].gainDb",
            minimum=-96,
            maximum=24,
        )
        fade_in = _integer(
            clip["fadeInSamples"],
            label=f"audioMix.clips[{index}].fadeInSamples",
        )
        fade_out = _integer(
            clip["fadeOutSamples"],
            label=f"audioMix.clips[{index}].fadeOutSamples",
        )
        source_span = source_end - source_start
        timeline_span = timeline_end_sample - timeline_start_sample
        if (
            source_start >= source_end
            or source_end > source_count
            or timeline_start_frame >= timeline_end_frame
            or timeline_end_frame > total_frames
            or timeline_start_sample
            != _timeline_preview_frame_to_sample(timeline_start_frame, output_rate)
            or timeline_end_sample
            != _timeline_preview_frame_to_sample(timeline_end_frame, output_rate)
            or timeline_end_sample > duration_samples
            or source_span != timeline_span
            or fade_in + fade_out > source_span
            or not -96 <= gain_db <= 24
        ):
            raise RenderArtifactError("timeline preview audio clip timing is invalid")
        normalized_clips.append(clip)
    if list(clips) != sorted(
        normalized_clips,
        key=lambda item: (
            -_TIMELINE_PREVIEW_ROLE_PRIORITY[item["audioRole"]],
            item["clipRef"],
        ),
    ):
        raise RenderArtifactError("timeline preview audio clips are not canonical")

    expected_bindings_digest = sha256(
        _timeline_preview_canonical_json(
            {
                "videoInput": video,
                "audioMix": audio_mix,
                "subtitleManifest": subtitle,
            }
        )
    ).hexdigest()
    if result["inputBindingsDigest"] != expected_bindings_digest:
        raise RenderArtifactError("timeline preview inputBindingsDigest is invalid")
    output_contract_digest = sha256(
        _timeline_preview_canonical_json(output)
    ).hexdigest()
    expected_execution_ref = "m13-composition-execution-" + sha256(
        _timeline_preview_canonical_json(
            {
                "timelineVersionRef": result["timelineVersionRef"],
                "timelineVersionDigest": result["timelineVersionDigest"],
                "inputBindingsDigest": result["inputBindingsDigest"],
                "outputContractDigest": output_contract_digest,
            }
        )
    ).hexdigest()[:32]
    if result["executionRequestRef"] != expected_execution_ref:
        raise RenderArtifactError("timeline preview executionRequestRef is invalid")
    return result


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

    def _glyph_artifact_v2(
        self,
        path: Path,
        *,
        requirement_ref: str,
        requirement_digest: str,
        execution_request_ref: str,
        execution_request_digest: str,
        ffmpeg_path: Path,
        ffprobe_path: Path,
        ffmpeg_identity: str,
        width: int,
        height: int,
        frame_rate: int,
        frame_count: int,
        pixel_format: str,
    ) -> dict[str, Any]:
        """Measure one v2 artifact without reinterpreting the frozen v1 record."""

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
            output_digest = decoded_frame_pixel_digest_metadata(
                path,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
            )
        except DigestError as exc:
            raise RenderArtifactError("glyph output digest failed") from exc
        if _file_state(path) != before:
            raise RenderArtifactError("glyph output changed during digest")
        if (
            output_digest.get("width") != width
            or output_digest.get("height") != height
            or output_digest.get("frameCount") != frame_count
        ):
            raise RenderArtifactError("glyph output digest media contract is invalid")
        output_digest["frameRate"] = frame_rate
        runtime_payload = json.dumps(
            {
                "ffmpegIdentity": ffmpeg_identity,
                "rendererIdentity": _GLYPH_RENDERER_IDENTITY_V2,
                "rendererVersion": _GLYPH_RENDERER_VERSION_V2,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        runtime_evidence_digest = (
            "sha256:" + sha256(runtime_payload.encode("utf-8")).hexdigest()
        )
        return {
            "internalPath": str(path),
            "outputStorageKey": str(path.relative_to(self.artifact_root)),
            "outputByteSize": path.stat().st_size,
            "outputMediaProbe": {
                "width": width,
                "height": height,
                "frameCount": frame_count,
                "frameRate": frame_rate,
            },
            "outputDigest": output_digest,
            "rendererIdentity": _GLYPH_RENDERER_IDENTITY_V2,
            "rendererVersion": _GLYPH_RENDERER_VERSION_V2,
            "ffmpegIdentity": ffmpeg_identity,
            "runtimeEvidenceDigest": runtime_evidence_digest,
            "requirementRef": requirement_ref,
            "requirementDigest": requirement_digest,
            "executionRequestRef": execution_request_ref,
            "executionRequestDigest": execution_request_digest,
            "publicationAllowed": False,
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

    def compose_glyph_reveal_v2(
        self,
        *,
        workspace_ref: str,
        run_ref: str,
        requirement_ref: str,
        requirement_digest: str,
        execution_request_ref: str,
        execution_request_digest: str,
        base_plate: Mapping[str, Any],
        masks: list[Mapping[str, Any]],
        frame_range_start: int,
        frame_range_end: int,
        reveal_schedule: list[Mapping[str, Any]],
        composite_params: Mapping[str, Any],
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Composite a v2 glyph reveal from an explicit zero-based schedule.

        ``frame_range_end`` is exclusive.  V3 never derives stage durations;
        the final cumulative mask remains active through the base-plate tail.
        """

        if not isinstance(workspace_ref, str) or not workspace_ref:
            raise RenderArtifactError("glyph workspace reference is invalid")
        if not isinstance(run_ref, str) or not run_ref:
            raise RenderArtifactError("glyph run reference is invalid")
        if not isinstance(requirement_ref, str) or not requirement_ref:
            raise RenderArtifactError("glyph requirement reference is invalid")
        if not isinstance(execution_request_ref, str) or not execution_request_ref:
            raise RenderArtifactError(
                "glyph execution request reference is invalid"
            )
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
        if not isinstance(masks, list) or not masks:
            raise RenderArtifactError("glyph mask count is invalid")
        start = _integer(frame_range_start, label="glyph frame range start")
        end = _integer(frame_range_end, label="glyph frame range end", minimum=1)
        if end <= start:
            raise RenderArtifactError("glyph frame range is invalid")
        stage_ranges = _explicit_stage_ranges_v2(
            reveal_schedule,
            masks=masks,
            frame_range_start=start,
            frame_range_end=end,
        )
        count = len(stage_ranges)

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
        ffmpeg_identity = _runtime_version(ffmpeg_path).strip()
        if (
            not ffmpeg_identity
            or len(ffmpeg_identity) > 500
            or any(
                ord(character) < 32 or ord(character) == 127
                for character in ffmpeg_identity
            )
        ):
            raise RenderArtifactError("FFmpeg runtime identity is invalid")

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
                        "assetVersionRef",
                        "revealOrdinal",
                        "storageKey",
                        "fileDigest",
                        "pixelDigest",
                        "pixelDigestSpec",
                        "width",
                        "height",
                    },
                    label=f"glyph mask {index}",
                )
                mask_ordinal = _integer(
                    mask_record["revealOrdinal"],
                    label=f"glyph mask {index} reveal ordinal",
                    minimum=1,
                )
                if (
                    not isinstance(mask_record["assetVersionRef"], str)
                    or not mask_record["assetVersionRef"]
                    or mask_ordinal != index + 1
                ):
                    raise RenderArtifactError(
                        "glyph mask schedule binding is invalid"
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
                "-noautorotate",
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
            artifact = self._glyph_artifact_v2(
                candidate,
                requirement_ref=requirement_ref,
                requirement_digest=requirement_digest,
                execution_request_ref=execution_request_ref,
                execution_request_digest=execution_request_digest,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                ffmpeg_identity=ffmpeg_identity,
                width=base_width,
                height=base_height,
                frame_rate=frame_rate,
                frame_count=base_frames,
                pixel_format=base_pixel_format,
            )
            destination = _publish_glyph_output_v2(
                root=self.artifact_root,
                directory=root / "glyph-reveal",
                source=candidate,
                output_name=output_name,
            )
            artifact["internalPath"] = str(destination)
            artifact["outputStorageKey"] = str(
                destination.relative_to(self.artifact_root)
            )
            return artifact

    def compose_timeline_preview_v1(
        self, execution_request: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Mix one sealed M13 timeline and mux it with a glyph-v2 video.

        The request contains only server-resolved relative storage keys and
        closed parameters.  FFmpeg argv and filter expressions are derived
        here and never accepted across the V4/V3 boundary.
        """

        request = _validate_timeline_preview_execution_request(execution_request)
        with (
            _PinnedRuntimeBinary(
                _runtime_path("ffmpeg"), label="FFmpeg"
            ) as ffmpeg_runtime,
            _PinnedRuntimeBinary(
                _runtime_path("ffprobe"), label="FFprobe"
            ) as ffprobe_runtime,
        ):
            return self._compose_timeline_preview_v1_with_runtimes(
                request,
                ffmpeg_runtime=ffmpeg_runtime,
                ffprobe_runtime=ffprobe_runtime,
            )

    def _compose_timeline_preview_v1_with_runtimes(
        self,
        request: Mapping[str, Any],
        *,
        ffmpeg_runtime: _PinnedRuntimeBinary,
        ffprobe_runtime: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        video = request["videoInput"]
        audio_mix = request["audioMix"]
        output = request["output"]
        output_rate = _timeline_preview_frame_rate(
            output["frameRate"], label="timeline preview output frame rate"
        )
        ffmpeg_path = ffmpeg_runtime.executable_path
        ffprobe_path = ffprobe_runtime.executable_path
        runtime_pass_fds = (
            *ffmpeg_runtime.pass_fds,
            *ffprobe_runtime.pass_fds,
        )
        ffmpeg_identity = (
            f"ffmpeg={ffmpeg_runtime.version_identity()} || "
            f"ffprobe={ffprobe_runtime.version_identity()}"
        )
        if len(ffmpeg_identity) > 500:
            raise RenderArtifactError(
                "timeline preview runtime identity is invalid"
            )
        root = _glyph_scope_path(
            self.artifact_root,
            request["workspaceRef"],
            request["productionRunRef"],
        )
        output_name = f"preview-{request['payloadDigest']}.mp4"
        with tempfile.TemporaryDirectory(
            prefix=".timeline-preview-work-",
            dir=self.artifact_root,
            ignore_cleanup_errors=True,
        ) as temporary_directory:
            work_root = Path(temporary_directory)
            work_root.chmod(0o700)
            input_root = work_root / "inputs"
            input_root.mkdir(mode=0o700)
            video_path = input_root / "glyph-video.mp4"
            _stage_timeline_preview_input(
                root=self.artifact_root,
                storage_key=video["storageKey"],
                expected_digest=video["fileDigest"],
                destination=video_path,
                prefixed_digest=True,
            )
            video_probe = _glyph_probe(
                video_path,
                ffprobe_path,
                pass_fds=ffprobe_runtime.pass_fds,
            )
            video_stream = _one_video_stream(
                video_probe, label="timeline preview video input"
            )
            if video_stream.get("side_data_list") or (
                isinstance(video_stream.get("tags"), Mapping)
                and str(video_stream["tags"].get("rotate", "0")) != "0"
            ):
                raise RenderArtifactError(
                    "timeline preview video display transform is unsupported"
                )
            if (
                video_stream.get("codec_name") != video["codec"]
                or video_stream.get("pix_fmt") != video["pixelFormat"]
                or _stream_integer(
                    video_stream, "width", label="timeline preview video width"
                )
                != video["width"]
                or _stream_integer(
                    video_stream, "height", label="timeline preview video height"
                )
                != video["height"]
                or _stream_frame_count(
                    video_stream, label="timeline preview video input"
                )
                != video["frameCount"]
                or _stream_frame_rate(
                    video_stream, label="timeline preview video input"
                )
                != output_rate
            ):
                raise RenderArtifactError(
                    "timeline preview video input media contract changed"
                )
            try:
                video_content = decoded_frame_pixel_digest_metadata(
                    video_path,
                    ffmpeg_path=ffmpeg_path,
                    ffprobe_path=ffprobe_path,
                    pass_fds=runtime_pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError(
                    "timeline preview video input digest failed"
                ) from exc
            if (
                video_content.get("fileDigest") != video["fileDigest"]
                or video_content.get("decodedFramePixelDigest")
                != video["decodedFramePixelDigest"]
                or video_content.get("decodedFramePixelDigestSpec")
                != video["decodedFramePixelDigestSpec"]
            ):
                raise RenderArtifactError(
                    "timeline preview video input content changed"
                )

            audio_paths: list[Path] = []
            for index, clip in enumerate(audio_mix["clips"]):
                audio_path = input_root / f"audio-{index:04d}.wav"
                _stage_timeline_preview_input(
                    root=self.artifact_root,
                    storage_key=clip["storageKey"],
                    expected_digest=clip["fileDigest"],
                    destination=audio_path,
                    prefixed_digest=False,
                )
                try:
                    pcm = canonical_pcm_digest_metadata(
                        audio_path,
                        expected_sample_count=clip["sourceSampleCount"],
                        ffmpeg_path=ffmpeg_path,
                        ffprobe_path=ffprobe_path,
                        pass_fds=runtime_pass_fds,
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        f"timeline preview audio input {index} digest failed"
                    ) from exc
                if (
                    pcm.get("pcmContentDigest") != clip["pcmContentDigest"]
                    or pcm.get("pcmDigestSpec") != PCM_CONTENT_DIGEST_SPEC
                    or pcm.get("sampleRate") != clip["sampleRate"]
                    or pcm.get("sourceChannelCount")
                    != clip["sourceChannelCount"]
                    or pcm.get("sourceCodecName") != "pcm_s16le"
                ):
                    raise RenderArtifactError(
                        f"timeline preview audio input {index} content changed"
                    )
                audio_paths.append(audio_path)

            filter_graph = _timeline_preview_mix_filter_graph(audio_mix)
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
                "-fflags", "+bitexact",
                "-hwaccel", "none",
                "-noautorotate",
                "-i", str(video_path),
            ]
            for audio_path in audio_paths:
                command.extend(["-i", str(audio_path)])
            command.extend(
                [
                    "-filter_complex", filter_graph,
                    "-map", "0:v:0",
                    "-map", "[aout]",
                    "-frames:v", str(output["totalFrames"]),
                    "-fps_mode", "passthrough",
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", str(output["audioBitRate"]),
                    "-ar", str(output["sampleRate"]),
                    "-ac", str(output["channelCount"]),
                    "-flags:a", "+bitexact",
                    "-map_metadata", "-1",
                    "-map_chapters", "-1",
                    "-metadata", "creation_time=1970-01-01T00:00:00Z",
                    "-movflags", "+faststart",
                    "-video_track_timescale",
                    str(output_rate.numerator * 512),
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
                    pass_fds=ffmpeg_runtime.pass_fds,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise RenderArtifactError(
                    "FFmpeg timeline preview composition failed"
                ) from exc

            return self._finalize_timeline_preview_candidate_v1(
                candidate=candidate,
                request=request,
                video=video,
                output=output,
                output_rate=output_rate,
                root=root,
                output_name=output_name,
                ffmpeg_runtime=ffmpeg_runtime,
                ffprobe_runtime=ffprobe_runtime,
                ffmpeg_identity=ffmpeg_identity,
            )

    def _finalize_timeline_preview_candidate_v1(
        self,
        *,
        candidate: Path,
        request: Mapping[str, Any],
        video: Mapping[str, Any],
        output: Mapping[str, Any],
        output_rate: Fraction,
        root: Path,
        output_name: str,
        ffmpeg_runtime: _PinnedRuntimeBinary,
        ffprobe_runtime: _PinnedRuntimeBinary,
        ffmpeg_identity: str,
    ) -> dict[str, Any]:
        with _PinnedRegularFile(
            candidate,
            label="timeline preview candidate",
        ) as pinned_candidate:
            return self._finalize_pinned_timeline_preview_candidate_v1(
                pinned_candidate=pinned_candidate,
                request=request,
                video=video,
                output=output,
                output_rate=output_rate,
                root=root,
                output_name=output_name,
                ffmpeg_runtime=ffmpeg_runtime,
                ffprobe_runtime=ffprobe_runtime,
                ffmpeg_identity=ffmpeg_identity,
            )

    def _finalize_pinned_timeline_preview_candidate_v1(
        self,
        *,
        pinned_candidate: _PinnedRegularFile,
        request: Mapping[str, Any],
        video: Mapping[str, Any],
        output: Mapping[str, Any],
        output_rate: Fraction,
        root: Path,
        output_name: str,
        ffmpeg_runtime: _PinnedRuntimeBinary,
        ffprobe_runtime: _PinnedRuntimeBinary,
        ffmpeg_identity: str,
    ) -> dict[str, Any]:
        candidate = pinned_candidate.descriptor_path
        ffmpeg_path = ffmpeg_runtime.executable_path
        ffprobe_path = ffprobe_runtime.executable_path
        pass_fds = (
            *pinned_candidate.pass_fds,
            *ffmpeg_runtime.pass_fds,
            *ffprobe_runtime.pass_fds,
        )
        candidate_probe = _glyph_probe(
            candidate,
            ffprobe_path,
            pass_fds=pass_fds,
        )
        streams = candidate_probe.get("streams")
        if not isinstance(streams, list):
            raise RenderArtifactError(
                "timeline preview output stream layout is invalid"
            )
        video_streams = [
            stream
            for stream in streams
            if isinstance(stream, Mapping)
            and stream.get("codec_type") == "video"
        ]
        audio_streams = [
            stream
            for stream in streams
            if isinstance(stream, Mapping)
            and stream.get("codec_type") == "audio"
        ]
        if (
            len(streams) != 2
            or len(video_streams) != 1
            or len(audio_streams) != 1
        ):
            raise RenderArtifactError(
                "timeline preview output stream layout is invalid"
            )
        output_video = video_streams[0]
        output_audio = audio_streams[0]
        try:
            output_audio_rate = int(output_audio.get("sample_rate"))
            output_audio_channels = int(output_audio.get("channels"))
        except (TypeError, ValueError) as exc:
            raise RenderArtifactError(
                "timeline preview output audio probe is invalid"
            ) from exc
        if (
            output_video.get("codec_name") != output["videoCodec"]
            or output_video.get("pix_fmt") != output["pixelFormat"]
            or _stream_integer(
                output_video, "width", label="timeline preview output width"
            )
            != output["width"]
            or _stream_integer(
                output_video, "height", label="timeline preview output height"
            )
            != output["height"]
            or _stream_frame_count(
                output_video, label="timeline preview output"
            )
            != output["totalFrames"]
            or _stream_frame_rate(
                output_video, label="timeline preview output"
            )
            != output_rate
            or output_audio.get("codec_name") != output["audioCodec"]
            or output_audio_rate != output["sampleRate"]
            or output_audio_channels != output["channelCount"]
        ):
            raise RenderArtifactError(
                "timeline preview output media contract is invalid"
            )
        try:
            pixel_digest = decoded_frame_pixel_digest_metadata(
                candidate,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                pass_fds=pass_fds,
            )
            pcm_digest = canonical_pcm_digest_metadata(
                pinned_candidate.source_path,
                expected_sample_count=output["durationSamples"],
                allow_aac_frame_padding=True,
                ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path,
                pass_fds=(
                    *ffmpeg_runtime.pass_fds,
                    *ffprobe_runtime.pass_fds,
                ),
                _input_descriptor=pinned_candidate.descriptor,
            )
        except DigestError as exc:
            raise RenderArtifactError(
                "timeline preview output digest failed"
            ) from exc
        pinned_candidate.require_stable()
        if (
            pixel_digest.get("decodedFramePixelDigest")
            != video["decodedFramePixelDigest"]
            or pixel_digest.get("decodedFramePixelDigestSpec")
            != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
            or pixel_digest.get("width") != output["width"]
            or pixel_digest.get("height") != output["height"]
            or pixel_digest.get("frameCount") != output["totalFrames"]
            or pcm_digest.get("pcmDigestSpec") != PCM_CONTENT_DIGEST_SPEC
            or pcm_digest.get("sampleRate") != output["sampleRate"]
            or pcm_digest.get("channelCount") != output["channelCount"]
            or pcm_digest.get("sampleCount") != output["durationSamples"]
            or pcm_digest.get("sourceChannelCount") != output["channelCount"]
            or pcm_digest.get("sourceCodecName") != output["audioCodec"]
        ):
            raise RenderArtifactError(
                "timeline preview output content contract is invalid"
            )
        output_digest = {
            "fileDigest": pixel_digest["fileDigest"],
            "fileDigestAlgorithm": pixel_digest["fileDigestAlgorithm"],
            "decodedFramePixelDigest": pixel_digest[
                "decodedFramePixelDigest"
            ],
            "decodedFramePixelDigestSpec": pixel_digest[
                "decodedFramePixelDigestSpec"
            ],
            "pixelMode": pixel_digest["pixelMode"],
            "width": pixel_digest["width"],
            "height": pixel_digest["height"],
            "frameCount": pixel_digest["frameCount"],
            "frameRate": dict(output["frameRate"]),
            "pcmContentDigest": pcm_digest["pcmContentDigest"],
            "pcmDigestSpec": pcm_digest["pcmDigestSpec"],
            "sampleRate": pcm_digest["sampleRate"],
            "channelCount": pcm_digest["channelCount"],
            "sampleCount": pcm_digest["sampleCount"],
        }
        output_media_probe = {
            "container": output["container"],
            "videoCodec": output["videoCodec"],
            "pixelFormat": output["pixelFormat"],
            "width": output["width"],
            "height": output["height"],
            "frameRate": dict(output["frameRate"]),
            "frameCount": output["totalFrames"],
            "audioCodec": output["audioCodec"],
            "sampleRate": output["sampleRate"],
            "channelCount": output["channelCount"],
            "sampleCount": output["durationSamples"],
        }
        ffmpeg_runtime.require_stable()
        ffprobe_runtime.require_stable()
        pinned_candidate.require_stable()
        runtime_payload = {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": _TIMELINE_PREVIEW_RENDERER_IDENTITY,
            "rendererVersion": _TIMELINE_PREVIEW_RENDERER_VERSION,
        }
        runtime_evidence_digest = "sha256:" + sha256(
            _timeline_preview_canonical_json(runtime_payload)
        ).hexdigest()
        destination = _publish_timeline_output_v1(
            root=self.artifact_root,
            directory=root / "composition",
            source=pinned_candidate,
            expected_file_digest=output_digest["fileDigest"],
            output_name=output_name,
        )
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(
                destination.relative_to(self.artifact_root)
            ),
            "outputByteSize": os.fstat(
                pinned_candidate.descriptor
            ).st_size,
            "outputMediaProbe": output_media_probe,
            "outputDigest": output_digest,
            "rendererIdentity": _TIMELINE_PREVIEW_RENDERER_IDENTITY,
            "rendererVersion": _TIMELINE_PREVIEW_RENDERER_VERSION,
            "ffmpegIdentity": ffmpeg_identity,
            "runtimeEvidenceDigest": runtime_evidence_digest,
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["payloadDigest"],
            "timelineVersionRef": request["timelineVersionRef"],
            "timelineVersionDigest": request["timelineVersionDigest"],
            "inputBindingsDigest": request["inputBindingsDigest"],
            "subtitleManifestRef": request["subtitleManifest"][
                "subtitleManifestRef"
            ],
            "subtitleManifestDigest": request["subtitleManifest"][
                "subtitleManifestDigest"
            ],
            "publicationAllowed": False,
        }

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
