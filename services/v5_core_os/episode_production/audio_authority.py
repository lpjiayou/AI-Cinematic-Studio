"""M12 audio authority contracts, rights bindings, and voice consent.

This module is deliberately contract-only.  It validates immutable proposed
audio-domain envelopes and their exact upstream bindings; it does not persist an
AssetVersion, perform Admission, execute an audio engine, or advance publication.
The existing V5 RightsManifest remains the rights authority.  ``RightsBinding``
only pins one exact manifest/evidence projection for downstream validation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .audio import (
    SPEECH_EMOTION_TAGS,
    normalize_clone_speech_parameters,
    normalize_speech_parameters,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _required_ref,
)
from .voice import (
    CLONE_VOICE_ENGINE_FAMILY,
    CLONE_VOICE_MODEL_ID,
    VoiceLockNotConfirmedError,
    validate_confirmed_clone_voice_lock_bundle,
    validate_confirmed_voice_lock_bundle,
)


AUDIO_GENERATION_REQUEST_SCHEMA_VERSION = "v5.audio-generation-request.v1"
AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION = "v5.audio-generation-request.v2"
CONSENT_GRANT_SCHEMA_VERSION = "v5.audio-consent-grant-version.v1"
AUDIO_RIGHTS_BINDING_SCHEMA_VERSION = "v5.audio-rights-binding.v1"
AUDIO_PROVENANCE_SCHEMA_VERSION = "v5.audio-provenance.v1"
AUDIO_REQUESTED_PROVENANCE_SCHEMA_VERSION = "v5.audio-requested-provenance.v1"

DIALOGUE_ASSET_VERSION_SCHEMA_VERSION = "v5.dialogue-asset-version.v1"
VOICE_ASSET_VERSION_SCHEMA_VERSION = "v5.voice-asset-version.v1"
DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION = (
    "v5.m12-dialogue-asset-version.v2"
)
VOICE_ASSET_VERSION_V2_SCHEMA_VERSION = "v5.m12-voice-asset-version.v2"
MUSIC_ASSET_VERSION_SCHEMA_VERSION = "v5.music-asset-version.v1"
SFX_ASSET_VERSION_SCHEMA_VERSION = "v5.sfx-asset-version.v1"
AMBIENCE_ASSET_VERSION_SCHEMA_VERSION = "v5.ambience-asset-version.v1"

AUDIO_ASSET_VERSION_TYPES = frozenset(
    {
        "DialogueAssetVersion",
        "VoiceAssetVersion",
        "MusicAssetVersion",
        "SfxAssetVersion",
        "AmbienceAssetVersion",
    }
)
AUDIO_REQUEST_KINDS = frozenset(
    {
        "DIALOGUE_SYNTHESIS",
        "NARRATION_SYNTHESIS",
        "VOICE_PROFILE_CREATION",
        "MUSIC_GENERATION",
        "SFX_GENERATION",
        "AMBIENCE_GENERATION",
    }
)
VOICE_SOURCE_KINDS = frozenset({"LOCAL_PRESET", "CLONED_WITH_CONSENT"})
CONSENT_REVOCATION_STATES = frozenset({"ACTIVE", "REVOKED"})
VOICE_CLONING_USE = "VOICE_CLONING"

_SCHEMA_BY_TYPE = {
    "DialogueAssetVersion": DIALOGUE_ASSET_VERSION_SCHEMA_VERSION,
    "VoiceAssetVersion": VOICE_ASSET_VERSION_SCHEMA_VERSION,
    "MusicAssetVersion": MUSIC_ASSET_VERSION_SCHEMA_VERSION,
    "SfxAssetVersion": SFX_ASSET_VERSION_SCHEMA_VERSION,
    "AmbienceAssetVersion": AMBIENCE_ASSET_VERSION_SCHEMA_VERSION,
}
_AUDIO_KIND_BY_TYPE = {
    "DialogueAssetVersion": "dialogue",
    "VoiceAssetVersion": "voice",
    "MusicAssetVersion": "music",
    "SfxAssetVersion": "sfx",
    "AmbienceAssetVersion": "ambience",
}
_OUTPUT_TYPE_BY_REQUEST_KIND = {
    "DIALOGUE_SYNTHESIS": "DialogueAssetVersion",
    "NARRATION_SYNTHESIS": "DialogueAssetVersion",
    "VOICE_PROFILE_CREATION": "VoiceAssetVersion",
    "MUSIC_GENERATION": "MusicAssetVersion",
    "SFX_GENERATION": "SfxAssetVersion",
    "AMBIENCE_GENERATION": "AmbienceAssetVersion",
}
_RIGHTS_USES_BY_ASSET_TYPE = {
    "DialogueAssetVersion": frozenset({"AUDIO_PRODUCTION", "SPEECH_SYNTHESIS"}),
    "VoiceAssetVersion": frozenset({"AUDIO_PRODUCTION", "VOICE_PROFILE_USE"}),
    "MusicAssetVersion": frozenset({"AUDIO_PRODUCTION", "MUSIC_GENERATION"}),
    "SfxAssetVersion": frozenset({"AUDIO_PRODUCTION", "SFX_GENERATION"}),
    "AmbienceAssetVersion": frozenset(
        {"AUDIO_PRODUCTION", "AMBIENCE_GENERATION"}
    ),
}
_RIGHTS_USES_BY_REQUEST_KIND = {
    "DIALOGUE_SYNTHESIS": frozenset(
        {"AUDIO_PRODUCTION", "SPEECH_SYNTHESIS"}
    ),
    "NARRATION_SYNTHESIS": frozenset(
        {"AUDIO_PRODUCTION", "SPEECH_SYNTHESIS"}
    ),
    "VOICE_PROFILE_CREATION": frozenset(
        {"AUDIO_PRODUCTION", "VOICE_PROFILE_USE"}
    ),
    "MUSIC_GENERATION": frozenset({"AUDIO_PRODUCTION", "MUSIC_GENERATION"}),
    "SFX_GENERATION": frozenset({"AUDIO_PRODUCTION", "SFX_GENERATION"}),
    "AMBIENCE_GENERATION": frozenset(
        {"AUDIO_PRODUCTION", "AMBIENCE_GENERATION"}
    ),
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMON_SCOPE_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
    }
)
_SOURCE_BINDING_FIELDS = frozenset({"sourceRef", "sourceDigest"})
_RIGHTS_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "rightsBindingRef",
        "rightsSource",
        "license",
        "ownership",
        "usageScope",
        "attributionRequirement",
        "sourceRefs",
        "rightsManifestRef",
        "rightsManifestVersion",
        "rightsManifestDigest",
        "authorityEvidenceRef",
        "authorityEvidenceDigest",
        "authorityState",
        "payloadDigest",
    }
)
_CONSENT_GRANT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "consentGrantRef",
        "consentGrantVersionRef",
        "version",
        "subjectRef",
        "grantorRef",
        "allowedUses",
        "prohibitedUses",
        "territories",
        "validFrom",
        "expiresAt",
        "revocationState",
        "evidenceRef",
        "evidenceDigest",
        "rightsManifestRef",
        "rightsManifestDigest",
        "supersedesConsentGrantVersionRef",
        "supersedesConsentGrantVersionDigest",
        "authorityState",
        "immutable",
        "createdAt",
        "payloadDigest",
    }
)
_PROVENANCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "originKind",
        "adapterIdentity",
        "generationRecordRef",
        "parametersDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "sourceRefs",
        "authorityState",
        "payloadDigest",
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
_ARTIFACT_FIELDS = frozenset(
    {
        "artifactKind",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "mediaType",
    }
)
_COMMON_ASSET_FIELDS = frozenset(
    {
        "schemaVersion",
        "assetVersionType",
        *_COMMON_SCOPE_FIELDS,
        "assetRef",
        "assetVersionRef",
        "version",
        "assetKind",
        "audioKind",
        "assetRequirementRef",
        "assetRequirementDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "artifact",
        "supersedesAssetVersionRef",
        "supersedesAssetVersionDigest",
        "provenance",
        "rightsBinding",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_DIALOGUE_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {
        "speechRole",
        "scriptVersionRef",
        "scriptVersionDigest",
        "dialogueRef",
        "narrationRef",
        "voiceAssetVersionRef",
        "voiceAssetVersionDigest",
        "language",
        "normalizedSpeechParameters",
        "sourceAudioCueRefs",
    }
)
_VOICE_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {
        "voiceIdentityRef",
        "characterRef",
        "voiceLockVersionRef",
        "voiceLockDigest",
        "voiceSourceKind",
        "voiceSourceSubjectRef",
        "engineRef",
        "modelRef",
        "profilePackage",
        "consentGrantRef",
        "consentGrantVersionRef",
        "consentGrantDigest",
    }
)
_CLONE_VOICE_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {
        "voiceIdentityRef",
        "characterRef",
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "voiceProfileVersionDigest",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceSourceKind",
        "voiceSourceSubjectRef",
        "sourceRecordingBindingRef",
        "sourceRecordingBindingDigest",
        "consentGrantRef",
        "consentGrantVersionRef",
        "consentGrantVersionDigest",
        "rightsBindingRef",
        "rightsBindingDigest",
        "engineId",
        "engineCommit",
        "modelId",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
    }
)
_CLONE_DIALOGUE_FIELDS = _DIALOGUE_FIELDS | frozenset(
    {
        "audioTechnicalValidationRef",
        "audioTechnicalValidationDigest",
        "audioFileDigest",
        "audioPcmContentDigest",
    }
)
_MUSIC_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {"musicSourceKind", "musicSpecDigest", "sourceAudioCueRefs"}
)
_SFX_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {"sfxKind", "synthesisSpecDigest", "sourceAudioCueRefs"}
)
_AMBIENCE_FIELDS = _COMMON_ASSET_FIELDS | frozenset(
    {"ambienceKind", "synthesisSpecDigest", "sourceAudioCueRefs"}
)
_ASSET_FIELDS_BY_TYPE = {
    "DialogueAssetVersion": _DIALOGUE_FIELDS,
    "VoiceAssetVersion": _VOICE_FIELDS,
    "MusicAssetVersion": _MUSIC_FIELDS,
    "SfxAssetVersion": _SFX_FIELDS,
    "AmbienceAssetVersion": _AMBIENCE_FIELDS,
}
_GENERATION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "requestKind",
        *_COMMON_SCOPE_FIELDS,
        "generationRequestRef",
        "generationRequestVersionRef",
        "version",
        "supersedesGenerationRequestVersionRef",
        "supersedesGenerationRequestVersionDigest",
        "assetRequirementRef",
        "assetRequirementDigest",
        "outputAssetVersionType",
        "outputTarget",
        "requestSpec",
        "rightsBinding",
        "requestedProvenance",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_M9_AUDIO_BINDING_BASE_FIELDS = frozenset(
    {
        "audioRequirementRef",
        "audioRequirementDigest",
        "executionMethodPlanVersionRef",
        "executionMethodPlanDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "creativeShotVersionRef",
        "creativeShotVersionDigest",
        "audioRole",
        "timingReference",
    }
)
_M9_SOURCE_SPAN_FIELDS = frozenset(
    {
        "scriptSceneRef",
        "sourceField",
        "sourceIndex",
        "startOffsetInclusive",
        "endOffsetExclusive",
    }
)
_M9_TIMING_REFERENCE_FIELDS = frozenset(
    {"startFrameInclusive", "endFrameExclusive"}
)
_M9_CLONE_LINEAGE_FIELDS = frozenset(
    {
        "consentGrantRef",
        "consentGrantVersionRef",
        "consentGrantVersionDigest",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "voiceProfileVersionDigest",
    }
)
_M9_AUDIO_ROLE_BY_REQUEST_KIND = {
    "DIALOGUE_SYNTHESIS": "dialogue",
    "NARRATION_SYNTHESIS": "narration",
    "SFX_GENERATION": "sfx",
    "AMBIENCE_GENERATION": "ambience",
}


class AudioDomainTypeMismatchError(EpisodeProductionError):
    code = "audio_domain_type_mismatch"


class AudioRightsRequiredError(UpstreamNotReadyError):
    code = "audio_rights_required"


class AudioConsentRequiredError(UpstreamNotReadyError):
    code = "audio_consent_required"


class AudioConsentNotEffectiveError(UpstreamNotReadyError):
    code = "audio_consent_not_effective"


class AudioProvenanceRequiredError(UpstreamNotReadyError):
    code = "audio_provenance_required"


class LegacyAudioTargetError(EpisodeProductionError):
    code = "legacy_audio_target_rejected"


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise EpisodeProductionError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise EpisodeProductionError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _exact(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise StaleInputError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not value and not allow_empty)
        or any(ord(character) < 32 for character in value)
    ):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EpisodeProductionError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EpisodeProductionError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EpisodeProductionError(f"{field} must include a timezone")
    return parsed


def _string_list(
    value: Any,
    field: str,
    *,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise EpisodeProductionError(f"{field} is invalid")
    result = [_text(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise EpisodeProductionError(f"{field} contains duplicates")
    return result


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(  # type: ignore[return-value]
        _required_ref(value[field], field)
        for field in (
            "workspaceRef",
            "projectRef",
            "seriesRef",
            "episodeRef",
            "productionRunRef",
        )
    )


def _source_refs(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise EpisodeProductionError(f"{field} is invalid")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact(raw, _SOURCE_BINDING_FIELDS, f"{field}[{index}]")
        ref = _required_ref(item["sourceRef"], f"{field}[{index}].sourceRef")
        if ref in seen:
            raise EpisodeProductionError(f"{field} contains duplicate refs")
        seen.add(ref)
        result.append(
            {
                "sourceRef": ref,
                "sourceDigest": _sha256(
                    item["sourceDigest"], f"{field}[{index}].sourceDigest"
                ),
            }
        )
    return result


def _ref_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise EpisodeProductionError(f"{field} is invalid")
    refs = [_required_ref(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if len(refs) != len(set(refs)):
        raise EpisodeProductionError(f"{field} contains duplicates")
    return refs


def _deferred_audio_cue_refs(value: Any) -> list[str]:
    refs = _ref_list(value, "sourceAudioCueRefs")
    if refs:
        raise UpstreamNotReadyError(
            "sourceAudioCueRefs require the M12 AudioCue authority contract"
        )
    return refs


def _parent(
    version: int,
    parent_ref: Any,
    parent_digest: Any,
    *,
    ref_field: str,
    digest_field: str,
) -> None:
    if version == 1:
        if parent_ref is not None or parent_digest is not None:
            raise EpisodeProductionError("initial version cannot have a predecessor")
        return
    _required_ref(parent_ref, ref_field)
    _sha256(parent_digest, digest_field)


def _validate_rights_binding(
    value: Any,
    *,
    required_uses: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if value is None:
        raise AudioRightsRequiredError("RightsBinding is required")
    result = _verify_sealed(value, _RIGHTS_BINDING_FIELDS, "RightsBinding")
    if result["schemaVersion"] != AUDIO_RIGHTS_BINDING_SCHEMA_VERSION:
        raise AudioRightsRequiredError("RightsBinding schema is unsupported")
    _required_ref(result["rightsBindingRef"], "rightsBindingRef")
    _text(result["rightsSource"], "rightsSource")
    _text(result["license"], "license")
    _text(result["ownership"], "ownership")
    uses = _string_list(result["usageScope"], "usageScope")
    if not required_uses.issubset(uses):
        raise AudioRightsRequiredError(
            "RightsBinding usageScope does not cover the audio operation"
        )
    _text(
        result["attributionRequirement"],
        "attributionRequirement",
        allow_empty=True,
    )
    sources = _source_refs(result["sourceRefs"], "sourceRefs")
    _required_ref(result["rightsManifestRef"], "rightsManifestRef")
    _positive_int(result["rightsManifestVersion"], "rightsManifestVersion")
    _sha256(result["rightsManifestDigest"], "rightsManifestDigest")
    _required_ref(result["authorityEvidenceRef"], "authorityEvidenceRef")
    _sha256(result["authorityEvidenceDigest"], "authorityEvidenceDigest")
    required_authority_sources = {
        (result["rightsManifestRef"], result["rightsManifestDigest"]),
        (result["authorityEvidenceRef"], result["authorityEvidenceDigest"]),
    }
    if not required_authority_sources.issubset(
        {(source["sourceRef"], source["sourceDigest"]) for source in sources}
    ):
        raise AudioRightsRequiredError(
            "RightsBinding authority sources are not digest-pinned"
        )
    if result["authorityState"] != "EVIDENCE_BOUND_NOT_RIGHTS_DECISION":
        raise AudioRightsRequiredError(
            "RightsBinding cannot claim an independent rights decision"
        )
    return result


def validate_rights_binding(value: Any) -> "RightsBinding":
    return RightsBinding.from_mapping(value)


def build_rights_binding(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _RIGHTS_BINDING_FIELDS - {"schemaVersion", "authorityState", "payloadDigest"}
    value = _exact(command, fields, "RightsBinding command")
    result = _seal(
        {
            "schemaVersion": AUDIO_RIGHTS_BINDING_SCHEMA_VERSION,
            **value,
            "authorityState": "EVIDENCE_BOUND_NOT_RIGHTS_DECISION",
        }
    )
    return RightsBinding.from_mapping(result).as_dict()


def _validate_consent_grant(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _CONSENT_GRANT_FIELDS, "ConsentGrant")
    if result["schemaVersion"] != CONSENT_GRANT_SCHEMA_VERSION:
        raise EpisodeProductionError("ConsentGrant schema is unsupported")
    for field in ("workspaceRef", "projectRef", "seriesRef"):
        _required_ref(result[field], field)
    for field in (
        "consentGrantRef",
        "consentGrantVersionRef",
        "subjectRef",
        "grantorRef",
        "evidenceRef",
        "rightsManifestRef",
    ):
        _required_ref(result[field], field)
    version = _positive_int(result["version"], "version")
    allowed = _string_list(result["allowedUses"], "allowedUses")
    prohibited = _string_list(
        result["prohibitedUses"], "prohibitedUses", allow_empty=True
    )
    if set(allowed) & set(prohibited):
        raise EpisodeProductionError("ConsentGrant use scopes overlap")
    _string_list(result["territories"], "territories")
    valid_from = _timestamp(result["validFrom"], "validFrom")
    expires_at = _timestamp(result["expiresAt"], "expiresAt")
    if valid_from >= expires_at:
        raise EpisodeProductionError("ConsentGrant effective interval is invalid")
    if result["revocationState"] not in CONSENT_REVOCATION_STATES:
        raise EpisodeProductionError("ConsentGrant revocationState is invalid")
    _sha256(result["evidenceDigest"], "evidenceDigest")
    _sha256(result["rightsManifestDigest"], "rightsManifestDigest")
    _parent(
        version,
        result["supersedesConsentGrantVersionRef"],
        result["supersedesConsentGrantVersionDigest"],
        ref_field="supersedesConsentGrantVersionRef",
        digest_field="supersedesConsentGrantVersionDigest",
    )
    if (
        result["supersedesConsentGrantVersionRef"]
        == result["consentGrantVersionRef"]
    ):
        raise EpisodeProductionError("ConsentGrant cannot supersede itself")
    if result["authorityState"] != "EVIDENCE_BOUND_CONTRACT_ONLY":
        raise AudioConsentRequiredError(
            "ConsentGrant cannot claim an independent consent decision"
        )
    if result["immutable"] is not True:
        raise EpisodeProductionError("ConsentGrant must be immutable")
    _timestamp(result["createdAt"], "createdAt")
    return result


def validate_consent_grant(value: Any) -> "ConsentGrant":
    return ConsentGrant.from_mapping(value)


def build_consent_grant(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _CONSENT_GRANT_FIELDS - {
        "schemaVersion",
        "authorityState",
        "immutable",
        "payloadDigest",
    }
    value = _exact(command, fields, "ConsentGrant command")
    result = _seal(
        {
            "schemaVersion": CONSENT_GRANT_SCHEMA_VERSION,
            **value,
            "authorityState": "EVIDENCE_BOUND_CONTRACT_ONLY",
            "immutable": True,
        }
    )
    return ConsentGrant.from_mapping(result).as_dict()


def require_effective_consent_grant(
    value: Any,
    *,
    evaluated_at: str,
    required_use: str,
    expected_subject_ref: str | None = None,
    expected_grant_ref: str | None = None,
    expected_version_ref: str | None = None,
    expected_digest: str | None = None,
    expected_scope: tuple[str, str, str] | None = None,
    territory: str | None = None,
) -> "ConsentGrant":
    grant = ConsentGrant.from_mapping(value)
    raw = grant.as_dict()
    when = _timestamp(evaluated_at, "evaluatedAt")
    if (
        raw["revocationState"] != "ACTIVE"
        or when < _timestamp(raw["validFrom"], "validFrom")
        or when >= _timestamp(raw["expiresAt"], "expiresAt")
        or required_use not in raw["allowedUses"]
        or required_use in raw["prohibitedUses"]
    ):
        raise AudioConsentNotEffectiveError("ConsentGrant is not effective")
    if (
        territory is not None
        and territory not in raw["territories"]
        and "WORLDWIDE" not in raw["territories"]
    ):
        raise AudioConsentNotEffectiveError("ConsentGrant territory is not effective")
    if expected_subject_ref is not None and raw["subjectRef"] != expected_subject_ref:
        raise StaleInputError("ConsentGrant subject binding is stale")
    if expected_grant_ref is not None and raw["consentGrantRef"] != expected_grant_ref:
        raise StaleInputError("ConsentGrant root binding is stale")
    if (
        expected_version_ref is not None
        and raw["consentGrantVersionRef"] != expected_version_ref
    ):
        raise StaleInputError("ConsentGrant version binding is stale")
    if expected_digest is not None and raw["payloadDigest"] != expected_digest:
        raise StaleInputError("ConsentGrant digest binding is stale")
    if expected_scope is not None and tuple(
        raw[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    ) != expected_scope:
        raise StaleInputError("ConsentGrant scope binding is stale")
    return grant


def _validate_provenance(value: Any) -> dict[str, Any]:
    if value is None:
        raise AudioProvenanceRequiredError("audio provenance is required")
    result = _verify_sealed(value, _PROVENANCE_FIELDS, "AudioProvenance")
    if result["schemaVersion"] != AUDIO_PROVENANCE_SCHEMA_VERSION:
        raise AudioProvenanceRequiredError("audio provenance schema is unsupported")
    _text(result["originKind"], "originKind")
    _text(result["adapterIdentity"], "adapterIdentity")
    _required_ref(result["generationRecordRef"], "generationRecordRef")
    _sha256(result["parametersDigest"], "parametersDigest")
    _required_ref(result["artifactEvidenceRef"], "artifactEvidenceRef")
    _sha256(result["artifactEvidenceDigest"], "artifactEvidenceDigest")
    _source_refs(result["sourceRefs"], "sourceRefs")
    if result["authorityState"] != "TECHNICAL_EVIDENCE_ONLY":
        raise AudioProvenanceRequiredError("audio provenance overclaims authority")
    return result


def validate_audio_provenance(value: Any) -> dict[str, Any]:
    return _validate_provenance(value)


def build_audio_provenance(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _PROVENANCE_FIELDS - {"schemaVersion", "authorityState", "payloadDigest"}
    value = _exact(command, fields, "AudioProvenance command")
    return _validate_provenance(
        _seal(
            {
                "schemaVersion": AUDIO_PROVENANCE_SCHEMA_VERSION,
                **value,
                "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            }
        )
    )


def _validate_requested_provenance(value: Any) -> dict[str, Any]:
    if value is None:
        raise AudioProvenanceRequiredError("requested provenance is required")
    result = _verify_sealed(
        value, _REQUESTED_PROVENANCE_FIELDS, "AudioRequestedProvenance"
    )
    if result["schemaVersion"] != AUDIO_REQUESTED_PROVENANCE_SCHEMA_VERSION:
        raise AudioProvenanceRequiredError("requested provenance schema is unsupported")
    _text(result["originKind"], "originKind")
    _text(result["adapterIdentity"], "adapterIdentity")
    _sha256(result["parametersDigest"], "parametersDigest")
    _source_refs(result["sourceRefs"], "sourceRefs")
    return result


def build_requested_audio_provenance(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _REQUESTED_PROVENANCE_FIELDS - {"schemaVersion", "payloadDigest"}
    value = _exact(command, fields, "AudioRequestedProvenance command")
    return _validate_requested_provenance(
        _seal({"schemaVersion": AUDIO_REQUESTED_PROVENANCE_SCHEMA_VERSION, **value})
    )


def _artifact(value: Any, asset_version_type: str) -> dict[str, Any]:
    result = _exact(value, _ARTIFACT_FIELDS, "audio artifact")
    expected_artifact = (
        ("VOICE_PROFILE_PACKAGE", "application/octet-stream", ".voicepkg")
        if asset_version_type == "VoiceAssetVersion"
        else ("PCM_AUDIO", "audio/wav", ".wav")
    )
    if (
        result["artifactKind"] != expected_artifact[0]
        or result["mediaType"] != expected_artifact[1]
    ):
        raise AudioDomainTypeMismatchError(
            f"{asset_version_type} artifact kind is invalid"
        )
    _required_ref(result["artifactEvidenceRef"], "artifact.artifactEvidenceRef")
    _sha256(result["artifactEvidenceDigest"], "artifact.artifactEvidenceDigest")
    _required_ref(result["artifactRef"], "artifact.artifactRef")
    storage_key = _text(result["storageKey"], "artifact.storageKey")
    path = PurePosixPath(storage_key)
    if (
        not storage_key.startswith("asset-versions/audio/")
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in storage_key
        or str(path) != storage_key
        or not storage_key.endswith(expected_artifact[2])
    ):
        raise LegacyAudioTargetError("audio output must use AssetVersion storage")
    _positive_int(result["byteSize"], "artifact.byteSize")
    _sha256(result["fileDigest"], "artifact.fileDigest")
    return result


def _common_asset(
    value: Any,
    asset_version_type: str,
    *,
    schema_version: str | None = None,
    fields: frozenset[str] | None = None,
) -> dict[str, Any]:
    selected_fields = fields or _ASSET_FIELDS_BY_TYPE[asset_version_type]
    selected_schema = schema_version or _SCHEMA_BY_TYPE[asset_version_type]
    result = _verify_sealed(value, selected_fields, asset_version_type)
    if (
        result["schemaVersion"] != selected_schema
        or result["assetVersionType"] != asset_version_type
        or result["audioKind"] != _AUDIO_KIND_BY_TYPE[asset_version_type]
        or result["assetKind"] != "audio"
    ):
        raise AudioDomainTypeMismatchError(
            f"{asset_version_type} discriminator is invalid"
        )
    _scope(result)
    for field in (
        "assetRef",
        "assetVersionRef",
        "assetRequirementRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationResultRef",
        "createdBy",
    ):
        _required_ref(result[field], field)
    version = _positive_int(result["version"], "version")
    for field in (
        "assetRequirementDigest",
        "generationRequestDigest",
        "generationResultDigest",
    ):
        _sha256(result[field], field)
    artifact = _artifact(result["artifact"], asset_version_type)
    _parent(
        version,
        result["supersedesAssetVersionRef"],
        result["supersedesAssetVersionDigest"],
        ref_field="supersedesAssetVersionRef",
        digest_field="supersedesAssetVersionDigest",
    )
    if result["supersedesAssetVersionRef"] == result["assetVersionRef"]:
        raise EpisodeProductionError("audio AssetVersion cannot supersede itself")
    try:
        provenance = _validate_provenance(result["provenance"])
    except EpisodeProductionError as exc:
        if isinstance(exc, AudioProvenanceRequiredError):
            raise
        raise AudioProvenanceRequiredError("audio provenance is invalid") from exc
    if (
        provenance["artifactEvidenceRef"] != artifact["artifactEvidenceRef"]
        or provenance["artifactEvidenceDigest"]
        != artifact["artifactEvidenceDigest"]
    ):
        raise StaleInputError("audio artifact provenance binding is stale")
    if provenance["generationRecordRef"] != result["generationResultRef"]:
        raise StaleInputError("audio generation record binding is stale")
    required_provenance_sources = {
        (result["generationRequestVersionRef"], result["generationRequestDigest"]),
        (result["generationResultRef"], result["generationResultDigest"]),
    }
    if not required_provenance_sources.issubset(
        {
            (source["sourceRef"], source["sourceDigest"])
            for source in provenance["sourceRefs"]
        }
    ):
        raise AudioProvenanceRequiredError(
            "audio provenance does not cover generation lineage"
        )
    try:
        rights = _validate_rights_binding(
            result["rightsBinding"],
            required_uses=_RIGHTS_USES_BY_ASSET_TYPE[asset_version_type],
        )
    except EpisodeProductionError as exc:
        if isinstance(exc, AudioRightsRequiredError):
            raise
        raise AudioRightsRequiredError("audio rights binding is invalid") from exc
    if not any(
        source["sourceRef"] == result["assetRequirementRef"]
        and source["sourceDigest"] == result["assetRequirementDigest"]
        for source in rights["sourceRefs"]
    ):
        raise AudioRightsRequiredError(
            "RightsBinding does not cover the audio AssetRequirement"
        )
    if (
        result["state"] != "PROPOSED"
        or result["authorityState"] != "CONTRACT_ONLY_NOT_ADMITTED"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise EpisodeProductionError("audio proposal lifecycle is invalid")
    _timestamp(result["createdAt"], "createdAt")
    return result


def _confirmed_voice(value: Any) -> dict[str, Any]:
    if value is None:
        raise VoiceLockNotConfirmedError("confirmed VoiceLock is required")
    return validate_confirmed_voice_lock_bundle(value)


def _voice_lineage_wrapper(
    value: Any,
    *,
    class_name: str,
    label: str,
) -> dict[str, Any]:
    """Require an immutable C1 wrapper, never a detached caller mapping."""

    from . import voice_profile as voice_profile_contracts

    expected_type = getattr(voice_profile_contracts, class_name, None)
    if expected_type is None or type(value) is not expected_type:
        raise AudioDomainTypeMismatchError(
            f"{label} requires the exact immutable {class_name} wrapper"
        )
    result = value.as_dict()
    if not isinstance(result, Mapping):
        raise AudioDomainTypeMismatchError(f"{label} wrapper is invalid")
    unsigned = deepcopy(dict(result))
    supplied = unsigned.pop("payloadDigest", None)
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise StaleInputError(f"{label} payloadDigest is invalid")
    return deepcopy(dict(result))


def _effective_clone_consent(
    value: Any,
    *,
    evaluated_at: str | None,
) -> dict[str, Any]:
    consent = _voice_lineage_wrapper(
        value,
        class_name="ConsentGrantVersionV2",
        label="clone ConsentGrantVersion",
    )
    if evaluated_at is None:
        raise AudioConsentRequiredError(
            "clone consent requires an explicit evaluation time"
        )
    instant = _timestamp(evaluated_at, "evaluatedAt")
    if (
        consent.get("revocationState") != "ACTIVE"
        or not {
            "VOICE_CLONING",
            "VOICE_PROFILE_USE",
            "AUDIO_PRODUCTION",
        }.issubset(set(consent.get("allowedUses", ())))
        or instant < _timestamp(consent.get("validFrom"), "validFrom")
        or instant >= _timestamp(consent.get("expiresAt"), "expiresAt")
    ):
        raise AudioConsentNotEffectiveError(
            "clone ConsentGrantVersion is not effective"
        )
    return consent


def _current_clone_authority(
    value: Any,
    *,
    voice_profile_version: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    confirmed_voice_lock: Any,
    rights_binding: Mapping[str, Any],
    evaluated_at: str | None,
    required: bool,
    expected_scope: tuple[str, str, str, str],
) -> dict[str, Any] | None:
    """Match a service-issued current-head proof to every explicit input.

    The proof is ephemeral and never enters an AssetVersion payload.  Historical
    validators may omit it, while every clone builder sets ``required=True`` so
    a detached CONFIRMED/ACTIVE historical version cannot authorize a new write.
    """

    if value is None:
        if required:
            raise AudioConsentNotEffectiveError(
                "a service-issued current VoiceProfile authority is required"
            )
        return None
    from .voice_profile import CurrentConfirmedVoiceProfileAuthority

    if type(value) is not CurrentConfirmedVoiceProfileAuthority:
        raise AudioDomainTypeMismatchError(
            "current clone VoiceProfile authority requires the exact "
            "service-issued wrapper"
        )
    assert_current = getattr(value, "assert_current", None)
    if not callable(assert_current):
        raise AudioDomainTypeMismatchError(
            "current clone VoiceProfile authority cannot revalidate its journal head"
        )
    # This is deliberately performed at every consumption point.  It re-reads
    # the evidence journal so a proof issued before a revocation successor
    # cannot authorize a later proposal.
    assert_current()
    authority = _voice_lineage_wrapper(
        value,
        class_name="CurrentConfirmedVoiceProfileAuthority",
        label="current clone VoiceProfile authority",
    )
    if evaluated_at is None or authority.get("evaluatedAt") != evaluated_at:
        raise StaleInputError(
            "current clone VoiceProfile authority evaluation time is stale"
        )
    if tuple(
        authority.get(field)
        for field in (
            "workspaceRef",
            "projectRef",
            "seriesRef",
            "productionRunRef",
        )
    ) != expected_scope:
        raise StaleInputError(
            "current clone VoiceProfile authority production scope is stale"
        )
    profile = _voice_lineage_wrapper(
        voice_profile_version,
        class_name="VoiceProfileVersion",
        label="VoiceProfileVersion",
    )
    consent = _voice_lineage_wrapper(
        consent_grant_version,
        class_name="ConsentGrantVersionV2",
        label="clone ConsentGrantVersion",
    )
    source = _voice_lineage_wrapper(
        source_recording_binding,
        class_name="SourceVoiceRecordingAssetVersionBinding",
        label="source voice recording binding",
    )
    lock = validate_confirmed_clone_voice_lock_bundle(confirmed_voice_lock)
    expected = {
        "voiceProfileVersion": profile,
        "consentGrantVersion": consent,
        "sourceRecordingBinding": source,
        "confirmedVoiceLock": lock,
        "rightsBinding": deepcopy(dict(rights_binding)),
    }
    if any(authority.get(field) != selected for field, selected in expected.items()):
        raise StaleInputError(
            "current clone VoiceProfile authority upstream binding is stale"
        )
    if authority.get("publicationAllowed") is not False:
        raise AudioDomainTypeMismatchError(
            "current clone VoiceProfile authority overclaims publication"
        )
    return authority


def _match_voice_asset_to_lock(
    value: Mapping[str, Any], confirmed_voice_lock: Any
) -> dict[str, Any]:
    bundle = _confirmed_voice(confirmed_voice_lock)
    root = bundle["voiceLock"]
    version = bundle["voiceLockVersion"]
    scope = (root["workspaceRef"], root["projectRef"], root["seriesRef"])
    if (
        tuple(value[field] for field in ("workspaceRef", "projectRef", "seriesRef"))
        != scope
        or value["voiceIdentityRef"] != root["voiceRef"]
        or value["characterRef"] != root["characterRef"]
        or value["voiceLockVersionRef"] != version["voiceLockVersionRef"]
        or value["voiceLockDigest"] != version["payloadDigest"]
        or value["engineRef"] != version["engineFamily"]
        or value["modelRef"] != version["voiceId"]
    ):
        raise StaleInputError("VoiceAssetVersion VoiceLock binding is stale")
    return bundle


def _validate_dialogue_asset_version(
    value: Any,
    *,
    confirmed_voice_lock: Any,
    voice_asset_version: Any,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    result = _common_asset(value, "DialogueAssetVersion")
    if result["speechRole"] not in {"dialogue", "narration"}:
        raise AudioDomainTypeMismatchError("speechRole is invalid")
    _required_ref(result["scriptVersionRef"], "scriptVersionRef")
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    dialogue_ref = result["dialogueRef"]
    narration_ref = result["narrationRef"]
    expected_dialogue = result["speechRole"] == "dialogue"
    if expected_dialogue:
        _required_ref(dialogue_ref, "dialogueRef")
        if narration_ref is not None:
            raise AudioDomainTypeMismatchError("dialogue cannot bind narrationRef")
    else:
        _required_ref(narration_ref, "narrationRef")
        if dialogue_ref is not None:
            raise AudioDomainTypeMismatchError("narration cannot bind dialogueRef")
    voice = _validate_voice_asset_version(
        voice_asset_version,
        confirmed_voice_lock=confirmed_voice_lock,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
    )
    if (
        result["voiceAssetVersionRef"] != voice["assetVersionRef"]
        or result["voiceAssetVersionDigest"] != voice["payloadDigest"]
    ):
        raise StaleInputError("DialogueAssetVersion voice binding is stale")
    _text(result["language"], "language")
    voice_version = _confirmed_voice(confirmed_voice_lock)["voiceLockVersion"]
    if result["language"] != voice_version["languageCode"]:
        raise StaleInputError("DialogueAssetVersion language binding is stale")
    normalized = normalize_speech_parameters(
        result["normalizedSpeechParameters"],
        confirmed_voice_lock=confirmed_voice_lock,
    )
    if normalized != result["normalizedSpeechParameters"]:
        raise StaleInputError("normalizedSpeechParameters are not normalized")
    if normalized["audioRole"] != result["speechRole"]:
        raise AudioDomainTypeMismatchError("speechRole does not match parameters")
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def validate_persisted_audio_domain_asset_version_evidence(
    value: Any,
    *,
    expected_scope: tuple[str, str, str, str, str],
    expected_asset_version_ref: str,
    expected_asset_version_digest: str,
) -> dict[str, Any]:
    """Validate one journaled typed DialogueAssetVersion without detached locks.

    This read-only resolver boundary accepts only the historical v1 dialogue
    contract.  It verifies the exact sealed payload, proposal lifecycle,
    rights/provenance, PCM artifact binding, and closed speech projection.  A
    separate canonical AssetAdmission fact remains responsible for admission;
    this helper neither creates nor upgrades authority.
    """

    if (
        not isinstance(expected_scope, tuple)
        or len(expected_scope) != 5
    ):
        raise EpisodeProductionError(
            "expected_scope must contain the five audio scope refs"
        )
    selected_scope = tuple(
        _required_ref(selected, field)
        for field, selected in zip(
            (
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "productionRunRef",
            ),
            expected_scope,
        )
    )
    selected_ref = _required_ref(
        expected_asset_version_ref,
        "expected_asset_version_ref",
    )
    selected_digest = _sha256(
        expected_asset_version_digest,
        "expected_asset_version_digest",
    )
    result = _common_asset(value, "DialogueAssetVersion")
    if (
        tuple(
            result[field]
            for field in (
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "productionRunRef",
            )
        )
        != selected_scope
        or result["assetVersionRef"] != selected_ref
        or result["payloadDigest"] != selected_digest
    ):
        raise StaleInputError(
            "persisted DialogueAssetVersion identity or scope is stale"
        )
    role = result["speechRole"]
    if not isinstance(role, str) or role not in {"dialogue", "narration"}:
        raise AudioDomainTypeMismatchError("speechRole is invalid")
    _required_ref(result["scriptVersionRef"], "scriptVersionRef")
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    if role == "dialogue":
        _required_ref(result["dialogueRef"], "dialogueRef")
        if result["narrationRef"] is not None:
            raise AudioDomainTypeMismatchError(
                "dialogue cannot bind narrationRef"
            )
    else:
        _required_ref(result["narrationRef"], "narrationRef")
        if result["dialogueRef"] is not None:
            raise AudioDomainTypeMismatchError(
                "narration cannot bind dialogueRef"
            )
    _required_ref(result["voiceAssetVersionRef"], "voiceAssetVersionRef")
    _sha256(result["voiceAssetVersionDigest"], "voiceAssetVersionDigest")
    _text(result["language"], "language")
    parameters = result["normalizedSpeechParameters"]
    if not isinstance(parameters, Mapping):
        raise EpisodeProductionError(
            "normalizedSpeechParameters are invalid"
        )
    required_parameters = {
        "speechSynthesis",
        "text",
        "voiceRef",
        "sampleRate",
        "channels",
        "audioRole",
    }
    optional_parameters = {"emotionTag"}
    if (
        not required_parameters.issubset(parameters)
        or set(parameters) - required_parameters - optional_parameters
        or parameters["speechSynthesis"] is not True
        or parameters["audioRole"] != role
    ):
        raise EpisodeProductionError(
            "normalizedSpeechParameters are invalid"
        )
    _text(parameters["text"], "normalizedSpeechParameters.text")
    _required_ref(
        parameters["voiceRef"],
        "normalizedSpeechParameters.voiceRef",
    )
    sample_rate = parameters["sampleRate"]
    channels = parameters["channels"]
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, int)
        or sample_rate < 8_000
        or sample_rate > 384_000
        or isinstance(channels, bool)
        or not isinstance(channels, int)
        or channels not in {1, 2}
    ):
        raise EpisodeProductionError(
            "normalizedSpeechParameters technical format is invalid"
        )
    emotion = parameters.get("emotionTag")
    if emotion is not None and (
        not isinstance(emotion, str) or emotion not in SPEECH_EMOTION_TAGS
    ):
        raise EpisodeProductionError(
            "normalizedSpeechParameters emotionTag is invalid"
        )
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def _validated_v4_generation_evidence(
    generation_result: Any,
    artifact_evidence: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from .audio import (
        V4_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
        V4_AUDIO_GENERATION_RESULT_SCHEMA_VERSION,
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        _V4_AUDIO_GENERATION_RESULT_FIELDS,
    )

    result = _verify_sealed(
        generation_result,
        _V4_AUDIO_GENERATION_RESULT_FIELDS,
        "V4 audio GenerationResult",
    )
    evidence = _verify_sealed(
        artifact_evidence,
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        "V4 audio ArtifactEvidence",
    )
    if (
        result["schemaVersion"] != V4_AUDIO_GENERATION_RESULT_SCHEMA_VERSION
        or evidence["schemaVersion"]
        != V4_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or result["state"] != "SUCCEEDED"
        or evidence["state"] != "TECHNICALLY_VERIFIED"
        or result["provenance"] != "LOCAL_EVIDENCE"
        or result["publicationAllowed"] is not False
        or evidence["publicationAllowed"] is not False
        or result["artifactEvidenceRef"] != evidence["artifactEvidenceRef"]
        or result["artifactEvidenceDigest"] != evidence["payloadDigest"]
    ):
        raise StaleInputError("V4 audio generation evidence is stale")
    shared = set(result) & set(evidence) - {
        "schemaVersion",
        "state",
        "payloadDigest",
    }
    if any(result[field] != evidence[field] for field in shared):
        raise StaleInputError("V4 audio generation evidence aliases are stale")
    return result, evidence


def _audio_technical_validation_wrapper(value: Any) -> dict[str, Any]:
    from .audio_validation import (
        AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
        AUDIO_TECHNICAL_VALIDATION_STATE,
        AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION,
        AudioTechnicalValidation,
    )

    if type(value) is not AudioTechnicalValidation:
        raise AudioDomainTypeMismatchError(
            "clone DialogueAssetVersion requires an exact "
            "AudioTechnicalValidation wrapper"
        )
    result = value.as_dict()
    unsigned = deepcopy(result)
    supplied = unsigned.pop("payloadDigest", None)
    if not isinstance(supplied, str) or supplied != _digest(unsigned):
        raise StaleInputError("AudioTechnicalValidation payloadDigest is invalid")
    if (
        result.get("schemaVersion")
        != AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION
        or result.get("validationKind")
        != "PRE_ASSET_GENERATION_EVIDENCE"
        or result.get("state") != AUDIO_TECHNICAL_VALIDATION_STATE
        or result.get("authorityState")
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or result.get("immutable") is not True
        or result.get("publicationAllowed") is not False
    ):
        raise AudioDomainTypeMismatchError(
            "clone DialogueAssetVersion requires pre-asset "
            "AudioTechnicalValidation v2"
        )
    return result


def _validate_clone_dialogue_asset_version(
    value: Any,
    *,
    voice_asset_version: Any,
    audio_generation_request: Any,
    generation_result: Any,
    artifact_evidence: Any,
    audio_technical_validation: Any,
    confirmed_voice_lock: Any,
    voice_profile_version: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str | None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> dict[str, Any]:
    result = _common_asset(
        value,
        "DialogueAssetVersion",
        schema_version=DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION,
        fields=_CLONE_DIALOGUE_FIELDS,
    )
    if type(voice_asset_version) is not VoiceAssetVersion:
        raise AudioDomainTypeMismatchError(
            "clone DialogueAssetVersion requires an exact VoiceAssetVersion wrapper"
        )
    selected_voice = voice_asset_version.as_dict()
    if selected_voice.get("schemaVersion") != VOICE_ASSET_VERSION_V2_SCHEMA_VERSION:
        raise AudioDomainTypeMismatchError(
            "fixed-voice v1 cannot satisfy clone DialogueAssetVersion"
        )
    voice = _validate_clone_voice_asset_version(
        selected_voice,
        voice_profile_version=voice_profile_version,
        confirmed_voice_lock=confirmed_voice_lock,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        evaluated_at=evaluated_at,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
    )
    if type(audio_generation_request) is not AudioGenerationRequest:
        raise AudioDomainTypeMismatchError(
            "clone DialogueAssetVersion requires an exact AudioGenerationRequest wrapper"
        )
    request = _validate_audio_generation_request(
        audio_generation_request.as_dict(),
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
    )
    generation, evidence = _validated_v4_generation_evidence(
        generation_result,
        artifact_evidence,
    )
    technical = _audio_technical_validation_wrapper(audio_technical_validation)
    lock_bundle = validate_confirmed_clone_voice_lock_bundle(
        confirmed_voice_lock
    )

    if result["speechRole"] not in {"dialogue", "narration"}:
        raise AudioDomainTypeMismatchError("speechRole is invalid")
    _required_ref(result["scriptVersionRef"], "scriptVersionRef")
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    if result["speechRole"] == "dialogue":
        _required_ref(result["dialogueRef"], "dialogueRef")
        if result["narrationRef"] is not None:
            raise AudioDomainTypeMismatchError("dialogue cannot bind narrationRef")
    else:
        _required_ref(result["narrationRef"], "narrationRef")
        if result["dialogueRef"] is not None:
            raise AudioDomainTypeMismatchError("narration cannot bind dialogueRef")
    _text(result["language"], "language")
    normalized = normalize_clone_speech_parameters(
        result["normalizedSpeechParameters"],
        confirmed_voice_lock=lock_bundle,
    )
    if (
        normalized != result["normalizedSpeechParameters"]
        or normalized["audioRole"] != result["speechRole"]
    ):
        raise StaleInputError("clone dialogue speech parameters are stale")
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    if (
        result["voiceAssetVersionRef"] != voice["assetVersionRef"]
        or result["voiceAssetVersionDigest"] != voice["payloadDigest"]
    ):
        raise StaleInputError("clone DialogueAssetVersion voice binding is stale")
    expected_request_kind = (
        "DIALOGUE_SYNTHESIS"
        if result["speechRole"] == "dialogue"
        else "NARRATION_SYNTHESIS"
    )
    request_spec = request.get("requestSpec")
    if (
        request.get("requestKind") != expected_request_kind
        or request.get("outputAssetVersionType") != "DialogueAssetVersion"
        or not isinstance(request_spec, Mapping)
        or result["generationRequestRef"] != request["generationRequestRef"]
        or result["generationRequestVersionRef"]
        != request["generationRequestVersionRef"]
        or result["generationRequestDigest"] != request["payloadDigest"]
        or result["assetRequirementRef"] != request["assetRequirementRef"]
        or result["assetRequirementDigest"]
        != request["assetRequirementDigest"]
        or result["scriptVersionRef"] != request_spec.get("scriptVersionRef")
        or result["scriptVersionDigest"]
        != request_spec.get("scriptVersionDigest")
        or result["dialogueRef"] != request_spec.get("dialogueRef")
        or result["narrationRef"] != request_spec.get("narrationRef")
        or result["voiceAssetVersionRef"]
        != request_spec.get("voiceAssetVersionRef")
        or result["voiceAssetVersionDigest"]
        != request_spec.get("voiceAssetVersionDigest")
        or result["language"] != request_spec.get("language")
        or result["normalizedSpeechParameters"]
        != request_spec.get("normalizedSpeechParameters")
        or result["sourceAudioCueRefs"]
        != request_spec.get("sourceAudioCueRefs")
    ):
        raise StaleInputError("clone audio generation request binding is stale")
    if (
        result["generationResultRef"] != generation["generationResultRef"]
        or result["generationResultDigest"] != generation["payloadDigest"]
        or generation["generationRequestRef"] != request["generationRequestRef"]
        or generation["generationRequestVersionRef"]
        != request["generationRequestVersionRef"]
        or generation["generationRequestDigest"] != request["payloadDigest"]
        or generation["assetRequirementRef"]
        != request["assetRequirementRef"]
        or generation["assetRequirementDigest"]
        != request["assetRequirementDigest"]
        or generation["scriptVersionRef"]
        != request_spec["scriptVersionRef"]
        or generation["scriptVersionDigest"]
        != request_spec["scriptVersionDigest"]
        or generation["audioRole"] != result["speechRole"]
    ):
        raise StaleInputError("clone GenerationResult binding is stale")
    artifact = result["artifact"]
    if (
        artifact["artifactEvidenceRef"] != evidence["artifactEvidenceRef"]
        or artifact["artifactEvidenceDigest"] != evidence["payloadDigest"]
        or artifact["artifactRef"] != evidence["artifactRef"]
        or artifact["storageKey"] != evidence["storageKey"]
        or artifact["byteSize"] != evidence["byteSize"]
        or artifact["fileDigest"] != evidence["sha256"]
    ):
        raise StaleInputError("clone ArtifactEvidence binding is stale")
    provenance = result["provenance"]
    requested_provenance = request["requestedProvenance"]
    if (
        requested_provenance["adapterIdentity"]
        != generation["adapterIdentity"]
        or requested_provenance["originKind"] != provenance["originKind"]
        or requested_provenance["parametersDigest"]
        != generation["parametersDigest"]
        or provenance["adapterIdentity"] != generation["adapterIdentity"]
        or provenance["generationRecordRef"]
        != generation["generationResultRef"]
        or provenance["parametersDigest"] != generation["parametersDigest"]
        or provenance["artifactEvidenceRef"]
        != evidence["artifactEvidenceRef"]
        or provenance["artifactEvidenceDigest"] != evidence["payloadDigest"]
        or not any(
            source["sourceRef"] == request["generationRequestVersionRef"]
            and source["sourceDigest"] == request["payloadDigest"]
            for source in provenance["sourceRefs"]
        )
        or not any(
            source["sourceRef"] == generation["generationResultRef"]
            and source["sourceDigest"] == generation["payloadDigest"]
            for source in provenance["sourceRefs"]
        )
    ):
        raise StaleInputError("clone audio provenance binding is stale")
    for field in (
        "audioTechnicalValidationDigest",
        "audioFileDigest",
        "audioPcmContentDigest",
    ):
        _sha256(result[field], field)
    _required_ref(
        result["audioTechnicalValidationRef"],
        "audioTechnicalValidationRef",
    )
    _required_ref(technical["analysisEvidenceRef"], "analysisEvidenceRef")
    _sha256(technical["analysisEvidenceDigest"], "analysisEvidenceDigest")
    if (
        result["audioTechnicalValidationRef"]
        != technical["validationVersionRef"]
        or result["audioTechnicalValidationDigest"] != technical["payloadDigest"]
        or result["audioFileDigest"] != artifact["fileDigest"]
        or result["audioFileDigest"] != technical["fileDigest"]
        or result["audioPcmContentDigest"] != technical["pcmContentDigest"]
        or technical["generationRequestRef"] != request["generationRequestRef"]
        or technical["generationRequestVersionRef"]
        != request["generationRequestVersionRef"]
        or technical["generationRequestDigest"] != request["payloadDigest"]
        or technical["generationResultRef"]
        != generation["generationResultRef"]
        or technical["generationResultDigest"] != generation["payloadDigest"]
        or technical["artifactEvidenceRef"]
        != evidence["artifactEvidenceRef"]
        or technical["artifactEvidenceDigest"] != evidence["payloadDigest"]
        or technical["artifactRef"] != evidence["artifactRef"]
        or technical["storageKey"] != evidence["storageKey"]
        or technical["byteSize"] != evidence["byteSize"]
        or technical["validationState"] != "PASSED"
    ):
        raise StaleInputError("clone AudioTechnicalValidation binding is stale")
    expected_scope = (
        result["workspaceRef"],
        result["productionRunRef"],
    )
    if any(
        (item["workspaceRef"], item["productionRunRef"]) != expected_scope
        for item in (request, generation, evidence, technical)
    ):
        raise StaleInputError("clone dialogue production scope is stale")
    full_scope_fields = (
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
    )
    dialogue_scope = tuple(result[field] for field in full_scope_fields)
    if any(
        tuple(item[field] for field in full_scope_fields) != dialogue_scope
        for item in (voice, request)
    ):
        raise StaleInputError("clone dialogue full production scope is stale")
    return result


def validate_dialogue_asset_version(
    value: Any,
    *,
    confirmed_voice_lock: Any,
    voice_asset_version: Any,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    audio_generation_request: Any = None,
    generation_result: Any = None,
    artifact_evidence: Any = None,
    audio_technical_validation: Any = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> "DialogueAssetVersion":
    return DialogueAssetVersion.from_mapping(
        value,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        audio_generation_request=audio_generation_request,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        audio_technical_validation=audio_technical_validation,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
    )


def validate_clone_dialogue_asset_version(
    value: Any,
    *,
    voice_asset_version: Any,
    audio_generation_request: Any,
    generation_result: Any,
    artifact_evidence: Any,
    audio_technical_validation: Any,
    confirmed_voice_lock: Any,
    voice_profile_version: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str,
    current_voice_profile_authority: Any = None,
) -> "DialogueAssetVersion":
    if not isinstance(value, Mapping) or value.get("schemaVersion") != (
        DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION
    ):
        raise AudioDomainTypeMismatchError(
            "clone DialogueAssetVersion v2 schema is required"
        )
    return DialogueAssetVersion._from_validated(
        _validate_clone_dialogue_asset_version(
            value,
            voice_asset_version=voice_asset_version,
            audio_generation_request=audio_generation_request,
            generation_result=generation_result,
            artifact_evidence=artifact_evidence,
            audio_technical_validation=audio_technical_validation,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_profile_version=voice_profile_version,
            consent_grant_version=consent_grant_version,
            source_recording_binding=source_recording_binding,
            evaluated_at=evaluated_at,
            current_voice_profile_authority=current_voice_profile_authority,
        )
    )


def _validate_voice_asset_version(
    value: Any,
    *,
    confirmed_voice_lock: Any,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    result = _common_asset(value, "VoiceAssetVersion")
    for field in (
        "voiceIdentityRef",
        "characterRef",
        "voiceLockVersionRef",
        "voiceSourceSubjectRef",
        "engineRef",
        "modelRef",
    ):
        _required_ref(result[field], field)
    _sha256(result["voiceLockDigest"], "voiceLockDigest")
    if result["voiceSourceKind"] not in VOICE_SOURCE_KINDS:
        raise AudioDomainTypeMismatchError("voiceSourceKind is invalid")
    package = _exact(
        result["profilePackage"],
        frozenset({"reusable", "packageKind", "packageDigest"}),
        "profilePackage",
    )
    if package["reusable"] is not True:
        raise EpisodeProductionError("voice profile package must be reusable")
    _text(package["packageKind"], "profilePackage.packageKind")
    _sha256(package["packageDigest"], "profilePackage.packageDigest")
    if package["packageDigest"] != result["artifact"]["fileDigest"]:
        raise StaleInputError("voice profile package digest is stale")
    _match_voice_asset_to_lock(result, confirmed_voice_lock)
    consent_ref = result["consentGrantRef"]
    consent_version_ref = result["consentGrantVersionRef"]
    consent_digest = result["consentGrantDigest"]
    if result["voiceSourceKind"] == "CLONED_WITH_CONSENT":
        if (
            consent_ref is None
            or consent_version_ref is None
            or consent_digest is None
            or consent_grant is None
        ):
            raise AudioConsentRequiredError("cloned voice requires ConsentGrant")
        if evaluated_at is None:
            raise AudioConsentRequiredError(
                "cloned voice consent requires an explicit evaluation time"
            )
        grant = require_effective_consent_grant(
            consent_grant,
            evaluated_at=evaluated_at,
            required_use=VOICE_CLONING_USE,
            expected_subject_ref=result["voiceSourceSubjectRef"],
            expected_grant_ref=consent_ref,
            expected_version_ref=consent_version_ref,
            expected_digest=consent_digest,
            expected_scope=tuple(
                result[field]
                for field in ("workspaceRef", "projectRef", "seriesRef")
            ),
        ).as_dict()
        rights = _validate_rights_binding(
            result["rightsBinding"],
            required_uses=frozenset(
                {"AUDIO_PRODUCTION", "VOICE_PROFILE_USE", "VOICE_CLONING"}
            ),
        )
        if (
            rights["rightsManifestRef"] != grant["rightsManifestRef"]
            or rights["rightsManifestDigest"] != grant["rightsManifestDigest"]
            or not any(
                source["sourceRef"] == grant["consentGrantVersionRef"]
                and source["sourceDigest"] == grant["payloadDigest"]
                for source in rights["sourceRefs"]
            )
        ):
            raise StaleInputError("voice consent rights binding is stale")
    elif (
        consent_ref is not None
        or consent_version_ref is not None
        or consent_digest is not None
    ):
        raise AudioDomainTypeMismatchError(
            "local preset voice cannot claim clone consent"
        )
    return result


def _validate_clone_voice_asset_version(
    value: Any,
    *,
    voice_profile_version: Any,
    confirmed_voice_lock: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str | None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> dict[str, Any]:
    result = _common_asset(
        value,
        "VoiceAssetVersion",
        schema_version=VOICE_ASSET_VERSION_V2_SCHEMA_VERSION,
        fields=_CLONE_VOICE_FIELDS,
    )
    for field in (
        "voiceIdentityRef",
        "characterRef",
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "voiceLockVersionRef",
        "voiceSourceSubjectRef",
        "sourceRecordingBindingRef",
        "consentGrantRef",
        "consentGrantVersionRef",
        "rightsBindingRef",
    ):
        _required_ref(result[field], field)
    _text(result["engineId"], "engineId")
    _text(result["modelId"], "modelId")
    if (
        result["engineId"] != CLONE_VOICE_ENGINE_FAMILY
        or result["modelId"] != CLONE_VOICE_MODEL_ID
    ):
        raise AudioDomainTypeMismatchError(
            "clone VoiceAssetVersion runtime identity is not the frozen "
            "zero-shot clone runtime"
        )
    if (
        not isinstance(result["engineCommit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", result["engineCommit"]) is None
    ):
        raise EpisodeProductionError("engineCommit must be a pinned commit SHA")
    for field in (
        "voiceProfileVersionDigest",
        "voiceLockVersionDigest",
        "sourceRecordingBindingDigest",
        "consentGrantVersionDigest",
        "rightsBindingDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
    ):
        _sha256(result[field], field)
    if result["voiceSourceKind"] != "CLONED_WITH_CONSENT":
        raise AudioDomainTypeMismatchError(
            "clone VoiceAssetVersion cannot represent a fixed preset voice"
        )

    source = _voice_lineage_wrapper(
        source_recording_binding,
        class_name="SourceVoiceRecordingAssetVersionBinding",
        label="source voice recording binding",
    )
    consent = _effective_clone_consent(
        consent_grant_version,
        evaluated_at=evaluated_at,
    )
    profile = _voice_lineage_wrapper(
        voice_profile_version,
        class_name="VoiceProfileVersion",
        label="VoiceProfileVersion",
    )
    lock_bundle = validate_confirmed_clone_voice_lock_bundle(
        confirmed_voice_lock
    )
    lock_root = lock_bundle["voiceLock"]
    lock_version = lock_bundle["voiceLockVersion"]
    confirmation = lock_bundle["voiceLockConfirmation"]
    rights = _validate_rights_binding(
        result["rightsBinding"],
        required_uses=frozenset(
            {"VOICE_CLONING", "VOICE_PROFILE_USE", "AUDIO_PRODUCTION"}
        ),
    )
    scope = tuple(
        result[field] for field in ("workspaceRef", "projectRef", "seriesRef")
    )
    if any(
        tuple(item[field] for field in ("workspaceRef", "projectRef", "seriesRef"))
        != scope
        for item in (source, consent, profile, lock_root, lock_version)
    ):
        raise StaleInputError("clone voice scope binding is stale")
    if (
        source["subjectRef"] != result["voiceSourceSubjectRef"]
        or consent["subjectRef"] != source["subjectRef"]
        or profile["subjectRef"] != source["subjectRef"]
        or lock_version["subjectRef"] != source["subjectRef"]
    ):
        raise StaleInputError("clone voice subject binding is stale")
    if (
        result["voiceIdentityRef"] != profile["voiceIdentityRef"]
        or result["voiceIdentityRef"] != lock_version["voiceIdentityRef"]
        or result["characterRef"] != lock_root["characterRef"]
        or result["voiceProfileRef"] != profile["voiceProfileRef"]
        or result["voiceProfileVersionRef"]
        != profile["voiceProfileVersionRef"]
        or result["voiceProfileVersionDigest"] != profile["payloadDigest"]
        or profile.get("status") != "CONFIRMED"
        or profile.get("confirmedAt") is None
    ):
        raise StaleInputError("clone VoiceProfileVersion binding is stale")
    if (
        result["voiceLockVersionRef"] != lock_version["voiceLockVersionRef"]
        or result["voiceLockVersionDigest"] != lock_version["payloadDigest"]
        or profile["voiceLockRef"] != lock_root["voiceRef"]
        or profile["voiceLockVersionRef"] != lock_version["voiceLockVersionRef"]
        or profile["voiceLockVersionDigest"] != lock_version["payloadDigest"]
        or profile["voiceLockConfirmationRef"]
        != confirmation["voiceLockConfirmationRef"]
        or profile["voiceLockConfirmationDigest"]
        != confirmation["payloadDigest"]
    ):
        raise StaleInputError("clone VoiceLock binding is stale")
    if (
        result["sourceRecordingBindingRef"]
        != source["sourceRecordingBindingRef"]
        or result["sourceRecordingBindingDigest"] != source["payloadDigest"]
        or consent["sourceRecordingBindingRef"]
        != source["sourceRecordingBindingRef"]
        or consent["sourceRecordingBindingDigest"] != source["payloadDigest"]
        or profile["sourceRecordingBindingRef"]
        != source["sourceRecordingBindingRef"]
        or profile["sourceRecordingBindingDigest"] != source["payloadDigest"]
        or lock_version["sourceRecordingBindingRef"]
        != source["sourceRecordingBindingRef"]
        or lock_version["sourceRecordingBindingDigest"] != source["payloadDigest"]
    ):
        raise StaleInputError("clone source-recording binding is stale")
    if (
        result["consentGrantRef"] != consent["consentGrantRef"]
        or result["consentGrantVersionRef"]
        != consent["consentGrantVersionRef"]
        or result["consentGrantVersionDigest"] != consent["payloadDigest"]
        or profile["consentGrantVersionRef"]
        != consent["consentGrantVersionRef"]
        or profile["consentGrantVersionDigest"] != consent["payloadDigest"]
        or lock_version["consentGrantVersionRef"]
        != consent["consentGrantVersionRef"]
        or lock_version["consentGrantVersionDigest"] != consent["payloadDigest"]
    ):
        raise StaleInputError("clone consent binding is stale")
    if (
        result["rightsBindingRef"] != rights["rightsBindingRef"]
        or result["rightsBindingDigest"] != rights["payloadDigest"]
        or consent["rightsBindingRef"] != rights["rightsBindingRef"]
        or consent["rightsBindingDigest"] != rights["payloadDigest"]
        or profile["rightsBindingRef"] != rights["rightsBindingRef"]
        or profile["rightsBindingDigest"] != rights["payloadDigest"]
        or lock_version["rightsBindingRef"] != rights["rightsBindingRef"]
        or lock_version["rightsBindingDigest"] != rights["payloadDigest"]
    ):
        raise StaleInputError("clone rights binding is stale")
    runtime_fields = (
        "engineId",
        "engineCommit",
        "modelId",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
    )
    if any(result[field] != profile[field] for field in runtime_fields):
        raise StaleInputError("clone runtime binding is stale")
    package = profile.get("profilePackage")
    if (
        not isinstance(package, Mapping)
        or result["artifact"]["fileDigest"] != package.get("fileDigest")
    ):
        raise StaleInputError("clone profile package artifact binding is stale")
    _current_clone_authority(
        current_voice_profile_authority,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        confirmed_voice_lock=confirmed_voice_lock,
        rights_binding=rights,
        evaluated_at=evaluated_at,
        required=require_current_authority,
        expected_scope=(
            result["workspaceRef"],
            result["projectRef"],
            result["seriesRef"],
            result["productionRunRef"],
        ),
    )
    return result


def validate_voice_asset_version(
    value: Any,
    *,
    confirmed_voice_lock: Any,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> "VoiceAssetVersion":
    return VoiceAssetVersion.from_mapping(
        value,
        confirmed_voice_lock=confirmed_voice_lock,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
    )


def validate_clone_voice_asset_version(
    value: Any,
    *,
    voice_profile_version: Any,
    confirmed_voice_lock: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str,
    current_voice_profile_authority: Any = None,
) -> "VoiceAssetVersion":
    if not isinstance(value, Mapping) or value.get("schemaVersion") != (
        VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
    ):
        raise AudioDomainTypeMismatchError(
            "clone VoiceAssetVersion v2 schema is required"
        )
    return VoiceAssetVersion._from_validated(
        _validate_clone_voice_asset_version(
            value,
            voice_profile_version=voice_profile_version,
            confirmed_voice_lock=confirmed_voice_lock,
            consent_grant_version=consent_grant_version,
            source_recording_binding=source_recording_binding,
            evaluated_at=evaluated_at,
            current_voice_profile_authority=current_voice_profile_authority,
        )
    )


def _validate_music_asset_version(value: Any) -> dict[str, Any]:
    result = _common_asset(value, "MusicAssetVersion")
    if result["musicSourceKind"] != "PROGRAMMATIC":
        raise AudioDomainTypeMismatchError("musicSourceKind is invalid")
    _sha256(result["musicSpecDigest"], "musicSpecDigest")
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def validate_music_asset_version(value: Any) -> "MusicAssetVersion":
    return MusicAssetVersion.from_mapping(value)


def _validate_sfx_asset_version(value: Any) -> dict[str, Any]:
    result = _common_asset(value, "SfxAssetVersion")
    _text(result["sfxKind"], "sfxKind")
    _sha256(result["synthesisSpecDigest"], "synthesisSpecDigest")
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def validate_sfx_asset_version(value: Any) -> "SfxAssetVersion":
    return SfxAssetVersion.from_mapping(value)


def _validate_ambience_asset_version(value: Any) -> dict[str, Any]:
    result = _common_asset(value, "AmbienceAssetVersion")
    _text(result["ambienceKind"], "ambienceKind")
    _sha256(result["synthesisSpecDigest"], "synthesisSpecDigest")
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def validate_ambience_asset_version(value: Any) -> "AmbienceAssetVersion":
    return AmbienceAssetVersion.from_mapping(value)


def validate_audio_domain_asset_version(
    value: Any,
    *,
    confirmed_voice_lock: Any = None,
    voice_asset_version: Any = None,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    audio_generation_request: Any = None,
    generation_result: Any = None,
    artifact_evidence: Any = None,
    audio_technical_validation: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> "_ImmutableContract":
    if not isinstance(value, Mapping):
        raise EpisodeProductionError("audio AssetVersion is invalid")
    asset_type = value.get("assetVersionType")
    if asset_type == "DialogueAssetVersion":
        return validate_dialogue_asset_version(
            value,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_asset_version=voice_asset_version,
            consent_grant=consent_grant,
            evaluated_at=evaluated_at,
            audio_generation_request=audio_generation_request,
            generation_result=generation_result,
            artifact_evidence=artifact_evidence,
            audio_technical_validation=audio_technical_validation,
            voice_profile_version=voice_profile_version,
            consent_grant_version=consent_grant_version,
            source_recording_binding=source_recording_binding,
            current_voice_profile_authority=current_voice_profile_authority,
            require_current_authority=require_current_authority,
        )
    if asset_type == "VoiceAssetVersion":
        return validate_voice_asset_version(
            value,
            confirmed_voice_lock=confirmed_voice_lock,
            consent_grant=consent_grant,
            evaluated_at=evaluated_at,
            voice_profile_version=voice_profile_version,
            consent_grant_version=consent_grant_version,
            source_recording_binding=source_recording_binding,
            current_voice_profile_authority=current_voice_profile_authority,
            require_current_authority=require_current_authority,
        )
    if asset_type == "MusicAssetVersion":
        return validate_music_asset_version(value)
    if asset_type == "SfxAssetVersion":
        return validate_sfx_asset_version(value)
    if asset_type == "AmbienceAssetVersion":
        return validate_ambience_asset_version(value)
    raise AudioDomainTypeMismatchError("unknown audio AssetVersion type")


def _request_spec(
    kind: str,
    value: Any,
    *,
    confirmed_voice_lock: Any,
    voice_asset_version: Any,
    consent_grant: Any,
    evaluated_at: str | None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EpisodeProductionError("requestSpec is invalid")
    result = deepcopy(dict(value))
    if kind in {"DIALOGUE_SYNTHESIS", "NARRATION_SYNTHESIS"}:
        fields = frozenset(
            {
                "speechRole",
                "scriptVersionRef",
                "scriptVersionDigest",
                "dialogueRef",
                "narrationRef",
                "voiceAssetVersionRef",
                "voiceAssetVersionDigest",
                "language",
                "normalizedSpeechParameters",
                "sourceAudioCueRefs",
            }
        )
        result = _exact(result, fields, "speech requestSpec")
        expected_role = "dialogue" if kind == "DIALOGUE_SYNTHESIS" else "narration"
        if result["speechRole"] != expected_role:
            raise AudioDomainTypeMismatchError("request speechRole is invalid")
        _required_ref(result["scriptVersionRef"], "scriptVersionRef")
        _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
        if expected_role == "dialogue":
            _required_ref(result["dialogueRef"], "dialogueRef")
            if result["narrationRef"] is not None:
                raise AudioDomainTypeMismatchError("dialogue request has narrationRef")
        else:
            _required_ref(result["narrationRef"], "narrationRef")
            if result["dialogueRef"] is not None:
                raise AudioDomainTypeMismatchError("narration request has dialogueRef")
        exact_voice_wrapper = type(voice_asset_version) is VoiceAssetVersion
        selected_voice_asset = (
            voice_asset_version.as_dict()
            if exact_voice_wrapper
            else voice_asset_version
        )
        clone_voice_requested = voice_profile_version is not None or (
            isinstance(selected_voice_asset, Mapping)
            and selected_voice_asset.get("schemaVersion")
            == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
        )
        if clone_voice_requested:
            if not exact_voice_wrapper:
                raise AudioDomainTypeMismatchError(
                    "clone speech request requires an exact VoiceAssetVersion wrapper"
                )
            voice = _validate_clone_voice_asset_version(
                selected_voice_asset,
                voice_profile_version=voice_profile_version,
                confirmed_voice_lock=confirmed_voice_lock,
                consent_grant_version=consent_grant_version,
                source_recording_binding=source_recording_binding,
                evaluated_at=evaluated_at,
                current_voice_profile_authority=current_voice_profile_authority,
                require_current_authority=require_current_authority,
            )
        else:
            voice = _validate_voice_asset_version(
                selected_voice_asset,
                confirmed_voice_lock=confirmed_voice_lock,
                consent_grant=consent_grant,
                evaluated_at=evaluated_at,
            )
        if (
            result["voiceAssetVersionRef"] != voice["assetVersionRef"]
            or result["voiceAssetVersionDigest"] != voice["payloadDigest"]
        ):
            raise StaleInputError("request voice AssetVersion binding is stale")
        _text(result["language"], "language")
        voice_lock_bundle = (
            validate_confirmed_clone_voice_lock_bundle(confirmed_voice_lock)
            if clone_voice_requested
            else _confirmed_voice(confirmed_voice_lock)
        )
        voice_version = voice_lock_bundle["voiceLockVersion"]
        if result["language"] != voice_version["languageCode"]:
            raise StaleInputError("speech request language binding is stale")
        normalizer = (
            normalize_clone_speech_parameters
            if clone_voice_requested
            else normalize_speech_parameters
        )
        normalized = normalizer(
            result["normalizedSpeechParameters"],
            confirmed_voice_lock=voice_lock_bundle,
        )
        if normalized != result["normalizedSpeechParameters"]:
            raise StaleInputError("request speech parameters are not normalized")
        _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
        return result
    if kind == "VOICE_PROFILE_CREATION":
        fields = frozenset(
            {
                "voiceIdentityRef",
                "voiceLockVersionRef",
                "voiceLockDigest",
                "voiceSourceKind",
                "voiceSourceSubjectRef",
                "engineRef",
                "modelRef",
                "profilePackageSpec",
                "consentGrantRef",
                "consentGrantVersionRef",
                "consentGrantDigest",
            }
        )
        result = _exact(result, fields, "voice requestSpec")
        bundle = _confirmed_voice(confirmed_voice_lock)
        root = bundle["voiceLock"]
        version = bundle["voiceLockVersion"]
        if (
            result["voiceIdentityRef"] != root["voiceRef"]
            or result["voiceLockVersionRef"] != version["voiceLockVersionRef"]
            or result["voiceLockDigest"] != version["payloadDigest"]
            or result["engineRef"] != version["engineFamily"]
            or result["modelRef"] != version["voiceId"]
        ):
            raise StaleInputError("voice request VoiceLock binding is stale")
        _required_ref(result["voiceSourceSubjectRef"], "voiceSourceSubjectRef")
        if result["voiceSourceKind"] not in VOICE_SOURCE_KINDS:
            raise AudioDomainTypeMismatchError("voiceSourceKind is invalid")
        package_spec = _exact(
            result["profilePackageSpec"],
            frozenset({"reusable", "packageKind"}),
            "profilePackageSpec",
        )
        if package_spec["reusable"] is not True:
            raise EpisodeProductionError("voice profile package must be reusable")
        _text(package_spec["packageKind"], "profilePackageSpec.packageKind")
        if result["voiceSourceKind"] == "CLONED_WITH_CONSENT":
            if (
                result["consentGrantRef"] is None
                or result["consentGrantVersionRef"] is None
                or result["consentGrantDigest"] is None
                or consent_grant is None
                or evaluated_at is None
            ):
                raise AudioConsentRequiredError(
                    "cloned voice request requires effective ConsentGrant"
                )
            require_effective_consent_grant(
                consent_grant,
                evaluated_at=evaluated_at,
                required_use=VOICE_CLONING_USE,
                expected_subject_ref=result["voiceSourceSubjectRef"],
                expected_grant_ref=result["consentGrantRef"],
                expected_version_ref=result["consentGrantVersionRef"],
                expected_digest=result["consentGrantDigest"],
                expected_scope=tuple(
                    root[field]
                    for field in ("workspaceRef", "projectRef", "seriesRef")
                ),
            )
        elif (
            result["consentGrantRef"] is not None
            or result["consentGrantVersionRef"] is not None
            or result["consentGrantDigest"] is not None
        ):
            raise AudioDomainTypeMismatchError(
                "local preset voice request cannot claim clone consent"
            )
        return result
    variants = {
        "MUSIC_GENERATION": ("musicSourceKind", "musicSpecDigest"),
        "SFX_GENERATION": ("sfxKind", "synthesisSpecDigest"),
        "AMBIENCE_GENERATION": ("ambienceKind", "synthesisSpecDigest"),
    }
    kind_field, digest_field = variants[kind]
    result = _exact(
        result,
        frozenset({kind_field, digest_field, "sourceAudioCueRefs"}),
        f"{kind} requestSpec",
    )
    _text(result[kind_field], kind_field)
    if kind == "MUSIC_GENERATION" and result[kind_field] != "PROGRAMMATIC":
        raise AudioDomainTypeMismatchError("musicSourceKind is invalid")
    _sha256(result[digest_field], digest_field)
    _deferred_audio_cue_refs(result["sourceAudioCueRefs"])
    return result


def _m9_generation_request_fields(value: Any) -> frozenset[str]:
    if not isinstance(value, Mapping):
        raise EpisodeProductionError("AudioGenerationRequest is invalid")
    kind = value.get("requestKind")
    fields = set(_GENERATION_REQUEST_FIELDS | _M9_AUDIO_BINDING_BASE_FIELDS)
    if kind in {"DIALOGUE_SYNTHESIS", "NARRATION_SYNTHESIS"}:
        fields.update({"sourceSpan", "sourceTextDigest"})
    if kind == "DIALOGUE_SYNTHESIS":
        fields.add("speakerCharacterRef")
    if "voiceLineage" in value:
        fields.add("voiceLineage")
    return frozenset(fields)


def _m9_voice_asset_mapping(value: Any) -> Mapping[str, Any] | None:
    if type(value) is VoiceAssetVersion:
        return value.as_dict()
    if isinstance(value, Mapping):
        return value
    return None


def _validate_m9_audio_binding(
    result: Mapping[str, Any],
    *,
    audio_requirement: Any = None,
    execution_method_plan: Any = None,
    voice_asset_version: Any = None,
) -> None:
    expected_role = _M9_AUDIO_ROLE_BY_REQUEST_KIND.get(result["requestKind"])
    if expected_role is None or result["audioRole"] != expected_role:
        raise AudioDomainTypeMismatchError(
            "M9-bound AudioGenerationRequest role is invalid"
        )
    for field in (
        "audioRequirementRef",
        "executionMethodPlanVersionRef",
        "scriptVersionRef",
        "creativeShotVersionRef",
    ):
        _required_ref(result[field], field)
    for field in (
        "audioRequirementDigest",
        "executionMethodPlanDigest",
        "scriptVersionDigest",
        "creativeShotVersionDigest",
    ):
        _sha256(result[field], field)
    if (
        result["assetRequirementRef"] != result["audioRequirementRef"]
        or result["assetRequirementDigest"] != result["audioRequirementDigest"]
    ):
        raise StaleInputError(
            "AudioGenerationRequest M9 requirement binding is stale"
        )

    timing = _exact(
        result["timingReference"],
        _M9_TIMING_REFERENCE_FIELDS,
        "timingReference",
    )
    start = timing["startFrameInclusive"]
    end = timing["endFrameExclusive"]
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or start < 0
        or isinstance(end, bool)
        or not isinstance(end, int)
        or end <= start
    ):
        raise EpisodeProductionError("timingReference is invalid")

    speech = expected_role in {"dialogue", "narration"}
    if speech:
        span = _exact(
            result["sourceSpan"], _M9_SOURCE_SPAN_FIELDS, "sourceSpan"
        )
        for field in ("scriptSceneRef", "sourceField"):
            _required_ref(span[field], f"sourceSpan.{field}")
        source_index = span["sourceIndex"]
        span_start = span["startOffsetInclusive"]
        span_end = span["endOffsetExclusive"]
        if (
            span["sourceField"]
            != ("DIALOGUE" if expected_role == "dialogue" else "NARRATION")
            or isinstance(source_index, bool)
            or not isinstance(source_index, int)
            or source_index < 0
            or isinstance(span_start, bool)
            or not isinstance(span_start, int)
            or span_start < 0
            or isinstance(span_end, bool)
            or not isinstance(span_end, int)
            or span_end <= span_start
        ):
            raise EpisodeProductionError("sourceSpan is invalid")
        _sha256(result["sourceTextDigest"], "sourceTextDigest")
        request_spec = result["requestSpec"]
        if (
            request_spec["scriptVersionRef"] != result["scriptVersionRef"]
            or request_spec["scriptVersionDigest"]
            != result["scriptVersionDigest"]
            or sha256(
                request_spec["normalizedSpeechParameters"]["text"].encode(
                    "utf-8"
                )
            ).hexdigest()
            != result["sourceTextDigest"]
        ):
            raise StaleInputError(
                "AudioGenerationRequest source authority is stale"
            )
    if expected_role == "dialogue":
        _required_ref(result["speakerCharacterRef"], "speakerCharacterRef")

    selected_voice = _m9_voice_asset_mapping(voice_asset_version)
    clone_requested = (
        speech
        and isinstance(selected_voice, Mapping)
        and selected_voice.get("schemaVersion")
        == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
    )
    lineage = result.get("voiceLineage")
    if clone_requested:
        lineage = _exact(
            lineage, _M9_CLONE_LINEAGE_FIELDS, "voiceLineage"
        )
        for field in (
            "consentGrantRef",
            "consentGrantVersionRef",
            "voiceLockVersionRef",
            "voiceProfileRef",
            "voiceProfileVersionRef",
        ):
            _required_ref(lineage[field], f"voiceLineage.{field}")
        for field in (
            "consentGrantVersionDigest",
            "voiceLockVersionDigest",
            "voiceProfileVersionDigest",
        ):
            _sha256(lineage[field], f"voiceLineage.{field}")
        expected_lineage = {
            "consentGrantRef": selected_voice["consentGrantRef"],
            "consentGrantVersionRef": selected_voice[
                "consentGrantVersionRef"
            ],
            "consentGrantVersionDigest": selected_voice[
                "consentGrantVersionDigest"
            ],
            "voiceLockVersionRef": selected_voice["voiceLockVersionRef"],
            "voiceLockVersionDigest": selected_voice[
                "voiceLockVersionDigest"
            ],
            "voiceProfileRef": selected_voice["voiceProfileRef"],
            "voiceProfileVersionRef": selected_voice[
                "voiceProfileVersionRef"
            ],
            "voiceProfileVersionDigest": selected_voice[
                "voiceProfileVersionDigest"
            ],
        }
        if lineage != expected_lineage:
            raise StaleInputError("clone request voice lineage is stale")
    elif lineage is not None:
        raise AudioDomainTypeMismatchError(
            "non-clone AudioGenerationRequest cannot claim clone lineage"
        )

    if audio_requirement is not None:
        if not isinstance(audio_requirement, Mapping):
            raise EpisodeProductionError("AudioRequirement is invalid")
        expected_type = {
            "dialogue": "DIALOGUE",
            "narration": "NARRATION",
            "sfx": "SFX",
            "ambience": "AMBIENCE",
        }[expected_role]
        comparisons = {
            "audioRequirementRef": audio_requirement.get(
                "audioRequirementRef"
            ),
            "audioRequirementDigest": audio_requirement.get("payloadDigest"),
            "scriptVersionRef": audio_requirement.get("scriptVersionRef"),
            "scriptVersionDigest": audio_requirement.get("scriptVersionDigest"),
            "creativeShotVersionRef": audio_requirement.get(
                "creativeShotVersionRef"
            ),
            "creativeShotVersionDigest": audio_requirement.get(
                "creativeShotVersionDigest"
            ),
            "timingReference": audio_requirement.get("timingReference"),
        }
        if (
            audio_requirement.get("audioType") != expected_type
            or any(result[field] != expected for field, expected in comparisons.items())
        ):
            raise StaleInputError("AudioRequirement binding is stale")
        if speech and (
            result["sourceSpan"] != audio_requirement.get("sourceSpan")
            or result["sourceTextDigest"]
            != audio_requirement.get("sourceTextDigest")
        ):
            raise StaleInputError("AudioRequirement source binding is stale")
        if expected_role == "dialogue" and result[
            "speakerCharacterRef"
        ] != audio_requirement.get("speakerCharacterRef"):
            raise StaleInputError("AudioRequirement speaker binding is stale")

    if execution_method_plan is not None:
        if not isinstance(execution_method_plan, Mapping):
            raise EpisodeProductionError("ExecutionMethodPlanVersion is invalid")
        if (
            result["executionMethodPlanVersionRef"]
            != execution_method_plan.get("executionMethodPlanVersionRef")
            or result["executionMethodPlanDigest"]
            != execution_method_plan.get("payloadDigest")
            or not any(
                isinstance(item, Mapping)
                and item.get("audioRequirementRef")
                == result["audioRequirementRef"]
                and item.get("payloadDigest")
                == result["audioRequirementDigest"]
                for item in execution_method_plan.get("audioRequirements", [])
            )
            or not any(
                isinstance(item, Mapping)
                and item.get("creativeShotVersionRef")
                == result["creativeShotVersionRef"]
                and item.get("payloadDigest")
                == result["creativeShotVersionDigest"]
                for item in execution_method_plan.get(
                    "creativeShotVersions", []
                )
            )
        ):
            raise StaleInputError("ExecutionMethodPlanVersion binding is stale")


def _validate_audio_generation_request(
    value: Any,
    *,
    confirmed_voice_lock: Any = None,
    voice_asset_version: Any = None,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
    audio_requirement: Any = None,
    execution_method_plan: Any = None,
) -> dict[str, Any]:
    if (
        isinstance(value, Mapping)
        and value.get("schemaVersion")
        == AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION
    ):
        result = _verify_sealed(
            value,
            _m9_generation_request_fields(value),
            "AudioGenerationRequest v2",
        )
        legacy = {
            field: deepcopy(result[field])
            for field in _GENERATION_REQUEST_FIELDS
            if field not in {"schemaVersion", "payloadDigest"}
        }
        legacy = _seal(
            {
                "schemaVersion": AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
                **legacy,
            }
        )
        _validate_audio_generation_request(
            legacy,
            confirmed_voice_lock=confirmed_voice_lock,
            voice_asset_version=voice_asset_version,
            consent_grant=consent_grant,
            evaluated_at=evaluated_at,
            voice_profile_version=voice_profile_version,
            consent_grant_version=consent_grant_version,
            source_recording_binding=source_recording_binding,
            current_voice_profile_authority=current_voice_profile_authority,
            require_current_authority=require_current_authority,
        )
        _validate_m9_audio_binding(
            result,
            audio_requirement=audio_requirement,
            execution_method_plan=execution_method_plan,
            voice_asset_version=voice_asset_version,
        )
        return result
    result = _verify_sealed(
        value, _GENERATION_REQUEST_FIELDS, "AudioGenerationRequest"
    )
    if result["schemaVersion"] != AUDIO_GENERATION_REQUEST_SCHEMA_VERSION:
        raise EpisodeProductionError("AudioGenerationRequest schema is unsupported")
    kind = result["requestKind"]
    if kind not in AUDIO_REQUEST_KINDS:
        raise AudioDomainTypeMismatchError("audio requestKind is invalid")
    _scope(result)
    for field in (
        "generationRequestRef",
        "generationRequestVersionRef",
        "assetRequirementRef",
        "createdBy",
    ):
        _required_ref(result[field], field)
    version = _positive_int(result["version"], "version")
    _parent(
        version,
        result["supersedesGenerationRequestVersionRef"],
        result["supersedesGenerationRequestVersionDigest"],
        ref_field="supersedesGenerationRequestVersionRef",
        digest_field="supersedesGenerationRequestVersionDigest",
    )
    if (
        result["supersedesGenerationRequestVersionRef"]
        == result["generationRequestVersionRef"]
    ):
        raise EpisodeProductionError(
            "AudioGenerationRequest cannot supersede itself"
        )
    _sha256(result["assetRequirementDigest"], "assetRequirementDigest")
    if (
        result["outputAssetVersionType"] != _OUTPUT_TYPE_BY_REQUEST_KIND[kind]
        or result["outputTarget"] != "ASSET_VERSION"
    ):
        raise LegacyAudioTargetError("audio request target is invalid")
    request_spec = _request_spec(
        kind,
        result["requestSpec"],
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
    )
    is_clone_speech_request = False
    if kind in {"DIALOGUE_SYNTHESIS", "NARRATION_SYNTHESIS"}:
        selected_voice = (
            voice_asset_version.as_dict()
            if type(voice_asset_version) is VoiceAssetVersion
            else voice_asset_version
        )
        is_clone_speech_request = voice_profile_version is not None or (
            isinstance(selected_voice, Mapping)
            and selected_voice.get("schemaVersion")
            == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
        )
        if is_clone_speech_request:
            full_scope_fields = (
                "workspaceRef",
                "projectRef",
                "seriesRef",
                "episodeRef",
                "productionRunRef",
            )
            if tuple(result[field] for field in full_scope_fields) != tuple(
                selected_voice.get(field) for field in full_scope_fields
            ):
                raise StaleInputError(
                    "clone audio request VoiceAsset production scope is stale"
                )
    if kind in {
        "DIALOGUE_SYNTHESIS",
        "NARRATION_SYNTHESIS",
        "VOICE_PROFILE_CREATION",
    }:
        bundle = (
            validate_confirmed_clone_voice_lock_bundle(confirmed_voice_lock)
            if is_clone_speech_request
            else _confirmed_voice(confirmed_voice_lock)
        )
        root = bundle["voiceLock"]
        if tuple(result[field] for field in ("workspaceRef", "projectRef", "seriesRef")) != tuple(
            root[field] for field in ("workspaceRef", "projectRef", "seriesRef")
        ):
            raise StaleInputError("audio request VoiceLock scope is stale")
    try:
        required_rights_uses = _RIGHTS_USES_BY_REQUEST_KIND[kind]
        if (
            kind == "VOICE_PROFILE_CREATION"
            and request_spec["voiceSourceKind"] == "CLONED_WITH_CONSENT"
        ):
            required_rights_uses = required_rights_uses | {"VOICE_CLONING"}
        rights = _validate_rights_binding(
            result["rightsBinding"],
            required_uses=frozenset(required_rights_uses),
        )
    except EpisodeProductionError as exc:
        if isinstance(exc, AudioRightsRequiredError):
            raise
        raise AudioRightsRequiredError("audio request rights binding is invalid") from exc
    if not any(
        source["sourceRef"] == result["assetRequirementRef"]
        and source["sourceDigest"] == result["assetRequirementDigest"]
        for source in rights["sourceRefs"]
    ):
        raise AudioRightsRequiredError(
            "RightsBinding does not cover the audio request AssetRequirement"
        )
    if (
        kind == "VOICE_PROFILE_CREATION"
        and request_spec["voiceSourceKind"] == "CLONED_WITH_CONSENT"
    ):
        grant = ConsentGrant.from_mapping(consent_grant).as_dict()
        if (
            rights["rightsManifestRef"] != grant["rightsManifestRef"]
            or rights["rightsManifestDigest"] != grant["rightsManifestDigest"]
            or not any(
                source["sourceRef"] == grant["consentGrantVersionRef"]
                and source["sourceDigest"] == grant["payloadDigest"]
                for source in rights["sourceRefs"]
            )
        ):
            raise StaleInputError("voice request consent rights binding is stale")
    requested_provenance = _validate_requested_provenance(
        result["requestedProvenance"]
    )
    if (
        is_clone_speech_request
        and requested_provenance["parametersDigest"]
        != _digest(request_spec["normalizedSpeechParameters"])
    ):
        raise StaleInputError(
            "clone speech requested parameters digest is stale"
        )
    if not any(
        source["sourceRef"] == result["assetRequirementRef"]
        and source["sourceDigest"] == result["assetRequirementDigest"]
        for source in requested_provenance["sourceRefs"]
    ):
        raise AudioProvenanceRequiredError(
            "requested provenance does not cover the AssetRequirement"
        )
    if (
        result["state"] != "CONTRACT_ONLY_ADAPTER_REQUIRED"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise EpisodeProductionError("AudioGenerationRequest lifecycle is invalid")
    _timestamp(result["createdAt"], "createdAt")
    return result


def validate_audio_generation_request(
    value: Any,
    *,
    confirmed_voice_lock: Any = None,
    voice_asset_version: Any = None,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
    require_current_authority: bool = False,
    audio_requirement: Any = None,
    execution_method_plan: Any = None,
) -> "AudioGenerationRequest":
    return AudioGenerationRequest.from_mapping(
        value,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=require_current_authority,
        audio_requirement=audio_requirement,
        execution_method_plan=execution_method_plan,
    )


def build_audio_generation_request(
    command: Mapping[str, Any],
    *,
    confirmed_voice_lock: Any = None,
    voice_asset_version: Any = None,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
) -> dict[str, Any]:
    fields = _GENERATION_REQUEST_FIELDS - {
        "schemaVersion",
        "state",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
    value = _exact(command, fields, "AudioGenerationRequest command")
    request_spec = value.get("requestSpec")
    if (
        value.get("requestKind") == "VOICE_PROFILE_CREATION"
        and isinstance(request_spec, Mapping)
        and request_spec.get("voiceSourceKind") == "CLONED_WITH_CONSENT"
    ):
        raise AudioDomainTypeMismatchError(
            "new cloned voices cannot use the legacy voice-profile request path"
        )
    selected_voice_asset = (
        voice_asset_version.as_dict()
        if type(voice_asset_version) is VoiceAssetVersion
        else voice_asset_version
    )
    if (
        value.get("requestKind")
        in {"DIALOGUE_SYNTHESIS", "NARRATION_SYNTHESIS"}
        and isinstance(selected_voice_asset, Mapping)
        and selected_voice_asset.get("schemaVersion")
        == VOICE_ASSET_VERSION_SCHEMA_VERSION
        and selected_voice_asset.get("voiceSourceKind")
        == "CLONED_WITH_CONSENT"
    ):
        raise AudioDomainTypeMismatchError(
            "new clone speech requests require VoiceAssetVersion v2"
        )
    result = _seal(
        {
            "schemaVersion": AUDIO_GENERATION_REQUEST_SCHEMA_VERSION,
            **value,
            "state": "CONTRACT_ONLY_ADAPTER_REQUIRED",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return validate_audio_generation_request(
        result,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=True,
    ).as_dict()


def build_m9_audio_generation_request(
    command: Mapping[str, Any],
    *,
    audio_requirement: Mapping[str, Any],
    execution_method_plan: Mapping[str, Any],
    confirmed_voice_lock: Any = None,
    voice_asset_version: Any = None,
    consent_grant: Any = None,
    evaluated_at: str | None = None,
    voice_profile_version: Any = None,
    consent_grant_version: Any = None,
    source_recording_binding: Any = None,
    current_voice_profile_authority: Any = None,
) -> dict[str, Any]:
    """Build an additive request bound to one current explicit M9 requirement.

    ``command`` is the existing v1 command shape.  All M9 fields are derived
    from the already validated requirement and plan; callers cannot submit or
    override source spans, speaker identity, timing or upstream digests.
    """

    if not isinstance(audio_requirement, Mapping) or not isinstance(
        execution_method_plan, Mapping
    ):
        raise EpisodeProductionError("M9 audio request authority is invalid")
    audio_type = audio_requirement.get("audioType")
    expected_kind = {
        "DIALOGUE": "DIALOGUE_SYNTHESIS",
        "NARRATION": "NARRATION_SYNTHESIS",
        "SFX": "SFX_GENERATION",
        "AMBIENCE": "AMBIENCE_GENERATION",
    }.get(audio_type)
    if expected_kind is None or command.get("requestKind") != expected_kind:
        raise AudioDomainTypeMismatchError(
            "AudioRequirement cannot create this AudioGenerationRequest"
        )
    base = build_audio_generation_request(
        command,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
    )
    result = {
        key: deepcopy(value)
        for key, value in base.items()
        if key not in {"schemaVersion", "payloadDigest"}
    }
    result.update(
        {
            "schemaVersion": AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION,
            "audioRequirementRef": audio_requirement["audioRequirementRef"],
            "audioRequirementDigest": audio_requirement["payloadDigest"],
            "executionMethodPlanVersionRef": execution_method_plan[
                "executionMethodPlanVersionRef"
            ],
            "executionMethodPlanDigest": execution_method_plan["payloadDigest"],
            "scriptVersionRef": audio_requirement["scriptVersionRef"],
            "scriptVersionDigest": audio_requirement["scriptVersionDigest"],
            "creativeShotVersionRef": audio_requirement[
                "creativeShotVersionRef"
            ],
            "creativeShotVersionDigest": audio_requirement[
                "creativeShotVersionDigest"
            ],
            "audioRole": str(audio_type).lower(),
            "timingReference": deepcopy(audio_requirement["timingReference"]),
        }
    )
    if audio_type in {"DIALOGUE", "NARRATION"}:
        result["sourceSpan"] = deepcopy(audio_requirement["sourceSpan"])
        result["sourceTextDigest"] = audio_requirement["sourceTextDigest"]
    if audio_type == "DIALOGUE":
        result["speakerCharacterRef"] = audio_requirement[
            "speakerCharacterRef"
        ]
    selected_voice = _m9_voice_asset_mapping(voice_asset_version)
    if (
        isinstance(selected_voice, Mapping)
        and selected_voice.get("schemaVersion")
        == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
    ):
        result["voiceLineage"] = {
            "consentGrantRef": selected_voice["consentGrantRef"],
            "consentGrantVersionRef": selected_voice[
                "consentGrantVersionRef"
            ],
            "consentGrantVersionDigest": selected_voice[
                "consentGrantVersionDigest"
            ],
            "voiceLockVersionRef": selected_voice["voiceLockVersionRef"],
            "voiceLockVersionDigest": selected_voice[
                "voiceLockVersionDigest"
            ],
            "voiceProfileRef": selected_voice["voiceProfileRef"],
            "voiceProfileVersionRef": selected_voice[
                "voiceProfileVersionRef"
            ],
            "voiceProfileVersionDigest": selected_voice[
                "voiceProfileVersionDigest"
            ],
        }
    sealed = _seal(result)
    return validate_audio_generation_request(
        sealed,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_asset_version=voice_asset_version,
        consent_grant=consent_grant,
        evaluated_at=evaluated_at,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=(
            isinstance(selected_voice, Mapping)
            and selected_voice.get("schemaVersion")
            == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
        ),
        audio_requirement=audio_requirement,
        execution_method_plan=execution_method_plan,
    ).as_dict()


def _build_asset_version(
    asset_version_type: str,
    command: Mapping[str, Any],
    **validation: Any,
) -> dict[str, Any]:
    fields = _ASSET_FIELDS_BY_TYPE[asset_version_type] - {
        "schemaVersion",
        "assetVersionType",
        "assetKind",
        "audioKind",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
    value = _exact(command, fields, f"{asset_version_type} command")
    result = _seal(
        {
            "schemaVersion": _SCHEMA_BY_TYPE[asset_version_type],
            "assetVersionType": asset_version_type,
            **value,
            "assetKind": "audio",
            "audioKind": _AUDIO_KIND_BY_TYPE[asset_version_type],
            "state": "PROPOSED",
            "authorityState": "CONTRACT_ONLY_NOT_ADMITTED",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return validate_audio_domain_asset_version(result, **validation).as_dict()


def _build_clone_asset_version(
    asset_version_type: str,
    command: Mapping[str, Any],
    **validation: Any,
) -> dict[str, Any]:
    contract = {
        "VoiceAssetVersion": (
            VOICE_ASSET_VERSION_V2_SCHEMA_VERSION,
            _CLONE_VOICE_FIELDS,
        ),
        "DialogueAssetVersion": (
            DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION,
            _CLONE_DIALOGUE_FIELDS,
        ),
    }.get(asset_version_type)
    if contract is None:
        raise AudioDomainTypeMismatchError("clone audio AssetVersion type is invalid")
    schema_version, fields = contract
    command_fields = fields - {
        "schemaVersion",
        "assetVersionType",
        "assetKind",
        "audioKind",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
    value = _exact(command, command_fields, f"clone {asset_version_type} command")
    result = _seal(
        {
            "schemaVersion": schema_version,
            "assetVersionType": asset_version_type,
            **value,
            "assetKind": "audio",
            "audioKind": _AUDIO_KIND_BY_TYPE[asset_version_type],
            "state": "PROPOSED",
            "authorityState": "CONTRACT_ONLY_NOT_ADMITTED",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return validate_audio_domain_asset_version(result, **validation).as_dict()


def build_dialogue_asset_version(
    command: Mapping[str, Any], **validation: Any
) -> dict[str, Any]:
    selected_voice_asset = validation.get("voice_asset_version")
    if type(selected_voice_asset) is VoiceAssetVersion:
        selected_voice_asset = selected_voice_asset.as_dict()
    if (
        isinstance(selected_voice_asset, Mapping)
        and selected_voice_asset.get("voiceSourceKind")
        == "CLONED_WITH_CONSENT"
    ):
        raise AudioDomainTypeMismatchError(
            "new clone dialogue assets require DialogueAssetVersion v2"
        )
    return _build_asset_version("DialogueAssetVersion", command, **validation)


def build_voice_asset_version(
    command: Mapping[str, Any], **validation: Any
) -> dict[str, Any]:
    if (
        isinstance(command, Mapping)
        and command.get("voiceSourceKind") == "CLONED_WITH_CONSENT"
    ):
        raise AudioDomainTypeMismatchError(
            "new cloned voices require VoiceAssetVersion v2"
        )
    return _build_asset_version("VoiceAssetVersion", command, **validation)


def build_clone_voice_asset_version(
    command: Mapping[str, Any],
    *,
    voice_profile_version: Any,
    confirmed_voice_lock: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str,
    current_voice_profile_authority: Any,
) -> dict[str, Any]:
    return _build_clone_asset_version(
        "VoiceAssetVersion",
        command,
        voice_profile_version=voice_profile_version,
        confirmed_voice_lock=confirmed_voice_lock,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        evaluated_at=evaluated_at,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=True,
    )


def build_clone_dialogue_asset_version(
    command: Mapping[str, Any],
    *,
    voice_asset_version: Any,
    audio_generation_request: Any,
    generation_result: Any,
    artifact_evidence: Any,
    audio_technical_validation: Any,
    confirmed_voice_lock: Any,
    voice_profile_version: Any,
    consent_grant_version: Any,
    source_recording_binding: Any,
    evaluated_at: str,
    current_voice_profile_authority: Any,
) -> dict[str, Any]:
    return _build_clone_asset_version(
        "DialogueAssetVersion",
        command,
        voice_asset_version=voice_asset_version,
        audio_generation_request=audio_generation_request,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        audio_technical_validation=audio_technical_validation,
        confirmed_voice_lock=confirmed_voice_lock,
        voice_profile_version=voice_profile_version,
        consent_grant_version=consent_grant_version,
        source_recording_binding=source_recording_binding,
        evaluated_at=evaluated_at,
        current_voice_profile_authority=current_voice_profile_authority,
        require_current_authority=True,
    )


def build_music_asset_version(command: Mapping[str, Any]) -> dict[str, Any]:
    return _build_asset_version("MusicAssetVersion", command)


def build_sfx_asset_version(command: Mapping[str, Any]) -> dict[str, Any]:
    return _build_asset_version("SfxAssetVersion", command)


def build_ambience_asset_version(command: Mapping[str, Any]) -> dict[str, Any]:
    return _build_asset_version("AmbienceAssetVersion", command)


@dataclass(frozen=True, slots=True, init=False)
class _ImmutableContract:
    _payload_json: str

    @classmethod
    def _from_validated(cls, value: Mapping[str, Any]):
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(value))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


class RightsBinding(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RightsBinding":
        return cls._from_validated(_validate_rights_binding(value))


class ConsentGrant(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "ConsentGrant":
        return cls._from_validated(_validate_consent_grant(value))


class AudioGenerationRequest(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any, **validation: Any) -> "AudioGenerationRequest":
        return cls._from_validated(
            _validate_audio_generation_request(value, **validation)
        )


class DialogueAssetVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any, **validation: Any) -> "DialogueAssetVersion":
        if (
            isinstance(value, Mapping)
            and value.get("schemaVersion")
            == DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION
        ):
            return cls._from_validated(
                _validate_clone_dialogue_asset_version(
                    value,
                    voice_asset_version=validation.get("voice_asset_version"),
                    audio_generation_request=validation.get(
                        "audio_generation_request"
                    ),
                    generation_result=validation.get("generation_result"),
                    artifact_evidence=validation.get("artifact_evidence"),
                    audio_technical_validation=validation.get(
                        "audio_technical_validation"
                    ),
                    confirmed_voice_lock=validation.get("confirmed_voice_lock"),
                    voice_profile_version=validation.get("voice_profile_version"),
                    consent_grant_version=validation.get("consent_grant_version"),
                    source_recording_binding=validation.get(
                        "source_recording_binding"
                    ),
                    evaluated_at=validation.get("evaluated_at"),
                    current_voice_profile_authority=validation.get(
                        "current_voice_profile_authority"
                    ),
                    require_current_authority=validation.get(
                        "require_current_authority", False
                    ),
                )
            )
        return cls._from_validated(
            _validate_dialogue_asset_version(
                value,
                confirmed_voice_lock=validation.get("confirmed_voice_lock"),
                voice_asset_version=validation.get("voice_asset_version"),
                consent_grant=validation.get("consent_grant"),
                evaluated_at=validation.get("evaluated_at"),
            )
        )


class VoiceAssetVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any, **validation: Any) -> "VoiceAssetVersion":
        if (
            isinstance(value, Mapping)
            and value.get("schemaVersion") == VOICE_ASSET_VERSION_V2_SCHEMA_VERSION
        ):
            return cls._from_validated(
                _validate_clone_voice_asset_version(
                    value,
                    voice_profile_version=validation.get("voice_profile_version"),
                    confirmed_voice_lock=validation.get("confirmed_voice_lock"),
                    consent_grant_version=validation.get("consent_grant_version"),
                    source_recording_binding=validation.get(
                        "source_recording_binding"
                    ),
                    evaluated_at=validation.get("evaluated_at"),
                    current_voice_profile_authority=validation.get(
                        "current_voice_profile_authority"
                    ),
                    require_current_authority=validation.get(
                        "require_current_authority", False
                    ),
                )
            )
        return cls._from_validated(
            _validate_voice_asset_version(
                value,
                confirmed_voice_lock=validation.get("confirmed_voice_lock"),
                consent_grant=validation.get("consent_grant"),
                evaluated_at=validation.get("evaluated_at"),
            )
        )


class MusicAssetVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MusicAssetVersion":
        return cls._from_validated(_validate_music_asset_version(value))


class SfxAssetVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "SfxAssetVersion":
        return cls._from_validated(_validate_sfx_asset_version(value))


class AmbienceAssetVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "AmbienceAssetVersion":
        return cls._from_validated(_validate_ambience_asset_version(value))


__all__ = [
    "AMBIENCE_ASSET_VERSION_SCHEMA_VERSION",
    "AUDIO_ASSET_VERSION_TYPES",
    "AUDIO_GENERATION_REQUEST_SCHEMA_VERSION",
    "AUDIO_GENERATION_REQUEST_V2_SCHEMA_VERSION",
    "AUDIO_PROVENANCE_SCHEMA_VERSION",
    "AUDIO_REQUESTED_PROVENANCE_SCHEMA_VERSION",
    "AUDIO_RIGHTS_BINDING_SCHEMA_VERSION",
    "CONSENT_GRANT_SCHEMA_VERSION",
    "DIALOGUE_ASSET_VERSION_SCHEMA_VERSION",
    "DIALOGUE_ASSET_VERSION_V2_SCHEMA_VERSION",
    "MUSIC_ASSET_VERSION_SCHEMA_VERSION",
    "SFX_ASSET_VERSION_SCHEMA_VERSION",
    "VOICE_ASSET_VERSION_SCHEMA_VERSION",
    "VOICE_ASSET_VERSION_V2_SCHEMA_VERSION",
    "AmbienceAssetVersion",
    "AudioConsentNotEffectiveError",
    "AudioConsentRequiredError",
    "AudioDomainTypeMismatchError",
    "AudioGenerationRequest",
    "AudioProvenanceRequiredError",
    "AudioRightsRequiredError",
    "ConsentGrant",
    "DialogueAssetVersion",
    "LegacyAudioTargetError",
    "MusicAssetVersion",
    "RightsBinding",
    "SfxAssetVersion",
    "VoiceAssetVersion",
    "build_ambience_asset_version",
    "build_audio_generation_request",
    "build_m9_audio_generation_request",
    "build_audio_provenance",
    "build_clone_dialogue_asset_version",
    "build_clone_voice_asset_version",
    "build_consent_grant",
    "build_dialogue_asset_version",
    "build_music_asset_version",
    "build_requested_audio_provenance",
    "build_rights_binding",
    "build_sfx_asset_version",
    "build_voice_asset_version",
    "require_effective_consent_grant",
    "validate_ambience_asset_version",
    "validate_audio_domain_asset_version",
    "validate_audio_generation_request",
    "validate_audio_provenance",
    "validate_consent_grant",
    "validate_clone_dialogue_asset_version",
    "validate_clone_voice_asset_version",
    "validate_dialogue_asset_version",
    "validate_music_asset_version",
    "validate_persisted_audio_domain_asset_version_evidence",
    "validate_rights_binding",
    "validate_sfx_asset_version",
    "validate_voice_asset_version",
]
