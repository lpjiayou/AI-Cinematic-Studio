"""M13 exact-glyph reveal requirements and V3 execution handoff contracts.

This module owns only immutable V5 facts and boundary validation.  It does not
read media bytes, invoke FFmpeg, admit an AssetVersion, or create Timeline
authority.  The renderer receives digest-pinned internal storage keys only.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping, Protocol, Sequence

from .foundation import (
    EpisodeProductionError,
    StaleInputError,
    UpstreamNotReadyError,
    _digest,
    _required_ref,
)


GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION = (
    "v5.m13-glyph-reveal-requirement.v1"
)
BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION = (
    "v5.m13-base-plate-glyph-inspection.v1"
)
GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-glyph-reveal-execution-request.v1"
)
GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-glyph-reveal-artifact-evidence.v1"
)
GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION = (
    "v5.m13-glyph-reveal-composition-result.v1"
)
GLYPH_REVEAL_COMPOSER_CAPABILITY = (
    "v3.deterministic-glyph-reveal-ffmpeg.v1"
)
CANONICAL_ASSET_VERSION_SCHEMA_VERSION = "v5.asset-version.v1"
REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION = (
    "v5.k2-real-video-asset-version.v1"
)
REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION = (
    "v5.k2-real-image-asset-version.v1"
)
PIXEL_DIGEST_SPEC = "RGBA8/exif-transposed/row-major/v1"
PIXEL_MODE = "RGBA"
VIDEO_PIXEL_DIGEST_SPEC = (
    "RGBA8/display-transposed/frame-major/row-major/v1"
)
VIDEO_PIXEL_MODE = "RGBA"
GLYPH_REVEAL_BLEND_MODE = "GRAZING_LIGHT_RELIEF"
V4_COMPOSITION_ADAPTER_IDENTITY = "v4.local-composition-executor.v1"
BASE_PLATE_GLYPH_INSPECTOR_IDENTITY = (
    "v4.local-base-plate-glyph-inspector.v1"
)
BASE_PLATE_GLYPH_INSPECTION_METHOD = (
    "LOCAL_FRAME_GLYPH_READABILITY_INSPECTION_V1"
)
LOCAL_EVIDENCE_PROVENANCE = "LOCAL_EVIDENCE"
GLYPH_MASK_ASSET_ROLE = "GLYPH_REVEAL_CUMULATIVE_MASK"

_GLYPH_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")

_REQUIREMENT_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStart",
        "frameRangeEnd",
        "revealFrameCount",
        "maskAssetRefs",
        "basePlateAssetRef",
        "inspectionDigest",
        "inputBindings",
        "inputBindingsDigest",
        "compositeParams",
        "outputDigest",
        "publicationAllowed",
        "payloadDigest",
    }
)
_REQUIREMENT_COMMAND_FIELDS = _REQUIREMENT_FIELDS - {
    "schemaVersion",
    "inspectionDigest",
    "inputBindings",
    "inputBindingsDigest",
    "outputDigest",
    "publicationAllowed",
    "payloadDigest",
}
_INSPECTION_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "inspectionRef",
        "inspectorIdentity",
        "method",
        "provenance",
        "basePlateAssetRef",
        "basePlateAssetDigest",
        "basePlateFileDigest",
        "mediaProbe",
        "verdict",
        "publicationAllowed",
        "payloadDigest",
    }
)
_MEDIA_PROBE_FIELDS = frozenset(
    {"width", "height", "frameCount", "frameRate"}
)
_BASE_INPUT_BINDING_FIELDS = frozenset(
    {"assetVersionRef", "assetVersionDigest", "fileDigest"}
)
_MASK_INPUT_BINDING_FIELDS = frozenset(
    {
        "assetVersionRef",
        "assetVersionDigest",
        "fileDigest",
        "pixelDigest",
    }
)
_INPUT_BINDINGS_FIELDS = frozenset({"basePlate", "masks"})
_EXECUTION_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "requirementDigest",
        "glyphSlug",
        "targetShotRef",
        "frameRangeStart",
        "frameRangeEnd",
        "revealFrameCount",
        "inputBindingsDigest",
        "basePlate",
        "masks",
        "inspectionDigest",
        "compositeParams",
        "output",
        "publicationAllowed",
        "payloadDigest",
    }
)
_EXECUTION_BASE_PLATE_FIELDS = frozenset(
    {
        "assetVersionRef",
        "assetVersionDigest",
        "storageKey",
        "fileDigest",
    }
)
_EXECUTION_MASK_FIELDS = frozenset(
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
_EXECUTION_OUTPUT_FIELDS = frozenset(
    {"width", "height", "frameRate", "totalFrames"}
)
_ASSET_REQUIRED_FIELDS = frozenset(
    {
        "schemaVersion",
        "workspaceRef",
        "productionRunRef",
        "assetVersionRef",
        "mediaKind",
        "mediaType",
        "storageKey",
        "byteSize",
        "sha256",
        "publicationAllowed",
        "payloadDigest",
    }
)
_OUTPUT_DIGEST_FIELDS = frozenset(
    {
        "fileDigest",
        "fileDigestAlgorithm",
        "pixelDigest",
        "pixelDigestSpec",
        "pixelMode",
        "width",
        "height",
        "frameCount",
    }
)
_ARTIFACT_EVIDENCE_FIELDS = frozenset(
    {
        "schemaVersion",
        "storageKey",
        "byteSize",
        "sha256",
        "probe",
        "outputDigest",
        "composerIdentity",
        "adapterIdentity",
        "runtimeIdentity",
        "ffmpegVersion",
        "ffprobeVersion",
        "provenance",
        "gpuUsed",
        "publicationAllowed",
        "requirementDigest",
        "executionRequestDigest",
        "payloadDigest",
    }
)


class GlyphRevealError(EpisodeProductionError):
    code = "glyph_reveal_invalid"


class GlyphRevealMaskCountError(GlyphRevealError):
    code = "glyph_reveal_mask_count_mismatch"


class GlyphRevealFrameRangeError(GlyphRevealError):
    code = "glyph_reveal_frame_range_invalid"


class NondeterministicCompositeParamsError(GlyphRevealError):
    code = "glyph_reveal_nondeterministic_params"


class BasePlateGlyphInspectionRequiredError(UpstreamNotReadyError):
    code = "base_plate_glyph_inspection_required"


class ReadableGlyphInBasePlateError(GlyphRevealError):
    code = "base_plate_contains_readable_glyph"


class GlyphRevealArtifactError(GlyphRevealError):
    code = "glyph_reveal_artifact_invalid"


class BasePlateGlyphInspectionPort(Protocol):
    """Evidence producer for semantic glyph-readability inspection.

    This is an evidence boundary, not an approval or second-identity gate.  The
    implementation must inspect the exact digest-pinned M11 base AssetVersion
    and return one sealed local-evidence record.
    """

    def inspect_base_plate(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        target_shot_ref: str,
        base_plate_asset: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


def _sealed(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(payload))
    result["payloadDigest"] = _digest(result)
    return result


def _verify_sealed(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StaleInputError(f"{field} must be a sealed object")
    result = deepcopy(dict(value))
    claimed = result.pop("payloadDigest", None)
    try:
        actual = _digest(result)
    except EpisodeProductionError as exc:
        raise StaleInputError(f"{field} payload is not canonical") from exc
    if claimed != actual:
        raise StaleInputError(f"{field} payload digest is invalid")
    result["payloadDigest"] = claimed
    return result


def _integer(
    value: Any,
    field: str,
    *,
    minimum: int,
    maximum: int,
    error_type: type[EpisodeProductionError] = GlyphRevealError,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise error_type(f"{field} is invalid")
    return value


def _raw_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise GlyphRevealError(f"{field} is invalid")
    return value


def _pixel_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_DIGEST.fullmatch(value) is None:
        raise GlyphRevealError(f"{field} is invalid")
    return value


def _storage_key(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
    ):
        raise GlyphRevealError(f"{field} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise GlyphRevealError(f"{field} is invalid")
    return value


def _glyph_slug(value: Any) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _GLYPH_SLUG.fullmatch(value) is None
    ):
        raise GlyphRevealError("glyphSlug is invalid")
    return value


def _point(value: Any, field: str) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise NondeterministicCompositeParamsError(f"{field} is invalid")
    return (
        _integer(
            value[0],
            f"{field}[0]",
            minimum=0,
            maximum=131_072,
            error_type=NondeterministicCompositeParamsError,
        ),
        _integer(
            value[1],
            f"{field}[1]",
            minimum=0,
            maximum=131_072,
            error_type=NondeterministicCompositeParamsError,
        ),
    )


def _normalize_composite_params(value: Any) -> dict[str, Any]:
    """Return one closed, expression-free deterministic composite recipe."""

    if not isinstance(value, Mapping) or set(value) != {
        "position",
        "scale",
        "perspective",
        "blendMode",
    }:
        raise NondeterministicCompositeParamsError(
            "compositeParams fields are not deterministic"
        )
    position = value.get("position")
    scale = value.get("scale")
    perspective = value.get("perspective")
    if not isinstance(position, Mapping) or set(position) != {
        "xPixels",
        "yPixels",
    }:
        raise NondeterministicCompositeParamsError(
            "compositeParams.position is invalid"
        )
    if not isinstance(scale, Mapping) or set(scale) != {
        "widthPixels",
        "heightPixels",
    }:
        raise NondeterministicCompositeParamsError(
            "compositeParams.scale is invalid"
        )
    if not isinstance(perspective, Mapping) or set(perspective) != {
        "topLeft",
        "topRight",
        "bottomLeft",
        "bottomRight",
    }:
        raise NondeterministicCompositeParamsError(
            "compositeParams.perspective is invalid"
        )
    x_pixels = _integer(
        position.get("xPixels"),
        "compositeParams.position.xPixels",
        minimum=0,
        maximum=131_072,
        error_type=NondeterministicCompositeParamsError,
    )
    y_pixels = _integer(
        position.get("yPixels"),
        "compositeParams.position.yPixels",
        minimum=0,
        maximum=131_072,
        error_type=NondeterministicCompositeParamsError,
    )
    width = _integer(
        scale.get("widthPixels"),
        "compositeParams.scale.widthPixels",
        minimum=2,
        maximum=131_072,
        error_type=NondeterministicCompositeParamsError,
    )
    height = _integer(
        scale.get("heightPixels"),
        "compositeParams.scale.heightPixels",
        minimum=2,
        maximum=131_072,
        error_type=NondeterministicCompositeParamsError,
    )
    points = {
        name: _point(
            perspective.get(name), f"compositeParams.perspective.{name}"
        )
        for name in ("topLeft", "topRight", "bottomLeft", "bottomRight")
    }
    if value.get("blendMode") != GLYPH_REVEAL_BLEND_MODE:
        raise NondeterministicCompositeParamsError(
            "compositeParams.blendMode is invalid"
        )
    top_left = points["topLeft"]
    top_right = points["topRight"]
    bottom_left = points["bottomLeft"]
    bottom_right = points["bottomRight"]
    if (
        len(set(points.values())) != 4
        or any(
            point[0] >= width or point[1] >= height
            for point in points.values()
        )
        or not (
            top_left[0] < top_right[0]
            and bottom_left[0] < bottom_right[0]
            and top_left[1] < bottom_left[1]
            and top_right[1] < bottom_right[1]
        )
    ):
        raise NondeterministicCompositeParamsError(
            "compositeParams.perspective is outside the scaled glyph"
        )
    return {
        "position": {"xPixels": x_pixels, "yPixels": y_pixels},
        "scale": {"widthPixels": width, "heightPixels": height},
        "perspective": {
            name: [points[name][0], points[name][1]]
            for name in ("topLeft", "topRight", "bottomLeft", "bottomRight")
        },
        "blendMode": GLYPH_REVEAL_BLEND_MODE,
    }


def _frame_range(
    start_value: Any, end_value: Any, count_value: Any
) -> tuple[int, int, int]:
    start = _integer(
        start_value,
        "frameRangeStart",
        minimum=0,
        maximum=10_000_000,
        error_type=GlyphRevealFrameRangeError,
    )
    end = _integer(
        end_value,
        "frameRangeEnd",
        minimum=1,
        maximum=10_000_001,
        error_type=GlyphRevealFrameRangeError,
    )
    count = _integer(
        count_value,
        "revealFrameCount",
        minimum=1,
        maximum=1_024,
        error_type=GlyphRevealMaskCountError,
    )
    if end <= start or end - start < count:
        raise GlyphRevealFrameRangeError(
            "frameRange must be end-exclusive and fit every reveal frame"
        )
    return start, end, count


def _frame_rate(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise GlyphRevealError(f"{field} is invalid")
    try:
        rate = Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        raise GlyphRevealError(f"{field} is invalid") from None
    if rate <= 0 or rate.denominator != 1 or rate.numerator > 1_000:
        raise GlyphRevealError(f"{field} must be a positive integer rate")
    return rate.numerator


def _video_probe_facts(
    probe: Any, *, field: str = "videoProbe"
) -> tuple[int, int, int, int]:
    if not isinstance(probe, Mapping):
        raise GlyphRevealError(f"{field} is invalid")
    if set(("width", "height", "frameCount", "frameRate")).issubset(probe):
        return (
            _integer(
                probe.get("width"),
                f"{field}.width",
                minimum=1,
                maximum=131_072,
            ),
            _integer(
                probe.get("height"),
                f"{field}.height",
                minimum=1,
                maximum=131_072,
            ),
            _integer(
                probe.get("frameCount"),
                f"{field}.frameCount",
                minimum=1,
                maximum=10_000_000,
            ),
            _frame_rate(
                probe.get("frameRate"), f"{field}.frameRate"
            ),
        )
    streams = probe.get("streams")
    if not isinstance(streams, list):
        raise GlyphRevealError(f"{field} frameCount is missing")
    video_streams = [
        stream
        for stream in streams
        if isinstance(stream, Mapping) and stream.get("codec_type") == "video"
    ]
    if len(video_streams) != 1:
        raise GlyphRevealError(f"{field} video stream is invalid")
    stream = video_streams[0]
    raw_frames = stream.get("nb_read_frames", stream.get("nb_frames"))
    try:
        frame_count = int(raw_frames)
    except (TypeError, ValueError):
        raise GlyphRevealError(
            f"{field} actual frameCount is missing"
        ) from None
    return (
        _integer(
            stream.get("width"),
            f"{field}.width",
            minimum=1,
            maximum=131_072,
        ),
        _integer(
            stream.get("height"),
            f"{field}.height",
            minimum=1,
            maximum=131_072,
        ),
        _integer(
            frame_count,
            f"{field}.frameCount",
            minimum=1,
            maximum=10_000_000,
        ),
        _frame_rate(
            stream.get("avg_frame_rate"),
            f"{field}.avg_frame_rate",
        ),
    )


def _canonical_asset(
    value: Any,
    *,
    field: str,
    workspace_ref: str,
    production_run_ref: str,
    allowed_schemas: frozenset[str],
) -> dict[str, Any]:
    asset = _verify_sealed(value, field)
    if not _ASSET_REQUIRED_FIELDS.issubset(asset):
        raise GlyphRevealError(f"{field} canonical AssetVersion is incomplete")
    if asset.get("schemaVersion") not in allowed_schemas:
        raise GlyphRevealError(f"{field} schemaVersion is unsupported")
    _required_ref(asset.get("assetVersionRef"), f"{field}.assetVersionRef")
    if (
        asset.get("workspaceRef") != workspace_ref
        or asset.get("productionRunRef") != production_run_ref
    ):
        raise StaleInputError(f"{field} scope is stale")
    _storage_key(asset.get("storageKey"), f"{field}.storageKey")
    _integer(
        asset.get("byteSize"),
        f"{field}.byteSize",
        minimum=1,
        maximum=10**12,
    )
    _raw_sha256(asset.get("sha256"), f"{field}.sha256")
    if asset.get("publicationAllowed") is not False:
        raise GlyphRevealError(f"{field} is outside the local candidate boundary")
    return asset


def _base_plate_asset(
    value: Any,
    *,
    workspace_ref: str,
    production_run_ref: str,
    target_shot_ref: str,
) -> dict[str, Any]:
    asset = _canonical_asset(
        value,
        field="basePlateAsset",
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        allowed_schemas=frozenset({REAL_VIDEO_ASSET_VERSION_SCHEMA_VERSION}),
    )
    if (
        asset.get("mediaKind") != "video"
        or asset.get("mediaType") != "video/mp4"
        or asset.get("creativeShotRef") != target_shot_ref
        or asset.get("state") != "REGISTERED"
        or asset.get("immutable") is not True
    ):
        raise StaleInputError("basePlateAsset is not the target Shot video")
    _required_ref(asset.get("assetRef"), "basePlateAsset.assetRef")
    _required_ref(
        asset.get("creativeShotVersionRef"),
        "basePlateAsset.creativeShotVersionRef",
    )
    _integer(
        asset.get("version"),
        "basePlateAsset.version",
        minimum=1,
        maximum=10_000_000,
    )
    return asset


def _mask_assets(
    values: Any,
    *,
    workspace_ref: str,
    production_run_ref: str,
    glyph_slug: str,
    expected_refs: Sequence[str],
) -> list[dict[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise GlyphRevealMaskCountError("maskAssets must be an ordered sequence")
    if len(values) != len(expected_refs):
        raise GlyphRevealMaskCountError(
            "mask AssetVersion count does not match revealFrameCount"
        )
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(values, start=1):
        asset = _canonical_asset(
            raw,
            field=f"maskAssets[{index - 1}]",
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            allowed_schemas=frozenset(
                {
                    CANONICAL_ASSET_VERSION_SCHEMA_VERSION,
                    REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION,
                }
            ),
        )
        required = {
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
        if not required.issubset(asset):
            raise GlyphRevealError("mask AssetVersion pixel evidence is incomplete")
        if (
            asset.get("assetVersionRef") != expected_refs[index - 1]
            or asset.get("mediaKind") != "image"
            or asset.get("mediaType") != "image/png"
            or asset.get("state") != "REGISTERED"
            or asset.get("pixelDigestSpec") != PIXEL_DIGEST_SPEC
            or asset.get("pixelMode") != PIXEL_MODE
            or asset.get("glyphSlug") != glyph_slug
            or asset.get("revealOrdinal") != index
            or asset.get("assetRole") != GLYPH_MASK_ASSET_ROLE
        ):
            raise StaleInputError("mask AssetVersion binding is stale")
        if (
            asset.get("schemaVersion") == REAL_IMAGE_ASSET_VERSION_SCHEMA_VERSION
            and asset.get("immutable") is not True
        ):
            raise StaleInputError(
                "real-image mask AssetVersion must be immutable"
            )
        _pixel_digest(asset.get("pixelDigest"), f"maskAssets[{index - 1}].pixelDigest")
        _integer(
            asset.get("width"),
            f"maskAssets[{index - 1}].width",
            minimum=1,
            maximum=131_072,
        )
        _integer(
            asset.get("height"),
            f"maskAssets[{index - 1}].height",
            minimum=1,
            maximum=131_072,
        )
        _pixel_digest(
            asset.get("glyphManifestDigest"),
            f"maskAssets[{index - 1}].glyphManifestDigest",
        )
        result.append(asset)
    refs = [asset["assetVersionRef"] for asset in result]
    if len(set(refs)) != len(refs):
        raise GlyphRevealMaskCountError("mask AssetVersion refs must be unique")
    pixel_digests = [asset["pixelDigest"] for asset in result]
    if len(set(pixel_digests)) != len(pixel_digests):
        raise StaleInputError(
            "mask AssetVersion pixel digests must be unique across reveal stages"
        )
    first = result[0]
    if any(
        (
            asset["width"],
            asset["height"],
            asset["pixelMode"],
            asset["pixelDigestSpec"],
        )
        != (
            first["width"],
            first["height"],
            first["pixelMode"],
            first["pixelDigestSpec"],
        )
        for asset in result[1:]
    ):
        raise GlyphRevealError("mask AssetVersion pixel contracts disagree")
    if any(
        asset["glyphManifestDigest"] != first["glyphManifestDigest"]
        for asset in result[1:]
    ):
        raise StaleInputError("mask AssetVersion glyph manifests disagree")
    return result


def _inspection_evidence(
    inspection_port: BasePlateGlyphInspectionPort,
    *,
    workspace_ref: str,
    production_run_ref: str,
    target_shot_ref: str,
    base_plate_asset: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[int, int, int, int]]:
    if inspection_port is None or not callable(
        getattr(inspection_port, "inspect_base_plate", None)
    ):
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection port is required"
        )
    try:
        value = inspection_port.inspect_base_plate(
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            target_shot_ref=target_shot_ref,
            base_plate_asset=deepcopy(dict(base_plate_asset)),
        )
    except EpisodeProductionError:
        raise
    except Exception as exc:
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection failed closed"
        ) from exc
    evidence = _verify_sealed(value, "basePlateGlyphInspection")
    if set(evidence) != _INSPECTION_FIELDS:
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection evidence fields are invalid"
        )
    if (
        evidence.get("schemaVersion")
        != BASE_PLATE_GLYPH_INSPECTION_SCHEMA_VERSION
        or evidence.get("inspectorIdentity")
        != BASE_PLATE_GLYPH_INSPECTOR_IDENTITY
        or evidence.get("method") != BASE_PLATE_GLYPH_INSPECTION_METHOD
        or evidence.get("provenance") != LOCAL_EVIDENCE_PROVENANCE
        or evidence.get("publicationAllowed") is not False
    ):
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection evidence is unsupported"
        )
    _required_ref(evidence.get("inspectionRef"), "inspectionRef")
    verdict = evidence.get("verdict")
    if verdict == "READABLE_GLYPH_DETECTED":
        raise ReadableGlyphInBasePlateError(
            "base plate already contains a readable glyph"
        )
    if verdict != "VERIFIED_NO_READABLE_GLYPH":
        raise BasePlateGlyphInspectionRequiredError(
            "base plate has no conclusive no-glyph inspection"
        )
    if (
        evidence.get("workspaceRef") != workspace_ref
        or evidence.get("productionRunRef") != production_run_ref
        or evidence.get("basePlateAssetRef")
        != base_plate_asset.get("assetVersionRef")
        or evidence.get("basePlateAssetDigest")
        != base_plate_asset.get("payloadDigest")
        or evidence.get("basePlateFileDigest")
        != base_plate_asset.get("sha256")
    ):
        raise StaleInputError("base plate glyph inspection evidence is stale")
    if not isinstance(evidence.get("mediaProbe"), Mapping) or set(
        evidence["mediaProbe"]
    ) != _MEDIA_PROBE_FIELDS:
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection mediaProbe is invalid"
        )
    try:
        dimensions = _video_probe_facts(
            evidence["mediaProbe"], field="basePlateGlyphInspection.mediaProbe"
        )
    except GlyphRevealError as exc:
        raise BasePlateGlyphInspectionRequiredError(
            "base plate glyph inspection mediaProbe is invalid"
        ) from exc
    if "probe" in base_plate_asset:
        base_probe = _video_probe_facts(
            base_plate_asset.get("probe"), field="basePlateAsset.probe"
        )
        if base_probe != dimensions:
            raise StaleInputError(
                "base plate glyph inspection mediaProbe is stale"
            )
    return evidence, dimensions


def _validate_geometry(
    params: Mapping[str, Any], *, base_width: int, base_height: int
) -> None:
    position = params["position"]
    scale = params["scale"]
    perspective = params["perspective"]
    if (
        position["xPixels"] + scale["widthPixels"] > base_width
        or position["yPixels"] + scale["heightPixels"] > base_height
    ):
        raise GlyphRevealError("compositeParams geometry exceeds the base plate")
    for point in perspective.values():
        if (
            position["xPixels"] + point[0] > base_width
            or position["yPixels"] + point[1] > base_height
        ):
            raise GlyphRevealError(
                "compositeParams perspective exceeds the base plate"
            )


def _input_bindings_from_assets(
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "basePlate": {
            "assetVersionRef": base_plate_asset["assetVersionRef"],
            "assetVersionDigest": base_plate_asset["payloadDigest"],
            "fileDigest": f"sha256:{base_plate_asset['sha256']}",
        },
        "masks": [
            {
                "assetVersionRef": mask["assetVersionRef"],
                "assetVersionDigest": mask["payloadDigest"],
                "fileDigest": f"sha256:{mask['sha256']}",
                "pixelDigest": mask["pixelDigest"],
            }
            for mask in mask_assets
        ],
    }


def _normalize_input_bindings(
    value: Any,
    *,
    base_plate_asset_ref: str,
    mask_asset_refs: Sequence[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _INPUT_BINDINGS_FIELDS:
        raise StaleInputError("GlyphRevealRequirement inputBindings are invalid")
    base = value.get("basePlate")
    masks = value.get("masks")
    if not isinstance(base, Mapping) or set(base) != _BASE_INPUT_BINDING_FIELDS:
        raise StaleInputError(
            "GlyphRevealRequirement base input binding is invalid"
        )
    if (
        not isinstance(masks, list)
        or len(masks) != len(mask_asset_refs)
        or any(
            not isinstance(mask, Mapping)
            or set(mask) != _MASK_INPUT_BINDING_FIELDS
            for mask in masks
        )
    ):
        raise StaleInputError(
            "GlyphRevealRequirement mask input bindings are invalid"
        )
    if base.get("assetVersionRef") != base_plate_asset_ref:
        raise StaleInputError(
            "GlyphRevealRequirement base input binding is stale"
        )
    _raw_sha256(
        base.get("assetVersionDigest"),
        "inputBindings.basePlate.assetVersionDigest",
    )
    _pixel_digest(
        base.get("fileDigest"), "inputBindings.basePlate.fileDigest"
    )
    normalized_masks: list[dict[str, Any]] = []
    for index, (mask, expected_ref) in enumerate(zip(masks, mask_asset_refs)):
        if mask.get("assetVersionRef") != expected_ref:
            raise StaleInputError(
                "GlyphRevealRequirement mask input binding order is stale"
            )
        _raw_sha256(
            mask.get("assetVersionDigest"),
            f"inputBindings.masks[{index}].assetVersionDigest",
        )
        _pixel_digest(
            mask.get("fileDigest"),
            f"inputBindings.masks[{index}].fileDigest",
        )
        _pixel_digest(
            mask.get("pixelDigest"),
            f"inputBindings.masks[{index}].pixelDigest",
        )
        normalized_masks.append(deepcopy(dict(mask)))
    return {
        "basePlate": deepcopy(dict(base)),
        "masks": normalized_masks,
    }


@dataclass(frozen=True, slots=True)
class GlyphRevealRequirement:
    """Immutable, digest-sealed M13 glyph-reveal requirement value."""

    workspace_ref: str
    production_run_ref: str
    requirement_ref: str
    glyph_slug: str
    target_shot_ref: str
    frame_range_start: int
    frame_range_end: int
    reveal_frame_count: int
    mask_asset_refs: tuple[str, ...]
    base_plate_asset_ref: str
    inspection_digest: str
    _input_bindings_json: str
    input_bindings_digest: str
    _composite_params_json: str
    payload_digest: str

    @property
    def composite_params(self) -> dict[str, Any]:
        return json.loads(self._composite_params_json)

    @property
    def input_bindings(self) -> dict[str, Any]:
        return json.loads(self._input_bindings_json)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GlyphRevealRequirement":
        requirement = _verify_sealed(value, "GlyphRevealRequirement")
        if (
            set(requirement) != _REQUIREMENT_FIELDS
            or requirement.get("schemaVersion")
            != GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION
            or requirement.get("outputDigest") is not None
            or requirement.get("publicationAllowed") is not False
        ):
            raise GlyphRevealError("GlyphRevealRequirement fields are invalid")
        workspace_ref = _required_ref(
            requirement.get("workspaceRef"), "workspaceRef"
        )
        production_run_ref = _required_ref(
            requirement.get("productionRunRef"), "productionRunRef"
        )
        requirement_ref = _required_ref(
            requirement.get("requirementRef"), "requirementRef"
        )
        glyph_slug = _glyph_slug(requirement.get("glyphSlug"))
        target_shot_ref = _required_ref(
            requirement.get("targetShotRef"), "targetShotRef"
        )
        start, end, count = _frame_range(
            requirement.get("frameRangeStart"),
            requirement.get("frameRangeEnd"),
            requirement.get("revealFrameCount"),
        )
        refs = requirement.get("maskAssetRefs")
        if not isinstance(refs, list) or len(refs) != count:
            raise GlyphRevealMaskCountError(
                "maskAssetRefs count does not match revealFrameCount"
            )
        mask_refs = tuple(
            _required_ref(ref, f"maskAssetRefs[{index}]")
            for index, ref in enumerate(refs)
        )
        if len(set(mask_refs)) != len(mask_refs):
            raise GlyphRevealMaskCountError("maskAssetRefs must be unique")
        base_ref = _required_ref(
            requirement.get("basePlateAssetRef"), "basePlateAssetRef"
        )
        if base_ref in mask_refs:
            raise GlyphRevealError("basePlateAssetRef cannot also be a mask")
        input_bindings = _normalize_input_bindings(
            requirement.get("inputBindings"),
            base_plate_asset_ref=base_ref,
            mask_asset_refs=mask_refs,
        )
        input_bindings_digest = _raw_sha256(
            requirement.get("inputBindingsDigest"), "inputBindingsDigest"
        )
        if input_bindings_digest != _digest(input_bindings):
            raise StaleInputError(
                "GlyphRevealRequirement inputBindingsDigest is invalid"
            )
        params = _normalize_composite_params(requirement.get("compositeParams"))
        inspection_digest = _raw_sha256(
            requirement.get("inspectionDigest"), "inspectionDigest"
        )
        return cls(
            workspace_ref=workspace_ref,
            production_run_ref=production_run_ref,
            requirement_ref=requirement_ref,
            glyph_slug=glyph_slug,
            target_shot_ref=target_shot_ref,
            frame_range_start=start,
            frame_range_end=end,
            reveal_frame_count=count,
            mask_asset_refs=mask_refs,
            base_plate_asset_ref=base_ref,
            inspection_digest=inspection_digest,
            _input_bindings_json=json.dumps(
                input_bindings,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            input_bindings_digest=input_bindings_digest,
            _composite_params_json=json.dumps(
                params,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            payload_digest=requirement["payloadDigest"],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION,
            "workspaceRef": self.workspace_ref,
            "productionRunRef": self.production_run_ref,
            "requirementRef": self.requirement_ref,
            "glyphSlug": self.glyph_slug,
            "targetShotRef": self.target_shot_ref,
            "frameRangeStart": self.frame_range_start,
            "frameRangeEnd": self.frame_range_end,
            "revealFrameCount": self.reveal_frame_count,
            "maskAssetRefs": list(self.mask_asset_refs),
            "basePlateAssetRef": self.base_plate_asset_ref,
            "inspectionDigest": self.inspection_digest,
            "inputBindings": self.input_bindings,
            "inputBindingsDigest": self.input_bindings_digest,
            "compositeParams": self.composite_params,
            "outputDigest": None,
            "publicationAllowed": False,
            "payloadDigest": self.payload_digest,
        }

def _requirement_value(
    value: GlyphRevealRequirement | Mapping[str, Any],
) -> GlyphRevealRequirement:
    if isinstance(value, GlyphRevealRequirement):
        return GlyphRevealRequirement.from_mapping(value.as_dict())
    return GlyphRevealRequirement.from_mapping(value)


def _validate_current_bindings(
    requirement: GlyphRevealRequirement,
    *,
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_port: BasePlateGlyphInspectionPort,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    tuple[int, int, int, int],
]:
    base = _base_plate_asset(
        base_plate_asset,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        target_shot_ref=requirement.target_shot_ref,
    )
    if base["assetVersionRef"] != requirement.base_plate_asset_ref:
        raise StaleInputError("basePlateAssetRef binding is stale")
    masks = _mask_assets(
        mask_assets,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        glyph_slug=requirement.glyph_slug,
        expected_refs=requirement.mask_asset_refs,
    )
    inspection, dimensions = _inspection_evidence(
        inspection_port,
        workspace_ref=requirement.workspace_ref,
        production_run_ref=requirement.production_run_ref,
        target_shot_ref=requirement.target_shot_ref,
        base_plate_asset=base,
    )
    if inspection["payloadDigest"] != requirement.inspection_digest:
        raise StaleInputError(
            "GlyphRevealRequirement base plate inspection binding is stale"
        )
    if dimensions[2] < requirement.frame_range_end:
        raise GlyphRevealFrameRangeError(
            "frameRangeEnd exceeds the base plate actual frameCount"
        )
    _validate_geometry(
        requirement.composite_params,
        base_width=dimensions[0],
        base_height=dimensions[1],
    )
    current_bindings = _input_bindings_from_assets(base, masks)
    if (
        current_bindings != requirement.input_bindings
        or _digest(current_bindings) != requirement.input_bindings_digest
    ):
        raise StaleInputError("GlyphRevealRequirement input bindings are stale")
    return base, masks, inspection, dimensions


def build_glyph_reveal_requirement(
    command: Mapping[str, Any],
    *,
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_port: BasePlateGlyphInspectionPort,
) -> GlyphRevealRequirement:
    """Create one planned, non-publishable M13 requirement.

    The output digest remains ``null`` until a separate composition result is
    built.  Both AssetVersion inputs and port-issued inspection evidence are
    verified here; the byte bindings are verified again at execution so a
    same-ref replacement cannot be substituted.
    """

    if (
        not isinstance(command, Mapping)
        or set(command) != _REQUIREMENT_COMMAND_FIELDS
    ):
        raise GlyphRevealError(
            "glyph reveal requirement command fields are invalid"
        )
    workspace_ref = _required_ref(command.get("workspaceRef"), "workspaceRef")
    production_run_ref = _required_ref(
        command.get("productionRunRef"), "productionRunRef"
    )
    requirement_ref = _required_ref(
        command.get("requirementRef"), "requirementRef"
    )
    glyph_slug = _glyph_slug(command.get("glyphSlug"))
    target_shot_ref = _required_ref(command.get("targetShotRef"), "targetShotRef")
    start, end, count = _frame_range(
        command.get("frameRangeStart"),
        command.get("frameRangeEnd"),
        command.get("revealFrameCount"),
    )
    refs = command.get("maskAssetRefs")
    if not isinstance(refs, list) or len(refs) != count:
        raise GlyphRevealMaskCountError(
            "maskAssetRefs count does not match revealFrameCount"
        )
    mask_refs = [
        _required_ref(ref, f"maskAssetRefs[{index}]")
        for index, ref in enumerate(refs)
    ]
    if len(set(mask_refs)) != len(mask_refs):
        raise GlyphRevealMaskCountError("maskAssetRefs must be unique")
    base_ref = _required_ref(command.get("basePlateAssetRef"), "basePlateAssetRef")
    params = _normalize_composite_params(command.get("compositeParams"))
    base = _base_plate_asset(
        base_plate_asset,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        target_shot_ref=target_shot_ref,
    )
    if base["assetVersionRef"] != base_ref:
        raise StaleInputError("basePlateAssetRef binding is stale")
    masks = _mask_assets(
        mask_assets,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        glyph_slug=glyph_slug,
        expected_refs=mask_refs,
    )
    inspection, dimensions = _inspection_evidence(
        inspection_port,
        workspace_ref=workspace_ref,
        production_run_ref=production_run_ref,
        target_shot_ref=target_shot_ref,
        base_plate_asset=base,
    )
    if dimensions[2] < end:
        raise GlyphRevealFrameRangeError(
            "frameRangeEnd exceeds the base plate actual frameCount"
        )
    _validate_geometry(
        params,
        base_width=dimensions[0],
        base_height=dimensions[1],
    )
    input_bindings = _input_bindings_from_assets(base, masks)
    unsigned = {
        "schemaVersion": GLYPH_REVEAL_REQUIREMENT_SCHEMA_VERSION,
        "workspaceRef": workspace_ref,
        "productionRunRef": production_run_ref,
        "requirementRef": requirement_ref,
        "glyphSlug": glyph_slug,
        "targetShotRef": target_shot_ref,
        "frameRangeStart": start,
        "frameRangeEnd": end,
        "revealFrameCount": count,
        "maskAssetRefs": mask_refs,
        "basePlateAssetRef": base_ref,
        "inspectionDigest": inspection["payloadDigest"],
        "inputBindings": input_bindings,
        "inputBindingsDigest": _digest(input_bindings),
        "compositeParams": params,
        "outputDigest": None,
        "publicationAllowed": False,
    }
    requirement = GlyphRevealRequirement.from_mapping(_sealed(unsigned))
    return requirement


def build_glyph_reveal_execution_request(
    requirement: GlyphRevealRequirement | Mapping[str, Any],
    base_plate_asset: Mapping[str, Any],
    mask_assets: Sequence[Mapping[str, Any]],
    inspection_port: BasePlateGlyphInspectionPort,
) -> dict[str, Any]:
    """Project current V5 AssetVersions into one digest-pinned V4 command."""

    current = _requirement_value(requirement)
    base, masks, inspection, dimensions = _validate_current_bindings(
        current,
        base_plate_asset=base_plate_asset,
        mask_assets=mask_assets,
        inspection_port=inspection_port,
    )
    execution = {
        "schemaVersion": GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION,
        "workspaceRef": current.workspace_ref,
        "productionRunRef": current.production_run_ref,
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "glyphSlug": current.glyph_slug,
        "targetShotRef": current.target_shot_ref,
        "frameRangeStart": current.frame_range_start,
        "frameRangeEnd": current.frame_range_end,
        "revealFrameCount": current.reveal_frame_count,
        "inputBindingsDigest": current.input_bindings_digest,
        "basePlate": {
            "assetVersionRef": base["assetVersionRef"],
            "assetVersionDigest": base["payloadDigest"],
            "storageKey": base["storageKey"],
            "fileDigest": f"sha256:{base['sha256']}",
        },
        "masks": [
            {
                "assetVersionRef": mask["assetVersionRef"],
                "assetVersionDigest": mask["payloadDigest"],
                "storageKey": mask["storageKey"],
                "fileDigest": f"sha256:{mask['sha256']}",
                "pixelDigest": mask["pixelDigest"],
                "pixelDigestSpec": mask["pixelDigestSpec"],
                "pixelMode": mask["pixelMode"],
                "width": mask["width"],
                "height": mask["height"],
                "glyphSlug": mask["glyphSlug"],
                "revealOrdinal": mask["revealOrdinal"],
                "assetRole": mask["assetRole"],
                "glyphManifestDigest": mask["glyphManifestDigest"],
            }
            for mask in masks
        ],
        "inspectionDigest": current.inspection_digest,
        "compositeParams": current.composite_params,
        "output": {
            "width": dimensions[0],
            "height": dimensions[1],
            "frameRate": dimensions[3],
            "totalFrames": dimensions[2],
        },
        "publicationAllowed": False,
    }
    return _validate_execution_request(_sealed(execution), requirement=current)


def _validate_execution_request(
    value: Any,
    *,
    requirement: GlyphRevealRequirement,
) -> dict[str, Any]:
    request = _verify_sealed(value, "glyphRevealExecutionRequest")
    if (
        set(request) != _EXECUTION_REQUEST_FIELDS
        or request.get("schemaVersion")
        != GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION
        or request.get("workspaceRef") != requirement.workspace_ref
        or request.get("productionRunRef") != requirement.production_run_ref
        or request.get("requirementRef") != requirement.requirement_ref
        or request.get("requirementDigest") != requirement.payload_digest
        or request.get("glyphSlug") != requirement.glyph_slug
        or request.get("targetShotRef") != requirement.target_shot_ref
        or request.get("frameRangeStart") != requirement.frame_range_start
        or request.get("frameRangeEnd") != requirement.frame_range_end
        or request.get("revealFrameCount")
        != requirement.reveal_frame_count
        or request.get("inputBindingsDigest")
        != requirement.input_bindings_digest
        or request.get("inspectionDigest") != requirement.inspection_digest
        or request.get("publicationAllowed") is not False
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal execution request is not bound to the requirement"
        )
    if _normalize_composite_params(
        request.get("compositeParams")
    ) != requirement.composite_params:
        raise GlyphRevealArtifactError(
            "glyph reveal execution compositeParams are stale"
        )
    base = request.get("basePlate")
    masks = request.get("masks")
    if (
        not isinstance(base, Mapping)
        or set(base) != _EXECUTION_BASE_PLATE_FIELDS
        or not isinstance(masks, list)
        or len(masks) != requirement.reveal_frame_count
        or any(
            not isinstance(mask, Mapping)
            or set(mask) != _EXECUTION_MASK_FIELDS
            for mask in masks
        )
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal execution input fields are invalid"
        )
    _storage_key(base.get("storageKey"), "basePlate.storageKey")
    _raw_sha256(
        base.get("assetVersionDigest"), "basePlate.assetVersionDigest"
    )
    _pixel_digest(base.get("fileDigest"), "basePlate.fileDigest")
    execution_bindings = {
        "basePlate": {
            "assetVersionRef": base.get("assetVersionRef"),
            "assetVersionDigest": base.get("assetVersionDigest"),
            "fileDigest": base.get("fileDigest"),
        },
        "masks": [],
    }
    manifest_digest: str | None = None
    for index, mask in enumerate(masks, start=1):
        _storage_key(mask.get("storageKey"), f"masks[{index - 1}].storageKey")
        _raw_sha256(
            mask.get("assetVersionDigest"),
            f"masks[{index - 1}].assetVersionDigest",
        )
        _pixel_digest(
            mask.get("fileDigest"), f"masks[{index - 1}].fileDigest"
        )
        _pixel_digest(
            mask.get("pixelDigest"), f"masks[{index - 1}].pixelDigest"
        )
        current_manifest = _pixel_digest(
            mask.get("glyphManifestDigest"),
            f"masks[{index - 1}].glyphManifestDigest",
        )
        if manifest_digest is None:
            manifest_digest = current_manifest
        if (
            current_manifest != manifest_digest
            or mask.get("assetVersionRef")
            != requirement.mask_asset_refs[index - 1]
            or mask.get("pixelDigestSpec") != PIXEL_DIGEST_SPEC
            or mask.get("pixelMode") != PIXEL_MODE
            or mask.get("glyphSlug") != requirement.glyph_slug
            or mask.get("revealOrdinal") != index
            or mask.get("assetRole") != GLYPH_MASK_ASSET_ROLE
        ):
            raise GlyphRevealArtifactError(
                "glyph reveal execution mask binding is stale"
            )
        _integer(
            mask.get("width"),
            f"masks[{index - 1}].width",
            minimum=1,
            maximum=131_072,
            error_type=GlyphRevealArtifactError,
        )
        _integer(
            mask.get("height"),
            f"masks[{index - 1}].height",
            minimum=1,
            maximum=131_072,
            error_type=GlyphRevealArtifactError,
        )
        execution_bindings["masks"].append(
            {
                "assetVersionRef": mask.get("assetVersionRef"),
                "assetVersionDigest": mask.get("assetVersionDigest"),
                "fileDigest": mask.get("fileDigest"),
                "pixelDigest": mask.get("pixelDigest"),
            }
        )
    if (
        execution_bindings != requirement.input_bindings
        or _digest(execution_bindings) != requirement.input_bindings_digest
    ):
        raise GlyphRevealArtifactError(
            "glyph reveal execution input bindings are stale"
        )

    output = request.get("output")
    if not isinstance(output, Mapping) or set(output) != _EXECUTION_OUTPUT_FIELDS:
        raise GlyphRevealArtifactError("glyph reveal execution output is invalid")
    width = _integer(
        output.get("width"),
        "output.width",
        minimum=1,
        maximum=131_072,
        error_type=GlyphRevealArtifactError,
    )
    height = _integer(
        output.get("height"),
        "output.height",
        minimum=1,
        maximum=131_072,
        error_type=GlyphRevealArtifactError,
    )
    _frame_rate(output.get("frameRate"), "output.frameRate")
    total_frames = _integer(
        output.get("totalFrames"),
        "output.totalFrames",
        minimum=1,
        maximum=10_000_000,
        error_type=GlyphRevealArtifactError,
    )
    if total_frames < requirement.frame_range_end:
        raise GlyphRevealArtifactError(
            "glyph reveal execution truncates the reveal range"
        )
    _validate_geometry(
        requirement.composite_params,
        base_width=width,
        base_height=height,
    )
    return request


def _validate_output_digest(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OUTPUT_DIGEST_FIELDS:
        raise GlyphRevealArtifactError("outputDigest fields are invalid")
    result = deepcopy(dict(value))
    if (
        result.get("fileDigestAlgorithm") != "sha256"
        or result.get("pixelDigestSpec") != VIDEO_PIXEL_DIGEST_SPEC
        or result.get("pixelMode") != VIDEO_PIXEL_MODE
    ):
        raise GlyphRevealArtifactError("outputDigest algorithms are invalid")
    _pixel_digest(result.get("fileDigest"), "outputDigest.fileDigest")
    _pixel_digest(result.get("pixelDigest"), "outputDigest.pixelDigest")
    for field, maximum in (
        ("width", 131_072),
        ("height", 131_072),
        ("frameCount", 10_000_000),
    ):
        _integer(
            result.get(field),
            f"outputDigest.{field}",
            minimum=1,
            maximum=maximum,
            error_type=GlyphRevealArtifactError,
        )
    return result


def build_glyph_reveal_composition_result(
    requirement: GlyphRevealRequirement | Mapping[str, Any],
    execution_request: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    """Seal one deterministic render as a candidate-only M13 result."""

    current = _requirement_value(requirement)
    execution = _validate_execution_request(
        execution_request, requirement=current
    )
    execution_digest = execution["payloadDigest"]
    try:
        artifact = _verify_sealed(artifact, "glyphRevealArtifactEvidence")
    except StaleInputError as exc:
        raise GlyphRevealArtifactError(
            "glyph reveal artifact evidence seal is invalid"
        ) from exc
    if (
        set(artifact) != _ARTIFACT_EVIDENCE_FIELDS
        or artifact.get("schemaVersion")
        != GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION
    ):
        raise GlyphRevealArtifactError("glyph reveal artifact fields are invalid")
    storage_key = _storage_key(artifact.get("storageKey"), "artifact.storageKey")
    if PurePosixPath(storage_key).name != (
        f"glyph-reveal-{execution_digest}.mp4"
    ):
        raise GlyphRevealArtifactError(
            "artifact storageKey is not bound to the execution request digest"
        )
    byte_size = _integer(
        artifact.get("byteSize"),
        "artifact.byteSize",
        minimum=1,
        maximum=10**12,
        error_type=GlyphRevealArtifactError,
    )
    file_sha256 = _raw_sha256(artifact.get("sha256"), "artifact.sha256")
    output_digest = _validate_output_digest(artifact.get("outputDigest"))
    if output_digest["fileDigest"] != f"sha256:{file_sha256}":
        raise GlyphRevealArtifactError(
            "artifact sha256 and outputDigest.fileDigest disagree"
        )
    if (
        artifact.get("requirementDigest") != current.payload_digest
        or artifact.get("executionRequestDigest") != execution_digest
        or artifact.get("provenance") != "LOCAL_EVIDENCE"
        or artifact.get("gpuUsed") is not False
        or artifact.get("publicationAllowed") is not False
    ):
        raise GlyphRevealArtifactError("artifact escaped the local candidate boundary")
    composer_identity = _required_ref(
        artifact.get("composerIdentity"), "artifact.composerIdentity"
    )
    adapter_identity = _required_ref(
        artifact.get("adapterIdentity"), "artifact.adapterIdentity"
    )
    if composer_identity != GLYPH_REVEAL_COMPOSER_CAPABILITY:
        raise GlyphRevealArtifactError("artifact composerIdentity is unsupported")
    if adapter_identity != V4_COMPOSITION_ADAPTER_IDENTITY:
        raise GlyphRevealArtifactError("artifact adapterIdentity is unsupported")
    runtime_identity = _pixel_digest(
        artifact.get("runtimeIdentity"), "artifact.runtimeIdentity"
    )
    runtime_versions: dict[str, str] = {}
    for field in ("ffmpegVersion", "ffprobeVersion"):
        value = artifact.get(field)
        if (
            not isinstance(value, str)
            or value != value.strip()
            or not value
            or len(value) > 500
            or any(ord(character) < 32 for character in value)
        ):
            raise GlyphRevealArtifactError(f"artifact.{field} is invalid")
        runtime_versions[field] = value
    expected_runtime_identity = "sha256:" + sha256(
        json.dumps(
            runtime_versions,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if runtime_identity != expected_runtime_identity:
        raise GlyphRevealArtifactError("artifact runtimeIdentity is invalid")
    probe_dimensions = _video_probe_facts(
        artifact.get("probe"), field="artifact.probe"
    )
    expected_output = execution["output"]
    if probe_dimensions != (
        output_digest["width"],
        output_digest["height"],
        output_digest["frameCount"],
        expected_output["frameRate"],
    ):
        raise GlyphRevealArtifactError("artifact probe and outputDigest disagree")
    if (
        output_digest["width"] != expected_output["width"]
        or output_digest["height"] != expected_output["height"]
        or output_digest["frameCount"] != expected_output["totalFrames"]
    ):
        raise GlyphRevealArtifactError(
            "artifact output is not bound to the execution request"
        )
    artifact_ref = "m13-glyph-reveal-artifact-" + file_sha256[:32]
    semantic = {
        "workspaceRef": current.workspace_ref,
        "productionRunRef": current.production_run_ref,
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "executionRequestDigest": execution_digest,
        "inspectionDigest": current.inspection_digest,
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "artifactRef": artifact_ref,
        "fileDigest": output_digest["fileDigest"],
        "pixelDigest": output_digest["pixelDigest"],
    }
    result_ref = "m13-glyph-reveal-result-" + _digest(semantic)[:32]
    result = {
        "schemaVersion": GLYPH_REVEAL_COMPOSITION_RESULT_SCHEMA_VERSION,
        "workspaceRef": current.workspace_ref,
        "productionRunRef": current.production_run_ref,
        "compositionResultRef": result_ref,
        "requirementRef": current.requirement_ref,
        "requirementDigest": current.payload_digest,
        "executionRequestDigest": execution_digest,
        "inspectionDigest": current.inspection_digest,
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "inputBindingsDigest": current.input_bindings_digest,
        "glyphSlug": current.glyph_slug,
        "targetShotRef": current.target_shot_ref,
        "basePlateAssetRef": current.base_plate_asset_ref,
        "maskAssetRefs": list(current.mask_asset_refs),
        "artifactRef": artifact_ref,
        "storageKey": storage_key,
        "byteSize": byte_size,
        "sha256": file_sha256,
        "outputDigest": output_digest,
        "composerIdentity": composer_identity,
        "adapterIdentity": adapter_identity,
        "runtimeIdentity": runtime_identity,
        "ffmpegVersion": runtime_versions["ffmpegVersion"],
        "ffprobeVersion": runtime_versions["ffprobeVersion"],
        "provenance": "LOCAL_EVIDENCE",
        "state": "COMPOSED_CANDIDATE",
        "publicationAllowed": False,
    }
    return _sealed(result)
