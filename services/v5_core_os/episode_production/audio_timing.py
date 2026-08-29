"""M12 source-relative audio timing, stem, and premix candidate contracts.

The contracts in this module never assign final Timeline positions.  AudioCue
uses integer source samples as its authority, AudioStemSet groups immutable
source assets for preliminary mixing, and PreliminaryMixCandidate only binds V4
technical evidence.  Nothing here persists, admits, selects, or publishes an
AssetVersion.  Confidence values are integer basis points in the closed range
0..10000; floating-point confidence is intentionally excluded from the wire
contracts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
from math import gcd, isfinite
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from .audio_authority import (
    AmbienceAssetVersion,
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _required_ref,
)


AUDIO_CUE_SCHEMA_VERSION = "v5.audio-cue-version.v1"
AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION = (
    "v5.audio-source-timing-evidence-projection.v1"
)
AUDIO_TIMING_PROVENANCE_SCHEMA_VERSION = "v5.audio-timing-provenance.v1"
SUBTITLE_TIMING_REFERENCE_SCHEMA_VERSION = (
    "v5.subtitle-timing-reference.v1"
)
WORD_TIMING_SCHEMA_VERSION = "v5.audio-word-timing.v1"
PHONEME_TIMING_SCHEMA_VERSION = "v5.audio-phoneme-timing.v1"
AUDIO_STEM_MEMBER_SCHEMA_VERSION = "v5.audio-stem-member.v1"
AUDIO_STEM_SET_SCHEMA_VERSION = "v5.audio-stem-set-version.v1"
PRELIMINARY_MIX_CANDIDATE_SCHEMA_VERSION = (
    "v5.preliminary-mix-candidate.v1"
)

AUDIO_STEM_ROLES = frozenset(
    {"dialogue", "narration", "sfx", "ambience", "music"}
)
AUDIO_INTERVAL_SEMANTICS = "HALF_OPEN"
AUDIO_TIME_AUTHORITY = "INTEGER_SAMPLE_INDEX"
AUDIO_CUE_AUTHORITY_STATE = "CONTRACT_ONLY_SOURCE_TIMING_NOT_TIMELINE"
AUDIO_STEM_AUTHORITY_STATE = "CONTRACT_ONLY_SOURCE_GROUPING_NOT_TIMELINE"
PRELIMINARY_MIX_AUTHORITY_STATE = "CONTRACT_ONLY_NOT_ADMITTED"
PRELIMINARY_MIX_ADMISSION_STATE = "NOT_ADMITTED"
AUDIO_TIMELINE_BINDING_STATE = "UNASSIGNED"
PRELIMINARY_MIX_KIND = "PRELIMINARY"
PRELIMINARY_MIX_ADAPTER_ID = (
    "v4.deterministic-preliminary-ffmpeg-mix.v1"
)
PRELIMINARY_MIX_REQUEST_SCHEMA_VERSION = (
    "v4.preliminary-audio-mix-request.v1"
)

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
_SOURCE_REF_FIELDS = frozenset({"sourceRef", "sourceDigest"})
_RATIONAL_FIELDS = frozenset({"numerator", "denominator"})
_TIMEBASE_FIELDS = frozenset(
    {"unit", "ticksPerSecondNumerator", "ticksPerSecondDenominator"}
)
_TIMING_PROVENANCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "originKind",
        "producerIdentity",
        "recordRef",
        "parametersDigest",
        "sourceRefs",
        "authorityState",
        "payloadDigest",
    }
)
_SOURCE_TIMING_EVIDENCE_FIELDS = frozenset(
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
_SUBTITLE_FIELDS = frozenset(
    {
        "schemaVersion",
        "scriptVersionRef",
        "scriptVersionDigest",
        "language",
        "sourceText",
        "sourceTextDigest",
        "textOffsetUnit",
        "textRangeStart",
        "textRangeEndExclusive",
        "text",
        "textDigest",
        "payloadDigest",
    }
)
_SUBTITLE_COMMAND_FIELDS = _SUBTITLE_FIELDS - {
    "schemaVersion",
    "sourceTextDigest",
    "textOffsetUnit",
    "textDigest",
    "payloadDigest",
}
_WORD_TIMING_FIELDS = frozenset(
    {
        "schemaVersion",
        "wordRef",
        "text",
        "textDigest",
        "textRangeStart",
        "textRangeEndExclusive",
        "sourceStartSample",
        "sourceEndSample",
        "confidence",
        "payloadDigest",
    }
)
_WORD_TIMING_COMMAND_FIELDS = _WORD_TIMING_FIELDS - {
    "schemaVersion",
    "textDigest",
    "payloadDigest",
}
_PHONEME_TIMING_FIELDS = frozenset(
    {
        "schemaVersion",
        "phonemeRef",
        "wordRef",
        "symbol",
        "sourceStartSample",
        "sourceEndSample",
        "confidence",
        "payloadDigest",
    }
)
_PHONEME_TIMING_COMMAND_FIELDS = _PHONEME_TIMING_FIELDS - {
    "schemaVersion",
    "payloadDigest",
}
_AUDIO_CUE_FIELDS = frozenset(
    {
        "schemaVersion",
        *_COMMON_SCOPE_FIELDS,
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
_AUDIO_CUE_COMMAND_FIELDS = _AUDIO_CUE_FIELDS - {
    "schemaVersion",
    "sourceTimingEvidence",
    "sourceStartTime",
    "sourceEndTime",
    "timebase",
    "intervalSemantics",
    "timeAuthority",
    "state",
    "authorityState",
    "timelineBindingState",
    "immutable",
    "publicationAllowed",
    "payloadDigest",
}
_FORBIDDEN_DOWNSTREAM_FIELDS = frozenset(
    {
        "timelineRef",
        "timelineVersionRef",
        "timelineClipRef",
        "timelineTrackRef",
        "trackRef",
        "timelineStartSample",
        "timelineEndSample",
        "timelineStartFrame",
        "timelineEndFrame",
        "timelineEndFrameExclusive",
        "timelineStartTime",
        "timelineEndTime",
        "destinationStartSample",
        "destinationEndSample",
        "destinationStartFrame",
        "destinationEndFrameExclusive",
        "clipPosition",
        "sequencePosition",
        "finalTimelinePosition",
        "previewCandidateRef",
        "episodeMasterRef",
        "masterRef",
        "exportRef",
        "outputAssetVersionRef",
        "assetAdmissionRef",
    }
)
_AUDIBLE_ASSET_TYPES = frozenset(
    {
        "DialogueAssetVersion",
        "MusicAssetVersion",
        "SfxAssetVersion",
        "AmbienceAssetVersion",
    }
)
_AUDIBLE_ASSET_CONTRACT_TYPES = (
    DialogueAssetVersion,
    MusicAssetVersion,
    SfxAssetVersion,
    AmbienceAssetVersion,
)
_ASSET_TYPE_BY_ROLE = {
    "dialogue": "DialogueAssetVersion",
    "narration": "DialogueAssetVersion",
    "music": "MusicAssetVersion",
    "sfx": "SfxAssetVersion",
    "ambience": "AmbienceAssetVersion",
}
_AUDIO_KIND_BY_TYPE = {
    "DialogueAssetVersion": "dialogue",
    "MusicAssetVersion": "music",
    "SfxAssetVersion": "sfx",
    "AmbienceAssetVersion": "ambience",
}
_SCHEMA_BY_ASSET_TYPE = {
    "DialogueAssetVersion": "v5.dialogue-asset-version.v1",
    "MusicAssetVersion": "v5.music-asset-version.v1",
    "SfxAssetVersion": "v5.sfx-asset-version.v1",
    "AmbienceAssetVersion": "v5.ambience-asset-version.v1",
}
_SOURCE_ARTIFACT_FIELDS = frozenset(
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
_V4_AUDIO_PROBE_FIELDS = frozenset(
    {
        "sampleRate",
        "channels",
        "durationSeconds",
        "durationSamples",
        "codec",
        "container",
    }
)
_V4_PRELIMINARY_MIX_REQUEST_FIELDS = frozenset(
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
        "scriptSceneRef",
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
_V4_PRELIMINARY_MIX_CONTEXT_FIELDS = frozenset(
    {
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptSceneRef",
    }
)


class AudioTimingError(EpisodeProductionError):
    code = "audio_timing_invalid"


class AudioCueRangeError(AudioTimingError):
    code = "audio_cue_range_invalid"


class AudioCueScriptBindingError(StaleInputError):
    code = "audio_cue_script_binding_stale"


class AudioCueOverlapError(AudioTimingError):
    code = "audio_cue_overlap"


class AudioStemRoleError(AudioTimingError):
    code = "audio_stem_role_invalid"


class AudioFinalTimelineFieldRejectedError(AudioTimingError):
    code = "final_timeline_field_rejected"


def _reject_downstream_fields(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        forbidden = set(value) & _FORBIDDEN_DOWNSTREAM_FIELDS
        if forbidden:
            raise AudioFinalTimelineFieldRejectedError(
                f"{label} cannot contain final Timeline fields"
            )


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    _reject_downstream_fields(value, label)
    if not isinstance(value, Mapping) or set(value) != fields:
        raise AudioTimingError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise AudioTimingError("payloadDigest is derived")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    if isinstance(value, _ImmutableContract):
        value = value.as_dict()
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
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise AudioTimingError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise AudioTimingError(f"{field} is invalid") from exc


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AudioTimingError(f"{field} is invalid")
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
        raise AudioTimingError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AudioTimingError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AudioTimingError(f"{field} must include a timezone")
    return parsed


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(  # type: ignore[return-value]
        _ref(value[field], field)
        for field in (
            "workspaceRef",
            "projectRef",
            "seriesRef",
            "episodeRef",
            "productionRunRef",
        )
    )


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
            raise AudioTimingError("initial version cannot have a predecessor")
        return
    _ref(parent_ref, ref_field)
    _sha256(parent_digest, digest_field)


def _text_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _rational_mapping(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _rational(value: Any, field: str) -> Fraction:
    result = _exact(value, _RATIONAL_FIELDS, field)
    numerator = _integer(result["numerator"], f"{field}.numerator")
    denominator = _integer(
        result["denominator"], f"{field}.denominator", minimum=1
    )
    if numerator == 0:
        if denominator != 1:
            raise AudioTimingError(f"{field} is not canonical")
    elif gcd(numerator, denominator) != 1:
        raise AudioTimingError(f"{field} is not canonical")
    return Fraction(numerator, denominator)


def _timebase_mapping(sample_rate: int) -> dict[str, Any]:
    return {
        "unit": "AUDIO_SAMPLE",
        "ticksPerSecondNumerator": sample_rate,
        "ticksPerSecondDenominator": 1,
    }


def _timebase(value: Any, sample_rate: int) -> None:
    result = _exact(value, _TIMEBASE_FIELDS, "timebase")
    if (
        result["unit"] != "AUDIO_SAMPLE"
        or result["ticksPerSecondNumerator"] != sample_rate
        or result["ticksPerSecondDenominator"] != 1
    ):
        raise AudioTimingError("timebase is not the source sample clock")


def _confidence(value: Any, field: str) -> int:
    return _integer(value, field, maximum=10_000)


def _source_refs(value: Any, field: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AudioTimingError(f"{field} is invalid")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _exact(raw, _SOURCE_REF_FIELDS, f"{field}[{index}]")
        source_ref = _ref(item["sourceRef"], f"{field}[{index}].sourceRef")
        if source_ref in seen:
            raise AudioTimingError(f"{field} contains duplicate refs")
        seen.add(source_ref)
        result.append(
            {
                "sourceRef": source_ref,
                "sourceDigest": _sha256(
                    item["sourceDigest"], f"{field}[{index}].sourceDigest"
                ),
            }
        )
    return result


def _required_sources(
    provenance: Mapping[str, Any], required: set[tuple[str, str]]
) -> None:
    actual = {
        (item["sourceRef"], item["sourceDigest"])
        for item in provenance["sourceRefs"]
    }
    if not required.issubset(actual):
        raise StaleInputError("audio timing provenance source binding is stale")


def _validate_timing_provenance(
    value: Any,
    *,
    required_sources: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _TIMING_PROVENANCE_FIELDS, "AudioTimingProvenance"
    )
    if result["schemaVersion"] != AUDIO_TIMING_PROVENANCE_SCHEMA_VERSION:
        raise AudioTimingError("AudioTimingProvenance schema is unsupported")
    if result["originKind"] not in {
        "LOCAL_DETERMINISTIC_EXECUTION",
        "FORCED_ALIGNMENT",
        "MANUAL_ALIGNMENT",
        "IMPORTED_VERIFIED_TIMING",
    }:
        raise AudioTimingError("AudioTimingProvenance originKind is invalid")
    _text(result["producerIdentity"], "producerIdentity")
    _ref(result["recordRef"], "recordRef")
    _sha256(result["parametersDigest"], "parametersDigest")
    result["sourceRefs"] = _source_refs(result["sourceRefs"], "sourceRefs")
    if result["sourceRefs"] != sorted(
        result["sourceRefs"], key=lambda item: item["sourceRef"]
    ):
        raise AudioTimingError("AudioTimingProvenance sourceRefs are not canonical")
    if result["authorityState"] != "TECHNICAL_EVIDENCE_ONLY":
        raise AudioTimingError("audio timing provenance overclaims authority")
    if required_sources:
        _required_sources(result, required_sources)
    return result


def build_audio_timing_provenance(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _TIMING_PROVENANCE_FIELDS - {
        "schemaVersion",
        "authorityState",
        "payloadDigest",
    }
    value = _exact(command, fields, "AudioTimingProvenance command")
    value["sourceRefs"] = sorted(
        _source_refs(value["sourceRefs"], "sourceRefs"),
        key=lambda item: item["sourceRef"],
    )
    return _validate_timing_provenance(
        _seal(
            {
                "schemaVersion": AUDIO_TIMING_PROVENANCE_SCHEMA_VERSION,
                **value,
                "authorityState": "TECHNICAL_EVIDENCE_ONLY",
            }
        )
    )


def validate_audio_timing_provenance(value: Any) -> dict[str, Any]:
    return _validate_timing_provenance(value)


def _asset_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, _AUDIBLE_ASSET_CONTRACT_TYPES):
        raise UpstreamNotReadyError(
            "a fully validated explicit audio AssetVersion is required"
        )
    # The concrete PR-3 wrapper is the authority boundary: its constructor has
    # already performed the complete type-specific validation (including Voice,
    # Consent and Rights checks where applicable).  Accepting a detached mapping
    # here would let a caller shallow-reseal only the fields this module reads.
    asset = value.as_dict()
    asset_type = asset.get("assetVersionType")
    if (
        asset_type not in _AUDIBLE_ASSET_TYPES
        or asset.get("schemaVersion") != _SCHEMA_BY_ASSET_TYPE.get(asset_type)
        or asset.get("assetKind") != "audio"
        or asset.get("audioKind") != _AUDIO_KIND_BY_TYPE[asset_type]
        or asset.get("state") != "PROPOSED"
        or asset.get("authorityState") != "CONTRACT_ONLY_NOT_ADMITTED"
        or asset.get("immutable") is not True
        or asset.get("publicationAllowed") is not False
    ):
        raise AudioTimingError("source audio AssetVersion semantics are invalid")
    asset_ref = _ref(asset.get("assetVersionRef"), "assetVersionRef")
    artifact = asset.get("artifact")
    if not isinstance(artifact, Mapping) or set(artifact) != _SOURCE_ARTIFACT_FIELDS:
        raise AudioTimingError("source audio artifact is invalid")
    for field in (
        "artifactEvidenceRef",
        "artifactRef",
        "storageKey",
        "fileDigest",
        "byteSize",
    ):
        if field not in artifact:
            raise AudioTimingError("source audio artifact is incomplete")
    if (
        artifact.get("artifactKind") != "PCM_AUDIO"
        or artifact.get("mediaType") != "audio/wav"
    ):
        raise AudioTimingError("source audio artifact media contract is invalid")
    _storage_key(artifact.get("storageKey"))
    _ref(artifact["artifactEvidenceRef"], "artifact.artifactEvidenceRef")
    _sha256(
        artifact.get("artifactEvidenceDigest"),
        "artifact.artifactEvidenceDigest",
    )
    _ref(artifact["artifactRef"], "artifact.artifactRef")
    _sha256(artifact["fileDigest"], "artifact.fileDigest")
    _integer(artifact["byteSize"], "artifact.byteSize", minimum=1)
    rights = deepcopy(asset["rightsBinding"])
    if (
        rights.get("schemaVersion") != "v5.audio-rights-binding.v1"
        or rights.get("authorityState")
        != "EVIDENCE_BOUND_NOT_RIGHTS_DECISION"
    ):
        raise AudioTimingError("source RightsBinding semantics are invalid")
    rights_ref = _ref(rights.get("rightsBindingRef"), "rightsBindingRef")
    if asset_type == "DialogueAssetVersion":
        role = asset.get("speechRole")
        if role not in {"dialogue", "narration"}:
            raise AudioStemRoleError("DialogueAssetVersion speechRole is invalid")
        _ref(asset.get("scriptVersionRef"), "scriptVersionRef")
        _sha256(asset.get("scriptVersionDigest"), "scriptVersionDigest")
    else:
        role = _AUDIO_KIND_BY_TYPE[asset_type]
    return {
        "mapping": asset,
        "assetVersionRef": asset_ref,
        "assetVersionDigest": asset["payloadDigest"],
        "assetVersionType": asset_type,
        "role": role,
        "artifact": deepcopy(dict(artifact)),
        "rightsBindingRef": rights_ref,
        "rightsBindingDigest": rights["payloadDigest"],
        "scope": _scope(asset),
    }


def build_source_audio_timing_evidence(
    artifact_evidence: Any,
    *,
    source_asset_version: Any,
) -> dict[str, Any]:
    """Project verified V4 WAV evidence into an integer-sample extent pin."""

    asset = _asset_identity(source_asset_version)
    evidence = _verify_sealed(
        artifact_evidence,
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        "V4 audio artifact evidence",
    )
    probe = evidence.get("probe")
    if (
        evidence.get("schemaVersion") != "v4.audio-artifact-evidence.v1"
        or evidence.get("state") != "TECHNICALLY_VERIFIED"
        or evidence.get("publicationAllowed") is not False
        or evidence.get("provenance") != "LOCAL_EVIDENCE"
        or evidence.get("audioRole") != asset["role"]
        or not isinstance(probe, Mapping)
        or set(probe) != _V4_AUDIO_PROBE_FIELDS
        or probe.get("codec") != "pcm_s16le"
        or probe.get("container") != "wav"
    ):
        raise AudioTimingError("V4 audio timing evidence is invalid")
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
        _ref(evidence[field], field)
    for field in (
        "assetRequirementDigest",
        "generationRequestDigest",
        "executionRequestDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
        "sha256",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
    ):
        _sha256(evidence[field], field)
    _integer(evidence["byteSize"], "byteSize", minimum=1)
    _storage_key(evidence["storageKey"])
    artifact = asset["artifact"]
    aliases = {
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactRef": artifact["artifactRef"],
        "storageKey": artifact["storageKey"],
        "byteSize": artifact["byteSize"],
        "sha256": artifact["fileDigest"],
    }
    if any(
        evidence.get(field) != expected
        for field, expected in aliases.items()
    ):
        raise StaleInputError("V4 evidence does not match the source AssetVersion")
    if evidence["payloadDigest"] != artifact["artifactEvidenceDigest"]:
        raise StaleInputError(
            "V4 evidence digest does not match the source AssetVersion"
        )
    asset_mapping = asset["mapping"]
    lineage_aliases = {
        "workspaceRef": asset_mapping["workspaceRef"],
        "productionRunRef": asset_mapping["productionRunRef"],
        "assetRequirementRef": asset_mapping["assetRequirementRef"],
        "assetRequirementDigest": asset_mapping["assetRequirementDigest"],
        "generationRequestRef": asset_mapping["generationRequestRef"],
        "generationRequestVersionRef": asset_mapping[
            "generationRequestVersionRef"
        ],
        "generationRequestDigest": asset_mapping["generationRequestDigest"],
    }
    if asset["assetVersionType"] == "DialogueAssetVersion":
        lineage_aliases.update(
            {
                "scriptVersionRef": asset_mapping["scriptVersionRef"],
                "scriptVersionDigest": asset_mapping["scriptVersionDigest"],
            }
        )
    if any(
        evidence[field] != expected
        for field, expected in lineage_aliases.items()
    ):
        raise StaleInputError(
            "V4 evidence lineage does not match the source AssetVersion"
        )
    provenance = asset_mapping["provenance"]
    if (
        evidence["adapterIdentity"] != provenance["adapterIdentity"]
        or evidence["parametersDigest"] != provenance["parametersDigest"]
    ):
        raise StaleInputError(
            "V4 evidence provenance does not match the source AssetVersion"
        )
    sample_rate = _integer(
        probe.get("sampleRate"), "probe.sampleRate", minimum=8_000, maximum=384_000
    )
    channel_count = _integer(
        probe.get("channels"), "probe.channels", minimum=1, maximum=32
    )
    sample_count = _integer(
        probe.get("durationSamples"), "probe.durationSamples", minimum=1
    )
    if (
        evidence.get("sampleRate") != sample_rate
        or evidence.get("channels") != channel_count
    ):
        raise StaleInputError("V4 audio probe aliases are stale")
    duration_seconds = probe.get("durationSeconds")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not isfinite(float(duration_seconds))
        or duration_seconds <= 0
        or abs(float(duration_seconds) * sample_rate - sample_count) > 1
    ):
        raise AudioTimingError("V4 audio duration evidence is inconsistent")
    return _seal(
        {
            "schemaVersion": AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION,
            "sourceAssetVersionRef": asset["assetVersionRef"],
            "sourceAssetVersionDigest": asset["assetVersionDigest"],
            "artifactEvidenceRef": artifact["artifactEvidenceRef"],
            "artifactEvidenceDigest": artifact["artifactEvidenceDigest"],
            "storageKey": artifact["storageKey"],
            "fileDigest": artifact["fileDigest"],
            "sampleRate": sample_rate,
            "channelCount": channel_count,
            "sampleCount": sample_count,
            "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        }
    )


def _validate_source_timing_evidence(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SOURCE_TIMING_EVIDENCE_FIELDS,
        "SourceAudioTimingEvidence",
    )
    if (
        result["schemaVersion"]
        != AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION
        or result["authorityState"] != "TECHNICAL_EVIDENCE_ONLY"
    ):
        raise AudioTimingError("SourceAudioTimingEvidence semantics are invalid")
    expected = build_source_audio_timing_evidence(
        source_artifact_evidence,
        source_asset_version=source_asset_version,
    )
    if result != expected:
        raise StaleInputError("SourceAudioTimingEvidence projection is stale")
    return result


def validate_source_audio_timing_evidence(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
) -> dict[str, Any]:
    return _validate_source_timing_evidence(
        value,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
    )


def _build_subtitle_reference(value: Any) -> dict[str, Any]:
    result = _exact(
        value, _SUBTITLE_COMMAND_FIELDS, "SubtitleTimingReference command"
    )
    source_text = _text(result["sourceText"], "sourceText")
    text = _text(result["text"], "text")
    return _seal(
        {
            "schemaVersion": SUBTITLE_TIMING_REFERENCE_SCHEMA_VERSION,
            **result,
            "sourceTextDigest": _text_digest(source_text),
            "textOffsetUnit": "UNICODE_CODE_POINT",
            "textDigest": _text_digest(text),
        }
    )


def _validate_subtitle_reference(
    value: Any,
    *,
    script_version_ref: str,
    script_version_digest: str,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _SUBTITLE_FIELDS, "SubtitleTimingReference"
    )
    if result["schemaVersion"] != SUBTITLE_TIMING_REFERENCE_SCHEMA_VERSION:
        raise AudioTimingError("SubtitleTimingReference schema is unsupported")
    if (
        result["scriptVersionRef"] != script_version_ref
        or result["scriptVersionDigest"] != script_version_digest
    ):
        raise AudioCueScriptBindingError(
            "subtitle ScriptVersion binding is stale"
        )
    _ref(result["scriptVersionRef"], "scriptVersionRef")
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    _text(result["language"], "language")
    if result["textOffsetUnit"] != "UNICODE_CODE_POINT":
        raise AudioTimingError("subtitle text offset unit is invalid")
    source_text = _text(result["sourceText"], "sourceText")
    text = _text(result["text"], "text")
    if (
        result["sourceTextDigest"] != _text_digest(source_text)
        or result["textDigest"] != _text_digest(text)
    ):
        raise StaleInputError("subtitle text digest is stale")
    start = _integer(result["textRangeStart"], "textRangeStart")
    end = _integer(
        result["textRangeEndExclusive"], "textRangeEndExclusive", minimum=1
    )
    if start >= end or end > len(source_text) or source_text[start:end] != text:
        raise AudioCueScriptBindingError("subtitle text range binding is stale")
    return result


def _build_word_timing(value: Any) -> dict[str, Any]:
    result = _exact(value, _WORD_TIMING_COMMAND_FIELDS, "WordTiming command")
    text = _text(result["text"], "word text")
    return _seal(
        {
            "schemaVersion": WORD_TIMING_SCHEMA_VERSION,
            **result,
            "textDigest": _text_digest(text),
        }
    )


def _validate_word_timing(
    value: Any,
    *,
    cue_start: int,
    cue_end: int,
    subtitle: Mapping[str, Any],
) -> dict[str, Any]:
    result = _verify_sealed(value, _WORD_TIMING_FIELDS, "WordTiming")
    if result["schemaVersion"] != WORD_TIMING_SCHEMA_VERSION:
        raise AudioTimingError("WordTiming schema is unsupported")
    _ref(result["wordRef"], "wordRef")
    text = _text(result["text"], "word text")
    if result["textDigest"] != _text_digest(text):
        raise StaleInputError("word text digest is stale")
    text_start = _integer(result["textRangeStart"], "word.textRangeStart")
    text_end = _integer(
        result["textRangeEndExclusive"],
        "word.textRangeEndExclusive",
        minimum=1,
    )
    source_text = subtitle["sourceText"]
    if (
        text_start < subtitle["textRangeStart"]
        or text_end > subtitle["textRangeEndExclusive"]
        or text_start >= text_end
        or source_text[text_start:text_end] != text
    ):
        raise AudioCueScriptBindingError("word text range binding is stale")
    start = _integer(result["sourceStartSample"], "word.sourceStartSample")
    end = _integer(
        result["sourceEndSample"], "word.sourceEndSample", minimum=1
    )
    if start < cue_start or start >= end or end > cue_end:
        raise AudioCueRangeError("word sample range is outside its AudioCue")
    _confidence(result["confidence"], "word.confidence")
    return result


def _build_phoneme_timing(value: Any) -> dict[str, Any]:
    result = _exact(
        value, _PHONEME_TIMING_COMMAND_FIELDS, "PhonemeTiming command"
    )
    return _seal(
        {"schemaVersion": PHONEME_TIMING_SCHEMA_VERSION, **result}
    )


def _validate_phoneme_timing(
    value: Any, *, words: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    result = _verify_sealed(value, _PHONEME_TIMING_FIELDS, "PhonemeTiming")
    if result["schemaVersion"] != PHONEME_TIMING_SCHEMA_VERSION:
        raise AudioTimingError("PhonemeTiming schema is unsupported")
    _ref(result["phonemeRef"], "phonemeRef")
    word_ref = _ref(result["wordRef"], "wordRef")
    _text(result["symbol"], "symbol")
    word = words.get(word_ref)
    if word is None:
        raise AudioCueScriptBindingError("phoneme word binding is stale")
    start = _integer(result["sourceStartSample"], "phoneme.sourceStartSample")
    end = _integer(
        result["sourceEndSample"], "phoneme.sourceEndSample", minimum=1
    )
    if (
        start < word["sourceStartSample"]
        or start >= end
        or end > word["sourceEndSample"]
    ):
        raise AudioCueRangeError("phoneme range is outside its word")
    _confidence(
        result["confidence"], "phoneme.confidence"
    )
    return result


def _validate_audio_cue(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    result = _verify_sealed(value, _AUDIO_CUE_FIELDS, "AudioCue")
    if result["schemaVersion"] != AUDIO_CUE_SCHEMA_VERSION:
        raise AudioTimingError("AudioCue schema is unsupported")
    cue_scope = _scope(result)
    for field in ("cueRef", "cueVersionRef", "createdBy"):
        _ref(result[field], field)
    version = _integer(result["version"], "version", minimum=1)
    _parent(
        version,
        result["supersedesCueVersionRef"],
        result["supersedesCueVersionDigest"],
        ref_field="supersedesCueVersionRef",
        digest_field="supersedesCueVersionDigest",
    )
    if result["supersedesCueVersionRef"] == result["cueVersionRef"]:
        raise AudioTimingError("AudioCue cannot supersede itself")
    asset = _asset_identity(source_asset_version)
    evidence = _validate_source_timing_evidence(
        source_timing_evidence,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
    )
    artifact_evidence = _verify_sealed(
        source_artifact_evidence,
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        "V4 audio artifact evidence",
    )
    if result["sourceTimingEvidence"] != evidence:
        raise StaleInputError("AudioCue timing evidence binding is stale")
    if (
        cue_scope != asset["scope"]
        or result["assetVersionRef"] != asset["assetVersionRef"]
        or result["assetVersionDigest"] != asset["assetVersionDigest"]
        or result["assetVersionType"] != asset["assetVersionType"]
    ):
        raise StaleInputError("AudioCue AssetVersion binding is stale")
    if result["cueVersionRef"] in asset["mapping"].get(
        "sourceAudioCueRefs", []
    ):
        raise AudioTimingError("AudioCue cannot form a digest cycle with its asset")
    cue_role = result["cueRole"]
    if cue_role not in AUDIO_STEM_ROLES:
        raise AudioStemRoleError("AudioCue role is invalid")
    if (
        result["assetVersionType"] != _ASSET_TYPE_BY_ROLE[cue_role]
        or cue_role != asset["role"]
    ):
        raise AudioStemRoleError("AudioCue role does not match its AssetVersion")
    _ref(result["scriptVersionRef"], "scriptVersionRef")
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    if (
        result["scriptVersionRef"] != expected_script_version_ref
        or result["scriptVersionDigest"] != expected_script_version_digest
        or artifact_evidence["scriptVersionRef"]
        != expected_script_version_ref
        or artifact_evidence["scriptVersionDigest"]
        != expected_script_version_digest
    ):
        raise AudioCueScriptBindingError("AudioCue ScriptVersion binding is stale")
    if asset["assetVersionType"] == "DialogueAssetVersion" and (
        asset["mapping"]["scriptVersionRef"] != result["scriptVersionRef"]
        or asset["mapping"]["scriptVersionDigest"]
        != result["scriptVersionDigest"]
    ):
        raise AudioCueScriptBindingError(
            "AudioCue source asset ScriptVersion binding is stale"
        )
    start = _integer(result["sourceStartSample"], "sourceStartSample")
    end = _integer(result["sourceEndSample"], "sourceEndSample", minimum=1)
    if start >= end or end > evidence["sampleCount"]:
        raise AudioCueRangeError("AudioCue source range is invalid")
    sample_rate = evidence["sampleRate"]
    _timebase(result["timebase"], sample_rate)
    if (
        _rational(result["sourceStartTime"], "sourceStartTime")
        != Fraction(start, sample_rate)
        or _rational(result["sourceEndTime"], "sourceEndTime")
        != Fraction(end, sample_rate)
    ):
        raise AudioCueRangeError("AudioCue rational time does not match samples")
    if (
        result["intervalSemantics"] != AUDIO_INTERVAL_SEMANTICS
        or result["timeAuthority"] != AUDIO_TIME_AUTHORITY
    ):
        raise AudioCueRangeError("AudioCue time authority is invalid")
    dialogue_ref = result["dialogueRef"]
    narration_ref = result["narrationRef"]
    subtitle = result["subtitleTimingReference"]
    if cue_role == "dialogue":
        _ref(dialogue_ref, "dialogueRef")
        if narration_ref is not None or subtitle is None:
            raise AudioCueScriptBindingError("dialogue cue binding is invalid")
        if asset["mapping"].get("dialogueRef") != dialogue_ref:
            raise AudioCueScriptBindingError("dialogueRef binding is stale")
    elif cue_role == "narration":
        _ref(narration_ref, "narrationRef")
        if dialogue_ref is not None or subtitle is None:
            raise AudioCueScriptBindingError("narration cue binding is invalid")
        if asset["mapping"].get("narrationRef") != narration_ref:
            raise AudioCueScriptBindingError("narrationRef binding is stale")
    elif dialogue_ref is not None or narration_ref is not None or subtitle is not None:
        raise AudioCueScriptBindingError(
            "non-speech AudioCue cannot claim subtitle bindings"
        )
    if subtitle is None:
        subtitle_value = None
    else:
        subtitle_value = _validate_subtitle_reference(
            subtitle,
            script_version_ref=result["scriptVersionRef"],
            script_version_digest=result["scriptVersionDigest"],
        )
        speech = asset["mapping"]
        if (
            subtitle_value["language"] != speech["language"]
            or subtitle_value["sourceText"]
            != speech["normalizedSpeechParameters"]["text"]
        ):
            raise AudioCueScriptBindingError(
                "subtitle text does not match the speech AssetVersion"
            )
    raw_words = result["wordTimings"]
    if not isinstance(raw_words, list):
        raise AudioTimingError("wordTimings is invalid")
    if subtitle_value is None and raw_words:
        raise AudioCueScriptBindingError(
            "non-speech AudioCue cannot contain word timings"
        )
    words: list[dict[str, Any]] = []
    seen_word_refs: set[str] = set()
    previous_end: int | None = None
    previous_text_end: int | None = None
    for raw_word in raw_words:
        word = _validate_word_timing(
            raw_word,
            cue_start=start,
            cue_end=end,
            subtitle=subtitle_value,
        )
        if word["wordRef"] in seen_word_refs:
            raise AudioTimingError("wordTimings contains duplicate refs")
        if previous_end is not None and word["sourceStartSample"] < previous_end:
            raise AudioCueOverlapError("wordTimings overlap or are unordered")
        if (
            previous_text_end is not None
            and word["textRangeStart"] < previous_text_end
        ):
            raise AudioCueOverlapError(
                "wordTimings text ranges overlap or are unordered"
            )
        seen_word_refs.add(word["wordRef"])
        previous_end = word["sourceEndSample"]
        previous_text_end = word["textRangeEndExclusive"]
        words.append(word)
    raw_phonemes = result["phonemeTimings"]
    if not isinstance(raw_phonemes, list):
        raise AudioTimingError("phonemeTimings is invalid")
    word_by_ref = {item["wordRef"]: item for item in words}
    phonemes: list[dict[str, Any]] = []
    seen_phoneme_refs: set[str] = set()
    previous_by_word: dict[str, int] = {}
    for raw_phoneme in raw_phonemes:
        phoneme = _validate_phoneme_timing(
            raw_phoneme, words=word_by_ref
        )
        if phoneme["phonemeRef"] in seen_phoneme_refs:
            raise AudioTimingError("phonemeTimings contains duplicate refs")
        previous = previous_by_word.get(phoneme["wordRef"])
        if previous is not None and phoneme["sourceStartSample"] < previous:
            raise AudioCueOverlapError("phonemeTimings overlap or are unordered")
        seen_phoneme_refs.add(phoneme["phonemeRef"])
        previous_by_word[phoneme["wordRef"]] = phoneme["sourceEndSample"]
        phonemes.append(phoneme)
    _confidence(result["confidence"], "confidence")
    required_sources = {
        (asset["assetVersionRef"], asset["assetVersionDigest"]),
        (result["scriptVersionRef"], result["scriptVersionDigest"]),
        (evidence["artifactEvidenceRef"], evidence["artifactEvidenceDigest"]),
    }
    _validate_timing_provenance(
        result["provenance"], required_sources=required_sources
    )
    if (
        result["state"] != "PROPOSED"
        or result["authorityState"] != AUDIO_CUE_AUTHORITY_STATE
        or result["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTimingError("AudioCue lifecycle is invalid")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_audio_cue(
    command: Mapping[str, Any],
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    if not isinstance(command, Mapping):
        raise AudioTimingError("AudioCue command fields are invalid")
    normalized_command = deepcopy(dict(command))
    normalized_command.setdefault("phonemeTimings", [])
    value = _exact(
        normalized_command, _AUDIO_CUE_COMMAND_FIELDS, "AudioCue command"
    )
    evidence = _validate_source_timing_evidence(
        source_timing_evidence,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
    )
    subtitle = (
        None
        if value["subtitleTimingReference"] is None
        else _build_subtitle_reference(value["subtitleTimingReference"])
    )
    if not isinstance(value["wordTimings"], list) or not isinstance(
        value["phonemeTimings"], list
    ):
        raise AudioTimingError("AudioCue timing lists are invalid")
    start = _integer(value["sourceStartSample"], "sourceStartSample")
    end = _integer(value["sourceEndSample"], "sourceEndSample", minimum=1)
    result = _seal(
        {
            "schemaVersion": AUDIO_CUE_SCHEMA_VERSION,
            **value,
            "sourceStartTime": _rational_mapping(
                Fraction(start, evidence["sampleRate"])
            ),
            "sourceEndTime": _rational_mapping(
                Fraction(end, evidence["sampleRate"])
            ),
            "sourceTimingEvidence": evidence,
            "wordTimings": [
                _build_word_timing(item) for item in value["wordTimings"]
            ],
            "phonemeTimings": [
                _build_phoneme_timing(item)
                for item in value["phonemeTimings"]
            ],
            "subtitleTimingReference": subtitle,
            "timebase": _timebase_mapping(evidence["sampleRate"]),
            "intervalSemantics": AUDIO_INTERVAL_SEMANTICS,
            "timeAuthority": AUDIO_TIME_AUTHORITY,
            "state": "PROPOSED",
            "authorityState": AUDIO_CUE_AUTHORITY_STATE,
            "timelineBindingState": AUDIO_TIMELINE_BINDING_STATE,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_audio_cue(
        result,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
    )


def validate_audio_cue(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> "AudioCue":
    return AudioCue.from_mapping(
        value,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
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
_STEM_MEMBER_COMMAND_FIELDS = _STEM_MEMBER_FIELDS - {
    "schemaVersion",
    "sourceTimingEvidence",
    "timebase",
    "state",
    "authorityState",
    "timelineBindingState",
    "immutable",
    "publicationAllowed",
    "payloadDigest",
}
_STEM_SET_FIELDS = frozenset(
    {
        "schemaVersion",
        *_COMMON_SCOPE_FIELDS,
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
_STEM_SET_COMMAND_FIELDS = _STEM_SET_FIELDS - {
    "schemaVersion",
    "timebase",
    "state",
    "authorityState",
    "timelineBindingState",
    "immutable",
    "publicationAllowed",
    "payloadDigest",
}
_STEM_BINDING_FIELDS = frozenset({"stemMemberRef", "stemMemberDigest"})
_RIGHTS_BINDING_PIN_FIELDS = frozenset(
    {"rightsBindingRef", "rightsBindingDigest"}
)
_PRELIMINARY_MIX_FIELDS = frozenset(
    {
        "schemaVersion",
        *_COMMON_SCOPE_FIELDS,
        "candidateRef",
        "sourceStemSetRef",
        "sourceStemSetVersionRef",
        "sourceStemSetDigest",
        "sourceStemMembers",
        "sourceRightsBindings",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "executionRequestDigest",
        "generationResultRef",
        "generationResultDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "mediaType",
        "sampleRate",
        "channelCount",
        "durationSamples",
        "adapterIdentity",
        "mixParametersDigest",
        "provenance",
        "mixKind",
        "finalMix",
        "state",
        "authorityState",
        "admissionState",
        "timelineBindingState",
        "immutable",
        "publicationAllowed",
        "createdBy",
        "createdAt",
        "payloadDigest",
    }
)
_PRELIMINARY_MIX_COMMAND_FIELDS = frozenset(
    {"candidateRef", "provenance", "createdBy", "createdAt"}
)


def _nullable_cue_binding(value: Mapping[str, Any]) -> bool:
    values = (
        value["sourceCueRef"],
        value["sourceCueVersionRef"],
        value["sourceCueDigest"],
    )
    if all(item is None for item in values):
        return False
    if any(item is None for item in values):
        raise AudioTimingError("AudioStemMember cue binding is incomplete")
    return True


def _validate_stem_member(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    audio_cue: Any | None,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    result = _verify_sealed(value, _STEM_MEMBER_FIELDS, "AudioStemMember")
    if result["schemaVersion"] != AUDIO_STEM_MEMBER_SCHEMA_VERSION:
        raise AudioTimingError("AudioStemMember schema is unsupported")
    _ref(result["stemMemberRef"], "stemMemberRef")
    role = result["stemRole"]
    if role not in AUDIO_STEM_ROLES:
        raise AudioStemRoleError("AudioStemMember role is invalid")
    _ref(result["stemLaneRef"], "stemLaneRef")
    if result["overlapPolicy"] not in {"NON_OVERLAPPING", "ALLOW_OVERLAP"}:
        raise AudioTimingError("AudioStemMember overlapPolicy is invalid")
    asset = _asset_identity(source_asset_version)
    evidence = _validate_source_timing_evidence(
        source_timing_evidence,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
    )
    artifact_evidence = _verify_sealed(
        source_artifact_evidence,
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        "V4 audio artifact evidence",
    )
    if (
        artifact_evidence["scriptVersionRef"]
        != expected_script_version_ref
        or artifact_evidence["scriptVersionDigest"]
        != expected_script_version_digest
    ):
        raise AudioCueScriptBindingError(
            "AudioStemMember source ScriptVersion binding is stale"
        )
    if result["sourceTimingEvidence"] != evidence:
        raise StaleInputError("AudioStemMember timing evidence binding is stale")
    if (
        result["sourceAssetVersionRef"] != asset["assetVersionRef"]
        or result["sourceAssetVersionDigest"] != asset["assetVersionDigest"]
        or result["sourceAssetVersionType"] != asset["assetVersionType"]
    ):
        raise StaleInputError("AudioStemMember AssetVersion binding is stale")
    if (
        role != asset["role"]
        or result["sourceAssetVersionType"] != _ASSET_TYPE_BY_ROLE[role]
    ):
        raise AudioStemRoleError(
            "AudioStemMember role does not match its AssetVersion"
        )
    if (
        result["rightsBindingRef"] != asset["rightsBindingRef"]
        or result["rightsBindingDigest"] != asset["rightsBindingDigest"]
    ):
        raise StaleInputError("AudioStemMember RightsBinding pin is stale")
    source_start = _integer(
        result["sourceStartSample"], "sourceStartSample"
    )
    source_end = _integer(
        result["sourceEndSample"], "sourceEndSample", minimum=1
    )
    stem_start = _integer(result["stemStartSample"], "stemStartSample")
    stem_end = _integer(result["stemEndSample"], "stemEndSample", minimum=1)
    if (
        source_start >= source_end
        or source_end > evidence["sampleCount"]
        or stem_start >= stem_end
        or source_end - source_start != stem_end - stem_start
    ):
        raise AudioCueRangeError("AudioStemMember sample range is invalid")
    _timebase(result["timebase"], evidence["sampleRate"])
    has_cue = _nullable_cue_binding(result)
    required_sources = {
        (asset["assetVersionRef"], asset["assetVersionDigest"]),
        (evidence["artifactEvidenceRef"], evidence["artifactEvidenceDigest"]),
        (asset["rightsBindingRef"], asset["rightsBindingDigest"]),
    }
    if has_cue:
        if audio_cue is None:
            raise UpstreamNotReadyError("AudioStemMember requires its AudioCue")
        cue = _validate_audio_cue(
            audio_cue,
            source_asset_version=source_asset_version,
            source_artifact_evidence=source_artifact_evidence,
            source_timing_evidence=source_timing_evidence,
            expected_script_version_ref=expected_script_version_ref,
            expected_script_version_digest=expected_script_version_digest,
        )
        if (
            result["sourceCueRef"] != cue["cueRef"]
            or result["sourceCueVersionRef"] != cue["cueVersionRef"]
            or result["sourceCueDigest"] != cue["payloadDigest"]
            or result["sourceStartSample"] != cue["sourceStartSample"]
            or result["sourceEndSample"] != cue["sourceEndSample"]
            or result["stemRole"] != cue["cueRole"]
        ):
            raise StaleInputError("AudioStemMember AudioCue binding is stale")
        required_sources.add((cue["cueVersionRef"], cue["payloadDigest"]))
    elif audio_cue is not None:
        raise AudioTimingError("AudioStemMember has unexpected AudioCue context")
    _validate_timing_provenance(
        result["provenance"], required_sources=required_sources
    )
    if (
        result["state"] != "CONTRACT_ONLY"
        or result["authorityState"] != AUDIO_STEM_AUTHORITY_STATE
        or result["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTimingError("AudioStemMember lifecycle is invalid")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_audio_stem_member(
    command: Mapping[str, Any],
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    audio_cue: Any | None = None,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    value = _exact(
        command, _STEM_MEMBER_COMMAND_FIELDS, "AudioStemMember command"
    )
    evidence = _validate_source_timing_evidence(
        source_timing_evidence,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
    )
    result = _seal(
        {
            "schemaVersion": AUDIO_STEM_MEMBER_SCHEMA_VERSION,
            **value,
            "sourceTimingEvidence": evidence,
            "timebase": _timebase_mapping(evidence["sampleRate"]),
            "state": "CONTRACT_ONLY",
            "authorityState": AUDIO_STEM_AUTHORITY_STATE,
            "timelineBindingState": AUDIO_TIMELINE_BINDING_STATE,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_stem_member(
        result,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        audio_cue=audio_cue,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
    )


def validate_audio_stem_member(
    value: Any,
    *,
    source_asset_version: Any,
    source_artifact_evidence: Any,
    source_timing_evidence: Any,
    audio_cue: Any | None = None,
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> "AudioStemMember":
    return AudioStemMember.from_mapping(
        value,
        source_asset_version=source_asset_version,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        audio_cue=audio_cue,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
    )


def _member_sort_key(value: Any) -> tuple[Any, ...]:
    if isinstance(value, AudioStemMember):
        value = value.as_dict()
    if not isinstance(value, Mapping):
        raise AudioTimingError("AudioStemSet member is invalid")
    return (
        _ref(value.get("stemLaneRef"), "stemLaneRef"),
        _integer(value.get("stemStartSample"), "stemStartSample"),
        _integer(value.get("stemEndSample"), "stemEndSample", minimum=1),
        _ref(value.get("stemMemberRef"), "stemMemberRef"),
    )


def _validate_stem_set_shape(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _STEM_SET_FIELDS, "AudioStemSet")
    if result["schemaVersion"] != AUDIO_STEM_SET_SCHEMA_VERSION:
        raise AudioTimingError("AudioStemSet schema is unsupported")
    _scope(result)
    for field in (
        "stemSetRef",
        "stemSetVersionRef",
        "scriptVersionRef",
        "createdBy",
    ):
        _ref(result[field], field)
    _sha256(result["scriptVersionDigest"], "scriptVersionDigest")
    version = _integer(result["version"], "version", minimum=1)
    _parent(
        version,
        result["supersedesStemSetVersionRef"],
        result["supersedesStemSetVersionDigest"],
        ref_field="supersedesStemSetVersionRef",
        digest_field="supersedesStemSetVersionDigest",
    )
    if result["supersedesStemSetVersionRef"] == result["stemSetVersionRef"]:
        raise AudioTimingError("AudioStemSet cannot supersede itself")
    sample_rate = _integer(
        result["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000
    )
    duration = _integer(
        result["preliminaryDurationSamples"],
        "preliminaryDurationSamples",
        minimum=1,
    )
    _timebase(result["timebase"], sample_rate)
    raw_members = result["members"]
    if not isinstance(raw_members, list) or not raw_members or len(raw_members) > 64:
        raise AudioTimingError("AudioStemSet members are invalid")
    members = [
        _verify_sealed(item, _STEM_MEMBER_FIELDS, "AudioStemMember")
        for item in raw_members
    ]
    if members != sorted(members, key=_member_sort_key):
        raise AudioTimingError("AudioStemSet members are not canonical")
    member_refs = [item["stemMemberRef"] for item in members]
    if len(member_refs) != len(set(member_refs)):
        raise AudioTimingError("AudioStemSet contains duplicate members")
    lane_policies: dict[str, str] = {}
    lane_roles: dict[str, str] = {}
    lane_ranges: dict[str, list[tuple[int, int, str]]] = {}
    rights_digests: dict[str, str] = {}
    for member in members:
        if member["schemaVersion"] != AUDIO_STEM_MEMBER_SCHEMA_VERSION:
            raise AudioTimingError("AudioStemSet member schema is unsupported")
        evidence = _verify_sealed(
            member["sourceTimingEvidence"],
            _SOURCE_TIMING_EVIDENCE_FIELDS,
            "SourceAudioTimingEvidence",
        )
        role = member["stemRole"]
        if role not in AUDIO_STEM_ROLES:
            raise AudioStemRoleError("AudioStemSet member role is invalid")
        _ref(member["stemLaneRef"], "stemLaneRef")
        if member["overlapPolicy"] not in {
            "NON_OVERLAPPING",
            "ALLOW_OVERLAP",
        }:
            raise AudioTimingError("AudioStemSet member overlapPolicy is invalid")
        stem_start = _integer(member["stemStartSample"], "stemStartSample")
        stem_end = _integer(
            member["stemEndSample"], "stemEndSample", minimum=1
        )
        if stem_start >= stem_end:
            raise AudioCueRangeError("AudioStemMember stem range is invalid")
        if evidence["sampleRate"] != sample_rate:
            raise AudioTimingError("AudioStemSet sample rates are inconsistent")
        if stem_end > duration:
            raise AudioCueRangeError("AudioStemMember exceeds preliminary duration")
        lane = member["stemLaneRef"]
        policy = member["overlapPolicy"]
        previous_policy = lane_policies.setdefault(lane, policy)
        if previous_policy != policy:
            raise AudioTimingError("AudioStemSet lane policies are inconsistent")
        previous_role = lane_roles.setdefault(lane, role)
        if previous_role != role:
            raise AudioStemRoleError("AudioStemSet lane roles are inconsistent")
        rights_ref = _ref(member["rightsBindingRef"], "rightsBindingRef")
        rights_digest = _sha256(
            member["rightsBindingDigest"], "rightsBindingDigest"
        )
        previous_rights_digest = rights_digests.setdefault(
            rights_ref, rights_digest
        )
        if previous_rights_digest != rights_digest:
            raise StaleInputError(
                "AudioStemSet contains conflicting RightsBinding pins"
            )
        lane_ranges.setdefault(lane, []).append(
            (
                stem_start,
                stem_end,
                member["stemMemberRef"],
            )
        )
    for lane, ranges in lane_ranges.items():
        if lane_policies[lane] != "NON_OVERLAPPING":
            continue
        ordered = sorted(ranges)
        for previous, current in zip(ordered, ordered[1:]):
            if current[0] < previous[1] and previous[0] < current[1]:
                raise AudioCueOverlapError(
                    "AudioStemSet contains overlapping non-overlap lane cues"
                )
    required_sources = {
        (result["scriptVersionRef"], result["scriptVersionDigest"]),
        *{
            (item["stemMemberRef"], item["payloadDigest"])
            for item in members
        },
    }
    _validate_timing_provenance(
        result["provenance"], required_sources=required_sources
    )
    if (
        result["state"] != "CONTRACT_ONLY"
        or result["authorityState"] != AUDIO_STEM_AUTHORITY_STATE
        or result["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTimingError("AudioStemSet lifecycle is invalid")
    _timestamp(result["createdAt"], "createdAt")
    return result


def _context_item(
    values: Mapping[str, Any], key: str, label: str
) -> Any:
    try:
        value = values[key]
    except (KeyError, TypeError) as exc:
        raise UpstreamNotReadyError(f"{label} context is required") from exc
    return value


def _validate_audio_stem_set(
    value: Any,
    *,
    source_asset_versions: Mapping[str, Any],
    source_artifact_evidence: Mapping[str, Any],
    source_timing_evidence: Mapping[str, Any],
    audio_cues: Mapping[str, Any],
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    result = _validate_stem_set_shape(value)
    if (
        result["scriptVersionRef"] != expected_script_version_ref
        or result["scriptVersionDigest"] != expected_script_version_digest
    ):
        raise AudioCueScriptBindingError("AudioStemSet ScriptVersion binding is stale")
    scope = _scope(result)
    validated_members: list[dict[str, Any]] = []
    for member in result["members"]:
        asset = _context_item(
            source_asset_versions,
            member["sourceAssetVersionRef"],
            "source AssetVersion",
        )
        evidence = _context_item(
            source_timing_evidence,
            member["sourceAssetVersionRef"],
            "source timing evidence",
        )
        artifact_evidence = _context_item(
            source_artifact_evidence,
            member["sourceAssetVersionRef"],
            "source artifact evidence",
        )
        cue = None
        if member["sourceCueVersionRef"] is not None:
            cue = _context_item(
                audio_cues, member["sourceCueVersionRef"], "AudioCue"
            )
        validated = _validate_stem_member(
            member,
            source_asset_version=asset,
            source_artifact_evidence=artifact_evidence,
            source_timing_evidence=evidence,
            audio_cue=cue,
            expected_script_version_ref=expected_script_version_ref,
            expected_script_version_digest=expected_script_version_digest,
        )
        if _asset_identity(asset)["scope"] != scope:
            raise StaleInputError("AudioStemSet member scope is stale")
        validated_members.append(validated)
    result["members"] = validated_members
    return result


def build_audio_stem_set(
    command: Mapping[str, Any],
    *,
    source_asset_versions: Mapping[str, Any],
    source_artifact_evidence: Mapping[str, Any],
    source_timing_evidence: Mapping[str, Any],
    audio_cues: Mapping[str, Any],
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> dict[str, Any]:
    value = _exact(command, _STEM_SET_COMMAND_FIELDS, "AudioStemSet command")
    if not isinstance(value["members"], list):
        raise AudioTimingError("AudioStemSet members are invalid")
    sample_rate = _integer(
        value["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000
    )
    members = [
        item.as_dict() if isinstance(item, AudioStemMember) else deepcopy(item)
        for item in value["members"]
    ]
    members.sort(key=_member_sort_key)
    result = _seal(
        {
            "schemaVersion": AUDIO_STEM_SET_SCHEMA_VERSION,
            **value,
            "members": members,
            "timebase": _timebase_mapping(sample_rate),
            "state": "CONTRACT_ONLY",
            "authorityState": AUDIO_STEM_AUTHORITY_STATE,
            "timelineBindingState": AUDIO_TIMELINE_BINDING_STATE,
            "immutable": True,
            "publicationAllowed": False,
        }
    )
    return _validate_audio_stem_set(
        result,
        source_asset_versions=source_asset_versions,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        audio_cues=audio_cues,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
    )


def validate_audio_stem_set(
    value: Any,
    *,
    source_asset_versions: Mapping[str, Any],
    source_artifact_evidence: Mapping[str, Any],
    source_timing_evidence: Mapping[str, Any],
    audio_cues: Mapping[str, Any],
    expected_script_version_ref: str,
    expected_script_version_digest: str,
) -> "AudioStemSet":
    return AudioStemSet.from_mapping(
        value,
        source_asset_versions=source_asset_versions,
        source_artifact_evidence=source_artifact_evidence,
        source_timing_evidence=source_timing_evidence,
        audio_cues=audio_cues,
        expected_script_version_ref=expected_script_version_ref,
        expected_script_version_digest=expected_script_version_digest,
    )


def _validated_stem_set_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, AudioStemSet):
        raise UpstreamNotReadyError(
            "a fully validated immutable AudioStemSet is required"
        )
    return value.as_dict()


def build_preliminary_mix_execution_request(
    command: Mapping[str, Any],
    *,
    stem_set: Any,
) -> dict[str, Any]:
    """Project one validated StemSet into the frozen PR-2 V4 request."""

    context = _exact(
        command,
        _V4_PRELIMINARY_MIX_CONTEXT_FIELDS,
        "preliminary mix execution context",
    )
    stems = _validated_stem_set_contract(stem_set)
    parameters = _expected_v4_mix_parameters(stems)
    for field in (
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptSceneRef",
    ):
        _ref(context[field], field)
    _sha256(context["creativeShotDigest"], "creativeShotDigest")
    requirement_semantic = {
        "kind": "preliminaryAudioMixFromStemSet",
        "sourceStemSetVersionRef": stems["stemSetVersionRef"],
        "sourceStemSetDigest": stems["payloadDigest"],
        "mixParametersDigest": _digest(parameters),
    }
    requirement_digest = _digest(requirement_semantic)
    requirement_ref = (
        "m12-stem-premix-requirement-" + requirement_digest[:32]
    )
    request_semantic = {
        "assetRequirementDigest": requirement_digest,
        "sourceStemSetDigest": stems["payloadDigest"],
        "executionContext": context,
    }
    request_ref = "m12-stem-premix-request-" + _digest(request_semantic)[:32]
    return _seal(
        {
            "schemaVersion": PRELIMINARY_MIX_REQUEST_SCHEMA_VERSION,
            "workspaceRef": stems["workspaceRef"],
            "productionRunRef": stems["productionRunRef"],
            "generationRequestRef": request_ref,
            "generationRequestVersionRef": f"{request_ref}-v1",
            "assetRequirementRef": requirement_ref,
            "assetRequirementDigest": requirement_digest,
            "creativeShotRef": context["creativeShotRef"],
            "creativeShotVersionRef": context["creativeShotVersionRef"],
            "creativeShotDigest": context["creativeShotDigest"],
            "scriptRef": context["scriptRef"],
            "scriptVersionRef": stems["scriptVersionRef"],
            "scriptVersionDigest": stems["scriptVersionDigest"],
            "scriptSceneRef": context["scriptSceneRef"],
            "mediaKind": "audio",
            "mediaType": "audio/wav",
            "adapterCapability": PRELIMINARY_MIX_ADAPTER_ID,
            "parameters": parameters,
            "state": "LOCAL_EXECUTION_REQUEST",
            "requestedProvenance": "LOCAL_EVIDENCE",
            "publicationAllowed": False,
        }
    )


def _validated_v4_premix_request(
    value: Any, *, stem_set: Any
) -> dict[str, Any]:
    request = _verify_sealed(
        value,
        _V4_PRELIMINARY_MIX_REQUEST_FIELDS,
        "V4 preliminary mix execution request",
    )
    context = {
        field: request[field]
        for field in _V4_PRELIMINARY_MIX_CONTEXT_FIELDS
    }
    expected = build_preliminary_mix_execution_request(
        context, stem_set=stem_set
    )
    if request != expected:
        raise StaleInputError(
            "V4 preliminary mix request does not consume the exact StemSet"
        )
    return request


def _validated_v4_premix_evidence(
    value: Any,
    *,
    execution_request: Mapping[str, Any],
) -> dict[str, Any]:
    bundle = _verify_sealed(
        value,
        _V4_AUDIO_ARTIFACT_RESULT_FIELDS,
        "V4 preliminary mix artifact result",
    )
    generation_result = _verify_sealed(
        bundle["generationResult"],
        _V4_AUDIO_GENERATION_RESULT_FIELDS,
        "V4 audio GenerationResult",
    )
    evidence = _verify_sealed(
        bundle["artifactEvidence"],
        _V4_AUDIO_ARTIFACT_EVIDENCE_FIELDS,
        "V4 audio ArtifactEvidence",
    )
    if (
        bundle["schemaVersion"] != "v4.audio-artifact-result.v1"
        or generation_result["schemaVersion"]
        != "v4.audio-generation-result.v1"
        or evidence["schemaVersion"] != "v4.audio-artifact-evidence.v1"
        or generation_result["state"] != "SUCCEEDED"
        or evidence["state"] != "TECHNICALLY_VERIFIED"
    ):
        raise AudioTimingError("V4 preliminary mix evidence semantics are invalid")
    for layer in (bundle, generation_result, evidence):
        if (
            layer["adapterIdentity"] != PRELIMINARY_MIX_ADAPTER_ID
            or layer["provenance"] != "LOCAL_EVIDENCE"
            or layer["audioRole"] != "preliminary_mix"
            or layer["publicationAllowed"] is not False
        ):
            raise AudioTimingError(
                "V4 preliminary mix evidence authority is invalid"
            )
    for field in _V4_AUDIO_LINEAGE_FIELDS:
        expected = execution_request[field]
        if (
            bundle[field] != expected
            or generation_result[field] != expected
            or evidence[field] != expected
        ):
            raise StaleInputError(
                f"V4 preliminary mix {field} lineage is stale"
            )
    execution_digest = execution_request["payloadDigest"]
    parameters = execution_request["parameters"]
    parameters_digest = _digest(parameters)
    synthesis_spec_digest = _digest(
        {
            "adapterIdentity": PRELIMINARY_MIX_ADAPTER_ID,
            "parameters": parameters,
        }
    )
    for layer in (bundle, generation_result, evidence):
        if (
            layer["generationRequestDigest"] != execution_digest
            or layer["executionRequestDigest"] != execution_digest
            or layer["parametersDigest"] != parameters_digest
            or layer["effectiveParametersDigest"] != parameters_digest
            or layer["synthesisSpecDigest"] != synthesis_spec_digest
        ):
            raise StaleInputError(
                "V4 preliminary mix request digest binding is stale"
            )
    common_aliases = (
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
    )
    for field in common_aliases:
        if not (
            bundle[field] == generation_result[field] == evidence[field]
        ):
            raise StaleInputError(
                f"V4 preliminary mix {field} alias is stale"
            )
    if (
        bundle["generationResultRef"]
        != generation_result["generationResultRef"]
        or bundle["generationResultDigest"]
        != generation_result["payloadDigest"]
        or bundle["artifactEvidenceDigest"] != evidence["payloadDigest"]
        or generation_result["artifactEvidenceDigest"]
        != evidence["payloadDigest"]
    ):
        raise StaleInputError("V4 preliminary mix evidence lineage is stale")
    for field in (
        "generationResultRef",
        "artifactEvidenceRef",
        "artifactRef",
        "adapterIdentity",
    ):
        _ref(bundle[field], field)
    for field in (
        "generationResultDigest",
        "artifactEvidenceDigest",
        "sha256",
        "parametersDigest",
        "effectiveParametersDigest",
        "synthesisSpecDigest",
    ):
        _sha256(bundle[field], field)
    _integer(bundle["byteSize"], "byteSize", minimum=1)
    _storage_key(bundle["storageKey"])
    probe = _exact(bundle["probe"], _V4_AUDIO_PROBE_FIELDS, "audio probe")
    sample_rate = _integer(
        bundle["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000
    )
    channels = _integer(bundle["channels"], "channels", minimum=1, maximum=2)
    duration_samples = _integer(
        probe["durationSamples"], "durationSamples", minimum=1
    )
    duration_seconds = probe["durationSeconds"]
    if (
        probe["sampleRate"] != sample_rate
        or probe["channels"] != channels
        or probe["codec"] != "pcm_s16le"
        or probe["container"] != "wav"
        or isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not isfinite(float(duration_seconds))
        or duration_seconds <= 0
        or abs(float(duration_seconds) * sample_rate - duration_samples) > 1
        or sample_rate != parameters["sampleRate"]
        or channels != parameters["channels"]
        or duration_samples != parameters["durationSamples"]
    ):
        raise AudioTimingError("V4 preliminary mix probe is invalid")
    evidence_semantic = {
        "generationRequestDigest": execution_digest,
        "executionRequestDigest": execution_digest,
        "storageKey": bundle["storageKey"],
        "sha256": bundle["sha256"],
    }
    expected_evidence_ref = (
        "audio-artifact-evidence-" + _digest(evidence_semantic)[:32]
    )
    expected_artifact_ref = "audio-artifact-" + bundle["sha256"][:32]
    result_semantic = {
        "generationRequestDigest": execution_digest,
        "executionRequestDigest": execution_digest,
        "artifactEvidenceDigest": evidence["payloadDigest"],
    }
    expected_result_ref = (
        "audio-generation-result-" + _digest(result_semantic)[:32]
    )
    if (
        bundle["artifactEvidenceRef"] != expected_evidence_ref
        or bundle["artifactRef"] != expected_artifact_ref
        or bundle["generationResultRef"] != expected_result_ref
    ):
        raise StaleInputError("V4 preliminary mix deterministic refs are stale")
    return bundle


def _stem_bindings(stem_set: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "stemMemberRef": member["stemMemberRef"],
            "stemMemberDigest": member["payloadDigest"],
        }
        for member in stem_set["members"]
    ]


def _rights_bindings(stem_set: Mapping[str, Any]) -> list[dict[str, str]]:
    bindings = {
        (member["rightsBindingRef"], member["rightsBindingDigest"])
        for member in stem_set["members"]
    }
    return [
        {"rightsBindingRef": ref, "rightsBindingDigest": digest}
        for ref, digest in sorted(bindings)
    ]


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
        raise AudioTimingError("preliminary mix storageKey is invalid")
    return key


def _expected_v4_mix_parameters(stem_set: Mapping[str, Any]) -> dict[str, Any]:
    """Project the subset executable by the frozen PR-2 premix adapter."""

    duration = stem_set["preliminaryDurationSamples"]
    sample_rate = stem_set["sampleRate"]
    if sample_rate != 48_000 or duration > 48_000 * 600:
        raise UpstreamNotReadyError(
            "PRELIMINARY_MIX_FORMAT_EXECUTION_PENDING"
        )
    if len(stem_set["members"]) > 32:
        raise UpstreamNotReadyError(
            "PRELIMINARY_MIX_TRACK_LIMIT_EXCEEDED"
        )
    tracks: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    channel_count: int | None = None
    for member in stem_set["members"]:
        if member["stemRole"] == "music":
            raise UpstreamNotReadyError(
                "PRELIMINARY_MIX_MUSIC_PARAMETERS_PENDING"
            )
        evidence = member["sourceTimingEvidence"]
        asset_ref = member["sourceAssetVersionRef"]
        if asset_ref in seen_assets:
            raise UpstreamNotReadyError(
                "PRELIMINARY_MIX_STEM_PLACEMENT_EXECUTION_PENDING"
            )
        seen_assets.add(asset_ref)
        if (
            member["sourceStartSample"] != 0
            or member["sourceEndSample"] != duration
            or member["stemStartSample"] != 0
            or member["stemEndSample"] != duration
            or evidence["sampleCount"] != duration
            or evidence["sampleRate"] != sample_rate
        ):
            raise UpstreamNotReadyError(
                "PRELIMINARY_MIX_STEM_PLACEMENT_EXECUTION_PENDING"
            )
        if channel_count is None:
            channel_count = evidence["channelCount"]
        elif channel_count != evidence["channelCount"]:
            raise AudioTimingError(
                "preliminary mix stem channel layouts are inconsistent"
            )
        if evidence["channelCount"] not in {1, 2}:
            raise UpstreamNotReadyError(
                "PRELIMINARY_MIX_FORMAT_EXECUTION_PENDING"
            )
        tracks.append(
            {
                "audioRole": member["stemRole"],
                "assetVersionRef": asset_ref,
                "assetVersionDigest": member["sourceAssetVersionDigest"],
                "storageKey": evidence["storageKey"],
                "sha256": evidence["fileDigest"],
                "sampleRate": sample_rate,
                "channels": evidence["channelCount"],
                "durationSamples": duration,
            }
        )
    priority = {"dialogue": 3, "narration": 3, "sfx": 2, "ambience": 1}
    tracks.sort(
        key=lambda item: (-priority[item["audioRole"]], item["assetVersionRef"])
    )
    return {
        "mixKind": "preliminary",
        "sampleRate": sample_rate,
        "channels": channel_count,
        "durationSamples": duration,
        "tracks": tracks,
    }


def _validate_preliminary_mix_candidate(
    value: Any,
    *,
    stem_set: Any,
    v4_execution_request: Any,
    v4_artifact_result: Any,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _PRELIMINARY_MIX_FIELDS, "PreliminaryMixCandidate"
    )
    if result["schemaVersion"] != PRELIMINARY_MIX_CANDIDATE_SCHEMA_VERSION:
        raise AudioTimingError("PreliminaryMixCandidate schema is unsupported")
    stems = _validated_stem_set_contract(stem_set)
    execution_request = _validated_v4_premix_request(
        v4_execution_request, stem_set=stem_set
    )
    evidence = _validated_v4_premix_evidence(
        v4_artifact_result,
        execution_request=execution_request,
    )
    expected_mix_parameters = _expected_v4_mix_parameters(stems)
    if execution_request["parameters"] != expected_mix_parameters:
        raise StaleInputError(
            "V4 preliminary mix request does not consume the exact StemSet"
        )
    if (
        _scope(result) != _scope(stems)
        or result["sourceStemSetRef"] != stems["stemSetRef"]
        or result["sourceStemSetVersionRef"] != stems["stemSetVersionRef"]
        or result["sourceStemSetDigest"] != stems["payloadDigest"]
        or result["sourceStemMembers"] != _stem_bindings(stems)
        or result["sourceRightsBindings"] != _rights_bindings(stems)
    ):
        raise StaleInputError("PreliminaryMixCandidate StemSet binding is stale")
    evidence_fields = {
        "generationRequestRef": "generationRequestRef",
        "generationRequestVersionRef": "generationRequestVersionRef",
        "generationRequestDigest": "generationRequestDigest",
        "executionRequestDigest": "executionRequestDigest",
        "generationResultRef": "generationResultRef",
        "generationResultDigest": "generationResultDigest",
        "artifactEvidenceRef": "artifactEvidenceRef",
        "artifactEvidenceDigest": "artifactEvidenceDigest",
        "artifactRef": "artifactRef",
        "storageKey": "storageKey",
        "byteSize": "byteSize",
        "fileDigest": "sha256",
        "sampleRate": "sampleRate",
        "channelCount": "channels",
        "adapterIdentity": "adapterIdentity",
        "mixParametersDigest": "parametersDigest",
    }
    if any(
        result[target] != evidence[source]
        for target, source in evidence_fields.items()
    ):
        raise StaleInputError("PreliminaryMixCandidate V4 evidence binding is stale")
    if result["durationSamples"] != evidence["probe"]["durationSamples"]:
        raise StaleInputError("PreliminaryMixCandidate duration binding is stale")
    _storage_key(result["storageKey"])
    if (
        result["mediaType"] != "audio/wav"
        or result["sampleRate"] != stems["sampleRate"]
        or result["durationSamples"] != stems["preliminaryDurationSamples"]
    ):
        raise AudioTimingError("PreliminaryMixCandidate media contract is invalid")
    for index, item in enumerate(result["sourceStemMembers"]):
        _exact(item, _STEM_BINDING_FIELDS, f"sourceStemMembers[{index}]")
    for index, item in enumerate(result["sourceRightsBindings"]):
        _exact(
            item,
            _RIGHTS_BINDING_PIN_FIELDS,
            f"sourceRightsBindings[{index}]",
        )
    required_sources = {
        (stems["stemSetVersionRef"], stems["payloadDigest"]),
        (
            execution_request["generationRequestVersionRef"],
            execution_request["payloadDigest"],
        ),
        (result["generationResultRef"], result["generationResultDigest"]),
        (result["artifactEvidenceRef"], result["artifactEvidenceDigest"]),
    }
    provenance = _validate_timing_provenance(
        result["provenance"], required_sources=required_sources
    )
    if provenance["parametersDigest"] != result["mixParametersDigest"]:
        raise StaleInputError("PreliminaryMixCandidate parameters binding is stale")
    if (
        result["mixKind"] != PRELIMINARY_MIX_KIND
        or result["finalMix"] is not False
        or result["state"] != "TECHNICALLY_VERIFIED_CANDIDATE"
        or result["authorityState"] != PRELIMINARY_MIX_AUTHORITY_STATE
        or result["admissionState"] != PRELIMINARY_MIX_ADMISSION_STATE
        or result["timelineBindingState"] != AUDIO_TIMELINE_BINDING_STATE
        or result["immutable"] is not True
        or result["publicationAllowed"] is not False
    ):
        raise AudioTimingError("PreliminaryMixCandidate lifecycle is invalid")
    _ref(result["candidateRef"], "candidateRef")
    _ref(result["createdBy"], "createdBy")
    _timestamp(result["createdAt"], "createdAt")
    return result


def build_preliminary_mix_candidate(
    command: Mapping[str, Any],
    *,
    stem_set: Any,
    v4_execution_request: Any,
    v4_artifact_result: Any,
) -> dict[str, Any]:
    value = _exact(
        command,
        _PRELIMINARY_MIX_COMMAND_FIELDS,
        "PreliminaryMixCandidate command",
    )
    stems = _validated_stem_set_contract(stem_set)
    execution_request = _validated_v4_premix_request(
        v4_execution_request, stem_set=stem_set
    )
    evidence = _validated_v4_premix_evidence(
        v4_artifact_result,
        execution_request=execution_request,
    )
    result = _seal(
        {
            "schemaVersion": PRELIMINARY_MIX_CANDIDATE_SCHEMA_VERSION,
            **{field: stems[field] for field in _COMMON_SCOPE_FIELDS},
            "candidateRef": value["candidateRef"],
            "sourceStemSetRef": stems["stemSetRef"],
            "sourceStemSetVersionRef": stems["stemSetVersionRef"],
            "sourceStemSetDigest": stems["payloadDigest"],
            "sourceStemMembers": _stem_bindings(stems),
            "sourceRightsBindings": _rights_bindings(stems),
            "generationRequestRef": evidence["generationRequestRef"],
            "generationRequestVersionRef": evidence[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": evidence["generationRequestDigest"],
            "executionRequestDigest": evidence["executionRequestDigest"],
            "generationResultRef": evidence["generationResultRef"],
            "generationResultDigest": evidence["generationResultDigest"],
            "artifactEvidenceRef": evidence["artifactEvidenceRef"],
            "artifactEvidenceDigest": evidence["artifactEvidenceDigest"],
            "artifactRef": evidence["artifactRef"],
            "storageKey": evidence["storageKey"],
            "byteSize": evidence["byteSize"],
            "fileDigest": evidence["sha256"],
            "mediaType": "audio/wav",
            "sampleRate": evidence["sampleRate"],
            "channelCount": evidence["channels"],
            "durationSamples": evidence["probe"]["durationSamples"],
            "adapterIdentity": evidence["adapterIdentity"],
            "mixParametersDigest": evidence["parametersDigest"],
            "provenance": value["provenance"],
            "mixKind": PRELIMINARY_MIX_KIND,
            "finalMix": False,
            "state": "TECHNICALLY_VERIFIED_CANDIDATE",
            "authorityState": PRELIMINARY_MIX_AUTHORITY_STATE,
            "admissionState": PRELIMINARY_MIX_ADMISSION_STATE,
            "timelineBindingState": AUDIO_TIMELINE_BINDING_STATE,
            "immutable": True,
            "publicationAllowed": False,
            "createdBy": value["createdBy"],
            "createdAt": value["createdAt"],
        }
    )
    return _validate_preliminary_mix_candidate(
        result,
        stem_set=stem_set,
        v4_execution_request=v4_execution_request,
        v4_artifact_result=v4_artifact_result,
    )


def validate_preliminary_mix_candidate(
    value: Any,
    *,
    stem_set: Any,
    v4_execution_request: Any,
    v4_artifact_result: Any,
) -> "PreliminaryMixCandidate":
    return PreliminaryMixCandidate.from_mapping(
        value,
        stem_set=stem_set,
        v4_execution_request=v4_execution_request,
        v4_artifact_result=v4_artifact_result,
    )


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


class AudioCue(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any, **validation: Any) -> "AudioCue":
        return cls._from_validated(_validate_audio_cue(value, **validation))


class AudioStemMember(_ImmutableContract):
    @classmethod
    def from_mapping(
        cls, value: Any, **validation: Any
    ) -> "AudioStemMember":
        return cls._from_validated(_validate_stem_member(value, **validation))


class AudioStemSet(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any, **validation: Any) -> "AudioStemSet":
        return cls._from_validated(_validate_audio_stem_set(value, **validation))


class PreliminaryMixCandidate(_ImmutableContract):
    @classmethod
    def from_mapping(
        cls, value: Any, **validation: Any
    ) -> "PreliminaryMixCandidate":
        return cls._from_validated(
            _validate_preliminary_mix_candidate(value, **validation)
        )


__all__ = [
    "AUDIO_CUE_AUTHORITY_STATE",
    "AUDIO_CUE_SCHEMA_VERSION",
    "AUDIO_INTERVAL_SEMANTICS",
    "AUDIO_SOURCE_TIMING_EVIDENCE_SCHEMA_VERSION",
    "AUDIO_STEM_AUTHORITY_STATE",
    "AUDIO_STEM_MEMBER_SCHEMA_VERSION",
    "AUDIO_STEM_ROLES",
    "AUDIO_STEM_SET_SCHEMA_VERSION",
    "AUDIO_TIME_AUTHORITY",
    "AUDIO_TIMING_PROVENANCE_SCHEMA_VERSION",
    "PHONEME_TIMING_SCHEMA_VERSION",
    "PRELIMINARY_MIX_ADMISSION_STATE",
    "PRELIMINARY_MIX_AUTHORITY_STATE",
    "PRELIMINARY_MIX_CANDIDATE_SCHEMA_VERSION",
    "PRELIMINARY_MIX_KIND",
    "SUBTITLE_TIMING_REFERENCE_SCHEMA_VERSION",
    "AUDIO_TIMELINE_BINDING_STATE",
    "WORD_TIMING_SCHEMA_VERSION",
    "AudioCue",
    "AudioCueOverlapError",
    "AudioCueRangeError",
    "AudioCueScriptBindingError",
    "AudioStemMember",
    "AudioStemRoleError",
    "AudioStemSet",
    "AudioTimingError",
    "AudioFinalTimelineFieldRejectedError",
    "PreliminaryMixCandidate",
    "build_audio_cue",
    "build_audio_stem_member",
    "build_audio_stem_set",
    "build_audio_timing_provenance",
    "build_preliminary_mix_execution_request",
    "build_preliminary_mix_candidate",
    "build_source_audio_timing_evidence",
    "validate_audio_cue",
    "validate_audio_stem_member",
    "validate_audio_stem_set",
    "validate_audio_timing_provenance",
    "validate_preliminary_mix_candidate",
    "validate_source_audio_timing_evidence",
]
