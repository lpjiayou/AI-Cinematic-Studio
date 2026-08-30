"""M12 immutable audio technical-validation contracts.

This module binds one already-validated audible ``AssetVersion`` to sealed V4
analysis evidence.  The resulting record is technical evidence only: it does
not create or mutate an AssetVersion, perform Admission, assign Timeline
positions, or grant publication authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Sequence

from services.v4_platform.audio_validation import (
    AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST,
    AUDIO_TECHNICAL_VALIDATOR_IDENTITY,
    AUDIO_TECHNICAL_VALIDATOR_VERSION,
    AudioTechnicalAnalysisEvidence,
    CLIPPING_THRESHOLD_ABS,
    PCM_CLIPPING_THRESHOLD,
    PCM_CONTENT_DIGEST_SPEC,
    SILENCE_MINIMUM_FRAME_COUNT,
)

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
    AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION,
    AudioCue,
    build_source_audio_timing_evidence,
    validate_audio_cue,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _required_ref,
)


AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION = (
    "v5.audio-technical-validation.v1"
)
AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION = (
    "v5.m12-audio-technical-validation.v2"
)
V4_AUDIO_TECHNICAL_ANALYSIS_SCHEMA_VERSION = (
    "v4.audio-technical-analysis-evidence.v1"
)
AUDIO_TECHNICAL_VALIDATION_STATE = "RECORDED"
AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE = "TECHNICAL_EVIDENCE_ONLY"
AUDIO_TECHNICAL_FAILURE_REASON = "CLIPPING_THRESHOLD_EXCEEDED"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL_3 = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{3}\Z")
_DECIMAL_9 = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{9}\Z")
_COMMON_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_COMMAND_FIELDS = frozenset(
    {
        "validationRef",
        "validationVersionRef",
        "version",
        "supersedesValidationVersionRef",
        "supersedesValidationVersionDigest",
        "createdBy",
        "createdAt",
    }
)
_DURATION_FIELDS = frozenset({"numerator", "denominator", "unit"})
_SILENCE_RANGE_FIELDS = frozenset(
    {"startSample", "endSampleExclusive"}
)
_SOURCE_TIMING_PROJECTION_FIELDS = frozenset(
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
_CUE_BINDING_FIELDS = frozenset(
    {"cueRef", "cueVersionRef", "cueDigest"}
)
_PCM_DIGEST_SPEC = deepcopy(PCM_CONTENT_DIGEST_SPEC)
_PCM_DIGEST_SPEC_FIELDS = frozenset(_PCM_DIGEST_SPEC)
_CLIPPING_THRESHOLD = deepcopy(PCM_CLIPPING_THRESHOLD)
_CLIPPING_THRESHOLD_FIELDS = frozenset(_CLIPPING_THRESHOLD)
_V4_ANALYSIS_FIELDS = frozenset(
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
_VALIDATION_FIELDS = frozenset(
    {
        "schemaVersion",
        *_COMMON_SCOPE_FIELDS,
        "validationRef",
        "validationVersionRef",
        "version",
        "supersedesValidationVersionRef",
        "supersedesValidationVersionDigest",
        "sourceAssetVersionType",
        "sourceAssetVersionRef",
        "sourceAssetVersionDigest",
        "sourceArtifactEvidenceRef",
        "sourceArtifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
        "sourceTimingEvidence",
        "audioCueBindings",
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
        "fileDigest",
        "pcmContentDigest",
        "pcmDigestSpec",
        "analysisParametersDigest",
        "validationState",
        "failureReasons",
        "validatorIdentity",
        "validatorVersion",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_PRE_ASSET_VALIDATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "validationKind",
        "workspaceRef",
        "productionRunRef",
        "validationRef",
        "validationVersionRef",
        "version",
        "supersedesValidationVersionRef",
        "supersedesValidationVersionDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "analysisEvidenceRef",
        "analysisEvidenceDigest",
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
        "fileDigest",
        "pcmContentDigest",
        "pcmDigestSpec",
        "analysisParametersDigest",
        "validationState",
        "failureReasons",
        "validatorIdentity",
        "validatorVersion",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_AUDIBLE_ASSET_TYPES = (
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
    AmbienceAssetVersion,
)
_ASSET_TYPE_NAMES = {
    DialogueAssetVersion: "DialogueAssetVersion",
    MusicAssetVersion: "MusicAssetVersion",
    SfxAssetVersion: "SfxAssetVersion",
    AmbienceAssetVersion: "AmbienceAssetVersion",
}
_FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "admissionRef",
        "admissionState",
        "assetAdmissionRef",
        "selected",
        "selectionRef",
        "timelineRef",
        "timelineVersionRef",
        "timelineClipRef",
        "timelineTrackRef",
        "timelineStartSample",
        "timelineEndSample",
        "timelineStartFrame",
        "timelineEndFrame",
        "publicationState",
        "publishedAt",
        "releaseRef",
        "episodeMasterRef",
    }
)


class AudioTechnicalValidationError(EpisodeProductionError):
    """Base error for the closed M12 audio technical-validation contract."""

    code = "audio_technical_validation_invalid"


class AudioTechnicalEvidenceBindingError(StaleInputError):
    """Raised when sealed V4 evidence does not bind the exact source bytes."""

    code = "audio_technical_evidence_binding_stale"


class AudioTechnicalCueBindingError(StaleInputError):
    """Raised when a Cue does not bind the exact validated source extent."""

    code = "audio_technical_cue_binding_stale"


def _reject_authority_fields(value: Any, label: str) -> None:
    if isinstance(value, Mapping) and set(value) & _FORBIDDEN_AUTHORITY_FIELDS:
        raise AudioTechnicalValidationError(
            f"{label} cannot contain Admission, Timeline, or publication fields"
        )


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    _reject_authority_fields(value, label)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AudioTechnicalValidationError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise AudioTechnicalValidationError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any,
    fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    result = _exact(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise AudioTechnicalEvidenceBindingError(
            f"{label} payloadDigest is invalid"
        )
    result["payloadDigest"] = supplied
    return result


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise AudioTechnicalValidationError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise AudioTechnicalValidationError(f"{field} is invalid") from exc


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AudioTechnicalValidationError(f"{field} is invalid")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 2**63 - 1,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise AudioTechnicalValidationError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AudioTechnicalValidationError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AudioTechnicalValidationError(f"{field} must include a timezone")
    return parsed


def _fixed_decimal(
    value: Any,
    field: str,
    *,
    places: int,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> str:
    pattern = _DECIMAL_3 if places == 3 else _DECIMAL_9
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise AudioTechnicalValidationError(f"{field} is invalid")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise AudioTechnicalValidationError(f"{field} is invalid") from exc
    if not number.is_finite():
        raise AudioTechnicalValidationError(f"{field} must be finite")
    if number == 0 and value.startswith("-"):
        raise AudioTechnicalValidationError(f"{field} is not canonical")
    if minimum is not None and number < minimum:
        raise AudioTechnicalValidationError(f"{field} is out of range")
    if maximum is not None and number > maximum:
        raise AudioTechnicalValidationError(f"{field} is out of range")
    return value


def _storage_key(value: Any) -> str:
    key = _text(value, "storageKey")
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
        raise AudioTechnicalValidationError("storageKey is invalid")
    return key


def _version_lineage_fields(command: Mapping[str, Any]) -> int:
    version = _integer(
        command["version"], "version", minimum=1, maximum=2**31 - 1
    )
    parent_ref = command["supersedesValidationVersionRef"]
    parent_digest = command["supersedesValidationVersionDigest"]
    if version == 1:
        if parent_ref is not None or parent_digest is not None:
            raise AudioTechnicalValidationError(
                "initial validation version cannot have a predecessor"
            )
    else:
        _ref(parent_ref, "supersedesValidationVersionRef")
        _sha256(parent_digest, "supersedesValidationVersionDigest")
    if parent_ref == command["validationVersionRef"]:
        raise AudioTechnicalValidationError(
            "AudioTechnicalValidation cannot supersede itself"
        )
    return version


def _validate_predecessor(
    value: Mapping[str, Any],
    *,
    predecessor_validation: Any,
    asset: Mapping[str, Any],
) -> None:
    version = _version_lineage_fields(value)
    if version == 1:
        if predecessor_validation is not None:
            raise AudioTechnicalValidationError(
                "initial validation version cannot receive a predecessor"
            )
        return
    if type(predecessor_validation) is not AudioTechnicalValidation:
        raise UpstreamNotReadyError(
            "versioned AudioTechnicalValidation requires its exact predecessor wrapper"
        )
    predecessor = _verify_sealed(
        predecessor_validation.as_dict(),
        _VALIDATION_FIELDS,
        "predecessor AudioTechnicalValidation",
    )
    _validate_command_identity(predecessor)
    if (
        predecessor["schemaVersion"]
        != AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION
        or predecessor["state"] != AUDIO_TECHNICAL_VALIDATION_STATE
        or predecessor["authorityState"]
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or predecessor["immutable"] is not True
        or predecessor["publicationAllowed"] is not False
    ):
        raise AudioTechnicalValidationError(
            "predecessor AudioTechnicalValidation lifecycle is invalid"
        )
    expected_asset = (
        asset["type"],
        asset["ref"],
        asset["digest"],
    )
    predecessor_asset = (
        predecessor["sourceAssetVersionType"],
        predecessor["sourceAssetVersionRef"],
        predecessor["sourceAssetVersionDigest"],
    )
    if (
        value["validationRef"] != predecessor["validationRef"]
        or version != predecessor["version"] + 1
        or value["supersedesValidationVersionRef"]
        != predecessor["validationVersionRef"]
        or value["supersedesValidationVersionDigest"]
        != predecessor["payloadDigest"]
        or predecessor_asset != expected_asset
        or any(
            predecessor[field] != asset["scope"][field]
            for field in _COMMON_SCOPE_FIELDS
        )
    ):
        raise AudioTechnicalEvidenceBindingError(
            "AudioTechnicalValidation predecessor binding is stale"
        )


def _asset_identity(source_asset_version: Any) -> dict[str, Any]:
    if type(source_asset_version) not in _AUDIBLE_ASSET_TYPES:
        raise UpstreamNotReadyError(
            "a fully validated audible Audio AssetVersion wrapper is required"
        )
    value = source_asset_version.as_dict()
    expected_type = _ASSET_TYPE_NAMES.get(type(source_asset_version))
    if expected_type is None:
        raise UpstreamNotReadyError(
            "the exact validated Audio AssetVersion wrapper type is required"
        )
    if value.get("assetVersionType") != expected_type:
        raise AudioTechnicalValidationError(
            "source AssetVersion wrapper type is inconsistent"
        )
    payload_digest = value.get("payloadDigest")
    body = deepcopy(value)
    body.pop("payloadDigest", None)
    if not isinstance(payload_digest, str) or payload_digest != _digest(body):
        raise AudioTechnicalEvidenceBindingError(
            "source AssetVersion payloadDigest is invalid"
        )
    # Non-speech PR-3 types have context-free public validators, so exercise
    # those full validators again instead of treating wrapper identity alone as
    # sufficient.  Dialogue validation requires the exact VoiceLock/VoiceAsset
    # and optional Consent context; its exact wrapper is therefore the retained
    # capability boundary, followed below by the public source-timing
    # projection over the exact V4 evidence.
    validator = {
        MusicAssetVersion: validate_music_asset_version,
        SfxAssetVersion: validate_sfx_asset_version,
        AmbienceAssetVersion: validate_ambience_asset_version,
    }.get(type(source_asset_version))
    if validator is not None and validator(value).as_dict() != value:
        raise AudioTechnicalEvidenceBindingError(
            "source AssetVersion public validation is inconsistent"
        )
    scope = {field: _ref(value.get(field), field) for field in _COMMON_SCOPE_FIELDS}
    artifact = value.get("artifact")
    if not isinstance(artifact, Mapping):
        raise AudioTechnicalValidationError("source audio artifact is invalid")
    return {
        "mapping": value,
        "scope": scope,
        "type": expected_type,
        "ref": _ref(value.get("assetVersionRef"), "assetVersionRef"),
        "digest": _sha256(payload_digest, "sourceAssetVersionDigest"),
        "artifact": deepcopy(dict(artifact)),
    }


def _validate_duration(
    value: Any,
    *,
    sample_count: int,
    sample_rate: int,
    label: str,
) -> dict[str, Any]:
    result = _exact(value, _DURATION_FIELDS, label)
    numerator = _integer(result["numerator"], f"{label}.numerator", minimum=1)
    denominator = _integer(
        result["denominator"], f"{label}.denominator", minimum=1
    )
    if result["unit"] != "SECONDS":
        raise AudioTechnicalValidationError(f"{label}.unit is invalid")
    supplied = Fraction(numerator, denominator)
    if numerator != supplied.numerator or denominator != supplied.denominator:
        raise AudioTechnicalValidationError(f"{label} is not reduced")
    if supplied != Fraction(sample_count, sample_rate):
        raise AudioTechnicalEvidenceBindingError(
            f"{label} does not match sampleCount/sampleRate"
        )
    return result


def _validate_silence_ranges(
    value: Any,
    *,
    sample_count: int,
) -> list[dict[str, int]]:
    if not isinstance(value, list):
        raise AudioTechnicalValidationError("silenceRanges is invalid")
    ranges: list[dict[str, int]] = []
    previous_end = 0
    for index, raw in enumerate(value):
        item = _exact(
            raw,
            _SILENCE_RANGE_FIELDS,
            f"silenceRanges[{index}]",
        )
        start = _integer(
            item["startSample"], f"silenceRanges[{index}].startSample"
        )
        end = _integer(
            item["endSampleExclusive"],
            f"silenceRanges[{index}].endSampleExclusive",
            minimum=1,
            maximum=sample_count,
        )
        if start >= end or (ranges and start <= previous_end):
            raise AudioTechnicalValidationError(
                "silenceRanges must be sorted, disjoint half-open ranges"
            )
        if end - start < SILENCE_MINIMUM_FRAME_COUNT:
            raise AudioTechnicalValidationError(
                "silenceRanges contains a range below the frozen minimum"
            )
        previous_end = end
        ranges.append({"startSample": start, "endSampleExclusive": end})
    return ranges


def _cue_bindings(
    audio_cues: Sequence[Any],
    *,
    asset: Mapping[str, Any],
    source_asset_version: Any,
    source_artifact_evidence: Mapping[str, Any],
    source_timing: Mapping[str, Any],
) -> list[dict[str, str]]:
    if isinstance(audio_cues, (str, bytes)) or not isinstance(
        audio_cues, Sequence
    ):
        raise AudioTechnicalCueBindingError(
            "audio_cues must be a sequence of AudioCue wrappers"
        )
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, cue_wrapper in enumerate(audio_cues):
        if type(cue_wrapper) is not AudioCue:
            raise AudioTechnicalCueBindingError(
                f"audio_cues[{index}] must be a validated AudioCue wrapper"
            )
        supplied_cue = cue_wrapper.as_dict()
        try:
            cue = validate_audio_cue(
                supplied_cue,
                source_asset_version=source_asset_version,
                source_artifact_evidence=source_artifact_evidence,
                source_timing_evidence=source_timing,
                expected_script_version_ref=source_artifact_evidence[
                    "scriptVersionRef"
                ],
                expected_script_version_digest=source_artifact_evidence[
                    "scriptVersionDigest"
                ],
            ).as_dict()
        except EpisodeProductionError as exc:
            raise AudioTechnicalCueBindingError(
                "AudioCue failed full public revalidation"
            ) from exc
        if cue != supplied_cue:
            raise AudioTechnicalCueBindingError(
                "AudioCue public validation changed its payload"
            )
        cue_scope = {field: cue.get(field) for field in _COMMON_SCOPE_FIELDS}
        if cue_scope != asset["scope"]:
            raise AudioTechnicalCueBindingError("AudioCue scope binding is stale")
        if (
            cue.get("assetVersionRef") != asset["ref"]
            or cue.get("assetVersionDigest") != asset["digest"]
            or cue.get("assetVersionType") != asset["type"]
        ):
            raise AudioTechnicalCueBindingError(
                "AudioCue AssetVersion binding is stale"
            )
        if cue.get("sourceTimingEvidence") != source_timing:
            raise AudioTechnicalCueBindingError(
                "AudioCue SourceAudioTimingEvidence binding is stale"
            )
        end = _integer(
            cue.get("sourceEndSample"),
            f"audio_cues[{index}].sourceEndSample",
            minimum=1,
        )
        if end > source_timing["sampleCount"]:
            raise AudioTechnicalCueBindingError(
                "AudioCue exceeds the analyzed source extent"
            )
        cue_version_ref = _ref(
            cue.get("cueVersionRef"), f"audio_cues[{index}].cueVersionRef"
        )
        if cue_version_ref in seen:
            raise AudioTechnicalCueBindingError(
                "audio_cues contains duplicate CueVersion refs"
            )
        seen.add(cue_version_ref)
        result.append(
            {
                "cueRef": _ref(cue.get("cueRef"), f"audio_cues[{index}].cueRef"),
                "cueVersionRef": cue_version_ref,
                "cueDigest": _sha256(
                    cue.get("payloadDigest"), f"audio_cues[{index}].cueDigest"
                ),
            }
        )
    return sorted(result, key=lambda item: item["cueVersionRef"])


def _validate_pcm_digest_spec(value: Any) -> dict[str, Any]:
    result = _exact(value, _PCM_DIGEST_SPEC_FIELDS, "pcmDigestSpec")
    if result != _PCM_DIGEST_SPEC:
        raise AudioTechnicalValidationError(
            "pcmDigestSpec is not the frozen canonical PCM profile"
        )
    return result


def _validate_clipping_threshold(value: Any) -> dict[str, Any]:
    result = _exact(
        value, _CLIPPING_THRESHOLD_FIELDS, "clippingThreshold"
    )
    if result != _CLIPPING_THRESHOLD:
        raise AudioTechnicalValidationError(
            "clippingThreshold is not the frozen PCM threshold"
        )
    return result


def _source_evidence_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioTechnicalValidationError(
            "source_artifact_evidence must be a sealed mapping"
        )
    return deepcopy(dict(value))


def _validate_v4_analysis_evidence(
    value: Any,
    *,
    asset: Mapping[str, Any],
    source_artifact_evidence: Mapping[str, Any],
    source_timing: Mapping[str, Any],
) -> dict[str, Any]:
    if type(value) is not AudioTechnicalAnalysisEvidence:
        raise UpstreamNotReadyError(
            "the exact validated V4 AudioTechnicalAnalysisEvidence wrapper is required"
        )
    evidence = _verify_sealed(
        value.as_dict(),
        _V4_ANALYSIS_FIELDS,
        "V4 AudioTechnicalAnalysisEvidence",
    )
    if (
        evidence["schemaVersion"]
        != V4_AUDIO_TECHNICAL_ANALYSIS_SCHEMA_VERSION
        or evidence["state"] != "TECHNICAL_ANALYSIS_COMPLETE"
        or evidence["publicationAllowed"] is not False
    ):
        raise AudioTechnicalValidationError(
            "V4 AudioTechnicalAnalysisEvidence lifecycle is invalid"
        )

    for field in (
        "analysisEvidenceRef",
        "sourceArtifactEvidenceRef",
        "artifactRef",
    ):
        _ref(evidence[field], field)
    for field in (
        "sourceArtifactEvidenceDigest",
        "fileDigest",
        "pcmContentDigest",
        "analysisParametersDigest",
    ):
        _sha256(evidence[field], field)
    _storage_key(evidence["storageKey"])
    _integer(evidence["byteSize"], "byteSize", minimum=1)

    source_aliases = {
        "sourceArtifactEvidenceRef": source_artifact_evidence.get(
            "artifactEvidenceRef"
        ),
        "sourceArtifactEvidenceDigest": source_artifact_evidence.get(
            "payloadDigest"
        ),
        "artifactRef": source_artifact_evidence.get("artifactRef"),
        "storageKey": source_artifact_evidence.get("storageKey"),
        "byteSize": source_artifact_evidence.get("byteSize"),
        "fileDigest": source_artifact_evidence.get("sha256"),
    }
    artifact = asset["artifact"]
    asset_aliases = {
        "sourceArtifactEvidenceRef": artifact.get("artifactEvidenceRef"),
        "sourceArtifactEvidenceDigest": artifact.get("artifactEvidenceDigest"),
        "artifactRef": artifact.get("artifactRef"),
        "storageKey": artifact.get("storageKey"),
        "byteSize": artifact.get("byteSize"),
        "fileDigest": artifact.get("fileDigest"),
    }
    if any(
        evidence.get(field) != expected
        for field, expected in source_aliases.items()
    ) or any(
        evidence.get(field) != expected
        for field, expected in asset_aliases.items()
    ):
        raise AudioTechnicalEvidenceBindingError(
            "V4 analysis artifact binding is stale"
        )
    analysis_ref_semantic = deepcopy(evidence)
    analysis_ref_semantic.pop("analysisEvidenceRef")
    analysis_ref_semantic.pop("payloadDigest")
    expected_analysis_ref = "audio-technical-analysis-evidence-" + _digest(
        analysis_ref_semantic
    )[:32]
    if evidence["analysisEvidenceRef"] != expected_analysis_ref:
        raise AudioTechnicalEvidenceBindingError(
            "V4 analysisEvidenceRef is stale"
        )

    probe = source_artifact_evidence.get("probe")
    if not isinstance(probe, Mapping):
        raise AudioTechnicalValidationError(
            "source artifact probe is unavailable"
        )
    sample_rate = _integer(
        evidence["sampleRate"],
        "sampleRate",
        minimum=8_000,
        maximum=384_000,
    )
    channel_count = _integer(
        evidence["channelCount"],
        "channelCount",
        minimum=1,
        maximum=32,
    )
    sample_count = _integer(
        evidence["sampleCount"], "sampleCount", minimum=1
    )
    channel_layout = _text(evidence["channelLayout"], "channelLayout")
    expected_layout = {1: "mono", 2: "stereo"}.get(channel_count)
    if expected_layout is None or channel_layout != expected_layout:
        raise AudioTechnicalValidationError(
            "channelLayout does not match channelCount"
        )
    technical_aliases = {
        "codec": probe.get("codec"),
        "container": probe.get("container"),
        "sampleRate": source_timing["sampleRate"],
        "channelCount": source_timing["channelCount"],
        "sampleCount": source_timing["sampleCount"],
    }
    if any(
        evidence.get(field) != expected
        for field, expected in technical_aliases.items()
    ):
        raise AudioTechnicalEvidenceBindingError(
            "V4 analysis technical aliases do not match source timing"
        )
    _text(evidence["codec"], "codec")
    _text(evidence["container"], "container")
    _validate_duration(
        evidence["duration"],
        sample_count=sample_count,
        sample_rate=sample_rate,
        label="V4 analysis duration",
    )

    _fixed_decimal(
        evidence["integratedLufs"],
        "integratedLufs",
        places=3,
        minimum=Decimal("-200"),
        maximum=Decimal("100"),
    )
    _fixed_decimal(
        evidence["loudnessRangeLra"],
        "loudnessRangeLra",
        places=3,
        minimum=Decimal("0"),
        maximum=Decimal("200"),
    )
    _fixed_decimal(
        evidence["truePeakDbtp"],
        "truePeakDbtp",
        places=3,
        minimum=Decimal("-200"),
        maximum=Decimal("100"),
    )
    if evidence["dcOffset"] is not None:
        _fixed_decimal(
            evidence["dcOffset"],
            "dcOffset",
            places=9,
            minimum=Decimal("-1"),
            maximum=Decimal("1"),
        )
    peak = _integer(
        evidence["maxSamplePeak"],
        "maxSamplePeak",
        maximum=32_768,
    )
    clipped_count = _integer(
        evidence["clippedSampleCount"],
        "clippedSampleCount",
        maximum=sample_count * channel_count,
    )
    if not isinstance(evidence["clippingDetected"], bool):
        raise AudioTechnicalValidationError("clippingDetected is invalid")
    clipping_detected = clipped_count > 0
    if (
        evidence["clippingDetected"] is not clipping_detected
        or (clipping_detected and peak < CLIPPING_THRESHOLD_ABS)
        or (not clipping_detected and peak >= CLIPPING_THRESHOLD_ABS)
    ):
        raise AudioTechnicalValidationError(
            "clipping measurements are inconsistent"
        )
    _validate_clipping_threshold(evidence["clippingThreshold"])
    evidence["silenceRanges"] = _validate_silence_ranges(
        evidence["silenceRanges"], sample_count=sample_count
    )
    _validate_pcm_digest_spec(evidence["pcmDigestSpec"])
    if (
        evidence["analysisParametersDigest"]
        != AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST
    ):
        raise AudioTechnicalValidationError(
            "V4 analysis parameters are not the frozen profile"
        )

    expected_state = "FAILED" if clipping_detected else "PASSED"
    expected_reasons = (
        [AUDIO_TECHNICAL_FAILURE_REASON] if clipping_detected else []
    )
    if (
        evidence["validationState"] != expected_state
        or evidence["failureReasons"] != expected_reasons
    ):
        raise AudioTechnicalValidationError(
            "V4 analysis validation outcome is inconsistent"
        )
    if (
        evidence["validatorIdentity"] != AUDIO_TECHNICAL_VALIDATOR_IDENTITY
        or evidence["validatorVersion"] != AUDIO_TECHNICAL_VALIDATOR_VERSION
    ):
        raise AudioTechnicalValidationError(
            "V4 analysis validator identity is unsupported"
        )
    ffmpeg_version = _text(evidence["ffmpegVersion"], "ffmpegVersion")
    ffprobe_version = _text(evidence["ffprobeVersion"], "ffprobeVersion")
    if (
        not ffmpeg_version.startswith("ffmpeg version ")
        or not ffprobe_version.startswith("ffprobe version ")
        or not re.search(r" \| sha256:[0-9a-f]{64}\Z", ffmpeg_version)
        or not re.search(r" \| sha256:[0-9a-f]{64}\Z", ffprobe_version)
    ):
        raise AudioTechnicalValidationError(
            "V4 analysis runtime versions are invalid"
        )
    return evidence


def _derived_projection(
    *,
    asset: Mapping[str, Any],
    source_timing: Mapping[str, Any],
    analysis: Mapping[str, Any],
    cue_bindings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        **asset["scope"],
        "sourceAssetVersionType": asset["type"],
        "sourceAssetVersionRef": asset["ref"],
        "sourceAssetVersionDigest": asset["digest"],
        "sourceArtifactEvidenceRef": analysis[
            "sourceArtifactEvidenceRef"
        ],
        "sourceArtifactEvidenceDigest": analysis[
            "sourceArtifactEvidenceDigest"
        ],
        "artifactRef": analysis["artifactRef"],
        "storageKey": analysis["storageKey"],
        "byteSize": analysis["byteSize"],
        "analysisEvidenceRef": analysis["analysisEvidenceRef"],
        "analysisEvidenceDigest": analysis["payloadDigest"],
        "sourceTimingEvidence": deepcopy(dict(source_timing)),
        "audioCueBindings": deepcopy(cue_bindings),
        "codec": analysis["codec"],
        "container": analysis["container"],
        "sampleRate": analysis["sampleRate"],
        "channelCount": analysis["channelCount"],
        "channelLayout": analysis["channelLayout"],
        "sampleCount": analysis["sampleCount"],
        "duration": deepcopy(analysis["duration"]),
        "integratedLufs": analysis["integratedLufs"],
        "loudnessRangeLra": analysis["loudnessRangeLra"],
        "truePeakDbtp": analysis["truePeakDbtp"],
        "maxSamplePeak": analysis["maxSamplePeak"],
        "silenceRanges": deepcopy(analysis["silenceRanges"]),
        "clippedSampleCount": analysis["clippedSampleCount"],
        "clippingThreshold": deepcopy(analysis["clippingThreshold"]),
        "clippingDetected": analysis["clippingDetected"],
        "dcOffset": analysis["dcOffset"],
        "fileDigest": analysis["fileDigest"],
        "pcmContentDigest": analysis["pcmContentDigest"],
        "pcmDigestSpec": deepcopy(analysis["pcmDigestSpec"]),
        "analysisParametersDigest": analysis["analysisParametersDigest"],
        "validationState": analysis["validationState"],
        "failureReasons": deepcopy(analysis["failureReasons"]),
        "validatorIdentity": analysis["validatorIdentity"],
        "validatorVersion": analysis["validatorVersion"],
    }


def _validate_command_identity(value: Mapping[str, Any]) -> None:
    _ref(value["validationRef"], "validationRef")
    _ref(value["validationVersionRef"], "validationVersionRef")
    _version_lineage_fields(value)
    _ref(value["createdBy"], "createdBy")
    _timestamp(value["createdAt"], "createdAt")


def validate_persisted_audio_technical_validation_evidence(
    value: Any,
    *,
    expected_scope: tuple[str, str, str, str, str],
    expected_source_ref: str,
    expected_source_digest: str,
) -> dict[str, Any]:
    """Read a persisted v1 technical fact without recreating its V4 inputs.

    This is a read-only evidence validator for repository resolvers.  It does
    not build a second authority and cannot be used to mint a validation: the
    complete, exact v1 payload must already be sealed in the evidence journal.
    """

    result = _verify_sealed(
        value,
        _VALIDATION_FIELDS,
        "persisted AudioTechnicalValidation",
    )
    if (
        not isinstance(expected_scope, tuple)
        or len(expected_scope) != len(_COMMON_SCOPE_FIELDS)
    ):
        raise AudioTechnicalValidationError(
            "expected_scope must contain the five audio scope refs"
        )
    scope = tuple(
        _ref(selected, field)
        for field, selected in zip(_COMMON_SCOPE_FIELDS, expected_scope)
    )
    selected_source_ref = _ref(expected_source_ref, "expected_source_ref")
    selected_source_digest = _sha256(
        expected_source_digest,
        "expected_source_digest",
    )
    _validate_command_identity(result)
    if (
        result["schemaVersion"] != AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION
        or tuple(result[field] for field in _COMMON_SCOPE_FIELDS) != scope
        or result["sourceAssetVersionRef"] != selected_source_ref
        or result["sourceAssetVersionDigest"] != selected_source_digest
        or result["sourceAssetVersionType"]
        not in {
            "DialogueAssetVersion",
            "MusicAssetVersion",
            "SfxAssetVersion",
            "AmbienceAssetVersion",
            # Read-only M12-C1 support for a pre-existing canonical human
            # source recording.  This discriminator binds the underlying
            # canonical AssetVersion ref/digest; it is not the derived
            # SourceVoiceRecordingAssetVersion projection and is intentionally
            # absent from the builder's audible wrapper types.
            "SourceRecordingCanonicalAssetVersion",
        }
        or result["state"] != AUDIO_TECHNICAL_VALIDATION_STATE
        or result["authorityState"]
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTechnicalEvidenceBindingError(
            "persisted AudioTechnicalValidation authority binding is stale"
        )

    for field in (
        "sourceArtifactEvidenceRef",
        "artifactRef",
        "analysisEvidenceRef",
    ):
        _ref(result[field], field)
    for field in (
        "sourceAssetVersionDigest",
        "sourceArtifactEvidenceDigest",
        "analysisEvidenceDigest",
        "fileDigest",
        "pcmContentDigest",
        "analysisParametersDigest",
    ):
        _sha256(result[field], field)
    _storage_key(result["storageKey"])
    _integer(result["byteSize"], "byteSize", minimum=1)

    sample_rate = _integer(
        result["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000
    )
    channel_count = _integer(
        result["channelCount"], "channelCount", minimum=1, maximum=32
    )
    sample_count = _integer(result["sampleCount"], "sampleCount", minimum=1)
    expected_layout = {1: "mono", 2: "stereo"}.get(channel_count)
    if expected_layout is None or result["channelLayout"] != expected_layout:
        raise AudioTechnicalValidationError(
            "persisted AudioTechnicalValidation channel layout is invalid"
        )
    if result["codec"] != "pcm_s16le" or result["container"] != "wav":
        raise AudioTechnicalValidationError(
            "persisted AudioTechnicalValidation format is unsupported"
        )
    _validate_duration(
        result["duration"],
        sample_count=sample_count,
        sample_rate=sample_rate,
        label="persisted AudioTechnicalValidation duration",
    )

    timing = _verify_sealed(
        result["sourceTimingEvidence"],
        _SOURCE_TIMING_PROJECTION_FIELDS,
        "persisted SourceAudioTimingEvidence",
    )
    if (
        timing["schemaVersion"]
        != AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION
        or timing["authorityState"] != "TECHNICAL_EVIDENCE_ONLY"
        or timing["sourceAssetVersionRef"] != selected_source_ref
        or timing["sourceAssetVersionDigest"] != selected_source_digest
        or timing["artifactEvidenceRef"]
        != result["sourceArtifactEvidenceRef"]
        or timing["artifactEvidenceDigest"]
        != result["sourceArtifactEvidenceDigest"]
        or timing["storageKey"] != result["storageKey"]
        or timing["fileDigest"] != result["fileDigest"]
        or timing["sampleRate"] != sample_rate
        or timing["channelCount"] != channel_count
        or timing["sampleCount"] != sample_count
    ):
        raise AudioTechnicalEvidenceBindingError(
            "persisted source timing projection is stale"
        )

    bindings = result["audioCueBindings"]
    if not isinstance(bindings, list):
        raise AudioTechnicalCueBindingError(
            "persisted AudioTechnicalValidation Cue bindings are invalid"
        )
    normalized_bindings: list[dict[str, str]] = []
    seen_cue_versions: set[str] = set()
    for index, raw in enumerate(bindings):
        item = _exact(
            raw,
            _CUE_BINDING_FIELDS,
            f"audioCueBindings[{index}]",
        )
        _ref(item["cueRef"], f"audioCueBindings[{index}].cueRef")
        version_ref = _ref(
            item["cueVersionRef"],
            f"audioCueBindings[{index}].cueVersionRef",
        )
        _sha256(item["cueDigest"], f"audioCueBindings[{index}].cueDigest")
        if version_ref in seen_cue_versions:
            raise AudioTechnicalCueBindingError(
                "persisted AudioTechnicalValidation has duplicate Cue bindings"
            )
        seen_cue_versions.add(version_ref)
        normalized_bindings.append(item)
    if bindings != sorted(
        normalized_bindings, key=lambda item: item["cueVersionRef"]
    ):
        raise AudioTechnicalCueBindingError(
            "persisted AudioTechnicalValidation Cue bindings are not canonical"
        )

    for field, places, minimum, maximum in (
        ("integratedLufs", 3, Decimal("-200"), Decimal("100")),
        ("loudnessRangeLra", 3, Decimal("0"), Decimal("200")),
        ("truePeakDbtp", 3, Decimal("-200"), Decimal("100")),
    ):
        _fixed_decimal(
            result[field],
            field,
            places=places,
            minimum=minimum,
            maximum=maximum,
        )
    if result["dcOffset"] is not None:
        _fixed_decimal(
            result["dcOffset"],
            "dcOffset",
            places=9,
            minimum=Decimal("-1"),
            maximum=Decimal("1"),
        )
    peak = _integer(
        result["maxSamplePeak"],
        "maxSamplePeak",
        maximum=32_768,
    )
    clipped_count = _integer(
        result["clippedSampleCount"],
        "clippedSampleCount",
        maximum=sample_count * channel_count,
    )
    if (
        result["validationState"] != "PASSED"
        or result["failureReasons"] != []
        or result["clippingDetected"] is not False
        or clipped_count != 0
        or peak >= CLIPPING_THRESHOLD_ABS
    ):
        raise AudioTechnicalValidationError(
            "persisted AudioTechnicalValidation did not pass"
        )
    _validate_silence_ranges(
        result["silenceRanges"], sample_count=sample_count
    )
    _validate_clipping_threshold(result["clippingThreshold"])
    _validate_pcm_digest_spec(result["pcmDigestSpec"])
    if (
        result["analysisParametersDigest"]
        != AUDIO_TECHNICAL_ANALYSIS_PARAMETERS_DIGEST
        or result["validatorIdentity"] != AUDIO_TECHNICAL_VALIDATOR_IDENTITY
        or result["validatorVersion"] != AUDIO_TECHNICAL_VALIDATOR_VERSION
    ):
        raise AudioTechnicalValidationError(
            "persisted AudioTechnicalValidation analysis identity is unsupported"
        )
    return result


def _validated_inputs(
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    v4_analysis_evidence: Any,
    audio_cues: Sequence[Any],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, str]],
]:
    asset = _asset_identity(source_asset_version)
    source_mapping = _source_evidence_mapping(source_artifact_evidence)
    source_timing = build_source_audio_timing_evidence(
        source_mapping,
        source_asset_version=source_asset_version,
    )
    analysis = _validate_v4_analysis_evidence(
        v4_analysis_evidence,
        asset=asset,
        source_artifact_evidence=source_mapping,
        source_timing=source_timing,
    )
    cue_bindings = _cue_bindings(
        audio_cues,
        asset=asset,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_mapping,
        source_timing=source_timing,
    )
    return asset, source_timing, analysis, cue_bindings


def _validated_pre_asset_inputs(
    *,
    generation_result: Any,
    artifact_evidence: Any,
    v4_analysis_evidence: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Validate generation evidence before any Audio AssetVersion exists."""

    from .audio_authority import _validated_v4_generation_evidence

    result, evidence = _validated_v4_generation_evidence(
        generation_result,
        artifact_evidence,
    )
    probe = evidence.get("probe")
    if not isinstance(probe, Mapping):
        raise AudioTechnicalValidationError(
            "pre-asset ArtifactEvidence probe is unavailable"
        )
    source_timing = {
        "sampleRate": evidence.get("sampleRate"),
        "channelCount": evidence.get("channels"),
        "sampleCount": probe.get("durationSamples"),
    }
    synthetic_asset = {
        "artifact": {
            "artifactEvidenceRef": evidence.get("artifactEvidenceRef"),
            "artifactEvidenceDigest": evidence.get("payloadDigest"),
            "artifactRef": evidence.get("artifactRef"),
            "storageKey": evidence.get("storageKey"),
            "byteSize": evidence.get("byteSize"),
            "fileDigest": evidence.get("sha256"),
        }
    }
    analysis = _validate_v4_analysis_evidence(
        v4_analysis_evidence,
        asset=synthetic_asset,
        source_artifact_evidence=evidence,
        source_timing=source_timing,
    )
    if (
        result["workspaceRef"] != evidence["workspaceRef"]
        or result["productionRunRef"] != evidence["productionRunRef"]
    ):
        raise AudioTechnicalEvidenceBindingError(
            "pre-asset generation scope is stale"
        )
    return result, evidence, analysis


def _pre_asset_projection(
    *,
    generation_result: Mapping[str, Any],
    artifact_evidence: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "validationKind": "PRE_ASSET_GENERATION_EVIDENCE",
        "workspaceRef": generation_result["workspaceRef"],
        "productionRunRef": generation_result["productionRunRef"],
        "generationRequestRef": generation_result["generationRequestRef"],
        "generationRequestVersionRef": generation_result[
            "generationRequestVersionRef"
        ],
        "generationRequestDigest": generation_result["generationRequestDigest"],
        "generationResultRef": generation_result["generationResultRef"],
        "generationResultDigest": generation_result["payloadDigest"],
        "artifactEvidenceRef": artifact_evidence["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact_evidence["payloadDigest"],
        "artifactRef": analysis["artifactRef"],
        "storageKey": analysis["storageKey"],
        "byteSize": analysis["byteSize"],
        "analysisEvidenceRef": analysis["analysisEvidenceRef"],
        "analysisEvidenceDigest": analysis["payloadDigest"],
        "codec": analysis["codec"],
        "container": analysis["container"],
        "sampleRate": analysis["sampleRate"],
        "channelCount": analysis["channelCount"],
        "channelLayout": analysis["channelLayout"],
        "sampleCount": analysis["sampleCount"],
        "duration": deepcopy(analysis["duration"]),
        "integratedLufs": analysis["integratedLufs"],
        "loudnessRangeLra": analysis["loudnessRangeLra"],
        "truePeakDbtp": analysis["truePeakDbtp"],
        "maxSamplePeak": analysis["maxSamplePeak"],
        "silenceRanges": deepcopy(analysis["silenceRanges"]),
        "clippedSampleCount": analysis["clippedSampleCount"],
        "clippingThreshold": deepcopy(analysis["clippingThreshold"]),
        "clippingDetected": analysis["clippingDetected"],
        "dcOffset": analysis["dcOffset"],
        "fileDigest": analysis["fileDigest"],
        "pcmContentDigest": analysis["pcmContentDigest"],
        "pcmDigestSpec": deepcopy(analysis["pcmDigestSpec"]),
        "analysisParametersDigest": analysis["analysisParametersDigest"],
        "validationState": analysis["validationState"],
        "failureReasons": deepcopy(analysis["failureReasons"]),
        "validatorIdentity": analysis["validatorIdentity"],
        "validatorVersion": analysis["validatorVersion"],
    }


def _validate_pre_asset_predecessor(
    value: Mapping[str, Any],
    *,
    predecessor_validation: Any,
    projection: Mapping[str, Any],
) -> None:
    version = _version_lineage_fields(value)
    if version == 1:
        if predecessor_validation is not None:
            raise AudioTechnicalValidationError(
                "initial pre-asset validation cannot receive a predecessor"
            )
        return
    if type(predecessor_validation) is not AudioTechnicalValidation:
        raise UpstreamNotReadyError(
            "pre-asset validation successor requires its exact predecessor wrapper"
        )
    predecessor = _verify_sealed(
        predecessor_validation.as_dict(),
        _PRE_ASSET_VALIDATION_FIELDS,
        "predecessor pre-asset AudioTechnicalValidation",
    )
    stable_fields = (
        "workspaceRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
    )
    if (
        predecessor["schemaVersion"]
        != AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION
        or predecessor["validationKind"] != "PRE_ASSET_GENERATION_EVIDENCE"
        or value["validationRef"] != predecessor["validationRef"]
        or version != predecessor["version"] + 1
        or value["supersedesValidationVersionRef"]
        != predecessor["validationVersionRef"]
        or value["supersedesValidationVersionDigest"]
        != predecessor["payloadDigest"]
        or any(predecessor[field] != projection[field] for field in stable_fields)
    ):
        raise AudioTechnicalEvidenceBindingError(
            "pre-asset AudioTechnicalValidation predecessor binding is stale"
        )


def _validate_pre_asset_audio_technical_validation(
    value: Any,
    *,
    generation_result: Any,
    artifact_evidence: Any,
    v4_analysis_evidence: Any,
    predecessor_validation: Any = None,
) -> dict[str, Any]:
    selected = _verify_sealed(
        value,
        _PRE_ASSET_VALIDATION_FIELDS,
        "pre-asset AudioTechnicalValidation",
    )
    if selected["schemaVersion"] != AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION:
        raise AudioTechnicalValidationError(
            "pre-asset AudioTechnicalValidation schema is unsupported"
        )
    _validate_command_identity(selected)
    generation, evidence, analysis = _validated_pre_asset_inputs(
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )
    projection = _pre_asset_projection(
        generation_result=generation,
        artifact_evidence=evidence,
        analysis=analysis,
    )
    _validate_pre_asset_predecessor(
        selected,
        predecessor_validation=predecessor_validation,
        projection=projection,
    )
    for field, expected in projection.items():
        if selected[field] != expected:
            raise AudioTechnicalEvidenceBindingError(
                f"pre-asset AudioTechnicalValidation {field} binding is stale"
            )
    if (
        selected["state"] != AUDIO_TECHNICAL_VALIDATION_STATE
        or selected["authorityState"]
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or selected["immutable"] is not True
        or selected["publicationAllowed"] is not False
    ):
        raise AudioTechnicalValidationError(
            "pre-asset AudioTechnicalValidation lifecycle is invalid"
        )
    return selected


def build_pre_asset_audio_technical_validation(
    command: Mapping[str, Any],
    *,
    generation_result: Any,
    artifact_evidence: Any,
    v4_analysis_evidence: Any,
    predecessor_validation: Any = None,
) -> dict[str, Any]:
    """Build the acyclic technical fact consumed by a new audio AssetVersion."""

    selected = _exact(
        command,
        _COMMAND_FIELDS,
        "pre-asset AudioTechnicalValidation command",
    )
    _validate_command_identity(selected)
    generation, evidence, analysis = _validated_pre_asset_inputs(
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
    )
    projection = _pre_asset_projection(
        generation_result=generation,
        artifact_evidence=evidence,
        analysis=analysis,
    )
    _validate_pre_asset_predecessor(
        selected,
        predecessor_validation=predecessor_validation,
        projection=projection,
    )
    result = _seal(
        {
            "schemaVersion": AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION,
            **selected,
            **projection,
            "state": AUDIO_TECHNICAL_VALIDATION_STATE,
            "authorityState": AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_pre_asset_audio_technical_validation(
        result,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        predecessor_validation=predecessor_validation,
    )


def validate_pre_asset_audio_technical_validation(
    value: Any,
    *,
    generation_result: Any,
    artifact_evidence: Any,
    v4_analysis_evidence: Any,
    predecessor_validation: Any = None,
) -> "AudioTechnicalValidation":
    return AudioTechnicalValidation.from_mapping(
        value,
        generation_result=generation_result,
        artifact_evidence=artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        predecessor_validation=predecessor_validation,
    )


def _validate_audio_technical_validation(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    v4_analysis_evidence: Any,
    audio_cues: Sequence[Any] = (),
    predecessor_validation: Any = None,
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _VALIDATION_FIELDS,
        "AudioTechnicalValidation",
    )
    if result["schemaVersion"] != AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION:
        raise AudioTechnicalValidationError(
            "AudioTechnicalValidation schema is unsupported"
        )
    _validate_command_identity(result)
    asset, source_timing, analysis, cue_bindings = _validated_inputs(
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        audio_cues=audio_cues,
    )
    expected = _derived_projection(
        asset=asset,
        source_timing=source_timing,
        analysis=analysis,
        cue_bindings=cue_bindings,
    )
    _validate_predecessor(
        result,
        predecessor_validation=predecessor_validation,
        asset=asset,
    )
    for field, expected_value in expected.items():
        if result[field] != expected_value:
            if field == "audioCueBindings":
                raise AudioTechnicalCueBindingError(
                    "AudioTechnicalValidation Cue bindings are stale"
                )
            raise AudioTechnicalEvidenceBindingError(
                f"AudioTechnicalValidation {field} binding is stale"
            )
    if (
        result["state"] != AUDIO_TECHNICAL_VALIDATION_STATE
        or result["authorityState"]
        != AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTechnicalValidationError(
            "AudioTechnicalValidation lifecycle is invalid"
        )
    return result


def build_audio_technical_validation(
    command: Mapping[str, Any],
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    v4_analysis_evidence: Any,
    audio_cues: Sequence[Any] = (),
    predecessor_validation: Any = None,
) -> dict[str, Any]:
    """Build a sealed technical-evidence record from validated upstream facts."""

    value = _exact(
        command,
        _COMMAND_FIELDS,
        "AudioTechnicalValidation command",
    )
    _validate_command_identity(value)
    asset, source_timing, analysis, cue_bindings = _validated_inputs(
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        audio_cues=audio_cues,
    )
    _validate_predecessor(
        value,
        predecessor_validation=predecessor_validation,
        asset=asset,
    )
    result = _seal(
        {
            "schemaVersion": AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION,
            **asset["scope"],
            **value,
            **_derived_projection(
                asset=asset,
                source_timing=source_timing,
                analysis=analysis,
                cue_bindings=cue_bindings,
            ),
            "state": AUDIO_TECHNICAL_VALIDATION_STATE,
            "authorityState": AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_audio_technical_validation(
        result,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        audio_cues=audio_cues,
        predecessor_validation=predecessor_validation,
    )


def validate_audio_technical_validation(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    v4_analysis_evidence: Any,
    audio_cues: Sequence[Any] = (),
    predecessor_validation: Any = None,
) -> "AudioTechnicalValidation":
    """Return an immutable wrapper only after every exact binding revalidates."""

    return AudioTechnicalValidation.from_mapping(
        value,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        v4_analysis_evidence=v4_analysis_evidence,
        audio_cues=audio_cues,
        predecessor_validation=predecessor_validation,
    )


@dataclass(frozen=True, slots=True, init=False)
class AudioTechnicalValidation:
    _payload_json: str

    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        source_asset_version: Any = None,
        source_artifact_evidence: Any = None,
        v4_analysis_evidence: Any,
        audio_cues: Sequence[Any] = (),
        predecessor_validation: Any = None,
        generation_result: Any = None,
        artifact_evidence: Any = None,
    ) -> "AudioTechnicalValidation":
        if (
            isinstance(value, Mapping)
            and value.get("schemaVersion")
            == AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION
        ):
            normalized = _validate_pre_asset_audio_technical_validation(
                value,
                generation_result=generation_result,
                artifact_evidence=artifact_evidence,
                v4_analysis_evidence=v4_analysis_evidence,
                predecessor_validation=predecessor_validation,
            )
        else:
            normalized = _validate_audio_technical_validation(
                value,
                source_asset_version=source_asset_version,
                source_artifact_evidence=source_artifact_evidence,
                v4_analysis_evidence=v4_analysis_evidence,
                audio_cues=audio_cues,
                predecessor_validation=predecessor_validation,
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


__all__ = [
    "AUDIO_TECHNICAL_FAILURE_REASON",
    "AUDIO_TECHNICAL_VALIDATION_AUTHORITY_STATE",
    "AUDIO_TECHNICAL_VALIDATION_SCHEMA_VERSION",
    "AUDIO_TECHNICAL_VALIDATION_V2_SCHEMA_VERSION",
    "AUDIO_TECHNICAL_VALIDATION_STATE",
    "V4_AUDIO_TECHNICAL_ANALYSIS_SCHEMA_VERSION",
    "AudioTechnicalCueBindingError",
    "AudioTechnicalEvidenceBindingError",
    "AudioTechnicalValidation",
    "AudioTechnicalValidationError",
    "build_audio_technical_validation",
    "build_pre_asset_audio_technical_validation",
    "validate_audio_technical_validation",
    "validate_persisted_audio_technical_validation_evidence",
    "validate_pre_asset_audio_technical_validation",
]
