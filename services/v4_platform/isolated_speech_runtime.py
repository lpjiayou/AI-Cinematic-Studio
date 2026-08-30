"""Closed subprocess protocols for the two ADR-0015 speech runtimes.

This module owns execution evidence only.  It does not install a runtime, resolve
models, create a VoiceProfile/AssetVersion, persist domain facts, or admit media.
Production adapters accept only digest-pinned manifests and fixed executable
locations below a server-owned runtime root.  The test harness is deliberately a
different type and can never mint :class:`IsolatedSpeechRuntimeEvidence`.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
from typing import Any, Callable, Mapping

from .audio_validation import (
    AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION,
    AudioTechnicalAnalysisEvidence,
    analyze_audio_artifact,
)


KOKORO_ENGINE_ID = "hexgrad/kokoro:LOCAL_FIXED_VOICE"
KOKORO_ENGINE_COMMIT = "dfb907a02bba8152ca444717ca5d78747ccb4bec"
KOKORO_MODEL_ID = KOKORO_ENGINE_ID
KOKORO_MODEL_BUNDLE_SHA256 = (
    "849ed6061f60a9b82ba13ff9538380fca4014fe19f1762475ab0997a2590cc92"
)

COSYVOICE_ENGINE_ID = "QwenAudio/CosyVoice:CosyVoice3.ZERO_SHOT_LOCAL"
COSYVOICE_ENGINE_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
MATCHA_TTS_COMMIT = "dd9105b34bf2be2230f4aa1e4769fb586a3c824e"
COSYVOICE_MODEL_ID = (
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512@"
    "29e01c4e8d000f4bcd70751be16fa94bf3d85a18"
)
COSYVOICE_MODEL_BUNDLE_SHA256 = (
    "f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d"
)

KOKORO_RUNTIME_KIND = "KOKORO_FIXED_VOICE"
COSYVOICE_RUNTIME_KIND = "COSYVOICE3_ZERO_SHOT"
KOKORO_MANIFEST_SCHEMA_VERSION = "m12.kokoro-isolated-runtime-manifest.v1"
COSYVOICE_MANIFEST_SCHEMA_VERSION = "m12.cosyvoice-isolated-runtime-manifest.v1"
TEST_MANIFEST_SCHEMA_VERSION = "m12.isolated-runtime-test-fixture-manifest.v1"
PROTOCOL_VERSION = "m12.isolated-speech-stdio-fd.v1"
TRANSPORT_SCHEMA_VERSION = "m12.isolated-runtime-transport.v1"

KOKORO_REQUEST_SCHEMA_VERSION = "m12.kokoro-runtime-request.v1"
KOKORO_RESPONSE_SCHEMA_VERSION = "m12.kokoro-runtime-response.v1"
COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION = "m12.cosyvoice-profile-request.v1"
COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION = "m12.cosyvoice-profile-response.v1"
COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION = "m12.cosyvoice-dialogue-request.v1"
COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION = "m12.cosyvoice-dialogue-response.v1"
PRODUCTION_EVIDENCE_SCHEMA_VERSION = (
    "m12.isolated-speech-runtime-evidence.v1"
)
TEST_EVIDENCE_SCHEMA_VERSION = "m12.isolated-runtime-test-evidence.v1"
TEST_ANALYSIS_BINDING_SCHEMA_VERSION = (
    "m12.test-audio-analysis-binding.v1"
)

KOKORO_SYNTHESIZE_FIXED_VOICE = "KOKORO_SYNTHESIZE_FIXED_VOICE"
COSYVOICE_BUILD_VOICE_PROFILE = "COSYVOICE_BUILD_VOICE_PROFILE"
COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE = (
    "COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE"
)
ISOLATED_SPEECH_OPERATIONS = frozenset(
    {
        KOKORO_SYNTHESIZE_FIXED_VOICE,
        COSYVOICE_BUILD_VOICE_PROFILE,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    }
)

M12_RUNTIME_NOT_INSTALLED = "M12_RUNTIME_NOT_INSTALLED"
TEST_FIXTURE_MARKERS = frozenset(
    {
        "TEST_FIXTURE_ONLY",
        "NOT_KOKORO",
        "NOT_COSYVOICE",
        "NOT_PRODUCTION_RUNTIME",
        "NOT_AUTHORITY",
        "NOT_ADMITTED",
    }
)
TEST_DEPENDENCY_LOCK_DIGEST = "a" * 64

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_MAX_TEXT = 100_000
_MAX_STDOUT = 1_000_000
_DEFAULT_TIMEOUT_SECONDS = 120
_MINIMAL_ENVIRONMENT = {"LC_ALL": "C", "LANG": "C", "TZ": "UTC"}
_STREAM_CHUNK_BYTES = 1024 * 1024

_MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "runtimeManifestRef",
        "runtimeKind",
        "runtimeExecutableDigest",
        "engineId",
        "engineCommit",
        "matchaTtsCommit",
        "engineArchiveDigest",
        "modelId",
        "modelBundleDigest",
        "pythonVersion",
        "pytorchVersion",
        "torchaudioVersion",
        "cudaVariant",
        "dependencyLockDigest",
        "wheelhouseDigest",
        "protocolVersion",
        "networkPolicy",
        "createdAt",
        "payloadDigest",
    }
)
_TEST_MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "runtimeManifestRef",
        "runtimeKind",
        "runtimeExecutableDigest",
        "dependencyLockDigest",
        "fixtureMarkers",
        "protocolVersion",
        "publicationAllowed",
        "payloadDigest",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "requestRef",
        "operationKind",
        "inputLineageRefsAndDigests",
        "text",
        "language",
        "voiceId",
        "voiceProfileVersionRef",
        "effectiveSpeechParameters",
        "sampleRate",
        "channelCount",
        "runtimeManifestRef",
        "runtimeManifestDigest",
        "outputArtifactBindingRef",
        "payloadDigest",
    }
)
_RESPONSE_FIELDS = frozenset(
    {
        "schemaVersion",
        "requestRef",
        "requestDigest",
        "operationKind",
        "engineCommit",
        "matchaTtsCommit",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
        "outputByteSize",
        "outputFileDigest",
        "outputPcmContentDigest",
        "mediaProbe",
        "deviceFacts",
        "networkUsed",
        "executionStartedAt",
        "executionCompletedAt",
        "payloadDigest",
    }
)
_PROFILE_RESPONSE_FIELDS = _RESPONSE_FIELDS | frozenset(
    {
        "profilePackageByteSize",
        "profilePackageFileDigest",
        "profilePackageContentDigest",
        "profilePackageSchemaVersion",
    }
)
_MEDIA_PROBE_FIELDS = frozenset(
    {
        "codec",
        "sampleRate",
        "channelCount",
        "sampleCount",
        "durationRational",
    }
)
_RATIONAL_FIELDS = frozenset({"numerator", "denominator"})
_DEVICE_FACTS_FIELDS = frozenset(
    {"deviceType", "deviceCount", "gpuUsed", "deviceFactsDigest"}
)
_PRODUCTION_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "runtimeKind",
        "operationKind",
        "runtimeManifestRef",
        "runtimeManifestDigest",
        "engineId",
        "engineCommit",
        "matchaTtsCommit",
        "modelId",
        "modelBundleDigest",
        "dependencyLockDigest",
        "requestRef",
        "requestDigest",
        "responseDigest",
        "inputLineageRefsAndDigests",
        "outputArtifactBindingRef",
        "outputByteSize",
        "outputFileDigest",
        "outputPcmContentDigest",
        "mediaProbe",
        "deviceFacts",
        "profilePackageByteSize",
        "profilePackageFileDigest",
        "profilePackageContentDigest",
        "profilePackageSchemaVersion",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
        "networkUsed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TEST_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "fixtureMarkers",
        "runtimeManifestRef",
        "runtimeManifestDigest",
        "requestBinding",
        "response",
        "independentAudioAnalysis",
        "outputByteSize",
        "outputFileDigest",
        "state",
        "authorityState",
        "admissionState",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TEST_ANALYSIS_FACT_FIELDS = (
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
)
_TEST_ANALYSIS_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "analysisSchemaVersion",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
        *_TEST_ANALYSIS_FACT_FIELDS,
        "payloadDigest",
    }
)
_REQUEST_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "requestRef",
        "requestDigest",
        "operationKind",
        "inputLineageRefsAndDigests",
        "runtimeManifestRef",
        "runtimeManifestDigest",
        "outputArtifactBindingRef",
        "textDigest",
    }
)

_DIALOGUE_PRODUCTION_LINEAGE_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
    }
)
_PROFILE_PRODUCTION_LINEAGE_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
    }
)
_FIXED_LINEAGE_FIELDS = _DIALOGUE_PRODUCTION_LINEAGE_FIELDS | frozenset(
    {
        "voiceLockRef",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceLockConfirmationRef",
        "voiceLockConfirmationDigest",
    }
)
_PROFILE_LINEAGE_FIELDS = _PROFILE_PRODUCTION_LINEAGE_FIELDS | frozenset(
    {
        "sourceRecordingBindingRef",
        "sourceRecordingBindingDigest",
        "canonicalAssetVersionRef",
        "canonicalAssetVersionDigest",
        "audioFileDigest",
        "audioPcmContentDigest",
        "transcriptVersionRef",
        "transcriptVersionDigest",
        "transcriptTextDigest",
        "consentGrantVersionRef",
        "consentGrantVersionDigest",
        "voiceLockRef",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceLockConfirmationRef",
        "voiceLockConfirmationDigest",
        "rightsBindingRef",
        "rightsBindingDigest",
        "voiceIdentityRef",
        "voiceIdentityVersionRef",
        "voiceIdentityDigest",
    }
)
_DIALOGUE_LINEAGE_FIELDS = _DIALOGUE_PRODUCTION_LINEAGE_FIELDS | frozenset(
    {
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "voiceProfileVersionDigest",
        "voiceProfilePackageFileDigest",
        "voiceProfilePackageContentDigest",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "sourceRecordingBindingRef",
        "sourceRecordingBindingDigest",
        "consentGrantVersionRef",
        "consentGrantVersionDigest",
        "rightsBindingRef",
        "rightsBindingDigest",
        "voiceAssetVersionRef",
        "voiceAssetVersionDigest",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
        "absolutePath",
        "storageKey",
        "modelPath",
        "pythonPath",
        "shellCommand",
        "environmentOverride",
        "downloadUrl",
        "networkEndpoint",
        "engineOverride",
        "modelOverride",
        "rawAudioBytes",
        "rawAssetVersion",
        "rawConsent",
        "rawVoiceProfile",
        "sourcePath",
        "outputPath",
        "inputFd",
        "outputFd",
    }
)


class IsolatedSpeechRuntimeError(RuntimeError):
    """Base error for closed speech execution."""


class IsolatedSpeechContractError(IsolatedSpeechRuntimeError):
    """A manifest, request, response, or transport contract is invalid."""


class IsolatedSpeechRuntimeNotInstalledError(IsolatedSpeechRuntimeError):
    code = M12_RUNTIME_NOT_INSTALLED

    def __init__(self) -> None:
        super().__init__(M12_RUNTIME_NOT_INSTALLED)


class IsolatedSpeechExecutionError(IsolatedSpeechRuntimeError):
    """The pinned subprocess failed, timed out, or returned untrusted evidence."""


class IsolatedSpeechArtifactError(IsolatedSpeechRuntimeError):
    """The output descriptor or bytes changed during independent verification."""


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
        raise IsolatedSpeechContractError(
            "isolated speech payload is not canonical JSON"
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise IsolatedSpeechContractError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise IsolatedSpeechContractError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _exact(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise IsolatedSpeechContractError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _text(value: Any, field: str, *, maximum: int = 2_000) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise IsolatedSpeechContractError(f"{field} is invalid")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _text(value, field)


def _ref(value: Any, field: str) -> str:
    return _text(value, field, maximum=512)


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise IsolatedSpeechContractError(f"{field} is invalid")
    return value


def _commit(value: Any, field: str) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise IsolatedSpeechContractError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str, *, maximum: int = 2**63 - 1) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > maximum
    ):
        raise IsolatedSpeechContractError(f"{field} is invalid")
    return value


def _utc(value: Any, field: str) -> datetime:
    text = _text(value, field)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IsolatedSpeechContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise IsolatedSpeechContractError(f"{field} must be UTC")
    return parsed


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in _FORBIDDEN_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _runtime_spec(runtime_kind: str) -> dict[str, Any]:
    if runtime_kind == KOKORO_RUNTIME_KIND:
        return {
            "schemaVersion": KOKORO_MANIFEST_SCHEMA_VERSION,
            "engineId": KOKORO_ENGINE_ID,
            "engineCommit": KOKORO_ENGINE_COMMIT,
            "matchaTtsCommit": None,
            "modelId": KOKORO_MODEL_ID,
            "modelBundleDigest": KOKORO_MODEL_BUNDLE_SHA256,
            "relativeExecutable": "bin/kokoro-runtime",
        }
    if runtime_kind == COSYVOICE_RUNTIME_KIND:
        return {
            "schemaVersion": COSYVOICE_MANIFEST_SCHEMA_VERSION,
            "engineId": COSYVOICE_ENGINE_ID,
            "engineCommit": COSYVOICE_ENGINE_COMMIT,
            "matchaTtsCommit": MATCHA_TTS_COMMIT,
            "modelId": COSYVOICE_MODEL_ID,
            "modelBundleDigest": COSYVOICE_MODEL_BUNDLE_SHA256,
            "relativeExecutable": "bin/cosyvoice-runtime",
        }
    raise IsolatedSpeechContractError("runtimeKind is unsupported")


def validate_runtime_manifest(value: Any, *, runtime_kind: str) -> dict[str, Any]:
    """Validate a production manifest without accepting an executable path."""

    result = _verify_sealed(value, _MANIFEST_FIELDS, "isolated runtime manifest")
    spec = _runtime_spec(runtime_kind)
    if (
        result["schemaVersion"] != spec["schemaVersion"]
        or result["runtimeKind"] != runtime_kind
        or result["engineId"] != spec["engineId"]
        or result["engineCommit"] != spec["engineCommit"]
        or result["matchaTtsCommit"] != spec["matchaTtsCommit"]
        or result["modelId"] != spec["modelId"]
        or result["modelBundleDigest"] != spec["modelBundleDigest"]
        or result["protocolVersion"] != PROTOCOL_VERSION
        or result["networkPolicy"] != "OFFLINE"
    ):
        raise IsolatedSpeechContractError("runtime manifest pins are invalid")
    for field in ("runtimeManifestRef", "pythonVersion", "pytorchVersion", "torchaudioVersion", "cudaVariant"):
        _text(result[field], field)
    _commit(result["engineCommit"], "engineCommit")
    if runtime_kind == COSYVOICE_RUNTIME_KIND:
        _commit(result["matchaTtsCommit"], "matchaTtsCommit")
    elif result["matchaTtsCommit"] is not None:
        raise IsolatedSpeechContractError(
            "Kokoro runtime cannot claim a Matcha-TTS commit"
        )
    for field in (
        "runtimeExecutableDigest",
        "engineArchiveDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "wheelhouseDigest",
    ):
        _sha256(result[field], field)
    _utc(result["createdAt"], "createdAt")
    return result


def build_test_runtime_manifest(
    *, runtime_kind: str, executable_digest: str, fixture_ref: str
) -> dict[str, Any]:
    """Create explicit non-authority metadata for the repository fake runtime."""

    _runtime_spec(runtime_kind)
    return _seal(
        {
            "schemaVersion": TEST_MANIFEST_SCHEMA_VERSION,
            "runtimeManifestRef": _ref(fixture_ref, "fixtureRef"),
            "runtimeKind": runtime_kind,
            "runtimeExecutableDigest": _sha256(
                executable_digest, "runtimeExecutableDigest"
            ),
            "dependencyLockDigest": TEST_DEPENDENCY_LOCK_DIGEST,
            "fixtureMarkers": sorted(TEST_FIXTURE_MARKERS),
            "protocolVersion": PROTOCOL_VERSION,
            "publicationAllowed": False,
        }
    )


def validate_test_runtime_manifest(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TEST_MANIFEST_FIELDS, "test runtime manifest")
    _runtime_spec(result["runtimeKind"])
    if (
        result["schemaVersion"] != TEST_MANIFEST_SCHEMA_VERSION
        or result["fixtureMarkers"] != sorted(TEST_FIXTURE_MARKERS)
        or result["protocolVersion"] != PROTOCOL_VERSION
        or result["publicationAllowed"] is not False
    ):
        raise IsolatedSpeechContractError("test runtime manifest semantics are invalid")
    _ref(result["runtimeManifestRef"], "runtimeManifestRef")
    _sha256(result["runtimeExecutableDigest"], "runtimeExecutableDigest")
    if result["dependencyLockDigest"] != TEST_DEPENDENCY_LOCK_DIGEST:
        raise IsolatedSpeechContractError(
            "test dependency lock marker is invalid"
        )
    return result


def _lineage(value: Any, operation: str) -> dict[str, Any]:
    fields = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: _FIXED_LINEAGE_FIELDS,
        COSYVOICE_BUILD_VOICE_PROFILE: _PROFILE_LINEAGE_FIELDS,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: _DIALOGUE_LINEAGE_FIELDS,
    }[operation]
    result = _exact(value, fields, "inputLineageRefsAndDigests")
    for field, item in result.items():
        if field.endswith("Digest"):
            _sha256(item, field)
        else:
            _ref(item, field)
    return result


def _speech_parameters(value: Any, operation: str) -> dict[str, Any]:
    if operation == COSYVOICE_BUILD_VOICE_PROFILE:
        if value != {}:
            raise IsolatedSpeechContractError(
                "voice profile request speech parameters must be empty"
            )
        return {}
    fields = frozenset({"rateScale", "pitchSemitones", "emotionTag"})
    result = _exact(value, fields, "effectiveSpeechParameters")
    rate = result["rateScale"]
    pitch = result["pitchSemitones"]
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
        or isinstance(pitch, bool)
        or not isinstance(pitch, (int, float))
        or not math.isfinite(pitch)
    ):
        raise IsolatedSpeechContractError("effective speech parameters are invalid")
    _text(result["emotionTag"], "effectiveSpeechParameters.emotionTag")
    return result


def validate_runtime_request(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _REQUEST_FIELDS, "isolated runtime request")
    operation = result["operationKind"]
    schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_REQUEST_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION,
    }.get(operation)
    if schema is None or result["schemaVersion"] != schema:
        raise IsolatedSpeechContractError("runtime request operation is unsupported")
    if _contains_forbidden_key(result):
        raise IsolatedSpeechContractError("runtime request contains a forbidden override")
    _ref(result["requestRef"], "requestRef")
    _lineage(result["inputLineageRefsAndDigests"], operation)
    text_value = _text(result["text"], "text", maximum=_MAX_TEXT)
    _text(result["language"], "language")
    _speech_parameters(result["effectiveSpeechParameters"], operation)
    sample_rate = _positive_int(result["sampleRate"], "sampleRate", maximum=384_000)
    channel_count = _positive_int(result["channelCount"], "channelCount", maximum=2)
    if sample_rate < 8_000 or channel_count not in {1, 2}:
        raise IsolatedSpeechContractError("runtime request audio format is invalid")
    _ref(result["runtimeManifestRef"], "runtimeManifestRef")
    _sha256(result["runtimeManifestDigest"], "runtimeManifestDigest")
    _ref(result["outputArtifactBindingRef"], "outputArtifactBindingRef")
    if operation == KOKORO_SYNTHESIZE_FIXED_VOICE:
        _ref(result["voiceId"], "voiceId")
        if result["voiceProfileVersionRef"] is not None:
            raise IsolatedSpeechContractError("Kokoro cannot consume VoiceProfileVersion")
    elif operation == COSYVOICE_BUILD_VOICE_PROFILE:
        if text_value.encode("utf-8") == b"":
            raise IsolatedSpeechContractError("profile transcript text is empty")
        if sha256(text_value.encode("utf-8")).hexdigest() != result[
            "inputLineageRefsAndDigests"
        ]["transcriptTextDigest"]:
            raise IsolatedSpeechContractError(
                "profile transcript text digest is stale"
            )
        if result["voiceId"] is not None or result["voiceProfileVersionRef"] is not None:
            raise IsolatedSpeechContractError("profile build cannot select a voice output")
    else:
        if result["voiceId"] is not None:
            raise IsolatedSpeechContractError("clone dialogue cannot select a preset voice")
        profile_ref = _ref(
            result["voiceProfileVersionRef"], "voiceProfileVersionRef"
        )
        if (
            profile_ref
            != result["inputLineageRefsAndDigests"][
                "voiceProfileVersionRef"
            ]
        ):
            raise IsolatedSpeechContractError(
                "clone dialogue VoiceProfileVersion binding is stale"
            )
    return result


def build_runtime_request(
    *,
    operation_kind: str,
    request_ref: str,
    input_lineage_refs_and_digests: Mapping[str, Any],
    text: str,
    language: str,
    voice_id: str | None,
    voice_profile_version_ref: str | None,
    effective_speech_parameters: Mapping[str, Any],
    sample_rate: int,
    channel_count: int,
    runtime_manifest_ref: str,
    runtime_manifest_digest: str,
    output_artifact_binding_ref: str,
) -> dict[str, Any]:
    """Seal one closed request after every operation-specific check passes."""

    schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_REQUEST_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION,
    }.get(operation_kind)
    if schema is None:
        raise IsolatedSpeechContractError("runtime request operation is unsupported")
    return validate_runtime_request(
        _seal(
            {
                "schemaVersion": schema,
                "requestRef": request_ref,
                "operationKind": operation_kind,
                "inputLineageRefsAndDigests": deepcopy(
                    dict(input_lineage_refs_and_digests)
                ),
                "text": text,
                "language": language,
                "voiceId": voice_id,
                "voiceProfileVersionRef": voice_profile_version_ref,
                "effectiveSpeechParameters": deepcopy(
                    dict(effective_speech_parameters)
                ),
                "sampleRate": sample_rate,
                "channelCount": channel_count,
                "runtimeManifestRef": runtime_manifest_ref,
                "runtimeManifestDigest": runtime_manifest_digest,
                "outputArtifactBindingRef": output_artifact_binding_ref,
            }
        )
    )


def _media_probe(value: Any) -> dict[str, Any]:
    result = _exact(value, _MEDIA_PROBE_FIELDS, "mediaProbe")
    if result["codec"] != "pcm_s16le":
        raise IsolatedSpeechContractError("mediaProbe codec is unsupported")
    sample_rate = _positive_int(result["sampleRate"], "mediaProbe.sampleRate", maximum=384_000)
    channels = _positive_int(result["channelCount"], "mediaProbe.channelCount", maximum=2)
    samples = _positive_int(result["sampleCount"], "mediaProbe.sampleCount")
    duration = _exact(result["durationRational"], _RATIONAL_FIELDS, "durationRational")
    numerator = _positive_int(duration["numerator"], "durationRational.numerator")
    denominator = _positive_int(duration["denominator"], "durationRational.denominator")
    if channels not in {1, 2} or numerator * sample_rate != samples * denominator:
        raise IsolatedSpeechContractError("mediaProbe duration is invalid")
    return result


def _device_facts(value: Any) -> dict[str, Any]:
    result = _exact(value, _DEVICE_FACTS_FIELDS, "deviceFacts")
    if (
        result["deviceType"] not in {"CPU", "CUDA"}
        or type(result["gpuUsed"]) is not bool
        or result["gpuUsed"] != (result["deviceType"] == "CUDA")
    ):
        raise IsolatedSpeechContractError("isolated runtime device facts are invalid")
    _positive_int(result["deviceCount"], "deviceFacts.deviceCount")
    semantic = {key: item for key, item in result.items() if key != "deviceFactsDigest"}
    if result["deviceFactsDigest"] != _digest(semantic):
        raise IsolatedSpeechContractError("deviceFacts digest is invalid")
    return result


def validate_runtime_response(
    value: Any, *, request: Any, manifest: Any
) -> dict[str, Any]:
    selected_request = validate_runtime_request(request)
    operation = selected_request["operationKind"]
    runtime_kind = (
        KOKORO_RUNTIME_KIND
        if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
        else COSYVOICE_RUNTIME_KIND
    )
    selected_manifest = validate_runtime_manifest(manifest, runtime_kind=runtime_kind)
    fields = (
        _PROFILE_RESPONSE_FIELDS
        if operation == COSYVOICE_BUILD_VOICE_PROFILE
        else _RESPONSE_FIELDS
    )
    result = _verify_sealed(value, fields, "isolated runtime response")
    schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION,
    }[operation]
    if (
        selected_request["runtimeManifestRef"]
        != selected_manifest["runtimeManifestRef"]
        or selected_request["runtimeManifestDigest"]
        != selected_manifest["payloadDigest"]
        or result["schemaVersion"] != schema
        or result["requestRef"] != selected_request["requestRef"]
        or result["requestDigest"] != selected_request["payloadDigest"]
        or result["operationKind"] != operation
        or result["engineCommit"] != selected_manifest["engineCommit"]
        or result["matchaTtsCommit"] != selected_manifest["matchaTtsCommit"]
        or result["modelBundleDigest"] != selected_manifest["modelBundleDigest"]
        or result["dependencyLockDigest"] != selected_manifest["dependencyLockDigest"]
        or result["runtimeManifestDigest"] != selected_manifest["payloadDigest"]
        or result["networkUsed"] is not False
    ):
        raise IsolatedSpeechContractError("runtime response binding is stale")
    for field in (
        "requestDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
        "outputFileDigest",
        "outputPcmContentDigest",
    ):
        _sha256(result[field], field)
    _commit(result["engineCommit"], "engineCommit")
    if runtime_kind == COSYVOICE_RUNTIME_KIND:
        _commit(result["matchaTtsCommit"], "matchaTtsCommit")
    elif result["matchaTtsCommit"] is not None:
        raise IsolatedSpeechContractError(
            "Kokoro response cannot claim a Matcha-TTS commit"
        )
    _positive_int(result["outputByteSize"], "outputByteSize", maximum=10**15)
    probe = _media_probe(result["mediaProbe"])
    if (
        probe["sampleRate"] != selected_request["sampleRate"]
        or probe["channelCount"] != selected_request["channelCount"]
    ):
        raise IsolatedSpeechContractError("runtime response probe is stale")
    _device_facts(result["deviceFacts"])
    started = _utc(result["executionStartedAt"], "executionStartedAt")
    completed = _utc(result["executionCompletedAt"], "executionCompletedAt")
    if completed < started:
        raise IsolatedSpeechContractError("runtime response interval is invalid")
    if operation == COSYVOICE_BUILD_VOICE_PROFILE:
        if (
            result["profilePackageByteSize"] != result["outputByteSize"]
            or result["profilePackageFileDigest"] != result["outputFileDigest"]
            or result["profilePackageContentDigest"]
            != result["outputFileDigest"]
            or result["profilePackageSchemaVersion"] != "voice-profile-package.v1"
            or result["outputPcmContentDigest"]
            != selected_request["inputLineageRefsAndDigests"][
                "audioPcmContentDigest"
            ]
        ):
            raise IsolatedSpeechContractError("profile package response is stale")
        _sha256(
            result["profilePackageContentDigest"],
            "profilePackageContentDigest",
        )
    return result


def validate_test_runtime_response(
    value: Any, *, request: Any, manifest: Any
) -> dict[str, Any]:
    """Validate fake output without upgrading it to production evidence."""

    selected_request = validate_runtime_request(request)
    selected_manifest = validate_test_runtime_manifest(manifest)
    operation = selected_request["operationKind"]
    expected_kind = (
        KOKORO_RUNTIME_KIND
        if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
        else COSYVOICE_RUNTIME_KIND
    )
    if selected_manifest["runtimeKind"] != expected_kind:
        raise IsolatedSpeechContractError(
            "test response targets a different runtime"
        )
    fields = (
        _PROFILE_RESPONSE_FIELDS
        if operation == COSYVOICE_BUILD_VOICE_PROFILE
        else _RESPONSE_FIELDS
    )
    result = _verify_sealed(value, fields, "test runtime response")
    spec = _runtime_spec(expected_kind)
    expected_schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION,
    }[operation]
    if (
        selected_request["runtimeManifestRef"]
        != selected_manifest["runtimeManifestRef"]
        or selected_request["runtimeManifestDigest"]
        != selected_manifest["payloadDigest"]
        or result["schemaVersion"] != expected_schema
        or result["requestRef"] != selected_request["requestRef"]
        or result["requestDigest"] != selected_request["payloadDigest"]
        or result["operationKind"] != operation
        or result["engineCommit"] != spec["engineCommit"]
        or result["matchaTtsCommit"] != spec["matchaTtsCommit"]
        or result["modelBundleDigest"] != spec["modelBundleDigest"]
        or result["dependencyLockDigest"]
        != selected_manifest["dependencyLockDigest"]
        or result["runtimeManifestDigest"]
        != selected_request["runtimeManifestDigest"]
        or result["runtimeManifestDigest"]
        != selected_manifest["payloadDigest"]
        or result["networkUsed"] is not False
    ):
        raise IsolatedSpeechContractError("test runtime response binding is stale")
    for field in (
        "requestDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
        "outputFileDigest",
        "outputPcmContentDigest",
    ):
        _sha256(result[field], field)
    _positive_int(result["outputByteSize"], "outputByteSize", maximum=10**15)
    probe = _media_probe(result["mediaProbe"])
    if (
        probe["sampleRate"] != selected_request["sampleRate"]
        or probe["channelCount"] != selected_request["channelCount"]
    ):
        raise IsolatedSpeechContractError("test runtime response probe is stale")
    _device_facts(result["deviceFacts"])
    started = _utc(result["executionStartedAt"], "executionStartedAt")
    completed = _utc(result["executionCompletedAt"], "executionCompletedAt")
    if completed < started:
        raise IsolatedSpeechContractError("test runtime response interval is invalid")
    if operation == COSYVOICE_BUILD_VOICE_PROFILE:
        if (
            result["profilePackageByteSize"] != result["outputByteSize"]
            or result["profilePackageFileDigest"] != result["outputFileDigest"]
            or result["profilePackageContentDigest"]
            != result["outputFileDigest"]
            or result["profilePackageSchemaVersion"]
            != "voice-profile-package.v1"
            or result["outputPcmContentDigest"]
            != selected_request["inputLineageRefsAndDigests"][
                "audioPcmContentDigest"
            ]
        ):
            raise IsolatedSpeechContractError("test profile response is stale")
        _sha256(
            result["profilePackageContentDigest"],
            "profilePackageContentDigest",
        )
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


def _hash_descriptor(descriptor: int, *, require_executable: bool = False) -> tuple[str, int, tuple[int, ...]]:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
            raise IsolatedSpeechArtifactError("descriptor is not a linked regular file")
        if require_executable and before.st_mode & 0o111 == 0:
            raise IsolatedSpeechArtifactError("runtime executable is not executable")
        digest = sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, _STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except IsolatedSpeechRuntimeError:
        raise
    except OSError as exc:
        raise IsolatedSpeechArtifactError("descriptor hashing failed") from exc
    if _file_identity(before) != _file_identity(after) or size != before.st_size:
        raise IsolatedSpeechArtifactError("descriptor changed during hashing")
    return digest.hexdigest(), size, _file_identity(before)


def _open_readonly(path: Path, *, executable: bool = False) -> tuple[int, str, tuple[int, ...]]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        digest, _, identity = _hash_descriptor(descriptor, require_executable=executable)
    except IsolatedSpeechRuntimeError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise
    except (OSError, TypeError, ValueError):
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise IsolatedSpeechArtifactError(
            "server-resolved descriptor is unavailable"
        ) from None
    return descriptor, digest, identity


def _pin_output_root(path: Path) -> int:
    if not path.is_absolute():
        raise IsolatedSpeechContractError(
            "server-owned output root must be absolute"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise IsolatedSpeechArtifactError(
            "server-owned output root is unavailable"
        ) from None
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise IsolatedSpeechArtifactError(
            "server-owned output root is invalid"
        )
    return descriptor


def _open_output_no_replace(
    root_descriptor: int, storage_key: str
) -> tuple[int, str, int, tuple[int, ...]]:
    pure = PurePosixPath(storage_key)
    if (
        pure.is_absolute()
        or pure.as_posix() != storage_key
        or not storage_key.startswith("asset-versions/audio/")
        or pure.suffix not in {".wav", ".voicepkg"}
        or "." in pure.parts
        or ".." in pure.parts
        or "\\" in storage_key
    ):
        raise IsolatedSpeechContractError("output storage binding is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    directory_descriptor: int | None = None
    descriptor: int | None = None
    try:
        directory_descriptor = os.dup(root_descriptor)
        for part in pure.parts[:-1]:
            child: int | None = None
            try:
                child = os.open(
                    part,
                    directory_flags,
                    dir_fd=directory_descriptor,
                )
            except FileNotFoundError:
                os.mkdir(part, 0o700, dir_fd=directory_descriptor)
                child = os.open(
                    part,
                    directory_flags,
                    dir_fd=directory_descriptor,
                )
            previous = directory_descriptor
            directory_descriptor = child
            try:
                os.close(previous)
            except OSError:
                os.close(directory_descriptor)
                directory_descriptor = None
                raise
        descriptor = os.open(
            pure.parts[-1],
            flags,
            0o600,
            dir_fd=directory_descriptor,
        )
        identity = _file_identity(os.fstat(descriptor))
    except FileExistsError:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        raise IsolatedSpeechArtifactError("output artifact already exists") from None
    except OSError:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if directory_descriptor is not None:
            try:
                os.close(directory_descriptor)
            except OSError:
                pass
        raise IsolatedSpeechArtifactError(
            "output artifact cannot be created"
        ) from None
    return (
        directory_descriptor,
        pure.parts[-1],
        descriptor,
        identity,
    )


def _verify_visible_output(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    original: tuple[int, ...],
) -> tuple[str, int]:
    digest, size, identity = _hash_descriptor(descriptor)
    try:
        visible = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        raise IsolatedSpeechArtifactError("output artifact is not visible") from None
    if (
        _file_identity(visible) != identity
        or identity[5] != 1
        or original[:2] != identity[:2]
    ):
        raise IsolatedSpeechArtifactError("output artifact was replaced")
    return digest, size


def _neutralize_owned_output(
    descriptor: int | None, original: tuple[int, ...] | None
) -> None:
    """Clear only the held inode; never unlink a name that can race replacement."""

    if descriptor is None or original is None:
        return
    try:
        current = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != original[:2]:
            return
        os.ftruncate(descriptor, 0)
        os.fsync(descriptor)
    except OSError:
        return


def _single_json_stdout(output: bytes) -> dict[str, Any]:
    if len(output) <= 0 or len(output) > _MAX_STDOUT:
        raise IsolatedSpeechExecutionError("runtime stdout size is invalid")
    try:
        text = output.decode("utf-8", errors="strict")
        if not text.endswith("\n"):
            raise IsolatedSpeechExecutionError(
                "runtime stdout must end in one newline"
            )
        text = text[:-1]
        value = json.loads(text)
    except (UnicodeError, json.JSONDecodeError):
        raise IsolatedSpeechExecutionError(
            "runtime stdout is not one JSON response"
        ) from None
    if (
        not text
        or not isinstance(value, Mapping)
        or output != _canonical(value) + b"\n"
    ):
        raise IsolatedSpeechExecutionError("runtime stdout is not one canonical JSON response")
    return deepcopy(dict(value))


def _terminate_runtime_group(process: subprocess.Popen[bytes]) -> None:
    """Stop the isolated process group without exposing command or pipe data."""

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.SubprocessError:
        pass


def _run_isolated_runtime(
    *,
    executable_fd: int,
    transport: Mapping[str, Any],
    inherited_descriptors: tuple[int, ...],
    timeout_seconds: float,
) -> bytes:
    """Run one process group and capture at most one bounded stdout response."""

    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    try:
        with tempfile.TemporaryFile() as stdin_file:
            stdin_file.write(_canonical(transport))
            stdin_file.seek(0)
            process = subprocess.Popen(
                [f"/proc/self/fd/{executable_fd}"],
                stdin=stdin_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=dict(_MINIMAL_ENVIRONMENT),
                pass_fds=inherited_descriptors,
                start_new_session=True,
            )
            if process.stdout is None:
                raise IsolatedSpeechExecutionError(
                    "isolated runtime stdout is unavailable"
                )
            os.set_blocking(process.stdout.fileno(), False)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            deadline = time.monotonic() + timeout_seconds
            captured = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise IsolatedSpeechExecutionError(
                        "isolated runtime timed out"
                    )
                events = selector.select(timeout=min(remaining, 0.25))
                if not events:
                    if process.poll() is None:
                        continue
                    try:
                        chunk = os.read(process.stdout.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        break
                else:
                    try:
                        chunk = os.read(process.stdout.fileno(), 65_536)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        break
                captured.extend(chunk)
                if len(captured) > _MAX_STDOUT:
                    raise IsolatedSpeechExecutionError(
                        "runtime stdout size is invalid"
                    )
            return_code = process.wait(
                timeout=max(deadline - time.monotonic(), 0.001)
            )
            if return_code != 0:
                raise IsolatedSpeechExecutionError(
                    "isolated runtime exited non-zero"
                )
            return bytes(captured)
    except IsolatedSpeechRuntimeError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise IsolatedSpeechExecutionError(
            "isolated runtime could not execute"
        ) from None
    finally:
        if selector is not None:
            selector.close()
        if process is not None:
            _terminate_runtime_group(process)
            if process.stdout is not None:
                process.stdout.close()


def _execute_subprocess(
    *,
    executable: Path,
    executable_digest: str,
    request: Mapping[str, Any],
    output_root: Path,
    output_storage_key: str,
    source_path: Path | None,
    expected_source_digest: str | None,
    profile_package_path: Path | None,
    expected_profile_package_digest: str | None,
    timeout_seconds: float,
    response_validator: Callable[[Mapping[str, Any]], dict[str, Any]],
    artifact_validator: Callable[
        [Path, Mapping[str, Any], str, int], Any
    ]
    | None = None,
) -> tuple[dict[str, Any], str, int, Any]:
    if timeout_seconds <= 0 or not math.isfinite(timeout_seconds):
        raise IsolatedSpeechContractError("runtime timeout is invalid")
    executable_fd: int | None = None
    source_fd: int | None = None
    profile_package_fd: int | None = None
    output_root_fd: int | None = None
    output_parent_fd: int | None = None
    output_name: str | None = None
    output_fd: int | None = None
    output_identity: tuple[int, ...] | None = None
    source_identity: tuple[int, ...] | None = None
    profile_package_identity: tuple[int, ...] | None = None
    try:
        executable_fd, observed_executable_digest, executable_identity = _open_readonly(
            executable, executable=True
        )
        if observed_executable_digest != executable_digest:
            raise IsolatedSpeechExecutionError("runtime executable digest drifted")
        if source_path is not None:
            source_fd, source_digest, source_identity = _open_readonly(source_path)
            if source_digest != expected_source_digest:
                raise IsolatedSpeechArtifactError(
                    "server-resolved source audio digest is stale"
                )
        elif expected_source_digest is not None:
            raise IsolatedSpeechContractError(
                "source audio digest has no server-resolved descriptor"
            )
        if profile_package_path is not None:
            (
                profile_package_fd,
                profile_package_digest,
                profile_package_identity,
            ) = _open_readonly(profile_package_path)
            if profile_package_digest != expected_profile_package_digest:
                raise IsolatedSpeechArtifactError(
                    "server-resolved VoiceProfile package digest is stale"
                )
        elif expected_profile_package_digest is not None:
            raise IsolatedSpeechContractError(
                "VoiceProfile package digest has no server-resolved descriptor"
            )
        output_root_fd = _pin_output_root(output_root)
        (
            output_parent_fd,
            output_name,
            output_fd,
            output_identity,
        ) = _open_output_no_replace(
            output_root_fd,
            output_storage_key,
        )
        is_profile = (
            request["operationKind"] == COSYVOICE_BUILD_VOICE_PROFILE
        )
        transport = {
            "schemaVersion": TRANSPORT_SCHEMA_VERSION,
            "request": deepcopy(dict(request)),
            "sourceRecordingFd": source_fd,
            "voiceProfilePackageFd": profile_package_fd,
            "outputAudioArtifactFd": None if is_profile else output_fd,
            "outputProfilePackageFd": output_fd if is_profile else None,
        }
        inherited = tuple(
            descriptor
            for descriptor in (
                executable_fd,
                source_fd,
                profile_package_fd,
                output_fd,
            )
            if descriptor is not None
        )
        stdout = _run_isolated_runtime(
            executable_fd=executable_fd,
            transport=transport,
            inherited_descriptors=inherited,
            timeout_seconds=timeout_seconds,
        )
        response = response_validator(_single_json_stdout(stdout))
        if source_fd is not None:
            source_digest_after, _, source_identity_after = _hash_descriptor(source_fd)
            if (
                source_digest_after != expected_source_digest
                or source_identity_after != source_identity
            ):
                raise IsolatedSpeechArtifactError(
                    "server-resolved source audio changed during execution"
                )
        if profile_package_fd is not None:
            (
                profile_digest_after,
                _,
                profile_identity_after,
            ) = _hash_descriptor(profile_package_fd)
            if (
                profile_digest_after != expected_profile_package_digest
                or profile_identity_after != profile_package_identity
            ):
                raise IsolatedSpeechArtifactError(
                    "server-resolved VoiceProfile package changed during execution"
                )
        output_digest, output_size = _verify_visible_output(
            output_parent_fd,
            output_name,
            output_fd,
            output_identity,
        )
        if (
            response["outputFileDigest"] != output_digest
            or response["outputByteSize"] != output_size
        ):
            raise IsolatedSpeechArtifactError(
                "runtime response does not match descriptor bytes"
            )
        analysis = (
            None
            if artifact_validator is None
            else artifact_validator(
                output_root.joinpath(
                    *PurePosixPath(output_storage_key).parts
                ),
                response,
                output_digest,
                output_size,
            )
        )
        final_output_digest, final_output_size = _verify_visible_output(
            output_parent_fd,
            output_name,
            output_fd,
            output_identity,
        )
        if (
            final_output_digest != output_digest
            or final_output_size != output_size
        ):
            raise IsolatedSpeechArtifactError(
                "runtime output changed during independent verification"
            )
        observed_after, _, identity_after = _hash_descriptor(
            executable_fd, require_executable=True
        )
        if (
            observed_after != executable_digest
            or identity_after != executable_identity
        ):
            raise IsolatedSpeechExecutionError("runtime executable changed during execution")
        return response, output_digest, output_size, analysis
    except Exception:
        _neutralize_owned_output(output_fd, output_identity)
        raise
    finally:
        for descriptor in (
            output_fd,
            output_parent_fd,
            output_root_fd,
            profile_package_fd,
            source_fd,
            executable_fd,
        ):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


_PRODUCTION_EVIDENCE_MINT = object()
_TEST_EVIDENCE_MINT = object()


def _contains_fixture_marker(value: Any) -> bool:
    if isinstance(value, str):
        return value in TEST_FIXTURE_MARKERS
    if isinstance(value, Mapping):
        return any(
            _contains_fixture_marker(key) or _contains_fixture_marker(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_fixture_marker(item) for item in value)
    return False


def _validate_production_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _PRODUCTION_EVIDENCE_FIELDS,
        "isolated speech production evidence",
    )
    operation = result["operationKind"]
    runtime_kind = (
        KOKORO_RUNTIME_KIND
        if operation == KOKORO_SYNTHESIZE_FIXED_VOICE
        else COSYVOICE_RUNTIME_KIND
        if operation
        in {
            COSYVOICE_BUILD_VOICE_PROFILE,
            COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
        }
        else None
    )
    if runtime_kind is None:
        raise IsolatedSpeechContractError(
            "production evidence operation is unsupported"
        )
    spec = _runtime_spec(runtime_kind)
    if (
        result["schemaVersion"] != PRODUCTION_EVIDENCE_SCHEMA_VERSION
        or result["runtimeKind"] != runtime_kind
        or result["engineId"] != spec["engineId"]
        or result["engineCommit"] != spec["engineCommit"]
        or result["matchaTtsCommit"] != spec["matchaTtsCommit"]
        or result["modelId"] != spec["modelId"]
        or result["modelBundleDigest"] != spec["modelBundleDigest"]
        or result["networkUsed"] is not False
        or result["publicationAllowed"] is not False
        or _contains_fixture_marker(result)
        or _contains_forbidden_key(result)
    ):
        raise IsolatedSpeechContractError(
            "production evidence semantics are invalid"
        )
    for field in (
        "runtimeManifestRef",
        "requestRef",
        "outputArtifactBindingRef",
        "analysisEvidenceRef",
    ):
        _ref(result[field], field)
    for field in (
        "runtimeManifestDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "requestDigest",
        "responseDigest",
        "outputFileDigest",
        "outputPcmContentDigest",
        "analysisEvidenceDigest",
    ):
        _sha256(result[field], field)
    _commit(result["engineCommit"], "engineCommit")
    if runtime_kind == COSYVOICE_RUNTIME_KIND:
        _commit(result["matchaTtsCommit"], "matchaTtsCommit")
    elif result["matchaTtsCommit"] is not None:
        raise IsolatedSpeechContractError(
            "Kokoro evidence cannot claim Matcha-TTS"
        )
    _lineage(result["inputLineageRefsAndDigests"], operation)
    _positive_int(result["outputByteSize"], "outputByteSize", maximum=10**15)
    _media_probe(result["mediaProbe"])
    _device_facts(result["deviceFacts"])
    profile_fields = (
        "profilePackageByteSize",
        "profilePackageFileDigest",
        "profilePackageContentDigest",
        "profilePackageSchemaVersion",
    )
    if operation == COSYVOICE_BUILD_VOICE_PROFILE:
        _positive_int(
            result["profilePackageByteSize"],
            "profilePackageByteSize",
            maximum=10**15,
        )
        for field in (
            "profilePackageFileDigest",
            "profilePackageContentDigest",
        ):
            _sha256(result[field], field)
        if (
            result["profilePackageByteSize"] != result["outputByteSize"]
            or result["profilePackageFileDigest"]
            != result["outputFileDigest"]
            or result["profilePackageContentDigest"]
            != result["outputFileDigest"]
            or result["profilePackageSchemaVersion"]
            != "voice-profile-package.v1"
        ):
            raise IsolatedSpeechContractError(
                "profile package evidence is stale"
            )
    elif any(result[field] is not None for field in profile_fields):
        raise IsolatedSpeechContractError(
            "audio output cannot claim a VoiceProfile package"
        )
    return result


@dataclass(frozen=True, slots=True, init=False)
class IsolatedSpeechRuntimeEvidence:
    """Mint-only production execution evidence; mappings cannot construct it."""

    _payload_json: str

    @classmethod
    def _from_adapter(cls, value: Mapping[str, Any], *, token: object) -> "IsolatedSpeechRuntimeEvidence":
        if token is not _PRODUCTION_EVIDENCE_MINT:
            raise IsolatedSpeechContractError("production evidence mint is private")
        normalized = _validate_production_evidence(value)
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            _canonical(normalized).decode("utf-8"),
        )
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def _redacted_test_analysis_binding(
    analysis: AudioTechnicalAnalysisEvidence,
) -> dict[str, Any]:
    """Project analysis facts without serializing artifact locator authority."""

    if type(analysis) is not AudioTechnicalAnalysisEvidence:
        raise IsolatedSpeechContractError(
            "exact audio analysis wrapper is required"
        )
    source = analysis.as_dict()
    return _seal(
        {
            "schemaVersion": TEST_ANALYSIS_BINDING_SCHEMA_VERSION,
            "analysisSchemaVersion": source["schemaVersion"],
            "analysisEvidenceRef": source["analysisEvidenceRef"],
            "analysisEvidenceDigest": source["payloadDigest"],
            **{
                field: deepcopy(source[field])
                for field in _TEST_ANALYSIS_FACT_FIELDS
            },
        }
    )


def _validate_test_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _TEST_EVIDENCE_FIELDS,
        "isolated runtime test evidence",
    )
    if (
        result["schemaVersion"] != TEST_EVIDENCE_SCHEMA_VERSION
        or result["fixtureMarkers"] != sorted(TEST_FIXTURE_MARKERS)
        or result["state"] != "TEST_FIXTURE_ONLY"
        or result["authorityState"] != "NOT_AUTHORITY"
        or result["admissionState"] != "NOT_ADMITTED"
        or result["publicationAllowed"] is not False
    ):
        raise IsolatedSpeechContractError("test evidence semantics are invalid")
    _ref(result["runtimeManifestRef"], "runtimeManifestRef")
    for field in (
        "runtimeManifestDigest",
        "outputFileDigest",
    ):
        _sha256(result[field], field)
    _positive_int(result["outputByteSize"], "outputByteSize", maximum=10**15)
    binding = _exact(
        result["requestBinding"],
        _REQUEST_BINDING_FIELDS,
        "test request binding",
    )
    operation = binding["operationKind"]
    expected_schema = {
        KOKORO_SYNTHESIZE_FIXED_VOICE: KOKORO_REQUEST_SCHEMA_VERSION,
        COSYVOICE_BUILD_VOICE_PROFILE: COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE: COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION,
    }.get(operation)
    if binding["schemaVersion"] != expected_schema:
        raise IsolatedSpeechContractError("test request binding is invalid")
    for field in (
        "requestRef",
        "runtimeManifestRef",
        "outputArtifactBindingRef",
    ):
        _ref(binding[field], field)
    for field in (
        "requestDigest",
        "runtimeManifestDigest",
        "textDigest",
    ):
        _sha256(binding[field], field)
    _lineage(binding["inputLineageRefsAndDigests"], operation)
    response = result["response"]
    if not isinstance(response, Mapping):
        raise IsolatedSpeechContractError("test response evidence is invalid")
    supplied_response = response.get("payloadDigest")
    unsigned_response = deepcopy(dict(response))
    unsigned_response.pop("payloadDigest", None)
    if supplied_response != _digest(unsigned_response):
        raise IsolatedSpeechContractError("test response digest is stale")
    analysis = _verify_sealed(
        result["independentAudioAnalysis"],
        _TEST_ANALYSIS_BINDING_FIELDS,
        "test audio analysis binding",
    )
    if (
        analysis["schemaVersion"] != TEST_ANALYSIS_BINDING_SCHEMA_VERSION
        or analysis["analysisSchemaVersion"]
        != AUDIO_TECHNICAL_ANALYSIS_EVIDENCE_SCHEMA_VERSION
    ):
        raise IsolatedSpeechContractError(
            "test audio analysis binding schema is invalid"
        )
    _ref(analysis["analysisEvidenceRef"], "analysisEvidenceRef")
    for field in (
        "analysisEvidenceDigest",
        "fileDigest",
        "pcmContentDigest",
        "analysisParametersDigest",
    ):
        _sha256(analysis[field], field)
    for field in ("byteSize", "sampleRate", "channelCount", "sampleCount"):
        _positive_int(analysis[field], field, maximum=10**15)
    if (
        analysis["validationState"] != "PASSED"
        or analysis["failureReasons"] != []
        or analysis["state"] != "TECHNICAL_ANALYSIS_COMPLETE"
        or analysis["publicationAllowed"] is not False
        or analysis["pcmContentDigest"]
        != response["outputPcmContentDigest"]
    ):
        raise IsolatedSpeechContractError(
            "test audio analysis binding semantics are invalid"
        )
    return result


@dataclass(frozen=True, slots=True, init=False)
class TestOnlyIsolatedRuntimeEvidence:
    """Non-authority evidence emitted only by the repository fake harness."""

    _payload_json: str
    _analysis: AudioTechnicalAnalysisEvidence

    @classmethod
    def _from_harness(
        cls,
        value: Mapping[str, Any],
        *,
        analysis: AudioTechnicalAnalysisEvidence,
        token: object,
    ) -> "TestOnlyIsolatedRuntimeEvidence":
        if token is not _TEST_EVIDENCE_MINT:
            raise IsolatedSpeechContractError("test evidence mint is private")
        if type(analysis) is not AudioTechnicalAnalysisEvidence:
            raise IsolatedSpeechContractError(
                "exact audio analysis wrapper is required"
            )
        normalized = _validate_test_evidence(value)
        if normalized["independentAudioAnalysis"] != (
            _redacted_test_analysis_binding(analysis)
        ):
            raise IsolatedSpeechContractError(
                "test audio analysis capability does not match its binding"
            )
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            _canonical(normalized).decode("utf-8"),
        )
        object.__setattr__(instance, "_analysis", analysis)
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def independent_audio_analysis(self) -> AudioTechnicalAnalysisEvidence:
        return self._analysis


class _ProductionAdapter:
    """Fail-closed production adapter until C3/C4 install evidence exists.

    C2 intentionally exposes no manifest, install-root, executable, descriptor, or
    output-path override.  A future accepted C3/C4 resolver may add a private mint
    for an installed-runtime binding; mapping injection is not a substitute.
    """

    __slots__ = ("_runtime_kind",)

    def __init__(self, *, runtime_kind: str, **configuration: Any) -> None:
        self._runtime_kind = runtime_kind
        if configuration:
            raise IsolatedSpeechContractError(
                "production runtime configuration is install-resolver-only"
            )

    def execute(self, request: Mapping[str, Any]) -> IsolatedSpeechRuntimeEvidence:
        selected = validate_runtime_request(request)
        expected_kind = (
            KOKORO_RUNTIME_KIND
            if selected["operationKind"] == KOKORO_SYNTHESIZE_FIXED_VOICE
            else COSYVOICE_RUNTIME_KIND
        )
        if expected_kind != self._runtime_kind:
            raise IsolatedSpeechContractError(
                "request targets a different production runtime"
            )
        raise IsolatedSpeechRuntimeNotInstalledError()


class KokoroIsolatedRuntimeAdapter(_ProductionAdapter):
    def __init__(self, **configuration: Any) -> None:
        super().__init__(runtime_kind=KOKORO_RUNTIME_KIND, **configuration)


class CosyVoiceIsolatedRuntimeAdapter(_ProductionAdapter):
    def __init__(self, **configuration: Any) -> None:
        super().__init__(runtime_kind=COSYVOICE_RUNTIME_KIND, **configuration)


def _test_output_storage_key(
    *, output_path: Path, artifact_root: Path, is_profile: bool
) -> str:
    try:
        root = artifact_root.absolute()
        output = output_path.absolute()
        relative = output.relative_to(root)
    except (OSError, ValueError):
        raise IsolatedSpeechContractError(
            "test output is outside the server-owned artifact root"
        ) from None
    storage_key = PurePosixPath(relative.as_posix()).as_posix()
    if (
        not storage_key.startswith("asset-versions/audio/")
        or not storage_key.endswith(".voicepkg" if is_profile else ".wav")
        or ".." in PurePosixPath(storage_key).parts
    ):
        raise IsolatedSpeechContractError(
            "test audio output binding is invalid"
        )
    return storage_key


def _test_audio_artifact_evidence(
    *,
    request: Mapping[str, Any],
    response: Mapping[str, Any],
    storage_key: str,
    output_digest: str,
    output_size: int,
) -> dict[str, Any]:
    lineage = request["inputLineageRefsAndDigests"]
    probe = response["mediaProbe"]
    parameters_digest = _digest(request["effectiveSpeechParameters"])
    synthesis_digest = _digest(
        {
            "operationKind": request["operationKind"],
            "runtimeManifestDigest": request["runtimeManifestDigest"],
            "requestDigest": request["payloadDigest"],
        }
    )
    artifact_ref = "audio-artifact-" + output_digest[:32]
    evidence_semantic = {
        "generationRequestDigest": lineage["generationRequestDigest"],
        "executionRequestDigest": request["payloadDigest"],
        "storageKey": storage_key,
        "sha256": output_digest,
    }
    artifact_evidence_ref = (
        "audio-artifact-evidence-" + _digest(evidence_semantic)[:32]
    )
    return _seal(
        {
            "schemaVersion": "v4.audio-artifact-evidence.v1",
            "workspaceRef": lineage["workspaceRef"],
            "productionRunRef": lineage["productionRunRef"],
            "assetRequirementRef": lineage["assetRequirementRef"],
            "assetRequirementDigest": lineage["assetRequirementDigest"],
            "generationRequestRef": lineage["generationRequestRef"],
            "generationRequestVersionRef": lineage[
                "generationRequestVersionRef"
            ],
            "creativeShotRef": lineage["creativeShotRef"],
            "creativeShotVersionRef": lineage["creativeShotVersionRef"],
            "creativeShotDigest": lineage["creativeShotDigest"],
            "scriptRef": lineage["scriptRef"],
            "scriptVersionRef": lineage["scriptVersionRef"],
            "scriptVersionDigest": lineage["scriptVersionDigest"],
            "generationRequestDigest": lineage["generationRequestDigest"],
            "executionRequestDigest": request["payloadDigest"],
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactRef": artifact_ref,
            "storageKey": storage_key,
            "byteSize": output_size,
            "sha256": output_digest,
            "sampleRate": probe["sampleRate"],
            "channels": probe["channelCount"],
            "probe": {
                "sampleRate": probe["sampleRate"],
                "channels": probe["channelCount"],
                "durationSeconds": (
                    probe["sampleCount"] / probe["sampleRate"]
                ),
                "durationSamples": probe["sampleCount"],
                "codec": probe["codec"],
                "container": "wav",
            },
            "parametersDigest": parameters_digest,
            "effectiveParametersDigest": parameters_digest,
            "synthesisSpecDigest": synthesis_digest,
            "adapterIdentity": "m12.test-only-isolated-runtime.v1",
            "audioRole": "dialogue",
            "provenance": "LOCAL_EVIDENCE",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )


def _analyze_test_audio_output(
    *,
    request: Mapping[str, Any],
    artifact_root: Path,
    storage_key: str,
    response: Mapping[str, Any],
    output_digest: str,
    output_size: int,
) -> AudioTechnicalAnalysisEvidence:
    source_evidence = _test_audio_artifact_evidence(
        request=request,
        response=response,
        storage_key=storage_key,
        output_digest=output_digest,
        output_size=output_size,
    )
    try:
        analysis_wrapper = analyze_audio_artifact(
            source_evidence,
            artifact_root=artifact_root,
        )
    except Exception:
        raise IsolatedSpeechArtifactError(
            "independent audio analysis failed"
        ) from None
    analysis = analysis_wrapper.as_dict()
    duration = analysis["duration"]
    response_duration = response["mediaProbe"]["durationRational"]
    if (
        analysis["fileDigest"] != response["outputFileDigest"]
        or analysis["byteSize"] != response["outputByteSize"]
        or analysis["pcmContentDigest"]
        != response["outputPcmContentDigest"]
        or analysis["codec"] != response["mediaProbe"]["codec"]
        or analysis["sampleRate"]
        != response["mediaProbe"]["sampleRate"]
        or analysis["channelCount"]
        != response["mediaProbe"]["channelCount"]
        or analysis["sampleCount"]
        != response["mediaProbe"]["sampleCount"]
        or duration["numerator"] != response_duration["numerator"]
        or duration["denominator"] != response_duration["denominator"]
        or analysis["validationState"] != "PASSED"
        or analysis["clippingDetected"] is not False
    ):
        raise IsolatedSpeechArtifactError(
            "runtime response differs from independent audio analysis"
        )
    return analysis_wrapper


def _validate_profile_source_analysis(
    *,
    request: Mapping[str, Any],
    response: Mapping[str, Any],
    analysis: AudioTechnicalAnalysisEvidence | None,
) -> AudioTechnicalAnalysisEvidence:
    if type(analysis) is not AudioTechnicalAnalysisEvidence:
        raise IsolatedSpeechContractError(
            "profile build requires exact source audio analysis"
        )
    selected = analysis.as_dict()
    lineage = request["inputLineageRefsAndDigests"]
    probe = response["mediaProbe"]
    duration = selected.get("duration")
    response_duration = probe["durationRational"]
    if (
        selected.get("fileDigest") != lineage["audioFileDigest"]
        or selected.get("pcmContentDigest")
        != lineage["audioPcmContentDigest"]
        or selected.get("sampleRate") != probe["sampleRate"]
        or selected.get("channelCount") != probe["channelCount"]
        or selected.get("sampleCount") != probe["sampleCount"]
        or not isinstance(duration, Mapping)
        or duration.get("numerator") != response_duration["numerator"]
        or duration.get("denominator") != response_duration["denominator"]
        or selected.get("validationState") != "PASSED"
        or selected.get("clippingDetected") is not False
    ):
        raise IsolatedSpeechArtifactError(
            "profile response differs from source audio analysis"
        )
    return analysis


class TestOnlyIsolatedRuntimeHarness:
    """Run one digest-pinned fake executable without entering production adapters."""

    __slots__ = ("_executable", "_manifest")

    def __init__(self, *, executable: Path | str, manifest: Mapping[str, Any]) -> None:
        try:
            path = Path(executable).resolve(strict=True)
        except (OSError, TypeError, ValueError):
            raise IsolatedSpeechContractError(
                "test executable is unavailable"
            ) from None
        selected = validate_test_runtime_manifest(manifest)
        descriptor, observed, _ = _open_readonly(path, executable=True)
        os.close(descriptor)
        if observed != selected["runtimeExecutableDigest"]:
            raise IsolatedSpeechContractError("test executable digest is stale")
        self._executable = path
        self._manifest = selected

    def execute(
        self,
        request: Mapping[str, Any],
        *,
        output_path: Path | str,
        source_path: Path | str | None = None,
        voice_profile_package_path: Path | str | None = None,
        artifact_root: Path | str,
        source_audio_analysis: AudioTechnicalAnalysisEvidence | None = None,
        timeout_seconds: float = 5,
    ) -> TestOnlyIsolatedRuntimeEvidence:
        selected = validate_runtime_request(request)
        expected_kind = (
            KOKORO_RUNTIME_KIND
            if selected["operationKind"] == KOKORO_SYNTHESIZE_FIXED_VOICE
            else COSYVOICE_RUNTIME_KIND
        )
        if expected_kind != self._manifest["runtimeKind"]:
            raise IsolatedSpeechContractError("test request targets a different runtime")
        if selected["operationKind"] == COSYVOICE_BUILD_VOICE_PROFILE and source_path is None:
            raise IsolatedSpeechContractError(
                "test profile build requires server-resolved source audio"
            )
        if selected["operationKind"] != COSYVOICE_BUILD_VOICE_PROFILE and source_path is not None:
            raise IsolatedSpeechContractError(
                "test runtime operation cannot receive reference audio"
            )
        if (
            selected["operationKind"] == COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE
            and voice_profile_package_path is None
        ):
            raise IsolatedSpeechContractError(
                "test clone dialogue requires a server-resolved VoiceProfile package"
            )
        if selected["operationKind"] == COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE:
            lineage = selected["inputLineageRefsAndDigests"]
            if (
                lineage["voiceProfilePackageContentDigest"]
                != lineage["voiceProfilePackageFileDigest"]
            ):
                raise IsolatedSpeechContractError(
                    "VoiceProfile package v1 must be byte-addressed"
                )
        if (
            selected["operationKind"] != COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE
            and voice_profile_package_path is not None
        ):
            raise IsolatedSpeechContractError(
                "test runtime operation cannot receive a VoiceProfile package"
            )
        is_profile = (
            selected["operationKind"] == COSYVOICE_BUILD_VOICE_PROFILE
        )
        if not is_profile and source_audio_analysis is not None:
            raise IsolatedSpeechContractError(
                "audio synthesis cannot receive source analysis"
            )
        output = Path(output_path)
        selected_artifact_root = Path(artifact_root)
        storage_key = _test_output_storage_key(
            output_path=output,
            artifact_root=selected_artifact_root,
            is_profile=is_profile,
        )

        def independently_verify(
            _output_path: Path,
            runtime_response: Mapping[str, Any],
            output_digest: str,
            output_size: int,
        ) -> AudioTechnicalAnalysisEvidence:
            if is_profile:
                return _validate_profile_source_analysis(
                    request=selected,
                    response=runtime_response,
                    analysis=source_audio_analysis,
                )
            return _analyze_test_audio_output(
                request=selected,
                artifact_root=selected_artifact_root,
                storage_key=storage_key,
                response=runtime_response,
                output_digest=output_digest,
                output_size=output_size,
            )

        response, output_digest, output_size, independent_analysis = _execute_subprocess(
            executable=self._executable,
            executable_digest=self._manifest["runtimeExecutableDigest"],
            request=selected,
            output_root=selected_artifact_root,
            output_storage_key=storage_key,
            source_path=None if source_path is None else Path(source_path),
            expected_source_digest=(
                selected["inputLineageRefsAndDigests"]["audioFileDigest"]
                if source_path is not None
                else None
            ),
            profile_package_path=(
                None
                if voice_profile_package_path is None
                else Path(voice_profile_package_path)
            ),
            expected_profile_package_digest=(
                selected["inputLineageRefsAndDigests"][
                    "voiceProfilePackageFileDigest"
                ]
                if voice_profile_package_path is not None
                else None
            ),
            timeout_seconds=timeout_seconds,
            response_validator=lambda value: validate_test_runtime_response(
                value,
                request=selected,
                manifest=self._manifest,
            ),
            artifact_validator=independently_verify,
        )
        if (
            response["outputFileDigest"] != output_digest
            or response["outputByteSize"] != output_size
        ):
            raise IsolatedSpeechArtifactError(
                "test runtime response does not match descriptor bytes"
            )
        value = _seal(
            {
                "schemaVersion": "m12.isolated-runtime-test-evidence.v1",
                "fixtureMarkers": sorted(TEST_FIXTURE_MARKERS),
                "runtimeManifestRef": self._manifest["runtimeManifestRef"],
                "runtimeManifestDigest": self._manifest["payloadDigest"],
                "requestBinding": {
                    "schemaVersion": selected["schemaVersion"],
                    "requestRef": selected["requestRef"],
                    "requestDigest": selected["payloadDigest"],
                    "operationKind": selected["operationKind"],
                    "inputLineageRefsAndDigests": selected[
                        "inputLineageRefsAndDigests"
                    ],
                    "runtimeManifestRef": selected["runtimeManifestRef"],
                    "runtimeManifestDigest": selected[
                        "runtimeManifestDigest"
                    ],
                    "outputArtifactBindingRef": selected[
                        "outputArtifactBindingRef"
                    ],
                    "textDigest": sha256(
                        selected["text"].encode("utf-8")
                    ).hexdigest(),
                },
                "response": response,
                "independentAudioAnalysis": _redacted_test_analysis_binding(
                    independent_analysis
                ),
                "outputByteSize": output_size,
                "outputFileDigest": output_digest,
                "state": "TEST_FIXTURE_ONLY",
                "authorityState": "NOT_AUTHORITY",
                "admissionState": "NOT_ADMITTED",
                "publicationAllowed": False,
            }
        )
        return TestOnlyIsolatedRuntimeEvidence._from_harness(
            value,
            analysis=independent_analysis,
            token=_TEST_EVIDENCE_MINT,
        )


def hash_test_executable(path: Path | str) -> str:
    """Hash a fake executable for a test-only manifest."""

    descriptor, digest, _ = _open_readonly(Path(path), executable=True)
    os.close(descriptor)
    return digest


__all__ = [
    "COSYVOICE_BUILD_VOICE_PROFILE",
    "COSYVOICE_DIALOGUE_REQUEST_SCHEMA_VERSION",
    "COSYVOICE_DIALOGUE_RESPONSE_SCHEMA_VERSION",
    "COSYVOICE_ENGINE_COMMIT",
    "COSYVOICE_ENGINE_ID",
    "COSYVOICE_MANIFEST_SCHEMA_VERSION",
    "COSYVOICE_MODEL_BUNDLE_SHA256",
    "COSYVOICE_MODEL_ID",
    "COSYVOICE_PROFILE_REQUEST_SCHEMA_VERSION",
    "COSYVOICE_PROFILE_RESPONSE_SCHEMA_VERSION",
    "COSYVOICE_RUNTIME_KIND",
    "COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE",
    "CosyVoiceIsolatedRuntimeAdapter",
    "ISOLATED_SPEECH_OPERATIONS",
    "IsolatedSpeechArtifactError",
    "IsolatedSpeechContractError",
    "IsolatedSpeechExecutionError",
    "IsolatedSpeechRuntimeEvidence",
    "IsolatedSpeechRuntimeNotInstalledError",
    "KOKORO_ENGINE_COMMIT",
    "KOKORO_ENGINE_ID",
    "KOKORO_MANIFEST_SCHEMA_VERSION",
    "KOKORO_MODEL_BUNDLE_SHA256",
    "KOKORO_MODEL_ID",
    "KOKORO_REQUEST_SCHEMA_VERSION",
    "KOKORO_RESPONSE_SCHEMA_VERSION",
    "KOKORO_RUNTIME_KIND",
    "KOKORO_SYNTHESIZE_FIXED_VOICE",
    "KokoroIsolatedRuntimeAdapter",
    "M12_RUNTIME_NOT_INSTALLED",
    "MATCHA_TTS_COMMIT",
    "PROTOCOL_VERSION",
    "TEST_FIXTURE_MARKERS",
    "TEST_MANIFEST_SCHEMA_VERSION",
    "TestOnlyIsolatedRuntimeEvidence",
    "TestOnlyIsolatedRuntimeHarness",
    "build_runtime_request",
    "build_test_runtime_manifest",
    "hash_test_executable",
    "validate_runtime_manifest",
    "validate_runtime_request",
    "validate_runtime_response",
    "validate_test_runtime_manifest",
    "validate_test_runtime_response",
]
