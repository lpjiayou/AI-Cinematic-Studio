"""Deterministic, local-only technical analysis for M12 audio artifacts.

The analyzer accepts only a sealed ``v4.audio-artifact-evidence.v1`` object and
resolves its ``storageKey`` below one caller-pinned artifact root.  Arbitrary
input paths are deliberately not part of the public contract.  It emits new V4
analysis evidence; it does not mutate the source evidence, create an
``AssetVersion``, perform admission, or advance publication state.

PCM content identity is computed over FFmpeg-decoded, headerless
``s16le/48000/stereo`` frames.  Container metadata therefore has no influence on
``pcmContentDigest``.  All thresholds and decimal representations used by the
analysis are frozen below and are included in ``analysisParametersDigest``.
"""

from __future__ import annotations

from array import array
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from fractions import Fraction
from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, BinaryIO, Mapping


SOURCE_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.audio-artifact-evidence.v1"
AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION = (
    "v4.audio-technical-analysis-evidence.v1"
)
PCM_CONTENT_DIGEST_SPEC_SCHEMA_VERSION = "v4.pcm-content-digest-spec.v1"
PCM_CLIPPING_THRESHOLD_SCHEMA_VERSION = "v4.pcm-clipping-threshold.v1"
AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_SCHEMA_VERSION = (
    "v4.audio-technical-analysis-parameters.v1"
)
AUDIO_TECHNICAL_VALIDATOR_IDENTITY = "v4.ffmpeg-audio-technical-validator.v1"
AUDIO_TECHNICAL_VALIDATOR_VERSION = "1"

CANONICAL_PCM_SAMPLE_RATE = 48_000
CANONICAL_PCM_CHANNEL_COUNT = 2
MAX_DURATION_SAMPLES = 28_800_000
MAX_CANONICAL_PCM_BYTES = (
    MAX_DURATION_SAMPLES * CANONICAL_PCM_CHANNEL_COUNT * 2
)
MAX_SOURCE_ARTIFACT_BYTES = MAX_CANONICAL_PCM_BYTES + 1_048_576
SILENCE_THRESHOLD_MAX_ABS = 32
SILENCE_MINIMUM_FRAME_COUNT = 4_800
CLIPPING_THRESHOLD_ABS = 32_767
CLIPPING_MAXIMUM_SAMPLE_COUNT = 0
CLIPPING_FAILURE_REASON = "CLIPPING_THRESHOLD_EXCEEDED"
VALIDATION_STATE_PASSED = "PASSED"
VALIDATION_STATE_FAILED = "FAILED"
ANALYSIS_STATE_COMPLETE = "TECHNICAL_ANALYSIS_COMPLETE"

_AUDIO_STORAGE_PREFIX = "asset-versions/audio/"
_FFMPEG_TIMEOUT_SECONDS = 120
_FFPROBE_TIMEOUT_SECONDS = 30
_VERSION_TIMEOUT_SECONDS = 10
_STREAM_CHUNK_BYTES = 1024 * 1024
_LUFS_DECIMAL_PLACES = 3
_DC_OFFSET_DECIMAL_PLACES = 9
_LOUDNORM_FILTER = "loudnorm=I=-24:LRA=7:TP=-2:print_format=json"

_PCM_CONTENT_DIGEST_SPEC_TEMPLATE: dict[str, Any] = {
    "schemaVersion": PCM_CONTENT_DIGEST_SPEC_SCHEMA_VERSION,
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

_PCM_CLIPPING_THRESHOLD_TEMPLATE: dict[str, Any] = {
    "schemaVersion": PCM_CLIPPING_THRESHOLD_SCHEMA_VERSION,
    "sampleFormat": "s16le",
    "absoluteMagnitude": CLIPPING_THRESHOLD_ABS,
    "maximumClippedSampleCount": CLIPPING_MAXIMUM_SAMPLE_COUNT,
    "comparison": "ABSOLUTE_SAMPLE_GREATER_THAN_OR_EQUAL",
}

_AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_TEMPLATE: dict[str, Any] = {
    "schemaVersion": AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_SCHEMA_VERSION,
    "pcmDigestSpec": deepcopy(_PCM_CONTENT_DIGEST_SPEC_TEMPLATE),
    "clippingThreshold": deepcopy(_PCM_CLIPPING_THRESHOLD_TEMPLATE),
    "technicalMetrics": {
        "sampleFormat": "s16le",
        "sampleRate": CANONICAL_PCM_SAMPLE_RATE,
        "channelDomain": "SOURCE_NATIVE",
        "monoScalarSamplesCountedOnce": True,
        "loudnessChannelLayout": "SOURCE_NATIVE",
    },
    "loudness": {
        "filter": _LOUDNORM_FILTER,
        "integratedTargetLufs": "-24.000",
        "loudnessRangeTargetLra": "7.000",
        "truePeakTargetDbtp": "-2.000",
        "parseRule": "ONE_COMPLETE_JSON_OBJECT_WITH_FINITE_INPUT_FIELDS",
        "integratedField": "input_i",
        "loudnessRangeField": "input_lra",
        "truePeakField": "input_tp",
    },
    "silence": {
        "thresholdDbfs": "-60.000",
        "absoluteMagnitudeMaximum": SILENCE_THRESHOLD_MAX_ABS,
        "minimumFrameCount": SILENCE_MINIMUM_FRAME_COUNT,
        "channelRule": "ALL_CHANNELS_AT_OR_BELOW",
        "rangeSemantics": "HALF_OPEN_CANONICAL_FRAMES",
    },
    "decimalRepresentation": {
        "integratedLufsPlaces": _LUFS_DECIMAL_PLACES,
        "loudnessRangeLraPlaces": _LUFS_DECIMAL_PLACES,
        "truePeakDbtpPlaces": _LUFS_DECIMAL_PLACES,
        "dcOffsetPlaces": _DC_OFFSET_DECIMAL_PLACES,
        "rounding": "ROUND_HALF_EVEN",
        "negativeZero": "NORMALIZED_TO_POSITIVE_ZERO",
    },
}

# Detached public values make the frozen contracts easy for tests and callers to
# inspect.  Analysis itself always uses the private templates above, so a caller
# cannot change analyzer behavior by mutating an imported dictionary.
PCM_CONTENT_DIGEST_SPEC = deepcopy(_PCM_CONTENT_DIGEST_SPEC_TEMPLATE)
PCM_CLIPPING_THRESHOLD = deepcopy(_PCM_CLIPPING_THRESHOLD_TEMPLATE)
AUDIO_TECHNICAL_ANALYSIS_PARAMETERS = deepcopy(
    _AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_TEMPLATE
)


class AudioTechnicalAnalysisError(RuntimeError):
    """Base failure at the isolated V4 audio-analysis boundary."""


class AudioTechnicalEvidenceValidationError(AudioTechnicalAnalysisError):
    """The sealed source artifact evidence is invalid or unsupported."""


class AudioTechnicalRuntimeError(AudioTechnicalAnalysisError):
    """A required local FFmpeg/FFprobe runtime could not execute."""


class AudioTechnicalArtifactError(AudioTechnicalAnalysisError):
    """Pinned artifact bytes could not produce trustworthy technical evidence."""


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
        raise AudioTechnicalEvidenceValidationError(
            "audio technical payload is not canonical JSON"
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST = _digest(
    _AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_TEMPLATE
)


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise AudioTechnicalEvidenceValidationError(
            "audio technical payload is already sealed"
        )
    result["payloadDigest"] = _digest(result)
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256(value: Any, field: str) -> str:
    if not _is_sha256(value):
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 2_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    return value


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    return value


_SOURCE_LINEAGE_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
    }
)
_SOURCE_EVIDENCE_FIELDS = _SOURCE_LINEAGE_FIELDS | frozenset(
    {
        "schemaVersion",
        "generationRequestDigest",
        "executionRequestDigest",
        "artifactEvidenceRef",
        "artifactRef",
        "storageKey",
        "byteSize",
        "sha256",
        "sampleRate",
        "channels",
        "probe",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
        "adapterIdentity",
        "audioRole",
        "provenance",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_AUDIO_ROLES = frozenset(
    {"dialogue", "narration", "music", "sfx", "ambience", "preliminary_mix"}
)
_SOURCE_PROBE_FIELDS = frozenset(
    {
        "sampleRate",
        "channels",
        "durationSeconds",
        "durationSamples",
        "codec",
        "container",
    }
)
_ANALYSIS_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "analysisEvidenceRef",
        "sourceArtifactEvidenceRef",
        "sourceArtifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "codec",
        "container",
        "sampleRate",
        "channelCount",
        "channelLayout",
        "sampleCount",
        "duration",
        "integratedLufs",
        "loudnessRangeLra",
        "truePeakDbtp",
        "maxSamplePeak",
        "silenceRanges",
        "clippedSampleCount",
        "clippingThreshold",
        "clippingDetected",
        "dcOffset",
        "pcmContentDigest",
        "pcmDigestSpec",
        "analysisParametersDigest",
        "validatorIdentity",
        "validatorVersion",
        "ffmpegVersion",
        "ffprobeVersion",
        "validationState",
        "failureReasons",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)


def _storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(_AUDIO_STORAGE_PREFIX):
        raise AudioTechnicalEvidenceValidationError("storageKey is invalid")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or "." in pure.parts
        or ".." in pure.parts
        or "//" in value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or value.endswith("/")
        or pure.suffix.lower() != ".wav"
    ):
        raise AudioTechnicalEvidenceValidationError("storageKey is invalid")
    return value


def _verify_source_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence must be an object"
        )
    evidence = deepcopy(dict(value))
    if set(evidence) != _SOURCE_EVIDENCE_FIELDS:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence fields are invalid"
        )
    claimed_digest = evidence.pop("payloadDigest", None)
    if not _is_sha256(claimed_digest) or claimed_digest != _digest(evidence):
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence payload digest is invalid"
        )
    evidence["payloadDigest"] = claimed_digest
    if evidence.get("schemaVersion") != SOURCE_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence schema is invalid"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
        "artifactEvidenceRef",
        "artifactRef",
        "adapterIdentity",
    ):
        _text(evidence.get(field), field, maximum=512)
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "generationRequestDigest",
        "executionRequestDigest",
        "sha256",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
    ):
        _sha256(evidence.get(field), field)
    evidence["storageKey"] = _storage_key(evidence.get("storageKey"))
    byte_size = _positive_integer(evidence.get("byteSize"), "byteSize")
    if byte_size > MAX_SOURCE_ARTIFACT_BYTES:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact byteSize exceeds the frozen maximum"
        )
    if evidence.get("sampleRate") != CANONICAL_PCM_SAMPLE_RATE:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact sampleRate is unsupported"
        )
    if evidence.get("channels") not in {1, 2}:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact channels are unsupported"
        )
    if (
        evidence.get("audioRole") not in _SOURCE_AUDIO_ROLES
        or evidence.get("provenance") != "LOCAL_EVIDENCE"
        or evidence.get("state") != "TECHNICALLY_VERIFIED"
        or evidence.get("publicationAllowed") is not False
    ):
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence semantics are invalid"
        )
    probe = evidence.get("probe")
    if not isinstance(probe, Mapping) or set(probe) != _SOURCE_PROBE_FIELDS:
        raise AudioTechnicalEvidenceValidationError("source artifact probe is invalid")
    probe = deepcopy(dict(probe))
    duration_seconds = probe.get("durationSeconds")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or duration_seconds <= 0
        or probe.get("sampleRate") != evidence["sampleRate"]
        or probe.get("channels") != evidence["channels"]
        or probe.get("codec") != "pcm_s16le"
        or probe.get("container") != "wav"
    ):
        raise AudioTechnicalEvidenceValidationError("source artifact probe is invalid")
    duration_samples = _positive_integer(
        probe.get("durationSamples"), "probe.durationSamples"
    )
    if duration_samples > MAX_DURATION_SAMPLES:
        raise AudioTechnicalEvidenceValidationError(
            "source artifact durationSamples exceeds the frozen maximum"
        )
    evidence["probe"] = probe

    expected_artifact_ref = "audio-artifact-" + evidence["sha256"][:32]
    evidence_semantic = {
        "generationRequestDigest": evidence["generationRequestDigest"],
        "executionRequestDigest": evidence["executionRequestDigest"],
        "storageKey": evidence["storageKey"],
        "sha256": evidence["sha256"],
    }
    expected_evidence_ref = "audio-artifact-evidence-" + _digest(
        evidence_semantic
    )[:32]
    if (
        evidence["artifactRef"] != expected_artifact_ref
        or evidence["artifactEvidenceRef"] != expected_evidence_ref
    ):
        raise AudioTechnicalEvidenceValidationError(
            "source artifact evidence references are invalid"
        )
    return evidence


def _open_pinned_artifact_root(value: Path | str) -> int:
    try:
        raw = Path(value)
    except TypeError as exc:
        raise AudioTechnicalEvidenceValidationError(
            "artifact_root is invalid"
        ) from exc
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        # One open pins the caller-selected root.  Resolving or probing the path
        # first would create a rename/replace window before the directory FD is
        # acquired.  All descendant access below is relative to this FD.
        descriptor = os.open(raw, flags)
        opened = os.fstat(descriptor)
    except OSError as exc:
        raise AudioTechnicalEvidenceValidationError(
            "artifact_root cannot be pinned"
        ) from exc
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise AudioTechnicalEvidenceValidationError(
            "artifact_root is unavailable"
        )
    return descriptor


def _open_pinned_artifact(root_descriptor: int, storage_key: str) -> int:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.dup(root_descriptor)
        parts = PurePosixPath(storage_key).parts
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=directory_descriptor)
            os.close(directory_descriptor)
            directory_descriptor = child
        descriptor = os.open(parts[-1], file_flags, dir_fd=directory_descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            os.close(descriptor)
            raise AudioTechnicalArtifactError(
                "pinned audio artifact is not one regular file"
            )
        return descriptor
    except AudioTechnicalArtifactError:
        raise
    except OSError as exc:
        raise AudioTechnicalArtifactError(
            "pinned audio artifact is unavailable"
        ) from exc
    finally:
        if directory_descriptor is not None:
            try:
                os.close(directory_descriptor)
            except OSError:
                pass


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _hash_descriptor(
    descriptor: int, *, maximum_bytes: int = MAX_SOURCE_ARTIFACT_BYTES
) -> tuple[str, int, tuple[int, ...]]:
    digest = sha256()
    byte_size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AudioTechnicalArtifactError(
                "pinned audio artifact is not one regular file"
            )
        if before.st_size > maximum_bytes:
            raise AudioTechnicalArtifactError(
                "pinned audio artifact exceeds the frozen byte maximum"
            )
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                break
            byte_size += len(chunk)
            if byte_size > maximum_bytes:
                raise AudioTechnicalArtifactError(
                    "pinned audio artifact exceeds the frozen byte maximum"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except AudioTechnicalArtifactError:
        raise
    except OSError as exc:
        raise AudioTechnicalArtifactError(
            "pinned audio artifact hashing failed"
        ) from exc
    if (
        _file_identity(before) != _file_identity(after)
        or byte_size != before.st_size
    ):
        raise AudioTechnicalArtifactError(
            "pinned audio artifact changed while hashing"
        )
    return digest.hexdigest(), byte_size, _file_identity(before)


def _hash_executable_descriptor(
    descriptor: int, name: str
) -> tuple[str, tuple[int, ...]]:
    digest = sha256()
    byte_size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            raise AudioTechnicalRuntimeError(f"{name} runtime is not a regular file")
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            byte_size += len(chunk)
        after = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except AudioTechnicalRuntimeError:
        raise
    except OSError as exc:
        raise AudioTechnicalRuntimeError(f"{name} runtime hashing failed") from exc
    if (
        _file_identity(before) != _file_identity(after)
        or byte_size != before.st_size
    ):
        raise AudioTechnicalRuntimeError(f"{name} runtime changed while hashing")
    return digest.hexdigest(), _file_identity(before)


def _open_executable(name: str) -> tuple[int, str, tuple[int, ...]]:
    resolved = shutil.which(name)
    if not resolved:
        raise AudioTechnicalRuntimeError(f"{name} runtime is unavailable")
    try:
        path = Path(resolved).resolve(strict=True)
    except OSError as exc:
        raise AudioTechnicalRuntimeError(f"{name} runtime is unavailable") from exc
    if not path.is_file() or not os.access(path, os.X_OK):
        raise AudioTechnicalRuntimeError(f"{name} runtime is unavailable")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise AudioTechnicalRuntimeError(f"{name} runtime cannot be pinned") from exc
    try:
        digest, identity = _hash_executable_descriptor(descriptor, name)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor, digest, identity


def _subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    environment["TZ"] = "UTC"
    return environment


def _runtime_version(descriptor: int, binary_digest: str, name: str) -> str:
    try:
        result = subprocess.run(
            [f"/proc/self/fd/{descriptor}", "-version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=_VERSION_TIMEOUT_SECONDS,
            env=_subprocess_environment(),
            pass_fds=(descriptor,),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise AudioTechnicalRuntimeError(
            f"{name} version is unavailable"
        ) from exc
    lines = result.stdout.splitlines()
    if result.returncode != 0 or not lines:
        raise AudioTechnicalRuntimeError(f"{name} version is unavailable")
    first_line = lines[0].strip()
    if not first_line or any(ord(character) < 32 for character in first_line):
        raise AudioTechnicalRuntimeError(f"{name} version is invalid")
    return f"{first_line} | sha256:{binary_digest}"


def _proc_descriptor_path(descriptor: int) -> str:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
    except OSError as exc:
        raise AudioTechnicalArtifactError(
            "pinned audio descriptor cannot be rewound"
        ) from exc
    return f"/proc/self/fd/{descriptor}"


def _probe_artifact(
    ffprobe_descriptor: int,
    descriptor: int,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    command = [
        f"/proc/self/fd/{ffprobe_descriptor}",
        "-v",
        "error",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout:"
            "format=format_name"
        ),
        "-of",
        "json",
        _proc_descriptor_path(descriptor),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            env=_subprocess_environment(),
            pass_fds=(ffprobe_descriptor, descriptor),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioTechnicalRuntimeError("local FFprobe analysis failed") from exc
    except (subprocess.SubprocessError, UnicodeError) as exc:
        raise AudioTechnicalArtifactError("audio FFprobe output is invalid") from exc
    if result.returncode != 0:
        raise AudioTechnicalArtifactError("audio FFprobe analysis failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AudioTechnicalArtifactError("audio FFprobe output is invalid") from exc
    streams = payload.get("streams")
    format_value = payload.get("format")
    if (
        not isinstance(streams, list)
        or len(streams) != 1
        or not isinstance(streams[0], Mapping)
        or streams[0].get("index") != 0
        or streams[0].get("codec_type") != "audio"
        or not isinstance(format_value, Mapping)
    ):
        raise AudioTechnicalArtifactError(
            "audio artifact must contain exactly one audio stream"
        )
    stream = streams[0]
    try:
        sample_rate = int(stream.get("sample_rate"))
        channel_count = int(stream.get("channels"))
    except (TypeError, ValueError) as exc:
        raise AudioTechnicalArtifactError("audio FFprobe values are invalid") from exc
    codec = stream.get("codec_name")
    container = format_value.get("format_name")
    expected_layout = "mono" if channel_count == 1 else "stereo"
    raw_layout = stream.get("channel_layout")
    channel_layout = expected_layout if raw_layout in {None, "unknown"} else raw_layout
    source_probe = evidence["probe"]
    if (
        codec != source_probe["codec"]
        or container != source_probe["container"]
        or sample_rate != evidence["sampleRate"]
        or channel_count != evidence["channels"]
        or channel_count not in {1, 2}
        or channel_layout != expected_layout
    ):
        raise AudioTechnicalArtifactError(
            "audio FFprobe values do not match source evidence"
        )
    return {
        "codec": codec,
        "container": container,
        "sampleRate": sample_rate,
        "channelCount": channel_count,
        "channelLayout": channel_layout,
    }


def _canonical_filter(channel_count: int) -> str:
    if channel_count == 1:
        return (
            "pan=stereo|c0=c0|c1=c0,"
            "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
        )
    if channel_count == 2:
        return (
            "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
        )
    raise AudioTechnicalArtifactError("audio channel count is unsupported")


def _technical_filter(channel_count: int) -> str:
    if channel_count == 1:
        return "aformat=sample_rates=48000:channel_layouts=mono"
    if channel_count == 2:
        return "aformat=sample_rates=48000:channel_layouts=stereo"
    raise AudioTechnicalArtifactError("audio channel count is unsupported")


def _ffmpeg_base(ffmpeg_descriptor: int) -> list[str]:
    return [
        f"/proc/self/fd/{ffmpeg_descriptor}",
        "-nostdin",
        "-hide_banner",
        "-threads",
        "1",
        "-filter_threads",
        "1",
        "-filter_complex_threads",
        "1",
    ]


def _decode_canonical_pcm(
    ffmpeg_descriptor: int,
    descriptor: int,
    channel_count: int,
    expected_sample_count: int,
) -> BinaryIO:
    expected_bytes = expected_sample_count * CANONICAL_PCM_CHANNEL_COUNT * 2
    if expected_bytes <= 0 or expected_bytes > MAX_CANONICAL_PCM_BYTES:
        raise AudioTechnicalArtifactError(
            "expected PCM byte count exceeds the frozen duration maximum"
        )
    raw = tempfile.TemporaryFile(mode="w+b")
    command = [
        *_ffmpeg_base(ffmpeg_descriptor),
        "-loglevel",
        "error",
        "-i",
        _proc_descriptor_path(descriptor),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        _canonical_filter(channel_count),
        "-ar",
        str(CANONICAL_PCM_SAMPLE_RATE),
        "-ac",
        str(CANONICAL_PCM_CHANNEL_COUNT),
        "-c:a",
        "pcm_s16le",
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-fs",
        str(expected_bytes + CANONICAL_PCM_CHANNEL_COUNT * 2),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=_subprocess_environment(),
            pass_fds=(ffmpeg_descriptor, descriptor),
        )
        if process.stdout is None:
            raise AudioTechnicalRuntimeError("local FFmpeg PCM pipe is unavailable")
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + _FFMPEG_TIMEOUT_SECONDS
        captured = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AudioTechnicalRuntimeError("local FFmpeg PCM decode timed out")
            events = selector.select(timeout=min(remaining, 0.25))
            if not events:
                if process.poll() is None:
                    continue
                try:
                    chunk = os.read(process.stdout.fileno(), _STREAM_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
            else:
                try:
                    chunk = os.read(process.stdout.fileno(), _STREAM_CHUNK_BYTES)
                except BlockingIOError:
                    continue
                if not chunk:
                    break
            captured += len(chunk)
            if captured > expected_bytes:
                raise AudioTechnicalArtifactError(
                    "decoded PCM exceeds source evidence durationSamples"
                )
            raw.write(chunk)
        return_code = process.wait(timeout=max(deadline - time.monotonic(), 0.001))
        if return_code != 0:
            raise AudioTechnicalArtifactError("audio PCM decode failed")
    except (AudioTechnicalAnalysisError, OSError, subprocess.SubprocessError) as exc:
        if process is not None and process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.SubprocessError:
                pass
        raw.close()
        if isinstance(exc, AudioTechnicalAnalysisError):
            raise
        raise AudioTechnicalRuntimeError("local FFmpeg PCM decode failed") from exc
    finally:
        if selector is not None:
            selector.close()
        if process is not None and process.stdout is not None:
            process.stdout.close()
    raw.seek(0)
    return raw


def _canonical_pcm_metrics(
    raw: BinaryIO, source_channel_count: int
) -> dict[str, Any]:
    if source_channel_count not in {1, 2}:
        raise AudioTechnicalArtifactError("audio channel count is unsupported")
    digest = sha256()
    frame_count = 0
    scalar_sample_count = 0
    signed_sum = 0
    max_sample_peak = 0
    clipped_sample_count = 0
    silence_ranges: list[dict[str, int]] = []
    silence_start: int | None = None

    while True:
        chunk = raw.read(_STREAM_CHUNK_BYTES)
        if not chunk:
            break
        if len(chunk) % (CANONICAL_PCM_CHANNEL_COUNT * 2) != 0:
            raise AudioTechnicalArtifactError(
                "canonical PCM byte count is not frame-aligned"
            )
        digest.update(chunk)
        samples = array("h")
        samples.frombytes(chunk)
        if sys.byteorder != "little":
            samples.byteswap()
        for offset in range(0, len(samples), CANONICAL_PCM_CHANNEL_COUNT):
            canonical_frame = samples[
                offset : offset + CANONICAL_PCM_CHANNEL_COUNT
            ]
            technical_frame = (
                canonical_frame[:1]
                if source_channel_count == 1
                else canonical_frame
            )
            magnitudes = [abs(sample) for sample in technical_frame]
            frame_peak = max(magnitudes)
            max_sample_peak = max(max_sample_peak, frame_peak)
            clipped_sample_count += sum(
                magnitude >= CLIPPING_THRESHOLD_ABS for magnitude in magnitudes
            )
            signed_sum += sum(technical_frame)
            scalar_sample_count += source_channel_count
            if all(
                magnitude <= SILENCE_THRESHOLD_MAX_ABS
                for magnitude in magnitudes
            ):
                if silence_start is None:
                    silence_start = frame_count
            elif silence_start is not None:
                if frame_count - silence_start >= SILENCE_MINIMUM_FRAME_COUNT:
                    silence_ranges.append(
                        {
                            "startSample": silence_start,
                            "endSampleExclusive": frame_count,
                        }
                    )
                silence_start = None
            frame_count += 1

    if frame_count <= 0 or scalar_sample_count <= 0:
        raise AudioTechnicalArtifactError("canonical PCM stream is empty")
    if (
        silence_start is not None
        and frame_count - silence_start >= SILENCE_MINIMUM_FRAME_COUNT
    ):
        silence_ranges.append(
            {
                "startSample": silence_start,
                "endSampleExclusive": frame_count,
            }
        )
    denominator = scalar_sample_count * 32_768
    dc_offset = _fixed_decimal(
        Decimal(signed_sum) / Decimal(denominator),
        _DC_OFFSET_DECIMAL_PLACES,
        "dcOffset",
    )
    return {
        "pcmContentDigest": digest.hexdigest(),
        "sampleCount": frame_count,
        "maxSamplePeak": max_sample_peak,
        "silenceRanges": silence_ranges,
        "clippedSampleCount": clipped_sample_count,
        "dcOffset": dc_offset,
    }


def _loudness_output(
    ffmpeg_descriptor: int, descriptor: int, channel_count: int
) -> str:
    filtergraph = f"{_technical_filter(channel_count)},{_LOUDNORM_FILTER}"
    command = [
        *_ffmpeg_base(ffmpeg_descriptor),
        "-loglevel",
        "info",
        "-i",
        _proc_descriptor_path(descriptor),
        "-map",
        "0:a:0",
        "-vn",
        "-sn",
        "-dn",
        "-af",
        filtergraph,
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            env=_subprocess_environment(),
            pass_fds=(ffmpeg_descriptor, descriptor),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioTechnicalRuntimeError(
            "local FFmpeg loudness analysis failed"
        ) from exc
    except (subprocess.SubprocessError, UnicodeError) as exc:
        raise AudioTechnicalArtifactError("audio loudness output is invalid") from exc
    if result.returncode != 0:
        raise AudioTechnicalArtifactError("audio loudness analysis failed")
    return result.stderr


def _loudnorm_objects(output: str) -> list[Mapping[str, Any]]:
    decoder = json.JSONDecoder()
    objects: list[Mapping[str, Any]] = []
    index = 0
    while index < len(output):
        start = output.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(output, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = end
        if isinstance(value, Mapping) and any(
            field in value for field in ("input_i", "input_lra", "input_tp")
        ):
            objects.append(value)
    return objects


def _fixed_decimal(value: Any, places: int, field: str) -> str:
    if isinstance(value, bool):
        raise AudioTechnicalArtifactError(f"{field} is invalid")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if not decimal_value.is_finite():
            raise AudioTechnicalArtifactError(f"{field} is not finite")
        quantum = Decimal(1).scaleb(-places)
        rounded = decimal_value.quantize(quantum, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError) as exc:
        raise AudioTechnicalArtifactError(f"{field} is invalid") from exc
    if rounded == 0:
        rounded = abs(rounded)
    return f"{rounded:.{places}f}"


def _parse_loudness(output: str) -> dict[str, str]:
    objects = _loudnorm_objects(output)
    if len(objects) != 1:
        raise AudioTechnicalArtifactError(
            "loudnorm must emit exactly one complete JSON object"
        )
    payload = objects[0]
    required = {"input_i", "input_lra", "input_tp"}
    if not required.issubset(payload):
        raise AudioTechnicalArtifactError("loudnorm fields are missing")
    return {
        "integratedLufs": _fixed_decimal(
            payload["input_i"], _LUFS_DECIMAL_PLACES, "integratedLufs"
        ),
        "loudnessRangeLra": _fixed_decimal(
            payload["input_lra"], _LUFS_DECIMAL_PLACES, "loudnessRangeLra"
        ),
        "truePeakDbtp": _fixed_decimal(
            payload["input_tp"], _LUFS_DECIMAL_PLACES, "truePeakDbtp"
        ),
    }


def _reduced_duration(sample_count: int) -> dict[str, Any]:
    duration = Fraction(sample_count, CANONICAL_PCM_SAMPLE_RATE)
    return {
        "numerator": duration.numerator,
        "denominator": duration.denominator,
        "unit": "SECONDS",
    }


def _analysis_evidence_ref(payload: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(payload))
    semantic.pop("analysisEvidenceRef", None)
    semantic.pop("payloadDigest", None)
    return "audio-technical-analysis-evidence-" + _digest(semantic)[:32]


def _verify_artifact_unchanged(
    *,
    descriptor: int,
    root_descriptor: int,
    storage_key: str,
    expected_digest: str,
    expected_size: int,
    expected_identity: tuple[int, ...],
) -> None:
    digest_after, size_after, identity_after = _hash_descriptor(descriptor)
    if (
        digest_after != expected_digest
        or size_after != expected_size
        or identity_after != expected_identity
    ):
        raise AudioTechnicalArtifactError(
            "pinned audio artifact changed during analysis"
        )
    reopened: int | None = None
    try:
        reopened = _open_pinned_artifact(root_descriptor, storage_key)
        reopened_digest, reopened_size, reopened_identity = _hash_descriptor(reopened)
        if (
            reopened_digest != expected_digest
            or reopened_size != expected_size
            or reopened_identity != expected_identity
        ):
            raise AudioTechnicalArtifactError(
                "pinned audio storage entry changed during analysis"
            )
    finally:
        if reopened is not None:
            try:
                os.close(reopened)
            except OSError:
                pass


def _verify_executable_unchanged(
    descriptor: int,
    name: str,
    expected_digest: str,
    expected_identity: tuple[int, ...],
) -> None:
    digest_after, identity_after = _hash_executable_descriptor(descriptor, name)
    if digest_after != expected_digest or identity_after != expected_identity:
        raise AudioTechnicalRuntimeError(f"{name} runtime changed during analysis")


def _nonnegative_integer(value: Any, field: str, *, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > maximum
    ):
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    return value


def _validate_decimal_string(value: Any, places: int, field: str) -> str:
    if not isinstance(value, str):
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    try:
        normalized = _fixed_decimal(value, places, field)
    except AudioTechnicalArtifactError as exc:
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid") from exc
    if value != normalized:
        raise AudioTechnicalEvidenceValidationError(f"{field} is not canonical")
    return value


def _validate_runtime_evidence(value: Any, field: str) -> str:
    normalized = _text(value, field, maximum=4_000)
    first_line, separator, digest = normalized.rpartition(" | sha256:")
    runtime_name = field.removesuffix("Version")
    if (
        not separator
        or not first_line.startswith(f"{runtime_name} version ")
        or not _is_sha256(digest)
    ):
        raise AudioTechnicalEvidenceValidationError(f"{field} is invalid")
    return normalized


def _validate_analysis_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analysis evidence must be an object"
        )
    evidence = deepcopy(dict(value))
    if set(evidence) != _ANALYSIS_EVIDENCE_FIELDS:
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analysis evidence fields are invalid"
        )
    claimed_digest = evidence.pop("payloadDigest", None)
    if not _is_sha256(claimed_digest) or claimed_digest != _digest(evidence):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analysis payload digest is invalid"
        )
    evidence["payloadDigest"] = claimed_digest
    if (
        evidence.get("schemaVersion")
        != AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION
    ):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analysis schema is invalid"
        )
    for field in (
        "analysisEvidenceRef",
        "sourceArtifactEvidenceRef",
        "artifactRef",
    ):
        _text(evidence.get(field), field, maximum=512)
    for field in (
        "sourceArtifactEvidenceDigest",
        "fileDigest",
        "pcmContentDigest",
        "analysisParametersDigest",
    ):
        _sha256(evidence.get(field), field)
    evidence["storageKey"] = _storage_key(evidence.get("storageKey"))
    byte_size = _positive_integer(evidence.get("byteSize"), "byteSize")
    if byte_size > MAX_SOURCE_ARTIFACT_BYTES:
        raise AudioTechnicalEvidenceValidationError(
            "audio technical byteSize exceeds the frozen maximum"
        )
    if (
        evidence.get("artifactRef")
        != "audio-artifact-" + evidence["fileDigest"][:32]
        or evidence.get("codec") != "pcm_s16le"
        or evidence.get("container") != "wav"
        or evidence.get("sampleRate") != CANONICAL_PCM_SAMPLE_RATE
        or evidence.get("channelCount") not in {1, 2}
        or evidence.get("channelLayout")
        != ("mono" if evidence.get("channelCount") == 1 else "stereo")
    ):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical format projection is invalid"
        )
    sample_count = _positive_integer(evidence.get("sampleCount"), "sampleCount")
    if sample_count > MAX_DURATION_SAMPLES:
        raise AudioTechnicalEvidenceValidationError(
            "audio technical sampleCount exceeds the frozen maximum"
        )
    if evidence.get("duration") != _reduced_duration(sample_count):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical duration is invalid"
        )
    for field in ("integratedLufs", "loudnessRangeLra", "truePeakDbtp"):
        _validate_decimal_string(evidence.get(field), _LUFS_DECIMAL_PLACES, field)
    dc_offset = _validate_decimal_string(
        evidence.get("dcOffset"), _DC_OFFSET_DECIMAL_PLACES, "dcOffset"
    )
    if abs(Decimal(dc_offset)) > 1:
        raise AudioTechnicalEvidenceValidationError("dcOffset is out of range")
    if Decimal(evidence["loudnessRangeLra"]) < 0:
        raise AudioTechnicalEvidenceValidationError(
            "loudnessRangeLra is out of range"
        )
    max_sample_peak = _nonnegative_integer(
        evidence.get("maxSamplePeak"), "maxSamplePeak", maximum=32_768
    )
    maximum_scalar_samples = sample_count * evidence["channelCount"]
    clipped_sample_count = _nonnegative_integer(
        evidence.get("clippedSampleCount"),
        "clippedSampleCount",
        maximum=maximum_scalar_samples,
    )
    clipping_detected = clipped_sample_count > CLIPPING_MAXIMUM_SAMPLE_COUNT
    if (
        evidence.get("clippingThreshold") != _PCM_CLIPPING_THRESHOLD_TEMPLATE
        or evidence.get("clippingDetected") is not clipping_detected
        or (clipping_detected and max_sample_peak < CLIPPING_THRESHOLD_ABS)
        or (not clipping_detected and max_sample_peak >= CLIPPING_THRESHOLD_ABS)
    ):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical clipping projection is invalid"
        )
    silence_ranges = evidence.get("silenceRanges")
    if not isinstance(silence_ranges, list):
        raise AudioTechnicalEvidenceValidationError("silenceRanges is invalid")
    previous_end = -1
    for index, item in enumerate(silence_ranges):
        if not isinstance(item, Mapping) or set(item) != {
            "startSample",
            "endSampleExclusive",
        }:
            raise AudioTechnicalEvidenceValidationError(
                f"silenceRanges[{index}] is invalid"
            )
        start = item.get("startSample")
        end = item.get("endSampleExclusive")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < 0
            or end > sample_count
            or end - start < SILENCE_MINIMUM_FRAME_COUNT
            or start <= previous_end
        ):
            raise AudioTechnicalEvidenceValidationError(
                f"silenceRanges[{index}] is invalid"
            )
        previous_end = end
    if (
        evidence.get("pcmDigestSpec") != _PCM_CONTENT_DIGEST_SPEC_TEMPLATE
        or evidence.get("analysisParametersDigest")
        != AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST
        or evidence.get("validatorIdentity")
        != AUDIO_TECHNICAL_VALIDATOR_IDENTITY
        or evidence.get("validatorVersion")
        != AUDIO_TECHNICAL_VALIDATOR_VERSION
    ):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analyzer binding is invalid"
        )
    _validate_runtime_evidence(evidence.get("ffmpegVersion"), "ffmpegVersion")
    _validate_runtime_evidence(evidence.get("ffprobeVersion"), "ffprobeVersion")
    expected_validation = (
        VALIDATION_STATE_FAILED if clipping_detected else VALIDATION_STATE_PASSED
    )
    expected_reasons = [CLIPPING_FAILURE_REASON] if clipping_detected else []
    if (
        evidence.get("validationState") != expected_validation
        or evidence.get("failureReasons") != expected_reasons
        or evidence.get("state") != ANALYSIS_STATE_COMPLETE
        or evidence.get("publicationAllowed") is not False
    ):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical validation state is invalid"
        )
    if evidence.get("analysisEvidenceRef") != _analysis_evidence_ref(evidence):
        raise AudioTechnicalEvidenceValidationError(
            "audio technical analysisEvidenceRef is invalid"
        )
    return evidence


@dataclass(frozen=True, slots=True, init=False)
class AudioTechnicalAnalysisEvidence:
    """Immutable exact wrapper for sealed V4 technical-analysis evidence."""

    _payload_json: str

    @classmethod
    def _from_analyzer(cls, value: Any) -> "AudioTechnicalAnalysisEvidence":
        normalized = _validate_analysis_evidence(value)
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            _canonical(normalized).decode("utf-8"),
        )
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def analyze_audio_artifact(
    artifact_evidence: Mapping[str, Any], *, artifact_root: Path | str
) -> AudioTechnicalAnalysisEvidence:
    """Analyze one digest-pinned V4 audio artifact and seal exact V4 evidence.

    The function accepts no media path.  It resolves only the exact ``storageKey``
    carried by a valid source evidence object and retains an open descriptor for
    the entire probe/decode/loudness operation.  File identity and content are
    checked both before and after analysis, including a final secure re-open of
    the storage entry.
    """

    root_descriptor: int | None = None
    descriptor: int | None = None
    ffmpeg_descriptor: int | None = None
    ffprobe_descriptor: int | None = None
    try:
        root_descriptor = _open_pinned_artifact_root(artifact_root)
        evidence = _verify_source_evidence(artifact_evidence)
        descriptor = _open_pinned_artifact(
            root_descriptor, evidence["storageKey"]
        )
        file_digest, byte_size, file_identity = _hash_descriptor(descriptor)
        if file_digest != evidence["sha256"] or byte_size != evidence["byteSize"]:
            raise AudioTechnicalArtifactError(
                "pinned audio bytes do not match source evidence"
            )

        (
            ffmpeg_descriptor,
            ffmpeg_digest,
            ffmpeg_identity,
        ) = _open_executable("ffmpeg")
        (
            ffprobe_descriptor,
            ffprobe_digest,
            ffprobe_identity,
        ) = _open_executable("ffprobe")
        ffmpeg_version = _runtime_version(
            ffmpeg_descriptor, ffmpeg_digest, "ffmpeg"
        )
        ffprobe_version = _runtime_version(
            ffprobe_descriptor, ffprobe_digest, "ffprobe"
        )
        probe = _probe_artifact(ffprobe_descriptor, descriptor, evidence)

        raw = _decode_canonical_pcm(
            ffmpeg_descriptor,
            descriptor,
            probe["channelCount"],
            evidence["probe"]["durationSamples"],
        )
        try:
            pcm = _canonical_pcm_metrics(raw, probe["channelCount"])
        finally:
            raw.close()
        if pcm["sampleCount"] != evidence["probe"]["durationSamples"]:
            raise AudioTechnicalArtifactError(
                "decoded PCM sampleCount does not match source evidence"
            )
        loudness = _parse_loudness(
            _loudness_output(
                ffmpeg_descriptor, descriptor, probe["channelCount"]
            )
        )

        _verify_artifact_unchanged(
            descriptor=descriptor,
            root_descriptor=root_descriptor,
            storage_key=evidence["storageKey"],
            expected_digest=file_digest,
            expected_size=byte_size,
            expected_identity=file_identity,
        )
        _verify_executable_unchanged(
            ffmpeg_descriptor,
            "ffmpeg",
            ffmpeg_digest,
            ffmpeg_identity,
        )
        _verify_executable_unchanged(
            ffprobe_descriptor,
            "ffprobe",
            ffprobe_digest,
            ffprobe_identity,
        )

        clipping_detected = (
            pcm["clippedSampleCount"] > CLIPPING_MAXIMUM_SAMPLE_COUNT
        )
        semantic: dict[str, Any] = {
            "schemaVersion": AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION,
            "sourceArtifactEvidenceRef": evidence["artifactEvidenceRef"],
            "sourceArtifactEvidenceDigest": evidence["payloadDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": evidence["storageKey"],
            "byteSize": byte_size,
            "fileDigest": file_digest,
            "codec": probe["codec"],
            "container": probe["container"],
            "sampleRate": probe["sampleRate"],
            "channelCount": probe["channelCount"],
            "channelLayout": probe["channelLayout"],
            "sampleCount": pcm["sampleCount"],
            "duration": _reduced_duration(pcm["sampleCount"]),
            **loudness,
            "maxSamplePeak": pcm["maxSamplePeak"],
            "silenceRanges": pcm["silenceRanges"],
            "clippedSampleCount": pcm["clippedSampleCount"],
            "clippingThreshold": deepcopy(_PCM_CLIPPING_THRESHOLD_TEMPLATE),
            "clippingDetected": clipping_detected,
            "dcOffset": pcm["dcOffset"],
            "pcmContentDigest": pcm["pcmContentDigest"],
            "pcmDigestSpec": deepcopy(_PCM_CONTENT_DIGEST_SPEC_TEMPLATE),
            "analysisParametersDigest": AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST,
            "validatorIdentity": AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
            "validatorVersion": AUDIO_TECHNICAL_VALIDATOR_VERSION,
            "ffmpegVersion": ffmpeg_version,
            "ffprobeVersion": ffprobe_version,
            "validationState": (
                VALIDATION_STATE_FAILED
                if clipping_detected
                else VALIDATION_STATE_PASSED
            ),
            "failureReasons": (
                [CLIPPING_FAILURE_REASON] if clipping_detected else []
            ),
            "state": ANALYSIS_STATE_COMPLETE,
            "publicationAllowed": False,
        }
        semantic["analysisEvidenceRef"] = _analysis_evidence_ref(semantic)
        return AudioTechnicalAnalysisEvidence._from_analyzer(_sealed(semantic))
    finally:
        for open_descriptor in (
            descriptor,
            ffmpeg_descriptor,
            ffprobe_descriptor,
            root_descriptor,
        ):
            if open_descriptor is None:
                continue
            try:
                os.close(open_descriptor)
            except OSError:
                pass


__all__ = [
    "SOURCE_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION",
    "PCM_CONTENT_DIGEST_SPEC_SCHEMA_VERSION",
    "PCM_CLIPPING_THRESHOLD_SCHEMA_VERSION",
    "AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_SCHEMA_VERSION",
    "AUDIO_TECHNICAL_VALIDATOR_IDENTITY",
    "AUDIO_TECHNICAL_VALIDATOR_VERSION",
    "CANONICAL_PCM_SAMPLE_RATE",
    "CANONICAL_PCM_CHANNEL_COUNT",
    "MAX_DURATION_SAMPLES",
    "MAX_CANONICAL_PCM_BYTES",
    "MAX_SOURCE_ARTIFACT_BYTES",
    "SILENCE_THRESHOLD_MAX_ABS",
    "SILENCE_MINIMUM_FRAME_COUNT",
    "CLIPPING_THRESHOLD_ABS",
    "CLIPPING_MAXIMUM_SAMPLE_COUNT",
    "CLIPPING_FAILURE_REASON",
    "VALIDATION_STATE_PASSED",
    "VALIDATION_STATE_FAILED",
    "ANALYSIS_STATE_COMPLETE",
    "PCM_CONTENT_DIGEST_SPEC",
    "PCM_CLIPPING_THRESHOLD",
    "AUDIO_TECHNICAL_ANALYSIS_PARAMETERS",
    "AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST",
    "AudioTechnicalAnalysisError",
    "AudioTechnicalEvidenceValidationError",
    "AudioTechnicalRuntimeError",
    "AudioTechnicalArtifactError",
    "AudioTechnicalAnalysisEvidence",
    "analyze_audio_artifact",
]
