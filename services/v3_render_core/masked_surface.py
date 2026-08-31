"""Deterministic CPU/FFmpeg masked-surface execution owned by V3.

The public executor accepts one closed, V4-sealed request.  Storage keys are
server-resolved relative keys; callers cannot supply paths, argv or filter
expressions.  Every FFmpeg expression below is generated from validated
integer keyframes.
"""

from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

from .composition import (
    DeterministicFfmpegComposer,
    RenderArtifactError,
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
    _fixed_environment,
    _explicit_stage_ranges_v2,
    _glyph_filter_graph,
    _publish_timeline_output_v1,
    _safe_glyph_input,
    _stage_digest_pinned_input,
    _stage_timeline_preview_input,
    _validate_composite_params,
    _validate_timeline_preview_execution_request,
)
from .digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    _decoded_rgba_sha256,
    _probe_video_stream,
    decoded_frame_pixel_digest_metadata,
    image_digest_metadata,
)


MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v4.m13-masked-surface-execution-request.v1"
)
FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v4.m13-flame-smoke-execution-request.v1"
)
MASKED_SURFACE_RENDERER_IDENTITY = "v3.deterministic-masked-surface-ffmpeg"
MASKED_SURFACE_RENDERER_VERSION = "1"
EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v4.m13-effect-preview-execution-request.v2"
)
EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V3 = (
    "v4.m13-effect-preview-execution-request.v3"
)
EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4 = (
    "v4.m13-effect-preview-execution-request.v4"
)
EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V5 = (
    "v4.m13-effect-preview-execution-request.v5"
)
EFFECT_PREVIEW_RENDERER_IDENTITY = "v3.deterministic-timeline-preview-ffmpeg"
EFFECT_PREVIEW_RENDERER_VERSION = "2"
EFFECT_PREVIEW_RENDERER_VERSION_V3 = "3"
EFFECT_PREVIEW_RENDERER_VERSION_V4 = "4"
EFFECT_PREVIEW_RENDERER_VERSION_V5 = "5"

_RAW_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_E1_EFFECT_MODES = {"SCRATCH_REVEAL", "LIGHT_SWEEP", "LOCAL_EXPOSURE"}
_E2_EFFECT_MODES = {"FLAME_EXTINGUISH", "SMOKE"}
_EFFECT_MODES = _E1_EFFECT_MODES | _E2_EFFECT_MODES
_INTERPOLATIONS = {"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"}
_FLAME_STATE_PROFILES = {
    ("LIT", "DIMMING", "EXTINGUISHED", "DARK"),
    ("LIT", "DIMMING", "EXTINGUISHED", "EMBER", "DARK"),
}
_SMOKE_SOURCE_KINDS = {"PINNED_SMOKE_LAYER", "DETERMINISTIC_CPU_PROCEDURAL"}
_SMOKE_ALGORITHM_IDENTITY = "v3.deterministic-smoke-cpu"
_SMOKE_ALGORITHM_VERSION = "1"
_PROCEDURAL_SMOKE_TILE_WIDTH = 32
_PROCEDURAL_SMOKE_TILE_HEIGHT = 32
_BLEND_FILTERS = {
    "NORMAL": "normal",
    "MULTIPLY": "multiply",
    "SCREEN": "screen",
    "OVERLAY": "overlay",
    "ADD": "addition",
    "DARKEN": "darken",
    "LIGHTEN": "lighten",
}
_REQUEST_FIELDS = {
    "schemaVersion",
    "v5ExecutionRequestRef",
    "v5ExecutionRequestDigest",
    "workspaceRef",
    "productionRunRef",
    "requirementSchemaVersion",
    "requirementRef",
    "requirementDigest",
    "effectMode",
    "targetShot",
    "basePlate",
    "mask",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
    "explicitSchedule",
    "trajectoryKeyframes",
    "intensityCurve",
    "exposureCurve",
    "position",
    "scale",
    "perspective",
    "blendMode",
    "layer",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
_FLAME_REQUEST_FIELDS = {
    "schemaVersion",
    "v5ExecutionRequestRef",
    "v5ExecutionRequestDigest",
    "workspaceRef",
    "productionRunRef",
    "requirementSchemaVersion",
    "requirementRef",
    "requirementDigest",
    "effectMode",
    "targetShot",
    "basePlate",
    "flameMask",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
    "stateSchedule",
    "brightnessCurve",
    "alphaCurve",
    "localExposureRequirementRef",
    "localExposureRequirementDigest",
    "localExposureResultRef",
    "localExposureResultDigest",
    "localExposureStage",
    "blendMode",
    "layer",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
_SMOKE_REQUEST_FIELDS = {
    "schemaVersion",
    "v5ExecutionRequestRef",
    "v5ExecutionRequestDigest",
    "workspaceRef",
    "productionRunRef",
    "requirementSchemaVersion",
    "requirementRef",
    "requirementDigest",
    "effectMode",
    "targetShot",
    "basePlate",
    "smokeSourceKind",
    "smokeLayer",
    "emissionMask",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
    "opacitySchedule",
    "positionKeyframes",
    "scaleKeyframes",
    "driftKeyframes",
    "dissipationCurve",
    "algorithmIdentity",
    "algorithmVersion",
    "deterministicSeed",
    "blendMode",
    "layer",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
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
_MASK_FIELDS = {
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
_OUTPUT_FIELDS = {
    "width",
    "height",
    "frameCount",
    "frameRate",
    "pixelFormat",
    "container",
    "videoCodec",
}
_EFFECT_PREVIEW_FIELDS = {
    "schemaVersion",
    "executionRequestRef",
    "workspaceRef",
    "productionRunRef",
    "timelineVersionRef",
    "timelineVersionDigest",
    "inputBindingsDigest",
    "baseVideo",
    "effectStages",
    "glyphStage",
    "effectResultBindings",
    "glyphRequirementBinding",
    "effectBindingsDigest",
    "audioMix",
    "subtitleManifest",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
_EFFECT_RESULT_BINDING_FIELDS = {
    "clipRef",
    "clipDigest",
    "effectMode",
    "requirementRef",
    "requirementDigest",
    "resultRef",
    "resultDigest",
    "executionRequestRef",
    "executionRequestDigest",
    "artifactEvidenceRef",
    "artifactEvidenceDigest",
    "runtimeEvidenceRef",
    "runtimeEvidenceDigest",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
}
_GLYPH_BINDING_FIELDS = {"clipRef", "clipDigest", "requirementRef", "requirementDigest"}
_GLYPH_REQUEST_FIELDS = {
    "schemaVersion",
    "executionRequestRef",
    "workspaceRef",
    "productionRunRef",
    "requirementRef",
    "requirementDigest",
    "glyphSlug",
    "targetShotRef",
    "frameRangeStartInclusive",
    "frameRangeEndExclusive",
    "revealSchedule",
    "inputBindingsDigest",
    "basePlate",
    "masks",
    "basePlateInspectionRef",
    "basePlateInspectionDigest",
    "compositeParams",
    "output",
    "publicationAllowed",
    "payloadDigest",
}
_GLYPH_MASK_FIELDS = {
    "assetVersionRef",
    "assetVersionDigest",
    "storageKey",
    "fileDigest",
    "pixelDigest",
    "pixelDigestSpec",
    "pixelMode",
    "width",
    "height",
    "glyphSlug",
    "revealOrdinal",
    "assetRole",
    "glyphManifestDigest",
}


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError("masked-surface request is not canonical JSON") from exc


def _closed(value: object, fields: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderArtifactError(f"{label} fields are invalid")
    if not all(isinstance(key, str) for key in value):
        raise RenderArtifactError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _integer(
    value: object,
    *,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _reference(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _REF.fullmatch(value) is None
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _raw_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _RAW_DIGEST.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _prefixed_digest(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _PREFIXED_DIGEST.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _permille_point(value: object, *, label: str, minimum: int = 0) -> dict[str, int]:
    record = _closed(value, {"xPermille", "yPermille"}, label=label)
    return {
        "xPermille": _integer(
            record["xPermille"], label=f"{label}.xPermille", minimum=minimum, maximum=1000
        ),
        "yPermille": _integer(
            record["yPermille"], label=f"{label}.yPermille", minimum=minimum, maximum=1000
        ),
    }


def _validate_schedule(value: object, *, start: int, end: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise RenderArtifactError("masked-surface explicit schedule is invalid")
    result: list[dict[str, Any]] = []
    cursor = start
    any_enabled = False
    for index, item in enumerate(value):
        record = _closed(
            item,
            {"startFrameInclusive", "endFrameExclusive", "enabled", "interpolation"},
            label=f"masked-surface schedule {index}",
        )
        item_start = _integer(
            record["startFrameInclusive"],
            label=f"masked-surface schedule {index} start",
            minimum=0,
            maximum=10_000_000,
        )
        item_end = _integer(
            record["endFrameExclusive"],
            label=f"masked-surface schedule {index} end",
            minimum=1,
            maximum=10_000_001,
        )
        if (
            item_start != cursor
            or item_end <= item_start
            or item_end > end
            or not isinstance(record["enabled"], bool)
            or record["interpolation"] != "STEP"
        ):
            raise RenderArtifactError("masked-surface explicit schedule has overlap or gap")
        any_enabled = any_enabled or record["enabled"]
        result.append(record)
        cursor = item_end
    if cursor != end or not any_enabled:
        raise RenderArtifactError("masked-surface explicit schedule has overlap or gap")
    return result


def _validate_keyframes(
    value: object,
    *,
    start: int,
    end: int,
    kind: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise RenderArtifactError(f"masked-surface {kind} is invalid")
    if kind == "trajectory":
        fields = {"frame", "xPermille", "yPermille", "interpolation"}
    elif kind == "intensity curve":
        fields = {"frame", "valuePermille", "interpolation"}
    else:
        fields = {"frame", "valueMilliStops", "interpolation"}
    result: list[dict[str, Any]] = []
    previous = -1
    for index, item in enumerate(value):
        record = _closed(item, fields, label=f"masked-surface {kind} {index}")
        frame = _integer(
            record["frame"],
            label=f"masked-surface {kind} {index} frame",
            minimum=start,
            maximum=end - 1,
        )
        if frame <= previous or record["interpolation"] not in _INTERPOLATIONS:
            raise RenderArtifactError(f"masked-surface {kind} order is invalid")
        if kind == "trajectory":
            _integer(
                record["xPermille"],
                label=f"masked-surface {kind} {index} x",
                minimum=0,
                maximum=1000,
            )
            _integer(
                record["yPermille"],
                label=f"masked-surface {kind} {index} y",
                minimum=0,
                maximum=1000,
            )
        elif kind == "intensity curve":
            _integer(
                record["valuePermille"],
                label=f"masked-surface {kind} {index} value",
                minimum=0,
                maximum=1000,
            )
        else:
            _integer(
                record["valueMilliStops"],
                label=f"masked-surface {kind} {index} value",
                minimum=-8000,
                maximum=8000,
            )
        result.append(record)
        previous = frame
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise RenderArtifactError(f"masked-surface {kind} endpoints are invalid")
    return result


def _validate_e2_keyframes(
    value: object,
    *,
    fields: set[str],
    bounds: Mapping[str, tuple[int, int]],
    start: int,
    end: int,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 4_096:
        raise RenderArtifactError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    previous = -1
    for index, item in enumerate(value):
        record = _closed(item, fields, label=f"{label} {index}")
        frame = _integer(
            record["frame"],
            label=f"{label} {index} frame",
            minimum=start,
            maximum=end - 1,
        )
        if frame <= previous or record["interpolation"] not in _INTERPOLATIONS:
            raise RenderArtifactError(f"{label} order is invalid")
        for field, (minimum, maximum) in bounds.items():
            _integer(
                record[field],
                label=f"{label} {index} {field}",
                minimum=minimum,
                maximum=maximum,
            )
        result.append(record)
        previous = frame
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise RenderArtifactError(f"{label} endpoints are invalid")
    return result


def _validate_flame_state_schedule(
    value: object, *, start: int, end: int
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 5:
        raise RenderArtifactError("flame stateSchedule is invalid")
    result: list[dict[str, Any]] = []
    cursor = start
    for index, item in enumerate(value):
        record = _closed(
            item,
            {"state", "startFrameInclusive", "endFrameExclusive"},
            label=f"flame stateSchedule {index}",
        )
        item_start = _integer(
            record["startFrameInclusive"],
            label=f"flame stateSchedule {index} start",
            minimum=start,
            maximum=end - 1,
        )
        item_end = _integer(
            record["endFrameExclusive"],
            label=f"flame stateSchedule {index} end",
            minimum=start + 1,
            maximum=end,
        )
        if item_start != cursor or item_end <= item_start:
            raise RenderArtifactError("flame stateSchedule has overlap or gap")
        if not isinstance(record["state"], str):
            raise RenderArtifactError("flame stateSchedule state is invalid")
        result.append(record)
        cursor = item_end
    if cursor != end or tuple(item["state"] for item in result) not in _FLAME_STATE_PROFILES:
        raise RenderArtifactError("flame stateSchedule order is invalid")
    return result


def _validate_e2_base(value: object, *, label: str) -> dict[str, Any]:
    base = _closed(value, _BASE_FIELDS, label=label)
    _reference(base["assetVersionRef"], label=f"{label}.assetVersionRef")
    _raw_digest(base["assetVersionDigest"], label=f"{label}.assetVersionDigest")
    _prefixed_digest(base["fileDigest"], label=f"{label}.fileDigest")
    _prefixed_digest(base["pixelDigest"], label=f"{label}.pixelDigest")
    width = _integer(base["width"], label=f"{label}.width", minimum=2, maximum=16_384)
    height = _integer(base["height"], label=f"{label}.height", minimum=2, maximum=16_384)
    _integer(
        base["frameCount"],
        label=f"{label}.frameCount",
        minimum=1,
        maximum=10_000_000,
    )
    _integer(base["frameRate"], label=f"{label}.frameRate", minimum=1, maximum=240)
    if (
        base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or base["pixelFormat"] != "yuv420p"
        or width % 2
        or height % 2
    ):
        raise RenderArtifactError(f"{label} media contract is unsupported")
    return base


def _validate_e2_mask(value: object, *, label: str) -> dict[str, Any]:
    mask = _closed(value, _MASK_FIELDS, label=label)
    _reference(mask["assetVersionRef"], label=f"{label}.assetVersionRef")
    _raw_digest(mask["assetVersionDigest"], label=f"{label}.assetVersionDigest")
    _prefixed_digest(mask["fileDigest"], label=f"{label}.fileDigest")
    _prefixed_digest(mask["pixelDigest"], label=f"{label}.pixelDigest")
    _integer(mask["width"], label=f"{label}.width", minimum=1, maximum=16_384)
    _integer(mask["height"], label=f"{label}.height", minimum=1, maximum=16_384)
    if mask["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC or mask["pixelMode"] != "RGBA":
        raise RenderArtifactError(f"{label} pixel contract is unsupported")
    return mask


def _validate_e2_common(
    request: dict[str, Any], *, expected_mode: str
) -> tuple[dict[str, Any], dict[str, Any], int, int]:
    if (
        request["schemaVersion"] != FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION
        or request["effectMode"] != expected_mode
        or request["publicationAllowed"] is not False
    ):
        raise RenderArtifactError("flame/smoke execution boundary is invalid")
    expected_requirement_schema = (
        "v5.m13-flame-extinguish-requirement.v1"
        if expected_mode == "FLAME_EXTINGUISH"
        else "v5.m13-smoke-requirement.v1"
    )
    if request["requirementSchemaVersion"] != expected_requirement_schema:
        raise RenderArtifactError("flame/smoke Requirement schema is invalid")
    for field in (
        "v5ExecutionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _reference(request[field], label=field)
    for field in ("v5ExecutionRequestDigest", "requirementDigest", "payloadDigest"):
        _raw_digest(request[field], label=field)
    unsealed = deepcopy(request)
    claimed = unsealed.pop("payloadDigest")
    if claimed != sha256(_canonical_json(unsealed)).hexdigest():
        raise RenderArtifactError("flame/smoke request seal is invalid")
    shot = _closed(
        request["targetShot"],
        {"shotRef", "shotVersionRef", "shotVersionDigest"},
        label="flame/smoke targetShot",
    )
    _reference(shot["shotRef"], label="targetShot.shotRef")
    _reference(shot["shotVersionRef"], label="targetShot.shotVersionRef")
    _raw_digest(shot["shotVersionDigest"], label="targetShot.shotVersionDigest")
    base = _validate_e2_base(request["basePlate"], label="flame/smoke basePlate")
    start = _integer(
        request["frameRangeStartInclusive"],
        label="frameRangeStartInclusive",
        minimum=0,
        maximum=base["frameCount"] - 1,
    )
    end = _integer(
        request["frameRangeEndExclusive"],
        label="frameRangeEndExclusive",
        minimum=1,
        maximum=base["frameCount"],
    )
    if end <= start:
        raise RenderArtifactError("flame/smoke frame range is invalid")
    output = _closed(request["output"], _OUTPUT_FIELDS, label="flame/smoke output")
    if output != {
        "width": base["width"],
        "height": base["height"],
        "frameCount": base["frameCount"],
        "frameRate": base["frameRate"],
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }:
        raise RenderArtifactError("flame/smoke output does not match basePlate")
    if request["blendMode"] not in _BLEND_FILTERS:
        raise RenderArtifactError("flame/smoke blend mode is unsupported")
    _integer(request["layer"], label="flame/smoke layer", minimum=0, maximum=1024)
    request["targetShot"] = shot
    request["basePlate"] = base
    request["output"] = output
    return base, output, start, end


def _validate_flame_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _FLAME_REQUEST_FIELDS, label="flame request")
    base, _, start, end = _validate_e2_common(
        request, expected_mode="FLAME_EXTINGUISH"
    )
    flame_mask = _validate_e2_mask(request["flameMask"], label="flameMask")
    if flame_mask["assetVersionRef"] == base["assetVersionRef"]:
        raise RenderArtifactError("flameMask must be distinct from basePlate")
    states = _validate_flame_state_schedule(request["stateSchedule"], start=start, end=end)
    brightness = _validate_e2_keyframes(
        request["brightnessCurve"],
        fields={"frame", "valuePermille", "interpolation"},
        bounds={"valuePermille": (0, 1000)},
        start=start,
        end=end,
        label="flame brightnessCurve",
    )
    alpha = _validate_e2_keyframes(
        request["alphaCurve"],
        fields={"frame", "valuePermille", "interpolation"},
        bounds={"valuePermille": (0, 1000)},
        start=start,
        end=end,
        label="flame alphaCurve",
    )
    dark_start = next(
        item["startFrameInclusive"]
        for item in states
        if item["state"] == "DARK"
    )
    for label, curve in (("brightnessCurve", brightness), ("alphaCurve", alpha)):
        values = [item["valuePermille"] for item in curve]
        if (
            values[0] <= 0
            or any(left < right for left, right in zip(values, values[1:]))
            or not any(item["frame"] == dark_start for item in curve)
            or any(
                item["valuePermille"] != 0
                for item in curve
                if item["frame"] >= dark_start
            )
        ):
            raise RenderArtifactError(f"flame {label} extinction profile is invalid")
    for field in ("localExposureRequirementRef", "localExposureResultRef"):
        _reference(request[field], label=field)
    for field in ("localExposureRequirementDigest", "localExposureResultDigest"):
        _raw_digest(request[field], label=field)
    local = _validate_request(request["localExposureStage"])
    if (
        local["effectMode"] != "LOCAL_EXPOSURE"
        or local["workspaceRef"] != request["workspaceRef"]
        or local["productionRunRef"] != request["productionRunRef"]
        or local["requirementRef"] != request["localExposureRequirementRef"]
        or local["requirementDigest"] != request["localExposureRequirementDigest"]
        or local["targetShot"] != request["targetShot"]
        or local["basePlate"] != base
        or local["mask"] != flame_mask
        or local["frameRangeStartInclusive"] != start
        or local["frameRangeEndExclusive"] != end
        or local["exposureCurve"][-1]["valueMilliStops"] >= 0
    ):
        raise RenderArtifactError("flame LocalExposure stage is stale")
    request["flameMask"] = flame_mask
    request["stateSchedule"] = states
    request["brightnessCurve"] = brightness
    request["alphaCurve"] = alpha
    request["localExposureStage"] = local
    return request


def _validate_smoke_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _SMOKE_REQUEST_FIELDS, label="smoke request")
    base, _, start, end = _validate_e2_common(request, expected_mode="SMOKE")
    emission = _validate_e2_mask(request["emissionMask"], label="emissionMask")
    if emission["assetVersionRef"] == base["assetVersionRef"]:
        raise RenderArtifactError("emissionMask must be distinct from basePlate")
    source_kind = request["smokeSourceKind"]
    if source_kind not in _SMOKE_SOURCE_KINDS:
        raise RenderArtifactError("smoke source kind is unsupported")
    if source_kind == "PINNED_SMOKE_LAYER":
        layer = _validate_e2_mask(request["smokeLayer"], label="smokeLayer")
        if layer["assetVersionRef"] in {
            base["assetVersionRef"],
            emission["assetVersionRef"],
        }:
            raise RenderArtifactError("smoke AssetVersions must be distinct")
        if any(
            request[field] is not None
            for field in ("algorithmIdentity", "algorithmVersion", "deterministicSeed")
        ):
            raise RenderArtifactError("pinned smoke cannot declare a procedural algorithm")
    else:
        layer = None
        if (
            request["smokeLayer"] is not None
            or request["algorithmIdentity"] != _SMOKE_ALGORITHM_IDENTITY
            or request["algorithmVersion"] != _SMOKE_ALGORITHM_VERSION
        ):
            raise RenderArtifactError("procedural smoke algorithm is not frozen")
        _integer(
            request["deterministicSeed"],
            label="deterministicSeed",
            minimum=0,
            maximum=(1 << 63) - 1,
        )
    opacity = _validate_e2_keyframes(
        request["opacitySchedule"],
        fields={"frame", "valuePermille", "interpolation"},
        bounds={"valuePermille": (0, 1000)},
        start=start,
        end=end,
        label="smoke opacitySchedule",
    )
    position = _validate_e2_keyframes(
        request["positionKeyframes"],
        fields={"frame", "xPermille", "yPermille", "interpolation"},
        bounds={"xPermille": (0, 1000), "yPermille": (0, 1000)},
        start=start,
        end=end,
        label="smoke positionKeyframes",
    )
    scale = _validate_e2_keyframes(
        request["scaleKeyframes"],
        fields={"frame", "xPermille", "yPermille", "interpolation"},
        bounds={"xPermille": (1, 4000), "yPermille": (1, 4000)},
        start=start,
        end=end,
        label="smoke scaleKeyframes",
    )
    drift = _validate_e2_keyframes(
        request["driftKeyframes"],
        fields={"frame", "xDeltaPermille", "yDeltaPermille", "interpolation"},
        bounds={"xDeltaPermille": (-4000, 4000), "yDeltaPermille": (-4000, 4000)},
        start=start,
        end=end,
        label="smoke driftKeyframes",
    )
    dissipation = _validate_e2_keyframes(
        request["dissipationCurve"],
        fields={"frame", "valuePermille", "interpolation"},
        bounds={"valuePermille": (0, 1000)},
        start=start,
        end=end,
        label="smoke dissipationCurve",
    )
    request["smokeLayer"] = layer
    request["emissionMask"] = emission
    request["opacitySchedule"] = opacity
    request["positionKeyframes"] = position
    request["scaleKeyframes"] = scale
    request["driftKeyframes"] = drift
    request["dissipationCurve"] = dissipation
    return request


def _validate_effect_request(value: Mapping[str, Any]) -> dict[str, Any]:
    schema = value.get("schemaVersion") if isinstance(value, Mapping) else None
    if schema == MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION:
        return _validate_request(value)
    if schema == FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION:
        mode = value.get("effectMode")
        if mode == "FLAME_EXTINGUISH":
            return _validate_flame_request(value)
        if mode == "SMOKE":
            return _validate_smoke_request(value)
    raise RenderArtifactError("deterministic effect request schema is unsupported")


def _validate_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _REQUEST_FIELDS, label="masked-surface request")
    if request["schemaVersion"] != MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION:
        raise RenderArtifactError("masked-surface request schema is unsupported")
    for field in (
        "v5ExecutionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _reference(request[field], label=field)
    for field in ("v5ExecutionRequestDigest", "requirementDigest", "payloadDigest"):
        _raw_digest(request[field], label=field)
    effect_mode = request["effectMode"]
    if effect_mode not in _E1_EFFECT_MODES:
        raise RenderArtifactError("masked-surface effect mode is unsupported")
    expected_schema = (
        "v5.m13-local-exposure-requirement.v1"
        if effect_mode == "LOCAL_EXPOSURE"
        else "v5.m13-scratch-light-requirement.v1"
    )
    if request["requirementSchemaVersion"] != expected_schema:
        raise RenderArtifactError("masked-surface requirement schema does not match mode")
    if request["publicationAllowed"] is not False:
        raise RenderArtifactError("masked-surface publication is forbidden")

    unsealed = deepcopy(request)
    supplied_payload_digest = unsealed.pop("payloadDigest")
    actual_payload_digest = sha256(_canonical_json(unsealed)).hexdigest()
    if supplied_payload_digest != actual_payload_digest:
        raise RenderArtifactError("masked-surface request seal is invalid")

    shot = _closed(
        request["targetShot"],
        {"shotRef", "shotVersionRef", "shotVersionDigest"},
        label="masked-surface target shot",
    )
    _reference(shot["shotRef"], label="targetShot.shotRef")
    _reference(shot["shotVersionRef"], label="targetShot.shotVersionRef")
    _raw_digest(shot["shotVersionDigest"], label="targetShot.shotVersionDigest")

    base = _closed(request["basePlate"], _BASE_FIELDS, label="masked-surface base plate")
    mask = _closed(request["mask"], _MASK_FIELDS, label="masked-surface mask")
    for label, binding in (("basePlate", base), ("mask", mask)):
        _reference(binding["assetVersionRef"], label=f"{label}.assetVersionRef")
        _raw_digest(binding["assetVersionDigest"], label=f"{label}.assetVersionDigest")
        _prefixed_digest(binding["fileDigest"], label=f"{label}.fileDigest")
        _prefixed_digest(binding["pixelDigest"], label=f"{label}.pixelDigest")
    if base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2:
        raise RenderArtifactError("masked-surface base pixel digest spec is unsupported")
    if mask["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC or mask["pixelMode"] != "RGBA":
        raise RenderArtifactError("masked-surface mask pixel contract is invalid")

    width = _integer(base["width"], label="basePlate.width", minimum=2, maximum=16_384)
    height = _integer(base["height"], label="basePlate.height", minimum=2, maximum=16_384)
    frame_count = _integer(
        base["frameCount"], label="basePlate.frameCount", minimum=1, maximum=10_000_000
    )
    frame_rate = _integer(base["frameRate"], label="basePlate.frameRate", minimum=1, maximum=240)
    if base["pixelFormat"] != "yuv420p" or width % 2 or height % 2:
        raise RenderArtifactError("masked-surface base pixel format is unsupported")
    _integer(mask["width"], label="mask.width", minimum=1, maximum=16_384)
    _integer(mask["height"], label="mask.height", minimum=1, maximum=16_384)

    output = _closed(request["output"], _OUTPUT_FIELDS, label="masked-surface output")
    if output != {
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "frameRate": frame_rate,
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }:
        raise RenderArtifactError("masked-surface output contract does not match base plate")

    start = _integer(
        request["frameRangeStartInclusive"],
        label="frameRangeStartInclusive",
        minimum=0,
        maximum=frame_count - 1,
    )
    end = _integer(
        request["frameRangeEndExclusive"],
        label="frameRangeEndExclusive",
        minimum=1,
        maximum=frame_count,
    )
    if end <= start:
        raise RenderArtifactError("masked-surface frame range is invalid")
    schedule = _validate_schedule(request["explicitSchedule"], start=start, end=end)
    trajectory = _validate_keyframes(
        request["trajectoryKeyframes"], start=start, end=end, kind="trajectory"
    )
    intensity = _validate_keyframes(
        request["intensityCurve"], start=start, end=end, kind="intensity curve"
    )
    exposure = _validate_keyframes(
        request["exposureCurve"], start=start, end=end, kind="exposure curve"
    )
    position = _permille_point(request["position"], label="masked-surface position")
    scale = _permille_point(request["scale"], label="masked-surface scale", minimum=1)
    if trajectory[0]["xPermille"] != position["xPermille"] or trajectory[0]["yPermille"] != position["yPermille"]:
        raise RenderArtifactError("masked-surface position does not match trajectory")
    if any(
        item["xPermille"] + scale["xPermille"] > 1000
        or item["yPermille"] + scale["yPermille"] > 1000
        for item in trajectory
    ):
        raise RenderArtifactError("masked-surface trajectory exceeds output canvas")

    perspective = _closed(
        request["perspective"], {"mode", "quadPermille"}, label="masked-surface perspective"
    )
    quad = perspective["quadPermille"]
    if perspective["mode"] == "NONE":
        if quad != []:
            raise RenderArtifactError("masked-surface NONE perspective is invalid")
    elif perspective["mode"] == "FIXED_QUAD":
        if not isinstance(quad, list) or len(quad) != 4:
            raise RenderArtifactError("masked-surface fixed perspective is invalid")
        points = [
            _permille_point(item, label=f"masked-surface perspective point {index}")
            for index, item in enumerate(quad)
        ]
        if not (
            points[0]["xPermille"] < points[1]["xPermille"]
            and points[2]["xPermille"] < points[3]["xPermille"]
            and points[0]["yPermille"] < points[2]["yPermille"]
            and points[1]["yPermille"] < points[3]["yPermille"]
        ):
            raise RenderArtifactError("masked-surface fixed perspective is ambiguous")
    else:
        raise RenderArtifactError("masked-surface perspective mode is unsupported")
    if request["blendMode"] not in _BLEND_FILTERS:
        raise RenderArtifactError("masked-surface blend mode is unsupported")
    _integer(request["layer"], label="masked-surface layer", minimum=0, maximum=1024)

    request["targetShot"] = shot
    request["basePlate"] = base
    request["mask"] = mask
    request["output"] = output
    request["explicitSchedule"] = schedule
    request["trajectoryKeyframes"] = trajectory
    request["intensityCurve"] = intensity
    request["exposureCurve"] = exposure
    request["position"] = position
    request["scale"] = scale
    request["perspective"] = perspective
    return request


def _validate_glyph_request(
    value: object,
    *,
    workspace_ref: str,
    run_ref: str,
    base_video: Mapping[str, Any],
    glyph_binding: Mapping[str, Any],
) -> dict[str, Any]:
    glyph = _closed(value, _GLYPH_REQUEST_FIELDS, label="effect preview glyph request")
    claimed = _raw_digest(glyph["payloadDigest"], label="glyphRevealRequest.payloadDigest")
    unsealed = deepcopy(glyph)
    unsealed.pop("payloadDigest")
    if claimed != sha256(_canonical_json(unsealed)).hexdigest():
        raise RenderArtifactError("effect preview glyph request seal is invalid")
    if (
        glyph["schemaVersion"] != "v5.m13-glyph-reveal-execution-request.v2"
        or glyph["workspaceRef"] != workspace_ref
        or glyph["productionRunRef"] != run_ref
        or glyph["publicationAllowed"] is not False
        or glyph["requirementRef"] != glyph_binding["requirementRef"]
        or glyph["requirementDigest"] != glyph_binding["requirementDigest"]
    ):
        raise RenderArtifactError("effect preview glyph lineage is invalid")
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
        "basePlateInspectionRef",
    ):
        _reference(glyph[field], label=f"glyphRevealRequest.{field}")
    for field in (
        "requirementDigest",
        "inputBindingsDigest",
        "basePlateInspectionDigest",
    ):
        _raw_digest(glyph[field], label=f"glyphRevealRequest.{field}")
    base = _closed(
        glyph["basePlate"],
        {"assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest"},
        label="effect preview glyph base plate",
    )
    if base != {field: base_video[field] for field in base}:
        raise RenderArtifactError("effect preview glyph base plate is not the original base")
    start = _integer(
        glyph["frameRangeStartInclusive"],
        label="glyphRevealRequest.frameRangeStartInclusive",
        minimum=0,
        maximum=10_000_000,
    )
    end = _integer(
        glyph["frameRangeEndExclusive"],
        label="glyphRevealRequest.frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start or end > base_video["frameCount"]:
        raise RenderArtifactError("effect preview glyph frame range is invalid")
    output = _closed(
        glyph["output"],
        {"width", "height", "frameRate", "totalFrames"},
        label="effect preview glyph output",
    )
    if output != {
        "width": base_video["width"],
        "height": base_video["height"],
        "frameRate": base_video["frameRate"],
        "totalFrames": base_video["frameCount"],
    }:
        raise RenderArtifactError("effect preview glyph output does not match base")
    masks = glyph["masks"]
    if not isinstance(masks, list) or not masks or len(masks) > 1024:
        raise RenderArtifactError("effect preview glyph masks are invalid")
    normalized_masks: list[dict[str, Any]] = []
    for index, item in enumerate(masks):
        mask = _closed(item, _GLYPH_MASK_FIELDS, label=f"effect preview glyph mask {index}")
        _reference(mask["assetVersionRef"], label=f"glyph mask {index} assetVersionRef")
        _raw_digest(mask["assetVersionDigest"], label=f"glyph mask {index} assetVersionDigest")
        _prefixed_digest(mask["fileDigest"], label=f"glyph mask {index} fileDigest")
        _prefixed_digest(mask["pixelDigest"], label=f"glyph mask {index} pixelDigest")
        _prefixed_digest(mask["glyphManifestDigest"], label=f"glyph mask {index} manifest")
        if (
            mask["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC
            or mask["pixelMode"] != "RGBA"
            or mask["glyphSlug"] != glyph["glyphSlug"]
            or mask["revealOrdinal"] != index + 1
            or mask["assetRole"] != "GLYPH_REVEAL_CUMULATIVE_MASK"
        ):
            raise RenderArtifactError("effect preview glyph mask contract is invalid")
        _integer(mask["width"], label=f"glyph mask {index} width", minimum=1, maximum=16_384)
        _integer(mask["height"], label=f"glyph mask {index} height", minimum=1, maximum=16_384)
        normalized_masks.append(mask)
    _explicit_stage_ranges_v2(
        glyph["revealSchedule"],
        masks=normalized_masks,
        frame_range_start=start,
        frame_range_end=end,
    )
    _validate_composite_params(
        glyph["compositeParams"],
        canvas_width=base_video["width"],
        canvas_height=base_video["height"],
    )
    glyph["masks"] = normalized_masks
    glyph["basePlate"] = base
    glyph["output"] = output
    return glyph


def _validate_effect_preview_request(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _EFFECT_PREVIEW_FIELDS, label="effect preview request")
    claimed = _raw_digest(request["payloadDigest"], label="effect preview payloadDigest")
    unsealed = deepcopy(request)
    unsealed.pop("payloadDigest")
    if claimed != sha256(_canonical_json(unsealed)).hexdigest():
        raise RenderArtifactError("effect preview request seal is invalid")
    schema = request["schemaVersion"]
    if schema == EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION:
        expected_stage_count = 2
        bindings_schema = "v5.m13-effect-preview-bindings.v1"
    elif schema == EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V3:
        expected_stage_count = 4
        bindings_schema = "v5.m13-effect-preview-bindings.v2"
    elif schema == EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4:
        expected_stage_count = 6
        bindings_schema = "v5.m13-effect-preview-bindings.v3"
    elif schema == EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V5:
        expected_stage_count = 7
        bindings_schema = "v5.m13-effect-preview-bindings.v4"
    else:
        raise RenderArtifactError("effect preview execution schema is unsupported")
    if request["publicationAllowed"] is not False:
        raise RenderArtifactError("effect preview execution boundary is invalid")
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
    ):
        _reference(request[field], label=field)
    for field in (
        "timelineVersionDigest",
        "inputBindingsDigest",
        "effectBindingsDigest",
    ):
        _raw_digest(request[field], label=field)
    base = _closed(request["baseVideo"], _BASE_FIELDS, label="effect preview base video")
    stages = request["effectStages"]
    if not isinstance(stages, list) or len(stages) != expected_stage_count:
        raise RenderArtifactError("effect preview stage profile is invalid")
    normalized_stages = []
    for index, stage in enumerate(stages):
        if index < 4:
            normalized_stages.append(_validate_effect_request(stage))
        elif index < 6:
            from .deterministic_overlays import validate_overlay_preview_stage

            normalized_stages.append(validate_overlay_preview_stage(stage))
        else:
            from .distance_state import validate_distance_state_preview_stage

            normalized_stages.append(validate_distance_state_preview_stage(stage))
    expected_modes = [
        normalized_stages[0]["effectMode"],
        "LOCAL_EXPOSURE",
        *(
            ["FLAME_EXTINGUISH", "SMOKE"]
            if expected_stage_count == 4
            else [
                "FLAME_EXTINGUISH",
                "SMOKE",
                "NAMEPLATE_TEXT",
                "FACE_MARK_COMPENSATION",
            ]
            if expected_stage_count in {6, 7}
            else []
        ),
        *(
            ["DISTANCE_STATE_TRANSITION"]
            if expected_stage_count == 7
            else []
        ),
    ]
    if (
        normalized_stages[0]["effectMode"]
        not in {"SCRATCH_REVEAL", "LIGHT_SWEEP"}
        or [stage["effectMode"] for stage in normalized_stages]
        != expected_modes
    ):
        raise RenderArtifactError("effect preview stages are not in fixed order")
    if (
        expected_stage_count in {4, 6, 7}
        and normalized_stages[2]["localExposureStage"]
        != normalized_stages[1]
    ):
        raise RenderArtifactError(
            "effect preview Flame does not bind the exact LocalExposure stage"
        )
    for stage in normalized_stages:
        if (
            stage["workspaceRef"] != request["workspaceRef"]
            or stage["productionRunRef"] != request["productionRunRef"]
            or stage["basePlate"] != base
        ):
            raise RenderArtifactError("effect preview stage base lineage is invalid")

    bindings_value = request["effectResultBindings"]
    if (
        not isinstance(bindings_value, list)
        or len(bindings_value) != expected_stage_count
    ):
        raise RenderArtifactError("effect preview result bindings are invalid")
    bindings: list[dict[str, Any]] = []
    for index, (item, stage) in enumerate(zip(bindings_value, normalized_stages, strict=True)):
        stage_semantics = (
            stage["overlaySpec"]
            if stage["effectMode"]
            in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}
            else stage
        )
        binding = _closed(
            item,
            _EFFECT_RESULT_BINDING_FIELDS,
            label=f"effect preview result binding {index}",
        )
        for field in (
            "clipRef",
            "requirementRef",
            "resultRef",
            "executionRequestRef",
            "artifactEvidenceRef",
            "runtimeEvidenceRef",
        ):
            _reference(binding[field], label=f"effectResultBindings[{index}].{field}")
        for field in (
            "clipDigest",
            "requirementDigest",
            "resultDigest",
            "executionRequestDigest",
            "artifactEvidenceDigest",
            "runtimeEvidenceDigest",
        ):
            _raw_digest(binding[field], label=f"effectResultBindings[{index}].{field}")
        if (
            binding["effectMode"] != stage["effectMode"]
            or binding["requirementRef"] != stage["requirementRef"]
            or binding["requirementDigest"] != stage["requirementDigest"]
            or binding["executionRequestRef"] != stage["v5ExecutionRequestRef"]
            or binding["executionRequestDigest"] != stage["v5ExecutionRequestDigest"]
            or binding["frameRangeStartInclusive"]
            != stage_semantics["frameRangeStartInclusive"]
            or binding["frameRangeEndExclusive"]
            != stage_semantics["frameRangeEndExclusive"]
        ):
            raise RenderArtifactError("effect preview result binding is stale")
        bindings.append(binding)
    glyph_binding = _closed(
        request["glyphRequirementBinding"],
        _GLYPH_BINDING_FIELDS,
        label="effect preview glyph binding",
    )
    for field in ("clipRef", "requirementRef"):
        _reference(glyph_binding[field], label=f"glyphRequirementBinding.{field}")
    for field in ("clipDigest", "requirementDigest"):
        _raw_digest(glyph_binding[field], label=f"glyphRequirementBinding.{field}")
    expected_effect_digest = sha256(
        _canonical_json(
            {
                "schemaVersion": bindings_schema,
                "effectResultBindings": bindings,
                "glyphRequirementBinding": glyph_binding,
            }
        )
    ).hexdigest()
    if request["effectBindingsDigest"] != expected_effect_digest:
        raise RenderArtifactError("effect preview bindings digest is invalid")
    glyph = _validate_glyph_request(
        request["glyphStage"],
        workspace_ref=request["workspaceRef"],
        run_ref=request["productionRunRef"],
        base_video=base,
        glyph_binding=glyph_binding,
    )
    expected_input_digest = sha256(
        _canonical_json(
            {
                "baseVideo": base,
                (
                    "deterministicEffectRequestDigests"
                    if expected_stage_count in {6, 7}
                    else "maskedSurfaceRequestDigests"
                ): [stage["payloadDigest"] for stage in normalized_stages],
                "glyphRevealRequestDigest": glyph["payloadDigest"],
                "effectResultBindings": bindings,
                "glyphRequirementBinding": glyph_binding,
                "audioMix": request["audioMix"],
                "subtitleManifest": request["subtitleManifest"],
            }
        )
    ).hexdigest()
    if request["inputBindingsDigest"] != expected_input_digest:
        raise RenderArtifactError("effect preview input bindings digest is invalid")
    output_contract_digest = sha256(_canonical_json(request["output"])).hexdigest()
    expected_ref = "m13-effect-preview-execution-" + sha256(
        _canonical_json(
            {
                "timelineVersionRef": request["timelineVersionRef"],
                "timelineVersionDigest": request["timelineVersionDigest"],
                "inputBindingsDigest": request["inputBindingsDigest"],
                "effectBindingsDigest": request["effectBindingsDigest"],
                "outputContractDigest": output_contract_digest,
            }
        )
    ).hexdigest()[:32]
    if request["executionRequestRef"] != expected_ref:
        raise RenderArtifactError("effect preview execution request ref is invalid")
    request["baseVideo"] = base
    request["effectStages"] = normalized_stages
    request["effectResultBindings"] = bindings
    request["glyphRequirementBinding"] = glyph_binding
    request["glyphStage"] = glyph
    return request


def _curve_expression(
    records: Sequence[Mapping[str, Any]],
    value_field: str,
    *,
    frame_variable: str = "N",
) -> str:
    expression = str(records[-1][value_field])
    for index in range(len(records) - 2, -1, -1):
        current = records[index]
        following = records[index + 1]
        start = current["frame"]
        end = following["frame"]
        start_value = current[value_field]
        delta = following[value_field] - start_value
        interpolation = current["interpolation"]
        ratio = f"(({frame_variable}-{start})/{end - start})"
        if interpolation == "STEP":
            segment = str(start_value)
        elif interpolation == "LINEAR":
            segment = f"({start_value}+({delta}*{ratio}))"
        elif interpolation == "EASE_IN":
            segment = f"({start_value}+({delta}*{ratio}*{ratio}))"
        elif interpolation == "EASE_OUT":
            segment = f"({start_value}+({delta}*(1-(1-{ratio})*(1-{ratio}))))"
        else:
            segment = f"({start_value}+({delta}*{ratio}*{ratio}*(3-2*{ratio})))"
        expression = f"if(lt({frame_variable},{end}),{segment},{expression})"
    return expression


def _schedule_expression(records: Sequence[Mapping[str, Any]], *, start: int, end: int) -> str:
    expression = "0"
    for record in reversed(records):
        enabled = "1" if record["enabled"] else "0"
        expression = (
            f"if(between(N,{record['startFrameInclusive']},"
            f"{record['endFrameExclusive'] - 1}),{enabled},{expression})"
        )
    return f"if(between(N,{start},{end - 1}),{expression},0)"


def _scaled_dimension(dimension: int, permille: int) -> int:
    return max(1, dimension * permille // 1000)


def _effect_stage_filters(
    request: Mapping[str, Any],
    *,
    input_label: str,
    mask_input_index: int,
    prefix: str,
) -> tuple[list[str], str]:
    output = request["output"]
    width = output["width"]
    height = output["height"]
    frame_rate = output["frameRate"]
    scale_width = _scaled_dimension(width, request["scale"]["xPermille"])
    scale_height = _scaled_dimension(height, request["scale"]["yPermille"])
    x_records = [
        {**item, "pixel": width * item["xPermille"] // 1000}
        for item in request["trajectoryKeyframes"]
    ]
    y_records = [
        {**item, "pixel": height * item["yPermille"] // 1000}
        for item in request["trajectoryKeyframes"]
    ]
    x_expression = _curve_expression(x_records, "pixel", frame_variable="n")
    y_expression = _curve_expression(y_records, "pixel", frame_variable="n")
    intensity_expression = _curve_expression(request["intensityCurve"], "valuePermille")
    exposure_expression = _curve_expression(request["exposureCurve"], "valueMilliStops")
    schedule_expression = _schedule_expression(
        request["explicitSchedule"],
        start=request["frameRangeStartInclusive"],
        end=request["frameRangeEndExclusive"],
    )

    mask_filters = (
        f"[{mask_input_index}:v]settb=expr=1/{frame_rate},setpts=N,format=gray,"
        f"scale={scale_width}:{scale_height}:flags=neighbor:in_range=full:out_range=full"
    )
    if request["perspective"]["mode"] == "FIXED_QUAD":
        coordinates: list[int] = []
        for point in request["perspective"]["quadPermille"]:
            coordinates.extend(
                (
                    (scale_width - 1) * point["xPermille"] // 1000,
                    (scale_height - 1) * point["yPermille"] // 1000,
                )
            )
        mask_filters += ",perspective=" + ":".join(
            [
                f"x0={coordinates[0]}",
                f"y0={coordinates[1]}",
                f"x1={coordinates[2]}",
                f"y1={coordinates[3]}",
                f"x2={coordinates[4]}",
                f"y2={coordinates[5]}",
                f"x3={coordinates[6]}",
                f"y3={coordinates[7]}",
                "sense=destination",
                "interpolation=linear",
                "eval=init",
            ]
        )
    mask_filters += f"[{prefix}maskgray]"
    filters = [mask_filters]
    filters.extend(
        [
            f"color=c=white@1:s={scale_width}x{scale_height}:r={frame_rate},format=rgba[{prefix}white]",
            f"[{prefix}white][{prefix}maskgray]alphamerge[{prefix}masklocal]",
            f"color=c=black@0:s={width}x{height}:r={frame_rate},format=rgba[{prefix}canvas]",
            (
                f"[{prefix}canvas][{prefix}masklocal]overlay=x='{x_expression}':y='{y_expression}':"
                f"eval=frame:eof_action=repeat:shortest=0:format=auto[{prefix}maskcanvas]"
            ),
            (
                f"[{prefix}maskcanvas]alphaextract,"
                f"geq=lum='clip(lum(X,Y)*({schedule_expression})*"
                f"({intensity_expression})/1000,0,255)'[{prefix}effectmask]"
            ),
        ]
    )
    blend_mode = request["blendMode"]
    if blend_mode == "NORMAL":
        filters.extend(
            [
                f"[{input_label}]settb=expr=1/{frame_rate},setpts=N,format=gbrp,split=2[{prefix}baseout][{prefix}exposuresrc]",
                (
                    f"[{prefix}exposuresrc]geq="
                    f"r='clip(r(X,Y)*pow(2,({exposure_expression})/1000),0,255)':"
                    f"g='clip(g(X,Y)*pow(2,({exposure_expression})/1000),0,255)':"
                    f"b='clip(b(X,Y)*pow(2,({exposure_expression})/1000),0,255)'[{prefix}effect]"
                ),
            ]
        )
    else:
        filters.extend(
            [
                f"[{input_label}]settb=expr=1/{frame_rate},setpts=N,format=gbrp,split=3[{prefix}baseout][{prefix}blendbase][{prefix}exposuresrc]",
                (
                    f"[{prefix}exposuresrc]geq="
                    f"r='clip(r(X,Y)*pow(2,({exposure_expression})/1000),0,255)':"
                    f"g='clip(g(X,Y)*pow(2,({exposure_expression})/1000),0,255)':"
                    f"b='clip(b(X,Y)*pow(2,({exposure_expression})/1000),0,255)'[{prefix}exposed]"
                ),
                f"[{prefix}blendbase][{prefix}exposed]blend=all_mode={_BLEND_FILTERS[blend_mode]}[{prefix}effect]",
            ]
        )
    output_label = f"{prefix}out"
    filters.append(
        f"[{prefix}baseout][{prefix}effect][{prefix}effectmask]"
        f"maskedmerge,format=yuv420p[{output_label}]"
    )
    return filters, output_label


def _filter_graph(request: Mapping[str, Any]) -> str:
    filters, output_label = _effect_stage_filters(
        request,
        input_label="0:v",
        mask_input_index=1,
        prefix="effect0",
    )
    filters.append(f"[{output_label}]null[vout]")
    return ";".join(filters)


def _state_expression(
    records: Sequence[Mapping[str, Any]], state: str, *, frame_variable: str = "N"
) -> str:
    parts = [
        (
            f"between({frame_variable},{record['startFrameInclusive']},"
            f"{record['endFrameExclusive'] - 1})"
        )
        for record in records
        if record["state"] == state
    ]
    return "+".join(parts) if parts else "0"


def _fixed_masked_composite_filters(
    *,
    input_label: str,
    effect_label: str,
    mask_label: str,
    blend_mode: str,
    frame_rate: int,
    prefix: str,
) -> tuple[list[str], str]:
    filters: list[str] = []
    if blend_mode == "NORMAL":
        filters.append(
            f"[{input_label}]settb=expr=1/{frame_rate},setpts=N,"
            f"format=gbrp[{prefix}baseout]"
        )
        selected_effect = effect_label
    else:
        filters.extend(
            [
                (
                    f"[{input_label}]settb=expr=1/{frame_rate},setpts=N,"
                    f"format=gbrp,split=2[{prefix}baseout][{prefix}blendbase]"
                ),
                (
                    f"[{prefix}blendbase][{effect_label}]"
                    f"blend=all_mode={_BLEND_FILTERS[blend_mode]}[{prefix}blended]"
                ),
            ]
        )
        selected_effect = f"{prefix}blended"
    output_label = f"{prefix}out"
    filters.append(
        f"[{prefix}baseout][{selected_effect}][{mask_label}]"
        f"maskedmerge,format=yuv420p[{output_label}]"
    )
    return filters, output_label


def _flame_stage_filters(
    request: Mapping[str, Any],
    *,
    input_label: str,
    mask_input_index: int,
    prefix: str,
) -> tuple[list[str], str]:
    output = request["output"]
    width = output["width"]
    height = output["height"]
    frame_rate = output["frameRate"]
    brightness = _curve_expression(request["brightnessCurve"], "valuePermille")
    alpha = _curve_expression(request["alphaCurve"], "valuePermille")
    ember = _state_expression(request["stateSchedule"], "EMBER")
    in_range = (
        f"between(N,{request['frameRangeStartInclusive']},"
        f"{request['frameRangeEndExclusive'] - 1})"
    )
    filters = [
        (
            f"[{mask_input_index}:v]settb=expr=1/{frame_rate},setpts=N,"
            f"format=gray,scale={width}:{height}:flags=neighbor:"
            f"in_range=full:out_range=full,"
            f"geq=lum='clip(lum(X,Y)*({in_range})*(1000-({alpha}))/1000,0,255)'"
            f"[{prefix}mask]"
        ),
        (
            f"[{input_label}]settb=expr=1/{frame_rate},setpts=N,format=gbrp,"
            f"split=2[{prefix}base][{prefix}source]"
        ),
        (
            f"[{prefix}source]geq="
            f"r='clip(r(X,Y)*({brightness})/1000+255*({ember})*({alpha})/1000,0,255)':"
            f"g='clip(g(X,Y)*({brightness})/1000+72*({ember})*({alpha})/1000,0,255)':"
            f"b='clip(b(X,Y)*({brightness})/1000+8*({ember})*({alpha})/1000,0,255)'"
            f"[{prefix}effect]"
        ),
    ]
    composite, output_label = _fixed_masked_composite_filters(
        input_label=f"{prefix}base",
        effect_label=f"{prefix}effect",
        mask_label=f"{prefix}mask",
        blend_mode=request["blendMode"],
        frame_rate=frame_rate,
        prefix=prefix,
    )
    filters.extend(composite)
    return filters, output_label


def _smoke_stage_filters(
    request: Mapping[str, Any],
    *,
    input_label: str,
    smoke_input_index: int,
    emission_input_index: int,
    prefix: str,
) -> tuple[list[str], str]:
    output = request["output"]
    width = output["width"]
    height = output["height"]
    frame_rate = output["frameRate"]
    opacity = _curve_expression(request["opacitySchedule"], "valuePermille")
    dissipation = _curve_expression(
        request["dissipationCurve"], "valuePermille"
    )
    position_x = _curve_expression(
        request["positionKeyframes"], "xPermille", frame_variable="n"
    )
    position_y = _curve_expression(
        request["positionKeyframes"], "yPermille", frame_variable="n"
    )
    drift_x = _curve_expression(
        request["driftKeyframes"], "xDeltaPermille", frame_variable="n"
    )
    drift_y = _curve_expression(
        request["driftKeyframes"], "yDeltaPermille", frame_variable="n"
    )
    scale_x = _curve_expression(
        request["scaleKeyframes"], "xPermille", frame_variable="n"
    )
    scale_y = _curve_expression(
        request["scaleKeyframes"], "yPermille", frame_variable="n"
    )
    scale_width = f"max(1,trunc({width}*({scale_x})/1000))"
    scale_height = f"max(1,trunc({height}*({scale_y})/1000))"
    x_expression = f"trunc({width}*(({position_x})+({drift_x}))/1000)"
    y_expression = f"trunc({height}*(({position_y})+({drift_y}))/1000)"
    active = (
        f"between(N,{request['frameRangeStartInclusive']},"
        f"{request['frameRangeEndExclusive'] - 1})"
    )
    filters = [
        (
            f"[{smoke_input_index}:v]settb=expr=1/{frame_rate},setpts=N,format=gray,"
            f"scale={_PROCEDURAL_SMOKE_TILE_WIDTH}:{_PROCEDURAL_SMOKE_TILE_HEIGHT}:"
            f"flags=bilinear:eval=init,"
            f"split=2[{prefix}texture][{prefix}density]"
        ),
        (
            f"[{emission_input_index}:v]settb=expr=1/{frame_rate},setpts=N,format=gray,"
            f"scale={_PROCEDURAL_SMOKE_TILE_WIDTH}:{_PROCEDURAL_SMOKE_TILE_HEIGHT}:"
            f"flags=bilinear:eval=init"
            f"[{prefix}emission]"
        ),
        (
            f"[{prefix}density][{prefix}emission]blend=all_mode=multiply,"
            f"geq=lum='clip(lum(X,Y)*({active})*({opacity})*"
            f"(1000-({dissipation}))/1000000,0,255)'[{prefix}alpha]"
        ),
        (
            f"[{prefix}texture]geq=lum='clip(64+lum(X,Y)*3/4,0,255)',"
            f"format=rgb24[{prefix}rgb]"
        ),
        (
            f"color=c=black:s={_PROCEDURAL_SMOKE_TILE_WIDTH}x"
            f"{_PROCEDURAL_SMOKE_TILE_HEIGHT}:r={frame_rate},"
            f"format=rgb24[{prefix}localblack]"
        ),
        (
            f"[{prefix}localblack][{prefix}rgb][{prefix}alpha]"
            f"maskedmerge[{prefix}local0]"
        ),
        (
            f"[{prefix}local0]scale=w='{scale_width}':h='{scale_height}':"
            f"flags=bilinear:eval=frame[{prefix}local]"
        ),
        (
            f"color=c=black:s={width}x{height}:r={frame_rate},"
            f"format=rgb24[{prefix}canvas]"
        ),
        (
            f"[{prefix}canvas][{prefix}local]overlay=x='{x_expression}':y='{y_expression}':"
            f"eval=frame:eof_action=repeat:shortest=0:format=auto[{prefix}placed]"
        ),
        f"[{prefix}placed]split=2[{prefix}placedrgb][{prefix}placedalpha]",
        f"[{prefix}placedrgb]format=gbrp[{prefix}effect]",
        f"[{prefix}placedalpha]format=gray[{prefix}mask]",
    ]
    composite, output_label = _fixed_masked_composite_filters(
        input_label=input_label,
        effect_label=f"{prefix}effect",
        mask_label=f"{prefix}mask",
        blend_mode=request["blendMode"],
        frame_rate=frame_rate,
        prefix=prefix,
    )
    filters.extend(composite)
    return filters, output_label


def _glyph_stage_filters(
    glyph: Mapping[str, Any],
    *,
    input_label: str,
    mask_input_indices: Sequence[int],
    prefix: str,
) -> tuple[list[str], str]:
    masks = glyph["masks"]
    ranges = _explicit_stage_ranges_v2(
        glyph["revealSchedule"],
        masks=masks,
        frame_range_start=glyph["frameRangeStartInclusive"],
        frame_range_end=glyph["frameRangeEndExclusive"],
    )
    output = glyph["output"]
    frame_rate = output["frameRate"]
    canvas_width = output["width"]
    canvas_height = output["height"]
    geometry = _validate_composite_params(
        glyph["compositeParams"],
        canvas_width=canvas_width,
        canvas_height=canvas_height,
    )
    points = geometry["points"]
    perspective = ":".join(
        (
            f"x0={points['topLeft'][0]}",
            f"y0={points['topLeft'][1]}",
            f"x1={points['topRight'][0]}",
            f"y1={points['topRight'][1]}",
            f"x2={points['bottomLeft'][0]}",
            f"y2={points['bottomLeft'][1]}",
            f"x3={points['bottomRight'][0]}",
            f"y3={points['bottomRight'][1]}",
            "sense=destination",
            "interpolation=linear",
            "eval=init",
        )
    )
    filters = [
        f"[{input_label}]settb=expr=1/{frame_rate},setpts=N[{prefix}base0]"
    ]
    relief_kernel = "-1 -1 0 -1 0 1 0 1 1"
    for index, input_index in enumerate(mask_input_indices):
        filters.append(
            f"[{input_index}:v]settb=expr=1/{frame_rate},setpts=N,format=gray,"
            f"scale={geometry['width']}:{geometry['height']}:flags=neighbor:"
            "in_range=full:out_range=full,"
            f"perspective={perspective},"
            f"convolution=0m='{relief_kernel}':0rdiv=1:0bias=128,"
            f"pad={canvas_width}:{canvas_height}:{geometry['x']}:{geometry['y']}:color=0x808080,"
            f"format=yuv420p[{prefix}stage{index}]"
        )
    previous = f"{prefix}base0"
    roi = (
        f"if(between(X,{geometry['x']},{geometry['x'] + geometry['width'] - 1})*"
        f"between(Y,{geometry['y']},{geometry['y'] + geometry['height'] - 1}),A+B-128,A)"
    )
    for index, (stage_start, stage_end) in enumerate(ranges):
        output_label = f"{prefix}blend{index}"
        enable = (
            f"gte(n,{stage_start})"
            if stage_end is None
            else f"between(n,{stage_start},{stage_end})"
        )
        filters.append(
            f"[{previous}][{prefix}stage{index}]"
            f"blend=c0_expr='{roi}':c1_expr='A':c2_expr='A':"
            f"enable='{enable}'[{output_label}]"
        )
        previous = output_label
    final_label = f"{prefix}out"
    filters.append(f"[{previous}]format=yuv420p[{final_label}]")
    return filters, final_label


def _probe_video(
    path: Path,
    ffprobe: _PinnedRuntimeBinary,
    *,
    pass_fds: Sequence[int] = (),
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                str(ffprobe.executable_path),
                "-v",
                "error",
                "-count_frames",
                "-show_entries",
                (
                    "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,"
                    "r_frame_rate,nb_frames,nb_read_frames,time_base,start_pts,"
                    "duration_ts:"
                    "stream_tags=rotate:"
                    "stream_side_data=side_data_type,rotation:format=format_name"
                ),
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            env=_fixed_environment(),
            pass_fds=tuple(dict.fromkeys(ffprobe.pass_fds + tuple(pass_fds))),
        )
        payload = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError) as exc:
        raise RenderArtifactError("masked-surface video probe failed") from exc
    streams = payload.get("streams")
    if (
        not isinstance(streams, list)
        or len(streams) != 1
        or not isinstance(streams[0], Mapping)
        or streams[0].get("codec_type") != "video"
    ):
        raise RenderArtifactError(
            "masked-surface media must contain exactly one video-only stream"
        )
    stream = streams[0]
    if stream.get("side_data_list") or (
        isinstance(stream.get("tags"), Mapping) and str(stream["tags"].get("rotate", "0")) != "0"
    ):
        raise RenderArtifactError("masked-surface display transforms are unsupported")
    try:
        rate = Fraction(str(stream["avg_frame_rate"]))
        real_rate = Fraction(str(stream["r_frame_rate"]))
        frame_count = int(stream.get("nb_read_frames") or stream["nb_frames"])
        width = int(stream["width"])
        height = int(stream["height"])
        time_base = Fraction(str(stream["time_base"]))
        start_time = int(stream["start_pts"]) * time_base
        duration = int(stream["duration_ts"]) * time_base
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RenderArtifactError("masked-surface video probe is incomplete") from exc
    return {
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "frameRate": rate,
        "realFrameRate": real_rate,
        "startTime": start_time,
        "duration": duration,
        "pixelFormat": stream.get("pix_fmt"),
        "videoCodec": stream.get("codec_name"),
        "formatName": payload.get("format", {}).get("format_name"),
    }


def _held_png_digest_metadata(
    path: Path,
    *,
    ffmpeg: _PinnedRuntimeBinary,
    ffprobe: _PinnedRuntimeBinary,
    pass_fds: tuple[int, ...],
) -> dict[str, object]:
    """Measure one held PNG inode without reopening its staging path."""

    probe = _probe_video_stream(
        path,
        ffprobe_path=ffprobe.executable_path,
        pass_fds=pass_fds,
    )
    if (
        probe["codecName"] != "png"
        or probe["formatName"] != "png_pipe"
        or probe["frameCount"] != 1
    ):
        raise DigestError(
            "image pixel digest input must be a single-frame PNG"
        )
    pixel_hex, byte_count = _decoded_rgba_sha256(
        path,
        frame_count=1,
        ffmpeg_path=ffmpeg.executable_path,
        pass_fds=pass_fds,
    )
    if byte_count != probe["width"] * probe["height"] * 4:
        raise DigestError(
            "image pixel digest decoded byte count is invalid"
        )
    return {
        "width": probe["width"],
        "height": probe["height"],
        "source_mode": None,
        "pixel_mode": "RGBA",
        "pixel_digest": f"sha256:{pixel_hex}",
        "pixel_digest_spec": IMAGE_PIXEL_DIGEST_SPEC,
    }


def _validate_probe(probe: Mapping[str, Any], output: Mapping[str, Any], *, input_media: bool) -> None:
    if (
        probe["width"] != output["width"]
        or probe["height"] != output["height"]
        or probe["frameCount"] != output["frameCount"]
        or probe["frameRate"] != Fraction(output["frameRate"], 1)
        or probe["realFrameRate"] != Fraction(output["frameRate"], 1)
        or probe["startTime"] != 0
        or abs(
            probe["duration"]
            - Fraction(output["frameCount"], output["frameRate"])
        )
        > Fraction(1, 1_000_000)
        or probe["pixelFormat"] != output["pixelFormat"]
    ):
        raise RenderArtifactError("masked-surface media facts do not match output contract")
    if not input_media and (
        probe["videoCodec"] != "h264"
        or "mp4" not in str(probe["formatName"]).split(",")
    ):
        raise RenderArtifactError("masked-surface output codec contract is invalid")


def _procedural_smoke_sample(seed: int, frame: int, x: int, y: int) -> int:
    """Return one code-owned, integer-only smoke texel.

    This is deliberately a counter hash rather than a PRNG API: there is no
    mutable generator state, platform entropy, clock, locale, or thread-order
    input.  The constants and uint64 wrap are part of renderer version 1.
    """

    mask = (1 << 64) - 1
    value = (
        seed
        ^ ((frame + 1) * 0x9E3779B97F4A7C15)
        ^ ((x + 1) * 0xBF58476D1CE4E5B9)
        ^ ((y + 1) * 0x94D049BB133111EB)
    ) & mask
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & mask
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & mask
    value ^= value >> 31
    return (value >> 56) & 0xFF


def _write_procedural_smoke(
    destination: Path, *, seed: int, frame_count: int
) -> str:
    """Materialize the frozen gray8 procedural source with safe creation."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destination, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            for frame in range(frame_count):
                payload = bytearray(
                    _PROCEDURAL_SMOKE_TILE_WIDTH
                    * _PROCEDURAL_SMOKE_TILE_HEIGHT
                )
                cursor = 0
                for y in range(_PROCEDURAL_SMOKE_TILE_HEIGHT):
                    for x in range(_PROCEDURAL_SMOKE_TILE_WIDTH):
                        payload[cursor] = _procedural_smoke_sample(
                            seed, frame, x, y
                        )
                        cursor += 1
                handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise RenderArtifactError("procedural smoke staging failed") from exc
    return "sha256:" + sha256(destination.read_bytes()).hexdigest()


class DeterministicMaskedSurfaceExecutor:
    """Execute one sealed Scratch/Light/Local-Exposure primitive."""

    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise RenderArtifactError("masked-surface artifact root is invalid")

    def execute(self, execution_request: Mapping[str, Any]) -> dict[str, Any]:
        request = _validate_effect_request(execution_request)
        base_source = _safe_glyph_input(self.artifact_root, request["basePlate"]["storageKey"])

        with _PinnedRuntimeBinary(Path(os.path.realpath(self._runtime("ffmpeg"))), label="FFmpeg") as ffmpeg:
            with _PinnedRuntimeBinary(Path(os.path.realpath(self._runtime("ffprobe"))), label="FFprobe") as ffprobe:
                if request["effectMode"] in _E1_EFFECT_MODES:
                    mask_source = _safe_glyph_input(
                        self.artifact_root, request["mask"]["storageKey"]
                    )
                    if mask_source.suffix.lower() != ".png":
                        raise RenderArtifactError("masked-surface mask must be a PNG")
                    return self._execute_with_runtimes(
                        request, base_source, mask_source, ffmpeg, ffprobe
                    )
                return self._execute_flame_smoke_with_runtimes(
                    request, base_source, ffmpeg, ffprobe
                )

    def compose_timeline_preview_v2(
        self, execution_request: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Replay Effect primitives in fixed phases, then Glyph and audio mux.

        Result artifacts from the independent executions are lineage evidence;
        their full-frame videos are never overlaid.  The exact sealed E1 or E2
        stage profile and the sealed Glyph request are replayed against one
        original base in the code-owned deterministic order.
        """

        request = _validate_effect_preview_request(execution_request)
        base_source = _safe_glyph_input(
            self.artifact_root, request["baseVideo"]["storageKey"]
        )
        with _PinnedRuntimeBinary(
            Path(os.path.realpath(self._runtime("ffmpeg"))), label="FFmpeg"
        ) as ffmpeg:
            with _PinnedRuntimeBinary(
                Path(os.path.realpath(self._runtime("ffprobe"))), label="FFprobe"
            ) as ffprobe:
                return self._compose_timeline_preview_v2_with_runtimes(
                    request,
                    base_source=base_source,
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                )

    def _compose_timeline_preview_v2_with_runtimes(
        self,
        request: Mapping[str, Any],
        *,
        base_source: Path,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        stages = request["effectStages"]
        glyph = request["glyphStage"]
        base = request["baseVideo"]
        pass_fds = tuple(dict.fromkeys(ffmpeg.pass_fds + ffprobe.pass_fds))
        with tempfile.TemporaryDirectory(
            prefix=".effect-preview-work-", dir=self.artifact_root
        ) as temporary, ExitStack() as overlay_stack:
            work_root = Path(temporary)
            work_root.chmod(0o700)
            inputs = work_root / "inputs"
            inputs.mkdir(mode=0o700)
            base_path = inputs / "base.mp4"
            _stage_digest_pinned_input(
                base_source, base_path, base["fileDigest"]
            )
            input_file_pins: list[_PinnedRegularFile] = []
            input_pass_fds: list[int] = []

            def pin_input(path: Path, *, label: str) -> Path:
                pinned = overlay_stack.enter_context(
                    _PinnedRegularFile(path, label=label)
                )
                input_file_pins.append(pinned)
                input_pass_fds.extend(pinned.pass_fds)
                return pinned.descriptor_path

            def active_pass_fds() -> tuple[int, ...]:
                return tuple(
                    dict.fromkeys(pass_fds + tuple(input_pass_fds))
                )

            base_path = pin_input(
                base_path, label="effect preview staged base"
            )
            base_probe = _probe_video(
                base_path, ffprobe, pass_fds=active_pass_fds()
            )
            expected_visual = {
                "width": base["width"],
                "height": base["height"],
                "frameCount": base["frameCount"],
                "frameRate": base["frameRate"],
                "pixelFormat": base["pixelFormat"],
                "container": "mp4",
                "videoCodec": "h264",
            }
            _validate_probe(base_probe, expected_visual, input_media=True)
            try:
                base_digest = decoded_frame_pixel_digest_metadata(
                    base_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=active_pass_fds(),
                )
            except DigestError as exc:
                raise RenderArtifactError("effect preview base digest failed") from exc
            if (
                base_digest["decodedFramePixelDigest"] != base["pixelDigest"]
                or base_digest["decodedFramePixelDigestSpec"] != base["pixelDigestSpec"]
            ):
                raise RenderArtifactError("effect preview base pixels changed")

            effect_inputs: list[tuple[str, Path]] = []
            stage_input_indices: list[tuple[int, ...]] = []
            overlay_stage_files: dict[int, dict[str, Path]] = {}
            distance_stage_input_names: dict[int, tuple[str, ...]] = {}

            def stage_image(
                binding: Mapping[str, Any], *, label: str
            ) -> int:
                source = _safe_glyph_input(
                    self.artifact_root, binding["storageKey"]
                )
                path = inputs / f"effect-{len(effect_inputs):04d}-{label}.png"
                _stage_digest_pinned_input(source, path, binding["fileDigest"])
                path = pin_input(
                    path, label=f"effect preview staged {label}"
                )
                try:
                    measured = _held_png_digest_metadata(
                        path,
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        pass_fds=active_pass_fds(),
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        f"effect preview {label} digest failed"
                    ) from exc
                if (
                    measured["pixel_digest"] != binding["pixelDigest"]
                    or measured["pixel_digest_spec"]
                    != binding["pixelDigestSpec"]
                    or measured["pixel_mode"] != binding["pixelMode"]
                    or measured["width"] != binding["width"]
                    or measured["height"] != binding["height"]
                ):
                    raise RenderArtifactError(
                        f"effect preview {label} pixels changed"
                    )
                input_index = 1 + len(effect_inputs)
                effect_inputs.append(("image", path))
                return input_index

            for index, stage in enumerate(stages):
                mode = stage["effectMode"]
                if mode in _E1_EFFECT_MODES:
                    stage_input_indices.append(
                        (stage_image(stage["mask"], label=f"stage-{index}-mask"),)
                    )
                elif mode == "FLAME_EXTINGUISH":
                    stage_input_indices.append(
                        (
                            stage_image(
                                stage["flameMask"],
                                label=f"stage-{index}-flame-mask",
                            ),
                        )
                    )
                elif mode == "SMOKE":
                    if stage["smokeSourceKind"] == "PINNED_SMOKE_LAYER":
                        smoke_index = stage_image(
                            stage["smokeLayer"],
                            label=f"stage-{index}-smoke-layer",
                        )
                    else:
                        path = inputs / f"effect-{len(effect_inputs):04d}-smoke.gray"
                        _write_procedural_smoke(
                            path,
                            seed=stage["deterministicSeed"],
                            frame_count=base["frameCount"],
                        )
                        path = pin_input(
                            path,
                            label=(
                                "effect preview staged procedural smoke "
                                f"{index}"
                            ),
                        )
                        smoke_index = 1 + len(effect_inputs)
                        effect_inputs.append(("raw-smoke", path))
                    emission_index = stage_image(
                        stage["emissionMask"],
                        label=f"stage-{index}-emission-mask",
                    )
                    stage_input_indices.append((smoke_index, emission_index))
                elif mode == "NAMEPLATE_TEXT":
                    from .deterministic_overlays import overlay_text_bytes

                    font = stage["overlayAsset"]
                    source = _safe_glyph_input(
                        self.artifact_root, font["storageKey"]
                    )
                    font_path = inputs / f"overlay-{index:04d}-font.ttf"
                    _stage_digest_pinned_input(
                        source, font_path, font["fileDigest"]
                    )
                    text_path = inputs / f"overlay-{index:04d}-text.txt"
                    text_fd: int | None = None
                    try:
                        text_fd = os.open(
                            text_path,
                            os.O_WRONLY
                            | os.O_CREAT
                            | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0),
                            0o400,
                        )
                        text_payload = overlay_text_bytes(stage)
                        view = memoryview(text_payload)
                        while view:
                            written = os.write(text_fd, view)
                            if written <= 0:
                                raise OSError("short Nameplate text write")
                            view = view[written:]
                        os.fsync(text_fd)
                    except (OSError, UnicodeError) as exc:
                        raise RenderArtifactError(
                            "effect preview Nameplate text staging failed"
                        ) from exc
                    finally:
                        if text_fd is not None:
                            os.close(text_fd)
                    font_path = pin_input(
                        font_path,
                        label=f"effect preview Nameplate font {index}",
                    )
                    text_path = pin_input(
                        text_path,
                        label=f"effect preview Nameplate text {index}",
                    )
                    overlay_stage_files[index] = {
                        "fontPath": font_path,
                        "textPath": text_path,
                    }
                    stage_input_indices.append(())
                elif mode == "FACE_MARK_COMPENSATION":
                    mark_index = stage_image(
                        stage["overlayAsset"],
                        label=f"stage-{index}-face-mark",
                    )
                    stage_input_indices.append((mark_index,))
                elif mode == "DISTANCE_STATE_TRANSITION":
                    from .distance_state import distance_state_preview_assets

                    distance_assets = distance_state_preview_assets(stage)
                    distance_stage_input_names[index] = tuple(
                        name for name, _binding in distance_assets
                    )
                    stage_input_indices.append(
                        tuple(
                            stage_image(
                                binding,
                                label=f"stage-{index}-distance-{asset_index}",
                            )
                            for asset_index, (_name, binding) in enumerate(
                                distance_assets
                            )
                        )
                    )
                else:
                    raise RenderArtifactError(
                        "effect preview stage profile is unsupported"
                    )

            glyph_mask_paths: list[Path] = []
            for index, mask in enumerate(glyph["masks"]):
                source = _safe_glyph_input(
                    self.artifact_root, mask["storageKey"]
                )
                path = inputs / f"glyph-mask-{index}.png"
                _stage_digest_pinned_input(source, path, mask["fileDigest"])
                path = pin_input(
                    path,
                    label=f"effect preview staged Glyph mask {index}",
                )
                try:
                    measured = _held_png_digest_metadata(
                        path,
                        ffmpeg=ffmpeg,
                        ffprobe=ffprobe,
                        pass_fds=active_pass_fds(),
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        f"effect preview Glyph mask {index} digest failed"
                    ) from exc
                if (
                    measured["pixel_digest"] != mask["pixelDigest"]
                    or measured["pixel_digest_spec"] != mask["pixelDigestSpec"]
                    or measured["width"] != mask["width"]
                    or measured["height"] != mask["height"]
                ):
                    raise RenderArtifactError(
                        f"effect preview Glyph mask {index} pixels changed"
                    )
                glyph_mask_paths.append(path)

            filters: list[str] = []
            previous_label = "0:v"
            for index, (stage, input_indices) in enumerate(
                zip(stages, stage_input_indices, strict=True)
            ):
                prefix = f"phase{index}"
                if stage["effectMode"] in _E1_EFFECT_MODES:
                    stage_filters, output_label = _effect_stage_filters(
                        stage,
                        input_label=previous_label,
                        mask_input_index=input_indices[0],
                        prefix=prefix,
                    )
                elif stage["effectMode"] == "FLAME_EXTINGUISH":
                    # LocalExposure is stage 1 and is deliberately not replayed
                    # from Flame's dependency projection a second time.
                    stage_filters, output_label = _flame_stage_filters(
                        stage,
                        input_label=previous_label,
                        mask_input_index=input_indices[0],
                        prefix=prefix,
                    )
                elif stage["effectMode"] == "SMOKE":
                    stage_filters, output_label = _smoke_stage_filters(
                        stage,
                        input_label=previous_label,
                        smoke_input_index=input_indices[0],
                        emission_input_index=input_indices[1],
                        prefix=prefix,
                    )
                elif stage["effectMode"] == "DISTANCE_STATE_TRANSITION":
                    from .distance_state import build_distance_state_preview_filters

                    input_names = distance_stage_input_names.get(index, ())
                    if len(input_names) != len(input_indices):
                        raise RenderArtifactError(
                            "distance/state preview inputs are inconsistent"
                        )
                    stage_filters, output_label = build_distance_state_preview_filters(
                        stage,
                        input_label=previous_label,
                        asset_input_labels={
                            name: f"{input_index}:v"
                            for name, input_index in zip(
                                input_names, input_indices, strict=True
                            )
                        },
                        prefix=prefix,
                    )
                else:
                    from .deterministic_overlays import (
                        build_overlay_stage_filters,
                    )

                    overlay_files = overlay_stage_files.get(index, {})
                    stage_filters, output_label = build_overlay_stage_filters(
                        stage,
                        input_label=previous_label,
                        prefix=prefix,
                        font_path=overlay_files.get("fontPath"),
                        text_path=overlay_files.get("textPath"),
                        overlay_input_label=(
                            f"{input_indices[0]}:v"
                            if stage["effectMode"]
                            == "FACE_MARK_COMPENSATION"
                            else None
                        ),
                    )
                filters.extend(stage_filters)
                previous_label = output_label
            glyph_start = 1 + len(effect_inputs)
            glyph_indices = list(
                range(glyph_start, glyph_start + len(glyph_mask_paths))
            )
            glyph_filters, glyph_label = _glyph_stage_filters(
                glyph,
                input_label=previous_label,
                mask_input_indices=glyph_indices,
                prefix=f"phase{len(stages)}glyph",
            )
            filters.extend(glyph_filters)
            filters.append(f"[{glyph_label}]null[vout]")
            visual = work_root / "combined-visual.mp4"
            command = [
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
            for kind, path in effect_inputs:
                if kind == "raw-smoke":
                    command.extend(
                        [
                            "-f",
                            "rawvideo",
                            "-pixel_format",
                            "gray",
                            "-video_size",
                            f"{_PROCEDURAL_SMOKE_TILE_WIDTH}x{_PROCEDURAL_SMOKE_TILE_HEIGHT}",
                            "-framerate",
                            str(base["frameRate"]),
                            "-i",
                            str(path),
                        ]
                    )
                else:
                    command.extend(
                        [
                            "-loop",
                            "1",
                            "-framerate",
                            str(base["frameRate"]),
                            "-i",
                            str(path),
                        ]
                    )
            for path in glyph_mask_paths:
                command.extend(
                    [
                        "-loop",
                        "1",
                        "-framerate",
                        str(base["frameRate"]),
                        "-i",
                        str(path),
                    ]
                )
            command.extend(
                [
                    "-filter_complex",
                    ";".join(filters),
                    "-map",
                    "[vout]",
                    "-an",
                    "-sn",
                    "-dn",
                    "-frames:v",
                    str(base["frameCount"]),
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
                    "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0:rc-lookahead=0:scenecut=0",
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
                    str(base["frameRate"] * 512),
                    "-n",
                    str(visual),
                ]
            )
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    timeout=300,
                    env=_fixed_environment(),
                    pass_fds=active_pass_fds(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                message = ""
                if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                    message = bytes(exc.stderr)[:1000].decode(
                        "utf-8", "replace"
                    ).strip()
                raise RenderArtifactError(
                    "FFmpeg effect preview visual replay failed"
                    + (f": {message}" if message else "")
                ) from exc
            for input_pin in input_file_pins:
                input_pin.require_stable()
            _validate_probe(_probe_video(visual, ffprobe), expected_visual, input_media=False)
            try:
                visual_digest = decoded_frame_pixel_digest_metadata(
                    visual,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError("effect preview visual digest failed") from exc

            raw_result = self._mux_effect_preview_audio(
                request,
                visual=visual,
                visual_digest=visual_digest,
                work_root=work_root,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )
            source = Path(raw_result["internalPath"])
            workspace_hash = sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
            run_hash = sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
            destination_root = self.artifact_root / workspace_hash / run_hash
            with _PinnedRegularFile(source, label="effect preview candidate") as pinned:
                destination = _publish_timeline_output_v1(
                    root=self.artifact_root,
                    directory=destination_root / "composition",
                    source=pinned,
                    expected_file_digest=raw_result["outputDigest"]["fileDigest"],
                    output_name=f"preview-{request['payloadDigest']}.mp4",
                )
            ffmpeg.require_stable()
            ffprobe.require_stable()

        renderer_version = {
            EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION: EFFECT_PREVIEW_RENDERER_VERSION,
            EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V3: EFFECT_PREVIEW_RENDERER_VERSION_V3,
            EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4: EFFECT_PREVIEW_RENDERER_VERSION_V4,
            EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V5: EFFECT_PREVIEW_RENDERER_VERSION_V5,
        }[request["schemaVersion"]]
        runtime_payload = {
            "ffmpegIdentity": raw_result["ffmpegIdentity"],
            "rendererIdentity": EFFECT_PREVIEW_RENDERER_IDENTITY,
            "rendererVersion": renderer_version,
        }
        runtime_digest = "sha256:" + sha256(_canonical_json(runtime_payload)).hexdigest()
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(destination.relative_to(self.artifact_root)),
            "outputByteSize": destination.stat().st_size,
            "outputMediaProbe": raw_result["outputMediaProbe"],
            "outputDigest": raw_result["outputDigest"],
            "rendererIdentity": EFFECT_PREVIEW_RENDERER_IDENTITY,
            "rendererVersion": renderer_version,
            "ffmpegIdentity": raw_result["ffmpegIdentity"],
            "runtimeEvidenceDigest": runtime_digest,
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["payloadDigest"],
            "timelineVersionRef": request["timelineVersionRef"],
            "timelineVersionDigest": request["timelineVersionDigest"],
            "inputBindingsDigest": request["inputBindingsDigest"],
            "effectResultBindings": deepcopy(request["effectResultBindings"]),
            "glyphRequirementBinding": deepcopy(request["glyphRequirementBinding"]),
            "effectBindingsDigest": request["effectBindingsDigest"],
            "mixRequestRef": request["audioMix"]["mixRequestRef"],
            "mixRequestDigest": request["audioMix"]["mixRequestDigest"],
            "subtitleManifestRef": request["subtitleManifest"]["subtitleManifestRef"],
            "subtitleManifestDigest": request["subtitleManifest"]["subtitleManifestDigest"],
            "publicationAllowed": False,
        }

    def _mux_effect_preview_audio(
        self,
        request: Mapping[str, Any],
        *,
        visual: Path,
        visual_digest: Mapping[str, Any],
        work_root: Path,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        """Reuse the v1 mux under the already-pinned visual runtimes."""

        inner_root = work_root / "inner-composer"
        inner_inputs = inner_root / "inputs"
        inner_inputs.mkdir(parents=True, mode=0o700)
        visual_key = "inputs/combined-visual.mp4"
        _stage_timeline_preview_input(
            root=self.artifact_root,
            storage_key=str(visual.relative_to(self.artifact_root)),
            expected_digest=visual_digest["fileDigest"],
            destination=inner_root / visual_key,
            prefixed_digest=True,
        )
        audio_mix = deepcopy(request["audioMix"])
        for index, clip in enumerate(audio_mix.get("clips", [])):
            destination_key = f"inputs/audio-{index:04d}.wav"
            _stage_timeline_preview_input(
                root=self.artifact_root,
                storage_key=clip["storageKey"],
                expected_digest=clip["fileDigest"],
                destination=inner_root / destination_key,
                prefixed_digest=False,
            )
            clip["storageKey"] = destination_key
        glyph = request["glyphStage"]
        glyph_binding = request["glyphRequirementBinding"]
        derived_artifact = {
            "effectBindingsDigest": request["effectBindingsDigest"],
            "glyphRequestDigest": glyph["payloadDigest"],
            "visualFileDigest": visual_digest["fileDigest"],
        }
        artifact_digest = sha256(_canonical_json(derived_artifact)).hexdigest()
        video_input = {
            "glyphRevealRequirementRef": glyph_binding["requirementRef"],
            "glyphRevealRequirementDigest": glyph_binding["requirementDigest"],
            "glyphRevealExecutionRequestRef": glyph["executionRequestRef"],
            "glyphRevealExecutionRequestDigest": glyph["payloadDigest"],
            "glyphRevealArtifactEvidenceRef": "m13-effect-preview-visual-" + artifact_digest[:32],
            "glyphRevealArtifactEvidenceDigest": artifact_digest,
            "storageKey": visual_key,
            "fileDigest": visual_digest["fileDigest"],
            "decodedFramePixelDigest": visual_digest["decodedFramePixelDigest"],
            "decodedFramePixelDigestSpec": visual_digest["decodedFramePixelDigestSpec"],
            "codec": "h264",
            "pixelFormat": request["baseVideo"]["pixelFormat"],
            "width": request["baseVideo"]["width"],
            "height": request["baseVideo"]["height"],
            "frameCount": request["baseVideo"]["frameCount"],
            "frameRate": deepcopy(request["output"]["frameRate"]),
        }
        input_digest = sha256(
            _canonical_json(
                {
                    "videoInput": video_input,
                    "audioMix": audio_mix,
                    "subtitleManifest": request["subtitleManifest"],
                }
            )
        ).hexdigest()
        output_digest = sha256(_canonical_json(request["output"])).hexdigest()
        execution_ref = "m13-composition-execution-" + sha256(
            _canonical_json(
                {
                    "timelineVersionRef": request["timelineVersionRef"],
                    "timelineVersionDigest": request["timelineVersionDigest"],
                    "inputBindingsDigest": input_digest,
                    "outputContractDigest": output_digest,
                }
            )
        ).hexdigest()[:32]
        inner = {
            "schemaVersion": "v4.m13-composition-execution-request.v1",
            "executionRequestRef": execution_ref,
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "timelineVersionRef": request["timelineVersionRef"],
            "timelineVersionDigest": request["timelineVersionDigest"],
            "inputBindingsDigest": input_digest,
            "videoInput": video_input,
            "audioMix": audio_mix,
            "subtitleManifest": deepcopy(request["subtitleManifest"]),
            "output": deepcopy(request["output"]),
            "publicationAllowed": False,
        }
        inner["payloadDigest"] = sha256(_canonical_json(inner)).hexdigest()
        validated_inner = _validate_timeline_preview_execution_request(inner)
        return DeterministicFfmpegComposer(
            inner_root
        )._compose_timeline_preview_v1_with_runtimes(
            validated_inner,
            ffmpeg_runtime=ffmpeg,
            ffprobe_runtime=ffprobe,
        )

    @staticmethod
    def _runtime(name: str) -> str:
        from shutil import which

        value = which(name)
        if value is None:
            raise RenderArtifactError(f"{name} runtime is unavailable")
        return value

    def _execute_flame_smoke_with_runtimes(
        self,
        request: Mapping[str, Any],
        base_source: Path,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        """Execute one E2 graph without accepting a caller-authored graph."""

        pass_fds = tuple(dict.fromkeys(ffmpeg.pass_fds + ffprobe.pass_fds))
        ffmpeg_identity = ffmpeg.version_identity()
        output = request["output"]
        with tempfile.TemporaryDirectory(
            prefix=".flame-smoke-work-", dir=self.artifact_root
        ) as temporary:
            work_root = Path(temporary)
            work_root.chmod(0o700)
            inputs = work_root / "inputs"
            inputs.mkdir(mode=0o700)
            base_path = inputs / "base-plate.media"
            _stage_digest_pinned_input(
                base_source, base_path, request["basePlate"]["fileDigest"]
            )
            _validate_probe(_probe_video(base_path, ffprobe), output, input_media=True)
            try:
                base_digest = decoded_frame_pixel_digest_metadata(
                    base_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError(
                    "flame/smoke base pixel digest failed"
                ) from exc
            if (
                base_digest["decodedFramePixelDigest"]
                != request["basePlate"]["pixelDigest"]
                or base_digest["decodedFramePixelDigestSpec"]
                != request["basePlate"]["pixelDigestSpec"]
                or base_digest["width"] != output["width"]
                or base_digest["height"] != output["height"]
                or base_digest["frameCount"] != output["frameCount"]
            ):
                raise RenderArtifactError("flame/smoke base pixels changed")

            image_inputs: list[tuple[Path, Mapping[str, Any]]] = []
            procedural_path: Path | None = None
            if request["effectMode"] == "FLAME_EXTINGUISH":
                flame = request["flameMask"]
                source = _safe_glyph_input(self.artifact_root, flame["storageKey"])
                flame_path = inputs / "flame-mask.png"
                _stage_digest_pinned_input(source, flame_path, flame["fileDigest"])
                image_inputs.append((flame_path, flame))
                local_filters, local_label = _effect_stage_filters(
                    request["localExposureStage"],
                    input_label="0:v",
                    mask_input_index=1,
                    prefix="localexposure",
                )
                flame_filters, final_label = _flame_stage_filters(
                    request,
                    input_label=local_label,
                    mask_input_index=1,
                    prefix="flame",
                )
                filters = [*local_filters, *flame_filters]
            else:
                if request["smokeSourceKind"] == "PINNED_SMOKE_LAYER":
                    smoke = request["smokeLayer"]
                    smoke_source = _safe_glyph_input(
                        self.artifact_root, smoke["storageKey"]
                    )
                    smoke_path = inputs / "smoke-layer.png"
                    _stage_digest_pinned_input(
                        smoke_source, smoke_path, smoke["fileDigest"]
                    )
                    image_inputs.append((smoke_path, smoke))
                else:
                    procedural_path = inputs / "procedural-smoke.gray"
                    _write_procedural_smoke(
                        procedural_path,
                        seed=request["deterministicSeed"],
                        frame_count=output["frameCount"],
                    )
                    smoke_path = procedural_path
                emission = request["emissionMask"]
                emission_source = _safe_glyph_input(
                    self.artifact_root, emission["storageKey"]
                )
                emission_path = inputs / "emission-mask.png"
                _stage_digest_pinned_input(
                    emission_source, emission_path, emission["fileDigest"]
                )
                image_inputs.append((emission_path, emission))
                filters, final_label = _smoke_stage_filters(
                    request,
                    input_label="0:v",
                    smoke_input_index=1,
                    emission_input_index=2,
                    prefix="smoke",
                )

            for path, binding in image_inputs:
                if path.suffix.lower() != ".png":
                    raise RenderArtifactError(
                        "flame/smoke image inputs must be PNG"
                    )
                try:
                    measured = image_digest_metadata(
                        path,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=pass_fds,
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        "flame/smoke image pixel digest failed"
                    ) from exc
                if (
                    measured["pixel_digest"] != binding["pixelDigest"]
                    or measured["pixel_digest_spec"]
                    != binding["pixelDigestSpec"]
                    or measured["pixel_mode"] != binding["pixelMode"]
                    or measured["width"] != binding["width"]
                    or measured["height"] != binding["height"]
                ):
                    raise RenderArtifactError("flame/smoke input pixels changed")

            candidate = work_root / "candidate.mp4"
            command = [
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
            if request["effectMode"] == "FLAME_EXTINGUISH":
                command.extend(
                    [
                        "-loop",
                        "1",
                        "-framerate",
                        str(output["frameRate"]),
                        "-i",
                        str(image_inputs[0][0]),
                    ]
                )
            else:
                if procedural_path is None:
                    command.extend(
                        [
                            "-loop",
                            "1",
                            "-framerate",
                            str(output["frameRate"]),
                            "-i",
                            str(image_inputs[0][0]),
                        ]
                    )
                else:
                    command.extend(
                        [
                            "-f",
                            "rawvideo",
                            "-pixel_format",
                            "gray",
                            "-video_size",
                            f"{_PROCEDURAL_SMOKE_TILE_WIDTH}x{_PROCEDURAL_SMOKE_TILE_HEIGHT}",
                            "-framerate",
                            str(output["frameRate"]),
                            "-i",
                            str(procedural_path),
                        ]
                    )
                command.extend(
                    [
                        "-loop",
                        "1",
                        "-framerate",
                        str(output["frameRate"]),
                        "-i",
                        str(image_inputs[-1][0]),
                    ]
                )
            filters.append(f"[{final_label}]null[vout]")
            command.extend(
                [
                    "-filter_complex",
                    ";".join(filters),
                    "-map",
                    "[vout]",
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
                    "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0:rc-lookahead=0:scenecut=0",
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
                    "FFmpeg flame/smoke execution failed"
                    + (f": {message}" if message else "")
                ) from exc

            _validate_probe(_probe_video(candidate, ffprobe), output, input_media=False)
            try:
                output_digest = decoded_frame_pixel_digest_metadata(
                    candidate,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError("flame/smoke output digest failed") from exc
            if (
                output_digest["width"] != output["width"]
                or output_digest["height"] != output["height"]
                or output_digest["frameCount"] != output["frameCount"]
            ):
                raise RenderArtifactError("flame/smoke output media facts changed")
            output_digest["frameRate"] = output["frameRate"]
            workspace_hash = sha256(
                request["workspaceRef"].encode("utf-8")
            ).hexdigest()[:20]
            run_hash = sha256(
                request["productionRunRef"].encode("utf-8")
            ).hexdigest()[:20]
            directory = self.artifact_root / workspace_hash / run_hash / "masked-surface"
            output_name = f"masked-surface-{request['payloadDigest']}.mp4"
            with _PinnedRegularFile(candidate, label="flame/smoke candidate") as pinned:
                destination = _publish_timeline_output_v1(
                    root=self.artifact_root,
                    directory=directory,
                    source=pinned,
                    expected_file_digest=output_digest["fileDigest"],
                    output_name=output_name,
                )
            ffmpeg.require_stable()
            ffprobe.require_stable()

        runtime_payload = {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": MASKED_SURFACE_RENDERER_VERSION,
        }
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(destination.relative_to(self.artifact_root)),
            "outputByteSize": destination.stat().st_size,
            "outputMediaProbe": deepcopy(output),
            "outputDigest": output_digest,
            "rendererIdentity": MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": MASKED_SURFACE_RENDERER_VERSION,
            "ffmpegIdentity": ffmpeg_identity,
            "runtimeEvidenceDigest": "sha256:"
            + sha256(_canonical_json(runtime_payload)).hexdigest(),
            "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
            "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
            "v3ExecutionRequestDigest": request["payloadDigest"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "publicationAllowed": False,
        }

    def _execute_with_runtimes(
        self,
        request: Mapping[str, Any],
        base_source: Path,
        mask_source: Path,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        pass_fds = tuple(dict.fromkeys(ffmpeg.pass_fds + ffprobe.pass_fds))
        ffmpeg_identity = ffmpeg.version_identity()
        output = request["output"]
        with tempfile.TemporaryDirectory(prefix=".masked-surface-work-", dir=self.artifact_root) as temporary:
            work_root = Path(temporary)
            work_root.chmod(0o700)
            inputs = work_root / "inputs"
            inputs.mkdir(mode=0o700)
            base_path = inputs / "base-plate.media"
            mask_path = inputs / "mask.png"
            _stage_digest_pinned_input(base_source, base_path, request["basePlate"]["fileDigest"])
            _stage_digest_pinned_input(mask_source, mask_path, request["mask"]["fileDigest"])

            base_probe = _probe_video(base_path, ffprobe)
            _validate_probe(base_probe, output, input_media=True)
            try:
                base_digest = decoded_frame_pixel_digest_metadata(
                    base_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
                mask_digest = image_digest_metadata(
                    mask_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError("masked-surface input pixel digest failed") from exc
            if (
                base_digest["decodedFramePixelDigest"] != request["basePlate"]["pixelDigest"]
                or base_digest["decodedFramePixelDigestSpec"] != request["basePlate"]["pixelDigestSpec"]
                or base_digest["width"] != output["width"]
                or base_digest["height"] != output["height"]
                or base_digest["frameCount"] != output["frameCount"]
                or mask_digest["pixel_digest"] != request["mask"]["pixelDigest"]
                or mask_digest["pixel_digest_spec"] != request["mask"]["pixelDigestSpec"]
                or mask_digest["pixel_mode"] != request["mask"]["pixelMode"]
                or mask_digest["width"] != request["mask"]["width"]
                or mask_digest["height"] != request["mask"]["height"]
            ):
                raise RenderArtifactError("masked-surface input pixel digest changed")

            candidate = work_root / "candidate.mp4"
            command = [
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
                "-loop",
                "1",
                "-framerate",
                str(output["frameRate"]),
                "-i",
                str(mask_path),
                "-filter_complex",
                _filter_graph(request),
                "-map",
                "[vout]",
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
                "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0:rc-lookahead=0:scenecut=0",
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
                    message = bytes(exc.stderr)[:1000].decode("utf-8", "replace").strip()
                raise RenderArtifactError(
                    "FFmpeg masked-surface execution failed" + (f": {message}" if message else "")
                ) from exc

            output_probe = _probe_video(candidate, ffprobe)
            _validate_probe(output_probe, output, input_media=False)
            try:
                output_digest = decoded_frame_pixel_digest_metadata(
                    candidate,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            except DigestError as exc:
                raise RenderArtifactError("masked-surface output digest failed") from exc
            if (
                output_digest["width"] != output["width"]
                or output_digest["height"] != output["height"]
                or output_digest["frameCount"] != output["frameCount"]
            ):
                raise RenderArtifactError("masked-surface output digest media facts are invalid")
            output_digest["frameRate"] = output["frameRate"]
            expected_file_digest = str(output_digest["fileDigest"])
            workspace_hash = sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
            run_hash = sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
            directory = self.artifact_root / workspace_hash / run_hash / "masked-surface"
            output_name = f"masked-surface-{request['payloadDigest']}.mp4"
            with _PinnedRegularFile(candidate, label="masked-surface candidate") as pinned:
                destination = _publish_timeline_output_v1(
                    root=self.artifact_root,
                    directory=directory,
                    source=pinned,
                    expected_file_digest=expected_file_digest,
                    output_name=output_name,
                )
            ffmpeg.require_stable()
            ffprobe.require_stable()

        runtime_payload = {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": MASKED_SURFACE_RENDERER_VERSION,
        }
        runtime_digest = "sha256:" + sha256(_canonical_json(runtime_payload)).hexdigest()
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(destination.relative_to(self.artifact_root)),
            "outputByteSize": destination.stat().st_size,
            "outputMediaProbe": deepcopy(output),
            "outputDigest": output_digest,
            "rendererIdentity": MASKED_SURFACE_RENDERER_IDENTITY,
            "rendererVersion": MASKED_SURFACE_RENDERER_VERSION,
            "ffmpegIdentity": ffmpeg_identity,
            "runtimeEvidenceDigest": runtime_digest,
            "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
            "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
            "v3ExecutionRequestDigest": request["payloadDigest"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "publicationAllowed": False,
        }


__all__ = [
    "DeterministicMaskedSurfaceExecutor",
    "EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION",
    "EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V3",
    "EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V4",
    "EFFECT_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V5",
    "EFFECT_PREVIEW_RENDERER_IDENTITY",
    "EFFECT_PREVIEW_RENDERER_VERSION",
    "EFFECT_PREVIEW_RENDERER_VERSION_V3",
    "EFFECT_PREVIEW_RENDERER_VERSION_V4",
    "EFFECT_PREVIEW_RENDERER_VERSION_V5",
    "FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "MASKED_SURFACE_RENDERER_IDENTITY",
    "MASKED_SURFACE_RENDERER_VERSION",
]
