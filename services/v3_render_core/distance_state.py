"""Closed deterministic screen-distance and visual-state renderer for M13-E4.

This module owns only CPU execution.  It accepts a V4-sealed projection,
generates the FFmpeg graph in code, and publishes a digest-addressed technical
artifact.  It never accepts a path, filter, argv, world-distance, or state
authority from a public caller.
"""

from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
from fractions import Fraction
from hashlib import sha256
import json
from math import gcd, isqrt
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from .composition import (
    RenderArtifactError,
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
    _fixed_environment,
    _publish_timeline_output_v1,
    _safe_glyph_input,
    _stage_digest_pinned_input,
)
from .digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    IMAGE_PIXEL_DIGEST_SPEC,
    DigestError,
    decoded_frame_pixel_digest_metadata,
    image_digest_metadata,
)
from .masked_surface import _probe_video, _validate_probe


DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION = (
    "v4.m13-distance-state-execution-request.v1"
)
DISTANCE_STATE_RENDERER_IDENTITY = "v3.deterministic-distance-state-ffmpeg"
DISTANCE_STATE_RENDERER_VERSION = "1"

_RAW = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_INTERPOLATIONS = {"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"}
_TARGET_KINDS = {"FULL_FRAME", "OVERLAY_LAYER"}
_TRANSITION_MODES = {
    "SCREEN_DISTANCE",
    "VISUAL_STATE",
    "SCREEN_DISTANCE_AND_VISUAL_STATE",
}
_COORDINATE_SPACES = {"CANVAS_PIXELS", "NORMALIZED_PERMILLE"}
_DISTANCE_METRICS = {"SCREEN_EUCLIDEAN_PIXELS", "RELATIVE_SCALE_PERMILLE"}
_DIRECTIONS = {"APPROACH", "RECEDE", "LATERAL", "CUSTOM_EXACT"}
_BLEND_MODES = {"NORMAL"}

_REQUEST_FIELDS = {
    "schemaVersion",
    "v5ExecutionRequestRef",
    "v5ExecutionRequestDigest",
    "workspaceRef",
    "productionRunRef",
    "requirementRef",
    "requirementDigest",
    "effectMode",
    "targetShot",
    "basePlate",
    "targetKind",
    "subjectLayer",
    "mask",
    "variantAssets",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
    "transitionMode",
    "coordinateSpace",
    "motionKeyframes",
    "distanceContract",
    "startStateRef",
    "endStateRef",
    "visualStateDefinitions",
    "visualStateSchedule",
    "blendMode",
    "layer",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
_SHOT_FIELDS = {"shotRef", "shotVersionRef", "shotVersionDigest"}
_BASE_FIELDS = {
    "assetVersionRef",
    "assetVersionDigest",
    "storageKey",
    "fileDigest",
    "pixelDigest",
    "pixelDigestSpec",
    "width",
    "height",
    "frameCount",
    "frameRate",
    "pixelFormat",
}
_IMAGE_FIELDS = {
    "assetVersionRef",
    "assetVersionDigest",
    "storageKey",
    "fileDigest",
    "pixelDigest",
    "pixelDigestSpec",
    "pixelMode",
    "width",
    "height",
}
_MOTION_FIELDS = {
    "frame",
    "x",
    "y",
    "scaleXNumerator",
    "scaleXDenominator",
    "scaleYNumerator",
    "scaleYDenominator",
    "rotationMilliDegrees",
    "perspectiveQuad",
    "interpolation",
}
_DISTANCE_FIELDS = {
    "metric",
    "startValue",
    "endValue",
    "tolerance",
    "direction",
    "referenceX",
    "referenceY",
}
_STATE_FIELDS = {
    "stateRef",
    "visibility",
    "opacityPermille",
    "variantAssetVersionRef",
    "variantAssetVersionDigest",
    "layer",
    "blendMode",
}
_SCHEDULE_FIELDS = {
    "stateRef",
    "startFrameInclusive",
    "endFrameExclusive",
    "transitionInterpolation",
}
_OUTPUT_FIELDS = {
    "width",
    "height",
    "frameCount",
    "frameRate",
    "pixelFormat",
    "container",
    "videoCodec",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _closed(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderArtifactError(f"{label} is not closed-world")
    result = deepcopy(dict(value))
    _reject_floats(result)
    return result


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise RenderArtifactError("distance/state float authority is forbidden")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def _ref(value: object, label: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _digest(value: object, label: str, *, prefixed: bool = False) -> str:
    pattern = _SHA if prefixed else _RAW
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _integer(
    value: object, label: str, minimum: int, maximum: int
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _validate_base(value: object) -> dict[str, Any]:
    base = _closed(value, _BASE_FIELDS, "basePlate")
    _ref(base["assetVersionRef"], "basePlate.assetVersionRef")
    _digest(base["assetVersionDigest"], "basePlate.assetVersionDigest")
    _digest(base["fileDigest"], "basePlate.fileDigest", prefixed=True)
    _digest(base["pixelDigest"], "basePlate.pixelDigest", prefixed=True)
    width = _integer(base["width"], "basePlate.width", 2, 16384)
    height = _integer(base["height"], "basePlate.height", 2, 16384)
    _integer(base["frameCount"], "basePlate.frameCount", 1, 10_000_000)
    _integer(base["frameRate"], "basePlate.frameRate", 1, 240)
    if (
        not isinstance(base["storageKey"], str)
        or base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or base["pixelFormat"] != "yuv420p"
        or width % 2
        or height % 2
    ):
        raise RenderArtifactError("basePlate media contract is unsupported")
    return base


def _validate_image(value: object, label: str) -> dict[str, Any]:
    image = _closed(value, _IMAGE_FIELDS, label)
    _ref(image["assetVersionRef"], f"{label}.assetVersionRef")
    _digest(image["assetVersionDigest"], f"{label}.assetVersionDigest")
    _digest(image["fileDigest"], f"{label}.fileDigest", prefixed=True)
    _digest(image["pixelDigest"], f"{label}.pixelDigest", prefixed=True)
    _integer(image["width"], f"{label}.width", 1, 16384)
    _integer(image["height"], f"{label}.height", 1, 16384)
    if (
        not isinstance(image["storageKey"], str)
        or image["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC
        or image["pixelMode"] != "RGBA"
    ):
        raise RenderArtifactError(f"{label} pixel contract is unsupported")
    return image


def _validate_quad(
    value: object,
    *,
    coordinate_space: str,
    width: int,
    height: int,
    label: str,
) -> list[int]:
    if not isinstance(value, list) or len(value) != 8:
        raise RenderArtifactError(f"{label} is invalid")
    x_bounds = (
        (-4000, 5000)
        if coordinate_space == "NORMALIZED_PERMILLE"
        else (-width * 4, width * 5)
    )
    y_bounds = (
        (-4000, 5000)
        if coordinate_space == "NORMALIZED_PERMILLE"
        else (-height * 4, height * 5)
    )
    result = [
        _integer(
            item,
            f"{label}[{index}]",
            *(x_bounds if index % 2 == 0 else y_bounds),
        )
        for index, item in enumerate(value)
    ]
    points = [
        (result[index], result[index + 1]) for index in range(0, 8, 2)
    ]
    crosses = []
    for index in range(4):
        a, b, c = (
            points[index],
            points[(index + 1) % 4],
            points[(index + 2) % 4],
        )
        crosses.append(
            (b[0] - a[0]) * (c[1] - b[1])
            - (b[1] - a[1]) * (c[0] - b[0])
        )
    if any(item == 0 for item in crosses) or not (
        all(item > 0 for item in crosses)
        or all(item < 0 for item in crosses)
    ):
        raise RenderArtifactError(f"{label} is not a convex quad")
    return result


def _quad_crosses(value: Sequence[int | Fraction]) -> list[Fraction]:
    points = [
        (Fraction(value[index]), Fraction(value[index + 1]))
        for index in range(0, 8, 2)
    ]
    result: list[Fraction] = []
    for index in range(4):
        a, b, c = (
            points[index],
            points[(index + 1) % 4],
            points[(index + 2) % 4],
        )
        result.append(
            (b[0] - a[0]) * (c[1] - b[1])
            - (b[1] - a[1]) * (c[0] - b[0])
        )
    return result


def _require_safe_quad_interpolation(
    left: Sequence[int], right: Sequence[int], *, winding: int
) -> None:
    """Prove each signed corner cross stays non-zero for p in [0,1]."""

    def crosses(progress: Fraction) -> list[Fraction]:
        value = [
            Fraction(start) + (Fraction(end) - Fraction(start)) * progress
            for start, end in zip(left, right, strict=True)
        ]
        return _quad_crosses(value)

    at_zero = crosses(Fraction(0))
    at_half = crosses(Fraction(1, 2))
    at_one = crosses(Fraction(1))
    for first, half, last in zip(
        at_zero, at_half, at_one, strict=True
    ):
        quadratic = 2 * (last + first - 2 * half)
        linear = last - first - quadratic
        candidates = [first, last]
        if quadratic:
            vertex = -linear / (2 * quadratic)
            if 0 < vertex < 1:
                candidates.append(
                    quadratic * vertex * vertex + linear * vertex + first
                )
        if any(winding * value <= 0 for value in candidates):
            raise RenderArtifactError(
                "perspective interpolation becomes degenerate"
            )


def _validate_motion(
    value: object,
    *,
    start: int,
    end: int,
    coordinate_space: str,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 128:
        raise RenderArtifactError("motionKeyframes are invalid")
    x_bounds = (
        (-4000, 5000)
        if coordinate_space == "NORMALIZED_PERMILLE"
        else (-width * 4, width * 5)
    )
    y_bounds = (
        (-4000, 5000)
        if coordinate_space == "NORMALIZED_PERMILLE"
        else (-height * 4, height * 5)
    )
    result: list[dict[str, Any]] = []
    previous = start - 1
    for index, raw in enumerate(value):
        item = _closed(raw, _MOTION_FIELDS, f"motionKeyframes[{index}]")
        frame = _integer(
            item["frame"], f"motionKeyframes[{index}].frame", start, end - 1
        )
        if frame <= previous or item["interpolation"] not in _INTERPOLATIONS:
            raise RenderArtifactError("motionKeyframes order is invalid")
        item["x"] = _integer(item["x"], "motion.x", *x_bounds)
        item["y"] = _integer(item["y"], "motion.y", *y_bounds)
        for axis in ("X", "Y"):
            numerator = _integer(
                item[f"scale{axis}Numerator"],
                f"scale{axis}Numerator",
                1,
                16000,
            )
            denominator = _integer(
                item[f"scale{axis}Denominator"],
                f"scale{axis}Denominator",
                1,
                16000,
            )
            if gcd(numerator, denominator) != 1:
                raise RenderArtifactError("motion scale rational is not normalized")
        _integer(
            item["rotationMilliDegrees"],
            "rotationMilliDegrees",
            -360000,
            360000,
        )
        item["perspectiveQuad"] = _validate_quad(
            item["perspectiveQuad"],
            coordinate_space=coordinate_space,
            width=width,
            height=height,
            label=f"motionKeyframes[{index}].perspectiveQuad",
        )
        result.append(item)
        previous = frame
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise RenderArtifactError("motionKeyframes do not close the frame range")
    winding = 1 if _quad_crosses(result[0]["perspectiveQuad"])[0] > 0 else -1
    for item in result:
        if any(
            winding * value <= 0
            for value in _quad_crosses(item["perspectiveQuad"])
        ):
            raise RenderArtifactError(
                "perspective keyframes change winding"
            )
    for left, right in zip(result, result[1:]):
        if left["interpolation"] != "STEP":
            _require_safe_quad_interpolation(
                left["perspectiveQuad"],
                right["perspectiveQuad"],
                winding=winding,
            )
    return result


def _pixel(value: int, extent: int, coordinate_space: str) -> int:
    if coordinate_space == "CANVAS_PIXELS":
        return value
    scaled = value * extent
    if scaled % 1000:
        raise RenderArtifactError("normalized coordinate is not an exact pixel")
    return scaled // 1000


def _derive_distance(
    motion: Sequence[Mapping[str, Any]],
    contract_value: object,
    *,
    coordinate_space: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    contract = _closed(contract_value, _DISTANCE_FIELDS, "distanceContract")
    metric, direction = contract["metric"], contract["direction"]
    if metric not in _DISTANCE_METRICS or direction not in _DIRECTIONS:
        raise RenderArtifactError("distanceContract mode is invalid")
    _integer(contract["startValue"], "distanceContract.startValue", 0, 100_000_000)
    _integer(contract["endValue"], "distanceContract.endValue", 0, 100_000_000)
    if _integer(contract["tolerance"], "distanceContract.tolerance", 0, 0) != 0:
        raise RenderArtifactError("distanceContract tolerance must be zero")
    first, last = motion[0], motion[-1]
    if metric == "RELATIVE_SCALE_PERMILLE":
        if contract["referenceX"] is not None or contract["referenceY"] is not None:
            raise RenderArtifactError("scale distance forbids a reference point")
        derived = []
        all_scales = []
        for item in motion:
            if (
                item["scaleXNumerator"] != item["scaleYNumerator"]
                or item["scaleXDenominator"] != item["scaleYDenominator"]
            ):
                raise RenderArtifactError("scale distance must be uniform")
            value = item["scaleXNumerator"] * 1000
            if value % item["scaleXDenominator"]:
                raise RenderArtifactError("scale distance is not exact permille")
            all_scales.append(value // item["scaleXDenominator"])
        derived = [all_scales[0], all_scales[-1]]
    else:
        rx = _pixel(
            _integer(contract["referenceX"], "referenceX", -100_000_000, 100_000_000),
            width,
            coordinate_space,
        )
        ry = _pixel(
            _integer(contract["referenceY"], "referenceY", -100_000_000, 100_000_000),
            height,
            coordinate_space,
        )
        derived = []
        for item in (first, last):
            x = _pixel(item["x"], width, coordinate_space)
            y = _pixel(item["y"], height, coordinate_space)
            squared = (x - rx) ** 2 + (y - ry) ** 2
            distance = isqrt(squared)
            if distance * distance != squared:
                raise RenderArtifactError("screen distance is not an exact integer")
            derived.append(distance)
    start_value, end_value = derived
    if (contract["startValue"], contract["endValue"]) != (
        start_value,
        end_value,
    ):
        raise RenderArtifactError("distanceContract is stale")
    if direction == "APPROACH" and not (
        end_value < start_value
        if metric == "SCREEN_EUCLIDEAN_PIXELS"
        else end_value > start_value
    ):
        raise RenderArtifactError("APPROACH distanceContract is false")
    if direction == "RECEDE" and not (
        end_value > start_value
        if metric == "SCREEN_EUCLIDEAN_PIXELS"
        else end_value < start_value
    ):
        raise RenderArtifactError("RECEDE distanceContract is false")
    if direction == "LATERAL" and not (
        metric == "SCREEN_EUCLIDEAN_PIXELS"
        and start_value == end_value
        and (first["x"], first["y"]) != (last["x"], last["y"])
    ):
        raise RenderArtifactError("LATERAL distanceContract is false")
    return deepcopy(contract)


def _validate_visual_states(
    definitions_value: object,
    schedule_value: object,
    *,
    start_state_ref: object,
    end_state_ref: object,
    variants: Mapping[str, Mapping[str, Any]],
    start: int,
    end: int,
    layer: int,
    blend_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if (
        not isinstance(definitions_value, list)
        or not 1 <= len(definitions_value) <= 64
    ):
        raise RenderArtifactError("visualStateDefinitions are invalid")
    definitions: list[dict[str, Any]] = []
    by_ref: dict[str, dict[str, Any]] = {}
    used_variants: set[str] = set()
    for index, raw in enumerate(definitions_value):
        item = _closed(raw, _STATE_FIELDS, f"visualStateDefinitions[{index}]")
        state_ref = _ref(item["stateRef"], f"visualStateDefinitions[{index}].stateRef")
        if state_ref in by_ref or item["visibility"] not in {"VISIBLE", "HIDDEN"}:
            raise RenderArtifactError("visual state identity is invalid")
        opacity = _integer(item["opacityPermille"], "opacityPermille", 0, 1000)
        if item["visibility"] == "HIDDEN" and opacity != 0:
            raise RenderArtifactError("HIDDEN visual state must be transparent")
        if item["layer"] != layer or item["blendMode"] != blend_mode:
            raise RenderArtifactError("visual state layer/blend binding is stale")
        variant_ref = item["variantAssetVersionRef"]
        variant_digest = item["variantAssetVersionDigest"]
        if variant_ref is None and variant_digest is None:
            pass
        elif variant_ref is None or variant_digest is None:
            raise RenderArtifactError("visual state variant binding is partial")
        else:
            _ref(variant_ref, "variantAssetVersionRef")
            _digest(variant_digest, "variantAssetVersionDigest")
            if (
                variant_ref not in variants
                or variants[variant_ref]["assetVersionDigest"] != variant_digest
            ):
                raise RenderArtifactError("visual state variant binding is stale")
            used_variants.add(variant_ref)
        by_ref[state_ref] = item
        definitions.append(item)
    if used_variants != set(variants):
        raise RenderArtifactError("variantAssets are not the exact visual set")
    first_ref = _ref(start_state_ref, "startStateRef")
    last_ref = _ref(end_state_ref, "endStateRef")
    if first_ref not in by_ref or last_ref not in by_ref:
        raise RenderArtifactError("start/end visual state is undefined")
    if (
        not isinstance(schedule_value, list)
        or not 1 <= len(schedule_value) <= 64
    ):
        raise RenderArtifactError("visualStateSchedule is invalid")
    schedule: list[dict[str, Any]] = []
    cursor = start
    for index, raw in enumerate(schedule_value):
        item = _closed(raw, _SCHEDULE_FIELDS, f"visualStateSchedule[{index}]")
        state_ref = _ref(item["stateRef"], f"visualStateSchedule[{index}].stateRef")
        interval_start = _integer(
            item["startFrameInclusive"], "startFrameInclusive", start, end - 1
        )
        interval_end = _integer(
            item["endFrameExclusive"], "endFrameExclusive", start + 1, end
        )
        interpolation = item["transitionInterpolation"]
        if (
            state_ref not in by_ref
            or interval_start != cursor
            or interval_end <= interval_start
            or interpolation not in _INTERPOLATIONS
        ):
            raise RenderArtifactError("visualStateSchedule has a gap or overlap")
        if (
            by_ref[state_ref]["variantAssetVersionRef"] is not None
            and interpolation != "STEP"
        ):
            raise RenderArtifactError("variant state switching requires STEP")
        schedule.append(item)
        cursor = interval_end
    if (
        cursor != end
        or schedule[0]["stateRef"] != first_ref
        or schedule[-1]["stateRef"] != last_ref
    ):
        raise RenderArtifactError("visualStateSchedule does not close its range")
    return definitions, schedule


def _validate_render_budget(
    *,
    request: Mapping[str, Any],
    base: Mapping[str, Any],
    subject: Mapping[str, Any] | None,
    variants: Mapping[str, Mapping[str, Any]],
    motion: Sequence[Mapping[str, Any]],
    definitions: Sequence[Mapping[str, Any]],
    schedule: Sequence[Mapping[str, Any]],
) -> None:
    """Reject sealed graphs that exceed a canvas-relative CPU budget."""

    canvas_area = int(base["width"]) * int(base["height"])
    max_scale_x = max(
        Fraction(item["scaleXNumerator"], item["scaleXDenominator"])
        for item in motion
    )
    max_scale_y = max(
        Fraction(item["scaleYNumerator"], item["scaleYDenominator"])
        for item in motion
    )
    branches: list[Mapping[str, Any]] = []
    if request["targetKind"] == "FULL_FRAME":
        x_limit = (
            1000
            if request["coordinateSpace"] == "NORMALIZED_PERMILLE"
            else base["width"]
        )
        y_limit = (
            1000
            if request["coordinateSpace"] == "NORMALIZED_PERMILLE"
            else base["height"]
        )
        if any(
            not 0 <= item["x"] <= x_limit
            or not 0 <= item["y"] <= y_limit
            for item in motion
        ):
            raise RenderArtifactError(
                "FULL_FRAME center leaves the fixed canvas safe area"
            )
        branches = [base] * max(1, len(schedule))
    else:
        if subject is None:
            raise RenderArtifactError("overlay subject is unavailable")
        by_state = {item["stateRef"]: item for item in definitions}
        intervals: Sequence[Mapping[str, Any]] = schedule or (
            {"stateRef": None},
        )
        for interval in intervals:
            definition = by_state.get(interval["stateRef"])
            variant_ref = (
                None
                if definition is None
                else definition["variantAssetVersionRef"]
            )
            branches.append(
                subject if variant_ref is None else variants[variant_ref]
            )
    if len(branches) > 64:
        raise RenderArtifactError("distance/state graph has too many branches")

    total_pixels = 0
    per_branch_limit = max(canvas_area * 4, 1_000_000)
    total_limit = max(canvas_area * 8, 4_000_000)
    for source in branches:
        scaled_width = (
            int(source["width"]) * max_scale_x.numerator
            + max_scale_x.denominator
            - 1
        ) // max_scale_x.denominator
        scaled_height = (
            int(source["height"]) * max_scale_y.numerator
            + max_scale_y.denominator
            - 1
        ) // max_scale_y.denominator
        scaled_area = scaled_width * scaled_height
        if (
            scaled_width > 32_768
            or scaled_height > 32_768
            or scaled_area > per_branch_limit
        ):
            raise RenderArtifactError(
                "distance/state transformed surface exceeds the closed budget"
            )
        total_pixels += scaled_area
    if total_pixels > total_limit:
        raise RenderArtifactError(
            "distance/state graph exceeds the closed aggregate pixel budget"
        )


def _validate(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _REQUEST_FIELDS, "distance/state request")
    claimed = request.pop("payloadDigest")
    _digest(claimed, "payloadDigest")
    if claimed != sha256(_canonical(request)).hexdigest():
        raise RenderArtifactError("distance/state request seal is invalid")
    request["payloadDigest"] = claimed
    if (
        request["schemaVersion"] != DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION
        or request["effectMode"] != "DISTANCE_STATE_TRANSITION"
        or request["publicationAllowed"] is not False
        or request["targetKind"] not in _TARGET_KINDS
        or request["transitionMode"] not in _TRANSITION_MODES
        or request["coordinateSpace"] not in _COORDINATE_SPACES
        or request["blendMode"] not in _BLEND_MODES
    ):
        raise RenderArtifactError("distance/state execution boundary is invalid")
    for field in (
        "v5ExecutionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _ref(request[field], field)
    for field in ("v5ExecutionRequestDigest", "requirementDigest"):
        _digest(request[field], field)
    shot = _closed(request["targetShot"], _SHOT_FIELDS, "targetShot")
    _ref(shot["shotRef"], "targetShot.shotRef")
    _ref(shot["shotVersionRef"], "targetShot.shotVersionRef")
    _digest(shot["shotVersionDigest"], "targetShot.shotVersionDigest")
    base = _validate_base(request["basePlate"])
    start = _integer(
        request["frameRangeStartInclusive"],
        "frameRangeStartInclusive",
        0,
        base["frameCount"] - 1,
    )
    end = _integer(
        request["frameRangeEndExclusive"],
        "frameRangeEndExclusive",
        1,
        base["frameCount"],
    )
    if end <= start:
        raise RenderArtifactError("distance/state frame range is invalid")
    layer = _integer(request["layer"], "layer", 0, 1024)
    output = _closed(request["output"], _OUTPUT_FIELDS, "output")
    if output != {
        "width": base["width"],
        "height": base["height"],
        "frameCount": base["frameCount"],
        "frameRate": base["frameRate"],
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }:
        raise RenderArtifactError("distance/state output does not match basePlate")
    motion = _validate_motion(
        request["motionKeyframes"],
        start=start,
        end=end,
        coordinate_space=request["coordinateSpace"],
        width=base["width"],
        height=base["height"],
    )
    if not isinstance(request["variantAssets"], list):
        raise RenderArtifactError("variantAssets are invalid")
    variants_list = [
        _validate_image(item, f"variantAssets[{index}]")
        for index, item in enumerate(request["variantAssets"])
    ]
    variants = {item["assetVersionRef"]: item for item in variants_list}
    if len(variants) != len(variants_list):
        raise RenderArtifactError("variantAssets are ambiguous")
    if request["targetKind"] == "FULL_FRAME":
        if (
            request["subjectLayer"] is not None
            or request["mask"] is not None
            or variants
        ):
            raise RenderArtifactError("FULL_FRAME forbids overlay assets")
        subject = mask = None
    else:
        subject = _validate_image(request["subjectLayer"], "subjectLayer")
        mask = _validate_image(request["mask"], "mask")
        if (
            (subject["width"], subject["height"])
            != (mask["width"], mask["height"])
            or any(
                (item["width"], item["height"])
                != (subject["width"], subject["height"])
                for item in variants.values()
            )
        ):
            raise RenderArtifactError("overlay image dimensions are incompatible")
        refs = {
            base["assetVersionRef"],
            subject["assetVersionRef"],
            mask["assetVersionRef"],
            *variants,
        }
        if len(refs) != 3 + len(variants):
            raise RenderArtifactError("distance/state asset roles collide")
    if request["transitionMode"] == "VISUAL_STATE":
        if request["distanceContract"] is not None or any(
            any(
                item[field] != motion[0][field]
                for field in (
                    "x",
                    "y",
                    "scaleXNumerator",
                    "scaleXDenominator",
                    "scaleYNumerator",
                    "scaleYDenominator",
                    "rotationMilliDegrees",
                    "perspectiveQuad",
                )
            )
            for item in motion[1:]
        ):
            raise RenderArtifactError("VISUAL_STATE motion must be constant")
        derived_distance = None
    else:
        derived_distance = _derive_distance(
            motion,
            request["distanceContract"],
            coordinate_space=request["coordinateSpace"],
            width=base["width"],
            height=base["height"],
        )
    if request["transitionMode"] == "SCREEN_DISTANCE":
        if (
            request["startStateRef"] is not None
            or request["endStateRef"] is not None
            or request["visualStateDefinitions"] != []
            or request["visualStateSchedule"] != []
            or variants
        ):
            raise RenderArtifactError("SCREEN_DISTANCE forbids visual states")
        definitions: list[dict[str, Any]] = []
        schedule: list[dict[str, Any]] = []
    else:
        definitions, schedule = _validate_visual_states(
            request["visualStateDefinitions"],
            request["visualStateSchedule"],
            start_state_ref=request["startStateRef"],
            end_state_ref=request["endStateRef"],
            variants=variants,
            start=start,
            end=end,
            layer=layer,
            blend_mode=request["blendMode"],
        )
    _validate_render_budget(
        request=request,
        base=base,
        subject=subject,
        variants=variants,
        motion=motion,
        definitions=definitions,
        schedule=schedule,
    )
    request.update(
        {
            "targetShot": shot,
            "basePlate": base,
            "subjectLayer": subject,
            "mask": mask,
            "variantAssets": variants_list,
            "motionKeyframes": motion,
            "distanceContract": derived_distance,
            "visualStateDefinitions": definitions,
            "visualStateSchedule": schedule,
            "output": output,
        }
    )
    return request


def validate_distance_state_preview_stage(
    stage: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate Preview through the exact standalone V3 request contract."""

    return _validate(stage)


def _asset_name(reference: str) -> str:
    return "variant:" + reference


def distance_state_preview_assets(
    stage: Mapping[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    """Return one closed, unique, deterministic image-input order."""

    request = _validate(stage)
    if request["targetKind"] == "FULL_FRAME":
        return []
    return [
        ("subject", deepcopy(request["subjectLayer"])),
        ("mask", deepcopy(request["mask"])),
        *[
            (_asset_name(item["assetVersionRef"]), deepcopy(item))
            for item in request["variantAssets"]
        ],
    ]


def _ease(progress: str, interpolation: str) -> str:
    return {
        "STEP": "0",
        "LINEAR": progress,
        "EASE_IN": f"({progress}*{progress})",
        "EASE_OUT": f"(1-(1-{progress})*(1-{progress}))",
        "EASE_IN_OUT": (
            f"if(lt({progress},0.5),2*{progress}*{progress},"
            f"1-2*(1-{progress})*(1-{progress}))"
        ),
    }[interpolation]


def _motion_expression(
    motion: Sequence[Mapping[str, Any]],
    value,
    *,
    frame_variable: str = "n",
) -> str:
    first_value = value(motion[0])
    expression = value(motion[-1])
    for left, right in reversed(list(zip(motion, motion[1:]))):
        start, end = left["frame"], right["frame"]
        progress = f"(({frame_variable}-{start})/{end - start})"
        eased = _ease(progress, left["interpolation"])
        left_value, right_value = value(left), value(right)
        segment = f"({left_value}+({right_value}-{left_value})*{eased})"
        expression = f"if(lt({frame_variable},{end}),{segment},{expression})"
    return f"if(lt({frame_variable},{motion[0]['frame']}),{first_value},{expression})"


def _coordinate_expression(
    request: Mapping[str, Any], field: str, extent: int
) -> str:
    expression = _motion_expression(
        request["motionKeyframes"], lambda item: str(item[field])
    )
    if request["coordinateSpace"] == "NORMALIZED_PERMILLE":
        return f"(({expression})*{extent}/1000)"
    return expression


def _scale_expression(request: Mapping[str, Any], axis: str) -> str:
    return _motion_expression(
        request["motionKeyframes"],
        lambda item: (
            f"({item[f'scale{axis}Numerator']}/"
            f"{item[f'scale{axis}Denominator']})"
        ),
    )


def _quad_expression(
    request: Mapping[str, Any],
    index: int,
    *,
    frame_variable: str,
    source_facts: Mapping[str, Any],
) -> str:
    expression = _motion_expression(
        request["motionKeyframes"],
        lambda item: str(item["perspectiveQuad"][index]),
        frame_variable=frame_variable,
    )
    if request["coordinateSpace"] == "NORMALIZED_PERMILLE":
        extent = source_facts["width" if index % 2 == 0 else "height"]
        return f"(({expression})*{extent}/1000)"
    return expression


def _perspective_is_identity(
    request: Mapping[str, Any], source: Mapping[str, Any]
) -> bool:
    if request["coordinateSpace"] == "NORMALIZED_PERMILLE":
        identity = [0, 0, 1000, 0, 1000, 1000, 0, 1000]
    else:
        identity = [
            0,
            0,
            source["width"],
            0,
            source["width"],
            source["height"],
            0,
            source["height"],
        ]
    return all(
        item["perspectiveQuad"] == identity
        for item in request["motionKeyframes"]
    )


def _transform_filters(
    request: Mapping[str, Any],
    *,
    source_label: str,
    source_facts: Mapping[str, Any],
    prefix: str,
    opacity: int | str,
) -> tuple[list[str], str]:
    filters: list[str] = []
    current = source_label
    if not _perspective_is_identity(request, source_facts):
        perspective = f"{prefix}perspective"
        # The closed quad is TL,TR,BR,BL while FFmpeg's perspective options
        # are TL,TR,BL,BR.  Map the final two points deliberately.
        order = (0, 1, 2, 3, 6, 7, 4, 5)
        options = []
        for option_index, contract_index in enumerate(order):
            axis = "x" if option_index % 2 == 0 else "y"
            corner = option_index // 2
            options.append(
                f"{axis}{corner}='{_quad_expression(request, contract_index, frame_variable='in', source_facts=source_facts)}'"
            )
        filters.append(
            f"[{current}]format=rgba,perspective={':'.join(options)}:"
            f"sense=destination:eval=frame[{perspective}]"
        )
        current = perspective
    rotated = f"{prefix}rotated"
    rotation = _motion_expression(
        request["motionKeyframes"],
        lambda item: str(item["rotationMilliDegrees"]),
    )
    filters.append(
        f"[{current}]rotate=a='({rotation})*PI/180000':ow=iw:oh=ih:"
        f"fillcolor=black@0[{rotated}]"
    )
    scaled = f"{prefix}scaled"
    scale_x = _scale_expression(request, "X")
    scale_y = _scale_expression(request, "Y")
    filters.append(
        f"[{rotated}]scale=w='max(1,round(iw*({scale_x})))':"
        f"h='max(1,round(ih*({scale_y})))':eval=frame:flags=neighbor"
        f"[{scaled}]"
    )
    output = f"{prefix}opacity"
    if isinstance(opacity, int):
        filters.append(
            f"[{scaled}]format=rgba,colorchannelmixer=aa="
            f"{opacity / 1000:.3f}[{output}]"
        )
    else:
        filters.append(
            f"[{scaled}]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':"
            f"b='b(X,Y)':a='alpha(X,Y)*(({opacity})/1000)'[{output}]"
        )
    return filters, output


def _split_filter(
    input_label: str, output_labels: list[str], *, rgba: bool = True
) -> str:
    prefix = "format=rgba," if rgba else ""
    if len(output_labels) == 1:
        return f"[{input_label}]{prefix}null[{output_labels[0]}]"
    outputs = "".join(f"[{item}]" for item in output_labels)
    return f"[{input_label}]{prefix}split={len(output_labels)}{outputs}"


def _interval_opacity(
    intervals: Sequence[Mapping[str, Any]],
    definitions: Mapping[Any, Mapping[str, Any]],
    index: int,
) -> int | str:
    current = definitions[intervals[index]["stateRef"]]
    current_value = (
        current["opacityPermille"]
        if current["visibility"] == "VISIBLE"
        else 0
    )
    interpolation = intervals[index]["transitionInterpolation"]
    if index == 0 or interpolation == "STEP":
        return current_value
    previous = definitions[intervals[index - 1]["stateRef"]]
    if previous["variantAssetVersionRef"] != current["variantAssetVersionRef"]:
        raise RenderArtifactError("variant transition interpolation is forbidden")
    previous_value = (
        previous["opacityPermille"]
        if previous["visibility"] == "VISIBLE"
        else 0
    )
    start = intervals[index]["startFrameInclusive"]
    end = intervals[index]["endFrameExclusive"]
    if end - start <= 1:
        return current_value
    progress = f"((N-{start})/{end - start - 1})"
    eased = _ease(progress, interpolation)
    return f"({previous_value}+({current_value}-{previous_value})*{eased})"


def build_distance_state_preview_filters(
    stage: Mapping[str, Any],
    *,
    input_label: str,
    asset_input_labels: Mapping[str, str],
    prefix: str,
) -> tuple[list[str], str]:
    """Generate the exact graph used by standalone and Timeline Preview."""

    request = _validate(stage)
    if (
        not isinstance(input_label, str)
        or re.fullmatch(
            r"[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?", input_label
        )
        is None
        or not isinstance(prefix, str)
        or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", prefix)
        or not isinstance(asset_input_labels, Mapping)
        or input_label.startswith(prefix)
    ):
        raise RenderArtifactError("distance/state graph labels are invalid")
    expected_assets = dict(distance_state_preview_assets(request))
    asset_labels = list(asset_input_labels.values())
    if (
        set(asset_input_labels) != set(expected_assets)
        or len(set(asset_labels)) != len(asset_labels)
        or input_label in asset_labels
        or any(
            not isinstance(item, str)
            or re.fullmatch(
                r"[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?", item
            )
            is None
            or item.startswith(prefix)
            for item in asset_labels
        )
    ):
        raise RenderArtifactError("distance/state graph assets are not exact")

    start = request["frameRangeStartInclusive"]
    end = request["frameRangeEndExclusive"]
    if request["visualStateSchedule"]:
        intervals = deepcopy(request["visualStateSchedule"])
        definitions = {
            item["stateRef"]: item
            for item in request["visualStateDefinitions"]
        }
    else:
        intervals = [
            {
                "stateRef": None,
                "startFrameInclusive": start,
                "endFrameExclusive": end,
                "transitionInterpolation": "STEP",
            }
        ]
        definitions = {
            None: {
                "visibility": "VISIBLE",
                "opacityPermille": 1000,
                "variantAssetVersionRef": None,
            }
        }

    filters: list[str] = []
    previous_label: str
    source_labels: list[str] = []
    if request["targetKind"] == "FULL_FRAME":
        previous_label = f"{prefix}base"
        source_labels = [f"{prefix}source{index}" for index in range(len(intervals))]
        filters.append(
            _split_filter(
                input_label,
                [previous_label, *source_labels],
            )
        )
    else:
        previous_label = input_label
        source_usage: dict[str, list[tuple[int, str]]] = {}
        for index, interval in enumerate(intervals):
            definition = definitions[interval["stateRef"]]
            variant_ref = definition["variantAssetVersionRef"]
            name = "subject" if variant_ref is None else _asset_name(variant_ref)
            source_usage.setdefault(name, []).append(
                (index, f"{prefix}raw{index}")
            )
        for name, uses in source_usage.items():
            filters.append(
                _split_filter(
                    asset_input_labels[name],
                    [label for _index, label in uses],
                )
            )
            for index, label in uses:
                while len(source_labels) <= index:
                    source_labels.append("")
                source_labels[index] = label
        mask_labels = [f"{prefix}mask{index}" for index in range(len(intervals))]
        mask_outputs = "".join(f"[{item}]" for item in mask_labels)
        if len(mask_labels) == 1:
            filters.append(
                f"[{asset_input_labels['mask']}]format=gray"
                f"[{mask_labels[0]}]"
            )
        else:
            filters.append(
                f"[{asset_input_labels['mask']}]format=gray,"
                f"split={len(mask_labels)}{mask_outputs}"
            )

    for index, interval in enumerate(intervals):
        definition = definitions[interval["stateRef"]]
        source = source_labels[index]
        source_facts: Mapping[str, Any]
        if request["targetKind"] == "OVERLAY_LAYER":
            alpha = f"{prefix}alpha{index}"
            filters.append(f"[{source}][{prefix}mask{index}]alphamerge[{alpha}]")
            source = alpha
            variant_ref = definition["variantAssetVersionRef"]
            source_facts = (
                request["subjectLayer"]
                if variant_ref is None
                else next(
                    item
                    for item in request["variantAssets"]
                    if item["assetVersionRef"] == variant_ref
                )
            )
        else:
            source_facts = request["basePlate"]
        opacity = _interval_opacity(intervals, definitions, index)
        stage_filters, transformed = _transform_filters(
            request,
            source_label=source,
            source_facts=source_facts,
            prefix=f"{prefix}s{index}",
            opacity=opacity,
        )
        filters.extend(stage_filters)
        x = _coordinate_expression(request, "x", request["output"]["width"])
        y = _coordinate_expression(request, "y", request["output"]["height"])
        active = (
            f"between(n,{interval['startFrameInclusive']},"
            f"{interval['endFrameExclusive'] - 1})"
        )
        if request["targetKind"] == "FULL_FRAME":
            canvas = f"{prefix}canvas{index}"
            moved = f"{prefix}moved{index}"
            filters.append(
                f"color=c=black@1.0:s={request['output']['width']}x"
                f"{request['output']['height']}:r={request['output']['frameRate']},"
                f"format=rgba[{canvas}]"
            )
            filters.append(
                f"[{canvas}][{transformed}]overlay=x='({x})-w/2':"
                f"y='({y})-h/2':eof_action=pass:shortest=0:format=auto"
                f"[{moved}]"
            )
            transformed = moved
            overlay_x, overlay_y = "0", "0"
        else:
            overlay_x, overlay_y = f"({x})-w/2", f"({y})-h/2"
        output_label = f"{prefix}out{index}"
        filters.append(
            f"[{previous_label}][{transformed}]overlay=x='{overlay_x}':"
            f"y='{overlay_y}':enable='{active}':eof_action=pass:shortest=0:"
            f"format=auto[{output_label}]"
        )
        previous_label = output_label
    final = f"{prefix}out"
    filters.append(f"[{previous_label}]format=yuv420p[{final}]")
    return filters, final


def _require_image_pixels(
    path: Path,
    binding: Mapping[str, Any],
    *,
    ffmpeg: _PinnedRuntimeBinary,
    ffprobe: _PinnedRuntimeBinary,
    pass_fds: tuple[int, ...],
) -> None:
    try:
        measured = image_digest_metadata(
            path,
            ffmpeg_path=ffmpeg.executable_path,
            ffprobe_path=ffprobe.executable_path,
            pass_fds=pass_fds,
        )
    except DigestError as exc:
        raise RenderArtifactError("distance/state image digest failed") from exc
    if (
        measured["pixel_digest"] != binding["pixelDigest"]
        or measured["pixel_digest_spec"] != binding["pixelDigestSpec"]
        or measured["pixel_mode"] != binding["pixelMode"]
        or measured["width"] != binding["width"]
        or measured["height"] != binding["height"]
    ):
        raise RenderArtifactError("distance/state image pixels changed")


class DeterministicDistanceStateExecutor:
    """Execute one sealed E4 projection with held runtimes and inputs."""

    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise RenderArtifactError("distance/state artifact root is invalid")

    def execute(self, value: Mapping[str, Any]) -> dict[str, Any]:
        request = _validate(value)
        base_source = _safe_glyph_input(
            self.artifact_root, request["basePlate"]["storageKey"]
        )
        asset_bindings = distance_state_preview_assets(request)
        asset_sources = [
            _safe_glyph_input(self.artifact_root, binding["storageKey"])
            for _name, binding in asset_bindings
        ]
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path is None or ffprobe_path is None:
            raise RenderArtifactError("pinned FFmpeg runtime is unavailable")
        with (
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffmpeg_path)), label="FFmpeg"
            ) as ffmpeg,
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffprobe_path)), label="FFprobe"
            ) as ffprobe,
        ):
            return self._execute_validated(
                request,
                base_source=base_source,
                asset_bindings=asset_bindings,
                asset_sources=asset_sources,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )

    def _execute_validated(
        self,
        request: Mapping[str, Any],
        *,
        base_source: Path,
        asset_bindings: list[tuple[str, dict[str, Any]]],
        asset_sources: list[Path],
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        output = request["output"]
        runtime_fds = tuple(dict.fromkeys(ffmpeg.pass_fds + ffprobe.pass_fds))
        ffmpeg_identity = ffmpeg.version_identity()
        with tempfile.TemporaryDirectory(
            prefix=".distance-state-work-", dir=self.artifact_root
        ) as temporary:
            work_root = Path(temporary)
            work_root.chmod(0o700)
            inputs = work_root / "inputs"
            inputs.mkdir(mode=0o700)
            base_path = inputs / "base.media"
            _stage_digest_pinned_input(
                base_source, base_path, request["basePlate"]["fileDigest"]
            )
            staged_assets: list[Path] = []
            for index, (source, (_name, binding)) in enumerate(
                zip(asset_sources, asset_bindings, strict=True)
            ):
                path = inputs / f"image-{index:04d}.png"
                _stage_digest_pinned_input(source, path, binding["fileDigest"])
                staged_assets.append(path)

            candidate = work_root / "candidate.mp4"
            with ExitStack() as stack:
                base_pin = stack.enter_context(
                    _PinnedRegularFile(base_path, label="distance/state base")
                )
                image_pins = [
                    stack.enter_context(
                        _PinnedRegularFile(
                            path, label=f"distance/state image {index}"
                        )
                    )
                    for index, path in enumerate(staged_assets)
                ]
                held_fds = tuple(
                    dict.fromkeys(
                        runtime_fds
                        + base_pin.pass_fds
                        + tuple(
                            descriptor
                            for pin in image_pins
                            for descriptor in pin.pass_fds
                        )
                    )
                )
                held_probe = SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=held_fds,
                )
                _validate_probe(
                    _probe_video(base_pin.descriptor_path, held_probe),
                    output,
                    input_media=True,
                )
                try:
                    base_pixels = decoded_frame_pixel_digest_metadata(
                        base_pin.descriptor_path,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=held_fds,
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        "distance/state base pixel digest failed"
                    ) from exc
                if (
                    base_pixels["decodedFramePixelDigest"]
                    != request["basePlate"]["pixelDigest"]
                    or base_pixels["decodedFramePixelDigestSpec"]
                    != request["basePlate"]["pixelDigestSpec"]
                    or base_pixels["width"] != output["width"]
                    or base_pixels["height"] != output["height"]
                    or base_pixels["frameCount"] != output["frameCount"]
                ):
                    raise RenderArtifactError("distance/state base pixels changed")
                for image_index, (pin, (_name, binding)) in enumerate(
                    zip(image_pins, asset_bindings, strict=True)
                ):
                    image_alias = inputs / f"held-image-{image_index:04d}.png"
                    os.symlink(pin.descriptor_path, image_alias)
                    _require_image_pixels(
                        image_alias,
                        binding,
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        pass_fds=held_fds,
                    )

                command = self._command_prefix(
                    ffmpeg=ffmpeg, base_path=base_pin.descriptor_path
                )
                for pin in image_pins:
                    command.extend(
                        [
                            "-loop",
                            "1",
                            "-framerate",
                            str(output["frameRate"]),
                            "-i",
                            str(pin.descriptor_path),
                        ]
                    )
                asset_labels = {
                    name: f"{index + 1}:v"
                    for index, (name, _binding) in enumerate(asset_bindings)
                }
                filters, output_label = build_distance_state_preview_filters(
                    request,
                    input_label="0:v",
                    asset_input_labels=asset_labels,
                    prefix="distance",
                )
                self._run(
                    command,
                    filters=filters,
                    output_label=output_label,
                    output=output,
                    candidate=candidate,
                    pass_fds=held_fds,
                )
                base_pin.require_stable()
                for pin in image_pins:
                    pin.require_stable()

            _validate_probe(
                _probe_video(candidate, ffprobe), output, input_media=False
            )
            try:
                output_digest = decoded_frame_pixel_digest_metadata(
                    candidate,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=runtime_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError(
                    "distance/state output digest failed"
                ) from exc
            if (
                output_digest["width"] != output["width"]
                or output_digest["height"] != output["height"]
                or output_digest["frameCount"] != output["frameCount"]
            ):
                raise RenderArtifactError("distance/state output media facts changed")
            output_digest["frameRate"] = output["frameRate"]
            state_digest = sha256(
                _canonical(
                    {
                        "visualStateDefinitions": request[
                            "visualStateDefinitions"
                        ],
                        "visualStateSchedule": request["visualStateSchedule"],
                    }
                )
            ).hexdigest()
            manifest = {
                "schemaVersion": DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION,
                "v3ExecutionRequestDigest": request["payloadDigest"],
                "rendererIdentity": DISTANCE_STATE_RENDERER_IDENTITY,
                "rendererVersion": DISTANCE_STATE_RENDERER_VERSION,
                "output": output,
                "graphDigest": "sha256:" + sha256(_canonical(filters)).hexdigest(),
                "edgePolicy": (
                    "BLACK_PAD_FIXED_CANVAS_CENTER_WITHIN_CANVAS"
                    if request["targetKind"] == "FULL_FRAME"
                    else "TRANSPARENT_OVERLAY_CLIPPED_TO_FIXED_CANVAS"
                ),
                "derivedDistanceFacts": request["distanceContract"],
                "appliedStateScheduleDigest": state_digest,
            }
            execution_manifest_digest = (
                "sha256:" + sha256(_canonical(manifest)).hexdigest()
            )
            directory = (
                self.artifact_root
                / sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
                / sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
                / "distance-state"
            )
            with _PinnedRegularFile(
                candidate, label="distance/state candidate"
            ) as pinned:
                if pinned.descriptor is None:
                    raise RenderArtifactError(
                        "distance/state candidate descriptor is unavailable"
                    )
                output_byte_size = os.fstat(pinned.descriptor).st_size
                destination = _publish_timeline_output_v1(
                    root=self.artifact_root,
                    directory=directory,
                    source=pinned,
                    expected_file_digest=output_digest["fileDigest"],
                    output_name=f"distance-state-{request['payloadDigest']}.mp4",
                )
            ffmpeg.require_stable()
            ffprobe.require_stable()

        runtime = {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": DISTANCE_STATE_RENDERER_IDENTITY,
            "rendererVersion": DISTANCE_STATE_RENDERER_VERSION,
            "executionManifestDigest": execution_manifest_digest,
        }
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(destination.relative_to(self.artifact_root)),
            "outputByteSize": output_byte_size,
            "outputMediaProbe": deepcopy(output),
            "outputDigest": output_digest,
            **runtime,
            "runtimeEvidenceDigest": "sha256:"
            + sha256(_canonical(runtime)).hexdigest(),
            "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
            "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
            "v3ExecutionRequestDigest": request["payloadDigest"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "derivedDistanceFacts": deepcopy(request["distanceContract"]),
            "appliedStateScheduleDigest": state_digest,
            "publicationAllowed": False,
        }

    @staticmethod
    def _command_prefix(
        *, ffmpeg: _PinnedRuntimeBinary, base_path: Path
    ) -> list[str]:
        return [
            str(ffmpeg.executable_path),
            "-hide_banner",
            "-loglevel",
            "error",
            "-xerror",
            "-nostdin",
            "-threads",
            "1",
            "-filter_threads",
            "1",
            "-filter_complex_threads",
            "1",
            "-sws_flags",
            "bitexact+accurate_rnd+full_chroma_int",
            "-hwaccel",
            "none",
            "-noautorotate",
            "-i",
            str(base_path),
        ]

    @staticmethod
    def _run(
        command: list[str],
        *,
        filters: list[str],
        output_label: str,
        output: Mapping[str, Any],
        candidate: Path,
        pass_fds: tuple[int, ...],
    ) -> None:
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                f"[{output_label}]",
                "-an",
                "-sn",
                "-dn",
                "-frames:v",
                str(output["frameCount"]),
                "-fps_mode",
                "passthrough",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-threads:v",
                "1",
                "-x264-params",
                "threads=1:lookahead_threads=1:sliced_threads=0:"
                "sync-lookahead=0:rc-lookahead=0:scenecut=0",
                "-fflags",
                "+bitexact",
                "-flags:v",
                "+bitexact",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-metadata",
                "creation_time=1970-01-01T00:00:00Z",
                "-movflags",
                "+faststart",
                "-video_track_timescale",
                str(output["frameRate"] * 512),
                "-n",
                str(candidate),
            ]
        )
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=300,
                env=_fixed_environment(),
                pass_fds=pass_fds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            message = ""
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                message = bytes(exc.stderr)[:1000].decode(
                    "utf-8", "replace"
                ).strip()
            raise RenderArtifactError(
                "FFmpeg distance/state execution failed"
                + (f": {message}" if message else "")
            ) from exc


__all__ = [
    "DISTANCE_STATE_RENDERER_IDENTITY",
    "DISTANCE_STATE_RENDERER_VERSION",
    "DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION",
    "DeterministicDistanceStateExecutor",
    "build_distance_state_preview_filters",
    "distance_state_preview_assets",
    "validate_distance_state_preview_stage",
]
