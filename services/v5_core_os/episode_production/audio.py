"""M12 voice-bound dialogue requests and canonical audio AssetVersions.

This module deliberately does not execute a TTS engine.  It plans immutable,
provider-neutral speech requests from the current ExecutableShotGraph lineage and
validates the proposed audio AssetVersion output contract without admission or
storage.  The legacy G4/G5 deterministic sine path remains a separate compatibility
path.
"""

from __future__ import annotations

from copy import deepcopy
import math
from pathlib import PurePosixPath
from typing import Any, Mapping, Protocol

from .assets import ASSET_REQUIREMENT_SCHEMA_VERSION, GENERATION_REQUEST_SCHEMA_VERSION
from .foundation import (
    EpisodeProductionError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _required_ref,
)
from .shot_graph import K2ShotGraphService, require_legacy_executable_graph
from .voice import (
    validate_confirmed_clone_voice_lock_bundle,
    validate_confirmed_voice_lock_bundle,
)


AUDIO_ASSET_VERSION_SCHEMA_VERSION = "v5.k2-audio-asset-version.v1"
AUDIO_REQUEST_PLANNER_ID = "v5.k2.audio-request-planner.v1"
AUDIO_ASSET_ADMISSION_ID = "v5.k2.audio-admission.v1"
AUDIO_ASSET_PROPOSAL_ID = "v5.k2.audio-asset-proposal.v1"
AUDIO_STORAGE_PREFIX = "asset-versions/audio/"
SPEECH_EMOTION_TAGS = frozenset({"neutral", "tense", "whisper", "weary"})
_SPEECH_EMOTION_PARAMETERS: dict[str, tuple[float, float, float]] = {
    "neutral": (0.0, 1.0, 1.0),
    "tense": (1.5, 1.08, 1.12),
    "whisper": (-1.0, 0.90, 0.58),
    "weary": (-2.0, 0.86, 0.72),
}
SPEECH_AUDIO_ROLES = frozenset({"dialogue", "narration"})
PROGRAMMATIC_AUDIO_ROLES = frozenset({"ambience", "sfx"})
AUDIO_ROLES = SPEECH_AUDIO_ROLES | PROGRAMMATIC_AUDIO_ROLES | frozenset({"music"})
PROGRAMMATIC_AUDIO_KINDS = frozenset({"rain", "wind", "fire_crackle", "paper"})
PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION = (
    "v5.k2-programmatic-audio-generation-request.v1"
)
TTS_EXECUTION_REQUEST_SCHEMA_VERSION = "v4.local-tts-request.v1"
PROGRAMMATIC_AUDIO_REQUEST_PLANNER_ID = "v5.k2.programmatic-audio-planner.v1"
LOCAL_PIPER_TTS_ADAPTER_ID = "v4.local-piper-tts.v1"
PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID = (
    "v4.deterministic-programmatic-ffmpeg-audio.v1"
)
V4_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.audio-artifact-evidence.v1"
V4_AUDIO_GENERATION_RESULT_SCHEMA_VERSION = "v4.audio-generation-result.v1"
V4_AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION = "v4.audio-artifact-result.v1"
PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION = (
    "v4.preliminary-audio-mix-request.v1"
)
PRELIMINARY_MIX_ADAPTER_ID = "v4.deterministic-preliminary-ffmpeg-mix.v2"
_DIALOGUE_AUDIO_GENERATION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "version",
        "ordinal",
        "assetRequirementRef",
        "assetRequirementDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceScriptSpan",
        "dialogueOrdinal",
        "dialogueSourceDigest",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "mediaKind",
        "mediaType",
        "adapterCapability",
        "providerSelection",
        "parameters",
        "state",
        "requestedProvenance",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_PROGRAMMATIC_AUDIO_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "version",
        "assetRequirementRef",
        "assetRequirementDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceCueRef",
        "sourceCueDigest",
        "cueOrdinal",
        "mediaKind",
        "mediaType",
        "adapterCapability",
        "parameters",
        "state",
        "requestedProvenance",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_AUDIO_ASSET_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "version",
        "assetKind",
        "mediaKind",
        "mediaType",
        "assetAdmissionRef",
        "assetAdmissionVersion",
        "assetAdmissionDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceScriptSpan",
        "dialogueOrdinal",
        "dialogueSourceDigest",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "engineFamily",
        "voiceId",
        "generationParametersDigest",
        "audioRole",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "sha256",
        "sampleRate",
        "channels",
        "probe",
        "supersedesAssetVersionRef",
        "supersedesAssetVersionDigest",
        "provenance",
        "rightsState",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)

AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION = "v5.k2-audio-asset-version.v2"
_AUDIO_ASSET_VERSION_V2_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "version",
        "assetKind",
        "mediaKind",
        "mediaType",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceBinding",
        "voiceBinding",
        "synthesisBinding",
        "generationParametersDigest",
        "audioRole",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "sha256",
        "sampleRate",
        "channels",
        "probe",
        "supersedesAssetVersionRef",
        "supersedesAssetVersionDigest",
        "provenance",
        "rightsState",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)

_V4_AUDIO_LINEAGE_FIELDS = frozenset(
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
_V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS = _V4_AUDIO_LINEAGE_FIELDS | frozenset(
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
_V4_AUDIO_GENERATION_RESULT_FIELDS = _V4_AUDIO_LINEAGE_FIELDS | frozenset(
    {
        "schemaVersion",
        "generationRequestDigest",
        "executionRequestDigest",
        "generationResultRef",
        "adapterIdentity",
        "provenance",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
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
        "audioRole",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_V4_AUDIO_ARTIFACT_RESULT_FIELDS = _V4_AUDIO_LINEAGE_FIELDS | frozenset(
    {
        "schemaVersion",
        "generationRequestDigest",
        "executionRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "adapterIdentity",
        "provenance",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
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
        "audioRole",
        "generationResult",
        "artifactEvidence",
        "publicationAllowed",
        "payloadDigest",
    }
)


class ConfirmedVoiceLockReader(Protocol):
    def get_confirmed_voice_lock(
        self,
        workspace_ref: str,
        project_ref: str,
        series_ref: str,
        character_ref: str,
    ) -> Mapping[str, Any]: ...


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 8_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in value
        )
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _verify_sealed(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EpisodeProductionError(f"{field} must be an object")
    result = deepcopy(dict(value))
    claimed = result.pop("payloadDigest", None)
    if claimed != _digest(result):
        raise StaleInputError(f"{field} payload digest is invalid")
    result["payloadDigest"] = claimed
    return result


def _confirmed_voice_version(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the fixed VoiceLock public bundle without caller aliases."""

    if value is None:
        raise UpstreamNotReadyError("confirmed VoiceLock is required")
    return validate_confirmed_voice_lock_bundle(value)["voiceLockVersion"]


def _normalize_speech_parameters_for_voice_mode(
    value: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any] | None = None,
    voice_mode: str,
) -> dict[str, Any]:
    """Normalize speech parameters against one explicit VoiceLock generation.

    Existing ``speechSynthesis=false`` requests are returned byte-for-byte (as a
    detached copy).  The true branch is closed-world and fills only the two
    documented defaults.  Fixed and clone bundles intentionally use different
    validators so a confirmed v1 bundle can never authorize clone speech and a
    confirmed v2 successor can never enter the fixed-voice TTS path.
    """

    if not isinstance(value, Mapping):
        raise EpisodeProductionError("audio parameters must be an object")
    parameters = deepcopy(dict(value))
    speech_synthesis = parameters.get("speechSynthesis")
    if speech_synthesis is False:
        return parameters
    allowed = {
        "speechSynthesis",
        "text",
        "voiceRef",
        "emotionTag",
        "sampleRate",
        "channels",
        "audioRole",
    }
    if speech_synthesis is not True or set(parameters) - allowed:
        raise EpisodeProductionError("speech synthesis parameters are invalid")
    text = _text(parameters.get("text"), "text", maximum=2_000)
    voice_ref = _required_ref(parameters.get("voiceRef"), "voiceRef")
    emotion = parameters.get("emotionTag")
    if emotion is not None and (
        not isinstance(emotion, str) or emotion not in SPEECH_EMOTION_TAGS
    ):
        raise EpisodeProductionError("emotionTag is invalid")
    sample_rate = _integer(
        parameters.get("sampleRate", 48_000),
        "sampleRate",
        minimum=8_000,
        maximum=384_000,
    )
    channels = _integer(
        parameters.get("channels", 1), "channels", minimum=1, maximum=2
    )
    audio_role = parameters.get("audioRole")
    if not isinstance(audio_role, str) or audio_role not in SPEECH_AUDIO_ROLES:
        raise EpisodeProductionError("audioRole is invalid")
    if confirmed_voice_lock is None:
        raise UpstreamNotReadyError("confirmed VoiceLock is required")
    if voice_mode == "FIXED_V1":
        bundle = validate_confirmed_voice_lock_bundle(confirmed_voice_lock)
    elif voice_mode == "CLONE_V2":
        bundle = validate_confirmed_clone_voice_lock_bundle(
            confirmed_voice_lock
        )
    else:
        raise EpisodeProductionError("speech voice mode is invalid")
    version = bundle["voiceLockVersion"]
    if version.get("voiceRef") != voice_ref:
        raise UpstreamNotReadyError("voiceRef is not the confirmed VoiceLock")
    normalized: dict[str, Any] = {
        "speechSynthesis": True,
        "text": text,
        "voiceRef": voice_ref,
        "sampleRate": sample_rate,
        "channels": channels,
        "audioRole": audio_role,
    }
    if emotion is not None:
        normalized["emotionTag"] = emotion
    return normalized


def normalize_speech_parameters(
    value: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize fixed-voice speech using only a confirmed VoiceLock v1."""

    return _normalize_speech_parameters_for_voice_mode(
        value,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_mode="FIXED_V1",
    )


def normalize_clone_speech_parameters(
    value: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize clone speech using only a confirmed VoiceLock v2 successor."""

    return _normalize_speech_parameters_for_voice_mode(
        value,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_mode="CLONE_V2",
    )


def _effective_speech_parameters(value: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct the frozen V4 emotion profile for evidence verification."""

    parameters = deepcopy(dict(value))
    emotion_tag = parameters.get("emotionTag", "neutral")
    if emotion_tag not in _SPEECH_EMOTION_PARAMETERS:
        raise EpisodeProductionError("emotionTag is invalid")
    pitch, rate, energy = _SPEECH_EMOTION_PARAMETERS[emotion_tag]
    parameters.setdefault("emotionTag", emotion_tag)
    parameters["emotionParameters"] = {
        "pitch": pitch,
        "rate": rate,
        "energy": energy,
    }
    return parameters


def build_tts_execution_request(
    generation_request: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any],
) -> dict[str, Any]:
    """Bridge one sealed V5 dialogue request to the independent V4 TTS port.

    V4 must not import V5.  This function therefore validates the PR-1 request and
    confirmed VoiceLock first, then copies only the closed execution fields that the
    V4 adapter is allowed to consume.  It performs no dispatch or canonical write.
    """

    request = _verify_sealed(generation_request, "audio GenerationRequest")
    if (
        set(request) != _DIALOGUE_AUDIO_GENERATION_REQUEST_FIELDS
        or request.get("schemaVersion") != GENERATION_REQUEST_SCHEMA_VERSION
        or request.get("version") != 1
        or request.get("mediaKind") != "audio"
        or request.get("mediaType") != "audio/wav"
        or request.get("providerSelection") != "UNSELECTED"
        or request.get("state") != "CONTRACT_ONLY_ADAPTER_REQUIRED"
        or request.get("requestedProvenance") != "LOCAL_EVIDENCE"
        or request.get("publicationAllowed") is not False
        or request.get("createdBy") != AUDIO_REQUEST_PLANNER_ID
    ):
        raise EpisodeProductionError("audio GenerationRequest is invalid")
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
        "scriptSceneRef",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "adapterCapability",
    ):
        _required_ref(request.get(field), field)
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "dialogueSourceDigest",
        "voiceLockDigest",
    ):
        _sha256(request.get(field), field)
    _integer(request.get("ordinal"), "ordinal", minimum=1, maximum=10_000)
    _integer(
        request.get("dialogueOrdinal"),
        "dialogueOrdinal",
        minimum=1,
        maximum=10_000,
    )
    _text(request.get("sourceScriptSpan"), "sourceScriptSpan")
    _text(request.get("createdAt"), "createdAt", maximum=64)
    voice = _confirmed_voice_version(confirmed_voice_lock)
    if (
        request.get("workspaceRef") != voice.get("workspaceRef")
        or request.get("characterRef") != voice.get("characterRef")
        or request.get("voiceRef") != voice.get("voiceRef")
        or request.get("voiceLockVersionRef") != voice.get("voiceLockVersionRef")
        or request.get("voiceLockDigest") != voice.get("payloadDigest")
        or request.get("adapterCapability") != voice.get("engineFamily")
    ):
        raise StaleInputError("audio GenerationRequest VoiceLock lineage is stale")
    parameters = normalize_speech_parameters(
        request.get("parameters"), confirmed_voice_lock=confirmed_voice_lock
    )
    if parameters != request.get("parameters"):
        raise StaleInputError("audio GenerationRequest parameters are not normalized")
    if parameters.get("sampleRate") != 48_000:
        raise EpisodeProductionError("local TTS sampleRate must be 48000")
    return _sealed(
        {
            "schemaVersion": TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "generationRequestRef": request["generationRequestRef"],
            "generationRequestVersionRef": request["generationRequestVersionRef"],
            "generationRequestDigest": request["payloadDigest"],
            "assetRequirementRef": request["assetRequirementRef"],
            "assetRequirementDigest": request["assetRequirementDigest"],
            "creativeShotRef": request["creativeShotRef"],
            "creativeShotVersionRef": request["creativeShotVersionRef"],
            "creativeShotDigest": request["creativeShotDigest"],
            "scriptRef": request["scriptRef"],
            "scriptVersionRef": request["scriptVersionRef"],
            "scriptVersionDigest": request["scriptVersionDigest"],
            "scriptSceneRef": request["scriptSceneRef"],
            "sourceScriptSpan": request["sourceScriptSpan"],
            "dialogueOrdinal": request["dialogueOrdinal"],
            "dialogueSourceDigest": request["dialogueSourceDigest"],
            "characterRef": request["characterRef"],
            "voiceRef": request["voiceRef"],
            "voiceLockVersionRef": request["voiceLockVersionRef"],
            "voiceLockDigest": request["voiceLockDigest"],
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "adapterCapability": LOCAL_PIPER_TTS_ADAPTER_ID,
            "engine": {
                "engineFamily": voice["engineFamily"],
                "voiceId": voice["voiceId"],
                "languageCode": voice["languageCode"],
                "basePitchSemitones": voice["pitchSemitones"],
                "baseRateScale": voice["rateScale"],
            },
            "parameters": parameters,
            "state": "LOCAL_EXECUTION_REQUEST",
            "requestedProvenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )


def normalize_programmatic_audio_parameters(value: Any) -> dict[str, Any]:
    """Validate one closed, source-free ambience or SFX synthesis recipe."""

    if not isinstance(value, Mapping):
        raise EpisodeProductionError("programmatic audio parameters must be an object")
    parameters = deepcopy(dict(value))
    expected = {
        "audioRole",
        "synthesisKind",
        "effectKind",
        "durationSamples",
        "sampleRate",
        "channels",
        "seed",
    }
    if set(parameters) != expected:
        raise EpisodeProductionError("programmatic audio parameters are invalid")
    role = parameters.get("audioRole")
    kind = parameters.get("effectKind")
    if (
        parameters.get("synthesisKind") != "programmatic"
        or role not in PROGRAMMATIC_AUDIO_ROLES
        or kind not in PROGRAMMATIC_AUDIO_KINDS
    ):
        raise EpisodeProductionError("programmatic audio role or kind is invalid")
    if (kind in {"rain", "wind"}) != (role == "ambience"):
        raise EpisodeProductionError("programmatic audio role does not match its kind")
    duration_samples = _integer(
        parameters.get("durationSamples"),
        "durationSamples",
        minimum=2_400 if kind == "paper" else 4_800,
        maximum=48_000 if kind == "paper" else 28_800_000,
    )
    sample_rate = _integer(
        parameters.get("sampleRate"),
        "sampleRate",
        minimum=48_000,
        maximum=48_000,
    )
    channels = _integer(
        parameters.get("channels", 1), "channels", minimum=1, maximum=2
    )
    seed = _integer(
        parameters.get("seed"), "seed", minimum=0, maximum=4_294_967_295
    )
    return {
        "audioRole": role,
        "synthesisKind": "programmatic",
        "effectKind": kind,
        "durationSamples": duration_samples,
        "sampleRate": sample_rate,
        "channels": channels,
        "seed": seed,
    }


def build_programmatic_audio_request(value: Any) -> dict[str, Any]:
    """Create one deterministic, Shot/Script-linked non-durable audio request."""

    if not isinstance(value, Mapping):
        raise EpisodeProductionError("programmatic audio request must be an object")
    command = deepcopy(dict(value))
    expected = {
        "workspaceRef",
        "productionRunRef",
        "assetRequirementRef",
        "assetRequirementDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
        "sourceCueRef",
        "sourceCueDigest",
        "cueOrdinal",
        "parameters",
        "createdAt",
    }
    if set(command) != expected:
        raise EpisodeProductionError(
            "programmatic audio request fields do not match the contract"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "assetRequirementRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "sourceCueRef",
    ):
        _required_ref(command.get(field), field)
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "sourceCueDigest",
    ):
        _sha256(command.get(field), field)
    cue_ordinal = _integer(
        command.get("cueOrdinal"), "cueOrdinal", minimum=1, maximum=10_000
    )
    created_at = _text(command.get("createdAt"), "createdAt", maximum=64)
    parameters = normalize_programmatic_audio_parameters(command.get("parameters"))
    semantic = {
        field: command[field]
        for field in (
            "workspaceRef",
            "productionRunRef",
            "assetRequirementRef",
            "assetRequirementDigest",
            "creativeShotRef",
            "creativeShotVersionRef",
            "creativeShotDigest",
            "scriptRef",
            "scriptVersionRef",
            "scriptVersionDigest",
            "scriptSceneRef",
            "sourceCueRef",
            "sourceCueDigest",
        )
    }
    semantic.update(
        {
            "cueOrdinal": cue_ordinal,
            "parameters": parameters,
            "createdAt": created_at,
        }
    )
    request_ref = "m12-programmatic-audio-request-" + _digest(semantic)[:32]
    return _sealed(
        {
            "schemaVersion": PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION,
            "workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"],
            "generationRequestRef": request_ref,
            "generationRequestVersionRef": f"{request_ref}-v1",
            "version": 1,
            "assetRequirementRef": command["assetRequirementRef"],
            "assetRequirementDigest": command["assetRequirementDigest"],
            "creativeShotRef": command["creativeShotRef"],
            "creativeShotVersionRef": command["creativeShotVersionRef"],
            "creativeShotDigest": command["creativeShotDigest"],
            "scriptRef": command["scriptRef"],
            "scriptVersionRef": command["scriptVersionRef"],
            "scriptVersionDigest": command["scriptVersionDigest"],
            "scriptSceneRef": command["scriptSceneRef"],
            "sourceCueRef": command["sourceCueRef"],
            "sourceCueDigest": command["sourceCueDigest"],
            "cueOrdinal": cue_ordinal,
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "adapterCapability": PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID,
            "parameters": parameters,
            "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
            "requestedProvenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
            "createdBy": PROGRAMMATIC_AUDIO_REQUEST_PLANNER_ID,
            "createdAt": created_at,
        }
    )


def build_preliminary_mix_request(value: Any) -> dict[str, Any]:
    """Build one local-only premix request from validated Audio AssetVersions.

    All inputs must be role-discriminated v2 assets from one Shot/Script lineage.
    The request contains only digest-pinned internal storage keys and creates no
    Timeline, Admission, or canonical mix AssetVersion fact.
    """

    if not isinstance(value, list) or not value or len(value) > 32:
        raise EpisodeProductionError("preliminary mix assets are invalid")
    assets = [validate_audio_asset_version_contract(item) for item in value]
    if any(
        asset.get("schemaVersion") != AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION
        for asset in assets
    ):
        raise EpisodeProductionError(
            "preliminary mix requires audio AssetVersion v2 inputs"
        )
    lineage_fields = (
        "workspaceRef",
        "productionRunRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "scriptSceneRef",
    )
    first = assets[0]
    if any(
        any(asset.get(field) != first.get(field) for field in lineage_fields)
        for asset in assets[1:]
    ):
        raise StaleInputError("preliminary mix asset lineage is inconsistent")
    if first.get("sampleRate") != 48_000:
        raise EpisodeProductionError("preliminary mix sampleRate must be 48000")
    channels = first["channels"]
    duration_samples = first["probe"]["durationSamples"]
    seen_versions: set[str] = set()
    tracks: list[dict[str, Any]] = []
    for asset in assets:
        version_ref = asset["assetVersionRef"]
        if version_ref in seen_versions:
            raise EpisodeProductionError("preliminary mix asset is duplicated")
        seen_versions.add(version_ref)
        if (
            asset.get("sampleRate") != 48_000
            or asset.get("channels") != channels
            or asset.get("probe", {}).get("durationSamples") != duration_samples
        ):
            raise EpisodeProductionError(
                "preliminary mix asset formats are inconsistent"
            )
        tracks.append(
            {
                "audioRole": asset["audioRole"],
                "assetVersionRef": version_ref,
                "assetVersionDigest": asset["payloadDigest"],
                "storageKey": asset["storageKey"],
                "sha256": asset["sha256"],
                "sampleRate": asset["sampleRate"],
                "channels": asset["channels"],
                "durationSamples": duration_samples,
            }
        )
    priority = {
        "dialogue": 3,
        "narration": 3,
        "sfx": 2,
        "ambience": 1,
        "music": 0,
    }
    tracks.sort(key=lambda item: (-priority[item["audioRole"]], item["assetVersionRef"]))
    requirement_semantic = {
        "kind": "preliminaryAudioMix",
        "lineage": {field: first[field] for field in lineage_fields},
        "assetVersionDigests": [track["assetVersionDigest"] for track in tracks],
    }
    requirement_digest = _digest(requirement_semantic)
    requirement_ref = "m12-preliminary-mix-requirement-" + requirement_digest[:32]
    request_semantic = {
        "assetRequirementDigest": requirement_digest,
        "tracks": tracks,
    }
    request_ref = "m12-preliminary-mix-request-" + _digest(request_semantic)[:32]
    return _sealed(
        {
            "schemaVersion": PRELIMINARY_AUDIO_MIX_REQUEST_SCHEMA_VERSION,
            "workspaceRef": first["workspaceRef"],
            "productionRunRef": first["productionRunRef"],
            "generationRequestRef": request_ref,
            "generationRequestVersionRef": f"{request_ref}-v1",
            "assetRequirementRef": requirement_ref,
            "assetRequirementDigest": requirement_digest,
            "creativeShotRef": first["creativeShotRef"],
            "creativeShotVersionRef": first["creativeShotVersionRef"],
            "creativeShotDigest": first["creativeShotDigest"],
            "scriptRef": first["scriptRef"],
            "scriptVersionRef": first["scriptVersionRef"],
            "scriptVersionDigest": first["scriptVersionDigest"],
            "scriptSceneRef": first["scriptSceneRef"],
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "adapterCapability": PRELIMINARY_MIX_ADAPTER_ID,
            "parameters": {
                "mixKind": "preliminary",
                "sampleRate": 48_000,
                "channels": channels,
                "durationSamples": duration_samples,
                "tracks": tracks,
            },
            "state": "LOCAL_EXECUTION_REQUEST",
            "requestedProvenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )


def _source_dialogue_spans(shot: Mapping[str, Any]) -> list[str]:
    raw = shot.get("sourceScriptSpans")
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise StaleInputError("CreativeShotVersion source spans are malformed")
    return [item for item in raw if "/dialogue/" in item]


def _voice_bundle(
    reader: ConfirmedVoiceLockReader,
    *,
    workspace_ref: str,
    project_ref: str,
    series_ref: str,
    character_ref: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        bundle = reader.get_confirmed_voice_lock(
            workspace_ref, project_ref, series_ref, character_ref
        )
    except EpisodeProductionError:
        raise
    except Exception as exc:
        raise RepositoryUnavailableError("VoiceLock repository is unavailable") from exc
    version = _confirmed_voice_version(bundle)
    if (
        version.get("workspaceRef") != workspace_ref
        or version.get("projectRef") != project_ref
        or version.get("seriesRef") != series_ref
        or version.get("characterRef") != character_ref
    ):
        raise StaleInputError("confirmed VoiceLock scope is inconsistent")
    return deepcopy(dict(bundle)), version


def validate_audio_asset_version_contract(value: Any) -> dict[str, Any]:
    """Validate the proposed M12 output shape without admitting or storing it."""

    if (
        isinstance(value, Mapping)
        and value.get("schemaVersion") == AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION
    ):
        return validate_audio_asset_version_v2_contract(value)
    asset = _verify_sealed(value, "audio AssetVersion")
    if set(asset) != _AUDIO_ASSET_VERSION_FIELDS:
        raise RepositoryUnavailableError(
            "audio AssetVersion fields do not match the contract"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "assetAdmissionRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationResultRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "characterRef",
        "voiceRef",
        "voiceLockVersionRef",
        "engineFamily",
        "voiceId",
        "artifactEvidenceRef",
        "artifactRef",
    ):
        _required_ref(asset.get(field), field)
    for field in (
        "assetRequirementDigest",
        "assetAdmissionDigest",
        "generationRequestDigest",
        "generationResultDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "dialogueSourceDigest",
        "voiceLockDigest",
        "generationParametersDigest",
        "artifactEvidenceDigest",
        "sha256",
    ):
        _sha256(asset.get(field), field)
    audio_role = asset.get("audioRole")
    if (
        asset.get("schemaVersion") != AUDIO_ASSET_VERSION_SCHEMA_VERSION
        or asset.get("assetKind") != "audio"
        or asset.get("mediaKind") != "audio"
        or asset.get("mediaType") != "audio/wav"
        or not isinstance(audio_role, str)
        or audio_role not in SPEECH_AUDIO_ROLES
        or asset.get("provenance") != "LOCAL_EVIDENCE"
        or asset.get("rightsState") != "LOCAL_EVIDENCE_ONLY"
        or asset.get("state") != "REGISTERED"
        or asset.get("immutable") is not True
        or asset.get("publicationAllowed") is not False
        or asset.get("createdBy") != AUDIO_ASSET_ADMISSION_ID
    ):
        raise RepositoryUnavailableError("audio AssetVersion semantics are invalid")
    _text(asset.get("sourceScriptSpan"), "sourceScriptSpan")
    _text(asset.get("createdAt"), "createdAt", maximum=64)
    version = _integer(asset.get("version"), "version", minimum=1, maximum=10_000)
    _integer(
        asset.get("assetAdmissionVersion"),
        "assetAdmissionVersion",
        minimum=1,
        maximum=10_000,
    )
    _integer(asset.get("dialogueOrdinal"), "dialogueOrdinal", minimum=1, maximum=10_000)
    _integer(asset.get("byteSize"), "byteSize", minimum=1, maximum=10_000_000_000)
    _integer(asset.get("sampleRate"), "sampleRate", minimum=8_000, maximum=384_000)
    _integer(asset.get("channels"), "channels", minimum=1, maximum=2)
    predecessor_ref = asset.get("supersedesAssetVersionRef")
    predecessor_digest = asset.get("supersedesAssetVersionDigest")
    if version == 1:
        if predecessor_ref is not None or predecessor_digest is not None:
            raise RepositoryUnavailableError(
                "initial audio AssetVersion cannot have a predecessor"
            )
    else:
        _required_ref(predecessor_ref, "supersedesAssetVersionRef")
        _sha256(predecessor_digest, "supersedesAssetVersionDigest")
        if predecessor_ref == asset.get("assetVersionRef"):
            raise RepositoryUnavailableError(
                "audio AssetVersion cannot supersede itself"
            )
    probe = asset.get("probe")
    if not isinstance(probe, Mapping) or set(probe) != {
        "sampleRate",
        "channels",
        "durationSeconds",
        "codec",
        "container",
    }:
        raise RepositoryUnavailableError("audio AssetVersion probe is invalid")
    duration = probe.get("durationSeconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
        or probe.get("sampleRate") != asset.get("sampleRate")
        or probe.get("channels") != asset.get("channels")
        or probe.get("container") != "wav"
    ):
        raise RepositoryUnavailableError("audio AssetVersion probe is inconsistent")
    _text(probe.get("codec"), "probe.codec", maximum=64)
    storage_key = asset.get("storageKey")
    if (
        not isinstance(storage_key, str)
        or not storage_key.startswith(AUDIO_STORAGE_PREFIX)
        or storage_key.startswith("/")
        or ".." in storage_key.split("/")
        or storage_key.endswith("/")
    ):
        raise RepositoryUnavailableError("audio AssetVersion storage path is invalid")
    return asset


def validate_audio_asset_version_v2_contract(value: Any) -> dict[str, Any]:
    """Validate the additive role-discriminated proposed AssetVersion contract.

    Version 1 remains frozen for dialogue/narration.  Version 2 can additionally
    represent ambience and SFX without inventing Character or VoiceLock lineage.
    Validation alone never admits or persists the returned object.
    """

    asset = _verify_sealed(value, "audio AssetVersion v2")
    if set(asset) != _AUDIO_ASSET_VERSION_V2_FIELDS:
        raise RepositoryUnavailableError(
            "audio AssetVersion v2 fields do not match the contract"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "assetRef",
        "assetVersionRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationResultRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
        "scriptSceneRef",
        "artifactEvidenceRef",
        "artifactRef",
    ):
        _required_ref(asset.get(field), field)
    for field in (
        "assetRequirementDigest",
        "generationRequestDigest",
        "generationResultDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "generationParametersDigest",
        "artifactEvidenceDigest",
        "sha256",
    ):
        _sha256(asset.get(field), field)
    role = asset.get("audioRole")
    if (
        asset.get("schemaVersion") != AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION
        or asset.get("assetKind") != "audio"
        or asset.get("mediaKind") != "audio"
        or asset.get("mediaType") != "audio/wav"
        or role not in AUDIO_ROLES
        or asset.get("provenance") != "LOCAL_EVIDENCE"
        or asset.get("rightsState") != "LOCAL_EVIDENCE_ONLY"
        or asset.get("state") != "PROPOSED"
        or asset.get("immutable") is not True
        or asset.get("publicationAllowed") is not False
        or asset.get("createdBy") != AUDIO_ASSET_PROPOSAL_ID
    ):
        raise RepositoryUnavailableError("audio AssetVersion v2 semantics are invalid")

    source = asset.get("sourceBinding")
    if not isinstance(source, Mapping) or set(source) != {
        "kind",
        "sourceRef",
        "sourceDigest",
        "ordinal",
    }:
        raise RepositoryUnavailableError("audio source binding is invalid")
    _sha256(source.get("sourceDigest"), "sourceBinding.sourceDigest")
    _integer(
        source.get("ordinal"),
        "sourceBinding.ordinal",
        minimum=1,
        maximum=10_000,
    )

    voice = asset.get("voiceBinding")
    synthesis = asset.get("synthesisBinding")
    if role in SPEECH_AUDIO_ROLES:
        if source.get("kind") != "scriptDialogue" or synthesis is not None:
            raise RepositoryUnavailableError("speech audio lineage is invalid")
        _text(source.get("sourceRef"), "sourceBinding.sourceRef")
        if not isinstance(voice, Mapping) or set(voice) != {
            "characterRef",
            "voiceRef",
            "voiceLockVersionRef",
            "voiceLockDigest",
            "engineFamily",
            "voiceId",
        }:
            raise RepositoryUnavailableError("speech VoiceLock binding is invalid")
        for field in (
            "characterRef",
            "voiceRef",
            "voiceLockVersionRef",
            "engineFamily",
            "voiceId",
        ):
            _required_ref(voice.get(field), f"voiceBinding.{field}")
        _sha256(voice.get("voiceLockDigest"), "voiceBinding.voiceLockDigest")
    elif role in PROGRAMMATIC_AUDIO_ROLES:
        if source.get("kind") != "audioCue" or voice is not None:
            raise RepositoryUnavailableError("programmatic audio lineage is invalid")
        _required_ref(source.get("sourceRef"), "sourceBinding.sourceRef")
        if not isinstance(synthesis, Mapping) or set(synthesis) != {
            "synthesisKind",
            "effectKind",
            "seed",
            "synthesisSpecDigest",
            "adapterIdentity",
        }:
            raise RepositoryUnavailableError(
                "programmatic synthesis binding is invalid"
            )
        if synthesis.get("synthesisKind") != "programmatic":
            raise RepositoryUnavailableError(
                "programmatic synthesis kind is invalid"
            )
        kind = synthesis.get("effectKind")
        if kind not in PROGRAMMATIC_AUDIO_KINDS:
            raise RepositoryUnavailableError("programmatic effect kind is invalid")
        if (kind in {"rain", "wind"}) != (role == "ambience"):
            raise RepositoryUnavailableError(
                "programmatic synthesis role is inconsistent"
            )
        _integer(
            synthesis.get("seed"),
            "synthesisBinding.seed",
            minimum=0,
            maximum=4_294_967_295,
        )
        _sha256(
            synthesis.get("synthesisSpecDigest"),
            "synthesisBinding.synthesisSpecDigest",
        )
        if (
            synthesis.get("adapterIdentity")
            != PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID
        ):
            raise RepositoryUnavailableError(
                "programmatic synthesis adapter is invalid"
            )
    else:
        raise RepositoryUnavailableError(
            "audio AssetVersion v2 role requires its authoritative typed contract"
        )

    _text(asset.get("createdAt"), "createdAt", maximum=64)
    version = _integer(asset.get("version"), "version", minimum=1, maximum=10_000)
    _integer(asset.get("byteSize"), "byteSize", minimum=1, maximum=10_000_000_000)
    _integer(asset.get("sampleRate"), "sampleRate", minimum=48_000, maximum=48_000)
    _integer(asset.get("channels"), "channels", minimum=1, maximum=2)
    predecessor_ref = asset.get("supersedesAssetVersionRef")
    predecessor_digest = asset.get("supersedesAssetVersionDigest")
    if version == 1:
        if predecessor_ref is not None or predecessor_digest is not None:
            raise RepositoryUnavailableError(
                "initial audio AssetVersion cannot have a predecessor"
            )
    else:
        _required_ref(predecessor_ref, "supersedesAssetVersionRef")
        _sha256(predecessor_digest, "supersedesAssetVersionDigest")
        if predecessor_ref == asset.get("assetVersionRef"):
            raise RepositoryUnavailableError(
                "audio AssetVersion cannot supersede itself"
            )
    probe = asset.get("probe")
    if not isinstance(probe, Mapping) or set(probe) != {
        "sampleRate",
        "channels",
        "durationSeconds",
        "durationSamples",
        "codec",
        "container",
    }:
        raise RepositoryUnavailableError("audio AssetVersion probe is invalid")
    duration = probe.get("durationSeconds")
    probe_rate = _integer(
        probe.get("sampleRate"),
        "probe.sampleRate",
        minimum=48_000,
        maximum=48_000,
    )
    probe_channels = _integer(
        probe.get("channels"), "probe.channels", minimum=1, maximum=2
    )
    duration_samples = _integer(
        probe.get("durationSamples"),
        "probe.durationSamples",
        minimum=1,
        maximum=230_400_000,
    )
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration <= 0
        or abs(duration * probe_rate - duration_samples) > 1
        or probe_rate != asset.get("sampleRate")
        or probe_channels != asset.get("channels")
        or probe.get("codec") != "pcm_s16le"
        or probe.get("container") != "wav"
    ):
        raise RepositoryUnavailableError("audio AssetVersion probe is inconsistent")
    _text(probe.get("codec"), "probe.codec", maximum=64)
    storage_key = asset.get("storageKey")
    storage_path = PurePosixPath(storage_key) if isinstance(storage_key, str) else None
    if (
        not isinstance(storage_key, str)
        or not storage_key.startswith(AUDIO_STORAGE_PREFIX)
        or storage_key.startswith("/")
        or "\\" in storage_key
        or "\x00" in storage_key
        or "//" in storage_key
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in storage_key
        )
        or storage_path is None
        or storage_path.as_posix() != storage_key
        or "." in storage_path.parts
        or ".." in storage_path.parts
        or storage_key.endswith("/")
        or storage_path.suffix.lower() != ".wav"
    ):
        raise RepositoryUnavailableError("audio AssetVersion storage path is invalid")
    return asset


def _validated_v4_audio_artifact_bundle(
    value: Any,
    *,
    execution_request: Mapping[str, Any],
    generation_request_digest: str,
    adapter_identity: str,
    audio_role: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Revalidate the complete V4 handoff without trusting repeated aliases."""

    bundle = _verify_sealed(value, "audio artifact result")
    if set(bundle) != _V4_AUDIO_ARTIFACT_RESULT_FIELDS:
        raise EpisodeProductionError("audio artifact result fields are invalid")
    result = _verify_sealed(bundle.get("generationResult"), "audio GenerationResult")
    evidence = _verify_sealed(
        bundle.get("artifactEvidence"), "audio artifact evidence"
    )
    if (
        set(result) != _V4_AUDIO_GENERATION_RESULT_FIELDS
        or set(evidence) != _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS
    ):
        raise EpisodeProductionError("audio artifact contract is invalid")

    execution = _verify_sealed(execution_request, "audio execution request")
    expected_parameters = execution.get("parameters")
    if not isinstance(expected_parameters, Mapping):
        raise EpisodeProductionError("audio execution parameters are invalid")
    expected_parameters_digest = _digest(expected_parameters)
    _sha256(generation_request_digest, "generationRequestDigest")

    for field in _V4_AUDIO_LINEAGE_FIELDS:
        expected = execution.get(field)
        if (
            bundle.get(field) != expected
            or result.get(field) != expected
            or evidence.get(field) != expected
        ):
            raise StaleInputError(f"audio artifact {field} lineage is stale")

    common_fields = {
        "generationRequestDigest",
        "executionRequestDigest",
        "adapterIdentity",
        "provenance",
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
        "audioRole",
        "publicationAllowed",
    }
    for field in common_fields:
        if result.get(field) != bundle.get(field) or evidence.get(field) != bundle.get(
            field
        ):
            raise StaleInputError(f"audio artifact {field} alias is stale")

    if (
        bundle.get("schemaVersion") != V4_AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION
        or result.get("schemaVersion") != V4_AUDIO_GENERATION_RESULT_SCHEMA_VERSION
        or evidence.get("schemaVersion")
        != V4_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or bundle.get("generationRequestDigest") != generation_request_digest
        or bundle.get("executionRequestDigest") != execution["payloadDigest"]
        or bundle.get("adapterIdentity") != adapter_identity
        or bundle.get("provenance") != "LOCAL_EVIDENCE"
        or bundle.get("audioRole") != audio_role
        or bundle.get("parametersDigest") != expected_parameters_digest
        or bundle.get("publicationAllowed") is not False
        or result.get("state") != "SUCCEEDED"
        or evidence.get("state") != "TECHNICALLY_VERIFIED"
        or bundle.get("generationResultRef") != result.get("generationResultRef")
        or bundle.get("generationResultDigest") != result.get("payloadDigest")
        or bundle.get("artifactEvidenceDigest") != evidence.get("payloadDigest")
        or result.get("artifactEvidenceDigest") != evidence.get("payloadDigest")
        or bundle.get("generationResult") != result
        or bundle.get("artifactEvidence") != evidence
    ):
        raise StaleInputError("audio artifact lineage is stale")

    effective_parameters_digest = _sha256(
        bundle.get("effectiveParametersDigest"), "effectiveParametersDigest"
    )
    synthesis_spec_digest = _sha256(
        bundle.get("synthesisSpecDigest"), "synthesisSpecDigest"
    )
    if audio_role in SPEECH_AUDIO_ROLES:
        expected_effective_parameters = _effective_speech_parameters(
            expected_parameters
        )
        if (
            effective_parameters_digest
            != _digest(expected_effective_parameters)
            or synthesis_spec_digest
            != _digest(
                {
                    "adapterIdentity": adapter_identity,
                    "parameters": expected_effective_parameters,
                }
            )
        ):
            raise StaleInputError("speech emotion evidence is stale")
    elif audio_role in PROGRAMMATIC_AUDIO_ROLES:
        if (
            effective_parameters_digest != expected_parameters_digest
            or synthesis_spec_digest
            != _digest(
                {
                    "adapterIdentity": adapter_identity,
                    "parameters": deepcopy(dict(expected_parameters)),
                }
            )
        ):
            raise StaleInputError("programmatic synthesis evidence is stale")
    else:
        raise EpisodeProductionError(
            "audioRole is unsupported by the legacy v1 artifact bundle"
        )

    for field, item in (
        ("generationResultRef", result),
        ("artifactEvidenceRef", evidence),
        ("artifactRef", evidence),
        ("adapterIdentity", result),
    ):
        _required_ref(item.get(field), field)
    for field, item in (
        ("generationResultDigest", bundle),
        ("artifactEvidenceDigest", bundle),
        ("sha256", evidence),
        ("parametersDigest", result),
        ("effectiveParametersDigest", result),
        ("synthesisSpecDigest", evidence),
    ):
        _sha256(item.get(field), field)
    return bundle, result, evidence


def build_proposed_audio_asset_version(
    generation_request: Any,
    artifact_bundle: Any,
    *,
    confirmed_voice_lock: Mapping[str, Any] | None = None,
    version: int = 1,
    supersedes_asset_version_ref: str | None = None,
    supersedes_asset_version_digest: str | None = None,
    created_at: str,
) -> dict[str, Any]:
    """Build, but never persist or admit, a proposed Audio AssetVersion.

    Asset and version refs are derived from sealed lineage and execution evidence;
    no caller-supplied Admission or canonical identity is accepted.  The returned
    immutable proposal remains fenced at ``publicationAllowed=false``.
    """

    request = _verify_sealed(generation_request, "audio GenerationRequest")
    raw_parameters = request.get("parameters")
    if not isinstance(raw_parameters, Mapping):
        raise EpisodeProductionError("audio GenerationRequest parameters are invalid")
    role = raw_parameters.get("audioRole")
    if role in SPEECH_AUDIO_ROLES:
        if confirmed_voice_lock is None:
            raise UpstreamNotReadyError("confirmed VoiceLock is required")
        execution = build_tts_execution_request(
            request, confirmed_voice_lock=confirmed_voice_lock
        )
        expected_adapter_identity = LOCAL_PIPER_TTS_ADAPTER_ID
        voice = _confirmed_voice_version(confirmed_voice_lock)
        source_binding = {
            "kind": "scriptDialogue",
            "sourceRef": request["sourceScriptSpan"],
            "sourceDigest": request["dialogueSourceDigest"],
            "ordinal": request["dialogueOrdinal"],
        }
        voice_binding: dict[str, Any] | None = {
            "characterRef": request["characterRef"],
            "voiceRef": request["voiceRef"],
            "voiceLockVersionRef": request["voiceLockVersionRef"],
            "voiceLockDigest": request["voiceLockDigest"],
            "engineFamily": voice["engineFamily"],
            "voiceId": voice["voiceId"],
        }
        synthesis_binding = None
    elif role in PROGRAMMATIC_AUDIO_ROLES:
        if confirmed_voice_lock is not None:
            raise EpisodeProductionError(
                "programmatic audio cannot contain VoiceLock lineage"
            )
        if (
            set(request) != _PROGRAMMATIC_AUDIO_REQUEST_FIELDS
            or request.get("schemaVersion")
            != PROGRAMMATIC_AUDIO_REQUEST_SCHEMA_VERSION
            or request.get("version") != 1
            or request.get("mediaKind") != "audio"
            or request.get("mediaType") != "audio/wav"
            or request.get("adapterCapability")
            != PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID
            or request.get("state") != "CONTRACT_ONLY_ADAPTER_REQUIRED"
            or request.get("requestedProvenance") != "LOCAL_EVIDENCE"
            or request.get("publicationAllowed") is not False
            or request.get("createdBy") != PROGRAMMATIC_AUDIO_REQUEST_PLANNER_ID
        ):
            raise EpisodeProductionError("programmatic audio request is invalid")
        normalized = normalize_programmatic_audio_parameters(raw_parameters)
        if normalized != request.get("parameters"):
            raise StaleInputError("programmatic audio parameters are not normalized")
        execution = request
        expected_adapter_identity = PROGRAMMATIC_FFMPEG_AUDIO_ADAPTER_ID
        source_binding = {
            "kind": "audioCue",
            "sourceRef": request["sourceCueRef"],
            "sourceDigest": request["sourceCueDigest"],
            "ordinal": request["cueOrdinal"],
        }
        voice_binding = None
        synthesis_binding = {
            "synthesisKind": "programmatic",
            "effectKind": normalized["effectKind"],
            "seed": normalized["seed"],
            "synthesisSpecDigest": None,
            "adapterIdentity": expected_adapter_identity,
        }
    else:
        raise EpisodeProductionError(
            "audioRole is invalid for the legacy audio proposal path"
        )

    _, result, evidence = _validated_v4_audio_artifact_bundle(
        artifact_bundle,
        execution_request=execution,
        generation_request_digest=request["payloadDigest"],
        adapter_identity=expected_adapter_identity,
        audio_role=role,
    )
    if synthesis_binding is not None:
        synthesis_binding["synthesisSpecDigest"] = evidence[
            "synthesisSpecDigest"
        ]

    asset_version_number = _integer(
        version, "version", minimum=1, maximum=10_000
    )
    created = _text(created_at, "createdAt", maximum=64)
    asset_identity_semantic = {
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "sourceBinding": source_binding,
        "audioRole": role,
    }
    asset_ref = "m12-audio-asset-" + _digest(asset_identity_semantic)[:32]
    asset_version_semantic = {
        "assetRef": asset_ref,
        "version": asset_version_number,
        "generationRequestDigest": request["payloadDigest"],
        "generationResultDigest": result["payloadDigest"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
        "createdAt": created,
        "supersedesAssetVersionRef": supersedes_asset_version_ref,
        "supersedesAssetVersionDigest": supersedes_asset_version_digest,
    }
    asset_version_ref = "m12-audio-asset-version-" + _digest(
        asset_version_semantic
    )[:32]

    return validate_audio_asset_version_v2_contract(
        _sealed(
            {
                "schemaVersion": AUDIO_ASSET_VERSION_V2_SCHEMA_VERSION,
                "workspaceRef": request["workspaceRef"],
                "productionRunRef": request["productionRunRef"],
                "assetRef": asset_ref,
                "assetVersionRef": asset_version_ref,
                "version": asset_version_number,
                "assetKind": "audio",
                "mediaKind": "audio",
                "mediaType": "audio/wav",
                "assetRequirementRef": request["assetRequirementRef"],
                "assetRequirementDigest": request["assetRequirementDigest"],
                "generationRequestRef": request["generationRequestRef"],
                "generationRequestVersionRef": request[
                    "generationRequestVersionRef"
                ],
                "generationRequestDigest": request["payloadDigest"],
                "generationResultRef": result["generationResultRef"],
                "generationResultDigest": result["payloadDigest"],
                "creativeShotRef": request["creativeShotRef"],
                "creativeShotVersionRef": request["creativeShotVersionRef"],
                "creativeShotDigest": request["creativeShotDigest"],
                "scriptRef": request["scriptRef"],
                "scriptVersionRef": request["scriptVersionRef"],
                "scriptVersionDigest": request["scriptVersionDigest"],
                "scriptSceneRef": request["scriptSceneRef"],
                "sourceBinding": source_binding,
                "voiceBinding": voice_binding,
                "synthesisBinding": synthesis_binding,
                "generationParametersDigest": result[
                    "effectiveParametersDigest"
                ],
                "audioRole": role,
                "artifactEvidenceRef": evidence["artifactEvidenceRef"],
                "artifactEvidenceDigest": evidence["payloadDigest"],
                "artifactRef": evidence["artifactRef"],
                "storageKey": evidence["storageKey"],
                "byteSize": evidence["byteSize"],
                "sha256": evidence["sha256"],
                "sampleRate": evidence["sampleRate"],
                "channels": evidence["channels"],
                "probe": deepcopy(dict(evidence["probe"])),
                "supersedesAssetVersionRef": supersedes_asset_version_ref,
                "supersedesAssetVersionDigest": supersedes_asset_version_digest,
                "provenance": "LOCAL_EVIDENCE",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "state": "PROPOSED",
                "immutable": True,
                "publicationAllowed": False,
                "createdBy": AUDIO_ASSET_PROPOSAL_ID,
                "createdAt": created,
            }
        )
    )


class K2AudioProductionService:
    """Provider-neutral M12 contract service; it never invokes a TTS engine."""

    def __init__(
        self,
        shot_graph: K2ShotGraphService,
        voice_locks: ConfirmedVoiceLockReader,
    ) -> None:
        self.shot_graph = shot_graph
        self.voice_locks = voice_locks

    @staticmethod
    def _shot_lineage(
        verified: Mapping[str, Any], graph_node: Mapping[str, Any]
    ) -> dict[str, Any]:
        shots = verified.get("creativeShotVersions")
        if not isinstance(shots, list):
            raise RepositoryUnavailableError("CreativeShotVersion bundle is unavailable")
        matches = [
            item
            for item in shots
            if isinstance(item, Mapping)
            and item.get("creativeShotVersionRef")
            == graph_node.get("creativeShotVersionRef")
            and item.get("payloadDigest") == graph_node.get("payloadDigest")
        ]
        if len(matches) != 1:
            raise StaleInputError("ExecutableShotGraph shot lineage is ambiguous")
        shot = _verify_sealed(matches[0], "CreativeShotVersion")
        if shot.get("creativeShotRef") != graph_node.get("creativeShotRef"):
            raise StaleInputError("ExecutableShotGraph shot ref is stale")
        return shot

    @staticmethod
    def _character_by_name(shot: Mapping[str, Any]) -> dict[str, str]:
        locks = shot.get("requiredCharacterIdentityLocks")
        if not isinstance(locks, list) or not all(
            isinstance(item, Mapping) for item in locks
        ):
            raise StaleInputError("shot character identity bindings are unavailable")
        result: dict[str, str] = {}
        character_refs: set[str] = set()
        for item in locks:
            name = item.get("scriptCharacterName")
            character_ref = item.get("characterRef")
            if (
                not isinstance(name, str)
                or not isinstance(character_ref, str)
                or name in result
                or character_ref in character_refs
            ):
                raise StaleInputError("shot character identity bindings are ambiguous")
            result[name] = character_ref
            character_refs.add(character_ref)
        return result

    @staticmethod
    def _requirement(
        *,
        root: Mapping[str, Any],
        graph: Mapping[str, Any],
        shot: Mapping[str, Any],
        line: Mapping[str, Any],
        source_span: str,
        dialogue_ordinal: int,
        global_ordinal: int,
        voice_version: Mapping[str, Any],
    ) -> dict[str, Any]:
        semantic = {
            "workspaceRef": root["workspaceRef"],
            "productionRunRef": root["productionRunRef"],
            "creativeShotVersionRef": shot["creativeShotVersionRef"],
            "creativeShotDigest": shot["payloadDigest"],
            "dialogueOrdinal": dialogue_ordinal,
            "dialogueSourceDigest": _digest(
                {
                    "scriptVersionRef": root["scriptVersionRef"],
                    "scriptSceneRef": shot["scriptSceneRef"],
                    "sourceScriptSpan": source_span,
                    "line": deepcopy(dict(line)),
                }
            ),
            "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
            "voiceLockDigest": voice_version["payloadDigest"],
        }
        requirement_ref = "m12-dialogue-requirement-" + _digest(semantic)[:32]
        return _sealed(
            {
                "schemaVersion": ASSET_REQUIREMENT_SCHEMA_VERSION,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "assetRequirementRef": requirement_ref,
                "version": 1,
                "ordinal": global_ordinal,
                "requirementKey": (
                    f"shot-dialogue:{shot['creativeShotRef']}:{dialogue_ordinal}"
                ),
                "requirementType": "shot-dialogue-audio",
                "required": True,
                "mediaType": "audio/wav",
                "creativeShotRef": shot["creativeShotRef"],
                "creativeShotVersionRef": shot["creativeShotVersionRef"],
                "creativeShotDigest": shot["payloadDigest"],
                "scriptRef": root["scriptRef"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "scriptSceneRef": shot["scriptSceneRef"],
                "sourceScriptSpan": source_span,
                "dialogueOrdinal": dialogue_ordinal,
                "dialogueSourceDigest": semantic["dialogueSourceDigest"],
                "characterRef": voice_version["characterRef"],
                "voiceRef": voice_version["voiceRef"],
                "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
                "voiceLockDigest": voice_version["payloadDigest"],
                "executableShotGraphVersionRef": graph[
                    "executableShotGraphVersionRef"
                ],
                "executableShotGraphDigest": graph["payloadDigest"],
                "resolutionState": "GENERATION_REQUESTED",
                "resolutionKind": "M12_TTS_ADAPTER_REQUIRED",
                "requestedProvenance": "LOCAL_EVIDENCE",
                "rightsState": "LOCAL_EVIDENCE_ONLY",
                "publicationAllowed": False,
                "createdBy": AUDIO_REQUEST_PLANNER_ID,
                "createdAt": graph["createdAt"],
            }
        )

    @staticmethod
    def _request(
        *,
        root: Mapping[str, Any],
        graph: Mapping[str, Any],
        shot: Mapping[str, Any],
        line: Mapping[str, Any],
        source_span: str,
        dialogue_ordinal: int,
        global_ordinal: int,
        requirement: Mapping[str, Any],
        voice_bundle: Mapping[str, Any],
        voice_version: Mapping[str, Any],
    ) -> dict[str, Any]:
        parameters = normalize_speech_parameters(
            {
                "speechSynthesis": True,
                "text": line.get("text"),
                "voiceRef": voice_version["voiceRef"],
                "sampleRate": 48_000,
                "channels": 1,
                "audioRole": "dialogue",
            },
            confirmed_voice_lock=voice_bundle,
        )
        semantic = {
            "assetRequirementDigest": requirement["payloadDigest"],
            "creativeShotDigest": shot["payloadDigest"],
            "dialogueSourceDigest": requirement["dialogueSourceDigest"],
            "voiceLockDigest": voice_version["payloadDigest"],
            "parameters": parameters,
        }
        request_ref = "m12-dialogue-generation-request-" + _digest(semantic)[:32]
        return _sealed(
            {
                "schemaVersion": GENERATION_REQUEST_SCHEMA_VERSION,
                "workspaceRef": root["workspaceRef"],
                "productionRunRef": root["productionRunRef"],
                "generationRequestRef": request_ref,
                "generationRequestVersionRef": f"{request_ref}-v1",
                "version": 1,
                "ordinal": global_ordinal,
                "assetRequirementRef": requirement["assetRequirementRef"],
                "assetRequirementDigest": requirement["payloadDigest"],
                "creativeShotRef": shot["creativeShotRef"],
                "creativeShotVersionRef": shot["creativeShotVersionRef"],
                "creativeShotDigest": shot["payloadDigest"],
                "scriptRef": root["scriptRef"],
                "scriptVersionRef": root["scriptVersionRef"],
                "scriptVersionDigest": root["upstreamSnapshot"]["script"][
                    "versionDigest"
                ],
                "scriptSceneRef": shot["scriptSceneRef"],
                "sourceScriptSpan": source_span,
                "dialogueOrdinal": dialogue_ordinal,
                "dialogueSourceDigest": requirement["dialogueSourceDigest"],
                "characterRef": voice_version["characterRef"],
                "voiceRef": voice_version["voiceRef"],
                "voiceLockVersionRef": voice_version["voiceLockVersionRef"],
                "voiceLockDigest": voice_version["payloadDigest"],
                "mediaKind": "audio",
                "mediaType": "audio/wav",
                "adapterCapability": voice_version["engineFamily"],
                "providerSelection": "UNSELECTED",
                "parameters": parameters,
                "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
                "requestedProvenance": "LOCAL_EVIDENCE",
                "publicationAllowed": False,
                "createdBy": AUDIO_REQUEST_PLANNER_ID,
                "createdAt": graph["createdAt"],
            }
        )

    def plan_dialogue_requests(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        verified = self.shot_graph.verify_shot_graph_current(workspace, run_ref)
        root = verified["root"]
        graph = verified["executableShotGraph"]
        require_legacy_executable_graph(graph)
        requirements: list[dict[str, Any]] = []
        requests: list[dict[str, Any]] = []
        voice_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
        global_ordinal = 0
        nodes = sorted(graph["shots"], key=lambda item: item["globalOrder"])
        for node in nodes:
            shot = self._shot_lineage(verified, node)
            dialogue = shot.get("dialogueRequirements")
            if not isinstance(dialogue, list) or not all(
                isinstance(item, Mapping) for item in dialogue
            ):
                raise StaleInputError("CreativeShotVersion dialogue is malformed")
            spans = _source_dialogue_spans(shot)
            if len(spans) != len(dialogue):
                raise StaleInputError("CreativeShotVersion dialogue lineage is incomplete")
            character_by_name = self._character_by_name(shot)
            for dialogue_index, (raw_line, source_span) in enumerate(
                zip(dialogue, spans), start=1
            ):
                line = deepcopy(dict(raw_line))
                if set(line) != {"speaker", "text", "emotion"}:
                    raise StaleInputError("Script dialogue contract is malformed")
                speaker = line.get("speaker")
                if not isinstance(speaker, str):
                    raise StaleInputError(
                        "dialogue speaker has no exact shot character"
                    )
                character_ref = character_by_name.get(speaker)
                if not isinstance(character_ref, str):
                    raise StaleInputError("dialogue speaker has no exact shot character")
                if character_ref not in voice_cache:
                    voice_cache[character_ref] = _voice_bundle(
                        self.voice_locks,
                        workspace_ref=workspace,
                        project_ref=root["projectRef"],
                        series_ref=root["seriesRef"],
                        character_ref=character_ref,
                    )
                bundle, version = voice_cache[character_ref]
                global_ordinal += 1
                requirement = self._requirement(
                    root=root,
                    graph=graph,
                    shot=shot,
                    line=line,
                    source_span=source_span,
                    dialogue_ordinal=dialogue_index,
                    global_ordinal=global_ordinal,
                    voice_version=version,
                )
                request = self._request(
                    root=root,
                    graph=graph,
                    shot=shot,
                    line=line,
                    source_span=source_span,
                    dialogue_ordinal=dialogue_index,
                    global_ordinal=global_ordinal,
                    requirement=requirement,
                    voice_bundle=bundle,
                    voice_version=version,
                )
                requirements.append(requirement)
                requests.append(request)
        return _sealed({
            "schemaVersion": "v5.k2-dialogue-audio-plan.v1",
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "rootPayloadDigest": root["payloadDigest"],
            "executableShotGraphVersionRef": graph[
                "executableShotGraphVersionRef"
            ],
            "executableShotGraphDigest": graph["payloadDigest"],
            "audioRequirements": requirements,
            "generationRequests": requests,
            "summary": {"dialogueRequests": len(requests)},
            "authorityState": "CONTRACT_ONLY_NOT_DURABLE",
            "dispatchAllowed": False,
            "publicationAllowed": False,
        })

def reject_speech_synthesis_in_legacy_media(
    requests: list[Mapping[str, Any]],
) -> None:
    """Fail closed before the legacy G5 runner can turn TTS into a sine wave."""

    for request in requests:
        parameters = request.get("parameters")
        if request.get("mediaKind") == "audio" and (
            not isinstance(parameters, Mapping)
            or parameters.get("speechSynthesis") is not False
        ):
            raise EpisodeProductionError(
                "speech synthesis audio cannot use legacy G5 media"
            )
