"""M12-C2 V5 bridge for the two isolated speech runtime protocols.

The bridge consumes existing V5 authority wrappers and projects only the closed
lineage required by the V4 subprocess protocol.  It owns no runtime registry,
VoiceLock, VoiceProfile, Audio AssetVersion, or persistence authority.  Runtime
outputs can enter the existing audio technical-validation and typed-asset path
only through the mint-only production evidence wrapper plus the exact existing
V4 :class:`AudioTechnicalAnalysisEvidence` capability.  Test-harness evidence
therefore fails closed before any production contract can be built.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import re
from typing import Any, Mapping

from services.v4_platform.audio_validation import AudioTechnicalAnalysisEvidence
from services.v4_platform.isolated_speech_runtime import (
    COSYVOICE_BUILD_VOICE_PROFILE,
    COSYVOICE_ENGINE_ID,
    COSYVOICE_MODEL_ID,
    COSYVOICE_RUNTIME_KIND,
    COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    IsolatedSpeechRuntimeEvidence,
    KOKORO_RUNTIME_KIND,
    KOKORO_SYNTHESIZE_FIXED_VOICE,
    PRODUCTION_EVIDENCE_SCHEMA_VERSION,
    build_runtime_request,
    validate_runtime_manifest,
    validate_runtime_request,
)

from .audio import SPEECH_EMOTION_TAGS
from .audio_authority import (
    AudioGenerationRequest,
    RightsBinding,
    VOICE_ASSET_VERSION_SCHEMA_VERSION,
    VoiceAssetVersion,
    build_clone_dialogue_asset_version,
    build_dialogue_asset_version,
    validate_audio_generation_request,
    validate_clone_voice_asset_version,
    validate_voice_asset_version,
)
from .audio_validation import (
    AudioTechnicalValidation,
    build_pre_asset_audio_technical_validation,
    validate_pre_asset_audio_technical_validation,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _required_ref,
)
from .voice import (
    validate_confirmed_clone_voice_lock_bundle,
    validate_confirmed_voice_lock_bundle,
)
from .voice_profile import (
    ConsentGrantVersionV2,
    CurrentConfirmedVoiceProfileAuthority,
    SourceVoiceRecordingAssetVersionBinding,
    VOICE_PROFILE_PACKAGE_FORMAT,
    VOICE_PROFILE_PACKAGE_SCHEMA_VERSION,
    VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION,
    VoiceProfileVersion,
    require_active_consent_grant_version,
    validate_source_transcript_version,
    validate_voice_profile_technical_validation,
)


ISOLATED_SPEECH_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    PRODUCTION_EVIDENCE_SCHEMA_VERSION
)
ISOLATED_SPEECH_ADAPTER_IDENTITY = "v4.isolated-speech-runtime.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMON_SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef")
_DIALOGUE_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_DIALOGUE_PRODUCTION_FIELDS = frozenset(
    {
        *_DIALOGUE_SCOPE_FIELDS,
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
_RUNTIME_BINDING_FIELDS = frozenset(
    {
        "requestRef",
        "runtimeManifestRef",
        "runtimeManifestDigest",
        "outputArtifactBindingRef",
    }
)
_SPEECH_REQUEST_COMMAND_FIELDS = (
    _DIALOGUE_PRODUCTION_FIELDS
    | _RUNTIME_BINDING_FIELDS
    | frozenset(
        {
            "text",
            "language",
            "effectiveSpeechParameters",
            "sampleRate",
            "channelCount",
        }
    )
)
_PROFILE_REQUEST_COMMAND_FIELDS = _RUNTIME_BINDING_FIELDS | frozenset(
    {
        "productionRunRef",
        "evaluatedAt",
        "transcriptText",
        "sampleRate",
        "channelCount",
    }
)
_EFFECTIVE_SPEECH_PARAMETER_FIELDS = frozenset(
    {"rateScale", "pitchSemitones", "emotionTag"}
)
_MEDIA_PROBE_FIELDS = frozenset(
    {"codec", "sampleRate", "channelCount", "sampleCount", "durationRational"}
)
_DURATION_RATIONAL_FIELDS = frozenset({"numerator", "denominator"})
_DEVICE_FACTS_FIELDS = frozenset(
    {"deviceType", "deviceCount", "gpuUsed", "deviceFactsDigest"}
)
_PROFILE_TECHNICAL_COMMAND_FIELDS = frozenset({"technicalValidationRef"})


class IsolatedSpeechBridgeError(EpisodeProductionError):
    """The isolated runtime cannot be connected to existing V5 authority."""

    code = "isolated_speech_bridge_invalid"


class IsolatedSpeechEvidenceBindingError(StaleInputError):
    """Runtime, analysis, generation, or authority aliases do not match."""

    code = "isolated_speech_evidence_binding_stale"


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise IsolatedSpeechBridgeError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise IsolatedSpeechBridgeError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 100_000) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in value
        )
    ):
        raise IsolatedSpeechBridgeError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str, *, maximum: int = 2**63 - 1) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > maximum
    ):
        raise IsolatedSpeechBridgeError(f"{field} is invalid")
    return value


def _utc(value: Any, field: str) -> str:
    selected = _text(value, field, maximum=128)
    normalized = selected[:-1] + "+00:00" if selected.endswith("Z") else selected
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IsolatedSpeechBridgeError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise IsolatedSpeechBridgeError(f"{field} must be an explicit UTC instant")
    return selected


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise IsolatedSpeechBridgeError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _typed_wrapper(value: Any, expected: type, label: str) -> dict[str, Any]:
    if type(value) is not expected:
        raise UpstreamNotReadyError(f"{label} requires the exact immutable wrapper")
    as_dict = getattr(value, "as_dict", None)
    if not callable(as_dict):
        raise UpstreamNotReadyError(f"{label} wrapper is unavailable")
    result = as_dict()
    if not isinstance(result, Mapping):
        raise IsolatedSpeechBridgeError(f"{label} wrapper is invalid")
    return deepcopy(dict(result))


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(
        _required_ref(value.get(field), field) for field in _COMMON_SCOPE_FIELDS
    )  # type: ignore[return-value]


def _dialogue_lineage(command: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in _DIALOGUE_PRODUCTION_FIELDS:
        value = command[field]
        result[field] = (
            _sha256(value, field)
            if field.endswith("Digest")
            else _required_ref(value, field)
        )
    return result


def _effective_speech_parameters(
    value: Any, *, voice_lock_version: Mapping[str, Any]
) -> dict[str, Any]:
    result = _exact(
        value,
        _EFFECTIVE_SPEECH_PARAMETER_FIELDS,
        "effectiveSpeechParameters",
    )
    for field in ("rateScale", "pitchSemitones"):
        selected = result[field]
        expected = voice_lock_version[field]
        if (
            isinstance(selected, bool)
            or not isinstance(selected, (int, float))
            or selected != expected
        ):
            raise IsolatedSpeechEvidenceBindingError(
                f"effectiveSpeechParameters.{field} is stale"
            )
    emotion = _text(
        result["emotionTag"],
        "effectiveSpeechParameters.emotionTag",
        maximum=128,
    )
    if emotion not in SPEECH_EMOTION_TAGS:
        raise IsolatedSpeechEvidenceBindingError(
            "effectiveSpeechParameters.emotionTag is unsupported"
        )
    return result


def build_kokoro_fixed_voice_runtime_request(
    command: Mapping[str, Any],
    *,
    confirmed_voice_lock: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the fixed Kokoro request from one confirmed VoiceLock v1 bundle."""

    selected = _exact(
        command, _SPEECH_REQUEST_COMMAND_FIELDS, "Kokoro runtime request command"
    )
    lock = validate_confirmed_voice_lock_bundle(confirmed_voice_lock)
    root = lock["voiceLock"]
    version = lock["voiceLockVersion"]
    confirmation = lock["voiceLockConfirmation"]
    if _scope(selected) != _scope(root):
        raise IsolatedSpeechEvidenceBindingError(
            "Kokoro request VoiceLock scope is stale"
        )
    language = _text(selected["language"], "language", maximum=64)
    if language != version["languageCode"]:
        raise IsolatedSpeechEvidenceBindingError(
            "Kokoro request language is stale"
        )
    lineage = {
        **_dialogue_lineage(selected),
        "voiceLockRef": root["voiceRef"],
        "voiceLockVersionRef": version["voiceLockVersionRef"],
        "voiceLockVersionDigest": version["payloadDigest"],
        "voiceLockConfirmationRef": confirmation["voiceLockConfirmationRef"],
        "voiceLockConfirmationDigest": confirmation["payloadDigest"],
    }
    return build_runtime_request(
        operation_kind=KOKORO_SYNTHESIZE_FIXED_VOICE,
        request_ref=_required_ref(selected["requestRef"], "requestRef"),
        input_lineage_refs_and_digests=lineage,
        text=_text(selected["text"], "text"),
        language=language,
        voice_id=_required_ref(version["voiceId"], "voiceId"),
        voice_profile_version_ref=None,
        effective_speech_parameters=_effective_speech_parameters(
            selected["effectiveSpeechParameters"], voice_lock_version=version
        ),
        sample_rate=_positive_int(
            selected["sampleRate"], "sampleRate", maximum=384_000
        ),
        channel_count=_positive_int(
            selected["channelCount"], "channelCount", maximum=2
        ),
        runtime_manifest_ref=_required_ref(
            selected["runtimeManifestRef"], "runtimeManifestRef"
        ),
        runtime_manifest_digest=_sha256(
            selected["runtimeManifestDigest"], "runtimeManifestDigest"
        ),
        output_artifact_binding_ref=_required_ref(
            selected["outputArtifactBindingRef"], "outputArtifactBindingRef"
        ),
    )


def build_cosyvoice_profile_runtime_request(
    command: Mapping[str, Any],
    *,
    source_recording_binding: SourceVoiceRecordingAssetVersionBinding,
    consent_grant_version: ConsentGrantVersionV2,
    confirmed_voice_lock: Mapping[str, Any],
    transcript_version: Mapping[str, Any],
    rights_binding: RightsBinding,
) -> dict[str, Any]:
    """Build a profile request from the exact, active C1 clone lineage."""

    selected = _exact(
        command,
        _PROFILE_REQUEST_COMMAND_FIELDS,
        "CosyVoice profile runtime request command",
    )
    source = _typed_wrapper(
        source_recording_binding,
        SourceVoiceRecordingAssetVersionBinding,
        "source recording binding",
    )
    consent = _typed_wrapper(
        consent_grant_version,
        ConsentGrantVersionV2,
        "ConsentGrantVersion v2",
    )
    rights = _typed_wrapper(rights_binding, RightsBinding, "RightsBinding")
    lock = validate_confirmed_clone_voice_lock_bundle(confirmed_voice_lock)
    root = lock["voiceLock"]
    version = lock["voiceLockVersion"]
    confirmation = lock["voiceLockConfirmation"]
    scope = _scope(source)
    if any(_scope(item) != scope for item in (consent, root, version, confirmation)):
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice profile authority scope is stale"
        )
    evaluated_at = _utc(selected["evaluatedAt"], "evaluatedAt")
    effective_consent = require_active_consent_grant_version(
        consent,
        evaluated_at=evaluated_at,
        expected_subject_ref=source["subjectRef"],
        expected_source_binding_ref=source["sourceRecordingBindingRef"],
        expected_source_binding_digest=source["payloadDigest"],
        expected_rights_binding_ref=rights["rightsBindingRef"],
        expected_rights_binding_digest=rights["payloadDigest"],
    ).as_dict()
    transcript = validate_source_transcript_version(
        transcript_version,
        workspace_ref=scope[0],
        project_ref=scope[1],
        series_ref=scope[2],
        production_run_ref=_required_ref(
            selected["productionRunRef"], "productionRunRef"
        ),
        source_asset_version_ref=source["canonicalAssetVersionRef"],
        source_asset_version_digest=source["canonicalAssetVersionDigest"],
    )
    transcript_text = _text(selected["transcriptText"], "transcriptText")
    if sha256(transcript_text.encode("utf-8")).hexdigest() != transcript[
        "transcriptTextDigest"
    ]:
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice profile transcript bytes are stale"
        )
    expected_aliases = {
        "transcriptVersionRef": transcript["transcriptVersionRef"],
        "transcriptVersionDigest": transcript["payloadDigest"],
        "transcriptLanguage": transcript["transcriptLanguage"],
        "transcriptTextDigest": transcript["transcriptTextDigest"],
    }
    if any(source[field] != expected for field, expected in expected_aliases.items()):
        raise IsolatedSpeechEvidenceBindingError(
            "source binding TranscriptVersion aliases are stale"
        )
    if (
        effective_consent != consent
        or version["sourceRecordingBindingRef"]
        != source["sourceRecordingBindingRef"]
        or version["sourceRecordingBindingDigest"] != source["payloadDigest"]
        or version["consentGrantVersionRef"]
        != consent["consentGrantVersionRef"]
        or version["consentGrantVersionDigest"] != consent["payloadDigest"]
        or version["rightsBindingRef"] != rights["rightsBindingRef"]
        or version["rightsBindingDigest"] != rights["payloadDigest"]
        or version["subjectRef"] != source["subjectRef"]
        or version["engineFamily"] != COSYVOICE_ENGINE_ID
        or version["voiceId"] != COSYVOICE_MODEL_ID
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice profile clone lineage is stale"
        )
    sample_rate = _positive_int(
        selected["sampleRate"], "sampleRate", maximum=384_000
    )
    channel_count = _positive_int(
        selected["channelCount"], "channelCount", maximum=2
    )
    if (
        sample_rate != source["mediaProbe"]["sampleRate"]
        or channel_count != source["mediaProbe"]["channelCount"]
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice profile source audio format is stale"
        )
    lineage = {
        "workspaceRef": scope[0],
        "projectRef": scope[1],
        "seriesRef": scope[2],
        "productionRunRef": selected["productionRunRef"],
        "sourceRecordingBindingRef": source["sourceRecordingBindingRef"],
        "sourceRecordingBindingDigest": source["payloadDigest"],
        "canonicalAssetVersionRef": source["canonicalAssetVersionRef"],
        "canonicalAssetVersionDigest": source["canonicalAssetVersionDigest"],
        "audioFileDigest": source["audioFileDigest"],
        "audioPcmContentDigest": source["audioPcmContentDigest"],
        "transcriptVersionRef": transcript["transcriptVersionRef"],
        "transcriptVersionDigest": transcript["payloadDigest"],
        "transcriptTextDigest": transcript["transcriptTextDigest"],
        "consentGrantVersionRef": consent["consentGrantVersionRef"],
        "consentGrantVersionDigest": consent["payloadDigest"],
        "voiceLockRef": root["voiceRef"],
        "voiceLockVersionRef": version["voiceLockVersionRef"],
        "voiceLockVersionDigest": version["payloadDigest"],
        "voiceLockConfirmationRef": confirmation["voiceLockConfirmationRef"],
        "voiceLockConfirmationDigest": confirmation["payloadDigest"],
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "voiceIdentityRef": version["voiceIdentityRef"],
        "voiceIdentityVersionRef": version["voiceIdentityVersionRef"],
        "voiceIdentityDigest": version["voiceIdentityDigest"],
    }
    return build_runtime_request(
        operation_kind=COSYVOICE_BUILD_VOICE_PROFILE,
        request_ref=_required_ref(selected["requestRef"], "requestRef"),
        input_lineage_refs_and_digests=lineage,
        text=transcript_text,
        language=transcript["transcriptLanguage"],
        voice_id=None,
        voice_profile_version_ref=None,
        effective_speech_parameters={},
        sample_rate=sample_rate,
        channel_count=channel_count,
        runtime_manifest_ref=_required_ref(
            selected["runtimeManifestRef"], "runtimeManifestRef"
        ),
        runtime_manifest_digest=_sha256(
            selected["runtimeManifestDigest"], "runtimeManifestDigest"
        ),
        output_artifact_binding_ref=_required_ref(
            selected["outputArtifactBindingRef"], "outputArtifactBindingRef"
        ),
    )


def build_cosyvoice_dialogue_runtime_request(
    command: Mapping[str, Any],
    *,
    current_voice_profile_authority: CurrentConfirmedVoiceProfileAuthority,
    voice_asset_version: VoiceAssetVersion,
) -> dict[str, Any]:
    """Build clone dialogue only from a service-issued current C1 authority."""

    selected = _exact(
        command,
        _SPEECH_REQUEST_COMMAND_FIELDS,
        "CosyVoice dialogue runtime request command",
    )
    if type(current_voice_profile_authority) is not (
        CurrentConfirmedVoiceProfileAuthority
    ):
        raise UpstreamNotReadyError(
            "CosyVoice dialogue requires current confirmed VoiceProfile authority"
        )
    current_voice_profile_authority.assert_current()
    authority = current_voice_profile_authority.as_dict()
    profile = _typed_wrapper(
        VoiceProfileVersion.from_mapping(authority["voiceProfileVersion"]),
        VoiceProfileVersion,
        "VoiceProfileVersion",
    )
    if profile["status"] != "CONFIRMED":
        raise UpstreamNotReadyError(
            "CosyVoice dialogue requires a confirmed VoiceProfileVersion"
        )
    source = authority["sourceRecordingBinding"]
    consent = authority["consentGrantVersion"]
    lock = authority["confirmedVoiceLock"]
    rights = authority["rightsBinding"]
    evaluated_at = authority["evaluatedAt"]
    expected_scope = tuple(selected[field] for field in _DIALOGUE_SCOPE_FIELDS)
    authority_scope = tuple(
        authority[field]
        for field in (*_COMMON_SCOPE_FIELDS, "productionRunRef")
    )
    if (
        expected_scope[:3] != authority_scope[:3]
        or selected["productionRunRef"] != authority_scope[3]
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice dialogue current authority scope is stale"
        )
    voice = _typed_wrapper(
        voice_asset_version, VoiceAssetVersion, "VoiceAssetVersion"
    )
    validated_voice = validate_clone_voice_asset_version(
        voice,
        voice_profile_version=VoiceProfileVersion.from_mapping(profile),
        confirmed_voice_lock=lock,
        consent_grant_version=ConsentGrantVersionV2.from_mapping(consent),
        source_recording_binding=SourceVoiceRecordingAssetVersionBinding.from_mapping(
            source
        ),
        evaluated_at=evaluated_at,
        current_voice_profile_authority=current_voice_profile_authority,
    ).as_dict()
    version = lock["voiceLockVersion"]
    language = _text(selected["language"], "language", maximum=64)
    if language != version["languageCode"]:
        raise IsolatedSpeechEvidenceBindingError(
            "CosyVoice dialogue language is stale"
        )
    lineage = {
        **_dialogue_lineage(selected),
        "voiceProfileRef": profile["voiceProfileRef"],
        "voiceProfileVersionRef": profile["voiceProfileVersionRef"],
        "voiceProfileVersionDigest": profile["payloadDigest"],
        "voiceProfilePackageFileDigest": profile["profilePackage"]["fileDigest"],
        "voiceProfilePackageContentDigest": profile["profilePackage"][
            "contentDigest"
        ],
        "voiceLockVersionRef": profile["voiceLockVersionRef"],
        "voiceLockVersionDigest": profile["voiceLockVersionDigest"],
        "sourceRecordingBindingRef": profile["sourceRecordingBindingRef"],
        "sourceRecordingBindingDigest": profile["sourceRecordingBindingDigest"],
        "consentGrantVersionRef": profile["consentGrantVersionRef"],
        "consentGrantVersionDigest": profile["consentGrantVersionDigest"],
        "rightsBindingRef": profile["rightsBindingRef"],
        "rightsBindingDigest": profile["rightsBindingDigest"],
        "voiceAssetVersionRef": validated_voice["assetVersionRef"],
        "voiceAssetVersionDigest": validated_voice["payloadDigest"],
    }
    return build_runtime_request(
        operation_kind=COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
        request_ref=_required_ref(selected["requestRef"], "requestRef"),
        input_lineage_refs_and_digests=lineage,
        text=_text(selected["text"], "text"),
        language=language,
        voice_id=None,
        voice_profile_version_ref=profile["voiceProfileVersionRef"],
        effective_speech_parameters=_effective_speech_parameters(
            selected["effectiveSpeechParameters"], voice_lock_version=version
        ),
        sample_rate=_positive_int(
            selected["sampleRate"], "sampleRate", maximum=384_000
        ),
        channel_count=_positive_int(
            selected["channelCount"], "channelCount", maximum=2
        ),
        runtime_manifest_ref=_required_ref(
            selected["runtimeManifestRef"], "runtimeManifestRef"
        ),
        runtime_manifest_digest=_sha256(
            selected["runtimeManifestDigest"], "runtimeManifestDigest"
        ),
        output_artifact_binding_ref=_required_ref(
            selected["outputArtifactBindingRef"], "outputArtifactBindingRef"
        ),
    )


def _validate_production_evidence(
    runtime_evidence: Any,
    *,
    runtime_request: Mapping[str, Any],
    expected_operation: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if type(runtime_evidence) is not IsolatedSpeechRuntimeEvidence:
        raise UpstreamNotReadyError(
            "exact production IsolatedSpeechRuntimeEvidence is required"
        )
    request = validate_runtime_request(runtime_request)
    raw_evidence = runtime_evidence.as_dict()
    if not isinstance(raw_evidence, Mapping):
        raise IsolatedSpeechBridgeError(
            "production isolated speech runtime evidence is invalid"
        )
    # The exact V4 wrapper is the sole schema validator and mint authority.  Do
    # not duplicate its closed envelope here: doing so would create a second,
    # eventually divergent evidence contract at the V5 boundary.
    evidence = deepcopy(dict(raw_evidence))
    unsigned = deepcopy(evidence)
    supplied = unsigned.pop("payloadDigest")
    if supplied != _digest(unsigned):
        raise IsolatedSpeechEvidenceBindingError(
            "production runtime evidence payloadDigest is stale"
        )
    expected_kind = (
        KOKORO_RUNTIME_KIND
        if expected_operation == KOKORO_SYNTHESIZE_FIXED_VOICE
        else COSYVOICE_RUNTIME_KIND
    )
    if (
        request["operationKind"] != expected_operation
        or evidence["schemaVersion"]
        != ISOLATED_SPEECH_RUNTIME_EVIDENCE_SCHEMA_VERSION
        or evidence["runtimeKind"] != expected_kind
        or evidence["operationKind"] != expected_operation
        or evidence["runtimeManifestRef"] != request["runtimeManifestRef"]
        or evidence["runtimeManifestDigest"] != request["runtimeManifestDigest"]
        or evidence["requestRef"] != request["requestRef"]
        or evidence["requestDigest"] != request["payloadDigest"]
        or evidence["outputArtifactBindingRef"]
        != request["outputArtifactBindingRef"]
        or evidence["inputLineageRefsAndDigests"]
        != request["inputLineageRefsAndDigests"]
        or evidence["networkUsed"] is not False
        or evidence["publicationAllowed"] is not False
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "production runtime evidence request binding is stale"
        )
    for field in (
        "runtimeManifestDigest",
        "requestDigest",
        "responseDigest",
        "outputFileDigest",
        "outputPcmContentDigest",
        "analysisEvidenceDigest",
    ):
        _sha256(evidence[field], field)
    for field in (
        "runtimeManifestRef",
        "requestRef",
        "outputArtifactBindingRef",
        "analysisEvidenceRef",
    ):
        _required_ref(evidence[field], field)
    _positive_int(evidence["outputByteSize"], "outputByteSize", maximum=10**15)
    _validate_media_probe(evidence["mediaProbe"])
    _validate_device_facts(evidence["deviceFacts"])
    return request, evidence


def _validate_media_probe(value: Any) -> dict[str, Any]:
    result = _exact(value, _MEDIA_PROBE_FIELDS, "mediaProbe")
    if result["codec"] != "pcm_s16le":
        raise IsolatedSpeechBridgeError("mediaProbe.codec is unsupported")
    sample_rate = _positive_int(
        result["sampleRate"], "mediaProbe.sampleRate", maximum=384_000
    )
    channels = _positive_int(
        result["channelCount"], "mediaProbe.channelCount", maximum=2
    )
    samples = _positive_int(result["sampleCount"], "mediaProbe.sampleCount")
    duration = _exact(
        result["durationRational"],
        _DURATION_RATIONAL_FIELDS,
        "mediaProbe.durationRational",
    )
    numerator = _positive_int(
        duration["numerator"], "mediaProbe.durationRational.numerator"
    )
    denominator = _positive_int(
        duration["denominator"], "mediaProbe.durationRational.denominator"
    )
    if channels not in {1, 2} or Fraction(samples, sample_rate) != Fraction(
        numerator, denominator
    ):
        raise IsolatedSpeechBridgeError("mediaProbe duration is stale")
    return result


def _validate_device_facts(value: Any) -> dict[str, Any]:
    result = _exact(value, _DEVICE_FACTS_FIELDS, "deviceFacts")
    if (
        result["deviceType"] != "CPU"
        or type(result["gpuUsed"]) is not bool
        or result["gpuUsed"] is not False
    ):
        raise IsolatedSpeechBridgeError(
            "C2 isolated speech evidence must be CPU-only"
        )
    _positive_int(result["deviceCount"], "deviceFacts.deviceCount")
    semantic = {key: item for key, item in result.items() if key != "deviceFactsDigest"}
    if result["deviceFactsDigest"] != _digest(semantic):
        raise IsolatedSpeechEvidenceBindingError("deviceFacts digest is stale")
    return result


def _bind_analysis(
    runtime_evidence: Mapping[str, Any],
    analysis_evidence: Any,
) -> dict[str, Any]:
    analysis = _typed_wrapper(
        analysis_evidence,
        AudioTechnicalAnalysisEvidence,
        "AudioTechnicalAnalysisEvidence",
    )
    probe = _validate_media_probe(runtime_evidence["mediaProbe"])
    duration = analysis.get("duration")
    expected_duration = {
        "numerator": probe["durationRational"]["numerator"],
        "denominator": probe["durationRational"]["denominator"],
        "unit": "SECONDS",
    }
    if (
        runtime_evidence["analysisEvidenceRef"]
        != analysis.get("analysisEvidenceRef")
        or runtime_evidence["analysisEvidenceDigest"]
        != analysis.get("payloadDigest")
        or runtime_evidence["outputByteSize"] != analysis.get("byteSize")
        or runtime_evidence["outputFileDigest"] != analysis.get("fileDigest")
        or runtime_evidence["outputPcmContentDigest"]
        != analysis.get("pcmContentDigest")
        or probe["codec"] != analysis.get("codec")
        or probe["sampleRate"] != analysis.get("sampleRate")
        or probe["channelCount"] != analysis.get("channelCount")
        or probe["sampleCount"] != analysis.get("sampleCount")
        or duration != expected_duration
        or analysis.get("validationState") != "PASSED"
        or analysis.get("failureReasons") != []
        or analysis.get("clippingDetected") is not False
        or analysis.get("state") != "TECHNICAL_ANALYSIS_COMPLETE"
        or analysis.get("publicationAllowed") is not False
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime output and AudioTechnicalAnalysisEvidence are stale"
        )
    return analysis


def _bind_generation_and_artifact(
    *,
    request: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> None:
    lineage = request["inputLineageRefsAndDigests"]
    expected_generation_aliases = {
        "workspaceRef": lineage["workspaceRef"],
        "productionRunRef": lineage["productionRunRef"],
        "assetRequirementRef": lineage["assetRequirementRef"],
        "assetRequirementDigest": lineage["assetRequirementDigest"],
        "generationRequestRef": lineage["generationRequestRef"],
        "generationRequestVersionRef": lineage["generationRequestVersionRef"],
        "generationRequestDigest": lineage["generationRequestDigest"],
        "creativeShotRef": lineage["creativeShotRef"],
        "creativeShotVersionRef": lineage["creativeShotVersionRef"],
        "creativeShotDigest": lineage["creativeShotDigest"],
        "scriptRef": lineage["scriptRef"],
        "scriptVersionRef": lineage["scriptVersionRef"],
        "scriptVersionDigest": lineage["scriptVersionDigest"],
    }
    if any(
        generation_result.get(field) != expected
        or artifact_evidence.get(field) != expected
        for field, expected in expected_generation_aliases.items()
    ) or any(
        item.get("executionRequestDigest") != request["payloadDigest"]
        or item.get("effectiveParametersDigest")
        != _digest(request["effectiveSpeechParameters"])
        or item.get("adapterIdentity") != ISOLATED_SPEECH_ADAPTER_IDENTITY
        or item.get("provenance") != "LOCAL_EVIDENCE"
        or item.get("publicationAllowed") is not False
        for item in (generation_result, artifact_evidence)
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and V4 generation lineage are stale"
        )
    artifact_probe = artifact_evidence.get("probe")
    media_probe = runtime_evidence["mediaProbe"]
    if (
        not isinstance(artifact_probe, Mapping)
        or artifact_evidence.get("sha256") != runtime_evidence["outputFileDigest"]
        or artifact_evidence.get("byteSize") != runtime_evidence["outputByteSize"]
        or artifact_evidence.get("sampleRate") != media_probe["sampleRate"]
        or artifact_evidence.get("channels") != media_probe["channelCount"]
        or artifact_probe.get("codec") != media_probe["codec"]
        or artifact_probe.get("sampleRate") != media_probe["sampleRate"]
        or artifact_probe.get("channels") != media_probe["channelCount"]
        or artifact_probe.get("durationSamples") != media_probe["sampleCount"]
        or analysis.get("sourceArtifactEvidenceRef")
        != artifact_evidence.get("artifactEvidenceRef")
        or analysis.get("sourceArtifactEvidenceDigest")
        != artifact_evidence.get("payloadDigest")
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and V4 artifact evidence are stale"
        )


def _validated_existing_technical_validation(
    value: Any,
    *,
    runtime_evidence: Mapping[str, Any],
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    v4_analysis_evidence: AudioTechnicalAnalysisEvidence,
) -> dict[str, Any]:
    if type(value) is not AudioTechnicalValidation:
        raise UpstreamNotReadyError(
            "exact AudioTechnicalValidation wrapper is required"
        )
    validated = validate_pre_asset_audio_technical_validation(
        value.as_dict(),
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    ).as_dict()
    if (
        validated["analysisEvidenceRef"]
        != runtime_evidence["analysisEvidenceRef"]
        or validated["analysisEvidenceDigest"]
        != runtime_evidence["analysisEvidenceDigest"]
        or validated["fileDigest"] != runtime_evidence["outputFileDigest"]
        or validated["pcmContentDigest"]
        != runtime_evidence["outputPcmContentDigest"]
        or validated["validationState"] != "PASSED"
        or validated["clippingDetected"] is not False
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and AudioTechnicalValidation are stale"
        )
    return validated


def _bind_runtime_to_audio_generation_request(
    *,
    request: Mapping[str, Any],
    audio_generation_request: Mapping[str, Any],
    voice_asset_version: Mapping[str, Any],
    generation_result: Mapping[str, Any],
) -> None:
    """Close runtime text/voice/lineage onto an existing domain request."""

    lineage = request["inputLineageRefsAndDigests"]
    shared_lineage_fields = (
        *_DIALOGUE_SCOPE_FIELDS,
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
    )
    request_spec = audio_generation_request.get("requestSpec")
    normalized = (
        request_spec.get("normalizedSpeechParameters")
        if isinstance(request_spec, Mapping)
        else None
    )
    expected_kind = (
        "DIALOGUE_SYNTHESIS"
        if isinstance(request_spec, Mapping)
        and request_spec.get("speechRole") == "dialogue"
        else "NARRATION_SYNTHESIS"
        if isinstance(request_spec, Mapping)
        and request_spec.get("speechRole") == "narration"
        else None
    )
    if (
        any(
            audio_generation_request.get(field) != lineage[field]
            for field in shared_lineage_fields
        )
        or audio_generation_request.get("payloadDigest")
        != lineage["generationRequestDigest"]
        or audio_generation_request.get("requestKind") != expected_kind
        or audio_generation_request.get("outputAssetVersionType")
        != "DialogueAssetVersion"
        or not isinstance(request_spec, Mapping)
        or not isinstance(normalized, Mapping)
        or request_spec.get("scriptVersionRef") != lineage["scriptVersionRef"]
        or request_spec.get("scriptVersionDigest")
        != lineage["scriptVersionDigest"]
        or request_spec.get("voiceAssetVersionRef")
        != voice_asset_version["assetVersionRef"]
        or request_spec.get("voiceAssetVersionDigest")
        != voice_asset_version["payloadDigest"]
        or (
            "voiceAssetVersionRef" in lineage
            and lineage["voiceAssetVersionRef"]
            != voice_asset_version["assetVersionRef"]
        )
        or (
            "voiceAssetVersionDigest" in lineage
            and lineage["voiceAssetVersionDigest"]
            != voice_asset_version["payloadDigest"]
        )
        or request_spec.get("language") != request["language"]
        or normalized.get("text") != request["text"]
        or normalized.get("sampleRate") != request["sampleRate"]
        or normalized.get("channels") != request["channelCount"]
        or normalized.get("emotionTag", "neutral")
        != request["effectiveSpeechParameters"]["emotionTag"]
        or generation_result.get("audioRole") != request_spec.get("speechRole")
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and AudioGenerationRequest are stale"
        )


def _bind_fixed_asset_command_to_validated_evidence(
    command: Mapping[str, Any],
    *,
    audio_generation_request: Mapping[str, Any],
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    voice_asset_version: Mapping[str, Any],
) -> None:
    if not isinstance(command, Mapping):
        raise IsolatedSpeechBridgeError(
            "fixed DialogueAssetVersion command is invalid"
        )
    request_spec = audio_generation_request["requestSpec"]
    artifact = command.get("artifact")
    provenance = command.get("provenance")
    expected_request_aliases = {
        **{
            field: audio_generation_request[field]
            for field in _DIALOGUE_SCOPE_FIELDS
        },
        "assetRequirementRef": audio_generation_request[
            "assetRequirementRef"
        ],
        "assetRequirementDigest": audio_generation_request[
            "assetRequirementDigest"
        ],
        "generationRequestRef": audio_generation_request[
            "generationRequestRef"
        ],
        "generationRequestVersionRef": audio_generation_request[
            "generationRequestVersionRef"
        ],
        "generationRequestDigest": audio_generation_request["payloadDigest"],
        "scriptVersionRef": request_spec["scriptVersionRef"],
        "scriptVersionDigest": request_spec["scriptVersionDigest"],
        "voiceAssetVersionRef": voice_asset_version["assetVersionRef"],
        "voiceAssetVersionDigest": voice_asset_version["payloadDigest"],
        "language": request_spec["language"],
        "normalizedSpeechParameters": request_spec[
            "normalizedSpeechParameters"
        ],
        "sourceAudioCueRefs": request_spec["sourceAudioCueRefs"],
        "speechRole": request_spec["speechRole"],
        "dialogueRef": request_spec["dialogueRef"],
        "narrationRef": request_spec["narrationRef"],
    }
    if (
        any(
            command.get(field) != expected
            for field, expected in expected_request_aliases.items()
        )
        or command.get("generationResultRef")
        != generation_result.get("generationResultRef")
        or command.get("generationResultDigest")
        != generation_result.get("payloadDigest")
        or not isinstance(artifact, Mapping)
        or artifact.get("artifactEvidenceRef")
        != artifact_evidence.get("artifactEvidenceRef")
        or artifact.get("artifactEvidenceDigest")
        != artifact_evidence.get("payloadDigest")
        or artifact.get("artifactRef") != artifact_evidence.get("artifactRef")
        or artifact.get("storageKey") != artifact_evidence.get("storageKey")
        or artifact.get("byteSize") != artifact_evidence.get("byteSize")
        or artifact.get("fileDigest") != artifact_evidence.get("sha256")
        or not isinstance(provenance, Mapping)
        or provenance.get("adapterIdentity")
        != generation_result.get("adapterIdentity")
        or provenance.get("generationRecordRef")
        != generation_result.get("generationResultRef")
        or provenance.get("artifactEvidenceRef")
        != artifact_evidence.get("artifactEvidenceRef")
        or provenance.get("artifactEvidenceDigest")
        != artifact_evidence.get("payloadDigest")
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "fixed DialogueAssetVersion evidence binding is stale"
        )


def build_isolated_speech_audio_technical_validation(
    command: Mapping[str, Any],
    *,
    runtime_request: Mapping[str, Any],
    runtime_evidence: IsolatedSpeechRuntimeEvidence,
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    v4_analysis_evidence: AudioTechnicalAnalysisEvidence,
) -> AudioTechnicalValidation:
    """Bind one production synth output into existing pre-asset validation.

    No V4 or V5 evidence is minted here.  Existing generation/artifact evidence
    and the exact V4 analysis wrapper are revalidated by the existing authority
    contracts; this function only proves their aliases refer to the same isolated
    runtime output.
    """

    request = validate_runtime_request(runtime_request)
    operation = request["operationKind"]
    if operation not in {
        KOKORO_SYNTHESIZE_FIXED_VOICE,
        COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    }:
        raise IsolatedSpeechBridgeError(
            "profile package output is not an audio technical-validation input"
        )
    request, evidence = _validate_production_evidence(
        runtime_evidence,
        runtime_request=request,
        expected_operation=operation,
    )
    analysis = _bind_analysis(evidence, v4_analysis_evidence)
    _bind_generation_and_artifact(
        request=request,
        runtime_evidence=evidence,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        analysis=analysis,
    )
    mapping = build_pre_asset_audio_technical_validation(
        command,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )
    return validate_pre_asset_audio_technical_validation(
        mapping,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )


def build_isolated_voice_profile_technical_validation(
    command: Mapping[str, Any],
    *,
    runtime_request: Mapping[str, Any],
    runtime_evidence: IsolatedSpeechRuntimeEvidence,
    runtime_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Project production profile-package evidence into the existing C1 fact."""

    selected = _exact(
        command,
        _PROFILE_TECHNICAL_COMMAND_FIELDS,
        "VoiceProfile technical-validation command",
    )
    request, evidence = _validate_production_evidence(
        runtime_evidence,
        runtime_request=runtime_request,
        expected_operation=COSYVOICE_BUILD_VOICE_PROFILE,
    )
    manifest = validate_runtime_manifest(
        runtime_manifest, runtime_kind=COSYVOICE_RUNTIME_KIND
    )
    if (
        manifest["runtimeManifestRef"] != evidence["runtimeManifestRef"]
        or manifest["payloadDigest"] != evidence["runtimeManifestDigest"]
        or request["runtimeManifestRef"] != manifest["runtimeManifestRef"]
        or request["runtimeManifestDigest"] != manifest["payloadDigest"]
        or evidence["engineId"] != manifest["engineId"]
        or evidence["engineCommit"] != manifest["engineCommit"]
        or evidence["matchaTtsCommit"] != manifest["matchaTtsCommit"]
        or evidence["modelId"] != manifest["modelId"]
        or evidence["modelBundleDigest"] != manifest["modelBundleDigest"]
        or evidence["dependencyLockDigest"]
        != manifest["dependencyLockDigest"]
        or evidence["outputPcmContentDigest"]
        != request["inputLineageRefsAndDigests"]["audioPcmContentDigest"]
        or evidence["profilePackageByteSize"] != evidence["outputByteSize"]
        or evidence["profilePackageFileDigest"]
        != evidence["outputFileDigest"]
        or evidence["profilePackageSchemaVersion"]
        != VOICE_PROFILE_PACKAGE_SCHEMA_VERSION
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "profile runtime manifest binding is stale"
        )
    result = _sealed(
        {
            "schemaVersion": VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION,
            "technicalValidationRef": _required_ref(
                selected["technicalValidationRef"], "technicalValidationRef"
            ),
            "storageBindingRef": request["outputArtifactBindingRef"],
            "byteSize": evidence["profilePackageByteSize"],
            "fileDigest": evidence["profilePackageFileDigest"],
            "contentDigest": evidence["profilePackageContentDigest"],
            "packageFormat": VOICE_PROFILE_PACKAGE_FORMAT,
            "packageSchemaVersion": VOICE_PROFILE_PACKAGE_SCHEMA_VERSION,
            "engineId": manifest["engineId"],
            "engineCommit": manifest["engineCommit"],
            "modelId": manifest["modelId"],
            "modelBundleDigest": manifest["modelBundleDigest"],
            "dependencyLockDigest": manifest["dependencyLockDigest"],
            "runtimeManifestDigest": manifest["payloadDigest"],
            "validationState": "PASSED",
            "publicationAllowed": False,
        }
    )
    return validate_voice_profile_technical_validation(result)


def build_isolated_fixed_dialogue_asset_version(
    command: Mapping[str, Any],
    *,
    runtime_request: Mapping[str, Any],
    runtime_evidence: IsolatedSpeechRuntimeEvidence,
    v4_analysis_evidence: AudioTechnicalAnalysisEvidence,
    audio_technical_validation: AudioTechnicalValidation,
    voice_asset_version: VoiceAssetVersion,
    audio_generation_request: AudioGenerationRequest,
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    confirmed_voice_lock: Mapping[str, Any],
) -> dict[str, Any]:
    """Create the existing fixed v1 dialogue proposal from validated output.

    DialogueAssetVersion v1 intentionally gains no technical-validation fields.
    The validation is consumed here as the gate proving the generation/artifact
    aliases that the existing v1 command already carries.
    """

    request, evidence = _validate_production_evidence(
        runtime_evidence,
        runtime_request=runtime_request,
        expected_operation=KOKORO_SYNTHESIZE_FIXED_VOICE,
    )
    analysis = _bind_analysis(evidence, v4_analysis_evidence)
    _bind_generation_and_artifact(
        request=request,
        runtime_evidence=evidence,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        analysis=analysis,
    )
    _validated_existing_technical_validation(
        audio_technical_validation,
        runtime_evidence=evidence,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )
    lock = validate_confirmed_voice_lock_bundle(confirmed_voice_lock)
    voice_mapping = _typed_wrapper(
        voice_asset_version, VoiceAssetVersion, "VoiceAssetVersion"
    )
    if voice_mapping.get("schemaVersion") != VOICE_ASSET_VERSION_SCHEMA_VERSION:
        raise UpstreamNotReadyError(
            "Kokoro fixed dialogue requires VoiceAssetVersion v1"
        )
    voice = validate_voice_asset_version(
        voice_mapping,
        confirmed_voice_lock=lock,
    ).as_dict()
    lock_root = lock["voiceLock"]
    lock_version = lock["voiceLockVersion"]
    lock_confirmation = lock["voiceLockConfirmation"]
    runtime_lineage = request["inputLineageRefsAndDigests"]
    if (
        runtime_lineage["voiceLockRef"] != lock_root["voiceRef"]
        or runtime_lineage["voiceLockVersionRef"]
        != lock_version["voiceLockVersionRef"]
        or runtime_lineage["voiceLockVersionDigest"]
        != lock_version["payloadDigest"]
        or runtime_lineage["voiceLockConfirmationRef"]
        != lock_confirmation["voiceLockConfirmationRef"]
        or runtime_lineage["voiceLockConfirmationDigest"]
        != lock_confirmation["payloadDigest"]
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and fixed VoiceLock authority are stale"
        )
    generation_request_mapping = _typed_wrapper(
        audio_generation_request,
        AudioGenerationRequest,
        "AudioGenerationRequest",
    )
    domain_request = validate_audio_generation_request(
        generation_request_mapping,
        confirmed_voice_lock=lock,
        voice_asset_version=voice_asset_version,
    ).as_dict()
    _bind_runtime_to_audio_generation_request(
        request=request,
        audio_generation_request=domain_request,
        voice_asset_version=voice,
        generation_result=generation_result,
    )
    _bind_fixed_asset_command_to_validated_evidence(
        command,
        audio_generation_request=domain_request,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        voice_asset_version=voice,
    )
    return build_dialogue_asset_version(
        command,
        confirmed_voice_lock=lock,
        voice_asset_version=voice,
    )


def build_isolated_clone_dialogue_asset_version(
    command: Mapping[str, Any],
    *,
    runtime_request: Mapping[str, Any],
    runtime_evidence: IsolatedSpeechRuntimeEvidence,
    v4_analysis_evidence: AudioTechnicalAnalysisEvidence,
    audio_technical_validation: AudioTechnicalValidation,
    voice_asset_version: VoiceAssetVersion,
    audio_generation_request: AudioGenerationRequest,
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    current_voice_profile_authority: CurrentConfirmedVoiceProfileAuthority,
) -> dict[str, Any]:
    """Use existing typed authority to create a non-admitted dialogue proposal."""

    request, evidence = _validate_production_evidence(
        runtime_evidence,
        runtime_request=runtime_request,
        expected_operation=COSYVOICE_SYNTHESIZE_CLONED_DIALOGUE,
    )
    analysis = _bind_analysis(evidence, v4_analysis_evidence)
    _bind_generation_and_artifact(
        request=request,
        runtime_evidence=evidence,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        analysis=analysis,
    )
    _validated_existing_technical_validation(
        audio_technical_validation,
        runtime_evidence=evidence,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )
    if type(current_voice_profile_authority) is not (
        CurrentConfirmedVoiceProfileAuthority
    ):
        raise UpstreamNotReadyError(
            "current confirmed VoiceProfile authority is required"
        )
    current_voice_profile_authority.assert_current()
    authority = current_voice_profile_authority.as_dict()
    voice = _typed_wrapper(
        voice_asset_version, VoiceAssetVersion, "VoiceAssetVersion"
    )
    profile = VoiceProfileVersion.from_mapping(authority["voiceProfileVersion"])
    consent = ConsentGrantVersionV2.from_mapping(authority["consentGrantVersion"])
    source = SourceVoiceRecordingAssetVersionBinding.from_mapping(
        authority["sourceRecordingBinding"]
    )
    validated_voice = validate_clone_voice_asset_version(
        voice,
        voice_profile_version=profile,
        confirmed_voice_lock=authority["confirmedVoiceLock"],
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=authority["evaluatedAt"],
        current_voice_profile_authority=current_voice_profile_authority,
    ).as_dict()
    profile_mapping = profile.as_dict()
    consent_mapping = consent.as_dict()
    source_mapping = source.as_dict()
    lock_mapping = authority["confirmedVoiceLock"]["voiceLockVersion"]
    rights_mapping = authority["rightsBinding"]
    runtime_lineage = request["inputLineageRefsAndDigests"]
    expected_authority_lineage = {
        "voiceProfileRef": profile_mapping["voiceProfileRef"],
        "voiceProfileVersionRef": profile_mapping["voiceProfileVersionRef"],
        "voiceProfileVersionDigest": profile_mapping["payloadDigest"],
        "voiceProfilePackageFileDigest": profile_mapping["profilePackage"][
            "fileDigest"
        ],
        "voiceProfilePackageContentDigest": profile_mapping["profilePackage"][
            "contentDigest"
        ],
        "voiceLockVersionRef": lock_mapping["voiceLockVersionRef"],
        "voiceLockVersionDigest": lock_mapping["payloadDigest"],
        "sourceRecordingBindingRef": source_mapping[
            "sourceRecordingBindingRef"
        ],
        "sourceRecordingBindingDigest": source_mapping["payloadDigest"],
        "consentGrantVersionRef": consent_mapping["consentGrantVersionRef"],
        "consentGrantVersionDigest": consent_mapping["payloadDigest"],
        "rightsBindingRef": rights_mapping["rightsBindingRef"],
        "rightsBindingDigest": rights_mapping["payloadDigest"],
        "voiceAssetVersionRef": validated_voice["assetVersionRef"],
        "voiceAssetVersionDigest": validated_voice["payloadDigest"],
    }
    if any(
        runtime_lineage.get(field) != expected
        for field, expected in expected_authority_lineage.items()
    ):
        raise IsolatedSpeechEvidenceBindingError(
            "runtime and current VoiceProfile authority are stale"
        )
    generation_request_mapping = _typed_wrapper(
        audio_generation_request,
        AudioGenerationRequest,
        "AudioGenerationRequest",
    )
    domain_request = validate_audio_generation_request(
        generation_request_mapping,
        confirmed_voice_lock=authority["confirmedVoiceLock"],
        voice_asset_version=voice_asset_version,
        voice_profile_version=profile,
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=authority["evaluatedAt"],
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=True,
    ).as_dict()
    _bind_runtime_to_audio_generation_request(
        request=request,
        audio_generation_request=domain_request,
        voice_asset_version=validated_voice,
        generation_result=generation_result,
    )
    return build_clone_dialogue_asset_version(
        command,
        voice_asset_version=voice_asset_version,
        audio_generation_request=audio_generation_request,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        audio_technical_validation=audio_technical_validation,
        confirmed_voice_lock=authority["confirmedVoiceLock"],
        voice_profile_version=profile,
        consent_grant_version=consent,
        source_recording_binding=source,
        evaluated_at=authority["evaluatedAt"],
        current_voice_profile_authority=current_voice_profile_authority,
    )


__all__ = [
    "ISOLATED_SPEECH_ADAPTER_IDENTITY",
    "ISOLATED_SPEECH_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "IsolatedSpeechBridgeError",
    "IsolatedSpeechEvidenceBindingError",
    "build_cosyvoice_dialogue_runtime_request",
    "build_cosyvoice_profile_runtime_request",
    "build_isolated_clone_dialogue_asset_version",
    "build_isolated_fixed_dialogue_asset_version",
    "build_isolated_speech_audio_technical_validation",
    "build_isolated_voice_profile_technical_validation",
    "build_kokoro_fixed_voice_runtime_request",
]
