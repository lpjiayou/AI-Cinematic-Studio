"""Closed M13-E4 screen-space distance and visual-state contracts.

V5 owns immutable Requirement/Result lineage only.  All paths and runtime
details are resolved below this boundary by the existing V4 composition owner.
The visual states in this module are render states, never M6/M8 canonical state.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import gcd, isqrt
import re
from typing import Any, Mapping, Sequence

from .evidence import EpisodeProductionEvidenceRepository, EvidenceRecord
from .foundation import (
    EpisodeProductionError,
    RepositoryUnavailableError,
    StaleInputError,
    _digest,
    _idempotency_key,
    _required_ref,
)


DISTANCE_STATE_TRANSITION = "DISTANCE_STATE_TRANSITION"
DISTANCE_STATE_TRANSITION_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-distance-state-transition-requirement.v1"
)
DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-distance-state-execution-request.v1"
)
DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-distance-state-runtime-evidence.v1"
)
DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-distance-state-artifact-evidence.v1"
)
DISTANCE_STATE_TRANSITION_RESULT_SCHEMA_VERSION = (
    "v5.m13-distance-state-transition-result.v1"
)

DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND = (
    "DistanceStateTransitionRequirement"
)
DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND = "DistanceStateExecutionRequest"
DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND = "DistanceStateRuntimeEvidence"
DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND = "DistanceStateArtifactEvidence"
DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND = "DistanceStateTransitionResult"

DISTANCE_STATE_RENDERER_IDENTITY = "v3.deterministic-distance-state-ffmpeg"
DISTANCE_STATE_RENDERER_VERSION = "1"
DISTANCE_STATE_PROVENANCE = "LOCAL_EVIDENCE"
DECODED_FRAME_PIXEL_DIGEST_SPEC = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)

_RAW_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CONTENT_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_INTERPOLATIONS = frozenset(
    {"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"}
)
_TARGET_KINDS = frozenset({"FULL_FRAME", "OVERLAY_LAYER"})
_TRANSITION_MODES = frozenset(
    {"SCREEN_DISTANCE", "VISUAL_STATE", "SCREEN_DISTANCE_AND_VISUAL_STATE"}
)
_COORDINATE_SPACES = frozenset({"CANVAS_PIXELS", "NORMALIZED_PERMILLE"})
_DISTANCE_METRICS = frozenset(
    {"SCREEN_EUCLIDEAN_PIXELS", "RELATIVE_SCALE_PERMILLE"}
)
_DIRECTIONS = frozenset({"APPROACH", "RECEDE", "LATERAL", "CUSTOM_EXACT"})
_VISIBILITY = frozenset({"VISIBLE", "HIDDEN"})
_BLEND_MODES = frozenset({"NORMAL"})
_FORBIDDEN_KEYS = (
    "path", "storage", "filter", "argv", "argument", "expression",
    "random", "shell", "command", "prompt", "world", "physical",
    "meter", "centimeter", "natural", "environment", "canonicalmutation",
)
_FORBIDDEN_VALUES = frozenset(
    {"WORLD_METERS", "WORLD_CENTIMETERS", "UNSPECIFIED_3D", "NATURAL_LANGUAGE"}
)

_MOTION_FIELDS = frozenset(
    {
        "frame", "x", "y", "scaleXNumerator", "scaleXDenominator",
        "scaleYNumerator", "scaleYDenominator", "rotationMilliDegrees",
        "perspectiveQuad", "interpolation",
    }
)
_DISTANCE_FIELDS = frozenset(
    {"metric", "startValue", "endValue", "tolerance", "direction", "referenceX", "referenceY"}
)
_STATE_FIELDS = frozenset(
    {"stateRef", "visibility", "opacityPermille", "variantAssetVersionRef", "variantAssetVersionDigest", "layer", "blendMode"}
)
_SCHEDULE_FIELDS = frozenset(
    {"stateRef", "startFrameInclusive", "endFrameExclusive", "transitionInterpolation"}
)
_PUBLIC_FIELDS = frozenset(
    {
        "workspaceRef", "productionRunRef", "requirementRef", "effectMode",
        "targetShotRef", "targetShotVersionRef", "targetShotVersionDigest",
        "basePlateAssetVersionRef", "basePlateAssetVersionDigest",
        "targetKind", "subjectLayerAssetVersionRef",
        "subjectLayerAssetVersionDigest", "maskAssetVersionRef",
        "maskAssetVersionDigest", "frameRangeStartInclusive",
        "frameRangeEndExclusive", "transitionMode", "coordinateSpace",
        "motionKeyframes", "distanceContract", "startStateRef",
        "endStateRef", "visualStateDefinitions", "visualStateSchedule",
        "blendMode", "layer",
    }
)
_REQUIREMENT_FIELDS = _PUBLIC_FIELDS | frozenset(
    {
        "schemaVersion", "basePlateFileDigest", "basePlatePixelDigest",
        "subjectLayerFileDigest", "subjectLayerPixelDigest", "maskFileDigest",
        "maskPixelDigest", "canvasWidth", "canvasHeight", "frameCount",
        "frameRate", "publicationAllowed", "payloadDigest",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion", "executionRequestRef", "workspaceRef",
        "productionRunRef", "requirementRef", "requirementDigest",
        "effectMode", "transitionSpec", "publicationAllowed", "payloadDigest",
    }
)
_PROBE_FIELDS = frozenset(
    {"width", "height", "frameCount", "frameRate", "pixelFormat", "container", "videoCodec"}
)
_OUTPUT_DIGEST_FIELDS = frozenset(
    {
        "fileDigest", "fileDigestAlgorithm", "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec", "pixelMode", "width", "height",
        "frameCount", "frameRate",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "schemaVersion", "runtimeEvidenceRef", "workspaceRef",
        "productionRunRef", "requirementRef", "requirementDigest",
        "executionRequestRef", "executionRequestDigest",
        "v3ExecutionRequestDigest", "effectMode", "rendererIdentity",
        "rendererVersion", "ffmpegIdentity", "executionManifestDigest",
        "gpuUsed", "publicationAllowed", "payloadDigest",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {
        "schemaVersion", "artifactEvidenceRef", "workspaceRef",
        "productionRunRef", "requirementRef", "requirementDigest",
        "executionRequestRef", "executionRequestDigest",
        "v3ExecutionRequestDigest", "effectMode", "outputByteSize",
        "outputMediaProbe", "outputDigest", "derivedDistanceFacts",
        "appliedStateScheduleDigest", "runtimeEvidenceRef",
        "runtimeEvidenceDigest", "provenance", "publicationAllowed",
        "payloadDigest",
    }
)
_BINDING_FIELDS = frozenset(
    {
        "workspaceRef", "productionRunRef", "requirementRef",
        "requirementDigest", "executionRequestRef", "executionRequestDigest",
        "artifactEvidenceRef", "artifactEvidenceDigest", "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
    }
)
_RESULT_FIELDS = frozenset(
    {
        "schemaVersion", "workspaceRef", "productionRunRef", "resultRef",
        "effectMode", "requirementRef", "requirementDigest",
        "executionRequestRef", "executionRequestDigest",
        "artifactEvidenceRef", "artifactEvidenceDigest", "runtimeEvidenceRef",
        "runtimeEvidenceDigest", "outputFileDigest",
        "outputDecodedFramePixelDigest", "outputMediaProbe",
        "derivedDistanceFacts", "appliedStateScheduleDigest", "state",
        "assetAdmissionState", "masterState", "exportState",
        "publicationAllowed", "payloadDigest",
    }
)


class DistanceStateContractError(EpisodeProductionError):
    code = "m13_distance_state_contract_invalid"


class DistanceStateStaleInputError(StaleInputError):
    code = "m13_distance_state_stale"


class DistanceStateJournalError(RepositoryUnavailableError):
    code = "m13_distance_state_journal_invalid"


def _reject(value: Any) -> None:
    if isinstance(value, float):
        raise DistanceStateContractError("float authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if not isinstance(key, str) or any(part in normalized for part in _FORBIDDEN_KEYS):
                raise DistanceStateContractError(f"{key!s} is forbidden")
            _reject(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject(item)
    elif isinstance(value, str) and value.upper() in _FORBIDDEN_VALUES:
        raise DistanceStateContractError(f"{value} is forbidden")


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DistanceStateContractError(f"{label} fields are invalid")
    result = deepcopy(dict(value))
    _reject(result)
    return result


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise DistanceStateContractError("payloadDigest is derived")
    _reject(result)
    result["payloadDigest"] = _digest(result)
    return result


def _sealed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    result = _closed(value, fields, label)
    claimed = result.pop("payloadDigest")
    if not isinstance(claimed, str) or _RAW_SHA.fullmatch(claimed) is None or claimed != _digest(result):
        raise DistanceStateStaleInputError(f"{label} payloadDigest is stale")
    result["payloadDigest"] = claimed
    return result


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise DistanceStateContractError(f"{field} is invalid") from exc


def _raw(value: Any, field: str) -> str:
    if not isinstance(value, str) or _RAW_SHA.fullmatch(value) is None:
        raise DistanceStateContractError(f"{field} must be a raw sha256")
    return value


def _content(value: Any, field: str) -> str:
    if not isinstance(value, str) or _CONTENT_SHA.fullmatch(value) is None:
        raise DistanceStateContractError(f"{field} must be a sha256 content digest")
    return value


def _text(value: Any, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise DistanceStateContractError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise DistanceStateContractError(f"{field} is invalid")
    return value


def _nullable_pair(reference: Any, digest: Any, label: str) -> tuple[str | None, str | None]:
    if reference is None and digest is None:
        return None, None
    if reference is None or digest is None:
        raise DistanceStateContractError(f"{label} binding is partial")
    return _ref(reference, f"{label}Ref"), _raw(digest, f"{label}Digest")


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 100:
        raise DistanceStateContractError("createdAt is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DistanceStateContractError("createdAt is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DistanceStateContractError("createdAt must include timezone")
    return value


def _perspective_quad(value: Any, *, coordinate_space: str, width: int, height: int, label: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 8:
        raise DistanceStateContractError(f"{label} must contain four points")
    if coordinate_space == "NORMALIZED_PERMILLE":
        x_low, x_high = -4000, 5000
        y_low, y_high = -4000, 5000
    else:
        x_low, x_high = -width * 4, width * 5
        y_low, y_high = -height * 4, height * 5
    result = [
        _integer(
            item,
            f"{label}[{index}]",
            x_low if index % 2 == 0 else y_low,
            x_high if index % 2 == 0 else y_high,
        )
        for index, item in enumerate(value)
    ]
    points = [(result[index], result[index + 1]) for index in range(0, 8, 2)]
    crosses = []
    for index in range(4):
        a, b, c = points[index], points[(index + 1) % 4], points[(index + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
    if any(value == 0 for value in crosses) or not (all(value > 0 for value in crosses) or all(value < 0 for value in crosses)):
        raise DistanceStateContractError(f"{label} must be a non-degenerate convex quad")
    return result


def _motion(value: Any, *, start: int, end: int, coordinate_space: str, width: int, height: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 128:
        raise DistanceStateContractError("motionKeyframes is invalid")
    result: list[dict[str, Any]] = []
    previous = -1
    x_low, x_high = (-4000, 5000) if coordinate_space == "NORMALIZED_PERMILLE" else (-width * 4, width * 5)
    y_low, y_high = (-4000, 5000) if coordinate_space == "NORMALIZED_PERMILLE" else (-height * 4, height * 5)
    for index, raw in enumerate(value):
        item = _closed(raw, _MOTION_FIELDS, f"motionKeyframes[{index}]")
        frame = _integer(item["frame"], f"motionKeyframes[{index}].frame", start, end - 1)
        if frame <= previous or item["interpolation"] not in _INTERPOLATIONS:
            raise DistanceStateContractError("motionKeyframes order/interpolation is invalid")
        item["x"] = _integer(item["x"], "motion.x", x_low, x_high)
        item["y"] = _integer(item["y"], "motion.y", y_low, y_high)
        for axis in ("X", "Y"):
            numerator = _integer(item[f"scale{axis}Numerator"], f"scale{axis}Numerator", 1, 16000)
            denominator = _integer(item[f"scale{axis}Denominator"], f"scale{axis}Denominator", 1, 16000)
            if gcd(numerator, denominator) != 1:
                raise DistanceStateContractError("scale rational must be normalized")
            if numerator > 8 * denominator:
                raise DistanceStateContractError("scale exceeds the fixed render budget")
        item["rotationMilliDegrees"] = _integer(item["rotationMilliDegrees"], "rotationMilliDegrees", -360000, 360000)
        item["perspectiveQuad"] = _perspective_quad(item["perspectiveQuad"], coordinate_space=coordinate_space, width=width, height=height, label=f"motionKeyframes[{index}].perspectiveQuad")
        result.append(item)
        previous = frame
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise DistanceStateContractError("motionKeyframes must close the frame range")
    return result


def _pixel_coordinate(value: int, extent: int, coordinate_space: str, field: str) -> int:
    if coordinate_space == "CANVAS_PIXELS":
        return value
    product = value * extent
    if product % 1000:
        raise DistanceStateContractError(f"{field} does not map to an exact pixel")
    return product // 1000


def _derived_distance(motion: Sequence[Mapping[str, Any]], contract: Any, *, coordinate_space: str, width: int, height: int) -> dict[str, Any]:
    value = _closed(contract, _DISTANCE_FIELDS, "distanceContract")
    metric, direction = value["metric"], value["direction"]
    if metric not in _DISTANCE_METRICS or direction not in _DIRECTIONS:
        raise DistanceStateContractError("distance metric/direction is invalid")
    _integer(value["startValue"], "distanceContract.startValue", 0, 100_000_000)
    _integer(value["endValue"], "distanceContract.endValue", 0, 100_000_000)
    if _integer(value["tolerance"], "distanceContract.tolerance", 0, 0) != 0:
        raise DistanceStateContractError("distance tolerance must be zero")
    first, last = motion[0], motion[-1]
    if metric == "RELATIVE_SCALE_PERMILLE":
        if value["referenceX"] is not None or value["referenceY"] is not None:
            raise DistanceStateContractError("scale distance forbids a reference point")
        derived = []
        for item in (first, last):
            if item["scaleXNumerator"] != item["scaleYNumerator"] or item["scaleXDenominator"] != item["scaleYDenominator"]:
                raise DistanceStateContractError("relative scale requires uniform scale")
            scaled = item["scaleXNumerator"] * 1000
            if scaled % item["scaleXDenominator"]:
                raise DistanceStateContractError("relative scale is not an exact permille")
            derived.append(scaled // item["scaleXDenominator"])
    else:
        reference_x = _integer(value["referenceX"], "distanceContract.referenceX", -100_000_000, 100_000_000)
        reference_y = _integer(value["referenceY"], "distanceContract.referenceY", -100_000_000, 100_000_000)
        rx = _pixel_coordinate(reference_x, width, coordinate_space, "referenceX")
        ry = _pixel_coordinate(reference_y, height, coordinate_space, "referenceY")
        derived = []
        for item in (first, last):
            x = _pixel_coordinate(item["x"], width, coordinate_space, "motion.x")
            y = _pixel_coordinate(item["y"], height, coordinate_space, "motion.y")
            squared = (x - rx) ** 2 + (y - ry) ** 2
            distance = isqrt(squared)
            if distance * distance != squared:
                raise DistanceStateContractError("screen Euclidean distance is not an exact integer")
            derived.append(distance)
    start_value, end_value = derived
    if value["startValue"] != start_value or value["endValue"] != end_value:
        raise DistanceStateContractError("distance declaration does not match motion")
    if direction == "APPROACH" and not (end_value < start_value if metric == "SCREEN_EUCLIDEAN_PIXELS" else end_value > start_value):
        raise DistanceStateContractError("APPROACH direction is false")
    if direction == "RECEDE" and not (end_value > start_value if metric == "SCREEN_EUCLIDEAN_PIXELS" else end_value < start_value):
        raise DistanceStateContractError("RECEDE direction is false")
    if direction == "LATERAL" and (metric != "SCREEN_EUCLIDEAN_PIXELS" or start_value != end_value or (first["x"], first["y"]) == (last["x"], last["y"])):
        raise DistanceStateContractError("LATERAL direction is false")
    return {
        "metric": metric,
        "startValue": start_value,
        "endValue": end_value,
        "tolerance": 0,
        "direction": direction,
        "referenceX": value["referenceX"],
        "referenceY": value["referenceY"],
    }


def _visual_contract(
    definitions_value: Any,
    schedule_value: Any,
    *,
    start_state_ref: Any,
    end_state_ref: Any,
    start: int,
    end: int,
    layer: int,
    blend_mode: str,
    resolved_variants: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, str]:
    if not isinstance(definitions_value, list) or not 1 <= len(definitions_value) <= 64:
        raise DistanceStateContractError("visualStateDefinitions is invalid")
    definitions: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    used_variants: set[str] = set()
    for index, raw in enumerate(definitions_value):
        item = _closed(raw, _STATE_FIELDS, f"visualStateDefinitions[{index}]")
        state_ref = _ref(item["stateRef"], f"visualStateDefinitions[{index}].stateRef")
        if state_ref in by_ref or item["visibility"] not in _VISIBILITY:
            raise DistanceStateContractError("visual state identity/visibility is invalid")
        opacity = _integer(item["opacityPermille"], "opacityPermille", 0, 1000)
        if item["visibility"] == "HIDDEN" and opacity != 0:
            raise DistanceStateContractError("HIDDEN state must have zero opacity")
        if item["layer"] != layer or item["blendMode"] != blend_mode:
            raise DistanceStateContractError("visual state layer/blend authority differs")
        variant_ref, variant_digest = _nullable_pair(
            item["variantAssetVersionRef"],
            item["variantAssetVersionDigest"],
            f"visualStateDefinitions[{index}].variantAssetVersion",
        )
        if variant_ref is not None:
            authority = resolved_variants.get(variant_ref)
            if authority is None or authority.get("assetVersionDigest") != variant_digest:
                raise DistanceStateStaleInputError("visual state variant is stale")
            used_variants.add(variant_ref)
        item["stateRef"] = state_ref
        by_ref[state_ref] = item
        definitions.append(item)
    if used_variants != set(resolved_variants):
        raise DistanceStateContractError("resolved variant set is not exact")
    first_ref = _ref(start_state_ref, "startStateRef")
    last_ref = _ref(end_state_ref, "endStateRef")
    if first_ref not in by_ref or last_ref not in by_ref:
        raise DistanceStateContractError("start/end visual state is undefined")
    if not isinstance(schedule_value, list) or not 1 <= len(schedule_value) <= 64:
        raise DistanceStateContractError("visualStateSchedule is invalid")
    schedule: list[dict[str, Any]] = []
    cursor = start
    for index, raw in enumerate(schedule_value):
        item = _closed(raw, _SCHEDULE_FIELDS, f"visualStateSchedule[{index}]")
        state_ref = _ref(item["stateRef"], f"visualStateSchedule[{index}].stateRef")
        interval_start = _integer(item["startFrameInclusive"], "startFrameInclusive", start, end - 1)
        interval_end = _integer(item["endFrameExclusive"], "endFrameExclusive", start + 1, end)
        interpolation = item["transitionInterpolation"]
        if (
            state_ref not in by_ref
            or interval_start != cursor
            or interval_end <= interval_start
            or interpolation not in _INTERPOLATIONS
        ):
            raise DistanceStateContractError("visual state schedule has a gap, overlap, or invalid item")
        if by_ref[state_ref]["variantAssetVersionRef"] is not None and interpolation != "STEP":
            raise DistanceStateContractError("variant switching requires STEP")
        cursor = interval_end
        schedule.append(item)
    if cursor != end or schedule[0]["stateRef"] != first_ref or schedule[-1]["stateRef"] != last_ref:
        raise DistanceStateContractError("visual state schedule does not close the frame range")
    for left, right in zip(schedule, schedule[1:]):
        left_variant = by_ref[left["stateRef"]]["variantAssetVersionRef"]
        right_variant = by_ref[right["stateRef"]]["variantAssetVersionRef"]
        if left_variant != right_variant and left["transitionInterpolation"] != "STEP":
            raise DistanceStateContractError("variant transition requires STEP")
    return definitions, schedule, first_ref, last_ref


@dataclass(frozen=True, slots=True)
class _Contract:
    _value: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self._value))

    @property
    def payload_digest(self) -> str:
        return str(self._value["payloadDigest"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])

    @property
    def requirement_ref(self) -> str:
        return str(self._value["requirementRef"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


class DistanceStateTransitionRequirement(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "DistanceStateTransitionRequirement":
        result = _sealed(value, _REQUIREMENT_FIELDS, "Distance/State Requirement")
        if result["schemaVersion"] != DISTANCE_STATE_TRANSITION_REQUIREMENT_SCHEMA_VERSION:
            raise DistanceStateContractError("Requirement schema is invalid")
        _ref(result["workspaceRef"], "workspaceRef")
        _ref(result["productionRunRef"], "productionRunRef")
        _ref(result["requirementRef"], "requirementRef")
        if result["effectMode"] != DISTANCE_STATE_TRANSITION:
            raise DistanceStateContractError("effectMode is invalid")
        for field in (
            "targetShotRef", "targetShotVersionRef", "basePlateAssetVersionRef"
        ):
            _ref(result[field], field)
        for field in (
            "targetShotVersionDigest", "basePlateAssetVersionDigest"
        ):
            _raw(result[field], field)
        for field in ("basePlateFileDigest", "basePlatePixelDigest"):
            _content(result[field], field)
        width = _integer(result["canvasWidth"], "canvasWidth", 2, 16384)
        height = _integer(result["canvasHeight"], "canvasHeight", 2, 16384)
        _integer(result["frameCount"], "frameCount", 1, 10_000_000)
        _integer(result["frameRate"], "frameRate", 1, 240)
        start = _integer(result["frameRangeStartInclusive"], "frameRangeStartInclusive", 0, result["frameCount"] - 1)
        end = _integer(result["frameRangeEndExclusive"], "frameRangeEndExclusive", 1, result["frameCount"])
        if end <= start or result["targetKind"] not in _TARGET_KINDS or result["transitionMode"] not in _TRANSITION_MODES or result["coordinateSpace"] not in _COORDINATE_SPACES:
            raise DistanceStateContractError("Requirement range or closed mode is invalid")
        layer = _integer(result["layer"], "layer", 0, 1024)
        if result["blendMode"] not in _BLEND_MODES:
            raise DistanceStateContractError("blendMode is invalid")
        subject_ref, subject_digest = _nullable_pair(
            result["subjectLayerAssetVersionRef"], result["subjectLayerAssetVersionDigest"], "subjectLayerAssetVersion"
        )
        mask_ref, mask_digest = _nullable_pair(
            result["maskAssetVersionRef"], result["maskAssetVersionDigest"], "maskAssetVersion"
        )
        if result["targetKind"] == "FULL_FRAME":
            if any(
                result[field] is not None
                for field in (
                    "subjectLayerAssetVersionRef", "subjectLayerAssetVersionDigest",
                    "subjectLayerFileDigest", "subjectLayerPixelDigest",
                    "maskAssetVersionRef", "maskAssetVersionDigest",
                    "maskFileDigest", "maskPixelDigest",
                )
            ):
                raise DistanceStateContractError("FULL_FRAME forbids overlay assets")
            if any(item.get("variantAssetVersionRef") is not None for item in result["visualStateDefinitions"] if isinstance(item, Mapping)):
                raise DistanceStateContractError("FULL_FRAME v1 forbids variant assets")
        else:
            if subject_ref is None or mask_ref is None:
                raise DistanceStateContractError("OVERLAY_LAYER requires subject and explicit mask")
            for field in (
                "subjectLayerFileDigest", "subjectLayerPixelDigest",
                "maskFileDigest", "maskPixelDigest",
            ):
                _content(result[field], field)
        motion = _motion(result["motionKeyframes"], start=start, end=end, coordinate_space=result["coordinateSpace"], width=width, height=height)
        if result["transitionMode"] == "VISUAL_STATE":
            if result["distanceContract"] is not None or any(
                any(item[field] != motion[0][field] for field in (
                    "x", "y", "scaleXNumerator", "scaleXDenominator",
                    "scaleYNumerator", "scaleYDenominator", "rotationMilliDegrees",
                    "perspectiveQuad",
                ))
                for item in motion[1:]
            ):
                raise DistanceStateContractError("VISUAL_STATE requires a constant motion contract")
        else:
            result["distanceContract"] = _derived_distance(
                motion, result["distanceContract"], coordinate_space=result["coordinateSpace"], width=width, height=height
            )
        if result["transitionMode"] == "SCREEN_DISTANCE":
            if result["startStateRef"] is not None or result["endStateRef"] is not None or result["visualStateDefinitions"] != [] or result["visualStateSchedule"] != []:
                raise DistanceStateContractError("SCREEN_DISTANCE forbids visual state authority")
        else:
            variants = {
                item["variantAssetVersionRef"]: {
                    "assetVersionDigest": item["variantAssetVersionDigest"]
                }
                for item in result["visualStateDefinitions"]
                if isinstance(item, Mapping) and item.get("variantAssetVersionRef") is not None
            }
            result["visualStateDefinitions"], result["visualStateSchedule"], result["startStateRef"], result["endStateRef"] = _visual_contract(
                result["visualStateDefinitions"], result["visualStateSchedule"], start_state_ref=result["startStateRef"], end_state_ref=result["endStateRef"], start=start, end=end, layer=layer, blend_mode=result["blendMode"], resolved_variants=variants
            )
        result["motionKeyframes"] = motion
        if result["publicationAllowed"] is not False:
            raise DistanceStateContractError("publicationAllowed must be false")
        return cls(result)


def _resolved_image(value: Any, label: str) -> dict[str, Any]:
    fields = {
        "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
        "pixelDigest", "pixelDigestSpec", "pixelMode", "width", "height",
    }
    if not isinstance(value, Mapping) or not fields.issubset(value):
        raise DistanceStateStaleInputError(f"{label} resolution is incomplete")
    result = {field: deepcopy(value[field]) for field in fields}
    _ref(result["assetVersionRef"], f"{label}.assetVersionRef")
    _raw(result["assetVersionDigest"], f"{label}.assetVersionDigest")
    _content(result["fileDigest"], f"{label}.fileDigest")
    _content(result["pixelDigest"], f"{label}.pixelDigest")
    if result["pixelMode"] != "RGBA":
        raise DistanceStateStaleInputError(f"{label} must be RGBA")
    _integer(result["width"], f"{label}.width", 1, 16384)
    _integer(result["height"], f"{label}.height", 1, 16384)
    return result


def build_distance_state_requirement(
    public_fields: Mapping[str, Any],
    *,
    resolved_base: Mapping[str, Any],
    resolved_subject: Mapping[str, Any] | None,
    resolved_mask: Mapping[str, Any] | None,
    resolved_variants: Sequence[Mapping[str, Any]],
) -> DistanceStateTransitionRequirement:
    public = _closed(public_fields, _PUBLIC_FIELDS, "Distance/State public Requirement")
    if not isinstance(resolved_base, Mapping):
        raise DistanceStateStaleInputError("base resolution is missing")
    for field in (
        "assetVersionRef", "assetVersionDigest", "fileDigest", "pixelDigest",
        "width", "height", "frameCount", "frameRate",
    ):
        if field not in resolved_base:
            raise DistanceStateStaleInputError("base resolution is incomplete")
    if public["basePlateAssetVersionRef"] != resolved_base["assetVersionRef"] or public["basePlateAssetVersionDigest"] != resolved_base["assetVersionDigest"]:
        raise DistanceStateStaleInputError("base AssetVersion is stale")
    subject = _resolved_image(resolved_subject, "subject") if resolved_subject is not None else None
    mask = _resolved_image(resolved_mask, "mask") if resolved_mask is not None else None
    variants_list = [_resolved_image(item, f"variant[{index}]") for index, item in enumerate(resolved_variants)]
    variants = {item["assetVersionRef"]: item for item in variants_list}
    if len(variants) != len(variants_list):
        raise DistanceStateContractError("resolved variants are ambiguous")
    if public["targetKind"] == "OVERLAY_LAYER":
        if subject is None or mask is None:
            raise DistanceStateContractError("OVERLAY_LAYER requires subject and explicit mask")
        if public["subjectLayerAssetVersionRef"] != subject["assetVersionRef"] or public["subjectLayerAssetVersionDigest"] != subject["assetVersionDigest"] or public["maskAssetVersionRef"] != mask["assetVersionRef"] or public["maskAssetVersionDigest"] != mask["assetVersionDigest"]:
            raise DistanceStateStaleInputError("overlay AssetVersion binding is stale")
        if (subject["width"], subject["height"]) != (mask["width"], mask["height"]) or any((item["width"], item["height"]) != (subject["width"], subject["height"]) for item in variants.values()):
            raise DistanceStateStaleInputError("overlay image dimensions are incompatible")
    elif subject is not None or mask is not None or variants:
        raise DistanceStateContractError("FULL_FRAME v1 forbids overlay assets")
    # Validate variants against the exact public definitions before sealing.
    declared_variants: dict[str, str] = {}
    definitions = public.get("visualStateDefinitions")
    if isinstance(definitions, list):
        for item in definitions:
            if isinstance(item, Mapping) and item.get("variantAssetVersionRef") is not None:
                declared_variants[str(item["variantAssetVersionRef"])] = str(item.get("variantAssetVersionDigest"))
    if set(declared_variants) != set(variants) or any(variants[ref]["assetVersionDigest"] != digest for ref, digest in declared_variants.items()):
        raise DistanceStateStaleInputError("variant AssetVersion set is stale")
    sealed = _seal(
        {
            "schemaVersion": DISTANCE_STATE_TRANSITION_REQUIREMENT_SCHEMA_VERSION,
            **public,
            "basePlateFileDigest": resolved_base["fileDigest"],
            "basePlatePixelDigest": resolved_base["pixelDigest"],
            "subjectLayerFileDigest": None if subject is None else subject["fileDigest"],
            "subjectLayerPixelDigest": None if subject is None else subject["pixelDigest"],
            "maskFileDigest": None if mask is None else mask["fileDigest"],
            "maskPixelDigest": None if mask is None else mask["pixelDigest"],
            "canvasWidth": resolved_base["width"],
            "canvasHeight": resolved_base["height"],
            "frameCount": resolved_base["frameCount"],
            "frameRate": resolved_base["frameRate"],
            "publicationAllowed": False,
        }
    )
    # Pass real variant resolution into the semantic validator rather than
    # trusting its digest-only parser, then return the sealed canonical value.
    parsed = DistanceStateTransitionRequirement.from_mapping(sealed)
    if parsed.as_dict()["targetKind"] == "OVERLAY_LAYER":
        _visual_contract(
            parsed.as_dict()["visualStateDefinitions"],
            parsed.as_dict()["visualStateSchedule"],
            start_state_ref=parsed.as_dict()["startStateRef"],
            end_state_ref=parsed.as_dict()["endStateRef"],
            start=parsed.as_dict()["frameRangeStartInclusive"],
            end=parsed.as_dict()["frameRangeEndExclusive"],
            layer=parsed.as_dict()["layer"],
            blend_mode=parsed.as_dict()["blendMode"],
            resolved_variants=variants,
        ) if parsed.as_dict()["transitionMode"] != "SCREEN_DISTANCE" else None
    return parsed


def parse_distance_state_requirement(value: Any) -> DistanceStateTransitionRequirement:
    if type(value) is DistanceStateTransitionRequirement:
        return value
    return DistanceStateTransitionRequirement.from_mapping(value)


_TRANSITION_SPEC_FIELDS = _REQUIREMENT_FIELDS - frozenset(
    {"schemaVersion", "workspaceRef", "productionRunRef", "requirementRef", "effectMode", "publicationAllowed", "payloadDigest"}
)


class DistanceStateExecutionRequest(_Contract):
    @property
    def execution_request_ref(self) -> str:
        return str(self._value["executionRequestRef"])

    @classmethod
    def from_mapping(cls, value: Any) -> "DistanceStateExecutionRequest":
        result = _sealed(value, _REQUEST_FIELDS, "Distance/State execution request")
        if result["schemaVersion"] != DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION or result["effectMode"] != DISTANCE_STATE_TRANSITION or result["publicationAllowed"] is not False:
            raise DistanceStateContractError("execution request boundary is invalid")
        for field in ("executionRequestRef", "workspaceRef", "productionRunRef", "requirementRef"):
            _ref(result[field], field)
        _raw(result["requirementDigest"], "requirementDigest")
        _closed(result["transitionSpec"], _TRANSITION_SPEC_FIELDS, "transitionSpec")
        expected_ref = "m13-distance-state-execution-" + _digest(
            {"requirementRef": result["requirementRef"], "requirementDigest": result["requirementDigest"], "transitionSpec": result["transitionSpec"]}
        )[:32]
        if result["executionRequestRef"] != expected_ref:
            raise DistanceStateStaleInputError("executionRequestRef is stale")
        return cls(result)


def build_distance_state_execution_request(requirement: DistanceStateTransitionRequirement | Mapping[str, Any]) -> DistanceStateExecutionRequest:
    req = parse_distance_state_requirement(requirement)
    value = req.as_dict()
    transition = {field: deepcopy(value[field]) for field in _TRANSITION_SPEC_FIELDS}
    ref = "m13-distance-state-execution-" + _digest(
        {"requirementRef": value["requirementRef"], "requirementDigest": value["payloadDigest"], "transitionSpec": transition}
    )[:32]
    return DistanceStateExecutionRequest.from_mapping(
        _seal(
            {
                "schemaVersion": DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION,
                "executionRequestRef": ref,
                "workspaceRef": value["workspaceRef"],
                "productionRunRef": value["productionRunRef"],
                "requirementRef": value["requirementRef"],
                "requirementDigest": value["payloadDigest"],
                "effectMode": DISTANCE_STATE_TRANSITION,
                "transitionSpec": transition,
                "publicationAllowed": False,
            }
        )
    )


def validate_distance_state_execution_request_binding(
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
) -> DistanceStateExecutionRequest:
    req = parse_distance_state_requirement(requirement)
    request = execution_request if type(execution_request) is DistanceStateExecutionRequest else DistanceStateExecutionRequest.from_mapping(execution_request)
    expected = build_distance_state_execution_request(req)
    if request.as_dict() != expected.as_dict():
        raise DistanceStateStaleInputError("execution request is not the exact Requirement projection")
    return request


def _runtime_text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= 500
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise DistanceStateContractError(f"{field} is invalid")
    return value


def _probe(value: Any) -> dict[str, Any]:
    result = _closed(value, _PROBE_FIELDS, "outputMediaProbe")
    width = _integer(result["width"], "outputMediaProbe.width", 2, 16384)
    height = _integer(result["height"], "outputMediaProbe.height", 2, 16384)
    _integer(result["frameCount"], "outputMediaProbe.frameCount", 1, 10_000_000)
    _integer(result["frameRate"], "outputMediaProbe.frameRate", 1, 240)
    if (
        width % 2
        or height % 2
        or result["pixelFormat"] != "yuv420p"
        or result["container"] != "mp4"
        or result["videoCodec"] != "h264"
    ):
        raise DistanceStateContractError("outputMediaProbe is unsupported")
    return result


def _output_digest(value: Any) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_DIGEST_FIELDS, "outputDigest")
    _content(result["fileDigest"], "outputDigest.fileDigest")
    _content(
        result["decodedFramePixelDigest"],
        "outputDigest.decodedFramePixelDigest",
    )
    _integer(result["width"], "outputDigest.width", 2, 16384)
    _integer(result["height"], "outputDigest.height", 2, 16384)
    _integer(result["frameCount"], "outputDigest.frameCount", 1, 10_000_000)
    _integer(result["frameRate"], "outputDigest.frameRate", 1, 240)
    if (
        result["fileDigestAlgorithm"] != "sha256"
        or result["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC
        or result["pixelMode"] != "RGBA"
    ):
        raise DistanceStateContractError("outputDigest contract is invalid")
    return result


def _evidence_ref(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + _digest(value)[:32]


def distance_state_derived_distance_facts(
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
) -> dict[str, Any] | None:
    value = parse_distance_state_requirement(requirement).as_dict()
    return deepcopy(value["distanceContract"])


def distance_state_schedule_digest(
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
) -> str:
    value = parse_distance_state_requirement(requirement).as_dict()
    return _digest(
        {
            "visualStateDefinitions": value["visualStateDefinitions"],
            "visualStateSchedule": value["visualStateSchedule"],
        }
    )


def _validate_output_requirement(
    requirement: DistanceStateTransitionRequirement,
    probe: Mapping[str, Any],
    output: Mapping[str, Any],
) -> None:
    value = requirement.as_dict()
    expected = {
        "width": value["canvasWidth"],
        "height": value["canvasHeight"],
        "frameCount": value["frameCount"],
        "frameRate": value["frameRate"],
    }
    if any(
        probe[field] != expected_value
        or output[field] != expected_value
        for field, expected_value in expected.items()
    ):
        raise DistanceStateStaleInputError(
            "output media facts do not match the Requirement"
        )


def _lineage(
    requirement: DistanceStateTransitionRequirement,
    execution_request: DistanceStateExecutionRequest,
) -> dict[str, Any]:
    return {
        "workspaceRef": requirement.workspace_ref,
        "productionRunRef": requirement.production_run_ref,
        "requirementRef": requirement.requirement_ref,
        "requirementDigest": requirement.payload_digest,
        "executionRequestRef": execution_request.execution_request_ref,
        "executionRequestDigest": execution_request.payload_digest,
    }


class DistanceStateRuntimeEvidence(_Contract):
    @property
    def runtime_evidence_ref(self) -> str:
        return str(self._value["runtimeEvidenceRef"])

    @classmethod
    def from_mapping(cls, value: Any) -> "DistanceStateRuntimeEvidence":
        result = _sealed(value, _RUNTIME_FIELDS, "Distance/State runtime evidence")
        if (
            result["schemaVersion"] != DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION
            or result["effectMode"] != DISTANCE_STATE_TRANSITION
            or result["rendererIdentity"] != DISTANCE_STATE_RENDERER_IDENTITY
            or result["rendererVersion"] != DISTANCE_STATE_RENDERER_VERSION
            or result["gpuUsed"] is not False
            or result["publicationAllowed"] is not False
        ):
            raise DistanceStateContractError("runtime evidence authority is invalid")
        for field in (
            "runtimeEvidenceRef",
            "workspaceRef",
            "productionRunRef",
            "requirementRef",
            "executionRequestRef",
        ):
            _ref(result[field], field)
        for field in (
            "requirementDigest",
            "executionRequestDigest",
            "v3ExecutionRequestDigest",
        ):
            _raw(result[field], field)
        _runtime_text(result["ffmpegIdentity"], "ffmpegIdentity")
        _content(result["executionManifestDigest"], "executionManifestDigest")
        expected_ref = _evidence_ref(
            "m13-distance-state-runtime-evidence-",
            {
                key: result[key]
                for key in (
                    "v3ExecutionRequestDigest",
                    "rendererIdentity",
                    "rendererVersion",
                    "ffmpegIdentity",
                    "executionManifestDigest",
                )
            },
        )
        if result["runtimeEvidenceRef"] != expected_ref:
            raise DistanceStateStaleInputError("runtimeEvidenceRef is stale")
        return cls(result)


def build_distance_state_runtime_evidence(
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    execution_facts: Mapping[str, Any],
) -> DistanceStateRuntimeEvidence:
    req = parse_distance_state_requirement(requirement)
    request = validate_distance_state_execution_request_binding(
        execution_request, req
    )
    fields = frozenset(
        {
            "v3ExecutionRequestDigest",
            "rendererIdentity",
            "rendererVersion",
            "ffmpegIdentity",
            "executionManifestDigest",
        }
    )
    facts = _closed(execution_facts, fields, "runtime execution facts")
    for field in ("v3ExecutionRequestDigest",):
        _raw(facts[field], field)
    if (
        facts["rendererIdentity"] != DISTANCE_STATE_RENDERER_IDENTITY
        or facts["rendererVersion"] != DISTANCE_STATE_RENDERER_VERSION
    ):
        raise DistanceStateStaleInputError("runtime renderer identity is stale")
    _runtime_text(facts["ffmpegIdentity"], "ffmpegIdentity")
    _content(facts["executionManifestDigest"], "executionManifestDigest")
    runtime_ref = _evidence_ref(
        "m13-distance-state-runtime-evidence-", facts
    )
    return DistanceStateRuntimeEvidence.from_mapping(
        _seal(
            {
                "schemaVersion": DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
                "runtimeEvidenceRef": runtime_ref,
                **_lineage(req, request),
                "v3ExecutionRequestDigest": facts["v3ExecutionRequestDigest"],
                "effectMode": DISTANCE_STATE_TRANSITION,
                "rendererIdentity": facts["rendererIdentity"],
                "rendererVersion": facts["rendererVersion"],
                "ffmpegIdentity": facts["ffmpegIdentity"],
                "executionManifestDigest": facts["executionManifestDigest"],
                "gpuUsed": False,
                "publicationAllowed": False,
            }
        )
    )


class DistanceStateArtifactEvidence(_Contract):
    @property
    def artifact_evidence_ref(self) -> str:
        return str(self._value["artifactEvidenceRef"])

    @classmethod
    def from_mapping(cls, value: Any) -> "DistanceStateArtifactEvidence":
        result = _sealed(value, _ARTIFACT_FIELDS, "Distance/State artifact evidence")
        if (
            result["schemaVersion"] != DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION
            or result["effectMode"] != DISTANCE_STATE_TRANSITION
            or result["provenance"] != DISTANCE_STATE_PROVENANCE
            or result["publicationAllowed"] is not False
        ):
            raise DistanceStateContractError("artifact evidence authority is invalid")
        for field in (
            "artifactEvidenceRef",
            "workspaceRef",
            "productionRunRef",
            "requirementRef",
            "executionRequestRef",
            "runtimeEvidenceRef",
        ):
            _ref(result[field], field)
        for field in (
            "requirementDigest",
            "executionRequestDigest",
            "v3ExecutionRequestDigest",
            "runtimeEvidenceDigest",
            "appliedStateScheduleDigest",
        ):
            _raw(result[field], field)
        _integer(result["outputByteSize"], "outputByteSize", 1, 10**12)
        result["outputMediaProbe"] = _probe(result["outputMediaProbe"])
        result["outputDigest"] = _output_digest(result["outputDigest"])
        if any(
            result["outputDigest"][field] != result["outputMediaProbe"][field]
            for field in ("width", "height", "frameCount", "frameRate")
        ):
            raise DistanceStateContractError("artifact media facts disagree")
        if result["derivedDistanceFacts"] is not None:
            _closed(
                result["derivedDistanceFacts"],
                _DISTANCE_FIELDS,
                "derivedDistanceFacts",
            )
        expected_ref = _evidence_ref(
            "m13-distance-state-artifact-evidence-",
            {
                "v3ExecutionRequestDigest": result["v3ExecutionRequestDigest"],
                "fileDigest": result["outputDigest"]["fileDigest"],
                "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
            },
        )
        if result["artifactEvidenceRef"] != expected_ref:
            raise DistanceStateStaleInputError("artifactEvidenceRef is stale")
        return cls(result)


def build_distance_state_artifact_evidence(
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    runtime_evidence: DistanceStateRuntimeEvidence | Mapping[str, Any],
    execution_facts: Mapping[str, Any],
) -> DistanceStateArtifactEvidence:
    req = parse_distance_state_requirement(requirement)
    request = validate_distance_state_execution_request_binding(
        execution_request, req
    )
    runtime = (
        runtime_evidence
        if type(runtime_evidence) is DistanceStateRuntimeEvidence
        else DistanceStateRuntimeEvidence.from_mapping(runtime_evidence)
    )
    if any(
        runtime.as_dict()[field] != expected
        for field, expected in {
            **_lineage(req, request),
            "effectMode": DISTANCE_STATE_TRANSITION,
        }.items()
    ):
        raise DistanceStateStaleInputError("runtime evidence lineage is stale")
    facts = _closed(
        execution_facts,
        frozenset(
            {
                "v3ExecutionRequestDigest",
                "outputByteSize",
                "outputMediaProbe",
                "outputDigest",
                "derivedDistanceFacts",
                "appliedStateScheduleDigest",
            }
        ),
        "artifact execution facts",
    )
    _raw(facts["v3ExecutionRequestDigest"], "v3ExecutionRequestDigest")
    if facts["v3ExecutionRequestDigest"] != runtime.as_dict()["v3ExecutionRequestDigest"]:
        raise DistanceStateStaleInputError("V3 execution digest is crossed")
    if facts["derivedDistanceFacts"] != distance_state_derived_distance_facts(req):
        raise DistanceStateStaleInputError("derived distance facts are stale")
    if facts["appliedStateScheduleDigest"] != distance_state_schedule_digest(req):
        raise DistanceStateStaleInputError("visual state schedule digest is stale")
    probe = _probe(facts["outputMediaProbe"])
    output = _output_digest(facts["outputDigest"])
    _validate_output_requirement(req, probe, output)
    runtime_value = runtime.as_dict()
    artifact_ref = _evidence_ref(
        "m13-distance-state-artifact-evidence-",
        {
            "v3ExecutionRequestDigest": facts["v3ExecutionRequestDigest"],
            "fileDigest": output["fileDigest"],
            "runtimeEvidenceDigest": runtime.payload_digest,
        },
    )
    return DistanceStateArtifactEvidence.from_mapping(
        _seal(
            {
                "schemaVersion": DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
                "artifactEvidenceRef": artifact_ref,
                **_lineage(req, request),
                "v3ExecutionRequestDigest": facts["v3ExecutionRequestDigest"],
                "effectMode": DISTANCE_STATE_TRANSITION,
                "outputByteSize": facts["outputByteSize"],
                "outputMediaProbe": probe,
                "outputDigest": output,
                "derivedDistanceFacts": deepcopy(facts["derivedDistanceFacts"]),
                "appliedStateScheduleDigest": facts["appliedStateScheduleDigest"],
                "runtimeEvidenceRef": runtime.runtime_evidence_ref,
                "runtimeEvidenceDigest": runtime.payload_digest,
                "provenance": DISTANCE_STATE_PROVENANCE,
                "publicationAllowed": False,
            }
        )
    )


def validate_distance_state_execution_evidence(
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    artifact_evidence: DistanceStateArtifactEvidence | Mapping[str, Any],
    runtime_evidence: DistanceStateRuntimeEvidence | Mapping[str, Any],
) -> tuple[DistanceStateArtifactEvidence, DistanceStateRuntimeEvidence]:
    req = parse_distance_state_requirement(requirement)
    request = validate_distance_state_execution_request_binding(
        execution_request, req
    )
    artifact = (
        artifact_evidence
        if type(artifact_evidence) is DistanceStateArtifactEvidence
        else DistanceStateArtifactEvidence.from_mapping(artifact_evidence)
    )
    runtime = (
        runtime_evidence
        if type(runtime_evidence) is DistanceStateRuntimeEvidence
        else DistanceStateRuntimeEvidence.from_mapping(runtime_evidence)
    )
    expected = {
        **_lineage(req, request),
        "effectMode": DISTANCE_STATE_TRANSITION,
    }
    artifact_value = artifact.as_dict()
    runtime_value = runtime.as_dict()
    if any(
        artifact_value[field] != value or runtime_value[field] != value
        for field, value in expected.items()
    ):
        raise DistanceStateStaleInputError("execution evidence lineage is stale")
    if (
        artifact_value["v3ExecutionRequestDigest"]
        != runtime_value["v3ExecutionRequestDigest"]
        or artifact_value["runtimeEvidenceRef"] != runtime.runtime_evidence_ref
        or artifact_value["runtimeEvidenceDigest"] != runtime.payload_digest
        or artifact_value["derivedDistanceFacts"]
        != distance_state_derived_distance_facts(req)
        or artifact_value["appliedStateScheduleDigest"]
        != distance_state_schedule_digest(req)
    ):
        raise DistanceStateStaleInputError("artifact/runtime binding is stale")
    _validate_output_requirement(
        req,
        artifact_value["outputMediaProbe"],
        artifact_value["outputDigest"],
    )
    return artifact, runtime


@dataclass(frozen=True, slots=True)
class DistanceStateTransitionResult(_Contract):
    @property
    def result_ref(self) -> str:
        return str(self._value["resultRef"])

    @classmethod
    def from_mapping(cls, value: Any) -> "DistanceStateTransitionResult":
        result = _sealed(value, _RESULT_FIELDS, "Distance/State Result")
        if (
            result["schemaVersion"]
            != DISTANCE_STATE_TRANSITION_RESULT_SCHEMA_VERSION
            or result["effectMode"] != DISTANCE_STATE_TRANSITION
            or result["state"] != "COMPOSED_CANDIDATE"
            or result["assetAdmissionState"] != "NOT_ADMITTED"
            or result["masterState"] != "NOT_CREATED"
            or result["exportState"] != "NOT_CREATED"
            or result["publicationAllowed"] is not False
        ):
            raise DistanceStateContractError("Result state is invalid")
        for field in (
            "workspaceRef",
            "productionRunRef",
            "resultRef",
            "requirementRef",
            "executionRequestRef",
            "artifactEvidenceRef",
            "runtimeEvidenceRef",
        ):
            _ref(result[field], field)
        for field in (
            "requirementDigest",
            "executionRequestDigest",
            "artifactEvidenceDigest",
            "runtimeEvidenceDigest",
            "appliedStateScheduleDigest",
        ):
            _raw(result[field], field)
        _content(result["outputFileDigest"], "outputFileDigest")
        _content(
            result["outputDecodedFramePixelDigest"],
            "outputDecodedFramePixelDigest",
        )
        result["outputMediaProbe"] = _probe(result["outputMediaProbe"])
        if result["derivedDistanceFacts"] is not None:
            result["derivedDistanceFacts"] = _closed(
                result["derivedDistanceFacts"],
                _DISTANCE_FIELDS,
                "derivedDistanceFacts",
            )
        expected_ref = "m13-distance-state-result-" + _digest(
            {
                key: result[key]
                for key in (
                    "effectMode",
                    "requirementDigest",
                    "executionRequestDigest",
                    "artifactEvidenceDigest",
                    "runtimeEvidenceDigest",
                    "outputFileDigest",
                    "outputDecodedFramePixelDigest",
                )
            }
        )[:32]
        if result["resultRef"] != expected_ref:
            raise DistanceStateStaleInputError("resultRef is stale")
        return cls(result)


def parse_distance_state_result(value: Any) -> DistanceStateTransitionResult:
    if type(value) is DistanceStateTransitionResult:
        return value
    return DistanceStateTransitionResult.from_mapping(value)


def build_distance_state_result(
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    evidence_bindings: Mapping[str, Any],
    artifact_evidence: DistanceStateArtifactEvidence | Mapping[str, Any],
) -> DistanceStateTransitionResult:
    req = parse_distance_state_requirement(requirement)
    request = validate_distance_state_execution_request_binding(
        execution_request, req
    )
    artifact = (
        artifact_evidence
        if type(artifact_evidence) is DistanceStateArtifactEvidence
        else DistanceStateArtifactEvidence.from_mapping(artifact_evidence)
    )
    bindings = _closed(
        evidence_bindings, _BINDING_FIELDS, "evidenceBindings"
    )
    artifact_value = artifact.as_dict()
    expected = {
        **_lineage(req, request),
        "artifactEvidenceRef": artifact.artifact_evidence_ref,
        "artifactEvidenceDigest": artifact.payload_digest,
        "runtimeEvidenceRef": artifact_value["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": artifact_value["runtimeEvidenceDigest"],
    }
    if bindings != expected:
        raise DistanceStateStaleInputError("evidence bindings are stale")
    if any(
        artifact_value[field] != expected[field]
        for field in (
            "workspaceRef",
            "productionRunRef",
            "requirementRef",
            "requirementDigest",
            "executionRequestRef",
            "executionRequestDigest",
        )
    ):
        raise DistanceStateStaleInputError("artifact lineage is stale")
    if (
        artifact_value["derivedDistanceFacts"]
        != distance_state_derived_distance_facts(req)
        or artifact_value["appliedStateScheduleDigest"]
        != distance_state_schedule_digest(req)
    ):
        raise DistanceStateStaleInputError("artifact projection is stale")
    output = artifact_value["outputDigest"]
    base = {
        "schemaVersion": DISTANCE_STATE_TRANSITION_RESULT_SCHEMA_VERSION,
        "workspaceRef": req.workspace_ref,
        "productionRunRef": req.production_run_ref,
        "effectMode": DISTANCE_STATE_TRANSITION,
        "requirementRef": req.requirement_ref,
        "requirementDigest": req.payload_digest,
        "executionRequestRef": request.execution_request_ref,
        "executionRequestDigest": request.payload_digest,
        "artifactEvidenceRef": artifact.artifact_evidence_ref,
        "artifactEvidenceDigest": artifact.payload_digest,
        "runtimeEvidenceRef": artifact_value["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": artifact_value["runtimeEvidenceDigest"],
        "outputFileDigest": output["fileDigest"],
        "outputDecodedFramePixelDigest": output[
            "decodedFramePixelDigest"
        ],
        "outputMediaProbe": artifact_value["outputMediaProbe"],
        "derivedDistanceFacts": artifact_value["derivedDistanceFacts"],
        "appliedStateScheduleDigest": artifact_value[
            "appliedStateScheduleDigest"
        ],
        "state": "COMPOSED_CANDIDATE",
        "assetAdmissionState": "NOT_ADMITTED",
        "masterState": "NOT_CREATED",
        "exportState": "NOT_CREATED",
        "publicationAllowed": False,
    }
    base["resultRef"] = "m13-distance-state-result-" + _digest(
        {
            key: base[key]
            for key in (
                "effectMode",
                "requirementDigest",
                "executionRequestDigest",
                "artifactEvidenceDigest",
                "runtimeEvidenceDigest",
                "outputFileDigest",
                "outputDecodedFramePixelDigest",
            )
        }
    )[:32]
    return DistanceStateTransitionResult.from_mapping(_seal(base))


@dataclass(frozen=True, slots=True)
class ResolvedDistanceStateResultChain:
    requirement: DistanceStateTransitionRequirement
    execution_request: DistanceStateExecutionRequest
    artifact_evidence: DistanceStateArtifactEvidence
    runtime_evidence: DistanceStateRuntimeEvidence
    result: DistanceStateTransitionResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement.as_dict(),
            "executionRequest": self.execution_request.as_dict(),
            "artifactEvidence": self.artifact_evidence.as_dict(),
            "runtimeEvidence": self.runtime_evidence.as_dict(),
            "result": self.result.as_dict(),
        }


def _validated_chain(
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    artifact_evidence: DistanceStateArtifactEvidence | Mapping[str, Any],
    runtime_evidence: DistanceStateRuntimeEvidence | Mapping[str, Any],
    result: DistanceStateTransitionResult | Mapping[str, Any],
) -> ResolvedDistanceStateResultChain:
    req = parse_distance_state_requirement(requirement)
    request = validate_distance_state_execution_request_binding(
        execution_request, req
    )
    artifact, runtime = validate_distance_state_execution_evidence(
        requirement=req,
        execution_request=request,
        artifact_evidence=artifact_evidence,
        runtime_evidence=runtime_evidence,
    )
    parsed_result = parse_distance_state_result(result)
    bindings = {
        **_lineage(req, request),
        "artifactEvidenceRef": artifact.artifact_evidence_ref,
        "artifactEvidenceDigest": artifact.payload_digest,
        "runtimeEvidenceRef": runtime.runtime_evidence_ref,
        "runtimeEvidenceDigest": runtime.payload_digest,
    }
    expected = build_distance_state_result(
        requirement=req,
        execution_request=request,
        evidence_bindings=bindings,
        artifact_evidence=artifact,
    )
    if parsed_result.as_dict() != expected.as_dict():
        raise DistanceStateStaleInputError(
            "Result is not the exact Distance/State execution projection"
        )
    return ResolvedDistanceStateResultChain(
        req, request, artifact, runtime, parsed_result
    )


def _record_key(client_key: str, slot: str) -> str:
    return _digest(
        {
            "schemaVersion": "v5.m13-distance-state-record-idempotency.v1",
            "clientIdempotencyKey": _idempotency_key(client_key),
            "slot": slot,
        }
    )


def _chain_records(
    chain: ResolvedDistanceStateResultChain,
    *,
    idempotency_key: str,
    created_at: str,
) -> tuple[EvidenceRecord, ...]:
    values = (
        (
            DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND,
            chain.requirement.requirement_ref,
            chain.requirement.as_dict(),
        ),
        (
            DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND,
            chain.execution_request.execution_request_ref,
            chain.execution_request.as_dict(),
        ),
        (
            DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND,
            chain.artifact_evidence.artifact_evidence_ref,
            chain.artifact_evidence.as_dict(),
        ),
        (
            DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND,
            chain.runtime_evidence.runtime_evidence_ref,
            chain.runtime_evidence.as_dict(),
        ),
        (
            DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
            chain.result.result_ref,
            chain.result.as_dict(),
        ),
    )
    chain_digest = _digest(
        {
            "schemaVersion": "v5.m13-distance-state-result-chain.v1",
            "workspaceRef": chain.requirement.workspace_ref,
            "productionRunRef": chain.requirement.production_run_ref,
            "members": [
                {
                    "recordKind": kind,
                    "recordRef": reference,
                    "payloadDigest": payload["payloadDigest"],
                }
                for kind, reference, payload in values
            ],
        }
    )
    timestamp = _timestamp(created_at)
    return tuple(
        EvidenceRecord(
            workspaceRef=chain.requirement.workspace_ref,
            productionRunRef=chain.requirement.production_run_ref,
            recordKind=kind,
            recordRef=reference,
            recordVersion=1,
            idempotencyKey=_record_key(
                idempotency_key, f"{index}:{kind}"
            ),
            requestDigest=_digest(
                {
                    "schemaVersion": "v5.m13-distance-state-record-append.v1",
                    "chainDigest": chain_digest,
                    "recordKind": kind,
                    "recordRef": reference,
                    "payloadDigest": payload["payloadDigest"],
                }
            ),
            createdAt=timestamp,
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        for index, (kind, reference, payload) in enumerate(values)
    )


def _record_payload(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    record_ref: str,
    expected_kind: str,
    expected_digest: str,
) -> dict[str, Any]:
    workspace = _ref(workspace_ref, "workspaceRef")
    run_ref = _ref(production_run_ref, "productionRunRef")
    reference = _ref(record_ref, "recordRef")
    digest = _raw(expected_digest, "record payloadDigest")
    stored = repository.get_record(workspace, run_ref, reference, 1)
    if stored is None:
        raise DistanceStateJournalError(
            "Distance/State evidence record is missing"
        )
    try:
        record = _closed(
            stored,
            frozenset(
                {
                    "workspaceRef",
                    "productionRunRef",
                    "recordKind",
                    "recordRef",
                    "recordVersion",
                    "idempotencyKey",
                    "requestDigest",
                    "createdAt",
                    "payload",
                    "payloadDigest",
                }
            ),
            "Distance/State evidence record",
        )
        if (
            record["workspaceRef"] != workspace
            or record["productionRunRef"] != run_ref
            or record["recordKind"] != expected_kind
            or record["recordRef"] != reference
            or record["recordVersion"] != 1
            or record["payloadDigest"] != digest
        ):
            raise DistanceStateJournalError(
                "Distance/State evidence record identity is stale"
            )
        _idempotency_key(record["idempotencyKey"])
        _raw(record["requestDigest"], "record requestDigest")
        _timestamp(record["createdAt"])
        if not isinstance(record["payload"], Mapping):
            raise DistanceStateJournalError(
                "Distance/State evidence payload is invalid"
            )
        payload = deepcopy(dict(record["payload"]))
        if payload.get("payloadDigest") != digest:
            raise DistanceStateJournalError(
                "Distance/State evidence payload digest is stale"
            )
        return payload
    except DistanceStateJournalError:
        raise
    except EpisodeProductionError as exc:
        raise DistanceStateJournalError(
            "Distance/State evidence record is invalid"
        ) from exc


def resolve_distance_state_result_chain(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    result_ref: str,
    result_digest: str,
) -> ResolvedDistanceStateResultChain:
    result_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_ref,
        expected_kind=DISTANCE_STATE_TRANSITION_RESULT_RECORD_KIND,
        expected_digest=result_digest,
    )
    try:
        result = parse_distance_state_result(result_payload)
        value = result.as_dict()
        if value["resultRef"] != result_ref:
            raise DistanceStateJournalError("Result record ref is stale")
        requirement_payload = _record_payload(
            repository,
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            record_ref=value["requirementRef"],
            expected_kind=DISTANCE_STATE_TRANSITION_REQUIREMENT_RECORD_KIND,
            expected_digest=value["requirementDigest"],
        )
        request_payload = _record_payload(
            repository,
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            record_ref=value["executionRequestRef"],
            expected_kind=DISTANCE_STATE_EXECUTION_REQUEST_RECORD_KIND,
            expected_digest=value["executionRequestDigest"],
        )
        artifact_payload = _record_payload(
            repository,
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            record_ref=value["artifactEvidenceRef"],
            expected_kind=DISTANCE_STATE_ARTIFACT_EVIDENCE_RECORD_KIND,
            expected_digest=value["artifactEvidenceDigest"],
        )
        runtime_payload = _record_payload(
            repository,
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            record_ref=value["runtimeEvidenceRef"],
            expected_kind=DISTANCE_STATE_RUNTIME_EVIDENCE_RECORD_KIND,
            expected_digest=value["runtimeEvidenceDigest"],
        )
        return _validated_chain(
            requirement=requirement_payload,
            execution_request=request_payload,
            artifact_evidence=artifact_payload,
            runtime_evidence=runtime_payload,
            result=result,
        )
    except DistanceStateJournalError:
        raise
    except EpisodeProductionError as exc:
        raise DistanceStateJournalError(
            "Distance/State evidence chain is invalid"
        ) from exc


def resolve_distance_state_result(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    result_ref: str,
    result_digest: str,
) -> DistanceStateTransitionResult:
    return resolve_distance_state_result_chain(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        result_ref=result_ref,
        result_digest=result_digest,
    ).result


def append_distance_state_result_chain(
    repository: EpisodeProductionEvidenceRepository,
    *,
    requirement: DistanceStateTransitionRequirement | Mapping[str, Any],
    execution_request: DistanceStateExecutionRequest | Mapping[str, Any],
    artifact_evidence: DistanceStateArtifactEvidence | Mapping[str, Any],
    runtime_evidence: DistanceStateRuntimeEvidence | Mapping[str, Any],
    result: DistanceStateTransitionResult | Mapping[str, Any],
    idempotency_key: str,
    created_at: str,
    expected_record_journal_head: str | None = None,
) -> tuple[ResolvedDistanceStateResultChain, bool]:
    chain = _validated_chain(
        requirement=requirement,
        execution_request=execution_request,
        artifact_evidence=artifact_evidence,
        runtime_evidence=runtime_evidence,
        result=result,
    )
    records = _chain_records(
        chain,
        idempotency_key=idempotency_key,
        created_at=created_at,
    )
    _, replayed = repository.append_records(
        records,
        expected_record_journal_head=expected_record_journal_head,
    )
    resolved = resolve_distance_state_result_chain(
        repository,
        workspace_ref=chain.requirement.workspace_ref,
        production_run_ref=chain.requirement.production_run_ref,
        result_ref=chain.result.result_ref,
        result_digest=chain.result.payload_digest,
    )
    if resolved.as_dict() != chain.as_dict():
        raise DistanceStateJournalError(
            "stored Distance/State result chain differs from append"
        )
    return resolved, replayed


append_distance_state_result = append_distance_state_result_chain


__all__ = [name for name in globals() if name.isupper()] + [
    "DistanceStateContractError",
    "DistanceStateStaleInputError",
    "DistanceStateJournalError",
    "DistanceStateTransitionRequirement",
    "DistanceStateExecutionRequest",
    "DistanceStateRuntimeEvidence",
    "DistanceStateArtifactEvidence",
    "DistanceStateTransitionResult",
    "ResolvedDistanceStateResultChain",
    "build_distance_state_requirement",
    "parse_distance_state_requirement",
    "build_distance_state_execution_request",
    "validate_distance_state_execution_request_binding",
    "distance_state_derived_distance_facts",
    "distance_state_schedule_digest",
    "build_distance_state_runtime_evidence",
    "build_distance_state_artifact_evidence",
    "validate_distance_state_execution_evidence",
    "build_distance_state_result",
    "parse_distance_state_result",
    "append_distance_state_result_chain",
    "append_distance_state_result",
    "resolve_distance_state_result_chain",
    "resolve_distance_state_result",
]
