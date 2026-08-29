"""Deterministic local M12 audio execution adapters.

The module is deliberately independent from the legacy G5 media-job adapter.  It
accepts no provider credentials and no caller-selected input paths.  Programmatic
ambience/SFX are synthesized from closed parameter sets, while preliminary mixes
may read only digest-pinned WAV artifacts below one constructor-pinned root.

V4 returns candidates and sealed execution evidence.  It does not create or admit
V5 ``AssetVersion`` records.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
from typing import Any, Mapping, Protocol

from .audio_validation import (
    AudioTechnicalAnalysisEvidence,
    analyze_audio_artifact,
)


AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.audio-artifact-evidence.v1"
AUDIO_GENERATION_RESULT_SCHEMA_VERSION = "v4.audio-generation-result.v1"
AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION = "v4.audio-artifact-result.v1"
PIPER_TTS_EXECUTION_EVIDENCE_SCHEMA_VERSION = (
    "v4.piper-tts-execution-evidence.v1"
)
AUDIO_STORAGE_PREFIX = "asset-versions/audio/"
TTS_EXECUTION_REQUEST_SCHEMA_VERSION = "v4.local-tts-request.v1"
PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION = (
    "v5.k2-programmatic-audio-generation-request.v1"
)
PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION = (
    "v4.preliminary-audio-mix-request.v1"
)
PIPER_TTS_ADAPTER_ID = "v4.local-piper-tts.v1"
PIPER_TTS_EXECUTION_STATE = "PIPER_TTS_TECHNICALLY_VERIFIED"
PROGRAMMATIC_AUDIO_ADAPTER_ID = (
    "v4.deterministic-programmatic-ffmpeg-audio.v1"
)
PRELIMINARY_MIX_ADAPTER_ID = "v4.deterministic-preliminary-ffmpeg-mix.v2"

SPEECH_AUDIO_ROLES = frozenset({"dialogue", "narration"})
PROGRAMMATIC_AUDIO_ROLES = frozenset({"ambience", "sfx"})
AUDIO_ROLES = SPEECH_AUDIO_ROLES | PROGRAMMATIC_AUDIO_ROLES | frozenset({"music"})
PROGRAMMATIC_EFFECTS = frozenset({"rain", "wind", "fire_crackle", "paper"})

_DescriptorIdentity = tuple[int, int, int, int, int, int]
_DescriptorDigest = tuple[str, int, _DescriptorIdentity]

_COMMON_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "assetRequirementRef",
        "assetRequirementDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "mediaKind",
        "mediaType",
        "adapterCapability",
        "parameters",
        "state",
        "requestedProvenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TTS_REQUEST_FIELDS = _COMMON_REQUEST_FIELDS | frozenset(
    {
        "generationRequestDigest",
        "scriptSceneRef",
        "sourceScriptSpan",
        "dialogueOrdinal",
        "dialogueSourceDigest",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "engine",
    }
)
_PROGRAMMATIC_REQUEST_FIELDS = _COMMON_REQUEST_FIELDS | frozenset(
    {
        "version",
        "scriptSceneRef",
        "sourceCueRef",
        "sourceCueDigest",
        "cueOrdinal",
        "createdBy",
        "createdAt",
    }
)
_MIX_REQUEST_FIELDS = _COMMON_REQUEST_FIELDS | frozenset({"scriptSceneRef"})

_FFMPEG_TIMEOUT_SECONDS = 120
_FFPROBE_TIMEOUT_SECONDS = 30
_SAMPLE_RATE = 48_000
_MAX_DURATION_SAMPLES = _SAMPLE_RATE * 600
_UINT32_MAX = (1 << 32) - 1

_EMOTION_PARAMETERS: dict[str, tuple[float, float, float]] = {
    "neutral": (0.0, 1.0, 1.0),
    "tense": (1.5, 1.08, 1.12),
    "whisper": (-1.0, 0.90, 0.58),
    "weary": (-2.0, 0.86, 0.72),
}

_FORBIDDEN_EXTERNAL_INPUT_KEYS = frozenset(
    {
        "path",
        "file",
        "filename",
        "uri",
        "url",
        "sourcepath",
        "inputpath",
        "audiopath",
        "sourceuri",
        "inputuri",
        "audiofile",
        "externalfile",
        "externalinput",
        "filepath",
        "sourcefile",
        "inputfile",
        "sourceurl",
        "inputurl",
        "externalurl",
        "audiobytes",
        "sourcebytes",
        "inputbytes",
    }
)


class AudioAdapterError(RuntimeError):
    """Base failure for the isolated V4 local-audio boundary."""


class AudioRequestValidationError(AudioAdapterError):
    """The closed local-audio request contract was not satisfied."""


class AudioRuntimeUnavailableError(AudioAdapterError):
    """A required local executable or injected runtime could not execute."""


class AudioArtifactVerificationError(AudioAdapterError):
    """Generated or internally resolved bytes failed independent verification."""


class AudioGenerationAdapter(Protocol):
    """The complete public execution contract shared by local audio adapters."""

    adapter_identity: str
    provenance: str

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path: ...


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
        raise AudioRequestValidationError("audio payload is not canonical JSON") from exc


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise AudioRequestValidationError("audio payload is already sealed")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioRequestValidationError(f"{field} must be an object")
    result = deepcopy(dict(value))
    claimed = result.pop("payloadDigest", None)
    if not _is_sha256(claimed) or claimed != _digest(result):
        raise AudioRequestValidationError(f"{field} payload digest is invalid")
    result["payloadDigest"] = claimed
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256(value: Any, field: str) -> str:
    if not _is_sha256(value):
        raise AudioRequestValidationError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 2_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 and character not in "\t\n\r" for character in value)
    ):
        raise AudioRequestValidationError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    return _text(value, field, maximum=512)


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise AudioRequestValidationError(f"{field} is invalid")
    return value


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _reject_external_inputs(value: Any) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            if (
                isinstance(raw_key, str)
                and _normalized_key(raw_key) in _FORBIDDEN_EXTERNAL_INPUT_KEYS
            ):
                raise AudioRequestValidationError("external audio input is forbidden")
            _reject_external_inputs(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_external_inputs(child)


def _closed_request(
    request: Any,
    *,
    schema_version: str,
    fields: frozenset[str],
    adapter_identity: str,
    state: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = _verify_sealed(request, "audio execution request")
    _reject_external_inputs(normalized)
    if set(normalized) != fields:
        raise AudioRequestValidationError("audio request fields are invalid")
    if (
        normalized.get("schemaVersion") != schema_version
        or normalized.get("mediaKind") != "audio"
        or normalized.get("mediaType") != "audio/wav"
        or normalized.get("adapterCapability") != adapter_identity
        or normalized.get("state") != state
        or normalized.get("requestedProvenance") != "LOCAL_EVIDENCE"
        or normalized.get("publicationAllowed") is not False
    ):
        raise AudioRequestValidationError("audio request semantics are invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "assetRequirementRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
    ):
        _ref(normalized.get(field), field)
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
    ):
        _sha256(normalized.get(field), field)
    parameters = normalized.get("parameters")
    if not isinstance(parameters, Mapping):
        raise AudioRequestValidationError("audio parameters must be an object")
    return normalized, deepcopy(dict(parameters))


def _tts_request(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, parameters = _closed_request(
        request,
        schema_version=TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
        fields=_TTS_REQUEST_FIELDS,
        adapter_identity=PIPER_TTS_ADAPTER_ID,
        state="LOCAL_EXECUTION_REQUEST",
    )
    _sha256(normalized.get("generationRequestDigest"), "generationRequestDigest")
    for field in (
        "scriptSceneRef",
        "sourceScriptSpan",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
    ):
        _ref(normalized.get(field), field)
    for field in ("dialogueSourceDigest", "voiceLockDigest"):
        _sha256(normalized.get(field), field)
    _integer(
        normalized.get("dialogueOrdinal"),
        "dialogueOrdinal",
        minimum=1,
        maximum=10_000,
    )
    engine = normalized.get("engine")
    if not isinstance(engine, Mapping) or set(engine) != {
        "engineFamily",
        "voiceId",
        "languageCode",
        "basePitchSemitones",
        "baseRateScale",
    }:
        raise AudioRequestValidationError("TTS engine binding is invalid")
    for field in ("engineFamily", "voiceId", "languageCode"):
        _ref(engine.get(field), f"engine.{field}")
    for field in ("basePitchSemitones", "baseRateScale"):
        value = engine.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or (field == "baseRateScale" and value <= 0)
        ):
            raise AudioRequestValidationError(f"engine.{field} is invalid")
    return normalized, parameters


def _programmatic_request(
    request: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, parameters = _closed_request(
        request,
        schema_version=PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION,
        fields=_PROGRAMMATIC_REQUEST_FIELDS,
        adapter_identity=PROGRAMMATIC_AUDIO_ADAPTER_ID,
        state="CONTRACT_ONLY_ADAPTER_REQUIRED",
    )
    if normalized.get("version") != 1:
        raise AudioRequestValidationError("programmatic request version is invalid")
    for field in ("scriptSceneRef", "sourceCueRef", "createdBy", "createdAt"):
        _ref(normalized.get(field), field)
    _sha256(normalized.get("sourceCueDigest"), "sourceCueDigest")
    _integer(
        normalized.get("cueOrdinal"),
        "cueOrdinal",
        minimum=1,
        maximum=10_000,
    )
    return normalized, parameters


def _mix_request(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, parameters = _closed_request(
        request,
        schema_version=PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
        fields=_MIX_REQUEST_FIELDS,
        adapter_identity=PRELIMINARY_MIX_ADAPTER_ID,
        state="LOCAL_EXECUTION_REQUEST",
    )
    _ref(normalized.get("scriptSceneRef"), "scriptSceneRef")
    return normalized, parameters


def emotion_parameters(emotion_tag: str) -> dict[str, float]:
    """Return the immutable-table pitch/rate/energy mapping as a detached value."""

    if not isinstance(emotion_tag, str) or emotion_tag not in _EMOTION_PARAMETERS:
        raise AudioRequestValidationError("emotionTag is invalid")
    pitch, rate, energy = _EMOTION_PARAMETERS[emotion_tag]
    return {"pitch": pitch, "rate": rate, "energy": energy}


def _validated_speech_request(
    request: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    normalized, parameters = _tts_request(request)
    required = {
        "speechSynthesis",
        "text",
        "voiceRef",
        "sampleRate",
        "channels",
        "audioRole",
    }
    allowed = required | {"emotionTag"}
    if set(parameters) - allowed or not required.issubset(parameters):
        raise AudioRequestValidationError("speech parameters are invalid")
    if parameters.get("speechSynthesis") is not True:
        raise AudioRequestValidationError("speechSynthesis must be true")
    _text(parameters.get("text"), "text")
    _ref(parameters.get("voiceRef"), "voiceRef")
    if parameters.get("sampleRate") != _SAMPLE_RATE:
        raise AudioRequestValidationError("sampleRate must be 48000")
    _integer(parameters.get("channels"), "channels", minimum=1, maximum=2)
    if parameters.get("audioRole") not in SPEECH_AUDIO_ROLES:
        raise AudioRequestValidationError("speech audioRole is invalid")
    if normalized.get("voiceRef") != parameters.get("voiceRef"):
        raise AudioRequestValidationError("TTS voiceRef lineage is inconsistent")
    tag = parameters.get("emotionTag", "neutral")
    mapping = emotion_parameters(tag)
    effective = deepcopy(parameters)
    effective.setdefault("emotionTag", tag)
    effective["emotionParameters"] = mapping
    return normalized, parameters, effective


def _speech_parameters(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, _, effective = _validated_speech_request(request)
    return normalized, effective


def _validate_candidate_path(candidate_path: Any) -> Path:
    if not isinstance(candidate_path, Path):
        raise AudioRequestValidationError("candidate_path must be a Path")
    if (
        candidate_path.name in {"", ".", ".."}
        or candidate_path.suffix.lower() != ".wav"
        or "\x00" in str(candidate_path)
    ):
        raise AudioRequestValidationError("candidate_path must name one WAV file")
    if candidate_path.exists() or candidate_path.is_symlink():
        raise AudioRequestValidationError("candidate_path already exists")
    return candidate_path


def _prepare_candidate(candidate_path: Any) -> Path:
    candidate = _validate_candidate_path(candidate_path)
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AudioRuntimeUnavailableError("candidate directory is unavailable") from exc
    if not candidate.parent.is_dir():
        raise AudioRuntimeUnavailableError("candidate directory is unavailable")
    return candidate


def _remove_partial(candidate_path: Path) -> None:
    try:
        if candidate_path.is_file() and not candidate_path.is_symlink():
            candidate_path.unlink()
    except OSError:
        pass


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise AudioRuntimeUnavailableError(f"{name} runtime is unavailable")
    path = Path(resolved).resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise AudioRuntimeUnavailableError(f"{name} runtime is unavailable")
    return str(path)


def _subprocess_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    environment["TZ"] = "UTC"
    return environment


def _run_ffmpeg(
    arguments: list[str],
    candidate_path: Path,
    *,
    pass_fds: tuple[int, ...] = (),
    cleanup_on_failure: bool = True,
) -> None:
    command = [
        _executable("ffmpeg"),
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
        "file,pipe",
        *arguments,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
            env=_subprocess_environment(),
            pass_fds=pass_fds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if cleanup_on_failure:
            _remove_partial(candidate_path)
        raise AudioRuntimeUnavailableError("local FFmpeg audio execution failed") from exc


def _wav_output_arguments(
    *,
    sample_rate: int,
    channels: int,
    candidate_path: Path | str,
    overwrite_open_descriptor: bool = False,
) -> list[str]:
    return [
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-fflags",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-write_bext",
        "0",
        "-write_peak",
        "off",
        "-rf64",
        "never",
        "-f",
        "wav",
        "-y" if overwrite_open_descriptor else "-n",
        str(candidate_path),
    ]


def _channel_tail(channels: int) -> str:
    if channels == 1:
        return ",aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono"
    return (
        ",pan=stereo|c0=c0|c1=c0,"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
    )


def _seconds(samples: int) -> str:
    whole, remainder = divmod(samples, _SAMPLE_RATE)
    if remainder == 0:
        return str(whole)
    return f"{whole}.{remainder * 10**9 // _SAMPLE_RATE:09d}".rstrip("0")


def _effect_parameters(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, parameters = _programmatic_request(request)
    fields = {
        "synthesisKind",
        "effectKind",
        "audioRole",
        "durationSamples",
        "sampleRate",
        "channels",
        "seed",
    }
    if set(parameters) != fields or parameters.get("synthesisKind") != "programmatic":
        raise AudioRequestValidationError("programmatic audio parameters are invalid")
    effect = parameters.get("effectKind")
    if effect not in PROGRAMMATIC_EFFECTS:
        raise AudioRequestValidationError("effectKind is invalid")
    expected_role = "ambience" if effect in {"rain", "wind"} else "sfx"
    if parameters.get("audioRole") != expected_role:
        raise AudioRequestValidationError("effect audioRole is invalid")
    if parameters.get("sampleRate") != _SAMPLE_RATE:
        raise AudioRequestValidationError("sampleRate must be 48000")
    _integer(parameters.get("channels"), "channels", minimum=1, maximum=2)
    duration = _integer(
        parameters.get("durationSamples"),
        "durationSamples",
        minimum=2_400 if effect == "paper" else 4_800,
        maximum=_SAMPLE_RATE if effect == "paper" else _MAX_DURATION_SAMPLES,
    )
    _integer(parameters.get("seed"), "seed", minimum=0, maximum=_UINT32_MAX)
    parameters["durationSamples"] = duration
    return normalized, parameters


def _effect_filtergraph(parameters: Mapping[str, Any]) -> tuple[list[str], str]:
    effect = parameters["effectKind"]
    seed = parameters["seed"]
    samples = parameters["durationSamples"]
    channels = parameters["channels"]
    tail = _channel_tail(channels)
    fade_out_start = _seconds(max(samples - 2_400, 0))

    if effect == "rain":
        envelope_seed = (seed ^ 0x9E3779B9) & _UINT32_MAX
        inputs = [
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=white:sample_rate=48000:amplitude=0.22:seed={seed}",
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=white:sample_rate=48000:amplitude=1:"
                f"seed={envelope_seed}"
            ),
        ]
        graph = (
            "[0:a]highpass=f=500:precision=f64,"
            "lowpass=f=9000:precision=f64[carrier];"
            "[1:a]lowpass=f=1.4:precision=f64,"
            "aeval=exprs='0.72+8*abs(val(0))':c=mono[envelope];"
            "[carrier][envelope]amultiply,"
            "afade=t=in:st=0:d=0.02,"
            f"afade=t=out:st={fade_out_start}:d=0.05,"
            "alimiter=limit=0.9:level=false:latency=true,"
            f"atrim=end_sample={samples},asetpts=N/SR/TB{tail}[out]"
        )
        return inputs, graph

    if effect == "wind":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:sample_rate=48000:amplitude=0.35:seed={seed}",
        ]
        graph = (
            "[0:a]lowpass=f=700:precision=f64,"
            "tremolo=f=0.18:d=0.65,highpass=f=30:precision=f64,"
            "afade=t=in:st=0:d=0.02,"
            f"afade=t=out:st={fade_out_start}:d=0.05,"
            "alimiter=limit=0.9:level=false:latency=true,"
            f"atrim=end_sample={samples},asetpts=N/SR/TB{tail}[out]"
        )
        return inputs, graph

    if effect == "fire_crackle":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=velvet:sample_rate=48000:amplitude=0.65:"
                f"seed={seed}:density=0.004"
            ),
        ]
        graph = (
            "[0:a]asplit=3[p1][p2][p3];"
            "[p1]bandpass=f=1200:t=q:w=7:precision=f64[f1];"
            "[p2]bandpass=f=2600:t=q:w=9:precision=f64[f2];"
            "[p3]bandpass=f=4800:t=q:w=11:precision=f64[f3];"
            "[f1][f2][f3]amix=inputs=3:weights='1 0.7 0.45':"
            "normalize=false:duration=longest:dropout_transition=0,"
            "afade=t=in:st=0:d=0.01,"
            f"afade=t=out:st={fade_out_start}:d=0.05,"
            "alimiter=limit=0.9:level=false:latency=true,"
            f"atrim=end_sample={samples},asetpts=N/SR/TB{tail}[out]"
        )
        return inputs, graph

    paper_fade_duration = _seconds(samples - 480)
    inputs = [
        "-f",
        "lavfi",
        "-i",
        f"anoisesrc=color=white:sample_rate=48000:amplitude=0.7:seed={seed}",
    ]
    graph = (
        "[0:a]highpass=f=2500:precision=f64,"
        "afade=t=in:st=0:d=0.002,"
        f"afade=t=out:st=0.01:d={paper_fade_duration}:curve=exp,"
        "alimiter=limit=0.9:level=false:latency=true,"
        f"atrim=end_sample={samples},asetpts=N/SR/TB{tail}[out]"
    )
    return inputs, graph


def _hash_regular_path(path: Path) -> tuple[str, int, tuple[int, int, int]]:
    digest = sha256()
    size = 0
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            os.close(descriptor)
            raise AudioArtifactVerificationError("audio artifact is not one regular file")
        with os.fdopen(descriptor, "rb") as source:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
            closed_over = os.fstat(source.fileno())
        if (
            opened.st_dev != closed_over.st_dev
            or opened.st_ino != closed_over.st_ino
            or opened.st_size != closed_over.st_size
            or size != opened.st_size
        ):
            raise AudioArtifactVerificationError("audio artifact changed while hashing")
    except AudioArtifactVerificationError:
        raise
    except OSError as exc:
        raise AudioArtifactVerificationError("audio artifact hashing failed") from exc
    return digest.hexdigest(), size, (opened.st_dev, opened.st_ino, opened.st_size)


def _descriptor_identity(metadata: os.stat_result) -> _DescriptorIdentity:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_nlink,
    )


def _hash_descriptor(descriptor: int) -> _DescriptorDigest:
    digest = sha256()
    size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise AudioArtifactVerificationError("audio input is not one regular file")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        closed_over = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except AudioArtifactVerificationError:
        raise
    except OSError as exc:
        raise AudioArtifactVerificationError("audio input hashing failed") from exc
    opened_identity = _descriptor_identity(opened)
    closed_identity = _descriptor_identity(closed_over)
    if opened_identity != closed_identity or size != opened.st_size:
        raise AudioArtifactVerificationError("audio input changed while hashing")
    return digest.hexdigest(), size, opened_identity


def _probe_wav(
    source: str | Path, *, pass_fds: tuple[int, ...] = ()
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                _executable("ffprobe"),
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=_FFPROBE_TIMEOUT_SECONDS,
            env=_subprocess_environment(),
            pass_fds=pass_fds,
        )
        payload = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise AudioArtifactVerificationError("audio ffprobe verification failed") from exc
    streams = payload.get("streams")
    if (
        not isinstance(streams, list)
        or len(streams) != 1
        or not isinstance(streams[0], Mapping)
        or streams[0].get("codec_type") != "audio"
        or streams[0].get("codec_name") != "pcm_s16le"
    ):
        raise AudioArtifactVerificationError("audio artifact must be one PCM WAV stream")
    stream = streams[0]
    format_value = payload.get("format")
    if not isinstance(format_value, Mapping) or format_value.get("format_name") != "wav":
        raise AudioArtifactVerificationError("audio artifact container is not WAV")
    try:
        sample_rate = int(stream.get("sample_rate"))
        channels = int(stream.get("channels"))
        duration = float(stream.get("duration", format_value.get("duration")))
    except (TypeError, ValueError):
        raise AudioArtifactVerificationError("audio probe values are invalid") from None
    if (
        sample_rate <= 0
        or channels not in {1, 2}
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise AudioArtifactVerificationError("audio probe values are invalid")
    return {
        "sampleRate": sample_rate,
        "channels": channels,
        "durationSeconds": duration,
        "durationSamples": int(round(duration * sample_rate)),
        "codec": "pcm_s16le",
        "container": "wav",
    }


def _verify_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    duration_samples: int | None = None,
) -> tuple[str, int, dict[str, Any]]:
    before_digest, byte_size, before_identity = _hash_regular_path(path)
    probe = _probe_wav(path)
    after_digest, after_size, after_identity = _hash_regular_path(path)
    if (
        before_digest != after_digest
        or byte_size != after_size
        or before_identity != after_identity
    ):
        raise AudioArtifactVerificationError("audio artifact changed during probe")
    if probe["sampleRate"] != sample_rate or probe["channels"] != channels:
        raise AudioArtifactVerificationError("audio artifact format does not match request")
    if duration_samples is not None and abs(probe["durationSamples"] - duration_samples) > 1:
        raise AudioArtifactVerificationError("audio artifact duration does not match request")
    return before_digest, byte_size, probe


class PiperTtsAdapter:
    """A-tier Piper boundary; production synthesis is deliberately unavailable."""

    __slots__ = ()

    adapter_identity = PIPER_TTS_ADAPTER_ID
    provenance = "LOCAL_EVIDENCE"

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path:
        _speech_parameters(request)
        _validate_candidate_path(candidate_path)
        raise NotImplementedError("PIPER_RUNTIME_ABSENT")


class DeterministicProgrammaticAudioAdapter:
    """Seeded FFmpeg synthesis for the frozen rain/wind/fire/paper set."""

    adapter_identity = PROGRAMMATIC_AUDIO_ADAPTER_ID
    provenance = "LOCAL_EVIDENCE"

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path:
        _, parameters = _effect_parameters(request)
        candidate = _prepare_candidate(candidate_path)
        inputs, graph = _effect_filtergraph(parameters)
        arguments = [
            *inputs,
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            *_wav_output_arguments(
                sample_rate=parameters["sampleRate"],
                channels=parameters["channels"],
                candidate_path=candidate,
            ),
        ]
        _run_ffmpeg(arguments, candidate)
        try:
            _verify_wav(
                candidate,
                sample_rate=parameters["sampleRate"],
                channels=parameters["channels"],
                duration_samples=parameters["durationSamples"],
            )
        except Exception:
            _remove_partial(candidate)
            raise
        return candidate


def _storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(AUDIO_STORAGE_PREFIX):
        raise AudioRequestValidationError("audio storageKey is invalid")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or ".." in pure.parts
        or "." in pure.parts
        or pure.as_posix() != value
        or "//" in value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or value.endswith("/")
        or pure.suffix.lower() != ".wav"
    ):
        raise AudioRequestValidationError("audio storageKey is invalid")
    return value


def _pinned_artifact_root(value: Path | str) -> Path:
    raw = Path(value)
    if raw.is_symlink():
        raise AudioRequestValidationError("artifact_root cannot be a symlink")
    try:
        root = raw.resolve(strict=True)
    except OSError as exc:
        raise AudioRequestValidationError("artifact_root is unavailable") from exc
    if not root.is_dir():
        raise AudioRequestValidationError("artifact_root is unavailable")
    return root


def _pinned_artifact_candidate(
    artifact_root: Path,
    storage_key: str,
    *,
    must_not_exist: bool,
) -> Path:
    parts = PurePosixPath(storage_key).parts
    candidate = artifact_root.joinpath(*parts)
    cursor = artifact_root
    for part in parts[:-1]:
        cursor = cursor / part
        if cursor.is_symlink():
            raise AudioRequestValidationError("artifact path contains a symlink")
        if cursor.exists() and not cursor.is_dir():
            raise AudioRequestValidationError("artifact parent is not a directory")
    try:
        candidate.parent.resolve(strict=False).relative_to(artifact_root)
    except (OSError, ValueError) as exc:
        raise AudioRequestValidationError("artifact path escapes its pinned root") from exc
    if candidate.is_symlink():
        raise AudioRequestValidationError("artifact candidate cannot be a symlink")
    if must_not_exist and candidate.exists():
        raise AudioRequestValidationError("artifact candidate already exists")
    if not must_not_exist and not candidate.is_file():
        raise AudioArtifactVerificationError("audio adapter did not create its candidate")
    return candidate


def _mix_parameters(request: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized, parameters = _mix_request(request)
    if set(parameters) != {
        "mixKind",
        "sampleRate",
        "channels",
        "durationSamples",
        "tracks",
    } or parameters.get("mixKind") != "preliminary":
        raise AudioRequestValidationError("preliminary mix parameters are invalid")
    if parameters.get("sampleRate") != _SAMPLE_RATE:
        raise AudioRequestValidationError("sampleRate must be 48000")
    channels = _integer(parameters.get("channels"), "channels", minimum=1, maximum=2)
    duration = _integer(
        parameters.get("durationSamples"),
        "durationSamples",
        minimum=1,
        maximum=_MAX_DURATION_SAMPLES,
    )
    tracks = parameters.get("tracks")
    if not isinstance(tracks, list) or not tracks or len(tracks) > 32:
        raise AudioRequestValidationError("preliminary mix tracks are invalid")
    normalized_tracks: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    for index, raw_track in enumerate(tracks):
        if not isinstance(raw_track, Mapping):
            raise AudioRequestValidationError("preliminary mix track is invalid")
        track = deepcopy(dict(raw_track))
        if set(track) != {
            "audioRole",
            "assetVersionRef",
            "assetVersionDigest",
            "storageKey",
            "sha256",
            "sampleRate",
            "channels",
            "durationSamples",
        }:
            raise AudioRequestValidationError("preliminary mix track fields are invalid")
        role = track.get("audioRole")
        if role not in AUDIO_ROLES:
            raise AudioRequestValidationError("preliminary mix audioRole is invalid")
        asset_ref = _ref(track.get("assetVersionRef"), f"tracks[{index}].assetVersionRef")
        if asset_ref in seen_refs:
            raise AudioRequestValidationError("preliminary mix track is duplicated")
        seen_refs.add(asset_ref)
        _sha256(track.get("assetVersionDigest"), f"tracks[{index}].assetVersionDigest")
        _sha256(track.get("sha256"), f"tracks[{index}].sha256")
        track["storageKey"] = _storage_key(track.get("storageKey"))
        if (
            track.get("sampleRate") != _SAMPLE_RATE
            or track.get("channels") != channels
            or track.get("durationSamples") != duration
        ):
            raise AudioRequestValidationError("preliminary mix track format is inconsistent")
        normalized_tracks.append(track)
    parameters["tracks"] = normalized_tracks
    return normalized, parameters


def _canonical_mix_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(parameters))
    result["tracks"] = sorted(
        result["tracks"],
        key=lambda item: (
            -(
                {
                    "dialogue": 3,
                    "narration": 3,
                    "sfx": 2,
                    "ambience": 1,
                    "music": 0,
                }[item["audioRole"]]
            ),
            item["assetVersionRef"],
        ),
    )
    return result


def _open_audio_root_descriptor(artifact_root: Path) -> tuple[int, tuple[int, int]]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(artifact_root, flags)
        info = os.fstat(descriptor)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise AudioArtifactVerificationError(
            "artifact root cannot be pinned"
        ) from exc
    if not stat.S_ISDIR(info.st_mode):
        os.close(descriptor)
        raise AudioArtifactVerificationError("artifact root is not a directory")
    return descriptor, (info.st_dev, info.st_ino)


def _open_audio_parent_descriptor(
    root_descriptor: int,
    parts: tuple[str, ...],
    *,
    create: bool,
) -> int:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        current = os.dup(root_descriptor)
    except OSError as exc:
        raise AudioArtifactVerificationError(
            "artifact root descriptor is unavailable"
        ) from exc
    try:
        for part in parts:
            next_descriptor: int | None = None
            try:
                next_descriptor = os.open(part, flags, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                next_descriptor = os.open(part, flags, dir_fd=current)
            try:
                info = os.fstat(next_descriptor)
            except OSError:
                os.close(next_descriptor)
                raise
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_descriptor)
                raise AudioArtifactVerificationError(
                    "artifact parent is not a directory"
                )
            os.close(current)
            current = next_descriptor
        return current
    except AudioArtifactVerificationError:
        os.close(current)
        raise
    except OSError as exc:
        os.close(current)
        raise AudioArtifactVerificationError(
            "artifact descendant cannot be pinned"
        ) from exc


def _mix_candidate_parts(artifact_root: Path, candidate_path: Any) -> tuple[Path, tuple[str, ...]]:
    candidate = _validate_candidate_path(candidate_path)
    absolute = Path(os.path.abspath(os.fspath(candidate)))
    try:
        relative = absolute.relative_to(artifact_root)
    except ValueError as exc:
        raise AudioRequestValidationError(
            "preliminary mix candidate must be below artifact_root"
        ) from exc
    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise AudioRequestValidationError("preliminary mix candidate is invalid")
    return absolute, parts


def _create_mix_output(
    artifact_root: Path,
    root_descriptor: int,
    candidate_path: Any,
) -> tuple[Path, int, int, str]:
    candidate, parts = _mix_candidate_parts(artifact_root, candidate_path)
    parent_descriptor = _open_audio_parent_descriptor(
        root_descriptor, parts[:-1], create=True
    )
    leaf = parts[-1]
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    output_descriptor: int | None = None
    try:
        output_descriptor = os.open(
            leaf, flags, 0o600, dir_fd=parent_descriptor
        )
        info = os.fstat(output_descriptor)
    except FileExistsError as exc:
        os.close(parent_descriptor)
        raise AudioRequestValidationError("candidate_path already exists") from exc
    except OSError as exc:
        if output_descriptor is not None:
            os.close(output_descriptor)
        os.close(parent_descriptor)
        raise AudioRuntimeUnavailableError(
            "preliminary mix output cannot be created"
        ) from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size != 0
    ):
        os.close(output_descriptor)
        os.close(parent_descriptor)
        raise AudioArtifactVerificationError(
            "preliminary mix output is not a new regular file"
        )
    return candidate, parent_descriptor, output_descriptor, leaf


def _verify_wav_descriptor(
    descriptor: int,
    *,
    sample_rate: int,
    channels: int,
    duration_samples: int,
) -> tuple[str, int, _DescriptorIdentity, dict[str, Any]]:
    before = _hash_descriptor(descriptor)
    probe = _probe_wav(
        f"/proc/self/fd/{descriptor}", pass_fds=(descriptor,)
    )
    after = _hash_descriptor(descriptor)
    if before != after:
        raise AudioArtifactVerificationError(
            "preliminary mix output changed during probe"
        )
    if (
        probe["sampleRate"] != sample_rate
        or probe["channels"] != channels
        or abs(probe["durationSamples"] - duration_samples) > 1
    ):
        raise AudioArtifactVerificationError(
            "preliminary mix output does not match request"
        )
    return (*before, probe)


def _verify_mix_output_visible(
    root_descriptor: int,
    relative_parts: tuple[str, ...],
    expected: _DescriptorDigest,
) -> None:
    parent_descriptor = _open_audio_parent_descriptor(
        root_descriptor, relative_parts[:-1], create=False
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(
            relative_parts[-1], flags, dir_fd=parent_descriptor
        )
        actual = _hash_descriptor(descriptor)
    except OSError as exc:
        raise AudioArtifactVerificationError(
            "preliminary mix output is no longer visible"
        ) from exc
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
        os.close(parent_descriptor)
    if actual != expected:
        raise AudioArtifactVerificationError(
            "preliminary mix output namespace binding changed"
        )


def _neutralize_audio_descriptor(descriptor: int) -> None:
    try:
        os.ftruncate(descriptor, 0)
        os.fsync(descriptor)
    except OSError:
        pass


def _open_internal_track(
    root_descriptor: int, track: Mapping[str, Any]
) -> tuple[int, _DescriptorDigest]:
    storage_key = track["storageKey"]
    parts = PurePosixPath(storage_key).parts
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_audio_parent_descriptor(
            root_descriptor, parts[:-1], create=False
        )
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
    except AudioArtifactVerificationError:
        raise
    except OSError as exc:
        raise AudioArtifactVerificationError("internal audio artifact is unavailable") from exc
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    try:
        digest_value, size, identity = _hash_descriptor(descriptor)
        if digest_value != track["sha256"]:
            raise AudioArtifactVerificationError("internal audio digest does not match")
        probe = _probe_wav(f"/proc/self/fd/{descriptor}", pass_fds=(descriptor,))
        if (
            probe["sampleRate"] != track["sampleRate"]
            or probe["channels"] != track["channels"]
            or abs(probe["durationSamples"] - track["durationSamples"]) > 1
        ):
            raise AudioArtifactVerificationError("internal audio probe does not match")
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor, (digest_value, size, identity)
    except Exception:
        os.close(descriptor)
        raise


def _bus(
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


def _mix_filtergraph(parameters: Mapping[str, Any]) -> str:
    channels = parameters["channels"]
    samples = parameters["durationSamples"]
    layout = "mono" if channels == 1 else "stereo"
    gains = {
        "dialogue": "0",
        "narration": "0",
        "sfx": "-6",
        "ambience": "-12",
        "music": "-18",
    }
    graph: list[str] = []
    roles: dict[str, list[str]] = {role: [] for role in AUDIO_ROLES}
    for index, track in enumerate(parameters["tracks"]):
        role = track["audioRole"]
        label = f"track-{index}"
        roles[role].append(label)
        graph.append(
            f"[{index}:a:0]atrim=end_sample={samples},asetpts=N/SR/TB,"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts={layout},"
            f"volume={gains[role]}dB[{label}]"
        )
    dialogue = _bus(graph, roles["dialogue"] + roles["narration"], "dialogue")
    sfx = _bus(graph, roles["sfx"], "sfx")
    ambience = _bus(graph, roles["ambience"], "ambience")
    music = _bus(graph, roles["music"], "music")
    bed_labels = [label for label in (sfx, ambience, music) if label is not None]
    bed = _bus(graph, bed_labels, "bed")
    if dialogue is not None and bed is not None:
        graph.append(f"[{dialogue}]asplit=2[dialogue-final][dialogue-key]")
        graph.append(
            f"[{bed}][dialogue-key]sidechaincompress=threshold=0.125:ratio=8:"
            "attack=5:release=180:makeup=1:knee=2:link=maximum:detection=rms:"
            "level_sc=1:mix=1[ducked-bed]"
        )
        graph.append(
            "[dialogue-final][ducked-bed]amix=inputs=2:weights='1 1':"
            "normalize=false:duration=longest:dropout_transition=0[premix]"
        )
        source = "premix"
    elif dialogue is not None:
        source = dialogue
    elif bed is not None:
        source = bed
    else:  # The role validator plus non-empty list makes this unreachable.
        raise AudioRequestValidationError("preliminary mix has no usable tracks")
    graph.append(
        f"[{source}]alimiter=limit=0.95:attack=5:release=50:level=false:latency=true,"
        f"atrim=end_sample={samples},asetpts=N/SR/TB,"
        f"aformat=sample_fmts=s16:sample_rates=48000:channel_layouts={layout}[out]"
    )
    return ";".join(graph)


class DeterministicPreliminaryMixAdapter:
    """Deterministic role-level mix over verified internal audio artifacts only."""

    __slots__ = ("_artifact_root", "_verified_output_claim")

    adapter_identity = PRELIMINARY_MIX_ADAPTER_ID
    provenance = "LOCAL_EVIDENCE"

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_artifact_root" and hasattr(self, "_artifact_root"):
            raise AttributeError("artifact_root is immutable")
        object.__setattr__(self, name, value)

    def __init__(self, artifact_root: Path | str) -> None:
        raw_root = Path(artifact_root)
        if raw_root.is_symlink():
            raise AudioRequestValidationError("artifact_root cannot be a symlink")
        try:
            root = raw_root.resolve(strict=True)
        except OSError as exc:
            raise AudioRequestValidationError("artifact_root is unavailable") from exc
        if not root.is_dir():
            raise AudioRequestValidationError("artifact_root is unavailable")
        self._artifact_root = root
        self._verified_output_claim: (
            tuple[str, Path, tuple[str, ...], _DescriptorDigest]
            | None
        ) = None

    def _consume_verified_output_claim(
        self, *, request_digest: str, candidate: Path
    ) -> tuple[tuple[str, ...], _DescriptorDigest]:
        claim = self._verified_output_claim
        self._verified_output_claim = None
        if (
            claim is None
            or claim[0] != request_digest
            or claim[1] != candidate
        ):
            raise AudioArtifactVerificationError(
                "preliminary mix verified-output claim is unavailable"
            )
        return claim[2], claim[3]

    def generate(self, request: Mapping[str, Any], candidate_path: Path) -> Path:
        self._verified_output_claim = None
        _, parameters = _mix_parameters(request)
        execution_parameters = _canonical_mix_parameters(parameters)
        root_descriptor: int | None = None
        parent_descriptor: int | None = None
        output_descriptor: int | None = None
        opened: list[tuple[int, _DescriptorDigest]] = []
        succeeded = False
        try:
            root_descriptor, root_identity = _open_audio_root_descriptor(
                self._artifact_root
            )
            for track in execution_parameters["tracks"]:
                opened.append(_open_internal_track(root_descriptor, track))
            candidate, relative_parts = _mix_candidate_parts(
                self._artifact_root, candidate_path
            )
            (
                candidate,
                parent_descriptor,
                output_descriptor,
                _,
            ) = _create_mix_output(
                self._artifact_root, root_descriptor, candidate
            )
            descriptors = tuple(item[0] for item in opened)
            input_arguments: list[str] = []
            for descriptor in descriptors:
                input_arguments.extend(["-i", f"/proc/self/fd/{descriptor}"])
            arguments = [
                *input_arguments,
                "-filter_complex",
                _mix_filtergraph(execution_parameters),
                "-map",
                "[out]",
                *_wav_output_arguments(
                    sample_rate=execution_parameters["sampleRate"],
                    channels=execution_parameters["channels"],
                    candidate_path=f"/proc/self/fd/{output_descriptor}",
                    overwrite_open_descriptor=True,
                ),
            ]
            _run_ffmpeg(
                arguments,
                candidate,
                pass_fds=(*descriptors, output_descriptor),
                cleanup_on_failure=False,
            )
            for descriptor, expected in opened:
                if _hash_descriptor(descriptor) != expected:
                    raise AudioArtifactVerificationError("internal audio changed during mix")
            try:
                os.fsync(output_descriptor)
            except OSError as exc:
                raise AudioArtifactVerificationError(
                    "preliminary mix output cannot be synchronized"
                ) from exc
            verified_output = _verify_wav_descriptor(
                output_descriptor,
                sample_rate=execution_parameters["sampleRate"],
                channels=execution_parameters["channels"],
                duration_samples=execution_parameters["durationSamples"],
            )
            expected_output = verified_output[:3]
            visible_root = os.stat(self._artifact_root, follow_symlinks=False)
            if (visible_root.st_dev, visible_root.st_ino) != root_identity:
                raise AudioArtifactVerificationError(
                    "artifact root namespace binding changed"
                )
            _verify_mix_output_visible(
                root_descriptor, relative_parts, expected_output
            )
            self._verified_output_claim = (
                request["payloadDigest"],
                candidate,
                relative_parts,
                expected_output,
            )
            succeeded = True
        except Exception:
            if output_descriptor is not None:
                _neutralize_audio_descriptor(output_descriptor)
            raise
        finally:
            for descriptor in (
                *(item[0] for item in opened),
                output_descriptor,
                parent_descriptor,
                root_descriptor,
            ):
                if descriptor is None:
                    continue
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if not succeeded:
            raise AudioArtifactVerificationError(
                "preliminary mix did not complete"
            )
        return candidate


def _artifact_lineage(request: Mapping[str, Any]) -> dict[str, str]:
    fields = (
        "workspaceRef",
        "productionRunRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
    )
    lineage = {field: _ref(request.get(field), field) for field in fields}
    digest_fields = (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
    )
    lineage.update(
        {field: _sha256(request.get(field), field) for field in digest_fields}
    )
    return lineage


def _validated_execution_request(
    request: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(request, Mapping):
        raise AudioRequestValidationError("audio request must be an object")
    schema_version = request.get("schemaVersion")
    if schema_version == TTS_EXECUTION_REQUEST_SCHEMA_VERSION:
        return _validated_speech_request(request)
    if schema_version == PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION:
        normalized, parameters = _effect_parameters(request)
        return normalized, parameters, deepcopy(parameters)
    if schema_version == PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION:
        normalized, parameters = _mix_parameters(request)
        return normalized, parameters, deepcopy(parameters)
    raise AudioRequestValidationError("audio request schema is unsupported")


def _sealed_audio_artifact_result(
    *,
    normalized: Mapping[str, Any],
    requested_parameters: Mapping[str, Any],
    effective_parameters: Mapping[str, Any],
    lineage: Mapping[str, str],
    safe_storage_key: str,
    artifact_sha: str,
    byte_size: int,
    probe: Mapping[str, Any],
    sample_rate: int,
    channels: int,
    adapter_identity: str,
    adapter_provenance: str,
    role: str,
) -> dict[str, Any]:
    """Seal an already verified artifact without touching its namespace."""

    execution_request_digest = normalized["payloadDigest"]
    generation_request_digest = normalized.get(
        "generationRequestDigest", execution_request_digest
    )
    _sha256(generation_request_digest, "generationRequestDigest")
    parameters_digest = _digest(requested_parameters)
    effective_parameters_digest = _digest(effective_parameters)
    synthesis_spec_digest = _digest(
        {
            "adapterIdentity": adapter_identity,
            "parameters": effective_parameters,
        }
    )
    evidence_semantic = {
        "generationRequestDigest": generation_request_digest,
        "executionRequestDigest": execution_request_digest,
        "storageKey": safe_storage_key,
        "sha256": artifact_sha,
    }
    artifact_evidence_ref = "audio-artifact-evidence-" + _digest(evidence_semantic)[:32]
    artifact_ref = "audio-artifact-" + artifact_sha[:32]
    artifact_evidence = _sealed(
        {
            "schemaVersion": AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            **lineage,
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": execution_request_digest,
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactRef": artifact_ref,
            "storageKey": safe_storage_key,
            "byteSize": byte_size,
            "sha256": artifact_sha,
            "sampleRate": sample_rate,
            "channels": channels,
            "probe": deepcopy(dict(probe)),
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": synthesis_spec_digest,
            "adapterIdentity": adapter_identity,
            "audioRole": role,
            "provenance": adapter_provenance,
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )
    result_semantic = {
        "generationRequestDigest": generation_request_digest,
        "executionRequestDigest": execution_request_digest,
        "artifactEvidenceDigest": artifact_evidence["payloadDigest"],
    }
    generation_result_ref = "audio-generation-result-" + _digest(result_semantic)[:32]
    generation_result = _sealed(
        {
            "schemaVersion": AUDIO_GENERATION_RESULT_SCHEMA_VERSION,
            **lineage,
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": execution_request_digest,
            "generationResultRef": generation_result_ref,
            "adapterIdentity": adapter_identity,
            "provenance": adapter_provenance,
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactEvidenceDigest": artifact_evidence["payloadDigest"],
            "artifactRef": artifact_ref,
            "storageKey": safe_storage_key,
            "byteSize": byte_size,
            "sha256": artifact_sha,
            "sampleRate": sample_rate,
            "channels": channels,
            "probe": deepcopy(dict(probe)),
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": synthesis_spec_digest,
            "audioRole": role,
            "state": "SUCCEEDED",
            "publicationAllowed": False,
        }
    )
    return _sealed(
        {
            "schemaVersion": AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION,
            **lineage,
            "generationRequestDigest": generation_request_digest,
            "executionRequestDigest": execution_request_digest,
            "generationResultRef": generation_result_ref,
            "generationResultDigest": generation_result["payloadDigest"],
            "adapterIdentity": adapter_identity,
            "provenance": adapter_provenance,
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactEvidenceDigest": artifact_evidence["payloadDigest"],
            "artifactRef": artifact_ref,
            "storageKey": safe_storage_key,
            "byteSize": byte_size,
            "sha256": artifact_sha,
            "sampleRate": sample_rate,
            "channels": channels,
            "probe": deepcopy(dict(probe)),
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": effective_parameters_digest,
            "synthesisSpecDigest": synthesis_spec_digest,
            "audioRole": role,
            "generationResult": generation_result,
            "artifactEvidence": artifact_evidence,
            "publicationAllowed": False,
        }
    )


def audio_artifact_evidence(
    request: Mapping[str, Any],
    *,
    artifact_root: Path | str,
    storage_key: str,
    adapter: AudioGenerationAdapter,
) -> dict[str, Any]:
    """Execute one adapter and seal its verified result/evidence bundle.

    The output candidate is derived only from ``artifact_root`` and ``storage_key``.
    Existing files cannot be retroactively signed.  The returned mapping is V4
    execution evidence only; no authoritative V5 asset fact is created here.
    """

    normalized, requested_parameters, effective_parameters = (
        _validated_execution_request(request)
    )
    lineage = _artifact_lineage(normalized)
    adapter_identity = _ref(
        getattr(adapter, "adapter_identity", None), "adapter.adapter_identity"
    )
    adapter_provenance = _ref(
        getattr(adapter, "provenance", None), "adapter.provenance"
    )
    if not callable(getattr(adapter, "generate", None)):
        raise AudioRequestValidationError("audio adapter generate is unavailable")
    if (
        normalized.get("adapterCapability") != adapter_identity
        or normalized.get("requestedProvenance") != adapter_provenance
        or adapter_provenance != "LOCAL_EVIDENCE"
    ):
        raise AudioRequestValidationError("audio adapter binding is invalid")
    role = requested_parameters.get("audioRole")
    if role is None and requested_parameters.get("mixKind") == "preliminary":
        role = "preliminary_mix"
    if role not in AUDIO_ROLES | {"preliminary_mix"}:
        raise AudioRequestValidationError("audioRole is invalid")
    if role == "preliminary_mix" and type(adapter) is not DeterministicPreliminaryMixAdapter:
        raise AudioRequestValidationError(
            "preliminary mix requires the exact built-in adapter"
        )
    if role == "preliminary_mix" and {
        "generate",
        "_consume_verified_output_claim",
    }.intersection(getattr(adapter, "__dict__", {})):
        raise AudioRequestValidationError(
            "preliminary mix adapter methods cannot be overridden"
        )
    sample_rate = effective_parameters.get("sampleRate")
    channels = effective_parameters.get("channels")
    if sample_rate != _SAMPLE_RATE:
        raise AudioRequestValidationError("sampleRate must be 48000")
    _integer(channels, "channels", minimum=1, maximum=2)
    expected_samples = effective_parameters.get("durationSamples")
    if expected_samples is not None:
        _integer(
            expected_samples,
            "durationSamples",
            minimum=1,
            maximum=_MAX_DURATION_SAMPLES,
        )
    safe_storage_key = _storage_key(storage_key)
    root = _pinned_artifact_root(artifact_root)
    if role == "preliminary_mix" and adapter._artifact_root != root:
        raise AudioRequestValidationError(
            "preliminary mix adapter artifact_root binding is stale"
        )
    storage_parts = PurePosixPath(safe_storage_key).parts
    candidate = root.joinpath(*storage_parts)
    if role == "preliminary_mix":
        root_descriptor: int | None = None
        parent_descriptor: int | None = None
        artifact_descriptor: int | None = None
        artifact_claim_verified = False
        try:
            root_descriptor, root_identity = _open_audio_root_descriptor(root)
            execution_adapter = DeterministicPreliminaryMixAdapter(root)
            produced = DeterministicPreliminaryMixAdapter.generate(
                execution_adapter, normalized, candidate
            )
            if not isinstance(produced, Path) or produced != candidate:
                raise AudioArtifactVerificationError(
                    "audio adapter returned an unexpected candidate"
                )
            claim_parts, claim = (
                DeterministicPreliminaryMixAdapter._consume_verified_output_claim(
                    execution_adapter,
                    request_digest=normalized["payloadDigest"],
                    candidate=candidate,
                )
            )
            if claim_parts != storage_parts:
                raise AudioArtifactVerificationError(
                    "preliminary mix storage claim is stale"
                )
            parent_descriptor = _open_audio_parent_descriptor(
                root_descriptor, storage_parts[:-1], create=False
            )
            artifact_descriptor = os.open(
                storage_parts[-1],
                os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            verified = _verify_wav_descriptor(
                artifact_descriptor,
                sample_rate=sample_rate,
                channels=channels,
                duration_samples=expected_samples,
            )
            artifact_sha, byte_size, identity, probe = verified
            if (artifact_sha, byte_size, identity) != claim:
                raise AudioArtifactVerificationError(
                    "preliminary mix output claim changed before evidence"
                )
            artifact_claim_verified = True
            visible_root = os.stat(root, follow_symlinks=False)
            if (visible_root.st_dev, visible_root.st_ino) != root_identity:
                raise AudioArtifactVerificationError(
                    "artifact root namespace binding changed"
                )
            _verify_mix_output_visible(
                root_descriptor, storage_parts, claim
            )
            result_bundle = _sealed_audio_artifact_result(
                normalized=normalized,
                requested_parameters=requested_parameters,
                effective_parameters=effective_parameters,
                lineage=lineage,
                safe_storage_key=safe_storage_key,
                artifact_sha=artifact_sha,
                byte_size=byte_size,
                probe=probe,
                sample_rate=sample_rate,
                channels=channels,
                adapter_identity=adapter_identity,
                adapter_provenance=adapter_provenance,
                role=role,
            )
            _verify_mix_output_visible(
                root_descriptor, storage_parts, claim
            )
            visible_root = os.stat(root, follow_symlinks=False)
            if (visible_root.st_dev, visible_root.st_ino) != root_identity:
                raise AudioArtifactVerificationError(
                    "artifact root namespace binding changed before evidence mint"
                )
            return result_bundle
        except AudioAdapterError:
            if artifact_claim_verified and artifact_descriptor is not None:
                _neutralize_audio_descriptor(artifact_descriptor)
            raise
        except OSError as exc:
            if artifact_claim_verified and artifact_descriptor is not None:
                _neutralize_audio_descriptor(artifact_descriptor)
            raise AudioArtifactVerificationError(
                "preliminary mix evidence cannot pin its output"
            ) from exc
        except Exception:
            if artifact_claim_verified and artifact_descriptor is not None:
                _neutralize_audio_descriptor(artifact_descriptor)
            raise
        finally:
            for descriptor in (
                artifact_descriptor,
                parent_descriptor,
                root_descriptor,
            ):
                if descriptor is not None:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
    else:
        candidate = _pinned_artifact_candidate(
            root, safe_storage_key, must_not_exist=True
        )
        try:
            produced = adapter.generate(normalized, candidate)
            if not isinstance(produced, Path) or produced != candidate:
                raise AudioArtifactVerificationError(
                    "audio adapter returned an unexpected candidate"
                )
            _pinned_artifact_candidate(root, safe_storage_key, must_not_exist=False)
            artifact_sha, byte_size, probe = _verify_wav(
                candidate,
                sample_rate=sample_rate,
                channels=channels,
                duration_samples=expected_samples,
            )
        except Exception:
            _remove_partial(candidate)
            raise
    return _sealed_audio_artifact_result(
        normalized=normalized,
        requested_parameters=requested_parameters,
        effective_parameters=effective_parameters,
        lineage=lineage,
        safe_storage_key=safe_storage_key,
        artifact_sha=artifact_sha,
        byte_size=byte_size,
        probe=probe,
        sample_rate=sample_rate,
        channels=channels,
        adapter_identity=adapter_identity,
        adapter_provenance=adapter_provenance,
        role=role,
    )


_PIPER_TTS_EXECUTION_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionEvidenceRef",
        "generationRequestDigest",
        "executionRequestDigest",
        "adapterIdentity",
        "audioRole",
        "generationResultRef",
        "generationResultDigest",
        "artifactResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
        "artifactResult",
        "technicalAnalysisEvidence",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_PIPER_TTS_EVIDENCE_MINT_TOKEN = object()


def _piper_tts_execution_evidence_ref(value: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(value))
    semantic.pop("executionEvidenceRef", None)
    semantic.pop("payloadDigest", None)
    return "piper-tts-execution-evidence-" + _digest(semantic)[:32]


@dataclass(frozen=True, slots=True, init=False)
class PiperTtsExecutionEvidence:
    """Mint-only proof of exact built-in Piper execution plus PR-5 analysis.

    There is intentionally no mapping constructor.  The only supported mint is
    :func:`execute_piper_tts_evidence`, which owns the exact adapter instance and
    binds the resulting artifact to an exact technical-analysis capability.
    """

    _payload_json: str

    @classmethod
    def _from_executor(
        cls,
        artifact_result: Mapping[str, Any],
        technical_analysis: AudioTechnicalAnalysisEvidence,
        *,
        _mint_token: object,
    ) -> "PiperTtsExecutionEvidence":
        if _mint_token is not _PIPER_TTS_EVIDENCE_MINT_TOKEN:
            raise AudioArtifactVerificationError(
                "Piper execution evidence mint authority is unavailable"
            )
        if type(technical_analysis) is not AudioTechnicalAnalysisEvidence:
            raise AudioArtifactVerificationError(
                "exact audio technical-analysis evidence is required"
            )
        bundle = _verify_sealed(artifact_result, "Piper artifact result")
        analysis = technical_analysis.as_dict()
        evidence = bundle.get("artifactEvidence")
        result = bundle.get("generationResult")
        if not isinstance(evidence, Mapping) or not isinstance(result, Mapping):
            raise AudioArtifactVerificationError(
                "Piper artifact result is incomplete"
            )
        evidence = _verify_sealed(evidence, "Piper artifact evidence")
        result = _verify_sealed(result, "Piper generation result")
        if (
            bundle.get("schemaVersion") != AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION
            or bundle.get("adapterIdentity") != PIPER_TTS_ADAPTER_ID
            or bundle.get("audioRole") not in SPEECH_AUDIO_ROLES
            or bundle.get("provenance") != "LOCAL_EVIDENCE"
            or bundle.get("publicationAllowed") is not False
            or bundle.get("generationResult") != result
            or bundle.get("artifactEvidence") != evidence
            or bundle.get("generationResultRef")
            != result.get("generationResultRef")
            or bundle.get("generationResultDigest") != result.get("payloadDigest")
            or bundle.get("artifactEvidenceRef")
            != evidence.get("artifactEvidenceRef")
            or bundle.get("artifactEvidenceDigest")
            != evidence.get("payloadDigest")
            or analysis.get("sourceArtifactEvidenceRef")
            != evidence.get("artifactEvidenceRef")
            or analysis.get("sourceArtifactEvidenceDigest")
            != evidence.get("payloadDigest")
            or analysis.get("artifactRef") != evidence.get("artifactRef")
            or analysis.get("storageKey") != evidence.get("storageKey")
            or analysis.get("byteSize") != evidence.get("byteSize")
            or analysis.get("fileDigest") != evidence.get("sha256")
            or analysis.get("validationState") != "PASSED"
            or analysis.get("failureReasons") != []
            or analysis.get("clippingDetected") is not False
            or analysis.get("state") != "TECHNICAL_ANALYSIS_COMPLETE"
            or analysis.get("publicationAllowed") is not False
        ):
            raise AudioArtifactVerificationError(
                "Piper artifact and technical analysis are not exactly bound"
            )
        for field, value in (
            ("generationRequestDigest", bundle.get("generationRequestDigest")),
            ("executionRequestDigest", bundle.get("executionRequestDigest")),
            ("generationResultDigest", result.get("payloadDigest")),
            ("artifactResultDigest", bundle.get("payloadDigest")),
            ("artifactEvidenceDigest", evidence.get("payloadDigest")),
            ("analysisEvidenceDigest", analysis.get("payloadDigest")),
            ("pcmContentDigest", analysis.get("pcmContentDigest")),
        ):
            _sha256(value, field)
        for field, value in (
            ("generationResultRef", result.get("generationResultRef")),
            ("artifactEvidenceRef", evidence.get("artifactEvidenceRef")),
            ("analysisEvidenceRef", analysis.get("analysisEvidenceRef")),
        ):
            _ref(value, field)
        semantic: dict[str, Any] = {
            "schemaVersion": PIPER_TTS_EXECUTION_EVIDENCE_SCHEMA_VERSION,
            "generationRequestDigest": bundle["generationRequestDigest"],
            "executionRequestDigest": bundle["executionRequestDigest"],
            "adapterIdentity": PIPER_TTS_ADAPTER_ID,
            "audioRole": bundle["audioRole"],
            "generationResultRef": result["generationResultRef"],
            "generationResultDigest": result["payloadDigest"],
            "artifactResultDigest": bundle["payloadDigest"],
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["payloadDigest"],
            "analysisEvidenceRef": analysis["analysisEvidenceRef"],
            "analysisEvidenceDigest": analysis["payloadDigest"],
            "artifactResult": bundle,
            "technicalAnalysisEvidence": analysis,
            "state": PIPER_TTS_EXECUTION_STATE,
            "publicationAllowed": False,
        }
        semantic["executionEvidenceRef"] = _piper_tts_execution_evidence_ref(
            semantic
        )
        sealed = _sealed(semantic)
        if set(sealed) != _PIPER_TTS_EXECUTION_EVIDENCE_FIELDS:
            raise AudioArtifactVerificationError(
                "Piper execution evidence fields are invalid"
            )
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            _canonical(sealed).decode("utf-8"),
        )
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def execute_piper_tts_evidence(
    request: Mapping[str, Any],
    *,
    artifact_root: Path | str,
    storage_key: str,
) -> PiperTtsExecutionEvidence:
    """Execute only the built-in Piper boundary and mint production evidence.

    The current A-tier adapter always raises
    ``NotImplementedError("PIPER_RUNTIME_ABSENT")`` before creating an output.
    No caller-selected adapter can enter this authority-bearing path.
    """

    normalized, _, _ = _validated_speech_request(request)
    adapter = PiperTtsAdapter()
    if type(adapter) is not PiperTtsAdapter:
        raise AudioRuntimeUnavailableError("exact Piper adapter is unavailable")
    artifact_result = audio_artifact_evidence(
        normalized,
        artifact_root=artifact_root,
        storage_key=storage_key,
        adapter=adapter,
    )
    technical_analysis = analyze_audio_artifact(
        artifact_result["artifactEvidence"], artifact_root=artifact_root
    )
    return PiperTtsExecutionEvidence._from_executor(
        artifact_result,
        technical_analysis,
        _mint_token=_PIPER_TTS_EVIDENCE_MINT_TOKEN,
    )


__all__ = [
    "AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "AUDIO_GENERATION_RESULT_SCHEMA_VERSION",
    "AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION",
    "PIPER_TTS_EXECUTION_EVIDENCE_SCHEMA_VERSION",
    "AUDIO_STORAGE_PREFIX",
    "TTS_EXECUTION_REQUEST_SCHEMA_VERSION",
    "PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION",
    "PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION",
    "PIPER_TTS_ADAPTER_ID",
    "PIPER_TTS_EXECUTION_STATE",
    "PROGRAMMATIC_AUDIO_ADAPTER_ID",
    "PRELIMINARY_MIX_ADAPTER_ID",
    "SPEECH_AUDIO_ROLES",
    "PROGRAMMATIC_AUDIO_ROLES",
    "AUDIO_ROLES",
    "PROGRAMMATIC_EFFECTS",
    "AudioAdapterError",
    "AudioRequestValidationError",
    "AudioRuntimeUnavailableError",
    "AudioArtifactVerificationError",
    "AudioGenerationAdapter",
    "PiperTtsAdapter",
    "PiperTtsExecutionEvidence",
    "DeterministicProgrammaticAudioAdapter",
    "DeterministicPreliminaryMixAdapter",
    "emotion_parameters",
    "audio_artifact_evidence",
    "execute_piper_tts_evidence",
]
