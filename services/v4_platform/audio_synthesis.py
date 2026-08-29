"""Closed deterministic V4 audio synthesis for M12 PR-6.

The boundary projects one sealed V5 ``AudioGenerationRequest`` plus a sealed
execution context into a closed V4 request.  Execution always instantiates the
built-in pinned FFmpeg runtime; callers cannot inject adapters, commands,
filters, protocols, external samples, or output paths.

The emitted evidence closes four independently useful identities: the exact
recipe, the pinned runtime, the legacy-compatible V4 artifact evidence consumed
by the PR-5 analyzer, and the analyzer's canonical PCM content digest.  It does
not create an AssetVersion or make a music-quality decision.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any, Mapping, Sequence
import wave

from .audio_validation import (
    AudioTechnicalAnalysisEvidence,
    MAX_SOURCE_ARTIFACT_BYTES,
    analyze_audio_artifact,
)
from .local_audio_runtime import (
    BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
    FFMPEG_PROTOCOL_WHITELIST,
    LOCAL_AUDIO_RUNTIME_EVIDENCE_SCHEMA_VERSION,
    LocalAudioRuntimeError,
    _PinnedFfmpegAudioRuntime,
)


AUDIO_SYNTHESIS_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v4.audio-synthesis-execution-request.v2"
)
AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION = (
    "v4.audio-synthesis-execution-context.v1"
)
AUDIO_SYNTHESIS_EXECUTION_EVIDENCE_SCHEMA_VERSION = (
    "v4.audio-synthesis-execution-evidence.v1"
)
PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION = (
    "v4.programmatic-effect-synthesis-spec.v2"
)
PROCEDURAL_MUSIC_SYNTHESIS_SPEC_SCHEMA_VERSION = (
    "v4.procedural-music-synthesis-spec.v1"
)
AUDIO_SYNTHESIS_RECIPE_SCHEMA_VERSION = "v4.audio-synthesis-recipe.v1"
AUDIO_SYNTHESIS_COMMAND_SPEC_SCHEMA_VERSION = (
    "v4.audio-synthesis-command-spec.v1"
)

MUSIC_STRUCTURE_SCHEMA_VERSION = "v4.procedural-music-structure.v1"
MUSIC_SEQUENCE_SCHEMA_VERSION = "v4.procedural-music-sequence.v1"
MUSIC_INSTRUMENT_SCHEMA_VERSION = "v4.procedural-music-instrument.v1"
MUSIC_STEM_RECIPE_SCHEMA_VERSION = "v4.procedural-music-stem-recipe.v1"

SOURCE_AUDIO_GENERATION_REQUEST_SCHEMA_VERSION = "v5.audio-generation-request.v1"
SOURCE_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.audio-artifact-evidence.v1"
AUDIO_STORAGE_PREFIX = "asset-versions/audio/"

SAMPLE_RATE = 48_000
MAX_DURATION_SAMPLES = SAMPLE_RATE * 600
UINT32_MAX = (1 << 32) - 1
MUSIC_QUALITY_APPROVAL = "HUMAN_REQUIRED"

AMBIENCE_EFFECTS = frozenset({"rain", "wind", "room_tone"})
SFX_EFFECTS = frozenset(
    {
        "door_hinge",
        "footsteps",
        "paper",
        "clothing",
        "fire_crackle",
        "impact_transient",
    }
)
PROGRAMMATIC_EFFECT_ROLE = {
    **{effect: "ambience" for effect in AMBIENCE_EFFECTS},
    **{effect: "sfx" for effect in SFX_EFFECTS},
}
PROGRAMMATIC_EFFECTS = frozenset(PROGRAMMATIC_EFFECT_ROLE)

SUPPORTED_PROGRAMMATIC_REQUEST_KINDS = frozenset(
    {"AMBIENCE_GENERATION", "SFX_GENERATION", "MUSIC_GENERATION"}
)

_OUTPUT_TYPE_BY_REQUEST_KIND = {
    "AMBIENCE_GENERATION": "AmbienceAssetVersion",
    "SFX_GENERATION": "SfxAssetVersion",
    "MUSIC_GENERATION": "MusicAssetVersion",
}
_ROLE_BY_REQUEST_KIND = {
    "AMBIENCE_GENERATION": "ambience",
    "SFX_GENERATION": "sfx",
    "MUSIC_GENERATION": "music",
}

_EXECUTION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
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
        "requestKind",
        "outputAssetVersionType",
        "adapterCapability",
        "requestedProvenance",
        "storageKey",
        "synthesisSpec",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_EXECUTION_CONTEXT_FIELDS = frozenset(
    {
        "schemaVersion",
        "creativeShotRef",
        "creativeShotVersionRef",
        "creativeShotDigest",
        "scriptRef",
        "scriptVersionRef",
        "scriptVersionDigest",
        "storageKey",
        "synthesisSpec",
        "payloadDigest",
    }
)
_EXECUTION_CONTEXT_COMMAND_FIELDS = _EXECUTION_CONTEXT_FIELDS - {
    "schemaVersion",
    "payloadDigest",
}
_EFFECT_SPEC_FIELDS = frozenset(
    {
        "schemaVersion",
        "audioRole",
        "effectKind",
        "durationSamples",
        "sampleRate",
        "channels",
        "seed",
        "payloadDigest",
    }
)
_EFFECT_SPEC_COMMAND_FIELDS = _EFFECT_SPEC_FIELDS - {
    "schemaVersion",
    "payloadDigest",
}
_MUSIC_SPEC_FIELDS = frozenset(
    {
        "schemaVersion",
        "audioRole",
        "durationSamples",
        "sampleRate",
        "channels",
        "seed",
        "tempoBpm",
        "key",
        "mode",
        "structure",
        "sequence",
        "instrument",
        "stemRecipe",
        "musicQualityApproval",
        "payloadDigest",
    }
)
_MUSIC_SPEC_COMMAND_FIELDS = _MUSIC_SPEC_FIELDS - {
    "schemaVersion",
    "payloadDigest",
}
_MUSIC_STRUCTURE_FIELDS = frozenset(
    {"schemaVersion", "bars", "beatsPerBar", "sectionPattern"}
)
_MUSIC_SEQUENCE_FIELDS = frozenset(
    {"schemaVersion", "algorithm", "stepsPerBeat", "gatePermille"}
)
_MUSIC_INSTRUMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "synthesizer",
        "waveform",
        "attackSamples",
        "releaseSamples",
    }
)
_MUSIC_STEM_FIELDS = frozenset(
    {"schemaVersion", "availableStems", "outputStem"}
)
_SOURCE_GENERATION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "requestKind",
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
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
_SOURCE_REF_FIELDS = frozenset({"sourceRef", "sourceDigest"})
_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionEvidenceRef",
        "executionRequestRef",
        "executionRequestDigest",
        "generationRequestRef",
        "generationRequestVersionRef",
        "generationRequestDigest",
        "adapterIdentity",
        "audioRole",
        "effectKind",
        "recipe",
        "recipeDigest",
        "runtime",
        "runtimeDigest",
        "replayKey",
        "artifactEvidence",
        "technicalAnalysisEvidence",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_RECIPE_FIELDS = frozenset(
    {
        "schemaVersion",
        "recipeKind",
        "adapterIdentity",
        "audioRole",
        "effectKind",
        "synthesisSpec",
        "seedDomains",
        "derivedNoteSequence",
        "commandSpec",
        "publicationAllowed",
        "payloadDigest",
    }
)
_COMMAND_SPEC_FIELDS = frozenset(
    {
        "schemaVersion",
        "inputArguments",
        "filterComplex",
        "mapLabel",
        "outputSpec",
        "payloadDigest",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "schemaVersion",
        "engine",
        "adapterIdentity",
        "binarySha256",
        "version",
        "ffmpegBuildFingerprint",
        "cpuProfile",
        "determinismScope",
        "protocolWhitelist",
        "networkAccess",
        "environment",
        "threadCount",
        "filterThreadCount",
        "bitExact",
        "commandSpecDigest",
        "state",
        "payloadDigest",
    }
)
_CPU_PROFILE_FIELDS = frozenset(
    {"system", "machine", "release", "cpuFlags", "profileDigest"}
)

_FORBIDDEN_EXTERNAL_KEYS = frozenset(
    {
        "path",
        "filepath",
        "sourcepath",
        "inputpath",
        "outputpath",
        "file",
        "filename",
        "uri",
        "sourceuri",
        "inputuri",
        "url",
        "sourceurl",
        "inputurl",
        "sample",
        "samplefile",
        "samplelibrary",
        "externalsample",
        "library",
        "libraryref",
        "soundlibrary",
        "filter",
        "filtergraph",
        "filterchain",
        "plugin",
        "pluginref",
        "audiounit",
        "vst",
        "provider",
        "endpoint",
        "network",
    }
)

_MUSIC_KEYS = frozenset(
    {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
)
_MUSIC_MODES: dict[str, tuple[int, ...]] = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "natural_minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "pentatonic_major": (0, 2, 4, 7, 9),
}
_KEY_SEMITONE = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "D#": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "G#": 8,
    "A": 9,
    "A#": 10,
    "B": 11,
}

DEFAULT_MUSIC_STRUCTURE = {
    "schemaVersion": MUSIC_STRUCTURE_SCHEMA_VERSION,
    "bars": 4,
    "beatsPerBar": 4,
    "sectionPattern": ["A", "B", "A", "B"],
}
DEFAULT_MUSIC_SEQUENCE = {
    "schemaVersion": MUSIC_SEQUENCE_SCHEMA_VERSION,
    "algorithm": "SHA256_COUNTER_SCALE_WALK_V1",
    "stepsPerBeat": 2,
    "gatePermille": 820,
}
DEFAULT_MUSIC_INSTRUMENT = {
    "schemaVersion": MUSIC_INSTRUMENT_SCHEMA_VERSION,
    "synthesizer": "FFMPEG_AEVAL_ADDITIVE_V1",
    "waveform": "SINE",
    "attackSamples": 240,
    "releaseSamples": 1_440,
}
DEFAULT_MUSIC_STEM_RECIPE = {
    "schemaVersion": MUSIC_STEM_RECIPE_SCHEMA_VERSION,
    "availableStems": ["melody", "bass", "pulse"],
    "outputStem": "full_mix",
}


class AudioSynthesisError(RuntimeError):
    """Base error for the closed V4 audio-synthesis boundary."""


class AudioSynthesisRequestError(AudioSynthesisError):
    """A source, context, request, or closed recipe was invalid."""


class AudioSynthesisRuntimeError(AudioSynthesisError):
    """The built-in offline runtime could not complete execution."""


class AudioSynthesisArtifactError(AudioSynthesisError):
    """Output bytes or their evidence could not be trusted."""


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
        raise AudioSynthesisRequestError(
            "audio synthesis payload is not canonical JSON"
        ) from exc


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(_canonical(value)).hexdigest()


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise AudioSynthesisRequestError("audio synthesis payload is already sealed")
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(value: Any, fields: frozenset[str], field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioSynthesisRequestError(f"{field} must be an object")
    result = deepcopy(dict(value))
    if set(result) != fields:
        raise AudioSynthesisRequestError(f"{field} fields are invalid")
    claimed = result.pop("payloadDigest", None)
    if not _is_sha256(claimed) or claimed != _digest(result):
        raise AudioSynthesisRequestError(f"{field} payload digest is invalid")
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
        raise AudioSynthesisRequestError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise AudioSynthesisRequestError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise AudioSynthesisRequestError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> str:
    text_value = _text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AudioSynthesisRequestError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AudioSynthesisRequestError(f"{field} must include a timezone")
    return text_value


def _verify_rights_binding(
    value: Any,
    *,
    request_kind: str,
    asset_requirement_ref: str,
    asset_requirement_digest: str,
) -> dict[str, Any]:
    rights = _verify_sealed(value, _RIGHTS_BINDING_FIELDS, "rightsBinding")
    if (
        rights.get("schemaVersion") != "v5.audio-rights-binding.v1"
        or rights.get("authorityState")
        != "EVIDENCE_BOUND_NOT_RIGHTS_DECISION"
    ):
        raise AudioSynthesisRequestError("rightsBinding semantics are invalid")
    for field in (
        "rightsBindingRef",
        "rightsSource",
        "license",
        "ownership",
        "rightsManifestRef",
        "authorityEvidenceRef",
    ):
        _text(rights.get(field), f"rightsBinding.{field}")
    attribution = rights.get("attributionRequirement")
    if (
        not isinstance(attribution, str)
        or attribution != attribution.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in attribution)
    ):
        raise AudioSynthesisRequestError(
            "rightsBinding.attributionRequirement is invalid"
        )
    _integer(
        rights.get("rightsManifestVersion"),
        "rightsBinding.rightsManifestVersion",
        minimum=1,
        maximum=10_000,
    )
    for field in ("rightsManifestDigest", "authorityEvidenceDigest"):
        _sha256(rights.get(field), f"rightsBinding.{field}")
    usage_scope = rights.get("usageScope")
    if (
        not isinstance(usage_scope, list)
        or not usage_scope
        or len(usage_scope) != len(set(usage_scope))
    ):
        raise AudioSynthesisRequestError("rightsBinding.usageScope is invalid")
    for index, item in enumerate(usage_scope):
        _text(item, f"rightsBinding.usageScope[{index}]")
    required_use = {
        "MUSIC_GENERATION": "MUSIC_GENERATION",
        "SFX_GENERATION": "SFX_GENERATION",
        "AMBIENCE_GENERATION": "AMBIENCE_GENERATION",
    }[request_kind]
    if not {"AUDIO_PRODUCTION", required_use}.issubset(usage_scope):
        raise AudioSynthesisRequestError(
            "rightsBinding usageScope does not cover synthesis"
        )
    sources = rights.get("sourceRefs")
    if not isinstance(sources, list) or not sources:
        raise AudioSynthesisRequestError("rightsBinding.sourceRefs is invalid")
    normalized_sources: set[tuple[str, str]] = set()
    seen_refs: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or set(source) != _SOURCE_REF_FIELDS:
            raise AudioSynthesisRequestError(
                f"rightsBinding.sourceRefs[{index}] is invalid"
            )
        source_ref = _text(
            source.get("sourceRef"), f"rightsBinding.sourceRefs[{index}].sourceRef"
        )
        source_digest = _sha256(
            source.get("sourceDigest"),
            f"rightsBinding.sourceRefs[{index}].sourceDigest",
        )
        if source_ref in seen_refs:
            raise AudioSynthesisRequestError(
                "rightsBinding.sourceRefs contains duplicate refs"
            )
        seen_refs.add(source_ref)
        normalized_sources.add((source_ref, source_digest))
    required_sources = {
        (asset_requirement_ref, asset_requirement_digest),
        (rights["rightsManifestRef"], rights["rightsManifestDigest"]),
        (rights["authorityEvidenceRef"], rights["authorityEvidenceDigest"]),
    }
    if not required_sources.issubset(normalized_sources):
        raise AudioSynthesisRequestError(
            "rightsBinding authority or AssetRequirement coverage is stale"
        )
    if request_kind == "MUSIC_GENERATION" and (
        rights["rightsSource"] != "RIGHTS_MANIFEST_VERSION"
        or rights["license"] != "PROJECT_OWNED"
        or rights["ownership"] != "PROJECT_OWNER"
    ):
        raise AudioSynthesisRequestError(
            "programmatic music rights must be project-owned"
        )
    return rights


def _normalized_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _reject_external_controls(value: Any) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            if (
                isinstance(raw_key, str)
                and _normalized_key(raw_key) in _FORBIDDEN_EXTERNAL_KEYS
            ):
                raise AudioSynthesisRequestError(
                    "external sample, path, URL, library, filter, plugin, or provider is forbidden"
                )
            _reject_external_controls(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_external_controls(child)


def _storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith(AUDIO_STORAGE_PREFIX):
        raise AudioSynthesisRequestError("storageKey is invalid")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or "." in pure.parts
        or ".." in pure.parts
        or "//" in value
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or value.endswith("/")
        or pure.suffix.lower() != ".wav"
    ):
        raise AudioSynthesisRequestError("storageKey is invalid")
    return value


def _execution_request_ref(payload: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(payload))
    semantic.pop("payloadDigest", None)
    semantic.pop("executionRequestRef", None)
    return "audio-synthesis-execution-request-" + _digest(semantic)[:32]


def _execution_evidence_ref(payload: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(payload))
    semantic.pop("payloadDigest", None)
    semantic.pop("executionEvidenceRef", None)
    return "audio-synthesis-execution-evidence-" + _digest(semantic)[:32]


def _validate_effect_spec(value: Any) -> dict[str, Any]:
    spec = _verify_sealed(value, _EFFECT_SPEC_FIELDS, "effect synthesisSpec")
    if spec.get("schemaVersion") != PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION:
        raise AudioSynthesisRequestError("effect synthesisSpec schema is invalid")
    effect = spec.get("effectKind")
    if effect not in PROGRAMMATIC_EFFECTS:
        raise AudioSynthesisRequestError("effectKind is invalid")
    if spec.get("audioRole") != PROGRAMMATIC_EFFECT_ROLE[effect]:
        raise AudioSynthesisRequestError("effect role mapping is invalid")
    if spec.get("sampleRate") != SAMPLE_RATE:
        raise AudioSynthesisRequestError("effect sampleRate must be 48000")
    _integer(spec.get("channels"), "channels", minimum=1, maximum=2)
    minimum_duration = 2_400 if effect in {"paper", "impact_transient"} else 4_800
    _integer(
        spec.get("durationSamples"),
        "durationSamples",
        minimum=minimum_duration,
        maximum=MAX_DURATION_SAMPLES,
    )
    _integer(spec.get("seed"), "seed", minimum=0, maximum=UINT32_MAX)
    return spec


def _validate_music_structure(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MUSIC_STRUCTURE_FIELDS:
        raise AudioSynthesisRequestError("music structure fields are invalid")
    result = deepcopy(dict(value))
    if result.get("schemaVersion") != MUSIC_STRUCTURE_SCHEMA_VERSION:
        raise AudioSynthesisRequestError("music structure schema is invalid")
    bars = _integer(result.get("bars"), "structure.bars", minimum=1, maximum=64)
    _integer(
        result.get("beatsPerBar"),
        "structure.beatsPerBar",
        minimum=2,
        maximum=7,
    )
    pattern = result.get("sectionPattern")
    if (
        not isinstance(pattern, list)
        or len(pattern) != bars
        or any(item not in {"A", "B", "C", "D"} for item in pattern)
    ):
        raise AudioSynthesisRequestError("music sectionPattern is invalid")
    return result


def _validate_music_sequence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MUSIC_SEQUENCE_FIELDS:
        raise AudioSynthesisRequestError("music sequence fields are invalid")
    result = deepcopy(dict(value))
    if (
        result.get("schemaVersion") != MUSIC_SEQUENCE_SCHEMA_VERSION
        or result.get("algorithm") != "SHA256_COUNTER_SCALE_WALK_V1"
    ):
        raise AudioSynthesisRequestError("music sequence algorithm is invalid")
    _integer(
        result.get("stepsPerBeat"),
        "sequence.stepsPerBeat",
        minimum=1,
        maximum=4,
    )
    _integer(
        result.get("gatePermille"),
        "sequence.gatePermille",
        minimum=100,
        maximum=950,
    )
    return result


def _validate_music_instrument(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MUSIC_INSTRUMENT_FIELDS:
        raise AudioSynthesisRequestError("music instrument fields are invalid")
    result = deepcopy(dict(value))
    if (
        result.get("schemaVersion") != MUSIC_INSTRUMENT_SCHEMA_VERSION
        or result.get("synthesizer") != "FFMPEG_AEVAL_ADDITIVE_V1"
        or result.get("waveform") != "SINE"
    ):
        raise AudioSynthesisRequestError("music instrument recipe is invalid")
    _integer(
        result.get("attackSamples"),
        "instrument.attackSamples",
        minimum=1,
        maximum=4_800,
    )
    _integer(
        result.get("releaseSamples"),
        "instrument.releaseSamples",
        minimum=1,
        maximum=24_000,
    )
    return result


def _validate_music_stems(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _MUSIC_STEM_FIELDS:
        raise AudioSynthesisRequestError("music stemRecipe fields are invalid")
    result = deepcopy(dict(value))
    if (
        result.get("schemaVersion") != MUSIC_STEM_RECIPE_SCHEMA_VERSION
        or result.get("availableStems") != ["melody", "bass", "pulse"]
        or result.get("outputStem")
        not in {"melody", "bass", "pulse", "full_mix"}
    ):
        raise AudioSynthesisRequestError("music stemRecipe is invalid")
    return result


def _validate_music_spec(value: Any) -> dict[str, Any]:
    spec = _verify_sealed(value, _MUSIC_SPEC_FIELDS, "music synthesisSpec")
    if (
        spec.get("schemaVersion") != PROCEDURAL_MUSIC_SYNTHESIS_SPEC_SCHEMA_VERSION
        or spec.get("audioRole") != "music"
        or spec.get("sampleRate") != SAMPLE_RATE
        or spec.get("musicQualityApproval") != MUSIC_QUALITY_APPROVAL
    ):
        raise AudioSynthesisRequestError("music synthesisSpec semantics are invalid")
    _integer(
        spec.get("durationSamples"),
        "durationSamples",
        minimum=4_800,
        maximum=MAX_DURATION_SAMPLES,
    )
    if spec.get("channels") != 2:
        raise AudioSynthesisRequestError("procedural music channels must be stereo")
    _integer(spec.get("seed"), "seed", minimum=0, maximum=UINT32_MAX)
    _integer(spec.get("tempoBpm"), "tempoBpm", minimum=40, maximum=240)
    if spec.get("key") not in _MUSIC_KEYS or spec.get("mode") not in _MUSIC_MODES:
        raise AudioSynthesisRequestError("music key or mode is invalid")
    spec["structure"] = _validate_music_structure(spec.get("structure"))
    spec["sequence"] = _validate_music_sequence(spec.get("sequence"))
    spec["instrument"] = _validate_music_instrument(spec.get("instrument"))
    spec["stemRecipe"] = _validate_music_stems(spec.get("stemRecipe"))
    return spec


def _validate_synthesis_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AudioSynthesisRequestError("synthesisSpec must be an object")
    schema = value.get("schemaVersion")
    if schema == PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION:
        return _validate_effect_spec(value)
    if schema == PROCEDURAL_MUSIC_SYNTHESIS_SPEC_SCHEMA_VERSION:
        return _validate_music_spec(value)
    raise AudioSynthesisRequestError("synthesisSpec schema is unsupported")


def build_programmatic_effect_synthesis_spec(
    command: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(command, Mapping) or set(command) != _EFFECT_SPEC_COMMAND_FIELDS:
        raise AudioSynthesisRequestError("effect synthesisSpec command fields are invalid")
    _reject_external_controls(command)
    return _validate_effect_spec(
        _sealed(
            {
                "schemaVersion": PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION,
                **deepcopy(dict(command)),
            }
        )
    )


def build_procedural_music_synthesis_spec(
    command: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(command, Mapping) or set(command) != _MUSIC_SPEC_COMMAND_FIELDS:
        raise AudioSynthesisRequestError("music synthesisSpec command fields are invalid")
    _reject_external_controls(command)
    return _validate_music_spec(
        _sealed(
            {
                "schemaVersion": PROCEDURAL_MUSIC_SYNTHESIS_SPEC_SCHEMA_VERSION,
                **deepcopy(dict(command)),
            }
        )
    )


def _verify_requested_provenance(
    value: Any, *, asset_requirement_ref: str, asset_requirement_digest: str
) -> dict[str, Any]:
    provenance = _verify_sealed(
        value, _REQUESTED_PROVENANCE_FIELDS, "requestedProvenance"
    )
    if (
        provenance.get("schemaVersion") != "v5.audio-requested-provenance.v1"
        or provenance.get("originKind") != "LOCAL_DETERMINISTIC_EXECUTION"
        or provenance.get("adapterIdentity") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
    ):
        raise AudioSynthesisRequestError("requestedProvenance semantics are invalid")
    _sha256(provenance.get("parametersDigest"), "requestedProvenance.parametersDigest")
    sources = provenance.get("sourceRefs")
    if not isinstance(sources, list) or not sources:
        raise AudioSynthesisRequestError("requestedProvenance sourceRefs are invalid")
    covered = False
    seen_refs: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping) or set(source) != _SOURCE_REF_FIELDS:
            raise AudioSynthesisRequestError(
                f"requestedProvenance.sourceRefs[{index}] is invalid"
            )
        source_ref = _text(source.get("sourceRef"), f"sourceRefs[{index}].sourceRef")
        source_digest = _sha256(
            source.get("sourceDigest"), f"sourceRefs[{index}].sourceDigest"
        )
        if source_ref in seen_refs:
            raise AudioSynthesisRequestError(
                "requestedProvenance sourceRefs contain duplicate refs"
            )
        seen_refs.add(source_ref)
        covered = covered or (
            source_ref == asset_requirement_ref
            and source_digest == asset_requirement_digest
        )
    if not covered:
        raise AudioSynthesisRequestError(
            "requestedProvenance does not cover the AssetRequirement"
        )
    return provenance


def _verify_generation_request(value: Any) -> dict[str, Any]:
    request = _verify_sealed(
        value, _SOURCE_GENERATION_REQUEST_FIELDS, "AudioGenerationRequest"
    )
    _reject_external_controls(request)
    kind = request.get("requestKind")
    if kind == "NARRATION_SYNTHESIS":
        raise NotImplementedError("PIPER_RUNTIME_ABSENT")
    if (
        request.get("schemaVersion") != SOURCE_AUDIO_GENERATION_REQUEST_SCHEMA_VERSION
        or kind not in SUPPORTED_PROGRAMMATIC_REQUEST_KINDS
        or request.get("outputAssetVersionType") != _OUTPUT_TYPE_BY_REQUEST_KIND.get(kind)
        or request.get("outputTarget") != "ASSET_VERSION"
        or request.get("state") != "CONTRACT_ONLY_ADAPTER_REQUIRED"
        or request.get("immutable") is not True
        or request.get("publicationAllowed") is not False
    ):
        raise AudioSynthesisRequestError("AudioGenerationRequest semantics are invalid")
    for field in (
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "assetRequirementRef",
    ):
        _text(request.get(field), field)
    _sha256(request.get("assetRequirementDigest"), "assetRequirementDigest")
    version = _integer(
        request.get("version"), "version", minimum=1, maximum=10_000
    )
    predecessor_ref = request.get("supersedesGenerationRequestVersionRef")
    predecessor_digest = request.get("supersedesGenerationRequestVersionDigest")
    if version == 1:
        if predecessor_ref is not None or predecessor_digest is not None:
            raise AudioSynthesisRequestError(
                "initial AudioGenerationRequest cannot have a predecessor"
            )
    else:
        _text(predecessor_ref, "supersedesGenerationRequestVersionRef")
        _sha256(
            predecessor_digest, "supersedesGenerationRequestVersionDigest"
        )
    if predecessor_ref == request["generationRequestVersionRef"]:
        raise AudioSynthesisRequestError(
            "AudioGenerationRequest cannot supersede itself"
        )
    _text(request.get("createdBy"), "createdBy")
    _timestamp(request.get("createdAt"), "createdAt")
    request_spec = request.get("requestSpec")
    if not isinstance(request_spec, Mapping):
        raise AudioSynthesisRequestError("requestSpec must be an object")
    if kind == "MUSIC_GENERATION":
        expected_fields = {"musicSourceKind", "musicSpecDigest", "sourceAudioCueRefs"}
        digest_field = "musicSpecDigest"
        if request_spec.get("musicSourceKind") != "PROGRAMMATIC":
            raise AudioSynthesisRequestError("musicSourceKind must be PROGRAMMATIC")
    elif kind == "SFX_GENERATION":
        expected_fields = {"sfxKind", "synthesisSpecDigest", "sourceAudioCueRefs"}
        digest_field = "synthesisSpecDigest"
        if request_spec.get("sfxKind") not in SFX_EFFECTS:
            raise AudioSynthesisRequestError("sfxKind is invalid")
    else:
        expected_fields = {"ambienceKind", "synthesisSpecDigest", "sourceAudioCueRefs"}
        digest_field = "synthesisSpecDigest"
        if request_spec.get("ambienceKind") not in AMBIENCE_EFFECTS:
            raise AudioSynthesisRequestError("ambienceKind is invalid")
    if set(request_spec) != expected_fields:
        raise AudioSynthesisRequestError("requestSpec fields are invalid")
    _sha256(request_spec.get(digest_field), f"requestSpec.{digest_field}")
    cues = request_spec.get("sourceAudioCueRefs")
    if cues != []:
        raise AudioSynthesisRequestError(
            "sourceAudioCueRefs require downstream AudioCue authority"
        )
    request["rightsBinding"] = _verify_rights_binding(
        request.get("rightsBinding"),
        request_kind=kind,
        asset_requirement_ref=request["assetRequirementRef"],
        asset_requirement_digest=request["assetRequirementDigest"],
    )
    request["requestedProvenance"] = _verify_requested_provenance(
        request.get("requestedProvenance"),
        asset_requirement_ref=request["assetRequirementRef"],
        asset_requirement_digest=request["assetRequirementDigest"],
    )
    return request


def _validate_execution_context(value: Any) -> dict[str, Any]:
    context = _verify_sealed(
        value, _EXECUTION_CONTEXT_FIELDS, "audio synthesis execution context"
    )
    _reject_external_controls(context)
    if context.get("schemaVersion") != AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION:
        raise AudioSynthesisRequestError("execution context schema is invalid")
    for field in (
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
    ):
        _text(context.get(field), field)
    for field in ("creativeShotDigest", "scriptVersionDigest"):
        _sha256(context.get(field), field)
    context["storageKey"] = _storage_key(context.get("storageKey"))
    context["synthesisSpec"] = _validate_synthesis_spec(context.get("synthesisSpec"))
    return context


def build_audio_synthesis_execution_context(
    command: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(command, Mapping)
        or set(command) != _EXECUTION_CONTEXT_COMMAND_FIELDS
    ):
        raise AudioSynthesisRequestError("execution context command fields are invalid")
    _reject_external_controls(command)
    return _validate_execution_context(
        _sealed(
            {
                "schemaVersion": AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION,
                **deepcopy(dict(command)),
            }
        )
    )


def _validate_execution_request(value: Any) -> dict[str, Any]:
    request = _verify_sealed(
        value, _EXECUTION_REQUEST_FIELDS, "audio synthesis execution request"
    )
    _reject_external_controls(request)
    if (
        request.get("schemaVersion") != AUDIO_SYNTHESIS_EXECUTION_REQUEST_SCHEMA_VERSION
        or request.get("requestKind") not in SUPPORTED_PROGRAMMATIC_REQUEST_KINDS
        or request.get("outputAssetVersionType")
        != _OUTPUT_TYPE_BY_REQUEST_KIND.get(request.get("requestKind"))
        or request.get("adapterCapability") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or request.get("requestedProvenance") != "LOCAL_EVIDENCE"
        or request.get("state") != "LOCAL_EXECUTION_REQUEST"
        or request.get("publicationAllowed") is not False
    ):
        raise AudioSynthesisRequestError("execution request semantics are invalid")
    for field in (
        "workspaceRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "productionRunRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "assetRequirementRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
    ):
        _text(request.get(field), field)
    for field in (
        "generationRequestDigest",
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
    ):
        _sha256(request.get(field), field)
    request["storageKey"] = _storage_key(request.get("storageKey"))
    request["synthesisSpec"] = _validate_synthesis_spec(request.get("synthesisSpec"))
    role = _ROLE_BY_REQUEST_KIND[request["requestKind"]]
    if request["synthesisSpec"]["audioRole"] != role:
        raise AudioSynthesisRequestError("request kind and synthesis role disagree")
    if request["requestKind"] != "MUSIC_GENERATION":
        effect = request["synthesisSpec"]["effectKind"]
        if PROGRAMMATIC_EFFECT_ROLE[effect] != role:
            raise AudioSynthesisRequestError("request kind and effect disagree")
    if request.get("executionRequestRef") != _execution_request_ref(request):
        raise AudioSynthesisRequestError("executionRequestRef is invalid")
    return request


@dataclass(frozen=True, slots=True, init=False)
class AudioSynthesisExecutionRequest:
    """Immutable exact V4 request accepted by the built-in synthesizer."""

    _payload_json: str

    @classmethod
    def from_mapping(cls, value: Any) -> "AudioSynthesisExecutionRequest":
        normalized = _validate_execution_request(value)
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical(normalized).decode("utf-8"))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_audio_synthesis_execution_request(
    generation_request: Mapping[str, Any],
    *,
    execution_context: Mapping[str, Any],
) -> AudioSynthesisExecutionRequest:
    source = _verify_generation_request(generation_request)
    context = _validate_execution_context(execution_context)
    spec = context["synthesisSpec"]
    kind = source["requestKind"]
    expected_role = _ROLE_BY_REQUEST_KIND[kind]
    if spec["audioRole"] != expected_role:
        raise AudioSynthesisRequestError("source request and synthesis role disagree")
    if kind == "MUSIC_GENERATION":
        expected_spec_digest = source["requestSpec"]["musicSpecDigest"]
    else:
        expected_spec_digest = source["requestSpec"]["synthesisSpecDigest"]
        kind_field = "sfxKind" if kind == "SFX_GENERATION" else "ambienceKind"
        if source["requestSpec"][kind_field] != spec["effectKind"]:
            raise AudioSynthesisRequestError("source request effect binding is stale")
    if (
        expected_spec_digest != spec["payloadDigest"]
        or source["requestedProvenance"]["parametersDigest"] != spec["payloadDigest"]
    ):
        raise AudioSynthesisRequestError("source synthesisSpec digest binding is stale")
    semantic: dict[str, Any] = {
        "schemaVersion": AUDIO_SYNTHESIS_EXECUTION_REQUEST_SCHEMA_VERSION,
        "workspaceRef": source["workspaceRef"],
        "projectRef": source["projectRef"],
        "seriesRef": source["seriesRef"],
        "episodeRef": source["episodeRef"],
        "productionRunRef": source["productionRunRef"],
        "generationRequestRef": source["generationRequestRef"],
        "generationRequestVersionRef": source["generationRequestVersionRef"],
        "generationRequestDigest": source["payloadDigest"],
        "assetRequirementRef": source["assetRequirementRef"],
        "assetRequirementDigest": source["assetRequirementDigest"],
        "creativeShotRef": context["creativeShotRef"],
        "creativeShotVersionRef": context["creativeShotVersionRef"],
        "creativeShotDigest": context["creativeShotDigest"],
        "scriptRef": context["scriptRef"],
        "scriptVersionRef": context["scriptVersionRef"],
        "scriptVersionDigest": context["scriptVersionDigest"],
        "requestKind": kind,
        "outputAssetVersionType": source["outputAssetVersionType"],
        "adapterCapability": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
        "requestedProvenance": "LOCAL_EVIDENCE",
        "storageKey": context["storageKey"],
        "synthesisSpec": spec,
        "state": "LOCAL_EXECUTION_REQUEST",
        "publicationAllowed": False,
    }
    semantic["executionRequestRef"] = _execution_request_ref(semantic)
    return AudioSynthesisExecutionRequest.from_mapping(_sealed(semantic))


def _seconds(samples: int) -> str:
    whole, remainder = divmod(samples, SAMPLE_RATE)
    if remainder == 0:
        return str(whole)
    return f"{whole}.{remainder * 10**9 // SAMPLE_RATE:09d}".rstrip("0")


def _domain_seed(seed: int, domain: str) -> int:
    payload = {
        "schemaVersion": "v4.audio-seed-domain.v1",
        "seed": seed,
        "domain": domain,
    }
    # FFmpeg's seeded sources accept positive signed integers consistently.
    return int(_digest(payload)[:8], 16) & 0x7FFFFFFF


def _channel_tail(channels: int) -> str:
    if channels == 1:
        return ",aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=mono"
    return (
        ",pan=stereo|c0=c0|c1=c0,"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo"
    )


def _finish_graph(
    source: str, *, duration_samples: int, channels: int, limit: str = "0.85"
) -> str:
    fade_start = _seconds(max(duration_samples - 2_400, 0))
    return (
        f"{source}afade=t=in:st=0:d=0.005,"
        f"afade=t=out:st={fade_start}:d=0.05,"
        f"alimiter=limit={limit}:level=false:latency=true,"
        f"atrim=end_sample={duration_samples},asetpts=N/SR/TB"
        f"{_channel_tail(channels)}[out]"
    )


def _effect_command_spec(
    spec: Mapping[str, Any]
) -> tuple[list[str], str, dict[str, int]]:
    effect = spec["effectKind"]
    seed = spec["seed"]
    samples = spec["durationSamples"]
    channels = spec["channels"]
    carrier_seed = _domain_seed(seed, f"effect:{effect}:carrier")
    modulation_seed = _domain_seed(seed, f"effect:{effect}:modulation")
    seeds = {
        "carrier": carrier_seed,
        "modulation": modulation_seed,
    }

    if effect == "rain":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=white:sample_rate=48000:amplitude=0.20:"
                f"seed={carrier_seed}"
            ),
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=white:sample_rate=48000:amplitude=1:"
                f"seed={modulation_seed}"
            ),
        ]
        source = (
            "[0:a]highpass=f=500:precision=f64,"
            "lowpass=f=9000:precision=f64[carrier];"
            "[1:a]lowpass=f=1.4:precision=f64,"
            "aeval=exprs='0.72+8*abs(val(0))':c=mono[envelope];"
            "[carrier][envelope]amultiply,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "wind":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=pink:sample_rate=48000:amplitude=0.32:"
                f"seed={carrier_seed}"
            ),
        ]
        lfo_millihertz = 140 + modulation_seed % 81
        source = (
            "[0:a]lowpass=f=720:precision=f64,highpass=f=28:precision=f64,"
            f"tremolo=f={lfo_millihertz / 1000:.3f}:d=0.62,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "room_tone":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=pink:sample_rate=48000:amplitude=0.035:"
                f"seed={carrier_seed}"
            ),
        ]
        cutoff = 2_200 + modulation_seed % 801
        source = (
            f"[0:a]highpass=f=45:precision=f64,lowpass=f={cutoff}:precision=f64,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels, limit="0.80"
        ), seeds

    if effect == "door_hinge":
        frequency = 115 + carrier_seed % 76
        tremolo_millihertz = 1_600 + modulation_seed % 1_001
        inputs = [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000",
        ]
        source = (
            f"[0:a]tremolo=f={tremolo_millihertz / 1000:.3f}:d=0.86,"
            "highpass=f=80:precision=f64,lowpass=f=2400:precision=f64,"
            "volume=0.32,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "footsteps":
        pace_millihertz = 1_500 + modulation_seed % 1_001
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=brown:sample_rate=48000:amplitude=0.58:"
                f"seed={carrier_seed}"
            ),
        ]
        source = (
            "[0:a]lowpass=f=420:precision=f64,highpass=f=35:precision=f64,"
            f"tremolo=f={pace_millihertz / 1000:.3f}:d=0.98,volume=0.62,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "paper":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=white:sample_rate=48000:amplitude=0.64:"
                f"seed={carrier_seed}"
            ),
        ]
        decay = _seconds(max(samples - 480, 1))
        source = (
            "[0:a]highpass=f=2500:precision=f64,"
            f"afade=t=out:st=0.01:d={decay}:curve=exp,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "clothing":
        center = 1_500 + modulation_seed % 1_501
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=pink:sample_rate=48000:amplitude=0.30:"
                f"seed={carrier_seed}"
            ),
        ]
        source = (
            f"[0:a]bandpass=f={center}:t=q:w=0.8:precision=f64,"
            "tremolo=f=3.2:d=0.72,volume=0.48,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect == "fire_crackle":
        inputs = [
            "-f",
            "lavfi",
            "-i",
            (
                "anoisesrc=color=velvet:sample_rate=48000:amplitude=0.60:"
                f"seed={carrier_seed}:density=0.004"
            ),
        ]
        source = (
            "[0:a]asplit=3[p1][p2][p3];"
            "[p1]bandpass=f=1200:t=q:w=7:precision=f64[f1];"
            "[p2]bandpass=f=2600:t=q:w=9:precision=f64[f2];"
            "[p3]bandpass=f=4800:t=q:w=11:precision=f64[f3];"
            "[f1][f2][f3]amix=inputs=3:weights='1 0.7 0.45':"
            "normalize=false:duration=longest:dropout_transition=0,"
        )
        return inputs, _finish_graph(
            source, duration_samples=samples, channels=channels
        ), seeds

    if effect != "impact_transient":
        raise AudioSynthesisRequestError("effectKind is unsupported")
    frequency = 52 + modulation_seed % 50
    inputs = [
        "-f",
        "lavfi",
        "-i",
        (
            "anoisesrc=color=white:sample_rate=48000:amplitude=0.72:"
            f"seed={carrier_seed}"
        ),
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={frequency}:sample_rate=48000",
    ]
    source = (
        "[0:a]highpass=f=900:precision=f64,"
        "afade=t=out:st=0:d=0.08:curve=exp[n];"
        "[1:a]lowpass=f=180:precision=f64,volume=0.35,"
        "afade=t=out:st=0:d=0.16:curve=exp[t];"
        "[n][t]amix=inputs=2:weights='0.72 0.28':"
        "normalize=false:duration=longest:dropout_transition=0,"
    )
    return inputs, _finish_graph(
        source, duration_samples=samples, channels=channels
    ), seeds


def _frequency(midi_note: int) -> str:
    value = 440.0 * (2.0 ** ((midi_note - 69) / 12.0))
    if not math.isfinite(value) or value <= 0:
        raise AudioSynthesisRequestError("music frequency is invalid")
    return f"{value:.9f}"


def _piecewise_frequency(values: Sequence[str], index_expression: str) -> str:
    expression = values[-1]
    for index in range(len(values) - 2, -1, -1):
        expression = (
            f"if(eq({index_expression},{index}),{values[index]},{expression})"
        )
    return expression


def _music_notes(spec: Mapping[str, Any], sequence_seed: int) -> list[int]:
    mode = _MUSIC_MODES[spec["mode"]]
    root = 60 + _KEY_SEMITONE[spec["key"]]
    pattern = "".join(spec["structure"]["sectionPattern"])
    notes: list[int] = []
    for index in range(16):
        material = {
            "schemaVersion": "v4.procedural-note-choice.v1",
            "sequenceSeed": sequence_seed,
            "sectionPattern": pattern,
            "step": index,
        }
        selection = int(_digest(material)[:8], 16)
        scale_degree = selection % len(mode)
        octave = (selection // len(mode)) % 2
        notes.append(root + mode[scale_degree] + 12 * octave)
    return notes


def _music_command_spec(
    spec: Mapping[str, Any]
) -> tuple[list[str], str, dict[str, int]]:
    sequence_seed = _domain_seed(spec["seed"], "music:sequence")
    pulse_seed = _domain_seed(spec["seed"], "music:pulse")
    seeds = {
        "sequence": sequence_seed,
        "pulse": pulse_seed,
    }
    notes = _music_notes(spec, sequence_seed)
    melody_frequencies = [_frequency(note) for note in notes]
    bass_frequencies = [
        _frequency(notes[(index // 2) * 2] - 24) for index in range(16)
    ]
    steps_per_beat = spec["sequence"]["stepsPerBeat"]
    steps_per_second = spec["tempoBpm"] * steps_per_beat / 60.0
    step_seconds = 1.0 / steps_per_second
    gate_seconds = step_seconds * spec["sequence"]["gatePermille"] / 1000.0
    attack_seconds = spec["instrument"]["attackSamples"] / SAMPLE_RATE
    release_seconds = min(
        spec["instrument"]["releaseSamples"] / SAMPLE_RATE,
        gate_seconds / 2,
    )
    index_expression = f"mod(floor(t*{steps_per_second:.9f}),16)"
    position_expression = f"mod(t,{step_seconds:.9f})"
    envelope = (
        f"if(lt({position_expression},{attack_seconds:.9f}),"
        f"{position_expression}/{attack_seconds:.9f},"
        f"if(lt({position_expression},{gate_seconds - release_seconds:.9f}),1,"
        f"if(lt({position_expression},{gate_seconds:.9f}),"
        f"({gate_seconds:.9f}-{position_expression})/{release_seconds:.9f},0)))"
    )
    melody_frequency = _piecewise_frequency(
        melody_frequencies, index_expression
    )
    bass_frequency = _piecewise_frequency(bass_frequencies, index_expression)
    melody_expression = (
        f"0.105*({envelope})*(sin(2*PI*({melody_frequency})*t)+"
        f"0.22*sin(4*PI*({melody_frequency})*t))"
    )
    bass_expression = (
        f"0.090*({envelope})*sin(2*PI*({bass_frequency})*t)"
    )
    beat_seconds = 60.0 / spec["tempoBpm"]
    pulse_frequency = 46 + pulse_seed % 17
    pulse_expression = (
        f"0.090*sin(2*PI*{pulse_frequency}*t)*"
        f"exp(-22*mod(t,{beat_seconds:.9f}))"
    )
    output_stem = spec["stemRecipe"]["outputStem"]
    expressions = {
        "melody": melody_expression,
        "bass": bass_expression,
        "pulse": pulse_expression,
    }
    selected = (
        ["melody", "bass", "pulse"]
        if output_stem == "full_mix"
        else [output_stem]
    )
    inputs: list[str] = []
    for stem in selected:
        inputs.extend(
            [
                "-f",
                "lavfi",
                "-i",
                f"aevalsrc=exprs='{expressions[stem]}':s=48000",
            ]
        )
    samples = spec["durationSamples"]
    if output_stem == "full_mix":
        source = (
            "[0:a][1:a][2:a]amix=inputs=3:weights='1 0.9 0.8':"
            "normalize=false:duration=longest:dropout_transition=0,"
        )
    else:
        source = "[0:a]"
    graph = _finish_graph(
        source,
        duration_samples=samples,
        channels=spec["channels"],
        limit="0.80",
    )
    return inputs, graph, seeds


def _recipe(spec: Mapping[str, Any]) -> tuple[dict[str, Any], list[str], str]:
    if spec["schemaVersion"] == PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION:
        inputs, graph, seeds = _effect_command_spec(spec)
        recipe_kind = "PROGRAMMATIC_EFFECT"
        effect_kind: str | None = spec["effectKind"]
        derived_note_sequence: list[int] | None = None
    else:
        inputs, graph, seeds = _music_command_spec(spec)
        recipe_kind = "PROCEDURAL_MUSIC"
        effect_kind = None
        derived_note_sequence = _music_notes(spec, seeds["sequence"])
    output_spec = {
        "codec": "pcm_s16le",
        "container": "wav",
        "sampleRate": SAMPLE_RATE,
        "channels": spec["channels"],
        "bitExact": True,
        "metadataIncluded": False,
    }
    command_spec = _sealed(
        {
            "schemaVersion": AUDIO_SYNTHESIS_COMMAND_SPEC_SCHEMA_VERSION,
            "inputArguments": inputs,
            "filterComplex": graph,
            "mapLabel": "[out]",
            "outputSpec": output_spec,
        }
    )
    recipe = _sealed(
        {
            "schemaVersion": AUDIO_SYNTHESIS_RECIPE_SCHEMA_VERSION,
            "recipeKind": recipe_kind,
            "adapterIdentity": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
            "audioRole": spec["audioRole"],
            "effectKind": effect_kind,
            "synthesisSpec": deepcopy(dict(spec)),
            "seedDomains": seeds,
            "derivedNoteSequence": derived_note_sequence,
            "commandSpec": command_spec,
            "publicationAllowed": False,
        }
    )
    return recipe, inputs, graph


def _output_arguments(output_descriptor: int, *, channels: int) -> list[str]:
    return [
        "-map",
        "[out]",
        "-vn",
        "-sn",
        "-dn",
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(SAMPLE_RATE),
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
        "-y",
        f"/proc/self/fd/{output_descriptor}",
    ]


def _directory_identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _file_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _open_artifact_root(value: Path | str) -> tuple[Path, int, tuple[int, int]]:
    try:
        raw = Path(value)
    except TypeError as exc:
        raise AudioSynthesisRequestError("artifact_root is invalid") from exc
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    # abspath removes lexical dot components without dereferencing symlinks.
    root_path = Path(os.path.abspath(os.fspath(raw)))
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(root_path, flags)
        info = os.fstat(descriptor)
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise AudioSynthesisRequestError("artifact_root cannot be pinned") from exc
    if not stat.S_ISDIR(info.st_mode):
        os.close(descriptor)
        raise AudioSynthesisRequestError("artifact_root must be a directory")
    return root_path, descriptor, _directory_identity(info)


def _open_or_create_output_parent(
    root_descriptor: int, storage_key: str
) -> tuple[int, str]:
    parts = PurePosixPath(storage_key).parts
    if len(parts) < 3:
        raise AudioSynthesisRequestError("storageKey is invalid")
    try:
        current = os.dup(root_descriptor)
    except OSError as exc:
        raise AudioSynthesisArtifactError("artifact root descriptor is unavailable") from exc
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        for part in parts[:-1]:
            try:
                next_descriptor = os.open(part, directory_flags, dir_fd=current)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                next_descriptor = os.open(part, directory_flags, dir_fd=current)
            info = os.fstat(next_descriptor)
            if not stat.S_ISDIR(info.st_mode):
                os.close(next_descriptor)
                raise AudioSynthesisArtifactError(
                    "storageKey parent is not a directory"
                )
            os.close(current)
            current = next_descriptor
        return current, parts[-1]
    except AudioSynthesisError:
        os.close(current)
        raise
    except OSError as exc:
        os.close(current)
        raise AudioSynthesisArtifactError(
            "storageKey parent cannot be pinned"
        ) from exc


def _create_output(parent_descriptor: int, leaf: str) -> int:
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor: int | None = None
    try:
        descriptor = os.open(leaf, flags, 0o600, dir_fd=parent_descriptor)
        info = os.fstat(descriptor)
    except FileExistsError as exc:
        raise AudioSynthesisArtifactError("audio output already exists") from exc
    except OSError as exc:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise AudioSynthesisArtifactError("audio output cannot be created") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_size != 0
    ):
        os.close(descriptor)
        raise AudioSynthesisArtifactError("audio output is not a new regular file")
    return descriptor


def _neutralize_failed_output(output_descriptor: int) -> None:
    """Erase bytes through the held FD without deleting a raced directory entry."""

    try:
        os.ftruncate(output_descriptor, 0)
        os.fsync(output_descriptor)
    except OSError:
        pass


def _hash_descriptor(
    descriptor: int,
) -> tuple[str, int, tuple[int, int, int, int, int, int]]:
    digest = sha256()
    byte_size = 0
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise AudioSynthesisArtifactError("audio output is not one regular file")
        if before.st_size <= 0 or before.st_size > MAX_SOURCE_ARTIFACT_BYTES:
            raise AudioSynthesisArtifactError("audio output byte size is invalid")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            byte_size += len(chunk)
            if byte_size > MAX_SOURCE_ARTIFACT_BYTES:
                raise AudioSynthesisArtifactError("audio output exceeds byte limit")
            digest.update(chunk)
        after = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
    except AudioSynthesisError:
        raise
    except OSError as exc:
        raise AudioSynthesisArtifactError("audio output hashing failed") from exc
    if (
        _file_identity(before) != _file_identity(after)
        or byte_size != before.st_size
    ):
        raise AudioSynthesisArtifactError("audio output changed while hashing")
    return digest.hexdigest(), byte_size, _file_identity(before)


def _probe_output_descriptor(
    descriptor: int, *, expected_channels: int, expected_samples: int
) -> dict[str, Any]:
    duplicate: int | None = None
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        duplicate = os.dup(descriptor)
        with os.fdopen(duplicate, "rb", closefd=True) as source:
            duplicate = None
            with wave.open(source, "rb") as reader:
                channels = reader.getnchannels()
                sample_width = reader.getsampwidth()
                sample_rate = reader.getframerate()
                frame_count = reader.getnframes()
                compression = reader.getcomptype()
        os.lseek(descriptor, 0, os.SEEK_SET)
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioSynthesisArtifactError("audio output WAV probe failed") from exc
    finally:
        if duplicate is not None:
            try:
                os.close(duplicate)
            except OSError:
                pass
    if (
        channels != expected_channels
        or sample_width != 2
        or sample_rate != SAMPLE_RATE
        or frame_count != expected_samples
        or compression != "NONE"
    ):
        raise AudioSynthesisArtifactError("audio output format is invalid")
    return {
        "sampleRate": SAMPLE_RATE,
        "channels": channels,
        "durationSeconds": frame_count / SAMPLE_RATE,
        "durationSamples": frame_count,
        "codec": "pcm_s16le",
        "container": "wav",
    }


def _reopen_and_verify_output(
    parent_descriptor: int,
    leaf: str,
    *,
    expected_digest: str,
    expected_size: int,
    expected_identity: tuple[int, int, int, int, int, int],
) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        reopened = os.open(leaf, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        raise AudioSynthesisArtifactError("audio output cannot be re-opened") from exc
    try:
        digest, size, identity = _hash_descriptor(reopened)
    finally:
        os.close(reopened)
    if (
        digest != expected_digest
        or size != expected_size
        or identity != expected_identity
    ):
        raise AudioSynthesisArtifactError("audio output changed after analysis")


def _reopen_from_root_and_verify_output(
    root_descriptor: int,
    storage_key: str,
    *,
    expected_digest: str,
    expected_size: int,
    expected_identity: tuple[int, int, int, int, int, int],
) -> None:
    """Resolve every storage component again from the pinned root descriptor."""

    parts = PurePosixPath(storage_key).parts
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    current: int | None = None
    artifact_descriptor: int | None = None
    try:
        current = os.dup(root_descriptor)
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = next_descriptor
        artifact_descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        digest, size, identity = _hash_descriptor(artifact_descriptor)
    except (OSError, AudioSynthesisError) as exc:
        if isinstance(exc, AudioSynthesisError):
            raise
        raise AudioSynthesisArtifactError(
            "storageKey cannot be re-resolved from pinned artifact_root"
        ) from exc
    finally:
        if artifact_descriptor is not None:
            try:
                os.close(artifact_descriptor)
            except OSError:
                pass
        if current is not None:
            try:
                os.close(current)
            except OSError:
                pass
    if (
        digest != expected_digest
        or size != expected_size
        or identity != expected_identity
    ):
        raise AudioSynthesisArtifactError(
            "storageKey binding changed below pinned artifact_root"
        )


def _verify_root_binding(
    root_path: Path, root_descriptor: int, expected_identity: tuple[int, int]
) -> None:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        current = _directory_identity(os.fstat(root_descriptor))
        reopened = os.open(root_path, flags)
        try:
            visible = _directory_identity(os.fstat(reopened))
        finally:
            os.close(reopened)
    except OSError as exc:
        raise AudioSynthesisArtifactError("artifact_root binding changed") from exc
    if current != expected_identity or visible != expected_identity:
        raise AudioSynthesisArtifactError("artifact_root binding changed")


def _artifact_evidence(
    request: Mapping[str, Any],
    *,
    artifact_digest: str,
    byte_size: int,
    probe: Mapping[str, Any],
    recipe_digest: str,
) -> dict[str, Any]:
    spec = request["synthesisSpec"]
    evidence_semantic = {
        "generationRequestDigest": request["generationRequestDigest"],
        "executionRequestDigest": request["payloadDigest"],
        "storageKey": request["storageKey"],
        "sha256": artifact_digest,
    }
    artifact_ref = "audio-artifact-" + artifact_digest[:32]
    artifact_evidence_ref = (
        "audio-artifact-evidence-" + _digest(evidence_semantic)[:32]
    )
    lineage_fields = (
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
    )
    lineage = {field: request[field] for field in lineage_fields}
    return _sealed(
        {
            "schemaVersion": SOURCE_AUDIO_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            **lineage,
            "generationRequestDigest": request["generationRequestDigest"],
            "executionRequestDigest": request["payloadDigest"],
            "artifactEvidenceRef": artifact_evidence_ref,
            "artifactRef": artifact_ref,
            "storageKey": request["storageKey"],
            "byteSize": byte_size,
            "sha256": artifact_digest,
            "sampleRate": SAMPLE_RATE,
            "channels": spec["channels"],
            "probe": deepcopy(dict(probe)),
            "parametersDigest": spec["payloadDigest"],
            "effectiveParametersDigest": spec["payloadDigest"],
            "synthesisSpecDigest": recipe_digest,
            "adapterIdentity": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
            "audioRole": spec["audioRole"],
            "provenance": "LOCAL_EVIDENCE",
            "state": "TECHNICALLY_VERIFIED",
            "publicationAllowed": False,
        }
    )


def _replay_key(
    *,
    generation_request_digest: str,
    synthesis_spec_digest: str,
    recipe_digest: str,
    runtime_digest: str,
    pcm_digest_spec_digest: str,
    pcm_content_digest: str,
) -> str:
    semantic = {
        "schemaVersion": "v4.audio-synthesis-replay-key.v1",
        "generationRequestDigest": generation_request_digest,
        "synthesisSpecDigest": synthesis_spec_digest,
        "recipeDigest": recipe_digest,
        "runtimeDigest": runtime_digest,
        "pcmDigestSpecDigest": pcm_digest_spec_digest,
        "pcmContentDigest": pcm_content_digest,
    }
    return "audio-synthesis-replay-" + _digest(semantic)


def _validate_execution_evidence(value: Any) -> dict[str, Any]:
    evidence = _verify_sealed(
        value, _EVIDENCE_FIELDS, "audio synthesis execution evidence"
    )
    if (
        evidence.get("schemaVersion")
        != AUDIO_SYNTHESIS_EXECUTION_EVIDENCE_SCHEMA_VERSION
        or evidence.get("adapterIdentity") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or evidence.get("audioRole") not in {"ambience", "sfx", "music"}
        or evidence.get("state") != "TECHNICAL_ANALYSIS_COMPLETE"
        or evidence.get("publicationAllowed") is not False
    ):
        raise AudioSynthesisRequestError("execution evidence semantics are invalid")
    for field in (
        "executionRequestRef",
        "generationRequestRef",
        "generationRequestVersionRef",
        "replayKey",
    ):
        _text(evidence.get(field), field)
    for field in (
        "executionRequestDigest",
        "generationRequestDigest",
        "recipeDigest",
        "runtimeDigest",
    ):
        _sha256(evidence.get(field), field)
    recipe = evidence.get("recipe")
    runtime = evidence.get("runtime")
    artifact = evidence.get("artifactEvidence")
    analysis = evidence.get("technicalAnalysisEvidence")
    for nested, field in (
        (recipe, "recipe"),
        (runtime, "runtime"),
        (artifact, "artifactEvidence"),
        (analysis, "technicalAnalysisEvidence"),
    ):
        if not isinstance(nested, Mapping):
            raise AudioSynthesisRequestError(f"{field} is invalid")
        normalized = deepcopy(dict(nested))
        claimed = normalized.pop("payloadDigest", None)
        if not _is_sha256(claimed) or claimed != _digest(normalized):
            raise AudioSynthesisRequestError(f"{field} payload digest is invalid")
    if set(recipe) != _RECIPE_FIELDS or set(runtime) != _RUNTIME_FIELDS:
        raise AudioSynthesisRequestError(
            "execution recipe or runtime evidence fields are invalid"
        )
    command_spec = recipe.get("commandSpec")
    if not isinstance(command_spec, Mapping) or set(command_spec) != _COMMAND_SPEC_FIELDS:
        raise AudioSynthesisRequestError("recipe commandSpec fields are invalid")
    normalized_command_spec = deepcopy(dict(command_spec))
    command_spec_digest = normalized_command_spec.pop("payloadDigest", None)
    if (
        not _is_sha256(command_spec_digest)
        or command_spec_digest != _digest(normalized_command_spec)
        or command_spec.get("schemaVersion")
        != AUDIO_SYNTHESIS_COMMAND_SPEC_SCHEMA_VERSION
        or command_spec.get("mapLabel") != "[out]"
    ):
        raise AudioSynthesisRequestError("recipe commandSpec is invalid")
    cpu_profile = runtime.get("cpuProfile")
    if not isinstance(cpu_profile, Mapping) or set(cpu_profile) != _CPU_PROFILE_FIELDS:
        raise AudioSynthesisRequestError("runtime cpuProfile fields are invalid")
    normalized_cpu_profile = deepcopy(dict(cpu_profile))
    cpu_profile_digest = normalized_cpu_profile.pop("profileDigest", None)
    cpu_flags = normalized_cpu_profile.get("cpuFlags")
    if (
        not _is_sha256(cpu_profile_digest)
        or cpu_profile_digest != _digest(normalized_cpu_profile)
        or not isinstance(cpu_flags, list)
        or cpu_flags != sorted(set(cpu_flags))
        or any(not isinstance(flag, str) or not flag for flag in cpu_flags)
    ):
        raise AudioSynthesisRequestError("runtime cpuProfile is invalid")
    for field in ("system", "machine", "release"):
        _text(cpu_profile.get(field), f"runtime.cpuProfile.{field}")
    if (
        recipe.get("schemaVersion") != AUDIO_SYNTHESIS_RECIPE_SCHEMA_VERSION
        or recipe.get("publicationAllowed") is not False
        or runtime.get("schemaVersion")
        != LOCAL_AUDIO_RUNTIME_EVIDENCE_SCHEMA_VERSION
        or runtime.get("engine") != "FFMPEG"
        or runtime.get("determinismScope")
        != "SAME_FFMPEG_BUILD_AND_CPU_PROFILE"
        or runtime.get("protocolWhitelist") != list(FFMPEG_PROTOCOL_WHITELIST)
        or runtime.get("networkAccess")
        != "DENIED_BY_CLOSED_RECIPE_AND_PROTOCOL_WHITELIST"
        or runtime.get("environment")
        != {"LC_ALL": "C", "LANG": "C", "TZ": "UTC"}
        or runtime.get("threadCount") != 1
        or runtime.get("filterThreadCount") != 1
        or runtime.get("bitExact") is not True
        or runtime.get("state") != "PINNED_EXECUTION_COMPLETE"
        or runtime.get("commandSpecDigest") != command_spec.get("payloadDigest")
    ):
        raise AudioSynthesisRequestError("runtime determinism boundary is invalid")
    for field in ("binarySha256", "ffmpegBuildFingerprint", "commandSpecDigest"):
        _sha256(runtime.get(field), f"runtime.{field}")
    if (
        not isinstance(recipe.get("synthesisSpec"), Mapping)
        or not isinstance(recipe.get("commandSpec"), Mapping)
        or not isinstance(artifact.get("probe"), Mapping)
        or not isinstance(analysis.get("pcmDigestSpec"), Mapping)
    ):
        raise AudioSynthesisRequestError("execution evidence nested shape is invalid")
    if (
        recipe["payloadDigest"] != evidence["recipeDigest"]
        or runtime["payloadDigest"] != evidence["runtimeDigest"]
        or recipe.get("adapterIdentity") != evidence["adapterIdentity"]
        or runtime.get("adapterIdentity") != evidence["adapterIdentity"]
        or recipe.get("audioRole") != evidence["audioRole"]
        or recipe.get("effectKind") != evidence["effectKind"]
        or artifact.get("generationRequestDigest")
        != evidence["generationRequestDigest"]
        or artifact.get("executionRequestDigest")
        != evidence["executionRequestDigest"]
        or analysis.get("sourceArtifactEvidenceRef")
        != artifact.get("artifactEvidenceRef")
        or analysis.get("sourceArtifactEvidenceDigest")
        != artifact.get("payloadDigest")
        or analysis.get("artifactRef") != artifact.get("artifactRef")
        or analysis.get("fileDigest") != artifact.get("sha256")
        or analysis.get("storageKey") != artifact.get("storageKey")
        or analysis.get("byteSize") != artifact.get("byteSize")
        or analysis.get("sampleRate") != artifact.get("sampleRate")
        or analysis.get("channelCount") != artifact.get("channels")
        or analysis.get("sampleCount")
        != artifact.get("probe", {}).get("durationSamples")
        or analysis.get("validationState") != "PASSED"
        or analysis.get("failureReasons") != []
        or analysis.get("clippingDetected") is not False
        or analysis.get("ffmpegVersion") != runtime.get("version")
    ):
        raise AudioSynthesisRequestError("execution evidence binding is invalid")
    _sha256(analysis.get("pcmContentDigest"), "pcmContentDigest")
    expected_replay = _replay_key(
        generation_request_digest=evidence["generationRequestDigest"],
        synthesis_spec_digest=recipe["synthesisSpec"]["payloadDigest"],
        recipe_digest=evidence["recipeDigest"],
        runtime_digest=evidence["runtimeDigest"],
        pcm_digest_spec_digest=_digest(analysis["pcmDigestSpec"]),
        pcm_content_digest=analysis["pcmContentDigest"],
    )
    if evidence["replayKey"] != expected_replay:
        raise AudioSynthesisRequestError("execution evidence replayKey is invalid")
    if evidence.get("executionEvidenceRef") != _execution_evidence_ref(evidence):
        raise AudioSynthesisRequestError("executionEvidenceRef is invalid")
    return evidence


@dataclass(frozen=True, slots=True, init=False)
class AudioSynthesisExecutionEvidence:
    """Immutable evidence that can only be minted by completed local execution."""

    _payload_json: str
    _technical_analysis_wrapper: AudioTechnicalAnalysisEvidence

    @classmethod
    def _from_executor(
        cls,
        value: Any,
        technical_analysis: AudioTechnicalAnalysisEvidence,
    ) -> "AudioSynthesisExecutionEvidence":
        if type(technical_analysis) is not AudioTechnicalAnalysisEvidence:
            raise AudioSynthesisRequestError(
                "exact AudioTechnicalAnalysisEvidence wrapper is required"
            )
        normalized = _validate_execution_evidence(value)
        if normalized["technicalAnalysisEvidence"] != technical_analysis.as_dict():
            raise AudioSynthesisRequestError(
                "technical analysis wrapper binding is invalid"
            )
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical(normalized).decode("utf-8"))
        object.__setattr__(
            instance, "_technical_analysis_wrapper", technical_analysis
        )
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def technical_analysis_evidence(self) -> AudioTechnicalAnalysisEvidence:
        """Return the exact PR-5 analyzer wrapper bound into this evidence."""

        return self._technical_analysis_wrapper


def execute_audio_synthesis(
    request: AudioSynthesisExecutionRequest,
    *,
    artifact_root: Path | str,
) -> AudioSynthesisExecutionEvidence:
    """Render, verify, analyze, and seal one closed local audio request."""

    if type(request) is not AudioSynthesisExecutionRequest:
        raise AudioSynthesisRequestError(
            "exact AudioSynthesisExecutionRequest wrapper is required"
        )
    normalized = _validate_execution_request(request.as_dict())
    # All request recursion and exact schemas are checked before the first write.
    recipe, inputs, graph = _recipe(normalized["synthesisSpec"])
    root_descriptor: int | None = None
    parent_descriptor: int | None = None
    output_descriptor: int | None = None
    output_created = False
    succeeded = False
    try:
        root_path, root_descriptor, root_identity = _open_artifact_root(artifact_root)
        parent_descriptor, leaf = _open_or_create_output_parent(
            root_descriptor, normalized["storageKey"]
        )
        output_descriptor = _create_output(parent_descriptor, leaf)
        output_created = True
        try:
            with _PinnedFfmpegAudioRuntime() as runtime:
                arguments = [
                    *inputs,
                    "-filter_complex",
                    graph,
                    *_output_arguments(
                        output_descriptor,
                        channels=normalized["synthesisSpec"]["channels"],
                    ),
                ]
                runtime.render(arguments, pass_fds=(output_descriptor,))
                runtime_evidence = runtime.evidence(
                    command_spec_digest=recipe["commandSpec"]["payloadDigest"]
                )
        except LocalAudioRuntimeError as exc:
            raise AudioSynthesisRuntimeError(str(exc)) from exc
        try:
            os.fsync(output_descriptor)
        except OSError as exc:
            raise AudioSynthesisArtifactError("audio output cannot be synchronized") from exc
        artifact_digest, byte_size, output_identity = _hash_descriptor(
            output_descriptor
        )
        probe = _probe_output_descriptor(
            output_descriptor,
            expected_channels=normalized["synthesisSpec"]["channels"],
            expected_samples=normalized["synthesisSpec"]["durationSamples"],
        )
        # Re-hash after the independent WAV parser to close descriptor-offset and
        # mutation races before creating source evidence.
        post_probe_digest, post_probe_size, post_probe_identity = _hash_descriptor(
            output_descriptor
        )
        if (
            post_probe_digest != artifact_digest
            or post_probe_size != byte_size
            or post_probe_identity != output_identity
        ):
            raise AudioSynthesisArtifactError("audio output changed during probe")
        artifact_evidence = _artifact_evidence(
            normalized,
            artifact_digest=artifact_digest,
            byte_size=byte_size,
            probe=probe,
            recipe_digest=recipe["payloadDigest"],
        )
        analysis_wrapper: AudioTechnicalAnalysisEvidence = analyze_audio_artifact(
            artifact_evidence,
            artifact_root=root_path,
        )
        technical_analysis = analysis_wrapper.as_dict()
        if (
            technical_analysis.get("validationState") != "PASSED"
            or technical_analysis.get("failureReasons") != []
            or technical_analysis.get("clippingDetected") is not False
        ):
            raise AudioSynthesisArtifactError(
                "generated audio failed frozen technical validation"
            )
        if technical_analysis.get("ffmpegVersion") != runtime_evidence.get(
            "version"
        ):
            raise AudioSynthesisArtifactError(
                "generation and analysis FFmpeg runtime bindings disagree"
            )
        _reopen_and_verify_output(
            parent_descriptor,
            leaf,
            expected_digest=artifact_digest,
            expected_size=byte_size,
            expected_identity=output_identity,
        )
        _verify_root_binding(root_path, root_descriptor, root_identity)
        runtime_digest = runtime_evidence["payloadDigest"]
        evidence_semantic: dict[str, Any] = {
            "schemaVersion": AUDIO_SYNTHESIS_EXECUTION_EVIDENCE_SCHEMA_VERSION,
            "executionRequestRef": normalized["executionRequestRef"],
            "executionRequestDigest": normalized["payloadDigest"],
            "generationRequestRef": normalized["generationRequestRef"],
            "generationRequestVersionRef": normalized[
                "generationRequestVersionRef"
            ],
            "generationRequestDigest": normalized["generationRequestDigest"],
            "adapterIdentity": BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
            "audioRole": normalized["synthesisSpec"]["audioRole"],
            "effectKind": normalized["synthesisSpec"].get("effectKind"),
            "recipe": recipe,
            "recipeDigest": recipe["payloadDigest"],
            "runtime": runtime_evidence,
            "runtimeDigest": runtime_digest,
            "replayKey": _replay_key(
                generation_request_digest=normalized["generationRequestDigest"],
                synthesis_spec_digest=normalized["synthesisSpec"]["payloadDigest"],
                recipe_digest=recipe["payloadDigest"],
                    runtime_digest=runtime_digest,
                    pcm_digest_spec_digest=_digest(
                        technical_analysis["pcmDigestSpec"]
                    ),
                    pcm_content_digest=technical_analysis[
                        "pcmContentDigest"
                    ],
            ),
            "artifactEvidence": artifact_evidence,
            "technicalAnalysisEvidence": technical_analysis,
            "state": "TECHNICAL_ANALYSIS_COMPLETE",
            "publicationAllowed": False,
        }
        evidence_semantic["executionEvidenceRef"] = _execution_evidence_ref(
            evidence_semantic
        )
        result = AudioSynthesisExecutionEvidence._from_executor(
            _sealed(evidence_semantic),
            analysis_wrapper,
        )
        # Namespace visibility, descendant identity, and bytes are checked as the
        # final operation before the immutable evidence capability is returned.
        _reopen_from_root_and_verify_output(
            root_descriptor,
            normalized["storageKey"],
            expected_digest=artifact_digest,
            expected_size=byte_size,
            expected_identity=output_identity,
        )
        _verify_root_binding(root_path, root_descriptor, root_identity)
        succeeded = True
        return result
    except AudioSynthesisError:
        raise
    except Exception as exc:
        raise AudioSynthesisArtifactError(
            "audio synthesis verification or analysis failed"
        ) from exc
    finally:
        if (
            output_created
            and not succeeded
            and parent_descriptor is not None
            and output_descriptor is not None
        ):
            _neutralize_failed_output(output_descriptor)
        for descriptor in (output_descriptor, parent_descriptor, root_descriptor):
            if descriptor is None:
                continue
            try:
                os.close(descriptor)
            except OSError:
                pass


__all__ = [
    "AUDIO_SYNTHESIS_EXECUTION_REQUEST_SCHEMA_VERSION",
    "AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION",
    "AUDIO_SYNTHESIS_EXECUTION_EVIDENCE_SCHEMA_VERSION",
    "PROGRAMMATIC_EFFECT_SYNTHESIS_SPEC_SCHEMA_VERSION",
    "PROCEDURAL_MUSIC_SYNTHESIS_SPEC_SCHEMA_VERSION",
    "AUDIO_SYNTHESIS_RECIPE_SCHEMA_VERSION",
    "AUDIO_SYNTHESIS_COMMAND_SPEC_SCHEMA_VERSION",
    "MUSIC_STRUCTURE_SCHEMA_VERSION",
    "MUSIC_SEQUENCE_SCHEMA_VERSION",
    "MUSIC_INSTRUMENT_SCHEMA_VERSION",
    "MUSIC_STEM_RECIPE_SCHEMA_VERSION",
    "MUSIC_QUALITY_APPROVAL",
    "BUILTIN_FFMPEG_AUDIO_ADAPTER_ID",
    "AMBIENCE_EFFECTS",
    "SFX_EFFECTS",
    "PROGRAMMATIC_EFFECTS",
    "PROGRAMMATIC_EFFECT_ROLE",
    "DEFAULT_MUSIC_STRUCTURE",
    "DEFAULT_MUSIC_SEQUENCE",
    "DEFAULT_MUSIC_INSTRUMENT",
    "DEFAULT_MUSIC_STEM_RECIPE",
    "AudioSynthesisError",
    "AudioSynthesisRequestError",
    "AudioSynthesisRuntimeError",
    "AudioSynthesisArtifactError",
    "AudioSynthesisExecutionRequest",
    "AudioSynthesisExecutionEvidence",
    "build_programmatic_effect_synthesis_spec",
    "build_procedural_music_synthesis_spec",
    "build_audio_synthesis_execution_context",
    "build_audio_synthesis_execution_request",
    "execute_audio_synthesis",
]
