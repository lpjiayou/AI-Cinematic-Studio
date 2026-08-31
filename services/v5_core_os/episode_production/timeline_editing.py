"""Immutable full-timeline editing contracts for M13-T1.

This module is an additive successor to :mod:`timeline_preview`.  It does not
reinterpret the accepted ``v5.timeline.v2`` evidence objects and it owns no
repository, database, renderer, preview, admission, or publication authority.
``K2DeliveryService`` remains the sole Timeline authority owner.

All wire objects are closed, immutable, canonically sealed mappings.  Time is
frame/sample/rational based; Python floats, arbitrary patches, expressions,
paths, shell fragments, and FFmpeg filters are never accepted as authority.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import gcd
import json
import re
from typing import Any, Callable, Mapping, Sequence

from .foundation import (
    EpisodeProductionError,
    IdempotencyConflictError,
    StaleInputError,
    UpstreamNotReadyError,
    _canonical_json,
    _digest,
    _required_ref,
)


TIMELINE_SCHEMA_VERSION = "v5.timeline.v3"
TIMELINE_VERSION_SCHEMA_VERSION = "v5.timeline-version.v3"
TIMELINE_TRACK_SCHEMA_VERSION = "v5.timeline-track.v2"
TIMELINE_CLIP_SCHEMA_VERSION = "v5.timeline-clip.v2"
TIMELINE_CLIP_SCHEMA_VERSION_V3 = "v5.timeline-clip.v3"
TRANSITION_SPEC_SCHEMA_VERSION = "v5.timeline-transition-spec.v1"
SPEED_SPEC_SCHEMA_VERSION = "v5.timeline-speed-spec.v1"
TRANSFORM_SPEC_SCHEMA_VERSION = "v5.timeline-transform-spec.v1"
MASK_BINDING_SCHEMA_VERSION = "v5.timeline-mask-binding.v1"
OUTPUT_PROFILE_BINDING_SCHEMA_VERSION = (
    "v5.timeline-output-profile-binding.v1"
)
TIMELINE_EDIT_COMMAND_SCHEMA_VERSION = "v5.timeline-edit-command.v1"
TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2 = "v5.timeline-edit-command.v2"
TIMELINE_TRACK_SNAPSHOT_SCHEMA_VERSION = "v5.timeline-track-snapshot.v1"
TIMELINE_CLIP_SNAPSHOT_SCHEMA_VERSION = "v5.timeline-clip-snapshot.v1"
TIMELINE_SNAPSHOT_SCHEMA_VERSION = "v5.timeline-snapshot.v1"

TIMELINE_SCHEMA_VERSION_V3 = TIMELINE_SCHEMA_VERSION
TIMELINE_VERSION_SCHEMA_VERSION_V3 = TIMELINE_VERSION_SCHEMA_VERSION
TIMELINE_TRACK_SCHEMA_VERSION_V2 = TIMELINE_TRACK_SCHEMA_VERSION
TIMELINE_CLIP_SCHEMA_VERSION_V2 = TIMELINE_CLIP_SCHEMA_VERSION

LEGACY_TIMELINE_SCHEMA_VERSION = "v5.timeline.v2"
LEGACY_TIMELINE_VERSION_SCHEMA_VERSION = "v5.timeline-version.v2"

TIMELINE_TRACK_KINDS = ("VIDEO", "AUDIO", "SUBTITLE", "EFFECT")
CLIP_KIND_BY_TRACK = {
    "VIDEO": frozenset({"VIDEO"}),
    "AUDIO": frozenset({"AUDIO"}),
    "SUBTITLE": frozenset({"SUBTITLE"}),
    "EFFECT": frozenset({"EFFECT"}),
}
TRANSITION_KINDS = (
    "CUT",
    "CROSSFADE",
    "FADE_IN",
    "FADE_OUT",
    "DIP_TO_BLACK",
)
TRANSITION_CURVES = ("LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT")
TRANSITION_ALIGNMENTS = ("START", "CENTER", "END")
BLEND_MODES = (
    "NORMAL",
    "MULTIPLY",
    "SCREEN",
    "OVERLAY",
    "ADD",
    "DARKEN",
    "LIGHTEN",
    "GRAZING_LIGHT_RELIEF",
)
MASK_MODES = ("ALPHA", "LUMA", "INVERTED_ALPHA", "INVERTED_LUMA")
LANE_POLICIES = ("EXCLUSIVE", "LAYERED", "LAYERED_Z_ORDER", "MIX")
PERSPECTIVE_MODES = ("NONE", "MATRIX_3X3", "FIXED_QUAD")
EDIT_OPERATIONS = (
    "INSERT_CLIP",
    "REMOVE_CLIP",
    "MOVE_CLIP",
    "TRIM_CLIP",
    "SPLIT_CLIP",
    "ENABLE_CLIP",
    "DISABLE_CLIP",
    "REORDER_TRACK",
    "SET_TRANSITION",
    "SET_SPEED",
    "SET_TRANSFORM",
    "SET_MASKS",
    "SET_SAFE_AREA",
    "SET_OUTPUT_PROFILES",
)
TIMELINE_EDIT_OPERATIONS_V2 = ("BIND_EFFECT_RESULT",)
M13_E1_DETERMINISTIC_EFFECT_KINDS = frozenset(
    {"SCRATCH_REVEAL", "LIGHT_SWEEP", "LOCAL_EXPOSURE"}
)
M13_E2_DETERMINISTIC_EFFECT_KINDS = frozenset(
    {"FLAME_EXTINGUISH", "SMOKE"}
)
DETERMINISTIC_EFFECT_KINDS = (
    "SCRATCH_REVEAL",
    "LIGHT_SWEEP",
    "LOCAL_EXPOSURE",
    "FLAME_EXTINGUISH",
    "SMOKE",
)

TIMELINE_PROVENANCE = "V5_K2_DELIVERY_SERVICE"
MAX_DURATION_FRAMES = 10**9
MAX_CANVAS_DIMENSION = 131_072
MAX_SPEED_NUMERATOR = 64
MAX_SPEED_DENOMINATOR = 64
FIXED_OPACITY_SCALE = 1000

_SHA256 = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")
_SCOPE_FIELDS = (
    "workspaceRef",
    "projectRef",
    "seriesRef",
    "episodeRef",
    "productionRunRef",
)
_FORBIDDEN_KEY_PARTS = (
    "path",
    "storagekey",
    "filter",
    "expression",
    "python",
    "shell",
    "ffmpeg",
    "patch",
    "jsonpointer",
    "canonicalmutations",
    "publicationallowed",
    "approvalref",
)


class TimelineEditingContractError(EpisodeProductionError):
    code = "timeline_editing_contract_invalid"


class TimelineEditingAuthorityError(UpstreamNotReadyError):
    code = "timeline_editing_authority_required"


class TimelineEditingStaleInputError(StaleInputError):
    code = "timeline_editing_source_stale"


class TimelineEditingRangeError(TimelineEditingContractError):
    code = "timeline_editing_range_invalid"


class TimelineEditingConflictError(IdempotencyConflictError):
    code = "timeline_editing_idempotency_conflict"


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TimelineEditingContractError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise TimelineEditingContractError("payloadDigest is derived")
    _reject_floats(result)
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = result.pop("payloadDigest")
    _reject_floats(result)
    if not isinstance(supplied, str) or supplied != _digest(result):
        raise TimelineEditingStaleInputError(f"{label} payloadDigest is invalid")
    result["payloadDigest"] = supplied
    return result


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TimelineEditingContractError("float authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TimelineEditingContractError("object keys must be strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def _reject_forbidden_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            folded = str(key).replace("_", "").lower()
            if any(part in folded for part in _FORBIDDEN_KEY_PARTS):
                raise TimelineEditingContractError(f"{key} is forbidden")
            _reject_forbidden_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_keys(item)


def _ref(value: Any, field: str) -> str:
    try:
        result = _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise TimelineEditingContractError(f"{field} is invalid") from exc
    if (
        result.startswith(("/", "\\"))
        or re.match(r"[A-Za-z]:[\\/]", result) is not None
        or "://" in result
    ):
        raise TimelineEditingContractError(f"{field} cannot be a path or URL")
    return result


def _optional_ref(value: Any, field: str) -> str | None:
    return None if value is None else _ref(value, field)


def _digest_value(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise TimelineEditingContractError(f"{field} is invalid")
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
        raise TimelineEditingContractError(f"{field} is invalid")
    return value


def _signed_integer(value: Any, field: str, *, bound: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > bound:
        raise TimelineEditingContractError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not value and not allow_empty)
        or any(ord(character) < 32 for character in value)
    ):
        raise TimelineEditingContractError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str = "createdAt") -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimelineEditingContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None:
        raise TimelineEditingContractError(f"{field} must include a timezone")
    return text


def _scope(value: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(_ref(value.get(field), field) for field in _SCOPE_FIELDS)  # type: ignore[return-value]


def _rational(
    value: Any,
    field: str,
    *,
    allow_zero: bool = False,
    max_component: int = 10**9,
) -> dict[str, int]:
    result = _closed(value, frozenset({"numerator", "denominator"}), field)
    numerator = _integer(
        result["numerator"],
        f"{field}.numerator",
        minimum=0 if allow_zero else 1,
        maximum=max_component,
    )
    denominator = _integer(
        result["denominator"],
        f"{field}.denominator",
        minimum=1,
        maximum=max_component,
    )
    if gcd(numerator, denominator) != 1:
        raise TimelineEditingContractError(f"{field} must be reduced")
    return {"numerator": numerator, "denominator": denominator}


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


_TRANSITION_FIELDS = frozenset(
    {
        "schemaVersion",
        "transitionKind",
        "durationFrames",
        "curve",
        "alignment",
        "payloadDigest",
    }
)
_TRANSITION_COMMAND_FIELDS = frozenset(
    {"transitionKind", "durationFrames", "curve", "alignment"}
)


def _validate_transition_spec_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TRANSITION_FIELDS, "TransitionSpec")
    if result["schemaVersion"] != TRANSITION_SPEC_SCHEMA_VERSION:
        raise TimelineEditingContractError("TransitionSpec schema is unsupported")
    if result["transitionKind"] not in TRANSITION_KINDS:
        raise TimelineEditingContractError("transitionKind is invalid")
    duration = _integer(
        result["durationFrames"],
        "durationFrames",
        maximum=MAX_DURATION_FRAMES,
    )
    if result["curve"] not in TRANSITION_CURVES:
        raise TimelineEditingContractError("transition curve is invalid")
    if result["alignment"] not in TRANSITION_ALIGNMENTS:
        raise TimelineEditingContractError("transition alignment is invalid")
    if (result["transitionKind"] == "CUT") != (duration == 0):
        raise TimelineEditingRangeError("CUT alone must have zero duration")
    return result


def build_transition_spec(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _TRANSITION_COMMAND_FIELDS, "TransitionSpec command")
    return _validate_transition_spec_mapping(
        _seal({"schemaVersion": TRANSITION_SPEC_SCHEMA_VERSION, **value})
    )


def validate_transition_spec(value: Any) -> "TransitionSpec":
    return TransitionSpec._from_validated(_validate_transition_spec_mapping(value))


class TransitionSpec(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TransitionSpec":
        return cls._from_validated(_validate_transition_spec_mapping(value))


_SPEED_FIELDS = frozenset(
    {"schemaVersion", "numerator", "denominator", "payloadDigest"}
)
_SPEED_COMMAND_FIELDS = frozenset({"numerator", "denominator"})


def _validate_speed_spec_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _SPEED_FIELDS, "SpeedSpec")
    if result["schemaVersion"] != SPEED_SPEC_SCHEMA_VERSION:
        raise TimelineEditingContractError("SpeedSpec schema is unsupported")
    rational = _rational(
        {"numerator": result["numerator"], "denominator": result["denominator"]},
        "speed",
        max_component=max(MAX_SPEED_NUMERATOR, MAX_SPEED_DENOMINATOR),
    )
    if (
        rational["numerator"] > MAX_SPEED_NUMERATOR
        or rational["denominator"] > MAX_SPEED_DENOMINATOR
        or rational["numerator"] > 16 * rational["denominator"]
        or rational["denominator"] > 16 * rational["numerator"]
    ):
        raise TimelineEditingRangeError("speed is outside the closed range")
    return result


def build_speed_spec(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _SPEED_COMMAND_FIELDS, "SpeedSpec command")
    return _validate_speed_spec_mapping(
        _seal({"schemaVersion": SPEED_SPEC_SCHEMA_VERSION, **value})
    )


def validate_speed_spec(value: Any) -> "SpeedSpec":
    return SpeedSpec._from_validated(_validate_speed_spec_mapping(value))


class SpeedSpec(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "SpeedSpec":
        return cls._from_validated(_validate_speed_spec_mapping(value))


_TRANSFORM_FIELDS = frozenset(
    {
        "schemaVersion",
        "positionXPixels",
        "positionYPixels",
        "scaleX",
        "scaleY",
        "rotationMilliDegrees",
        "anchorXPixels",
        "anchorYPixels",
        "opacity",
        "perspectiveMode",
        "perspectiveMatrix",
        "perspectiveCorners",
        "payloadDigest",
    }
)
_TRANSFORM_COMMAND_FIELDS = _TRANSFORM_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)
_CORNER_FIELDS = frozenset({"xPixels", "yPixels"})


def _validate_transform_spec_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TRANSFORM_FIELDS, "TransformSpec")
    if result["schemaVersion"] != TRANSFORM_SPEC_SCHEMA_VERSION:
        raise TimelineEditingContractError("TransformSpec schema is unsupported")
    for field in ("positionXPixels", "positionYPixels", "anchorXPixels", "anchorYPixels"):
        _signed_integer(result[field], field, bound=MAX_CANVAS_DIMENSION * 4)
    scale_x = _rational(result["scaleX"], "scaleX", max_component=10**6)
    scale_y = _rational(result["scaleY"], "scaleY", max_component=10**6)
    if (
        scale_x["numerator"] > 64 * scale_x["denominator"]
        or scale_y["numerator"] > 64 * scale_y["denominator"]
    ):
        raise TimelineEditingRangeError("transform scale is outside the closed range")
    _signed_integer(
        result["rotationMilliDegrees"],
        "rotationMilliDegrees",
        bound=360_000,
    )
    _integer(result["opacity"], "opacity", maximum=FIXED_OPACITY_SCALE)
    mode = result["perspectiveMode"]
    if mode not in PERSPECTIVE_MODES:
        raise TimelineEditingContractError("perspectiveMode is invalid")
    matrix = result["perspectiveMatrix"]
    corners = result["perspectiveCorners"]
    if mode == "NONE":
        if matrix is not None or corners is not None:
            raise TimelineEditingContractError("NONE perspective has no coordinates")
    elif mode == "MATRIX_3X3":
        if (
            not isinstance(matrix, list)
            or len(matrix) != 9
            or corners is not None
        ):
            raise TimelineEditingContractError("perspective matrix is invalid")
        for index, component in enumerate(matrix):
            _signed_integer(component, f"perspectiveMatrix[{index}]", bound=10**9)
    else:
        if matrix is not None or not isinstance(corners, list) or len(corners) != 4:
            raise TimelineEditingContractError("perspective corners are invalid")
        for index, corner in enumerate(corners):
            point = _closed(corner, _CORNER_FIELDS, f"perspectiveCorners[{index}]")
            _signed_integer(point["xPixels"], "corner.xPixels", bound=MAX_CANVAS_DIMENSION * 4)
            _signed_integer(point["yPixels"], "corner.yPixels", bound=MAX_CANVAS_DIMENSION * 4)
    return result


def build_transform_spec(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _TRANSFORM_COMMAND_FIELDS, "TransformSpec command")
    return _validate_transform_spec_mapping(
        _seal({"schemaVersion": TRANSFORM_SPEC_SCHEMA_VERSION, **value})
    )


def validate_transform_spec(value: Any) -> "TransformSpec":
    return TransformSpec._from_validated(_validate_transform_spec_mapping(value))


class TransformSpec(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TransformSpec":
        return cls._from_validated(_validate_transform_spec_mapping(value))


_MASK_FIELDS = frozenset(
    {
        "schemaVersion",
        "maskAssetVersionRef",
        "maskAssetVersionDigest",
        "mode",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "transform",
        "payloadDigest",
    }
)
_MASK_COMMAND_FIELDS = _MASK_FIELDS - frozenset({"schemaVersion", "payloadDigest"})


def _validate_mask_binding_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _MASK_FIELDS, "MaskBinding")
    if result["schemaVersion"] != MASK_BINDING_SCHEMA_VERSION:
        raise TimelineEditingContractError("MaskBinding schema is unsupported")
    _ref(result["maskAssetVersionRef"], "maskAssetVersionRef")
    _digest_value(result["maskAssetVersionDigest"], "maskAssetVersionDigest")
    if result["mode"] not in MASK_MODES:
        raise TimelineEditingContractError("mask mode is invalid")
    start = _integer(
        result["frameRangeStartInclusive"],
        "frameRangeStartInclusive",
        maximum=MAX_DURATION_FRAMES,
    )
    end = _integer(
        result["frameRangeEndExclusive"],
        "frameRangeEndExclusive",
        minimum=1,
        maximum=MAX_DURATION_FRAMES,
    )
    if start >= end:
        raise TimelineEditingRangeError("mask frame range is invalid")
    _validate_transform_spec_mapping(result["transform"])
    return result


def build_mask_binding(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _MASK_COMMAND_FIELDS, "MaskBinding command")
    transform = (
        command["transform"].as_dict()
        if type(command["transform"]) is TransformSpec
        else deepcopy(command["transform"])
    )
    return _validate_mask_binding_mapping(
        _seal(
            {
                "schemaVersion": MASK_BINDING_SCHEMA_VERSION,
                **{key: value[key] for key in _MASK_COMMAND_FIELDS if key != "transform"},
                "transform": transform,
            }
        )
    )


def validate_mask_binding(value: Any) -> "MaskBinding":
    return MaskBinding._from_validated(_validate_mask_binding_mapping(value))


class MaskBinding(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MaskBinding":
        return cls._from_validated(_validate_mask_binding_mapping(value))


_OUTPUT_PROFILE_FIELDS = frozenset(
    {
        "schemaVersion",
        "outputProfileRef",
        "outputProfileDigest",
        "canvasWidth",
        "canvasHeight",
        "frameRate",
        "pixelAspectRatio",
        "displayAspectRatio",
        "payloadDigest",
    }
)
_OUTPUT_PROFILE_COMMAND_FIELDS = _OUTPUT_PROFILE_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_output_profile_binding_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _OUTPUT_PROFILE_FIELDS, "OutputProfileBinding")
    if result["schemaVersion"] != OUTPUT_PROFILE_BINDING_SCHEMA_VERSION:
        raise TimelineEditingContractError(
            "OutputProfileBinding schema is unsupported"
        )
    _ref(result["outputProfileRef"], "outputProfileRef")
    _digest_value(result["outputProfileDigest"], "outputProfileDigest")
    width = _integer(
        result["canvasWidth"],
        "canvasWidth",
        minimum=1,
        maximum=MAX_CANVAS_DIMENSION,
    )
    height = _integer(
        result["canvasHeight"],
        "canvasHeight",
        minimum=1,
        maximum=MAX_CANVAS_DIMENSION,
    )
    _rational(result["frameRate"], "frameRate", max_component=1_000_000)
    pixel = _rational(
        result["pixelAspectRatio"],
        "pixelAspectRatio",
        max_component=1_000_000,
    )
    display = _rational(
        result["displayAspectRatio"],
        "displayAspectRatio",
        max_component=MAX_CANVAS_DIMENSION * 1_000_000,
    )
    expected_numerator = width * pixel["numerator"]
    expected_denominator = height * pixel["denominator"]
    common = gcd(expected_numerator, expected_denominator)
    if display != {
        "numerator": expected_numerator // common,
        "denominator": expected_denominator // common,
    }:
        raise TimelineEditingRangeError("displayAspectRatio is not canonical")
    return result


def build_output_profile_binding(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(
        command,
        _OUTPUT_PROFILE_COMMAND_FIELDS,
        "OutputProfileBinding command",
    )
    return _validate_output_profile_binding_mapping(
        _seal({"schemaVersion": OUTPUT_PROFILE_BINDING_SCHEMA_VERSION, **value})
    )


def validate_output_profile_binding(value: Any) -> "OutputProfileBinding":
    return OutputProfileBinding._from_validated(
        _validate_output_profile_binding_mapping(value)
    )


class OutputProfileBinding(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "OutputProfileBinding":
        return cls._from_validated(_validate_output_profile_binding_mapping(value))


_TIMELINE_FIELDS = frozenset(
    {
        "schemaVersion",
        "timelineRef",
        *_SCOPE_FIELDS,
        "createdAt",
        "payloadDigest",
    }
)
_TIMELINE_COMMAND_FIELDS = _TIMELINE_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)


def _validate_timeline_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_FIELDS, "Timeline")
    if result["schemaVersion"] != TIMELINE_SCHEMA_VERSION:
        raise TimelineEditingContractError("Timeline schema is unsupported")
    _ref(result["timelineRef"], "timelineRef")
    _scope(result)
    _timestamp(result["createdAt"])
    return result


def build_timeline(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _TIMELINE_COMMAND_FIELDS, "Timeline command")
    return _validate_timeline_mapping(
        _seal({"schemaVersion": TIMELINE_SCHEMA_VERSION, **value})
    )


def validate_timeline(value: Any) -> "Timeline":
    return Timeline.from_mapping(value)


class Timeline(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "Timeline":
        return cls._from_validated(_validate_timeline_mapping(value))


_TRACK_FIELDS = frozenset(
    {
        "schemaVersion",
        "trackRef",
        "timelineVersionRef",
        "trackKind",
        "order",
        "enabled",
        "lanePolicy",
        "payloadDigest",
    }
)
_TRACK_COMMAND_FIELDS = _TRACK_FIELDS - frozenset({"schemaVersion", "payloadDigest"})


def _validate_timeline_track_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TRACK_FIELDS, "TimelineTrack")
    if result["schemaVersion"] != TIMELINE_TRACK_SCHEMA_VERSION:
        raise TimelineEditingContractError("TimelineTrack schema is unsupported")
    _ref(result["trackRef"], "trackRef")
    _ref(result["timelineVersionRef"], "timelineVersionRef")
    if result["trackKind"] not in TIMELINE_TRACK_KINDS:
        raise TimelineEditingContractError("trackKind is invalid")
    _integer(result["order"], "order", maximum=1024)
    if not isinstance(result["enabled"], bool):
        raise TimelineEditingContractError("track enabled is invalid")
    if result["lanePolicy"] not in LANE_POLICIES:
        raise TimelineEditingContractError("lanePolicy is invalid")
    return result


def build_timeline_track(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _TRACK_COMMAND_FIELDS, "TimelineTrack command")
    return _validate_timeline_track_mapping(
        _seal({"schemaVersion": TIMELINE_TRACK_SCHEMA_VERSION, **value})
    )


def validate_timeline_track(value: Any) -> "TimelineTrack":
    return TimelineTrack.from_mapping(value)


class TimelineTrack(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TimelineTrack":
        return cls._from_validated(_validate_timeline_track_mapping(value))


_VIDEO_SOURCE_FIELDS = frozenset(
    {
        "assetVersionRef",
        "assetVersionDigest",
        "sourceInFrameInclusive",
        "sourceOutFrameExclusive",
    }
)
_AUDIO_SOURCE_FIELDS = frozenset(
    {
        "audioAssetVersionRef",
        "audioAssetVersionDigest",
        "sourceStartSampleInclusive",
        "sourceEndSampleExclusive",
        "sampleRate",
        "stemMemberRef",
        "gainDb",
        "pan",
        "fadeInSamples",
        "fadeOutSamples",
    }
)
_SUBTITLE_SOURCE_FIELDS = frozenset(
    {
        "audioCueRef",
        "audioCueDigest",
        "scriptVersionRef",
        "scriptVersionDigest",
        "textStart",
        "textEndExclusive",
        "textDigest",
        "language",
        "wordTiming",
    }
)
_EFFECT_SOURCE_FIELDS = frozenset(
    {
        "effectRequirementRef",
        "effectRequirementDigest",
        "effectKind",
        "effectResultRef",
        "layer",
        "blendMode",
    }
)
_EFFECT_SOURCE_FIELDS_V3 = _EFFECT_SOURCE_FIELDS | frozenset(
    {"effectResultDigest"}
)
_WORD_TIMING_FIELDS = frozenset(
    {
        "wordRef",
        "textStart",
        "textEndExclusive",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "textDigest",
    }
)

_CLIP_FIELDS = frozenset(
    {
        "schemaVersion",
        "clipRef",
        "timelineVersionRef",
        "trackRef",
        "clipKind",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "enabled",
        "layer",
        "zOrder",
        "opacity",
        "blendMode",
        "sourceBinding",
        "transitionIn",
        "transitionOut",
        "speed",
        "transform",
        "maskBindings",
        "payloadDigest",
    }
)
_CLIP_COMMAND_FIELDS = _CLIP_FIELDS - frozenset({"schemaVersion", "payloadDigest"})

SourceAuthorityResolver = Callable[[str, str], Mapping[str, Any] | None]


def _deterministic_effect_kind(value: Mapping[str, Any]) -> Any:
    """Read one closed E1/E2 kind without weakening either source schema."""

    mode = value.get("effectMode")
    kind = value.get("effectKind")
    if mode is not None and kind is not None and mode != kind:
        return None
    return mode if mode is not None else kind


def _effect_result_is_bindable(
    value: Mapping[str, Any], *, effect_kind: str
) -> bool:
    if effect_kind in M13_E1_DETERMINISTIC_EFFECT_KINDS:
        return value.get("state") == "SUCCEEDED"
    if effect_kind in M13_E2_DETERMINISTIC_EFFECT_KINDS:
        return (
            value.get("state") == "COMPOSED_CANDIDATE"
            and value.get("assetAdmissionState") == "NOT_ADMITTED"
            and value.get("masterState") == "NOT_CREATED"
            and value.get("exportState") == "NOT_CREATED"
        )
    return False


def _validate_word_timing(value: Any, index: int) -> dict[str, Any]:
    result = _closed(value, _WORD_TIMING_FIELDS, f"wordTiming[{index}]")
    _ref(result["wordRef"], "wordRef")
    text_start = _integer(result["textStart"], "word textStart")
    text_end = _integer(result["textEndExclusive"], "word textEndExclusive", minimum=1)
    frame_start = _integer(
        result["timelineStartFrameInclusive"],
        "word timelineStartFrameInclusive",
        maximum=MAX_DURATION_FRAMES,
    )
    frame_end = _integer(
        result["timelineEndFrameExclusive"],
        "word timelineEndFrameExclusive",
        minimum=1,
        maximum=MAX_DURATION_FRAMES,
    )
    if text_start >= text_end or frame_start >= frame_end:
        raise TimelineEditingRangeError("wordTiming range is invalid")
    _digest_value(result["textDigest"], "word textDigest")
    return result


def _validate_source_binding(
    value: Any,
    clip_kind: str,
    *,
    clip_schema_version: str = TIMELINE_CLIP_SCHEMA_VERSION,
    source_resolver: SourceAuthorityResolver | None = None,
    scope: Mapping[str, str] | None = None,
    timeline_start_frame_inclusive: int | None = None,
    timeline_end_frame_exclusive: int | None = None,
    timeline_frame_rate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if clip_kind == "VIDEO":
        result = _closed(value, _VIDEO_SOURCE_FIELDS, "VIDEO sourceBinding")
        ref_field, digest_field, source_type = (
            "assetVersionRef",
            "assetVersionDigest",
            "ASSET_VERSION",
        )
        start = _integer(result["sourceInFrameInclusive"], "sourceInFrameInclusive")
        end = _integer(
            result["sourceOutFrameExclusive"],
            "sourceOutFrameExclusive",
            minimum=1,
            maximum=MAX_DURATION_FRAMES,
        )
        if start >= end:
            raise TimelineEditingRangeError("VIDEO source trim is invalid")
    elif clip_kind == "AUDIO":
        result = _closed(value, _AUDIO_SOURCE_FIELDS, "AUDIO sourceBinding")
        ref_field, digest_field, source_type = (
            "audioAssetVersionRef",
            "audioAssetVersionDigest",
            "AUDIO_ASSET_VERSION",
        )
        start = _integer(
            result["sourceStartSampleInclusive"],
            "sourceStartSampleInclusive",
        )
        end = _integer(
            result["sourceEndSampleExclusive"],
            "sourceEndSampleExclusive",
            minimum=1,
        )
        sample_rate = _integer(
            result["sampleRate"], "sampleRate", minimum=1, maximum=768_000
        )
        _ref(result["stemMemberRef"], "stemMemberRef")
        _signed_integer(result["gainDb"], "gainDb", bound=96)
        _signed_integer(result["pan"], "pan", bound=1000)
        fade_in = _integer(result["fadeInSamples"], "fadeInSamples")
        fade_out = _integer(result["fadeOutSamples"], "fadeOutSamples")
        if start >= end or fade_in + fade_out > end - start:
            raise TimelineEditingRangeError("AUDIO source sample range is invalid")
        if sample_rate <= 0:
            raise TimelineEditingRangeError("sampleRate is invalid")
    elif clip_kind == "SUBTITLE":
        result = _closed(value, _SUBTITLE_SOURCE_FIELDS, "SUBTITLE sourceBinding")
        ref_field, digest_field, source_type = (
            "audioCueRef",
            "audioCueDigest",
            "AUDIO_CUE",
        )
        _ref(result["scriptVersionRef"], "scriptVersionRef")
        _digest_value(result["scriptVersionDigest"], "scriptVersionDigest")
        text_start = _integer(result["textStart"], "textStart")
        text_end = _integer(result["textEndExclusive"], "textEndExclusive", minimum=1)
        if text_start >= text_end:
            raise TimelineEditingRangeError("SUBTITLE text range is invalid")
        _digest_value(result["textDigest"], "textDigest")
        _text(result["language"], "language")
        if not isinstance(result["wordTiming"], list):
            raise TimelineEditingContractError("wordTiming must be a list")
        timings = [
            _validate_word_timing(item, index)
            for index, item in enumerate(result["wordTiming"])
        ]
        if timings != sorted(
            timings,
            key=lambda item: (
                item["timelineStartFrameInclusive"],
                item["textStart"],
                item["wordRef"],
            ),
        ):
            raise TimelineEditingRangeError("wordTiming is not canonical")
        if any(
            item["textStart"] < text_start or item["textEndExclusive"] > text_end
            for item in timings
        ):
            raise TimelineEditingRangeError("wordTiming exceeds subtitle text range")
    elif clip_kind == "EFFECT":
        effect_source_fields = (
            _EFFECT_SOURCE_FIELDS_V3
            if clip_schema_version == TIMELINE_CLIP_SCHEMA_VERSION_V3
            else _EFFECT_SOURCE_FIELDS
        )
        result = _closed(value, effect_source_fields, "EFFECT sourceBinding")
        ref_field, digest_field, source_type = (
            "effectRequirementRef",
            "effectRequirementDigest",
            "EFFECT_REQUIREMENT",
        )
        if clip_schema_version == TIMELINE_CLIP_SCHEMA_VERSION:
            if result["effectKind"] != "GLYPH_REVEAL":
                raise TimelineEditingContractError("effectKind is invalid")
            if result["effectResultRef"] is not None:
                raise TimelineEditingAuthorityError(
                    "M13-T1 EFFECT clips cannot bind an effect result"
                )
        else:
            if result["effectKind"] not in DETERMINISTIC_EFFECT_KINDS:
                raise TimelineEditingContractError("effectKind is invalid")
            result_ref = result["effectResultRef"]
            result_digest = result["effectResultDigest"]
            if (result_ref is None) != (result_digest is None):
                raise TimelineEditingStaleInputError(
                    "EFFECT result binding is incomplete"
                )
            if result_ref is not None:
                _ref(result_ref, "effectResultRef")
                _digest_value(result_digest, "effectResultDigest")
        _integer(result["layer"], "effect layer", maximum=1024)
        if result["blendMode"] not in BLEND_MODES:
            raise TimelineEditingContractError("effect blendMode is invalid")
    else:
        raise TimelineEditingContractError("clipKind is invalid")

    source_ref = _ref(result[ref_field], ref_field)
    source_digest = _digest_value(result[digest_field], digest_field)
    if source_resolver is not None:
        authority = source_resolver(source_type, source_ref)
        if not isinstance(authority, Mapping):
            raise TimelineEditingAuthorityError("source authority is not resolvable")
        if authority.get("payloadDigest") != source_digest:
            raise TimelineEditingStaleInputError("source digest is stale")
        if scope is not None and any(
            authority.get(field) != scope[field]
            for field in ("workspaceRef", "productionRunRef")
        ):
            raise TimelineEditingStaleInputError("source scope is stale")
        if clip_kind == "VIDEO":
            authority_frame_rate = authority.get("frameRate")
            if (
                (authority.get("assetVersionRef") or authority.get("videoAssetVersionRef"))
                != result["assetVersionRef"]
                or end > authority.get("frameCount", -1)
            ):
                raise TimelineEditingRangeError("VIDEO source trim exceeds source")
            if (
                timeline_frame_rate is None
                or not isinstance(authority_frame_rate, Mapping)
                or _rational(
                    authority_frame_rate,
                    "source frameRate",
                    max_component=1_000_000,
                )
                != _rational(
                    timeline_frame_rate,
                    "timeline frameRate",
                    max_component=1_000_000,
                )
            ):
                raise TimelineEditingStaleInputError(
                    "VIDEO source frameRate differs from Timeline frameRate"
                )
        if clip_kind == "AUDIO":
            authority_asset_ref = authority.get("audioAssetVersionRef") or authority.get(
                "assetVersionRef"
            )
            if (
                authority_asset_ref != result["audioAssetVersionRef"]
                or end > authority.get("sampleCount", -1)
                or result["sampleRate"] != authority.get("sampleRate")
            ):
                raise TimelineEditingRangeError("AUDIO source trim exceeds source")
            stem = source_resolver("AUDIO_STEM_MEMBER", result["stemMemberRef"])
            if not isinstance(stem, Mapping):
                raise TimelineEditingAuthorityError(
                    "AudioStemMember authority is not resolvable"
                )
            stem_timing = stem.get("sourceTimingEvidence")
            stem_sample_rate = stem.get("sampleRate")
            if stem_sample_rate is None and isinstance(stem_timing, Mapping):
                stem_sample_rate = stem_timing.get("sampleRate")
            stem_asset_ref = stem.get("sourceAudioAssetVersionRef") or stem.get(
                "sourceAssetVersionRef"
            )
            stem_asset_digest = stem.get(
                "sourceAudioAssetVersionDigest"
            ) or stem.get("sourceAssetVersionDigest")
            if (
                stem.get("stemMemberRef") != result["stemMemberRef"]
                or not isinstance(stem.get("payloadDigest"), str)
                or stem_asset_ref != result["audioAssetVersionRef"]
                or stem_asset_digest != result["audioAssetVersionDigest"]
                or isinstance(stem.get("sourceStartSample"), bool)
                or not isinstance(stem.get("sourceStartSample"), int)
                or isinstance(stem.get("sourceEndSample"), bool)
                or not isinstance(stem.get("sourceEndSample"), int)
                or stem.get("sourceStartSample")
                > result["sourceStartSampleInclusive"]
                or stem.get("sourceEndSample")
                < result["sourceEndSampleExclusive"]
                or stem_sample_rate != result["sampleRate"]
                or (
                    scope is not None
                    and any(
                        stem.get(field) != scope[field]
                        for field in ("workspaceRef", "productionRunRef")
                    )
                )
            ):
                raise TimelineEditingStaleInputError(
                    "AudioStemMember semantic binding is stale"
                )
            _digest_value(stem["payloadDigest"], "stemMember payloadDigest")
        if clip_kind == "SUBTITLE":
            cue_ref = authority.get("cueVersionRef") or authority.get(
                "audioCueRef"
            )
            subtitle = authority.get("subtitleTimingReference")
            if not isinstance(subtitle, Mapping):
                subtitle = authority
            authority_word_timing = authority.get("timelineWordTiming")
            clip_word_identity = [
                {
                    "wordRef": item["wordRef"],
                    "textStart": item["textStart"],
                    "textEndExclusive": item["textEndExclusive"],
                    "textDigest": item["textDigest"],
                }
                for item in result["wordTiming"]
            ]
            raw_words = authority.get("wordTimings")
            raw_word_identity = (
                [
                    {
                        "wordRef": item.get("wordRef"),
                        "textStart": item.get("textRangeStart"),
                        "textEndExclusive": item.get(
                            "textRangeEndExclusive"
                        ),
                        "textDigest": item.get("textDigest"),
                    }
                    if isinstance(item, Mapping)
                    else None
                    for item in raw_words
                ]
                if isinstance(raw_words, list)
                else None
            )
            if (
                cue_ref != result["audioCueRef"]
                or authority.get("scriptVersionRef")
                != result["scriptVersionRef"]
                or authority.get("scriptVersionDigest")
                != result["scriptVersionDigest"]
                or subtitle.get("textRangeStart") != result["textStart"]
                or subtitle.get("textRangeEndExclusive")
                != result["textEndExclusive"]
                or subtitle.get("textDigest") != result["textDigest"]
                or subtitle.get("language") != result["language"]
                or raw_word_identity != clip_word_identity
                or authority_word_timing != result["wordTiming"]
                or authority.get("timelineStartFrameInclusive")
                != timeline_start_frame_inclusive
                or authority.get("timelineEndFrameExclusive")
                != timeline_end_frame_exclusive
            ):
                raise TimelineEditingStaleInputError(
                    "AudioCue subtitle semantic binding is stale"
                )
        if clip_kind == "EFFECT":
            if clip_schema_version == TIMELINE_CLIP_SCHEMA_VERSION:
                composite = authority.get("compositeParams")
                if (
                    authority.get("requirementRef")
                    != result["effectRequirementRef"]
                    or not isinstance(composite, Mapping)
                    or composite.get("blendMode") != result["blendMode"]
                    or result["layer"] != 1
                    or timeline_start_frame_inclusive is None
                    or timeline_end_frame_exclusive is None
                    or timeline_end_frame_exclusive
                    - timeline_start_frame_inclusive
                    != authority.get("frameRangeEndExclusive", -1)
                    - authority.get("frameRangeStartInclusive", 0)
                ):
                    raise TimelineEditingStaleInputError(
                        "GlyphRevealRequirement semantic binding is stale"
                    )
            else:
                range_start = authority.get("frameRangeStartInclusive")
                range_end = authority.get("frameRangeEndExclusive")
                base_ref = authority.get("basePlateAssetVersionRef")
                base_digest = authority.get("basePlateAssetVersionDigest")
                if (
                    authority.get("requirementRef")
                    != result["effectRequirementRef"]
                    or _deterministic_effect_kind(authority)
                    != result["effectKind"]
                    or authority.get("blendMode") != result["blendMode"]
                    or authority.get("layer") != result["layer"]
                    or isinstance(range_start, bool)
                    or not isinstance(range_start, int)
                    or isinstance(range_end, bool)
                    or not isinstance(range_end, int)
                    or range_start < 0
                    or range_end <= range_start
                    or timeline_start_frame_inclusive is None
                    or timeline_end_frame_exclusive is None
                    or timeline_end_frame_exclusive
                    - timeline_start_frame_inclusive
                    != range_end - range_start
                    or not isinstance(base_ref, str)
                    or not isinstance(base_digest, str)
                ):
                    raise TimelineEditingStaleInputError(
                        "deterministic Effect Requirement binding is stale"
                    )
                base = source_resolver("ASSET_VERSION", base_ref)
                if not isinstance(base, Mapping):
                    raise TimelineEditingAuthorityError(
                        "effect base AssetVersion authority is not resolvable"
                    )
                if (
                    base.get("assetVersionRef") != base_ref
                    or base.get("payloadDigest") != base_digest
                    or base.get("creativeShotRef")
                    != authority.get("targetShotRef")
                    or base.get("creativeShotVersionRef")
                    != authority.get("targetShotVersionRef")
                    or base.get("creativeShotDigest")
                    != authority.get("targetShotVersionDigest")
                ):
                    raise TimelineEditingStaleInputError(
                        "effect Requirement shot/base binding is stale"
                    )
                if result["effectResultRef"] is not None:
                    effect_result = source_resolver(
                        "EFFECT_RESULT", result["effectResultRef"]
                    )
                    if not isinstance(effect_result, Mapping):
                        raise TimelineEditingAuthorityError(
                            "Effect Result authority is not resolvable"
                        )
                    if (
                        effect_result.get("resultRef")
                        != result["effectResultRef"]
                        or effect_result.get("payloadDigest")
                        != result["effectResultDigest"]
                        or effect_result.get("requirementRef")
                        != result["effectRequirementRef"]
                        or effect_result.get("requirementDigest")
                        != result["effectRequirementDigest"]
                        or _deterministic_effect_kind(effect_result)
                        != result["effectKind"]
                        or effect_result.get("workspaceRef")
                        != authority.get("workspaceRef")
                        or effect_result.get("productionRunRef")
                        != authority.get("productionRunRef")
                        or effect_result.get("targetShotRef")
                        != authority.get("targetShotRef")
                        or effect_result.get("frameRangeStartInclusive")
                        != range_start
                        or effect_result.get("frameRangeEndExclusive")
                        != range_end
                        or not _effect_result_is_bindable(
                            effect_result,
                            effect_kind=result["effectKind"],
                        )
                        or effect_result.get("publicationAllowed") is not False
                    ):
                        raise TimelineEditingStaleInputError(
                            "Effect Result binding is stale"
                        )
    return result


def _validate_timeline_clip_mapping(
    value: Any,
    *,
    duration_frames: int | None = None,
    frame_rate: Mapping[str, Any] | None = None,
    source_resolver: SourceAuthorityResolver | None = None,
    scope: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    result = _verify_sealed(value, _CLIP_FIELDS, "TimelineClip")
    clip_schema_version = result["schemaVersion"]
    if clip_schema_version not in {
        TIMELINE_CLIP_SCHEMA_VERSION,
        TIMELINE_CLIP_SCHEMA_VERSION_V3,
    }:
        raise TimelineEditingContractError("TimelineClip schema is unsupported")
    _ref(result["clipRef"], "clipRef")
    _ref(result["timelineVersionRef"], "timelineVersionRef")
    _ref(result["trackRef"], "trackRef")
    clip_kind = result["clipKind"]
    if clip_kind not in set().union(*CLIP_KIND_BY_TRACK.values()):
        raise TimelineEditingContractError("clipKind is invalid")
    if (
        clip_schema_version == TIMELINE_CLIP_SCHEMA_VERSION_V3
        and clip_kind != "EFFECT"
    ):
        raise TimelineEditingContractError(
            "TimelineClip v3 is reserved for deterministic EFFECT clips"
        )
    start = _integer(
        result["timelineStartFrameInclusive"],
        "timelineStartFrameInclusive",
        maximum=MAX_DURATION_FRAMES,
    )
    end = _integer(
        result["timelineEndFrameExclusive"],
        "timelineEndFrameExclusive",
        minimum=1,
        maximum=MAX_DURATION_FRAMES,
    )
    if start >= end or (duration_frames is not None and end > duration_frames):
        raise TimelineEditingRangeError("TimelineClip range is invalid")
    if not isinstance(result["enabled"], bool):
        raise TimelineEditingContractError("clip enabled is invalid")
    _integer(result["layer"], "layer", maximum=1024)
    _signed_integer(result["zOrder"], "zOrder", bound=1_000_000)
    _integer(result["opacity"], "opacity", maximum=FIXED_OPACITY_SCALE)
    if result["blendMode"] not in BLEND_MODES:
        raise TimelineEditingContractError("blendMode is invalid")
    source = _validate_source_binding(
        result["sourceBinding"],
        clip_kind,
        clip_schema_version=clip_schema_version,
        source_resolver=source_resolver,
        scope=scope,
        timeline_start_frame_inclusive=start,
        timeline_end_frame_exclusive=end,
        timeline_frame_rate=frame_rate,
    )
    if clip_kind == "SUBTITLE":
        previous_end: int | None = None
        for word in source["wordTiming"]:
            word_start = word["timelineStartFrameInclusive"]
            word_end = word["timelineEndFrameExclusive"]
            if (
                word_start < start
                or word_end > end
                or (previous_end is not None and word_start < previous_end)
            ):
                raise TimelineEditingRangeError(
                    "SUBTITLE word timing exceeds or overlaps its clip"
                )
            previous_end = word_end
    transitions: dict[str, dict[str, Any] | None] = {}
    for field in ("transitionIn", "transitionOut"):
        item = result[field]
        transitions[field] = (
            None if item is None else _validate_transition_spec_mapping(item)
        )
        if transitions[field] is not None and transitions[field]["durationFrames"] > end - start:
            raise TimelineEditingRangeError("transition exceeds clip duration")
    if (
        transitions["transitionIn"] is not None
        and transitions["transitionIn"]["transitionKind"] == "FADE_OUT"
    ) or (
        transitions["transitionOut"] is not None
        and transitions["transitionOut"]["transitionKind"] == "FADE_IN"
    ):
        raise TimelineEditingContractError("transition direction is invalid")
    speed = _validate_speed_spec_mapping(result["speed"])
    transform = _validate_transform_spec_mapping(result["transform"])
    if not isinstance(result["maskBindings"], list):
        raise TimelineEditingContractError("maskBindings must be a list")
    masks = [_validate_mask_binding_mapping(item) for item in result["maskBindings"]]
    refs = [item["maskAssetVersionRef"] for item in masks]
    if len(refs) != len(set(refs)):
        raise TimelineEditingContractError("mask refs are duplicated")
    if any(
        item["frameRangeStartInclusive"] < start
        or item["frameRangeEndExclusive"] > end
        for item in masks
    ):
        raise TimelineEditingRangeError("mask range exceeds clip")
    if source_resolver is not None:
        for mask in masks:
            authority = source_resolver(
                "MASK_ASSET_VERSION", mask["maskAssetVersionRef"]
            )
            if not isinstance(authority, Mapping):
                raise TimelineEditingAuthorityError(
                    "mask AssetVersion authority is not resolvable"
                )
            if (
                authority.get("assetVersionRef")
                != mask["maskAssetVersionRef"]
                or authority.get("payloadDigest")
                != mask["maskAssetVersionDigest"]
            ):
                raise TimelineEditingStaleInputError(
                    "mask AssetVersion ref/digest is stale"
                )
            if scope is not None and any(
                authority.get(field) != scope[field]
                for field in ("workspaceRef", "productionRunRef")
            ):
                raise TimelineEditingStaleInputError(
                    "mask AssetVersion scope is stale"
                )

    span = end - start
    numerator, denominator = speed["numerator"], speed["denominator"]
    if clip_kind == "VIDEO":
        source_span = source["sourceOutFrameExclusive"] - source["sourceInFrameInclusive"]
        if source_span * denominator != span * numerator:
            raise TimelineEditingRangeError("VIDEO speed/source duration is inexact")
    elif clip_kind == "AUDIO" and frame_rate is not None:
        rate = _rational(frame_rate, "frameRate", max_component=1_000_000)
        source_span = source["sourceEndSampleExclusive"] - source["sourceStartSampleInclusive"]
        if (
            source_span * denominator * rate["numerator"]
            != span * source["sampleRate"] * rate["denominator"] * numerator
        ):
            raise TimelineEditingRangeError("AUDIO speed/source duration is inexact")
    elif clip_kind in {"SUBTITLE", "EFFECT"} and (numerator, denominator) != (1, 1):
        raise TimelineEditingContractError("this clip kind does not support speed")
    if clip_kind == "EFFECT" and (
        result["layer"] != source["layer"]
        or result["blendMode"] != source["blendMode"]
        or result["opacity"] != FIXED_OPACITY_SCALE
        or any(
            transform[field] != expected
            for field, expected in {
                "positionXPixels": 0,
                "positionYPixels": 0,
                "scaleX": {"numerator": 1, "denominator": 1},
                "scaleY": {"numerator": 1, "denominator": 1},
                "rotationMilliDegrees": 0,
                "anchorXPixels": 0,
                "anchorYPixels": 0,
                "opacity": FIXED_OPACITY_SCALE,
                "perspectiveMode": "NONE",
                "perspectiveMatrix": None,
                "perspectiveCorners": None,
            }.items()
        )
    ):
        raise TimelineEditingStaleInputError(
            "EFFECT layer/blend/transform binding is stale"
        )
    return result


def _wire(value: Any, expected_type: type[_ImmutableWireContract]) -> Any:
    return value.as_dict() if type(value) is expected_type else deepcopy(value)


def _timeline_clip_schema_for_command(value: Mapping[str, Any]) -> str:
    source = value.get("sourceBinding")
    if (
        value.get("clipKind") == "EFFECT"
        and isinstance(source, Mapping)
        and (
            source.get("effectKind") in DETERMINISTIC_EFFECT_KINDS
            or "effectResultDigest" in source
        )
    ):
        return TIMELINE_CLIP_SCHEMA_VERSION_V3
    return TIMELINE_CLIP_SCHEMA_VERSION


def build_timeline_clip(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(command, _CLIP_COMMAND_FIELDS, "TimelineClip command")
    result = {"schemaVersion": _timeline_clip_schema_for_command(value)}
    for field in _CLIP_COMMAND_FIELDS:
        item = value[field]
        if field in {"transitionIn", "transitionOut"} and item is not None:
            item = _wire(item, TransitionSpec)
        elif field == "speed":
            item = _wire(item, SpeedSpec)
        elif field == "transform":
            item = _wire(item, TransformSpec)
        elif field == "maskBindings":
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
                raise TimelineEditingContractError("maskBindings must be a sequence")
            item = [_wire(mask, MaskBinding) for mask in item]
        result[field] = item
    return _validate_timeline_clip_mapping(_seal(result))


def validate_timeline_clip(
    value: Any,
    *,
    duration_frames: int | None = None,
    frame_rate: Mapping[str, Any] | None = None,
    source_resolver: SourceAuthorityResolver | None = None,
    scope: Mapping[str, str] | None = None,
) -> "TimelineClip":
    return TimelineClip._from_validated(
        _validate_timeline_clip_mapping(
            value,
            duration_frames=duration_frames,
            frame_rate=frame_rate,
            source_resolver=source_resolver,
            scope=scope,
        )
    )


class TimelineClip(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TimelineClip":
        return cls._from_validated(_validate_timeline_clip_mapping(value))


_SAFE_AREA_FIELDS = frozenset(
    {"leftPixels", "topPixels", "rightPixels", "bottomPixels"}
)
_TIMELINE_VERSION_FIELDS = frozenset(
    {
        "schemaVersion",
        "timelineRef",
        "timelineVersionRef",
        "versionNumber",
        "parentTimelineVersionRef",
        "parentTimelineVersionDigest",
        *_SCOPE_FIELDS,
        "scriptVersionRef",
        "scriptVersionDigest",
        "storyboardVersionRef",
        "storyboardVersionDigest",
        "frameRate",
        "canvasWidth",
        "canvasHeight",
        "pixelAspectRatio",
        "displayAspectRatio",
        "durationFrames",
        "safeArea",
        "outputProfileBindings",
        "trackRefs",
        "trackSnapshotDigest",
        "clipSnapshotDigest",
        "snapshotDigest",
        "provenance",
        "createdAt",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TIMELINE_VERSION_COMMAND_FIELDS = _TIMELINE_VERSION_FIELDS - frozenset(
    {
        "schemaVersion",
        "outputProfileBindings",
        "trackSnapshotDigest",
        "clipSnapshotDigest",
        "snapshotDigest",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)


def _snapshot_digests(
    tracks: Sequence[TimelineTrack | Mapping[str, Any]],
    clips: Sequence[TimelineClip | Mapping[str, Any]],
    *,
    timeline_version_ref: str,
) -> tuple[str, str, str]:
    """Digest a complete version-scoped Track/Clip snapshot.

    Each fact contributes its immutable identity and already verified payload
    digest.  Ordering is canonical and therefore independent of repository
    row order.
    """

    version_ref = _ref(timeline_version_ref, "timelineVersionRef")
    if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)):
        raise TimelineEditingContractError("tracks must be a sequence")
    if not isinstance(clips, Sequence) or isinstance(clips, (str, bytes)):
        raise TimelineEditingContractError("clips must be a sequence")
    track_mappings = [
        item.as_dict()
        if type(item) is TimelineTrack
        else _validate_timeline_track_mapping(item)
        for item in tracks
    ]
    clip_mappings = [
        item.as_dict()
        if type(item) is TimelineClip
        else _validate_timeline_clip_mapping(item)
        for item in clips
    ]
    if any(item["timelineVersionRef"] != version_ref for item in track_mappings):
        raise TimelineEditingStaleInputError("Track snapshot version is stale")
    if any(item["timelineVersionRef"] != version_ref for item in clip_mappings):
        raise TimelineEditingStaleInputError("Clip snapshot version is stale")
    track_facts = sorted(
        (
            {
                "trackRef": item["trackRef"],
                "payloadDigest": item["payloadDigest"],
            }
            for item in track_mappings
        ),
        key=lambda item: item["trackRef"],
    )
    clip_facts = sorted(
        (
            {
                "clipRef": item["clipRef"],
                "payloadDigest": item["payloadDigest"],
            }
            for item in clip_mappings
        ),
        key=lambda item: item["clipRef"],
    )
    if len({item["trackRef"] for item in track_facts}) != len(track_facts):
        raise TimelineEditingContractError("Track snapshot refs are duplicated")
    if len({item["clipRef"] for item in clip_facts}) != len(clip_facts):
        raise TimelineEditingContractError("Clip snapshot refs are duplicated")
    track_digest = _digest(
        {
            "schemaVersion": TIMELINE_TRACK_SNAPSHOT_SCHEMA_VERSION,
            "timelineVersionRef": version_ref,
            "tracks": track_facts,
        }
    )
    clip_digest = _digest(
        {
            "schemaVersion": TIMELINE_CLIP_SNAPSHOT_SCHEMA_VERSION,
            "timelineVersionRef": version_ref,
            "clips": clip_facts,
        }
    )
    snapshot_digest = _digest(
        {
            "schemaVersion": TIMELINE_SNAPSHOT_SCHEMA_VERSION,
            "timelineVersionRef": version_ref,
            "trackSnapshotDigest": track_digest,
            "clipSnapshotDigest": clip_digest,
        }
    )
    return track_digest, clip_digest, snapshot_digest


def compute_timeline_snapshot_digests(
    tracks: Sequence[TimelineTrack | Mapping[str, Any]],
    clips: Sequence[TimelineClip | Mapping[str, Any]],
    *,
    timeline_version_ref: str,
) -> dict[str, str]:
    track_digest, clip_digest, snapshot_digest = _snapshot_digests(
        tracks, clips, timeline_version_ref=timeline_version_ref
    )
    return {
        "trackSnapshotDigest": track_digest,
        "clipSnapshotDigest": clip_digest,
        "snapshotDigest": snapshot_digest,
    }


def _validate_safe_area(
    value: Any, *, canvas_width: int, canvas_height: int
) -> dict[str, int]:
    result = _closed(value, _SAFE_AREA_FIELDS, "safeArea")
    for field in _SAFE_AREA_FIELDS:
        _integer(result[field], f"safeArea.{field}", maximum=MAX_CANVAS_DIMENSION)
    if (
        result["leftPixels"] + result["rightPixels"] >= canvas_width
        or result["topPixels"] + result["bottomPixels"] >= canvas_height
    ):
        raise TimelineEditingRangeError("safeArea leaves no visible canvas")
    return result  # type: ignore[return-value]


def _validate_timeline_version_structure(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _TIMELINE_VERSION_FIELDS, "TimelineVersion")
    if result["schemaVersion"] != TIMELINE_VERSION_SCHEMA_VERSION:
        raise TimelineEditingContractError("TimelineVersion schema is unsupported")
    _ref(result["timelineRef"], "timelineRef")
    _ref(result["timelineVersionRef"], "timelineVersionRef")
    version_number = _integer(
        result["versionNumber"], "versionNumber", minimum=1, maximum=10**9
    )
    parent_ref = _optional_ref(
        result["parentTimelineVersionRef"], "parentTimelineVersionRef"
    )
    parent_digest = result["parentTimelineVersionDigest"]
    if parent_digest is not None:
        _digest_value(parent_digest, "parentTimelineVersionDigest")
    if version_number == 1:
        if parent_ref is not None or parent_digest is not None:
            raise TimelineEditingContractError("initial TimelineVersion has no parent")
    elif parent_ref is None or parent_digest is None:
        raise TimelineEditingStaleInputError("TimelineVersion parent is incomplete")
    _scope(result)
    _ref(result["scriptVersionRef"], "scriptVersionRef")
    _digest_value(result["scriptVersionDigest"], "scriptVersionDigest")
    _ref(result["storyboardVersionRef"], "storyboardVersionRef")
    _digest_value(result["storyboardVersionDigest"], "storyboardVersionDigest")
    frame_rate = _rational(
        result["frameRate"], "frameRate", max_component=1_000_000
    )
    width = _integer(
        result["canvasWidth"],
        "canvasWidth",
        minimum=1,
        maximum=MAX_CANVAS_DIMENSION,
    )
    height = _integer(
        result["canvasHeight"],
        "canvasHeight",
        minimum=1,
        maximum=MAX_CANVAS_DIMENSION,
    )
    pixel = _rational(
        result["pixelAspectRatio"],
        "pixelAspectRatio",
        max_component=1_000_000,
    )
    display = _rational(
        result["displayAspectRatio"],
        "displayAspectRatio",
        max_component=MAX_CANVAS_DIMENSION * 1_000_000,
    )
    expected_numerator = width * pixel["numerator"]
    expected_denominator = height * pixel["denominator"]
    common = gcd(expected_numerator, expected_denominator)
    if display != {
        "numerator": expected_numerator // common,
        "denominator": expected_denominator // common,
    }:
        raise TimelineEditingRangeError("displayAspectRatio is not canonical")
    duration = _integer(
        result["durationFrames"],
        "durationFrames",
        minimum=1,
        maximum=MAX_DURATION_FRAMES,
    )
    if duration <= 0 or frame_rate["numerator"] <= 0:
        raise TimelineEditingRangeError("Timeline duration/frameRate is invalid")
    _validate_safe_area(result["safeArea"], canvas_width=width, canvas_height=height)
    if not isinstance(result["outputProfileBindings"], list) or not result[
        "outputProfileBindings"
    ]:
        raise TimelineEditingContractError(
            "TimelineVersion requires outputProfileBindings"
        )
    profiles = [
        _validate_output_profile_binding_mapping(item)
        for item in result["outputProfileBindings"]
    ]
    profile_refs = [item["outputProfileRef"] for item in profiles]
    if (
        len(profile_refs) != len(set(profile_refs))
        or profiles
        != sorted(profiles, key=lambda item: item["outputProfileRef"])
        or any(item["frameRate"] != frame_rate for item in profiles)
    ):
        raise TimelineEditingContractError("outputProfileBindings are not canonical")
    if not isinstance(result["trackRefs"], list) or not result["trackRefs"]:
        raise TimelineEditingContractError("TimelineVersion requires trackRefs")
    track_refs = [_ref(item, "trackRef") for item in result["trackRefs"]]
    if len(track_refs) != len(set(track_refs)):
        raise TimelineEditingContractError("track refs are duplicated")
    track_snapshot_digest = _digest_value(
        result["trackSnapshotDigest"], "trackSnapshotDigest"
    )
    clip_snapshot_digest = _digest_value(
        result["clipSnapshotDigest"], "clipSnapshotDigest"
    )
    expected_snapshot_digest = _digest(
        {
            "schemaVersion": TIMELINE_SNAPSHOT_SCHEMA_VERSION,
            "timelineVersionRef": result["timelineVersionRef"],
            "trackSnapshotDigest": track_snapshot_digest,
            "clipSnapshotDigest": clip_snapshot_digest,
        }
    )
    if result["snapshotDigest"] != expected_snapshot_digest:
        raise TimelineEditingStaleInputError("Timeline snapshotDigest is stale")
    if result["provenance"] != TIMELINE_PROVENANCE:
        raise TimelineEditingContractError("TimelineVersion provenance is invalid")
    _timestamp(result["createdAt"])
    if result["publicationAllowed"] is not False:
        raise TimelineEditingAuthorityError("TimelineVersion cannot publish")
    return result


def _validate_predecessor(
    result: Mapping[str, Any], predecessor: Any
) -> dict[str, Any] | None:
    if result["versionNumber"] == 1:
        if predecessor is not None:
            raise TimelineEditingStaleInputError("initial version cannot have predecessor")
        return None
    if predecessor is None:
        raise TimelineEditingStaleInputError("TimelineVersion predecessor is required")
    prior = (
        predecessor.as_dict()
        if type(predecessor) is TimelineVersion
        else _validate_timeline_version_structure(predecessor)
    )
    if (
        result["timelineRef"] != prior["timelineRef"]
        or result["versionNumber"] != prior["versionNumber"] + 1
        or result["parentTimelineVersionRef"] != prior["timelineVersionRef"]
        or result["parentTimelineVersionDigest"] != prior["payloadDigest"]
        or _scope(result) != _scope(prior)
    ):
        raise TimelineEditingStaleInputError("TimelineVersion predecessor is stale")
    return prior


def build_timeline_version(
    command: Mapping[str, Any],
    *,
    output_profile_bindings: Sequence[OutputProfileBinding | Mapping[str, Any]],
    tracks: Sequence[TimelineTrack | Mapping[str, Any]],
    clips: Sequence[TimelineClip | Mapping[str, Any]],
    predecessor: "TimelineVersion | Mapping[str, Any] | None" = None,
) -> dict[str, Any]:
    value = _closed(
        command,
        _TIMELINE_VERSION_COMMAND_FIELDS,
        "TimelineVersion command",
    )
    if not isinstance(output_profile_bindings, Sequence) or isinstance(
        output_profile_bindings, (str, bytes)
    ):
        raise TimelineEditingContractError("output_profile_bindings is invalid")
    profiles = [
        _wire(item, OutputProfileBinding) for item in output_profile_bindings
    ]
    profiles.sort(key=lambda item: item.get("outputProfileRef", ""))
    supplied_tracks = [
        item.as_dict()
        if type(item) is TimelineTrack
        else _validate_timeline_track_mapping(item)
        for item in tracks
    ]
    supplied_tracks.sort(key=lambda item: (item["order"], item["trackRef"]))
    if [item["trackRef"] for item in supplied_tracks] != value["trackRefs"]:
        raise TimelineEditingStaleInputError(
            "TimelineVersion trackRefs do not match Track snapshot"
        )
    track_digest, clip_digest, snapshot_digest = _snapshot_digests(
        tracks,
        clips,
        timeline_version_ref=value["timelineVersionRef"],
    )
    result = _seal(
        {
            "schemaVersion": TIMELINE_VERSION_SCHEMA_VERSION,
            **value,
            "outputProfileBindings": profiles,
            "trackSnapshotDigest": track_digest,
            "clipSnapshotDigest": clip_digest,
            "snapshotDigest": snapshot_digest,
            "provenance": TIMELINE_PROVENANCE,
            "publicationAllowed": False,
        }
    )
    validated = _validate_timeline_version_structure(result)
    _validate_predecessor(validated, predecessor)
    return validated


def validate_timeline_version(
    value: Any,
    *,
    predecessor: "TimelineVersion | Mapping[str, Any] | None" = None,
) -> "TimelineVersion":
    result = _validate_timeline_version_structure(value)
    _validate_predecessor(result, predecessor)
    return TimelineVersion._from_validated(result)


class TimelineVersion(_ImmutableWireContract):
    @classmethod
    def from_mapping(
        cls,
        value: Any,
        *,
        predecessor: "TimelineVersion | Mapping[str, Any] | None" = None,
    ) -> "TimelineVersion":
        result = _validate_timeline_version_structure(value)
        _validate_predecessor(result, predecessor)
        return cls._from_validated(result)


def read_timeline_root(value: Any) -> Timeline | Mapping[str, Any]:
    """Read v3 or return an independently validated v2 root projection.

    Legacy payloads are never filled, rewritten, or resealed.  The returned
    v2 mapping is an explicit read-only projection retaining its exact digest.
    """

    if isinstance(value, Mapping) and value.get("schemaVersion") == LEGACY_TIMELINE_SCHEMA_VERSION:
        from .timeline_preview import validate_timeline as validate_legacy_timeline

        return validate_legacy_timeline(value).as_dict()
    return validate_timeline(value)


def read_timeline_version(
    value: Any,
    *,
    predecessor: TimelineVersion | Mapping[str, Any] | None = None,
    legacy_timeline: Any = None,
    legacy_timeline_input_bundle: Any = None,
    legacy_predecessor: Any = None,
) -> TimelineVersion | Mapping[str, Any]:
    """Read a v3 version or an exact, independently validated legacy v2 one."""

    if isinstance(value, Mapping) and value.get("schemaVersion") == LEGACY_TIMELINE_VERSION_SCHEMA_VERSION:
        if legacy_timeline is None or legacy_timeline_input_bundle is None:
            raise TimelineEditingAuthorityError(
                "legacy Timeline and input bundle are required"
            )
        from .timeline_preview import (
            validate_timeline_version as validate_legacy_timeline_version,
        )

        return validate_legacy_timeline_version(
            value,
            timeline=legacy_timeline,
            timeline_input_bundle=legacy_timeline_input_bundle,
            predecessor_timeline_version=legacy_predecessor,
        ).as_dict()
    return validate_timeline_version(value, predecessor=predecessor)


def read_timeline_track(
    value: Any,
    *,
    legacy_timeline_input_bundle: Any = None,
    legacy_frame_rate: Mapping[str, Any] | None = None,
    legacy_duration_frames: int | None = None,
) -> TimelineTrack | Mapping[str, Any]:
    """Read v2 Track or an exact, independently validated legacy v1 Track."""

    if isinstance(value, Mapping) and value.get("schemaVersion") == "v5.timeline-track.v1":
        if (
            legacy_timeline_input_bundle is None
            or legacy_frame_rate is None
            or legacy_duration_frames is None
        ):
            raise TimelineEditingAuthorityError(
                "legacy Track validation context is required"
            )
        from .timeline_preview import validate_timeline_track as validate_legacy_track

        return validate_legacy_track(
            value,
            timeline_input_bundle=legacy_timeline_input_bundle,
            frame_rate=legacy_frame_rate,
            duration_frames=legacy_duration_frames,
        ).as_dict()
    return validate_timeline_track(value)


def read_timeline_clip(
    value: Any,
    *,
    legacy_timeline_input_bundle: Any = None,
    legacy_frame_rate: Mapping[str, Any] | None = None,
    legacy_duration_frames: int | None = None,
) -> TimelineClip | Mapping[str, Any]:
    """Read v2 Clip or an exact, independently validated legacy v1 Clip."""

    if isinstance(value, Mapping) and value.get("schemaVersion") == "v5.timeline-clip.v1":
        if (
            legacy_timeline_input_bundle is None
            or legacy_frame_rate is None
            or legacy_duration_frames is None
        ):
            raise TimelineEditingAuthorityError(
                "legacy Clip validation context is required"
            )
        from .timeline_preview import validate_timeline_clip as validate_legacy_clip

        return validate_legacy_clip(
            value,
            timeline_input_bundle=legacy_timeline_input_bundle,
            frame_rate=legacy_frame_rate,
            duration_frames=legacy_duration_frames,
        ).as_dict()
    return validate_timeline_clip(value)


@dataclass(frozen=True, slots=True)
class TimelineSnapshot:
    timeline_version: TimelineVersion
    tracks: tuple[TimelineTrack, ...]
    clips: tuple[TimelineClip, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "timelineVersion": self.timeline_version.as_dict(),
            "tracks": [item.as_dict() for item in self.tracks],
            "clips": [item.as_dict() for item in self.clips],
        }


def _overlap(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left["timelineStartFrameInclusive"] < right["timelineEndFrameExclusive"]
        and right["timelineStartFrameInclusive"] < left["timelineEndFrameExclusive"]
    )


def validate_timeline_snapshot(
    timeline_version: TimelineVersion | Mapping[str, Any],
    tracks: Sequence[TimelineTrack | Mapping[str, Any]],
    clips: Sequence[TimelineClip | Mapping[str, Any]],
    *,
    timeline: Timeline | Mapping[str, Any] | None = None,
    predecessor: TimelineVersion | Mapping[str, Any] | None = None,
    source_resolver: SourceAuthorityResolver | None = None,
    expected_script: Mapping[str, Any] | None = None,
    expected_storyboard: Mapping[str, Any] | None = None,
) -> TimelineSnapshot:
    version_mapping = (
        timeline_version.as_dict()
        if type(timeline_version) is TimelineVersion
        else _validate_timeline_version_structure(timeline_version)
    )
    # Exact wrappers have already passed predecessor validation when created or
    # restored.  Raw successor mappings must supply their predecessor here.
    if predecessor is not None or type(timeline_version) is not TimelineVersion:
        _validate_predecessor(version_mapping, predecessor)
    if timeline is not None:
        root = timeline.as_dict() if type(timeline) is Timeline else _validate_timeline_mapping(timeline)
        if (
            version_mapping["timelineRef"] != root["timelineRef"]
            or _scope(version_mapping) != _scope(root)
        ):
            raise TimelineEditingStaleInputError("TimelineVersion root is stale")
    for expected, ref_field, digest_field in (
        (expected_script, "scriptVersionRef", "scriptVersionDigest"),
        (expected_storyboard, "storyboardVersionRef", "storyboardVersionDigest"),
    ):
        if expected is not None and (
            version_mapping[ref_field] != expected.get(ref_field)
            or version_mapping[digest_field] != expected.get(digest_field)
        ):
            raise TimelineEditingStaleInputError(f"{ref_field} is stale")
    if not isinstance(tracks, Sequence) or isinstance(tracks, (str, bytes)):
        raise TimelineEditingContractError("tracks must be a sequence")
    if not isinstance(clips, Sequence) or isinstance(clips, (str, bytes)):
        raise TimelineEditingContractError("clips must be a sequence")
    track_mappings = [
        item.as_dict()
        if type(item) is TimelineTrack
        else _validate_timeline_track_mapping(item)
        for item in tracks
    ]
    if len(track_mappings) != 4:
        raise TimelineEditingContractError("Timeline requires exactly four tracks")
    track_mappings.sort(key=lambda item: (item["order"], item["trackRef"]))
    if (
        [item["order"] for item in track_mappings] != list(range(4))
        or {item["trackKind"] for item in track_mappings}
        != set(TIMELINE_TRACK_KINDS)
        or [item["trackRef"] for item in track_mappings]
        != version_mapping["trackRefs"]
        or any(
            item["timelineVersionRef"] != version_mapping["timelineVersionRef"]
            for item in track_mappings
        )
    ):
        raise TimelineEditingStaleInputError("TimelineTrack membership is stale")
    scope = {field: version_mapping[field] for field in _SCOPE_FIELDS}
    clip_mappings = [
        _validate_timeline_clip_mapping(
            item.as_dict() if type(item) is TimelineClip else item,
            duration_frames=version_mapping["durationFrames"],
            frame_rate=version_mapping["frameRate"],
            source_resolver=source_resolver,
            scope=scope,
        )
        for item in clips
    ]
    clip_refs = [item["clipRef"] for item in clip_mappings]
    if len(clip_refs) != len(set(clip_refs)):
        raise TimelineEditingContractError("clip refs are duplicated")
    track_snapshot_digest, clip_snapshot_digest, snapshot_digest = _snapshot_digests(
        track_mappings,
        clip_mappings,
        timeline_version_ref=version_mapping["timelineVersionRef"],
    )
    if (
        version_mapping["trackSnapshotDigest"] != track_snapshot_digest
        or version_mapping["clipSnapshotDigest"] != clip_snapshot_digest
        or version_mapping["snapshotDigest"] != snapshot_digest
    ):
        raise TimelineEditingStaleInputError(
            "TimelineVersion snapshot membership digest is stale"
        )
    tracks_by_ref = {item["trackRef"]: item for item in track_mappings}
    if any(
        item["timelineVersionRef"] != version_mapping["timelineVersionRef"]
        or item["trackRef"] not in tracks_by_ref
        or item["clipKind"]
        not in CLIP_KIND_BY_TRACK[tracks_by_ref[item["trackRef"]]["trackKind"]]
        for item in clip_mappings
    ):
        raise TimelineEditingStaleInputError("TimelineClip membership is stale")
    if any(
        item["clipKind"] == "SUBTITLE"
        and (
            item["sourceBinding"]["scriptVersionRef"]
            != version_mapping["scriptVersionRef"]
            or item["sourceBinding"]["scriptVersionDigest"]
            != version_mapping["scriptVersionDigest"]
        )
        for item in clip_mappings
    ):
        raise TimelineEditingStaleInputError(
            "SUBTITLE ScriptVersion binding is stale"
        )
    if source_resolver is not None:
        for effect in (
            item for item in clip_mappings if item["clipKind"] == "EFFECT"
        ):
            requirement = source_resolver(
                "EFFECT_REQUIREMENT",
                effect["sourceBinding"]["effectRequirementRef"],
            )
            if not isinstance(requirement, Mapping):
                raise TimelineEditingAuthorityError(
                    "GlyphRevealRequirement authority is not resolvable"
                )
            range_start = requirement.get("frameRangeStartInclusive")
            range_end = requirement.get("frameRangeEndExclusive")
            base_ref = requirement.get("basePlateAssetVersionRef")
            base_digest = requirement.get("basePlateAssetVersionDigest")
            if (
                isinstance(range_start, bool)
                or not isinstance(range_start, int)
                or isinstance(range_end, bool)
                or not isinstance(range_end, int)
                or range_start < 0
                or range_end <= range_start
                or not isinstance(base_ref, str)
                or not isinstance(base_digest, str)
            ):
                raise TimelineEditingAuthorityError(
                    "GlyphRevealRequirement authority is invalid"
                )
            related_base_plates = []
            for video in (
                item for item in clip_mappings if item["clipKind"] == "VIDEO"
            ):
                binding = video["sourceBinding"]
                if (
                    binding["assetVersionRef"] != base_ref
                    or binding["assetVersionDigest"] != base_digest
                    or video["speed"].get("numerator") != 1
                    or video["speed"].get("denominator") != 1
                    or binding["sourceInFrameInclusive"] > range_start
                    or binding["sourceOutFrameExclusive"] < range_end
                ):
                    continue
                timeline_at_requirement_start = (
                    video["timelineStartFrameInclusive"]
                    + range_start
                    - binding["sourceInFrameInclusive"]
                )
                timeline_at_requirement_end = (
                    video["timelineStartFrameInclusive"]
                    + range_end
                    - binding["sourceInFrameInclusive"]
                )
                if (
                    timeline_at_requirement_start
                    == effect["timelineStartFrameInclusive"]
                    and timeline_at_requirement_end
                    == effect["timelineEndFrameExclusive"]
                ):
                    related_base_plates.append(video)
            if len(related_base_plates) != 1:
                raise TimelineEditingStaleInputError(
                    "EFFECT clip does not bind exactly one base plate frame interval"
                )
    for track in track_mappings:
        members = sorted(
            (item for item in clip_mappings if item["trackRef"] == track["trackRef"]),
            key=lambda item: (
                item["timelineStartFrameInclusive"],
                item["timelineEndFrameExclusive"],
                item["clipRef"],
            ),
        )
        for index, left in enumerate(members):
            for right in members[index + 1 :]:
                if not _overlap(left, right):
                    continue
                if track["lanePolicy"] == "EXCLUSIVE":
                    raise TimelineEditingConflictError("exclusive lane clips overlap")
                if track["lanePolicy"] == "LAYERED_Z_ORDER" and (
                    left["layer"], left["zOrder"]
                ) == (right["layer"], right["zOrder"]):
                    raise TimelineEditingConflictError("z-order conflicts in lane")
        for index, clip in enumerate(members):
            previous = members[index - 1] if index else None
            following = members[index + 1] if index + 1 < len(members) else None
            for field, neighbour in (
                ("transitionIn", previous),
                ("transitionOut", following),
            ):
                transition = clip[field]
                if transition is None or transition["transitionKind"] in {
                    "CUT",
                    "FADE_IN",
                    "FADE_OUT",
                }:
                    continue
                if neighbour is None or transition["durationFrames"] > (
                    neighbour["timelineEndFrameExclusive"]
                    - neighbour["timelineStartFrameInclusive"]
                ):
                    raise TimelineEditingRangeError(
                        "transition exceeds adjacent clip availability"
                    )
    return TimelineSnapshot(
        TimelineVersion._from_validated(version_mapping),
        tuple(TimelineTrack._from_validated(item) for item in track_mappings),
        tuple(TimelineClip._from_validated(item) for item in clip_mappings),
    )


_EDIT_COMMAND_FIELDS = frozenset(
    {
        "schemaVersion",
        "operationRef",
        "idempotencyKey",
        "parentTimelineVersionRef",
        "parentTimelineVersionDigest",
        "newTimelineVersionRef",
        "operation",
        "arguments",
        "createdAt",
        "payloadDigest",
    }
)
_EDIT_COMMAND_INPUT_FIELDS = _EDIT_COMMAND_FIELDS - frozenset(
    {"schemaVersion", "payloadDigest"}
)
_EDIT_ARGUMENT_FIELDS = {
    "INSERT_CLIP": frozenset({"clip"}),
    "REMOVE_CLIP": frozenset({"clipRef"}),
    "MOVE_CLIP": frozenset(
        {
            "clipRef",
            "trackRef",
            "timelineStartFrameInclusive",
            "timelineEndFrameExclusive",
        }
    ),
    "TRIM_CLIP": frozenset(
        {
            "clipRef",
            "timelineStartFrameInclusive",
            "timelineEndFrameExclusive",
            "sourceBinding",
        }
    ),
    "SPLIT_CLIP": frozenset(
        {"clipRef", "splitTimelineFrame", "rightClipRef"}
    ),
    "ENABLE_CLIP": frozenset({"clipRef"}),
    "DISABLE_CLIP": frozenset({"clipRef"}),
    "REORDER_TRACK": frozenset({"trackRef", "order"}),
    "SET_TRANSITION": frozenset({"clipRef", "edge", "transition"}),
    "SET_SPEED": frozenset({"clipRef", "speed"}),
    "SET_TRANSFORM": frozenset({"clipRef", "transform"}),
    "SET_MASKS": frozenset({"clipRef", "maskBindings"}),
    "SET_SAFE_AREA": frozenset({"safeArea"}),
    "SET_OUTPUT_PROFILES": frozenset({"outputProfileBindings"}),
}
_EDIT_ARGUMENT_FIELDS_V2 = {
    "BIND_EFFECT_RESULT": frozenset(
        {"clipRef", "effectResultRef", "effectResultDigest"}
    ),
}
_INSERT_CLIP_FIELDS = _CLIP_COMMAND_FIELDS - frozenset({"timelineVersionRef"})


def _validate_edit_arguments(
    operation: str,
    value: Any,
    *,
    new_timeline_version_ref: str,
    schema_version: str = TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
) -> dict[str, Any]:
    fields = (
        _EDIT_ARGUMENT_FIELDS_V2
        if schema_version == TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2
        else _EDIT_ARGUMENT_FIELDS
    )[operation]
    result = _closed(value, fields, f"{operation} arguments")
    _reject_forbidden_keys(result)
    if "clipRef" in result:
        _ref(result["clipRef"], "clipRef")
    if operation == "INSERT_CLIP":
        clip = _closed(result["clip"], _INSERT_CLIP_FIELDS, "INSERT_CLIP clip")
        _validate_timeline_clip_mapping(
            _seal(
                {
                    "schemaVersion": _timeline_clip_schema_for_command(clip),
                    **clip,
                    "timelineVersionRef": new_timeline_version_ref,
                }
            )
        )
    elif operation == "BIND_EFFECT_RESULT":
        _ref(result["effectResultRef"], "effectResultRef")
        _digest_value(result["effectResultDigest"], "effectResultDigest")
    elif operation == "MOVE_CLIP":
        _ref(result["trackRef"], "trackRef")
        start = _integer(
            result["timelineStartFrameInclusive"],
            "timelineStartFrameInclusive",
            maximum=MAX_DURATION_FRAMES,
        )
        end = _integer(
            result["timelineEndFrameExclusive"],
            "timelineEndFrameExclusive",
            minimum=1,
            maximum=MAX_DURATION_FRAMES,
        )
        if start >= end:
            raise TimelineEditingRangeError("MOVE_CLIP range is invalid")
    elif operation == "TRIM_CLIP":
        start = _integer(
            result["timelineStartFrameInclusive"],
            "timelineStartFrameInclusive",
            maximum=MAX_DURATION_FRAMES,
        )
        end = _integer(
            result["timelineEndFrameExclusive"],
            "timelineEndFrameExclusive",
            minimum=1,
            maximum=MAX_DURATION_FRAMES,
        )
        source_binding = result["sourceBinding"]
        if start >= end or not isinstance(source_binding, Mapping):
            raise TimelineEditingRangeError("TRIM_CLIP range is invalid")
        source_fields = frozenset(source_binding)
        if source_fields == _VIDEO_SOURCE_FIELDS:
            _validate_source_binding(source_binding, "VIDEO")
        elif source_fields == _AUDIO_SOURCE_FIELDS:
            _validate_source_binding(source_binding, "AUDIO")
        else:
            raise TimelineEditingContractError(
                "TRIM_CLIP sourceBinding fields are invalid"
            )
    elif operation == "SPLIT_CLIP":
        _integer(
            result["splitTimelineFrame"],
            "splitTimelineFrame",
            minimum=1,
            maximum=MAX_DURATION_FRAMES,
        )
        _ref(result["rightClipRef"], "rightClipRef")
    elif operation == "REORDER_TRACK":
        _ref(result["trackRef"], "trackRef")
        _integer(result["order"], "order", maximum=3)
    elif operation == "SET_TRANSITION":
        if result["edge"] not in {"IN", "OUT"}:
            raise TimelineEditingContractError("transition edge is invalid")
        if result["transition"] is not None:
            _validate_transition_spec_mapping(
                _wire(result["transition"], TransitionSpec)
            )
    elif operation == "SET_SPEED":
        _validate_speed_spec_mapping(_wire(result["speed"], SpeedSpec))
    elif operation == "SET_TRANSFORM":
        _validate_transform_spec_mapping(_wire(result["transform"], TransformSpec))
    elif operation == "SET_MASKS":
        if not isinstance(result["maskBindings"], list):
            raise TimelineEditingContractError("maskBindings must be a list")
        for item in result["maskBindings"]:
            _validate_mask_binding_mapping(_wire(item, MaskBinding))
    elif operation == "SET_SAFE_AREA":
        _closed(result["safeArea"], _SAFE_AREA_FIELDS, "safeArea")
    elif operation == "SET_OUTPUT_PROFILES":
        if not isinstance(result["outputProfileBindings"], list) or not result[
            "outputProfileBindings"
        ]:
            raise TimelineEditingContractError(
                "outputProfileBindings must be a non-empty list"
            )
        for item in result["outputProfileBindings"]:
            _validate_output_profile_binding_mapping(
                _wire(item, OutputProfileBinding)
            )
    return result


def _validate_timeline_edit_command_mapping(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _EDIT_COMMAND_FIELDS, "TimelineEditCommand")
    schema_version = result["schemaVersion"]
    if schema_version not in {
        TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
        TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
    }:
        raise TimelineEditingContractError("TimelineEditCommand schema is unsupported")
    _ref(result["operationRef"], "operationRef")
    _ref(result["idempotencyKey"], "idempotencyKey")
    _ref(result["parentTimelineVersionRef"], "parentTimelineVersionRef")
    _digest_value(
        result["parentTimelineVersionDigest"], "parentTimelineVersionDigest"
    )
    _ref(result["newTimelineVersionRef"], "newTimelineVersionRef")
    operation = result["operation"]
    allowed_operations = (
        TIMELINE_EDIT_OPERATIONS_V2
        if schema_version == TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2
        else EDIT_OPERATIONS
    )
    if operation not in allowed_operations:
        raise TimelineEditingContractError("edit operation is invalid")
    _validate_edit_arguments(
        operation,
        result["arguments"],
        new_timeline_version_ref=result["newTimelineVersionRef"],
        schema_version=schema_version,
    )
    _timestamp(result["createdAt"])
    return result


def build_timeline_edit_command(command: Mapping[str, Any]) -> dict[str, Any]:
    value = _closed(
        command, _EDIT_COMMAND_INPUT_FIELDS, "TimelineEditCommand command"
    )
    _reject_forbidden_keys(value["arguments"])
    schema_version = (
        TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2
        if value["operation"] in TIMELINE_EDIT_OPERATIONS_V2
        else TIMELINE_EDIT_COMMAND_SCHEMA_VERSION
    )
    result = {"schemaVersion": schema_version, **value}
    for field, expected in (
        ("transition", TransitionSpec),
        ("speed", SpeedSpec),
        ("transform", TransformSpec),
    ):
        if isinstance(result["arguments"], Mapping) and field in result["arguments"]:
            result["arguments"][field] = _wire(result["arguments"][field], expected)
    if "maskBindings" in result["arguments"]:
        result["arguments"]["maskBindings"] = [
            _wire(item, MaskBinding)
            for item in result["arguments"]["maskBindings"]
        ]
    if "outputProfileBindings" in result["arguments"]:
        result["arguments"]["outputProfileBindings"] = [
            _wire(item, OutputProfileBinding)
            for item in result["arguments"]["outputProfileBindings"]
        ]
    return _validate_timeline_edit_command_mapping(_seal(result))


def validate_timeline_edit_command(value: Any) -> "TimelineEditCommand":
    return TimelineEditCommand._from_validated(
        _validate_timeline_edit_command_mapping(value)
    )


class TimelineEditCommand(_ImmutableWireContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "TimelineEditCommand":
        return cls._from_validated(_validate_timeline_edit_command_mapping(value))


def assert_timeline_edit_replay(
    existing_command_digest: str, command: TimelineEditCommand | Mapping[str, Any]
) -> None:
    _digest_value(existing_command_digest, "existingCommandDigest")
    if type(command) is TimelineEditCommand:
        mapping = command.as_dict()
    elif (
        isinstance(command, Mapping)
        and command.get("schemaVersion")
        in {
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        }
        and "payloadDigest" in command
    ):
        mapping = _validate_timeline_edit_command_mapping(command)
    else:
        mapping = build_timeline_edit_command(command)
    if mapping["payloadDigest"] != existing_command_digest:
        raise TimelineEditingConflictError("changed idempotency replay")


@dataclass(frozen=True, slots=True)
class TimelineEditChain:
    versions: tuple[TimelineVersion, ...]
    commands: tuple[TimelineEditCommand, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "versions": [item.as_dict() for item in self.versions],
            "commands": [item.as_dict() for item in self.commands],
        }


def validate_timeline_edit_chain(
    versions: Sequence[TimelineVersion | Mapping[str, Any]],
    commands: Sequence[TimelineEditCommand | Mapping[str, Any]],
) -> TimelineEditChain:
    """Validate one exact version/operation lineage with no orphan records."""

    if not isinstance(versions, Sequence) or isinstance(versions, (str, bytes)):
        raise TimelineEditingContractError("versions must be a sequence")
    if not isinstance(commands, Sequence) or isinstance(commands, (str, bytes)):
        raise TimelineEditingContractError("commands must be a sequence")
    if not versions:
        raise TimelineEditingContractError("Timeline edit chain is empty")
    prevalidated_versions: list[
        tuple[TimelineVersion | Mapping[str, Any], dict[str, Any]]
    ] = []
    for item in versions:
        mapping = (
            item.as_dict()
            if type(item) is TimelineVersion
            else _validate_timeline_version_structure(item)
        )
        prevalidated_versions.append((item, mapping))
    version_refs = [
        mapping["timelineVersionRef"] for _, mapping in prevalidated_versions
    ]
    if len(version_refs) != len(set(version_refs)):
        raise TimelineEditingConflictError(
            "Timeline edit chain reuses a TimelineVersion ref"
        )

    version_wrappers: list[TimelineVersion] = []
    predecessor: TimelineVersion | None = None
    for index, (item, mapping) in enumerate(prevalidated_versions, start=1):
        if type(item) is TimelineVersion:
            _validate_predecessor(mapping, predecessor)
            wrapper = item
        else:
            _validate_predecessor(mapping, predecessor)
            wrapper = TimelineVersion._from_validated(mapping)
        if mapping["versionNumber"] != index:
            raise TimelineEditingStaleInputError(
                "Timeline edit chain version order is not contiguous"
            )
        version_wrappers.append(wrapper)
        predecessor = wrapper
    command_wrappers = [
        item
        if type(item) is TimelineEditCommand
        else validate_timeline_edit_command(item)
        for item in commands
    ]
    if len(command_wrappers) != len(version_wrappers) - 1:
        raise TimelineEditingStaleInputError(
            "Timeline edit chain command count is invalid"
        )
    command_mappings = [item.as_dict() for item in command_wrappers]
    if (
        len({item["operationRef"] for item in command_mappings})
        != len(command_mappings)
        or len({item["idempotencyKey"] for item in command_mappings})
        != len(command_mappings)
        or len({item["newTimelineVersionRef"] for item in command_mappings})
        != len(command_mappings)
    ):
        raise TimelineEditingConflictError(
            "Timeline edit chain contains duplicate operations"
        )
    commands_by_successor = {
        item["newTimelineVersionRef"]: item for item in command_mappings
    }
    for predecessor_wrapper, successor_wrapper in zip(
        version_wrappers, version_wrappers[1:]
    ):
        prior = predecessor_wrapper.as_dict()
        successor = successor_wrapper.as_dict()
        command = commands_by_successor.get(successor["timelineVersionRef"])
        if (
            command is None
            or command["parentTimelineVersionRef"]
            != prior["timelineVersionRef"]
            or command["parentTimelineVersionDigest"] != prior["payloadDigest"]
            or command["createdAt"] != successor["createdAt"]
        ):
            raise TimelineEditingStaleInputError(
                "Timeline edit operation/version binding is stale"
            )
    return TimelineEditChain(
        tuple(version_wrappers), tuple(command_wrappers)
    )


def _reseal_clip(value: Mapping[str, Any], **updates: Any) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("payloadDigest", None)
    result.update(deepcopy(updates))
    return _validate_timeline_clip_mapping(_seal(result))


def _reseal_track(value: Mapping[str, Any], **updates: Any) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop("payloadDigest", None)
    result.update(deepcopy(updates))
    return _validate_timeline_track_mapping(_seal(result))


def _find_clip(clips: list[dict[str, Any]], clip_ref: str) -> dict[str, Any]:
    matches = [item for item in clips if item["clipRef"] == clip_ref]
    if len(matches) != 1:
        raise TimelineEditingContractError("clipRef does not resolve exactly once")
    return matches[0]


def _replace_clip(
    clips: list[dict[str, Any]], old: Mapping[str, Any], new: Mapping[str, Any]
) -> None:
    index = next(
        index for index, item in enumerate(clips) if item["clipRef"] == old["clipRef"]
    )
    clips[index] = deepcopy(dict(new))


def _split_masks(
    masks: Sequence[Mapping[str, Any]], split_frame: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    for mask in masks:
        start = mask["frameRangeStartInclusive"]
        end = mask["frameRangeEndExclusive"]
        if start < split_frame:
            payload = deepcopy(dict(mask))
            payload.pop("payloadDigest", None)
            payload["frameRangeEndExclusive"] = min(end, split_frame)
            left.append(_validate_mask_binding_mapping(_seal(payload)))
        if end > split_frame:
            payload = deepcopy(dict(mask))
            payload.pop("payloadDigest", None)
            payload["frameRangeStartInclusive"] = max(start, split_frame)
            right.append(_validate_mask_binding_mapping(_seal(payload)))
    return left, right


@dataclass(frozen=True, slots=True)
class TimelineEditResult:
    timeline_version: TimelineVersion
    tracks: tuple[TimelineTrack, ...]
    clips: tuple[TimelineClip, ...]
    edit_command: TimelineEditCommand

    @property
    def edit_command_digest(self) -> str:
        return self.edit_command.as_dict()["payloadDigest"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "timelineVersion": self.timeline_version.as_dict(),
            "tracks": [item.as_dict() for item in self.tracks],
            "clips": [item.as_dict() for item in self.clips],
            "editCommand": self.edit_command.as_dict(),
        }


def apply_timeline_edit(
    parent_version: TimelineVersion,
    parent_tracks: Sequence[TimelineTrack],
    parent_clips: Sequence[TimelineClip],
    command: TimelineEditCommand | Mapping[str, Any],
    *,
    existing_timeline_versions: Sequence[TimelineVersion],
    timeline: Timeline | Mapping[str, Any] | None = None,
    source_resolver: SourceAuthorityResolver | None = None,
    expected_script: Mapping[str, Any] | None = None,
    expected_storyboard: Mapping[str, Any] | None = None,
) -> TimelineEditResult:
    if type(parent_version) is not TimelineVersion:
        raise TimelineEditingAuthorityError("exact parent TimelineVersion is required")
    if any(type(item) is not TimelineTrack for item in parent_tracks) or any(
        type(item) is not TimelineClip for item in parent_clips
    ):
        raise TimelineEditingAuthorityError("exact parent Track/Clip wrappers are required")
    if type(command) is TimelineEditCommand:
        edit_mapping = command.as_dict()
    elif (
        isinstance(command, Mapping)
        and command.get("schemaVersion")
        in {
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION,
            TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2,
        }
        and "payloadDigest" in command
    ):
        edit_mapping = _validate_timeline_edit_command_mapping(command)
    else:
        edit_mapping = build_timeline_edit_command(command)
    edit = TimelineEditCommand._from_validated(
        _validate_timeline_edit_command_mapping(edit_mapping)
    )
    parent = validate_timeline_snapshot(
        parent_version,
        parent_tracks,
        parent_clips,
        timeline=timeline,
        source_resolver=source_resolver,
        expected_script=expected_script,
        expected_storyboard=expected_storyboard,
    )
    version = parent.timeline_version.as_dict()
    if (
        not isinstance(existing_timeline_versions, Sequence)
        or isinstance(existing_timeline_versions, (str, bytes))
        or any(type(item) is not TimelineVersion for item in existing_timeline_versions)
    ):
        raise TimelineEditingAuthorityError(
            "complete exact TimelineVersion history is required"
        )
    validated_history: list[TimelineVersion] = []
    predecessor: TimelineVersion | None = None
    try:
        for item in existing_timeline_versions:
            validated = validate_timeline_version(
                item.as_dict(), predecessor=predecessor
            )
            validated_history.append(validated)
            predecessor = validated
    except EpisodeProductionError as exc:
        raise TimelineEditingAuthorityError(
            "complete exact TimelineVersion history is invalid"
        ) from exc
    history_mappings = [item.as_dict() for item in validated_history]
    existing_refs = [item["timelineVersionRef"] for item in history_mappings]
    if (
        len(history_mappings) != version["versionNumber"]
        or len(existing_refs) != len(set(existing_refs))
        or history_mappings[-1:] != [version]
    ):
        raise TimelineEditingAuthorityError(
            "complete exact TimelineVersion history is invalid"
        )
    if (
        edit_mapping["parentTimelineVersionRef"] != version["timelineVersionRef"]
        or edit_mapping["parentTimelineVersionDigest"] != version["payloadDigest"]
        or edit_mapping["newTimelineVersionRef"] in set(existing_refs)
    ):
        raise TimelineEditingStaleInputError("edit parent/new version binding is stale")
    tracks = [item.as_dict() for item in parent.tracks]
    clips = [item.as_dict() for item in parent.clips]
    operation = edit_mapping["operation"]
    arguments = edit_mapping["arguments"]

    if operation == "INSERT_CLIP":
        if any(item["clipRef"] == arguments["clip"]["clipRef"] for item in clips):
            raise TimelineEditingConflictError("clipRef already exists")
        clip_command = {
            **deepcopy(arguments["clip"]),
            "timelineVersionRef": edit_mapping["newTimelineVersionRef"],
        }
        clips.append(build_timeline_clip(clip_command))
    elif operation == "BIND_EFFECT_RESULT":
        target = _find_clip(clips, arguments["clipRef"])
        source = target["sourceBinding"]
        if (
            target["schemaVersion"] != TIMELINE_CLIP_SCHEMA_VERSION_V3
            or target["clipKind"] != "EFFECT"
            or source.get("effectResultRef") is not None
            or source.get("effectResultDigest") is not None
        ):
            raise TimelineEditingAuthorityError(
                "BIND_EFFECT_RESULT requires one unbound v3 EFFECT clip"
            )
        if source_resolver is None:
            raise TimelineEditingAuthorityError(
                "BIND_EFFECT_RESULT requires exact Effect authority"
            )
        requirement = source_resolver(
            "EFFECT_REQUIREMENT", source["effectRequirementRef"]
        )
        effect_result = source_resolver(
            "EFFECT_RESULT", arguments["effectResultRef"]
        )
        if not isinstance(requirement, Mapping) or not isinstance(
            effect_result, Mapping
        ):
            raise TimelineEditingAuthorityError(
                "BIND_EFFECT_RESULT authority is not resolvable"
            )
        if (
            effect_result.get("resultRef") != arguments["effectResultRef"]
            or effect_result.get("payloadDigest")
            != arguments["effectResultDigest"]
            or effect_result.get("requirementRef")
            != source["effectRequirementRef"]
            or effect_result.get("requirementDigest")
            != source["effectRequirementDigest"]
            or _deterministic_effect_kind(effect_result)
            != source["effectKind"]
            or effect_result.get("workspaceRef") != version["workspaceRef"]
            or effect_result.get("productionRunRef")
            != version["productionRunRef"]
            or requirement.get("payloadDigest")
            != source["effectRequirementDigest"]
            or requirement.get("workspaceRef") != version["workspaceRef"]
            or requirement.get("productionRunRef")
            != version["productionRunRef"]
            or effect_result.get("targetShotRef")
            != requirement.get("targetShotRef")
            or effect_result.get("frameRangeStartInclusive")
            != requirement.get("frameRangeStartInclusive")
            or effect_result.get("frameRangeEndExclusive")
            != requirement.get("frameRangeEndExclusive")
            or not _effect_result_is_bindable(
                effect_result,
                effect_kind=source["effectKind"],
            )
            or effect_result.get("publicationAllowed") is not False
        ):
            raise TimelineEditingStaleInputError(
                "BIND_EFFECT_RESULT authority is stale"
            )
        bound_source = {
            **deepcopy(source),
            "effectResultRef": arguments["effectResultRef"],
            "effectResultDigest": arguments["effectResultDigest"],
        }
        _replace_clip(
            clips,
            target,
            _reseal_clip(target, sourceBinding=bound_source),
        )
    elif operation == "REMOVE_CLIP":
        target = _find_clip(clips, arguments["clipRef"])
        clips.remove(target)
    elif operation == "MOVE_CLIP":
        target = _find_clip(clips, arguments["clipRef"])
        old_span = target["timelineEndFrameExclusive"] - target[
            "timelineStartFrameInclusive"
        ]
        new_span = arguments["timelineEndFrameExclusive"] - arguments[
            "timelineStartFrameInclusive"
        ]
        if old_span != new_span:
            raise TimelineEditingRangeError("MOVE_CLIP cannot trim")
        destination = [
            item for item in tracks if item["trackRef"] == arguments["trackRef"]
        ]
        if (
            len(destination) != 1
            or target["clipKind"] not in CLIP_KIND_BY_TRACK[destination[0]["trackKind"]]
        ):
            raise TimelineEditingContractError("MOVE_CLIP target track is invalid")
        frame_delta = (
            arguments["timelineStartFrameInclusive"]
            - target["timelineStartFrameInclusive"]
        )
        moved_masks: list[dict[str, Any]] = []
        for mask in target["maskBindings"]:
            payload = deepcopy(mask)
            payload.pop("payloadDigest", None)
            payload["frameRangeStartInclusive"] += frame_delta
            payload["frameRangeEndExclusive"] += frame_delta
            moved_masks.append(_validate_mask_binding_mapping(_seal(payload)))
        moved_source = deepcopy(target["sourceBinding"])
        if target["clipKind"] == "SUBTITLE":
            for word in moved_source["wordTiming"]:
                word["timelineStartFrameInclusive"] += frame_delta
                word["timelineEndFrameExclusive"] += frame_delta
        _replace_clip(
            clips,
            target,
            _reseal_clip(
                target,
                trackRef=arguments["trackRef"],
                timelineStartFrameInclusive=arguments[
                    "timelineStartFrameInclusive"
                ],
                timelineEndFrameExclusive=arguments["timelineEndFrameExclusive"],
                maskBindings=moved_masks,
                sourceBinding=moved_source,
            ),
        )
    elif operation == "TRIM_CLIP":
        target = _find_clip(clips, arguments["clipRef"])
        replacement_source = arguments["sourceBinding"]
        mutable_source_fields = {
            "VIDEO": {"sourceInFrameInclusive", "sourceOutFrameExclusive"},
            "AUDIO": {
                "sourceStartSampleInclusive",
                "sourceEndSampleExclusive",
            },
        }.get(target["clipKind"])
        if mutable_source_fields is None:
            raise TimelineEditingContractError(
                "TRIM_CLIP supports only VIDEO and AUDIO clips"
            )
        current_source = target["sourceBinding"]
        if (
            set(replacement_source) != set(current_source)
            or any(
                replacement_source[field] != current_source[field]
                for field in current_source
                if field not in mutable_source_fields
            )
        ):
            raise TimelineEditingAuthorityError(
                "TRIM_CLIP cannot rebind source authority or mix semantics"
            )
        _replace_clip(
            clips,
            target,
            _reseal_clip(
                target,
                timelineStartFrameInclusive=arguments[
                    "timelineStartFrameInclusive"
                ],
                timelineEndFrameExclusive=arguments["timelineEndFrameExclusive"],
                sourceBinding=replacement_source,
            ),
        )
    elif operation == "SPLIT_CLIP":
        target = _find_clip(clips, arguments["clipRef"])
        split = arguments["splitTimelineFrame"]
        if (
            target["clipKind"] not in {"VIDEO", "AUDIO"}
            or split <= target["timelineStartFrameInclusive"]
            or split >= target["timelineEndFrameExclusive"]
            or any(item["clipRef"] == arguments["rightClipRef"] for item in clips)
        ):
            raise TimelineEditingRangeError("SPLIT_CLIP boundary/kind is invalid")
        source = deepcopy(target["sourceBinding"])
        timeline_offset = split - target["timelineStartFrameInclusive"]
        timeline_span = target["timelineEndFrameExclusive"] - target[
            "timelineStartFrameInclusive"
        ]
        if target["clipKind"] == "VIDEO":
            source_offset_numerator = timeline_offset * target["speed"]["numerator"]
            if source_offset_numerator % target["speed"]["denominator"]:
                raise TimelineEditingRangeError("SPLIT_CLIP source boundary is inexact")
            source_split = source["sourceInFrameInclusive"] + (
                source_offset_numerator // target["speed"]["denominator"]
            )
            left_source = {**source, "sourceOutFrameExclusive": source_split}
            right_source = {**source, "sourceInFrameInclusive": source_split}
        else:
            source_span = source["sourceEndSampleExclusive"] - source[
                "sourceStartSampleInclusive"
            ]
            scaled = source_span * timeline_offset
            if scaled % timeline_span:
                raise TimelineEditingRangeError("SPLIT_CLIP sample boundary is inexact")
            source_split = source["sourceStartSampleInclusive"] + scaled // timeline_span
            left_source = {**source, "sourceEndSampleExclusive": source_split}
            right_source = {**source, "sourceStartSampleInclusive": source_split}
            left_source["fadeOutSamples"] = 0
            right_source["fadeInSamples"] = 0
        left_masks, right_masks = _split_masks(target["maskBindings"], split)
        cut = build_transition_spec(
            {
                "transitionKind": "CUT",
                "durationFrames": 0,
                "curve": "LINEAR",
                "alignment": "CENTER",
            }
        )
        left = _reseal_clip(
            target,
            timelineEndFrameExclusive=split,
            sourceBinding=left_source,
            transitionOut=cut,
            maskBindings=left_masks,
        )
        right_payload = deepcopy(target)
        right_payload.pop("payloadDigest", None)
        right_payload.update(
            {
                "clipRef": arguments["rightClipRef"],
                "timelineStartFrameInclusive": split,
                "sourceBinding": right_source,
                "transitionIn": cut,
                "maskBindings": right_masks,
            }
        )
        right = _validate_timeline_clip_mapping(_seal(right_payload))
        _replace_clip(clips, target, left)
        clips.append(right)
    elif operation in {"ENABLE_CLIP", "DISABLE_CLIP"}:
        target = _find_clip(clips, arguments["clipRef"])
        _replace_clip(
            clips,
            target,
            _reseal_clip(target, enabled=operation == "ENABLE_CLIP"),
        )
    elif operation == "REORDER_TRACK":
        candidates = [item for item in tracks if item["trackRef"] == arguments["trackRef"]]
        if len(candidates) != 1:
            raise TimelineEditingContractError("trackRef does not resolve exactly once")
        ordered = sorted(tracks, key=lambda item: item["order"])
        target = candidates[0]
        ordered.remove(target)
        ordered.insert(arguments["order"], target)
        tracks = [_reseal_track(item, order=index) for index, item in enumerate(ordered)]
    elif operation == "SET_TRANSITION":
        target = _find_clip(clips, arguments["clipRef"])
        field = "transitionIn" if arguments["edge"] == "IN" else "transitionOut"
        transition = (
            None
            if arguments["transition"] is None
            else _wire(arguments["transition"], TransitionSpec)
        )
        _replace_clip(clips, target, _reseal_clip(target, **{field: transition}))
    elif operation == "SET_SPEED":
        target = _find_clip(clips, arguments["clipRef"])
        speed_mapping = _wire(arguments["speed"], SpeedSpec)
        numerator = speed_mapping["numerator"]
        denominator = speed_mapping["denominator"]
        source = target["sourceBinding"]
        if target["clipKind"] == "VIDEO":
            source_span = source["sourceOutFrameExclusive"] - source[
                "sourceInFrameInclusive"
            ]
            scaled = source_span * denominator
            if scaled % numerator:
                raise TimelineEditingRangeError(
                    "SET_SPEED cannot map VIDEO duration exactly"
                )
            timeline_span = scaled // numerator
        elif target["clipKind"] == "AUDIO":
            source_span = source["sourceEndSampleExclusive"] - source[
                "sourceStartSampleInclusive"
            ]
            rate = version["frameRate"]
            scaled = source_span * denominator * rate["numerator"]
            divisor = source["sampleRate"] * rate["denominator"] * numerator
            if scaled % divisor:
                raise TimelineEditingRangeError(
                    "SET_SPEED cannot map AUDIO duration exactly"
                )
            timeline_span = scaled // divisor
        else:
            raise TimelineEditingContractError(
                "SET_SPEED is unsupported for this clip kind"
            )
        if timeline_span <= 0:
            raise TimelineEditingRangeError("SET_SPEED duration is invalid")
        _replace_clip(
            clips,
            target,
            _reseal_clip(
                target,
                speed=speed_mapping,
                timelineEndFrameExclusive=(
                    target["timelineStartFrameInclusive"] + timeline_span
                ),
            ),
        )
    elif operation == "SET_TRANSFORM":
        target = _find_clip(clips, arguments["clipRef"])
        _replace_clip(
            clips,
            target,
            _reseal_clip(
                target, transform=_wire(arguments["transform"], TransformSpec)
            ),
        )
    elif operation == "SET_MASKS":
        target = _find_clip(clips, arguments["clipRef"])
        _replace_clip(
            clips,
            target,
            _reseal_clip(
                target,
                maskBindings=[
                    _wire(item, MaskBinding) for item in arguments["maskBindings"]
                ],
            ),
        )

    new_version_ref = edit_mapping["newTimelineVersionRef"]
    tracks = [
        _reseal_track(item, timelineVersionRef=new_version_ref) for item in tracks
    ]
    clips = [
        _reseal_clip(item, timelineVersionRef=new_version_ref) for item in clips
    ]
    tracks.sort(key=lambda item: (item["order"], item["trackRef"]))
    next_profiles = version["outputProfileBindings"]
    next_safe_area = version["safeArea"]
    if operation == "SET_SAFE_AREA":
        next_safe_area = deepcopy(arguments["safeArea"])
    elif operation == "SET_OUTPUT_PROFILES":
        next_profiles = [
            _wire(item, OutputProfileBinding)
            for item in arguments["outputProfileBindings"]
        ]
    version_command = {
        key: deepcopy(version[key]) for key in _TIMELINE_VERSION_COMMAND_FIELDS
    }
    version_command.update(
        {
            "timelineVersionRef": new_version_ref,
            "versionNumber": version["versionNumber"] + 1,
            "parentTimelineVersionRef": version["timelineVersionRef"],
            "parentTimelineVersionDigest": version["payloadDigest"],
            "safeArea": next_safe_area,
            "trackRefs": [item["trackRef"] for item in tracks],
            "createdAt": edit_mapping["createdAt"],
        }
    )
    successor_mapping = build_timeline_version(
        version_command,
        output_profile_bindings=next_profiles,
        tracks=tracks,
        clips=clips,
        predecessor=parent_version,
    )
    successor = validate_timeline_snapshot(
        TimelineVersion._from_validated(successor_mapping),
        [TimelineTrack._from_validated(item) for item in tracks],
        [TimelineClip._from_validated(item) for item in clips],
        timeline=timeline,
        source_resolver=source_resolver,
        expected_script=expected_script,
        expected_storyboard=expected_storyboard,
    )
    return TimelineEditResult(
        successor.timeline_version,
        successor.tracks,
        successor.clips,
        edit,
    )


__all__ = [
    "BLEND_MODES",
    "CLIP_KIND_BY_TRACK",
    "DETERMINISTIC_EFFECT_KINDS",
    "EDIT_OPERATIONS",
    "FIXED_OPACITY_SCALE",
    "LANE_POLICIES",
    "LEGACY_TIMELINE_SCHEMA_VERSION",
    "LEGACY_TIMELINE_VERSION_SCHEMA_VERSION",
    "M13_E1_DETERMINISTIC_EFFECT_KINDS",
    "M13_E2_DETERMINISTIC_EFFECT_KINDS",
    "MASK_BINDING_SCHEMA_VERSION",
    "MASK_MODES",
    "MaskBinding",
    "OUTPUT_PROFILE_BINDING_SCHEMA_VERSION",
    "OutputProfileBinding",
    "PERSPECTIVE_MODES",
    "SPEED_SPEC_SCHEMA_VERSION",
    "SourceAuthorityResolver",
    "SpeedSpec",
    "TIMELINE_CLIP_SCHEMA_VERSION",
    "TIMELINE_CLIP_SCHEMA_VERSION_V2",
    "TIMELINE_CLIP_SCHEMA_VERSION_V3",
    "TIMELINE_CLIP_SNAPSHOT_SCHEMA_VERSION",
    "TIMELINE_EDIT_COMMAND_SCHEMA_VERSION",
    "TIMELINE_EDIT_COMMAND_SCHEMA_VERSION_V2",
    "TIMELINE_EDIT_OPERATIONS_V2",
    "TIMELINE_PROVENANCE",
    "TIMELINE_SCHEMA_VERSION",
    "TIMELINE_SCHEMA_VERSION_V3",
    "TIMELINE_SNAPSHOT_SCHEMA_VERSION",
    "TIMELINE_TRACK_KINDS",
    "TIMELINE_TRACK_SCHEMA_VERSION",
    "TIMELINE_TRACK_SCHEMA_VERSION_V2",
    "TIMELINE_TRACK_SNAPSHOT_SCHEMA_VERSION",
    "TIMELINE_VERSION_SCHEMA_VERSION",
    "TIMELINE_VERSION_SCHEMA_VERSION_V3",
    "TRANSFORM_SPEC_SCHEMA_VERSION",
    "TRANSITION_ALIGNMENTS",
    "TRANSITION_CURVES",
    "TRANSITION_KINDS",
    "TRANSITION_SPEC_SCHEMA_VERSION",
    "Timeline",
    "TimelineClip",
    "TimelineEditCommand",
    "TimelineEditChain",
    "TimelineEditResult",
    "TimelineEditingAuthorityError",
    "TimelineEditingConflictError",
    "TimelineEditingContractError",
    "TimelineEditingRangeError",
    "TimelineEditingStaleInputError",
    "TimelineSnapshot",
    "TimelineTrack",
    "TimelineVersion",
    "TransformSpec",
    "TransitionSpec",
    "apply_timeline_edit",
    "assert_timeline_edit_replay",
    "build_mask_binding",
    "build_output_profile_binding",
    "build_speed_spec",
    "build_timeline",
    "build_timeline_clip",
    "build_timeline_edit_command",
    "build_timeline_track",
    "build_timeline_version",
    "build_transform_spec",
    "build_transition_spec",
    "compute_timeline_snapshot_digests",
    "read_timeline_clip",
    "read_timeline_root",
    "read_timeline_track",
    "read_timeline_version",
    "validate_mask_binding",
    "validate_output_profile_binding",
    "validate_speed_spec",
    "validate_timeline",
    "validate_timeline_clip",
    "validate_timeline_edit_command",
    "validate_timeline_edit_chain",
    "validate_timeline_snapshot",
    "validate_timeline_track",
    "validate_timeline_version",
    "validate_transform_spec",
    "validate_transition_spec",
]
