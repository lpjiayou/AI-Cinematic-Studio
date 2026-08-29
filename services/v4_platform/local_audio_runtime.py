"""Pinned, offline-only FFmpeg runtime for deterministic local audio synthesis.

This module is intentionally narrow.  It exposes no caller-selected command,
filter, input, protocol, environment, or executable path.  The sibling audio
synthesis module owns the closed recipes and passes only arguments that it built
itself.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
from typing import Any, Mapping, Sequence


LOCAL_AUDIO_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    "v4.local-audio-runtime-evidence.v1"
)
BUILTIN_FFMPEG_AUDIO_ADAPTER_ID = "v4.builtin-ffmpeg-audio-synthesizer.v2"
FFMPEG_PROTOCOL_WHITELIST = ("file", "pipe")
FFMPEG_EXECUTION_TIMEOUT_SECONDS = 120
FFMPEG_VERSION_TIMEOUT_SECONDS = 10

_STREAM_CHUNK_BYTES = 1024 * 1024
_MINIMAL_ENVIRONMENT = {
    "LC_ALL": "C",
    "LANG": "C",
    "TZ": "UTC",
}


class LocalAudioRuntimeError(RuntimeError):
    """The pinned local FFmpeg runtime was unavailable or changed."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise LocalAudioRuntimeError("runtime evidence is not canonical JSON") from exc


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise LocalAudioRuntimeError("runtime evidence is already sealed")
    result["payloadDigest"] = _digest(result)
    return result


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _hash_executable(descriptor: int) -> tuple[str, tuple[int, ...]]:
    digest = sha256()
    byte_size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink < 1
            or before.st_size <= 0
        ):
            raise LocalAudioRuntimeError("FFmpeg runtime is not a regular file")
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            byte_size += len(chunk)
        after = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except LocalAudioRuntimeError:
        raise
    except OSError as exc:
        raise LocalAudioRuntimeError("FFmpeg runtime hashing failed") from exc
    if (
        _file_identity(before) != _file_identity(after)
        or byte_size != before.st_size
    ):
        raise LocalAudioRuntimeError("FFmpeg runtime changed while hashing")
    return digest.hexdigest(), _file_identity(before)


def _open_ffmpeg() -> tuple[int, str, tuple[int, ...]]:
    resolved = shutil.which("ffmpeg")
    if not resolved:
        raise LocalAudioRuntimeError("FFmpeg runtime is unavailable")
    try:
        path = Path(resolved).resolve(strict=True)
    except OSError as exc:
        raise LocalAudioRuntimeError("FFmpeg runtime is unavailable") from exc
    if not path.is_file() or not os.access(path, os.X_OK):
        raise LocalAudioRuntimeError("FFmpeg runtime is unavailable")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LocalAudioRuntimeError("FFmpeg runtime cannot be pinned") from exc
    try:
        binary_digest, identity = _hash_executable(descriptor)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, binary_digest, identity


def _version(descriptor: int, binary_digest: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            [f"/proc/self/fd/{descriptor}", "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=FFMPEG_VERSION_TIMEOUT_SECONDS,
            env=dict(_MINIMAL_ENVIRONMENT),
            pass_fds=(descriptor,),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise LocalAudioRuntimeError("FFmpeg version is unavailable") from exc
    lines = result.stdout.splitlines()
    if result.returncode != 0 or not lines:
        raise LocalAudioRuntimeError("FFmpeg version is unavailable")
    normalized_lines = [line.rstrip() for line in lines]
    first_line = normalized_lines[0].strip()
    if (
        not first_line
        or len(first_line) > 2_000
        or sum(len(line) for line in normalized_lines) > 100_000
        or any(ord(character) < 32 or ord(character) == 127 for character in first_line)
    ):
        raise LocalAudioRuntimeError("FFmpeg version is invalid")
    build_fingerprint = sha256(
        "\n".join(normalized_lines).encode("utf-8")
    ).hexdigest()
    return f"{first_line} | sha256:{binary_digest}", build_fingerprint


def _cpu_profile() -> dict[str, Any]:
    flags: set[str] = set()
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8", errors="strict") as source:
            for line in source:
                key, separator, raw_value = line.partition(":")
                if separator and key.strip().lower() in {"flags", "features"}:
                    flags.update(raw_value.split())
    except (OSError, UnicodeError):
        flags = set()
    semantic = {
        "system": platform.system(),
        "machine": platform.machine(),
        "release": platform.release(),
        "cpuFlags": sorted(flags),
    }
    return {**semantic, "profileDigest": _digest(semantic)}


class _PinnedFfmpegAudioRuntime:
    """One-use-capable pinned FFmpeg process boundary.

    Resolution, version inspection, synthesis execution, and the final mutation
    check all use the same open executable descriptor.
    """

    def __init__(self) -> None:
        descriptor, binary_digest, identity = _open_ffmpeg()
        self._descriptor: int | None = descriptor
        self._binary_digest = binary_digest
        self._identity = identity
        try:
            self._version, self._build_fingerprint = _version(
                descriptor, binary_digest
            )
        except Exception:
            os.close(descriptor)
            self._descriptor = None
            raise
        self._executed = False

    @property
    def binary_digest(self) -> str:
        return self._binary_digest

    @property
    def version(self) -> str:
        return self._version

    def _open_descriptor(self) -> int:
        if self._descriptor is None:
            raise LocalAudioRuntimeError("FFmpeg runtime is closed")
        return self._descriptor

    def verify_unchanged(self) -> None:
        descriptor = self._open_descriptor()
        digest, identity = _hash_executable(descriptor)
        if digest != self._binary_digest or identity != self._identity:
            raise LocalAudioRuntimeError("FFmpeg runtime changed during execution")

    def render(self, arguments: Sequence[str], *, pass_fds: Sequence[int]) -> None:
        """Execute one internally-built audio command through the pinned binary."""

        if self._executed:
            raise LocalAudioRuntimeError("FFmpeg runtime instance is single-use")
        if (
            not isinstance(arguments, (tuple, list))
            or not arguments
            or any(not isinstance(item, str) or "\x00" in item for item in arguments)
        ):
            raise LocalAudioRuntimeError("FFmpeg internal arguments are invalid")
        descriptor = self._open_descriptor()
        inherited = tuple(dict.fromkeys((descriptor, *pass_fds)))
        command = [
            f"/proc/self/fd/{descriptor}",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-protocol_whitelist",
            ",".join(FFMPEG_PROTOCOL_WHITELIST),
            *arguments,
        ]
        self._executed = True
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                timeout=FFMPEG_EXECUTION_TIMEOUT_SECONDS,
                env=dict(_MINIMAL_ENVIRONMENT),
                pass_fds=inherited,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise LocalAudioRuntimeError("local FFmpeg synthesis failed") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            if len(detail) > 1_000:
                detail = detail[:1_000]
            raise LocalAudioRuntimeError(
                "local FFmpeg synthesis failed"
                + (f": {detail}" if detail else "")
            )
        self.verify_unchanged()

    def evidence(self, *, command_spec_digest: str) -> dict[str, Any]:
        if (
            not isinstance(command_spec_digest, str)
            or len(command_spec_digest) != 64
            or any(character not in "0123456789abcdef" for character in command_spec_digest)
            or not self._executed
        ):
            raise LocalAudioRuntimeError("runtime command binding is invalid")
        self.verify_unchanged()
        return _sealed(
            {
                "schemaVersion": LOCAL_AUDIO_RUNTIME_EVIDENCE_SCHEMA_VERSION,
                "engine": "FFMPEG",
                "adapterIdentity": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
                "binarySha256": self._binary_digest,
                "version": self._version,
                "ffmpegBuildFingerprint": self._build_fingerprint,
                "cpuProfile": _cpu_profile(),
                "determinismScope": "SAME_FFMPEG_BUILD_AND_CPU_PROFILE",
                "protocolWhitelist": list(FFMPEG_PROTOCOL_WHITELIST),
                "networkAccess": "DENIED_BY_CLOSED_RECIPE_AND_PROTOCOL_WHITELIST",
                "environment": deepcopy(_MINIMAL_ENVIRONMENT),
                "threadCount": 1,
                "filterThreadCount": 1,
                "bitExact": True,
                "commandSpecDigest": command_spec_digest,
                "state": "PINNED_EXECUTION_COMPLETE",
            }
        )

    def close(self) -> None:
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def __enter__(self) -> "_PinnedFfmpegAudioRuntime":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()


__all__ = [
    "LOCAL_AUDIO_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "BUILTIN_FFMPEG_AUDIO_ADAPTER_ID",
    "FFMPEG_PROTOCOL_WHITELIST",
    "LocalAudioRuntimeError",
]
