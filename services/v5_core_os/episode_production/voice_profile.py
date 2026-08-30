"""M12-C1 source-recording, consent, clone-lock and VoiceProfile lineage.

The contracts in this module deliberately stop before voice-clone execution.
They bind already-admitted AUDIO evidence into one append-only, acyclic authority
chain.  All durable writes use the existing Episode Production evidence journal;
there is no VoiceProfile registry, sidecar database, path-based input or admission
authority here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
import json
import math
from pathlib import PurePosixPath
import re
from threading import RLock
from typing import Any, Callable, Mapping, Sequence

from .evidence import (
    EpisodeProductionEvidenceRepository,
    EvidenceRecord,
    EvidenceSnapshot,
    validated_evidence_snapshot,
)
from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    RecordNotFoundError,
    RepositoryUnavailableError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _idempotency_key,
    _required_ref,
)
from .media_candidate_review import CanonicalAssetVersionAuthority
from .voice import (
    CLONE_VOICE_ENGINE_FAMILY,
    CLONE_VOICE_MODEL_ID,
    VOICE_LOCK_VERSION_V2_SCHEMA_VERSION,
    validate_clone_voice_lock,
    validate_clone_voice_lock_version_v2,
    validate_confirmed_clone_voice_lock_bundle,
    validate_voice_lock_confirmation,
)

# Compatibility aliases for callers that read every C1 contract from this
# module.  The implementation authority remains ``voice.py``.
validate_clone_voice_lock_version = validate_clone_voice_lock_version_v2
validate_clone_voice_lock_confirmation = validate_voice_lock_confirmation


SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION = (
    "v5.m12-source-voice-recording-asset-version.v1"
)
SOURCE_RECORDING_CLASSIFICATION_SCHEMA_VERSION = (
    "v5.m12-source-recording-classification.v1"
)
SOURCE_RECORDING_IMPORT_EVIDENCE_SCHEMA_VERSION = (
    "v5.m12-source-recording-import-evidence.v1"
)
SOURCE_RECORDING_PROVENANCE_SCHEMA_VERSION = (
    "v5.m12-source-recording-provenance.v1"
)
SOURCE_RECORDING_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m12-human-source-recording-requirement.v1"
)
SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION = (
    "v5.m12-source-voice-recording-binding.v1"
)
SOURCE_VOICE_RECORDING_ASSET_VERSION_BINDING_SCHEMA_VERSION = (
    SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION
)
CONSENT_GRANT_ROOT_SCHEMA_VERSION = "v5.m12-consent-grant.v1"
CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION = "v5.m12-consent-grant-version.v2"
VOICE_PROFILE_SCHEMA_VERSION = "v5.m12-voice-profile.v1"
VOICE_PROFILE_VERSION_SCHEMA_VERSION = "v5.m12-voice-profile-version.v1"
VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION = (
    "v5.m12-voice-profile-lineage-graph.v1"
)
VOICE_PROFILE_TEST_FIXTURE_SCHEMA_VERSION = (
    "v5.m12-voice-profile-technical-fixture.v1"
)
VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION = (
    "v5.m12-voice-profile-technical-validation.v1"
)
SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION = (
    "v5.m12-source-transcript-version.v1"
)
CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_SCHEMA_VERSION = (
    "v5.m12-current-confirmed-voice-profile-authority.v1"
)

SOURCE_RECORDING_BINDING_RECORD_KIND = (
    "SourceVoiceRecordingAssetVersionBinding"
)
CONSENT_GRANT_RECORD_KIND = "ConsentGrant"
CONSENT_GRANT_VERSION_RECORD_KIND = "ConsentGrantVersion"
VOICE_PROFILE_RECORD_KIND = "VoiceProfile"
VOICE_PROFILE_VERSION_RECORD_KIND = "VoiceProfileVersion"

_SERIES_SCOPED_C1_RECORD_KINDS = frozenset(
    {
        SOURCE_RECORDING_BINDING_RECORD_KIND,
        CONSENT_GRANT_RECORD_KIND,
        CONSENT_GRANT_VERSION_RECORD_KIND,
        VOICE_PROFILE_RECORD_KIND,
        VOICE_PROFILE_VERSION_RECORD_KIND,
    }
)

REQUIRED_CLONE_CONSENT_USES = frozenset(
    {"VOICE_CLONING", "VOICE_PROFILE_USE", "AUDIO_PRODUCTION"}
)
CONSENT_ALLOWED_USES = REQUIRED_CLONE_CONSENT_USES
CONSENT_REVOCATION_STATES = frozenset({"ACTIVE", "REVOKED"})
VOICE_PROFILE_STATUSES = frozenset({"CANDIDATE", "CONFIRMED", "REVOKED"})
VOICE_PROFILE_TEST_FIXTURE_MARKERS = frozenset(
    {
        "TEST_FIXTURE_ONLY",
        "NOT_KOKORO",
        "NOT_COSYVOICE",
        "NOT_PRODUCTION_VOICE_PROFILE",
        "NOT_ADMITTED",
    }
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")
VOICE_PROFILE_PACKAGE_FORMAT = "VOICE_PROFILE_PACKAGE"
VOICE_PROFILE_PACKAGE_SCHEMA_VERSION = "voice-profile-package.v1"
VOICE_CLONE_ENGINE_ID = CLONE_VOICE_ENGINE_FAMILY
VOICE_CLONE_ENGINE_COMMIT = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
VOICE_CLONE_MODEL_ID = CLONE_VOICE_MODEL_ID
VOICE_CLONE_MODEL_BUNDLE_SHA256 = (
    "f17e288095c0514ad4bc8d7bfc976363d1bcb3f1ab5ff4e276c014740125e83d"
)
_SCOPE_FIELDS = ("workspaceRef", "projectRef", "seriesRef")
_DESCENDANT_FIELDS = frozenset(
    {
        "consentGrantRef",
        "consentGrantVersionRef",
        "consentGrantVersionDigest",
        "voiceLockRef",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "voiceProfileVersionDigest",
        "voiceAssetVersionRef",
        "dialogueAssetVersionRef",
    }
)
_PATH_FIELDS = frozenset(
    {
        "storageKey",
        "absolutePath",
        "sourcePath",
        "path",
        "filePath",
        "url",
        "uri",
        "downloadUrl",
        "legacyMediaRef",
    }
)
_ASSET_ADMISSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "admissionRef",
        "version",
        "ordinal",
        "candidateRef",
        "candidateDigest",
        "selectionRef",
        "selectionVersion",
        "selectionDigest",
        "assetVersionRef",
        "assetVersionDigest",
        "admissionState",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_ASSET_ADMISSION_SUCCESSOR_FIELDS = _ASSET_ADMISSION_FIELDS | frozenset(
    {"assetVersionVersion"}
)

_MEDIA_PROBE_FIELDS = frozenset(
    {"codec", "sampleRate", "channelCount", "sampleCount", "durationRational"}
)
_RATIONAL_FIELDS = frozenset({"numerator", "denominator"})
_SOURCE_ASSET_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "sourceVoiceRecordingAssetVersionRef",
        "subjectRef",
        "canonicalAssetVersionRef",
        "canonicalAssetVersionNumber",
        "canonicalAssetVersionDigest",
        "assetAdmissionRef",
        "assetAdmissionVersion",
        "assetAdmissionDigest",
        "mediaKind",
        "immutable",
        "admissionState",
        "sourceAudioKind",
        "speechSynthesis",
        "voiceClone",
        "syntheticSpeech",
        "audioFileDigest",
        "audioPcmContentDigest",
        "audioTechnicalValidationRef",
        "audioTechnicalValidationDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "byteSize",
        "mediaProbe",
        "provenanceRef",
        "provenanceDigest",
        "requirementRef",
        "requirementDigest",
        "importEvidenceRef",
        "importEvidenceDigest",
        "sourceKindEvidenceRef",
        "sourceKindEvidenceDigest",
        "rightsBindingRef",
        "rightsBindingDigest",
        "classificationEvidenceKind",
        "authorityState",
        "publicationAllowed",
        "createdAt",
        "createdBy",
        "payloadDigest",
    }
)
_SOURCE_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "sourceRecordingBindingRef",
        "subjectRef",
        "sourceVoiceRecordingAssetVersionRef",
        "sourceVoiceRecordingAssetVersionDigest",
        "canonicalAssetVersionRef",
        "canonicalAssetVersionNumber",
        "canonicalAssetVersionDigest",
        "audioFileDigest",
        "audioPcmContentDigest",
        "audioTechnicalValidationRef",
        "audioTechnicalValidationDigest",
        "mediaProbe",
        "transcriptVersionRef",
        "transcriptVersionDigest",
        "transcriptLanguage",
        "transcriptTextDigest",
        "sourceRightsBindingRef",
        "sourceRightsBindingDigest",
        "createdAt",
        "createdBy",
        "payloadDigest",
    }
)
_SOURCE_RECORDING_IMPORT_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "importEvidenceRef",
        "subjectRef",
        "mediaKind",
        "captureMethod",
        "originalFileDigest",
        "canonicalArtifactFileDigest",
        "canonicalPcmContentDigest",
        "classificationEvidenceKind",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_RECORDING_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "requirementRef",
        "subjectRef",
        "mediaKind",
        "sourceAudioKind",
        "speechSynthesis",
        "voiceClone",
        "syntheticSpeech",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_RECORDING_PROVENANCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "provenanceRef",
        "subjectRef",
        "sourceAudioKind",
        "importEvidenceRef",
        "importEvidenceDigest",
        "requirementRef",
        "requirementDigest",
        "generationEngine",
        "commercialProvider",
        "classificationEvidenceKind",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_RECORDING_CLASSIFICATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "sourceKindEvidenceRef",
        "subjectRef",
        "canonicalAssetVersionRef",
        "canonicalAssetVersionDigest",
        "sourceAudioKind",
        "speechSynthesis",
        "voiceClone",
        "syntheticSpeech",
        "classificationState",
        "provenanceRef",
        "provenanceDigest",
        "requirementRef",
        "requirementDigest",
        "importEvidenceRef",
        "importEvidenceDigest",
        "classificationEvidenceKind",
        "publicationAllowed",
        "payloadDigest",
    }
)
_CONSENT_ROOT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "consentGrantRef",
        "subjectRef",
        "createdAt",
        "payloadDigest",
    }
)
_CONSENT_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "consentGrantRef",
        "consentGrantVersionRef",
        "sourceRecordingBindingRef",
        "sourceRecordingBindingDigest",
        "subjectRef",
        "grantorRef",
        "rightsBindingRef",
        "rightsBindingDigest",
        "allowedUses",
        "prohibitedUses",
        "territories",
        "validFrom",
        "expiresAt",
        "revocationState",
        "evidenceRef",
        "evidenceDigest",
        "versionNumber",
        "parentConsentGrantVersionRef",
        "parentConsentGrantVersionDigest",
        "createdAt",
        "createdBy",
        "payloadDigest",
    }
)
_VOICE_PROFILE_ROOT_FIELDS = frozenset(
    {
        "schemaVersion",
        "voiceProfileRef",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "subjectRef",
        "createdAt",
        "payloadDigest",
    }
)
_PROFILE_PACKAGE_FIELDS = frozenset(
    {
        "storageBindingRef",
        "byteSize",
        "fileDigest",
        "contentDigest",
        "packageFormat",
        "packageSchemaVersion",
        "technicalValidationRef",
        "technicalValidationDigest",
    }
)
_VOICE_PROFILE_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "voiceProfileRef",
        "voiceProfileVersionRef",
        "versionNumber",
        "parentVoiceProfileVersionRef",
        "parentVoiceProfileVersionDigest",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "subjectRef",
        "voiceIdentityRef",
        "voiceIdentityVersionRef",
        "voiceIdentityDigest",
        "voiceLockRef",
        "voiceLockVersionRef",
        "voiceLockVersionDigest",
        "voiceLockConfirmationRef",
        "voiceLockConfirmationDigest",
        "sourceRecordingBindingRef",
        "sourceRecordingBindingDigest",
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
        "profilePackage",
        "status",
        "createdAt",
        "createdBy",
        "confirmedAt",
        "payloadDigest",
    }
)
_FIXTURE_FIELDS = frozenset(
    {
        "schemaVersion",
        "fixtureRef",
        "fixtureMarkers",
        "profilePackage",
        "publicationAllowed",
        "payloadDigest",
    }
)
_VOICE_PROFILE_TECHNICAL_VALIDATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "technicalValidationRef",
        "storageBindingRef",
        "byteSize",
        "fileDigest",
        "contentDigest",
        "packageFormat",
        "packageSchemaVersion",
        "engineId",
        "engineCommit",
        "modelId",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
        "validationState",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_TRANSCRIPT_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "transcriptVersionRef",
        "sourceAssetVersionRef",
        "sourceAssetVersionDigest",
        "transcriptLanguage",
        "transcriptTextDigest",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "productionRunRef",
        "journalHead",
        "voiceProfile",
        "voiceProfileVersion",
        "sourceRecordingBinding",
        "consentGrantVersion",
        "confirmedVoiceLock",
        "rightsBinding",
        "evaluatedAt",
        "publicationAllowed",
        "payloadDigest",
    }
)


class VoiceProfileLineageError(EpisodeProductionError):
    code = "voice_profile_lineage_invalid"


class VoiceProfileLineageNotFoundError(RecordNotFoundError):
    code = "not_found"


class VoiceProfileLineageStaleError(StaleInputError):
    code = "voice_profile_lineage_stale"


class VoiceProfileLineageNotEffectiveError(UpstreamNotReadyError):
    code = "voice_profile_lineage_not_effective"


class VoiceProfileFixtureRejectedError(VoiceProfileLineageError):
    code = "voice_profile_fixture_rejected"


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise VoiceProfileLineageError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise VoiceProfileLineageError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _exact(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise VoiceProfileLineageStaleError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise VoiceProfileLineageError(f"{field} is invalid")
    return value


def _commit_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _COMMIT_SHA.fullmatch(value):
        raise VoiceProfileLineageError(f"{field} must be a pinned commit SHA")
    return value


def _closed_profile_package_identity(
    package_format: Any, package_schema_version: Any, *, prefix: str = "profilePackage"
) -> None:
    if package_format != VOICE_PROFILE_PACKAGE_FORMAT:
        raise VoiceProfileLineageError(f"{prefix}.packageFormat is unsupported")
    if package_schema_version != VOICE_PROFILE_PACKAGE_SCHEMA_VERSION:
        raise VoiceProfileLineageError(
            f"{prefix}.packageSchemaVersion is unsupported"
        )


def _clone_runtime_identity(value: Mapping[str, Any], *, prefix: str = "") -> None:
    label = f"{prefix} " if prefix else ""
    _text(value.get("engineId"), f"{label}engineId")
    _commit_sha(value.get("engineCommit"), f"{label}engineCommit")
    _text(value.get("modelId"), f"{label}modelId")
    _sha256(value.get("modelBundleDigest"), f"{label}modelBundleDigest")
    if (
        value["engineId"] != VOICE_CLONE_ENGINE_ID
        or value["engineCommit"] != VOICE_CLONE_ENGINE_COMMIT
        or value["modelId"] != VOICE_CLONE_MODEL_ID
        or value["modelBundleDigest"] != VOICE_CLONE_MODEL_BUNDLE_SHA256
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "VoiceProfile clone runtime identity is not the frozen ADR-0015 runtime"
        )


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not value and not allow_empty)
        or any(ord(character) < 32 for character in value)
    ):
        raise VoiceProfileLineageError(f"{field} is invalid")
    return value


def _positive_int(value: Any, field: str, *, maximum: int = 2**63 - 1) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
        or value > maximum
    ):
        raise VoiceProfileLineageError(f"{field} is invalid")
    return value


def _utc_instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise VoiceProfileLineageError(f"{field} is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise VoiceProfileLineageError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise VoiceProfileLineageError(f"{field} must be an explicit UTC instant")
    return parsed


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return tuple(_required_ref(value.get(field), field) for field in _SCOPE_FIELDS)  # type: ignore[return-value]


def _rational(value: Any, field: str) -> dict[str, int]:
    result = _exact(value, _RATIONAL_FIELDS, field)
    numerator = _positive_int(result["numerator"], f"{field}.numerator")
    denominator = _positive_int(result["denominator"], f"{field}.denominator")
    if numerator <= 0 or denominator <= 0:
        raise VoiceProfileLineageError(f"{field} is invalid")
    return {"numerator": numerator, "denominator": denominator}


def _media_probe(value: Any) -> dict[str, Any]:
    result = _exact(value, _MEDIA_PROBE_FIELDS, "mediaProbe")
    if result["codec"] != "pcm_s16le":
        raise VoiceProfileLineageError("mediaProbe.codec is unsupported")
    sample_rate = _positive_int(
        result["sampleRate"], "mediaProbe.sampleRate", maximum=384_000
    )
    if sample_rate < 8_000:
        raise VoiceProfileLineageError("mediaProbe.sampleRate is unsupported")
    channel_count = _positive_int(
        result["channelCount"], "mediaProbe.channelCount", maximum=2
    )
    if channel_count not in {1, 2}:
        raise VoiceProfileLineageError("mediaProbe.channelCount is unsupported")
    _positive_int(result["sampleCount"], "mediaProbe.sampleCount")
    result["durationRational"] = _rational(
        result["durationRational"], "mediaProbe.durationRational"
    )
    duration = result["durationRational"]
    if (
        math.gcd(duration["numerator"], duration["denominator"]) != 1
        or duration["numerator"] * result["sampleRate"]
        != result["sampleCount"] * duration["denominator"]
    ):
        raise VoiceProfileLineageError(
            "mediaProbe duration does not match its sample extent"
        )
    return result


def _token_list(
    value: Any,
    field: str,
    *,
    allowed: frozenset[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise VoiceProfileLineageError(f"{field} is invalid")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _TOKEN.fullmatch(item):
            raise VoiceProfileLineageError(f"{field}[{index}] is invalid")
        if allowed is not None and item not in allowed:
            raise VoiceProfileLineageError(f"{field}[{index}] is unsupported")
        result.append(item)
    if len(result) != len(set(result)) or result != sorted(result):
        raise VoiceProfileLineageError(f"{field} must be sorted and unique")
    return result


def _version_parent(
    version: int,
    parent_ref: Any,
    parent_digest: Any,
    *,
    ref_field: str,
    digest_field: str,
    self_ref: str,
) -> None:
    if version == 1:
        if parent_ref is not None or parent_digest is not None:
            raise VoiceProfileLineageError("initial version cannot have a predecessor")
        return
    parent = _required_ref(parent_ref, ref_field)
    _sha256(parent_digest, digest_field)
    if parent == self_ref:
        raise VoiceProfileLineageError("version cannot be its own predecessor")


def _profile_package(value: Any) -> dict[str, Any]:
    result = _exact(value, _PROFILE_PACKAGE_FIELDS, "profilePackage")
    _required_ref(result["storageBindingRef"], "profilePackage.storageBindingRef")
    _positive_int(result["byteSize"], "profilePackage.byteSize")
    for field in ("fileDigest", "contentDigest", "technicalValidationDigest"):
        _sha256(result[field], f"profilePackage.{field}")
    if _contains_fixture_marker(result):
        raise VoiceProfileFixtureRejectedError(
            "test fixture cannot be used as a production VoiceProfile package"
        )
    _closed_profile_package_identity(
        result["packageFormat"], result["packageSchemaVersion"]
    )
    _required_ref(
        result["technicalValidationRef"],
        "profilePackage.technicalValidationRef",
    )
    return result


def _contains_fixture_marker(value: Any) -> bool:
    if isinstance(value, str):
        return value in VOICE_PROFILE_TEST_FIXTURE_MARKERS
    if isinstance(value, Mapping):
        return any(
            _contains_fixture_marker(key) or _contains_fixture_marker(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_fixture_marker(item) for item in value)
    return False


def _source_audio_storage_key(value: Any) -> str:
    key = _text(value, "canonical AssetVersion.artifact.storageKey")
    path = PurePosixPath(key)
    if (
        not key.startswith("asset-versions/audio/")
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or "\\" in key
        or str(path) != key
        or not key.endswith(".wav")
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "canonical source audio storage key is invalid"
        )
    return key


def _contains_forbidden_source_authority_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in (_PATH_FIELDS - {"storageKey"})
            or _contains_forbidden_source_authority_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return any(_contains_forbidden_source_authority_key(item) for item in value)
    return False


def _source_projection_ref(value: Mapping[str, Any]) -> str:
    body = {
        key: deepcopy(item)
        for key, item in value.items()
        if key
        not in {
            "sourceVoiceRecordingAssetVersionRef",
            "payloadDigest",
        }
    }
    return "source-voice-recording-asset-version-" + _digest(body)


def _coordinated_transition(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def locked(self: "K2VoiceProfileLineageService", *args: Any, **kwargs: Any) -> Any:
        with self._coordination_lock:
            return method(self, *args, **kwargs)

    return locked


_IMMUTABLE_CONTRACT_FACTORY_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class _ImmutableContract:
    _payload_json: str

    @classmethod
    def _from_validated(
        cls, value: Mapping[str, Any], *, _token: object
    ) -> "_ImmutableContract":
        if _token is not _IMMUTABLE_CONTRACT_FACTORY_TOKEN:
            raise VoiceProfileLineageError("immutable contract factory is private")
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            json.dumps(value, sort_keys=True, separators=(",", ":")),
        )
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def __getitem__(self, key: str) -> Any:
        return deepcopy(self.as_dict()[key])


@dataclass(frozen=True, slots=True, init=False)
class SourceVoiceRecordingAssetVersion(_ImmutableContract):
    """Closed, read-only M12 projection over one canonical AssetVersion.

    The projection has no repository or admission path of its own.  Its ref is
    deterministically derived from the exact canonical AssetVersion and
    classification evidence; callers cannot submit this mapping.
    """

    @classmethod
    def from_mapping(cls, value: Any) -> "SourceVoiceRecordingAssetVersion":
        result = _verify_sealed(
            value, _SOURCE_ASSET_VERSION_FIELDS, "SourceVoiceRecordingAssetVersion"
        )
        if (
            result["schemaVersion"]
            != SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION
            or result["mediaKind"] != "AUDIO"
            or result["immutable"] is not True
            or result["admissionState"] != "ADMITTED"
            or result["sourceAudioKind"] != "HUMAN_SOURCE_RECORDING"
            or result["speechSynthesis"] is not False
            or result["voiceClone"] is not False
            or result["syntheticSpeech"] is not False
            or result["classificationEvidenceKind"] != "AUTHORITY_EVIDENCE"
            or result["authorityState"]
            != "DERIVED_CANONICAL_ASSET_PROJECTION"
            or result["publicationAllowed"] is not False
            or _contains_fixture_marker(result)
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "SourceVoiceRecordingAssetVersion is not admitted human audio"
            )
        if set(result) & (_DESCENDANT_FIELDS | _PATH_FIELDS):
            raise VoiceProfileLineageError(
                "SourceVoiceRecordingAssetVersion contains descendant or path authority"
            )
        _scope(result)
        for field in (
            "sourceVoiceRecordingAssetVersionRef",
            "subjectRef",
            "canonicalAssetVersionRef",
            "assetAdmissionRef",
            "audioTechnicalValidationRef",
            "artifactEvidenceRef",
            "artifactRef",
            "provenanceRef",
            "requirementRef",
            "importEvidenceRef",
            "sourceKindEvidenceRef",
            "rightsBindingRef",
            "createdBy",
        ):
            _required_ref(result[field], field)
        _positive_int(
            result["canonicalAssetVersionNumber"],
            "canonicalAssetVersionNumber",
        )
        _positive_int(result["assetAdmissionVersion"], "assetAdmissionVersion")
        _positive_int(result["byteSize"], "byteSize", maximum=10**15)
        for field in (
            "canonicalAssetVersionDigest",
            "assetAdmissionDigest",
            "audioFileDigest",
            "audioPcmContentDigest",
            "audioTechnicalValidationDigest",
            "artifactEvidenceDigest",
            "provenanceDigest",
            "requirementDigest",
            "importEvidenceDigest",
            "sourceKindEvidenceDigest",
            "rightsBindingDigest",
        ):
            _sha256(result[field], field)
        expected_projection_ref = _source_projection_ref(result)
        if result["sourceVoiceRecordingAssetVersionRef"] != expected_projection_ref:
            raise VoiceProfileLineageStaleError(
                "SourceVoiceRecordingAssetVersion projection identity is stale"
            )
        result["mediaProbe"] = _media_probe(result["mediaProbe"])
        _utc_instant(result["createdAt"], "createdAt")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


@dataclass(frozen=True, slots=True, init=False)
class SourceVoiceRecordingAssetVersionBinding(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "SourceVoiceRecordingAssetVersionBinding":
        result = _verify_sealed(value, _SOURCE_BINDING_FIELDS, "SourceVoiceRecordingBinding")
        if result["schemaVersion"] != SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION:
            raise VoiceProfileLineageError("SourceVoiceRecordingBinding schema is unsupported")
        if set(result) & (_DESCENDANT_FIELDS | _PATH_FIELDS):
            raise VoiceProfileLineageError(
                "SourceVoiceRecordingBinding contains descendant or path authority"
            )
        _scope(result)
        for field in (
            "sourceRecordingBindingRef",
            "subjectRef",
            "sourceVoiceRecordingAssetVersionRef",
            "canonicalAssetVersionRef",
            "audioTechnicalValidationRef",
            "transcriptVersionRef",
            "sourceRightsBindingRef",
            "createdBy",
        ):
            _required_ref(result[field], field)
        _positive_int(
            result["canonicalAssetVersionNumber"],
            "canonicalAssetVersionNumber",
        )
        for field in (
            "sourceVoiceRecordingAssetVersionDigest",
            "canonicalAssetVersionDigest",
            "audioFileDigest",
            "audioPcmContentDigest",
            "audioTechnicalValidationDigest",
            "transcriptVersionDigest",
            "transcriptTextDigest",
            "sourceRightsBindingDigest",
        ):
            _sha256(result[field], field)
        result["mediaProbe"] = _media_probe(result["mediaProbe"])
        _text(result["transcriptLanguage"], "transcriptLanguage")
        _utc_instant(result["createdAt"], "createdAt")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


@dataclass(frozen=True, slots=True, init=False)
class ConsentGrantRoot(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "ConsentGrantRoot":
        result = _verify_sealed(value, _CONSENT_ROOT_FIELDS, "ConsentGrant root")
        if result["schemaVersion"] != CONSENT_GRANT_ROOT_SCHEMA_VERSION:
            raise VoiceProfileLineageError("ConsentGrant root schema is unsupported")
        _scope(result)
        _required_ref(result["consentGrantRef"], "consentGrantRef")
        _required_ref(result["subjectRef"], "subjectRef")
        _utc_instant(result["createdAt"], "createdAt")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


@dataclass(frozen=True, slots=True, init=False)
class ConsentGrantVersionV2(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "ConsentGrantVersionV2":
        result = _verify_sealed(value, _CONSENT_VERSION_FIELDS, "ConsentGrantVersion v2")
        if result["schemaVersion"] != CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION:
            raise VoiceProfileLineageError("ConsentGrantVersion schema is unsupported")
        _scope(result)
        for field in (
            "consentGrantRef",
            "consentGrantVersionRef",
            "sourceRecordingBindingRef",
            "subjectRef",
            "grantorRef",
            "rightsBindingRef",
            "evidenceRef",
            "createdBy",
        ):
            _required_ref(result[field], field)
        for field in (
            "sourceRecordingBindingDigest",
            "rightsBindingDigest",
            "evidenceDigest",
        ):
            _sha256(result[field], field)
        allowed = _token_list(
            result["allowedUses"], "allowedUses", allowed=CONSENT_ALLOWED_USES
        )
        prohibited = _token_list(
            result["prohibitedUses"], "prohibitedUses", allow_empty=True
        )
        if set(allowed) & set(prohibited):
            raise VoiceProfileLineageError("ConsentGrantVersion use scopes overlap")
        _token_list(result["territories"], "territories")
        valid_from = _utc_instant(result["validFrom"], "validFrom")
        expires_at = _utc_instant(result["expiresAt"], "expiresAt")
        if valid_from >= expires_at:
            raise VoiceProfileLineageError("ConsentGrantVersion interval is invalid")
        if result["revocationState"] not in CONSENT_REVOCATION_STATES:
            raise VoiceProfileLineageError("ConsentGrantVersion revocationState is invalid")
        version = _positive_int(result["versionNumber"], "versionNumber")
        _version_parent(
            version,
            result["parentConsentGrantVersionRef"],
            result["parentConsentGrantVersionDigest"],
            ref_field="parentConsentGrantVersionRef",
            digest_field="parentConsentGrantVersionDigest",
            self_ref=result["consentGrantVersionRef"],
        )
        _utc_instant(result["createdAt"], "createdAt")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


@dataclass(frozen=True, slots=True, init=False)
class VoiceProfile(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "VoiceProfile":
        result = _verify_sealed(value, _VOICE_PROFILE_ROOT_FIELDS, "VoiceProfile")
        if result["schemaVersion"] != VOICE_PROFILE_SCHEMA_VERSION:
            raise VoiceProfileLineageError("VoiceProfile schema is unsupported")
        _scope(result)
        _required_ref(result["voiceProfileRef"], "voiceProfileRef")
        _required_ref(result["subjectRef"], "subjectRef")
        _utc_instant(result["createdAt"], "createdAt")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


@dataclass(frozen=True, slots=True, init=False)
class VoiceProfileVersion(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "VoiceProfileVersion":
        result = _verify_sealed(value, _VOICE_PROFILE_VERSION_FIELDS, "VoiceProfileVersion")
        if result["schemaVersion"] != VOICE_PROFILE_VERSION_SCHEMA_VERSION:
            raise VoiceProfileLineageError("VoiceProfileVersion schema is unsupported")
        _scope(result)
        for field in (
            "voiceProfileRef",
            "voiceProfileVersionRef",
            "subjectRef",
            "voiceIdentityRef",
            "voiceIdentityVersionRef",
            "voiceLockRef",
            "voiceLockVersionRef",
            "voiceLockConfirmationRef",
            "sourceRecordingBindingRef",
            "consentGrantVersionRef",
            "rightsBindingRef",
            "createdBy",
        ):
            _required_ref(result[field], field)
        _clone_runtime_identity(result, prefix="VoiceProfileVersion")
        for field in (
            "voiceIdentityDigest",
            "voiceLockVersionDigest",
            "voiceLockConfirmationDigest",
            "sourceRecordingBindingDigest",
            "consentGrantVersionDigest",
            "rightsBindingDigest",
            "modelBundleDigest",
            "dependencyLockDigest",
            "runtimeManifestDigest",
        ):
            _sha256(result[field], field)
        version = _positive_int(result["versionNumber"], "versionNumber")
        _version_parent(
            version,
            result["parentVoiceProfileVersionRef"],
            result["parentVoiceProfileVersionDigest"],
            ref_field="parentVoiceProfileVersionRef",
            digest_field="parentVoiceProfileVersionDigest",
            self_ref=result["voiceProfileVersionRef"],
        )
        result["profilePackage"] = _profile_package(result["profilePackage"])
        status = result["status"]
        if status not in VOICE_PROFILE_STATUSES:
            raise VoiceProfileLineageError("VoiceProfileVersion status is invalid")
        created = _utc_instant(result["createdAt"], "createdAt")
        confirmed_at = result["confirmedAt"]
        if status == "CANDIDATE":
            if confirmed_at is not None:
                raise VoiceProfileLineageError("candidate VoiceProfileVersion is confirmed")
        else:
            confirmed = _utc_instant(confirmed_at, "confirmedAt")
            if (
                (status == "CONFIRMED" and confirmed != created)
                or (status == "REVOKED" and confirmed > created)
            ):
                raise VoiceProfileLineageError("VoiceProfileVersion confirmation time is invalid")
        return cls._from_validated(
            result, _token=_IMMUTABLE_CONTRACT_FACTORY_TOKEN
        )


_CURRENT_AUTHORITY_FACTORY_TOKEN = object()
_VOICE_PROFILE_COORDINATION_LOCK = RLock()


@dataclass(frozen=True, slots=True, init=False)
class CurrentConfirmedVoiceProfileAuthority:
    """Ephemeral proof that C1 heads were re-read from one journal snapshot.

    This is intentionally not a durable contract and has no public mapping
    constructor.  Downstream clone builders require this exact wrapper so a
    historical CONFIRMED/ACTIVE mapping cannot masquerade as current after an
    append-only revocation successor exists.
    """

    _payload_json: str
    _revalidate: Callable[[Mapping[str, Any]], None]

    @classmethod
    def _from_service(
        cls,
        value: Mapping[str, Any],
        *,
        _token: object,
        _revalidate: Callable[[Mapping[str, Any]], None],
    ) -> "CurrentConfirmedVoiceProfileAuthority":
        if _token is not _CURRENT_AUTHORITY_FACTORY_TOKEN:
            raise VoiceProfileLineageError(
                "current VoiceProfile authority is service-issued only"
            )
        result = _verify_sealed(
            value,
            _CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_FIELDS,
            "CurrentConfirmedVoiceProfileAuthority",
        )
        if (
            result["schemaVersion"]
            != CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_SCHEMA_VERSION
            or result["publicationAllowed"] is not False
        ):
            raise VoiceProfileLineageError(
                "current VoiceProfile authority semantics are invalid"
            )
        scope = _scope(result)
        _required_ref(result["productionRunRef"], "productionRunRef")
        _sha256(result["journalHead"], "journalHead")
        evaluated_at = result["evaluatedAt"]
        _utc_instant(evaluated_at, "evaluatedAt")

        root = validate_voice_profile(result["voiceProfile"]).as_dict()
        profile = validate_voice_profile_version(
            result["voiceProfileVersion"]
        ).as_dict()
        source = validate_source_voice_recording_binding(
            result["sourceRecordingBinding"]
        ).as_dict()
        try:
            from .audio_authority import validate_rights_binding

            rights = validate_rights_binding(result["rightsBinding"]).as_dict()
            consent = require_active_consent_grant_version(
                result["consentGrantVersion"],
                evaluated_at=evaluated_at,
                expected_subject_ref=source["subjectRef"],
                expected_source_binding_ref=source[
                    "sourceRecordingBindingRef"
                ],
                expected_source_binding_digest=source["payloadDigest"],
                expected_rights_binding_ref=rights["rightsBindingRef"],
                expected_rights_binding_digest=rights["payloadDigest"],
            ).as_dict()
            lock = validate_confirmed_clone_voice_lock_bundle(
                result["confirmedVoiceLock"]
            )
        except EpisodeProductionError as exc:
            raise VoiceProfileLineageNotEffectiveError(
                "current VoiceProfile upstream authority is invalid"
            ) from exc
        nested = {
            "voiceProfile": root,
            "voiceProfileVersion": profile,
            "sourceRecordingBinding": source,
            "consentGrantVersion": consent,
            "confirmedVoiceLock": lock,
            "rightsBinding": rights,
        }
        if any(result[field] != item for field, item in nested.items()):
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority nested contract changed"
            )
        lock_root = lock["voiceLock"]
        lock_version = lock["voiceLockVersion"]
        confirmation = lock["voiceLockConfirmation"]
        if any(
            tuple(item[field] for field in _SCOPE_FIELDS) != scope
            for item in (root, profile, source, consent, lock_root, lock_version)
        ):
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority scope is stale"
            )
        if (
            profile["status"] != "CONFIRMED"
            or profile["voiceProfileRef"] != root["voiceProfileRef"]
            or profile["subjectRef"] != source["subjectRef"]
            or profile["sourceRecordingBindingRef"]
            != source["sourceRecordingBindingRef"]
            or profile["sourceRecordingBindingDigest"] != source["payloadDigest"]
            or profile["consentGrantVersionRef"]
            != consent["consentGrantVersionRef"]
            or profile["consentGrantVersionDigest"] != consent["payloadDigest"]
            or profile["rightsBindingRef"] != rights["rightsBindingRef"]
            or profile["rightsBindingDigest"] != rights["payloadDigest"]
            or profile["voiceLockRef"] != lock_root["voiceRef"]
            or profile["voiceLockVersionRef"]
            != lock_version["voiceLockVersionRef"]
            or profile["voiceLockVersionDigest"] != lock_version["payloadDigest"]
            or profile["voiceIdentityRef"] != lock_version["voiceIdentityRef"]
            or profile["voiceIdentityVersionRef"]
            != lock_version["voiceIdentityVersionRef"]
            or profile["voiceIdentityDigest"]
            != lock_version["voiceIdentityDigest"]
            or profile["voiceLockConfirmationRef"]
            != confirmation["voiceLockConfirmationRef"]
            or profile["voiceLockConfirmationDigest"]
            != confirmation["payloadDigest"]
            or lock_version["sourceRecordingBindingRef"]
            != source["sourceRecordingBindingRef"]
            or lock_version["sourceRecordingBindingDigest"]
            != source["payloadDigest"]
            or lock_version["consentGrantVersionRef"]
            != consent["consentGrantVersionRef"]
            or lock_version["consentGrantVersionDigest"]
            != consent["payloadDigest"]
            or lock_version["rightsBindingRef"] != rights["rightsBindingRef"]
            or lock_version["rightsBindingDigest"] != rights["payloadDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority lineage is stale"
            )
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "_payload_json",
            json.dumps(result, sort_keys=True, separators=(",", ":")),
        )
        object.__setattr__(instance, "_revalidate", _revalidate)
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def __getitem__(self, key: str) -> Any:
        return deepcopy(self.as_dict()[key])

    def assert_current(self) -> None:
        """Fail closed if any evidence append made this proof stale."""

        self._revalidate(self.as_dict())


def validate_source_voice_recording_asset_version(
    value: Any,
) -> SourceVoiceRecordingAssetVersion:
    return SourceVoiceRecordingAssetVersion.from_mapping(value)


def validate_source_voice_recording_binding(
    value: Any,
) -> SourceVoiceRecordingAssetVersionBinding:
    return SourceVoiceRecordingAssetVersionBinding.from_mapping(value)


def validate_source_voice_recording_asset_version_binding(
    value: Any,
) -> SourceVoiceRecordingAssetVersionBinding:
    return validate_source_voice_recording_binding(value)


def validate_consent_grant_root(value: Any) -> ConsentGrantRoot:
    return ConsentGrantRoot.from_mapping(value)


def validate_consent_grant_version_v2(value: Any) -> ConsentGrantVersionV2:
    return ConsentGrantVersionV2.from_mapping(value)


def validate_voice_profile(value: Any) -> VoiceProfile:
    return VoiceProfile.from_mapping(value)


def validate_voice_profile_version(value: Any) -> VoiceProfileVersion:
    return VoiceProfileVersion.from_mapping(value)


def require_active_consent_grant_version(
    value: Any,
    *,
    evaluated_at: str,
    expected_subject_ref: str | None = None,
    expected_source_binding_ref: str | None = None,
    expected_source_binding_digest: str | None = None,
    expected_rights_binding_ref: str | None = None,
    expected_rights_binding_digest: str | None = None,
) -> ConsentGrantVersionV2:
    grant = validate_consent_grant_version_v2(value)
    raw = grant.as_dict()
    when = _utc_instant(evaluated_at, "evaluatedAt")
    if (
        raw["revocationState"] != "ACTIVE"
        or when < _utc_instant(raw["validFrom"], "validFrom")
        or when >= _utc_instant(raw["expiresAt"], "expiresAt")
        or not REQUIRED_CLONE_CONSENT_USES.issubset(raw["allowedUses"])
        or REQUIRED_CLONE_CONSENT_USES.intersection(raw["prohibitedUses"])
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "ConsentGrantVersion does not authorize clone profile use"
        )
    expected = {
        "subjectRef": expected_subject_ref,
        "sourceRecordingBindingRef": expected_source_binding_ref,
        "sourceRecordingBindingDigest": expected_source_binding_digest,
        "rightsBindingRef": expected_rights_binding_ref,
        "rightsBindingDigest": expected_rights_binding_digest,
    }
    for field, selected in expected.items():
        if selected is not None and raw[field] != selected:
            raise VoiceProfileLineageStaleError(
                f"ConsentGrantVersion {field} binding is stale"
            )
    return grant


def build_voice_profile_test_fixture(command: Mapping[str, Any]) -> dict[str, Any]:
    """Build sealed non-production evidence which no production builder accepts."""

    value = _exact(
        command,
        frozenset({"fixtureRef", "profilePackage"}),
        "VoiceProfile test fixture command",
    )
    _required_ref(value["fixtureRef"], "fixtureRef")
    package = _exact(value["profilePackage"], _PROFILE_PACKAGE_FIELDS, "profilePackage")
    _required_ref(package["storageBindingRef"], "profilePackage.storageBindingRef")
    _positive_int(package["byteSize"], "profilePackage.byteSize")
    for field in ("fileDigest", "contentDigest", "technicalValidationDigest"):
        _sha256(package[field], f"profilePackage.{field}")
    _closed_profile_package_identity(
        package["packageFormat"], package["packageSchemaVersion"]
    )
    _required_ref(package["technicalValidationRef"], "profilePackage.technicalValidationRef")
    return _seal(
        {
            "schemaVersion": VOICE_PROFILE_TEST_FIXTURE_SCHEMA_VERSION,
            "fixtureRef": value["fixtureRef"],
            "fixtureMarkers": sorted(VOICE_PROFILE_TEST_FIXTURE_MARKERS),
            "profilePackage": package,
            "publicationAllowed": False,
        }
    )


def validate_voice_profile_test_fixture(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _FIXTURE_FIELDS, "VoiceProfile test fixture")
    if (
        result["schemaVersion"] != VOICE_PROFILE_TEST_FIXTURE_SCHEMA_VERSION
        or result["fixtureMarkers"] != sorted(VOICE_PROFILE_TEST_FIXTURE_MARKERS)
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageError("VoiceProfile test fixture semantics are invalid")
    _required_ref(result["fixtureRef"], "fixtureRef")
    package = _exact(result["profilePackage"], _PROFILE_PACKAGE_FIELDS, "profilePackage")
    _closed_profile_package_identity(
        package["packageFormat"], package["packageSchemaVersion"]
    )
    for field in ("fileDigest", "contentDigest", "technicalValidationDigest"):
        _sha256(package[field], f"profilePackage.{field}")
    return result


def validate_voice_profile_technical_validation(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _VOICE_PROFILE_TECHNICAL_VALIDATION_FIELDS,
        "VoiceProfileTechnicalValidation",
    )
    if (
        result["schemaVersion"]
        != VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION
        or result["validationState"] != "PASSED"
        or result["publicationAllowed"] is not False
        or _contains_fixture_marker(result)
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "VoiceProfileTechnicalValidation semantics are invalid"
        )
    for field in (
        "technicalValidationRef",
        "storageBindingRef",
    ):
        _required_ref(result[field], field)
    _positive_int(result["byteSize"], "byteSize")
    _clone_runtime_identity(result, prefix="VoiceProfileTechnicalValidation")
    _closed_profile_package_identity(
        result["packageFormat"],
        result["packageSchemaVersion"],
        prefix="VoiceProfileTechnicalValidation",
    )
    for field in (
        "fileDigest",
        "contentDigest",
        "modelBundleDigest",
        "dependencyLockDigest",
        "runtimeManifestDigest",
    ):
        _sha256(result[field], field)
    return result


def validate_source_transcript_version(
    value: Any,
    *,
    workspace_ref: str,
    project_ref: str,
    series_ref: str,
    production_run_ref: str,
    source_asset_version_ref: str,
    source_asset_version_digest: str,
) -> dict[str, Any]:
    """Validate the closed source-transcript projection consumed by C1."""

    result = _verify_sealed(
        value,
        _SOURCE_TRANSCRIPT_VERSION_FIELDS,
        "source TranscriptVersion",
    )
    if (
        result["schemaVersion"] != SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION
        or result["workspaceRef"] != workspace_ref
        or result["projectRef"] != project_ref
        or result["seriesRef"] != series_ref
        or result["productionRunRef"] != production_run_ref
        or result["sourceAssetVersionRef"] != source_asset_version_ref
        or result["sourceAssetVersionDigest"] != source_asset_version_digest
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageStaleError(
            "source TranscriptVersion authority binding is stale"
        )
    _required_ref(result["transcriptVersionRef"], "transcriptVersionRef")
    _required_ref(result["sourceAssetVersionRef"], "sourceAssetVersionRef")
    _sha256(result["sourceAssetVersionDigest"], "sourceAssetVersionDigest")
    _text(result["transcriptLanguage"], "transcriptLanguage")
    _sha256(result["transcriptTextDigest"], "transcriptTextDigest")
    return result


def _source_recording_requirement(
    value: Any,
    *,
    scope: tuple[str, str, str],
    run_ref: str,
    subject_ref: str,
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SOURCE_RECORDING_REQUIREMENT_FIELDS,
        "human source-recording requirement",
    )
    if (
        result["schemaVersion"] != SOURCE_RECORDING_REQUIREMENT_SCHEMA_VERSION
        or tuple(result[field] for field in _SCOPE_FIELDS) != scope
        or result["productionRunRef"] != run_ref
        or result["subjectRef"] != subject_ref
        or result["mediaKind"] != "AUDIO"
        or result["sourceAudioKind"] != "HUMAN_SOURCE_RECORDING"
        or result["speechSynthesis"] is not False
        or result["voiceClone"] is not False
        or result["syntheticSpeech"] is not False
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "source-recording requirement does not require human audio"
        )
    _required_ref(result["requirementRef"], "requirementRef")
    return result


def _source_recording_import_evidence(
    value: Any,
    *,
    scope: tuple[str, str, str],
    run_ref: str,
    subject_ref: str,
    file_digest: str,
    pcm_digest: str,
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SOURCE_RECORDING_IMPORT_EVIDENCE_FIELDS,
        "source-recording import evidence",
    )
    if (
        result["schemaVersion"]
        != SOURCE_RECORDING_IMPORT_EVIDENCE_SCHEMA_VERSION
        or tuple(result[field] for field in _SCOPE_FIELDS) != scope
        or result["productionRunRef"] != run_ref
        or result["subjectRef"] != subject_ref
        or result["mediaKind"] != "AUDIO"
        or result["captureMethod"] != "HUMAN_RECORDED_IMPORT"
        or result["canonicalArtifactFileDigest"] != file_digest
        or result["canonicalPcmContentDigest"] != pcm_digest
        or result["classificationEvidenceKind"] != "AUTHORITY_EVIDENCE"
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "source-recording import evidence is not authoritative human capture"
        )
    _required_ref(result["importEvidenceRef"], "importEvidenceRef")
    _sha256(result["originalFileDigest"], "originalFileDigest")
    _sha256(result["canonicalArtifactFileDigest"], "canonicalArtifactFileDigest")
    _sha256(result["canonicalPcmContentDigest"], "canonicalPcmContentDigest")
    return result


def _source_recording_provenance(
    value: Any,
    *,
    scope: tuple[str, str, str],
    run_ref: str,
    subject_ref: str,
    requirement: Mapping[str, Any],
    import_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SOURCE_RECORDING_PROVENANCE_FIELDS,
        "source-recording provenance",
    )
    if (
        result["schemaVersion"] != SOURCE_RECORDING_PROVENANCE_SCHEMA_VERSION
        or tuple(result[field] for field in _SCOPE_FIELDS) != scope
        or result["productionRunRef"] != run_ref
        or result["subjectRef"] != subject_ref
        or result["sourceAudioKind"] != "HUMAN_SOURCE_RECORDING"
        or result["importEvidenceRef"] != import_evidence["importEvidenceRef"]
        or result["importEvidenceDigest"] != import_evidence["payloadDigest"]
        or result["requirementRef"] != requirement["requirementRef"]
        or result["requirementDigest"] != requirement["payloadDigest"]
        or result["generationEngine"] is not None
        or result["commercialProvider"] is not False
        or result["classificationEvidenceKind"]
        != import_evidence["classificationEvidenceKind"]
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "source-recording provenance is synthetic or incomplete"
        )
    _required_ref(result["provenanceRef"], "provenanceRef")
    return result


def _source_recording_classification(
    value: Any,
    *,
    scope: tuple[str, str, str],
    run_ref: str,
    subject_ref: str,
    canonical_ref: str,
    canonical_digest: str,
    requirement: Mapping[str, Any],
    import_evidence: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SOURCE_RECORDING_CLASSIFICATION_FIELDS,
        "source-recording classification",
    )
    if (
        result["schemaVersion"] != SOURCE_RECORDING_CLASSIFICATION_SCHEMA_VERSION
        or tuple(result[field] for field in _SCOPE_FIELDS) != scope
        or result["productionRunRef"] != run_ref
        or result["subjectRef"] != subject_ref
        or result["canonicalAssetVersionRef"] != canonical_ref
        or result["canonicalAssetVersionDigest"] != canonical_digest
        or result["sourceAudioKind"] != "HUMAN_SOURCE_RECORDING"
        or result["speechSynthesis"] is not False
        or result["voiceClone"] is not False
        or result["syntheticSpeech"] is not False
        or result["classificationState"] != "DETERMINATE"
        or result["provenanceRef"] != provenance["provenanceRef"]
        or result["provenanceDigest"] != provenance["payloadDigest"]
        or result["requirementRef"] != requirement["requirementRef"]
        or result["requirementDigest"] != requirement["payloadDigest"]
        or result["importEvidenceRef"] != import_evidence["importEvidenceRef"]
        or result["importEvidenceDigest"] != import_evidence["payloadDigest"]
        or result["classificationEvidenceKind"]
        != provenance["classificationEvidenceKind"]
        or result["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "source-recording classification is indeterminate or synthetic"
        )
    _required_ref(result["sourceKindEvidenceRef"], "sourceKindEvidenceRef")
    return result


def _canonical_human_source_audio(
    value: Mapping[str, Any],
    *,
    scope: tuple[str, str, str],
    episode_ref: str,
    run_ref: str,
    expected_ref: str,
    expected_version: int,
    expected_digest: str,
) -> dict[str, Any]:
    """Validate the human-source subset of the generic canonical AssetVersion."""

    result = deepcopy(dict(value))
    if (
        result.get("assetVersionRef") != expected_ref
        or result.get("version") != expected_version
        or result.get("payloadDigest") != expected_digest
        or tuple(result.get(field) for field in _SCOPE_FIELDS) != scope
        or result.get("episodeRef") != episode_ref
        or result.get("productionRunRef") != run_ref
        or result.get("mediaKind") != "AUDIO"
        or result.get("immutable") is not True
        or result.get("publicationAllowed") is not False
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "canonical AssetVersion is not immutable source AUDIO"
        )
    _utc_instant(result.get("createdAt"), "AssetVersion.createdAt")
    schema = str(result.get("schemaVersion", "")).lower()
    asset_type = str(result.get("assetVersionType", "")).lower()
    if (
        "dialogue" in schema
        or "voice-asset" in schema
        or "dialogueassetversion" in asset_type
        or "voiceassetversion" in asset_type
        or "normalizedSpeechParameters" in result
        or "generationRequestRef" in result
        or "generationRequestVersionRef" in result
        or "generationResultRef" in result
        or "generationResultDigest" in result
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "synthetic Dialogue/Voice AssetVersion cannot be a source recording"
        )
    for field, expected in (
        ("sourceAudioKind", "HUMAN_SOURCE_RECORDING"),
        ("speechSynthesis", False),
        ("voiceClone", False),
        ("syntheticSpeech", False),
    ):
        if field in result and result[field] != expected:
            raise VoiceProfileLineageNotEffectiveError(
                "canonical AssetVersion contains synthetic-source facts"
            )
    serialized = json.dumps(result, sort_keys=True).lower()
    if any(
        marker in serialized
        for marker in (
            "kokoro",
            "piper",
            "cosyvoice",
            "edge-tts",
            "edge_tts",
            "tts_adapter",
            "text_to_speech",
            "speech_synthesis",
            "voice_clone",
            "synthetic_speech",
            "test_fixed_wav",
            "fixed_wav_fixture",
            "local-audio-contract-fixture",
        )
    ):
        raise VoiceProfileLineageNotEffectiveError(
            "canonical AssetVersion provenance is generated or test audio"
        )
    artifact = result.get("artifact")
    if not isinstance(artifact, Mapping):
        raise VoiceProfileLineageNotEffectiveError(
            "canonical source audio artifact is missing"
        )
    if _contains_forbidden_source_authority_key(result):
        raise VoiceProfileLineageNotEffectiveError(
            "canonical source audio exposes path, URL, or legacy authority"
        )
    for field in (
        "artifactEvidenceRef",
        "artifactRef",
    ):
        _required_ref(artifact.get(field), f"artifact.{field}")
    _source_audio_storage_key(artifact.get("storageKey"))
    for field in (
        "sourceRequirementRef",
        "sourceImportEvidenceRef",
        "sourceProvenanceRef",
    ):
        _required_ref(result.get(field), field)
    for field in (
        "artifactEvidenceDigest",
        "fileDigest",
    ):
        _sha256(artifact.get(field), f"artifact.{field}")
    for field in (
        "sourceRequirementDigest",
        "sourceImportEvidenceDigest",
        "sourceProvenanceDigest",
    ):
        _sha256(result.get(field), field)
    if set(artifact) & {
        "sourceRequirementRef",
        "sourceRequirementDigest",
        "sourceImportEvidenceRef",
        "sourceImportEvidenceDigest",
        "sourceProvenanceRef",
        "sourceProvenanceDigest",
    } or set(result) & {
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
    }:
        raise VoiceProfileLineageNotEffectiveError(
            "canonical source audio evidence pointers are not normalized"
        )
    byte_size = artifact.get("byteSize")
    _positive_int(byte_size, "artifact.byteSize", maximum=10**15)
    return result


def _assert_evidence_envelope_identity(
    record: Mapping[str, Any], payload: Mapping[str, Any], label: str
) -> None:
    """Bind C1 evidence payload identity to its immutable journal envelope."""

    ref_field: str | None = None
    expected_version: int | None = None
    if label == SOURCE_RECORDING_BINDING_RECORD_KIND:
        ref_field, expected_version = "sourceRecordingBindingRef", 1
    elif label == CONSENT_GRANT_RECORD_KIND:
        ref_field, expected_version = "consentGrantRef", 1
    elif label == CONSENT_GRANT_VERSION_RECORD_KIND:
        ref_field = "consentGrantVersionRef"
        expected_version = payload.get("versionNumber")
    elif label == VOICE_PROFILE_RECORD_KIND:
        ref_field, expected_version = "voiceProfileRef", 1
    elif label == VOICE_PROFILE_VERSION_RECORD_KIND:
        ref_field = "voiceProfileVersionRef"
        expected_version = payload.get("versionNumber")
    elif label == "AudioTechnicalValidation":
        ref_field = "validationVersionRef"
        expected_version = payload.get("version")
    elif label == "TranscriptVersion":
        ref_field, expected_version = "transcriptVersionRef", 1
    elif label == "RightsBinding":
        ref_field, expected_version = "rightsBindingRef", 1
    elif label == "VoiceProfileTechnicalValidation":
        ref_field = (
            "fixtureRef"
            if payload.get("schemaVersion")
            == VOICE_PROFILE_TEST_FIXTURE_SCHEMA_VERSION
            else "technicalValidationRef"
        )
        expected_version = 1
    elif label == "AssetVersion":
        ref_field = "assetVersionRef"
        expected_version = payload.get("version")
    elif label == "SourceRecordingRequirement":
        ref_field, expected_version = "requirementRef", 1
    elif label == "SourceRecordingImportEvidence":
        ref_field, expected_version = "importEvidenceRef", 1
    elif label == "SourceRecordingProvenance":
        ref_field, expected_version = "provenanceRef", 1
    elif label == "SourceRecordingClassification":
        ref_field, expected_version = "sourceKindEvidenceRef", 1

    if ref_field is not None and (
        payload.get(ref_field) != record.get("recordRef")
        or type(expected_version) is not int
        or record.get("recordVersion") != expected_version
    ):
        raise RepositoryUnavailableError(f"{label} evidence identity is invalid")
    if (
        "workspaceRef" in payload
        and payload.get("workspaceRef") != record.get("workspaceRef")
    ) or (
        "productionRunRef" in payload
        and payload.get("productionRunRef") != record.get("productionRunRef")
    ):
        raise RepositoryUnavailableError(f"{label} evidence scope is invalid")


def _payload(record: Mapping[str, Any], label: str) -> dict[str, Any]:
    value = record.get("payload")
    if not isinstance(value, Mapping):
        raise RepositoryUnavailableError(f"{label} evidence payload is invalid")
    result = deepcopy(dict(value))
    if (
        result.get("payloadDigest") != record.get("payloadDigest")
        or _digest({key: item for key, item in result.items() if key != "payloadDigest"})
        != record.get("payloadDigest")
    ):
        raise RepositoryUnavailableError(f"{label} evidence digest is invalid")
    _assert_evidence_envelope_identity(record, result, label)
    return result


def _evidence_record(
    *,
    workspace_ref: str,
    run_ref: str,
    kind: str,
    ref: str,
    version: int,
    idempotency_key: str,
    request_digest: str,
    created_at: str,
    payload: Mapping[str, Any],
) -> EvidenceRecord:
    sealed = deepcopy(dict(payload))
    supplied = sealed.get("payloadDigest")
    if not isinstance(supplied, str):
        sealed = _seal(sealed)
        supplied = sealed["payloadDigest"]
    elif _digest({key: item for key, item in sealed.items() if key != "payloadDigest"}) != supplied:
        raise VoiceProfileLineageStaleError("evidence payloadDigest is invalid")
    return EvidenceRecord(
        workspaceRef=workspace_ref,
        productionRunRef=run_ref,
        recordKind=kind,
        recordRef=_required_ref(ref, "recordRef"),
        recordVersion=_positive_int(version, "recordVersion", maximum=1_000_000),
        idempotencyKey=_idempotency_key(idempotency_key),
        requestDigest=_sha256(request_digest, "requestDigest"),
        createdAt=created_at,
        payload=sealed,
        payloadDigest=supplied,
    )


def _operation_key(client_key: str, operation: str, ordinal: int) -> str:
    return _digest(
        {
            "clientIdempotencyKey": _idempotency_key(client_key),
            "operation": operation,
            "ordinal": ordinal,
        }
    )


def _normalized_probe_from_upstream(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    probe = value.get("mediaProbe", value.get("probe"))
    if probe is None:
        probe = {}
    elif not isinstance(probe, Mapping):
        raise VoiceProfileLineageStaleError(f"{label} media probe is missing")
    codec = probe.get("codec", value.get("codec"))
    sample_rate = probe.get("sampleRate", value.get("sampleRate"))
    channel_count = probe.get(
        "channelCount", probe.get("channels", value.get("channelCount", value.get("channels")))
    )
    sample_count = probe.get("sampleCount", value.get("sampleCount"))
    duration = probe.get("durationRational", probe.get("duration", value.get("durationRational", value.get("duration"))))
    if isinstance(duration, Mapping) and set(duration) == {"numerator", "denominator", "unit"}:
        if duration.get("unit") not in {"seconds", "SECOND", "SECONDS"}:
            raise VoiceProfileLineageStaleError(f"{label} duration unit is invalid")
        duration = {
            "numerator": duration.get("numerator"),
            "denominator": duration.get("denominator"),
        }
    normalized = _media_probe(
        {
            "codec": codec,
            "sampleRate": sample_rate,
            "channelCount": channel_count,
            "sampleCount": sample_count,
            "durationRational": duration,
        }
    )
    rational = normalized["durationRational"]
    if (
        math.gcd(rational["numerator"], rational["denominator"]) != 1
        or rational["numerator"] * normalized["sampleRate"]
        != normalized["sampleCount"] * rational["denominator"]
    ):
        raise VoiceProfileLineageStaleError(
            f"{label} sample extent and duration are inconsistent"
        )
    return normalized


def _file_digest(value: Mapping[str, Any], label: str) -> str:
    artifact = value.get("artifact")
    nested = artifact if isinstance(artifact, Mapping) else {}
    selected = value.get("fileDigest", value.get("sha256", nested.get("fileDigest")))
    return _sha256(selected, f"{label}.fileDigest")


def _pcm_digest(value: Mapping[str, Any], label: str) -> str:
    artifact = value.get("artifact")
    nested = artifact if isinstance(artifact, Mapping) else {}
    selected = value.get("pcmContentDigest", nested.get("pcmContentDigest"))
    return _sha256(selected, f"{label}.pcmContentDigest")


def _canonical_record(
    snapshot: EvidenceSnapshot,
    *,
    kind: str,
    ref: str,
    digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = [
        deepcopy(dict(item))
        for item in snapshot.records
        if item.get("recordKind") == kind and item.get("recordRef") == ref
    ]
    if len(matches) != 1:
        raise VoiceProfileLineageNotFoundError(f"{kind} was not found")
    record = matches[0]
    if digest is not None and record.get("payloadDigest") != digest:
        raise VoiceProfileLineageStaleError(f"{kind} digest binding is stale")
    return record, _payload(record, kind)


def _canonical_version_record(
    snapshot: EvidenceSnapshot,
    *,
    kind: str,
    ref: str,
    digest: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _canonical_record(snapshot, kind=kind, ref=ref, digest=digest)


def _canonical_asset_authority_payload(
    snapshot: EvidenceSnapshot,
    *,
    ref: str,
    digest: str,
) -> dict[str, Any]:
    """Resolve one exact canonical AssetVersion from gate facts or records."""

    candidates: list[dict[str, Any]] = []
    for gate in snapshot.gates:
        for fact in gate.get("facts", []):
            if (
                not isinstance(fact, Mapping)
                or not str(fact.get("factKind", "")).startswith("AssetVersion")
                or fact.get("factRef") != ref
                or not isinstance(fact.get("payload"), Mapping)
            ):
                continue
            payload = deepcopy(dict(fact["payload"]))
            supplied = payload.get("payloadDigest")
            if (
                supplied != fact.get("payloadDigest")
                or supplied != digest
                or _digest(
                    {
                        key: item
                        for key, item in payload.items()
                        if key != "payloadDigest"
                    }
                )
                != supplied
            ):
                raise RepositoryUnavailableError(
                    "AssetVersion gate digest is invalid"
                )
            _assert_evidence_envelope_identity(
                {
                    "workspaceRef": snapshot.workspaceRef,
                    "productionRunRef": snapshot.productionRunRef,
                    "recordRef": fact.get("factRef"),
                    "recordVersion": fact.get("factVersion"),
                },
                payload,
                "AssetVersion",
            )
            candidates.append(payload)
    for record in snapshot.records:
        if (
            record.get("recordKind") == "AssetVersion"
            and record.get("recordRef") == ref
        ):
            payload = _payload(record, "AssetVersion")
            if payload["payloadDigest"] != digest:
                raise VoiceProfileLineageStaleError(
                    "AssetVersion digest binding is stale"
                )
            candidates.append(payload)
    unique = {
        json.dumps(item, sort_keys=True, separators=(",", ":")): item
        for item in candidates
    }
    if len(unique) != 1:
        raise VoiceProfileLineageNotFoundError(
            "canonical AssetVersion was not uniquely found"
        )
    return deepcopy(next(iter(unique.values())))


def _require_series_scope(
    value: Mapping[str, Any],
    scope: tuple[str, str, str],
    label: str,
) -> None:
    if tuple(value.get(field) for field in _SCOPE_FIELDS) != scope:
        raise VoiceProfileLineageNotFoundError(f"{label} was not found")


def _validate_asset_admission_payload(
    value: Mapping[str, Any],
    *,
    authority_ref: str,
    authority_version: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RepositoryUnavailableError("AssetAdmission payload is invalid")
    fields = set(value)
    allowed_shapes = {
        _ASSET_ADMISSION_FIELDS,
        _ASSET_ADMISSION_SUCCESSOR_FIELDS,
    }
    if fields not in allowed_shapes:
        raise RepositoryUnavailableError("AssetAdmission fields are invalid")
    result = _verify_sealed(value, frozenset(fields), "AssetAdmission")
    if (
        result["schemaVersion"] != "v5.k2-asset-admission.v1"
        or result["admissionRef"]
        != _required_ref(authority_ref, "AssetAdmission.authorityRef")
        or result["version"]
        != _positive_int(
            authority_version,
            "AssetAdmission.authorityVersion",
            maximum=1_000_000,
        )
        or result["admissionState"] != "ADMITTED"
        or result["publicationAllowed"] is not False
    ):
        raise RepositoryUnavailableError(
            "AssetAdmission authority semantics are invalid"
        )
    _positive_int(result["ordinal"], "AssetAdmission.ordinal", maximum=1_000_000)
    _required_ref(result["candidateRef"], "AssetAdmission.candidateRef")
    _sha256(result["candidateDigest"], "AssetAdmission.candidateDigest")
    _required_ref(result["selectionRef"], "AssetAdmission.selectionRef")
    _positive_int(
        result["selectionVersion"],
        "AssetAdmission.selectionVersion",
        maximum=1_000_000,
    )
    _sha256(result["selectionDigest"], "AssetAdmission.selectionDigest")
    _required_ref(result["assetVersionRef"], "AssetAdmission.assetVersionRef")
    _sha256(result["assetVersionDigest"], "AssetAdmission.assetVersionDigest")
    if "assetVersionVersion" in result:
        _positive_int(
            result["assetVersionVersion"],
            "AssetAdmission.assetVersionVersion",
            maximum=1_000_000,
        )
    _utc_instant(result["createdAt"], "AssetAdmission.createdAt")
    return result


class K2VoiceProfileLineageService:
    """Append-only C1 service over the existing Episode Production journal."""

    _SOURCE_COMMAND_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "subjectRef",
            "canonicalAssetVersionRef",
            "canonicalAssetVersionNumber",
            "canonicalAssetVersionDigest",
            "audioTechnicalValidationRef",
            "audioTechnicalValidationDigest",
            "transcriptVersionRef",
            "transcriptVersionDigest",
            "sourceRightsBindingRef",
            "sourceRightsBindingDigest",
            "createdBy",
        }
    )
    _CONSENT_CREATE_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "sourceRecordingBindingRef",
            "sourceRecordingBindingDigest",
            "subjectRef",
            "grantorRef",
            "rightsBindingRef",
            "rightsBindingDigest",
            "allowedUses",
            "prohibitedUses",
            "territories",
            "validFrom",
            "expiresAt",
            "evidenceRef",
            "evidenceDigest",
            "createdBy",
        }
    )
    _CONSENT_SUCCESSOR_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "consentGrantRef",
            "baseConsentGrantVersionRef",
            "baseConsentGrantVersionDigest",
            "allowedUses",
            "prohibitedUses",
            "territories",
            "validFrom",
            "expiresAt",
            "revocationState",
            "rightsBindingRef",
            "rightsBindingDigest",
            "evidenceRef",
            "evidenceDigest",
            "createdBy",
        }
    )
    _VOICE_LOCK_CREATE_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "voiceRef",
            "baseVoiceLockVersionRef",
            "baseVoiceLockDigest",
            "expectedRevision",
            "subjectRef",
            "sourceRecordingBindingRef",
            "sourceRecordingBindingDigest",
            "consentGrantVersionRef",
            "consentGrantVersionDigest",
            "rightsBindingRef",
            "rightsBindingDigest",
            "voiceIdentityRef",
            "voiceIdentityVersionRef",
            "voiceIdentityDigest",
            "engineFamily",
            "voiceId",
            "gender",
            "apparentAge",
            "pitchSemitones",
            "rateScale",
            "timbreDescriptor",
            "languageCode",
        }
    )
    _VOICE_LOCK_CONFIRM_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "voiceRef",
            "voiceLockVersionRef",
            "voiceLockVersionDigest",
            "expectedRevision",
        }
    )
    _PROFILE_CREATE_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "voiceRef",
            "voiceLockVersionRef",
            "voiceLockVersionDigest",
            "voiceLockConfirmationRef",
            "voiceLockConfirmationDigest",
            "engineId",
            "engineCommit",
            "modelId",
            "modelBundleDigest",
            "dependencyLockDigest",
            "runtimeManifestDigest",
            "profilePackage",
            "createdBy",
        }
    )
    _PROFILE_SUCCESSOR_FIELDS = frozenset(
        {
            "workspaceRef",
            "productionRunRef",
            "idempotencyKey",
            "voiceProfileRef",
            "baseVoiceProfileVersionRef",
            "baseVoiceProfileVersionDigest",
            "status",
            "createdBy",
        }
    )

    def __init__(
        self,
        root_service: Any,
        evidence: EpisodeProductionEvidenceRepository,
        *,
        voice_locks: Any,
        ref_factory: Callable[[str], str],
        clock: Callable[[], str],
    ) -> None:
        self.root_service = root_service
        self.evidence = evidence
        self.asset_versions = CanonicalAssetVersionAuthority(evidence)
        self.voice_locks = voice_locks
        self._ref_factory = ref_factory
        self._clock = clock
        # One in-process coordinator lock closes cross-instance interleavings
        # between the Episode evidence journal and the single VoiceLock owner.
        # It never writes or mirrors VoiceLock state into the journal.
        self._coordination_lock = _VOICE_PROFILE_COORDINATION_LOCK

    def _scope_for_run(
        self, workspace: str, run_ref: str
    ) -> tuple[str, str, str]:
        try:
            run = self.root_service.get_run(workspace, run_ref)
        except RecordNotFoundError:
            raise
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "EpisodeProductionRun authority is unavailable"
            ) from exc
        if (
            not isinstance(run, Mapping)
            or run.get("workspaceRef") != workspace
            or (
                "productionRunRef" in run
                and run.get("productionRunRef") != run_ref
            )
        ):
            raise RepositoryUnavailableError(
                "EpisodeProductionRun scope is invalid"
            )
        return (
            workspace,
            _required_ref(run.get("projectRef"), "projectRef"),
            _required_ref(run.get("seriesRef"), "seriesRef"),
        )

    def _context(
        self,
        command: Mapping[str, Any],
        *,
        fields: frozenset[str],
        operation: str,
    ) -> tuple[dict[str, Any], str, str, str, tuple[str, str, str], str]:
        value = _exact(command, fields, f"{operation} command")
        workspace = _required_ref(value["workspaceRef"], "workspaceRef")
        run_ref = _required_ref(value["productionRunRef"], "productionRunRef")
        key = _idempotency_key(value["idempotencyKey"])
        scope = self._scope_for_run(workspace, run_ref)
        now = _text(self._clock(), "createdAt")
        _utc_instant(now, "createdAt")
        return value, workspace, run_ref, key, scope, now

    def _snapshot(self, workspace: str, run_ref: str) -> tuple[str, EvidenceSnapshot]:
        """Read one run's gates plus the workspace-wide durable C1 journal.

        Durable voice identities are series-owned and may be consumed from a
        later production run.  The run snapshot remains the authority for
        run-local AssetAdmission facts; records are projected from the same
        repository across the workspace and filtered by their sealed
        project/series scope at every C1 boundary.
        """

        head = self.evidence.workspace_record_journal_head(workspace)
        run_snapshot = validated_evidence_snapshot(
            self.evidence.read_snapshot(workspace, run_ref),
            workspace_ref=workspace,
            run_ref=run_ref,
        )
        scope = self._scope_for_run(workspace, run_ref)
        workspace_records = self.evidence.list_workspace_records(workspace)
        owner_scopes: dict[str, tuple[str, str, str]] = {run_ref: scope}

        def owner_scope(item: Mapping[str, Any]) -> tuple[str, str, str]:
            owner_run = _required_ref(
                item.get("productionRunRef"), "ownerProductionRunRef"
            )
            selected = owner_scopes.get(owner_run)
            if selected is None:
                try:
                    selected = self._scope_for_run(workspace, owner_run)
                except RecordNotFoundError as exc:
                    raise RepositoryUnavailableError(
                        "voice lineage owner production run is unavailable"
                    ) from exc
                owner_scopes[owner_run] = selected
            return selected

        scoped_c1_records: list[dict[str, Any]] = []
        for item in workspace_records:
            if item.get("recordKind") not in _SERIES_SCOPED_C1_RECORD_KINDS:
                continue
            if not isinstance(item.get("payload"), Mapping):
                raise RepositoryUnavailableError(
                    "voice lineage record payload is invalid"
                )
            payload_scope = tuple(
                item["payload"].get(field) for field in _SCOPE_FIELDS
            )
            selected_owner_scope = owner_scope(item)
            if selected_owner_scope != scope:
                continue
            if payload_scope != selected_owner_scope:
                raise RepositoryUnavailableError(
                    "voice lineage record owner scope is invalid"
                )
            scoped_c1_records.append(item)
        rights_refs: set[str] = set()
        technical_refs: set[str] = set()
        for item in scoped_c1_records:
            payload = item["payload"]
            for field in ("sourceRightsBindingRef", "rightsBindingRef"):
                selected = payload.get(field)
                if isinstance(selected, str):
                    rights_refs.add(selected)
            package = payload.get("profilePackage")
            if isinstance(package, Mapping):
                selected = package.get("technicalValidationRef")
                if isinstance(selected, str):
                    technical_refs.add(selected)
        referenced_cross_run_records = [
            item
            for item in workspace_records
            if (
                item.get("recordKind") == "RightsBinding"
                and item.get("recordRef") in rights_refs
            )
            or (
                item.get("recordKind") == "VoiceProfileTechnicalValidation"
                and item.get("recordRef") in technical_refs
            )
            if owner_scope(item) == scope
        ]
        current_run_records = [
            item
            for item in workspace_records
            if item.get("productionRunRef") == run_ref
            and item.get("recordKind")
            not in _SERIES_SCOPED_C1_RECORD_KINDS
        ]
        selected_records: dict[tuple[str, str, str, int], dict[str, Any]] = {}
        for item in (
            scoped_c1_records
            + referenced_cross_run_records
            + current_run_records
        ):
            identity = (
                str(item.get("productionRunRef")),
                str(item.get("recordKind")),
                str(item.get("recordRef")),
                int(item.get("recordVersion", 0)),
            )
            selected_records[identity] = item
        records = tuple(
            selected_records[key]
            for key in sorted(selected_records)
        )
        if self.evidence.workspace_record_journal_head(workspace) != head:
            raise VoiceProfileLineageStaleError(
                "workspace voice lineage changed while being read"
            )
        snapshot = EvidenceSnapshot(
            workspaceRef=workspace,
            productionRunRef=run_ref,
            currentState=run_snapshot.currentState,
            gates=run_snapshot.gates,
            records=records,
            revisionToken=run_snapshot.revisionToken,
        )
        return head, snapshot

    def _replay(
        self,
        *,
        workspace: str,
        run_ref: str,
        operation: str,
        client_key: str,
        request_digest: str,
        primary_kind: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        operation_key = _operation_key(client_key, operation, 1)
        scope = self._scope_for_run(workspace, run_ref)
        matches: list[dict[str, Any]] = []
        for item in self.evidence.list_workspace_records(workspace):
            if (
                item.get("idempotencyKey") != operation_key
                or not isinstance(item.get("payload"), Mapping)
                or tuple(
                    item["payload"].get(field) for field in _SCOPE_FIELDS
                )
                != scope
            ):
                continue
            owner_run = _required_ref(
                item.get("productionRunRef"), "ownerProductionRunRef"
            )
            try:
                owner_scope = self._scope_for_run(workspace, owner_run)
            except RecordNotFoundError as exc:
                raise RepositoryUnavailableError(
                    f"{operation} idempotency owner run is unavailable"
                ) from exc
            if owner_scope == scope:
                matches.append(item)
        if not matches:
            return None
        if len(matches) != 1:
            raise RepositoryUnavailableError(
                f"{operation} idempotency authority is ambiguous"
            )
        stored = matches[0]
        if (
            stored.get("recordKind") != primary_kind
            or stored.get("requestDigest") != request_digest
        ):
            raise IdempotencyConflictError(
                f"{operation} idempotency content changed"
            )
        return deepcopy(dict(stored)), _payload(stored, primary_kind)

    @staticmethod
    def _admissions(
        snapshot: EvidenceSnapshot, *, workspace: str, run_ref: str
    ) -> list[dict[str, Any]]:
        """Resolve admission facts with their already-validated journal scope."""

        values: list[dict[str, Any]] = []
        for gate in snapshot.gates:
            for fact in gate.get("facts", []):
                if (
                    isinstance(fact, Mapping)
                    and str(fact.get("factKind", "")).startswith("AssetAdmission")
                    and isinstance(fact.get("payload"), Mapping)
                ):
                    schema_version = fact["payload"].get("schemaVersion")
                    if (
                        schema_version
                        == "v5.k2-real-video-batch-activation.v2"
                    ):
                        continue
                    if schema_version != "v5.k2-asset-admission.v1":
                        raise RepositoryUnavailableError(
                            "AssetAdmission gate schema is unsupported"
                        )
                    payload = _validate_asset_admission_payload(
                        deepcopy(dict(fact["payload"])),
                        authority_ref=fact.get("factRef"),
                        authority_version=fact.get("factVersion"),
                    )
                    if (
                        fact.get("factRef") != payload.get("admissionRef")
                        or fact.get("payloadDigest") != payload.get("payloadDigest")
                        or _positive_int(
                            fact.get("factVersion"),
                            "AssetAdmission.factVersion",
                            maximum=1_000_000,
                        )
                        != payload.get("version", fact.get("factVersion"))
                    ):
                        raise RepositoryUnavailableError(
                            "AssetAdmission gate identity is invalid"
                        )
                    values.append(
                        {
                            "workspaceRef": workspace,
                            "productionRunRef": run_ref,
                            "authorityRef": fact["factRef"],
                            "authorityVersion": fact["factVersion"],
                            "payload": payload,
                        }
                    )
        for record in snapshot.records:
            if record.get("recordKind") != "AssetAdmission":
                continue
            raw_payload = _payload(record, "AssetAdmission")
            schema_version = raw_payload.get("schemaVersion")
            if schema_version == "v5.k2-real-video-batch-activation.v2":
                continue
            if schema_version != "v5.k2-asset-admission.v1":
                raise RepositoryUnavailableError(
                    "AssetAdmission record schema is unsupported"
                )
            payload = _validate_asset_admission_payload(
                raw_payload,
                authority_ref=record.get("recordRef"),
                authority_version=record.get("recordVersion"),
            )
            if (
                record.get("workspaceRef") != workspace
                or record.get("productionRunRef") != run_ref
                or record.get("recordRef") != payload.get("admissionRef")
                or record.get("payloadDigest") != payload.get("payloadDigest")
                or _positive_int(
                    record.get("recordVersion"),
                    "AssetAdmission.recordVersion",
                    maximum=1_000_000,
                )
                != payload.get("version", record.get("recordVersion"))
            ):
                raise RepositoryUnavailableError(
                    "AssetAdmission record identity or scope is invalid"
                )
            values.append(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "authorityRef": record["recordRef"],
                    "authorityVersion": record["recordVersion"],
                    "payload": payload,
                }
            )
        return values

    def _resolve_source_upstreams(
        self,
        snapshot: EvidenceSnapshot,
        command: Mapping[str, Any],
        *,
        workspace: str,
        run_ref: str,
        scope: tuple[str, str, str],
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        canonical_ref = _required_ref(
            command["canonicalAssetVersionRef"], "canonicalAssetVersionRef"
        )
        canonical_version = _positive_int(
            command["canonicalAssetVersionNumber"],
            "canonicalAssetVersionNumber",
            maximum=1_000_000,
        )
        canonical_digest = _sha256(
            command["canonicalAssetVersionDigest"],
            "canonicalAssetVersionDigest",
        )
        try:
            authority_matches = [
                item
                for item in self.asset_versions.list_asset_versions(
                    workspace,
                    run_ref,
                    gates=snapshot.gates,
                    records=snapshot.records,
                )
                if item.get("assetVersionRef") == canonical_ref
            ]
        except EpisodeProductionError as exc:
            raise RepositoryUnavailableError(
                "canonical AssetVersion authority is invalid"
            ) from exc
        if len(authority_matches) != 1:
            raise VoiceProfileLineageNotFoundError(
                "canonical source AUDIO AssetVersion was not found"
            )
        canonical_payload = _canonical_asset_authority_payload(
            snapshot,
            ref=canonical_ref,
            digest=canonical_digest,
        )
        if authority_matches[0] != canonical_payload:
            raise RepositoryUnavailableError(
                "canonical AssetVersion projections disagree"
            )
        run = self.root_service.get_run(workspace, run_ref)
        episode_ref = _required_ref(run.get("episodeRef"), "episodeRef")
        asset = _canonical_human_source_audio(
            canonical_payload,
            scope=scope,
            episode_ref=episode_ref,
            run_ref=run_ref,
            expected_ref=canonical_ref,
            expected_version=canonical_version,
            expected_digest=canonical_digest,
        )
        artifact = asset["artifact"]
        file_digest = _file_digest(asset, "canonical AssetVersion")

        matching_admissions: dict[tuple[str, str], dict[str, Any]] = {}
        for authority in self._admissions(
            snapshot, workspace=workspace, run_ref=run_ref
        ):
            admission = authority["payload"]
            if admission.get("assetVersionRef") != canonical_ref:
                continue
            if admission.get("assetVersionDigest") != canonical_digest:
                raise VoiceProfileLineageStaleError(
                    "AssetAdmission authority conflicts for immutable AssetVersion"
                )
            if (
                admission.get("schemaVersion") != "v5.k2-asset-admission.v1"
                or admission.get("admissionState") != "ADMITTED"
                or admission.get("publicationAllowed") is not False
                or admission.get("admissionRef") != authority["authorityRef"]
                or admission.get("version") != authority["authorityVersion"]
                or (
                    "assetVersionVersion" in admission
                    and admission["assetVersionVersion"] != canonical_version
                )
            ):
                raise RepositoryUnavailableError(
                    "AssetAdmission authority semantics are invalid"
                )
            identity = (
                admission["admissionRef"],
                admission["payloadDigest"],
            )
            existing = matching_admissions.get(identity)
            if existing is not None and existing != admission:
                raise RepositoryUnavailableError(
                    "AssetAdmission authority has conflicting facts"
                )
            matching_admissions[identity] = admission
        if len(matching_admissions) != 1:
            raise VoiceProfileLineageNotEffectiveError(
                "source AUDIO AssetVersion is not uniquely admitted"
            )
        admission = next(iter(matching_admissions.values()))

        validation_record, raw_validation = _canonical_record(
            snapshot,
            kind="AudioTechnicalValidation",
            ref=_required_ref(
                command["audioTechnicalValidationRef"],
                "audioTechnicalValidationRef",
            ),
            digest=_sha256(
                command["audioTechnicalValidationDigest"],
                "audioTechnicalValidationDigest",
            ),
        )
        if (
            validation_record.get("workspaceRef") != workspace
            or validation_record.get("productionRunRef") != run_ref
        ):
            raise VoiceProfileLineageNotFoundError(
                "AudioTechnicalValidation was not found"
            )
        try:
            from .audio_validation import (
                validate_persisted_audio_technical_validation_evidence,
            )

            validation = validate_persisted_audio_technical_validation_evidence(
                raw_validation,
                expected_scope=(
                    workspace,
                    scope[1],
                    scope[2],
                    episode_ref,
                    run_ref,
                ),
                expected_source_ref=canonical_ref,
                expected_source_digest=canonical_digest,
            )
        except EpisodeProductionError as exc:
            raise VoiceProfileLineageNotEffectiveError(
                "AudioTechnicalValidation authority is invalid"
            ) from exc
        if (
            validation["sourceAssetVersionType"]
            != "SourceRecordingCanonicalAssetVersion"
            or validation["validationVersionRef"]
            != validation_record["recordRef"]
            or validation["sourceArtifactEvidenceRef"]
            != artifact["artifactEvidenceRef"]
            or validation["sourceArtifactEvidenceDigest"]
            != artifact["artifactEvidenceDigest"]
            or validation["artifactRef"] != artifact["artifactRef"]
            or validation["storageKey"] != artifact["storageKey"]
            or validation["byteSize"] != artifact["byteSize"]
            or validation["fileDigest"] != file_digest
        ):
            raise VoiceProfileLineageStaleError(
                "canonical audio artifact or validation evidence drifted"
            )
        pcm_digest = _pcm_digest(validation, "AudioTechnicalValidation")
        media_probe = _normalized_probe_from_upstream(
            validation, "AudioTechnicalValidation"
        )

        requirement_ref = _required_ref(
            asset["sourceRequirementRef"], "sourceRequirementRef"
        )
        requirement_digest = _sha256(
            asset["sourceRequirementDigest"], "sourceRequirementDigest"
        )
        _, requirement_payload = _canonical_record(
            snapshot,
            kind="SourceRecordingRequirement",
            ref=requirement_ref,
            digest=requirement_digest,
        )
        requirement = _source_recording_requirement(
            requirement_payload,
            scope=scope,
            run_ref=run_ref,
            subject_ref=command["subjectRef"],
        )

        import_ref = _required_ref(
            asset["sourceImportEvidenceRef"], "sourceImportEvidenceRef"
        )
        import_digest = _sha256(
            asset["sourceImportEvidenceDigest"], "sourceImportEvidenceDigest"
        )
        _, import_payload = _canonical_record(
            snapshot,
            kind="SourceRecordingImportEvidence",
            ref=import_ref,
            digest=import_digest,
        )
        import_evidence = _source_recording_import_evidence(
            import_payload,
            scope=scope,
            run_ref=run_ref,
            subject_ref=command["subjectRef"],
            file_digest=file_digest,
            pcm_digest=pcm_digest,
        )

        provenance_ref = _required_ref(
            asset["sourceProvenanceRef"], "sourceProvenanceRef"
        )
        provenance_digest = _sha256(
            asset["sourceProvenanceDigest"], "sourceProvenanceDigest"
        )
        _, provenance_payload = _canonical_record(
            snapshot,
            kind="SourceRecordingProvenance",
            ref=provenance_ref,
            digest=provenance_digest,
        )
        provenance = _source_recording_provenance(
            provenance_payload,
            scope=scope,
            run_ref=run_ref,
            subject_ref=command["subjectRef"],
            requirement=requirement,
            import_evidence=import_evidence,
        )

        classifications: list[dict[str, Any]] = []
        for record in snapshot.records:
            if record.get("recordKind") != "SourceRecordingClassification":
                continue
            candidate = _payload(record, "SourceRecordingClassification")
            if candidate.get("canonicalAssetVersionRef") != canonical_ref:
                continue
            if candidate.get("canonicalAssetVersionDigest") != canonical_digest:
                raise VoiceProfileLineageStaleError(
                    "source recording classification conflicts for immutable "
                    "AssetVersion"
                )
            classifications.append(candidate)
        if len(classifications) != 1:
            raise VoiceProfileLineageNotEffectiveError(
                "source recording classification is missing or ambiguous"
            )
        classification = _source_recording_classification(
            classifications[0],
            scope=scope,
            run_ref=run_ref,
            subject_ref=command["subjectRef"],
            canonical_ref=canonical_ref,
            canonical_digest=canonical_digest,
            requirement=requirement,
            import_evidence=import_evidence,
            provenance=provenance,
        )

        transcript_record, transcript_payload = _canonical_record(
            snapshot,
            kind="TranscriptVersion",
            ref=_required_ref(
                command["transcriptVersionRef"], "transcriptVersionRef"
            ),
            digest=_sha256(
                command["transcriptVersionDigest"], "transcriptVersionDigest"
            ),
        )
        if (
            transcript_record.get("workspaceRef") != workspace
            or transcript_record.get("productionRunRef") != run_ref
        ):
            raise VoiceProfileLineageNotFoundError(
                "TranscriptVersion was not found"
            )
        transcript = validate_source_transcript_version(
            transcript_payload,
            workspace_ref=workspace,
            project_ref=scope[1],
            series_ref=scope[2],
            production_run_ref=run_ref,
            source_asset_version_ref=canonical_ref,
            source_asset_version_digest=canonical_digest,
        )

        rights_record, rights_payload = _canonical_record(
            snapshot,
            kind="RightsBinding",
            ref=_required_ref(
                command["sourceRightsBindingRef"], "sourceRightsBindingRef"
            ),
            digest=_sha256(
                command["sourceRightsBindingDigest"],
                "sourceRightsBindingDigest",
            ),
        )
        if (
            rights_record.get("workspaceRef") != workspace
            or rights_record.get("productionRunRef") != run_ref
        ):
            raise VoiceProfileLineageNotFoundError(
                "source RightsBinding was not found"
            )
        try:
            from .audio_authority import validate_rights_binding

            rights = validate_rights_binding(rights_payload).as_dict()
        except EpisodeProductionError as exc:
            raise VoiceProfileLineageNotEffectiveError(
                "source RightsBinding is invalid"
            ) from exc
        required_rights_sources = {
            (canonical_ref, canonical_digest),
            (requirement["requirementRef"], requirement["payloadDigest"]),
            (import_evidence["importEvidenceRef"], import_evidence["payloadDigest"]),
            (provenance["provenanceRef"], provenance["payloadDigest"]),
            (
                classification["sourceKindEvidenceRef"],
                classification["payloadDigest"],
            ),
        }
        actual_rights_sources = {
            (item.get("sourceRef"), item.get("sourceDigest"))
            for item in rights["sourceRefs"]
        }
        closed_ancestor_sources = required_rights_sources | {
            (rights["rightsManifestRef"], rights["rightsManifestDigest"]),
            (
                rights["authorityEvidenceRef"],
                rights["authorityEvidenceDigest"],
            ),
        }
        descendant_refs = {
            record.get("recordRef")
            for record in snapshot.records
            if record.get("recordKind")
            in {
                CONSENT_GRANT_RECORD_KIND,
                CONSENT_GRANT_VERSION_RECORD_KIND,
                VOICE_PROFILE_RECORD_KIND,
                VOICE_PROFILE_VERSION_RECORD_KIND,
            }
        }
        if (
            not REQUIRED_CLONE_CONSENT_USES.issubset(rights["usageScope"])
            or not closed_ancestor_sources.issubset(actual_rights_sources)
            # Additional digest pins can be earlier AssetRequirements or the
            # consent/authorization evidence consumed by create_consent_grant.
            # Already-created descendants remain categorically forbidden.
            or any(
                ref in descendant_refs for ref, _ in actual_rights_sources
            )
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "source RightsBinding does not cover human recording evidence"
            )

        projection_body = {
            "schemaVersion": (
                SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION
            ),
            "workspaceRef": scope[0],
            "projectRef": scope[1],
            "seriesRef": scope[2],
            "subjectRef": command["subjectRef"],
            "canonicalAssetVersionRef": canonical_ref,
            "canonicalAssetVersionNumber": canonical_version,
            "canonicalAssetVersionDigest": canonical_digest,
            "assetAdmissionRef": admission["admissionRef"],
            "assetAdmissionVersion": admission["version"],
            "assetAdmissionDigest": admission["payloadDigest"],
            "mediaKind": "AUDIO",
            "immutable": True,
            "admissionState": "ADMITTED",
            "sourceAudioKind": "HUMAN_SOURCE_RECORDING",
            "speechSynthesis": False,
            "voiceClone": False,
            "syntheticSpeech": False,
            "audioFileDigest": file_digest,
            "audioPcmContentDigest": pcm_digest,
            "audioTechnicalValidationRef": validation[
                "validationVersionRef"
            ],
            "audioTechnicalValidationDigest": validation["payloadDigest"],
            "artifactEvidenceRef": artifact["artifactEvidenceRef"],
            "artifactEvidenceDigest": artifact["artifactEvidenceDigest"],
            "artifactRef": artifact["artifactRef"],
            "byteSize": artifact["byteSize"],
            "mediaProbe": media_probe,
            "provenanceRef": provenance["provenanceRef"],
            "provenanceDigest": provenance["payloadDigest"],
            "requirementRef": requirement["requirementRef"],
            "requirementDigest": requirement["payloadDigest"],
            "importEvidenceRef": import_evidence["importEvidenceRef"],
            "importEvidenceDigest": import_evidence["payloadDigest"],
            "sourceKindEvidenceRef": classification[
                "sourceKindEvidenceRef"
            ],
            "sourceKindEvidenceDigest": classification["payloadDigest"],
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
            "classificationEvidenceKind": "AUTHORITY_EVIDENCE",
            "authorityState": "DERIVED_CANONICAL_ASSET_PROJECTION",
            "publicationAllowed": False,
            "createdAt": asset["createdAt"],
            "createdBy": "v5.m12-c1.source-recording-projection.v1",
        }
        projection_ref = _source_projection_ref(projection_body)
        typed = validate_source_voice_recording_asset_version(
            _seal(
                {
                    "sourceVoiceRecordingAssetVersionRef": projection_ref,
                    **projection_body,
                }
            )
        ).as_dict()
        return typed, asset, validation, transcript, rights, admission

    def create_source_recording_binding(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._SOURCE_COMMAND_FIELDS,
            operation="create-source-recording-binding",
        )
        for field in (
            "subjectRef",
            "canonicalAssetVersionRef",
            "audioTechnicalValidationRef",
            "transcriptVersionRef",
            "sourceRightsBindingRef",
            "createdBy",
        ):
            _required_ref(value[field], field)
        _positive_int(
            value["canonicalAssetVersionNumber"],
            "canonicalAssetVersionNumber",
        )
        for field in (
            "canonicalAssetVersionDigest",
            "audioTechnicalValidationDigest",
            "transcriptVersionDigest",
            "sourceRightsBindingDigest",
        ):
            _sha256(value[field], field)
        request_digest = _digest(
            {"operation": "create-source-recording-binding", "command": value}
        )
        replay = self._replay(
            workspace=workspace,
            run_ref=run_ref,
            operation="create-source-recording-binding",
            client_key=key,
            request_digest=request_digest,
            primary_kind=SOURCE_RECORDING_BINDING_RECORD_KIND,
        )
        if replay is not None:
            _, snapshot = self._snapshot(workspace, run_ref)
            binding = self._source_binding(
                snapshot,
                ref=replay[1]["sourceRecordingBindingRef"],
                digest=_sha256(
                    replay[0].get("payloadDigest"),
                    "sourceRecordingBindingDigest",
                ),
            )
            typed, _, _, _, _, _ = self._resolve_source_upstreams(
                snapshot,
                value,
                workspace=workspace,
                run_ref=run_ref,
                scope=scope,
            )
            return {
                "sourceVoiceRecordingAssetVersion": typed,
                "sourceVoiceRecordingAssetVersionBinding": binding,
                "idempotentReplay": True,
            }
        head, snapshot = self._snapshot(workspace, run_ref)
        typed, asset, validation, transcript, rights, _ = self._resolve_source_upstreams(
            snapshot,
            value,
            workspace=workspace,
            run_ref=run_ref,
            scope=scope,
        )
        binding_ref = _required_ref(
            self._ref_factory("source-voice-recording-binding"),
            "sourceRecordingBindingRef",
        )
        language = transcript["transcriptLanguage"]
        text_digest = transcript["transcriptTextDigest"]
        binding = _seal(
            {
                "schemaVersion": SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION,
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "sourceRecordingBindingRef": binding_ref,
                "subjectRef": value["subjectRef"],
                "sourceVoiceRecordingAssetVersionRef": typed[
                    "sourceVoiceRecordingAssetVersionRef"
                ],
                "sourceVoiceRecordingAssetVersionDigest": typed[
                    "payloadDigest"
                ],
                "canonicalAssetVersionRef": asset["assetVersionRef"],
                "canonicalAssetVersionNumber": asset["version"],
                "canonicalAssetVersionDigest": asset["payloadDigest"],
                "audioFileDigest": _file_digest(asset, "AssetVersion"),
                "audioPcmContentDigest": _pcm_digest(
                    validation, "AudioTechnicalValidation"
                ),
                "audioTechnicalValidationRef": value[
                    "audioTechnicalValidationRef"
                ],
                "audioTechnicalValidationDigest": validation["payloadDigest"],
                "mediaProbe": _normalized_probe_from_upstream(
                    validation, "AudioTechnicalValidation"
                ),
                "transcriptVersionRef": value["transcriptVersionRef"],
                "transcriptVersionDigest": transcript["payloadDigest"],
                "transcriptLanguage": language,
                "transcriptTextDigest": text_digest,
                "sourceRightsBindingRef": rights["rightsBindingRef"],
                "sourceRightsBindingDigest": rights["payloadDigest"],
                "createdAt": now,
                "createdBy": value["createdBy"],
            }
        )
        binding = validate_source_voice_recording_binding(binding).as_dict()
        item = _evidence_record(
            workspace_ref=workspace,
            run_ref=run_ref,
            kind=SOURCE_RECORDING_BINDING_RECORD_KIND,
            ref=binding_ref,
            version=1,
            idempotency_key=_operation_key(
                key, "create-source-recording-binding", 1
            ),
            request_digest=request_digest,
            created_at=now,
            payload=binding,
        )
        stored, replayed = self.evidence.append_records(
            (item,),
            expected_workspace_record_journal_head=head,
            expected_evidence_revision_token=snapshot.revisionToken,
        )
        result = validate_source_voice_recording_binding(
            _payload(stored[0], SOURCE_RECORDING_BINDING_RECORD_KIND)
        ).as_dict()
        return {
            "sourceVoiceRecordingAssetVersion": typed,
            "sourceVoiceRecordingAssetVersionBinding": result,
            "idempotentReplay": replayed,
        }

    def _source_binding(
        self,
        snapshot: EvidenceSnapshot,
        *,
        ref: str,
        digest: str,
    ) -> dict[str, Any]:
        record, payload = _canonical_record(
            snapshot,
            kind=SOURCE_RECORDING_BINDING_RECORD_KIND,
            ref=_required_ref(ref, "sourceRecordingBindingRef"),
            digest=_sha256(digest, "sourceRecordingBindingDigest"),
        )
        binding = validate_source_voice_recording_binding(payload).as_dict()
        owner_run = _required_ref(
            record.get("productionRunRef"),
            "SourceVoiceRecordingAssetVersionBinding.ownerProductionRunRef",
        )
        owner_snapshot = snapshot
        if owner_run != snapshot.productionRunRef:
            _, owner_snapshot = self._snapshot(snapshot.workspaceRef, owner_run)
        owner_scope = self._scope_for_run(snapshot.workspaceRef, owner_run)
        typed, _, _, transcript, _, _ = self._resolve_source_upstreams(
            owner_snapshot,
            {
                "subjectRef": binding["subjectRef"],
                "canonicalAssetVersionRef": binding[
                    "canonicalAssetVersionRef"
                ],
                "canonicalAssetVersionNumber": binding[
                    "canonicalAssetVersionNumber"
                ],
                "canonicalAssetVersionDigest": binding[
                    "canonicalAssetVersionDigest"
                ],
                "audioTechnicalValidationRef": binding[
                    "audioTechnicalValidationRef"
                ],
                "audioTechnicalValidationDigest": binding[
                    "audioTechnicalValidationDigest"
                ],
                "transcriptVersionRef": binding["transcriptVersionRef"],
                "transcriptVersionDigest": binding[
                    "transcriptVersionDigest"
                ],
                "sourceRightsBindingRef": binding[
                    "sourceRightsBindingRef"
                ],
                "sourceRightsBindingDigest": binding[
                    "sourceRightsBindingDigest"
                ],
            },
            workspace=snapshot.workspaceRef,
            run_ref=owner_run,
            scope=owner_scope,
        )
        expected = {
            "sourceVoiceRecordingAssetVersionRef": typed[
                "sourceVoiceRecordingAssetVersionRef"
            ],
            "sourceVoiceRecordingAssetVersionDigest": typed["payloadDigest"],
            "canonicalAssetVersionRef": typed["canonicalAssetVersionRef"],
            "canonicalAssetVersionNumber": typed[
                "canonicalAssetVersionNumber"
            ],
            "canonicalAssetVersionDigest": typed[
                "canonicalAssetVersionDigest"
            ],
            "audioFileDigest": typed["audioFileDigest"],
            "audioPcmContentDigest": typed["audioPcmContentDigest"],
            "audioTechnicalValidationRef": typed[
                "audioTechnicalValidationRef"
            ],
            "audioTechnicalValidationDigest": typed[
                "audioTechnicalValidationDigest"
            ],
            "mediaProbe": typed["mediaProbe"],
            "transcriptVersionRef": transcript["transcriptVersionRef"],
            "transcriptVersionDigest": transcript["payloadDigest"],
            "transcriptLanguage": transcript["transcriptLanguage"],
            "transcriptTextDigest": transcript["transcriptTextDigest"],
            "sourceRightsBindingRef": typed["rightsBindingRef"],
            "sourceRightsBindingDigest": typed["rightsBindingDigest"],
        }
        if any(binding[field] != selected for field, selected in expected.items()):
            raise VoiceProfileLineageStaleError(
                "SourceVoiceRecordingAssetVersionBinding projection is stale"
            )
        return binding

    @staticmethod
    def _rights_binding(
        snapshot: EvidenceSnapshot,
        *,
        ref: str,
        digest: str,
    ) -> dict[str, Any]:
        _, payload = _canonical_record(
            snapshot,
            kind="RightsBinding",
            ref=_required_ref(ref, "rightsBindingRef"),
            digest=_sha256(digest, "rightsBindingDigest"),
        )
        try:
            from .audio_authority import validate_rights_binding

            result = validate_rights_binding(payload).as_dict()
        except EpisodeProductionError as exc:
            raise VoiceProfileLineageNotEffectiveError(
                "RightsBinding is invalid"
            ) from exc
        if result != payload or result["rightsBindingRef"] != ref:
            raise VoiceProfileLineageStaleError("RightsBinding is stale")
        if not REQUIRED_CLONE_CONSENT_USES.issubset(result["usageScope"]):
            raise VoiceProfileLineageNotEffectiveError(
                "RightsBinding does not cover every clone use"
            )
        return result

    def _consent_versions(
        self, snapshot: EvidenceSnapshot, consent_grant_ref: str
    ) -> list[dict[str, Any]]:
        versions = [
            validate_consent_grant_version_v2(_payload(record, "ConsentGrantVersion")).as_dict()
            for record in snapshot.records
            if record.get("recordKind") == CONSENT_GRANT_VERSION_RECORD_KIND
            and isinstance(record.get("payload"), Mapping)
            and record["payload"].get("consentGrantRef") == consent_grant_ref
        ]
        versions.sort(key=lambda item: item["versionNumber"])
        if not versions:
            raise VoiceProfileLineageNotFoundError(
                "ConsentGrantVersion was not found"
            )
        for index, item in enumerate(versions, start=1):
            source = self._source_binding(
                snapshot,
                ref=item["sourceRecordingBindingRef"],
                digest=item["sourceRecordingBindingDigest"],
            )
            rights = self._rights_binding(
                snapshot,
                ref=item["rightsBindingRef"],
                digest=item["rightsBindingDigest"],
            )
            required_sources = {
                (
                    source["canonicalAssetVersionRef"],
                    source["canonicalAssetVersionDigest"],
                ),
                (item["evidenceRef"], item["evidenceDigest"]),
            }
            actual_sources = {
                (value.get("sourceRef"), value.get("sourceDigest"))
                for value in rights["sourceRefs"]
            }
            if not required_sources.issubset(actual_sources):
                raise RepositoryUnavailableError(
                    "ConsentGrantVersion rights evidence is incomplete"
                )
            if item["versionNumber"] != index:
                raise RepositoryUnavailableError(
                    "ConsentGrantVersion lineage is not contiguous"
                )
            if index == 1:
                if (
                    item["revocationState"] != "ACTIVE"
                    or item["rightsBindingRef"]
                    != source["sourceRightsBindingRef"]
                    or item["rightsBindingDigest"]
                    != source["sourceRightsBindingDigest"]
                ):
                    raise RepositoryUnavailableError(
                        "initial ConsentGrantVersion authority is invalid"
                    )
                continue
            parent = versions[index - 2]
            if (
                item["parentConsentGrantVersionRef"]
                != parent["consentGrantVersionRef"]
                or item["parentConsentGrantVersionDigest"]
                != parent["payloadDigest"]
                or item["sourceRecordingBindingRef"]
                != parent["sourceRecordingBindingRef"]
                or item["sourceRecordingBindingDigest"]
                != parent["sourceRecordingBindingDigest"]
                or item["subjectRef"] != parent["subjectRef"]
                or item["grantorRef"] != parent["grantorRef"]
                or (
                    parent["rightsBindingRef"],
                    parent["rightsBindingDigest"],
                )
                not in actual_sources
                or item["rightsBindingRef"] == parent["rightsBindingRef"]
                or (parent["revocationState"], item["revocationState"])
                not in {("ACTIVE", "ACTIVE"), ("ACTIVE", "REVOKED")}
            ):
                raise RepositoryUnavailableError(
                    "ConsentGrantVersion predecessor lineage is invalid"
                )
        return versions

    def _current_consent(
        self,
        snapshot: EvidenceSnapshot,
        *,
        version_ref: str,
        digest: str,
        evaluated_at: str,
        source_binding: Mapping[str, Any],
        rights_binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        _, selected_payload = _canonical_version_record(
            snapshot,
            kind=CONSENT_GRANT_VERSION_RECORD_KIND,
            ref=_required_ref(version_ref, "consentGrantVersionRef"),
            digest=_sha256(digest, "consentGrantVersionDigest"),
        )
        selected = validate_consent_grant_version_v2(selected_payload).as_dict()
        _, root_payload = _canonical_record(
            snapshot,
            kind=CONSENT_GRANT_RECORD_KIND,
            ref=selected["consentGrantRef"],
        )
        root = validate_consent_grant_root(root_payload).as_dict()
        if (
            tuple(root[field] for field in _SCOPE_FIELDS)
            != tuple(selected[field] for field in _SCOPE_FIELDS)
            or root["consentGrantRef"] != selected["consentGrantRef"]
            or root["subjectRef"] != selected["subjectRef"]
        ):
            raise RepositoryUnavailableError(
                "ConsentGrant root/version lineage is invalid"
            )
        versions = self._consent_versions(snapshot, selected["consentGrantRef"])
        if versions[-1]["consentGrantVersionRef"] != selected["consentGrantVersionRef"]:
            raise VoiceProfileLineageNotEffectiveError(
                "ConsentGrantVersion was superseded"
            )
        active = require_active_consent_grant_version(
            selected,
            evaluated_at=evaluated_at,
            expected_subject_ref=source_binding["subjectRef"],
            expected_source_binding_ref=source_binding[
                "sourceRecordingBindingRef"
            ],
            expected_source_binding_digest=source_binding["payloadDigest"],
            expected_rights_binding_ref=rights_binding["rightsBindingRef"],
            expected_rights_binding_digest=rights_binding["payloadDigest"],
        ).as_dict()
        return active

    def create_consent_grant(self, command: Mapping[str, Any]) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._CONSENT_CREATE_FIELDS,
            operation="create-consent-grant",
        )
        for field in (
            "sourceRecordingBindingRef",
            "subjectRef",
            "grantorRef",
            "rightsBindingRef",
            "evidenceRef",
            "createdBy",
        ):
            _required_ref(value[field], field)
        for field in (
            "sourceRecordingBindingDigest",
            "rightsBindingDigest",
            "evidenceDigest",
        ):
            _sha256(value[field], field)
        allowed = _token_list(
            value["allowedUses"], "allowedUses", allowed=CONSENT_ALLOWED_USES
        )
        if set(allowed) != REQUIRED_CLONE_CONSENT_USES:
            raise VoiceProfileLineageNotEffectiveError(
                "ConsentGrantVersion must authorize every clone use"
            )
        prohibited = _token_list(
            value["prohibitedUses"], "prohibitedUses", allow_empty=True
        )
        territories = _token_list(value["territories"], "territories")
        valid_from = _utc_instant(value["validFrom"], "validFrom")
        expires_at = _utc_instant(value["expiresAt"], "expiresAt")
        if valid_from >= expires_at:
            raise VoiceProfileLineageError("ConsentGrantVersion interval is invalid")
        request_digest = _digest(
            {"operation": "create-consent-grant", "command": value}
        )
        replay = self._replay(
            workspace=workspace,
            run_ref=run_ref,
            operation="create-consent-grant",
            client_key=key,
            request_digest=request_digest,
            primary_kind=CONSENT_GRANT_VERSION_RECORD_KIND,
        )
        if replay is not None:
            version = validate_consent_grant_version_v2(replay[1]).as_dict()
            _, replay_snapshot = self._snapshot(workspace, run_ref)
            _, root_payload = _canonical_record(
                replay_snapshot,
                kind=CONSENT_GRANT_RECORD_KIND,
                ref=version["consentGrantRef"],
            )
            return {
                "consentGrant": validate_consent_grant_root(root_payload).as_dict(),
                "consentGrantVersion": version,
                "idempotentReplay": True,
            }
        head, snapshot = self._snapshot(workspace, run_ref)
        source = self._source_binding(
            snapshot,
            ref=value["sourceRecordingBindingRef"],
            digest=value["sourceRecordingBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=value["rightsBindingRef"],
            digest=value["rightsBindingDigest"],
        )
        _require_series_scope(source, scope, "SourceVoiceRecordingAssetVersionBinding")
        if (
            value["subjectRef"] != source["subjectRef"]
            or rights["rightsBindingRef"] != source["sourceRightsBindingRef"]
            or rights["payloadDigest"] != source["sourceRightsBindingDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "ConsentGrantVersion subject or rights lineage is stale"
            )
        if not any(
            item.get("sourceRef") == value["evidenceRef"]
            and item.get("sourceDigest") == value["evidenceDigest"]
            for item in rights["sourceRefs"]
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "Consent evidence is not covered by canonical RightsBinding"
            )
        grant_ref = _required_ref(
            self._ref_factory("consent-grant"), "consentGrantRef"
        )
        version_ref = _required_ref(
            self._ref_factory("consent-grant-version"),
            "consentGrantVersionRef",
        )
        root = validate_consent_grant_root(
            _seal(
                {
                    "schemaVersion": CONSENT_GRANT_ROOT_SCHEMA_VERSION,
                    "workspaceRef": scope[0],
                    "projectRef": scope[1],
                    "seriesRef": scope[2],
                    "consentGrantRef": grant_ref,
                    "subjectRef": source["subjectRef"],
                    "createdAt": now,
                }
            )
        ).as_dict()
        version = validate_consent_grant_version_v2(
            _seal(
                {
                    "schemaVersion": CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION,
                    "workspaceRef": scope[0],
                    "projectRef": scope[1],
                    "seriesRef": scope[2],
                    "consentGrantRef": grant_ref,
                    "consentGrantVersionRef": version_ref,
                    "sourceRecordingBindingRef": source[
                        "sourceRecordingBindingRef"
                    ],
                    "sourceRecordingBindingDigest": source["payloadDigest"],
                    "subjectRef": source["subjectRef"],
                    "grantorRef": value["grantorRef"],
                    "rightsBindingRef": rights["rightsBindingRef"],
                    "rightsBindingDigest": rights["payloadDigest"],
                    "allowedUses": allowed,
                    "prohibitedUses": prohibited,
                    "territories": territories,
                    "validFrom": value["validFrom"],
                    "expiresAt": value["expiresAt"],
                    "revocationState": "ACTIVE",
                    "evidenceRef": value["evidenceRef"],
                    "evidenceDigest": value["evidenceDigest"],
                    "versionNumber": 1,
                    "parentConsentGrantVersionRef": None,
                    "parentConsentGrantVersionDigest": None,
                    "createdAt": now,
                    "createdBy": value["createdBy"],
                }
            )
        ).as_dict()
        records = (
            _evidence_record(
                workspace_ref=workspace,
                run_ref=run_ref,
                kind=CONSENT_GRANT_VERSION_RECORD_KIND,
                ref=version_ref,
                version=1,
                idempotency_key=_operation_key(key, "create-consent-grant", 1),
                request_digest=request_digest,
                created_at=now,
                payload=version,
            ),
            _evidence_record(
                workspace_ref=workspace,
                run_ref=run_ref,
                kind=CONSENT_GRANT_RECORD_KIND,
                ref=grant_ref,
                version=1,
                idempotency_key=_operation_key(key, "create-consent-grant", 2),
                request_digest=request_digest,
                created_at=now,
                payload=root,
            ),
        )
        stored, replayed = self.evidence.append_records(
            records,
            expected_workspace_record_journal_head=head,
        )
        return {
            "consentGrant": validate_consent_grant_root(
                _payload(stored[1], CONSENT_GRANT_RECORD_KIND)
            ).as_dict(),
            "consentGrantVersion": validate_consent_grant_version_v2(
                _payload(stored[0], CONSENT_GRANT_VERSION_RECORD_KIND)
            ).as_dict(),
            "idempotentReplay": replayed,
        }

    @_coordinated_transition
    def create_consent_grant_successor(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._CONSENT_SUCCESSOR_FIELDS,
            operation="create-consent-grant-successor",
        )
        for field in (
            "consentGrantRef",
            "baseConsentGrantVersionRef",
            "rightsBindingRef",
            "evidenceRef",
            "createdBy",
        ):
            _required_ref(value[field], field)
        for field in (
            "baseConsentGrantVersionDigest",
            "rightsBindingDigest",
            "evidenceDigest",
        ):
            _sha256(value[field], field)
        allowed = _token_list(
            value["allowedUses"], "allowedUses", allowed=CONSENT_ALLOWED_USES
        )
        prohibited = _token_list(
            value["prohibitedUses"], "prohibitedUses", allow_empty=True
        )
        territories = _token_list(value["territories"], "territories")
        if set(allowed) & set(prohibited):
            raise VoiceProfileLineageError("ConsentGrantVersion use scopes overlap")
        if value["revocationState"] not in CONSENT_REVOCATION_STATES:
            raise VoiceProfileLineageError("revocationState is invalid")
        if value["revocationState"] == "ACTIVE" and set(allowed) != REQUIRED_CLONE_CONSENT_USES:
            raise VoiceProfileLineageNotEffectiveError(
                "active ConsentGrantVersion must authorize every clone use"
            )
        valid_from = _utc_instant(value["validFrom"], "validFrom")
        expires_at = _utc_instant(value["expiresAt"], "expiresAt")
        if valid_from >= expires_at:
            raise VoiceProfileLineageError("ConsentGrantVersion interval is invalid")
        request_digest = _digest(
            {"operation": "create-consent-grant-successor", "command": value}
        )
        replay = self._replay(
            workspace=workspace,
            run_ref=run_ref,
            operation="create-consent-grant-successor",
            client_key=key,
            request_digest=request_digest,
            primary_kind=CONSENT_GRANT_VERSION_RECORD_KIND,
        )
        if replay is not None:
            return {
                "consentGrantVersion": validate_consent_grant_version_v2(
                    replay[1]
                ).as_dict(),
                "idempotentReplay": True,
            }
        head, snapshot = self._snapshot(workspace, run_ref)
        root_record, root_payload = _canonical_record(
            snapshot,
            kind=CONSENT_GRANT_RECORD_KIND,
            ref=value["consentGrantRef"],
        )
        root = validate_consent_grant_root(root_payload).as_dict()
        if tuple(root[field] for field in _SCOPE_FIELDS) != scope:
            raise VoiceProfileLineageNotFoundError("ConsentGrant was not found")
        versions = self._consent_versions(snapshot, value["consentGrantRef"])
        parent = versions[-1]
        if (
            parent["consentGrantVersionRef"]
            != value["baseConsentGrantVersionRef"]
            or parent["payloadDigest"] != value["baseConsentGrantVersionDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "ConsentGrantVersion predecessor is stale"
            )
        if parent["revocationState"] == "REVOKED":
            raise VoiceProfileLineageNotEffectiveError(
                "revoked ConsentGrantVersion cannot have a successor"
            )
        if value["revocationState"] == "ACTIVE":
            downstream_locks = self._authoritative_clone_lock_versions(scope)
            downstream_profiles = [
                validate_voice_profile_version(
                    _payload(record, VOICE_PROFILE_VERSION_RECORD_KIND)
                ).as_dict()
                for record in snapshot.records
                if record.get("recordKind")
                == VOICE_PROFILE_VERSION_RECORD_KIND
                and isinstance(record.get("payload"), Mapping)
            ]
            grant_version_identities = {
                (
                    item["consentGrantVersionRef"],
                    item["payloadDigest"],
                )
                for item in versions
            }
            if any(
                item["sourceRecordingBindingRef"]
                == parent["sourceRecordingBindingRef"]
                and (
                    item["consentGrantVersionRef"],
                    item["consentGrantVersionDigest"],
                )
                in grant_version_identities
                for item in (*downstream_locks, *downstream_profiles)
            ):
                raise VoiceProfileLineageNotEffectiveError(
                    "active Consent successor is forbidden after clone descendants"
                )
        source = self._source_binding(
            snapshot,
            ref=parent["sourceRecordingBindingRef"],
            digest=parent["sourceRecordingBindingDigest"],
        )
        parent_rights = self._rights_binding(
            snapshot,
            ref=parent["rightsBindingRef"],
            digest=parent["rightsBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=value["rightsBindingRef"],
            digest=value["rightsBindingDigest"],
        )
        required_rights_sources = {
            (
                source["canonicalAssetVersionRef"],
                source["canonicalAssetVersionDigest"],
            ),
            (value["evidenceRef"], value["evidenceDigest"]),
            (parent_rights["rightsBindingRef"], parent_rights["payloadDigest"]),
        }
        actual_rights_sources = {
            (item.get("sourceRef"), item.get("sourceDigest"))
            for item in rights["sourceRefs"]
        }
        if (
            rights["rightsBindingRef"] == parent_rights["rightsBindingRef"]
            or not required_rights_sources.issubset(actual_rights_sources)
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "Consent successor RightsBinding lineage is incomplete"
            )
        version_ref = _required_ref(
            self._ref_factory("consent-grant-version"),
            "consentGrantVersionRef",
        )
        successor = validate_consent_grant_version_v2(
            _seal(
                {
                    **{
                        field: parent[field]
                        for field in (
                            "schemaVersion",
                            "workspaceRef",
                            "projectRef",
                            "seriesRef",
                            "consentGrantRef",
                            "sourceRecordingBindingRef",
                            "sourceRecordingBindingDigest",
                            "subjectRef",
                            "grantorRef",
                        )
                    },
                    "rightsBindingRef": rights["rightsBindingRef"],
                    "rightsBindingDigest": rights["payloadDigest"],
                    "consentGrantVersionRef": version_ref,
                    "allowedUses": allowed,
                    "prohibitedUses": prohibited,
                    "territories": territories,
                    "validFrom": value["validFrom"],
                    "expiresAt": value["expiresAt"],
                    "revocationState": value["revocationState"],
                    "evidenceRef": value["evidenceRef"],
                    "evidenceDigest": value["evidenceDigest"],
                    "versionNumber": parent["versionNumber"] + 1,
                    "parentConsentGrantVersionRef": parent[
                        "consentGrantVersionRef"
                    ],
                    "parentConsentGrantVersionDigest": parent["payloadDigest"],
                    "createdAt": now,
                    "createdBy": value["createdBy"],
                }
            )
        ).as_dict()
        item = _evidence_record(
            workspace_ref=workspace,
            run_ref=_required_ref(
                root_record.get("productionRunRef"),
                "ConsentGrant.ownerProductionRunRef",
            ),
            kind=CONSENT_GRANT_VERSION_RECORD_KIND,
            ref=version_ref,
            version=successor["versionNumber"],
            idempotency_key=_operation_key(
                key, "create-consent-grant-successor", 1
            ),
            request_digest=request_digest,
            created_at=now,
            payload=successor,
        )
        stored, replayed = self.evidence.append_records(
            (item,),
            expected_workspace_record_journal_head=head,
        )
        return {
            "consentGrantVersion": validate_consent_grant_version_v2(
                _payload(stored[0], CONSENT_GRANT_VERSION_RECORD_KIND)
            ).as_dict(),
            "idempotentReplay": replayed,
        }

    def _authoritative_clone_lock_versions(
        self, scope: tuple[str, str, str]
    ) -> list[dict[str, Any]]:
        try:
            versions = self.voice_locks.list_clone_voice_lock_versions(*scope)
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "VoiceLock authority is unavailable"
            ) from exc
        validated = [
            validate_clone_voice_lock_version_v2(item) for item in versions
        ]
        identities: set[tuple[str, str, str]] = set()
        for item in validated:
            if tuple(item[field] for field in _SCOPE_FIELDS) != scope:
                raise RepositoryUnavailableError(
                    "VoiceLock authority returned a foreign scope"
                )
            identity = (
                item["voiceRef"],
                item["voiceLockVersionRef"],
                item["payloadDigest"],
            )
            if identity in identities:
                raise RepositoryUnavailableError(
                    "VoiceLock authority returned duplicate v2 versions"
                )
            identities.add(identity)
        return validated

    def _authoritative_confirmed_clone_lock(
        self,
        scope: tuple[str, str, str],
        *,
        voice_ref: str,
    ) -> dict[str, Any]:
        try:
            bundle = self.voice_locks.get_confirmed_clone_voice_lock(
                *scope,
                _required_ref(voice_ref, "voiceRef"),
            )
            result = validate_confirmed_clone_voice_lock_bundle(bundle)
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "VoiceLock authority is unavailable"
            ) from exc
        root = result["voiceLock"]
        version = result["voiceLockVersion"]
        confirmation = result["voiceLockConfirmation"]
        if any(
            tuple(item[field] for field in _SCOPE_FIELDS) != scope
            for item in (root, version, confirmation)
        ):
            raise RepositoryUnavailableError(
                "confirmed VoiceLock authority scope is invalid"
            )
        return result

    @_coordinated_transition
    def create_clone_voice_lock(self, command: Mapping[str, Any]) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._VOICE_LOCK_CREATE_FIELDS,
            operation="create-clone-voice-lock",
        )
        for field in (
            "voiceRef",
            "baseVoiceLockVersionRef",
            "subjectRef",
            "sourceRecordingBindingRef",
            "consentGrantVersionRef",
            "rightsBindingRef",
            "voiceIdentityRef",
            "voiceIdentityVersionRef",
            "languageCode",
        ):
            _required_ref(value[field], field)
        for field in (
            "baseVoiceLockDigest",
            "sourceRecordingBindingDigest",
            "consentGrantVersionDigest",
            "rightsBindingDigest",
            "voiceIdentityDigest",
        ):
            _sha256(value[field], field)
        _positive_int(value["expectedRevision"], "expectedRevision")
        _text(value["engineFamily"], "engineFamily")
        _text(value["voiceId"], "voiceId")
        if (
            value["engineFamily"] != CLONE_VOICE_ENGINE_FAMILY
            or value["voiceId"] != CLONE_VOICE_MODEL_ID
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "clone VoiceLock requires the frozen zero-shot clone runtime"
            )

        _, snapshot = self._snapshot(workspace, run_ref)
        source = self._source_binding(
            snapshot,
            ref=value["sourceRecordingBindingRef"],
            digest=value["sourceRecordingBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=value["rightsBindingRef"],
            digest=value["rightsBindingDigest"],
        )
        consent = self._current_consent(
            snapshot,
            version_ref=value["consentGrantVersionRef"],
            digest=value["consentGrantVersionDigest"],
            evaluated_at=now,
            source_binding=source,
            rights_binding=rights,
        )
        _require_series_scope(
            source, scope, "SourceVoiceRecordingAssetVersionBinding"
        )
        _require_series_scope(consent, scope, "ConsentGrantVersion")
        if (
            source["subjectRef"] != value["subjectRef"]
            or consent["subjectRef"] != value["subjectRef"]
            or consent["rightsBindingRef"] != rights["rightsBindingRef"]
            or consent["rightsBindingDigest"] != rights["payloadDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "clone VoiceLock subject or rights lineage is stale"
            )

        owner_command = {
            "workspaceRef": scope[0],
            "projectRef": scope[1],
            "seriesRef": scope[2],
            "voiceRef": value["voiceRef"],
            "baseVoiceLockVersionRef": value["baseVoiceLockVersionRef"],
            "baseVoiceLockDigest": value["baseVoiceLockDigest"],
            "expectedRevision": value["expectedRevision"],
            "idempotencyKey": key,
            "engineFamily": value["engineFamily"],
            "voiceId": value["voiceId"],
            "gender": value["gender"],
            "apparentAge": value["apparentAge"],
            "pitchSemitones": value["pitchSemitones"],
            "rateScale": value["rateScale"],
            "timbreDescriptor": value["timbreDescriptor"],
            "languageCode": value["languageCode"],
            "sourceRecordingBindingRef": source[
                "sourceRecordingBindingRef"
            ],
            "sourceRecordingBindingDigest": source["payloadDigest"],
            "consentGrantVersionRef": consent["consentGrantVersionRef"],
            "consentGrantVersionDigest": consent["payloadDigest"],
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
            "voiceIdentityRef": value["voiceIdentityRef"],
            "voiceIdentityVersionRef": value["voiceIdentityVersionRef"],
            "voiceIdentityDigest": value["voiceIdentityDigest"],
            "subjectRef": source["subjectRef"],
        }
        try:
            result = self.voice_locks.create_clone_voice_lock_version(
                owner_command
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "VoiceLock authority is unavailable"
            ) from exc
        root = validate_clone_voice_lock(result["voiceLock"])
        version = validate_clone_voice_lock_version_v2(
            result["voiceLockVersion"]
        )
        if (
            tuple(root[field] for field in _SCOPE_FIELDS) != scope
            or tuple(version[field] for field in _SCOPE_FIELDS) != scope
            or root["voiceRef"] != value["voiceRef"]
            or version["voiceRef"] != root["voiceRef"]
            or version["characterRef"] != root["characterRef"]
            or version["subjectRef"] != source["subjectRef"]
            or version["sourceRecordingBindingRef"]
            != source["sourceRecordingBindingRef"]
            or version["sourceRecordingBindingDigest"] != source["payloadDigest"]
            or version["consentGrantVersionRef"]
            != consent["consentGrantVersionRef"]
            or version["consentGrantVersionDigest"] != consent["payloadDigest"]
            or version["rightsBindingRef"] != rights["rightsBindingRef"]
            or version["rightsBindingDigest"] != rights["payloadDigest"]
        ):
            raise RepositoryUnavailableError(
                "VoiceLock authority returned stale clone lineage"
            )
        return {
            "voiceLock": root,
            "voiceLockVersion": version,
            "idempotentReplay": result.get("idempotentReplay") is True,
        }

    @_coordinated_transition
    def confirm_clone_voice_lock(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._VOICE_LOCK_CONFIRM_FIELDS,
            operation="confirm-clone-voice-lock",
        )
        for field in ("voiceRef", "voiceLockVersionRef"):
            _required_ref(value[field], field)
        version_digest = _sha256(
            value["voiceLockVersionDigest"], "voiceLockVersionDigest"
        )
        _positive_int(value["expectedRevision"], "expectedRevision")
        _, snapshot = self._snapshot(workspace, run_ref)
        matching = [
            item
            for item in self._authoritative_clone_lock_versions(scope)
            if item["voiceRef"] == value["voiceRef"]
            and item["voiceLockVersionRef"] == value["voiceLockVersionRef"]
            and item["payloadDigest"] == version_digest
        ]
        if len(matching) != 1:
            raise VoiceProfileLineageStaleError(
                "clone VoiceLockVersion authority is stale"
            )
        version = matching[0]
        source = self._source_binding(
            snapshot,
            ref=version["sourceRecordingBindingRef"],
            digest=version["sourceRecordingBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=version["rightsBindingRef"],
            digest=version["rightsBindingDigest"],
        )
        self._current_consent(
            snapshot,
            version_ref=version["consentGrantVersionRef"],
            digest=version["consentGrantVersionDigest"],
            evaluated_at=now,
            source_binding=source,
            rights_binding=rights,
        )
        try:
            result = self.voice_locks.confirm_clone_voice_lock(
                {
                    "workspaceRef": scope[0],
                    "projectRef": scope[1],
                    "seriesRef": scope[2],
                    "voiceRef": value["voiceRef"],
                    "voiceLockVersionRef": value["voiceLockVersionRef"],
                    "voiceLockDigest": version_digest,
                    "expectedRevision": value["expectedRevision"],
                    "idempotencyKey": key,
                }
            )
        except EpisodeProductionError:
            raise
        except Exception as exc:
            raise RepositoryUnavailableError(
                "VoiceLock authority is unavailable"
            ) from exc
        bundle = validate_confirmed_clone_voice_lock_bundle(result)
        if (
            bundle["voiceLockVersion"]["voiceLockVersionRef"]
            != value["voiceLockVersionRef"]
            or bundle["voiceLockVersion"]["payloadDigest"] != version_digest
        ):
            raise RepositoryUnavailableError(
                "VoiceLock authority confirmed a different clone version"
            )
        return {
            **bundle,
            "idempotentReplay": result.get("idempotentReplay") is True,
        }

    def _confirmed_clone_lock(
        self,
        *,
        scope: tuple[str, str, str],
        voice_ref: str,
        version_ref: str,
        version_digest: str,
        confirmation_ref: str,
        confirmation_digest: str,
    ) -> dict[str, Any]:
        bundle = self._authoritative_confirmed_clone_lock(
            scope, voice_ref=voice_ref
        )
        root = bundle["voiceLock"]
        version = bundle["voiceLockVersion"]
        confirmation = bundle["voiceLockConfirmation"]
        if (
            version["voiceLockVersionRef"]
            != _required_ref(version_ref, "voiceLockVersionRef")
            or version["payloadDigest"]
            != _sha256(version_digest, "voiceLockVersionDigest")
            or confirmation["voiceLockConfirmationRef"]
            != _required_ref(
                confirmation_ref, "voiceLockConfirmationRef"
            )
            or confirmation["payloadDigest"]
            != _sha256(
                confirmation_digest, "voiceLockConfirmationDigest"
            )
            or root["voiceRef"] != voice_ref
        ):
            raise VoiceProfileLineageStaleError(
                "confirmed clone VoiceLock authority is stale"
            )
        return bundle

    @staticmethod
    def _profile_package_evidence(
        snapshot: EvidenceSnapshot,
        package: Mapping[str, Any],
        *,
        runtime_pins: Mapping[str, Any],
    ) -> dict[str, Any]:
        selected = _profile_package(package)
        record, evidence = _canonical_record(
            snapshot,
            kind="VoiceProfileTechnicalValidation",
            ref=selected["technicalValidationRef"],
            digest=selected["technicalValidationDigest"],
        )
        evidence = validate_voice_profile_technical_validation(evidence)
        if evidence["technicalValidationRef"] != record["recordRef"]:
            raise VoiceProfileLineageStaleError(
                "VoiceProfile technical validation identity is stale"
            )
        expected = {
            field: selected[field]
            for field in (
                "storageBindingRef",
                "byteSize",
                "fileDigest",
                "contentDigest",
                "packageFormat",
                "packageSchemaVersion",
            )
        }
        runtime_fields = (
            "engineId",
            "engineCommit",
            "modelId",
            "modelBundleDigest",
            "dependencyLockDigest",
            "runtimeManifestDigest",
        )
        if (
            any(evidence.get(field) != item for field, item in expected.items())
            or any(
                evidence.get(field) != runtime_pins.get(field)
                for field in runtime_fields
            )
        ):
            raise VoiceProfileLineageStaleError(
                "VoiceProfile package or runtime technical evidence drifted"
            )
        return evidence

    @staticmethod
    def _profile_versions(
        snapshot: EvidenceSnapshot, voice_profile_ref: str
    ) -> list[dict[str, Any]]:
        versions = [
            validate_voice_profile_version(
                _payload(record, "VoiceProfileVersion")
            ).as_dict()
            for record in snapshot.records
            if record.get("recordKind") == VOICE_PROFILE_VERSION_RECORD_KIND
            and isinstance(record.get("payload"), Mapping)
            and record["payload"].get("voiceProfileRef") == voice_profile_ref
        ]
        versions.sort(key=lambda item: item["versionNumber"])
        if not versions:
            raise VoiceProfileLineageNotFoundError("VoiceProfileVersion was not found")
        immutable_fields = (
            "workspaceRef",
            "projectRef",
            "seriesRef",
            "subjectRef",
            "voiceIdentityRef",
            "voiceIdentityVersionRef",
            "voiceIdentityDigest",
            "voiceLockRef",
            "voiceLockVersionRef",
            "voiceLockVersionDigest",
            "voiceLockConfirmationRef",
            "voiceLockConfirmationDigest",
            "sourceRecordingBindingRef",
            "sourceRecordingBindingDigest",
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
            "profilePackage",
        )
        for index, item in enumerate(versions, start=1):
            if item["versionNumber"] != index:
                raise RepositoryUnavailableError(
                    "VoiceProfileVersion lineage is not contiguous"
                )
            if index == 1:
                if item["status"] != "CANDIDATE":
                    raise RepositoryUnavailableError(
                        "initial VoiceProfileVersion must be CANDIDATE"
                    )
                continue
            parent = versions[index - 2]
            if (
                item["parentVoiceProfileVersionRef"]
                != parent["voiceProfileVersionRef"]
                or item["parentVoiceProfileVersionDigest"]
                != parent["payloadDigest"]
                or any(item[field] != parent[field] for field in immutable_fields)
                or (parent["status"], item["status"])
                not in {("CANDIDATE", "CONFIRMED"), ("CONFIRMED", "REVOKED")}
            ):
                raise RepositoryUnavailableError(
                    "VoiceProfileVersion predecessor lineage is invalid"
                )
        return versions

    @_coordinated_transition
    def create_voice_profile(self, command: Mapping[str, Any]) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._PROFILE_CREATE_FIELDS,
            operation="create-voice-profile",
        )
        for field in (
            "voiceRef",
            "voiceLockVersionRef",
            "voiceLockConfirmationRef",
            "createdBy",
        ):
            _required_ref(value[field], field)
        _clone_runtime_identity(value, prefix="create VoiceProfile")
        for field in (
            "voiceLockVersionDigest",
            "voiceLockConfirmationDigest",
            "modelBundleDigest",
            "dependencyLockDigest",
            "runtimeManifestDigest",
        ):
            _sha256(value[field], field)
        package = _profile_package(value["profilePackage"])
        request_digest = _digest(
            {"operation": "create-voice-profile", "command": value}
        )
        replay = self._replay(
            workspace=workspace,
            run_ref=run_ref,
            operation="create-voice-profile",
            client_key=key,
            request_digest=request_digest,
            primary_kind=VOICE_PROFILE_VERSION_RECORD_KIND,
        )
        if replay is not None:
            version = validate_voice_profile_version(replay[1]).as_dict()
            _, snapshot = self._snapshot(workspace, run_ref)
            _, root_payload = _canonical_record(
                snapshot,
                kind=VOICE_PROFILE_RECORD_KIND,
                ref=version["voiceProfileRef"],
            )
            return {
                "voiceProfile": validate_voice_profile(root_payload).as_dict(),
                "voiceProfileVersion": version,
                "idempotentReplay": True,
            }
        head, snapshot = self._snapshot(workspace, run_ref)
        lock = self._confirmed_clone_lock(
            scope=scope,
            voice_ref=value["voiceRef"],
            version_ref=value["voiceLockVersionRef"],
            version_digest=value["voiceLockVersionDigest"],
            confirmation_ref=value["voiceLockConfirmationRef"],
            confirmation_digest=value["voiceLockConfirmationDigest"],
        )
        lock_version = lock["voiceLockVersion"]
        if lock_version["engineFamily"] != value["engineId"]:
            raise VoiceProfileLineageNotEffectiveError(
                "VoiceProfile engine does not match clone VoiceLock runtime"
            )
        source = self._source_binding(
            snapshot,
            ref=lock_version["sourceRecordingBindingRef"],
            digest=lock_version["sourceRecordingBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=lock_version["rightsBindingRef"],
            digest=lock_version["rightsBindingDigest"],
        )
        consent = self._current_consent(
            snapshot,
            version_ref=lock_version["consentGrantVersionRef"],
            digest=lock_version["consentGrantVersionDigest"],
            evaluated_at=now,
            source_binding=source,
            rights_binding=rights,
        )
        _require_series_scope(lock["voiceLock"], scope, "VoiceLock")
        _require_series_scope(lock_version, scope, "VoiceLockVersion")
        _require_series_scope(source, scope, "SourceVoiceRecordingAssetVersionBinding")
        _require_series_scope(consent, scope, "ConsentGrantVersion")
        self._profile_package_evidence(
            snapshot,
            package,
            runtime_pins={
                field: value[field]
                for field in (
                    "engineId",
                    "engineCommit",
                    "modelId",
                    "modelBundleDigest",
                    "dependencyLockDigest",
                    "runtimeManifestDigest",
                )
            },
        )
        roots = [
            validate_voice_profile(_payload(record, "VoiceProfile")).as_dict()
            for record in snapshot.records
            if record.get("recordKind") == VOICE_PROFILE_RECORD_KIND
            and isinstance(record.get("payload"), Mapping)
            and tuple(record["payload"].get(field) for field in _SCOPE_FIELDS)
            == scope
        ]
        if any(
            item["subjectRef"] == source["subjectRef"] for item in roots
        ):
            raise IdempotencyConflictError(
                "subject already has a VoiceProfile authority root"
            )
        profile_ref = _required_ref(
            self._ref_factory("voice-profile"), "voiceProfileRef"
        )
        version_ref = _required_ref(
            self._ref_factory("voice-profile-version"),
            "voiceProfileVersionRef",
        )
        root = validate_voice_profile(
            _seal(
                {
                    "schemaVersion": VOICE_PROFILE_SCHEMA_VERSION,
                    "voiceProfileRef": profile_ref,
                    "workspaceRef": scope[0],
                    "projectRef": scope[1],
                    "seriesRef": scope[2],
                    "subjectRef": source["subjectRef"],
                    "createdAt": now,
                }
            )
        ).as_dict()
        version = validate_voice_profile_version(
            _seal(
                {
                    "schemaVersion": VOICE_PROFILE_VERSION_SCHEMA_VERSION,
                    "voiceProfileRef": profile_ref,
                    "voiceProfileVersionRef": version_ref,
                    "versionNumber": 1,
                    "parentVoiceProfileVersionRef": None,
                    "parentVoiceProfileVersionDigest": None,
                    "workspaceRef": scope[0],
                    "projectRef": scope[1],
                    "seriesRef": scope[2],
                    "subjectRef": source["subjectRef"],
                    "voiceIdentityRef": lock_version["voiceIdentityRef"],
                    "voiceIdentityVersionRef": lock_version[
                        "voiceIdentityVersionRef"
                    ],
                    "voiceIdentityDigest": lock_version["voiceIdentityDigest"],
                    "voiceLockRef": lock["voiceLock"]["voiceRef"],
                    "voiceLockVersionRef": lock_version[
                        "voiceLockVersionRef"
                    ],
                    "voiceLockVersionDigest": lock_version["payloadDigest"],
                    "voiceLockConfirmationRef": lock[
                        "voiceLockConfirmation"
                    ]["voiceLockConfirmationRef"],
                    "voiceLockConfirmationDigest": lock[
                        "voiceLockConfirmation"
                    ]["payloadDigest"],
                    "sourceRecordingBindingRef": source[
                        "sourceRecordingBindingRef"
                    ],
                    "sourceRecordingBindingDigest": source["payloadDigest"],
                    "consentGrantVersionRef": consent[
                        "consentGrantVersionRef"
                    ],
                    "consentGrantVersionDigest": consent["payloadDigest"],
                    "rightsBindingRef": rights["rightsBindingRef"],
                    "rightsBindingDigest": rights["payloadDigest"],
                    "engineId": value["engineId"],
                    "engineCommit": value["engineCommit"],
                    "modelId": value["modelId"],
                    "modelBundleDigest": value["modelBundleDigest"],
                    "dependencyLockDigest": value["dependencyLockDigest"],
                    "runtimeManifestDigest": value["runtimeManifestDigest"],
                    "profilePackage": package,
                    "status": "CANDIDATE",
                    "createdAt": now,
                    "createdBy": value["createdBy"],
                    "confirmedAt": None,
                }
            )
        ).as_dict()
        records = (
            _evidence_record(
                workspace_ref=workspace,
                run_ref=run_ref,
                kind=VOICE_PROFILE_VERSION_RECORD_KIND,
                ref=version_ref,
                version=1,
                idempotency_key=_operation_key(key, "create-voice-profile", 1),
                request_digest=request_digest,
                created_at=now,
                payload=version,
            ),
            _evidence_record(
                workspace_ref=workspace,
                run_ref=run_ref,
                kind=VOICE_PROFILE_RECORD_KIND,
                ref=profile_ref,
                version=1,
                idempotency_key=_operation_key(key, "create-voice-profile", 2),
                request_digest=request_digest,
                created_at=now,
                payload=root,
            ),
        )
        stored, replayed = self.evidence.append_records(
            records,
            expected_workspace_record_journal_head=head,
        )
        return {
            "voiceProfile": validate_voice_profile(
                _payload(stored[1], VOICE_PROFILE_RECORD_KIND)
            ).as_dict(),
            "voiceProfileVersion": validate_voice_profile_version(
                _payload(stored[0], VOICE_PROFILE_VERSION_RECORD_KIND)
            ).as_dict(),
            "idempotentReplay": replayed,
        }

    @_coordinated_transition
    def create_voice_profile_successor(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        value, workspace, run_ref, key, scope, now = self._context(
            command,
            fields=self._PROFILE_SUCCESSOR_FIELDS,
            operation="create-voice-profile-successor",
        )
        for field in (
            "voiceProfileRef",
            "baseVoiceProfileVersionRef",
            "createdBy",
        ):
            _required_ref(value[field], field)
        _sha256(value["baseVoiceProfileVersionDigest"], "baseVoiceProfileVersionDigest")
        if value["status"] not in {"CONFIRMED", "REVOKED"}:
            raise VoiceProfileLineageError(
                "VoiceProfile successor status is invalid"
            )
        request_digest = _digest(
            {"operation": "create-voice-profile-successor", "command": value}
        )
        replay = self._replay(
            workspace=workspace,
            run_ref=run_ref,
            operation="create-voice-profile-successor",
            client_key=key,
            request_digest=request_digest,
            primary_kind=VOICE_PROFILE_VERSION_RECORD_KIND,
        )
        if replay is not None:
            return {
                "voiceProfileVersion": validate_voice_profile_version(
                    replay[1]
                ).as_dict(),
                "idempotentReplay": True,
            }
        head, snapshot = self._snapshot(workspace, run_ref)
        root_record, root_payload = _canonical_record(
            snapshot,
            kind=VOICE_PROFILE_RECORD_KIND,
            ref=value["voiceProfileRef"],
        )
        root = validate_voice_profile(root_payload).as_dict()
        if tuple(root[field] for field in _SCOPE_FIELDS) != scope:
            raise VoiceProfileLineageNotFoundError("VoiceProfile was not found")
        versions = self._profile_versions(snapshot, value["voiceProfileRef"])
        parent = versions[-1]
        if (
            parent["voiceProfileVersionRef"]
            != value["baseVoiceProfileVersionRef"]
            or parent["payloadDigest"] != value["baseVoiceProfileVersionDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "VoiceProfileVersion predecessor is stale"
            )
        transition = (parent["status"], value["status"])
        if transition not in {("CANDIDATE", "CONFIRMED"), ("CONFIRMED", "REVOKED")}:
            raise VoiceProfileLineageNotEffectiveError(
                "VoiceProfileVersion lifecycle transition is not allowed"
            )
        if value["status"] == "CONFIRMED":
            lock = self._confirmed_clone_lock(
                scope=scope,
                voice_ref=parent["voiceLockRef"],
                version_ref=parent["voiceLockVersionRef"],
                version_digest=parent["voiceLockVersionDigest"],
                confirmation_ref=parent["voiceLockConfirmationRef"],
                confirmation_digest=parent["voiceLockConfirmationDigest"],
            )
            lock_version = lock["voiceLockVersion"]
            source = self._source_binding(
                snapshot,
                ref=parent["sourceRecordingBindingRef"],
                digest=parent["sourceRecordingBindingDigest"],
            )
            rights = self._rights_binding(
                snapshot,
                ref=parent["rightsBindingRef"],
                digest=parent["rightsBindingDigest"],
            )
            consent = self._current_consent(
                snapshot,
                version_ref=parent["consentGrantVersionRef"],
                digest=parent["consentGrantVersionDigest"],
                evaluated_at=now,
                source_binding=source,
                rights_binding=rights,
            )
            if (
                lock_version["sourceRecordingBindingRef"]
                != source["sourceRecordingBindingRef"]
                or lock_version["sourceRecordingBindingDigest"]
                != source["payloadDigest"]
                or lock_version["consentGrantVersionRef"]
                != consent["consentGrantVersionRef"]
                or lock_version["consentGrantVersionDigest"]
                != consent["payloadDigest"]
                or lock_version["rightsBindingRef"] != rights["rightsBindingRef"]
                or lock_version["rightsBindingDigest"] != rights["payloadDigest"]
                or parent["voiceIdentityRef"]
                != lock_version["voiceIdentityRef"]
                or parent["voiceIdentityVersionRef"]
                != lock_version["voiceIdentityVersionRef"]
                or parent["voiceIdentityDigest"]
                != lock_version["voiceIdentityDigest"]
                or parent["voiceLockRef"] != lock["voiceLock"]["voiceRef"]
                or lock_version["engineFamily"] != parent["engineId"]
            ):
                raise VoiceProfileLineageStaleError(
                    "VoiceProfile upstream lineage is stale"
                )
            confirmed_at = now
        else:
            confirmed_at = parent["confirmedAt"]
        version_ref = _required_ref(
            self._ref_factory("voice-profile-version"),
            "voiceProfileVersionRef",
        )
        successor_payload = {
            **{
                field: parent[field]
                for field in _VOICE_PROFILE_VERSION_FIELDS
                if field
                not in {
                    "voiceProfileVersionRef",
                    "versionNumber",
                    "parentVoiceProfileVersionRef",
                    "parentVoiceProfileVersionDigest",
                    "status",
                    "createdAt",
                    "createdBy",
                    "confirmedAt",
                    "payloadDigest",
                }
            },
            "voiceProfileVersionRef": version_ref,
            "versionNumber": parent["versionNumber"] + 1,
            "parentVoiceProfileVersionRef": parent["voiceProfileVersionRef"],
            "parentVoiceProfileVersionDigest": parent["payloadDigest"],
            "status": value["status"],
            "createdAt": now,
            "createdBy": value["createdBy"],
            "confirmedAt": confirmed_at,
        }
        successor = validate_voice_profile_version(
            _seal(successor_payload)
        ).as_dict()
        item = _evidence_record(
            workspace_ref=workspace,
            run_ref=_required_ref(
                root_record.get("productionRunRef"),
                "VoiceProfile.ownerProductionRunRef",
            ),
            kind=VOICE_PROFILE_VERSION_RECORD_KIND,
            ref=version_ref,
            version=successor["versionNumber"],
            idempotency_key=_operation_key(
                key, "create-voice-profile-successor", 1
            ),
            request_digest=request_digest,
            created_at=now,
            payload=successor,
        )
        stored, replayed = self.evidence.append_records(
            (item,),
            expected_workspace_record_journal_head=head,
        )
        return {
            "voiceProfileVersion": validate_voice_profile_version(
                _payload(stored[0], VOICE_PROFILE_VERSION_RECORD_KIND)
            ).as_dict(),
            "idempotentReplay": replayed,
        }

    def _current_confirmed_profile_components(
        self,
        snapshot: EvidenceSnapshot,
        *,
        scope: tuple[str, str, str],
        voice_profile_version_ref: str,
        voice_profile_version_digest: str,
        evaluated_at: str,
    ) -> dict[str, Any]:
        _, selected_payload = _canonical_version_record(
            snapshot,
            kind=VOICE_PROFILE_VERSION_RECORD_KIND,
            ref=_required_ref(
                voice_profile_version_ref, "voiceProfileVersionRef"
            ),
            digest=_sha256(
                voice_profile_version_digest, "voiceProfileVersionDigest"
            ),
        )
        profile = validate_voice_profile_version(selected_payload).as_dict()
        versions = self._profile_versions(snapshot, profile["voiceProfileRef"])
        if (
            versions[-1]["voiceProfileVersionRef"]
            != profile["voiceProfileVersionRef"]
            or profile["status"] != "CONFIRMED"
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "VoiceProfileVersion is not the current confirmed head"
            )
        _, root_payload = _canonical_record(
            snapshot,
            kind=VOICE_PROFILE_RECORD_KIND,
            ref=profile["voiceProfileRef"],
        )
        root = validate_voice_profile(root_payload).as_dict()
        if (
            tuple(root[field] for field in _SCOPE_FIELDS) != scope
            or tuple(profile[field] for field in _SCOPE_FIELDS) != scope
            or root["voiceProfileRef"] != profile["voiceProfileRef"]
            or root["subjectRef"] != profile["subjectRef"]
        ):
            raise VoiceProfileLineageNotFoundError("VoiceProfile was not found")
        source = self._source_binding(
            snapshot,
            ref=profile["sourceRecordingBindingRef"],
            digest=profile["sourceRecordingBindingDigest"],
        )
        rights = self._rights_binding(
            snapshot,
            ref=profile["rightsBindingRef"],
            digest=profile["rightsBindingDigest"],
        )
        consent = self._current_consent(
            snapshot,
            version_ref=profile["consentGrantVersionRef"],
            digest=profile["consentGrantVersionDigest"],
            evaluated_at=evaluated_at,
            source_binding=source,
            rights_binding=rights,
        )
        lock = self._confirmed_clone_lock(
            scope=scope,
            voice_ref=profile["voiceLockRef"],
            version_ref=profile["voiceLockVersionRef"],
            version_digest=profile["voiceLockVersionDigest"],
            confirmation_ref=profile["voiceLockConfirmationRef"],
            confirmation_digest=profile["voiceLockConfirmationDigest"],
        )
        _require_series_scope(source, scope, "SourceVoiceRecordingAssetVersionBinding")
        _require_series_scope(consent, scope, "ConsentGrantVersion")
        _require_series_scope(lock["voiceLock"], scope, "VoiceLock")
        _require_series_scope(lock["voiceLockVersion"], scope, "VoiceLockVersion")
        self._profile_package_evidence(
            snapshot,
            profile["profilePackage"],
            runtime_pins={
                field: profile[field]
                for field in (
                    "engineId",
                    "engineCommit",
                    "modelId",
                    "modelBundleDigest",
                    "dependencyLockDigest",
                    "runtimeManifestDigest",
                )
            },
        )
        lock_version = lock["voiceLockVersion"]
        if (
            profile["subjectRef"] != source["subjectRef"]
            or lock_version["subjectRef"] != source["subjectRef"]
            or lock_version["sourceRecordingBindingRef"]
            != source["sourceRecordingBindingRef"]
            or lock_version["sourceRecordingBindingDigest"]
            != source["payloadDigest"]
            or lock_version["consentGrantVersionRef"]
            != consent["consentGrantVersionRef"]
            or lock_version["consentGrantVersionDigest"]
            != consent["payloadDigest"]
            or lock_version["rightsBindingRef"] != rights["rightsBindingRef"]
            or lock_version["rightsBindingDigest"] != rights["payloadDigest"]
            or profile["voiceIdentityRef"] != lock_version["voiceIdentityRef"]
            or profile["voiceIdentityVersionRef"]
            != lock_version["voiceIdentityVersionRef"]
            or profile["voiceIdentityDigest"]
            != lock_version["voiceIdentityDigest"]
            or lock_version["engineFamily"] != profile["engineId"]
        ):
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile upstream lineage is stale"
            )
        rights_sources = rights["sourceRefs"]
        if not any(
            item.get("sourceRef") == source["canonicalAssetVersionRef"]
            and item.get("sourceDigest")
            == source["canonicalAssetVersionDigest"]
            for item in rights_sources
        ) or not any(
            item.get("sourceRef") == consent["evidenceRef"]
            and item.get("sourceDigest") == consent["evidenceDigest"]
            for item in rights_sources
        ):
            raise VoiceProfileLineageNotEffectiveError(
                "current VoiceProfile rights evidence is incomplete"
            )
        return {
            "voiceProfile": root,
            "voiceProfileVersion": profile,
            "sourceRecordingBinding": source,
            "consentGrantVersion": consent,
            "confirmedVoiceLock": lock,
            "rightsBinding": rights,
        }

    def _assert_current_voice_profile_authority(
        self, value: Mapping[str, Any]
    ) -> None:
        proof = _verify_sealed(
            value,
            _CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_FIELDS,
            "CurrentConfirmedVoiceProfileAuthority",
        )
        if (
            proof["schemaVersion"]
            != CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_SCHEMA_VERSION
            or proof["publicationAllowed"] is not False
        ):
            raise VoiceProfileLineageError(
                "current VoiceProfile authority semantics are invalid"
            )
        workspace = _required_ref(proof["workspaceRef"], "workspaceRef")
        run_ref = _required_ref(proof["productionRunRef"], "productionRunRef")
        current_head = self.evidence.workspace_record_journal_head(workspace)
        if current_head != proof["journalHead"]:
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority journal head is stale"
            )
        run = self.root_service.get_run(workspace, run_ref)
        scope = (
            workspace,
            _required_ref(run.get("projectRef"), "projectRef"),
            _required_ref(run.get("seriesRef"), "seriesRef"),
        )
        if tuple(proof[field] for field in _SCOPE_FIELDS) != scope:
            raise VoiceProfileLineageNotFoundError("VoiceProfile was not found")
        observed_head, snapshot = self._snapshot(workspace, run_ref)
        if observed_head != current_head:
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority changed while being verified"
            )
        profile = proof["voiceProfileVersion"]
        if not isinstance(profile, Mapping):
            raise VoiceProfileLineageError(
                "current VoiceProfileVersion proof is invalid"
            )
        components = self._current_confirmed_profile_components(
            snapshot,
            scope=scope,
            voice_profile_version_ref=profile.get("voiceProfileVersionRef"),
            voice_profile_version_digest=profile.get("payloadDigest"),
            evaluated_at=_text(self._clock(), "evaluatedAt"),
        )
        if any(proof[field] != item for field, item in components.items()):
            raise VoiceProfileLineageStaleError(
                "current VoiceProfile authority projection is stale"
            )

    def resolve_current_confirmed_voice_profile(
        self,
        workspace_ref: str,
        production_run_ref: str,
        voice_profile_version_ref: str,
        voice_profile_version_digest: str,
        *,
        evaluated_at: str | None = None,
    ) -> CurrentConfirmedVoiceProfileAuthority:
        """Issue a non-serializable, head-bound proof for clone proposals."""

        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        _required_ref(voice_profile_version_ref, "voiceProfileVersionRef")
        _sha256(voice_profile_version_digest, "voiceProfileVersionDigest")
        issued_at = _text(self._clock(), "evaluatedAt")
        _utc_instant(issued_at, "evaluatedAt")
        if evaluated_at is not None:
            _utc_instant(evaluated_at, "evaluatedAt")
            if evaluated_at != issued_at:
                raise VoiceProfileLineageStaleError(
                    "caller evaluation time is not the service clock"
                )
        run = self.root_service.get_run(workspace, run_ref)
        scope = (
            workspace,
            _required_ref(run.get("projectRef"), "projectRef"),
            _required_ref(run.get("seriesRef"), "seriesRef"),
        )
        head, snapshot = self._snapshot(workspace, run_ref)
        components = self._current_confirmed_profile_components(
            snapshot,
            scope=scope,
            voice_profile_version_ref=voice_profile_version_ref,
            voice_profile_version_digest=voice_profile_version_digest,
            evaluated_at=issued_at,
        )
        proof = _seal(
            {
                "schemaVersion": (
                    CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_SCHEMA_VERSION
                ),
                "workspaceRef": scope[0],
                "projectRef": scope[1],
                "seriesRef": scope[2],
                "productionRunRef": run_ref,
                "journalHead": head,
                **components,
                "evaluatedAt": issued_at,
                "publicationAllowed": False,
            }
        )
        return CurrentConfirmedVoiceProfileAuthority._from_service(
            proof,
            _token=_CURRENT_AUTHORITY_FACTORY_TOKEN,
            _revalidate=self._assert_current_voice_profile_authority,
        )

    def get_source_recording_binding(
        self, workspace_ref: str, production_run_ref: str, binding_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        scope = self._scope_for_run(workspace, run_ref)
        _, snapshot = self._snapshot(workspace, run_ref)
        record, payload = _canonical_record(
            snapshot,
            kind=SOURCE_RECORDING_BINDING_RECORD_KIND,
            ref=_required_ref(binding_ref, "sourceRecordingBindingRef"),
        )
        result = self._source_binding(
            snapshot,
            ref=payload["sourceRecordingBindingRef"],
            digest=_sha256(
                record.get("payloadDigest"),
                "sourceRecordingBindingDigest",
            ),
        )
        _require_series_scope(
            result, scope, "SourceVoiceRecordingAssetVersionBinding"
        )
        return result

    def get_consent_grant_version(
        self, workspace_ref: str, production_run_ref: str, version_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        scope = self._scope_for_run(workspace, run_ref)
        _, snapshot = self._snapshot(workspace, run_ref)
        _, payload = _canonical_record(
            snapshot,
            kind=CONSENT_GRANT_VERSION_RECORD_KIND,
            ref=_required_ref(version_ref, "consentGrantVersionRef"),
        )
        result = validate_consent_grant_version_v2(payload).as_dict()
        _require_series_scope(result, scope, "ConsentGrantVersion")
        _, root_payload = _canonical_record(
            snapshot,
            kind=CONSENT_GRANT_RECORD_KIND,
            ref=result["consentGrantRef"],
        )
        root = validate_consent_grant_root(root_payload).as_dict()
        if (
            tuple(root[field] for field in _SCOPE_FIELDS) != scope
            or root["subjectRef"] != result["subjectRef"]
        ):
            raise RepositoryUnavailableError(
                "ConsentGrant root/version lineage is invalid"
            )
        self._consent_versions(snapshot, result["consentGrantRef"])
        return result

    def get_voice_profile_version(
        self, workspace_ref: str, production_run_ref: str, version_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        scope = self._scope_for_run(workspace, run_ref)
        _, snapshot = self._snapshot(workspace, run_ref)
        _, payload = _canonical_record(
            snapshot,
            kind=VOICE_PROFILE_VERSION_RECORD_KIND,
            ref=_required_ref(version_ref, "voiceProfileVersionRef"),
        )
        result = validate_voice_profile_version(payload).as_dict()
        _require_series_scope(result, scope, "VoiceProfileVersion")
        _, root_payload = _canonical_record(
            snapshot,
            kind=VOICE_PROFILE_RECORD_KIND,
            ref=result["voiceProfileRef"],
        )
        root = validate_voice_profile(root_payload).as_dict()
        if (
            tuple(root[field] for field in _SCOPE_FIELDS) != scope
            or root["subjectRef"] != result["subjectRef"]
        ):
            raise RepositoryUnavailableError(
                "VoiceProfile root/version lineage is invalid"
            )
        self._profile_versions(snapshot, result["voiceProfileRef"])
        return result

    def get_confirmed_clone_voice_lock(
        self, workspace_ref: str, production_run_ref: str, voice_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        scope = self._scope_for_run(workspace, run_ref)
        return self._authoritative_confirmed_clone_lock(
            scope,
            voice_ref=_required_ref(voice_ref, "voiceRef"),
        )

    def get_voice_profile_lineage(
        self, workspace_ref: str, production_run_ref: str
    ) -> dict[str, Any]:
        workspace = _required_ref(workspace_ref, "workspaceRef")
        run_ref = _required_ref(production_run_ref, "productionRunRef")
        scope = self._scope_for_run(workspace, run_ref)
        _, snapshot = self._snapshot(workspace, run_ref)

        scoped_kinds = {
            SOURCE_RECORDING_BINDING_RECORD_KIND,
            CONSENT_GRANT_RECORD_KIND,
            CONSENT_GRANT_VERSION_RECORD_KIND,
            VOICE_PROFILE_RECORD_KIND,
            VOICE_PROFILE_VERSION_RECORD_KIND,
        }

        def payloads(kind: str) -> list[dict[str, Any]]:
            values = [
                _payload(record, kind)
                for record in snapshot.records
                if record.get("recordKind") == kind
            ]
            if kind in scoped_kinds:
                values = [
                    item
                    for item in values
                    if tuple(item.get(field) for field in _SCOPE_FIELDS) == scope
                ]
            return values

        clone_version_payloads = self._authoritative_clone_lock_versions(scope)
        clone_lock_payloads: list[dict[str, Any]] = []
        clone_confirmation_payloads: list[dict[str, Any]] = []
        for voice_ref in sorted(
            {item["voiceRef"] for item in clone_version_payloads}
        ):
            try:
                state = self.voice_locks.get_voice_lock(*scope, voice_ref)
            except EpisodeProductionError:
                raise
            except Exception as exc:
                raise RepositoryUnavailableError(
                    "VoiceLock authority is unavailable"
                ) from exc
            root = validate_clone_voice_lock(state.get("voiceLock"))
            authoritative_versions = [
                validate_clone_voice_lock_version_v2(item)
                for item in state.get("voiceLockVersions", [])
                if isinstance(item, Mapping)
                and item.get("schemaVersion")
                == VOICE_LOCK_VERSION_V2_SCHEMA_VERSION
            ]
            expected_versions = [
                item
                for item in clone_version_payloads
                if item["voiceRef"] == voice_ref
            ]
            if authoritative_versions != expected_versions:
                raise RepositoryUnavailableError(
                    "VoiceLock authority projections disagree"
                )
            clone_lock_payloads.append(root)
            confirmed = state.get("confirmed")
            if isinstance(confirmed, Mapping):
                confirmed_version = confirmed.get("voiceLockVersion")
                confirmation = confirmed.get("voiceLockConfirmation")
                if (
                    isinstance(confirmed_version, Mapping)
                    and confirmed_version.get("schemaVersion")
                    == VOICE_LOCK_VERSION_V2_SCHEMA_VERSION
                ):
                    validated_confirmation = validate_voice_lock_confirmation(
                        confirmation
                    )
                    if (
                        validated_confirmation["voiceLockVersionRef"]
                        != confirmed_version.get("voiceLockVersionRef")
                    ):
                        raise RepositoryUnavailableError(
                            "VoiceLock confirmation projection is stale"
                        )
                    clone_confirmation_payloads.append(
                        validated_confirmation
                    )
        for root_payload in payloads(CONSENT_GRANT_RECORD_KIND):
            root = validate_consent_grant_root(root_payload).as_dict()
            self._consent_versions(snapshot, root["consentGrantRef"])
        for root_payload in payloads(VOICE_PROFILE_RECORD_KIND):
            root = validate_voice_profile(root_payload).as_dict()
            self._profile_versions(snapshot, root["voiceProfileRef"])

        graph = _seal(
            {
                "schemaVersion": VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION,
                "workspaceRef": workspace,
                "productionRunRef": run_ref,
                "sourceVoiceRecordingAssetVersionBindings": sorted(
                    (
                        validate_source_voice_recording_binding(item).as_dict()
                        for item in payloads(SOURCE_RECORDING_BINDING_RECORD_KIND)
                    ),
                    key=lambda item: item["sourceRecordingBindingRef"],
                ),
                "consentGrants": sorted(
                    (
                        validate_consent_grant_root(item).as_dict()
                        for item in payloads(CONSENT_GRANT_RECORD_KIND)
                    ),
                    key=lambda item: item["consentGrantRef"],
                ),
                "consentGrantVersions": sorted(
                    (
                        validate_consent_grant_version_v2(item).as_dict()
                        for item in payloads(CONSENT_GRANT_VERSION_RECORD_KIND)
                    ),
                    key=lambda item: (
                        item["consentGrantRef"], item["versionNumber"]
                    ),
                ),
                "voiceLocks": sorted(
                    (
                        validate_clone_voice_lock(item)
                        for item in clone_lock_payloads
                    ),
                    key=lambda item: item["voiceRef"],
                ),
                "voiceLockVersions": sorted(
                    (
                        validate_clone_voice_lock_version_v2(item)
                        for item in clone_version_payloads
                    ),
                    key=lambda item: (item["voiceRef"], item["versionNumber"]),
                ),
                "voiceLockConfirmations": sorted(
                    (
                        validate_voice_lock_confirmation(item)
                        for item in clone_confirmation_payloads
                    ),
                    key=lambda item: item["voiceLockConfirmationRef"],
                ),
                "voiceProfiles": sorted(
                    (
                        validate_voice_profile(item).as_dict()
                        for item in payloads(VOICE_PROFILE_RECORD_KIND)
                    ),
                    key=lambda item: item["voiceProfileRef"],
                ),
                "voiceProfileVersions": sorted(
                    (
                        validate_voice_profile_version(item).as_dict()
                        for item in payloads(VOICE_PROFILE_VERSION_RECORD_KIND)
                    ),
                    key=lambda item: (
                        item["voiceProfileRef"], item["versionNumber"]
                    ),
                ),
                "publicationAllowed": False,
            }
        )
        return validate_voice_profile_lineage_graph(graph)


_LINEAGE_GRAPH_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "sourceVoiceRecordingAssetVersionBindings",
        "consentGrants",
        "consentGrantVersions",
        "voiceLocks",
        "voiceLockVersions",
        "voiceLockConfirmations",
        "voiceProfiles",
        "voiceProfileVersions",
        "publicationAllowed",
        "payloadDigest",
    }
)


def validate_voice_profile_lineage_graph(value: Any) -> dict[str, Any]:
    """Verify every authoritative internal edge and reject any directed cycle."""

    graph = _verify_sealed(value, _LINEAGE_GRAPH_FIELDS, "VoiceProfile lineage graph")
    if (
        graph["schemaVersion"] != VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION
        or graph["publicationAllowed"] is not False
    ):
        raise VoiceProfileLineageError("VoiceProfile lineage graph semantics are invalid")
    workspace = _required_ref(graph["workspaceRef"], "workspaceRef")
    _required_ref(graph["productionRunRef"], "productionRunRef")

    list_fields = (
        "sourceVoiceRecordingAssetVersionBindings",
        "consentGrants",
        "consentGrantVersions",
        "voiceLocks",
        "voiceLockVersions",
        "voiceLockConfirmations",
        "voiceProfiles",
        "voiceProfileVersions",
    )
    if any(not isinstance(graph[field], list) for field in list_fields):
        raise VoiceProfileLineageError("VoiceProfile lineage collections are invalid")
    sources = [
        validate_source_voice_recording_binding(item).as_dict()
        for item in graph["sourceVoiceRecordingAssetVersionBindings"]
    ]
    consent_roots = [
        validate_consent_grant_root(item).as_dict()
        for item in graph["consentGrants"]
    ]
    consents = [
        validate_consent_grant_version_v2(item).as_dict()
        for item in graph["consentGrantVersions"]
    ]
    locks = [validate_clone_voice_lock(item) for item in graph["voiceLocks"]]
    lock_versions = [
        validate_clone_voice_lock_version_v2(item)
        for item in graph["voiceLockVersions"]
    ]
    confirmations = [
        validate_voice_lock_confirmation(item)
        for item in graph["voiceLockConfirmations"]
    ]
    profiles = [
        validate_voice_profile(item).as_dict() for item in graph["voiceProfiles"]
    ]
    profile_versions = [
        validate_voice_profile_version(item).as_dict()
        for item in graph["voiceProfileVersions"]
    ]
    scoped = (
        sources
        + consent_roots
        + consents
        + locks
        + lock_versions
        + confirmations
        + profiles
        + profile_versions
    )
    scopes = {
        tuple(item[field] for field in _SCOPE_FIELDS)
        for item in scoped
    }
    if (
        any(item["workspaceRef"] != workspace for item in scoped)
        or len(scopes) > 1
    ):
        raise VoiceProfileLineageError(
            "VoiceProfile lineage workspace/project/series scope is inconsistent"
        )

    def unique_index(
        items: Sequence[Mapping[str, Any]], ref_field: str, label: str
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            ref = item[ref_field]
            if ref in result:
                raise VoiceProfileLineageError(f"{label} identity is duplicated")
            result[ref] = deepcopy(dict(item))
        return result

    source_by_ref = unique_index(
        sources, "sourceRecordingBindingRef", "SourceVoiceRecordingAssetVersionBinding"
    )
    consent_root_by_ref = unique_index(consent_roots, "consentGrantRef", "ConsentGrant")
    consent_by_ref = unique_index(
        consents, "consentGrantVersionRef", "ConsentGrantVersion"
    )
    lock_by_ref = unique_index(locks, "voiceRef", "VoiceLock")
    lock_version_by_ref = unique_index(
        lock_versions, "voiceLockVersionRef", "VoiceLockVersion"
    )
    confirmation_by_ref = unique_index(
        confirmations, "voiceLockConfirmationRef", "VoiceLockConfirmation"
    )
    profile_by_ref = unique_index(profiles, "voiceProfileRef", "VoiceProfile")
    profile_version_by_ref = unique_index(
        profile_versions, "voiceProfileVersionRef", "VoiceProfileVersion"
    )

    def require_one_linear_chain(
        *,
        roots: Sequence[Mapping[str, Any]],
        versions: Sequence[Mapping[str, Any]],
        root_ref_field: str,
        version_ref_field: str,
        version_number_field: str,
        parent_ref_field: str,
        parent_digest_field: str,
        first_number: int,
        label: str,
    ) -> None:
        for root in roots:
            root_ref = root[root_ref_field]
            selected = sorted(
                (
                    item
                    for item in versions
                    if item[root_ref_field] == root_ref
                ),
                key=lambda item: item[version_number_field],
            )
            if not selected or [
                item[version_number_field] for item in selected
            ] != list(range(first_number, first_number + len(selected))):
                raise VoiceProfileLineageStaleError(
                    f"{label} version sequence is not one contiguous chain"
                )
            for previous, item in zip(selected, selected[1:]):
                if (
                    item[parent_ref_field] != previous[version_ref_field]
                    or item[parent_digest_field] != previous["payloadDigest"]
                ):
                    raise VoiceProfileLineageStaleError(
                        f"{label} version sequence forks or skips its predecessor"
                    )

    require_one_linear_chain(
        roots=consent_roots,
        versions=consents,
        root_ref_field="consentGrantRef",
        version_ref_field="consentGrantVersionRef",
        version_number_field="versionNumber",
        parent_ref_field="parentConsentGrantVersionRef",
        parent_digest_field="parentConsentGrantVersionDigest",
        first_number=1,
        label="ConsentGrant",
    )
    require_one_linear_chain(
        roots=locks,
        versions=lock_versions,
        root_ref_field="voiceRef",
        version_ref_field="voiceLockVersionRef",
        version_number_field="versionNumber",
        parent_ref_field="parentVoiceLockVersionRef",
        parent_digest_field="parentVoiceLockDigest",
        first_number=2,
        label="clone VoiceLock",
    )
    require_one_linear_chain(
        roots=profiles,
        versions=profile_versions,
        root_ref_field="voiceProfileRef",
        version_ref_field="voiceProfileVersionRef",
        version_number_field="versionNumber",
        parent_ref_field="parentVoiceProfileVersionRef",
        parent_digest_field="parentVoiceProfileVersionDigest",
        first_number=1,
        label="VoiceProfile",
    )

    for root in locks:
        selected = [
            item for item in lock_versions if item["voiceRef"] == root["voiceRef"]
        ]
        head = max(selected, key=lambda item: item["versionNumber"])
        if root["currentVoiceLockVersionRef"] != head["voiceLockVersionRef"]:
            raise VoiceProfileLineageStaleError(
                "VoiceLock root current pointer is not the unique clone head"
            )
        confirmed_ref = root["confirmedVoiceLockVersionRef"]
        if confirmed_ref in {
            item["voiceLockVersionRef"] for item in selected
        }:
            matching_confirmations = [
                item
                for item in confirmations
                if item["voiceRef"] == root["voiceRef"]
                and item["voiceLockVersionRef"] == confirmed_ref
                and item["voiceLockDigest"]
                == root["confirmedVoiceLockDigest"]
            ]
            if len(matching_confirmations) != 1:
                raise VoiceProfileLineageStaleError(
                    "VoiceLock confirmed clone head lacks one exact confirmation"
                )
    if any(
        not any(
            item["consentGrantRef"] == root_ref for item in consents
        )
        for root_ref in consent_root_by_ref
    ):
        raise VoiceProfileLineageStaleError(
            "ConsentGrant root has no version"
        )
    if any(
        not any(item["voiceRef"] == root_ref for item in lock_versions)
        for root_ref in lock_by_ref
    ):
        raise VoiceProfileLineageStaleError("VoiceLock root has no version")
    if any(
        not any(
            item["voiceProfileRef"] == root_ref for item in profile_versions
        )
        for root_ref in profile_by_ref
    ):
        raise VoiceProfileLineageStaleError(
            "VoiceProfile root has no version"
        )

    nodes: set[str] = set()
    edges: dict[str, set[str]] = {}

    def add_node(kind: str, ref: str) -> str:
        node = f"{kind}:{ref}"
        nodes.add(node)
        edges.setdefault(node, set())
        return node

    def bind(
        owner: str,
        target_kind: str,
        target_ref: str,
        target_digest: str,
        index: Mapping[str, Mapping[str, Any]],
    ) -> None:
        target = index.get(target_ref)
        if target is None or target.get("payloadDigest") != target_digest:
            raise VoiceProfileLineageStaleError(
                f"{target_kind} lineage binding is stale"
            )
        edges[owner].add(add_node(target_kind, target_ref))

    for item in sources:
        add_node("source", item["sourceRecordingBindingRef"])
    for root in consent_roots:
        add_node("consent-root", root["consentGrantRef"])
    for item in consents:
        owner = add_node("consent", item["consentGrantVersionRef"])
        root = consent_root_by_ref.get(item["consentGrantRef"])
        if root is None or root["subjectRef"] != item["subjectRef"]:
            raise VoiceProfileLineageStaleError("ConsentGrant root binding is stale")
        edges[owner].add(add_node("consent-root", root["consentGrantRef"]))
        bind(
            owner,
            "source",
            item["sourceRecordingBindingRef"],
            item["sourceRecordingBindingDigest"],
            source_by_ref,
        )
        source = source_by_ref[item["sourceRecordingBindingRef"]]
        if source["subjectRef"] != item["subjectRef"]:
            raise VoiceProfileLineageStaleError(
                "ConsentGrant source subject binding is stale"
            )
        parent_ref = item["parentConsentGrantVersionRef"]
        if parent_ref is None:
            if (
                item["versionNumber"] != 1
                or item["revocationState"] != "ACTIVE"
                or source["sourceRightsBindingRef"] != item["rightsBindingRef"]
                or source["sourceRightsBindingDigest"]
                != item["rightsBindingDigest"]
            ):
                raise VoiceProfileLineageStaleError(
                    "initial ConsentGrantVersion lifecycle is stale"
                )
        else:
            bind(
                owner,
                "consent",
                parent_ref,
                item["parentConsentGrantVersionDigest"],
                consent_by_ref,
            )
            parent = consent_by_ref[parent_ref]
            if (
                parent["consentGrantRef"] != item["consentGrantRef"]
                or parent["versionNumber"] + 1 != item["versionNumber"]
                or parent["sourceRecordingBindingRef"]
                != item["sourceRecordingBindingRef"]
                or parent["sourceRecordingBindingDigest"]
                != item["sourceRecordingBindingDigest"]
                or parent["subjectRef"] != item["subjectRef"]
                or parent["grantorRef"] != item["grantorRef"]
                or parent["rightsBindingRef"] == item["rightsBindingRef"]
                or parent["rightsBindingDigest"] == item["rightsBindingDigest"]
                or (parent["revocationState"], item["revocationState"])
                not in {("ACTIVE", "ACTIVE"), ("ACTIVE", "REVOKED")}
            ):
                raise VoiceProfileLineageStaleError(
                    "ConsentGrantVersion predecessor order is stale"
                )

    for root in locks:
        add_node("lock-root", root["voiceRef"])
    for item in lock_versions:
        owner = add_node("lock-version", item["voiceLockVersionRef"])
        root = lock_by_ref.get(item["voiceRef"])
        if (
            root is None
            or root["characterRef"] != item["characterRef"]
            or item["voiceIdentityRef"] != root["voiceRef"]
            or root["currentVoiceLockVersionRef"]
            not in {
                selected["voiceLockVersionRef"]
                for selected in lock_versions
                if selected["voiceRef"] == root["voiceRef"]
            }
        ):
            raise VoiceProfileLineageStaleError("VoiceLock root binding is stale")
        edges[owner].add(add_node("lock-root", root["voiceRef"]))
        bind(
            owner,
            "source",
            item["sourceRecordingBindingRef"],
            item["sourceRecordingBindingDigest"],
            source_by_ref,
        )
        bind(
            owner,
            "consent",
            item["consentGrantVersionRef"],
            item["consentGrantVersionDigest"],
            consent_by_ref,
        )
        source = source_by_ref[item["sourceRecordingBindingRef"]]
        consent = consent_by_ref[item["consentGrantVersionRef"]]
        if (
            source["subjectRef"] != item["subjectRef"]
            or consent["subjectRef"] != item["subjectRef"]
            or consent["sourceRecordingBindingRef"]
            != item["sourceRecordingBindingRef"]
            or consent["sourceRecordingBindingDigest"]
            != item["sourceRecordingBindingDigest"]
            or consent["rightsBindingRef"] != item["rightsBindingRef"]
            or consent["rightsBindingDigest"] != item["rightsBindingDigest"]
        ):
            raise VoiceProfileLineageStaleError("VoiceLock authority chain is stale")
        parent_ref = item["parentVoiceLockVersionRef"]
        if parent_ref is not None:
            parent = lock_version_by_ref.get(parent_ref)
            if parent is None:
                if (
                    item["versionNumber"] != 2
                    or item["voiceIdentityVersionRef"] != parent_ref
                    or item["voiceIdentityDigest"]
                    != item["parentVoiceLockDigest"]
                ):
                    raise VoiceProfileLineageStaleError(
                        "VoiceLockVersion fixed-v1 predecessor is stale"
                    )
                edges[owner].add(
                    add_node("fixed-voice-version", parent_ref)
                )
            else:
                bind(
                    owner,
                    "lock-version",
                    parent_ref,
                    item["parentVoiceLockDigest"],
                    lock_version_by_ref,
                )
                if (
                    parent["voiceRef"] != item["voiceRef"]
                    or parent["versionNumber"] + 1 != item["versionNumber"]
                    or item["voiceIdentityVersionRef"]
                    != parent["voiceIdentityVersionRef"]
                    or item["voiceIdentityDigest"]
                    != parent["voiceIdentityDigest"]
                ):
                    raise VoiceProfileLineageStaleError(
                        "VoiceLockVersion predecessor order is stale"
                    )

    confirmed_versions: set[str] = set()
    for item in confirmations:
        owner = add_node("confirmation", item["voiceLockConfirmationRef"])
        bind(
            owner,
            "lock-version",
            item["voiceLockVersionRef"],
            item["voiceLockDigest"],
            lock_version_by_ref,
        )
        version = lock_version_by_ref[item["voiceLockVersionRef"]]
        if item["voiceLockVersionRef"] in confirmed_versions:
            raise VoiceProfileLineageError(
                "VoiceLockVersion has multiple confirmations"
            )
        confirmed_versions.add(item["voiceLockVersionRef"])
        root = lock_by_ref.get(version["voiceRef"])
        if (
            root is None
            or version["voiceRef"] != item["voiceRef"]
            or version["characterRef"] != item["characterRef"]
            or root["confirmedVoiceLockVersionRef"]
            != item["voiceLockVersionRef"]
            or root["confirmedVoiceLockDigest"] != item["voiceLockDigest"]
        ):
            raise VoiceProfileLineageStaleError(
                "VoiceLockConfirmation binding is stale"
            )

    for root in profiles:
        add_node("profile-root", root["voiceProfileRef"])
    for item in profile_versions:
        owner = add_node("profile-version", item["voiceProfileVersionRef"])
        root = profile_by_ref.get(item["voiceProfileRef"])
        if root is None or root["subjectRef"] != item["subjectRef"]:
            raise VoiceProfileLineageStaleError("VoiceProfile root binding is stale")
        edges[owner].add(add_node("profile-root", root["voiceProfileRef"]))
        bind(
            owner,
            "source",
            item["sourceRecordingBindingRef"],
            item["sourceRecordingBindingDigest"],
            source_by_ref,
        )
        bind(
            owner,
            "consent",
            item["consentGrantVersionRef"],
            item["consentGrantVersionDigest"],
            consent_by_ref,
        )
        bind(
            owner,
            "lock-version",
            item["voiceLockVersionRef"],
            item["voiceLockVersionDigest"],
            lock_version_by_ref,
        )
        bind(
            owner,
            "confirmation",
            item["voiceLockConfirmationRef"],
            item["voiceLockConfirmationDigest"],
            confirmation_by_ref,
        )
        source = source_by_ref[item["sourceRecordingBindingRef"]]
        consent = consent_by_ref[item["consentGrantVersionRef"]]
        lock = lock_version_by_ref[item["voiceLockVersionRef"]]
        confirmation = confirmation_by_ref[item["voiceLockConfirmationRef"]]
        if (
            source["subjectRef"] != item["subjectRef"]
            or consent["subjectRef"] != item["subjectRef"]
            or lock["subjectRef"] != item["subjectRef"]
            or lock["sourceRecordingBindingRef"]
            != item["sourceRecordingBindingRef"]
            or lock["sourceRecordingBindingDigest"]
            != item["sourceRecordingBindingDigest"]
            or lock["consentGrantVersionRef"]
            != item["consentGrantVersionRef"]
            or lock["consentGrantVersionDigest"]
            != item["consentGrantVersionDigest"]
            or lock["voiceRef"] != item["voiceLockRef"]
            or lock["voiceIdentityRef"] != item["voiceIdentityRef"]
            or lock["voiceIdentityVersionRef"] != item["voiceIdentityVersionRef"]
            or lock["voiceIdentityDigest"] != item["voiceIdentityDigest"]
            or lock["rightsBindingRef"] != item["rightsBindingRef"]
            or lock["rightsBindingDigest"] != item["rightsBindingDigest"]
            or consent["rightsBindingRef"] != item["rightsBindingRef"]
            or consent["rightsBindingDigest"] != item["rightsBindingDigest"]
            or lock["engineFamily"] != item["engineId"]
            or confirmation["voiceRef"] != item["voiceLockRef"]
            or confirmation["voiceLockVersionRef"]
            != item["voiceLockVersionRef"]
            or confirmation["voiceLockDigest"]
            != item["voiceLockVersionDigest"]
        ):
            raise VoiceProfileLineageStaleError("VoiceProfile authority chain is stale")
        parent_ref = item["parentVoiceProfileVersionRef"]
        if parent_ref is None:
            if item["versionNumber"] != 1 or item["status"] != "CANDIDATE":
                raise VoiceProfileLineageStaleError(
                    "initial VoiceProfileVersion lifecycle is stale"
                )
        else:
            bind(
                owner,
                "profile-version",
                parent_ref,
                item["parentVoiceProfileVersionDigest"],
                profile_version_by_ref,
            )
            parent = profile_version_by_ref[parent_ref]
            immutable_profile_fields = _VOICE_PROFILE_VERSION_FIELDS - {
                "voiceProfileVersionRef",
                "versionNumber",
                "parentVoiceProfileVersionRef",
                "parentVoiceProfileVersionDigest",
                "status",
                "createdAt",
                "createdBy",
                "confirmedAt",
                "payloadDigest",
            }
            if (
                parent["voiceProfileRef"] != item["voiceProfileRef"]
                or parent["versionNumber"] + 1 != item["versionNumber"]
                or any(
                    parent[field] != item[field]
                    for field in immutable_profile_fields
                )
                or (parent["status"], item["status"])
                not in {
                    ("CANDIDATE", "CONFIRMED"),
                    ("CONFIRMED", "REVOKED"),
                }
            ):
                raise VoiceProfileLineageStaleError(
                    "VoiceProfileVersion predecessor order is stale"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise VoiceProfileLineageError("VoiceProfile lineage graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in edges.get(node, set()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node)
    return graph


__all__ = [
    "CURRENT_CONFIRMED_VOICE_PROFILE_AUTHORITY_SCHEMA_VERSION",
    "CurrentConfirmedVoiceProfileAuthority",
    "CONSENT_ALLOWED_USES",
    "CONSENT_GRANT_ROOT_SCHEMA_VERSION",
    "CONSENT_GRANT_VERSION_V2_SCHEMA_VERSION",
    "CONSENT_REVOCATION_STATES",
    "K2VoiceProfileLineageService",
    "REQUIRED_CLONE_CONSENT_USES",
    "SOURCE_RECORDING_BINDING_RECORD_KIND",
    "SOURCE_RECORDING_CLASSIFICATION_SCHEMA_VERSION",
    "SOURCE_RECORDING_IMPORT_EVIDENCE_SCHEMA_VERSION",
    "SOURCE_RECORDING_PROVENANCE_SCHEMA_VERSION",
    "SOURCE_RECORDING_REQUIREMENT_SCHEMA_VERSION",
    "SOURCE_TRANSCRIPT_VERSION_SCHEMA_VERSION",
    "SOURCE_VOICE_RECORDING_ASSET_VERSION_SCHEMA_VERSION",
    "SOURCE_VOICE_RECORDING_ASSET_VERSION_BINDING_SCHEMA_VERSION",
    "SOURCE_VOICE_RECORDING_BINDING_SCHEMA_VERSION",
    "SourceVoiceRecordingAssetVersion",
    "SourceVoiceRecordingAssetVersionBinding",
    "ConsentGrantRoot",
    "ConsentGrantVersionV2",
    "VoiceProfile",
    "VoiceProfileVersion",
    "VOICE_PROFILE_LINEAGE_GRAPH_SCHEMA_VERSION",
    "VOICE_PROFILE_SCHEMA_VERSION",
    "VOICE_PROFILE_STATUSES",
    "VOICE_PROFILE_TECHNICAL_VALIDATION_SCHEMA_VERSION",
    "VOICE_PROFILE_TEST_FIXTURE_MARKERS",
    "VOICE_PROFILE_TEST_FIXTURE_SCHEMA_VERSION",
    "VOICE_PROFILE_VERSION_SCHEMA_VERSION",
    "VOICE_PROFILE_PACKAGE_FORMAT",
    "VOICE_PROFILE_PACKAGE_SCHEMA_VERSION",
    "VOICE_CLONE_ENGINE_ID",
    "VOICE_CLONE_ENGINE_COMMIT",
    "VOICE_CLONE_MODEL_ID",
    "VOICE_CLONE_MODEL_BUNDLE_SHA256",
    "VoiceProfileFixtureRejectedError",
    "VoiceProfileLineageError",
    "VoiceProfileLineageNotEffectiveError",
    "VoiceProfileLineageNotFoundError",
    "VoiceProfileLineageStaleError",
    "build_voice_profile_test_fixture",
    "require_active_consent_grant_version",
    "validate_clone_voice_lock",
    "validate_clone_voice_lock_confirmation",
    "validate_clone_voice_lock_version",
    "validate_consent_grant_root",
    "validate_consent_grant_version_v2",
    "validate_source_voice_recording_asset_version",
    "validate_source_voice_recording_binding",
    "validate_source_voice_recording_asset_version_binding",
    "validate_source_transcript_version",
    "validate_voice_profile",
    "validate_voice_profile_lineage_graph",
    "validate_voice_profile_technical_validation",
    "validate_voice_profile_test_fixture",
    "validate_voice_profile_version",
]
