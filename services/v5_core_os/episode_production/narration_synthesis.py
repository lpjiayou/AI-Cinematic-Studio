"""Typed M12 narration bridge for the Piper-absent A-tier boundary.

This additive module projects an exact PR-3 ``NARRATION_SYNTHESIS`` request,
one confirmed narrator VoiceLock, and one existing ``LOCAL_PRESET``
``VoiceAssetVersion`` into the already-frozen V4 local-TTS request.  Production
records and typed assets require the mint-only V4 Piper execution capability;
that path cannot succeed while the A-tier runtime remains absent.

Deterministic fixed-WAV fixtures are retained behind explicitly named
``TEST_ONLY`` projection APIs.  Those projections carry no AssetVersion or
Admission authority and can never be passed to the production builders.

No Admission, publication, Timeline placement, voice cloning, planning, or
provider selection is performed here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from services.v4_platform.audio import (
    AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION,
    PIPER_TTS_ADAPTER_ID,
    PIPER_TTS_EXECUTION_EVIDENCE_SCHEMA_VERSION,
    PIPER_TTS_EXECUTION_STATE,
    TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
    PiperTtsExecutionEvidence,
)

from .audio import _validated_v4_audio_artifact_bundle
from .audio_authority import (
    AudioGenerationRequest,
    DialogueAssetVersion,
    VoiceAssetVersion,
    build_audio_provenance,
    build_dialogue_asset_version,
    validate_audio_generation_request,
    validate_voice_asset_version,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    _canonical_json,
    _digest,
    _required_ref,
)
from .voice import validate_confirmed_voice_lock_bundle


NARRATION_EXECUTION_CONTEXT_SCHEMA_VERSION = (
    "v5.narration-execution-context.v1"
)
NARRATION_GENERATION_RECORD_SCHEMA_VERSION = (
    "v5.narration-generation-record.v1"
)
NARRATION_SOURCE_DIGEST_SCHEMA_VERSION = "v5.narration-source-digest.v1"
NARRATION_ORIGIN_KIND = "LOCAL_DETERMINISTIC_EXECUTION"
NARRATION_BRIDGE_IDENTITY = "v5.typed-narration-synthesis-bridge.v1"
NARRATION_EXECUTION_STATE = "LOCAL_EXECUTION_REQUEST"
NARRATION_RECORD_STATE = "TECHNICAL_EVIDENCE_RECORDED"
NARRATION_TEST_EVIDENCE_PROJECTION_SCHEMA_VERSION = (
    "v5.narration-test-evidence-projection.v1"
)
NARRATION_TEST_DIALOGUE_PROJECTION_SCHEMA_VERSION = (
    "v5.narration-test-dialogue-projection.v1"
)
NARRATION_TEST_FIXTURE_MARKER = "TEST_FIXTURE_ONLY"
NARRATION_TEST_RUNTIME_IDENTITY = "TEST_ONLY_FIXED_WAV"
NARRATION_REQUIRED_RUNTIME_STATE = "PIPER_RUNTIME_ABSENT"
NARRATION_TEST_AUTHORITY_STATE = "TEST_ONLY_NO_AUTHORITY"
NARRATION_TEST_BRIDGE_IDENTITY = (
    "v5.test-only-fixed-wav-narration-bridge.v1"
)

_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_CONTEXT_FIELDS = frozenset(
    {
        "schemaVersion",
        *_SCOPE_FIELDS,
        "assetRequirementRef",
        "assetRequirementDigest",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptSceneRef",
        "sourceScriptSpan",
        "narrationOrdinal",
        "storageKey",
        "payloadDigest",
    }
)
_CONTEXT_COMMAND_FIELDS = _CONTEXT_FIELDS - {"schemaVersion", "payloadDigest"}
_V4_TTS_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
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
        "engine",
        "parameters",
        "state",
        "requestedProvenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_V4_ENGINE_FIELDS = frozenset(
    {
        "engineFamily",
        "voiceId",
        "languageCode",
        "basePitchSemitones",
        "baseRateScale",
    }
)
_REQUESTED_PROVENANCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "originKind",
        "adapterIdentity",
        "parametersDigest",
        "sourceRefs",
        "payloadDigest",
    }
)
_SOURCE_REF_FIELDS = frozenset({"sourceRef", "sourceDigest"})
_PIPER_EXECUTION_EVIDENCE_FIELDS = frozenset(
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
_RECORD_FIELDS = frozenset(
    {
        "schemaVersion",
        "generationRecordRef",
        *_SCOPE_FIELDS,
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "narrationRef",
        "narrationSourceDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "voiceAssetVersionRef",
        "voiceAssetVersionDigest",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "executionContextDigest",
        "executionRequestDigest",
        "executionEvidenceRef",
        "executionEvidenceDigest",
        "v4GenerationResultRef",
        "v4GenerationResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "pcmContentDigest",
        "sampleRate",
        "channels",
        "integratedLufs",
        "loudnessRangeLra",
        "truePeakDbtp",
        "validationState",
        "failureReasons",
        "clippingDetected",
        "analysisParametersDigest",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
        "adapterIdentity",
        "rightsBindingRef",
        "rightsBindingDigest",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)

_TEST_PROVENANCE_FIELDS = frozenset(
    {
        "originKind",
        "adapterIdentity",
        "runtimeState",
        "bridgeIdentity",
        "authorityState",
        "parametersDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
    }
)
_TEST_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "testEvidenceProjectionRef",
        *_SCOPE_FIELDS,
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "narrationRef",
        "narrationSourceDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "voiceAssetVersionRef",
        "voiceAssetVersionDigest",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "executionContextDigest",
        "executionRequestDigest",
        "v4GenerationResultRef",
        "v4GenerationResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "sampleRate",
        "channels",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
        "rightsBindingRef",
        "rightsBindingDigest",
        "provenance",
        "testFixtureOnly",
        "actualRuntimeIdentity",
        "requiredRuntimeState",
        "bridgeIdentity",
        "authorityState",
        "assetVersionAllowed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TEST_DIALOGUE_FIELDS = frozenset(
    {
        "schemaVersion",
        "dialogueProjectionRef",
        *_SCOPE_FIELDS,
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "testEvidenceProjectionRef",
        "testEvidenceProjectionDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "speechRole",
        "narrationRef",
        "dialogueRef",
        "voiceAssetVersionRef",
        "voiceAssetVersionDigest",
        "language",
        "normalizedSpeechParameters",
        "sourceAudioCueRefs",
        "rightsBindingRef",
        "rightsBindingDigest",
        "provenance",
        "createdBy",
        "createdAt",
        "testFixtureOnly",
        "actualRuntimeIdentity",
        "requiredRuntimeState",
        "bridgeIdentity",
        "authorityState",
        "assetVersionAllowed",
        "publicationAllowed",
        "payloadDigest",
    }
)


class NarrationSynthesisError(EpisodeProductionError):
    """A typed narration request or projection is invalid."""


class NarrationEvidenceBindingError(StaleInputError):
    """Narration execution evidence is stale or does not match its sources."""


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise NarrationSynthesisError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise NarrationSynthesisError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _exact(value, fields, label)
    claimed = result.pop("payloadDigest")
    if not _is_sha256(claimed) or claimed != _digest(result):
        raise NarrationEvidenceBindingError(f"{label} payloadDigest is invalid")
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
        raise NarrationSynthesisError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 2_000) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise NarrationSynthesisError(f"{field} is invalid")
    return value


def _positive_integer(value: Any, field: str, *, maximum: int = 10_000) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > maximum
    ):
        raise NarrationSynthesisError(f"{field} is invalid")
    return value


def _storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("asset-versions/audio/"):
        raise NarrationSynthesisError("storageKey is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "." in path.parts
        or ".." in path.parts
        or "//" in value
        or "\\" in value
        or "\x00" in value
        or value.endswith("/")
        or path.suffix.lower() != ".wav"
    ):
        raise NarrationSynthesisError("storageKey is invalid")
    return value


def _source_digest(request: Mapping[str, Any]) -> str:
    spec = request["requestSpec"]
    return _digest(
        {
            "schemaVersion": NARRATION_SOURCE_DIGEST_SCHEMA_VERSION,
            "scriptVersionRef": spec["scriptVersionRef"],
            "scriptVersionDigest": spec["scriptVersionDigest"],
            "narrationRef": spec["narrationRef"],
            "text": spec["normalizedSpeechParameters"]["text"],
        }
    )


def _record_ref(value: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(value))
    semantic.pop("generationRecordRef", None)
    semantic.pop("payloadDigest", None)
    return "narration-generation-record-" + _digest(semantic)[:32]


def _validate_context(value: Any) -> dict[str, Any]:
    context = _verify_sealed(value, _CONTEXT_FIELDS, "NarrationExecutionContext")
    if context["schemaVersion"] != NARRATION_EXECUTION_CONTEXT_SCHEMA_VERSION:
        raise NarrationSynthesisError("NarrationExecutionContext schema is unsupported")
    for field in (
        *_SCOPE_FIELDS,
        "assetRequirementRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptSceneRef",
    ):
        _required_ref(context[field], field)
    context["sourceScriptSpan"] = _text(
        context["sourceScriptSpan"], "sourceScriptSpan"
    )
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
    ):
        _sha256(context[field], field)
    _positive_integer(context["narrationOrdinal"], "narrationOrdinal")
    context["storageKey"] = _storage_key(context["storageKey"])
    return context


@dataclass(frozen=True, slots=True, init=False)
class NarrationExecutionContext:
    """Exact V5 supplement for lineage absent from the PR-3 speech request."""

    _payload_json: str

    @classmethod
    def from_mapping(cls, value: Any) -> "NarrationExecutionContext":
        normalized = _validate_context(value)
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_narration_execution_context(
    command: Mapping[str, Any],
) -> NarrationExecutionContext:
    value = _exact(
        command, _CONTEXT_COMMAND_FIELDS, "NarrationExecutionContext command"
    )
    return NarrationExecutionContext.from_mapping(
        _seal(
            {
                "schemaVersion": NARRATION_EXECUTION_CONTEXT_SCHEMA_VERSION,
                **value,
            }
        )
    )


def validate_narration_execution_context(value: Any) -> NarrationExecutionContext:
    if type(value) is NarrationExecutionContext:
        value = value.as_dict()
    return NarrationExecutionContext.from_mapping(value)


def _exact_request(
    value: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
) -> dict[str, Any]:
    if type(value) is not AudioGenerationRequest:
        raise NarrationSynthesisError("exact AudioGenerationRequest wrapper is required")
    if type(voice_asset_version) is not VoiceAssetVersion:
        raise NarrationSynthesisError("exact VoiceAssetVersion wrapper is required")
    voice_asset = validate_voice_asset_version(
        voice_asset_version.as_dict(),
        confirmed_voice_lock=confirmed_voice_lock,
    ).as_dict()
    request = validate_audio_generation_request(
        value.as_dict(),
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset,
    ).as_dict()
    spec = request["requestSpec"]
    if (
        request["requestKind"] != "NARRATION_SYNTHESIS"
        or request["outputAssetVersionType"] != "DialogueAssetVersion"
        or request["outputTarget"] != "ASSET_VERSION"
        or spec["speechRole"] != "narration"
        or spec["dialogueRef"] is not None
        or spec["sourceAudioCueRefs"] != []
        or spec["normalizedSpeechParameters"]["audioRole"] != "narration"
        or voice_asset["voiceSourceKind"] != "LOCAL_PRESET"
        or voice_asset["consentGrantRef"] is not None
        or voice_asset["consentGrantVersionRef"] is not None
        or voice_asset["consentGrantDigest"] is not None
    ):
        raise NarrationSynthesisError("typed narration source semantics are invalid")
    provenance = request["requestedProvenance"]
    if set(provenance) != _REQUESTED_PROVENANCE_FIELDS:
        raise NarrationSynthesisError("requested narration provenance fields are invalid")
    expected_parameters_digest = _digest(spec["normalizedSpeechParameters"])
    if (
        provenance["originKind"] != NARRATION_ORIGIN_KIND
        or provenance["adapterIdentity"] != PIPER_TTS_ADAPTER_ID
        or provenance["parametersDigest"] != expected_parameters_digest
    ):
        raise NarrationSynthesisError("requested narration provenance is stale")
    covered = False
    for index, source in enumerate(provenance["sourceRefs"]):
        if not isinstance(source, Mapping) or set(source) != _SOURCE_REF_FIELDS:
            raise NarrationSynthesisError(
                f"requestedProvenance.sourceRefs[{index}] is invalid"
            )
        covered = covered or (
            source["sourceRef"] == request["assetRequirementRef"]
            and source["sourceDigest"] == request["assetRequirementDigest"]
        )
    if not covered:
        raise NarrationSynthesisError(
            "requested narration provenance does not cover the AssetRequirement"
        )
    return request


def _exact_voice(
    voice_asset_version: VoiceAssetVersion,
    confirmed_voice_lock: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if type(voice_asset_version) is not VoiceAssetVersion:
        raise NarrationSynthesisError("exact VoiceAssetVersion wrapper is required")
    bundle = validate_confirmed_voice_lock_bundle(confirmed_voice_lock)
    asset = validate_voice_asset_version(
        voice_asset_version.as_dict(), confirmed_voice_lock=bundle
    ).as_dict()
    root = bundle["voiceLock"]
    version = bundle["voiceLockVersion"]
    if (
        asset["voiceSourceKind"] != "LOCAL_PRESET"
        or asset["voiceSourceSubjectRef"] != root["characterRef"]
        or asset["characterRef"] != root["characterRef"]
        or asset["voiceIdentityRef"] != root["voiceRef"]
        or asset["voiceLockVersionRef"] != version["voiceLockVersionRef"]
        or asset["voiceLockDigest"] != version["payloadDigest"]
    ):
        raise NarrationSynthesisError("narrator VoiceAssetVersion binding is invalid")
    return bundle, asset


def _exact_context(value: NarrationExecutionContext) -> dict[str, Any]:
    if type(value) is not NarrationExecutionContext:
        raise NarrationSynthesisError("exact NarrationExecutionContext wrapper is required")
    return _validate_context(value.as_dict())


def _bind_sources(
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    voice_asset: Mapping[str, Any],
) -> None:
    if any(request[field] != context[field] for field in _SCOPE_FIELDS):
        raise NarrationEvidenceBindingError("narration execution scope is stale")
    if (
        request["assetRequirementRef"] != context["assetRequirementRef"]
        or request["assetRequirementDigest"] != context["assetRequirementDigest"]
    ):
        raise NarrationEvidenceBindingError("narration execution lineage is stale")
    # Voice profiles are reusable series-scoped identities; their originating
    # episode/run need not equal the narration execution episode/run.
    if tuple(request[field] for field in ("workspaceRef", "projectRef", "seriesRef")) != tuple(
        voice_asset[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    ):
        raise NarrationEvidenceBindingError("narrator VoiceAssetVersion scope is stale")


def _validate_v4_tts_request(
    value: Any,
    *,
    request: Mapping[str, Any],
    context: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    execution = _verify_sealed(value, _V4_TTS_REQUEST_FIELDS, "V4 TTS request")
    root = bundle["voiceLock"]
    version = bundle["voiceLockVersion"]
    spec = request["requestSpec"]
    if (
        execution["schemaVersion"] != TTS_EXECUTION_REQUEST_SCHEMA_VERSION
        or execution["workspaceRef"] != request["workspaceRef"]
        or execution["productionRunRef"] != request["productionRunRef"]
        or execution["generationRequestRef"] != request["generationRequestRef"]
        or execution["generationRequestVersionRef"]
        != request["generationRequestVersionRef"]
        or execution["generationRequestDigest"] != request["payloadDigest"]
        or execution["assetRequirementRef"] != request["assetRequirementRef"]
        or execution["assetRequirementDigest"] != request["assetRequirementDigest"]
        or execution["creativeShotRef"] != context["creativeShotRef"]
        or execution["creativeShotVersionRef"]
        != context["creativeShotVersionRef"]
        or execution["creativeShotDigest"] != context["creativeShotDigest"]
        or execution["scriptRef"] != context["scriptRef"]
        or execution["scriptVersionRef"] != spec["scriptVersionRef"]
        or execution["scriptVersionDigest"] != spec["scriptVersionDigest"]
        or execution["scriptSceneRef"] != context["scriptSceneRef"]
        or execution["sourceScriptSpan"] != context["sourceScriptSpan"]
        or execution["dialogueOrdinal"] != context["narrationOrdinal"]
        or execution["dialogueSourceDigest"] != _source_digest(request)
        or execution["characterRef"] != root["characterRef"]
        or execution["voiceRef"] != root["voiceRef"]
        or execution["voiceLockVersionRef"] != version["voiceLockVersionRef"]
        or execution["voiceLockDigest"] != version["payloadDigest"]
        or execution["mediaKind"] != "audio"
        or execution["mediaType"] != "audio/wav"
        or execution["adapterCapability"] != PIPER_TTS_ADAPTER_ID
        or execution["parameters"] != spec["normalizedSpeechParameters"]
        or execution["state"] != NARRATION_EXECUTION_STATE
        or execution["requestedProvenance"] != "LOCAL_EVIDENCE"
        or execution["publicationAllowed"] is not False
    ):
        raise NarrationEvidenceBindingError("V4 narration TTS request is stale")
    engine = execution["engine"]
    if not isinstance(engine, Mapping) or set(engine) != _V4_ENGINE_FIELDS:
        raise NarrationSynthesisError("V4 narration engine fields are invalid")
    expected_engine = {
        "engineFamily": version["engineFamily"],
        "voiceId": version["voiceId"],
        "languageCode": version["languageCode"],
        "basePitchSemitones": version["pitchSemitones"],
        "baseRateScale": version["rateScale"],
    }
    if dict(engine) != expected_engine:
        raise NarrationEvidenceBindingError("V4 narration engine binding is stale")
    return execution


def build_narration_tts_execution_request(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
) -> dict[str, Any]:
    """Project exact typed narration sources into the frozen V4 TTS request."""

    bundle, voice_asset = _exact_voice(voice_asset_version, confirmed_voice_lock)
    request = _exact_request(
        generation_request,
        confirmed_voice_lock=bundle,
        voice_asset_version=voice_asset_version,
    )
    context = _exact_context(execution_context)
    _bind_sources(request, context, voice_asset)
    root = bundle["voiceLock"]
    version = bundle["voiceLockVersion"]
    spec = request["requestSpec"]
    execution = _seal(
        {
            "schemaVersion": TTS_EXECUTION_REQUEST_SCHEMA_VERSION,
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "generationRequestRef": request["generationRequestRef"],
            "generationRequestVersionRef": request["generationRequestVersionRef"],
            "generationRequestDigest": request["payloadDigest"],
            "assetRequirementRef": request["assetRequirementRef"],
            "assetRequirementDigest": request["assetRequirementDigest"],
            "creativeShotRef": context["creativeShotRef"],
            "creativeShotVersionRef": context["creativeShotVersionRef"],
            "creativeShotDigest": context["creativeShotDigest"],
            "scriptRef": context["scriptRef"],
            "scriptVersionRef": spec["scriptVersionRef"],
            "scriptVersionDigest": spec["scriptVersionDigest"],
            "scriptSceneRef": context["scriptSceneRef"],
            "sourceScriptSpan": context["sourceScriptSpan"],
            "dialogueOrdinal": context["narrationOrdinal"],
            "dialogueSourceDigest": _source_digest(request),
            "characterRef": root["characterRef"],
            "voiceRef": root["voiceRef"],
            "voiceLockVersionRef": version["voiceLockVersionRef"],
            "voiceLockDigest": version["payloadDigest"],
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "adapterCapability": PIPER_TTS_ADAPTER_ID,
            "engine": {
                "engineFamily": version["engineFamily"],
                "voiceId": version["voiceId"],
                "languageCode": version["languageCode"],
                "basePitchSemitones": version["pitchSemitones"],
                "baseRateScale": version["rateScale"],
            },
            "parameters": deepcopy(spec["normalizedSpeechParameters"]),
            "state": NARRATION_EXECUTION_STATE,
            "requestedProvenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )
    return _validate_v4_tts_request(
        execution, request=request, context=context, bundle=bundle
    )


def _derived_generation_record(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    execution_evidence: PiperTtsExecutionEvidence,
) -> dict[str, Any]:
    voice_bundle, voice_asset = _exact_voice(
        voice_asset_version, confirmed_voice_lock
    )
    request = _exact_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
    )
    context = _exact_context(execution_context)
    _bind_sources(request, context, voice_asset)
    expected_execution = build_narration_tts_execution_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
    )
    execution = _validate_v4_tts_request(
        execution_request,
        request=request,
        context=context,
        bundle=voice_bundle,
    )
    if execution != expected_execution:
        raise NarrationEvidenceBindingError(
            "V4 narration execution request is not the exact typed projection"
        )
    if type(execution_evidence) is not PiperTtsExecutionEvidence:
        raise NarrationSynthesisError(
            "exact mint-only PiperTtsExecutionEvidence is required"
        )
    piper_evidence = _verify_sealed(
        execution_evidence.as_dict(),
        _PIPER_EXECUTION_EVIDENCE_FIELDS,
        "PiperTtsExecutionEvidence",
    )
    artifact_bundle = piper_evidence["artifactResult"]
    analysis = piper_evidence["technicalAnalysisEvidence"]
    if not isinstance(analysis, Mapping):
        raise NarrationEvidenceBindingError(
            "Piper technical analysis evidence is invalid"
        )
    analysis = deepcopy(dict(analysis))
    analysis_digest = analysis.pop("payloadDigest", None)
    if not _is_sha256(analysis_digest) or analysis_digest != _digest(analysis):
        raise NarrationEvidenceBindingError(
            "Piper technical analysis payloadDigest is invalid"
        )
    analysis["payloadDigest"] = analysis_digest
    try:
        bundle, result, evidence = _validated_v4_audio_artifact_bundle(
            artifact_bundle,
            execution_request=execution,
            generation_request_digest=request["payloadDigest"],
            adapter_identity=PIPER_TTS_ADAPTER_ID,
            audio_role="narration",
        )
    except EpisodeProductionError:
        raise
    except Exception as exc:
        raise NarrationEvidenceBindingError(
            "V4 narration artifact bundle is invalid"
        ) from exc
    if (
        piper_evidence["schemaVersion"]
        != PIPER_TTS_EXECUTION_EVIDENCE_SCHEMA_VERSION
        or piper_evidence["generationRequestDigest"] != request["payloadDigest"]
        or piper_evidence["executionRequestDigest"] != execution["payloadDigest"]
        or piper_evidence["adapterIdentity"] != PIPER_TTS_ADAPTER_ID
        or piper_evidence["audioRole"] != "narration"
        or piper_evidence["state"] != PIPER_TTS_EXECUTION_STATE
        or piper_evidence["publicationAllowed"] is not False
        or piper_evidence["artifactResultDigest"] != bundle["payloadDigest"]
        or piper_evidence["generationResultRef"]
        != result["generationResultRef"]
        or piper_evidence["generationResultDigest"] != result["payloadDigest"]
        or piper_evidence["artifactEvidenceRef"]
        != evidence["artifactEvidenceRef"]
        or piper_evidence["artifactEvidenceDigest"] != evidence["payloadDigest"]
        or piper_evidence["analysisEvidenceRef"]
        != analysis.get("analysisEvidenceRef")
        or piper_evidence["analysisEvidenceDigest"] != analysis["payloadDigest"]
        or bundle["schemaVersion"] != AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION
        or evidence["storageKey"] != context["storageKey"]
        or bundle["storageKey"] != context["storageKey"]
        or evidence["sha256"] != result["sha256"]
        or evidence["sha256"] != bundle["sha256"]
        or evidence["byteSize"] != result["byteSize"]
        or evidence["byteSize"] != bundle["byteSize"]
        or evidence["parametersDigest"]
        != request["requestedProvenance"]["parametersDigest"]
        or analysis.get("sourceArtifactEvidenceRef")
        != evidence["artifactEvidenceRef"]
        or analysis.get("sourceArtifactEvidenceDigest")
        != evidence["payloadDigest"]
        or analysis.get("artifactRef") != evidence["artifactRef"]
        or analysis.get("storageKey") != evidence["storageKey"]
        or analysis.get("byteSize") != evidence["byteSize"]
        or analysis.get("fileDigest") != evidence["sha256"]
        or analysis.get("validationState") != "PASSED"
        or analysis.get("failureReasons") != []
        or analysis.get("clippingDetected") is not False
        or analysis.get("state") != "TECHNICAL_ANALYSIS_COMPLETE"
        or analysis.get("publicationAllowed") is not False
    ):
        raise NarrationEvidenceBindingError(
            "V4 narration artifact or file digest binding is stale"
        )
    for field in (
        "sha256",
        "payloadDigest",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
    ):
        _sha256(evidence[field], f"artifactEvidence.{field}")
    rights = request["rightsBinding"]
    semantic: dict[str, Any] = {
        "schemaVersion": NARRATION_GENERATION_RECORD_SCHEMA_VERSION,
        **{field: request[field] for field in _SCOPE_FIELDS},
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "narrationRef": request["requestSpec"]["narrationRef"],
        "narrationSourceDigest": _source_digest(request),
        "scriptVersionRef": request["requestSpec"]["scriptVersionRef"],
        "scriptVersionDigest": request["requestSpec"]["scriptVersionDigest"],
        "voiceAssetVersionRef": voice_asset["assetVersionRef"],
        "voiceAssetVersionDigest": voice_asset["payloadDigest"],
        "voiceLockVersionRef": voice_bundle["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockDigest": voice_bundle["voiceLockVersion"]["payloadDigest"],
        "executionContextDigest": context["payloadDigest"],
        "executionRequestDigest": execution["payloadDigest"],
        "executionEvidenceRef": piper_evidence["executionEvidenceRef"],
        "executionEvidenceDigest": piper_evidence["payloadDigest"],
        "v4GenerationResultRef": result["generationResultRef"],
        "v4GenerationResultDigest": result["payloadDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
        "analysisEvidenceRef": analysis["analysisEvidenceRef"],
        "analysisEvidenceDigest": analysis["payloadDigest"],
        "artifactRef": evidence["artifactRef"],
        "storageKey": evidence["storageKey"],
        "byteSize": evidence["byteSize"],
        "fileDigest": evidence["sha256"],
        "pcmContentDigest": analysis["pcmContentDigest"],
        "sampleRate": evidence["sampleRate"],
        "channels": evidence["channels"],
        "integratedLufs": analysis["integratedLufs"],
        "loudnessRangeLra": analysis["loudnessRangeLra"],
        "truePeakDbtp": analysis["truePeakDbtp"],
        "validationState": analysis["validationState"],
        "failureReasons": deepcopy(analysis["failureReasons"]),
        "clippingDetected": analysis["clippingDetected"],
        "analysisParametersDigest": analysis["analysisParametersDigest"],
        "parametersDigest": evidence["parametersDigest"],
        "effectiveParametersDigest": evidence["effectiveParametersDigest"],
        "synthesisSpecDigest": evidence["synthesisSpecDigest"],
        "adapterIdentity": evidence["adapterIdentity"],
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "state": NARRATION_RECORD_STATE,
        "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        "immutable": True,
        "publicationAllowed": False,
    }
    semantic["generationRecordRef"] = _record_ref(semantic)
    return _seal(semantic)


def _validate_record(
    value: Any,
    *,
    generation_request: AudioGenerationRequest,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    execution_evidence: PiperTtsExecutionEvidence,
) -> dict[str, Any]:
    record = _verify_sealed(
        value, _RECORD_FIELDS, "NarrationGenerationRecord"
    )
    expected = _derived_generation_record(
        generation_request,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )
    if record != expected:
        raise NarrationEvidenceBindingError(
            "NarrationGenerationRecord binding is stale"
        )
    return record


@dataclass(frozen=True, slots=True, init=False)
class NarrationGenerationRecord:
    """Immutable V5 technical record derived from exact A-tier TTS evidence."""

    _payload_json: str

    @classmethod
    def _from_derived(
        cls, value: Mapping[str, Any]
    ) -> "NarrationGenerationRecord":
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(value))
        return instance

    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        generation_request: AudioGenerationRequest,
        confirmed_voice_lock: Mapping[str, Any],
        voice_asset_version: VoiceAssetVersion,
        execution_context: NarrationExecutionContext,
        execution_request: Mapping[str, Any],
        execution_evidence: PiperTtsExecutionEvidence,
    ) -> "NarrationGenerationRecord":
        normalized = _validate_record(
            value,
            generation_request=generation_request,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_asset_version=voice_asset_version,
            execution_context=execution_context,
            execution_request=execution_request,
            execution_evidence=execution_evidence,
        )
        return cls._from_derived(normalized)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_narration_generation_record(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    execution_evidence: PiperTtsExecutionEvidence,
) -> NarrationGenerationRecord:
    return NarrationGenerationRecord._from_derived(
        _derived_generation_record(
            generation_request,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_asset_version=voice_asset_version,
            execution_context=execution_context,
            execution_request=execution_request,
            execution_evidence=execution_evidence,
        )
    )


def validate_narration_generation_record(
    value: Any,
    *,
    generation_request: AudioGenerationRequest,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    execution_evidence: PiperTtsExecutionEvidence,
) -> NarrationGenerationRecord:
    if type(value) is NarrationGenerationRecord:
        value = value.as_dict()
    return NarrationGenerationRecord.from_mapping(
        value,
        generation_request=generation_request,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )


def _test_projection_ref(value: Mapping[str, Any], *, prefix: str) -> str:
    semantic = deepcopy(dict(value))
    semantic.pop("testEvidenceProjectionRef", None)
    semantic.pop("dialogueProjectionRef", None)
    semantic.pop("payloadDigest", None)
    return prefix + _digest(semantic)[:32]


def _test_provenance(evidence: Mapping[str, Any]) -> dict[str, Any]:
    provenance = {
        "originKind": NARRATION_TEST_FIXTURE_MARKER,
        "adapterIdentity": NARRATION_TEST_RUNTIME_IDENTITY,
        "runtimeState": NARRATION_REQUIRED_RUNTIME_STATE,
        "bridgeIdentity": NARRATION_TEST_BRIDGE_IDENTITY,
        "authorityState": NARRATION_TEST_AUTHORITY_STATE,
        "parametersDigest": evidence["effectiveParametersDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
    }
    if set(provenance) != _TEST_PROVENANCE_FIELDS:
        raise NarrationSynthesisError("test-only narration provenance is invalid")
    return provenance


def _derived_test_evidence_projection(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    test_only_fixed_wav_artifact_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Project untrusted fixture bytes without creating production authority."""

    voice_bundle, voice_asset = _exact_voice(
        voice_asset_version, confirmed_voice_lock
    )
    request = _exact_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
    )
    context = _exact_context(execution_context)
    _bind_sources(request, context, voice_asset)
    expected_execution = build_narration_tts_execution_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
    )
    execution = _validate_v4_tts_request(
        execution_request,
        request=request,
        context=context,
        bundle=voice_bundle,
    )
    if execution != expected_execution:
        raise NarrationEvidenceBindingError(
            "test-only V4 narration request is not the exact typed projection"
        )
    try:
        bundle, result, evidence = _validated_v4_audio_artifact_bundle(
            test_only_fixed_wav_artifact_bundle,
            execution_request=execution,
            generation_request_digest=request["payloadDigest"],
            adapter_identity=PIPER_TTS_ADAPTER_ID,
            audio_role="narration",
        )
    except EpisodeProductionError:
        raise
    except Exception as exc:
        raise NarrationEvidenceBindingError(
            "test-only fixed-WAV artifact bundle is invalid"
        ) from exc
    if (
        bundle["schemaVersion"] != AUDIO_ARTIFACT_RESULT_SCHEMA_VERSION
        or evidence["storageKey"] != context["storageKey"]
        or bundle["storageKey"] != context["storageKey"]
        or evidence["sha256"] != result["sha256"]
        or evidence["sha256"] != bundle["sha256"]
        or evidence["byteSize"] != result["byteSize"]
        or evidence["byteSize"] != bundle["byteSize"]
        or evidence["parametersDigest"]
        != request["requestedProvenance"]["parametersDigest"]
    ):
        raise NarrationEvidenceBindingError(
            "test-only narration artifact binding is stale"
        )
    rights = request["rightsBinding"]
    semantic: dict[str, Any] = {
        "schemaVersion": NARRATION_TEST_EVIDENCE_PROJECTION_SCHEMA_VERSION,
        **{field: request[field] for field in _SCOPE_FIELDS},
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "narrationRef": request["requestSpec"]["narrationRef"],
        "narrationSourceDigest": _source_digest(request),
        "scriptVersionRef": request["requestSpec"]["scriptVersionRef"],
        "scriptVersionDigest": request["requestSpec"]["scriptVersionDigest"],
        "voiceAssetVersionRef": voice_asset["assetVersionRef"],
        "voiceAssetVersionDigest": voice_asset["payloadDigest"],
        "voiceLockVersionRef": voice_bundle["voiceLockVersion"][
            "voiceLockVersionRef"
        ],
        "voiceLockDigest": voice_bundle["voiceLockVersion"]["payloadDigest"],
        "executionContextDigest": context["payloadDigest"],
        "executionRequestDigest": execution["payloadDigest"],
        "v4GenerationResultRef": result["generationResultRef"],
        "v4GenerationResultDigest": result["payloadDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["payloadDigest"],
        "artifactRef": evidence["artifactRef"],
        "storageKey": evidence["storageKey"],
        "byteSize": evidence["byteSize"],
        "fileDigest": evidence["sha256"],
        "sampleRate": evidence["sampleRate"],
        "channels": evidence["channels"],
        "parametersDigest": evidence["parametersDigest"],
        "effectiveParametersDigest": evidence["effectiveParametersDigest"],
        "synthesisSpecDigest": evidence["synthesisSpecDigest"],
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "provenance": _test_provenance(evidence),
        "testFixtureOnly": NARRATION_TEST_FIXTURE_MARKER,
        "actualRuntimeIdentity": NARRATION_TEST_RUNTIME_IDENTITY,
        "requiredRuntimeState": NARRATION_REQUIRED_RUNTIME_STATE,
        "bridgeIdentity": NARRATION_TEST_BRIDGE_IDENTITY,
        "authorityState": NARRATION_TEST_AUTHORITY_STATE,
        "assetVersionAllowed": False,
        "publicationAllowed": False,
    }
    semantic["testEvidenceProjectionRef"] = _test_projection_ref(
        semantic, prefix="narration-test-evidence-"
    )
    return _seal(semantic)


@dataclass(frozen=True, slots=True, init=False)
class NarrationTestEvidenceProjection:
    """Immutable test-fixture projection with explicitly zero authority."""

    _payload_json: str

    @classmethod
    def _from_derived(
        cls, value: Mapping[str, Any]
    ) -> "NarrationTestEvidenceProjection":
        normalized = _verify_sealed(
            value, _TEST_EVIDENCE_FIELDS, "NarrationTestEvidenceProjection"
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_test_only_narration_evidence_projection(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    test_only_fixed_wav_artifact_bundle: Mapping[str, Any],
) -> NarrationTestEvidenceProjection:
    return NarrationTestEvidenceProjection._from_derived(
        _derived_test_evidence_projection(
            generation_request,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_asset_version=voice_asset_version,
            execution_context=execution_context,
            execution_request=execution_request,
            test_only_fixed_wav_artifact_bundle=(
                test_only_fixed_wav_artifact_bundle
            ),
        )
    )


@dataclass(frozen=True, slots=True, init=False)
class NarrationTestDialogueProjection:
    """Non-AssetVersion narration projection for deterministic fixtures only."""

    _payload_json: str

    @classmethod
    def _from_derived(
        cls, value: Mapping[str, Any]
    ) -> "NarrationTestDialogueProjection":
        normalized = _verify_sealed(
            value, _TEST_DIALOGUE_FIELDS, "NarrationTestDialogueProjection"
        )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_test_only_narration_dialogue_projection(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    test_only_fixed_wav_artifact_bundle: Mapping[str, Any],
    test_evidence_projection: NarrationTestEvidenceProjection,
    created_at: str,
) -> NarrationTestDialogueProjection:
    if type(test_evidence_projection) is not NarrationTestEvidenceProjection:
        raise NarrationSynthesisError(
            "exact NarrationTestEvidenceProjection wrapper is required"
        )
    expected = _derived_test_evidence_projection(
        generation_request,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
        execution_request=execution_request,
        test_only_fixed_wav_artifact_bundle=(
            test_only_fixed_wav_artifact_bundle
        ),
    )
    evidence = _verify_sealed(
        test_evidence_projection.as_dict(),
        _TEST_EVIDENCE_FIELDS,
        "NarrationTestEvidenceProjection",
    )
    if evidence != expected:
        raise NarrationEvidenceBindingError(
            "test-only narration evidence projection is stale"
        )
    voice_bundle, voice_asset = _exact_voice(
        voice_asset_version, confirmed_voice_lock
    )
    request = _exact_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
    )
    _bind_sources(request, _exact_context(execution_context), voice_asset)
    normalized_created_at = _text(created_at, "createdAt", maximum=64)
    spec = request["requestSpec"]
    semantic: dict[str, Any] = {
        "schemaVersion": NARRATION_TEST_DIALOGUE_PROJECTION_SCHEMA_VERSION,
        **{field: request[field] for field in _SCOPE_FIELDS},
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "testEvidenceProjectionRef": evidence["testEvidenceProjectionRef"],
        "testEvidenceProjectionDigest": evidence["payloadDigest"],
        "artifactEvidenceRef": evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": evidence["artifactEvidenceDigest"],
        "artifactRef": evidence["artifactRef"],
        "storageKey": evidence["storageKey"],
        "byteSize": evidence["byteSize"],
        "fileDigest": evidence["fileDigest"],
        "speechRole": "narration",
        "narrationRef": spec["narrationRef"],
        "dialogueRef": None,
        "voiceAssetVersionRef": voice_asset["assetVersionRef"],
        "voiceAssetVersionDigest": voice_asset["payloadDigest"],
        "language": spec["language"],
        "normalizedSpeechParameters": deepcopy(
            spec["normalizedSpeechParameters"]
        ),
        "sourceAudioCueRefs": [],
        "rightsBindingRef": evidence["rightsBindingRef"],
        "rightsBindingDigest": evidence["rightsBindingDigest"],
        "provenance": deepcopy(evidence["provenance"]),
        "createdBy": NARRATION_TEST_BRIDGE_IDENTITY,
        "createdAt": normalized_created_at,
        "testFixtureOnly": NARRATION_TEST_FIXTURE_MARKER,
        "actualRuntimeIdentity": NARRATION_TEST_RUNTIME_IDENTITY,
        "requiredRuntimeState": NARRATION_REQUIRED_RUNTIME_STATE,
        "bridgeIdentity": NARRATION_TEST_BRIDGE_IDENTITY,
        "authorityState": NARRATION_TEST_AUTHORITY_STATE,
        "assetVersionAllowed": False,
        "publicationAllowed": False,
    }
    semantic["dialogueProjectionRef"] = _test_projection_ref(
        semantic, prefix="narration-test-dialogue-"
    )
    return NarrationTestDialogueProjection._from_derived(_seal(semantic))


def _asset_refs(
    request: Mapping[str, Any], record: Mapping[str, Any], *, created_at: str
) -> tuple[str, str]:
    asset_semantic = {
        "schemaVersion": "v5.narration-asset-identity.v1",
        **{field: request[field] for field in _SCOPE_FIELDS},
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "narrationRef": record["narrationRef"],
        "voiceAssetVersionRef": record["voiceAssetVersionRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "generationRecordRef": record["generationRecordRef"],
        "generationRecordDigest": record["payloadDigest"],
        "createdAt": created_at,
    }
    asset_ref = "m12-narration-asset-" + _digest(asset_semantic)[:32]
    version_semantic = {
        "schemaVersion": "v5.narration-asset-version-identity.v1",
        "assetRef": asset_ref,
        "generationRequestDigest": request["payloadDigest"],
        "generationRecordDigest": record["payloadDigest"],
        "artifactEvidenceDigest": record["artifactEvidenceDigest"],
    }
    asset_version_ref = (
        "m12-narration-asset-version-" + _digest(version_semantic)[:32]
    )
    return asset_ref, asset_version_ref


def build_narration_dialogue_asset_version(
    generation_request: AudioGenerationRequest,
    *,
    confirmed_voice_lock: Mapping[str, Any],
    voice_asset_version: VoiceAssetVersion,
    execution_context: NarrationExecutionContext,
    execution_request: Mapping[str, Any],
    execution_evidence: PiperTtsExecutionEvidence,
    generation_record: NarrationGenerationRecord,
    created_at: str,
) -> DialogueAssetVersion:
    """Propose the existing typed narration asset without Admission authority."""

    if type(generation_record) is not NarrationGenerationRecord:
        raise NarrationSynthesisError(
            "exact NarrationGenerationRecord wrapper is required"
        )
    voice_bundle, voice_asset = _exact_voice(
        voice_asset_version, confirmed_voice_lock
    )
    request = _exact_request(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
    )
    context = _exact_context(execution_context)
    normalized_created_at = _text(created_at, "createdAt", maximum=64)
    expected_record = _derived_generation_record(
        generation_request,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset_version,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )
    record = generation_record.as_dict()
    if record != expected_record:
        raise NarrationEvidenceBindingError(
            "generation record is not the exact narration evidence projection"
        )
    if (
        record["storageKey"] != context["storageKey"]
        or record["rightsBindingRef"]
        != request["rightsBinding"]["rightsBindingRef"]
        or record["rightsBindingDigest"] != request["rightsBinding"]["payloadDigest"]
    ):
        raise NarrationEvidenceBindingError("narration record authority binding is stale")
    asset_ref, asset_version_ref = _asset_refs(
        request, record, created_at=normalized_created_at
    )
    provenance = build_audio_provenance(
        {
            "originKind": NARRATION_ORIGIN_KIND,
            "adapterIdentity": PIPER_TTS_ADAPTER_ID,
            "generationRecordRef": record["generationRecordRef"],
            "parametersDigest": record["effectiveParametersDigest"],
            "artifactEvidenceRef": record["artifactEvidenceRef"],
            "artifactEvidenceDigest": record["artifactEvidenceDigest"],
            "sourceRefs": [
                {
                    "sourceRef": request["generationRequestVersionRef"],
                    "sourceDigest": request["payloadDigest"],
                },
                {
                    "sourceRef": record["executionEvidenceRef"],
                    "sourceDigest": record["executionEvidenceDigest"],
                },
                {
                    "sourceRef": record["v4GenerationResultRef"],
                    "sourceDigest": record["v4GenerationResultDigest"],
                },
                {
                    "sourceRef": record["generationRecordRef"],
                    "sourceDigest": record["payloadDigest"],
                },
            ],
        }
    )
    spec = request["requestSpec"]
    command = {
        **{field: request[field] for field in _SCOPE_FIELDS},
        "assetRef": asset_ref,
        "assetVersionRef": asset_version_ref,
        "version": 1,
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "generationResultRef": record["generationRecordRef"],
        "generationResultDigest": record["payloadDigest"],
        "artifact": {
            "artifactKind": "PCM_AUDIO",
            "artifactEvidenceRef": record["artifactEvidenceRef"],
            "artifactEvidenceDigest": record["artifactEvidenceDigest"],
            "artifactRef": record["artifactRef"],
            "storageKey": record["storageKey"],
            "byteSize": record["byteSize"],
            "fileDigest": record["fileDigest"],
            "mediaType": "audio/wav",
        },
        "supersedesAssetVersionRef": None,
        "supersedesAssetVersionDigest": None,
        "provenance": provenance,
        "rightsBinding": deepcopy(request["rightsBinding"]),
        "createdBy": NARRATION_BRIDGE_IDENTITY,
        "createdAt": normalized_created_at,
        "speechRole": "narration",
        "scriptVersionRef": spec["scriptVersionRef"],
        "scriptVersionDigest": spec["scriptVersionDigest"],
        "dialogueRef": None,
        "narrationRef": spec["narrationRef"],
        "voiceAssetVersionRef": voice_asset["assetVersionRef"],
        "voiceAssetVersionDigest": voice_asset["payloadDigest"],
        "language": spec["language"],
        "normalizedSpeechParameters": deepcopy(
            spec["normalizedSpeechParameters"]
        ),
        "sourceAudioCueRefs": [],
    }
    built = build_dialogue_asset_version(
        command,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset,
    )
    return DialogueAssetVersion.from_mapping(
        built,
        confirmed_voice_lock=voice_bundle,
        voice_asset_version=voice_asset,
    )


__all__ = [
    "NARRATION_EXECUTION_CONTEXT_SCHEMA_VERSION",
    "NARRATION_GENERATION_RECORD_SCHEMA_VERSION",
    "NARRATION_SOURCE_DIGEST_SCHEMA_VERSION",
    "NARRATION_ORIGIN_KIND",
    "NARRATION_BRIDGE_IDENTITY",
    "NARRATION_TEST_EVIDENCE_PROJECTION_SCHEMA_VERSION",
    "NARRATION_TEST_DIALOGUE_PROJECTION_SCHEMA_VERSION",
    "NARRATION_TEST_FIXTURE_MARKER",
    "NARRATION_TEST_RUNTIME_IDENTITY",
    "NARRATION_REQUIRED_RUNTIME_STATE",
    "NARRATION_TEST_AUTHORITY_STATE",
    "NARRATION_TEST_BRIDGE_IDENTITY",
    "NarrationSynthesisError",
    "NarrationEvidenceBindingError",
    "NarrationExecutionContext",
    "NarrationGenerationRecord",
    "NarrationTestEvidenceProjection",
    "NarrationTestDialogueProjection",
    "build_narration_execution_context",
    "validate_narration_execution_context",
    "build_narration_tts_execution_request",
    "build_narration_generation_record",
    "validate_narration_generation_record",
    "build_narration_dialogue_asset_version",
    "build_test_only_narration_evidence_projection",
    "build_test_only_narration_dialogue_projection",
]
