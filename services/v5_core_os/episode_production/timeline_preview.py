"""Additive M12-to-M13 timeline and preview domain contracts.

The contracts in this module are deliberately authority-neutral builders and
validators.  ``K2DeliveryService`` remains the only owner that may register a
TimelineVersion or PreviewCandidate.  This module creates no service,
repository, database, gate, admission, master, export, provider, or GPU path.

Registration-facing builders require already validated immutable M12/M13
wrappers.  Persisted mappings remain independently digest-verifiable so the
existing EpisodeProduction evidence journal can fail closed after restart.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from .audio_authority import (
    AmbienceAssetVersion,
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
    validate_ambience_asset_version,
    validate_music_asset_version,
    validate_sfx_asset_version,
)
from .audio_timing import (
    AUDIO_CUE_AUTHORITY_STATE,
    AUDIO_CUE_SCHEMA_VERSION,
    AUDIO_STEM_AUTHORITY_STATE,
    AUDIO_STEM_MEMBER_SCHEMA_VERSION,
    AUDIO_STEM_ROLES,
    AUDIO_STEM_SET_SCHEMA_VERSION,
    AUDIO_TIMELINE_BINDING_STATE,
    AudioCue,
    AudioStemMember,
    AudioStemSet,
)
from .audio_validation import (
    AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
    AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION,
    AUDIO_TECHNICAL_VALIDATION_STATE,
    AudioTechnicalValidation,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _required_ref,
)
from .glyph_reveal import (
    CANONICAL_ASSET_VERSION_SCHEMA_VERSION,
    GLYPH_MASK_ASSET_ROLE,
    GLYPH_REVEAL_BLEND_MODE,
    PIXEL_DIGEST_SPEC,
    PIXEL_MODE,
    REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION,
)
from .glyph_reveal_v2 import (
    GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION_V2,
    GlyphRevealRequirementV2,
)


AUDIO_INPUT_BINDING_SCHEMA_VERSION = (
    "v5.m12-m13-audio-input-binding.v1"
)
MASK_ASSET_VERSION_BINDING_SCHEMA_VERSION = (
    "v5.m13-mask-asset-version-binding.v1"
)
TIMELINE_SCHEMA_VERSION_V2 = "v5.timeline.v2"
TIMELINE_VERSION_SCHEMA_VERSION_V2 = "v5.timeline-version.v2"
TIMELINE_TRACK_SCHEMA_VERSION = "v5.timeline-track.v1"
TIMELINE_CLIP_SCHEMA_VERSION = "v5.timeline-clip.v1"
SUBTITLE_MANIFEST_SCHEMA_VERSION = "v5.subtitle-manifest.v1"
TIMELINE_MIX_REQUEST_SCHEMA_VERSION = "v5.timeline-mix-request.v1"
COMPOSITION_RESULT_SCHEMA_VERSION = "v5.m13-composition-result.v1"
PREVIEW_CANDIDATE_SCHEMA_VERSION_V2 = "v5.preview-candidate.v2"

TIMELINE_ROUNDING_RULE = "FLOOR_EACH_BOUNDARY"
TIMELINE_INTERVAL_SEMANTICS = "HALF_OPEN"
TIMELINE_TRACK_KINDS = ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
TIMELINE_PROVENANCE = "LOCAL_EVIDENCE"
TIMELINE_AUTHORITY_STATE = "TECHNICAL_EVIDENCE_ONLY"
TECHNICAL_FIXTURE_LABELS = frozenset(
    {
        "LOCAL_TECHNICAL_FIXTURE",
        "NOT_TTS",
        "NOT_VOICE_CLONE",
        "NOT_ADMITTED",
    }
)
GLYPH_MASK_ASSET_KIND = "glyph-reveal-mask"
DECODED_FRAME_PIXEL_DIGEST_SPEC = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)
PCM_CONTENT_DIGEST_SPEC = {
    "schemaVersion": "v4.pcm-content-digest-spec.v1",
    "algorithm": "SHA-256",
    "decoder": "FFMPEG",
    "sampleFormat": "s16le",
    "sampleRate": 48_000,
    "channelLayout": "stereo",
    "channelOrder": ["FL", "FR"],
    "interleaving": "INTERLEAVED",
    "sampleOrder": "FRAME_MAJOR_CHANNEL_ORDER",
    "endianness": "LITTLE_ENDIAN",
    "containerMetadataIncluded": False,
    "monoExpansion": "DUPLICATE_TO_FL_FR",
}
TIMELINE_MIX_PARAMETERS = {
    "rolePriority": {
        "dialogue": 3,
        "narration": 3,
        "sfx": 2,
        "ambience": 1,
        "music": 0,
    },
    "roleGainDb": {
        "dialogue": 0,
        "narration": 0,
        "sfx": -6,
        "ambience": -12,
        "music": -18,
    },
    "ducking": {
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
    },
    "limiter": {
        "limit": "0.95",
        "attackMilliseconds": 5,
        "releaseMilliseconds": 50,
        "level": False,
        "latency": True,
    },
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GLYPH_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_DECIMAL_3 = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{3}\Z")
_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_FORBIDDEN_AUDIO_PREVIEW_KEYS = frozenset(
    {
        "timelineRef",
        "timelineVersionRef",
        "timelineClipRef",
        "timelineTrackRef",
        "timelineStartFrame",
        "timelineEndFrame",
        "timelineEndFrameExclusive",
        "timelineStartSample",
        "timelineEndSample",
    }
)


class TimelinePreviewContractError(EpisodeProductionError):
    code = "timeline_preview_contract_invalid"


class TimelineSourceBindingError(StaleInputError):
    code = "timeline_source_binding_stale"


class TimelineAuthorityError(UpstreamNotReadyError):
    code = "timeline_authority_required"


class TimelineRangeError(TimelinePreviewContractError):
    code = "timeline_range_invalid"


class TimelineTrackError(TimelinePreviewContractError):
    code = "timeline_track_invalid"


class PreviewArtifactError(TimelinePreviewContractError):
    code = "preview_artifact_invalid"


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TimelinePreviewContractError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise TimelinePreviewContractError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise TimelineSourceBindingError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _verify_nested_digest(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or "payloadDigest" not in value:
        raise TimelineSourceBindingError(f"{label} is not sealed")
    result = deepcopy(dict(value))
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise TimelineSourceBindingError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise TimelinePreviewContractError(f"{field} is invalid") from exc


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TimelinePreviewContractError(f"{field} is invalid")
    return value


def _prefixed_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _PREFIXED_SHA256.fullmatch(value) is None:
        raise TimelinePreviewContractError(f"{field} is invalid")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 10**12,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise TimelinePreviewContractError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not value and not allow_empty)
        or any(ord(character) < 32 for character in value)
    ):
        raise TimelinePreviewContractError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelinePreviewContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise TimelinePreviewContractError(f"{field} must include a timezone")
    return text


def _storage_key(value: Any, field: str) -> str:
    key = _text(value, field)
    path = PurePosixPath(key)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "." in path.parts
        or "\\" in key
        or str(path) != key
    ):
        raise TimelinePreviewContractError(f"{field} is invalid")
    return key


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(_ref(value.get(field), field) for field in _SCOPE_FIELDS)  # type: ignore[return-value]


def _frame_rate(value: Any) -> tuple[dict[str, int], int, int]:
    rate = _closed(
        value, frozenset({"numerator", "denominator"}), "frameRate"
    )
    numerator = _integer(
        rate["numerator"], "frameRate.numerator", minimum=1, maximum=1_000_000
    )
    denominator = _integer(
        rate["denominator"],
        "frameRate.denominator",
        minimum=1,
        maximum=1_000_000,
    )
    # Canonical reduced rational representation prevents two wire identities
    # for the same frame rate.
    from math import gcd

    if gcd(numerator, denominator) != 1:
        raise TimelinePreviewContractError("frameRate must be reduced")
    return {"numerator": numerator, "denominator": denominator}, numerator, denominator


def map_sample_boundary_to_frame(
    source_sample: int,
    *,
    sample_rate: int,
    frame_rate_numerator: int,
    frame_rate_denominator: int,
) -> int:
    """Map one boundary independently using the frozen floor rule."""

    sample = _integer(source_sample, "sourceSample")
    rate = _integer(sample_rate, "sampleRate", minimum=1)
    numerator = _integer(
        frame_rate_numerator, "frameRateNumerator", minimum=1
    )
    denominator = _integer(
        frame_rate_denominator, "frameRateDenominator", minimum=1
    )
    return (sample * numerator) // (rate * denominator)


def _fixed_decimal(value: Any, field: str) -> str:
    if not isinstance(value, str) or _DECIMAL_3.fullmatch(value) is None:
        raise TimelinePreviewContractError(f"{field} must use fixed decimal-3")
    return value


def _contains_forbidden_audio_claim(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _FORBIDDEN_AUDIO_PREVIEW_KEYS:
                return True
            if key == "assetVersionAllowed" and item is False:
                return True
            if _contains_forbidden_audio_claim(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_audio_claim(item) for item in value)
    return value == "TEST_ONLY_NO_AUTHORITY"


@dataclass(frozen=True, slots=True, init=False)
class _ImmutableWireContract:
    _payload_json: str

    @classmethod
    def _from_validated(cls, value: Mapping[str, Any]):
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(value))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


_AUDIO_INPUT_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "audioInputBindingRef",
        "assetVersionType",
        "assetVersionRef",
        "assetVersionDigest",
        "assetVersion",
        "technicalValidationRef",
        "technicalValidationVersionRef",
        "technicalValidationDigest",
        "sourceArtifactEvidenceDigest",
        "analysisEvidenceDigest",
        "technicalAuthorityBindingDigest",
        "technicalValidation",
        "fileDigest",
        "pcmContentDigest",
        "sampleRate",
        "sampleCount",
        "channelCount",
        "rightsBindingRef",
        "rightsBindingDigest",
        "provenanceDigest",
        "sourceLabels",
        "state",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_AUDIO_INPUT_BINDING_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "audioInputBindingRef",
        "sourceLabels",
    }
)
_AUDIBLE_ASSET_WRAPPERS = (
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
    AmbienceAssetVersion,
)
_ASSET_TYPE_BY_WRAPPER = {
    DialogueAssetVersion: "DialogueAssetVersion",
    MusicAssetVersion: "MusicAssetVersion",
    SfxAssetVersion: "SfxAssetVersion",
    AmbienceAssetVersion: "AmbienceAssetVersion",
}


def _audible_asset_mapping(value: Any) -> dict[str, Any]:
    if type(value) not in _AUDIBLE_ASSET_WRAPPERS:
        raise TimelineAuthorityError(
            "an exact immutable audible AssetVersion wrapper is required"
        )
    mapping = _verify_nested_digest(value.as_dict(), "audio AssetVersion")
    expected = _ASSET_TYPE_BY_WRAPPER[type(value)]
    if mapping.get("assetVersionType") != expected:
        raise TimelineSourceBindingError("audio AssetVersion wrapper type is stale")
    validator = {
        MusicAssetVersion: validate_music_asset_version,
        SfxAssetVersion: validate_sfx_asset_version,
        AmbienceAssetVersion: validate_ambience_asset_version,
    }.get(type(value))
    if validator is not None and validator(mapping).as_dict() != mapping:
        raise TimelineSourceBindingError("audio AssetVersion revalidation changed")
    if (
        mapping.get("assetKind") != "audio"
        or mapping.get("state") != "PROPOSED"
        or mapping.get("authorityState") != "CONTRACT_ONLY_NOT_ADMITTED"
        or mapping.get("immutable") is not True
        or mapping.get("publicationAllowed") is not False
    ):
        raise TimelineAuthorityError("audio AssetVersion lifecycle is not audible input")
    artifact = mapping.get("artifact")
    if not isinstance(artifact, Mapping):
        raise TimelineSourceBindingError("audio AssetVersion artifact is invalid")
    _sha256(artifact.get("fileDigest"), "assetVersion.artifact.fileDigest")
    rights = _verify_nested_digest(mapping.get("rightsBinding"), "RightsBinding")
    provenance = _verify_nested_digest(mapping.get("provenance"), "AudioProvenance")
    _ref(rights.get("rightsBindingRef"), "rightsBindingRef")
    if _contains_forbidden_audio_claim(mapping):
        raise TimelineAuthorityError("audio source is not allowed in a non-test preview")
    return mapping


def _technical_validation_mapping(value: Any) -> dict[str, Any]:
    if type(value) is not AudioTechnicalValidation:
        raise TimelineAuthorityError(
            "an exact immutable AudioTechnicalValidation wrapper is required"
        )
    mapping = _verify_nested_digest(value.as_dict(), "AudioTechnicalValidation")
    if (
        mapping.get("schemaVersion")
        != AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION
        or mapping.get("validationState") != "PASSED"
        or mapping.get("clippingDetected") is not False
        or mapping.get("clippedSampleCount") != 0
        or mapping.get("failureReasons") != []
        or mapping.get("state") != AUDIO_TECHNICAL_VALIDATION_STATE
        or mapping.get("authorityState")
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or mapping.get("immutable") is not True
        or mapping.get("publicationAllowed") is not False
    ):
        raise TimelineAuthorityError("AudioTechnicalValidation is not PASS")
    for field in ("fileDigest", "pcmContentDigest", "sourceAssetVersionDigest"):
        _sha256(mapping.get(field), f"technicalValidation.{field}")
    _integer(mapping.get("sampleRate"), "sampleRate", minimum=8_000, maximum=384_000)
    _integer(mapping.get("sampleCount"), "sampleCount", minimum=1)
    _integer(mapping.get("channelCount"), "channelCount", minimum=1, maximum=32)
    if _contains_forbidden_audio_claim(mapping):
        raise TimelineAuthorityError(
            "technical validation contains final Timeline authority"
        )
    return mapping


def _source_labels(
    value: Any, *, technical_fixture_speech: bool = False
) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TimelinePreviewContractError("sourceLabels is invalid")
    if value != sorted(set(value)):
        raise TimelinePreviewContractError("sourceLabels must be unique and canonical")
    labels = frozenset(value)
    if labels and labels != TECHNICAL_FIXTURE_LABELS:
        raise TimelineAuthorityError("technical fixture labels are incomplete or unsupported")
    if technical_fixture_speech and labels != TECHNICAL_FIXTURE_LABELS:
        raise TimelineAuthorityError(
            "technical fixture speech requires exact honesty labels"
        )
    return list(value)


def _is_technical_fixture_speech(asset: Mapping[str, Any]) -> bool:
    # Production TTS is unavailable for this vertical slice.  Every typed
    # dialogue/narration input is therefore technical-fixture speech and must
    # carry the complete honesty labels regardless of adapter identity.
    return asset.get("assetVersionType") == "DialogueAssetVersion"


def _validate_audio_input_binding_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _AUDIO_INPUT_BINDING_FIELDS, "AudioInputBinding"
    )
    if result["schemaVersion"] != AUDIO_INPUT_BINDING_SCHEMA_VERSION:
        raise TimelinePreviewContractError("AudioInputBinding schema is unsupported")
    workspace = _ref(result["workspaceRef"], "workspaceRef")
    run_ref = _ref(result["productionRunRef"], "productionRunRef")
    _ref(result["audioInputBindingRef"], "audioInputBindingRef")
    asset = _verify_nested_digest(result["assetVersion"], "bound AssetVersion")
    validation = _verify_nested_digest(
        result["technicalValidation"], "bound AudioTechnicalValidation"
    )
    if asset.get("assetVersionType") not in set(_ASSET_TYPE_BY_WRAPPER.values()):
        raise TimelineAuthorityError("VoiceAssetVersion is not an audible input")
    if (
        asset.get("workspaceRef") != workspace
        or asset.get("productionRunRef") != run_ref
        or result["assetVersionType"] != asset.get("assetVersionType")
        or result["assetVersionRef"] != asset.get("assetVersionRef")
        or result["assetVersionDigest"] != asset.get("payloadDigest")
        or validation.get("sourceAssetVersionType") != result["assetVersionType"]
        or validation.get("sourceAssetVersionRef") != result["assetVersionRef"]
        or validation.get("sourceAssetVersionDigest") != result["assetVersionDigest"]
        or validation.get("workspaceRef") != workspace
        or validation.get("productionRunRef") != run_ref
    ):
        raise TimelineSourceBindingError("AudioInputBinding source identity is stale")
    artifact = asset.get("artifact")
    if not isinstance(artifact, Mapping):
        raise TimelineSourceBindingError("AudioInputBinding artifact is invalid")
    rights = _verify_nested_digest(asset.get("rightsBinding"), "RightsBinding")
    provenance = _verify_nested_digest(asset.get("provenance"), "AudioProvenance")
    if (
        validation.get("validationState") != "PASSED"
        or validation.get("clippingDetected") is not False
        or validation.get("clippedSampleCount") != 0
        or validation.get("failureReasons") != []
        or validation.get("state") != AUDIO_TECHNICAL_VALIDATION_STATE
        or validation.get("authorityState")
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or validation.get("immutable") is not True
        or validation.get("publicationAllowed") is not False
        or asset.get("state") != "PROPOSED"
        or asset.get("authorityState") != "CONTRACT_ONLY_NOT_ADMITTED"
        or asset.get("immutable") is not True
        or asset.get("publicationAllowed") is not False
    ):
        raise TimelineAuthorityError("AudioInputBinding source lifecycle is invalid")
    expected_pairs = {
        "technicalValidationRef": validation.get("validationRef"),
        "technicalValidationVersionRef": validation.get("validationVersionRef"),
        "technicalValidationDigest": validation.get("payloadDigest"),
        "sourceArtifactEvidenceDigest": validation.get(
            "sourceArtifactEvidenceDigest"
        ),
        "analysisEvidenceDigest": validation.get("analysisEvidenceDigest"),
        "fileDigest": validation.get("fileDigest"),
        "pcmContentDigest": validation.get("pcmContentDigest"),
        "sampleRate": validation.get("sampleRate"),
        "sampleCount": validation.get("sampleCount"),
        "channelCount": validation.get("channelCount"),
        "rightsBindingRef": rights.get("rightsBindingRef"),
        "rightsBindingDigest": rights.get("payloadDigest"),
        "provenanceDigest": provenance.get("payloadDigest"),
    }
    if any(result[field] != expected for field, expected in expected_pairs.items()):
        raise TimelineSourceBindingError("AudioInputBinding projection is stale")
    authority_binding = {
        "workspaceRef": workspace,
        "productionRunRef": run_ref,
        "assetVersionRef": result["assetVersionRef"],
        "assetVersionDigest": result["assetVersionDigest"],
        "technicalValidationVersionRef": result[
            "technicalValidationVersionRef"
        ],
        "technicalValidationDigest": result["technicalValidationDigest"],
        "sourceArtifactEvidenceDigest": result[
            "sourceArtifactEvidenceDigest"
        ],
        "analysisEvidenceDigest": result["analysisEvidenceDigest"],
        "fileDigest": result["fileDigest"],
        "pcmContentDigest": result["pcmContentDigest"],
    }
    if result["technicalAuthorityBindingDigest"] != _digest(
        authority_binding
    ):
        raise TimelineSourceBindingError(
            "AudioInputBinding technical authority chain is stale"
        )
    if artifact.get("fileDigest") != result["fileDigest"]:
        raise TimelineSourceBindingError("audio fileDigest binding is stale")
    _sha256(result["fileDigest"], "fileDigest")
    _sha256(result["pcmContentDigest"], "pcmContentDigest")
    _source_labels(
        result["sourceLabels"],
        technical_fixture_speech=_is_technical_fixture_speech(asset),
    )
    if (
        result["state"] != "BOUND"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
        or _contains_forbidden_audio_claim(asset)
        or _contains_forbidden_audio_claim(validation)
    ):
        raise TimelineAuthorityError("AudioInputBinding is outside preview authority")
    return result


def build_audio_input_binding(
    command: Mapping[str, Any],
    *,
    asset_version: Any,
    technical_validation: Any,
) -> dict[str, Any]:
    value = _closed(
        command,
        _AUDIO_INPUT_BINDING_COMMAND_FIELDS,
        "AudioInputBinding command",
    )
    workspace = _ref(value["workspaceRef"], "workspaceRef")
    run_ref = _ref(value["productionRunRef"], "productionRunRef")
    _ref(value["audioInputBindingRef"], "audioInputBindingRef")
    asset = _audible_asset_mapping(asset_version)
    validation = _technical_validation_mapping(technical_validation)
    labels = _source_labels(
        value["sourceLabels"],
        technical_fixture_speech=_is_technical_fixture_speech(asset),
    )
    if (
        asset.get("workspaceRef") != workspace
        or asset.get("productionRunRef") != run_ref
        or validation.get("workspaceRef") != workspace
        or validation.get("productionRunRef") != run_ref
        or validation.get("sourceAssetVersionType") != asset["assetVersionType"]
        or validation.get("sourceAssetVersionRef") != asset["assetVersionRef"]
        or validation.get("sourceAssetVersionDigest") != asset["payloadDigest"]
        or validation.get("fileDigest") != asset["artifact"]["fileDigest"]
    ):
        raise TimelineSourceBindingError("AudioInputBinding exact source is stale")
    rights = _verify_nested_digest(asset["rightsBinding"], "RightsBinding")
    provenance = _verify_nested_digest(asset["provenance"], "AudioProvenance")
    result = _seal(
        {
            "schemaVersion": AUDIO_INPUT_BINDING_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "audioInputBindingRef": value["audioInputBindingRef"],
            "assetVersionType": asset["assetVersionType"],
            "assetVersionRef": asset["assetVersionRef"],
            "assetVersionDigest": asset["payloadDigest"],
            "assetVersion": asset,
            "technicalValidationRef": validation["validationRef"],
            "technicalValidationVersionRef": validation["validationVersionRef"],
            "technicalValidationDigest": validation["payloadDigest"],
            "sourceArtifactEvidenceDigest": validation[
                "sourceArtifactEvidenceDigest"
            ],
            "analysisEvidenceDigest": validation["analysisEvidenceDigest"],
            "technicalAuthorityBindingDigest": _digest(
                {
                    "workspaceRef": workspace,
                    "productionRunRef": run_ref,
                    "assetVersionRef": asset["assetVersionRef"],
                    "assetVersionDigest": asset["payloadDigest"],
                    "technicalValidationVersionRef": validation[
                        "validationVersionRef"
                    ],
                    "technicalValidationDigest": validation[
                        "payloadDigest"
                    ],
                    "sourceArtifactEvidenceDigest": validation[
                        "sourceArtifactEvidenceDigest"
                    ],
                    "analysisEvidenceDigest": validation[
                        "analysisEvidenceDigest"
                    ],
                    "fileDigest": validation["fileDigest"],
                    "pcmContentDigest": validation["pcmContentDigest"],
                }
            ),
            "technicalValidation": validation,
            "fileDigest": validation["fileDigest"],
            "pcmContentDigest": validation["pcmContentDigest"],
            "sampleRate": validation["sampleRate"],
            "sampleCount": validation["sampleCount"],
            "channelCount": validation["channelCount"],
            "rightsBindingRef": rights["rightsBindingRef"],
            "rightsBindingDigest": rights["payloadDigest"],
            "provenanceDigest": provenance["payloadDigest"],
            "sourceLabels": labels,
            "state": "BOUND",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_audio_input_binding_mapping(result)


def validate_audio_input_binding(value: Any) -> "AudioInputBinding":
    return AudioInputBinding.from_mapping(value)


class AudioInputBinding(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "AudioInputBinding":
        return cls._from_validated(_validate_audio_input_binding_mapping(value))


_MASK_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "maskAssetVersionBindingRef",
        "assetVersionRef",
        "assetVersionDigest",
        "assetKind",
        "glyphSlug",
        "maskOrdinal",
        "storageKey",
        "byteSize",
        "sha256",
        "fileDigest",
        "pixelDigest",
        "pixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_MASK_BINDING_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "maskAssetVersionBindingRef",
        "glyphSlug",
        "maskOrdinal",
    }
)


def _glyph_slug(value: Any) -> str:
    if not isinstance(value, str) or _GLYPH_SLUG.fullmatch(value) is None:
        raise TimelinePreviewContractError("glyphSlug is invalid")
    return value


def _validate_mask_binding_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _MASK_BINDING_FIELDS, "MaskAssetVersionBinding")
    if result["schemaVersion"] != MASK_ASSET_VERSION_BINDING_SCHEMA_VERSION:
        raise TimelinePreviewContractError("MaskAssetVersionBinding schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "maskAssetVersionBindingRef",
        "assetVersionRef",
    ):
        _ref(result[field], field)
    _sha256(result["assetVersionDigest"], "assetVersionDigest")
    if result["assetKind"] != GLYPH_MASK_ASSET_KIND:
        raise TimelineSourceBindingError("mask assetKind is stale")
    _glyph_slug(result["glyphSlug"])
    _integer(result["maskOrdinal"], "maskOrdinal", minimum=1, maximum=10_000)
    _storage_key(result["storageKey"], "storageKey")
    _integer(result["byteSize"], "byteSize", minimum=1)
    raw_sha = _sha256(result["sha256"], "sha256")
    if result["fileDigest"] != f"sha256:{raw_sha}":
        raise TimelineSourceBindingError("mask fileDigest is stale")
    _prefixed_sha256(result["pixelDigest"], "pixelDigest")
    if (
        result["pixelDigestSpec"] != PIXEL_DIGEST_SPEC
        or result["pixelMode"] != PIXEL_MODE
    ):
        raise TimelineSourceBindingError("mask pixel identity is unsupported")
    _integer(result["width"], "width", minimum=1, maximum=131_072)
    _integer(result["height"], "height", minimum=1, maximum=131_072)
    if result["immutable"] is not True or result["publicationAllowed"] is not False:
        raise TimelineAuthorityError("mask binding is outside candidate authority")
    return result


def build_mask_asset_version_binding(
    command: Mapping[str, Any], *, asset_version: Mapping[str, Any]
) -> dict[str, Any]:
    value = _closed(
        command, _MASK_BINDING_COMMAND_FIELDS, "MaskAssetVersionBinding command"
    )
    workspace = _ref(value["workspaceRef"], "workspaceRef")
    run_ref = _ref(value["productionRunRef"], "productionRunRef")
    binding_ref = _ref(
        value["maskAssetVersionBindingRef"], "maskAssetVersionBindingRef"
    )
    slug = _glyph_slug(value["glyphSlug"])
    ordinal = _integer(value["maskOrdinal"], "maskOrdinal", minimum=1)
    asset = _verify_nested_digest(asset_version, "mask AssetVersion")
    required = {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "assetVersionRef",
        "mediaKind",
        "mediaType",
        "storageKey",
        "byteSize",
        "sha256",
        "pixelDigest",
        "pixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "glyphSlug",
        "revealOrdinal",
        "assetRole",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
    if not required.issubset(asset):
        raise TimelineSourceBindingError("mask AssetVersion is incomplete")
    if (
        asset.get("schemaVersion")
        not in {
            CANONICAL_ASSET_VERSION_SCHEMA_VERSION,
            REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION,
        }
        or asset.get("workspaceRef") != workspace
        or asset.get("productionRunRef") != run_ref
        or asset.get("mediaKind") != "image"
        or asset.get("mediaType") != "image/png"
        or asset.get("glyphSlug") != slug
        or asset.get("revealOrdinal") != ordinal
        or asset.get("assetRole") != GLYPH_MASK_ASSET_ROLE
        or asset.get("state") != "REGISTERED"
        or asset.get("publicationAllowed") is not False
    ):
        raise TimelineSourceBindingError("mask AssetVersion identity is stale")
    if "assetKind" in asset and asset["assetKind"] != GLYPH_MASK_ASSET_KIND:
        raise TimelineSourceBindingError("mask AssetVersion assetKind is stale")
    if (
        asset.get("schemaVersion") == REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION
        and asset.get("immutable") is not True
    ):
        raise TimelineAuthorityError("real-image mask AssetVersion is mutable")
    storage = _storage_key(asset["storageKey"], "mask.storageKey")
    size = _integer(asset["byteSize"], "mask.byteSize", minimum=1)
    raw_sha = _sha256(asset["sha256"], "mask.sha256")
    pixel = _prefixed_sha256(asset["pixelDigest"], "mask.pixelDigest")
    if asset["pixelDigestSpec"] != PIXEL_DIGEST_SPEC or asset["pixelMode"] != PIXEL_MODE:
        raise TimelineSourceBindingError("mask pixel contract is stale")
    result = _seal(
        {
            "schemaVersion": MASK_ASSET_VERSION_BINDING_SCHEMA_VERSION,
            "workspaceRef": workspace,
            "productionRunRef": run_ref,
            "maskAssetVersionBindingRef": binding_ref,
            "assetVersionRef": _ref(asset["assetVersionRef"], "assetVersionRef"),
            "assetVersionDigest": _sha256(asset["payloadDigest"], "assetVersionDigest"),
            "assetKind": GLYPH_MASK_ASSET_KIND,
            "glyphSlug": slug,
            "maskOrdinal": ordinal,
            "storageKey": storage,
            "byteSize": size,
            "sha256": raw_sha,
            "fileDigest": f"sha256:{raw_sha}",
            "pixelDigest": pixel,
            "pixelDigestSpec": asset["pixelDigestSpec"],
            "pixelMode": asset["pixelMode"],
            "width": _integer(asset["width"], "mask.width", minimum=1),
            "height": _integer(asset["height"], "mask.height", minimum=1),
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_mask_binding_mapping(result)


def validate_mask_asset_version_binding(value: Any) -> "MaskAssetVersionBinding":
    return MaskAssetVersionBinding.from_mapping(value)


class MaskAssetVersionBinding(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MaskAssetVersionBinding":
        return cls._from_validated(_validate_mask_binding_mapping(value))


TIMELINE_INPUT_BUNDLE_SCHEMA_VERSION = (
    "v5.m12-m13-timeline-input-bundle.v1"
)
_SOURCE_TIMING_FIELDS = frozenset(
    {
        "schemaVersion",
        "sourceAssetVersionRef",
        "sourceAssetVersionDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "storageKey",
        "fileDigest",
        "sampleRate",
        "channelCount",
        "sampleCount",
        "authorityState",
        "payloadDigest",
    }
)
_AUDIO_CUE_FIELDS = frozenset(
    {
        "schemaVersion",
        *_SCOPE_FIELDS,
        "cueRef",
        "cueVersionRef",
        "version",
        "supersedesCueVersionRef",
        "supersedesCueVersionDigest",
        "cueRole",
        "assetVersionRef",
        "assetVersionDigest",
        "assetVersionType",
        "scriptVersionRef",
        "scriptVersionDigest",
        "dialogueRef",
        "narrationRef",
        "sourceStartSample",
        "sourceEndSample",
        "sourceStartTime",
        "sourceEndTime",
        "sourceTimingEvidence",
        "wordTimings",
        "phonemeTimings",
        "subtitleTimingReference",
        "confidence",
        "timebase",
        "intervalSemantics",
        "timeAuthority",
        "provenance",
        "state",
        "authorityState",
        "timelineBindingState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_STEM_MEMBER_FIELDS = frozenset(
    {
        "schemaVersion",
        "stemMemberRef",
        "stemRole",
        "stemLaneRef",
        "overlapPolicy",
        "sourceAssetVersionRef",
        "sourceAssetVersionDigest",
        "sourceAssetVersionType",
        "sourceTimingEvidence",
        "sourceCueRef",
        "sourceCueVersionRef",
        "sourceCueDigest",
        "sourceStartSample",
        "sourceEndSample",
        "stemStartSample",
        "stemEndSample",
        "timebase",
        "rightsBindingRef",
        "rightsBindingDigest",
        "provenance",
        "state",
        "authorityState",
        "timelineBindingState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_STEM_SET_FIELDS = frozenset(
    {
        "schemaVersion",
        *_SCOPE_FIELDS,
        "stemSetRef",
        "stemSetVersionRef",
        "version",
        "supersedesStemSetVersionRef",
        "supersedesStemSetVersionDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "sampleRate",
        "preliminaryDurationSamples",
        "timebase",
        "members",
        "provenance",
        "state",
        "authorityState",
        "timelineBindingState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_TIMELINE_INPUT_BUNDLE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "timelineInputBundleRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "audioInputBindings",
        "audioCues",
        "audioStemSet",
        "audioStemMembers",
        "glyphRevealRequirements",
        "maskAssetVersionBindings",
        "state",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TIMELINE_INPUT_BUNDLE_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "timelineInputBundleRef",
        "scriptVersionRef",
        "scriptVersionDigest",
    }
)


def _mapping_from_recorded(value: Any, expected_type: type, label: str) -> dict[str, Any]:
    if type(value) is expected_type:
        return value.as_dict()
    if not isinstance(value, Mapping):
        raise TimelineAuthorityError(f"{label} wrapper or recorded mapping is required")
    return deepcopy(dict(value))


def _rational_matches(value: Any, numerator: int, denominator: int, label: str) -> None:
    result = _closed(value, frozenset({"numerator", "denominator"}), label)
    observed_numerator = _integer(result["numerator"], f"{label}.numerator")
    observed_denominator = _integer(
        result["denominator"], f"{label}.denominator", minimum=1
    )
    from math import gcd

    common = gcd(numerator, denominator)
    if (
        observed_numerator != numerator // common
        or observed_denominator != denominator // common
    ):
        raise TimelineSourceBindingError(f"{label} is stale")


def _asset_role(asset: Mapping[str, Any]) -> str:
    if asset["assetVersionType"] == "DialogueAssetVersion":
        role = asset.get("speechRole")
    else:
        role = {
            "MusicAssetVersion": "music",
            "SfxAssetVersion": "sfx",
            "AmbienceAssetVersion": "ambience",
        }.get(asset["assetVersionType"])
    if role not in AUDIO_STEM_ROLES:
        raise TimelineSourceBindingError("audio AssetVersion role is invalid")
    return str(role)


def _critical_audio_cue(
    value: Any,
    *,
    bindings_by_asset: Mapping[str, dict[str, Any]],
    expected_workspace: str,
    expected_run_ref: str,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    raw = _mapping_from_recorded(value, AudioCue, "AudioCue")
    cue = _verify_sealed(raw, _AUDIO_CUE_FIELDS, "recorded AudioCue")
    if cue["schemaVersion"] != AUDIO_CUE_SCHEMA_VERSION:
        raise TimelinePreviewContractError("AudioCue schema is unsupported")
    if (
        cue["workspaceRef"] != expected_workspace
        or cue["productionRunRef"] != expected_run_ref
        or cue["scriptVersionRef"] != expected_script_version_ref
        or cue["scriptVersionDigest"] != expected_script_version_digest
        or _contains_forbidden_audio_claim(cue)
    ):
        raise TimelineSourceBindingError("AudioCue scope or authority is stale")
    _scope(cue)
    for field in ("cueRef", "cueVersionRef", "assetVersionRef", "createdBy"):
        _ref(cue[field], field)
    _sha256(cue["assetVersionDigest"], "assetVersionDigest")
    _sha256(cue["scriptVersionDigest"], "scriptVersionDigest")
    binding = bindings_by_asset.get(cue["assetVersionRef"])
    if binding is None:
        raise TimelineAuthorityError("AudioCue has no registered audio input binding")
    asset = binding["assetVersion"]
    validation = binding["technicalValidation"]
    role = _asset_role(asset)
    if (
        cue["assetVersionDigest"] != binding["assetVersionDigest"]
        or cue["assetVersionType"] != binding["assetVersionType"]
        or cue["cueRole"] != role
    ):
        raise TimelineSourceBindingError("AudioCue AssetVersion binding is stale")
    timing = _verify_sealed(
        cue["sourceTimingEvidence"], _SOURCE_TIMING_FIELDS, "AudioCue timing evidence"
    )
    expected_timing = validation.get("sourceTimingEvidence")
    if not isinstance(expected_timing, Mapping) or timing != expected_timing:
        raise TimelineSourceBindingError("AudioCue timing evidence is stale")
    start = _integer(cue["sourceStartSample"], "sourceStartSample")
    end = _integer(cue["sourceEndSample"], "sourceEndSample", minimum=1)
    if start >= end or end > binding["sampleCount"]:
        raise TimelineRangeError("AudioCue source sample range is invalid")
    _rational_matches(cue["sourceStartTime"], start, binding["sampleRate"], "sourceStartTime")
    _rational_matches(cue["sourceEndTime"], end, binding["sampleRate"], "sourceEndTime")
    timebase = _closed(
        cue["timebase"],
        frozenset(
            {"unit", "ticksPerSecondNumerator", "ticksPerSecondDenominator"}
        ),
        "AudioCue timebase",
    )
    if (
        timebase["unit"] != "AUDIO_SAMPLE"
        or timebase["ticksPerSecondNumerator"] != binding["sampleRate"]
        or timebase["ticksPerSecondDenominator"] != 1
        or cue["intervalSemantics"] != "HALF_OPEN"
        or cue["timeAuthority"] != "INTEGER_SAMPLE_INDEX"
    ):
        raise TimelineRangeError("AudioCue time authority is invalid")
    subtitle = cue["subtitleTimingReference"]
    if role in {"dialogue", "narration"}:
        if not isinstance(subtitle, Mapping):
            raise TimelineSourceBindingError("speech AudioCue requires subtitle timing")
        subtitle = _verify_nested_digest(subtitle, "SubtitleTimingReference")
        source_text = _text(subtitle.get("sourceText"), "sourceText")
        text = _text(subtitle.get("text"), "subtitle text")
        text_start = _integer(subtitle.get("textRangeStart"), "textRangeStart")
        text_end = _integer(
            subtitle.get("textRangeEndExclusive"),
            "textRangeEndExclusive",
            minimum=1,
        )
        from hashlib import sha256

        if (
            subtitle.get("scriptVersionRef") != expected_script_version_ref
            or subtitle.get("scriptVersionDigest") != expected_script_version_digest
            or subtitle.get("sourceTextDigest")
            != sha256(source_text.encode("utf-8")).hexdigest()
            or subtitle.get("textDigest") != sha256(text.encode("utf-8")).hexdigest()
            or text_start >= text_end
            or text_end > len(source_text)
            or source_text[text_start:text_end] != text
        ):
            raise TimelineSourceBindingError("subtitle text or ScriptVersion binding is stale")
    elif subtitle is not None:
        raise TimelineSourceBindingError("non-speech AudioCue cannot bind subtitles")
    for field in ("wordTimings", "phonemeTimings"):
        if not isinstance(cue[field], list):
            raise TimelinePreviewContractError(f"AudioCue {field} is invalid")
        for item in cue[field]:
            _verify_nested_digest(item, f"AudioCue {field} item")
    provenance = _verify_nested_digest(cue["provenance"], "AudioCue provenance")
    sources = provenance.get("sourceRefs")
    if not isinstance(sources, list):
        raise TimelineSourceBindingError("AudioCue provenance is incomplete")
    required_sources = {
        (cue["assetVersionRef"], cue["assetVersionDigest"]),
        (cue["scriptVersionRef"], cue["scriptVersionDigest"]),
        (timing["artifactEvidenceRef"], timing["artifactEvidenceDigest"]),
    }
    observed_sources = {
        (item.get("sourceRef"), item.get("sourceDigest"))
        for item in sources
        if isinstance(item, Mapping)
    }
    if not required_sources.issubset(observed_sources):
        raise TimelineSourceBindingError("AudioCue provenance sources are stale")
    technical_cues = validation.get("audioCueBindings")
    if not isinstance(technical_cues, list) or not any(
        isinstance(item, Mapping)
        and item.get("cueVersionRef") == cue["cueVersionRef"]
        and item.get("cueDigest") == cue["payloadDigest"]
        for item in technical_cues
    ):
        raise TimelineSourceBindingError(
            "AudioTechnicalValidation does not bind the exact AudioCue"
        )
    if (
        cue["state"] != "PROPOSED"
        or cue["authorityState"] != AUDIO_CUE_AUTHORITY_STATE
        or cue["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or cue["immutable"] is not True
        or cue["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("AudioCue lifecycle is invalid")
    return cue


def _critical_stem_member(
    value: Any,
    *,
    bindings_by_asset: Mapping[str, dict[str, Any]],
    cues_by_version: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    raw = _mapping_from_recorded(value, AudioStemMember, "AudioStemMember")
    member = _verify_sealed(raw, _STEM_MEMBER_FIELDS, "recorded AudioStemMember")
    if member["schemaVersion"] != AUDIO_STEM_MEMBER_SCHEMA_VERSION:
        raise TimelinePreviewContractError("AudioStemMember schema is unsupported")
    for field in ("stemMemberRef", "stemLaneRef", "sourceAssetVersionRef", "createdBy"):
        _ref(member[field], field)
    role = member["stemRole"]
    if role not in AUDIO_STEM_ROLES:
        raise TimelineTrackError("AudioStemMember role is invalid")
    if member["overlapPolicy"] not in {"NON_OVERLAPPING", "ALLOW_OVERLAP"}:
        raise TimelineTrackError("AudioStemMember overlap policy is invalid")
    binding = bindings_by_asset.get(member["sourceAssetVersionRef"])
    if binding is None:
        raise TimelineAuthorityError("AudioStemMember has no audio input binding")
    if (
        member["sourceAssetVersionDigest"] != binding["assetVersionDigest"]
        or member["sourceAssetVersionType"] != binding["assetVersionType"]
        or role != _asset_role(binding["assetVersion"])
        or member["rightsBindingRef"] != binding["rightsBindingRef"]
        or member["rightsBindingDigest"] != binding["rightsBindingDigest"]
    ):
        raise TimelineSourceBindingError("AudioStemMember source binding is stale")
    timing = _verify_sealed(
        member["sourceTimingEvidence"],
        _SOURCE_TIMING_FIELDS,
        "AudioStemMember timing evidence",
    )
    if timing != binding["technicalValidation"].get("sourceTimingEvidence"):
        raise TimelineSourceBindingError("AudioStemMember timing evidence is stale")
    timebase = _closed(
        member["timebase"],
        frozenset(
            {"unit", "ticksPerSecondNumerator", "ticksPerSecondDenominator"}
        ),
        "AudioStemMember timebase",
    )
    if (
        timebase["unit"] != "AUDIO_SAMPLE"
        or timebase["ticksPerSecondNumerator"] != binding["sampleRate"]
        or timebase["ticksPerSecondDenominator"] != 1
    ):
        raise TimelineRangeError("AudioStemMember timebase is invalid")
    source_start = _integer(member["sourceStartSample"], "sourceStartSample")
    source_end = _integer(member["sourceEndSample"], "sourceEndSample", minimum=1)
    stem_start = _integer(member["stemStartSample"], "stemStartSample")
    stem_end = _integer(member["stemEndSample"], "stemEndSample", minimum=1)
    if (
        source_start >= source_end
        or source_end > binding["sampleCount"]
        or stem_start >= stem_end
        or source_end - source_start != stem_end - stem_start
    ):
        raise TimelineRangeError("AudioStemMember sample ranges are invalid")
    cue_fields = (
        member["sourceCueRef"],
        member["sourceCueVersionRef"],
        member["sourceCueDigest"],
    )
    if any(item is not None for item in cue_fields):
        if any(item is None for item in cue_fields):
            raise TimelineSourceBindingError("AudioStemMember Cue binding is incomplete")
        cue = cues_by_version.get(str(member["sourceCueVersionRef"]))
        if (
            cue is None
            or cue["cueRef"] != member["sourceCueRef"]
            or cue["payloadDigest"] != member["sourceCueDigest"]
            or cue["assetVersionRef"] != member["sourceAssetVersionRef"]
            or cue["sourceStartSample"] != source_start
            or cue["sourceEndSample"] != source_end
            or cue["cueRole"] != role
        ):
            raise TimelineSourceBindingError("AudioStemMember Cue binding is stale")
    provenance = _verify_nested_digest(member["provenance"], "AudioStemMember provenance")
    sources = provenance.get("sourceRefs")
    if not isinstance(sources, list):
        raise TimelineSourceBindingError(
            "AudioStemMember provenance is incomplete"
        )
    observed = {
        (item.get("sourceRef"), item.get("sourceDigest"))
        for item in sources
        if isinstance(item, Mapping)
    }
    required = {
        (member["sourceAssetVersionRef"], member["sourceAssetVersionDigest"]),
        (member["rightsBindingRef"], member["rightsBindingDigest"]),
        (timing["artifactEvidenceRef"], timing["artifactEvidenceDigest"]),
    }
    if member["sourceCueVersionRef"] is not None:
        required.add((member["sourceCueVersionRef"], member["sourceCueDigest"]))
    if not required.issubset(observed):
        raise TimelineSourceBindingError("AudioStemMember provenance is stale")
    if (
        member["state"] != "CONTRACT_ONLY"
        or member["authorityState"] != AUDIO_STEM_AUTHORITY_STATE
        or member["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or member["immutable"] is not True
        or member["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("AudioStemMember lifecycle is invalid")
    return member


def _critical_stem_set(
    value: Any,
    *,
    members_by_ref: Mapping[str, dict[str, Any]],
    expected_workspace: str,
    expected_run_ref: str,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    raw = _mapping_from_recorded(value, AudioStemSet, "AudioStemSet")
    stems = _verify_sealed(raw, _STEM_SET_FIELDS, "recorded AudioStemSet")
    if stems["schemaVersion"] != AUDIO_STEM_SET_SCHEMA_VERSION:
        raise TimelinePreviewContractError("AudioStemSet schema is unsupported")
    if (
        stems["workspaceRef"] != expected_workspace
        or stems["productionRunRef"] != expected_run_ref
        or stems["scriptVersionRef"] != expected_script_version_ref
        or stems["scriptVersionDigest"] != expected_script_version_digest
    ):
        raise TimelineSourceBindingError("AudioStemSet scope is stale")
    _scope(stems)
    for field in ("stemSetRef", "stemSetVersionRef", "createdBy"):
        _ref(stems[field], field)
    _sha256(stems["scriptVersionDigest"], "scriptVersionDigest")
    sample_rate = _integer(stems["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000)
    duration = _integer(
        stems["preliminaryDurationSamples"], "preliminaryDurationSamples", minimum=1
    )
    timebase = _closed(
        stems["timebase"],
        frozenset(
            {"unit", "ticksPerSecondNumerator", "ticksPerSecondDenominator"}
        ),
        "AudioStemSet timebase",
    )
    if (
        timebase["unit"] != "AUDIO_SAMPLE"
        or timebase["ticksPerSecondNumerator"] != sample_rate
        or timebase["ticksPerSecondDenominator"] != 1
    ):
        raise TimelineRangeError("AudioStemSet timebase is invalid")
    raw_members = stems["members"]
    if not isinstance(raw_members, list) or not raw_members:
        raise TimelineAuthorityError("AudioStemSet has no members")
    expected_members = [members_by_ref.get(item.get("stemMemberRef")) for item in raw_members]
    if any(item is None for item in expected_members) or raw_members != expected_members:
        raise TimelineSourceBindingError("AudioStemSet member mappings are stale")
    for member in expected_members:
        assert member is not None
        if member["sourceTimingEvidence"]["sampleRate"] != sample_rate:
            raise TimelineSourceBindingError("AudioStemSet sample rates differ")
        if member["stemEndSample"] > duration:
            raise TimelineRangeError("AudioStemMember exceeds AudioStemSet duration")
    provenance = _verify_nested_digest(stems["provenance"], "AudioStemSet provenance")
    sources = provenance.get("sourceRefs")
    if not isinstance(sources, list):
        raise TimelineSourceBindingError("AudioStemSet provenance is incomplete")
    observed = {
        (item.get("sourceRef"), item.get("sourceDigest"))
        for item in sources
        if isinstance(item, Mapping)
    }
    required = {
        (stems["scriptVersionRef"], stems["scriptVersionDigest"]),
        *{
            (member["stemMemberRef"], member["payloadDigest"])
            for member in expected_members
            if member is not None
        },
    }
    if not required.issubset(observed):
        raise TimelineSourceBindingError("AudioStemSet provenance is stale")
    if (
        stems["state"] != "CONTRACT_ONLY"
        or stems["authorityState"] != AUDIO_STEM_AUTHORITY_STATE
        or stems["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or stems["immutable"] is not True
        or stems["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("AudioStemSet lifecycle is invalid")
    return stems


def _normalize_bundle_parts(
    *,
    workspace: str,
    run_ref: str,
    script_ref: str,
    script_digest: str,
    audio_input_bindings: Sequence[Any],
    audio_cues: Sequence[Any],
    audio_stem_set: Any,
    audio_stem_members: Sequence[Any],
    glyph_reveal_requirements: Sequence[Any],
    mask_asset_bindings: Sequence[Any],
    require_binding_wrappers: bool,
) -> dict[str, Any]:
    if not isinstance(audio_input_bindings, Sequence) or isinstance(
        audio_input_bindings, (str, bytes)
    ):
        raise TimelineAuthorityError("audio input bindings are required")
    bindings: list[dict[str, Any]] = []
    for value in audio_input_bindings:
        if require_binding_wrappers and type(value) is not AudioInputBinding:
            raise TimelineAuthorityError("AudioInputBinding wrapper is required")
        mapping = (
            value.as_dict()
            if type(value) is AudioInputBinding
            else _validate_audio_input_binding_mapping(value)
        )
        validated = _validate_audio_input_binding_mapping(mapping)
        if validated["workspaceRef"] != workspace or validated["productionRunRef"] != run_ref:
            raise TimelineSourceBindingError("AudioInputBinding scope is stale")
        bindings.append(validated)
    if not bindings:
        raise TimelineAuthorityError("at least one audible input is required")
    bindings.sort(key=lambda item: item["audioInputBindingRef"])
    if len({item["audioInputBindingRef"] for item in bindings}) != len(bindings):
        raise TimelinePreviewContractError("AudioInputBinding refs are duplicated")
    by_asset = {item["assetVersionRef"]: item for item in bindings}
    if len(by_asset) != len(bindings):
        raise TimelinePreviewContractError("audio AssetVersions are duplicated")

    cues = [
        _critical_audio_cue(
            value,
            bindings_by_asset=by_asset,
            expected_workspace=workspace,
            expected_run_ref=run_ref,
            expected_script_version_ref=script_ref,
            expected_script_version_digest=script_digest,
        )
        for value in audio_cues
    ]
    cues.sort(key=lambda item: item["cueVersionRef"])
    if len({item["cueVersionRef"] for item in cues}) != len(cues):
        raise TimelinePreviewContractError("AudioCue versions are duplicated")
    cues_by_version = {item["cueVersionRef"]: item for item in cues}

    members = [
        _critical_stem_member(
            value,
            bindings_by_asset=by_asset,
            cues_by_version=cues_by_version,
        )
        for value in audio_stem_members
    ]
    members.sort(key=lambda item: item["stemMemberRef"])
    if len({item["stemMemberRef"] for item in members}) != len(members):
        raise TimelinePreviewContractError("AudioStemMember refs are duplicated")
    members_by_ref = {item["stemMemberRef"]: item for item in members}
    stems = _critical_stem_set(
        audio_stem_set,
        members_by_ref=members_by_ref,
        expected_workspace=workspace,
        expected_run_ref=run_ref,
        expected_script_version_ref=script_ref,
        expected_script_version_digest=script_digest,
    )

    glyphs: list[dict[str, Any]] = []
    for value in glyph_reveal_requirements:
        requirement = (
            GlyphRevealRequirementV2.from_mapping(value.as_dict())
            if type(value) is GlyphRevealRequirementV2
            else GlyphRevealRequirementV2.from_mapping(value)
        )
        mapping = requirement.as_dict()
        if mapping["workspaceRef"] != workspace or mapping["productionRunRef"] != run_ref:
            raise TimelineSourceBindingError("GlyphRevealRequirement scope is stale")
        glyphs.append(mapping)
    glyphs.sort(key=lambda item: item["requirementRef"])
    if len({item["requirementRef"] for item in glyphs}) != len(glyphs):
        raise TimelinePreviewContractError("GlyphRevealRequirement refs are duplicated")

    masks: list[dict[str, Any]] = []
    for value in mask_asset_bindings:
        if require_binding_wrappers and type(value) is not MaskAssetVersionBinding:
            raise TimelineAuthorityError("MaskAssetVersionBinding wrapper is required")
        mapping = (
            value.as_dict()
            if type(value) is MaskAssetVersionBinding
            else _validate_mask_binding_mapping(value)
        )
        mapping = _validate_mask_binding_mapping(mapping)
        if mapping["workspaceRef"] != workspace or mapping["productionRunRef"] != run_ref:
            raise TimelineSourceBindingError("MaskAssetVersionBinding scope is stale")
        masks.append(mapping)
    masks.sort(key=lambda item: (item["glyphSlug"], item["maskOrdinal"]))
    if len({item["assetVersionRef"] for item in masks}) != len(masks):
        raise TimelinePreviewContractError("mask AssetVersion refs are duplicated")
    masks_by_asset = {item["assetVersionRef"]: item for item in masks}
    for glyph in glyphs:
        expected = glyph["maskAssetVersionBindings"]
        for source in expected:
            mask = masks_by_asset.get(source["assetVersionRef"])
            if (
                mask is None
                or mask["assetVersionDigest"] != source["assetVersionDigest"]
                or mask["fileDigest"] != source["fileDigest"]
                or mask["pixelDigest"] != source["pixelDigest"]
                or mask["glyphSlug"] != source["glyphSlug"]
                or mask["maskOrdinal"] != source["revealOrdinal"]
            ):
                raise TimelineSourceBindingError(
                    "GlyphRevealRequirement mask binding is stale"
                )
    return {
        "audioInputBindings": bindings,
        "audioCues": cues,
        "audioStemSet": stems,
        "audioStemMembers": members,
        "glyphRevealRequirements": glyphs,
        "maskAssetVersionBindings": masks,
    }


def _validate_timeline_input_bundle_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _TIMELINE_INPUT_BUNDLE_FIELDS, "TimelineInputBundle"
    )
    if result["schemaVersion"] != TIMELINE_INPUT_BUNDLE_SCHEMA_VERSION:
        raise TimelinePreviewContractError("TimelineInputBundle schema is unsupported")
    workspace = _ref(result["workspaceRef"], "workspaceRef")
    run_ref = _ref(result["productionRunRef"], "productionRunRef")
    _ref(result["timelineInputBundleRef"], "timelineInputBundleRef")
    script_ref = _ref(result["scriptVersionRef"], "scriptVersionRef")
    script_digest = _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    normalized = _normalize_bundle_parts(
        workspace=workspace,
        run_ref=run_ref,
        script_ref=script_ref,
        script_digest=script_digest,
        audio_input_bindings=result["audioInputBindings"],
        audio_cues=result["audioCues"],
        audio_stem_set=result["audioStemSet"],
        audio_stem_members=result["audioStemMembers"],
        glyph_reveal_requirements=result["glyphRevealRequirements"],
        mask_asset_bindings=result["maskAssetVersionBindings"],
        require_binding_wrappers=False,
    )
    if any(result[field] != normalized[field] for field in normalized):
        raise TimelineSourceBindingError("TimelineInputBundle canonical order is stale")
    if (
        result["state"] != "REGISTERED_INPUTS"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("TimelineInputBundle lifecycle is invalid")
    return result


def build_timeline_input_bundle(
    command: Mapping[str, Any],
    *,
    audio_input_bindings: Sequence[AudioInputBinding],
    audio_cues: Sequence[AudioCue | Mapping[str, Any]],
    audio_stem_set: AudioStemSet | Mapping[str, Any],
    audio_stem_members: Sequence[AudioStemMember | Mapping[str, Any]],
    glyph_reveal_requirements: Sequence[
        GlyphRevealRequirementV2 | Mapping[str, Any]
    ],
    mask_asset_bindings: Sequence[MaskAssetVersionBinding],
) -> dict[str, Any]:
    """Revalidate recorded Cue/Stem mappings against exact registered inputs."""

    value = _closed(
        command,
        _TIMELINE_INPUT_BUNDLE_COMMAND_FIELDS,
        "TimelineInputBundle command",
    )
    workspace = _ref(value["workspaceRef"], "workspaceRef")
    run_ref = _ref(value["productionRunRef"], "productionRunRef")
    _ref(value["timelineInputBundleRef"], "timelineInputBundleRef")
    script_ref = _ref(value["scriptVersionRef"], "scriptVersionRef")
    script_digest = _sha256(value["scriptVersionDigest"], "scriptVersionDigest")
    normalized = _normalize_bundle_parts(
        workspace=workspace,
        run_ref=run_ref,
        script_ref=script_ref,
        script_digest=script_digest,
        audio_input_bindings=audio_input_bindings,
        audio_cues=audio_cues,
        audio_stem_set=audio_stem_set,
        audio_stem_members=audio_stem_members,
        glyph_reveal_requirements=glyph_reveal_requirements,
        mask_asset_bindings=mask_asset_bindings,
        require_binding_wrappers=True,
    )
    result = _seal(
        {
            "schemaVersion": TIMELINE_INPUT_BUNDLE_SCHEMA_VERSION,
            **value,
            **normalized,
            "state": "REGISTERED_INPUTS",
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_timeline_input_bundle_mapping(result)


def validate_timeline_input_bundle(value: Any) -> "TimelineInputBundle":
    """Revalidate a persisted bundle without trusting its evidence-record digest alone."""

    return TimelineInputBundle.from_mapping(value)


class TimelineInputBundle(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TimelineInputBundle":
        return cls._from_validated(_validate_timeline_input_bundle_mapping(value))


_TIMELINE_FIELDS = frozenset(
    {
        "schemaVersion",
        *_SCOPE_FIELDS,
        "timelineRef",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_TIMELINE_COMMAND_FIELDS = frozenset(
    {*_SCOPE_FIELDS, "timelineRef", "createdBy", "createdAt"}
)


def _validate_timeline_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_FIELDS, "Timeline")
    if result["schemaVersion"] != TIMELINE_SCHEMA_VERSION_V2:
        raise TimelinePreviewContractError("Timeline schema is unsupported")
    _scope(result)
    _ref(result["timelineRef"], "timelineRef")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    if (
        result["state"] != "ROOT"
        or result["authorityState"] != TIMELINE_AUTHORITY_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("Timeline root lifecycle is invalid")
    return result


def build_timeline(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _TIMELINE_COMMAND_FIELDS, "Timeline command")
    _scope(value)
    _ref(value["timelineRef"], "timelineRef")
    _ref(value["createdBy"], "createdBy")
    _timestamp(value["createdAt"], "createdAt")
    return _validate_timeline_mapping(
        _seal(
            {
                "schemaVersion": TIMELINE_SCHEMA_VERSION_V2,
                **value,
                "state": "ROOT",
                "authorityState": TIMELINE_AUTHORITY_STATE,
                "immutable": True,
                "publicationAllowed": False,
            }
        )
    )


def validate_timeline(value: Any) -> "Timeline":
    return Timeline.from_mapping(value)


class Timeline(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "Timeline":
        return cls._from_validated(_validate_timeline_mapping(value))


_TIMELINE_CLIP_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "timelineClipRef",
        "timelineTrackRef",
        "trackKind",
        "clipRef",
        "trackRef",
        "clipKind",
        "enabled",
        "timelineStartFrame",
        "timelineEndFrameExclusive",
        "sourceBinding",
        "roundingRule",
        "intervalSemantics",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TIMELINE_CLIP_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "timelineClipRef",
        "timelineTrackRef",
        "trackKind",
        "timelineStartFrame",
        "timelineEndFrameExclusive",
        "sourceBinding",
    }
)
_VIDEO_SOURCE_COMMAND_FIELDS = frozenset(
    {
        "creativeShotRef",
        "assetVersionRef",
        "assetVersionDigest",
        "storageKey",
        "fileDigest",
        "sourceStartFrame",
        "sourceEndFrameExclusive",
    }
)
_VIDEO_SOURCE_FIELDS = _VIDEO_SOURCE_COMMAND_FIELDS | frozenset(
    {"sourceInFrame", "sourceOutFrameExclusive"}
)
_AUDIO_SOURCE_COMMAND_FIELDS = frozenset(
    {
        "audioInputBindingRef",
        "stemMemberRef",
        "gainDb",
        "fadeInSamples",
        "fadeOutSamples",
    }
)
_AUDIO_SOURCE_FIELDS = frozenset(
    {
        "audioInputBindingRef",
        "audioInputBindingDigest",
        "stemMemberRef",
        "stemMemberDigest",
        "audioRole",
        "assetVersionRef",
        "audioAssetVersionRef",
        "assetVersionType",
        "assetVersionDigest",
        "audioAssetVersionDigest",
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
        "timelineStartSample",
        "timelineEndSampleExclusive",
        "gainDb",
        "fadeInSamples",
        "fadeOutSamples",
    }
)
_SUBTITLE_SOURCE_COMMAND_FIELDS = frozenset(
    {"audioCueVersionRef", "stemMemberRef", "language"}
)
_SUBTITLE_SOURCE_FIELDS = frozenset(
    {
        "audioCueRef",
        "audioCueVersionRef",
        "audioCueDigest",
        "stemMemberRef",
        "stemMemberDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "language",
        "text",
        "textDigest",
        "textStart",
        "textEndExclusive",
        "textRangeStart",
        "textRangeEndExclusive",
        "wordTimings",
    }
)
_EFFECT_SOURCE_COMMAND_FIELDS = frozenset({"glyphRevealRequirementRef"})
_EFFECT_SOURCE_FIELDS = frozenset(
    {
        "glyphRevealRequirementRef",
        "glyphRevealRequirementDigest",
        "glyphSlug",
        "targetShotRef",
        "sourceStartFrame",
        "sourceEndFrameExclusive",
        "layer",
        "blendMode",
        "compositeParams",
        "maskAssetVersionBindings",
    }
)
_GLYPH_REVEAL_EFFECT_LAYER = 1
_CLIP_KIND_BY_TRACK = {
    "VIDEO": "VIDEO_ASSET",
    "AUDIO": "AUDIO_ASSET",
    "SUBTITLE": "SUBTITLE_CUE",
    "EFFECT": "GLYPH_REVEAL",
}


def map_frame_boundary_to_sample(
    frame: int,
    *,
    sample_rate: int,
    frame_rate_numerator: int,
    frame_rate_denominator: int,
) -> int:
    """Map one frame boundary independently with no accumulated duration."""

    boundary = _integer(frame, "frame")
    rate = _integer(sample_rate, "sampleRate", minimum=1)
    numerator = _integer(
        frame_rate_numerator, "frameRateNumerator", minimum=1
    )
    denominator = _integer(
        frame_rate_denominator, "frameRateDenominator", minimum=1
    )
    return (boundary * rate * denominator) // numerator


def _bundle_mapping(value: Any, *, exact_wrapper: bool) -> dict[str, Any]:
    if exact_wrapper and type(value) is not TimelineInputBundle:
        raise TimelineAuthorityError("exact TimelineInputBundle wrapper is required")
    mapping = (
        value.as_dict()
        if type(value) is TimelineInputBundle
        else _validate_timeline_input_bundle_mapping(value)
    )
    return _validate_timeline_input_bundle_mapping(mapping)


def _clip_range(
    value: Mapping[str, Any], *, duration_frames: int
) -> tuple[int, int]:
    start = _integer(value["timelineStartFrame"], "timelineStartFrame")
    end = _integer(
        value["timelineEndFrameExclusive"],
        "timelineEndFrameExclusive",
        minimum=1,
    )
    if start >= end or end > duration_frames:
        raise TimelineRangeError("TimelineClip frame range is invalid")
    return start, end


def _timeline_clip_source(
    value: Mapping[str, Any],
    *,
    bundle: Mapping[str, Any],
    frame_rate: Mapping[str, int],
    duration_frames: int,
    building: bool,
) -> dict[str, Any]:
    kind = value["trackKind"]
    start, end = _clip_range(value, duration_frames=duration_frames)
    source = value["sourceBinding"]
    bindings = {
        item["audioInputBindingRef"]: item
        for item in bundle["audioInputBindings"]
    }
    members = {
        item["stemMemberRef"]: item for item in bundle["audioStemMembers"]
    }
    cues = {item["cueVersionRef"]: item for item in bundle["audioCues"]}
    glyphs = {
        item["requirementRef"]: item
        for item in bundle["glyphRevealRequirements"]
    }
    if kind == "VIDEO":
        if building:
            command = _closed(
                source,
                _VIDEO_SOURCE_COMMAND_FIELDS,
                "VIDEO sourceBinding command",
            )
            result = {
                **command,
                "sourceInFrame": command["sourceStartFrame"],
                "sourceOutFrameExclusive": command[
                    "sourceEndFrameExclusive"
                ],
            }
        else:
            result = _closed(source, _VIDEO_SOURCE_FIELDS, "VIDEO sourceBinding")
        glyph_matches = [
            item
            for item in glyphs.values()
            if item["basePlateAssetVersionRef"] == result["assetVersionRef"]
            and item["targetShotRef"] == result["creativeShotRef"]
        ]
        source_start = _integer(result["sourceStartFrame"], "sourceStartFrame")
        source_end = _integer(
            result["sourceEndFrameExclusive"],
            "sourceEndFrameExclusive",
            minimum=1,
        )
        if (
            len(glyph_matches) != 1
            or result["assetVersionDigest"]
            != glyph_matches[0]["basePlateAssetVersionDigest"]
            or result["fileDigest"] != glyph_matches[0]["basePlateFileDigest"]
            or result["sourceInFrame"] != source_start
            or result["sourceOutFrameExclusive"] != source_end
            or source_start >= source_end
            or source_end - source_start != end - start
        ):
            raise TimelineSourceBindingError("VIDEO source binding is stale")
        _storage_key(result["storageKey"], "VIDEO storageKey")
        _prefixed_sha256(result["fileDigest"], "VIDEO fileDigest")
        return result
    if kind == "AUDIO":
        if building:
            command = _closed(
                source, _AUDIO_SOURCE_COMMAND_FIELDS, "AUDIO sourceBinding command"
            )
            binding = bindings.get(command["audioInputBindingRef"])
            member = members.get(command["stemMemberRef"])
            if binding is None or member is None:
                raise TimelineAuthorityError("AUDIO source is not registered")
            if member["sourceAssetVersionRef"] != binding["assetVersionRef"]:
                raise TimelineSourceBindingError("AUDIO member binding is stale")
            artifact = binding["assetVersion"]["artifact"]
            result = {
                "audioInputBindingRef": binding["audioInputBindingRef"],
                "audioInputBindingDigest": binding["payloadDigest"],
                "stemMemberRef": member["stemMemberRef"],
                "stemMemberDigest": member["payloadDigest"],
                "audioRole": member["stemRole"],
                "assetVersionRef": binding["assetVersionRef"],
                "audioAssetVersionRef": binding["assetVersionRef"],
                "assetVersionType": binding["assetVersionType"],
                "assetVersionDigest": binding["assetVersionDigest"],
                "audioAssetVersionDigest": binding["assetVersionDigest"],
                "technicalValidationRef": binding["technicalValidationRef"],
                "technicalValidationDigest": binding[
                    "technicalValidationDigest"
                ],
                "storageKey": artifact["storageKey"],
                "fileDigest": binding["fileDigest"],
                "pcmContentDigest": binding["pcmContentDigest"],
                "sampleRate": binding["sampleRate"],
                "sourceChannelCount": binding["channelCount"],
                "sourceSampleCount": binding["sampleCount"],
                "sourceStartSample": member["sourceStartSample"],
                "sourceEndSampleExclusive": member["sourceEndSample"],
                "timelineStartSample": member["stemStartSample"],
                "timelineEndSampleExclusive": member["stemEndSample"],
                "gainDb": command["gainDb"],
                "fadeInSamples": command["fadeInSamples"],
                "fadeOutSamples": command["fadeOutSamples"],
            }
        else:
            result = _closed(source, _AUDIO_SOURCE_FIELDS, "AUDIO sourceBinding")
        binding = bindings.get(result["audioInputBindingRef"])
        member = members.get(result["stemMemberRef"])
        if binding is None or member is None:
            raise TimelineAuthorityError("AUDIO source is not registered")
        artifact = binding["assetVersion"]["artifact"]
        expected = {
            "audioInputBindingDigest": binding["payloadDigest"],
            "stemMemberDigest": member["payloadDigest"],
            "audioRole": member["stemRole"],
            "assetVersionRef": binding["assetVersionRef"],
            "audioAssetVersionRef": binding["assetVersionRef"],
            "assetVersionType": binding["assetVersionType"],
            "assetVersionDigest": binding["assetVersionDigest"],
            "audioAssetVersionDigest": binding["assetVersionDigest"],
            "technicalValidationRef": binding["technicalValidationRef"],
            "technicalValidationDigest": binding["technicalValidationDigest"],
            "storageKey": artifact["storageKey"],
            "fileDigest": binding["fileDigest"],
            "pcmContentDigest": binding["pcmContentDigest"],
            "sampleRate": binding["sampleRate"],
            "sourceChannelCount": binding["channelCount"],
            "sourceSampleCount": binding["sampleCount"],
            "sourceStartSample": member["sourceStartSample"],
            "sourceEndSampleExclusive": member["sourceEndSample"],
            "timelineStartSample": member["stemStartSample"],
            "timelineEndSampleExclusive": member["stemEndSample"],
        }
        if any(result.get(field) != expected_value for field, expected_value in expected.items()):
            raise TimelineSourceBindingError("AUDIO source projection is stale")
        gain = result["gainDb"]
        if isinstance(gain, bool) or not isinstance(gain, int) or not -96 <= gain <= 24:
            raise TimelinePreviewContractError("gainDb is invalid")
        fade_in = _integer(result["fadeInSamples"], "fadeInSamples")
        fade_out = _integer(result["fadeOutSamples"], "fadeOutSamples")
        source_span = result["sourceEndSampleExclusive"] - result["sourceStartSample"]
        expected_start = map_frame_boundary_to_sample(
            start,
            sample_rate=result["sampleRate"],
            frame_rate_numerator=frame_rate["numerator"],
            frame_rate_denominator=frame_rate["denominator"],
        )
        expected_end = map_frame_boundary_to_sample(
            end,
            sample_rate=result["sampleRate"],
            frame_rate_numerator=frame_rate["numerator"],
            frame_rate_denominator=frame_rate["denominator"],
        )
        if (
            result["sampleRate"] != 48_000
            or result["sourceChannelCount"] not in {1, 2}
            or result["timelineStartSample"] != expected_start
            or result["timelineEndSampleExclusive"] != expected_end
            or source_span != expected_end - expected_start
            or fade_in + fade_out > source_span
        ):
            raise TimelineRangeError("AUDIO sample/frame range is invalid")
        return result
    if kind == "SUBTITLE":
        if building:
            command = _closed(
                source,
                _SUBTITLE_SOURCE_COMMAND_FIELDS,
                "SUBTITLE sourceBinding command",
            )
            cue = cues.get(command["audioCueVersionRef"])
            member = members.get(command["stemMemberRef"])
            if cue is None or member is None:
                raise TimelineAuthorityError("SUBTITLE source is not registered")
            subtitle = cue["subtitleTimingReference"]
            if not isinstance(subtitle, Mapping):
                raise TimelineSourceBindingError("SUBTITLE Cue has no exact text")
            result = {
                "audioCueRef": cue["cueRef"],
                "audioCueVersionRef": cue["cueVersionRef"],
                "audioCueDigest": cue["payloadDigest"],
                "stemMemberRef": member["stemMemberRef"],
                "stemMemberDigest": member["payloadDigest"],
                "scriptVersionRef": cue["scriptVersionRef"],
                "scriptVersionDigest": cue["scriptVersionDigest"],
                "language": command["language"],
                "text": subtitle["text"],
                "textDigest": subtitle["textDigest"],
                "textStart": subtitle["textRangeStart"],
                "textEndExclusive": subtitle["textRangeEndExclusive"],
                "textRangeStart": subtitle["textRangeStart"],
                "textRangeEndExclusive": subtitle["textRangeEndExclusive"],
                "wordTimings": deepcopy(cue["wordTimings"]),
            }
        else:
            result = _closed(
                source, _SUBTITLE_SOURCE_FIELDS, "SUBTITLE sourceBinding"
            )
        cue = cues.get(result["audioCueVersionRef"])
        member = members.get(result["stemMemberRef"])
        if cue is None or member is None:
            raise TimelineAuthorityError("SUBTITLE source is not registered")
        subtitle = cue["subtitleTimingReference"]
        expected = {
            "audioCueRef": cue["cueRef"],
            "audioCueDigest": cue["payloadDigest"],
            "stemMemberDigest": member["payloadDigest"],
            "scriptVersionRef": cue["scriptVersionRef"],
            "scriptVersionDigest": cue["scriptVersionDigest"],
            "text": subtitle["text"],
            "textDigest": subtitle["textDigest"],
            "textStart": subtitle["textRangeStart"],
            "textEndExclusive": subtitle["textRangeEndExclusive"],
            "textRangeStart": subtitle["textRangeStart"],
            "textRangeEndExclusive": subtitle["textRangeEndExclusive"],
            "wordTimings": cue["wordTimings"],
        }
        if (
            any(result.get(field) != expected_value for field, expected_value in expected.items())
            or member["sourceCueVersionRef"] != cue["cueVersionRef"]
            or member["stemStartSample"]
            != map_frame_boundary_to_sample(
                start,
                sample_rate=member["sourceTimingEvidence"]["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
            or member["stemEndSample"]
            != map_frame_boundary_to_sample(
                end,
                sample_rate=member["sourceTimingEvidence"]["sampleRate"],
                frame_rate_numerator=frame_rate["numerator"],
                frame_rate_denominator=frame_rate["denominator"],
            )
        ):
            raise TimelineSourceBindingError("SUBTITLE source binding is stale")
        _text(result["language"], "subtitle language")
        return result
    if kind == "EFFECT":
        if building:
            command = _closed(
                source, _EFFECT_SOURCE_COMMAND_FIELDS, "EFFECT sourceBinding command"
            )
            glyph = glyphs.get(command["glyphRevealRequirementRef"])
            if glyph is None:
                raise TimelineAuthorityError("EFFECT source is not registered")
            result = {
                "glyphRevealRequirementRef": glyph["requirementRef"],
                "glyphRevealRequirementDigest": glyph["payloadDigest"],
                "glyphSlug": glyph["glyphSlug"],
                "targetShotRef": glyph["targetShotRef"],
                "sourceStartFrame": glyph["frameRangeStartInclusive"],
                "sourceEndFrameExclusive": glyph["frameRangeEndExclusive"],
                "layer": _GLYPH_REVEAL_EFFECT_LAYER,
                "blendMode": glyph["compositeParams"]["blendMode"],
                "compositeParams": deepcopy(glyph["compositeParams"]),
                "maskAssetVersionBindings": deepcopy(
                    glyph["maskAssetVersionBindings"]
                ),
            }
        else:
            result = _closed(source, _EFFECT_SOURCE_FIELDS, "EFFECT sourceBinding")
        glyph = glyphs.get(result["glyphRevealRequirementRef"])
        expected = None if glyph is None else {
            "glyphRevealRequirementDigest": glyph["payloadDigest"],
            "glyphSlug": glyph["glyphSlug"],
            "targetShotRef": glyph["targetShotRef"],
            "sourceStartFrame": glyph["frameRangeStartInclusive"],
            "sourceEndFrameExclusive": glyph["frameRangeEndExclusive"],
            "layer": _GLYPH_REVEAL_EFFECT_LAYER,
            "blendMode": glyph["compositeParams"]["blendMode"],
            "compositeParams": glyph["compositeParams"],
            "maskAssetVersionBindings": glyph["maskAssetVersionBindings"],
        }
        if (
            expected is None
            or any(result.get(field) != expected_value for field, expected_value in expected.items())
            or result["sourceEndFrameExclusive"] - result["sourceStartFrame"]
            != end - start
        ):
            raise TimelineSourceBindingError("EFFECT source binding is stale")
        _integer(result["layer"], "EFFECT layer", minimum=1, maximum=1)
        if result["blendMode"] != GLYPH_REVEAL_BLEND_MODE:
            raise TimelineSourceBindingError("EFFECT blendMode is stale")
        return result
    raise TimelineTrackError("TimelineClip trackKind is unsupported")


def _validate_timeline_clip_mapping(
    value: Any,
    *,
    timeline_input_bundle: Any,
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_CLIP_FIELDS, "TimelineClip")
    if result["schemaVersion"] != TIMELINE_CLIP_SCHEMA_VERSION:
        raise TimelinePreviewContractError("TimelineClip schema is unsupported")
    _ref(result["workspaceRef"], "workspaceRef")
    _ref(result["productionRunRef"], "productionRunRef")
    _ref(result["timelineClipRef"], "timelineClipRef")
    _ref(result["timelineTrackRef"], "timelineTrackRef")
    if result["trackKind"] not in TIMELINE_TRACK_KINDS:
        raise TimelineTrackError("TimelineClip trackKind is invalid")
    if (
        result["clipRef"] != result["timelineClipRef"]
        or result["trackRef"] != result["timelineTrackRef"]
        or result["clipKind"] != _CLIP_KIND_BY_TRACK[result["trackKind"]]
        or result["enabled"] is not True
    ):
        raise TimelineTrackError("TimelineClip explicit identity is stale")
    rate, _, _ = _frame_rate(frame_rate)
    duration = _integer(duration_frames, "durationFrames", minimum=1)
    bundle = _bundle_mapping(timeline_input_bundle, exact_wrapper=False)
    if (
        result["workspaceRef"] != bundle["workspaceRef"]
        or result["productionRunRef"] != bundle["productionRunRef"]
    ):
        raise TimelineSourceBindingError("TimelineClip scope is stale")
    normalized = _timeline_clip_source(
        result,
        bundle=bundle,
        frame_rate=rate,
        duration_frames=duration,
        building=False,
    )
    if result["sourceBinding"] != normalized:
        raise TimelineSourceBindingError("TimelineClip source is not canonical")
    if (
        result["roundingRule"] != TIMELINE_ROUNDING_RULE
        or result["intervalSemantics"] != TIMELINE_INTERVAL_SEMANTICS
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("TimelineClip lifecycle is invalid")
    return result


def build_timeline_clip(
    command: Mapping[str, Any],
    *,
    timeline_input_bundle: TimelineInputBundle,
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> dict[str, Any]:
    value = _closed(
        command, _TIMELINE_CLIP_COMMAND_FIELDS, "TimelineClip command"
    )
    workspace = _ref(value["workspaceRef"], "workspaceRef")
    run_ref = _ref(value["productionRunRef"], "productionRunRef")
    _ref(value["timelineClipRef"], "timelineClipRef")
    _ref(value["timelineTrackRef"], "timelineTrackRef")
    if value["trackKind"] not in TIMELINE_TRACK_KINDS:
        raise TimelineTrackError("TimelineClip trackKind is invalid")
    rate, _, _ = _frame_rate(frame_rate)
    duration = _integer(duration_frames, "durationFrames", minimum=1)
    bundle = _bundle_mapping(timeline_input_bundle, exact_wrapper=True)
    if workspace != bundle["workspaceRef"] or run_ref != bundle["productionRunRef"]:
        raise TimelineSourceBindingError("TimelineClip scope is stale")
    source = _timeline_clip_source(
        value,
        bundle=bundle,
        frame_rate=rate,
        duration_frames=duration,
        building=True,
    )
    result = _seal(
        {
            "schemaVersion": TIMELINE_CLIP_SCHEMA_VERSION,
            **{key: value[key] for key in _TIMELINE_CLIP_COMMAND_FIELDS if key != "sourceBinding"},
            "clipRef": value["timelineClipRef"],
            "trackRef": value["timelineTrackRef"],
            "clipKind": _CLIP_KIND_BY_TRACK[value["trackKind"]],
            "enabled": True,
            "sourceBinding": source,
            "roundingRule": TIMELINE_ROUNDING_RULE,
            "intervalSemantics": TIMELINE_INTERVAL_SEMANTICS,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_timeline_clip_mapping(
        result,
        timeline_input_bundle=timeline_input_bundle,
        frame_rate=rate,
        duration_frames=duration,
    )


def validate_timeline_clip(
    value: Any,
    *,
    timeline_input_bundle: TimelineInputBundle | Mapping[str, Any],
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> "TimelineClip":
    return TimelineClip._from_validated(
        _validate_timeline_clip_mapping(
            value,
            timeline_input_bundle=timeline_input_bundle,
            frame_rate=frame_rate,
            duration_frames=duration_frames,
        )
    )


class TimelineClip(_ImmutableWireContract):
    pass


_TIMELINE_TRACK_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "timelineTrackRef",
        "trackKind",
        "ordinal",
        "clips",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TIMELINE_TRACK_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "timelineTrackRef",
        "trackKind",
        "ordinal",
    }
)


def _validate_timeline_track_mapping(
    value: Any,
    *,
    timeline_input_bundle: Any,
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_TRACK_FIELDS, "TimelineTrack")
    if result["schemaVersion"] != TIMELINE_TRACK_SCHEMA_VERSION:
        raise TimelinePreviewContractError("TimelineTrack schema is unsupported")
    _ref(result["workspaceRef"], "workspaceRef")
    _ref(result["productionRunRef"], "productionRunRef")
    _ref(result["timelineTrackRef"], "timelineTrackRef")
    kind = result["trackKind"]
    if kind not in TIMELINE_TRACK_KINDS:
        raise TimelineTrackError("TimelineTrack kind is invalid")
    _integer(result["ordinal"], "ordinal", maximum=3)
    if result["ordinal"] != TIMELINE_TRACK_KINDS.index(kind):
        raise TimelineTrackError("TimelineTrack ordinal is not canonical")
    if not isinstance(result["clips"], list) or not result["clips"]:
        raise TimelineTrackError("TimelineTrack must contain at least one clip")
    clips = [
        _validate_timeline_clip_mapping(
            item,
            timeline_input_bundle=timeline_input_bundle,
            frame_rate=frame_rate,
            duration_frames=duration_frames,
        )
        for item in result["clips"]
    ]
    expected = sorted(
        clips,
        key=lambda item: (
            item["timelineStartFrame"],
            item["timelineEndFrameExclusive"],
            item["timelineClipRef"],
        ),
    )
    if clips != expected or len({item["timelineClipRef"] for item in clips}) != len(clips):
        raise TimelineTrackError("TimelineTrack clips are not canonical")
    if any(
        item["trackKind"] != kind
        or item["timelineTrackRef"] != result["timelineTrackRef"]
        or item["workspaceRef"] != result["workspaceRef"]
        or item["productionRunRef"] != result["productionRunRef"]
        for item in clips
    ):
        raise TimelineTrackError("TimelineTrack contains a mismatched clip")
    if kind == "VIDEO" and any(
        current["timelineStartFrame"] < previous["timelineEndFrameExclusive"]
        for previous, current in zip(clips, clips[1:])
    ):
        raise TimelineTrackError("VIDEO clips overlap")
    if result["immutable"] is not True or result["publicationAllowed"] is not False:
        raise TimelineAuthorityError("TimelineTrack lifecycle is invalid")
    return result


def build_timeline_track(
    command: Mapping[str, Any],
    *,
    clips: Sequence[TimelineClip],
    timeline_input_bundle: TimelineInputBundle,
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> dict[str, Any]:
    value = _closed(
        command, _TIMELINE_TRACK_COMMAND_FIELDS, "TimelineTrack command"
    )
    if not isinstance(clips, Sequence) or isinstance(clips, (str, bytes)):
        raise TimelineTrackError("TimelineTrack clips must be a sequence")
    if any(type(item) is not TimelineClip for item in clips):
        raise TimelineAuthorityError("exact TimelineClip wrappers are required")
    payloads = [item.as_dict() for item in clips]
    payloads.sort(
        key=lambda item: (
            item["timelineStartFrame"],
            item["timelineEndFrameExclusive"],
            item["timelineClipRef"],
        )
    )
    result = _seal(
        {
            "schemaVersion": TIMELINE_TRACK_SCHEMA_VERSION,
            **value,
            "clips": payloads,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_timeline_track_mapping(
        result,
        timeline_input_bundle=timeline_input_bundle,
        frame_rate=frame_rate,
        duration_frames=duration_frames,
    )


def validate_timeline_track(
    value: Any,
    *,
    timeline_input_bundle: TimelineInputBundle | Mapping[str, Any],
    frame_rate: Mapping[str, Any],
    duration_frames: int,
) -> "TimelineTrack":
    return TimelineTrack._from_validated(
        _validate_timeline_track_mapping(
            value,
            timeline_input_bundle=timeline_input_bundle,
            frame_rate=frame_rate,
            duration_frames=duration_frames,
        )
    )


class TimelineTrack(_ImmutableWireContract):
    pass


_TIMELINE_VERSION_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
        "timelineVersionRef",
        "version",
        "supersedesTimelineVersionRef",
        "supersedesTimelineVersionDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "frameRate",
        "width",
        "height",
        "pixelFormat",
        "durationFrames",
        "createdBy",
        "createdAt",
    }
)
_TIMELINE_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        *_SCOPE_FIELDS,
        "timelineRef",
        "timelineDigest",
        "timelineVersionRef",
        "version",
        "supersedesTimelineVersionRef",
        "supersedesTimelineVersionDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "timelineInputBundleRef",
        "timelineInputBundleDigest",
        "storyboardVersionRef",
        "storyboardBindingState",
        "sourceVersionRef",
        "frameRate",
        "roundingRule",
        "intervalSemantics",
        "canvasWidth",
        "canvasHeight",
        "durationFrames",
        "trackRefs",
        "tracks",
        "output",
        "state",
        "authorityState",
        "provenance",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_TIMELINE_OUTPUT_FIELDS = frozenset(
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
    }
)


def _timeline_version_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not TimelineVersion:
        raise TimelineAuthorityError("exact TimelineVersion wrapper is required")
    return value.as_dict()


def _validate_timeline_version_mapping(
    value: Any,
    *,
    timeline: Any,
    timeline_input_bundle: Any,
    predecessor_timeline_version: Any = None,
) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_VERSION_FIELDS, "TimelineVersion")
    if result["schemaVersion"] != TIMELINE_VERSION_SCHEMA_VERSION_V2:
        raise TimelinePreviewContractError("TimelineVersion schema is unsupported")
    root = (
        timeline.as_dict()
        if type(timeline) is Timeline
        else _validate_timeline_mapping(timeline)
    )
    root = _validate_timeline_mapping(root)
    bundle = _bundle_mapping(timeline_input_bundle, exact_wrapper=False)
    if (
        _scope(result) != _scope(root)
        or result["workspaceRef"] != bundle["workspaceRef"]
        or result["productionRunRef"] != bundle["productionRunRef"]
        or result["timelineRef"] != root["timelineRef"]
        or result["timelineDigest"] != root["payloadDigest"]
        or result["timelineInputBundleRef"] != bundle["timelineInputBundleRef"]
        or result["timelineInputBundleDigest"] != bundle["payloadDigest"]
        or result["scriptVersionRef"] != bundle["scriptVersionRef"]
        or result["scriptVersionDigest"] != bundle["scriptVersionDigest"]
    ):
        raise TimelineSourceBindingError("TimelineVersion root/input binding is stale")
    _ref(result["timelineVersionRef"], "timelineVersionRef")
    version = _integer(result["version"], "version", minimum=1)
    predecessor_fields = (
        result["supersedesTimelineVersionRef"],
        result["supersedesTimelineVersionDigest"],
    )
    if version == 1:
        if (
            any(item is not None for item in predecessor_fields)
            or predecessor_timeline_version is not None
            or result["sourceVersionRef"] is not None
        ):
            raise TimelineAuthorityError("TimelineVersion v1 cannot supersede")
    else:
        predecessor = _timeline_version_wrapper(predecessor_timeline_version)
        if (
            predecessor["timelineRef"] != result["timelineRef"]
            or predecessor["version"] != version - 1
            or result["supersedesTimelineVersionRef"]
            != predecessor["timelineVersionRef"]
            or result["supersedesTimelineVersionDigest"]
            != predecessor["payloadDigest"]
            or result["sourceVersionRef"]
            != predecessor["timelineVersionRef"]
        ):
            raise TimelineSourceBindingError("TimelineVersion predecessor is stale")
    rate, numerator, denominator = _frame_rate(result["frameRate"])
    duration = _integer(result["durationFrames"], "durationFrames", minimum=1)
    if not isinstance(result["tracks"], list) or len(result["tracks"]) != 4:
        raise TimelineTrackError("TimelineVersion requires exactly four tracks")
    tracks = [
        _validate_timeline_track_mapping(
            item,
            timeline_input_bundle=bundle,
            frame_rate=rate,
            duration_frames=duration,
        )
        for item in result["tracks"]
    ]
    if [item["trackKind"] for item in tracks] != list(TIMELINE_TRACK_KINDS):
        raise TimelineTrackError("TimelineVersion track order/kinds are invalid")
    refs = [item["timelineTrackRef"] for item in tracks]
    if len(set(refs)) != 4 or result["trackRefs"] != refs:
        raise TimelineTrackError("TimelineVersion track refs are duplicated")
    video_clips = tracks[0]["clips"]
    cursor = 0
    for clip in video_clips:
        if clip["timelineStartFrame"] != cursor:
            raise TimelineRangeError("VIDEO track is not contiguous")
        cursor = clip["timelineEndFrameExclusive"]
    if cursor != duration:
        raise TimelineRangeError("VIDEO track does not cover Timeline duration")
    video_by_shot = {
        clip["sourceBinding"]["creativeShotRef"]: clip for clip in video_clips
    }
    for effect in tracks[3]["clips"]:
        source = effect["sourceBinding"]
        video = video_by_shot.get(source["targetShotRef"])
        if (
            video is None
            or effect["timelineStartFrame"]
            != video["timelineStartFrame"] + source["sourceStartFrame"]
            or effect["timelineEndFrameExclusive"]
            != video["timelineStartFrame"] + source["sourceEndFrameExclusive"]
        ):
            raise TimelineSourceBindingError("EFFECT is not aligned to target VIDEO")
    output = _closed(result["output"], _TIMELINE_OUTPUT_FIELDS, "Timeline output")
    expected_samples = map_frame_boundary_to_sample(
        duration,
        sample_rate=48_000,
        frame_rate_numerator=numerator,
        frame_rate_denominator=denominator,
    )
    if (
        output["frameRate"] != rate
        or output["totalFrames"] != duration
        or output["sampleRate"] != 48_000
        or output["channelCount"] != 2
        or output["durationSamples"] != expected_samples
        or output["container"] != "mp4"
        or output["videoCodec"] != "h264"
        or output["pixelFormat"] not in {"yuv420p", "yuv422p", "yuv444p"}
        or output["audioCodec"] != "aac"
        or output["audioBitRate"] != 128_000
    ):
        raise TimelinePreviewContractError("Timeline output is invalid")
    _integer(output["width"], "width", minimum=1, maximum=131_072)
    _integer(output["height"], "height", minimum=1, maximum=131_072)
    if (
        result["storyboardVersionRef"] is not None
        or result["storyboardBindingState"]
        != "TECHNICAL_FIXTURE_ABSENT"
        or result["canvasWidth"] != output["width"]
        or result["canvasHeight"] != output["height"]
        or result["roundingRule"] != TIMELINE_ROUNDING_RULE
        or result["intervalSemantics"] != TIMELINE_INTERVAL_SEMANTICS
        or result["state"] != "COMPOSITION_READY"
        or result["authorityState"] != TIMELINE_AUTHORITY_STATE
        or result["provenance"] != TIMELINE_PROVENANCE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("TimelineVersion lifecycle is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_timeline_version(
    command: Mapping[str, Any],
    *,
    timeline: Timeline,
    tracks: Sequence[TimelineTrack],
    timeline_input_bundle: TimelineInputBundle,
    predecessor_timeline_version: TimelineVersion | None = None,
) -> dict[str, Any]:
    value = _closed(
        command, _TIMELINE_VERSION_COMMAND_FIELDS, "TimelineVersion command"
    )
    if type(timeline) is not Timeline or type(timeline_input_bundle) is not TimelineInputBundle:
        raise TimelineAuthorityError("exact Timeline and input bundle wrappers are required")
    if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)) or any(
        type(item) is not TimelineTrack for item in tracks
    ):
        raise TimelineAuthorityError("exact TimelineTrack wrappers are required")
    root = timeline.as_dict()
    bundle = timeline_input_bundle.as_dict()
    rate, numerator, denominator = _frame_rate(value["frameRate"])
    duration = _integer(value["durationFrames"], "durationFrames", minimum=1)
    output = {
        "width": _integer(value["width"], "width", minimum=1, maximum=131_072),
        "height": _integer(value["height"], "height", minimum=1, maximum=131_072),
        "frameRate": rate,
        "totalFrames": duration,
        "sampleRate": 48_000,
        "channelCount": 2,
        "durationSamples": map_frame_boundary_to_sample(
            duration,
            sample_rate=48_000,
            frame_rate_numerator=numerator,
            frame_rate_denominator=denominator,
        ),
        "container": "mp4",
        "videoCodec": "h264",
        "pixelFormat": value["pixelFormat"],
        "audioCodec": "aac",
        "audioBitRate": 128_000,
    }
    result = _seal(
        {
            "schemaVersion": TIMELINE_VERSION_SCHEMA_VERSION_V2,
            **{field: value[field] for field in _SCOPE_FIELDS},
            "timelineRef": root["timelineRef"],
            "timelineDigest": root["payloadDigest"],
            "timelineVersionRef": value["timelineVersionRef"],
            "version": value["version"],
            "supersedesTimelineVersionRef": value[
                "supersedesTimelineVersionRef"
            ],
            "supersedesTimelineVersionDigest": value[
                "supersedesTimelineVersionDigest"
            ],
            "scriptVersionRef": value["scriptVersionRef"],
            "scriptVersionDigest": value["scriptVersionDigest"],
            "timelineInputBundleRef": bundle["timelineInputBundleRef"],
            "timelineInputBundleDigest": bundle["payloadDigest"],
            "storyboardVersionRef": None,
            "storyboardBindingState": "TECHNICAL_FIXTURE_ABSENT",
            "sourceVersionRef": (
                None
                if predecessor_timeline_version is None
                else predecessor_timeline_version.as_dict()[
                    "timelineVersionRef"
                ]
            ),
            "frameRate": rate,
            "roundingRule": TIMELINE_ROUNDING_RULE,
            "intervalSemantics": TIMELINE_INTERVAL_SEMANTICS,
            "canvasWidth": output["width"],
            "canvasHeight": output["height"],
            "durationFrames": duration,
            "trackRefs": [item.as_dict()["timelineTrackRef"] for item in tracks],
            "tracks": [item.as_dict() for item in tracks],
            "output": output,
            "state": "COMPOSITION_READY",
            "authorityState": TIMELINE_AUTHORITY_STATE,
            "provenance": TIMELINE_PROVENANCE,
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_timeline_version_mapping(
        result,
        timeline=timeline,
        timeline_input_bundle=timeline_input_bundle,
        predecessor_timeline_version=predecessor_timeline_version,
    )


def validate_timeline_version(
    value: Any,
    *,
    timeline: Timeline | Mapping[str, Any],
    timeline_input_bundle: TimelineInputBundle | Mapping[str, Any],
    predecessor_timeline_version: TimelineVersion | None = None,
) -> "TimelineVersion":
    return TimelineVersion._from_validated(
        _validate_timeline_version_mapping(
            value,
            timeline=timeline,
            timeline_input_bundle=timeline_input_bundle,
            predecessor_timeline_version=predecessor_timeline_version,
        )
    )


class TimelineVersion(_ImmutableWireContract):
    pass


_SUBTITLE_ENTRY_FIELDS = frozenset(
    {
        "subtitleRef",
        "timelineClipRef",
        "timelineClipDigest",
        "audioCueRef",
        "audioCueVersionRef",
        "audioCueDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "language",
        "text",
        "textDigest",
        "textRangeStart",
        "textRangeEndExclusive",
        "timelineStartFrame",
        "timelineEndFrameExclusive",
        "wordTimings",
    }
)
_SUBTITLE_MANIFEST_COMMAND_FIELDS = frozenset(
    {"subtitleManifestRef", "createdBy", "createdAt"}
)
_SUBTITLE_MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "subtitleManifestRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "roundingRule",
        "intervalSemantics",
        "entries",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)


def _validated_timeline_version_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not TimelineVersion:
        raise TimelineAuthorityError("exact TimelineVersion wrapper is required")
    return value.as_dict()


def _subtitle_entries(version: Mapping[str, Any]) -> list[dict[str, Any]]:
    subtitle_track = next(
        item for item in version["tracks"] if item["trackKind"] == "SUBTITLE"
    )
    entries: list[dict[str, Any]] = []
    for clip in subtitle_track["clips"]:
        source = clip["sourceBinding"]
        entries.append(
            {
                "subtitleRef": "subtitle-" + _digest(
                    {
                        "timelineClipRef": clip["timelineClipRef"],
                        "audioCueDigest": source["audioCueDigest"],
                    }
                )[:32],
                "timelineClipRef": clip["timelineClipRef"],
                "timelineClipDigest": clip["payloadDigest"],
                "audioCueRef": source["audioCueRef"],
                "audioCueVersionRef": source["audioCueVersionRef"],
                "audioCueDigest": source["audioCueDigest"],
                "scriptVersionRef": source["scriptVersionRef"],
                "scriptVersionDigest": source["scriptVersionDigest"],
                "language": source["language"],
                "text": source["text"],
                "textDigest": source["textDigest"],
                "textRangeStart": source["textRangeStart"],
                "textRangeEndExclusive": source["textRangeEndExclusive"],
                "timelineStartFrame": clip["timelineStartFrame"],
                "timelineEndFrameExclusive": clip[
                    "timelineEndFrameExclusive"
                ],
                "wordTimings": deepcopy(source["wordTimings"]),
            }
        )
    return entries


def _validate_subtitle_manifest_mapping(
    value: Any, *, timeline_version: Any
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _SUBTITLE_MANIFEST_FIELDS, "SubtitleManifest"
    )
    if result["schemaVersion"] != SUBTITLE_MANIFEST_SCHEMA_VERSION:
        raise TimelinePreviewContractError("SubtitleManifest schema is unsupported")
    version = _validated_timeline_version_wrapper(timeline_version)
    if (
        result["workspaceRef"] != version["workspaceRef"]
        or result["productionRunRef"] != version["productionRunRef"]
        or result["timelineVersionRef"] != version["timelineVersionRef"]
        or result["timelineVersionDigest"] != version["payloadDigest"]
        or result["scriptVersionRef"] != version["scriptVersionRef"]
        or result["scriptVersionDigest"] != version["scriptVersionDigest"]
    ):
        raise TimelineSourceBindingError("SubtitleManifest Timeline binding is stale")
    _ref(result["subtitleManifestRef"], "subtitleManifestRef")
    expected = _subtitle_entries(version)
    if result["entries"] != expected or not expected:
        raise TimelineSourceBindingError("SubtitleManifest entries are stale")
    for index, entry in enumerate(expected):
        _closed(entry, _SUBTITLE_ENTRY_FIELDS, f"subtitle entries[{index}]")
        _ref(entry["subtitleRef"], "subtitleRef")
        _sha256(entry["textDigest"], "textDigest")
        if entry["timelineStartFrame"] >= entry["timelineEndFrameExclusive"]:
            raise TimelineRangeError("SubtitleManifest entry range is invalid")
    if (
        result["roundingRule"] != TIMELINE_ROUNDING_RULE
        or result["intervalSemantics"] != TIMELINE_INTERVAL_SEMANTICS
        or result["state"] != "MANIFEST_READY"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("SubtitleManifest lifecycle is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_subtitle_manifest(
    command: Mapping[str, Any], *, timeline_version: TimelineVersion
) -> dict[str, Any]:
    value = _closed(
        command, _SUBTITLE_MANIFEST_COMMAND_FIELDS, "SubtitleManifest command"
    )
    version = _validated_timeline_version_wrapper(timeline_version)
    _ref(value["subtitleManifestRef"], "subtitleManifestRef")
    _ref(value["createdBy"], "createdBy")
    _timestamp(value["createdAt"], "createdAt")
    result = _seal(
        {
            "schemaVersion": SUBTITLE_MANIFEST_SCHEMA_VERSION,
            "workspaceRef": version["workspaceRef"],
            "productionRunRef": version["productionRunRef"],
            "subtitleManifestRef": value["subtitleManifestRef"],
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "scriptVersionRef": version["scriptVersionRef"],
            "scriptVersionDigest": version["scriptVersionDigest"],
            "roundingRule": TIMELINE_ROUNDING_RULE,
            "intervalSemantics": TIMELINE_INTERVAL_SEMANTICS,
            "entries": _subtitle_entries(version),
            "state": "MANIFEST_READY",
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_subtitle_manifest_mapping(
        result, timeline_version=timeline_version
    )


def validate_subtitle_manifest(
    value: Any, *, timeline_version: TimelineVersion
) -> "SubtitleManifest":
    return SubtitleManifest._from_validated(
        _validate_subtitle_manifest_mapping(
            value, timeline_version=timeline_version
        )
    )


class SubtitleManifest(_ImmutableWireContract):
    pass


_TIMELINE_MIX_REQUEST_COMMAND_FIELDS = frozenset(
    {"mixRequestRef", "createdBy", "createdAt"}
)
_TIMELINE_MIX_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "mixRequestRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "timelineInputBundleRef",
        "timelineInputBundleDigest",
        "stemSetVersionRef",
        "stemSetDigest",
        "sampleRate",
        "channelCount",
        "durationSamples",
        "roundingRule",
        "mixParameters",
        "mixParametersDigest",
        "clips",
        "state",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_TIMELINE_MIX_CLIP_FIELDS = frozenset(
    {
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
)


def _timeline_mix_clips(version: Mapping[str, Any]) -> list[dict[str, Any]]:
    audio_track = next(
        item for item in version["tracks"] if item["trackKind"] == "AUDIO"
    )
    clips: list[dict[str, Any]] = []
    for clip in audio_track["clips"]:
        source = clip["sourceBinding"]
        clips.append(
            {
                "clipRef": clip["timelineClipRef"],
                "clipDigest": clip["payloadDigest"],
                "stemMemberRef": source["stemMemberRef"],
                "stemMemberDigest": source["stemMemberDigest"],
                "audioRole": source["audioRole"],
                "assetVersionRef": source["assetVersionRef"],
                "assetVersionType": source["assetVersionType"],
                "assetVersionDigest": source["assetVersionDigest"],
                "technicalValidationRef": source["technicalValidationRef"],
                "technicalValidationDigest": source[
                    "technicalValidationDigest"
                ],
                "storageKey": source["storageKey"],
                "fileDigest": source["fileDigest"],
                "pcmContentDigest": source["pcmContentDigest"],
                "sampleRate": source["sampleRate"],
                "sourceChannelCount": source["sourceChannelCount"],
                "sourceSampleCount": source["sourceSampleCount"],
                "sourceStartSample": source["sourceStartSample"],
                "sourceEndSampleExclusive": source[
                    "sourceEndSampleExclusive"
                ],
                "timelineStartFrame": clip["timelineStartFrame"],
                "timelineEndFrameExclusive": clip[
                    "timelineEndFrameExclusive"
                ],
                "timelineStartSample": source["timelineStartSample"],
                "timelineEndSampleExclusive": source[
                    "timelineEndSampleExclusive"
                ],
                "gainDb": source["gainDb"],
                "fadeInSamples": source["fadeInSamples"],
                "fadeOutSamples": source["fadeOutSamples"],
            }
        )
    return sorted(
        clips,
        key=lambda item: (
            -TIMELINE_MIX_PARAMETERS["rolePriority"][item["audioRole"]],
            item["clipRef"],
        ),
    )


def _validate_timeline_mix_request_mapping(
    value: Any,
    *,
    timeline_version: Any,
    timeline_input_bundle: Any,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _TIMELINE_MIX_REQUEST_FIELDS, "TimelineMixRequest"
    )
    if result["schemaVersion"] != TIMELINE_MIX_REQUEST_SCHEMA_VERSION:
        raise TimelinePreviewContractError("TimelineMixRequest schema is unsupported")
    version = _validated_timeline_version_wrapper(timeline_version)
    bundle = _bundle_mapping(timeline_input_bundle, exact_wrapper=False)
    stems = bundle["audioStemSet"]
    if (
        result["workspaceRef"] != version["workspaceRef"]
        or result["productionRunRef"] != version["productionRunRef"]
        or result["timelineVersionRef"] != version["timelineVersionRef"]
        or result["timelineVersionDigest"] != version["payloadDigest"]
        or result["timelineInputBundleRef"] != bundle["timelineInputBundleRef"]
        or result["timelineInputBundleDigest"] != bundle["payloadDigest"]
        or result["stemSetVersionRef"] != stems["stemSetVersionRef"]
        or result["stemSetDigest"] != stems["payloadDigest"]
    ):
        raise TimelineSourceBindingError("TimelineMixRequest lineage is stale")
    _ref(result["mixRequestRef"], "mixRequestRef")
    expected_clips = _timeline_mix_clips(version)
    if result["clips"] != expected_clips or not expected_clips:
        raise TimelineSourceBindingError("TimelineMixRequest clips are stale")
    for index, clip in enumerate(expected_clips):
        _closed(clip, _TIMELINE_MIX_CLIP_FIELDS, f"mix clips[{index}]")
    if (
        result["sampleRate"] != 48_000
        or result["channelCount"] != 2
        or result["durationSamples"] != version["output"]["durationSamples"]
        or result["roundingRule"] != TIMELINE_ROUNDING_RULE
        or result["mixParameters"] != TIMELINE_MIX_PARAMETERS
        or result["mixParametersDigest"] != _digest(TIMELINE_MIX_PARAMETERS)
        or result["state"] != "MIX_READY"
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("TimelineMixRequest lifecycle/profile is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_timeline_mix_request(
    command: Mapping[str, Any],
    *,
    timeline_version: TimelineVersion,
    timeline_input_bundle: TimelineInputBundle,
) -> dict[str, Any]:
    value = _closed(
        command,
        _TIMELINE_MIX_REQUEST_COMMAND_FIELDS,
        "TimelineMixRequest command",
    )
    version = _validated_timeline_version_wrapper(timeline_version)
    bundle = _bundle_mapping(timeline_input_bundle, exact_wrapper=True)
    stems = bundle["audioStemSet"]
    _ref(value["mixRequestRef"], "mixRequestRef")
    _ref(value["createdBy"], "createdBy")
    _timestamp(value["createdAt"], "createdAt")
    result = _seal(
        {
            "schemaVersion": TIMELINE_MIX_REQUEST_SCHEMA_VERSION,
            "workspaceRef": version["workspaceRef"],
            "productionRunRef": version["productionRunRef"],
            "mixRequestRef": value["mixRequestRef"],
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "timelineInputBundleRef": bundle["timelineInputBundleRef"],
            "timelineInputBundleDigest": bundle["payloadDigest"],
            "stemSetVersionRef": stems["stemSetVersionRef"],
            "stemSetDigest": stems["payloadDigest"],
            "sampleRate": 48_000,
            "channelCount": 2,
            "durationSamples": version["output"]["durationSamples"],
            "roundingRule": TIMELINE_ROUNDING_RULE,
            "mixParameters": deepcopy(TIMELINE_MIX_PARAMETERS),
            "mixParametersDigest": _digest(TIMELINE_MIX_PARAMETERS),
            "clips": _timeline_mix_clips(version),
            "state": "MIX_READY",
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_timeline_mix_request_mapping(
        result,
        timeline_version=timeline_version,
        timeline_input_bundle=timeline_input_bundle,
    )


def validate_timeline_mix_request(
    value: Any,
    *,
    timeline_version: TimelineVersion,
    timeline_input_bundle: TimelineInputBundle | Mapping[str, Any],
) -> "TimelineMixRequest":
    return TimelineMixRequest._from_validated(
        _validate_timeline_mix_request_mapping(
            value,
            timeline_version=timeline_version,
            timeline_input_bundle=timeline_input_bundle,
        )
    )


def project_timeline_mix_request(
    value: TimelineMixRequest,
) -> dict[str, Any]:
    """Return the exact closed V4 ``audioMix`` execution projection."""

    if type(value) is not TimelineMixRequest:
        raise TimelineAuthorityError("exact TimelineMixRequest wrapper is required")
    result = value.as_dict()
    return {
        "mixRequestRef": result["mixRequestRef"],
        "mixRequestDigest": result["payloadDigest"],
        "timelineVersionRef": result["timelineVersionRef"],
        "timelineVersionDigest": result["timelineVersionDigest"],
        "stemSetVersionRef": result["stemSetVersionRef"],
        "stemSetDigest": result["stemSetDigest"],
        "sampleRate": result["sampleRate"],
        "channelCount": result["channelCount"],
        "durationSamples": result["durationSamples"],
        "roundingRule": result["roundingRule"],
        "mixParameters": deepcopy(result["mixParameters"]),
        "mixParametersDigest": result["mixParametersDigest"],
        "clips": deepcopy(result["clips"]),
    }


class TimelineMixRequest(_ImmutableWireContract):
    pass


_V4_TIMELINE_COMPOSITION_RESULT_SCHEMA_VERSION = (
    "v4.m13-composition-result.v1"
)
_V4_COMPOSITION_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "compositionResultRef",
        "artifactRef",
        "executionRequestRef",
        "executionRequestDigest",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "adapterIdentity",
        "provenance",
        "providerUsed",
        "gpuUsed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_COMPOSITION_OUTPUT_PROBE_FIELDS = frozenset(
    {
        "container",
        "videoCodec",
        "pixelFormat",
        "width",
        "height",
        "frameRate",
        "frameCount",
        "audioCodec",
        "sampleRate",
        "channelCount",
        "sampleCount",
    }
)
_COMPOSITION_OUTPUT_DIGEST_FIELDS = frozenset(
    {
        "fileDigest",
        "fileDigestAlgorithm",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "frameCount",
        "frameRate",
        "pcmContentDigest",
        "pcmDigestSpec",
        "sampleRate",
        "channelCount",
        "sampleCount",
    }
)
_COMPOSITION_RESULT_COMMAND_FIELDS = frozenset({"createdBy", "createdAt"})
_COMPOSITION_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "compositionResultRef",
        "artifactRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "mixRequestRef",
        "mixRequestDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "inputBindingsDigest",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "mixOutputPcmContentDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "adapterIdentity",
        "provenance",
        "providerUsed",
        "gpuUsed",
        "executionResult",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)


def _validated_mix_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not TimelineMixRequest:
        raise TimelineAuthorityError("exact TimelineMixRequest wrapper is required")
    return value.as_dict()


def _validated_subtitle_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not SubtitleManifest:
        raise TimelineAuthorityError("exact SubtitleManifest wrapper is required")
    return value.as_dict()


def _v4_composition_result(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _V4_COMPOSITION_RESULT_FIELDS, "V4 composition result"
    )
    if result["schemaVersion"] != _V4_TIMELINE_COMPOSITION_RESULT_SCHEMA_VERSION:
        raise PreviewArtifactError("V4 composition result schema is unsupported")
    for field in (
        "compositionResultRef",
        "artifactRef",
        "executionRequestRef",
        "timelineVersionRef",
        "subtitleManifestRef",
    ):
        _ref(result[field], field)
    for field in (
        "executionRequestDigest",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "subtitleManifestDigest",
    ):
        _sha256(result[field], field)
    _prefixed_sha256(
        result["runtimeEvidenceDigest"], "runtimeEvidenceDigest"
    )
    _storage_key(result["outputStorageKey"], "outputStorageKey")
    _integer(result["outputByteSize"], "outputByteSize", minimum=1)
    _closed(
        result["outputMediaProbe"],
        _COMPOSITION_OUTPUT_PROBE_FIELDS,
        "composition outputMediaProbe",
    )
    output_digest = _closed(
        result["outputDigest"],
        _COMPOSITION_OUTPUT_DIGEST_FIELDS,
        "composition outputDigest",
    )
    _prefixed_sha256(output_digest["fileDigest"], "output fileDigest")
    _prefixed_sha256(
        output_digest["decodedFramePixelDigest"],
        "decodedFramePixelDigest",
    )
    _sha256(output_digest["pcmContentDigest"], "output pcmContentDigest")
    if (
        output_digest["fileDigestAlgorithm"] != "sha256"
        or output_digest["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC
        or output_digest["pixelMode"] != "RGBA"
        or output_digest["pcmDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
        or result["rendererIdentity"]
        != "v3.deterministic-timeline-preview-ffmpeg"
        or result["rendererVersion"] != "1"
        or result["adapterIdentity"] != "v4.local-composition-executor.v1"
        or result["provenance"] != TIMELINE_PROVENANCE
        or result["providerUsed"] is not False
        or result["gpuUsed"] is not False
        or result["publicationAllowed"] is not False
    ):
        raise PreviewArtifactError("V4 composition result authority is invalid")
    _text(result["ffmpegIdentity"], "ffmpegIdentity")
    return result


def _validate_composition_result_mapping(
    value: Any,
    *,
    timeline_version: Any,
    timeline_mix_request: Any,
    subtitle_manifest: Any,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _COMPOSITION_RESULT_FIELDS, "CompositionResult"
    )
    if result["schemaVersion"] != COMPOSITION_RESULT_SCHEMA_VERSION:
        raise TimelinePreviewContractError("CompositionResult schema is unsupported")
    version = _validated_timeline_version_wrapper(timeline_version)
    mix = _validated_mix_wrapper(timeline_mix_request)
    subtitle = _validated_subtitle_wrapper(subtitle_manifest)
    execution = _v4_composition_result(result["executionResult"])
    expected = {
        "workspaceRef": version["workspaceRef"],
        "productionRunRef": version["productionRunRef"],
        "compositionResultRef": execution["compositionResultRef"],
        "artifactRef": execution["artifactRef"],
        "timelineVersionRef": version["timelineVersionRef"],
        "timelineVersionDigest": version["payloadDigest"],
        "mixRequestRef": mix["mixRequestRef"],
        "mixRequestDigest": mix["payloadDigest"],
        "subtitleManifestRef": subtitle["subtitleManifestRef"],
        "subtitleManifestDigest": subtitle["payloadDigest"],
        "executionRequestRef": execution["executionRequestRef"],
        "executionRequestDigest": execution["executionRequestDigest"],
        "inputBindingsDigest": execution["inputBindingsDigest"],
        "outputStorageKey": execution["outputStorageKey"],
        "outputByteSize": execution["outputByteSize"],
        "outputMediaProbe": execution["outputMediaProbe"],
        "outputDigest": execution["outputDigest"],
        "mixOutputPcmContentDigest": execution["outputDigest"][
            "pcmContentDigest"
        ],
        "rendererIdentity": execution["rendererIdentity"],
        "rendererVersion": execution["rendererVersion"],
        "ffmpegIdentity": execution["ffmpegIdentity"],
        "runtimeEvidenceDigest": execution["runtimeEvidenceDigest"],
        "adapterIdentity": execution["adapterIdentity"],
        "provenance": execution["provenance"],
        "providerUsed": execution["providerUsed"],
        "gpuUsed": execution["gpuUsed"],
    }
    if any(result[field] != expected_value for field, expected_value in expected.items()):
        raise TimelineSourceBindingError("CompositionResult projection is stale")
    if (
        execution["timelineVersionRef"] != version["timelineVersionRef"]
        or execution["timelineVersionDigest"] != version["payloadDigest"]
        or execution["subtitleManifestRef"] != subtitle["subtitleManifestRef"]
        or execution["subtitleManifestDigest"] != subtitle["payloadDigest"]
        or mix["timelineVersionDigest"] != version["payloadDigest"]
    ):
        raise TimelineSourceBindingError("CompositionResult execution lineage is stale")
    probe = result["outputMediaProbe"]
    digest = result["outputDigest"]
    output = version["output"]
    expected_probe = {
        "container": output["container"],
        "videoCodec": output["videoCodec"],
        "pixelFormat": output["pixelFormat"],
        "width": output["width"],
        "height": output["height"],
        "frameRate": output["frameRate"],
        "frameCount": output["totalFrames"],
        "audioCodec": output["audioCodec"],
        "sampleRate": output["sampleRate"],
        "channelCount": output["channelCount"],
        "sampleCount": output["durationSamples"],
    }
    if probe != expected_probe or any(
        digest[field] != expected_probe[probe_field]
        for field, probe_field in (
            ("width", "width"),
            ("height", "height"),
            ("frameCount", "frameCount"),
            ("frameRate", "frameRate"),
            ("sampleRate", "sampleRate"),
            ("channelCount", "channelCount"),
            ("sampleCount", "sampleCount"),
        )
    ):
        raise PreviewArtifactError("CompositionResult output facts are stale")
    _sha256(
        result["mixOutputPcmContentDigest"],
        "mixOutputPcmContentDigest",
    )
    if (
        result["state"] != "COMPOSED"
        or result["authorityState"] != TIMELINE_AUTHORITY_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("CompositionResult lifecycle is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_composition_result(
    command: Mapping[str, Any],
    *,
    timeline_version: TimelineVersion,
    timeline_mix_request: TimelineMixRequest,
    subtitle_manifest: SubtitleManifest,
    execution_result: Mapping[str, Any],
) -> dict[str, Any]:
    value = _closed(
        command, _COMPOSITION_RESULT_COMMAND_FIELDS, "CompositionResult command"
    )
    version = _validated_timeline_version_wrapper(timeline_version)
    mix = _validated_mix_wrapper(timeline_mix_request)
    subtitle = _validated_subtitle_wrapper(subtitle_manifest)
    execution = _v4_composition_result(execution_result)
    _ref(value["createdBy"], "createdBy")
    _timestamp(value["createdAt"], "createdAt")
    result = _seal(
        {
            "schemaVersion": COMPOSITION_RESULT_SCHEMA_VERSION,
            "workspaceRef": version["workspaceRef"],
            "productionRunRef": version["productionRunRef"],
            "compositionResultRef": execution["compositionResultRef"],
            "artifactRef": execution["artifactRef"],
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "mixRequestRef": mix["mixRequestRef"],
            "mixRequestDigest": mix["payloadDigest"],
            "subtitleManifestRef": subtitle["subtitleManifestRef"],
            "subtitleManifestDigest": subtitle["payloadDigest"],
            "executionRequestRef": execution["executionRequestRef"],
            "executionRequestDigest": execution["executionRequestDigest"],
            "inputBindingsDigest": execution["inputBindingsDigest"],
            "outputStorageKey": execution["outputStorageKey"],
            "outputByteSize": execution["outputByteSize"],
            "outputMediaProbe": deepcopy(execution["outputMediaProbe"]),
            "outputDigest": deepcopy(execution["outputDigest"]),
            "mixOutputPcmContentDigest": execution["outputDigest"][
                "pcmContentDigest"
            ],
            "rendererIdentity": execution["rendererIdentity"],
            "rendererVersion": execution["rendererVersion"],
            "ffmpegIdentity": execution["ffmpegIdentity"],
            "runtimeEvidenceDigest": execution["runtimeEvidenceDigest"],
            "adapterIdentity": execution["adapterIdentity"],
            "provenance": execution["provenance"],
            "providerUsed": execution["providerUsed"],
            "gpuUsed": execution["gpuUsed"],
            "executionResult": execution,
            "state": "COMPOSED",
            "authorityState": TIMELINE_AUTHORITY_STATE,
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_composition_result_mapping(
        result,
        timeline_version=timeline_version,
        timeline_mix_request=timeline_mix_request,
        subtitle_manifest=subtitle_manifest,
    )


def validate_composition_result(
    value: Any,
    *,
    timeline_version: TimelineVersion,
    timeline_mix_request: TimelineMixRequest,
    subtitle_manifest: SubtitleManifest,
) -> "CompositionResult":
    return CompositionResult._from_validated(
        _validate_composition_result_mapping(
            value,
            timeline_version=timeline_version,
            timeline_mix_request=timeline_mix_request,
            subtitle_manifest=subtitle_manifest,
        )
    )


class CompositionResult(_ImmutableWireContract):
    pass


_PREVIEW_CANDIDATE_COMMAND_FIELDS = frozenset(
    {
        "previewCandidateRef",
        "previewCandidateVersionRef",
        "version",
        "supersedesPreviewCandidateVersionRef",
        "supersedesPreviewCandidateVersionDigest",
        "createdBy",
        "createdAt",
    }
)
_PREVIEW_CANDIDATE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "previewCandidateRef",
        "previewCandidateVersionRef",
        "version",
        "supersedesPreviewCandidateVersionRef",
        "supersedesPreviewCandidateVersionDigest",
        "timelineRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "mixRequestRef",
        "mixRequestDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "compositionResultRef",
        "compositionResultDigest",
        "compositionRequestDigest",
        "artifactRef",
        "fileDigest",
        "decodedFramePixelDigest",
        "pcmContentDigest",
        "outputByteSize",
        "mediaProbe",
        "outputMediaProbe",
        "runtimeIdentity",
        "state",
        "approvalStatus",
        "provenance",
        "rightsState",
        "providerUsed",
        "gpuUsed",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)


def _composition_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not CompositionResult:
        raise TimelineAuthorityError("exact CompositionResult wrapper is required")
    return value.as_dict()


def _preview_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not PreviewCandidate:
        raise TimelineAuthorityError("exact PreviewCandidate wrapper is required")
    return value.as_dict()


def _validate_preview_candidate_mapping(
    value: Any,
    *,
    timeline_version: Any,
    timeline_mix_request: Any,
    subtitle_manifest: Any,
    composition_result: Any,
    predecessor_preview_candidate: Any = None,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _PREVIEW_CANDIDATE_FIELDS, "PreviewCandidate"
    )
    if result["schemaVersion"] != PREVIEW_CANDIDATE_SCHEMA_VERSION_V2:
        raise TimelinePreviewContractError("PreviewCandidate schema is unsupported")
    version = _validated_timeline_version_wrapper(timeline_version)
    mix = _validated_mix_wrapper(timeline_mix_request)
    subtitle = _validated_subtitle_wrapper(subtitle_manifest)
    composition = _composition_wrapper(composition_result)
    digest = composition["outputDigest"]
    expected = {
        "workspaceRef": version["workspaceRef"],
        "productionRunRef": version["productionRunRef"],
        "timelineRef": version["timelineRef"],
        "timelineVersionRef": version["timelineVersionRef"],
        "timelineVersionDigest": version["payloadDigest"],
        "mixRequestRef": mix["mixRequestRef"],
        "mixRequestDigest": mix["payloadDigest"],
        "subtitleManifestRef": subtitle["subtitleManifestRef"],
        "subtitleManifestDigest": subtitle["payloadDigest"],
        "compositionResultRef": composition["compositionResultRef"],
        "compositionResultDigest": composition["payloadDigest"],
        "compositionRequestDigest": composition["executionRequestDigest"],
        "artifactRef": composition["artifactRef"],
        "fileDigest": digest["fileDigest"],
        "decodedFramePixelDigest": digest["decodedFramePixelDigest"],
        "pcmContentDigest": digest["pcmContentDigest"],
        "outputByteSize": composition["outputByteSize"],
        "mediaProbe": composition["outputMediaProbe"],
        "outputMediaProbe": composition["outputMediaProbe"],
        "runtimeIdentity": composition["runtimeEvidenceDigest"],
        "provenance": composition["provenance"],
        "providerUsed": composition["providerUsed"],
        "gpuUsed": composition["gpuUsed"],
    }
    if any(result[field] != expected_value for field, expected_value in expected.items()):
        raise TimelineSourceBindingError("PreviewCandidate projection is stale")
    _sha256(result["compositionRequestDigest"], "compositionRequestDigest")
    _prefixed_sha256(result["runtimeIdentity"], "runtimeIdentity")
    _ref(result["previewCandidateRef"], "previewCandidateRef")
    _ref(result["previewCandidateVersionRef"], "previewCandidateVersionRef")
    candidate_version = _integer(result["version"], "version", minimum=1)
    predecessor_fields = (
        result["supersedesPreviewCandidateVersionRef"],
        result["supersedesPreviewCandidateVersionDigest"],
    )
    if candidate_version == 1:
        if any(item is not None for item in predecessor_fields) or predecessor_preview_candidate is not None:
            raise TimelineAuthorityError("PreviewCandidate v1 cannot supersede")
    else:
        predecessor = _preview_wrapper(predecessor_preview_candidate)
        if (
            predecessor["previewCandidateRef"] != result["previewCandidateRef"]
            or predecessor["version"] != candidate_version - 1
            or result["supersedesPreviewCandidateVersionRef"]
            != predecessor["previewCandidateVersionRef"]
            or result["supersedesPreviewCandidateVersionDigest"]
            != predecessor["payloadDigest"]
        ):
            raise TimelineSourceBindingError("PreviewCandidate predecessor is stale")
    if (
        result["state"] != "CANDIDATE"
        or result["approvalStatus"] != "UNAPPROVED"
        or result["rightsState"] != "SOURCE_BINDINGS_VERIFIED_LOCAL_EVIDENCE"
        or result["providerUsed"] is not False
        or result["gpuUsed"] is not False
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise TimelineAuthorityError("PreviewCandidate authority is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_preview_candidate(
    command: Mapping[str, Any],
    *,
    timeline_version: TimelineVersion,
    timeline_mix_request: TimelineMixRequest,
    subtitle_manifest: SubtitleManifest,
    composition_result: CompositionResult,
    predecessor_preview_candidate: "PreviewCandidate | None" = None,
) -> dict[str, Any]:
    value = _closed(
        command, _PREVIEW_CANDIDATE_COMMAND_FIELDS, "PreviewCandidate command"
    )
    version = _validated_timeline_version_wrapper(timeline_version)
    mix = _validated_mix_wrapper(timeline_mix_request)
    subtitle = _validated_subtitle_wrapper(subtitle_manifest)
    composition = _composition_wrapper(composition_result)
    output = composition["outputDigest"]
    result = _seal(
        {
            "schemaVersion": PREVIEW_CANDIDATE_SCHEMA_VERSION_V2,
            "workspaceRef": version["workspaceRef"],
            "productionRunRef": version["productionRunRef"],
            "previewCandidateRef": value["previewCandidateRef"],
            "previewCandidateVersionRef": value[
                "previewCandidateVersionRef"
            ],
            "version": value["version"],
            "supersedesPreviewCandidateVersionRef": value[
                "supersedesPreviewCandidateVersionRef"
            ],
            "supersedesPreviewCandidateVersionDigest": value[
                "supersedesPreviewCandidateVersionDigest"
            ],
            "timelineRef": version["timelineRef"],
            "timelineVersionRef": version["timelineVersionRef"],
            "timelineVersionDigest": version["payloadDigest"],
            "mixRequestRef": mix["mixRequestRef"],
            "mixRequestDigest": mix["payloadDigest"],
            "subtitleManifestRef": subtitle["subtitleManifestRef"],
            "subtitleManifestDigest": subtitle["payloadDigest"],
            "compositionResultRef": composition["compositionResultRef"],
            "compositionResultDigest": composition["payloadDigest"],
            "compositionRequestDigest": composition[
                "executionRequestDigest"
            ],
            "artifactRef": composition["artifactRef"],
            "fileDigest": output["fileDigest"],
            "decodedFramePixelDigest": output[
                "decodedFramePixelDigest"
            ],
            "pcmContentDigest": output["pcmContentDigest"],
            "outputByteSize": composition["outputByteSize"],
            "mediaProbe": deepcopy(composition["outputMediaProbe"]),
            "outputMediaProbe": deepcopy(composition["outputMediaProbe"]),
            "runtimeIdentity": composition["runtimeEvidenceDigest"],
            "state": "CANDIDATE",
            "approvalStatus": "UNAPPROVED",
            "provenance": composition["provenance"],
            "rightsState": "SOURCE_BINDINGS_VERIFIED_LOCAL_EVIDENCE",
            "providerUsed": composition["providerUsed"],
            "gpuUsed": composition["gpuUsed"],
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_preview_candidate_mapping(
        result,
        timeline_version=timeline_version,
        timeline_mix_request=timeline_mix_request,
        subtitle_manifest=subtitle_manifest,
        composition_result=composition_result,
        predecessor_preview_candidate=predecessor_preview_candidate,
    )


def validate_preview_candidate(
    value: Any,
    *,
    timeline_version: TimelineVersion,
    timeline_mix_request: TimelineMixRequest,
    subtitle_manifest: SubtitleManifest,
    composition_result: CompositionResult,
    predecessor_preview_candidate: "PreviewCandidate | None" = None,
) -> "PreviewCandidate":
    return PreviewCandidate._from_validated(
        _validate_preview_candidate_mapping(
            value,
            timeline_version=timeline_version,
            timeline_mix_request=timeline_mix_request,
            subtitle_manifest=subtitle_manifest,
            composition_result=composition_result,
            predecessor_preview_candidate=predecessor_preview_candidate,
        )
    )


class PreviewCandidate(_ImmutableWireContract):
    pass


__all__ = [
    "AUDIO_INPUT_BINDING_SCHEMA_VERSION",
    "COMPOSITION_RESULT_SCHEMA_VERSION",
    "MASK_ASSET_VERSION_BINDING_SCHEMA_VERSION",
    "PREVIEW_CANDIDATE_SCHEMA_VERSION_V2",
    "SUBTITLE_MANIFEST_SCHEMA_VERSION",
    "TECHNICAL_FIXTURE_LABELS",
    "TIMELINE_AUTHORITY_STATE",
    "TIMELINE_CLIP_SCHEMA_VERSION",
    "TIMELINE_INPUT_BUNDLE_SCHEMA_VERSION",
    "TIMELINE_INTERVAL_SEMANTICS",
    "TIMELINE_MIX_PARAMETERS",
    "TIMELINE_MIX_REQUEST_SCHEMA_VERSION",
    "TIMELINE_ROUNDING_RULE",
    "TIMELINE_SCHEMA_VERSION_V2",
    "TIMELINE_TRACK_KINDS",
    "TIMELINE_TRACK_SCHEMA_VERSION",
    "TIMELINE_VERSION_SCHEMA_VERSION_V2",
    "AudioInputBinding",
    "CompositionResult",
    "MaskAssetVersionBinding",
    "PreviewCandidate",
    "PreviewArtifactError",
    "SubtitleManifest",
    "Timeline",
    "TimelineAuthorityError",
    "TimelineClip",
    "TimelineInputBundle",
    "TimelineMixRequest",
    "TimelinePreviewContractError",
    "TimelineRangeError",
    "TimelineSourceBindingError",
    "TimelineTrack",
    "TimelineTrackError",
    "TimelineVersion",
    "build_audio_input_binding",
    "build_composition_result",
    "build_mask_asset_version_binding",
    "build_preview_candidate",
    "build_subtitle_manifest",
    "build_timeline",
    "build_timeline_clip",
    "build_timeline_input_bundle",
    "build_timeline_mix_request",
    "build_timeline_track",
    "build_timeline_version",
    "map_frame_boundary_to_sample",
    "map_sample_boundary_to_frame",
    "project_timeline_mix_request",
    "validate_audio_input_binding",
    "validate_composition_result",
    "validate_mask_asset_version_binding",
    "validate_preview_candidate",
    "validate_subtitle_manifest",
    "validate_timeline",
    "validate_timeline_clip",
    "validate_timeline_input_bundle",
    "validate_timeline_mix_request",
    "validate_timeline_track",
    "validate_timeline_version",
]
