"""Immutable M13 composition and render-manifest contracts.

The objects in this module are technical-evidence plans.  They do not execute
a renderer, name an artifact location, admit an AssetVersion, or grant any
master, export, approval, or publication authority.  ``K2DeliveryService`` is
the only writer and the existing Episode Production evidence journal is the
only persistence boundary.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import gcd
import json
import re
from typing import Any, Mapping, Sequence

from services.v3_render_core.digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    PCM_CONTENT_DIGEST_SPEC,
)

from .foundation import EpisodeProductionError, StaleInputError, _canonical_json, _digest


COMPOSITION_SCHEMA_VERSION = "v5.m13-composition.v1"
COMPOSITION_VERSION_SCHEMA_VERSION = "v5.m13-composition-version.v1"
COMPOSITION_TRACK_BINDING_SCHEMA_VERSION = (
    "v5.m13-composition-track-binding.v1"
)
RENDER_MANIFEST_SCHEMA_VERSION = "v5.m13-render-manifest.v1"
RENDER_RUNTIME_EVIDENCE_SCHEMA_VERSION = "v5.m13-render-runtime-evidence.v1"
RENDER_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v5.m13-render-artifact-evidence.v1"
RENDER_RESULT_SCHEMA_VERSION = "v5.m13-render-result.v1"
RENDER_CANDIDATE_SCHEMA_VERSION = "v5.m13-render-candidate.v1"
COMPOSITION_PROVENANCE = "V5_K2_DELIVERY_SERVICE"
SUBTITLE_TIMING_DIGEST_SPEC = "sha256/canonical-subtitle-timing-json/v1"

RESIZE_MODES = frozenset({"EXACT", "FIT_PAD", "FILL_CROP"})
BACKGROUND_POLICIES = frozenset(
    {"BLACK", "TRANSPARENT_WHEN_SUPPORTED", "TIMELINE_BACKGROUND"}
)
SUBTITLE_MODES = frozenset({"NONE", "SIDECAR", "BURN_IN"})
VIDEO_CODECS = frozenset({"H264"})
AUDIO_CODECS = frozenset({"AAC", "NONE"})
VIDEO_PIXEL_FORMATS = frozenset({"YUV420P"})
VIDEO_QUALITY_MODES = frozenset({"CRF"})
VIDEO_PROFILES = frozenset({"BASELINE", "MAIN", "HIGH"})
VIDEO_LEVELS = frozenset({"3.1", "4.0", "4.1", "5.0", "5.1"})
DETERMINISTIC_THREAD_POLICIES = frozenset({"SINGLE_THREAD"})
COLOR_PRIMARIES = frozenset({"BT709"})
COLOR_TRANSFERS = frozenset({"BT709"})
COLOR_SPACES = frozenset({"BT709"})
COLOR_RANGES = frozenset({"TV", "PC"})

# The accepted M13 8/8 slice contains one requirement-only Glyph stage and
# seven immutable result-bound stages.  Scratch reveal and its light sweep are
# one closed result chain, as established by the existing E1 authority.
REQUIRED_EFFECT_KINDS = frozenset(
    {
        "GLYPH_REVEAL",
        "SCRATCH_REVEAL",
        "LOCAL_EXPOSURE",
        "FLAME_EXTINGUISH",
        "SMOKE",
        "NAMEPLATE_TEXT",
        "FACE_MARK_COMPENSATION",
        "DISTANCE_STATE_TRANSITION",
    }
)

_SHA256 = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,511}\Z")
_FORBIDDEN_COMPOSITION_KEY_PARTS = (
    "storagekey",
    "path",
    "filter",
    "argv",
    "outputfile",
    "outputdigest",
    "filedigest",
    "decodedframepixeldigest",
    "pcmcontentdigest",
    "rendercandidate",
    "episodemaster",
    "exportartifact",
    "exportcandidate",
    "qcreport",
    "approvaldecision",
)


class RenderDomainContractError(EpisodeProductionError):
    code = "render_domain_contract_invalid"


class RenderDomainStaleInputError(StaleInputError):
    code = "render_domain_input_stale"


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderDomainContractError(f"{label} fields are invalid")
    result = deepcopy(dict(value))
    _reject_floats(result)
    return result


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise RenderDomainContractError("float authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RenderDomainContractError("object keys must be strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def _reject_composition_authority_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            folded = key.replace("_", "").replace("-", "").lower()
            if any(part in folded for part in _FORBIDDEN_COMPOSITION_KEY_PARTS):
                raise RenderDomainContractError(f"{key} is forbidden")
            _reject_composition_authority_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_composition_authority_keys(item)


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise RenderDomainContractError("payloadDigest is derived")
    _reject_floats(result)
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise RenderDomainStaleInputError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _ref(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or _REFERENCE.fullmatch(value) is None
        or value.startswith(("/", "\\"))
        or re.match(r"[A-Za-z]:[\\/]", value) is not None
        or "://" in value
        or ".." in value.split("/")
    ):
        raise RenderDomainContractError(f"{field} is invalid")
    return value


def _optional_ref(value: Any, field: str) -> str | None:
    return None if value is None else _ref(value, field)


def _digest_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise RenderDomainContractError(f"{field} is invalid")
    return value


def _optional_digest(value: Any, field: str) -> str | None:
    return None if value is None else _digest_value(value, field)


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
        raise RenderDomainContractError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str = "createdAt") -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise RenderDomainContractError(f"{field} is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RenderDomainContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise RenderDomainContractError(f"{field} must include a timezone")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise RenderDomainContractError(f"{field} is invalid")
    return value


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


_COMPOSITION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "compositionRef",
        "timelineRef",
        "createdAt",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_COMPOSITION_COMMAND_FIELDS = _COMPOSITION_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_composition_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _COMPOSITION_FIELDS, "Composition")
    if result["schemaVersion"] != COMPOSITION_SCHEMA_VERSION:
        raise RenderDomainContractError("Composition schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "compositionRef",
        "timelineRef",
    ):
        _ref(result[field], field)
    _timestamp(result["createdAt"])
    if (
        result["provenance"] != COMPOSITION_PROVENANCE
        or result["publicationAllowed"] is not False
    ):
        raise RenderDomainContractError("Composition authority state is invalid")
    _reject_composition_authority_keys(result)
    return result


def build_composition(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(command, _COMPOSITION_COMMAND_FIELDS, "Composition command")
    return _validate_composition_mapping(
        _seal({"schemaVersion": COMPOSITION_SCHEMA_VERSION, **selected})
    )


def validate_composition(value: Any) -> "Composition":
    return Composition.from_mapping(value)


class Composition(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "Composition":
        return cls._from_validated(_validate_composition_mapping(value))


_ASSET_BINDING_FIELDS = frozenset(
    {"assetVersionRef", "version", "assetVersionDigest"}
)
_AUDIO_CUE_BINDING_FIELDS = frozenset(
    {"cueVersionRef", "version", "cueDigest"}
)
_STEM_BINDING_FIELDS = frozenset(
    {
        "stemSetVersionRef",
        "stemSetVersion",
        "stemSetDigest",
        "stemMemberRef",
        "stemMemberDigest",
    }
)
_TECHNICAL_VALIDATION_BINDING_FIELDS = frozenset(
    {
        "validationRef",
        "validationVersionRef",
        "version",
        "validationDigest",
        "validationState",
    }
)
_EFFECT_BINDING_FIELDS = frozenset(
    {
        "effectKind",
        "requirementRef",
        "requirementDigest",
        "resultRef",
        "resultDigest",
    }
)
_TRACK_BINDING_FIELDS = frozenset(
    {
        "schemaVersion",
        "trackRef",
        "trackDigest",
        "trackKind",
        "trackOrder",
        "trackEnabled",
        "lanePolicy",
        "clipRef",
        "clipDigest",
        "clipKind",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "enabled",
        "layer",
        "zOrder",
        "opacity",
        "blendMode",
        "sourceBinding",
        "sourceAssetVersions",
        "audioCueBinding",
        "stemBinding",
        "technicalValidationBinding",
        "effectBinding",
        "transitionIn",
        "transitionOut",
        "speed",
        "transform",
        "maskBindings",
        "bindingDigest",
    }
)


def _validate_asset_binding(value: Any, index: int) -> dict[str, Any]:
    result = _closed(value, _ASSET_BINDING_FIELDS, f"sourceAssetVersions[{index}]")
    _ref(result["assetVersionRef"], "assetVersionRef")
    _integer(result["version"], "AssetVersion version", minimum=1)
    _digest_value(result["assetVersionDigest"], "assetVersionDigest")
    return result


def _validate_track_binding(value: Any, expected_kind: str, index: int) -> dict[str, Any]:
    result = _closed(value, _TRACK_BINDING_FIELDS, f"{expected_kind} binding[{index}]")
    supplied = result.pop("bindingDigest")
    if supplied != _digest(result):
        raise RenderDomainStaleInputError("Composition track binding digest is invalid")
    result["bindingDigest"] = supplied
    if result["schemaVersion"] != COMPOSITION_TRACK_BINDING_SCHEMA_VERSION:
        raise RenderDomainContractError("Composition track binding schema is unsupported")
    if result["trackKind"] != expected_kind or result["clipKind"] != expected_kind:
        raise RenderDomainContractError("Composition Track/Clip kind differs")
    for field in ("trackRef", "clipRef"):
        _ref(result[field], field)
    for field in ("trackDigest", "clipDigest"):
        _digest_value(result[field], field)
    _integer(result["trackOrder"], "trackOrder", maximum=1024)
    _boolean(result["trackEnabled"], "trackEnabled")
    _ref(result["lanePolicy"], "lanePolicy")
    start = _integer(
        result["timelineStartFrameInclusive"],
        "timelineStartFrameInclusive",
    )
    end = _integer(
        result["timelineEndFrameExclusive"],
        "timelineEndFrameExclusive",
        minimum=1,
    )
    if start >= end:
        raise RenderDomainContractError("Composition binding frame range is invalid")
    _boolean(result["enabled"], "enabled")
    for field in ("layer", "zOrder", "opacity"):
        _integer(result[field], field, maximum=10_000)
    _ref(result["blendMode"], "blendMode")
    if not isinstance(result["sourceBinding"], Mapping):
        raise RenderDomainContractError("sourceBinding is invalid")
    _reject_composition_authority_keys(result["sourceBinding"])
    if not isinstance(result["sourceAssetVersions"], list):
        raise RenderDomainContractError("sourceAssetVersions is invalid")
    assets = [
        _validate_asset_binding(item, asset_index)
        for asset_index, item in enumerate(result["sourceAssetVersions"])
    ]
    if assets != sorted(
        assets,
        key=lambda item: (item["assetVersionRef"], item["version"]),
    ) or len({item["assetVersionRef"] for item in assets}) != len(assets):
        raise RenderDomainContractError("sourceAssetVersions is not canonical")
    result["sourceAssetVersions"] = assets
    for field in ("transitionIn", "transitionOut"):
        if result[field] is not None and not isinstance(result[field], Mapping):
            raise RenderDomainContractError(f"{field} is invalid")
        if result[field] is not None:
            _reject_composition_authority_keys(result[field])
    for field in ("speed", "transform"):
        if not isinstance(result[field], Mapping):
            raise RenderDomainContractError(f"{field} is invalid")
        _reject_composition_authority_keys(result[field])
    if not isinstance(result["maskBindings"], list):
        raise RenderDomainContractError("maskBindings is invalid")
    _reject_composition_authority_keys(result["maskBindings"])

    cue = result["audioCueBinding"]
    stem = result["stemBinding"]
    validation = result["technicalValidationBinding"]
    effect = result["effectBinding"]
    if cue is not None:
        cue = _closed(cue, _AUDIO_CUE_BINDING_FIELDS, "AudioCue binding")
        _ref(cue["cueVersionRef"], "cueVersionRef")
        _integer(cue["version"], "AudioCue version", minimum=1)
        _digest_value(cue["cueDigest"], "cueDigest")
        result["audioCueBinding"] = cue
    if stem is not None:
        stem = _closed(stem, _STEM_BINDING_FIELDS, "Stem binding")
        _ref(stem["stemSetVersionRef"], "stemSetVersionRef")
        _integer(stem["stemSetVersion"], "StemSet version", minimum=1)
        _digest_value(stem["stemSetDigest"], "stemSetDigest")
        _ref(stem["stemMemberRef"], "stemMemberRef")
        _digest_value(stem["stemMemberDigest"], "stemMemberDigest")
        result["stemBinding"] = stem
    if validation is not None:
        validation = _closed(
            validation,
            _TECHNICAL_VALIDATION_BINDING_FIELDS,
            "AudioTechnicalValidation binding",
        )
        _ref(validation["validationRef"], "validationRef")
        _ref(validation["validationVersionRef"], "validationVersionRef")
        _integer(validation["version"], "AudioTechnicalValidation version", minimum=1)
        _digest_value(validation["validationDigest"], "validationDigest")
        if validation["validationState"] != "PASSED":
            raise RenderDomainContractError("AudioTechnicalValidation is not PASS")
        result["technicalValidationBinding"] = validation
    if effect is not None:
        effect = _closed(effect, _EFFECT_BINDING_FIELDS, "Effect binding")
        if effect["effectKind"] not in REQUIRED_EFFECT_KINDS:
            raise RenderDomainContractError("Effect kind is unsupported")
        _ref(effect["requirementRef"], "requirementRef")
        _digest_value(effect["requirementDigest"], "requirementDigest")
        result_ref = _optional_ref(effect["resultRef"], "resultRef")
        result_digest = _optional_digest(effect["resultDigest"], "resultDigest")
        if (result_ref is None) != (result_digest is None):
            raise RenderDomainContractError("Effect Result binding is incomplete")
        if effect["effectKind"] == "GLYPH_REVEAL":
            if result_ref is not None:
                raise RenderDomainContractError("Glyph stage cannot invent a Result")
        elif result_ref is None:
            raise RenderDomainContractError("deterministic Effect Result is required")
        result["effectBinding"] = effect

    if expected_kind == "VIDEO":
        if not assets or any(item is not None for item in (cue, stem, validation, effect)):
            raise RenderDomainContractError("VIDEO Composition binding is incomplete")
    elif expected_kind == "AUDIO":
        if not assets or stem is None or validation is None or cue is not None or effect is not None:
            raise RenderDomainContractError("AUDIO Composition binding is incomplete")
    elif expected_kind == "SUBTITLE":
        if not assets or cue is None or stem is None or validation is None or effect is not None:
            raise RenderDomainContractError("SUBTITLE Composition binding is incomplete")
    elif expected_kind == "EFFECT":
        if not assets or effect is None or any(item is not None for item in (cue, stem, validation)):
            raise RenderDomainContractError("EFFECT Composition binding is incomplete")
    return result


_COMPOSITION_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "compositionRef",
        "compositionVersionRef",
        "versionNumber",
        "parentCompositionVersionRef",
        "parentCompositionVersionDigest",
        "timelineRef",
        "timelineVersionRef",
        "timelineVersionNumber",
        "timelineVersionDigest",
        "videoTrackBindings",
        "audioTrackBindings",
        "subtitleTrackBindings",
        "effectTrackBindings",
        "clipOrderDigest",
        "transitionPlanDigest",
        "transformPlanDigest",
        "maskLayerPlanDigest",
        "audioMixPlanDigest",
        "subtitlePlanDigest",
        "effectResultSetDigest",
        "compositionGraphDigest",
        "createdAt",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_COMPOSITION_VERSION_COMMAND_FIELDS = _COMPOSITION_VERSION_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _plan_digests(value: Mapping[str, Any]) -> dict[str, str]:
    def plan_digest(kind: str, items: Sequence[Any]) -> str:
        return _digest(
            {
                "schemaVersion": f"v5.m13-composition-{kind}-plan.v1",
                "items": list(items),
            }
        )

    bindings = [
        item
        for field in (
            "videoTrackBindings",
            "audioTrackBindings",
            "subtitleTrackBindings",
            "effectTrackBindings",
        )
        for item in value[field]
    ]
    clip_order = [
        {
            "trackOrder": item["trackOrder"],
            "trackRef": item["trackRef"],
            "trackDigest": item["trackDigest"],
            "timelineStartFrameInclusive": item["timelineStartFrameInclusive"],
            "timelineEndFrameExclusive": item["timelineEndFrameExclusive"],
            "layer": item["layer"],
            "zOrder": item["zOrder"],
            "clipRef": item["clipRef"],
            "clipDigest": item["clipDigest"],
        }
        for item in sorted(
            bindings,
            key=lambda item: (
                item["trackOrder"],
                item["timelineStartFrameInclusive"],
                item["layer"],
                item["zOrder"],
                item["clipRef"],
            ),
        )
    ]
    transition = [
        {
            "clipRef": item["clipRef"],
            "clipDigest": item["clipDigest"],
            "transitionIn": item["transitionIn"],
            "transitionOut": item["transitionOut"],
            "speed": item["speed"],
        }
        for item in bindings
    ]
    transform = [
        {
            "clipRef": item["clipRef"],
            "clipDigest": item["clipDigest"],
            "transform": item["transform"],
        }
        for item in bindings
    ]
    masks = [
        {
            "clipRef": item["clipRef"],
            "clipDigest": item["clipDigest"],
            "layer": item["layer"],
            "zOrder": item["zOrder"],
            "maskBindings": item["maskBindings"],
        }
        for item in bindings
    ]
    audio = [
        {
            "bindingDigest": item["bindingDigest"],
            "sourceBinding": item["sourceBinding"],
            "stemBinding": item["stemBinding"],
            "technicalValidationBinding": item["technicalValidationBinding"],
        }
        for item in value["audioTrackBindings"]
    ]
    subtitle = [
        {
            "bindingDigest": item["bindingDigest"],
            "sourceBinding": item["sourceBinding"],
            "audioCueBinding": item["audioCueBinding"],
            "stemBinding": item["stemBinding"],
        }
        for item in value["subtitleTrackBindings"]
    ]
    effects = [
        {
            "bindingDigest": item["bindingDigest"],
            "effectBinding": item["effectBinding"],
            "sourceAssetVersions": item["sourceAssetVersions"],
        }
        for item in value["effectTrackBindings"]
    ]
    result = {
        "clipOrderDigest": plan_digest("clip-order", clip_order),
        "transitionPlanDigest": plan_digest("transition", transition),
        "transformPlanDigest": plan_digest("transform", transform),
        "maskLayerPlanDigest": plan_digest("mask-layer", masks),
        "audioMixPlanDigest": plan_digest("audio-mix", audio),
        "subtitlePlanDigest": plan_digest("subtitle", subtitle),
        "effectResultSetDigest": plan_digest("effect-result-set", effects),
    }
    result["compositionGraphDigest"] = _digest(
        {
            "timelineRef": value["timelineRef"],
            "timelineVersionRef": value["timelineVersionRef"],
            "timelineVersionNumber": value["timelineVersionNumber"],
            "timelineVersionDigest": value["timelineVersionDigest"],
            "bindingDigests": [item["bindingDigest"] for item in bindings],
            **result,
        }
    )
    return result


def _validate_composition_version_mapping(
    value: Any,
    *,
    predecessor: Any | None = None,
    _allow_orphan_lineage: bool = False,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _COMPOSITION_VERSION_FIELDS, "CompositionVersion"
    )
    if result["schemaVersion"] != COMPOSITION_VERSION_SCHEMA_VERSION:
        raise RenderDomainContractError("CompositionVersion schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "compositionRef",
        "compositionVersionRef",
        "timelineRef",
        "timelineVersionRef",
    ):
        _ref(result[field], field)
    version = _integer(result["versionNumber"], "versionNumber", minimum=1)
    _integer(result["timelineVersionNumber"], "timelineVersionNumber", minimum=1)
    _digest_value(result["timelineVersionDigest"], "timelineVersionDigest")
    parent_ref = _optional_ref(
        result["parentCompositionVersionRef"], "parentCompositionVersionRef"
    )
    parent_digest = _optional_digest(
        result["parentCompositionVersionDigest"],
        "parentCompositionVersionDigest",
    )
    if (parent_ref is None) != (parent_digest is None):
        raise RenderDomainContractError("CompositionVersion predecessor is incomplete")
    if version == 1:
        if parent_ref is not None or predecessor is not None:
            raise RenderDomainContractError("initial CompositionVersion has a predecessor")
    else:
        if predecessor is None and not _allow_orphan_lineage:
            raise RenderDomainContractError("CompositionVersion predecessor is required")
        if predecessor is not None:
            previous = _validate_composition_version_mapping(
                predecessor,
                _allow_orphan_lineage=True,
            )
            if (
                previous["compositionRef"] != result["compositionRef"]
                or previous["versionNumber"] + 1 != version
                or previous["compositionVersionRef"] != parent_ref
                or previous["payloadDigest"] != parent_digest
            ):
                raise RenderDomainStaleInputError(
                    "CompositionVersion predecessor is stale"
                )
    binding_fields = {
        "videoTrackBindings": "VIDEO",
        "audioTrackBindings": "AUDIO",
        "subtitleTrackBindings": "SUBTITLE",
        "effectTrackBindings": "EFFECT",
    }
    for field, kind in binding_fields.items():
        selected = result[field]
        if not isinstance(selected, list) or not selected:
            raise RenderDomainContractError(f"{field} must not be empty")
        validated = [
            _validate_track_binding(item, kind, index)
            for index, item in enumerate(selected)
        ]
        if validated != sorted(
            validated,
            key=lambda item: (
                item["trackOrder"],
                item["timelineStartFrameInclusive"],
                item["layer"],
                item["zOrder"],
                item["clipRef"],
            ),
        ):
            raise RenderDomainContractError(f"{field} is not canonical")
        result[field] = validated
    effects = [item["effectBinding"] for item in result["effectTrackBindings"]]
    if (
        len(effects) != len(REQUIRED_EFFECT_KINDS)
        or {item["effectKind"] for item in effects} != REQUIRED_EFFECT_KINDS
    ):
        raise RenderDomainContractError("CompositionVersion does not bind M13 8/8")
    expected_plans = _plan_digests(result)
    for field, expected in expected_plans.items():
        if result[field] != expected:
            raise RenderDomainStaleInputError(f"{field} is stale")
    _timestamp(result["createdAt"])
    if (
        result["provenance"] != COMPOSITION_PROVENANCE
        or result["publicationAllowed"] is not False
    ):
        raise RenderDomainContractError("CompositionVersion authority state is invalid")
    _reject_composition_authority_keys(result)
    return result


def build_composition_version(
    command: Mapping[str, Any],
    *,
    predecessor: Any | None = None,
) -> dict[str, Any]:
    selected = _closed(
        command,
        _COMPOSITION_VERSION_COMMAND_FIELDS,
        "CompositionVersion command",
    )
    expected_plans = _plan_digests(selected)
    if any(selected[field] != expected for field, expected in expected_plans.items()):
        raise RenderDomainContractError("CompositionVersion plan digests are derived")
    return _validate_composition_version_mapping(
        _seal({"schemaVersion": COMPOSITION_VERSION_SCHEMA_VERSION, **selected}),
        predecessor=predecessor,
    )


def seal_composition_track_binding(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _TRACK_BINDING_FIELDS - frozenset({"schemaVersion", "bindingDigest"})
    selected = _closed(command, fields, "Composition track binding command")
    value = {
        "schemaVersion": COMPOSITION_TRACK_BINDING_SCHEMA_VERSION,
        **selected,
    }
    value["bindingDigest"] = _digest(value)
    return _validate_track_binding(value, str(value["trackKind"]), 0)


def composition_plan_digests(command: Mapping[str, Any]) -> dict[str, str]:
    """Return all derived plan digests for a trusted server projection."""

    required = {
        "timelineRef",
        "timelineVersionRef",
        "timelineVersionNumber",
        "timelineVersionDigest",
        "videoTrackBindings",
        "audioTrackBindings",
        "subtitleTrackBindings",
        "effectTrackBindings",
    }
    if not isinstance(command, Mapping) or not required.issubset(command):
        raise RenderDomainContractError("Composition plan input is invalid")
    return _plan_digests(command)


def validate_composition_version(
    value: Any,
    *,
    predecessor: Any | None = None,
) -> "CompositionVersion":
    return CompositionVersion._from_validated(
        _validate_composition_version_mapping(value, predecessor=predecessor)
    )


class CompositionVersion(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "CompositionVersion":
        return validate_composition_version(value)


_SAFE_AREA_FIELDS = frozenset(
    {"leftPixels", "topPixels", "rightPixels", "bottomPixels"}
)
_OUTPUT_PROFILE_FIELDS = frozenset(
    {
        "profileRef",
        "width",
        "height",
        "frameRateNumerator",
        "frameRateDenominator",
        "pixelAspectRatioNumerator",
        "pixelAspectRatioDenominator",
        "resizeMode",
        "backgroundPolicy",
        "safeArea",
    }
)
_VIDEO_ENCODING_FIELDS = frozenset(
    {
        "codec",
        "pixelFormat",
        "qualityMode",
        "qualityValue",
        "profile",
        "level",
        "gopFrames",
        "deterministicThreadPolicy",
    }
)
_COLOR_METADATA_FIELDS = frozenset(
    {"colorPrimaries", "colorTransfer", "colorSpace", "colorRange"}
)
_AUDIO_ENCODING_FIELDS = frozenset(
    {"enabled", "codec", "sampleRate", "channelCount", "bitrate"}
)
_RENDER_TOOLCHAIN_FIELDS = frozenset(
    {
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    }
)
_RENDER_MANIFEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "renderManifestRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "compositionVersionRef",
        "compositionVersionDigest",
        "outputProfile",
        "videoEncoding",
        "colorMetadata",
        "audioEncoding",
        "subtitleMode",
        "subtitleTimingDigest",
        "subtitleFontAssetVersionRef",
        "subtitleFontAssetVersionDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
        "decodedFramePixelDigestSpec",
        "pcmContentDigestSpec",
        "subtitleTimingDigestSpec",
        "publicationAllowed",
        "masterState",
        "exportState",
        "createdAt",
        "payloadDigest",
    }
)
_RENDER_MANIFEST_COMMAND_FIELDS = _RENDER_MANIFEST_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def validate_render_toolchain_identity(value: Any) -> dict[str, str]:
    result = _closed(value, _RENDER_TOOLCHAIN_FIELDS, "render toolchain identity")
    _ref(result["rendererIdentity"], "rendererIdentity")
    _ref(result["rendererVersion"], "rendererVersion")
    _digest_value(result["ffmpegBinaryDigest"], "ffmpegBinaryDigest")
    _digest_value(result["ffprobeBinaryDigest"], "ffprobeBinaryDigest")
    return result


def _validate_output_profile(value: Any) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_PROFILE_FIELDS, "Render outputProfile")
    _ref(result["profileRef"], "profileRef")
    width = _integer(result["width"], "width", minimum=2, maximum=131_072)
    height = _integer(result["height"], "height", minimum=2, maximum=131_072)
    if width % 2 or height % 2:
        raise RenderDomainContractError("H264 output dimensions must be even")
    numerator = _integer(
        result["frameRateNumerator"],
        "frameRateNumerator",
        minimum=1,
        maximum=1_000_000,
    )
    denominator = _integer(
        result["frameRateDenominator"],
        "frameRateDenominator",
        minimum=1,
        maximum=1_000_000,
    )
    if gcd(numerator, denominator) != 1 or numerator > 240 * denominator:
        raise RenderDomainContractError("frame rate is invalid")
    par_numerator = _integer(
        result["pixelAspectRatioNumerator"],
        "pixelAspectRatioNumerator",
        minimum=1,
    )
    par_denominator = _integer(
        result["pixelAspectRatioDenominator"],
        "pixelAspectRatioDenominator",
        minimum=1,
    )
    if gcd(par_numerator, par_denominator) != 1:
        raise RenderDomainContractError("pixel aspect ratio is not reduced")
    if result["resizeMode"] not in RESIZE_MODES:
        raise RenderDomainContractError("resizeMode is invalid")
    if result["backgroundPolicy"] not in BACKGROUND_POLICIES:
        raise RenderDomainContractError("backgroundPolicy is invalid")
    safe_area = _closed(result["safeArea"], _SAFE_AREA_FIELDS, "safeArea")
    for field in _SAFE_AREA_FIELDS:
        _integer(safe_area[field], field, maximum=max(width, height))
    if (
        safe_area["leftPixels"] + safe_area["rightPixels"] >= width
        or safe_area["topPixels"] + safe_area["bottomPixels"] >= height
    ):
        raise RenderDomainContractError("safeArea exceeds output dimensions")
    result["safeArea"] = safe_area
    return result


def _validate_video_encoding(value: Any) -> dict[str, Any]:
    result = _closed(value, _VIDEO_ENCODING_FIELDS, "videoEncoding")
    if (
        result["codec"] not in VIDEO_CODECS
        or result["pixelFormat"] not in VIDEO_PIXEL_FORMATS
        or result["qualityMode"] not in VIDEO_QUALITY_MODES
        or result["profile"] not in VIDEO_PROFILES
        or result["level"] not in VIDEO_LEVELS
        or result["deterministicThreadPolicy"]
        not in DETERMINISTIC_THREAD_POLICIES
    ):
        raise RenderDomainContractError("videoEncoding is unsupported")
    _integer(result["qualityValue"], "qualityValue", maximum=51)
    _integer(result["gopFrames"], "gopFrames", minimum=1, maximum=10_000)
    return result


def _validate_color_metadata(value: Any) -> dict[str, Any]:
    result = _closed(value, _COLOR_METADATA_FIELDS, "colorMetadata")
    if (
        result["colorPrimaries"] not in COLOR_PRIMARIES
        or result["colorTransfer"] not in COLOR_TRANSFERS
        or result["colorSpace"] not in COLOR_SPACES
        or result["colorRange"] not in COLOR_RANGES
    ):
        raise RenderDomainContractError("colorMetadata is unsupported")
    return result


def _validate_audio_encoding(value: Any) -> dict[str, Any]:
    result = _closed(value, _AUDIO_ENCODING_FIELDS, "audioEncoding")
    _boolean(result["enabled"], "audio enabled")
    if result["codec"] not in AUDIO_CODECS:
        raise RenderDomainContractError("audio codec is unsupported")
    if result["enabled"]:
        if result["codec"] != "AAC":
            raise RenderDomainContractError("enabled audio requires AAC")
        _integer(result["sampleRate"], "sampleRate", minimum=8_000, maximum=384_000)
        _integer(result["channelCount"], "channelCount", minimum=1, maximum=8)
        _integer(result["bitrate"], "bitrate", minimum=8_000, maximum=1_536_000)
    elif (
        result["codec"] != "NONE"
        or result["sampleRate"] != 0
        or result["channelCount"] != 0
        or result["bitrate"] != 0
    ):
        raise RenderDomainContractError("disabled audio must use the NONE contract")
    return result


def _validate_render_manifest_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _RENDER_MANIFEST_FIELDS, "RenderManifest")
    if result["schemaVersion"] != RENDER_MANIFEST_SCHEMA_VERSION:
        raise RenderDomainContractError("RenderManifest schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "renderManifestRef",
        "timelineVersionRef",
        "compositionVersionRef",
        "rendererIdentity",
        "rendererVersion",
    ):
        _ref(result[field], field)
    for field in (
        "timelineVersionDigest",
        "compositionVersionDigest",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    ):
        _digest_value(result[field], field)
    result["outputProfile"] = _validate_output_profile(result["outputProfile"])
    result["videoEncoding"] = _validate_video_encoding(result["videoEncoding"])
    result["colorMetadata"] = _validate_color_metadata(result["colorMetadata"])
    result["audioEncoding"] = _validate_audio_encoding(result["audioEncoding"])
    mode = result["subtitleMode"]
    if mode not in SUBTITLE_MODES:
        raise RenderDomainContractError("subtitleMode is invalid")
    timing = _optional_digest(result["subtitleTimingDigest"], "subtitleTimingDigest")
    font_ref = _optional_ref(
        result["subtitleFontAssetVersionRef"],
        "subtitleFontAssetVersionRef",
    )
    font_digest = _optional_digest(
        result["subtitleFontAssetVersionDigest"],
        "subtitleFontAssetVersionDigest",
    )
    if (font_ref is None) != (font_digest is None):
        raise RenderDomainContractError("subtitle FONT binding is incomplete")
    if mode == "NONE":
        if timing is not None or font_ref is not None:
            raise RenderDomainContractError("NONE subtitle mode has no timing or FONT")
    elif mode == "SIDECAR":
        if timing is None or font_ref is not None:
            raise RenderDomainContractError("SIDECAR subtitle binding is invalid")
    elif timing is None or font_ref is None:
        raise RenderDomainContractError("BURN_IN requires timing and canonical FONT")
    if result["decodedFramePixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2:
        raise RenderDomainContractError("decoded pixel digest spec is unsupported")
    if result["pcmContentDigestSpec"] != PCM_CONTENT_DIGEST_SPEC:
        raise RenderDomainContractError("PCM digest spec is unsupported")
    if result["subtitleTimingDigestSpec"] != SUBTITLE_TIMING_DIGEST_SPEC:
        raise RenderDomainContractError("subtitle timing digest spec is unsupported")
    if (
        result["publicationAllowed"] is not False
        or result["masterState"] != "NOT_CREATED"
        or result["exportState"] != "NOT_CREATED"
    ):
        raise RenderDomainContractError("RenderManifest lifecycle state is invalid")
    _timestamp(result["createdAt"])
    return result


def build_render_manifest(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(
        command,
        _RENDER_MANIFEST_COMMAND_FIELDS,
        "RenderManifest command",
    )
    return _validate_render_manifest_mapping(
        _seal({"schemaVersion": RENDER_MANIFEST_SCHEMA_VERSION, **selected})
    )


def validate_render_manifest(value: Any) -> "RenderManifest":
    return RenderManifest.from_mapping(value)


class RenderManifest(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RenderManifest":
        return cls._from_validated(_validate_render_manifest_mapping(value))


_SUBTITLE_CUE_FIELDS = frozenset(
    {
        "cueRef",
        "clipRef",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "text",
        "textDigest",
        "language",
        "wordTiming",
    }
)
_SUBTITLE_WORD_FIELDS = frozenset(
    {
        "wordRef",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "text",
        "textDigest",
    }
)


def canonical_subtitle_timing(
    value: Any,
    *,
    include_text: bool = True,
) -> list[dict[str, Any]]:
    """Validate and canonicalize the exact frame-addressed subtitle signal."""

    if not isinstance(value, list):
        raise RenderDomainContractError("subtitle cues must be a list")
    cues: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        cue = _closed(item, _SUBTITLE_CUE_FIELDS, f"subtitle cue[{index}]")
        for field in ("cueRef", "clipRef"):
            _ref(cue[field], field)
        start = _integer(
            cue["timelineStartFrameInclusive"],
            "subtitle cue start frame",
        )
        end = _integer(
            cue["timelineEndFrameExclusive"],
            "subtitle cue end frame",
            minimum=1,
        )
        if start >= end:
            raise RenderDomainContractError("subtitle cue frame range is invalid")
        text = cue["text"]
        if not isinstance(text, str) or not text or text != text.strip():
            raise RenderDomainContractError("subtitle cue text is invalid")
        from hashlib import sha256

        if cue["textDigest"] != sha256(text.encode("utf-8")).hexdigest():
            raise RenderDomainStaleInputError("subtitle cue text digest is stale")
        _ref(cue["language"], "subtitle language")
        raw_words = cue["wordTiming"]
        if not isinstance(raw_words, list):
            raise RenderDomainContractError("subtitle wordTiming is invalid")
        words: list[dict[str, Any]] = []
        for word_index, raw_word in enumerate(raw_words):
            word = _closed(
                raw_word,
                _SUBTITLE_WORD_FIELDS,
                f"subtitle cue[{index}] word[{word_index}]",
            )
            _ref(word["wordRef"], "wordRef")
            word_start = _integer(
                word["timelineStartFrameInclusive"], "word start frame"
            )
            word_end = _integer(
                word["timelineEndFrameExclusive"],
                "word end frame",
                minimum=1,
            )
            word_text = word["text"]
            if (
                word_start < start
                or word_end > end
                or word_start >= word_end
                or not isinstance(word_text, str)
                or not word_text
                or word["textDigest"]
                != sha256(word_text.encode("utf-8")).hexdigest()
            ):
                raise RenderDomainStaleInputError(
                    "subtitle word timing authority is stale"
                )
            words.append(word)
        if words != sorted(
            words,
            key=lambda word: (
                word["timelineStartFrameInclusive"],
                word["timelineEndFrameExclusive"],
                word["wordRef"],
            ),
        ):
            raise RenderDomainContractError("subtitle word timing is not canonical")
        cue["wordTiming"] = words
        cues.append(cue)
    if cues != sorted(
        cues,
        key=lambda cue: (
            cue["timelineStartFrameInclusive"],
            cue["timelineEndFrameExclusive"],
            cue["clipRef"],
        ),
    ):
        raise RenderDomainContractError("subtitle cues are not canonical")
    if include_text:
        return cues
    return [
        {
            **{key: deepcopy(item[key]) for key in item if key != "text"},
            "wordTiming": [
                {key: deepcopy(word[key]) for key in word if key != "text"}
                for word in item["wordTiming"]
            ],
        }
        for item in cues
    ]


def canonical_subtitle_timing_digest(value: Any) -> str:
    return _digest(
        {
            "schemaVersion": "v5.m13-canonical-subtitle-timing.v1",
            "cues": canonical_subtitle_timing(value, include_text=False),
        }
    )


_RUNTIME_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "runtimeEvidenceRef",
        "executionRequestRef",
        "executionRequestDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
        "gpuUsed",
        "providerUsed",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_RUNTIME_EVIDENCE_COMMAND_FIELDS = _RUNTIME_EVIDENCE_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_runtime_evidence_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _RUNTIME_EVIDENCE_FIELDS, "RenderRuntimeEvidence"
    )
    if result["schemaVersion"] != RENDER_RUNTIME_EVIDENCE_SCHEMA_VERSION:
        raise RenderDomainContractError("RenderRuntimeEvidence schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "runtimeEvidenceRef",
        "executionRequestRef",
        "rendererIdentity",
        "rendererVersion",
    ):
        _ref(result[field], field)
    for field in (
        "executionRequestDigest",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    ):
        _digest_value(result[field], field)
    if (
        result["gpuUsed"] is not False
        or result["providerUsed"] is not False
        or result["publicationAllowed"] is not False
    ):
        raise RenderDomainContractError("RenderRuntimeEvidence authority is invalid")
    _timestamp(result["createdAt"])
    return result


def build_render_runtime_evidence(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(
        command,
        _RUNTIME_EVIDENCE_COMMAND_FIELDS,
        "RenderRuntimeEvidence command",
    )
    return _validate_runtime_evidence_mapping(
        _seal(
            {
                "schemaVersion": RENDER_RUNTIME_EVIDENCE_SCHEMA_VERSION,
                **selected,
            }
        )
    )


def validate_render_runtime_evidence(value: Any) -> "RenderRuntimeEvidence":
    return RenderRuntimeEvidence.from_mapping(value)


class RenderRuntimeEvidence(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RenderRuntimeEvidence":
        return cls._from_validated(_validate_runtime_evidence_mapping(value))


_MEDIA_PROBE_FIELDS = frozenset(
    {
        "container",
        "videoCodec",
        "width",
        "height",
        "frameRate",
        "frameCount",
        "pixelFormat",
        "colorMetadata",
        "audioCodec",
        "audioSampleRate",
        "audioChannels",
        "audioSampleCount",
        "duration",
    }
)
_MEDIA_PROBE_RATIONAL_FIELDS = frozenset({"numerator", "denominator"})
_MEDIA_PROBE_DURATION_FIELDS = frozenset({"samples", "sampleRate"})
_ARTIFACT_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "artifactEvidenceRef",
        "executionRequestRef",
        "executionRequestDigest",
        "renderManifestRef",
        "renderManifestDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "storageBindingRef",
        "mediaType",
        "byteSize",
        "fileDigest",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "pcmContentDigest",
        "pcmContentDigestSpec",
        "subtitleTimingDigest",
        "subtitleTimingDigestSpec",
        "mediaProbe",
        "subtitleSidecar",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_ARTIFACT_EVIDENCE_COMMAND_FIELDS = _ARTIFACT_EVIDENCE_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)
_SIDECAR_FIELDS = frozenset(
    {"mediaType", "byteSize", "fileDigest", "storageBindingRef"}
)


def _validate_media_probe(value: Any) -> dict[str, Any]:
    result = _closed(value, _MEDIA_PROBE_FIELDS, "Render mediaProbe")
    for field in ("container", "videoCodec", "pixelFormat", "audioCodec"):
        _ref(result[field], f"mediaProbe.{field}")
    for field in ("width", "height", "frameCount"):
        _integer(result[field], f"mediaProbe.{field}", minimum=1)
    _integer(result["audioSampleRate"], "audioSampleRate", minimum=1)
    _integer(result["audioChannels"], "audioChannels", minimum=1)
    _integer(result["audioSampleCount"], "audioSampleCount", minimum=1)
    frame_rate = _closed(
        result["frameRate"],
        _MEDIA_PROBE_RATIONAL_FIELDS,
        "mediaProbe.frameRate",
    )
    _integer(frame_rate["numerator"], "frameRate.numerator", minimum=1)
    _integer(frame_rate["denominator"], "frameRate.denominator", minimum=1)
    duration = _closed(
        result["duration"],
        _MEDIA_PROBE_DURATION_FIELDS,
        "mediaProbe.duration",
    )
    _integer(duration["samples"], "duration.samples", minimum=1)
    _integer(duration["sampleRate"], "duration.sampleRate", minimum=1)
    result["colorMetadata"] = _validate_color_metadata(result["colorMetadata"])
    result["frameRate"] = frame_rate
    result["duration"] = duration
    if (
        result["container"] != "mp4"
        or result["videoCodec"] != "h264"
        or result["pixelFormat"] != "yuv420p"
        or result["audioCodec"] != "aac"
        or result["audioSampleRate"] != 48_000
        or result["audioChannels"] != 2
        or duration["sampleRate"] != result["audioSampleRate"]
        or duration["samples"] != result["audioSampleCount"]
    ):
        raise RenderDomainContractError("Render mediaProbe is unsupported")
    return result


def _validate_artifact_evidence_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _ARTIFACT_EVIDENCE_FIELDS, "RenderArtifactEvidence"
    )
    if result["schemaVersion"] != RENDER_ARTIFACT_EVIDENCE_SCHEMA_VERSION:
        raise RenderDomainContractError("RenderArtifactEvidence schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "artifactEvidenceRef",
        "executionRequestRef",
        "renderManifestRef",
        "runtimeEvidenceRef",
        "storageBindingRef",
        "mediaType",
    ):
        _ref(result[field], field)
    for field in (
        "executionRequestDigest",
        "renderManifestDigest",
        "runtimeEvidenceDigest",
        "fileDigest",
        "decodedFramePixelDigest",
        "pcmContentDigest",
        "subtitleTimingDigest",
    ):
        _digest_value(result[field], field)
    _integer(result["byteSize"], "byteSize", minimum=1, maximum=4_000_000_000)
    if result["decodedFramePixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2:
        raise RenderDomainContractError("decoded pixel digest spec is unsupported")
    if result["pcmContentDigestSpec"] != PCM_CONTENT_DIGEST_SPEC:
        raise RenderDomainContractError("PCM digest spec is unsupported")
    if result["subtitleTimingDigestSpec"] != SUBTITLE_TIMING_DIGEST_SPEC:
        raise RenderDomainContractError("subtitle timing digest spec is unsupported")
    result["mediaProbe"] = _validate_media_probe(result["mediaProbe"])
    sidecar = result["subtitleSidecar"]
    if sidecar is not None:
        sidecar = _closed(sidecar, _SIDECAR_FIELDS, "subtitleSidecar")
        _ref(sidecar["mediaType"], "subtitleSidecar.mediaType")
        _ref(sidecar["storageBindingRef"], "subtitleSidecar.storageBindingRef")
        _integer(sidecar["byteSize"], "subtitleSidecar.byteSize", minimum=1)
        _digest_value(sidecar["fileDigest"], "subtitleSidecar.fileDigest")
        result["subtitleSidecar"] = sidecar
    if result["publicationAllowed"] is not False:
        raise RenderDomainContractError("RenderArtifactEvidence cannot publish")
    _timestamp(result["createdAt"])
    return result


def build_render_artifact_evidence(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(
        command,
        _ARTIFACT_EVIDENCE_COMMAND_FIELDS,
        "RenderArtifactEvidence command",
    )
    return _validate_artifact_evidence_mapping(
        _seal(
            {
                "schemaVersion": RENDER_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
                **selected,
            }
        )
    )


def validate_render_artifact_evidence(value: Any) -> "RenderArtifactEvidence":
    return RenderArtifactEvidence.from_mapping(value)


class RenderArtifactEvidence(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RenderArtifactEvidence":
        return cls._from_validated(_validate_artifact_evidence_mapping(value))


_RENDER_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "renderResultRef",
        "executionRequestRef",
        "executionRequestDigest",
        "renderManifestRef",
        "renderManifestDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "state",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_RENDER_RESULT_COMMAND_FIELDS = _RENDER_RESULT_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_render_result_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _RENDER_RESULT_FIELDS, "RenderResult")
    if result["schemaVersion"] != RENDER_RESULT_SCHEMA_VERSION:
        raise RenderDomainContractError("RenderResult schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "renderResultRef",
        "executionRequestRef",
        "renderManifestRef",
        "runtimeEvidenceRef",
        "artifactEvidenceRef",
    ):
        _ref(result[field], field)
    for field in (
        "executionRequestDigest",
        "renderManifestDigest",
        "runtimeEvidenceDigest",
        "artifactEvidenceDigest",
    ):
        _digest_value(result[field], field)
    if result["state"] != "SUCCEEDED" or result["publicationAllowed"] is not False:
        raise RenderDomainContractError("RenderResult state is invalid")
    _timestamp(result["createdAt"])
    return result


def build_render_result(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(command, _RENDER_RESULT_COMMAND_FIELDS, "RenderResult command")
    return _validate_render_result_mapping(
        _seal({"schemaVersion": RENDER_RESULT_SCHEMA_VERSION, **selected})
    )


def validate_render_result(value: Any) -> "RenderResult":
    return RenderResult.from_mapping(value)


class RenderResult(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RenderResult":
        return cls._from_validated(_validate_render_result_mapping(value))


_RENDER_CANDIDATE_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "renderCandidateRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "compositionVersionRef",
        "compositionVersionDigest",
        "renderManifestRef",
        "renderManifestDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "renderResultRef",
        "renderResultDigest",
        "renderProfileRef",
        "storageBindingRef",
        "mediaType",
        "fileDigest",
        "byteSize",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "pcmContentDigest",
        "pcmContentDigestSpec",
        "subtitleTimingDigest",
        "subtitleTimingDigestSpec",
        "mediaProbe",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
        "state",
        "technicalValidationState",
        "qcState",
        "approvalState",
        "assetAdmissionState",
        "masterState",
        "exportState",
        "publicationAllowed",
        "createdAt",
        "payloadDigest",
    }
)
_RENDER_CANDIDATE_COMMAND_FIELDS = _RENDER_CANDIDATE_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_render_candidate_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _RENDER_CANDIDATE_FIELDS, "RenderCandidate")
    if result["schemaVersion"] != RENDER_CANDIDATE_SCHEMA_VERSION:
        raise RenderDomainContractError("RenderCandidate schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "projectRef",
        "seriesRef",
        "episodeRef",
        "renderCandidateRef",
        "timelineVersionRef",
        "compositionVersionRef",
        "renderManifestRef",
        "executionRequestRef",
        "runtimeEvidenceRef",
        "artifactEvidenceRef",
        "renderResultRef",
        "renderProfileRef",
        "storageBindingRef",
        "mediaType",
        "rendererIdentity",
        "rendererVersion",
    ):
        _ref(result[field], field)
    for field in (
        "timelineVersionDigest",
        "compositionVersionDigest",
        "renderManifestDigest",
        "executionRequestDigest",
        "runtimeEvidenceDigest",
        "artifactEvidenceDigest",
        "renderResultDigest",
        "fileDigest",
        "decodedFramePixelDigest",
        "pcmContentDigest",
        "subtitleTimingDigest",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    ):
        _digest_value(result[field], field)
    _integer(result["byteSize"], "byteSize", minimum=1, maximum=4_000_000_000)
    if (
        result["decodedFramePixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or result["pcmContentDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
        or result["subtitleTimingDigestSpec"] != SUBTITLE_TIMING_DIGEST_SPEC
    ):
        raise RenderDomainContractError("RenderCandidate digest spec is unsupported")
    result["mediaProbe"] = _validate_media_probe(result["mediaProbe"])
    required_states = {
        "state": "RENDERED_CANDIDATE",
        "technicalValidationState": "PASS",
        "qcState": "NOT_RUN",
        "approvalState": "NOT_REQUESTED",
        "assetAdmissionState": "NOT_ADMITTED",
        "masterState": "NOT_CREATED",
        "exportState": "NOT_CREATED",
        "publicationAllowed": False,
    }
    if any(result[field] != expected for field, expected in required_states.items()):
        raise RenderDomainContractError("RenderCandidate lifecycle state is invalid")
    _timestamp(result["createdAt"])
    return result


def build_render_candidate(command: Mapping[str, Any]) -> dict[str, Any]:
    selected = _closed(
        command, _RENDER_CANDIDATE_COMMAND_FIELDS, "RenderCandidate command"
    )
    return _validate_render_candidate_mapping(
        _seal({"schemaVersion": RENDER_CANDIDATE_SCHEMA_VERSION, **selected})
    )


def validate_render_candidate(value: Any) -> "RenderCandidate":
    return RenderCandidate.from_mapping(value)


class RenderCandidate(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "RenderCandidate":
        return cls._from_validated(_validate_render_candidate_mapping(value))


def render_manifest_digest_specs() -> dict[str, Any]:
    return {
        "decodedFramePixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
        "pcmContentDigestSpec": deepcopy(PCM_CONTENT_DIGEST_SPEC),
        "subtitleTimingDigestSpec": SUBTITLE_TIMING_DIGEST_SPEC,
    }


__all__ = [
    "AUDIO_CODECS",
    "BACKGROUND_POLICIES",
    "COMPOSITION_PROVENANCE",
    "COMPOSITION_SCHEMA_VERSION",
    "COMPOSITION_TRACK_BINDING_SCHEMA_VERSION",
    "COMPOSITION_VERSION_SCHEMA_VERSION",
    "Composition",
    "CompositionVersion",
    "RENDER_MANIFEST_SCHEMA_VERSION",
    "RENDER_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "RENDER_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "RENDER_RESULT_SCHEMA_VERSION",
    "RENDER_CANDIDATE_SCHEMA_VERSION",
    "REQUIRED_EFFECT_KINDS",
    "RESIZE_MODES",
    "RenderDomainContractError",
    "RenderDomainStaleInputError",
    "RenderManifest",
    "RenderRuntimeEvidence",
    "RenderArtifactEvidence",
    "RenderResult",
    "RenderCandidate",
    "SUBTITLE_MODES",
    "SUBTITLE_TIMING_DIGEST_SPEC",
    "VIDEO_CODECS",
    "build_composition",
    "build_composition_version",
    "build_render_manifest",
    "build_render_runtime_evidence",
    "build_render_artifact_evidence",
    "build_render_result",
    "build_render_candidate",
    "canonical_subtitle_timing",
    "canonical_subtitle_timing_digest",
    "composition_plan_digests",
    "render_manifest_digest_specs",
    "seal_composition_track_binding",
    "validate_composition",
    "validate_composition_version",
    "validate_render_manifest",
    "validate_render_runtime_evidence",
    "validate_render_artifact_evidence",
    "validate_render_result",
    "validate_render_candidate",
    "validate_render_toolchain_identity",
]
