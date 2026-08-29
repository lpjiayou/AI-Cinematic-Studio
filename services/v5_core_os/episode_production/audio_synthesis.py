"""M12 deterministic programmatic-audio authority bridge.

This module is deliberately additive.  It does not redefine the PR-3 audio
authority types and it does not perform Admission, Timeline placement, or a
rights decision.  It binds one exact PR-3 ``AudioGenerationRequest`` to the
closed V4 FFmpeg synthesis boundary, derives technical generation lineage, and
can propose one of the existing Music/Sfx/Ambience AssetVersion contracts.

The V5 synthesis-spec envelope keeps policy facts (no external samples and no
network access) outside the V4 execution-spec digest.  The digest carried by the
PR-3 request is always the exact sealed V4 ``executionSpec.payloadDigest``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Mapping

from services.v4_platform.audio_synthesis import (
    AMBIENCE_EFFECTS,
    AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION,
    MUSIC_QUALITY_APPROVAL as V4_MUSIC_QUALITY_APPROVAL,
    PROGRAMMATIC_EFFECT_ROLE,
    PROGRAMMATIC_EFFECTS,
    SFX_EFFECTS,
    AudioSynthesisExecutionEvidence,
    AudioSynthesisExecutionRequest,
    build_audio_synthesis_execution_context,
    build_audio_synthesis_execution_request,
    build_procedural_music_synthesis_spec,
    build_programmatic_effect_synthesis_spec,
)
from services.v4_platform.local_audio_runtime import (
    BUILTIN_FFMPEG_AUDIO_ADAPTER_ID,
)

from .audio_authority import (
    AmbienceAssetVersion,
    AudioGenerationRequest,
    AudioRightsRequiredError,
    MusicAssetVersion,
    SfxAssetVersion,
    build_ambience_asset_version,
    build_audio_provenance,
    build_music_asset_version,
    build_sfx_asset_version,
)
from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    _canonical_json,
    _digest,
    _required_ref,
)


PROGRAMMATIC_AUDIO_SYNTHESIS_SPEC_SCHEMA_VERSION = (
    "v5.programmatic-audio-synthesis-spec.v1"
)
PROGRAMMATIC_AUDIO_EXECUTION_CONTEXT_SCHEMA_VERSION = (
    "v5.programmatic-audio-execution-context.v1"
)
PROGRAMMATIC_AUDIO_GENERATION_RECORD_SCHEMA_VERSION = (
    "v5.programmatic-audio-generation-record.v1"
)

PROGRAMMATIC_AUDIO_EFFECT_KINDS = frozenset(PROGRAMMATIC_EFFECTS)
PROGRAMMATIC_AMBIENCE_EFFECT_KINDS = frozenset(AMBIENCE_EFFECTS)
PROGRAMMATIC_SFX_EFFECT_KINDS = frozenset(SFX_EFFECTS)
PROGRAMMATIC_AUDIO_EFFECT_ROLE = MappingProxyType(dict(PROGRAMMATIC_EFFECT_ROLE))
MUSIC_QUALITY_APPROVAL = V4_MUSIC_QUALITY_APPROVAL
PROGRAMMATIC_AUDIO_ORIGIN_KIND = "LOCAL_DETERMINISTIC_EXECUTION"
PROGRAMMATIC_AUDIO_CREATED_BY = "v5.programmatic-audio-synthesis-bridge.v1"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_SPEC_ENVELOPE_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionSpec",
        "synthesisSpecDigest",
        "externalSampleRefs",
        "networkAccessAllowed",
        "payloadDigest",
    }
)
_EFFECT_COMMAND_FIELDS = frozenset(
    {
        "audioRole",
        "effectKind",
        "durationSamples",
        "sampleRate",
        "channels",
        "seed",
        "externalSampleRefs",
        "networkAccessAllowed",
    }
)
_MUSIC_COMMAND_FIELDS = frozenset(
    {
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
        "externalSampleRefs",
        "networkAccessAllowed",
    }
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
        "scriptVersionRef",
        "scriptVersionDigest",
        "storageKey",
        "payloadDigest",
    }
)
_CONTEXT_COMMAND_FIELDS = _CONTEXT_FIELDS - {"schemaVersion", "payloadDigest"}
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
        "requestKind",
        "outputAssetVersionType",
        "audioRole",
        "effectKind",
        "synthesisSpecEnvelope",
        "synthesisSpecDigest",
        "executionContextDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "executionEvidenceRef",
        "executionEvidenceDigest",
        "parametersDigest",
        "recipe",
        "recipeDigest",
        "seedProfile",
        "deterministicNoteSequence",
        "runtime",
        "runtimeDigest",
        "replayKey",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "artifactRef",
        "storageKey",
        "byteSize",
        "fileDigest",
        "pcmContentDigest",
        "technicalAnalysisEvidenceRef",
        "technicalAnalysisEvidenceDigest",
        "stemRecipe",
        "provenanceBasis",
        "rightsBindingRef",
        "rightsBindingDigest",
        "musicQualityApproval",
        "technicalValidationState",
        "state",
        "authorityState",
        "immutable",
        "publicationAllowed",
        "payloadDigest",
    }
)

_REQUEST_KIND_TO_ROLE = {
    "MUSIC_GENERATION": "music",
    "SFX_GENERATION": "sfx",
    "AMBIENCE_GENERATION": "ambience",
}
_REQUEST_KIND_TO_OUTPUT = {
    "MUSIC_GENERATION": "MusicAssetVersion",
    "SFX_GENERATION": "SfxAssetVersion",
    "AMBIENCE_GENERATION": "AmbienceAssetVersion",
}


class ProgrammaticAudioSynthesisError(EpisodeProductionError):
    """A V5 programmatic synthesis contract or binding is invalid."""


class ProgrammaticAudioEvidenceBindingError(StaleInputError):
    """V4 execution evidence does not match the exact V5 lineage."""


def _exact(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ProgrammaticAudioSynthesisError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise ProgrammaticAudioSynthesisError("payloadDigest is derived")
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


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ProgrammaticAudioSynthesisError(f"{field} is invalid")
    return value


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ProgrammaticAudioSynthesisError(f"{field} is invalid")
    return value


def _storage_key(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("asset-versions/audio/"):
        raise ProgrammaticAudioSynthesisError("storageKey is invalid")
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
        raise ProgrammaticAudioSynthesisError("storageKey is invalid")
    return value


def _v4_execution_spec(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProgrammaticAudioSynthesisError("executionSpec is invalid")
    supplied = deepcopy(dict(value))
    schema_version = supplied.get("schemaVersion")
    command = {
        key: item
        for key, item in supplied.items()
        if key not in {"schemaVersion", "payloadDigest"}
    }
    try:
        if "effectKind" in supplied:
            rebuilt = build_programmatic_effect_synthesis_spec(command)
        else:
            rebuilt = build_procedural_music_synthesis_spec(command)
    except Exception as exc:
        raise ProgrammaticAudioSynthesisError("executionSpec is invalid") from exc
    if rebuilt != supplied or rebuilt.get("schemaVersion") != schema_version:
        raise StaleInputError("executionSpec binding is stale")
    return rebuilt


def _validate_synthesis_spec(value: Any) -> dict[str, Any]:
    envelope = _verify_sealed(
        value, _SPEC_ENVELOPE_FIELDS, "ProgrammaticAudioSynthesisSpec"
    )
    if (
        envelope["schemaVersion"]
        != PROGRAMMATIC_AUDIO_SYNTHESIS_SPEC_SCHEMA_VERSION
        or envelope["externalSampleRefs"] != []
        or envelope["networkAccessAllowed"] is not False
    ):
        raise ProgrammaticAudioSynthesisError(
            "ProgrammaticAudioSynthesisSpec policy is invalid"
        )
    execution_spec = _v4_execution_spec(envelope["executionSpec"])
    if envelope["synthesisSpecDigest"] != execution_spec["payloadDigest"]:
        raise StaleInputError("synthesisSpecDigest binding is stale")
    envelope["executionSpec"] = execution_spec
    return envelope


@dataclass(frozen=True, slots=True, init=False)
class ProgrammaticAudioSynthesisSpec:
    """Immutable V5 policy envelope around one exact sealed V4 spec union."""

    _payload_json: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ProgrammaticAudioSynthesisSpec":
        normalized = _validate_synthesis_spec(value)
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    def execution_spec(self) -> dict[str, Any]:
        return self.as_dict()["executionSpec"]


def build_programmatic_audio_synthesis_spec(
    command: Mapping[str, Any],
) -> ProgrammaticAudioSynthesisSpec:
    """Build the closed effect/music union without accepting execution inputs."""

    if not isinstance(command, Mapping):
        raise ProgrammaticAudioSynthesisError(
            "ProgrammaticAudioSynthesisSpec command is invalid"
        )
    fields = set(command)
    if fields == _EFFECT_COMMAND_FIELDS:
        value = _exact(command, _EFFECT_COMMAND_FIELDS, "effect synthesis command")
        if value["effectKind"] not in PROGRAMMATIC_AUDIO_EFFECT_KINDS:
            raise ProgrammaticAudioSynthesisError("effectKind is invalid")
        if value["audioRole"] != PROGRAMMATIC_AUDIO_EFFECT_ROLE[value["effectKind"]]:
            raise ProgrammaticAudioSynthesisError("effect role mapping is invalid")
        v4_command = {
            key: item
            for key, item in value.items()
            if key not in {"externalSampleRefs", "networkAccessAllowed"}
        }
        try:
            execution_spec = build_programmatic_effect_synthesis_spec(v4_command)
        except Exception as exc:
            raise ProgrammaticAudioSynthesisError(
                "effect synthesis command is invalid"
            ) from exc
    elif fields == _MUSIC_COMMAND_FIELDS:
        value = _exact(command, _MUSIC_COMMAND_FIELDS, "music synthesis command")
        if value["audioRole"] != "music":
            raise ProgrammaticAudioSynthesisError("music audioRole is invalid")
        v4_command = {
            key: item
            for key, item in value.items()
            if key not in {"externalSampleRefs", "networkAccessAllowed"}
        }
        try:
            execution_spec = build_procedural_music_synthesis_spec(v4_command)
        except Exception as exc:
            raise ProgrammaticAudioSynthesisError(
                "music synthesis command is invalid"
            ) from exc
    else:
        raise ProgrammaticAudioSynthesisError(
            "ProgrammaticAudioSynthesisSpec command fields are invalid"
        )
    if value["externalSampleRefs"] != [] or value["networkAccessAllowed"] is not False:
        raise ProgrammaticAudioSynthesisError(
            "external samples and network access are forbidden"
        )
    result = _seal(
        {
            "schemaVersion": PROGRAMMATIC_AUDIO_SYNTHESIS_SPEC_SCHEMA_VERSION,
            "executionSpec": execution_spec,
            "synthesisSpecDigest": execution_spec["payloadDigest"],
            "externalSampleRefs": [],
            "networkAccessAllowed": False,
        }
    )
    return ProgrammaticAudioSynthesisSpec.from_mapping(result)


def validate_programmatic_audio_synthesis_spec(
    value: Any,
) -> ProgrammaticAudioSynthesisSpec:
    if isinstance(value, ProgrammaticAudioSynthesisSpec):
        value = value.as_dict()
    return ProgrammaticAudioSynthesisSpec.from_mapping(value)


def _validate_execution_context(value: Any) -> dict[str, Any]:
    context = _verify_sealed(
        value, _CONTEXT_FIELDS, "ProgrammaticAudioExecutionContext"
    )
    if (
        context["schemaVersion"]
        != PROGRAMMATIC_AUDIO_EXECUTION_CONTEXT_SCHEMA_VERSION
    ):
        raise ProgrammaticAudioSynthesisError(
            "ProgrammaticAudioExecutionContext schema is unsupported"
        )
    for field in (
        *_SCOPE_FIELDS,
        "assetRequirementRef",
        "creativeShotRef",
        "creativeShotVersionRef",
        "scriptRef",
        "scriptVersionRef",
    ):
        _required_ref(context[field], field)
    for field in (
        "assetRequirementDigest",
        "creativeShotDigest",
        "scriptVersionDigest",
    ):
        _sha256(context[field], field)
    context["storageKey"] = _storage_key(context["storageKey"])
    return context


@dataclass(frozen=True, slots=True, init=False)
class ProgrammaticAudioExecutionContext:
    """Exact V5 supplement for lineage absent from the PR-3 request schema."""

    _payload_json: str

    @classmethod
    def from_mapping(cls, value: Any) -> "ProgrammaticAudioExecutionContext":
        normalized = _validate_execution_context(value)
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(normalized))
        return instance

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_programmatic_audio_execution_context(
    command: Mapping[str, Any],
) -> ProgrammaticAudioExecutionContext:
    value = _exact(
        command,
        _CONTEXT_COMMAND_FIELDS,
        "ProgrammaticAudioExecutionContext command",
    )
    return ProgrammaticAudioExecutionContext.from_mapping(
        _seal(
            {
                "schemaVersion": PROGRAMMATIC_AUDIO_EXECUTION_CONTEXT_SCHEMA_VERSION,
                **value,
            }
        )
    )


def validate_programmatic_audio_execution_context(
    value: Any,
) -> ProgrammaticAudioExecutionContext:
    if isinstance(value, ProgrammaticAudioExecutionContext):
        value = value.as_dict()
    return ProgrammaticAudioExecutionContext.from_mapping(value)


def _exact_generation_request(value: Any) -> dict[str, Any]:
    if type(value) is not AudioGenerationRequest:
        raise ProgrammaticAudioSynthesisError(
            "exact AudioGenerationRequest wrapper is required"
        )
    request = value.as_dict()
    kind = request["requestKind"]
    if kind not in _REQUEST_KIND_TO_ROLE:
        raise ProgrammaticAudioSynthesisError(
            "AudioGenerationRequest is not programmatic audio"
        )
    if request["outputAssetVersionType"] != _REQUEST_KIND_TO_OUTPUT[kind]:
        raise StaleInputError("AudioGenerationRequest output type is stale")
    return request


def _exact_spec_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not ProgrammaticAudioSynthesisSpec:
        raise ProgrammaticAudioSynthesisError(
            "exact ProgrammaticAudioSynthesisSpec wrapper is required"
        )
    return value.as_dict()


def _exact_context_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not ProgrammaticAudioExecutionContext:
        raise ProgrammaticAudioSynthesisError(
            "exact ProgrammaticAudioExecutionContext wrapper is required"
        )
    return value.as_dict()


def _validate_music_rights(request: Mapping[str, Any]) -> None:
    if request["requestKind"] != "MUSIC_GENERATION":
        return
    rights = request["rightsBinding"]
    if (
        rights.get("rightsSource") != "RIGHTS_MANIFEST_VERSION"
        or rights.get("license") != "PROJECT_OWNED"
        or rights.get("ownership") != "PROJECT_OWNER"
        or not {"AUDIO_PRODUCTION", "MUSIC_GENERATION"}.issubset(
            set(rights.get("usageScope", []))
        )
    ):
        raise AudioRightsRequiredError(
            "programmatic music requires project-owned RightsManifest authority"
        )


def _bind_request_spec(
    request: Mapping[str, Any], spec: Mapping[str, Any]
) -> None:
    kind = request["requestKind"]
    execution_spec = spec["executionSpec"]
    expected_role = _REQUEST_KIND_TO_ROLE[kind]
    if execution_spec["audioRole"] != expected_role:
        raise StaleInputError("synthesis role binding is stale")
    request_spec = request["requestSpec"]
    if kind == "MUSIC_GENERATION":
        digest = request_spec["musicSpecDigest"]
        if request_spec["musicSourceKind"] != "PROGRAMMATIC":
            raise ProgrammaticAudioSynthesisError(
                "musicSourceKind must be PROGRAMMATIC"
            )
    else:
        digest = request_spec["synthesisSpecDigest"]
        field = "sfxKind" if kind == "SFX_GENERATION" else "ambienceKind"
        if request_spec[field] != execution_spec["effectKind"]:
            raise StaleInputError("effect kind binding is stale")
    requested = request["requestedProvenance"]
    if (
        digest != spec["synthesisSpecDigest"]
        or requested["originKind"] != PROGRAMMATIC_AUDIO_ORIGIN_KIND
        or requested["adapterIdentity"] != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or requested["parametersDigest"] != spec["synthesisSpecDigest"]
    ):
        raise StaleInputError("programmatic synthesis provenance binding is stale")


def _bind_execution_context(
    request: Mapping[str, Any], context: Mapping[str, Any]
) -> None:
    if any(request[field] != context[field] for field in _SCOPE_FIELDS):
        raise StaleInputError("execution context scope is stale")
    if (
        request["assetRequirementRef"] != context["assetRequirementRef"]
        or request["assetRequirementDigest"]
        != context["assetRequirementDigest"]
    ):
        raise StaleInputError("execution context AssetRequirement is stale")


def _v4_context(
    context: Mapping[str, Any], spec: Mapping[str, Any]
) -> dict[str, Any]:
    result = build_audio_synthesis_execution_context(
        {
            "creativeShotRef": context["creativeShotRef"],
            "creativeShotVersionRef": context["creativeShotVersionRef"],
            "creativeShotDigest": context["creativeShotDigest"],
            "scriptRef": context["scriptRef"],
            "scriptVersionRef": context["scriptVersionRef"],
            "scriptVersionDigest": context["scriptVersionDigest"],
            "storageKey": context["storageKey"],
            "synthesisSpec": spec["executionSpec"],
        }
    )
    if (
        result.get("schemaVersion")
        != AUDIO_SYNTHESIS_EXECUTION_CONTEXT_SCHEMA_VERSION
    ):
        raise ProgrammaticAudioSynthesisError(
            "V4 audio synthesis execution context schema is unsupported"
        )
    return result


def build_programmatic_audio_execution_request(
    generation_request: AudioGenerationRequest,
    *,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
) -> AudioSynthesisExecutionRequest:
    """Project exact V5 wrappers into the closed V4 request, without aliases."""

    request = _exact_generation_request(generation_request)
    spec = _exact_spec_wrapper(synthesis_spec)
    context = _exact_context_wrapper(execution_context)
    _bind_request_spec(request, spec)
    _bind_execution_context(request, context)
    _validate_music_rights(request)
    try:
        return build_audio_synthesis_execution_request(
            request,
            execution_context=_v4_context(context, spec),
        )
    except Exception as exc:
        raise ProgrammaticAudioSynthesisError(
            "V4 audio synthesis execution projection is invalid"
        ) from exc


def _exact_execution_request_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not AudioSynthesisExecutionRequest:
        raise ProgrammaticAudioSynthesisError(
            "exact AudioSynthesisExecutionRequest wrapper is required"
        )
    return value.as_dict()


def _exact_execution_evidence_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not AudioSynthesisExecutionEvidence:
        raise ProgrammaticAudioSynthesisError(
            "exact AudioSynthesisExecutionEvidence wrapper is required"
        )
    return value.as_dict()


def _record_ref(value: Mapping[str, Any]) -> str:
    semantic = deepcopy(dict(value))
    semantic.pop("generationRecordRef", None)
    semantic.pop("payloadDigest", None)
    return "programmatic-audio-generation-record-" + _digest(semantic)[:32]


def _evidence_projection(
    *,
    request: Mapping[str, Any],
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
    execution_request: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    expected_role = _REQUEST_KIND_TO_ROLE[request["requestKind"]]
    expected_effect = spec["executionSpec"].get("effectKind")
    if (
        evidence["executionRequestRef"] != execution_request["executionRequestRef"]
        or evidence["executionRequestDigest"] != execution_request["payloadDigest"]
        or evidence["generationRequestRef"] != request["generationRequestRef"]
        or evidence["generationRequestVersionRef"]
        != request["generationRequestVersionRef"]
        or evidence["generationRequestDigest"] != request["payloadDigest"]
        or evidence["adapterIdentity"] != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or evidence["audioRole"] != expected_role
        or evidence["effectKind"] != expected_effect
        or evidence["state"] != "TECHNICAL_ANALYSIS_COMPLETE"
        or evidence["publicationAllowed"] is not False
    ):
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 execution evidence lineage is stale"
        )

    recipe = deepcopy(dict(evidence["recipe"]))
    runtime = deepcopy(dict(evidence["runtime"]))
    artifact = deepcopy(dict(evidence["artifactEvidence"]))
    analysis = deepcopy(dict(evidence["technicalAnalysisEvidence"]))
    if (
        recipe.get("payloadDigest") != evidence["recipeDigest"]
        or recipe.get("synthesisSpec") != spec["executionSpec"]
        or recipe.get("audioRole") != expected_role
        or recipe.get("effectKind") != expected_effect
        or recipe.get("adapterIdentity") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or runtime.get("payloadDigest") != evidence["runtimeDigest"]
        or runtime.get("adapterIdentity") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or runtime.get("protocolWhitelist") != ["file", "pipe"]
        or runtime.get("networkAccess")
        != "DENIED_BY_CLOSED_RECIPE_AND_PROTOCOL_WHITELIST"
    ):
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 recipe or offline runtime binding is stale"
        )
    lineage = {
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "creativeShotRef": context["creativeShotRef"],
        "creativeShotVersionRef": context["creativeShotVersionRef"],
        "creativeShotDigest": context["creativeShotDigest"],
        "scriptRef": context["scriptRef"],
        "scriptVersionRef": context["scriptVersionRef"],
        "scriptVersionDigest": context["scriptVersionDigest"],
    }
    if (
        any(artifact.get(field) != expected for field, expected in lineage.items())
        or artifact.get("generationRequestDigest") != request["payloadDigest"]
        or artifact.get("executionRequestDigest")
        != execution_request["payloadDigest"]
        or artifact.get("storageKey") != context["storageKey"]
        or artifact.get("parametersDigest") != spec["synthesisSpecDigest"]
        or artifact.get("effectiveParametersDigest")
        != spec["synthesisSpecDigest"]
        or artifact.get("synthesisSpecDigest") != evidence["recipeDigest"]
        or artifact.get("adapterIdentity") != BUILTIN_FFMPEG_AUDIO_ADAPTER_ID
        or artifact.get("audioRole") != expected_role
        or artifact.get("provenance") != "LOCAL_EVIDENCE"
        or artifact.get("state") != "TECHNICALLY_VERIFIED"
        or artifact.get("publicationAllowed") is not False
    ):
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 artifact evidence binding is stale"
        )
    for field in ("payloadDigest", "sha256"):
        _sha256(artifact.get(field), f"artifactEvidence.{field}")
    if (
        analysis.get("sourceArtifactEvidenceRef")
        != artifact.get("artifactEvidenceRef")
        or analysis.get("sourceArtifactEvidenceDigest")
        != artifact.get("payloadDigest")
        or analysis.get("artifactRef") != artifact.get("artifactRef")
        or analysis.get("storageKey") != artifact.get("storageKey")
        or analysis.get("byteSize") != artifact.get("byteSize")
        or analysis.get("fileDigest") != artifact.get("sha256")
    ):
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 technical analysis binding is stale"
        )
    for field in ("payloadDigest", "fileDigest", "pcmContentDigest"):
        _sha256(analysis.get(field), f"technicalAnalysisEvidence.{field}")
    if (
        isinstance(artifact.get("byteSize"), bool)
        or not isinstance(artifact.get("byteSize"), int)
        or artifact["byteSize"] <= 0
    ):
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 artifact byteSize is invalid"
        )
    seed_domains = recipe.get("seedDomains")
    if (
        not isinstance(seed_domains, Mapping)
        or not seed_domains
        or any(
            not isinstance(key, str)
            or not key
            or isinstance(item, bool)
            or not isinstance(item, int)
            or item < 0
            for key, item in seed_domains.items()
        )
    ):
        raise ProgrammaticAudioEvidenceBindingError("V4 seed profile is invalid")
    return {
        "recipe": recipe,
        "runtime": runtime,
        "artifact": artifact,
        "analysis": analysis,
        "seedProfile": {
            "rootSeed": spec["executionSpec"]["seed"],
            "domains": dict(sorted(seed_domains.items())),
        },
    }


def _derived_generation_record(
    *,
    generation_request: AudioGenerationRequest,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
    execution_request: AudioSynthesisExecutionRequest,
    execution_evidence: AudioSynthesisExecutionEvidence,
) -> dict[str, Any]:
    request = _exact_generation_request(generation_request)
    spec = _exact_spec_wrapper(synthesis_spec)
    context = _exact_context_wrapper(execution_context)
    _bind_request_spec(request, spec)
    _bind_execution_context(request, context)
    _validate_music_rights(request)

    actual_execution = _exact_execution_request_wrapper(execution_request)
    expected_execution = build_programmatic_audio_execution_request(
        generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
    ).as_dict()
    if actual_execution != expected_execution:
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 execution request is not the exact V5 projection"
        )
    evidence = _exact_execution_evidence_wrapper(execution_evidence)
    exact_analysis = execution_evidence.technical_analysis_evidence().as_dict()
    if exact_analysis != evidence["technicalAnalysisEvidence"]:
        raise ProgrammaticAudioEvidenceBindingError(
            "V4 technical-analysis capability binding is stale"
        )
    projected = _evidence_projection(
        request=request,
        spec=spec,
        context=context,
        execution_request=actual_execution,
        evidence=evidence,
    )
    recipe = projected["recipe"]
    runtime = projected["runtime"]
    artifact = projected["artifact"]
    analysis = projected["analysis"]
    rights = request["rightsBinding"]
    music_quality = (
        MUSIC_QUALITY_APPROVAL
        if request["requestKind"] == "MUSIC_GENERATION"
        else None
    )
    stem_recipe = (
        deepcopy(spec["executionSpec"]["stemRecipe"])
        if request["requestKind"] == "MUSIC_GENERATION"
        else None
    )
    note_sequence = recipe.get("derivedNoteSequence")
    if request["requestKind"] == "MUSIC_GENERATION":
        if (
            not isinstance(note_sequence, list)
            or len(note_sequence) != 16
            or any(
                isinstance(note, bool)
                or not isinstance(note, int)
                or note < 0
                or note > 127
                for note in note_sequence
            )
        ):
            raise ProgrammaticAudioEvidenceBindingError(
                "V4 deterministic note sequence is invalid"
            )
    elif note_sequence is not None:
        raise ProgrammaticAudioEvidenceBindingError(
            "effect recipe cannot claim a deterministic note sequence"
        )
    provenance_basis = {
        "originKind": PROGRAMMATIC_AUDIO_ORIGIN_KIND,
        "adapterIdentity": evidence["adapterIdentity"],
        "parametersDigest": artifact["parametersDigest"],
        "executionEvidenceRef": evidence["executionEvidenceRef"],
        "executionEvidenceDigest": evidence["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
    }
    semantic: dict[str, Any] = {
        "schemaVersion": PROGRAMMATIC_AUDIO_GENERATION_RECORD_SCHEMA_VERSION,
        **{field: request[field] for field in _SCOPE_FIELDS},
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "requestKind": request["requestKind"],
        "outputAssetVersionType": request["outputAssetVersionType"],
        "audioRole": _REQUEST_KIND_TO_ROLE[request["requestKind"]],
        "effectKind": spec["executionSpec"].get("effectKind"),
        "synthesisSpecEnvelope": spec,
        "synthesisSpecDigest": spec["synthesisSpecDigest"],
        "executionContextDigest": context["payloadDigest"],
        "executionRequestRef": actual_execution["executionRequestRef"],
        "executionRequestDigest": actual_execution["payloadDigest"],
        "executionEvidenceRef": evidence["executionEvidenceRef"],
        "executionEvidenceDigest": evidence["payloadDigest"],
        "parametersDigest": artifact["parametersDigest"],
        "recipe": recipe,
        "recipeDigest": evidence["recipeDigest"],
        "seedProfile": projected["seedProfile"],
        "deterministicNoteSequence": deepcopy(note_sequence),
        "runtime": runtime,
        "runtimeDigest": evidence["runtimeDigest"],
        "replayKey": evidence["replayKey"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "artifactRef": artifact["artifactRef"],
        "storageKey": artifact["storageKey"],
        "byteSize": artifact["byteSize"],
        "fileDigest": analysis["fileDigest"],
        "pcmContentDigest": analysis["pcmContentDigest"],
        "technicalAnalysisEvidenceRef": analysis["analysisEvidenceRef"],
        "technicalAnalysisEvidenceDigest": analysis["payloadDigest"],
        "stemRecipe": stem_recipe,
        "provenanceBasis": provenance_basis,
        "rightsBindingRef": rights["rightsBindingRef"],
        "rightsBindingDigest": rights["payloadDigest"],
        "musicQualityApproval": music_quality,
        "technicalValidationState": analysis["validationState"],
        "state": "TECHNICAL_EVIDENCE_RECORDED",
        "authorityState": "TECHNICAL_EVIDENCE_ONLY",
        "immutable": True,
        "publicationAllowed": False,
    }
    semantic["generationRecordRef"] = _record_ref(semantic)
    return _seal(semantic)


def _validate_generation_record(
    value: Any,
    *,
    generation_request: AudioGenerationRequest,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
    execution_request: AudioSynthesisExecutionRequest,
    execution_evidence: AudioSynthesisExecutionEvidence,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _RECORD_FIELDS, "ProgrammaticAudioGenerationRecord"
    )
    expected = _derived_generation_record(
        generation_request=generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )
    if result != expected:
        raise ProgrammaticAudioEvidenceBindingError(
            "ProgrammaticAudioGenerationRecord binding is stale"
        )
    return result


@dataclass(frozen=True, slots=True, init=False)
class ProgrammaticAudioGenerationRecord:
    """Immutable V5 record derived only from exact request and V4 evidence wrappers."""

    _payload_json: str

    @classmethod
    def _from_derived(cls, value: Mapping[str, Any]) -> "ProgrammaticAudioGenerationRecord":
        instance = object.__new__(cls)
        object.__setattr__(instance, "_payload_json", _canonical_json(value))
        return instance

    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        generation_request: AudioGenerationRequest,
        synthesis_spec: ProgrammaticAudioSynthesisSpec,
        execution_context: ProgrammaticAudioExecutionContext,
        execution_request: AudioSynthesisExecutionRequest,
        execution_evidence: AudioSynthesisExecutionEvidence,
    ) -> "ProgrammaticAudioGenerationRecord":
        normalized = _validate_generation_record(
            value,
            generation_request=generation_request,
            synthesis_spec=synthesis_spec,
            execution_context=execution_context,
            execution_request=execution_request,
            execution_evidence=execution_evidence,
        )
        return cls._from_derived(normalized)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._payload_json)


def build_programmatic_audio_generation_record(
    generation_request: AudioGenerationRequest,
    *,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
    execution_request: AudioSynthesisExecutionRequest,
    execution_evidence: AudioSynthesisExecutionEvidence,
) -> ProgrammaticAudioGenerationRecord:
    result = _derived_generation_record(
        generation_request=generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )
    return ProgrammaticAudioGenerationRecord._from_derived(result)


def validate_programmatic_audio_generation_record(
    value: Any,
    *,
    generation_request: AudioGenerationRequest,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
    execution_request: AudioSynthesisExecutionRequest,
    execution_evidence: AudioSynthesisExecutionEvidence,
) -> ProgrammaticAudioGenerationRecord:
    if isinstance(value, ProgrammaticAudioGenerationRecord):
        value = value.as_dict()
    return ProgrammaticAudioGenerationRecord.from_mapping(
        value,
        generation_request=generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )


def _exact_record_wrapper(value: Any) -> dict[str, Any]:
    if type(value) is not ProgrammaticAudioGenerationRecord:
        raise ProgrammaticAudioSynthesisError(
            "exact ProgrammaticAudioGenerationRecord wrapper is required"
        )
    return value.as_dict()


def _asset_refs(
    request: Mapping[str, Any], record: Mapping[str, Any], *, created_at: str
) -> tuple[str, str]:
    role = record["audioRole"]
    asset_semantic = {
        "schemaVersion": "v5.programmatic-audio-asset-identity.v1",
        **{field: request[field] for field in _SCOPE_FIELDS},
        "assetRequirementRef": request["assetRequirementRef"],
        "assetRequirementDigest": request["assetRequirementDigest"],
        "generationRequestVersionRef": request["generationRequestVersionRef"],
        "generationRequestDigest": request["payloadDigest"],
        "generationRecordRef": record["generationRecordRef"],
        "generationRecordDigest": record["payloadDigest"],
        "audioRole": role,
        "effectKind": record["effectKind"],
        "createdAt": created_at,
    }
    asset_ref = f"m12-{role}-asset-" + _digest(asset_semantic)[:32]
    version_semantic = {
        "schemaVersion": "v5.programmatic-audio-asset-version-identity.v1",
        "assetRef": asset_ref,
        "generationRequestDigest": request["payloadDigest"],
        "generationRecordDigest": record["payloadDigest"],
        "artifactEvidenceDigest": record["artifactEvidenceDigest"],
    }
    asset_version_ref = f"m12-{role}-asset-version-" + _digest(version_semantic)[:32]
    return asset_ref, asset_version_ref


def build_programmatic_audio_asset_version(
    generation_request: AudioGenerationRequest,
    *,
    synthesis_spec: ProgrammaticAudioSynthesisSpec,
    execution_context: ProgrammaticAudioExecutionContext,
    execution_request: AudioSynthesisExecutionRequest,
    execution_evidence: AudioSynthesisExecutionEvidence,
    generation_record: ProgrammaticAudioGenerationRecord,
    created_at: str,
) -> MusicAssetVersion | SfxAssetVersion | AmbienceAssetVersion:
    """Propose one existing typed AssetVersion; never admit or place it."""

    request = _exact_generation_request(generation_request)
    spec = _exact_spec_wrapper(synthesis_spec)
    context = _exact_context_wrapper(execution_context)
    record = _exact_record_wrapper(generation_record)
    expected_record = _derived_generation_record(
        generation_request=generation_request,
        synthesis_spec=synthesis_spec,
        execution_context=execution_context,
        execution_request=execution_request,
        execution_evidence=execution_evidence,
    )
    if record != expected_record:
        raise ProgrammaticAudioEvidenceBindingError(
            "generation record is not the exact execution projection"
        )
    normalized_created_at = _text(created_at, "createdAt")
    asset_ref, asset_version_ref = _asset_refs(
        request, record, created_at=normalized_created_at
    )
    provenance = build_audio_provenance(
        {
            "originKind": PROGRAMMATIC_AUDIO_ORIGIN_KIND,
            "adapterIdentity": record["provenanceBasis"]["adapterIdentity"],
            "generationRecordRef": record["generationRecordRef"],
            "parametersDigest": record["parametersDigest"],
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
                    "sourceRef": record["executionRequestRef"],
                    "sourceDigest": record["executionRequestDigest"],
                },
                {
                    "sourceRef": record["generationRecordRef"],
                    "sourceDigest": record["payloadDigest"],
                },
            ],
        }
    )
    command: dict[str, Any] = {
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
        "createdBy": PROGRAMMATIC_AUDIO_CREATED_BY,
        "createdAt": normalized_created_at,
        "sourceAudioCueRefs": [],
    }
    kind = request["requestKind"]
    if kind == "MUSIC_GENERATION":
        command.update(
            {
                "musicSourceKind": "PROGRAMMATIC",
                "musicSpecDigest": spec["synthesisSpecDigest"],
            }
        )
        built = build_music_asset_version(command)
        return MusicAssetVersion.from_mapping(built)
    if kind == "SFX_GENERATION":
        command.update(
            {
                "sfxKind": spec["executionSpec"]["effectKind"],
                "synthesisSpecDigest": spec["synthesisSpecDigest"],
            }
        )
        built = build_sfx_asset_version(command)
        return SfxAssetVersion.from_mapping(built)
    command.update(
        {
            "ambienceKind": spec["executionSpec"]["effectKind"],
            "synthesisSpecDigest": spec["synthesisSpecDigest"],
        }
    )
    built = build_ambience_asset_version(command)
    return AmbienceAssetVersion.from_mapping(built)


__all__ = [
    "PROGRAMMATIC_AUDIO_SYNTHESIS_SPEC_SCHEMA_VERSION",
    "PROGRAMMATIC_AUDIO_EXECUTION_CONTEXT_SCHEMA_VERSION",
    "PROGRAMMATIC_AUDIO_GENERATION_RECORD_SCHEMA_VERSION",
    "PROGRAMMATIC_AUDIO_EFFECT_KINDS",
    "PROGRAMMATIC_AMBIENCE_EFFECT_KINDS",
    "PROGRAMMATIC_SFX_EFFECT_KINDS",
    "PROGRAMMATIC_AUDIO_EFFECT_ROLE",
    "MUSIC_QUALITY_APPROVAL",
    "PROGRAMMATIC_AUDIO_ORIGIN_KIND",
    "PROGRAMMATIC_AUDIO_CREATED_BY",
    "ProgrammaticAudioSynthesisError",
    "ProgrammaticAudioEvidenceBindingError",
    "ProgrammaticAudioSynthesisSpec",
    "ProgrammaticAudioExecutionContext",
    "ProgrammaticAudioGenerationRecord",
    "build_programmatic_audio_synthesis_spec",
    "validate_programmatic_audio_synthesis_spec",
    "build_programmatic_audio_execution_context",
    "validate_programmatic_audio_execution_context",
    "build_programmatic_audio_execution_request",
    "build_programmatic_audio_generation_record",
    "validate_programmatic_audio_generation_record",
    "build_programmatic_audio_asset_version",
]
