"""Closed V5 contracts for M13 deterministic masked-surface effects.

This module owns immutable Requirements, the storage-free V5-to-V4 execution
projection, immutable Results, and their append-only evidence-journal closure.
It does not resolve storage, execute FFmpeg, own a Timeline, or create another
repository/database.  ``K2DeliveryService`` remains the sole Timeline owner.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
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


SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-scratch-light-requirement.v1"
)
LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-local-exposure-requirement.v1"
)
FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-flame-extinguish-requirement.v1"
)
SMOKE_REQUIREMENT_SCHEMA_VERSION = "v5.m13-smoke-requirement.v1"
MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-masked-surface-execution-request.v1"
)
FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-flame-smoke-execution-request.v1"
)
SCRATCH_LIGHT_RESULT_SCHEMA_VERSION = "v5.m13-scratch-light-result.v1"
LOCAL_EXPOSURE_RESULT_SCHEMA_VERSION = "v5.m13-local-exposure-result.v1"
FLAME_EXTINGUISH_RESULT_SCHEMA_VERSION = (
    "v5.m13-flame-extinguish-result.v1"
)
SMOKE_RESULT_SCHEMA_VERSION = "v5.m13-smoke-result.v1"
MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-masked-surface-runtime-evidence.v1"
)
MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-masked-surface-artifact-evidence.v1"
)

SCRATCH_REVEAL = "SCRATCH_REVEAL"
LIGHT_SWEEP = "LIGHT_SWEEP"
LOCAL_EXPOSURE = "LOCAL_EXPOSURE"
FLAME_EXTINGUISH = "FLAME_EXTINGUISH"
SMOKE = "SMOKE"
SCRATCH_LIGHT_EFFECT_MODES = frozenset({SCRATCH_REVEAL, LIGHT_SWEEP})
MASKED_SURFACE_EFFECT_MODES = frozenset(
    {SCRATCH_REVEAL, LIGHT_SWEEP, LOCAL_EXPOSURE}
)
FLAME_SMOKE_EFFECT_MODES = frozenset({FLAME_EXTINGUISH, SMOKE})
DETERMINISTIC_EFFECT_MODES = frozenset(
    {*MASKED_SURFACE_EFFECT_MODES, *FLAME_SMOKE_EFFECT_MODES}
)
INTERPOLATIONS = frozenset(
    {"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"}
)
BLEND_MODES = frozenset(
    {"NORMAL", "MULTIPLY", "SCREEN", "OVERLAY", "ADD", "DARKEN", "LIGHTEN"}
)

SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND = "ScratchLightRequirement"
LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND = "LocalExposureRequirement"
FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND = "FlameExtinguishRequirement"
SMOKE_REQUIREMENT_RECORD_KIND = "SmokeRequirement"
MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND = "MaskedSurfaceExecutionRequest"
MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND = "MaskedSurfaceArtifactEvidence"
MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND = "MaskedSurfaceRuntimeEvidence"
SCRATCH_LIGHT_RESULT_RECORD_KIND = "ScratchLightResult"
LOCAL_EXPOSURE_RESULT_RECORD_KIND = "LocalExposureResult"
FLAME_EXTINGUISH_RESULT_RECORD_KIND = "FlameExtinguishResult"
SMOKE_RESULT_RECORD_KIND = "SmokeResult"

DECODED_FRAME_PIXEL_DIGEST_SPEC = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)
LOCAL_EVIDENCE_PROVENANCE = "LOCAL_EVIDENCE"
RESULT_STATE = "SUCCEEDED"
E2_RESULT_STATE = "COMPOSED_CANDIDATE"
ASSET_ADMISSION_STATE = "NOT_ADMITTED"
MASTER_STATE = "NOT_CREATED"
EXPORT_STATE = "NOT_CREATED"
MASKED_SURFACE_RENDERER_IDENTITY = "v3.deterministic-masked-surface-ffmpeg"
MASKED_SURFACE_RENDERER_VERSION = "1"
DETERMINISTIC_SMOKE_ALGORITHM_IDENTITY = "v3.deterministic-smoke-cpu"
DETERMINISTIC_SMOKE_ALGORITHM_VERSION = "1"
SMOKE_SOURCE_KINDS = frozenset(
    {"PINNED_SMOKE_LAYER", "DETERMINISTIC_CPU_PROCEDURAL"}
)
FLAME_STATES = ("LIT", "DIMMING", "EXTINGUISHED", "EMBER", "DARK")

_RAW_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FORBIDDEN_KEY_PARTS = (
    "path",
    "storage",
    "filter",
    "argv",
    "argument",
    "expression",
    "random",
    "seed",
    "shell",
    "command",
    "ffmpegfilter",
)

_SCHEDULE_FIELDS = frozenset(
    {"startFrameInclusive", "endFrameExclusive", "enabled", "interpolation"}
)
_TRAJECTORY_FIELDS = frozenset(
    {"frame", "xPermille", "yPermille", "interpolation"}
)
_INTENSITY_FIELDS = frozenset(
    {"frame", "valuePermille", "interpolation"}
)
_EXPOSURE_FIELDS = frozenset(
    {"frame", "valueMilliStops", "interpolation"}
)
_STATE_SCHEDULE_FIELDS = frozenset(
    {"state", "startFrameInclusive", "endFrameExclusive"}
)
_SCALE_KEYFRAME_FIELDS = frozenset(
    {"frame", "xPermille", "yPermille", "interpolation"}
)
_DRIFT_KEYFRAME_FIELDS = frozenset(
    {"frame", "xDeltaPermille", "yDeltaPermille", "interpolation"}
)
_POSITION_FIELDS = frozenset({"xPermille", "yPermille"})
_SCALE_FIELDS = frozenset({"xPermille", "yPermille"})
_PERSPECTIVE_FIELDS = frozenset({"mode", "quadPermille"})
_POINT_FIELDS = frozenset({"xPermille", "yPermille"})

_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "effectMode",
        "targetShotRef",
        "targetShotVersionRef",
        "targetShotVersionDigest",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "basePlatePixelDigest",
        "maskAssetVersionRef",
        "maskAssetVersionDigest",
        "maskFileDigest",
        "maskPixelDigest",
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
        "publicationAllowed",
        "payloadDigest",
    }
)
_REQUIREMENT_COMMAND_FIELDS = _REQUIREMENT_FIELDS - frozenset(
    {"schemaVersion", "publicationAllowed", "payloadDigest"}
)

_FLAME_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "effectMode",
        "targetShotRef",
        "targetShotVersionRef",
        "targetShotVersionDigest",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "basePlatePixelDigest",
        "flameMaskAssetVersionRef",
        "flameMaskAssetVersionDigest",
        "flameMaskFileDigest",
        "flameMaskPixelDigest",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "stateSchedule",
        "brightnessCurve",
        "alphaCurve",
        "localExposureRequirementRef",
        "localExposureRequirementDigest",
        "blendMode",
        "layer",
        "publicationAllowed",
        "payloadDigest",
    }
)
_FLAME_REQUIREMENT_COMMAND_FIELDS = _FLAME_REQUIREMENT_FIELDS - frozenset(
    {"schemaVersion", "publicationAllowed", "payloadDigest"}
)

_SMOKE_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "effectMode",
        "targetShotRef",
        "targetShotVersionRef",
        "targetShotVersionDigest",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "basePlatePixelDigest",
        "smokeSourceKind",
        "smokeLayerAssetVersionRef",
        "smokeLayerAssetVersionDigest",
        "smokeLayerFileDigest",
        "smokeLayerPixelDigest",
        "emissionMaskAssetVersionRef",
        "emissionMaskAssetVersionDigest",
        "emissionMaskFileDigest",
        "emissionMaskPixelDigest",
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
        "publicationAllowed",
        "payloadDigest",
    }
)
_SMOKE_REQUIREMENT_COMMAND_FIELDS = _SMOKE_REQUIREMENT_FIELDS - frozenset(
    {"schemaVersion", "publicationAllowed", "payloadDigest"}
)
_SMOKE_ALLOWED_FORBIDDEN_KEYS = frozenset({"deterministicSeed"})

_SHOT_BINDING_FIELDS = frozenset(
    {"shotRef", "shotVersionRef", "shotVersionDigest"}
)
_ASSET_BINDING_FIELDS = frozenset(
    {"assetVersionRef", "assetVersionDigest", "fileDigest", "pixelDigest"}
)
_EXECUTION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
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
        "publicationAllowed",
        "payloadDigest",
    }
)

_FLAME_EXECUTION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
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
        "blendMode",
        "layer",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SMOKE_EXECUTION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
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
        "publicationAllowed",
        "payloadDigest",
    }
)

_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "resultRef",
        "effectMode",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "state",
        "publicationAllowed",
        "payloadDigest",
    }
)
_E2_RESULT_FIELDS = _RESULT_FIELDS | frozenset(
    {
        "outputFileDigest",
        "outputDecodedFramePixelDigest",
        "outputMediaProbe",
        "assetAdmissionState",
        "masterState",
        "exportState",
    }
)
_EVIDENCE_BINDING_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
    }
)
_RUNTIME_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "runtimeEvidenceRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "v3ExecutionRequestDigest",
        "effectMode",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "gpuUsed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_OUTPUT_MEDIA_PROBE_FIELDS = frozenset(
    {
        "width",
        "height",
        "frameCount",
        "frameRate",
        "pixelFormat",
        "container",
        "videoCodec",
    }
)
_OUTPUT_DIGEST_FIELDS = frozenset(
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
    }
)
_ARTIFACT_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "artifactEvidenceRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "v3ExecutionRequestDigest",
        "effectMode",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)


class DeterministicEffectContractError(EpisodeProductionError):
    code = "m13_deterministic_effect_contract_invalid"


class DeterministicEffectStaleInputError(StaleInputError):
    code = "m13_deterministic_effect_source_stale"


class DeterministicEffectJournalError(RepositoryUnavailableError):
    code = "m13_deterministic_effect_journal_invalid"


def _closed(
    value: Any,
    fields: frozenset[str],
    label: str,
    *,
    allowed_forbidden_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DeterministicEffectContractError(f"{label} fields are invalid")
    result = deepcopy(dict(value))
    _reject_floats(
        result, allowed_forbidden_keys=allowed_forbidden_keys
    )
    return result


def _reject_floats(
    value: Any,
    *,
    allowed_forbidden_keys: frozenset[str] = frozenset(),
) -> None:
    if isinstance(value, float):
        raise DeterministicEffectContractError("float authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DeterministicEffectContractError(
                    "object keys must be strings"
                )
            folded = key.replace("_", "").lower()
            if (
                key not in allowed_forbidden_keys
                and any(part in folded for part in _FORBIDDEN_KEY_PARTS)
            ):
                raise DeterministicEffectContractError(f"{key} is forbidden")
            _reject_floats(
                item, allowed_forbidden_keys=allowed_forbidden_keys
            )
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_floats(
                item, allowed_forbidden_keys=allowed_forbidden_keys
            )


def _seal(
    value: Mapping[str, Any],
    *,
    allowed_forbidden_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise DeterministicEffectContractError("payloadDigest is derived")
    _reject_floats(
        result, allowed_forbidden_keys=allowed_forbidden_keys
    )
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(
    value: Any,
    fields: frozenset[str],
    label: str,
    *,
    allowed_forbidden_keys: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    result = _closed(
        value,
        fields,
        label,
        allowed_forbidden_keys=allowed_forbidden_keys,
    )
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or _RAW_SHA256.fullmatch(supplied) is None:
        raise DeterministicEffectStaleInputError(
            f"{label} payloadDigest is invalid"
        )
    if supplied != _digest(result):
        raise DeterministicEffectStaleInputError(
            f"{label} payloadDigest is stale"
        )
    result["payloadDigest"] = supplied
    return result


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise DeterministicEffectContractError(f"{field} is invalid") from exc


def _raw_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _RAW_SHA256.fullmatch(value) is None:
        raise DeterministicEffectContractError(f"{field} is invalid")
    return value


def _content_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _PREFIXED_SHA256.fullmatch(value) is None:
        raise DeterministicEffectContractError(f"{field} is invalid")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
    maximum: int = 10_000_000,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise DeterministicEffectContractError(f"{field} is invalid")
    return value


def _text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 500
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise DeterministicEffectContractError(f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str = "createdAt") -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeterministicEffectContractError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeterministicEffectContractError(f"{field} must include timezone")
    return text


def _frame_range(value: Mapping[str, Any]) -> tuple[int, int]:
    start = _integer(
        value.get("frameRangeStartInclusive"), "frameRangeStartInclusive"
    )
    end = _integer(
        value.get("frameRangeEndExclusive"),
        "frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start:
        raise DeterministicEffectContractError("frame range is empty")
    return start, end


def _schedule(value: Any, *, start: int, end: int) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or len(value) > 4_096
    ):
        raise DeterministicEffectContractError("explicitSchedule is invalid")
    result: list[dict[str, Any]] = []
    expected_start = start
    any_enabled = False
    for index, item in enumerate(value):
        current = _closed(item, _SCHEDULE_FIELDS, f"explicitSchedule[{index}]")
        segment_start = _integer(
            current["startFrameInclusive"],
            f"explicitSchedule[{index}].startFrameInclusive",
        )
        segment_end = _integer(
            current["endFrameExclusive"],
            f"explicitSchedule[{index}].endFrameExclusive",
            minimum=1,
            maximum=10_000_001,
        )
        if segment_start != expected_start or segment_end <= segment_start or segment_end > end:
            raise DeterministicEffectContractError(
                "explicitSchedule must cover the range without gaps or overlap"
            )
        if type(current["enabled"]) is not bool:
            raise DeterministicEffectContractError(
                f"explicitSchedule[{index}].enabled is invalid"
            )
        if current["interpolation"] != "STEP":
            raise DeterministicEffectContractError(
                "explicitSchedule interpolation must be STEP"
            )
        any_enabled = any_enabled or current["enabled"]
        expected_start = segment_end
        result.append(current)
    if expected_start != end or not any_enabled:
        raise DeterministicEffectContractError(
            "explicitSchedule must cover and enable the effect range"
        )
    return result


def _keyframes(
    value: Any,
    *,
    fields: frozenset[str],
    label: str,
    value_fields: Mapping[str, tuple[int, int]],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or len(value) > 4_096
    ):
        raise DeterministicEffectContractError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    prior_frame: int | None = None
    for index, item in enumerate(value):
        current = _closed(item, fields, f"{label}[{index}]")
        frame = _integer(current["frame"], f"{label}[{index}].frame")
        if frame < start or frame >= end or (
            prior_frame is not None and frame <= prior_frame
        ):
            raise DeterministicEffectContractError(
                f"{label} frames are not strictly increasing in range"
            )
        interpolation = current["interpolation"]
        if interpolation not in INTERPOLATIONS:
            raise DeterministicEffectContractError(
                f"{label}[{index}].interpolation is invalid"
            )
        for field, bounds in value_fields.items():
            _integer(
                current[field],
                f"{label}[{index}].{field}",
                minimum=bounds[0],
                maximum=bounds[1],
            )
        prior_frame = frame
        result.append(current)
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise DeterministicEffectContractError(
            f"{label} must bind the first and final effect frames"
        )
    return result


def _position(value: Any) -> dict[str, int]:
    result = _closed(value, _POSITION_FIELDS, "position")
    return {
        "xPermille": _integer(result["xPermille"], "position.xPermille", maximum=1000),
        "yPermille": _integer(result["yPermille"], "position.yPermille", maximum=1000),
    }


def _scale(value: Any) -> dict[str, int]:
    result = _closed(value, _SCALE_FIELDS, "scale")
    return {
        "xPermille": _integer(result["xPermille"], "scale.xPermille", minimum=1, maximum=1000),
        "yPermille": _integer(result["yPermille"], "scale.yPermille", minimum=1, maximum=1000),
    }


def _perspective(value: Any) -> dict[str, Any]:
    result = _closed(value, _PERSPECTIVE_FIELDS, "perspective")
    mode = result["mode"]
    quad = result["quadPermille"]
    if mode == "NONE":
        if quad != []:
            raise DeterministicEffectContractError(
                "NONE perspective cannot carry a quad"
            )
        return {"mode": mode, "quadPermille": []}
    if mode != "FIXED_QUAD" or not isinstance(quad, list) or len(quad) != 4:
        raise DeterministicEffectContractError("perspective is invalid")
    points: list[dict[str, int]] = []
    for index, item in enumerate(quad):
        point = _closed(item, _POINT_FIELDS, f"perspective.quadPermille[{index}]")
        points.append(
            {
                "xPermille": _integer(point["xPermille"], f"perspective.quadPermille[{index}].xPermille", maximum=1000),
                "yPermille": _integer(point["yPermille"], f"perspective.quadPermille[{index}].yPermille", maximum=1000),
            }
        )
    identities = {(item["xPermille"], item["yPermille"]) for item in points}
    # FFmpeg's perspective points use TL/TR/BL/BR row-major order, while the
    # polygon boundary is TL/TR/BR/BL.
    boundary = (points[0], points[1], points[3], points[2])
    area_twice = abs(
        sum(
            boundary[index]["xPermille"]
            * boundary[(index + 1) % 4]["yPermille"]
            - boundary[(index + 1) % 4]["xPermille"]
            * boundary[index]["yPermille"]
            for index in range(4)
        )
    )
    canonical_order = (
        points[0]["xPermille"] < points[1]["xPermille"]
        and points[2]["xPermille"] < points[3]["xPermille"]
        and points[0]["yPermille"] < points[2]["yPermille"]
        and points[1]["yPermille"] < points[3]["yPermille"]
    )
    if len(identities) != 4 or area_twice == 0 or not canonical_order:
        raise DeterministicEffectContractError("perspective quad is degenerate")
    return {"mode": mode, "quadPermille": points}


def _validate_requirement(
    value: Any,
    *,
    schema_version: str,
    modes: frozenset[str],
    label: str,
) -> dict[str, Any]:
    result = _verify_sealed(value, _REQUIREMENT_FIELDS, label)
    if result["schemaVersion"] != schema_version:
        raise DeterministicEffectContractError(f"{label} schema is unsupported")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
        "targetShotVersionRef",
        "basePlateAssetVersionRef",
        "maskAssetVersionRef",
    ):
        _ref(result[field], field)
    for field in (
        "targetShotVersionDigest",
        "basePlateAssetVersionDigest",
        "maskAssetVersionDigest",
    ):
        _raw_digest(result[field], field)
    for field in (
        "basePlateFileDigest",
        "basePlatePixelDigest",
        "maskFileDigest",
        "maskPixelDigest",
    ):
        _content_digest(result[field], field)
    if result["effectMode"] not in modes:
        raise DeterministicEffectContractError("effectMode is invalid")
    if result["basePlateAssetVersionRef"] == result["maskAssetVersionRef"]:
        raise DeterministicEffectContractError(
            "base plate and mask AssetVersions must be distinct"
        )
    start, end = _frame_range(result)
    result["explicitSchedule"] = _schedule(
        result["explicitSchedule"], start=start, end=end
    )
    result["trajectoryKeyframes"] = _keyframes(
        result["trajectoryKeyframes"],
        fields=_TRAJECTORY_FIELDS,
        label="trajectoryKeyframes",
        value_fields={"xPermille": (0, 1000), "yPermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["intensityCurve"] = _keyframes(
        result["intensityCurve"],
        fields=_INTENSITY_FIELDS,
        label="intensityCurve",
        value_fields={"valuePermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["exposureCurve"] = _keyframes(
        result["exposureCurve"],
        fields=_EXPOSURE_FIELDS,
        label="exposureCurve",
        value_fields={"valueMilliStops": (-8000, 8000)},
        start=start,
        end=end,
    )
    result["position"] = _position(result["position"])
    result["scale"] = _scale(result["scale"])
    result["perspective"] = _perspective(result["perspective"])
    first = result["trajectoryKeyframes"][0]
    if (
        first["xPermille"] != result["position"]["xPermille"]
        or first["yPermille"] != result["position"]["yPermille"]
    ):
        raise DeterministicEffectContractError(
            "position must equal the first trajectory keyframe"
        )
    if any(
        keyframe["xPermille"] + result["scale"]["xPermille"] > 1000
        or keyframe["yPermille"] + result["scale"]["yPermille"] > 1000
        for keyframe in result["trajectoryKeyframes"]
    ):
        raise DeterministicEffectContractError(
            "trajectory and scale exceed the output canvas"
        )
    if result["blendMode"] not in BLEND_MODES:
        raise DeterministicEffectContractError("blendMode is invalid")
    _integer(result["layer"], "layer", maximum=1024)
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    return result


def _flat_asset_binding(
    value: Mapping[str, Any],
    prefix: str,
    *,
    allow_none: bool = False,
) -> dict[str, str] | None:
    fields = {
        "assetVersionRef": f"{prefix}AssetVersionRef",
        "assetVersionDigest": f"{prefix}AssetVersionDigest",
        "fileDigest": f"{prefix}FileDigest",
        "pixelDigest": f"{prefix}PixelDigest",
    }
    observed = [value[field] for field in fields.values()]
    if allow_none and all(item is None for item in observed):
        return None
    if any(item is None for item in observed):
        raise DeterministicEffectContractError(
            f"{prefix} AssetVersion binding is incomplete"
        )
    return {
        "assetVersionRef": _ref(
            value[fields["assetVersionRef"]], fields["assetVersionRef"]
        ),
        "assetVersionDigest": _raw_digest(
            value[fields["assetVersionDigest"]],
            fields["assetVersionDigest"],
        ),
        "fileDigest": _content_digest(
            value[fields["fileDigest"]], fields["fileDigest"]
        ),
        "pixelDigest": _content_digest(
            value[fields["pixelDigest"]], fields["pixelDigest"]
        ),
    }


def _flame_state_schedule(
    value: Any, *, start: int, end: int
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) not in {4, 5}:
        raise DeterministicEffectContractError("stateSchedule is invalid")
    result: list[dict[str, Any]] = []
    expected_start = start
    for index, item in enumerate(value):
        current = _closed(
            item, _STATE_SCHEDULE_FIELDS, f"stateSchedule[{index}]"
        )
        segment_start = _integer(
            current["startFrameInclusive"],
            f"stateSchedule[{index}].startFrameInclusive",
        )
        segment_end = _integer(
            current["endFrameExclusive"],
            f"stateSchedule[{index}].endFrameExclusive",
            minimum=1,
            maximum=10_000_001,
        )
        if (
            segment_start != expected_start
            or segment_end <= segment_start
            or segment_end > end
        ):
            raise DeterministicEffectContractError(
                "stateSchedule must cover the range without gaps or overlap"
            )
        if current["state"] not in FLAME_STATES:
            raise DeterministicEffectContractError(
                f"stateSchedule[{index}].state is invalid"
            )
        expected_start = segment_end
        result.append(current)
    states = [item["state"] for item in result]
    if states not in (
        ["LIT", "DIMMING", "EXTINGUISHED", "DARK"],
        ["LIT", "DIMMING", "EXTINGUISHED", "EMBER", "DARK"],
    ) or expected_start != end:
        raise DeterministicEffectContractError(
            "stateSchedule transition order is invalid"
        )
    return result


def _flame_curve(
    value: Any,
    *,
    label: str,
    start: int,
    end: int,
    dark_start: int,
) -> list[dict[str, Any]]:
    result = _keyframes(
        value,
        fields=_INTENSITY_FIELDS,
        label=label,
        value_fields={"valuePermille": (0, 1000)},
        start=start,
        end=end,
    )
    values = [item["valuePermille"] for item in result]
    dark = [item for item in result if item["frame"] >= dark_start]
    if (
        values[0] <= 0
        or any(right > left for left, right in zip(values, values[1:]))
        or not dark
        or dark[0]["frame"] != dark_start
        or any(item["valuePermille"] != 0 for item in dark)
    ):
        raise DeterministicEffectContractError(
            f"{label} must decrease to exact DARK zero"
        )
    return result


def _validate_flame_requirement(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _FLAME_REQUIREMENT_FIELDS, "FlameExtinguishRequirement"
    )
    if result["schemaVersion"] != FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "FlameExtinguishRequirement schema is unsupported"
        )
    if result["effectMode"] != FLAME_EXTINGUISH:
        raise DeterministicEffectContractError("effectMode is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
        "targetShotVersionRef",
        "localExposureRequirementRef",
    ):
        _ref(result[field], field)
    for field in (
        "targetShotVersionDigest",
        "localExposureRequirementDigest",
    ):
        _raw_digest(result[field], field)
    base = _flat_asset_binding(result, "basePlate")
    flame_mask = _flat_asset_binding(result, "flameMask")
    assert base is not None and flame_mask is not None
    if base["assetVersionRef"] == flame_mask["assetVersionRef"]:
        raise DeterministicEffectContractError(
            "base plate and flame mask AssetVersions must be distinct"
        )
    start, end = _frame_range(result)
    result["stateSchedule"] = _flame_state_schedule(
        result["stateSchedule"], start=start, end=end
    )
    dark_start = result["stateSchedule"][-1]["startFrameInclusive"]
    result["brightnessCurve"] = _flame_curve(
        result["brightnessCurve"],
        label="brightnessCurve",
        start=start,
        end=end,
        dark_start=dark_start,
    )
    result["alphaCurve"] = _flame_curve(
        result["alphaCurve"],
        label="alphaCurve",
        start=start,
        end=end,
        dark_start=dark_start,
    )
    if result["blendMode"] not in BLEND_MODES:
        raise DeterministicEffectContractError("blendMode is invalid")
    _integer(result["layer"], "layer", maximum=1024)
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    return result


def _validate_smoke_requirement(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value,
        _SMOKE_REQUIREMENT_FIELDS,
        "SmokeRequirement",
        allowed_forbidden_keys=_SMOKE_ALLOWED_FORBIDDEN_KEYS,
    )
    if result["schemaVersion"] != SMOKE_REQUIREMENT_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "SmokeRequirement schema is unsupported"
        )
    if result["effectMode"] != SMOKE:
        raise DeterministicEffectContractError("effectMode is invalid")
    for field in (
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
        "targetShotVersionRef",
    ):
        _ref(result[field], field)
    _raw_digest(result["targetShotVersionDigest"], "targetShotVersionDigest")
    base = _flat_asset_binding(result, "basePlate")
    emission_mask = _flat_asset_binding(result, "emissionMask")
    assert base is not None and emission_mask is not None
    if base["assetVersionRef"] == emission_mask["assetVersionRef"]:
        raise DeterministicEffectContractError(
            "base plate and emission mask AssetVersions must be distinct"
        )
    source_kind = result["smokeSourceKind"]
    if source_kind not in SMOKE_SOURCE_KINDS:
        raise DeterministicEffectContractError("smokeSourceKind is invalid")
    smoke_layer = _flat_asset_binding(result, "smokeLayer", allow_none=True)
    if source_kind == "PINNED_SMOKE_LAYER":
        if (
            smoke_layer is None
            or any(
                result[field] is not None
                for field in (
                    "algorithmIdentity",
                    "algorithmVersion",
                    "deterministicSeed",
                )
            )
        ):
            raise DeterministicEffectContractError(
                "pinned smoke source binding is invalid"
            )
        if smoke_layer["assetVersionRef"] in {
            base["assetVersionRef"],
            emission_mask["assetVersionRef"],
        }:
            raise DeterministicEffectContractError(
                "smoke layer AssetVersion must be distinct"
            )
    else:
        if (
            smoke_layer is not None
            or result["algorithmIdentity"]
            != DETERMINISTIC_SMOKE_ALGORITHM_IDENTITY
            or result["algorithmVersion"]
            != DETERMINISTIC_SMOKE_ALGORITHM_VERSION
        ):
            raise DeterministicEffectContractError(
                "procedural smoke algorithm binding is invalid"
            )
        _integer(
            result["deterministicSeed"],
            "deterministicSeed",
            maximum=2**63 - 1,
        )
    start, end = _frame_range(result)
    result["opacitySchedule"] = _keyframes(
        result["opacitySchedule"],
        fields=_INTENSITY_FIELDS,
        label="opacitySchedule",
        value_fields={"valuePermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["positionKeyframes"] = _keyframes(
        result["positionKeyframes"],
        fields=_TRAJECTORY_FIELDS,
        label="positionKeyframes",
        value_fields={"xPermille": (0, 1000), "yPermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["scaleKeyframes"] = _keyframes(
        result["scaleKeyframes"],
        fields=_SCALE_KEYFRAME_FIELDS,
        label="scaleKeyframes",
        value_fields={"xPermille": (1, 4000), "yPermille": (1, 4000)},
        start=start,
        end=end,
    )
    result["driftKeyframes"] = _keyframes(
        result["driftKeyframes"],
        fields=_DRIFT_KEYFRAME_FIELDS,
        label="driftKeyframes",
        value_fields={
            "xDeltaPermille": (-4000, 4000),
            "yDeltaPermille": (-4000, 4000),
        },
        start=start,
        end=end,
    )
    result["dissipationCurve"] = _keyframes(
        result["dissipationCurve"],
        fields=_INTENSITY_FIELDS,
        label="dissipationCurve",
        value_fields={"valuePermille": (0, 1000)},
        start=start,
        end=end,
    )
    if result["blendMode"] not in BLEND_MODES:
        raise DeterministicEffectContractError("blendMode is invalid")
    _integer(result["layer"], "layer", maximum=1024)
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    return result


@dataclass(frozen=True, slots=True)
class _ImmutableContract:
    _value: Mapping[str, Any]

    @classmethod
    def _from_validated(cls, value: Mapping[str, Any]):
        return cls(deepcopy(dict(value)))

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(dict(self._value))

    @property
    def payload_digest(self) -> str:
        return str(self._value["payloadDigest"])


@dataclass(frozen=True, slots=True)
class ScratchLightRequirement(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "ScratchLightRequirement":
        return cls._from_validated(
            _validate_requirement(
                value,
                schema_version=SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION,
                modes=SCRATCH_LIGHT_EFFECT_MODES,
                label="ScratchLightRequirement",
            )
        )

    @property
    def requirement_ref(self) -> str:
        return str(self._value["requirementRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])

    @property
    def target_shot_ref(self) -> str:
        return str(self._value["targetShotRef"])

    @property
    def target_shot_version_ref(self) -> str:
        return str(self._value["targetShotVersionRef"])

    @property
    def target_shot_version_digest(self) -> str:
        return str(self._value["targetShotVersionDigest"])

    @property
    def frame_range_start_inclusive(self) -> int:
        return int(self._value["frameRangeStartInclusive"])

    @property
    def frame_range_end_exclusive(self) -> int:
        return int(self._value["frameRangeEndExclusive"])

    @property
    def frame_range(self) -> tuple[int, int]:
        return (
            int(self._value["frameRangeStartInclusive"]),
            int(self._value["frameRangeEndExclusive"]),
        )


@dataclass(frozen=True, slots=True)
class LocalExposureRequirement(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "LocalExposureRequirement":
        return cls._from_validated(
            _validate_requirement(
                value,
                schema_version=LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION,
                modes=frozenset({LOCAL_EXPOSURE}),
                label="LocalExposureRequirement",
            )
        )

    @property
    def requirement_ref(self) -> str:
        return str(self._value["requirementRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])

    @property
    def target_shot_ref(self) -> str:
        return str(self._value["targetShotRef"])

    @property
    def target_shot_version_ref(self) -> str:
        return str(self._value["targetShotVersionRef"])

    @property
    def target_shot_version_digest(self) -> str:
        return str(self._value["targetShotVersionDigest"])

    @property
    def frame_range_start_inclusive(self) -> int:
        return int(self._value["frameRangeStartInclusive"])

    @property
    def frame_range_end_exclusive(self) -> int:
        return int(self._value["frameRangeEndExclusive"])

    @property
    def frame_range(self) -> tuple[int, int]:
        return (
            int(self._value["frameRangeStartInclusive"]),
            int(self._value["frameRangeEndExclusive"]),
        )


@dataclass(frozen=True, slots=True)
class FlameExtinguishRequirement(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "FlameExtinguishRequirement":
        return cls._from_validated(_validate_flame_requirement(value))

    @property
    def requirement_ref(self) -> str:
        return str(self._value["requirementRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])

    @property
    def target_shot_ref(self) -> str:
        return str(self._value["targetShotRef"])

    @property
    def target_shot_version_ref(self) -> str:
        return str(self._value["targetShotVersionRef"])

    @property
    def target_shot_version_digest(self) -> str:
        return str(self._value["targetShotVersionDigest"])

    @property
    def frame_range_start_inclusive(self) -> int:
        return int(self._value["frameRangeStartInclusive"])

    @property
    def frame_range_end_exclusive(self) -> int:
        return int(self._value["frameRangeEndExclusive"])

    @property
    def frame_range(self) -> tuple[int, int]:
        return (
            int(self._value["frameRangeStartInclusive"]),
            int(self._value["frameRangeEndExclusive"]),
        )


@dataclass(frozen=True, slots=True)
class SmokeRequirement(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "SmokeRequirement":
        return cls._from_validated(_validate_smoke_requirement(value))

    @property
    def requirement_ref(self) -> str:
        return str(self._value["requirementRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])

    @property
    def target_shot_ref(self) -> str:
        return str(self._value["targetShotRef"])

    @property
    def target_shot_version_ref(self) -> str:
        return str(self._value["targetShotVersionRef"])

    @property
    def target_shot_version_digest(self) -> str:
        return str(self._value["targetShotVersionDigest"])

    @property
    def frame_range_start_inclusive(self) -> int:
        return int(self._value["frameRangeStartInclusive"])

    @property
    def frame_range_end_exclusive(self) -> int:
        return int(self._value["frameRangeEndExclusive"])

    @property
    def frame_range(self) -> tuple[int, int]:
        return (
            int(self._value["frameRangeStartInclusive"]),
            int(self._value["frameRangeEndExclusive"]),
        )


DeterministicEffectRequirement = (
    ScratchLightRequirement
    | LocalExposureRequirement
    | FlameExtinguishRequirement
    | SmokeRequirement
)


def build_scratch_light_requirement(command: Mapping[str, Any]) -> ScratchLightRequirement:
    value = _closed(command, _REQUIREMENT_COMMAND_FIELDS, "ScratchLightRequirement command")
    return ScratchLightRequirement.from_mapping(
        _seal(
            {
                "schemaVersion": SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION,
                **value,
                "publicationAllowed": False,
            }
        )
    )


def build_local_exposure_requirement(command: Mapping[str, Any]) -> LocalExposureRequirement:
    value = _closed(command, _REQUIREMENT_COMMAND_FIELDS, "LocalExposureRequirement command")
    if value.get("effectMode") != LOCAL_EXPOSURE:
        raise DeterministicEffectContractError(
            "LocalExposureRequirement effectMode is invalid"
        )
    return LocalExposureRequirement.from_mapping(
        _seal(
            {
                "schemaVersion": LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION,
                **value,
                "publicationAllowed": False,
            }
        )
    )


def build_flame_extinguish_requirement(
    command: Mapping[str, Any],
) -> FlameExtinguishRequirement:
    value = _closed(
        command,
        _FLAME_REQUIREMENT_COMMAND_FIELDS,
        "FlameExtinguishRequirement command",
    )
    if value.get("effectMode") != FLAME_EXTINGUISH:
        raise DeterministicEffectContractError(
            "FlameExtinguishRequirement effectMode is invalid"
        )
    return FlameExtinguishRequirement.from_mapping(
        _seal(
            {
                "schemaVersion": FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION,
                **value,
                "publicationAllowed": False,
            }
        )
    )


def build_smoke_requirement(command: Mapping[str, Any]) -> SmokeRequirement:
    value = _closed(
        command,
        _SMOKE_REQUIREMENT_COMMAND_FIELDS,
        "SmokeRequirement command",
        allowed_forbidden_keys=_SMOKE_ALLOWED_FORBIDDEN_KEYS,
    )
    if value.get("effectMode") != SMOKE:
        raise DeterministicEffectContractError(
            "SmokeRequirement effectMode is invalid"
        )
    return SmokeRequirement.from_mapping(
        _seal(
            {
                "schemaVersion": SMOKE_REQUIREMENT_SCHEMA_VERSION,
                **value,
                "publicationAllowed": False,
            },
            allowed_forbidden_keys=_SMOKE_ALLOWED_FORBIDDEN_KEYS,
        )
    )


def parse_deterministic_effect_requirement(value: Any) -> DeterministicEffectRequirement:
    if not isinstance(value, Mapping):
        raise DeterministicEffectContractError("Requirement must be an object")
    schema = value.get("schemaVersion")
    if schema == SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION:
        return ScratchLightRequirement.from_mapping(value)
    if schema == LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION:
        return LocalExposureRequirement.from_mapping(value)
    if schema == FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION:
        return FlameExtinguishRequirement.from_mapping(value)
    if schema == SMOKE_REQUIREMENT_SCHEMA_VERSION:
        return SmokeRequirement.from_mapping(value)
    raise DeterministicEffectContractError("Requirement schema is unsupported")


def _requirement_kind(
    requirement: DeterministicEffectRequirement,
) -> str:
    if type(requirement) is ScratchLightRequirement:
        return SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND
    if type(requirement) is LocalExposureRequirement:
        return LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND
    if type(requirement) is FlameExtinguishRequirement:
        return FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND
    if type(requirement) is SmokeRequirement:
        return SMOKE_REQUIREMENT_RECORD_KIND
    raise DeterministicEffectContractError(
        "an exact deterministic effect Requirement wrapper is required"
    )


def validate_flame_local_exposure_compatibility(
    flame_requirement: FlameExtinguishRequirement | Mapping[str, Any],
    local_exposure_requirement: LocalExposureRequirement | Mapping[str, Any],
    local_exposure_result: "LocalExposureResult | Mapping[str, Any] | None" = None,
) -> tuple[LocalExposureRequirement, "LocalExposureResult | None"]:
    flame = (
        FlameExtinguishRequirement.from_mapping(flame_requirement)
        if isinstance(flame_requirement, Mapping)
        else flame_requirement
    )
    exposure = (
        LocalExposureRequirement.from_mapping(local_exposure_requirement)
        if isinstance(local_exposure_requirement, Mapping)
        else local_exposure_requirement
    )
    if type(flame) is not FlameExtinguishRequirement or type(
        exposure
    ) is not LocalExposureRequirement:
        raise DeterministicEffectContractError(
            "exact Flame and LocalExposure Requirement wrappers are required"
        )
    flame_value = flame.as_dict()
    exposure_value = exposure.as_dict()
    exact_fields = {
        "workspaceRef": "workspaceRef",
        "productionRunRef": "productionRunRef",
        "targetShotRef": "targetShotRef",
        "targetShotVersionRef": "targetShotVersionRef",
        "targetShotVersionDigest": "targetShotVersionDigest",
        "basePlateAssetVersionRef": "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest": "basePlateAssetVersionDigest",
        "basePlateFileDigest": "basePlateFileDigest",
        "basePlatePixelDigest": "basePlatePixelDigest",
        "frameRangeStartInclusive": "frameRangeStartInclusive",
        "frameRangeEndExclusive": "frameRangeEndExclusive",
        "flameMaskAssetVersionRef": "maskAssetVersionRef",
        "flameMaskAssetVersionDigest": "maskAssetVersionDigest",
        "flameMaskFileDigest": "maskFileDigest",
        "flameMaskPixelDigest": "maskPixelDigest",
    }
    if (
        flame_value["localExposureRequirementRef"]
        != exposure_value["requirementRef"]
        or flame_value["localExposureRequirementDigest"]
        != exposure_value["payloadDigest"]
        or any(
            flame_value[flame_field] != exposure_value[exposure_field]
            for flame_field, exposure_field in exact_fields.items()
        )
        or exposure_value["effectMode"] != LOCAL_EXPOSURE
        or exposure_value["exposureCurve"][-1]["valueMilliStops"] >= 0
    ):
        raise DeterministicEffectStaleInputError(
            "Flame LocalExposure Requirement binding is stale"
        )
    if local_exposure_result is None:
        return exposure, None
    parsed_result = (
        LocalExposureResult.from_mapping(local_exposure_result)
        if isinstance(local_exposure_result, Mapping)
        else local_exposure_result
    )
    if type(parsed_result) is not LocalExposureResult:
        raise DeterministicEffectContractError(
            "an exact LocalExposureResult wrapper is required"
        )
    result_value = parsed_result.as_dict()
    if (
        result_value["workspaceRef"] != exposure_value["workspaceRef"]
        or result_value["productionRunRef"]
        != exposure_value["productionRunRef"]
        or result_value["requirementRef"]
        != exposure_value["requirementRef"]
        or result_value["requirementDigest"]
        != exposure_value["payloadDigest"]
    ):
        raise DeterministicEffectStaleInputError(
            "Flame LocalExposure Result binding is stale"
        )
    return exposure, parsed_result


def _execution_request_ref(requirement_ref: str, requirement_digest: str) -> str:
    identity_digest = _digest(
        {
            "schemaVersion": (
                "v5.m13-masked-surface-execution-request-identity.v1"
            ),
            "requirementRef": _ref(requirement_ref, "requirementRef"),
            "requirementDigest": _raw_digest(
                requirement_digest, "requirementDigest"
            ),
        }
    )
    return "m13-masked-surface-execution-" + identity_digest[:32]


def masked_surface_execution_request_ref(
    requirement_ref: str, requirement_digest: str
) -> str:
    """Return the deterministic public execution-request identity."""

    return _execution_request_ref(requirement_ref, requirement_digest)


def _flame_smoke_execution_request_ref(
    *,
    effect_mode: str,
    requirement_ref: str,
    requirement_digest: str,
    local_exposure_result_ref: str | None,
    local_exposure_result_digest: str | None,
) -> str:
    if effect_mode not in FLAME_SMOKE_EFFECT_MODES:
        raise DeterministicEffectContractError("effectMode is invalid")
    if effect_mode == FLAME_EXTINGUISH:
        exposure_ref = _ref(
            local_exposure_result_ref, "localExposureResultRef"
        )
        exposure_digest = _raw_digest(
            local_exposure_result_digest, "localExposureResultDigest"
        )
        prefix = "m13-flame-extinguish-execution-"
    else:
        if (
            local_exposure_result_ref is not None
            or local_exposure_result_digest is not None
        ):
            raise DeterministicEffectContractError(
                "Smoke execution cannot bind LocalExposure Result"
            )
        exposure_ref = None
        exposure_digest = None
        prefix = "m13-smoke-execution-"
    identity_digest = _digest(
        {
            "schemaVersion": (
                "v5.m13-flame-smoke-execution-request-identity.v1"
            ),
            "effectMode": effect_mode,
            "requirementRef": _ref(requirement_ref, "requirementRef"),
            "requirementDigest": _raw_digest(
                requirement_digest, "requirementDigest"
            ),
            "localExposureResultRef": exposure_ref,
            "localExposureResultDigest": exposure_digest,
        }
    )
    return prefix + identity_digest[:32]


def flame_smoke_execution_request_ref(
    *,
    effect_mode: str,
    requirement_ref: str,
    requirement_digest: str,
    local_exposure_result_ref: str | None = None,
    local_exposure_result_digest: str | None = None,
) -> str:
    """Return the deterministic public E2 execution-request identity."""

    return _flame_smoke_execution_request_ref(
        effect_mode=effect_mode,
        requirement_ref=requirement_ref,
        requirement_digest=requirement_digest,
        local_exposure_result_ref=local_exposure_result_ref,
        local_exposure_result_digest=local_exposure_result_digest,
    )


def _asset_binding(value: Any, label: str) -> dict[str, str]:
    result = _closed(value, _ASSET_BINDING_FIELDS, label)
    return {
        "assetVersionRef": _ref(
            result["assetVersionRef"], f"{label}.assetVersionRef"
        ),
        "assetVersionDigest": _raw_digest(
            result["assetVersionDigest"], f"{label}.assetVersionDigest"
        ),
        "fileDigest": _content_digest(
            result["fileDigest"], f"{label}.fileDigest"
        ),
        "pixelDigest": _content_digest(
            result["pixelDigest"], f"{label}.pixelDigest"
        ),
    }


def _validate_execution_request(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _EXECUTION_REQUEST_FIELDS, "MaskedSurfaceExecutionRequest"
    )
    if result["schemaVersion"] != MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "MaskedSurfaceExecutionRequest schema is unsupported"
        )
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _ref(result[field], field)
    _raw_digest(result["requirementDigest"], "requirementDigest")
    expected_ref = _execution_request_ref(
        result["requirementRef"], result["requirementDigest"]
    )
    if result["executionRequestRef"] != expected_ref:
        raise DeterministicEffectStaleInputError(
            "executionRequestRef does not match the Requirement"
        )
    mode = result["effectMode"]
    if mode not in MASKED_SURFACE_EFFECT_MODES:
        raise DeterministicEffectContractError("effectMode is invalid")
    expected_schema = (
        LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION
        if mode == LOCAL_EXPOSURE
        else SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION
    )
    if result["requirementSchemaVersion"] != expected_schema:
        raise DeterministicEffectContractError(
            "execution request Requirement schema is invalid"
        )
    shot = _closed(result["targetShot"], _SHOT_BINDING_FIELDS, "targetShot")
    result["targetShot"] = {
        "shotRef": _ref(shot["shotRef"], "targetShot.shotRef"),
        "shotVersionRef": _ref(
            shot["shotVersionRef"], "targetShot.shotVersionRef"
        ),
        "shotVersionDigest": _raw_digest(
            shot["shotVersionDigest"], "targetShot.shotVersionDigest"
        ),
    }
    result["basePlate"] = _asset_binding(result["basePlate"], "basePlate")
    result["mask"] = _asset_binding(result["mask"], "mask")
    if result["basePlate"]["assetVersionRef"] == result["mask"]["assetVersionRef"]:
        raise DeterministicEffectContractError(
            "base plate and mask AssetVersions must be distinct"
        )
    start, end = _frame_range(result)
    result["explicitSchedule"] = _schedule(
        result["explicitSchedule"], start=start, end=end
    )
    result["trajectoryKeyframes"] = _keyframes(
        result["trajectoryKeyframes"],
        fields=_TRAJECTORY_FIELDS,
        label="trajectoryKeyframes",
        value_fields={"xPermille": (0, 1000), "yPermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["intensityCurve"] = _keyframes(
        result["intensityCurve"],
        fields=_INTENSITY_FIELDS,
        label="intensityCurve",
        value_fields={"valuePermille": (0, 1000)},
        start=start,
        end=end,
    )
    result["exposureCurve"] = _keyframes(
        result["exposureCurve"],
        fields=_EXPOSURE_FIELDS,
        label="exposureCurve",
        value_fields={"valueMilliStops": (-8000, 8000)},
        start=start,
        end=end,
    )
    result["position"] = _position(result["position"])
    result["scale"] = _scale(result["scale"])
    result["perspective"] = _perspective(result["perspective"])
    first = result["trajectoryKeyframes"][0]
    if (
        first["xPermille"] != result["position"]["xPermille"]
        or first["yPermille"] != result["position"]["yPermille"]
    ):
        raise DeterministicEffectContractError(
            "position must equal the first trajectory keyframe"
        )
    if any(
        keyframe["xPermille"] + result["scale"]["xPermille"] > 1000
        or keyframe["yPermille"] + result["scale"]["yPermille"] > 1000
        for keyframe in result["trajectoryKeyframes"]
    ):
        raise DeterministicEffectContractError(
            "trajectory and scale exceed the output canvas"
        )
    if result["blendMode"] not in BLEND_MODES:
        raise DeterministicEffectContractError("blendMode is invalid")
    _integer(result["layer"], "layer", maximum=1024)
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    return result


def _validate_flame_smoke_execution_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DeterministicEffectContractError(
            "FlameSmokeExecutionRequest must be an object"
        )
    mode = value.get("effectMode")
    if mode == FLAME_EXTINGUISH:
        fields = _FLAME_EXECUTION_REQUEST_FIELDS
        allowed_forbidden_keys = frozenset()
    elif mode == SMOKE:
        fields = _SMOKE_EXECUTION_REQUEST_FIELDS
        allowed_forbidden_keys = _SMOKE_ALLOWED_FORBIDDEN_KEYS
    else:
        raise DeterministicEffectContractError("effectMode is invalid")
    result = _verify_sealed(
        value,
        fields,
        "FlameSmokeExecutionRequest",
        allowed_forbidden_keys=allowed_forbidden_keys,
    )
    if result["schemaVersion"] != FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "FlameSmokeExecutionRequest schema is unsupported"
        )
    expected_requirement_schema = (
        FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION
        if mode == FLAME_EXTINGUISH
        else SMOKE_REQUIREMENT_SCHEMA_VERSION
    )
    if result["requirementSchemaVersion"] != expected_requirement_schema:
        raise DeterministicEffectContractError(
            "execution request Requirement schema is invalid"
        )
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _ref(result[field], field)
    _raw_digest(result["requirementDigest"], "requirementDigest")
    shot = _closed(result["targetShot"], _SHOT_BINDING_FIELDS, "targetShot")
    result["targetShot"] = {
        "shotRef": _ref(shot["shotRef"], "targetShot.shotRef"),
        "shotVersionRef": _ref(
            shot["shotVersionRef"], "targetShot.shotVersionRef"
        ),
        "shotVersionDigest": _raw_digest(
            shot["shotVersionDigest"], "targetShot.shotVersionDigest"
        ),
    }
    result["basePlate"] = _asset_binding(result["basePlate"], "basePlate")
    common = {
        "schemaVersion": result["requirementSchemaVersion"],
        "workspaceRef": result["workspaceRef"],
        "productionRunRef": result["productionRunRef"],
        "requirementRef": result["requirementRef"],
        "effectMode": mode,
        "targetShotRef": result["targetShot"]["shotRef"],
        "targetShotVersionRef": result["targetShot"]["shotVersionRef"],
        "targetShotVersionDigest": result["targetShot"][
            "shotVersionDigest"
        ],
        "basePlateAssetVersionRef": result["basePlate"]["assetVersionRef"],
        "basePlateAssetVersionDigest": result["basePlate"][
            "assetVersionDigest"
        ],
        "basePlateFileDigest": result["basePlate"]["fileDigest"],
        "basePlatePixelDigest": result["basePlate"]["pixelDigest"],
        "frameRangeStartInclusive": result["frameRangeStartInclusive"],
        "frameRangeEndExclusive": result["frameRangeEndExclusive"],
        "blendMode": result["blendMode"],
        "layer": result["layer"],
        "publicationAllowed": result["publicationAllowed"],
        "payloadDigest": result["requirementDigest"],
    }
    if mode == FLAME_EXTINGUISH:
        result["flameMask"] = _asset_binding(
            result["flameMask"], "flameMask"
        )
        for field in (
            "localExposureRequirementRef",
            "localExposureResultRef",
        ):
            _ref(result[field], field)
        for field in (
            "localExposureRequirementDigest",
            "localExposureResultDigest",
        ):
            _raw_digest(result[field], field)
        requirement_mapping = {
            **common,
            "flameMaskAssetVersionRef": result["flameMask"][
                "assetVersionRef"
            ],
            "flameMaskAssetVersionDigest": result["flameMask"][
                "assetVersionDigest"
            ],
            "flameMaskFileDigest": result["flameMask"]["fileDigest"],
            "flameMaskPixelDigest": result["flameMask"]["pixelDigest"],
            "stateSchedule": result["stateSchedule"],
            "brightnessCurve": result["brightnessCurve"],
            "alphaCurve": result["alphaCurve"],
            "localExposureRequirementRef": result[
                "localExposureRequirementRef"
            ],
            "localExposureRequirementDigest": result[
                "localExposureRequirementDigest"
            ],
        }
        FlameExtinguishRequirement.from_mapping(requirement_mapping)
        exposure_ref = result["localExposureResultRef"]
        exposure_digest = result["localExposureResultDigest"]
    else:
        if result["smokeLayer"] is not None:
            result["smokeLayer"] = _asset_binding(
                result["smokeLayer"], "smokeLayer"
            )
        result["emissionMask"] = _asset_binding(
            result["emissionMask"], "emissionMask"
        )
        smoke_layer = result["smokeLayer"]
        requirement_mapping = {
            **common,
            "smokeSourceKind": result["smokeSourceKind"],
            "smokeLayerAssetVersionRef": (
                None if smoke_layer is None else smoke_layer["assetVersionRef"]
            ),
            "smokeLayerAssetVersionDigest": (
                None
                if smoke_layer is None
                else smoke_layer["assetVersionDigest"]
            ),
            "smokeLayerFileDigest": (
                None if smoke_layer is None else smoke_layer["fileDigest"]
            ),
            "smokeLayerPixelDigest": (
                None if smoke_layer is None else smoke_layer["pixelDigest"]
            ),
            "emissionMaskAssetVersionRef": result["emissionMask"][
                "assetVersionRef"
            ],
            "emissionMaskAssetVersionDigest": result["emissionMask"][
                "assetVersionDigest"
            ],
            "emissionMaskFileDigest": result["emissionMask"]["fileDigest"],
            "emissionMaskPixelDigest": result["emissionMask"]["pixelDigest"],
            "opacitySchedule": result["opacitySchedule"],
            "positionKeyframes": result["positionKeyframes"],
            "scaleKeyframes": result["scaleKeyframes"],
            "driftKeyframes": result["driftKeyframes"],
            "dissipationCurve": result["dissipationCurve"],
            "algorithmIdentity": result["algorithmIdentity"],
            "algorithmVersion": result["algorithmVersion"],
            "deterministicSeed": result["deterministicSeed"],
        }
        SmokeRequirement.from_mapping(requirement_mapping)
        exposure_ref = None
        exposure_digest = None
    expected_ref = _flame_smoke_execution_request_ref(
        effect_mode=mode,
        requirement_ref=result["requirementRef"],
        requirement_digest=result["requirementDigest"],
        local_exposure_result_ref=exposure_ref,
        local_exposure_result_digest=exposure_digest,
    )
    if result["executionRequestRef"] != expected_ref:
        raise DeterministicEffectStaleInputError(
            "executionRequestRef does not match the Requirement"
        )
    return result


@dataclass(frozen=True, slots=True)
class MaskedSurfaceExecutionRequest(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MaskedSurfaceExecutionRequest":
        return cls._from_validated(_validate_execution_request(value))

    @property
    def execution_request_ref(self) -> str:
        return str(self._value["executionRequestRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


@dataclass(frozen=True, slots=True)
class FlameSmokeExecutionRequest(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "FlameSmokeExecutionRequest":
        return cls._from_validated(
            _validate_flame_smoke_execution_request(value)
        )

    @property
    def execution_request_ref(self) -> str:
        return str(self._value["executionRequestRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


DeterministicEffectExecutionRequest = (
    MaskedSurfaceExecutionRequest | FlameSmokeExecutionRequest
)


def build_masked_surface_execution_request(
    requirement: DeterministicEffectRequirement,
) -> MaskedSurfaceExecutionRequest:
    if type(requirement) not in {ScratchLightRequirement, LocalExposureRequirement}:
        raise DeterministicEffectContractError(
            "an exact deterministic effect Requirement wrapper is required"
        )
    source = parse_deterministic_effect_requirement(requirement.as_dict()).as_dict()
    request = {
        "schemaVersion": MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION,
        "executionRequestRef": _execution_request_ref(
            source["requirementRef"], source["payloadDigest"]
        ),
        "workspaceRef": source["workspaceRef"],
        "productionRunRef": source["productionRunRef"],
        "requirementSchemaVersion": source["schemaVersion"],
        "requirementRef": source["requirementRef"],
        "requirementDigest": source["payloadDigest"],
        "effectMode": source["effectMode"],
        "targetShot": {
            "shotRef": source["targetShotRef"],
            "shotVersionRef": source["targetShotVersionRef"],
            "shotVersionDigest": source["targetShotVersionDigest"],
        },
        "basePlate": {
            "assetVersionRef": source["basePlateAssetVersionRef"],
            "assetVersionDigest": source["basePlateAssetVersionDigest"],
            "fileDigest": source["basePlateFileDigest"],
            "pixelDigest": source["basePlatePixelDigest"],
        },
        "mask": {
            "assetVersionRef": source["maskAssetVersionRef"],
            "assetVersionDigest": source["maskAssetVersionDigest"],
            "fileDigest": source["maskFileDigest"],
            "pixelDigest": source["maskPixelDigest"],
        },
        "frameRangeStartInclusive": source["frameRangeStartInclusive"],
        "frameRangeEndExclusive": source["frameRangeEndExclusive"],
        "explicitSchedule": source["explicitSchedule"],
        "trajectoryKeyframes": source["trajectoryKeyframes"],
        "intensityCurve": source["intensityCurve"],
        "exposureCurve": source["exposureCurve"],
        "position": source["position"],
        "scale": source["scale"],
        "perspective": source["perspective"],
        "blendMode": source["blendMode"],
        "layer": source["layer"],
        "publicationAllowed": False,
    }
    return MaskedSurfaceExecutionRequest.from_mapping(_seal(request))


def validate_masked_surface_execution_request_binding(
    execution_request: MaskedSurfaceExecutionRequest | Mapping[str, Any],
    requirement: DeterministicEffectRequirement | Mapping[str, Any],
) -> MaskedSurfaceExecutionRequest:
    parsed_requirement = (
        parse_deterministic_effect_requirement(requirement)
        if isinstance(requirement, Mapping)
        else requirement
    )
    if type(parsed_requirement) not in {
        ScratchLightRequirement,
        LocalExposureRequirement,
    }:
        raise DeterministicEffectContractError(
            "an exact deterministic effect Requirement wrapper is required"
        )
    parsed_request = (
        MaskedSurfaceExecutionRequest.from_mapping(execution_request)
        if isinstance(execution_request, Mapping)
        else execution_request
    )
    if type(parsed_request) is not MaskedSurfaceExecutionRequest:
        raise DeterministicEffectContractError(
            "an exact MaskedSurfaceExecutionRequest wrapper is required"
        )
    expected = build_masked_surface_execution_request(parsed_requirement)
    if parsed_request.as_dict() != expected.as_dict():
        raise DeterministicEffectStaleInputError(
            "execution request is not the exact Requirement projection"
        )
    return parsed_request


def build_flame_smoke_execution_request(
    requirement: FlameExtinguishRequirement | SmokeRequirement,
    *,
    local_exposure_requirement: LocalExposureRequirement | None = None,
    local_exposure_result: "LocalExposureResult | None" = None,
) -> FlameSmokeExecutionRequest:
    if type(requirement) not in {
        FlameExtinguishRequirement,
        SmokeRequirement,
    }:
        raise DeterministicEffectContractError(
            "an exact E2 Requirement wrapper is required"
        )
    source = parse_deterministic_effect_requirement(
        requirement.as_dict()
    ).as_dict()
    mode = source["effectMode"]
    request: dict[str, Any] = {
        "schemaVersion": FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION,
        "workspaceRef": source["workspaceRef"],
        "productionRunRef": source["productionRunRef"],
        "requirementSchemaVersion": source["schemaVersion"],
        "requirementRef": source["requirementRef"],
        "requirementDigest": source["payloadDigest"],
        "effectMode": mode,
        "targetShot": {
            "shotRef": source["targetShotRef"],
            "shotVersionRef": source["targetShotVersionRef"],
            "shotVersionDigest": source["targetShotVersionDigest"],
        },
        "basePlate": {
            "assetVersionRef": source["basePlateAssetVersionRef"],
            "assetVersionDigest": source["basePlateAssetVersionDigest"],
            "fileDigest": source["basePlateFileDigest"],
            "pixelDigest": source["basePlatePixelDigest"],
        },
        "frameRangeStartInclusive": source["frameRangeStartInclusive"],
        "frameRangeEndExclusive": source["frameRangeEndExclusive"],
        "blendMode": source["blendMode"],
        "layer": source["layer"],
        "publicationAllowed": False,
    }
    if mode == FLAME_EXTINGUISH:
        exposure_requirement, exposure_result = (
            validate_flame_local_exposure_compatibility(
                requirement,
                local_exposure_requirement,
                local_exposure_result,
            )
        )
        if exposure_result is None:
            raise DeterministicEffectContractError(
                "Flame execution requires an exact LocalExposure Result"
            )
        exposure_result_value = exposure_result.as_dict()
        request.update(
            {
                "flameMask": {
                    "assetVersionRef": source[
                        "flameMaskAssetVersionRef"
                    ],
                    "assetVersionDigest": source[
                        "flameMaskAssetVersionDigest"
                    ],
                    "fileDigest": source["flameMaskFileDigest"],
                    "pixelDigest": source["flameMaskPixelDigest"],
                },
                "stateSchedule": source["stateSchedule"],
                "brightnessCurve": source["brightnessCurve"],
                "alphaCurve": source["alphaCurve"],
                "localExposureRequirementRef": exposure_requirement.requirement_ref,
                "localExposureRequirementDigest": exposure_requirement.payload_digest,
                "localExposureResultRef": exposure_result.result_ref,
                "localExposureResultDigest": exposure_result.payload_digest,
            }
        )
        exposure_ref = exposure_result_value["resultRef"]
        exposure_digest = exposure_result_value["payloadDigest"]
        allowed_forbidden_keys = frozenset()
    else:
        if (
            local_exposure_requirement is not None
            or local_exposure_result is not None
        ):
            raise DeterministicEffectContractError(
                "Smoke execution cannot bind LocalExposure authority"
            )
        smoke_layer = (
            None
            if source["smokeLayerAssetVersionRef"] is None
            else {
                "assetVersionRef": source["smokeLayerAssetVersionRef"],
                "assetVersionDigest": source[
                    "smokeLayerAssetVersionDigest"
                ],
                "fileDigest": source["smokeLayerFileDigest"],
                "pixelDigest": source["smokeLayerPixelDigest"],
            }
        )
        request.update(
            {
                "smokeSourceKind": source["smokeSourceKind"],
                "smokeLayer": smoke_layer,
                "emissionMask": {
                    "assetVersionRef": source[
                        "emissionMaskAssetVersionRef"
                    ],
                    "assetVersionDigest": source[
                        "emissionMaskAssetVersionDigest"
                    ],
                    "fileDigest": source["emissionMaskFileDigest"],
                    "pixelDigest": source["emissionMaskPixelDigest"],
                },
                "opacitySchedule": source["opacitySchedule"],
                "positionKeyframes": source["positionKeyframes"],
                "scaleKeyframes": source["scaleKeyframes"],
                "driftKeyframes": source["driftKeyframes"],
                "dissipationCurve": source["dissipationCurve"],
                "algorithmIdentity": source["algorithmIdentity"],
                "algorithmVersion": source["algorithmVersion"],
                "deterministicSeed": source["deterministicSeed"],
            }
        )
        exposure_ref = None
        exposure_digest = None
        allowed_forbidden_keys = _SMOKE_ALLOWED_FORBIDDEN_KEYS
    request["executionRequestRef"] = _flame_smoke_execution_request_ref(
        effect_mode=mode,
        requirement_ref=source["requirementRef"],
        requirement_digest=source["payloadDigest"],
        local_exposure_result_ref=exposure_ref,
        local_exposure_result_digest=exposure_digest,
    )
    return FlameSmokeExecutionRequest.from_mapping(
        _seal(
            request,
            allowed_forbidden_keys=allowed_forbidden_keys,
        )
    )


def parse_deterministic_effect_execution_request(
    value: Any,
) -> DeterministicEffectExecutionRequest:
    if not isinstance(value, Mapping):
        raise DeterministicEffectContractError(
            "execution request must be an object"
        )
    schema = value.get("schemaVersion")
    if schema == MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION:
        return MaskedSurfaceExecutionRequest.from_mapping(value)
    if schema == FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION:
        return FlameSmokeExecutionRequest.from_mapping(value)
    raise DeterministicEffectContractError(
        "execution request schema is unsupported"
    )


def validate_deterministic_effect_execution_request_binding(
    execution_request: DeterministicEffectExecutionRequest | Mapping[str, Any],
    requirement: DeterministicEffectRequirement | Mapping[str, Any],
    *,
    local_exposure_requirement: LocalExposureRequirement | None = None,
    local_exposure_result: "LocalExposureResult | None" = None,
) -> DeterministicEffectExecutionRequest:
    parsed_requirement = (
        parse_deterministic_effect_requirement(requirement)
        if isinstance(requirement, Mapping)
        else requirement
    )
    parsed_request = (
        parse_deterministic_effect_execution_request(execution_request)
        if isinstance(execution_request, Mapping)
        else execution_request
    )
    if type(parsed_requirement) in {
        ScratchLightRequirement,
        LocalExposureRequirement,
    }:
        if (
            local_exposure_requirement is not None
            or local_exposure_result is not None
        ):
            raise DeterministicEffectContractError(
                "E1 execution cannot bind E2 dependencies"
            )
        return validate_masked_surface_execution_request_binding(
            parsed_request, parsed_requirement
        )
    if type(parsed_requirement) not in {
        FlameExtinguishRequirement,
        SmokeRequirement,
    } or type(parsed_request) is not FlameSmokeExecutionRequest:
        raise DeterministicEffectContractError(
            "matching exact deterministic effect wrappers are required"
        )
    expected = build_flame_smoke_execution_request(
        parsed_requirement,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    if parsed_request.as_dict() != expected.as_dict():
        raise DeterministicEffectStaleInputError(
            "execution request is not the exact Requirement projection"
        )
    return parsed_request


def _runtime_evidence_ref(value: Mapping[str, Any]) -> str:
    return "m13-masked-surface-runtime-evidence-" + _digest(
        {
            "v3ExecutionRequestDigest": value["v3ExecutionRequestDigest"],
            "rendererIdentity": value["rendererIdentity"],
            "rendererVersion": value["rendererVersion"],
            "ffmpegIdentity": value["ffmpegIdentity"],
        }
    )[:32]


def _artifact_evidence_ref(value: Mapping[str, Any]) -> str:
    output = value["outputDigest"]
    return "m13-masked-surface-artifact-evidence-" + _digest(
        {
            "v3ExecutionRequestDigest": value["v3ExecutionRequestDigest"],
            "fileDigest": output["fileDigest"],
            "runtimeEvidenceDigest": value["runtimeEvidenceDigest"],
        }
    )[:32]


def _validate_runtime_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _RUNTIME_EVIDENCE_FIELDS, "MaskedSurfaceRuntimeEvidence"
    )
    if result["schemaVersion"] != MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "MaskedSurfaceRuntimeEvidence schema is unsupported"
        )
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
        _raw_digest(result[field], field)
    if result["effectMode"] not in DETERMINISTIC_EFFECT_MODES:
        raise DeterministicEffectContractError("effectMode is invalid")
    for field in ("rendererIdentity", "rendererVersion", "ffmpegIdentity"):
        _text(result[field], field)
    if (
        result["rendererIdentity"] != MASKED_SURFACE_RENDERER_IDENTITY
        or result["rendererVersion"] != MASKED_SURFACE_RENDERER_VERSION
    ):
        raise DeterministicEffectContractError(
            "masked-surface renderer identity is invalid"
        )
    if result["gpuUsed"] is not False:
        raise DeterministicEffectContractError("gpuUsed must be false")
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    if result["runtimeEvidenceRef"] != _runtime_evidence_ref(result):
        raise DeterministicEffectStaleInputError(
            "runtimeEvidenceRef does not match runtime facts"
        )
    return result


@dataclass(frozen=True, slots=True)
class MaskedSurfaceRuntimeEvidence(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MaskedSurfaceRuntimeEvidence":
        return cls._from_validated(_validate_runtime_evidence(value))

    @property
    def runtime_evidence_ref(self) -> str:
        return str(self._value["runtimeEvidenceRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])


def _output_probe(value: Any) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_MEDIA_PROBE_FIELDS, "outputMediaProbe")
    normalized = {
        "width": _integer(result["width"], "outputMediaProbe.width", minimum=1, maximum=131_072),
        "height": _integer(result["height"], "outputMediaProbe.height", minimum=1, maximum=131_072),
        "frameCount": _integer(result["frameCount"], "outputMediaProbe.frameCount", minimum=1, maximum=10_000_001),
        "frameRate": _integer(result["frameRate"], "outputMediaProbe.frameRate", minimum=1, maximum=1_000),
        "pixelFormat": result["pixelFormat"],
        "container": result["container"],
        "videoCodec": result["videoCodec"],
    }
    if (
        normalized["pixelFormat"] != "yuv420p"
        or normalized["container"] != "mp4"
        or normalized["videoCodec"] != "h264"
    ):
        raise DeterministicEffectContractError(
            "outputMediaProbe codec contract is invalid"
        )
    return normalized


def _output_digest(value: Any) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_DIGEST_FIELDS, "outputDigest")
    normalized = {
        "fileDigest": _content_digest(result["fileDigest"], "outputDigest.fileDigest"),
        "fileDigestAlgorithm": result["fileDigestAlgorithm"],
        "decodedFramePixelDigest": _content_digest(
            result["decodedFramePixelDigest"],
            "outputDigest.decodedFramePixelDigest",
        ),
        "decodedFramePixelDigestSpec": result["decodedFramePixelDigestSpec"],
        "pixelMode": result["pixelMode"],
        "width": _integer(result["width"], "outputDigest.width", minimum=1, maximum=131_072),
        "height": _integer(result["height"], "outputDigest.height", minimum=1, maximum=131_072),
        "frameCount": _integer(result["frameCount"], "outputDigest.frameCount", minimum=1, maximum=10_000_001),
        "frameRate": _integer(result["frameRate"], "outputDigest.frameRate", minimum=1, maximum=1_000),
    }
    if (
        normalized["fileDigestAlgorithm"] != "sha256"
        or normalized["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC
        or normalized["pixelMode"] != "RGBA"
    ):
        raise DeterministicEffectContractError(
            "outputDigest algorithm/spec is invalid"
        )
    return normalized


def _validate_artifact_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _ARTIFACT_EVIDENCE_FIELDS, "MaskedSurfaceArtifactEvidence"
    )
    if result["schemaVersion"] != MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION:
        raise DeterministicEffectContractError(
            "MaskedSurfaceArtifactEvidence schema is unsupported"
        )
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
    ):
        _raw_digest(result[field], field)
    if result["effectMode"] not in DETERMINISTIC_EFFECT_MODES:
        raise DeterministicEffectContractError("effectMode is invalid")
    _integer(
        result["outputByteSize"],
        "outputByteSize",
        minimum=1,
        maximum=10**13,
    )
    result["outputMediaProbe"] = _output_probe(result["outputMediaProbe"])
    result["outputDigest"] = _output_digest(result["outputDigest"])
    probe = result["outputMediaProbe"]
    digest = result["outputDigest"]
    if any(
        probe[field] != digest[field]
        for field in ("width", "height", "frameCount", "frameRate")
    ):
        raise DeterministicEffectStaleInputError(
            "output digest facts do not match the media probe"
        )
    if result["provenance"] != LOCAL_EVIDENCE_PROVENANCE:
        raise DeterministicEffectContractError("artifact provenance is invalid")
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    if result["artifactEvidenceRef"] != _artifact_evidence_ref(result):
        raise DeterministicEffectStaleInputError(
            "artifactEvidenceRef does not match artifact facts"
        )
    return result


@dataclass(frozen=True, slots=True)
class MaskedSurfaceArtifactEvidence(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "MaskedSurfaceArtifactEvidence":
        return cls._from_validated(_validate_artifact_evidence(value))

    @property
    def artifact_evidence_ref(self) -> str:
        return str(self._value["artifactEvidenceRef"])

    @property
    def workspace_ref(self) -> str:
        return str(self._value["workspaceRef"])

    @property
    def production_run_ref(self) -> str:
        return str(self._value["productionRunRef"])


def validate_masked_surface_execution_evidence(
    *,
    requirement: DeterministicEffectRequirement | Mapping[str, Any],
    execution_request: DeterministicEffectExecutionRequest | Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any],
    runtime_evidence: MaskedSurfaceRuntimeEvidence | Mapping[str, Any],
    local_exposure_requirement: LocalExposureRequirement | None = None,
    local_exposure_result: "LocalExposureResult | None" = None,
) -> tuple[MaskedSurfaceArtifactEvidence, MaskedSurfaceRuntimeEvidence]:
    parsed_requirement = (
        parse_deterministic_effect_requirement(requirement)
        if isinstance(requirement, Mapping)
        else requirement
    )
    parsed_request = validate_deterministic_effect_execution_request_binding(
        execution_request,
        parsed_requirement,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    parsed_artifact = (
        MaskedSurfaceArtifactEvidence.from_mapping(artifact_evidence)
        if isinstance(artifact_evidence, Mapping)
        else artifact_evidence
    )
    parsed_runtime = (
        MaskedSurfaceRuntimeEvidence.from_mapping(runtime_evidence)
        if isinstance(runtime_evidence, Mapping)
        else runtime_evidence
    )
    if type(parsed_artifact) is not MaskedSurfaceArtifactEvidence or type(
        parsed_runtime
    ) is not MaskedSurfaceRuntimeEvidence:
        raise DeterministicEffectContractError(
            "exact masked-surface evidence wrappers are required"
        )
    requirement_value = parsed_requirement.as_dict()
    request_value = parsed_request.as_dict()
    artifact_value = parsed_artifact.as_dict()
    runtime_value = parsed_runtime.as_dict()
    expected_common = {
        "workspaceRef": requirement_value["workspaceRef"],
        "productionRunRef": requirement_value["productionRunRef"],
        "requirementRef": requirement_value["requirementRef"],
        "requirementDigest": requirement_value["payloadDigest"],
        "executionRequestRef": request_value["executionRequestRef"],
        "executionRequestDigest": request_value["payloadDigest"],
        "effectMode": requirement_value["effectMode"],
    }
    for evidence_value, label in (
        (runtime_value, "runtime evidence"),
        (artifact_value, "artifact evidence"),
    ):
        if any(evidence_value[field] != expected for field, expected in expected_common.items()):
            raise DeterministicEffectStaleInputError(f"{label} lineage is stale")
    if (
        artifact_value["v3ExecutionRequestDigest"]
        != runtime_value["v3ExecutionRequestDigest"]
        or artifact_value["runtimeEvidenceRef"]
        != runtime_value["runtimeEvidenceRef"]
        or artifact_value["runtimeEvidenceDigest"]
        != runtime_value["payloadDigest"]
    ):
        raise DeterministicEffectStaleInputError(
            "artifact and runtime evidence lineage is stale"
        )
    if (
        artifact_value["outputMediaProbe"]["frameCount"]
        < requirement_value["frameRangeEndExclusive"]
    ):
        raise DeterministicEffectStaleInputError(
            "output frame count does not cover the Requirement range"
        )
    return parsed_artifact, parsed_runtime


validate_deterministic_effect_execution_evidence = (
    validate_masked_surface_execution_evidence
)


def _validate_result(
    value: Any,
    *,
    schema_version: str,
    modes: frozenset[str],
    label: str,
) -> dict[str, Any]:
    result = _verify_sealed(value, _RESULT_FIELDS, label)
    if result["schemaVersion"] != schema_version:
        raise DeterministicEffectContractError(f"{label} schema is unsupported")
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
    ):
        _raw_digest(result[field], field)
    if result["effectMode"] not in modes:
        raise DeterministicEffectContractError("effectMode is invalid")
    if result["state"] != RESULT_STATE:
        raise DeterministicEffectContractError("Result state is invalid")
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    expected_ref = _result_ref(
        effect_mode=result["effectMode"],
        requirement_ref=result["requirementRef"],
        requirement_digest=result["requirementDigest"],
        execution_request_ref=result["executionRequestRef"],
        execution_request_digest=result["executionRequestDigest"],
        artifact_evidence_ref=result["artifactEvidenceRef"],
        artifact_evidence_digest=result["artifactEvidenceDigest"],
        runtime_evidence_ref=result["runtimeEvidenceRef"],
        runtime_evidence_digest=result["runtimeEvidenceDigest"],
    )
    if result["resultRef"] != expected_ref:
        raise DeterministicEffectStaleInputError(
            "resultRef does not match the predecessor evidence"
        )
    return result


@dataclass(frozen=True, slots=True)
class ScratchLightResult(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "ScratchLightResult":
        return cls._from_validated(
            _validate_result(
                value,
                schema_version=SCRATCH_LIGHT_RESULT_SCHEMA_VERSION,
                modes=SCRATCH_LIGHT_EFFECT_MODES,
                label="ScratchLightResult",
            )
        )

    @property
    def result_ref(self) -> str:
        return str(self._value["resultRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


@dataclass(frozen=True, slots=True)
class LocalExposureResult(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "LocalExposureResult":
        return cls._from_validated(
            _validate_result(
                value,
                schema_version=LOCAL_EXPOSURE_RESULT_SCHEMA_VERSION,
                modes=frozenset({LOCAL_EXPOSURE}),
                label="LocalExposureResult",
            )
        )

    @property
    def result_ref(self) -> str:
        return str(self._value["resultRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


def _validate_e2_result(
    value: Any,
    *,
    schema_version: str,
    effect_mode: str,
    label: str,
) -> dict[str, Any]:
    result = _verify_sealed(value, _E2_RESULT_FIELDS, label)
    if result["schemaVersion"] != schema_version:
        raise DeterministicEffectContractError(f"{label} schema is unsupported")
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
    ):
        _raw_digest(result[field], field)
    if result["effectMode"] != effect_mode:
        raise DeterministicEffectContractError("effectMode is invalid")
    _content_digest(result["outputFileDigest"], "outputFileDigest")
    _content_digest(
        result["outputDecodedFramePixelDigest"],
        "outputDecodedFramePixelDigest",
    )
    result["outputMediaProbe"] = _output_probe(result["outputMediaProbe"])
    if (
        result["state"] != E2_RESULT_STATE
        or result["assetAdmissionState"] != ASSET_ADMISSION_STATE
        or result["masterState"] != MASTER_STATE
        or result["exportState"] != EXPORT_STATE
    ):
        raise DeterministicEffectContractError("E2 Result state is invalid")
    if result["publicationAllowed"] is not False:
        raise DeterministicEffectContractError(
            "publicationAllowed must be server-fixed false"
        )
    expected_ref = _result_ref(
        effect_mode=result["effectMode"],
        requirement_ref=result["requirementRef"],
        requirement_digest=result["requirementDigest"],
        execution_request_ref=result["executionRequestRef"],
        execution_request_digest=result["executionRequestDigest"],
        artifact_evidence_ref=result["artifactEvidenceRef"],
        artifact_evidence_digest=result["artifactEvidenceDigest"],
        runtime_evidence_ref=result["runtimeEvidenceRef"],
        runtime_evidence_digest=result["runtimeEvidenceDigest"],
    )
    if result["resultRef"] != expected_ref:
        raise DeterministicEffectStaleInputError(
            "resultRef does not match the predecessor evidence"
        )
    return result


@dataclass(frozen=True, slots=True)
class FlameExtinguishResult(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "FlameExtinguishResult":
        return cls._from_validated(
            _validate_e2_result(
                value,
                schema_version=FLAME_EXTINGUISH_RESULT_SCHEMA_VERSION,
                effect_mode=FLAME_EXTINGUISH,
                label="FlameExtinguishResult",
            )
        )

    @property
    def result_ref(self) -> str:
        return str(self._value["resultRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


@dataclass(frozen=True, slots=True)
class SmokeResult(_ImmutableContract):
    @classmethod
    def from_mapping(cls, value: Any) -> "SmokeResult":
        return cls._from_validated(
            _validate_e2_result(
                value,
                schema_version=SMOKE_RESULT_SCHEMA_VERSION,
                effect_mode=SMOKE,
                label="SmokeResult",
            )
        )

    @property
    def result_ref(self) -> str:
        return str(self._value["resultRef"])

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
    def requirement_digest(self) -> str:
        return str(self._value["requirementDigest"])

    @property
    def effect_mode(self) -> str:
        return str(self._value["effectMode"])


DeterministicEffectResult = (
    ScratchLightResult
    | LocalExposureResult
    | FlameExtinguishResult
    | SmokeResult
)


def parse_deterministic_effect_result(value: Any) -> DeterministicEffectResult:
    if not isinstance(value, Mapping):
        raise DeterministicEffectContractError("Result must be an object")
    schema = value.get("schemaVersion")
    if schema == SCRATCH_LIGHT_RESULT_SCHEMA_VERSION:
        return ScratchLightResult.from_mapping(value)
    if schema == LOCAL_EXPOSURE_RESULT_SCHEMA_VERSION:
        return LocalExposureResult.from_mapping(value)
    if schema == FLAME_EXTINGUISH_RESULT_SCHEMA_VERSION:
        return FlameExtinguishResult.from_mapping(value)
    if schema == SMOKE_RESULT_SCHEMA_VERSION:
        return SmokeResult.from_mapping(value)
    raise DeterministicEffectContractError("Result schema is unsupported")


def _result_ref(
    *,
    effect_mode: str,
    requirement_ref: str,
    requirement_digest: str,
    execution_request_ref: str,
    execution_request_digest: str,
    artifact_evidence_ref: str,
    artifact_evidence_digest: str,
    runtime_evidence_ref: str,
    runtime_evidence_digest: str,
) -> str:
    identity = {
        "schemaVersion": "v5.m13-deterministic-effect-result-identity.v1",
        "effectMode": effect_mode,
        "requirementRef": requirement_ref,
        "requirementDigest": requirement_digest,
        "executionRequestRef": execution_request_ref,
        "executionRequestDigest": execution_request_digest,
        "artifactEvidenceRef": artifact_evidence_ref,
        "artifactEvidenceDigest": artifact_evidence_digest,
        "runtimeEvidenceRef": runtime_evidence_ref,
        "runtimeEvidenceDigest": runtime_evidence_digest,
    }
    prefixes = {
        SCRATCH_REVEAL: "m13-scratch-light-result-",
        LIGHT_SWEEP: "m13-scratch-light-result-",
        LOCAL_EXPOSURE: "m13-local-exposure-result-",
        FLAME_EXTINGUISH: "m13-flame-extinguish-result-",
        SMOKE: "m13-smoke-result-",
    }
    try:
        prefix = prefixes[effect_mode]
    except KeyError as exc:
        raise DeterministicEffectContractError("effectMode is invalid") from exc
    return prefix + _digest(identity)[:32]


def deterministic_effect_result_ref(evidence_bindings: Mapping[str, Any], *, effect_mode: str) -> str:
    bindings = _closed(
        evidence_bindings, _EVIDENCE_BINDING_FIELDS, "evidenceBindings"
    )
    if effect_mode not in DETERMINISTIC_EFFECT_MODES:
        raise DeterministicEffectContractError("effectMode is invalid")
    return _result_ref(effect_mode=effect_mode, **{
        "requirement_ref": _ref(bindings["requirementRef"], "requirementRef"),
        "requirement_digest": _raw_digest(bindings["requirementDigest"], "requirementDigest"),
        "execution_request_ref": _ref(bindings["executionRequestRef"], "executionRequestRef"),
        "execution_request_digest": _raw_digest(bindings["executionRequestDigest"], "executionRequestDigest"),
        "artifact_evidence_ref": _ref(bindings["artifactEvidenceRef"], "artifactEvidenceRef"),
        "artifact_evidence_digest": _raw_digest(bindings["artifactEvidenceDigest"], "artifactEvidenceDigest"),
        "runtime_evidence_ref": _ref(bindings["runtimeEvidenceRef"], "runtimeEvidenceRef"),
        "runtime_evidence_digest": _raw_digest(bindings["runtimeEvidenceDigest"], "runtimeEvidenceDigest"),
    })


def build_deterministic_effect_result(
    *,
    requirement: DeterministicEffectRequirement,
    execution_request: DeterministicEffectExecutionRequest,
    evidence_bindings: Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any] | None = None,
    local_exposure_requirement: LocalExposureRequirement | None = None,
    local_exposure_result: LocalExposureResult | None = None,
) -> DeterministicEffectResult:
    if type(requirement) not in {
        ScratchLightRequirement,
        LocalExposureRequirement,
        FlameExtinguishRequirement,
        SmokeRequirement,
    }:
        raise DeterministicEffectContractError(
            "an exact deterministic effect Requirement wrapper is required"
        )
    request = validate_deterministic_effect_execution_request_binding(
        execution_request,
        requirement,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    bindings = _closed(
        evidence_bindings, _EVIDENCE_BINDING_FIELDS, "evidenceBindings"
    )
    requirement_value = requirement.as_dict()
    request_value = request.as_dict()
    expected = {
        "workspaceRef": requirement_value["workspaceRef"],
        "productionRunRef": requirement_value["productionRunRef"],
        "requirementRef": requirement_value["requirementRef"],
        "requirementDigest": requirement_value["payloadDigest"],
        "executionRequestRef": request_value["executionRequestRef"],
        "executionRequestDigest": request_value["payloadDigest"],
    }
    if any(bindings[field] != value for field, value in expected.items()):
        raise DeterministicEffectStaleInputError(
            "evidence bindings do not match the Requirement execution"
        )
    for field in ("artifactEvidenceRef", "runtimeEvidenceRef"):
        _ref(bindings[field], field)
    for field in (
        "requirementDigest",
        "executionRequestDigest",
        "artifactEvidenceDigest",
        "runtimeEvidenceDigest",
    ):
        _raw_digest(bindings[field], field)
    mode = requirement_value["effectMode"]
    parsed_artifact: MaskedSurfaceArtifactEvidence | None = None
    if artifact_evidence is not None:
        parsed_artifact = (
            MaskedSurfaceArtifactEvidence.from_mapping(artifact_evidence)
            if isinstance(artifact_evidence, Mapping)
            else artifact_evidence
        )
        if type(parsed_artifact) is not MaskedSurfaceArtifactEvidence:
            raise DeterministicEffectContractError(
                "an exact MaskedSurfaceArtifactEvidence wrapper is required"
            )
        artifact_value = parsed_artifact.as_dict()
        if (
            artifact_value["workspaceRef"] != requirement_value["workspaceRef"]
            or artifact_value["productionRunRef"]
            != requirement_value["productionRunRef"]
            or artifact_value["requirementRef"]
            != requirement_value["requirementRef"]
            or artifact_value["requirementDigest"]
            != requirement_value["payloadDigest"]
            or artifact_value["executionRequestRef"]
            != request_value["executionRequestRef"]
            or artifact_value["executionRequestDigest"]
            != request_value["payloadDigest"]
            or artifact_value["artifactEvidenceRef"]
            != bindings["artifactEvidenceRef"]
            or artifact_value["payloadDigest"]
            != bindings["artifactEvidenceDigest"]
            or artifact_value["runtimeEvidenceRef"]
            != bindings["runtimeEvidenceRef"]
            or artifact_value["runtimeEvidenceDigest"]
            != bindings["runtimeEvidenceDigest"]
            or artifact_value["effectMode"] != mode
        ):
            raise DeterministicEffectStaleInputError(
                "artifact evidence does not match Result bindings"
            )
    if mode in FLAME_SMOKE_EFFECT_MODES and parsed_artifact is None:
        raise DeterministicEffectContractError(
            "E2 Result requires exact artifact evidence"
        )
    schema_by_mode = {
        SCRATCH_REVEAL: SCRATCH_LIGHT_RESULT_SCHEMA_VERSION,
        LIGHT_SWEEP: SCRATCH_LIGHT_RESULT_SCHEMA_VERSION,
        LOCAL_EXPOSURE: LOCAL_EXPOSURE_RESULT_SCHEMA_VERSION,
        FLAME_EXTINGUISH: FLAME_EXTINGUISH_RESULT_SCHEMA_VERSION,
        SMOKE: SMOKE_RESULT_SCHEMA_VERSION,
    }
    result = {
        "schemaVersion": schema_by_mode[mode],
        "workspaceRef": requirement_value["workspaceRef"],
        "productionRunRef": requirement_value["productionRunRef"],
        "resultRef": deterministic_effect_result_ref(
            bindings, effect_mode=mode
        ),
        "effectMode": mode,
        "requirementRef": bindings["requirementRef"],
        "requirementDigest": bindings["requirementDigest"],
        "executionRequestRef": bindings["executionRequestRef"],
        "executionRequestDigest": bindings["executionRequestDigest"],
        "artifactEvidenceRef": bindings["artifactEvidenceRef"],
        "artifactEvidenceDigest": bindings["artifactEvidenceDigest"],
        "runtimeEvidenceRef": bindings["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": bindings["runtimeEvidenceDigest"],
        "state": (
            E2_RESULT_STATE
            if mode in FLAME_SMOKE_EFFECT_MODES
            else RESULT_STATE
        ),
        "publicationAllowed": False,
    }
    if mode in FLAME_SMOKE_EFFECT_MODES:
        assert parsed_artifact is not None
        artifact_value = parsed_artifact.as_dict()
        result.update(
            {
                "outputFileDigest": artifact_value["outputDigest"][
                    "fileDigest"
                ],
                "outputDecodedFramePixelDigest": artifact_value[
                    "outputDigest"
                ]["decodedFramePixelDigest"],
                "outputMediaProbe": artifact_value["outputMediaProbe"],
                "assetAdmissionState": ASSET_ADMISSION_STATE,
                "masterState": MASTER_STATE,
                "exportState": EXPORT_STATE,
            }
        )
    return parse_deterministic_effect_result(_seal(result))


def build_scratch_light_result(
    *,
    requirement: ScratchLightRequirement,
    execution_request: MaskedSurfaceExecutionRequest,
    evidence_bindings: Mapping[str, Any],
) -> ScratchLightResult:
    if type(requirement) is not ScratchLightRequirement:
        raise DeterministicEffectContractError(
            "an exact ScratchLightRequirement wrapper is required"
        )
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=execution_request,
        evidence_bindings=evidence_bindings,
    )
    if type(result) is not ScratchLightResult:
        raise DeterministicEffectContractError("ScratchLightResult is invalid")
    return result


def build_local_exposure_result(
    *,
    requirement: LocalExposureRequirement,
    execution_request: MaskedSurfaceExecutionRequest,
    evidence_bindings: Mapping[str, Any],
) -> LocalExposureResult:
    if type(requirement) is not LocalExposureRequirement:
        raise DeterministicEffectContractError(
            "an exact LocalExposureRequirement wrapper is required"
        )
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=execution_request,
        evidence_bindings=evidence_bindings,
    )
    if type(result) is not LocalExposureResult:
        raise DeterministicEffectContractError("LocalExposureResult is invalid")
    return result


def build_flame_extinguish_result(
    *,
    requirement: FlameExtinguishRequirement,
    execution_request: FlameSmokeExecutionRequest,
    evidence_bindings: Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any],
    local_exposure_requirement: LocalExposureRequirement,
    local_exposure_result: LocalExposureResult,
) -> FlameExtinguishResult:
    if type(requirement) is not FlameExtinguishRequirement:
        raise DeterministicEffectContractError(
            "an exact FlameExtinguishRequirement wrapper is required"
        )
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=execution_request,
        evidence_bindings=evidence_bindings,
        artifact_evidence=artifact_evidence,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    if type(result) is not FlameExtinguishResult:
        raise DeterministicEffectContractError(
            "FlameExtinguishResult is invalid"
        )
    return result


def build_smoke_result(
    *,
    requirement: SmokeRequirement,
    execution_request: FlameSmokeExecutionRequest,
    evidence_bindings: Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any],
) -> SmokeResult:
    if type(requirement) is not SmokeRequirement:
        raise DeterministicEffectContractError(
            "an exact SmokeRequirement wrapper is required"
        )
    result = build_deterministic_effect_result(
        requirement=requirement,
        execution_request=execution_request,
        evidence_bindings=evidence_bindings,
        artifact_evidence=artifact_evidence,
    )
    if type(result) is not SmokeResult:
        raise DeterministicEffectContractError("SmokeResult is invalid")
    return result


def _result_record_kind(result: DeterministicEffectResult) -> str:
    if type(result) is ScratchLightResult:
        return SCRATCH_LIGHT_RESULT_RECORD_KIND
    if type(result) is LocalExposureResult:
        return LOCAL_EXPOSURE_RESULT_RECORD_KIND
    if type(result) is FlameExtinguishResult:
        return FLAME_EXTINGUISH_RESULT_RECORD_KIND
    if type(result) is SmokeResult:
        return SMOKE_RESULT_RECORD_KIND
    raise DeterministicEffectContractError(
        "an exact deterministic effect Result wrapper is required"
    )


def _requirement_record_kind_for_mode(effect_mode: str) -> str:
    kinds = {
        SCRATCH_REVEAL: SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND,
        LIGHT_SWEEP: SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND,
        LOCAL_EXPOSURE: LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND,
        FLAME_EXTINGUISH: FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND,
        SMOKE: SMOKE_REQUIREMENT_RECORD_KIND,
    }
    try:
        return kinds[effect_mode]
    except KeyError as exc:
        raise DeterministicEffectContractError("effectMode is invalid") from exc


def _validated_chain(
    *,
    requirement: DeterministicEffectRequirement | Mapping[str, Any],
    execution_request: DeterministicEffectExecutionRequest | Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any],
    runtime_evidence: MaskedSurfaceRuntimeEvidence | Mapping[str, Any],
    result: DeterministicEffectResult | Mapping[str, Any],
    local_exposure_requirement: LocalExposureRequirement | None = None,
    local_exposure_result: LocalExposureResult | None = None,
) -> tuple[
    DeterministicEffectRequirement,
    DeterministicEffectExecutionRequest,
    MaskedSurfaceArtifactEvidence,
    MaskedSurfaceRuntimeEvidence,
    DeterministicEffectResult,
]:
    parsed_requirement = (
        parse_deterministic_effect_requirement(requirement)
        if isinstance(requirement, Mapping)
        else requirement
    )
    if type(parsed_requirement) not in {
        ScratchLightRequirement,
        LocalExposureRequirement,
        FlameExtinguishRequirement,
        SmokeRequirement,
    }:
        raise DeterministicEffectContractError(
            "an exact deterministic effect Requirement wrapper is required"
        )
    parsed_request = validate_deterministic_effect_execution_request_binding(
        execution_request,
        parsed_requirement,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    parsed_artifact, parsed_runtime = validate_masked_surface_execution_evidence(
        requirement=parsed_requirement,
        execution_request=parsed_request,
        artifact_evidence=artifact_evidence,
        runtime_evidence=runtime_evidence,
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    parsed_result = (
        parse_deterministic_effect_result(result)
        if isinstance(result, Mapping)
        else result
    )
    if type(parsed_result) not in {
        ScratchLightResult,
        LocalExposureResult,
        FlameExtinguishResult,
        SmokeResult,
    }:
        raise DeterministicEffectContractError(
            "an exact deterministic effect Result wrapper is required"
        )
    artifact_value = parsed_artifact.as_dict()
    runtime_value = parsed_runtime.as_dict()
    bindings = {
        "workspaceRef": parsed_requirement.workspace_ref,
        "productionRunRef": parsed_requirement.production_run_ref,
        "requirementRef": parsed_requirement.requirement_ref,
        "requirementDigest": parsed_requirement.payload_digest,
        "executionRequestRef": parsed_request.execution_request_ref,
        "executionRequestDigest": parsed_request.payload_digest,
        "artifactEvidenceRef": artifact_value["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact_value["payloadDigest"],
        "runtimeEvidenceRef": runtime_value["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime_value["payloadDigest"],
    }
    expected_result = build_deterministic_effect_result(
        requirement=parsed_requirement,
        execution_request=parsed_request,
        evidence_bindings=bindings,
        artifact_evidence=(
            parsed_artifact
            if parsed_requirement.effect_mode in FLAME_SMOKE_EFFECT_MODES
            else None
        ),
        local_exposure_requirement=local_exposure_requirement,
        local_exposure_result=local_exposure_result,
    )
    if parsed_result.as_dict() != expected_result.as_dict():
        raise DeterministicEffectStaleInputError(
            "Result is not the exact Requirement execution projection"
        )
    return (
        parsed_requirement,
        parsed_request,
        parsed_artifact,
        parsed_runtime,
        parsed_result,
    )


@dataclass(frozen=True, slots=True)
class ResolvedDeterministicEffectResultChain:
    requirement: DeterministicEffectRequirement
    execution_request: DeterministicEffectExecutionRequest
    artifact_evidence: MaskedSurfaceArtifactEvidence
    runtime_evidence: MaskedSurfaceRuntimeEvidence
    result: DeterministicEffectResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement.as_dict(),
            "executionRequest": self.execution_request.as_dict(),
            "artifactEvidence": self.artifact_evidence.as_dict(),
            "runtimeEvidence": self.runtime_evidence.as_dict(),
            "result": self.result.as_dict(),
        }


def _record_idempotency_key(client_key: str, slot: str) -> str:
    return _digest(
        {
            "schemaVersion": (
                "v5.m13-deterministic-effect-record-idempotency.v1"
            ),
            "clientIdempotencyKey": _idempotency_key(client_key),
            "slot": slot,
        }
    )


def _chain_records(
    *,
    requirement: DeterministicEffectRequirement,
    execution_request: DeterministicEffectExecutionRequest,
    artifact_evidence: MaskedSurfaceArtifactEvidence,
    runtime_evidence: MaskedSurfaceRuntimeEvidence,
    result: DeterministicEffectResult,
    idempotency_key: str,
    created_at: str,
) -> tuple[EvidenceRecord, ...]:
    requirement_value = requirement.as_dict()
    request_value = execution_request.as_dict()
    artifact_value = artifact_evidence.as_dict()
    runtime_value = runtime_evidence.as_dict()
    result_value = result.as_dict()
    entries = (
        (
            _requirement_kind(requirement),
            requirement_value["requirementRef"],
            requirement_value,
        ),
        (
            MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND,
            request_value["executionRequestRef"],
            request_value,
        ),
        (
            MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND,
            artifact_value["artifactEvidenceRef"],
            artifact_value,
        ),
        (
            MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND,
            runtime_value["runtimeEvidenceRef"],
            runtime_value,
        ),
        (
            _result_record_kind(result),
            result_value["resultRef"],
            result_value,
        ),
    )
    chain_digest = _digest(
        {
            "schemaVersion": "v5.m13-deterministic-effect-result-chain.v1",
            "workspaceRef": requirement.workspace_ref,
            "productionRunRef": requirement.production_run_ref,
            "members": [
                {
                    "recordKind": kind,
                    "recordRef": ref,
                    "payloadDigest": payload["payloadDigest"],
                }
                for kind, ref, payload in entries
            ],
        }
    )
    timestamp = _timestamp(created_at)
    return tuple(
        EvidenceRecord(
            workspaceRef=requirement.workspace_ref,
            productionRunRef=requirement.production_run_ref,
            recordKind=kind,
            recordRef=ref,
            recordVersion=1,
            idempotencyKey=_record_idempotency_key(
                idempotency_key, f"{index}:{kind}"
            ),
            requestDigest=_digest(
                {
                    "schemaVersion": (
                        "v5.m13-deterministic-effect-record-append.v1"
                    ),
                    "chainDigest": chain_digest,
                    "recordKind": kind,
                    "recordRef": ref,
                    "payloadDigest": payload["payloadDigest"],
                }
            ),
            createdAt=timestamp,
            payload=payload,
            payloadDigest=payload["payloadDigest"],
        )
        for index, (kind, ref, payload) in enumerate(entries)
    )


def _record_payload(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    record_ref: str,
    expected_kind: str | frozenset[str],
    expected_digest: str,
) -> dict[str, Any]:
    workspace = _ref(workspace_ref, "workspaceRef")
    run_ref = _ref(production_run_ref, "productionRunRef")
    ref = _ref(record_ref, "recordRef")
    digest = _raw_digest(expected_digest, "record payloadDigest")
    stored = repository.get_record(workspace, run_ref, ref, 1)
    if stored is None:
        raise DeterministicEffectJournalError(
            "deterministic effect evidence record is missing"
        )
    fields = frozenset(
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
    )
    allowed_forbidden_keys = frozenset()
    if isinstance(stored, Mapping) and isinstance(
        stored.get("payload"), Mapping
    ):
        stored_kind = stored.get("recordKind")
        stored_payload = stored["payload"]
        if (
            stored_kind == SMOKE_REQUIREMENT_RECORD_KIND
            and stored_payload.get("schemaVersion")
            == SMOKE_REQUIREMENT_SCHEMA_VERSION
            and stored_payload.get("effectMode") == SMOKE
        ) or (
            stored_kind == MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND
            and stored_payload.get("schemaVersion")
            == FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION
            and stored_payload.get("effectMode") == SMOKE
        ):
            allowed_forbidden_keys = _SMOKE_ALLOWED_FORBIDDEN_KEYS
    try:
        record = _closed(
            stored,
            fields,
            "deterministic effect evidence record",
            allowed_forbidden_keys=allowed_forbidden_keys,
        )
        kinds = (
            expected_kind
            if isinstance(expected_kind, frozenset)
            else frozenset({expected_kind})
        )
        if (
            record["workspaceRef"] != workspace
            or record["productionRunRef"] != run_ref
            or record["recordKind"] not in kinds
            or record["recordRef"] != ref
            or record["recordVersion"] != 1
            or record["payloadDigest"] != digest
        ):
            raise DeterministicEffectJournalError(
                "deterministic effect evidence record identity is stale"
            )
        _idempotency_key(record["idempotencyKey"])
        _raw_digest(record["requestDigest"], "record requestDigest")
        _timestamp(record["createdAt"])
        if not isinstance(record["payload"], Mapping):
            raise DeterministicEffectJournalError(
                "deterministic effect evidence payload is invalid"
            )
        payload = deepcopy(dict(record["payload"]))
        if payload.get("payloadDigest") != digest:
            raise DeterministicEffectJournalError(
                "deterministic effect evidence payload digest is stale"
            )
        return payload
    except DeterministicEffectJournalError:
        raise
    except EpisodeProductionError as exc:
        raise DeterministicEffectJournalError(
            "deterministic effect evidence record is invalid"
        ) from exc


def _resolve_flame_local_exposure_dependency(
    repository: EpisodeProductionEvidenceRepository,
    *,
    requirement: DeterministicEffectRequirement,
    execution_request: DeterministicEffectExecutionRequest,
) -> tuple[LocalExposureRequirement | None, LocalExposureResult | None]:
    if type(requirement) is not FlameExtinguishRequirement:
        return None, None
    if type(execution_request) is not FlameSmokeExecutionRequest:
        raise DeterministicEffectContractError(
            "Flame execution request wrapper is invalid"
        )
    request_value = execution_request.as_dict()
    dependency = resolve_deterministic_effect_result_chain(
        repository,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        result_ref=request_value["localExposureResultRef"],
        result_digest=request_value["localExposureResultDigest"],
    )
    if type(dependency.requirement) is not LocalExposureRequirement or type(
        dependency.result
    ) is not LocalExposureResult:
        raise DeterministicEffectStaleInputError(
            "Flame LocalExposure dependency type is stale"
        )
    validate_flame_local_exposure_compatibility(
        requirement, dependency.requirement, dependency.result
    )
    return dependency.requirement, dependency.result


def resolve_deterministic_effect_result_chain(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    result_ref: str,
    result_digest: str,
) -> ResolvedDeterministicEffectResultChain:
    result_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_ref,
        expected_kind=frozenset(
            {
                SCRATCH_LIGHT_RESULT_RECORD_KIND,
                LOCAL_EXPOSURE_RESULT_RECORD_KIND,
                FLAME_EXTINGUISH_RESULT_RECORD_KIND,
                SMOKE_RESULT_RECORD_KIND,
            }
        ),
        expected_digest=result_digest,
    )
    result = parse_deterministic_effect_result(result_payload)
    result_value = result.as_dict()
    if result_value["resultRef"] != result_ref:
        raise DeterministicEffectJournalError("Result record ref is stale")
    exact_result_kind = _result_record_kind(result)
    # The initial read must accept either Result kind because resultRef alone
    # is the lookup key.  Re-read with the parsed exact kind so a re-sealed
    # payload cannot be stored under the other typed record kind.
    _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_ref,
        expected_kind=exact_result_kind,
        expected_digest=result_digest,
    )
    requirement_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_value["requirementRef"],
        expected_kind=_requirement_record_kind_for_mode(
            result_value["effectMode"]
        ),
        expected_digest=result_value["requirementDigest"],
    )
    request_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_value["executionRequestRef"],
        expected_kind=MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND,
        expected_digest=result_value["executionRequestDigest"],
    )
    artifact_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_value["artifactEvidenceRef"],
        expected_kind=MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND,
        expected_digest=result_value["artifactEvidenceDigest"],
    )
    runtime_payload = _record_payload(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        record_ref=result_value["runtimeEvidenceRef"],
        expected_kind=MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND,
        expected_digest=result_value["runtimeEvidenceDigest"],
    )
    parsed_requirement = parse_deterministic_effect_requirement(
        requirement_payload
    )
    parsed_request = parse_deterministic_effect_execution_request(
        request_payload
    )
    exposure_requirement, exposure_result = (
        _resolve_flame_local_exposure_dependency(
            repository,
            requirement=parsed_requirement,
            execution_request=parsed_request,
        )
    )
    chain = _validated_chain(
        requirement=parsed_requirement,
        execution_request=parsed_request,
        artifact_evidence=artifact_payload,
        runtime_evidence=runtime_payload,
        result=result,
        local_exposure_requirement=exposure_requirement,
        local_exposure_result=exposure_result,
    )
    return ResolvedDeterministicEffectResultChain(*chain)


def resolve_deterministic_effect_result(
    repository: EpisodeProductionEvidenceRepository,
    *,
    workspace_ref: str,
    production_run_ref: str,
    result_ref: str,
    result_digest: str,
) -> DeterministicEffectResult:
    return resolve_deterministic_effect_result_chain(
        repository,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        result_ref=result_ref,
        result_digest=result_digest,
    ).result


def append_deterministic_effect_result_chain(
    repository: EpisodeProductionEvidenceRepository,
    *,
    requirement: DeterministicEffectRequirement | Mapping[str, Any],
    execution_request: DeterministicEffectExecutionRequest | Mapping[str, Any],
    artifact_evidence: MaskedSurfaceArtifactEvidence | Mapping[str, Any],
    runtime_evidence: MaskedSurfaceRuntimeEvidence | Mapping[str, Any],
    result: DeterministicEffectResult | Mapping[str, Any],
    idempotency_key: str,
    created_at: str,
    expected_record_journal_head: str | None = None,
) -> tuple[ResolvedDeterministicEffectResultChain, bool]:
    parsed_requirement = (
        parse_deterministic_effect_requirement(requirement)
        if isinstance(requirement, Mapping)
        else requirement
    )
    parsed_request = (
        parse_deterministic_effect_execution_request(execution_request)
        if isinstance(execution_request, Mapping)
        else execution_request
    )
    if type(parsed_requirement) not in {
        ScratchLightRequirement,
        LocalExposureRequirement,
        FlameExtinguishRequirement,
        SmokeRequirement,
    } or type(parsed_request) not in {
        MaskedSurfaceExecutionRequest,
        FlameSmokeExecutionRequest,
    }:
        raise DeterministicEffectContractError(
            "exact deterministic effect wrappers are required"
        )
    exposure_requirement, exposure_result = (
        _resolve_flame_local_exposure_dependency(
            repository,
            requirement=parsed_requirement,
            execution_request=parsed_request,
        )
    )
    chain = _validated_chain(
        requirement=parsed_requirement,
        execution_request=parsed_request,
        artifact_evidence=artifact_evidence,
        runtime_evidence=runtime_evidence,
        result=result,
        local_exposure_requirement=exposure_requirement,
        local_exposure_result=exposure_result,
    )
    records = _chain_records(
        requirement=chain[0],
        execution_request=chain[1],
        artifact_evidence=chain[2],
        runtime_evidence=chain[3],
        result=chain[4],
        idempotency_key=idempotency_key,
        created_at=created_at,
    )
    _, replayed = repository.append_records(
        records,
        expected_record_journal_head=expected_record_journal_head,
    )
    resolved = resolve_deterministic_effect_result_chain(
        repository,
        workspace_ref=chain[0].workspace_ref,
        production_run_ref=chain[0].production_run_ref,
        result_ref=chain[4].result_ref,
        result_digest=chain[4].payload_digest,
    )
    if resolved.as_dict() != ResolvedDeterministicEffectResultChain(*chain).as_dict():
        raise DeterministicEffectJournalError(
            "stored deterministic effect result chain differs from the append"
        )
    return resolved, replayed


append_deterministic_effect_result = append_deterministic_effect_result_chain


__all__ = [
    "ASSET_ADMISSION_STATE",
    "BLEND_MODES",
    "DECODED_FRAME_PIXEL_DIGEST_SPEC",
    "DETERMINISTIC_EFFECT_MODES",
    "DETERMINISTIC_SMOKE_ALGORITHM_IDENTITY",
    "DETERMINISTIC_SMOKE_ALGORITHM_VERSION",
    "DeterministicEffectExecutionRequest",
    "DeterministicEffectContractError",
    "DeterministicEffectJournalError",
    "DeterministicEffectStaleInputError",
    "E2_RESULT_STATE",
    "EXPORT_STATE",
    "FLAME_EXTINGUISH",
    "FLAME_EXTINGUISH_REQUIREMENT_RECORD_KIND",
    "FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION",
    "FLAME_EXTINGUISH_RESULT_RECORD_KIND",
    "FLAME_EXTINGUISH_RESULT_SCHEMA_VERSION",
    "FLAME_SMOKE_EFFECT_MODES",
    "FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "FLAME_STATES",
    "FlameExtinguishRequirement",
    "FlameExtinguishResult",
    "FlameSmokeExecutionRequest",
    "INTERPOLATIONS",
    "LIGHT_SWEEP",
    "LOCAL_EXPOSURE",
    "LOCAL_EXPOSURE_REQUIREMENT_RECORD_KIND",
    "LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION",
    "LOCAL_EXPOSURE_RESULT_RECORD_KIND",
    "LOCAL_EXPOSURE_RESULT_SCHEMA_VERSION",
    "LocalExposureRequirement",
    "LocalExposureResult",
    "MASKED_SURFACE_ARTIFACT_EVIDENCE_RECORD_KIND",
    "MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "MASKED_SURFACE_EFFECT_MODES",
    "MASKED_SURFACE_EXECUTION_REQUEST_RECORD_KIND",
    "MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "MASKED_SURFACE_RUNTIME_EVIDENCE_RECORD_KIND",
    "MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "MASKED_SURFACE_RENDERER_IDENTITY",
    "MASKED_SURFACE_RENDERER_VERSION",
    "MASTER_STATE",
    "MaskedSurfaceArtifactEvidence",
    "MaskedSurfaceExecutionRequest",
    "MaskedSurfaceRuntimeEvidence",
    "ResolvedDeterministicEffectResultChain",
    "SCRATCH_LIGHT_EFFECT_MODES",
    "SCRATCH_LIGHT_REQUIREMENT_RECORD_KIND",
    "SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION",
    "SCRATCH_LIGHT_RESULT_RECORD_KIND",
    "SCRATCH_LIGHT_RESULT_SCHEMA_VERSION",
    "SCRATCH_REVEAL",
    "SMOKE",
    "SMOKE_REQUIREMENT_RECORD_KIND",
    "SMOKE_REQUIREMENT_SCHEMA_VERSION",
    "SMOKE_RESULT_RECORD_KIND",
    "SMOKE_RESULT_SCHEMA_VERSION",
    "SMOKE_SOURCE_KINDS",
    "ScratchLightRequirement",
    "ScratchLightResult",
    "SmokeRequirement",
    "SmokeResult",
    "append_deterministic_effect_result",
    "append_deterministic_effect_result_chain",
    "build_deterministic_effect_result",
    "build_flame_extinguish_requirement",
    "build_flame_extinguish_result",
    "build_flame_smoke_execution_request",
    "build_local_exposure_requirement",
    "build_local_exposure_result",
    "build_masked_surface_execution_request",
    "build_scratch_light_requirement",
    "build_scratch_light_result",
    "build_smoke_requirement",
    "build_smoke_result",
    "deterministic_effect_result_ref",
    "flame_smoke_execution_request_ref",
    "masked_surface_execution_request_ref",
    "parse_deterministic_effect_execution_request",
    "parse_deterministic_effect_requirement",
    "parse_deterministic_effect_result",
    "resolve_deterministic_effect_result",
    "resolve_deterministic_effect_result_chain",
    "validate_deterministic_effect_execution_evidence",
    "validate_deterministic_effect_execution_request_binding",
    "validate_flame_local_exposure_compatibility",
    "validate_masked_surface_execution_evidence",
    "validate_masked_surface_execution_request_binding",
]
