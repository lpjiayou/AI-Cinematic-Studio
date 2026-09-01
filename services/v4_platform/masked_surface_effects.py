"""Closed V4 orchestration for deterministic M13 masked-surface effects.

V5 owns Requirements, Results, and their durable evidence journal.  V3 owns
the fixed FFmpeg primitive.  This module is the deliberately narrow bridge:
it validates a path-free V5 request, resolves server-held AssetVersion facts,
and returns path-free evidence that V5 can append to its existing journal.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any, Mapping

from services.v3_render_core import (
    PCM_CONTENT_DIGEST_SPEC,
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)


MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-masked-surface-execution-request.v1"
)
MASKED_SURFACE_V3_REQUEST_SCHEMA_VERSION = (
    "v4.m13-masked-surface-execution-request.v1"
)
FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-flame-smoke-execution-request.v1"
)
FLAME_SMOKE_V3_REQUEST_SCHEMA_VERSION = (
    "v4.m13-flame-smoke-execution-request.v1"
)
FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-flame-extinguish-requirement.v1"
)
SMOKE_REQUIREMENT_SCHEMA_VERSION = "v5.m13-smoke-requirement.v1"
MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-masked-surface-artifact-evidence.v1"
)
MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-masked-surface-runtime-evidence.v1"
)
SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-scratch-light-requirement.v1"
)
LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-local-exposure-requirement.v1"
)
MASKED_SURFACE_RENDERER_IDENTITY = (
    "v3.deterministic-masked-surface-ffmpeg"
)
MASKED_SURFACE_RENDERER_VERSION_V1 = "1"
MASKED_SURFACE_RENDERER_VERSION_V2 = "2"
MASKED_SURFACE_RENDERER_VERSION_V3 = "3"
MASKED_SURFACE_RENDERER_VERSION_CURRENT = MASKED_SURFACE_RENDERER_VERSION_V3
MASKED_SURFACE_RENDERER_READ_VERSIONS = frozenset(
    {
        MASKED_SURFACE_RENDERER_VERSION_V1,
        MASKED_SURFACE_RENDERER_VERSION_V2,
        MASKED_SURFACE_RENDERER_VERSION_V3,
    }
)
MASKED_SURFACE_RENDERER_VERSION = MASKED_SURFACE_RENDERER_VERSION_CURRENT
MASKED_SURFACE_PROVENANCE = "LOCAL_EVIDENCE"
EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION = (
    "v4.m13-effect-preview-execution-request.v2"
)
EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V3 = (
    "v4.m13-effect-preview-execution-request.v3"
)
EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4 = (
    "v4.m13-effect-preview-execution-request.v4"
)
EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V5 = (
    "v4.m13-effect-preview-execution-request.v5"
)
EFFECT_PREVIEW_V4_RESULT_SCHEMA_VERSION = "v4.m13-composition-result.v2"
EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION = "v5.m13-effect-preview-bindings.v1"
EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2 = "v5.m13-effect-preview-bindings.v2"
EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3 = "v5.m13-effect-preview-bindings.v3"
EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4 = "v5.m13-effect-preview-bindings.v4"
EFFECT_PREVIEW_RENDERER_IDENTITY = "v3.deterministic-timeline-preview-ffmpeg"
EFFECT_PREVIEW_RENDERER_VERSION = "2"
EFFECT_PREVIEW_RENDERER_VERSION_V3 = "3"
EFFECT_PREVIEW_RENDERER_VERSION_V4 = "4"
EFFECT_PREVIEW_RENDERER_VERSION_V5 = "5"
EFFECT_PREVIEW_ADAPTER_IDENTITY = "v4.local-composition-executor.v1"

E1_EFFECT_MODES = ("SCRATCH_REVEAL", "LIGHT_SWEEP", "LOCAL_EXPOSURE")
E2_EFFECT_MODES = ("FLAME_EXTINGUISH", "SMOKE")
EFFECT_MODES = (*E1_EFFECT_MODES, *E2_EFFECT_MODES)
INTERPOLATIONS = ("STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT")
BLEND_MODES = (
    "NORMAL",
    "MULTIPLY",
    "SCREEN",
    "OVERLAY",
    "ADD",
    "DARKEN",
    "LIGHTEN",
)

_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_RAW_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")

_V5_REQUEST_FIELDS = frozenset(
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
_FLAME_V5_REQUEST_FIELDS = frozenset(
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
_SMOKE_V5_REQUEST_FIELDS = frozenset(
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
_TARGET_SHOT_FIELDS = frozenset(
    {"shotRef", "shotVersionRef", "shotVersionDigest"}
)
_REQUEST_ASSET_FIELDS = frozenset(
    {"assetVersionRef", "assetVersionDigest", "fileDigest", "pixelDigest"}
)
_SCHEDULE_FIELDS = frozenset(
    {"startFrameInclusive", "endFrameExclusive", "enabled", "interpolation"}
)
_TRAJECTORY_FIELDS = frozenset(
    {"frame", "xPermille", "yPermille", "interpolation"}
)
_INTENSITY_FIELDS = frozenset({"frame", "valuePermille", "interpolation"})
_EXPOSURE_FIELDS = frozenset({"frame", "valueMilliStops", "interpolation"})
_POINT_FIELDS = frozenset({"xPermille", "yPermille"})
_PERSPECTIVE_FIELDS = frozenset({"mode", "quadPermille"})

_RESOLVED_BASE_FIELDS = frozenset(
    {
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
)
_RESOLVED_MASK_FIELDS = frozenset(
    {
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
)
_V3_BASE_FIELDS = _RESOLVED_BASE_FIELDS
_V3_MASK_FIELDS = _RESOLVED_MASK_FIELDS
_OUTPUT_FIELDS = frozenset(
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
_V3_REQUEST_FIELDS = frozenset(
    {
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
)
_FLAME_V3_REQUEST_FIELDS = frozenset(
    {
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
)
_SMOKE_V3_REQUEST_FIELDS = frozenset(
    {
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
_V3_RESULT_FIELDS = frozenset(
    {
        "internalPath",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "v5ExecutionRequestRef",
        "v5ExecutionRequestDigest",
        "v3ExecutionRequestDigest",
        "requirementRef",
        "requirementDigest",
        "effectMode",
        "publicationAllowed",
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

_EFFECT_PREVIEW_COMMAND_FIELDS = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "baseVideo",
        "effectResultBindings",
        "glyphRequirementBinding",
        "audioMix",
        "subtitleManifest",
        "output",
    }
)
_EFFECT_PREVIEW_BASE_COMMAND_FIELDS = frozenset(
    {
        "assetVersionRef",
        "assetVersionDigest",
        "fileDigest",
        "pixelDigest",
        "width",
        "height",
        "frameCount",
        "frameRate",
    }
)
_EFFECT_RESULT_BINDING_FIELDS = frozenset(
    {
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
)
_GLYPH_REQUIREMENT_BINDING_FIELDS = frozenset(
    {"clipRef", "clipDigest", "requirementRef", "requirementDigest"}
)
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
_EFFECT_EXECUTION_RESOLUTION_FIELDS = frozenset(
    {
        "requirement",
        "executionRequest",
        "artifactEvidence",
        "runtimeEvidence",
        "result",
        "assetVersions",
        "artifactStorage",
    }
)
_EFFECT_ARTIFACT_STORAGE_FIELDS = frozenset(
    {
        "artifactEvidenceRef",
        "artifactEvidenceDigest",
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
)
_GLYPH_EXECUTION_RESOLUTION_FIELDS = frozenset(
    {"requirement", "executionRequest", "assetVersions"}
)
_GLYPH_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStartInclusive",
        "frameRangeEndExclusive",
        "revealSchedule",
        "basePlateAssetVersionRef",
        "basePlateAssetVersionDigest",
        "basePlateFileDigest",
        "maskAssetVersionBindings",
        "basePlateInspectionRef",
        "basePlateInspectionDigest",
        "compositeParams",
        "inputBindingsDigest",
        "publicationAllowed",
        "payloadDigest",
    }
)
_GLYPH_BASE_RESOLUTION_FIELDS = frozenset(
    {"assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest"}
)
_GLYPH_MASK_RESOLUTION_FIELDS = frozenset(
    {
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
)
_EFFECT_PREVIEW_RESOLUTION_FIELDS = frozenset(
    {"baseVideo", "effectExecutions", "glyphExecution"}
)
_EFFECT_PREVIEW_V3_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "effectResultBindings",
        "glyphRequirementBinding",
        "effectBindingsDigest",
        "baseVideo",
        "effectStages",
        "glyphStage",
        "audioMix",
        "subtitleManifest",
        "output",
        "publicationAllowed",
        "payloadDigest",
    }
)
_V3_EFFECT_PREVIEW_RESULT_FIELDS = frozenset(
    {
        "internalPath",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "effectResultBindings",
        "glyphRequirementBinding",
        "effectBindingsDigest",
        "mixRequestRef",
        "mixRequestDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "publicationAllowed",
    }
)
_V4_EFFECT_PREVIEW_RESULT_FIELDS = frozenset(
    {
        "schemaVersion",
        "compositionResultRef",
        "artifactRef",
        "executionRequestRef",
        "executionRequestDigest",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "effectResultBindings",
        "glyphRequirementBinding",
        "effectBindingsDigest",
        "mixRequestRef",
        "mixRequestDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "adapterIdentity",
        "provenance",
        "providerUsed",
        "gpuUsed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_PREVIEW_OUTPUT_PROBE_FIELDS = frozenset(
    {
        "container",
        "videoCodec",
        "pixelFormat",
        "width",
        "height",
        "frameRate",
        "frameCount",
        "audioCodec",
        "sampleRate",
        "channelCount",
        "sampleCount",
    }
)
_PREVIEW_OUTPUT_DIGEST_FIELDS = frozenset(
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
        "pcmContentDigest",
        "pcmDigestSpec",
        "sampleRate",
        "channelCount",
        "sampleCount",
    }
)


class MaskedSurfaceExecutionError(RuntimeError):
    """Raised when the closed V4/V3 execution boundary fails."""


class MaskedSurfaceRequestValidationError(MaskedSurfaceExecutionError):
    """Raised for a stale or open V5 execution request."""


class MaskedSurfaceAssetResolutionError(MaskedSurfaceExecutionError):
    """Raised for stale server-held AssetVersion or artifact facts."""


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
        raise MaskedSurfaceRequestValidationError(
            "masked-surface value is not canonical JSON"
        ) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise MaskedSurfaceRequestValidationError("payloadDigest is derived")
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return result


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise MaskedSurfaceRequestValidationError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _raw_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _RAW_SHA256.fullmatch(value) is None:
        raise MaskedSurfaceRequestValidationError(f"{field} is invalid")
    return value


def _prefixed_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _PREFIXED_SHA256.fullmatch(value) is None:
        raise MaskedSurfaceRequestValidationError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise MaskedSurfaceRequestValidationError(f"{field} is invalid")
    return value


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise MaskedSurfaceRequestValidationError(f"{field} is invalid")
    return value


def _point(
    value: Any,
    field: str,
    *,
    minimum: int = 0,
) -> dict[str, int]:
    point = _closed(value, _POINT_FIELDS, field)
    return {
        "xPermille": _integer(
            point["xPermille"], f"{field}.xPermille", minimum=minimum, maximum=1000
        ),
        "yPermille": _integer(
            point["yPermille"], f"{field}.yPermille", minimum=minimum, maximum=1000
        ),
    }


def _expected_execution_request_ref(request: Mapping[str, Any]) -> str:
    identity = {
        "schemaVersion": "v5.m13-masked-surface-execution-request-identity.v1",
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
    }
    return "m13-masked-surface-execution-" + sha256(
        _canonical_json(identity)
    ).hexdigest()[:32]


def _validate_keyframes(
    value: Any,
    *,
    fields: frozenset[str],
    value_field: str | None,
    value_minimum: int,
    value_maximum: int,
    start: int,
    end: int,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4_096:
        raise MaskedSurfaceRequestValidationError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    previous = -1
    for index, raw in enumerate(value):
        item = _closed(raw, fields, f"{label}[{index}]")
        frame = _integer(
            item["frame"], f"{label}[{index}].frame", minimum=start, maximum=end - 1
        )
        if frame <= previous:
            raise MaskedSurfaceRequestValidationError(
                f"{label} frames must be strictly increasing"
            )
        previous = frame
        interpolation = item.get("interpolation")
        if interpolation not in INTERPOLATIONS:
            raise MaskedSurfaceRequestValidationError(
                f"{label}[{index}].interpolation is invalid"
            )
        if value_field is None:
            _integer(
                item["xPermille"],
                f"{label}[{index}].xPermille",
                minimum=0,
                maximum=1000,
            )
            _integer(
                item["yPermille"],
                f"{label}[{index}].yPermille",
                minimum=0,
                maximum=1000,
            )
        else:
            _integer(
                item[value_field],
                f"{label}[{index}].{value_field}",
                minimum=value_minimum,
                maximum=value_maximum,
            )
        result.append(item)
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise MaskedSurfaceRequestValidationError(
            f"{label} must bind both frame-range boundaries"
        )
    return result


def _flame_smoke_execution_request_ref(request: Mapping[str, Any]) -> str:
    mode = request["effectMode"]
    identity = {
        "schemaVersion": "v5.m13-flame-smoke-execution-request-identity.v1",
        "effectMode": mode,
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "localExposureResultRef": (
            request["localExposureResultRef"]
            if mode == "FLAME_EXTINGUISH"
            else None
        ),
        "localExposureResultDigest": (
            request["localExposureResultDigest"]
            if mode == "FLAME_EXTINGUISH"
            else None
        ),
    }
    prefix = (
        "m13-flame-extinguish-execution-"
        if mode == "FLAME_EXTINGUISH"
        else "m13-smoke-execution-"
    )
    return prefix + sha256(_canonical_json(identity)).hexdigest()[:32]


def _request_asset(value: Any, label: str) -> dict[str, Any]:
    binding = _closed(value, _REQUEST_ASSET_FIELDS, label)
    _ref(binding["assetVersionRef"], f"{label}.assetVersionRef")
    _raw_digest(binding["assetVersionDigest"], f"{label}.assetVersionDigest")
    _prefixed_digest(binding["fileDigest"], f"{label}.fileDigest")
    _prefixed_digest(binding["pixelDigest"], f"{label}.pixelDigest")
    return binding


def _validate_e2_curve(
    value: Any,
    *,
    fields: frozenset[str],
    bounds: Mapping[str, tuple[int, int]],
    start: int,
    end: int,
    label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 4_096:
        raise MaskedSurfaceRequestValidationError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    previous = -1
    for index, raw in enumerate(value):
        item = _closed(raw, fields, f"{label}[{index}]")
        frame = _integer(
            item["frame"],
            f"{label}[{index}].frame",
            minimum=start,
            maximum=end - 1,
        )
        if frame <= previous or item["interpolation"] not in INTERPOLATIONS:
            raise MaskedSurfaceRequestValidationError(
                f"{label} order or interpolation is invalid"
            )
        previous = frame
        for field, (minimum, maximum) in bounds.items():
            _integer(
                item[field],
                f"{label}[{index}].{field}",
                minimum=minimum,
                maximum=maximum,
            )
        result.append(item)
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise MaskedSurfaceRequestValidationError(
            f"{label} must bind both frame-range boundaries"
        )
    return result


def validate_flame_smoke_execution_request(value: Any) -> dict[str, Any]:
    """Independently validate one storage-free V5 E2 execution request."""

    if not isinstance(value, Mapping):
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke request must be an object"
        )
    mode = value.get("effectMode")
    fields = (
        _FLAME_V5_REQUEST_FIELDS
        if mode == "FLAME_EXTINGUISH"
        else _SMOKE_V5_REQUEST_FIELDS
        if mode == "SMOKE"
        else frozenset()
    )
    if not fields:
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke effectMode is invalid"
        )
    request = _closed(value, fields, "flame/smoke request")
    supplied = _raw_digest(request.pop("payloadDigest"), "payloadDigest")
    if supplied != sha256(_canonical_json(request)).hexdigest():
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke payloadDigest is stale"
        )
    request["payloadDigest"] = supplied
    expected_schema = (
        FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION
        if mode == "FLAME_EXTINGUISH"
        else SMOKE_REQUIREMENT_SCHEMA_VERSION
    )
    if (
        request["schemaVersion"] != FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION
        or request["requirementSchemaVersion"] != expected_schema
        or request["publicationAllowed"] is not False
    ):
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke request boundary is invalid"
        )
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
    ):
        _ref(request[field], field)
    _raw_digest(request["requirementDigest"], "requirementDigest")
    shot = _closed(request["targetShot"], _TARGET_SHOT_FIELDS, "targetShot")
    _ref(shot["shotRef"], "targetShot.shotRef")
    _ref(shot["shotVersionRef"], "targetShot.shotVersionRef")
    _raw_digest(shot["shotVersionDigest"], "targetShot.shotVersionDigest")
    request["targetShot"] = shot
    base = _request_asset(request["basePlate"], "basePlate")
    request["basePlate"] = base
    start = _integer(
        request["frameRangeStartInclusive"],
        "frameRangeStartInclusive",
        minimum=0,
        maximum=10_000_000,
    )
    end = _integer(
        request["frameRangeEndExclusive"],
        "frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start:
        raise MaskedSurfaceRequestValidationError("flame/smoke frameRange is invalid")
    if request["blendMode"] not in BLEND_MODES:
        raise MaskedSurfaceRequestValidationError("flame/smoke blendMode is invalid")
    _integer(request["layer"], "layer", minimum=0, maximum=1024)

    if mode == "FLAME_EXTINGUISH":
        flame = _request_asset(request["flameMask"], "flameMask")
        if flame["assetVersionRef"] == base["assetVersionRef"]:
            raise MaskedSurfaceRequestValidationError(
                "basePlate and flameMask must be distinct"
            )
        states = request["stateSchedule"]
        if not isinstance(states, list) or not 4 <= len(states) <= 5:
            raise MaskedSurfaceRequestValidationError("stateSchedule is invalid")
        cursor = start
        sealed_states: list[dict[str, Any]] = []
        for index, raw in enumerate(states):
            item = _closed(
                raw,
                frozenset(
                    {"state", "startFrameInclusive", "endFrameExclusive"}
                ),
                f"stateSchedule[{index}]",
            )
            item_start = _integer(
                item["startFrameInclusive"],
                f"stateSchedule[{index}].startFrameInclusive",
                minimum=start,
                maximum=end - 1,
            )
            item_end = _integer(
                item["endFrameExclusive"],
                f"stateSchedule[{index}].endFrameExclusive",
                minimum=start + 1,
                maximum=end,
            )
            if item_start != cursor or item_end <= item_start:
                raise MaskedSurfaceRequestValidationError(
                    "stateSchedule is not exact and contiguous"
                )
            cursor = item_end
            sealed_states.append(item)
        profiles = {
            ("LIT", "DIMMING", "EXTINGUISHED", "DARK"),
            ("LIT", "DIMMING", "EXTINGUISHED", "EMBER", "DARK"),
        }
        if (
            cursor != end
            or tuple(item["state"] for item in sealed_states) not in profiles
        ):
            raise MaskedSurfaceRequestValidationError(
                "stateSchedule state order is invalid"
            )
        request["flameMask"] = flame
        request["stateSchedule"] = sealed_states
        request["brightnessCurve"] = _validate_e2_curve(
            request["brightnessCurve"],
            fields=frozenset({"frame", "valuePermille", "interpolation"}),
            bounds={"valuePermille": (0, 1000)},
            start=start,
            end=end,
            label="brightnessCurve",
        )
        request["alphaCurve"] = _validate_e2_curve(
            request["alphaCurve"],
            fields=frozenset({"frame", "valuePermille", "interpolation"}),
            bounds={"valuePermille": (0, 1000)},
            start=start,
            end=end,
            label="alphaCurve",
        )
        dark_start = next(
            item["startFrameInclusive"]
            for item in sealed_states
            if item["state"] == "DARK"
        )
        for label in ("brightnessCurve", "alphaCurve"):
            curve = request[label]
            values = [item["valuePermille"] for item in curve]
            if (
                values[0] <= 0
                or any(
                    left < right for left, right in zip(values, values[1:])
                )
                or not any(item["frame"] == dark_start for item in curve)
                or any(
                    item["valuePermille"] != 0
                    for item in curve
                    if item["frame"] >= dark_start
                )
            ):
                raise MaskedSurfaceRequestValidationError(
                    f"{label} extinction profile is invalid"
                )
        for field in ("localExposureRequirementRef", "localExposureResultRef"):
            _ref(request[field], field)
        for field in (
            "localExposureRequirementDigest",
            "localExposureResultDigest",
        ):
            _raw_digest(request[field], field)
    else:
        emission = _request_asset(request["emissionMask"], "emissionMask")
        if emission["assetVersionRef"] == base["assetVersionRef"]:
            raise MaskedSurfaceRequestValidationError(
                "basePlate and emissionMask must be distinct"
            )
        source_kind = request["smokeSourceKind"]
        if source_kind == "PINNED_SMOKE_LAYER":
            layer = _request_asset(request["smokeLayer"], "smokeLayer")
            if layer["assetVersionRef"] in {
                base["assetVersionRef"],
                emission["assetVersionRef"],
            }:
                raise MaskedSurfaceRequestValidationError(
                    "Smoke AssetVersions must be distinct"
                )
            if any(
                request[field] is not None
                for field in (
                    "algorithmIdentity",
                    "algorithmVersion",
                    "deterministicSeed",
                )
            ):
                raise MaskedSurfaceRequestValidationError(
                    "pinned smoke cannot select a procedural algorithm"
                )
        elif source_kind == "DETERMINISTIC_CPU_PROCEDURAL":
            layer = None
            if (
                request["smokeLayer"] is not None
                or request["algorithmIdentity"] != "v3.deterministic-smoke-cpu"
                or request["algorithmVersion"] != "1"
            ):
                raise MaskedSurfaceRequestValidationError(
                    "procedural smoke algorithm is not frozen"
                )
            _integer(
                request["deterministicSeed"],
                "deterministicSeed",
                minimum=0,
                maximum=(1 << 63) - 1,
            )
        else:
            raise MaskedSurfaceRequestValidationError(
                "smokeSourceKind is invalid"
            )
        request["smokeLayer"] = layer
        request["emissionMask"] = emission
        for field, bounds in (
            ("opacitySchedule", {"valuePermille": (0, 1000)}),
            (
                "positionKeyframes",
                {"xPermille": (0, 1000), "yPermille": (0, 1000)},
            ),
            (
                "scaleKeyframes",
                {"xPermille": (1, 4000), "yPermille": (1, 4000)},
            ),
            (
                "driftKeyframes",
                {
                    "xDeltaPermille": (-4000, 4000),
                    "yDeltaPermille": (-4000, 4000),
                },
            ),
            ("dissipationCurve", {"valuePermille": (0, 1000)}),
        ):
            curve_fields = frozenset({"frame", "interpolation", *bounds})
            request[field] = _validate_e2_curve(
                request[field],
                fields=curve_fields,
                bounds=bounds,
                start=start,
                end=end,
                label=field,
            )
    requirement_projection: dict[str, Any] = {
        "schemaVersion": request["requirementSchemaVersion"],
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementRef": request["requirementRef"],
        "effectMode": request["effectMode"],
        "targetShotRef": request["targetShot"]["shotRef"],
        "targetShotVersionRef": request["targetShot"]["shotVersionRef"],
        "targetShotVersionDigest": request["targetShot"]["shotVersionDigest"],
        "basePlateAssetVersionRef": request["basePlate"]["assetVersionRef"],
        "basePlateAssetVersionDigest": request["basePlate"]["assetVersionDigest"],
        "basePlateFileDigest": request["basePlate"]["fileDigest"],
        "basePlatePixelDigest": request["basePlate"]["pixelDigest"],
        "frameRangeStartInclusive": request["frameRangeStartInclusive"],
        "frameRangeEndExclusive": request["frameRangeEndExclusive"],
        "blendMode": request["blendMode"],
        "layer": request["layer"],
        "publicationAllowed": False,
    }
    if mode == "FLAME_EXTINGUISH":
        requirement_projection.update(
            {
                "flameMaskAssetVersionRef": request["flameMask"][
                    "assetVersionRef"
                ],
                "flameMaskAssetVersionDigest": request["flameMask"][
                    "assetVersionDigest"
                ],
                "flameMaskFileDigest": request["flameMask"]["fileDigest"],
                "flameMaskPixelDigest": request["flameMask"]["pixelDigest"],
                "stateSchedule": deepcopy(request["stateSchedule"]),
                "brightnessCurve": deepcopy(request["brightnessCurve"]),
                "alphaCurve": deepcopy(request["alphaCurve"]),
                "localExposureRequirementRef": request[
                    "localExposureRequirementRef"
                ],
                "localExposureRequirementDigest": request[
                    "localExposureRequirementDigest"
                ],
            }
        )
    else:
        smoke_layer = request["smokeLayer"]
        requirement_projection.update(
            {
                "smokeSourceKind": request["smokeSourceKind"],
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
                "emissionMaskAssetVersionRef": request["emissionMask"][
                    "assetVersionRef"
                ],
                "emissionMaskAssetVersionDigest": request["emissionMask"][
                    "assetVersionDigest"
                ],
                "emissionMaskFileDigest": request["emissionMask"]["fileDigest"],
                "emissionMaskPixelDigest": request["emissionMask"]["pixelDigest"],
                "opacitySchedule": deepcopy(request["opacitySchedule"]),
                "positionKeyframes": deepcopy(request["positionKeyframes"]),
                "scaleKeyframes": deepcopy(request["scaleKeyframes"]),
                "driftKeyframes": deepcopy(request["driftKeyframes"]),
                "dissipationCurve": deepcopy(request["dissipationCurve"]),
                "algorithmIdentity": request["algorithmIdentity"],
                "algorithmVersion": request["algorithmVersion"],
                "deterministicSeed": request["deterministicSeed"],
            }
        )
    if sha256(_canonical_json(requirement_projection)).hexdigest() != request[
        "requirementDigest"
    ]:
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke Requirement projection is stale"
        )
    if request["executionRequestRef"] != _flame_smoke_execution_request_ref(request):
        raise MaskedSurfaceRequestValidationError(
            "flame/smoke executionRequestRef derivation is invalid"
        )
    return request


def validate_masked_surface_execution_request(value: Any) -> dict[str, Any]:
    """Independently validate one sealed, path-free V5 request."""

    request = _closed(value, _V5_REQUEST_FIELDS, "masked-surface request")
    supplied = _raw_digest(request.pop("payloadDigest"), "payloadDigest")
    if supplied != sha256(_canonical_json(request)).hexdigest():
        raise MaskedSurfaceRequestValidationError("payloadDigest is stale")
    request["payloadDigest"] = supplied
    if (
        request["schemaVersion"]
        != MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION
        or request["publicationAllowed"] is not False
    ):
        raise MaskedSurfaceRequestValidationError(
            "masked-surface request boundary is invalid"
        )
    for field in ("executionRequestRef", "workspaceRef", "productionRunRef", "requirementRef"):
        _ref(request[field], field)
    _raw_digest(request["requirementDigest"], "requirementDigest")
    if request["executionRequestRef"] != _expected_execution_request_ref(request):
        raise MaskedSurfaceRequestValidationError(
            "executionRequestRef derivation is invalid"
        )

    schema = request["requirementSchemaVersion"]
    mode = request["effectMode"]
    if (
        schema == SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION
        and mode in {"SCRATCH_REVEAL", "LIGHT_SWEEP"}
    ):
        pass
    elif schema == LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION and mode == "LOCAL_EXPOSURE":
        pass
    else:
        raise MaskedSurfaceRequestValidationError(
            "requirement schema and effectMode are inconsistent"
        )

    shot = _closed(request["targetShot"], _TARGET_SHOT_FIELDS, "targetShot")
    _ref(shot["shotRef"], "targetShot.shotRef")
    _ref(shot["shotVersionRef"], "targetShot.shotVersionRef")
    _raw_digest(shot["shotVersionDigest"], "targetShot.shotVersionDigest")
    bindings: list[dict[str, Any]] = []
    for label in ("basePlate", "mask"):
        binding = _closed(request[label], _REQUEST_ASSET_FIELDS, label)
        _ref(binding["assetVersionRef"], f"{label}.assetVersionRef")
        _raw_digest(binding["assetVersionDigest"], f"{label}.assetVersionDigest")
        _prefixed_digest(binding["fileDigest"], f"{label}.fileDigest")
        _prefixed_digest(binding["pixelDigest"], f"{label}.pixelDigest")
        bindings.append(binding)
    if bindings[0]["assetVersionRef"] == bindings[1]["assetVersionRef"]:
        raise MaskedSurfaceRequestValidationError(
            "basePlate and mask AssetVersions must be distinct"
        )

    start = _integer(
        request["frameRangeStartInclusive"],
        "frameRangeStartInclusive",
        minimum=0,
        maximum=10_000_000,
    )
    end = _integer(
        request["frameRangeEndExclusive"],
        "frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start:
        raise MaskedSurfaceRequestValidationError("frameRange is invalid")

    schedule = request["explicitSchedule"]
    if not isinstance(schedule, list) or not 1 <= len(schedule) <= 4_096:
        raise MaskedSurfaceRequestValidationError("explicitSchedule is invalid")
    previous_end = start
    any_enabled = False
    for index, raw in enumerate(schedule):
        item = _closed(raw, _SCHEDULE_FIELDS, f"explicitSchedule[{index}]")
        item_start = _integer(
            item["startFrameInclusive"],
            f"explicitSchedule[{index}].startFrameInclusive",
            minimum=start,
            maximum=end - 1,
        )
        item_end = _integer(
            item["endFrameExclusive"],
            f"explicitSchedule[{index}].endFrameExclusive",
            minimum=start + 1,
            maximum=end,
        )
        if (
            item_start != previous_end
            or item_end <= item_start
            or type(item["enabled"]) is not bool
            or item["interpolation"] != "STEP"
        ):
            raise MaskedSurfaceRequestValidationError(
                "explicitSchedule must be contiguous, closed, and STEP-interpolated"
            )
        previous_end = item_end
        any_enabled = any_enabled or item["enabled"]
    if previous_end != end or not any_enabled:
        raise MaskedSurfaceRequestValidationError(
            "explicitSchedule must cover and enable the exact frameRange"
        )

    position = _point(request["position"], "position")
    _point(request["scale"], "scale", minimum=1)
    trajectory = _validate_keyframes(
        request["trajectoryKeyframes"],
        fields=_TRAJECTORY_FIELDS,
        value_field=None,
        value_minimum=0,
        value_maximum=1000,
        start=start,
        end=end,
        label="trajectoryKeyframes",
    )
    if (
        trajectory[0]["xPermille"], trajectory[0]["yPermille"]
    ) != (position["xPermille"], position["yPermille"]):
        raise MaskedSurfaceRequestValidationError(
            "trajectoryKeyframes must start at position"
        )
    scale = request["scale"]
    if any(
        item["xPermille"] + scale["xPermille"] > 1000
        or item["yPermille"] + scale["yPermille"] > 1000
        for item in trajectory
    ):
        raise MaskedSurfaceRequestValidationError(
            "trajectoryKeyframes exceed the output canvas"
        )
    _validate_keyframes(
        request["intensityCurve"],
        fields=_INTENSITY_FIELDS,
        value_field="valuePermille",
        value_minimum=0,
        value_maximum=1000,
        start=start,
        end=end,
        label="intensityCurve",
    )
    _validate_keyframes(
        request["exposureCurve"],
        fields=_EXPOSURE_FIELDS,
        value_field="valueMilliStops",
        value_minimum=-8000,
        value_maximum=8000,
        start=start,
        end=end,
        label="exposureCurve",
    )

    perspective = _closed(request["perspective"], _PERSPECTIVE_FIELDS, "perspective")
    quad = perspective["quadPermille"]
    if perspective["mode"] == "NONE":
        if quad != []:
            raise MaskedSurfaceRequestValidationError(
                "NONE perspective cannot contain a quad"
            )
    elif perspective["mode"] == "FIXED_QUAD":
        if not isinstance(quad, list) or len(quad) != 4:
            raise MaskedSurfaceRequestValidationError(
                "FIXED_QUAD perspective requires four points"
            )
        for index, point in enumerate(quad):
            _point(point, f"perspective.quadPermille[{index}]")
        if not (
            quad[0]["xPermille"] < quad[1]["xPermille"]
            and quad[2]["xPermille"] < quad[3]["xPermille"]
            and quad[0]["yPermille"] < quad[2]["yPermille"]
            and quad[1]["yPermille"] < quad[3]["yPermille"]
        ):
            raise MaskedSurfaceRequestValidationError(
                "FIXED_QUAD points are not in canonical corner order"
            )
    else:
        raise MaskedSurfaceRequestValidationError("perspective.mode is invalid")
    if request["blendMode"] not in BLEND_MODES:
        raise MaskedSurfaceRequestValidationError("blendMode is invalid")
    _integer(request["layer"], "layer", minimum=0, maximum=1024)
    return request


def _storage_key(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise MaskedSurfaceAssetResolutionError(f"{field} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise MaskedSurfaceAssetResolutionError(f"{field} is invalid")
    return value


def _server_file(root: Path, storage_key: str, *, label: str) -> Path:
    """Resolve one server-held key while rejecting every symlink component."""

    key = _storage_key(storage_key, f"{label}.storageKey")
    current = root
    try:
        for part in PurePosixPath(key).parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise MaskedSurfaceAssetResolutionError(
                    f"{label} storage cannot contain symlinks"
                )
        metadata = os.stat(current, follow_symlinks=False)
    except MaskedSurfaceAssetResolutionError:
        raise
    except OSError as exc:
        raise MaskedSurfaceAssetResolutionError(
            f"{label} storage is unavailable"
        ) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise MaskedSurfaceAssetResolutionError(
            f"{label} storage is not a regular file"
        )
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise MaskedSurfaceAssetResolutionError(
            f"{label} storage is unavailable"
        ) from exc
    if root not in resolved.parents:
        raise MaskedSurfaceAssetResolutionError(f"{label} escaped the artifact root")
    return resolved


def _resolved_record(
    value: Any,
    *,
    fields: frozenset[str],
    label: str,
) -> dict[str, Any]:
    try:
        record = _closed(value, fields, label)
        _ref(record["assetVersionRef"], f"{label}.assetVersionRef")
        _raw_digest(record["assetVersionDigest"], f"{label}.assetVersionDigest")
        _storage_key(record["storageKey"], f"{label}.storageKey")
        _prefixed_digest(record["fileDigest"], f"{label}.fileDigest")
        if "pixelDigest" in record:
            _prefixed_digest(record["pixelDigest"], f"{label}.pixelDigest")
        return record
    except MaskedSurfaceAssetResolutionError:
        raise
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceAssetResolutionError(f"{label} is invalid") from exc


def _resolve_asset_versions(
    request: Mapping[str, Any],
    resolved_asset_versions: Any,
    *,
    artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(resolved_asset_versions, Mapping):
        raise MaskedSurfaceAssetResolutionError(
            "resolved_asset_versions must be a server-held mapping"
        )
    expected_refs = {
        request["basePlate"]["assetVersionRef"],
        request["mask"]["assetVersionRef"],
    }
    if set(resolved_asset_versions) != expected_refs:
        raise MaskedSurfaceAssetResolutionError(
            "resolved AssetVersion set does not match the request"
        )
    base = _resolved_record(
        resolved_asset_versions[request["basePlate"]["assetVersionRef"]],
        fields=_RESOLVED_BASE_FIELDS,
        label="resolved basePlate",
    )
    mask = _resolved_record(
        resolved_asset_versions[request["mask"]["assetVersionRef"]],
        fields=_RESOLVED_MASK_FIELDS,
        label="resolved mask",
    )
    for label, requested, resolved in (
        ("basePlate", request["basePlate"], base),
        ("mask", request["mask"], mask),
    ):
        if any(
            resolved[field] != requested[field]
            for field in _REQUEST_ASSET_FIELDS
        ):
            raise MaskedSurfaceAssetResolutionError(
                f"{label} AssetVersion binding is stale"
            )

    try:
        width = _integer(base["width"], "basePlate.width", minimum=2, maximum=16_384)
        height = _integer(base["height"], "basePlate.height", minimum=2, maximum=16_384)
        frame_count = _integer(
            base["frameCount"], "basePlate.frameCount", minimum=1, maximum=10_000_000
        )
        _integer(base["frameRate"], "basePlate.frameRate", minimum=1, maximum=240)
        _integer(mask["width"], "mask.width", minimum=1, maximum=16_384)
        _integer(mask["height"], "mask.height", minimum=1, maximum=16_384)
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceAssetResolutionError(
            "resolved AssetVersion media facts are invalid"
        ) from exc
    if (
        base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or base["pixelFormat"] != "yuv420p"
        or width % 2
        or height % 2
        or mask["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC
        or mask["pixelMode"] != "RGBA"
        or request["frameRangeEndExclusive"] > frame_count
    ):
        raise MaskedSurfaceAssetResolutionError(
            "resolved AssetVersion media contract is unsupported or stale"
        )

    base_path = _server_file(
        artifact_root, base["storageKey"], label="resolved basePlate"
    )
    mask_path = _server_file(
        artifact_root, mask["storageKey"], label="resolved mask"
    )
    try:
        if file_digest(base_path) != base["fileDigest"]:
            raise MaskedSurfaceAssetResolutionError(
                "basePlate file digest is stale"
            )
        base_pixels = decoded_frame_pixel_digest_metadata(base_path)
        if (
            base_pixels.get("fileDigest") != base["fileDigest"]
            or base_pixels.get("decodedFramePixelDigest") != base["pixelDigest"]
            or base_pixels.get("decodedFramePixelDigestSpec")
            != base["pixelDigestSpec"]
            or base_pixels.get("width") != base["width"]
            or base_pixels.get("height") != base["height"]
            or base_pixels.get("frameCount") != base["frameCount"]
        ):
            raise MaskedSurfaceAssetResolutionError(
                "basePlate decoded-frame identity is stale"
            )
        if file_digest(mask_path) != mask["fileDigest"]:
            raise MaskedSurfaceAssetResolutionError("mask file digest is stale")
        mask_pixels = image_digest_metadata(mask_path)
        if (
            mask_pixels.get("pixel_digest") != mask["pixelDigest"]
            or mask_pixels.get("pixel_digest_spec") != mask["pixelDigestSpec"]
            or mask_pixels.get("pixel_mode") != mask["pixelMode"]
            or mask_pixels.get("width") != mask["width"]
            or mask_pixels.get("height") != mask["height"]
        ):
            raise MaskedSurfaceAssetResolutionError(
                "mask decoded-pixel identity is stale"
            )
    except MaskedSurfaceAssetResolutionError:
        raise
    except DigestError as exc:
        raise MaskedSurfaceAssetResolutionError(
            "resolved AssetVersion content could not be measured"
        ) from exc
    return base, mask


def _build_v3_request(
    request: Mapping[str, Any],
    *,
    base: Mapping[str, Any],
    mask: Mapping[str, Any],
) -> dict[str, Any]:
    result = _seal(
        {
            "schemaVersion": MASKED_SURFACE_V3_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": request["executionRequestRef"],
            "v5ExecutionRequestDigest": request["payloadDigest"],
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "requirementSchemaVersion": request["requirementSchemaVersion"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "targetShot": deepcopy(request["targetShot"]),
            "basePlate": deepcopy(dict(base)),
            "mask": deepcopy(dict(mask)),
            "frameRangeStartInclusive": request["frameRangeStartInclusive"],
            "frameRangeEndExclusive": request["frameRangeEndExclusive"],
            "explicitSchedule": deepcopy(request["explicitSchedule"]),
            "trajectoryKeyframes": deepcopy(request["trajectoryKeyframes"]),
            "intensityCurve": deepcopy(request["intensityCurve"]),
            "exposureCurve": deepcopy(request["exposureCurve"]),
            "position": deepcopy(request["position"]),
            "scale": deepcopy(request["scale"]),
            "perspective": deepcopy(request["perspective"]),
            "blendMode": request["blendMode"],
            "layer": request["layer"],
            "output": {
                "width": base["width"],
                "height": base["height"],
                "frameCount": base["frameCount"],
                "frameRate": base["frameRate"],
                "pixelFormat": "yuv420p",
                "container": "mp4",
                "videoCodec": "h264",
            },
            "publicationAllowed": False,
        }
    )
    if set(result) != _V3_REQUEST_FIELDS:
        raise MaskedSurfaceRequestValidationError(
            "derived V3 request fields are invalid"
        )
    return result


def _resolve_flame_smoke_assets(
    request: Mapping[str, Any],
    resolved_asset_versions: Any,
    *,
    artifact_root: Path,
) -> dict[str, dict[str, Any]]:
    if not isinstance(resolved_asset_versions, Mapping):
        raise MaskedSurfaceAssetResolutionError(
            "resolved_asset_versions must be a server-held mapping"
        )
    names = (
        ("basePlate", "flameMask")
        if request["effectMode"] == "FLAME_EXTINGUISH"
        else (
            ("basePlate", "emissionMask")
            if request["smokeLayer"] is None
            else ("basePlate", "emissionMask", "smokeLayer")
        )
    )
    expected_refs = {request[name]["assetVersionRef"] for name in names}
    if set(resolved_asset_versions) != expected_refs:
        raise MaskedSurfaceAssetResolutionError(
            "resolved Flame/Smoke AssetVersion set does not match the request"
        )
    result: dict[str, dict[str, Any]] = {}
    base_ref = request["basePlate"]["assetVersionRef"]
    for image_name in names[1:]:
        image_ref = request[image_name]["assetVersionRef"]
        pair_request = {
            "basePlate": request["basePlate"],
            "mask": request[image_name],
            "frameRangeEndExclusive": request["frameRangeEndExclusive"],
        }
        base, image = _resolve_asset_versions(
            pair_request,
            {
                base_ref: resolved_asset_versions[base_ref],
                image_ref: resolved_asset_versions[image_ref],
            },
            artifact_root=artifact_root,
        )
        if "basePlate" in result and result["basePlate"] != base:
            raise MaskedSurfaceAssetResolutionError(
                "resolved Flame/Smoke basePlate changed during resolution"
            )
        result["basePlate"] = base
        result[image_name] = image
    return result


def _resolve_flame_local_exposure_stage(
    request: Mapping[str, Any],
    resolved_effect_dependencies: Any,
    *,
    artifact_root: Path,
    base: Mapping[str, Any],
    flame_mask: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not isinstance(resolved_effect_dependencies, Mapping)
        or set(resolved_effect_dependencies)
        != {request["localExposureResultRef"]}
    ):
        raise MaskedSurfaceAssetResolutionError(
            "Flame requires its exact LocalExposure Result dependency"
        )
    raw = resolved_effect_dependencies[request["localExposureResultRef"]]
    resolved = _closed(
        raw,
        _EFFECT_EXECUTION_RESOLUTION_FIELDS,
        "Flame LocalExposure dependency",
    )
    local_request = validate_masked_surface_execution_request(
        resolved["executionRequest"]
    )
    requirement = _validate_requirement_binding(
        resolved["requirement"], execution_request=local_request
    )
    runtime = validate_masked_surface_runtime_evidence(
        resolved["runtimeEvidence"]
    )
    artifact = validate_masked_surface_artifact_evidence(
        resolved["artifactEvidence"], runtime_evidence=runtime
    )
    local_lineage = {
        "workspaceRef": local_request["workspaceRef"],
        "productionRunRef": local_request["productionRunRef"],
        "requirementRef": local_request["requirementRef"],
        "requirementDigest": local_request["requirementDigest"],
        "executionRequestRef": local_request["executionRequestRef"],
        "executionRequestDigest": local_request["payloadDigest"],
        "effectMode": local_request["effectMode"],
    }
    if any(
        runtime[field] != expected or artifact[field] != expected
        for field, expected in local_lineage.items()
    ):
        raise MaskedSurfaceExecutionError(
            "LocalExposure evidence does not bind its execution request"
        )
    _validate_result_binding(
        resolved["result"],
        binding={
            "resultRef": request["localExposureResultRef"],
            "resultDigest": request["localExposureResultDigest"],
        },
        request=local_request,
        artifact=artifact,
        runtime=runtime,
    )
    local_base, local_mask = _resolve_asset_versions(
        local_request,
        resolved["assetVersions"],
        artifact_root=artifact_root,
    )
    _validate_effect_artifact_storage(
        resolved["artifactStorage"],
        artifact=artifact,
        runtime_evidence=runtime,
        artifact_root=artifact_root,
    )
    exact = (
        local_request["effectMode"] == "LOCAL_EXPOSURE"
        and local_request["workspaceRef"] == request["workspaceRef"]
        and local_request["productionRunRef"] == request["productionRunRef"]
        and local_request["requirementRef"]
        == request["localExposureRequirementRef"]
        and local_request["requirementDigest"]
        == request["localExposureRequirementDigest"]
        and local_request["targetShot"] == request["targetShot"]
        and local_request["frameRangeStartInclusive"]
        == request["frameRangeStartInclusive"]
        and local_request["frameRangeEndExclusive"]
        == request["frameRangeEndExclusive"]
        and local_request["exposureCurve"][-1]["valueMilliStops"] < 0
        and all(local_base[field] == base[field] for field in _RESOLVED_BASE_FIELDS)
        and all(
            local_mask[field] == flame_mask[field]
            for field in _RESOLVED_MASK_FIELDS
        )
    )
    if not exact or requirement["payloadDigest"] != request[
        "localExposureRequirementDigest"
    ]:
        raise MaskedSurfaceExecutionError(
            "Flame LocalExposure dependency is stale"
        )
    local_stage = _build_v3_request(
        local_request, base=local_base, mask=local_mask
    )
    if (
        runtime["v3ExecutionRequestDigest"] != local_stage["payloadDigest"]
        or artifact["v3ExecutionRequestDigest"]
        != local_stage["payloadDigest"]
    ):
        raise MaskedSurfaceExecutionError(
            "LocalExposure evidence does not bind the rebuilt V3 request"
        )
    return local_stage


def _build_flame_smoke_v3_request(
    request: Mapping[str, Any],
    *,
    assets: Mapping[str, Mapping[str, Any]],
    local_exposure_stage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    common: dict[str, Any] = {
        "schemaVersion": FLAME_SMOKE_V3_REQUEST_SCHEMA_VERSION,
        "v5ExecutionRequestRef": request["executionRequestRef"],
        "v5ExecutionRequestDigest": request["payloadDigest"],
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementSchemaVersion": request["requirementSchemaVersion"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "effectMode": request["effectMode"],
        "targetShot": deepcopy(request["targetShot"]),
        "basePlate": deepcopy(dict(assets["basePlate"])),
        "frameRangeStartInclusive": request["frameRangeStartInclusive"],
        "frameRangeEndExclusive": request["frameRangeEndExclusive"],
        "blendMode": request["blendMode"],
        "layer": request["layer"],
        "output": {
            "width": assets["basePlate"]["width"],
            "height": assets["basePlate"]["height"],
            "frameCount": assets["basePlate"]["frameCount"],
            "frameRate": assets["basePlate"]["frameRate"],
            "pixelFormat": "yuv420p",
            "container": "mp4",
            "videoCodec": "h264",
        },
        "publicationAllowed": False,
    }
    if request["effectMode"] == "FLAME_EXTINGUISH":
        if local_exposure_stage is None:
            raise MaskedSurfaceExecutionError(
                "Flame LocalExposure stage was not resolved"
            )
        common.update(
            {
                "flameMask": deepcopy(dict(assets["flameMask"])),
                "stateSchedule": deepcopy(request["stateSchedule"]),
                "brightnessCurve": deepcopy(request["brightnessCurve"]),
                "alphaCurve": deepcopy(request["alphaCurve"]),
                "localExposureRequirementRef": request[
                    "localExposureRequirementRef"
                ],
                "localExposureRequirementDigest": request[
                    "localExposureRequirementDigest"
                ],
                "localExposureResultRef": request["localExposureResultRef"],
                "localExposureResultDigest": request[
                    "localExposureResultDigest"
                ],
                "localExposureStage": deepcopy(dict(local_exposure_stage)),
            }
        )
        fields = _FLAME_V3_REQUEST_FIELDS
    else:
        common.update(
            {
                "smokeSourceKind": request["smokeSourceKind"],
                "smokeLayer": (
                    None
                    if request["smokeLayer"] is None
                    else deepcopy(dict(assets["smokeLayer"]))
                ),
                "emissionMask": deepcopy(dict(assets["emissionMask"])),
                "opacitySchedule": deepcopy(request["opacitySchedule"]),
                "positionKeyframes": deepcopy(request["positionKeyframes"]),
                "scaleKeyframes": deepcopy(request["scaleKeyframes"]),
                "driftKeyframes": deepcopy(request["driftKeyframes"]),
                "dissipationCurve": deepcopy(request["dissipationCurve"]),
                "algorithmIdentity": request["algorithmIdentity"],
                "algorithmVersion": request["algorithmVersion"],
                "deterministicSeed": request["deterministicSeed"],
            }
        )
        fields = _SMOKE_V3_REQUEST_FIELDS
    sealed = _seal(common)
    if set(sealed) != fields:
        raise MaskedSurfaceExecutionError(
            "derived Flame/Smoke V3 request fields are invalid"
        )
    return sealed


def _expected_output_storage_key(
    request: Mapping[str, Any],
    *,
    renderer_version: str = MASKED_SURFACE_RENDERER_VERSION_CURRENT,
) -> str:
    workspace = sha256(str(request["workspaceRef"]).encode("utf-8")).hexdigest()[:20]
    run = sha256(str(request["productionRunRef"]).encode("utf-8")).hexdigest()[:20]
    if renderer_version == MASKED_SURFACE_RENDERER_VERSION_V1:
        filename = f"masked-surface-{request['payloadDigest']}.mp4"
    elif renderer_version == MASKED_SURFACE_RENDERER_VERSION_V2:
        filename = f"masked-surface-v2-{request['payloadDigest']}.mp4"
    elif renderer_version == MASKED_SURFACE_RENDERER_VERSION_V3:
        filename = f"masked-surface-v3-{request['payloadDigest']}.mp4"
    else:
        raise MaskedSurfaceExecutionError(
            "masked-surface artifact renderer version is unsupported"
        )
    return str(
        PurePosixPath(
            workspace,
            run,
            "masked-surface",
            filename,
        )
    )


def _runtime_digest(result: Mapping[str, Any]) -> str:
    identity = {
        "ffmpegIdentity": result["ffmpegIdentity"],
        "rendererIdentity": result["rendererIdentity"],
        "rendererVersion": result["rendererVersion"],
    }
    return "sha256:" + sha256(_canonical_json(identity)).hexdigest()


def _validate_v3_result(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    try:
        result = _closed(value, _V3_RESULT_FIELDS, "V3 masked-surface result")
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 result fields are invalid") from exc
    expected_output = request["output"]
    if (
        result["v5ExecutionRequestRef"] != request["v5ExecutionRequestRef"]
        or result["v5ExecutionRequestDigest"] != request["v5ExecutionRequestDigest"]
        or result["v3ExecutionRequestDigest"] != request["payloadDigest"]
        or result["requirementRef"] != request["requirementRef"]
        or result["requirementDigest"] != request["requirementDigest"]
        or result["effectMode"] != request["effectMode"]
        or result["publicationAllowed"] is not False
    ):
        raise MaskedSurfaceExecutionError("V3 result lineage is stale")
    expected_key = _expected_output_storage_key(request)
    if result["outputStorageKey"] != expected_key:
        raise MaskedSurfaceExecutionError("V3 result storage lineage is invalid")
    output_path = _server_file(
        artifact_root, result["outputStorageKey"], label="V3 output"
    )
    if str(output_path) != result["internalPath"]:
        raise MaskedSurfaceExecutionError("V3 internal output path is stale")
    try:
        byte_size = _integer(
            result["outputByteSize"],
            "outputByteSize",
            minimum=1,
            maximum=10**12,
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 outputByteSize is invalid") from exc
    if output_path.stat().st_size != byte_size:
        raise MaskedSurfaceExecutionError("V3 output byte size is stale")
    probe = result["outputMediaProbe"]
    if not isinstance(probe, Mapping) or set(probe) != _OUTPUT_FIELDS or probe != expected_output:
        raise MaskedSurfaceExecutionError("V3 output media facts are stale")
    digest = result["outputDigest"]
    if not isinstance(digest, Mapping) or set(digest) != _OUTPUT_DIGEST_FIELDS:
        raise MaskedSurfaceExecutionError("V3 output digest fields are invalid")
    expected_digest_media = {
        "width": expected_output["width"],
        "height": expected_output["height"],
        "frameCount": expected_output["frameCount"],
        "frameRate": expected_output["frameRate"],
    }
    try:
        _prefixed_digest(digest["fileDigest"], "outputDigest.fileDigest")
        _prefixed_digest(
            digest["decodedFramePixelDigest"],
            "outputDigest.decodedFramePixelDigest",
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 output digest is invalid") from exc
    if (
        digest["fileDigestAlgorithm"] != "sha256"
        or digest["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or digest["pixelMode"] != "RGBA"
        or {field: digest[field] for field in expected_digest_media}
        != expected_digest_media
    ):
        raise MaskedSurfaceExecutionError("V3 output digest contract is stale")
    identity = result["ffmpegIdentity"]
    if (
        result["rendererIdentity"] != MASKED_SURFACE_RENDERER_IDENTITY
        or result["rendererVersion"] != MASKED_SURFACE_RENDERER_VERSION_CURRENT
        or not isinstance(identity, str)
        or identity != identity.strip()
        or not 1 <= len(identity) <= 500
        or any(ord(character) < 32 or ord(character) == 127 for character in identity)
        or result["runtimeEvidenceDigest"] != _runtime_digest(result)
    ):
        raise MaskedSurfaceExecutionError("V3 runtime evidence is stale")
    try:
        measured = decoded_frame_pixel_digest_metadata(output_path)
    except DigestError as exc:
        raise MaskedSurfaceExecutionError("V3 output could not be remeasured") from exc
    if (
        measured.get("fileDigest") != digest["fileDigest"]
        or measured.get("decodedFramePixelDigest")
        != digest["decodedFramePixelDigest"]
        or measured.get("decodedFramePixelDigestSpec")
        != digest["decodedFramePixelDigestSpec"]
        or measured.get("width") != digest["width"]
        or measured.get("height") != digest["height"]
        or measured.get("frameCount") != digest["frameCount"]
    ):
        raise MaskedSurfaceExecutionError("V3 output content digest is stale")
    return result


def _evidence_ref(prefix: str, identity: Mapping[str, Any]) -> str:
    return prefix + sha256(_canonical_json(identity)).hexdigest()[:32]


def _build_evidence(
    *,
    v5_request: Mapping[str, Any],
    v3_request: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_ref = _evidence_ref(
        "m13-masked-surface-runtime-evidence-",
        {
            "v3ExecutionRequestDigest": v3_request["payloadDigest"],
            "rendererIdentity": result["rendererIdentity"],
            "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"],
        },
    )
    runtime = _seal(
        {
            "schemaVersion": MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION,
            "runtimeEvidenceRef": runtime_ref,
            "workspaceRef": v5_request["workspaceRef"],
            "productionRunRef": v5_request["productionRunRef"],
            "requirementRef": v5_request["requirementRef"],
            "requirementDigest": v5_request["requirementDigest"],
            "executionRequestRef": v5_request["executionRequestRef"],
            "executionRequestDigest": v5_request["payloadDigest"],
            "v3ExecutionRequestDigest": v3_request["payloadDigest"],
            "effectMode": v5_request["effectMode"],
            "rendererIdentity": result["rendererIdentity"],
            "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"],
            "gpuUsed": False,
            "publicationAllowed": False,
        }
    )
    if set(runtime) != _RUNTIME_EVIDENCE_FIELDS:
        raise MaskedSurfaceExecutionError("runtime evidence fields are invalid")
    artifact_ref = _evidence_ref(
        "m13-masked-surface-artifact-evidence-",
        {
            "v3ExecutionRequestDigest": v3_request["payloadDigest"],
            "fileDigest": result["outputDigest"]["fileDigest"],
            "runtimeEvidenceDigest": runtime["payloadDigest"],
        },
    )
    artifact = _seal(
        {
            "schemaVersion": MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            "artifactEvidenceRef": artifact_ref,
            "workspaceRef": v5_request["workspaceRef"],
            "productionRunRef": v5_request["productionRunRef"],
            "requirementRef": v5_request["requirementRef"],
            "requirementDigest": v5_request["requirementDigest"],
            "executionRequestRef": v5_request["executionRequestRef"],
            "executionRequestDigest": v5_request["payloadDigest"],
            "v3ExecutionRequestDigest": v3_request["payloadDigest"],
            "effectMode": v5_request["effectMode"],
            "outputByteSize": result["outputByteSize"],
            "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
            "outputDigest": deepcopy(result["outputDigest"]),
            "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
            "runtimeEvidenceDigest": runtime["payloadDigest"],
            "provenance": MASKED_SURFACE_PROVENANCE,
            "publicationAllowed": False,
        }
    )
    if set(artifact) != _ARTIFACT_EVIDENCE_FIELDS:
        raise MaskedSurfaceExecutionError("artifact evidence fields are invalid")
    runtime = validate_masked_surface_runtime_evidence(runtime)
    artifact = validate_masked_surface_artifact_evidence(
        artifact, runtime_evidence=runtime
    )
    bindings = {
        "workspaceRef": v5_request["workspaceRef"],
        "productionRunRef": v5_request["productionRunRef"],
        "requirementRef": v5_request["requirementRef"],
        "requirementDigest": v5_request["requirementDigest"],
        "executionRequestRef": v5_request["executionRequestRef"],
        "executionRequestDigest": v5_request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    if set(bindings) != _EVIDENCE_BINDING_FIELDS:
        raise MaskedSurfaceExecutionError("evidence binding fields are invalid")
    return {
        "artifactEvidence": artifact,
        "runtimeEvidence": runtime,
        "evidenceBindings": bindings,
    }


def _verify_sealed_evidence(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    try:
        result = _closed(value, fields, label)
        supplied = _raw_digest(result.pop("payloadDigest"), f"{label}.payloadDigest")
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError(f"{label} is invalid") from exc
    if supplied != sha256(_canonical_json(result)).hexdigest():
        raise MaskedSurfaceExecutionError(f"{label} payloadDigest is stale")
    result["payloadDigest"] = supplied
    return result


def validate_masked_surface_runtime_evidence(value: Any) -> dict[str, Any]:
    """Validate one path-free runtime record before V5 journal append/replay."""

    result = _verify_sealed_evidence(
        value, _RUNTIME_EVIDENCE_FIELDS, "masked-surface runtime evidence"
    )
    try:
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
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("runtime evidence lineage is invalid") from exc
    identity = result["ffmpegIdentity"]
    if (
        result["schemaVersion"]
        != MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] not in EFFECT_MODES
        or result["rendererIdentity"] != MASKED_SURFACE_RENDERER_IDENTITY
        or result["rendererVersion"] not in MASKED_SURFACE_RENDERER_READ_VERSIONS
        or not isinstance(identity, str)
        or identity != identity.strip()
        or not 1 <= len(identity) <= 500
        or any(ord(character) < 32 or ord(character) == 127 for character in identity)
        or result["gpuUsed"] is not False
        or result["publicationAllowed"] is not False
    ):
        raise MaskedSurfaceExecutionError("runtime evidence authority is invalid")
    expected_ref = _evidence_ref(
        "m13-masked-surface-runtime-evidence-",
        {
            "v3ExecutionRequestDigest": result["v3ExecutionRequestDigest"],
            "rendererIdentity": result["rendererIdentity"],
            "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"],
        },
    )
    if result["runtimeEvidenceRef"] != expected_ref:
        raise MaskedSurfaceExecutionError("runtimeEvidenceRef derivation is stale")
    return result


def validate_masked_surface_artifact_evidence(
    value: Any,
    *,
    runtime_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one path-free artifact record and optional runtime binding."""

    result = _verify_sealed_evidence(
        value, _ARTIFACT_EVIDENCE_FIELDS, "masked-surface artifact evidence"
    )
    try:
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
        _integer(
            result["outputByteSize"],
            "outputByteSize",
            minimum=1,
            maximum=10**12,
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("artifact evidence lineage is invalid") from exc
    probe = result["outputMediaProbe"]
    digest = result["outputDigest"]
    if (
        result["schemaVersion"]
        != MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] not in EFFECT_MODES
        or result["provenance"] != MASKED_SURFACE_PROVENANCE
        or result["publicationAllowed"] is not False
        or not isinstance(probe, Mapping)
        or set(probe) != _OUTPUT_FIELDS
        or not isinstance(digest, Mapping)
        or set(digest) != _OUTPUT_DIGEST_FIELDS
    ):
        raise MaskedSurfaceExecutionError("artifact evidence authority is invalid")
    try:
        _prefixed_digest(digest["fileDigest"], "outputDigest.fileDigest")
        _prefixed_digest(
            digest["decodedFramePixelDigest"],
            "outputDigest.decodedFramePixelDigest",
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("artifact output digest is invalid") from exc
    if (
        digest["fileDigestAlgorithm"] != "sha256"
        or digest["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or digest["pixelMode"] != "RGBA"
        or any(digest[field] != probe[field] for field in ("width", "height", "frameCount", "frameRate"))
    ):
        raise MaskedSurfaceExecutionError("artifact output facts are stale")
    expected_ref = _evidence_ref(
        "m13-masked-surface-artifact-evidence-",
        {
            "v3ExecutionRequestDigest": result["v3ExecutionRequestDigest"],
            "fileDigest": digest["fileDigest"],
            "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
        },
    )
    if result["artifactEvidenceRef"] != expected_ref:
        raise MaskedSurfaceExecutionError("artifactEvidenceRef derivation is stale")
    if runtime_evidence is not None:
        runtime = validate_masked_surface_runtime_evidence(runtime_evidence)
        common = (
            "workspaceRef",
            "productionRunRef",
            "requirementRef",
            "requirementDigest",
            "executionRequestRef",
            "executionRequestDigest",
            "v3ExecutionRequestDigest",
            "effectMode",
        )
        if (
            any(result[field] != runtime[field] for field in common)
            or result["runtimeEvidenceRef"] != runtime["runtimeEvidenceRef"]
            or result["runtimeEvidenceDigest"] != runtime["payloadDigest"]
        ):
            raise MaskedSurfaceExecutionError(
                "artifact and runtime evidence lineage disagree"
            )
    return result


def _frame_rate(value: Any, field: str) -> dict[str, int]:
    rate = _closed(value, frozenset({"numerator", "denominator"}), field)
    numerator = _integer(
        rate["numerator"], f"{field}.numerator", minimum=1, maximum=1_000_000
    )
    denominator = _integer(
        rate["denominator"], f"{field}.denominator", minimum=1, maximum=1_000_000
    )
    if numerator % denominator != 0:
        raise MaskedSurfaceRequestValidationError(
            f"{field} must be an integral frame rate"
        )
    return {"numerator": numerator, "denominator": denominator}


def _effect_preview_bindings(
    effect_bindings: Any, glyph_binding: Any
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if not isinstance(effect_bindings, list) or len(effect_bindings) not in {2, 4, 6, 7}:
        raise MaskedSurfaceRequestValidationError(
            "effectResultBindings must match a closed two-, four-, six-, or seven-stage profile"
        )
    stage_count = len(effect_bindings)
    result: list[dict[str, Any]] = []
    ranks = {
        "SCRATCH_REVEAL": 0,
        "LIGHT_SWEEP": 0,
        "LOCAL_EXPOSURE": 1,
        "FLAME_EXTINGUISH": 2,
        "SMOKE": 3,
        "NAMEPLATE_TEXT": 4,
        "FACE_MARK_COMPENSATION": 5,
        "DISTANCE_STATE_TRANSITION": 6,
    }
    seen_clips: set[str] = set()
    seen_results: set[str] = set()
    for index, raw in enumerate(effect_bindings):
        item = _closed(
            raw, _EFFECT_RESULT_BINDING_FIELDS, f"effectResultBindings[{index}]"
        )
        for field in (
            "clipRef",
            "requirementRef",
            "resultRef",
            "executionRequestRef",
            "artifactEvidenceRef",
            "runtimeEvidenceRef",
        ):
            _ref(item[field], f"effectResultBindings[{index}].{field}")
        for field in (
            "clipDigest",
            "requirementDigest",
            "resultDigest",
            "executionRequestDigest",
            "artifactEvidenceDigest",
            "runtimeEvidenceDigest",
        ):
            _raw_digest(item[field], f"effectResultBindings[{index}].{field}")
        if item["effectMode"] not in ranks:
            raise MaskedSurfaceRequestValidationError("effectMode is unsupported")
        start = _integer(
            item["frameRangeStartInclusive"],
            f"effectResultBindings[{index}].frameRangeStartInclusive",
            minimum=0,
            maximum=10_000_000,
        )
        end = _integer(
            item["frameRangeEndExclusive"],
            f"effectResultBindings[{index}].frameRangeEndExclusive",
            minimum=1,
            maximum=10_000_001,
        )
        if (
            start >= end
            or item["clipRef"] in seen_clips
            or item["resultRef"] in seen_results
        ):
            raise MaskedSurfaceRequestValidationError(
                "effect Result binding is duplicated or out of range"
            )
        seen_clips.add(item["clipRef"])
        seen_results.add(item["resultRef"])
        result.append(item)
    expected_ranks = {
        2: [0, 1],
        4: [0, 1, 2, 3],
        6: [0, 1, 2, 3, 4, 5],
        7: [0, 1, 2, 3, 4, 5, 6],
    }[stage_count]
    if [ranks[item["effectMode"]] for item in result] != expected_ranks:
        raise MaskedSurfaceRequestValidationError(
            "effect Result bindings are not in fixed phase order"
        )
    glyph = _closed(
        glyph_binding, _GLYPH_REQUIREMENT_BINDING_FIELDS, "glyphRequirementBinding"
    )
    for field in ("clipRef", "requirementRef"):
        _ref(glyph[field], f"glyphRequirementBinding.{field}")
    for field in ("clipDigest", "requirementDigest"):
        _raw_digest(glyph[field], f"glyphRequirementBinding.{field}")
    if glyph["clipRef"] in seen_clips:
        raise MaskedSurfaceRequestValidationError(
            "Glyph binding reuses an effect Clip"
        )
    digest = sha256(
        _canonical_json(
            {
                "schemaVersion": {
                    2: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION,
                    4: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2,
                    6: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3,
                    7: EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4,
                }[stage_count],
                "effectResultBindings": result,
                "glyphRequirementBinding": glyph,
            }
        )
    ).hexdigest()
    return result, glyph, digest


def _validate_requirement_binding(
    value: Any, *, execution_request: Mapping[str, Any]
) -> dict[str, Any]:
    requirement = _verify_sealed_evidence(
        value, _REQUIREMENT_FIELDS, "masked-surface Requirement"
    )
    expected = {
        "schemaVersion": execution_request["requirementSchemaVersion"],
        "workspaceRef": execution_request["workspaceRef"],
        "productionRunRef": execution_request["productionRunRef"],
        "requirementRef": execution_request["requirementRef"],
        "effectMode": execution_request["effectMode"],
        "targetShotRef": execution_request["targetShot"]["shotRef"],
        "targetShotVersionRef": execution_request["targetShot"]["shotVersionRef"],
        "targetShotVersionDigest": execution_request["targetShot"][
            "shotVersionDigest"
        ],
        "basePlateAssetVersionRef": execution_request["basePlate"][
            "assetVersionRef"
        ],
        "basePlateAssetVersionDigest": execution_request["basePlate"][
            "assetVersionDigest"
        ],
        "basePlateFileDigest": execution_request["basePlate"]["fileDigest"],
        "basePlatePixelDigest": execution_request["basePlate"]["pixelDigest"],
        "maskAssetVersionRef": execution_request["mask"]["assetVersionRef"],
        "maskAssetVersionDigest": execution_request["mask"]["assetVersionDigest"],
        "maskFileDigest": execution_request["mask"]["fileDigest"],
        "maskPixelDigest": execution_request["mask"]["pixelDigest"],
        "frameRangeStartInclusive": execution_request["frameRangeStartInclusive"],
        "frameRangeEndExclusive": execution_request["frameRangeEndExclusive"],
        "explicitSchedule": execution_request["explicitSchedule"],
        "trajectoryKeyframes": execution_request["trajectoryKeyframes"],
        "intensityCurve": execution_request["intensityCurve"],
        "exposureCurve": execution_request["exposureCurve"],
        "position": execution_request["position"],
        "scale": execution_request["scale"],
        "perspective": execution_request["perspective"],
        "blendMode": execution_request["blendMode"],
        "layer": execution_request["layer"],
        "publicationAllowed": False,
    }
    if any(requirement[field] != expected_value for field, expected_value in expected.items()):
        raise MaskedSurfaceExecutionError(
            "Requirement and execution request bindings disagree"
        )
    if requirement["payloadDigest"] != execution_request["requirementDigest"]:
        raise MaskedSurfaceExecutionError("Requirement digest binding is stale")
    return requirement


def _validate_result_binding(
    value: Any,
    *,
    binding: Mapping[str, Any],
    request: Mapping[str, Any],
    artifact: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    result = _verify_sealed_evidence(value, _RESULT_FIELDS, "masked-surface Result")
    expected_schema = (
        "v5.m13-local-exposure-result.v1"
        if request["effectMode"] == "LOCAL_EXPOSURE"
        else "v5.m13-scratch-light-result.v1"
    )
    expected = {
        "schemaVersion": expected_schema,
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "resultRef": binding["resultRef"],
        "effectMode": request["effectMode"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "state": "SUCCEEDED",
        "publicationAllowed": False,
    }
    if any(result[field] != expected_value for field, expected_value in expected.items()):
        raise MaskedSurfaceExecutionError("Result evidence chain is stale")
    if result["payloadDigest"] != binding["resultDigest"]:
        raise MaskedSurfaceExecutionError("Result digest binding is stale")
    return result


def _validate_e2_result_binding(
    value: Any,
    *,
    binding: Mapping[str, Any],
    request: Mapping[str, Any],
    artifact: Mapping[str, Any],
    runtime: Mapping[str, Any],
) -> dict[str, Any]:
    result = _verify_sealed_evidence(
        value, _E2_RESULT_FIELDS, "Flame/Smoke Result"
    )
    expected_schema = (
        "v5.m13-flame-extinguish-result.v1"
        if request["effectMode"] == "FLAME_EXTINGUISH"
        else "v5.m13-smoke-result.v1"
    )
    expected = {
        "schemaVersion": expected_schema,
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "resultRef": binding["resultRef"],
        "effectMode": request["effectMode"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "state": "COMPOSED_CANDIDATE",
        "outputFileDigest": artifact["outputDigest"]["fileDigest"],
        "outputDecodedFramePixelDigest": artifact["outputDigest"][
            "decodedFramePixelDigest"
        ],
        "outputMediaProbe": artifact["outputMediaProbe"],
        "assetAdmissionState": "NOT_ADMITTED",
        "masterState": "NOT_CREATED",
        "exportState": "NOT_CREATED",
        "publicationAllowed": False,
    }
    if any(result[field] != expected_value for field, expected_value in expected.items()):
        raise MaskedSurfaceExecutionError("Flame/Smoke Result evidence is stale")
    if result["payloadDigest"] != binding["resultDigest"]:
        raise MaskedSurfaceExecutionError("Flame/Smoke Result digest is stale")
    return result


def _validate_effect_request_evidence_lineage(
    request: Mapping[str, Any],
    runtime: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> None:
    expected_lineage = {
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "effectMode": request["effectMode"],
    }
    if any(
        runtime[field] != expected or artifact[field] != expected
        for field, expected in expected_lineage.items()
    ):
        raise MaskedSurfaceExecutionError(
            "effect evidence does not bind the resolved execution request"
        )


def _resolve_preview_base(
    command_base: Any,
    resolved_base: Any,
    *,
    artifact_root: Path,
) -> dict[str, Any]:
    requested = _closed(command_base, _EFFECT_PREVIEW_BASE_COMMAND_FIELDS, "baseVideo")
    for field in ("assetVersionRef",):
        _ref(requested[field], f"baseVideo.{field}")
    _raw_digest(requested["assetVersionDigest"], "baseVideo.assetVersionDigest")
    _prefixed_digest(requested["fileDigest"], "baseVideo.fileDigest")
    _prefixed_digest(requested["pixelDigest"], "baseVideo.pixelDigest")
    width = _integer(requested["width"], "baseVideo.width", minimum=2, maximum=16_384)
    height = _integer(requested["height"], "baseVideo.height", minimum=2, maximum=16_384)
    frame_count = _integer(
        requested["frameCount"], "baseVideo.frameCount", minimum=1, maximum=10_000_000
    )
    rate = _frame_rate(requested["frameRate"], "baseVideo.frameRate")
    if width % 2 or height % 2:
        raise MaskedSurfaceRequestValidationError(
            "baseVideo dimensions must be even for yuv420p"
        )
    resolved = _resolved_record(
        resolved_base,
        fields=_RESOLVED_BASE_FIELDS,
        label="resolved preview baseVideo",
    )
    expected = {
        "assetVersionRef": requested["assetVersionRef"],
        "assetVersionDigest": requested["assetVersionDigest"],
        "fileDigest": requested["fileDigest"],
        "pixelDigest": requested["pixelDigest"],
        "width": width,
        "height": height,
        "frameCount": frame_count,
        "frameRate": rate["numerator"] // rate["denominator"],
        "pixelFormat": "yuv420p",
        "pixelDigestSpec": DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    }
    if any(resolved[field] != value for field, value in expected.items()):
        raise MaskedSurfaceAssetResolutionError(
            "resolved preview baseVideo facts are stale"
        )
    path = _server_file(
        artifact_root, resolved["storageKey"], label="resolved preview baseVideo"
    )
    try:
        pixels = decoded_frame_pixel_digest_metadata(path)
    except DigestError as exc:
        raise MaskedSurfaceAssetResolutionError(
            "preview baseVideo could not be measured"
        ) from exc
    if (
        pixels.get("fileDigest") != resolved["fileDigest"]
        or pixels.get("decodedFramePixelDigest") != resolved["pixelDigest"]
        or pixels.get("decodedFramePixelDigestSpec")
        != resolved["pixelDigestSpec"]
        or pixels.get("width") != resolved["width"]
        or pixels.get("height") != resolved["height"]
        or pixels.get("frameCount") != resolved["frameCount"]
    ):
        raise MaskedSurfaceAssetResolutionError(
            "preview baseVideo content identity is stale"
        )
    return resolved


def _validate_effect_artifact_storage(
    value: Any,
    *,
    artifact: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    storage = _closed(
        value, _EFFECT_ARTIFACT_STORAGE_FIELDS, "effect artifactStorage"
    )
    try:
        _ref(storage["artifactEvidenceRef"], "artifactStorage.artifactEvidenceRef")
        _raw_digest(
            storage["artifactEvidenceDigest"], "artifactStorage.artifactEvidenceDigest"
        )
        _storage_key(storage["storageKey"], "artifactStorage.storageKey")
        _prefixed_digest(storage["fileDigest"], "artifactStorage.fileDigest")
        _prefixed_digest(storage["pixelDigest"], "artifactStorage.pixelDigest")
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceAssetResolutionError("artifactStorage is invalid") from exc
    output = artifact["outputDigest"]
    expected_probe = artifact["outputMediaProbe"]
    storage_identity = {
        "workspaceRef": artifact["workspaceRef"],
        "productionRunRef": artifact["productionRunRef"],
        "payloadDigest": artifact["v3ExecutionRequestDigest"],
    }
    renderer_version = runtime_evidence["rendererVersion"]
    expected_key = _expected_output_storage_key(
        storage_identity,
        renderer_version=renderer_version,
    )
    declared_keys = {expected_key}
    if renderer_version in {
        MASKED_SURFACE_RENDERER_VERSION_V2,
        MASKED_SURFACE_RENDERER_VERSION_V3,
    }:
        # The frozen V5 dependency projection reconstructs the historical
        # locator because storage paths are not part of the evidence DTO.
        # Treat that value only as a compatibility alias and always measure
        # the authoritative, version-bound v2/v3 artifact below.
        declared_keys.add(
            _expected_output_storage_key(
                storage_identity,
                renderer_version=MASKED_SURFACE_RENDERER_VERSION_V1,
            )
        )
    expected = {
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "fileDigest": output["fileDigest"],
        "pixelDigest": output["decodedFramePixelDigest"],
        "pixelDigestSpec": output["decodedFramePixelDigestSpec"],
        "width": output["width"],
        "height": output["height"],
        "frameCount": output["frameCount"],
        "frameRate": output["frameRate"],
        "pixelFormat": expected_probe["pixelFormat"],
    }
    if (
        storage["storageKey"] not in declared_keys
        or any(
            storage[field] != expected_value
            for field, expected_value in expected.items()
        )
    ):
        raise MaskedSurfaceAssetResolutionError(
            "effect artifactStorage does not match evidence"
        )
    path = _server_file(
        artifact_root, expected_key, label="effect artifactStorage"
    )
    if path.stat().st_size != artifact["outputByteSize"]:
        raise MaskedSurfaceAssetResolutionError("effect artifact byte size is stale")
    try:
        measured = decoded_frame_pixel_digest_metadata(path)
    except DigestError as exc:
        raise MaskedSurfaceAssetResolutionError(
            "effect artifact could not be measured"
        ) from exc
    if (
        measured.get("fileDigest") != storage["fileDigest"]
        or measured.get("decodedFramePixelDigest") != storage["pixelDigest"]
        or measured.get("decodedFramePixelDigestSpec") != storage["pixelDigestSpec"]
        or measured.get("width") != storage["width"]
        or measured.get("height") != storage["height"]
        or measured.get("frameCount") != storage["frameCount"]
    ):
        raise MaskedSurfaceAssetResolutionError(
            "effect artifact content identity is stale"
        )
    return storage


def _resolve_effect_stage(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path,
    base: Mapping[str, Any],
    local_exposure_stage: Mapping[str, Any] | None = None,
    local_exposure_binding: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = _closed(
        resolution,
        _EFFECT_EXECUTION_RESOLUTION_FIELDS,
        f"effect execution {binding['resultRef']}",
    )
    request_schema = (
        resolved["executionRequest"].get("schemaVersion")
        if isinstance(resolved["executionRequest"], Mapping)
        else None
    )
    is_e2 = request_schema == FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION
    request = (
        validate_flame_smoke_execution_request(resolved["executionRequest"])
        if is_e2
        else validate_masked_surface_execution_request(
            resolved["executionRequest"]
        )
    )
    if is_e2:
        requirement = _verify_generic_sealed_mapping(
            resolved["requirement"], "Flame/Smoke Requirement"
        )
        if (
            requirement.get("payloadDigest") != request["requirementDigest"]
            or requirement.get("schemaVersion")
            != request["requirementSchemaVersion"]
            or requirement.get("requirementRef") != request["requirementRef"]
            or requirement.get("effectMode") != request["effectMode"]
            or requirement.get("workspaceRef") != request["workspaceRef"]
            or requirement.get("productionRunRef")
            != request["productionRunRef"]
        ):
            raise MaskedSurfaceExecutionError(
                "Flame/Smoke Requirement binding is stale"
            )
    else:
        requirement = _validate_requirement_binding(
            resolved["requirement"], execution_request=request
        )
    runtime = validate_masked_surface_runtime_evidence(resolved["runtimeEvidence"])
    artifact = validate_masked_surface_artifact_evidence(
        resolved["artifactEvidence"], runtime_evidence=runtime
    )
    _validate_effect_request_evidence_lineage(request, runtime, artifact)
    if is_e2:
        _validate_e2_result_binding(
            resolved["result"],
            binding=binding,
            request=request,
            artifact=artifact,
            runtime=runtime,
        )
    else:
        _validate_result_binding(
            resolved["result"],
            binding=binding,
            request=request,
            artifact=artifact,
            runtime=runtime,
        )
    expected_binding = {
        "effectMode": request["effectMode"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "frameRangeStartInclusive": request["frameRangeStartInclusive"],
        "frameRangeEndExclusive": request["frameRangeEndExclusive"],
    }
    if any(binding[field] != value for field, value in expected_binding.items()):
        raise MaskedSurfaceExecutionError(
            "effect Result binding does not match resolved execution chain"
        )
    if is_e2:
        assets = _resolve_flame_smoke_assets(
            request,
            resolved["assetVersions"],
            artifact_root=artifact_root,
        )
        stage_base = assets["basePlate"]
    else:
        stage_base, stage_mask = _resolve_asset_versions(
            request,
            resolved["assetVersions"],
            artifact_root=artifact_root,
        )
    if any(
        stage_base[field] != base[field]
        for field in _RESOLVED_BASE_FIELDS
    ):
        raise MaskedSurfaceAssetResolutionError(
            "effect stage does not use the exact preview baseVideo"
        )
    _validate_effect_artifact_storage(
        resolved["artifactStorage"],
        artifact=artifact,
        runtime_evidence=runtime,
        artifact_root=artifact_root,
    )
    if not is_e2:
        stage_request = _build_v3_request(
            request, base=stage_base, mask=stage_mask
        )
    elif request["effectMode"] == "FLAME_EXTINGUISH":
        if (
            local_exposure_stage is None
            or local_exposure_binding is None
            or request["localExposureRequirementRef"]
            != local_exposure_stage["requirementRef"]
            or request["localExposureRequirementDigest"]
            != local_exposure_stage["requirementDigest"]
            or request["localExposureResultRef"]
            != local_exposure_binding["resultRef"]
            or request["localExposureResultDigest"]
            != local_exposure_binding["resultDigest"]
        ):
            raise MaskedSurfaceExecutionError(
                "Preview Flame LocalExposure dependency is stale"
            )
        local_stage = local_exposure_stage
        stage_request = _build_flame_smoke_v3_request(
            request,
            assets=assets,
            local_exposure_stage=local_stage,
        )
    else:
        if local_exposure_stage is not None or local_exposure_binding is not None:
            raise MaskedSurfaceExecutionError(
                "Preview Smoke cannot bind LocalExposure authority"
            )
        stage_request = _build_flame_smoke_v3_request(
            request,
            assets=assets,
            local_exposure_stage=None,
        )
    if (
        runtime["v3ExecutionRequestDigest"] != stage_request["payloadDigest"]
        or artifact["v3ExecutionRequestDigest"]
        != stage_request["payloadDigest"]
    ):
        raise MaskedSurfaceExecutionError(
            "effect evidence does not bind the rebuilt V3 request"
        )
    return stage_request


def _resolve_overlay_preview_stage_impl(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path,
    base: Mapping[str, Any],
    font_asset_authority: Any | None,
) -> dict[str, Any]:
    """Rebuild one E3 stage through the standalone overlay authority."""

    from services.v5_core_os.episode_production.deterministic_overlays import (
        OverlayResult,
        build_overlay_execution_request,
        parse_overlay_requirement,
    )
    from .deterministic_overlays import (
        rebuild_overlay_v3_request,
        validate_overlay_artifact_evidence,
        validate_overlay_execution_request,
        validate_overlay_runtime_evidence,
    )

    resolved = _closed(
        resolution,
        _EFFECT_EXECUTION_RESOLUTION_FIELDS,
        f"overlay execution {binding['resultRef']}",
    )
    requirement_wrapper = parse_overlay_requirement(resolved["requirement"])
    requirement = requirement_wrapper.as_dict()
    request = validate_overlay_execution_request(resolved["executionRequest"])
    if request != build_overlay_execution_request(requirement_wrapper).as_dict():
        raise MaskedSurfaceExecutionError(
            "overlay execution request is stale"
        )
    runtime = validate_overlay_runtime_evidence(resolved["runtimeEvidence"])
    artifact = validate_overlay_artifact_evidence(
        resolved["artifactEvidence"], runtime_evidence=runtime
    )
    result = OverlayResult.from_mapping(resolved["result"]).as_dict()

    expected_lineage = {
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "effectMode": request["effectMode"],
    }
    if any(
        runtime[field] != expected
        or artifact[field] != expected
        or result[field] != expected
        for field, expected in expected_lineage.items()
    ):
        raise MaskedSurfaceExecutionError(
            "overlay Requirement, evidence, and Result lineage disagree"
        )
    expected_result = {
        "resultRef": binding["resultRef"],
        "payloadDigest": binding["resultDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "outputFileDigest": artifact["outputDigest"]["fileDigest"],
        "outputDecodedFramePixelDigest": artifact["outputDigest"][
            "decodedFramePixelDigest"
        ],
        "outputMediaProbe": artifact["outputMediaProbe"],
    }
    if any(result[field] != expected for field, expected in expected_result.items()):
        raise MaskedSurfaceExecutionError("overlay Result binding is stale")

    overlay_spec = request["overlaySpec"]
    expected_binding = {
        "effectMode": request["effectMode"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "frameRangeStartInclusive": overlay_spec[
            "frameRangeStartInclusive"
        ],
        "frameRangeEndExclusive": overlay_spec["frameRangeEndExclusive"],
    }
    if any(binding[field] != expected for field, expected in expected_binding.items()):
        raise MaskedSurfaceExecutionError(
            "overlay Result binding does not match its evidence chain"
        )

    stage = rebuild_overlay_v3_request(
        request,
        resolved_asset_versions=resolved["assetVersions"],
        artifact_root=artifact_root,
        font_asset_authority=font_asset_authority,
    )
    if (
        runtime["v3ExecutionRequestDigest"] != stage["payloadDigest"]
        or artifact["v3ExecutionRequestDigest"] != stage["payloadDigest"]
    ):
        raise MaskedSurfaceExecutionError(
            "overlay evidence does not bind the rebuilt V3 request"
        )
    if any(
        stage["basePlate"][field] != base[field]
        for field in _RESOLVED_BASE_FIELDS
    ):
        raise MaskedSurfaceAssetResolutionError(
            "overlay stage does not use the exact preview baseVideo"
        )

    storage = _closed(
        resolved["artifactStorage"],
        _EFFECT_ARTIFACT_STORAGE_FIELDS,
        "overlay artifactStorage",
    )
    output = artifact["outputDigest"]
    expected_probe = artifact["outputMediaProbe"]
    workspace_hash = sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
    run_hash = sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
    expected_storage = {
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "storageKey": str(
            PurePosixPath(
                workspace_hash,
                run_hash,
                "deterministic-overlays",
                f"overlay-{stage['payloadDigest']}.mp4",
            )
        ),
        "fileDigest": output["fileDigest"],
        "pixelDigest": output["decodedFramePixelDigest"],
        "pixelDigestSpec": output["decodedFramePixelDigestSpec"],
        "width": output["width"],
        "height": output["height"],
        "frameCount": output["frameCount"],
        "frameRate": output["frameRate"],
        "pixelFormat": expected_probe["pixelFormat"],
    }
    if storage != expected_storage:
        raise MaskedSurfaceAssetResolutionError(
            "overlay artifactStorage does not match evidence"
        )
    output_path = _server_file(
        artifact_root, storage["storageKey"], label="overlay artifactStorage"
    )
    from shutil import which
    from services.v3_render_core.composition import (
        RenderArtifactError,
        _PinnedRegularFile,
        _PinnedRuntimeBinary,
    )
    from services.v3_render_core.masked_surface import (
        _probe_video,
        _validate_probe,
    )

    ffmpeg_path = which("ffmpeg")
    ffprobe_path = which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise MaskedSurfaceAssetResolutionError(
            "pinned overlay artifact measurement runtime is unavailable"
        )
    try:
        with (
            _PinnedRegularFile(
                output_path, label="resolved overlay artifact"
            ) as pinned_output,
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffmpeg_path)), label="FFmpeg"
            ) as ffmpeg,
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffprobe_path)), label="FFprobe"
            ) as ffprobe,
        ):
            if (
                pinned_output.descriptor is None
                or os.fstat(pinned_output.descriptor).st_size
                != artifact["outputByteSize"]
            ):
                raise MaskedSurfaceAssetResolutionError(
                    "overlay artifact byte size is stale"
                )
            pass_fds = tuple(
                dict.fromkeys(
                    pinned_output.pass_fds
                    + ffmpeg.pass_fds
                    + ffprobe.pass_fds
                )
            )
            actual_probe = _probe_video(
                pinned_output.descriptor_path,
                ffprobe,
                pass_fds=pass_fds,
            )
            _validate_probe(
                actual_probe, expected_probe, input_media=False
            )
            measured = decoded_frame_pixel_digest_metadata(
                pinned_output.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            pinned_output.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
    except MaskedSurfaceAssetResolutionError:
        raise
    except (DigestError, RenderArtifactError, OSError) as exc:
        raise MaskedSurfaceAssetResolutionError(
            "overlay artifact could not be measured"
        ) from exc
    if (
        measured.get("fileDigest") != storage["fileDigest"]
        or measured.get("decodedFramePixelDigest") != storage["pixelDigest"]
        or measured.get("decodedFramePixelDigestSpec")
        != storage["pixelDigestSpec"]
        or measured.get("width") != storage["width"]
        or measured.get("height") != storage["height"]
        or measured.get("frameCount") != storage["frameCount"]
    ):
        raise MaskedSurfaceAssetResolutionError(
            "overlay artifact content identity is stale"
        )
    return stage


def _resolve_overlay_preview_stage(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path,
    base: Mapping[str, Any],
    font_asset_authority: Any | None,
) -> dict[str, Any]:
    """Translate overlay-domain failures into this composition boundary."""

    from services.v5_core_os.episode_production.foundation import (
        EpisodeProductionError,
    )
    from .deterministic_overlays import OverlayExecutionError

    try:
        return _resolve_overlay_preview_stage_impl(
            binding,
            resolution,
            artifact_root=artifact_root,
            base=base,
            font_asset_authority=font_asset_authority,
        )
    except (
        MaskedSurfaceExecutionError,
        MaskedSurfaceAssetResolutionError,
    ):
        raise
    except (EpisodeProductionError, OverlayExecutionError) as exc:
        raise MaskedSurfaceExecutionError(
            "overlay execution chain could not be resolved"
        ) from exc


def _verify_generic_sealed_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or "payloadDigest" not in value:
        raise MaskedSurfaceExecutionError(f"{label} is not sealed")
    result = deepcopy(dict(value))
    try:
        supplied = _raw_digest(result.pop("payloadDigest"), f"{label}.payloadDigest")
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError(f"{label} seal is invalid") from exc
    if supplied != sha256(_canonical_json(result)).hexdigest():
        raise MaskedSurfaceExecutionError(f"{label} payloadDigest is stale")
    result["payloadDigest"] = supplied
    return result


def _resolve_glyph_stage(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path,
    base: Mapping[str, Any],
) -> dict[str, Any]:
    from .composition import _validate_glyph_reveal_request_v2

    resolved = _closed(
        resolution, _GLYPH_EXECUTION_RESOLUTION_FIELDS, "glyphExecution"
    )
    requirement = _verify_sealed_evidence(
        resolved["requirement"],
        _GLYPH_REQUIREMENT_FIELDS,
        "GlyphRevealRequirementV2",
    )
    try:
        request = _validate_glyph_reveal_request_v2(resolved["executionRequest"])
    except Exception as exc:
        raise MaskedSurfaceExecutionError(
            "Glyph Reveal execution request is invalid"
        ) from exc
    if (
        requirement["schemaVersion"] != "v5.m13-glyph-reveal-requirement.v2"
        or requirement["requirementRef"] != binding["requirementRef"]
        or requirement["payloadDigest"] != binding["requirementDigest"]
        or request["requirementRef"] != binding["requirementRef"]
        or request["requirementDigest"] != binding["requirementDigest"]
        or requirement["workspaceRef"] != request["workspaceRef"]
        or requirement["productionRunRef"] != request["productionRunRef"]
        or requirement["glyphSlug"] != request["glyphSlug"]
        or requirement["targetShotRef"] != request["targetShotRef"]
        or requirement["frameRangeStartInclusive"]
        != request["frameRangeStartInclusive"]
        or requirement["frameRangeEndExclusive"]
        != request["frameRangeEndExclusive"]
        or requirement["revealSchedule"] != request["revealSchedule"]
        or requirement["basePlateAssetVersionRef"]
        != request["basePlate"]["assetVersionRef"]
        or requirement["basePlateAssetVersionDigest"]
        != request["basePlate"]["assetVersionDigest"]
        or requirement["basePlateFileDigest"]
        != request["basePlate"]["fileDigest"]
        or requirement["maskAssetVersionBindings"]
        != [
            {key: value for key, value in mask.items() if key != "storageKey"}
            for mask in request["masks"]
        ]
        or requirement["basePlateInspectionRef"]
        != request["basePlateInspectionRef"]
        or requirement["basePlateInspectionDigest"]
        != request["basePlateInspectionDigest"]
        or requirement["compositeParams"] != request["compositeParams"]
        or requirement["inputBindingsDigest"] != request["inputBindingsDigest"]
        or requirement["publicationAllowed"] is not False
    ):
        raise MaskedSurfaceExecutionError("Glyph Reveal binding is stale")
    request_base = request["basePlate"]
    expected_base = {
        "assetVersionRef": base["assetVersionRef"],
        "assetVersionDigest": base["assetVersionDigest"],
        "storageKey": base["storageKey"],
        "fileDigest": base["fileDigest"],
    }
    if request_base != expected_base:
        raise MaskedSurfaceAssetResolutionError(
            "Glyph Reveal does not use the exact preview baseVideo"
        )
    if request["output"] != {
        "width": base["width"],
        "height": base["height"],
        "frameRate": base["frameRate"],
        "totalFrames": base["frameCount"],
    }:
        raise MaskedSurfaceExecutionError("Glyph Reveal output contract is stale")
    authorities = resolved["assetVersions"]
    expected_refs = {
        request_base["assetVersionRef"],
        *(mask["assetVersionRef"] for mask in request["masks"]),
    }
    if not isinstance(authorities, Mapping) or set(authorities) != expected_refs:
        raise MaskedSurfaceAssetResolutionError(
            "Glyph Reveal AssetVersion set is stale"
        )
    glyph_base = _resolved_record(
        authorities[request_base["assetVersionRef"]],
        fields=_GLYPH_BASE_RESOLUTION_FIELDS,
        label="glyph base AssetVersion",
    )
    if glyph_base != request_base:
        raise MaskedSurfaceAssetResolutionError(
            "Glyph Reveal base AssetVersion is stale"
        )
    for index, mask in enumerate(request["masks"]):
        authority = _resolved_record(
            authorities[mask["assetVersionRef"]],
            fields=_GLYPH_MASK_RESOLUTION_FIELDS,
            label=f"glyph mask AssetVersion {index}",
        )
        if authority != mask:
            raise MaskedSurfaceAssetResolutionError(
                "Glyph Reveal mask AssetVersion is stale"
            )
        path = _server_file(
            artifact_root,
            authority["storageKey"],
            label=f"glyph mask AssetVersion {index}",
        )
        try:
            pixels = image_digest_metadata(path)
        except DigestError as exc:
            raise MaskedSurfaceAssetResolutionError(
                "Glyph Reveal mask could not be measured"
            ) from exc
        if (
            file_digest(path) != authority["fileDigest"]
            or pixels.get("pixel_digest") != authority["pixelDigest"]
            or pixels.get("pixel_digest_spec") != authority["pixelDigestSpec"]
            or pixels.get("pixel_mode") != authority["pixelMode"]
            or pixels.get("width") != authority["width"]
            or pixels.get("height") != authority["height"]
        ):
            raise MaskedSurfaceAssetResolutionError(
                "Glyph Reveal mask content identity is stale"
            )
    return request


def _build_effect_preview_v3_request(
    command_value: Any,
    resolved_artifacts: Any,
    *,
    artifact_root: Path,
    font_asset_authority: Any | None = None,
) -> dict[str, Any]:
    from .composition import _build_timeline_preview_execution_request_v1

    command = _closed(
        command_value, _EFFECT_PREVIEW_COMMAND_FIELDS, "effect preview command"
    )
    for field in ("workspaceRef", "productionRunRef", "timelineVersionRef"):
        _ref(command[field], field)
    _raw_digest(command["timelineVersionDigest"], "timelineVersionDigest")
    bindings, glyph_binding, effect_digest = _effect_preview_bindings(
        command["effectResultBindings"], command["glyphRequirementBinding"]
    )
    resolved = _closed(
        resolved_artifacts,
        _EFFECT_PREVIEW_RESOLUTION_FIELDS,
        "resolved_artifacts",
    )
    base = _resolve_preview_base(
        command["baseVideo"], resolved["baseVideo"], artifact_root=artifact_root
    )
    effect_resolutions = resolved["effectExecutions"]
    expected_results = {binding["resultRef"] for binding in bindings}
    if not isinstance(effect_resolutions, Mapping) or set(effect_resolutions) != expected_results:
        raise MaskedSurfaceAssetResolutionError(
            "effectExecutions do not match effectResultBindings"
    )
    stages: list[dict[str, Any]] = []
    for binding in bindings:
        if binding["effectMode"] == "DISTANCE_STATE_TRANSITION":
            from .distance_state import (
                DistanceStateExecutionError,
                resolve_distance_state_preview_stage,
            )

            try:
                stage = resolve_distance_state_preview_stage(
                    binding,
                    effect_resolutions[binding["resultRef"]],
                    artifact_root=artifact_root,
                    base=base,
                )
            except DistanceStateExecutionError as exc:
                raise MaskedSurfaceExecutionError(
                    "distance/state execution chain could not be resolved"
                ) from exc
        elif binding["effectMode"] in {
            "NAMEPLATE_TEXT",
            "FACE_MARK_COMPENSATION",
        }:
            stage = _resolve_overlay_preview_stage(
                binding,
                effect_resolutions[binding["resultRef"]],
                artifact_root=artifact_root,
                base=base,
                font_asset_authority=font_asset_authority,
            )
        else:
            stage = _resolve_effect_stage(
                binding,
                effect_resolutions[binding["resultRef"]],
                artifact_root=artifact_root,
                base=base,
                local_exposure_stage=(
                    stages[1]
                    if binding["effectMode"] == "FLAME_EXTINGUISH"
                    and len(stages) == 2
                    else None
                ),
                local_exposure_binding=(
                    bindings[1]
                    if binding["effectMode"] == "FLAME_EXTINGUISH"
                    and len(stages) == 2
                    else None
                ),
            )
        stage_semantics = (
            stage["overlaySpec"]
            if binding["effectMode"]
            in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"}
            else stage
        )
        if (
            stage["workspaceRef"] != command["workspaceRef"]
            or stage["productionRunRef"] != command["productionRunRef"]
            or stage_semantics["frameRangeEndExclusive"] > base["frameCount"]
        ):
            raise MaskedSurfaceExecutionError(
                "effect stage scope or frame range is stale"
            )
        stages.append(stage)
    glyph_stage = _resolve_glyph_stage(
        glyph_binding,
        resolved["glyphExecution"],
        artifact_root=artifact_root,
        base=base,
    )
    if (
        glyph_stage["workspaceRef"] != command["workspaceRef"]
        or glyph_stage["productionRunRef"] != command["productionRunRef"]
    ):
        raise MaskedSurfaceExecutionError("Glyph Reveal scope is stale")

    # Reuse the existing closed M12 audio/output validator.  The temporary
    # video projection is validation-only; the combined V3 request below
    # replays the exact closed visual profile against the original baseVideo.
    placeholder_artifact_ref = "m13-effect-preview-glyph-replay-" + sha256(
        glyph_stage["payloadDigest"].encode("ascii")
    ).hexdigest()[:32]
    legacy = _build_timeline_preview_execution_request_v1(
        {
            "workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"],
            "timelineVersionRef": command["timelineVersionRef"],
            "timelineVersionDigest": command["timelineVersionDigest"],
            "videoInput": {
                "glyphRevealRequirementRef": glyph_binding["requirementRef"],
                "glyphRevealRequirementDigest": glyph_binding["requirementDigest"],
                "glyphRevealExecutionRequestRef": glyph_stage["executionRequestRef"],
                "glyphRevealExecutionRequestDigest": glyph_stage["payloadDigest"],
                "glyphRevealArtifactEvidenceRef": placeholder_artifact_ref,
                "glyphRevealArtifactEvidenceDigest": glyph_stage["payloadDigest"],
                "storageKey": base["storageKey"],
                "fileDigest": base["fileDigest"],
                "decodedFramePixelDigest": base["pixelDigest"],
                "decodedFramePixelDigestSpec": base["pixelDigestSpec"],
                "codec": "h264",
                "pixelFormat": base["pixelFormat"],
                "width": base["width"],
                "height": base["height"],
                "frameCount": base["frameCount"],
                "frameRate": deepcopy(command["baseVideo"]["frameRate"]),
            },
            "audioMix": deepcopy(command["audioMix"]),
            "subtitleManifest": deepcopy(command["subtitleManifest"]),
            "output": deepcopy(command["output"]),
        }
    )
    input_payload = {
        "baseVideo": deepcopy(base),
        (
            "deterministicEffectRequestDigests"
            if len(stages) in {6, 7}
            else "maskedSurfaceRequestDigests"
        ): [stage["payloadDigest"] for stage in stages],
        "glyphRevealRequestDigest": glyph_stage["payloadDigest"],
        "effectResultBindings": deepcopy(bindings),
        "glyphRequirementBinding": deepcopy(glyph_binding),
        "audioMix": deepcopy(legacy["audioMix"]),
        "subtitleManifest": deepcopy(legacy["subtitleManifest"]),
    }
    input_digest = sha256(_canonical_json(input_payload)).hexdigest()
    output_contract_digest = sha256(_canonical_json(legacy["output"])).hexdigest()
    execution_ref = "m13-effect-preview-execution-" + sha256(
        _canonical_json(
            {
                "timelineVersionRef": command["timelineVersionRef"],
                "timelineVersionDigest": command["timelineVersionDigest"],
                "inputBindingsDigest": input_digest,
                "effectBindingsDigest": effect_digest,
                "outputContractDigest": output_contract_digest,
            }
        )
    ).hexdigest()[:32]
    request = _seal(
        {
            "schemaVersion": {
                2: EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION,
                4: EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V3,
                6: EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4,
                7: EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V5,
            }[len(stages)],
            "executionRequestRef": execution_ref,
            "workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"],
            "timelineVersionRef": command["timelineVersionRef"],
            "timelineVersionDigest": command["timelineVersionDigest"],
            "inputBindingsDigest": input_digest,
            "effectResultBindings": deepcopy(bindings),
            "glyphRequirementBinding": deepcopy(glyph_binding),
            "effectBindingsDigest": effect_digest,
            "baseVideo": deepcopy(base),
            "effectStages": stages,
            "glyphStage": glyph_stage,
            "audioMix": deepcopy(legacy["audioMix"]),
            "subtitleManifest": deepcopy(legacy["subtitleManifest"]),
            "output": deepcopy(legacy["output"]),
            "publicationAllowed": False,
        }
    )
    if set(request) != _EFFECT_PREVIEW_V3_REQUEST_FIELDS:
        raise MaskedSurfaceExecutionError(
            "derived effect preview V3 request fields are invalid"
        )
    return request


def _preview_storage_key(request: Mapping[str, Any]) -> str:
    workspace = sha256(str(request["workspaceRef"]).encode("utf-8")).hexdigest()[:20]
    run = sha256(str(request["productionRunRef"]).encode("utf-8")).hexdigest()[:20]
    return str(
        PurePosixPath(
            workspace,
            run,
            "composition",
            f"preview-{request['payloadDigest']}.mp4",
        )
    )


def _validate_v3_effect_preview_result(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    try:
        result = _closed(
            value, _V3_EFFECT_PREVIEW_RESULT_FIELDS, "V3 effect preview result"
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 effect preview result is open") from exc
    expected = {
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "timelineVersionRef": request["timelineVersionRef"],
        "timelineVersionDigest": request["timelineVersionDigest"],
        "inputBindingsDigest": request["inputBindingsDigest"],
        "effectResultBindings": request["effectResultBindings"],
        "glyphRequirementBinding": request["glyphRequirementBinding"],
        "effectBindingsDigest": request["effectBindingsDigest"],
        "mixRequestRef": request["audioMix"]["mixRequestRef"],
        "mixRequestDigest": request["audioMix"]["mixRequestDigest"],
        "subtitleManifestRef": request["subtitleManifest"]["subtitleManifestRef"],
        "subtitleManifestDigest": request["subtitleManifest"][
            "subtitleManifestDigest"
        ],
        "publicationAllowed": False,
    }
    if any(result[field] != expected_value for field, expected_value in expected.items()):
        raise MaskedSurfaceExecutionError("V3 effect preview lineage is stale")
    expected_key = _preview_storage_key(request)
    if result["outputStorageKey"] != expected_key:
        raise MaskedSurfaceExecutionError("V3 effect preview storage lineage is stale")
    path = _server_file(
        artifact_root, result["outputStorageKey"], label="V3 effect preview output"
    )
    if result["internalPath"] != str(path):
        raise MaskedSurfaceExecutionError("V3 effect preview internal path is stale")
    try:
        size = _integer(
            result["outputByteSize"],
            "effect preview outputByteSize",
            minimum=1,
            maximum=10**12,
        )
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 effect preview size is invalid") from exc
    output = request["output"]
    expected_probe = {
        "container": output["container"],
        "videoCodec": output["videoCodec"],
        "pixelFormat": output["pixelFormat"],
        "width": output["width"],
        "height": output["height"],
        "frameRate": deepcopy(output["frameRate"]),
        "frameCount": output["totalFrames"],
        "audioCodec": output["audioCodec"],
        "sampleRate": output["sampleRate"],
        "channelCount": output["channelCount"],
        "sampleCount": output["durationSamples"],
    }
    probe = result["outputMediaProbe"]
    digest = result["outputDigest"]
    if (
        not isinstance(probe, Mapping)
        or set(probe) != _PREVIEW_OUTPUT_PROBE_FIELDS
        or probe != expected_probe
        or not isinstance(digest, Mapping)
        or set(digest) != _PREVIEW_OUTPUT_DIGEST_FIELDS
    ):
        raise MaskedSurfaceExecutionError("V3 effect preview output facts are stale")
    try:
        _prefixed_digest(digest["fileDigest"], "outputDigest.fileDigest")
        _prefixed_digest(
            digest["decodedFramePixelDigest"],
            "outputDigest.decodedFramePixelDigest",
        )
        _raw_digest(digest["pcmContentDigest"], "outputDigest.pcmContentDigest")
    except MaskedSurfaceRequestValidationError as exc:
        raise MaskedSurfaceExecutionError("V3 effect preview digest is invalid") from exc
    if (
        digest["fileDigestAlgorithm"] != "sha256"
        or digest["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or digest["pixelMode"] != "RGBA"
        or digest["pcmDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
        or any(
            digest[field] != expected_probe[probe_field]
            for field, probe_field in (
                ("width", "width"),
                ("height", "height"),
                ("frameCount", "frameCount"),
                ("frameRate", "frameRate"),
                ("sampleRate", "sampleRate"),
                ("channelCount", "channelCount"),
                ("sampleCount", "sampleCount"),
            )
        )
    ):
        raise MaskedSurfaceExecutionError(
            "V3 effect preview digest contract is stale"
        )
    ffmpeg_identity = result["ffmpegIdentity"]
    expected_renderer_version = {
        EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION: EFFECT_PREVIEW_RENDERER_VERSION,
        EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V3: EFFECT_PREVIEW_RENDERER_VERSION_V3,
        EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4: EFFECT_PREVIEW_RENDERER_VERSION_V4,
        EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V5: EFFECT_PREVIEW_RENDERER_VERSION_V5,
    }[request["schemaVersion"]]
    runtime_identity = {
        "ffmpegIdentity": ffmpeg_identity,
        "rendererIdentity": result["rendererIdentity"],
        "rendererVersion": result["rendererVersion"],
    }
    if (
        result["rendererIdentity"] != EFFECT_PREVIEW_RENDERER_IDENTITY
        or result["rendererVersion"] != expected_renderer_version
        or not isinstance(ffmpeg_identity, str)
        or ffmpeg_identity != ffmpeg_identity.strip()
        or not 1 <= len(ffmpeg_identity) <= 500
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in ffmpeg_identity
        )
        or result["runtimeEvidenceDigest"]
        != "sha256:" + sha256(_canonical_json(runtime_identity)).hexdigest()
    ):
        raise MaskedSurfaceExecutionError(
            "V3 effect preview runtime evidence is stale"
        )
    from shutil import which
    from services.v3_render_core.composition import (
        RenderArtifactError,
        _PinnedRegularFile,
        _PinnedRuntimeBinary,
    )

    ffmpeg_path = which("ffmpeg")
    ffprobe_path = which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise MaskedSurfaceExecutionError(
            "pinned effect preview measurement runtime is unavailable"
        )
    try:
        with (
            _PinnedRegularFile(
                path, label="V3 effect preview output"
            ) as pinned_output,
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffmpeg_path)), label="FFmpeg"
            ) as ffmpeg,
            _PinnedRuntimeBinary(
                Path(os.path.realpath(ffprobe_path)), label="FFprobe"
            ) as ffprobe,
        ):
            if (
                pinned_output.descriptor is None
                or os.fstat(pinned_output.descriptor).st_size != size
            ):
                raise MaskedSurfaceExecutionError(
                    "V3 effect preview byte size is stale"
                )
            pass_fds = tuple(
                dict.fromkeys(
                    pinned_output.pass_fds
                    + ffmpeg.pass_fds
                    + ffprobe.pass_fds
                )
            )
            pixels = decoded_frame_pixel_digest_metadata(
                pinned_output.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            pcm = canonical_pcm_digest_metadata(
                path,
                expected_sample_count=output["durationSamples"],
                allow_aac_frame_padding=True,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
                _input_descriptor=pinned_output.descriptor,
            )
            pinned_output.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
    except MaskedSurfaceExecutionError:
        raise
    except (DigestError, RenderArtifactError, OSError) as exc:
        raise MaskedSurfaceExecutionError(
            "V3 effect preview output could not be remeasured"
        ) from exc
    if (
        pixels.get("fileDigest") != digest["fileDigest"]
        or pixels.get("decodedFramePixelDigest")
        != digest["decodedFramePixelDigest"]
        or pixels.get("decodedFramePixelDigestSpec")
        != digest["decodedFramePixelDigestSpec"]
        or pixels.get("width") != digest["width"]
        or pixels.get("height") != digest["height"]
        or pixels.get("frameCount") != digest["frameCount"]
        or pcm.get("pcmContentDigest") != digest["pcmContentDigest"]
        or pcm.get("pcmDigestSpec") != digest["pcmDigestSpec"]
        or pcm.get("sampleRate") != digest["sampleRate"]
        or pcm.get("channelCount") != digest["channelCount"]
        or pcm.get("sampleCount") != digest["sampleCount"]
    ):
        raise MaskedSurfaceExecutionError(
            "V3 effect preview output content is stale"
        )
    return result


def _preview_artifact_ref(request_digest: str, output: Mapping[str, Any]) -> str:
    return "m13-preview-artifact-" + sha256(
        _canonical_json(
            {
                "executionRequestDigest": request_digest,
                "fileDigest": output["fileDigest"],
                "decodedFramePixelDigest": output["decodedFramePixelDigest"],
                "pcmContentDigest": output["pcmContentDigest"],
            }
        )
    ).hexdigest()[:32]


def _build_v4_effect_preview_result(
    *, request: Mapping[str, Any], result: Mapping[str, Any]
) -> dict[str, Any]:
    artifact_ref = _preview_artifact_ref(
        request["payloadDigest"], result["outputDigest"]
    )
    composition_ref = "m13-composition-result-" + sha256(
        _canonical_json(
            {
                "executionRequestDigest": request["payloadDigest"],
                "artifactRef": artifact_ref,
            }
        )
    ).hexdigest()[:32]
    sealed = _seal(
        {
            "schemaVersion": EFFECT_PREVIEW_V4_RESULT_SCHEMA_VERSION,
            "compositionResultRef": composition_ref,
            "artifactRef": artifact_ref,
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["payloadDigest"],
            "timelineVersionRef": request["timelineVersionRef"],
            "timelineVersionDigest": request["timelineVersionDigest"],
            "inputBindingsDigest": request["inputBindingsDigest"],
            "effectResultBindings": deepcopy(request["effectResultBindings"]),
            "glyphRequirementBinding": deepcopy(
                request["glyphRequirementBinding"]
            ),
            "effectBindingsDigest": request["effectBindingsDigest"],
            "mixRequestRef": request["audioMix"]["mixRequestRef"],
            "mixRequestDigest": request["audioMix"]["mixRequestDigest"],
            "subtitleManifestRef": request["subtitleManifest"][
                "subtitleManifestRef"
            ],
            "subtitleManifestDigest": request["subtitleManifest"][
                "subtitleManifestDigest"
            ],
            "outputStorageKey": result["outputStorageKey"],
            "outputByteSize": result["outputByteSize"],
            "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
            "outputDigest": deepcopy(result["outputDigest"]),
            "rendererIdentity": result["rendererIdentity"],
            "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"],
            "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
            "adapterIdentity": EFFECT_PREVIEW_ADAPTER_IDENTITY,
            "provenance": MASKED_SURFACE_PROVENANCE,
            "providerUsed": False,
            "gpuUsed": False,
            "publicationAllowed": False,
        }
    )
    if set(sealed) != _V4_EFFECT_PREVIEW_RESULT_FIELDS:
        raise MaskedSurfaceExecutionError(
            "V4 effect preview result fields are invalid"
        )
    return sealed


class V4MaskedSurfaceEffectExecutor:
    """One V4 orchestration boundary; it creates no domain authority."""

    def __init__(
        self,
        artifact_root: Path | str,
        v3_executor: Any,
        *,
        font_asset_authority: Any | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise MaskedSurfaceAssetResolutionError("artifact root is invalid")
        if not callable(getattr(v3_executor, "execute", None)):
            raise MaskedSurfaceExecutionError("V3 masked-surface executor is required")
        self.v3_executor = v3_executor
        self.font_asset_authority = font_asset_authority

    @classmethod
    def from_artifact_root(
        cls,
        artifact_root: Path | str,
        *,
        font_asset_authority: Any | None = None,
    ) -> "V4MaskedSurfaceEffectExecutor":
        """Create the production V3 primitive without exposing it to V5."""

        from services.v3_render_core.masked_surface import (
            DeterministicMaskedSurfaceExecutor,
        )

        root = Path(artifact_root).resolve()
        return cls(
            root,
            DeterministicMaskedSurfaceExecutor(root),
            font_asset_authority=font_asset_authority,
        )

    def execute(
        self,
        execution_request: Mapping[str, Any],
        *,
        resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Execute one sealed request against exact server-held AssetVersions."""

        request = validate_masked_surface_execution_request(execution_request)
        base, mask = _resolve_asset_versions(
            request,
            resolved_asset_versions,
            artifact_root=self.artifact_root,
        )
        v3_request = _build_v3_request(request, base=base, mask=mask)
        try:
            raw_result = self.v3_executor.execute(v3_request)
        except MaskedSurfaceExecutionError:
            raise
        except Exception as exc:
            raise MaskedSurfaceExecutionError(
                "V3 masked-surface execution failed"
            ) from exc
        result = _validate_v3_result(
            raw_result,
            request=v3_request,
            artifact_root=self.artifact_root,
        )
        return _build_evidence(
            v5_request=request,
            v3_request=v3_request,
            result=result,
        )

    def execute_flame_smoke(
        self,
        execution_request: Mapping[str, Any],
        *,
        resolved_asset_versions: Mapping[str, Mapping[str, Any]],
        resolved_effect_dependencies: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Execute one closed E2 request and return the existing evidence trio."""

        request = validate_flame_smoke_execution_request(execution_request)
        assets = _resolve_flame_smoke_assets(
            request,
            resolved_asset_versions,
            artifact_root=self.artifact_root,
        )
        local_stage: dict[str, Any] | None = None
        if request["effectMode"] == "FLAME_EXTINGUISH":
            local_stage = _resolve_flame_local_exposure_stage(
                request,
                resolved_effect_dependencies,
                artifact_root=self.artifact_root,
                base=assets["basePlate"],
                flame_mask=assets["flameMask"],
            )
        elif not isinstance(resolved_effect_dependencies, Mapping) or dict(
            resolved_effect_dependencies
        ):
            raise MaskedSurfaceAssetResolutionError(
                "Smoke cannot bind an Effect dependency"
            )
        v3_request = _build_flame_smoke_v3_request(
            request,
            assets=assets,
            local_exposure_stage=local_stage,
        )
        try:
            raw_result = self.v3_executor.execute(v3_request)
        except MaskedSurfaceExecutionError:
            raise
        except Exception as exc:
            raise MaskedSurfaceExecutionError(
                "V3 Flame/Smoke execution failed"
            ) from exc
        result = _validate_v3_result(
            raw_result,
            request=v3_request,
            artifact_root=self.artifact_root,
        )
        return _build_evidence(
            v5_request=request,
            v3_request=v3_request,
            result=result,
        )

    def compose_timeline_preview_v2(
        self,
        command: Mapping[str, Any],
        *,
        resolved_artifacts: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Replay sealed effects in the fixed phase order and mux Preview v2."""

        request = _build_effect_preview_v3_request(
            command,
            resolved_artifacts,
            artifact_root=self.artifact_root,
            font_asset_authority=self.font_asset_authority,
        )
        compose = getattr(self.v3_executor, "compose_timeline_preview_v2", None)
        if not callable(compose):
            raise MaskedSurfaceExecutionError(
                "V3 effect preview executor is unavailable"
            )
        try:
            raw_result = compose(request)
        except Exception as exc:
            raise MaskedSurfaceExecutionError(
                "V3 effect preview execution failed"
            ) from exc
        result = _validate_v3_effect_preview_result(
            raw_result,
            request=request,
            artifact_root=self.artifact_root,
        )
        return _build_v4_effect_preview_result(request=request, result=result)


__all__ = [
    "BLEND_MODES",
    "EFFECT_MODES",
    "EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION",
    "EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V2",
    "EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V3",
    "EFFECT_PREVIEW_BINDINGS_SCHEMA_VERSION_V4",
    "EFFECT_PREVIEW_RENDERER_IDENTITY",
    "EFFECT_PREVIEW_RENDERER_VERSION",
    "EFFECT_PREVIEW_RENDERER_VERSION_V3",
    "EFFECT_PREVIEW_RENDERER_VERSION_V4",
    "EFFECT_PREVIEW_RENDERER_VERSION_V5",
    "EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION",
    "EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V3",
    "EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V4",
    "EFFECT_PREVIEW_V3_REQUEST_SCHEMA_VERSION_V5",
    "EFFECT_PREVIEW_V4_RESULT_SCHEMA_VERSION",
    "FLAME_EXTINGUISH_REQUIREMENT_SCHEMA_VERSION",
    "FLAME_SMOKE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "FLAME_SMOKE_V3_REQUEST_SCHEMA_VERSION",
    "INTERPOLATIONS",
    "LOCAL_EXPOSURE_REQUIREMENT_SCHEMA_VERSION",
    "MASKED_SURFACE_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "MASKED_SURFACE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "MASKED_SURFACE_RENDERER_IDENTITY",
    "MASKED_SURFACE_RENDERER_VERSION",
    "MASKED_SURFACE_RENDERER_READ_VERSIONS",
    "MASKED_SURFACE_RENDERER_VERSION_CURRENT",
    "MASKED_SURFACE_RENDERER_VERSION_V1",
    "MASKED_SURFACE_RENDERER_VERSION_V2",
    "MASKED_SURFACE_RENDERER_VERSION_V3",
    "MASKED_SURFACE_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "MASKED_SURFACE_V3_REQUEST_SCHEMA_VERSION",
    "MaskedSurfaceAssetResolutionError",
    "MaskedSurfaceExecutionError",
    "MaskedSurfaceRequestValidationError",
    "SCRATCH_LIGHT_REQUIREMENT_SCHEMA_VERSION",
    "SMOKE_REQUIREMENT_SCHEMA_VERSION",
    "V4MaskedSurfaceEffectExecutor",
    "validate_masked_surface_artifact_evidence",
    "validate_masked_surface_execution_request",
    "validate_flame_smoke_execution_request",
    "validate_masked_surface_runtime_evidence",
]
