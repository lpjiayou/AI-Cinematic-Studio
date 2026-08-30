"""V4 execution boundary delegating deterministic composition to V3."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DeterministicFfmpegComposer,
    RenderArtifactError,
)


GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-glyph-reveal-execution-request.v1"
)
GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-glyph-reveal-artifact-evidence.v1"
)
GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2 = (
    "v5.m13-glyph-reveal-execution-request.v2"
)
GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2 = (
    "v4.m13-glyph-reveal-artifact-evidence.v2"
)
GLYPH_REVEAL_RENDERER_IDENTITY_V2 = (
    "v3.deterministic-glyph-reveal-ffmpeg"
)
GLYPH_REVEAL_RENDERER_VERSION_V2 = "2"
GLYPH_REVEAL_MASK_PIXEL_DIGEST_SPEC = (
    "RGBA8/exif-transposed/row-major/v1"
)

_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_GLYPH_SLUG = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GLYPH_REVEAL_REQUEST_FIELDS = frozenset(
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
_GLYPH_REVEAL_ARTIFACT_EVIDENCE_FIELDS = frozenset(
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
_GLYPH_REVEAL_REQUEST_FIELDS_V2 = frozenset(
    {
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
)
_GLYPH_REVEAL_SCHEDULE_FIELDS_V2 = frozenset(
    {
        "revealOrdinal",
        "maskAssetVersionRef",
        "startFrameInclusive",
        "endFrameExclusive",
    }
)
_GLYPH_REVEAL_OUTPUT_DIGEST_FIELDS_V2 = frozenset(
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
_GLYPH_REVEAL_OUTPUT_MEDIA_PROBE_FIELDS_V2 = frozenset(
    {"width", "height", "frameCount", "frameRate"}
)
_GLYPH_REVEAL_ARTIFACT_EVIDENCE_FIELDS_V2 = frozenset(
    {
        "schemaVersion",
        "artifactEvidenceRef",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegIdentity",
        "runtimeEvidenceDigest",
        "provenance",
        "gpuUsed",
        "publicationAllowed",
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "payloadDigest",
    }
)
_V3_GLYPH_REVEAL_RESULT_FIELDS_V2 = frozenset(
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
        "requirementRef",
        "requirementDigest",
        "executionRequestRef",
        "executionRequestDigest",
        "publicationAllowed",
    }
)


class CompositionExecutionError(RuntimeError):
    code = "worker_unavailable"


class CompositionRequestValidationError(CompositionExecutionError):
    code = "invalid_request"


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
        raise CompositionRequestValidationError(
            "glyph reveal request is not canonical JSON"
        ) from exc


def _sealed(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise CompositionRequestValidationError(
            "glyph reveal artifact evidence cannot predeclare payloadDigest"
        )
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return result


def _raw_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _prefixed_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _PREFIXED_SHA256.fullmatch(value) is None:
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _ref(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _REF.fullmatch(value) is None
    ):
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _integer(
    value: Any, field: str, *, minimum: int, maximum: int
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _closed_mapping(
    value: Any, fields: set[str], field: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise CompositionRequestValidationError(f"{field} fields are invalid")
    return deepcopy(dict(value))


def _storage_key(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
    ):
        raise CompositionRequestValidationError(f"{field} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _storage_key_v2(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or "//" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise CompositionRequestValidationError(f"{field} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CompositionRequestValidationError(f"{field} is invalid")
    return value


def _point(value: Any, field: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise CompositionRequestValidationError(f"{field} is invalid")
    return (
        _integer(value[0], f"{field}[0]", minimum=0, maximum=131_072),
        _integer(value[1], f"{field}[1]", minimum=0, maximum=131_072),
    )


def _validate_composite_params(
    value: Any, *, output_width: int, output_height: int
) -> dict[str, Any]:
    params = _closed_mapping(
        value,
        {"position", "scale", "perspective", "blendMode"},
        "compositeParams",
    )
    position = _closed_mapping(
        params["position"], {"xPixels", "yPixels"}, "compositeParams.position"
    )
    scale = _closed_mapping(
        params["scale"],
        {"widthPixels", "heightPixels"},
        "compositeParams.scale",
    )
    perspective = _closed_mapping(
        params["perspective"],
        {"topLeft", "topRight", "bottomLeft", "bottomRight"},
        "compositeParams.perspective",
    )
    if params["blendMode"] != "GRAZING_LIGHT_RELIEF":
        raise CompositionRequestValidationError(
            "compositeParams.blendMode is invalid"
        )
    x_pixels = _integer(
        position["xPixels"],
        "compositeParams.position.xPixels",
        minimum=0,
        maximum=131_072,
    )
    y_pixels = _integer(
        position["yPixels"],
        "compositeParams.position.yPixels",
        minimum=0,
        maximum=131_072,
    )
    width = _integer(
        scale["widthPixels"],
        "compositeParams.scale.widthPixels",
        minimum=2,
        maximum=131_072,
    )
    height = _integer(
        scale["heightPixels"],
        "compositeParams.scale.heightPixels",
        minimum=2,
        maximum=131_072,
    )
    if x_pixels + width > output_width or y_pixels + height > output_height:
        raise CompositionRequestValidationError(
            "compositeParams scale exceeds output"
        )
    points = {
        name: _point(
            perspective[name], f"compositeParams.perspective.{name}"
        )
        for name in ("topLeft", "topRight", "bottomLeft", "bottomRight")
    }
    if len(set(points.values())) != 4:
        raise CompositionRequestValidationError(
            "compositeParams perspective points are ambiguous"
        )
    if any(
        point_x >= width
        or point_y >= height
        or x_pixels + point_x > output_width
        or y_pixels + point_y > output_height
        for point_x, point_y in points.values()
    ):
        raise CompositionRequestValidationError(
            "compositeParams perspective exceeds output"
        )
    top_left = points["topLeft"]
    top_right = points["topRight"]
    bottom_left = points["bottomLeft"]
    bottom_right = points["bottomRight"]
    if not (
        top_left[0] < top_right[0]
        and bottom_left[0] < bottom_right[0]
        and top_left[1] < bottom_left[1]
        and top_right[1] < bottom_right[1]
    ):
        raise CompositionRequestValidationError(
            "compositeParams perspective corner ordering is invalid"
        )
    return params


def _validate_glyph_reveal_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CompositionRequestValidationError(
            "glyph reveal request must be an object"
        )
    request = deepcopy(dict(value))
    claimed_digest = request.pop("payloadDigest", None)
    _raw_digest(claimed_digest, "payloadDigest")
    actual_digest = sha256(_canonical_json(request)).hexdigest()
    if claimed_digest != actual_digest:
        raise CompositionRequestValidationError(
            "glyph reveal request payloadDigest is invalid"
        )
    request["payloadDigest"] = claimed_digest
    if set(request) != _GLYPH_REVEAL_REQUEST_FIELDS:
        raise CompositionRequestValidationError(
            "glyph reveal request fields are invalid"
        )
    if (
        request.get("schemaVersion")
        != GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION
        or request.get("publicationAllowed") is not False
    ):
        raise CompositionRequestValidationError(
            "glyph reveal request boundary is invalid"
        )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
    ):
        _ref(request.get(field), field)
    glyph_slug = request.get("glyphSlug")
    if (
        not isinstance(glyph_slug, str)
        or glyph_slug != glyph_slug.strip()
        or _GLYPH_SLUG.fullmatch(glyph_slug) is None
    ):
        raise CompositionRequestValidationError("glyphSlug is invalid")
    _raw_digest(request.get("requirementDigest"), "requirementDigest")
    _raw_digest(request.get("inputBindingsDigest"), "inputBindingsDigest")
    _raw_digest(request.get("inspectionDigest"), "inspectionDigest")
    count = _integer(
        request.get("revealFrameCount"),
        "revealFrameCount",
        minimum=1,
        maximum=1_024,
    )
    start = _integer(
        request.get("frameRangeStart"),
        "frameRangeStart",
        minimum=0,
        maximum=10_000_000,
    )
    end = _integer(
        request.get("frameRangeEnd"),
        "frameRangeEnd",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start or end - start < count:
        raise CompositionRequestValidationError("glyph reveal frameRange is invalid")

    base_plate = _closed_mapping(
        request.get("basePlate"),
        {
            "assetVersionRef",
            "assetVersionDigest",
            "storageKey",
            "fileDigest",
        },
        "basePlate",
    )
    _ref(base_plate["assetVersionRef"], "basePlate.assetVersionRef")
    _raw_digest(
        base_plate["assetVersionDigest"], "basePlate.assetVersionDigest"
    )
    _storage_key(base_plate["storageKey"], "basePlate.storageKey")
    _prefixed_digest(base_plate["fileDigest"], "basePlate.fileDigest")
    masks = request.get("masks")
    if not isinstance(masks, list) or len(masks) != count:
        raise CompositionRequestValidationError(
            "mask count does not match revealFrameCount"
        )
    seen_storage_keys: set[str] = {base_plate["storageKey"]}
    seen_asset_refs: set[str] = set()
    seen_pixel_digests: set[str] = set()
    mask_dimensions: tuple[int, int] | None = None
    glyph_manifest_digest: str | None = None
    for index, raw_mask in enumerate(masks):
        mask = _closed_mapping(
            raw_mask,
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
            },
            f"masks[{index}]",
        )
        asset_ref = _ref(
            mask["assetVersionRef"], f"masks[{index}].assetVersionRef"
        )
        if asset_ref in seen_asset_refs or asset_ref == base_plate["assetVersionRef"]:
            raise CompositionRequestValidationError(
                "mask AssetVersion refs must be unique"
            )
        seen_asset_refs.add(asset_ref)
        _raw_digest(
            mask["assetVersionDigest"], f"masks[{index}].assetVersionDigest"
        )
        storage_key = _storage_key(
            mask["storageKey"], f"masks[{index}].storageKey"
        )
        if storage_key in seen_storage_keys:
            raise CompositionRequestValidationError(
                "mask storage keys must be unique"
            )
        seen_storage_keys.add(storage_key)
        _prefixed_digest(mask["fileDigest"], f"masks[{index}].fileDigest")
        pixel_digest = _prefixed_digest(
            mask["pixelDigest"], f"masks[{index}].pixelDigest"
        )
        if pixel_digest in seen_pixel_digests:
            raise CompositionRequestValidationError(
                "mask pixel digests must be unique across reveal stages"
            )
        seen_pixel_digests.add(pixel_digest)
        manifest_digest = _prefixed_digest(
            mask["glyphManifestDigest"], f"masks[{index}].glyphManifestDigest"
        )
        if mask["pixelDigestSpec"] != GLYPH_REVEAL_MASK_PIXEL_DIGEST_SPEC:
            raise CompositionRequestValidationError(
                f"masks[{index}].pixelDigestSpec is invalid"
            )
        if (
            mask["pixelMode"] != "RGBA"
            or mask["glyphSlug"] != glyph_slug
            or mask["revealOrdinal"] != index + 1
            or mask["assetRole"] != "GLYPH_REVEAL_CUMULATIVE_MASK"
        ):
            raise CompositionRequestValidationError(
                f"masks[{index}] semantic binding is invalid"
            )
        mask_width = _integer(
            mask["width"],
            f"masks[{index}].width",
            minimum=1,
            maximum=131_072,
        )
        mask_height = _integer(
            mask["height"],
            f"masks[{index}].height",
            minimum=1,
            maximum=131_072,
        )
        dimensions = (mask_width, mask_height)
        if mask_dimensions is None:
            mask_dimensions = dimensions
            glyph_manifest_digest = manifest_digest
        elif (
            dimensions != mask_dimensions
            or manifest_digest != glyph_manifest_digest
        ):
            raise CompositionRequestValidationError(
                "mask pixel or manifest bindings disagree"
            )

    input_bindings = {
        "basePlate": {
            "assetVersionRef": base_plate["assetVersionRef"],
            "assetVersionDigest": base_plate["assetVersionDigest"],
            "fileDigest": base_plate["fileDigest"],
        },
        "masks": [
            {
                "assetVersionRef": mask["assetVersionRef"],
                "assetVersionDigest": mask["assetVersionDigest"],
                "fileDigest": mask["fileDigest"],
                "pixelDigest": mask["pixelDigest"],
            }
            for mask in masks
        ],
    }
    actual_input_bindings_digest = sha256(
        _canonical_json(input_bindings)
    ).hexdigest()
    if request["inputBindingsDigest"] != actual_input_bindings_digest:
        raise CompositionRequestValidationError("inputBindingsDigest is invalid")

    output = _closed_mapping(
        request.get("output"),
        {"width", "height", "frameRate", "totalFrames"},
        "output",
    )
    width = _integer(output["width"], "output.width", minimum=1, maximum=131_072)
    height = _integer(
        output["height"], "output.height", minimum=1, maximum=131_072
    )
    _integer(output["frameRate"], "output.frameRate", minimum=1, maximum=1_000)
    total_frames = _integer(
        output["totalFrames"],
        "output.totalFrames",
        minimum=1,
        maximum=10_000_000,
    )
    if end > total_frames:
        raise CompositionRequestValidationError(
            "frameRangeEnd exceeds output.totalFrames"
        )
    _validate_composite_params(
        request.get("compositeParams"),
        output_width=width,
        output_height=height,
    )
    return request


def _validate_glyph_reveal_request_v2(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CompositionRequestValidationError(
            "glyph reveal v2 request must be an object"
        )
    request = deepcopy(dict(value))
    claimed_digest = request.pop("payloadDigest", None)
    _raw_digest(claimed_digest, "payloadDigest")
    actual_digest = sha256(_canonical_json(request)).hexdigest()
    if claimed_digest != actual_digest:
        raise CompositionRequestValidationError(
            "glyph reveal v2 request payloadDigest is invalid"
        )
    request["payloadDigest"] = claimed_digest
    if set(request) != _GLYPH_REVEAL_REQUEST_FIELDS_V2:
        raise CompositionRequestValidationError(
            "glyph reveal v2 request fields are invalid"
        )
    if (
        request.get("schemaVersion")
        != GLYPH_REVEAL_EXECUTION_REQUEST_SCHEMA_VERSION_V2
        or request.get("publicationAllowed") is not False
    ):
        raise CompositionRequestValidationError(
            "glyph reveal v2 request boundary is invalid"
        )
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "requirementRef",
        "targetShotRef",
        "basePlateInspectionRef",
    ):
        _ref(request.get(field), field)
    glyph_slug = request.get("glyphSlug")
    if (
        not isinstance(glyph_slug, str)
        or glyph_slug != glyph_slug.strip()
        or _GLYPH_SLUG.fullmatch(glyph_slug) is None
    ):
        raise CompositionRequestValidationError("glyphSlug is invalid")
    for field in (
        "requirementDigest",
        "inputBindingsDigest",
        "basePlateInspectionDigest",
    ):
        _raw_digest(request.get(field), field)
    start = _integer(
        request.get("frameRangeStartInclusive"),
        "frameRangeStartInclusive",
        minimum=0,
        maximum=10_000_000,
    )
    end = _integer(
        request.get("frameRangeEndExclusive"),
        "frameRangeEndExclusive",
        minimum=1,
        maximum=10_000_001,
    )
    if end <= start:
        raise CompositionRequestValidationError("glyph reveal frameRange is invalid")

    base_plate = _closed_mapping(
        request.get("basePlate"),
        {
            "assetVersionRef",
            "assetVersionDigest",
            "storageKey",
            "fileDigest",
        },
        "basePlate",
    )
    _ref(base_plate["assetVersionRef"], "basePlate.assetVersionRef")
    _raw_digest(
        base_plate["assetVersionDigest"], "basePlate.assetVersionDigest"
    )
    _storage_key(base_plate["storageKey"], "basePlate.storageKey")
    _prefixed_digest(base_plate["fileDigest"], "basePlate.fileDigest")

    masks = request.get("masks")
    if (
        not isinstance(masks, list)
        or not masks
        or len(masks) > 1_024
    ):
        raise CompositionRequestValidationError("glyph reveal mask count is invalid")
    seen_storage_keys: set[str] = {base_plate["storageKey"]}
    seen_asset_refs: set[str] = set()
    seen_pixel_digests: set[str] = set()
    mask_dimensions: tuple[int, int] | None = None
    glyph_manifest_digest: str | None = None
    for index, raw_mask in enumerate(masks):
        mask = _closed_mapping(
            raw_mask,
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
            },
            f"masks[{index}]",
        )
        asset_ref = _ref(
            mask["assetVersionRef"], f"masks[{index}].assetVersionRef"
        )
        if asset_ref in seen_asset_refs or asset_ref == base_plate["assetVersionRef"]:
            raise CompositionRequestValidationError(
                "mask AssetVersion refs must be unique"
            )
        seen_asset_refs.add(asset_ref)
        _raw_digest(
            mask["assetVersionDigest"], f"masks[{index}].assetVersionDigest"
        )
        storage_key = _storage_key(
            mask["storageKey"], f"masks[{index}].storageKey"
        )
        if storage_key in seen_storage_keys:
            raise CompositionRequestValidationError(
                "mask storage keys must be unique"
            )
        seen_storage_keys.add(storage_key)
        _prefixed_digest(mask["fileDigest"], f"masks[{index}].fileDigest")
        pixel_digest = _prefixed_digest(
            mask["pixelDigest"], f"masks[{index}].pixelDigest"
        )
        if pixel_digest in seen_pixel_digests:
            raise CompositionRequestValidationError(
                "mask pixel digests must be unique across reveal stages"
            )
        seen_pixel_digests.add(pixel_digest)
        manifest_digest = _prefixed_digest(
            mask["glyphManifestDigest"], f"masks[{index}].glyphManifestDigest"
        )
        if mask["pixelDigestSpec"] != GLYPH_REVEAL_MASK_PIXEL_DIGEST_SPEC:
            raise CompositionRequestValidationError(
                f"masks[{index}].pixelDigestSpec is invalid"
            )
        reveal_ordinal = _integer(
            mask["revealOrdinal"],
            f"masks[{index}].revealOrdinal",
            minimum=1,
            maximum=1_024,
        )
        if (
            mask["pixelMode"] != "RGBA"
            or mask["glyphSlug"] != glyph_slug
            or reveal_ordinal != index + 1
            or mask["assetRole"] != "GLYPH_REVEAL_CUMULATIVE_MASK"
        ):
            raise CompositionRequestValidationError(
                f"masks[{index}] semantic binding is invalid"
            )
        dimensions = (
            _integer(
                mask["width"],
                f"masks[{index}].width",
                minimum=1,
                maximum=131_072,
            ),
            _integer(
                mask["height"],
                f"masks[{index}].height",
                minimum=1,
                maximum=131_072,
            ),
        )
        if mask_dimensions is None:
            mask_dimensions = dimensions
            glyph_manifest_digest = manifest_digest
        elif (
            dimensions != mask_dimensions
            or manifest_digest != glyph_manifest_digest
        ):
            raise CompositionRequestValidationError(
                "mask pixel or manifest bindings disagree"
            )

    input_bindings = {
        "basePlate": {
            "assetVersionRef": base_plate["assetVersionRef"],
            "assetVersionDigest": base_plate["assetVersionDigest"],
            "fileDigest": base_plate["fileDigest"],
        },
        "masks": [
            {
                "assetVersionRef": mask["assetVersionRef"],
                "assetVersionDigest": mask["assetVersionDigest"],
                "fileDigest": mask["fileDigest"],
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
        "basePlateInspection": {
            "inspectionRef": request["basePlateInspectionRef"],
            "inspectionDigest": request["basePlateInspectionDigest"],
        },
    }
    actual_input_bindings_digest = sha256(
        _canonical_json(input_bindings)
    ).hexdigest()
    if request["inputBindingsDigest"] != actual_input_bindings_digest:
        raise CompositionRequestValidationError("inputBindingsDigest is invalid")
    expected_execution_request_ref = "m13-glyph-reveal-execution-" + sha256(
        _canonical_json(
            {
                "requirementRef": request["requirementRef"],
                "requirementDigest": request["requirementDigest"],
                "inputBindingsDigest": request["inputBindingsDigest"],
                "basePlateInspectionDigest": request[
                    "basePlateInspectionDigest"
                ],
            }
        )
    ).hexdigest()[:32]
    if request["executionRequestRef"] != expected_execution_request_ref:
        raise CompositionRequestValidationError(
            "executionRequestRef derivation is invalid"
        )

    schedule = request.get("revealSchedule")
    if not isinstance(schedule, list) or len(schedule) != len(masks):
        raise CompositionRequestValidationError(
            "revealSchedule count does not match masks"
        )
    previous_end = start
    for index, raw_entry in enumerate(schedule):
        entry = _closed_mapping(
            raw_entry,
            set(_GLYPH_REVEAL_SCHEDULE_FIELDS_V2),
            f"revealSchedule[{index}]",
        )
        ordinal = _integer(
            entry["revealOrdinal"],
            f"revealSchedule[{index}].revealOrdinal",
            minimum=1,
            maximum=1_024,
        )
        stage_start = _integer(
            entry["startFrameInclusive"],
            f"revealSchedule[{index}].startFrameInclusive",
            minimum=0,
            maximum=10_000_000,
        )
        stage_end = _integer(
            entry["endFrameExclusive"],
            f"revealSchedule[{index}].endFrameExclusive",
            minimum=1,
            maximum=10_000_001,
        )
        if (
            ordinal != index + 1
            or entry["maskAssetVersionRef"] != masks[index]["assetVersionRef"]
        ):
            raise CompositionRequestValidationError(
                "revealSchedule mask binding is invalid"
            )
        _ref(
            entry["maskAssetVersionRef"],
            f"revealSchedule[{index}].maskAssetVersionRef",
        )
        if stage_start != previous_end or stage_end <= stage_start or stage_end > end:
            raise CompositionRequestValidationError(
                "revealSchedule intervals are invalid"
            )
        previous_end = stage_end
    if previous_end != end:
        raise CompositionRequestValidationError(
            "revealSchedule does not cover frameRange"
        )
    _storage_key_v2(base_plate["storageKey"], "basePlate.storageKey")
    for index, mask in enumerate(masks):
        _storage_key_v2(mask["storageKey"], f"masks[{index}].storageKey")

    output = _closed_mapping(
        request.get("output"),
        {"width", "height", "frameRate", "totalFrames"},
        "output",
    )
    width = _integer(output["width"], "output.width", minimum=1, maximum=131_072)
    height = _integer(
        output["height"], "output.height", minimum=1, maximum=131_072
    )
    _integer(output["frameRate"], "output.frameRate", minimum=1, maximum=1_000)
    total_frames = _integer(
        output["totalFrames"],
        "output.totalFrames",
        minimum=1,
        maximum=10_000_000,
    )
    if end > total_frames:
        raise CompositionRequestValidationError(
            "frameRangeEndExclusive exceeds output.totalFrames"
        )
    _validate_composite_params(
        request.get("compositeParams"),
        output_width=width,
        output_height=height,
    )
    return request


def _expected_glyph_output_storage_key_v2(request: Mapping[str, Any]) -> str:
    workspace_hash = sha256(str(request["workspaceRef"]).encode("utf-8")).hexdigest()[
        :20
    ]
    run_hash = sha256(str(request["productionRunRef"]).encode("utf-8")).hexdigest()[
        :20
    ]
    return (
        f"{workspace_hash}/{run_hash}/glyph-reveal/"
        f"glyph-reveal-{request['payloadDigest']}.mp4"
    )


def _runtime_evidence_digest_v2(
    *,
    ffmpeg_identity: str,
    renderer_identity: str,
    renderer_version: str,
) -> str:
    payload = {
        "ffmpegIdentity": ffmpeg_identity,
        "rendererIdentity": renderer_identity,
        "rendererVersion": renderer_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _artifact_evidence_ref_v2(
    *, execution_request_digest: str, file_digest: str
) -> str:
    encoded = json.dumps(
        {
            "executionRequestDigest": execution_request_digest,
            "fileDigest": file_digest,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        "m13-glyph-reveal-artifact-evidence-"
        + sha256(encoded).hexdigest()[:32]
    )


def _validate_v3_glyph_reveal_result_v2(
    value: Any,
    *,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    result = _closed_mapping(
        value,
        set(_V3_GLYPH_REVEAL_RESULT_FIELDS_V2),
        "V3 glyph reveal v2 result",
    )
    expected_storage_key = _expected_glyph_output_storage_key_v2(request)
    if (
        _storage_key_v2(result["outputStorageKey"], "outputStorageKey")
        != expected_storage_key
        or result.get("requirementRef") != request["requirementRef"]
        or result.get("requirementDigest") != request["requirementDigest"]
        or result.get("executionRequestRef") != request["executionRequestRef"]
        or result.get("executionRequestDigest") != request["payloadDigest"]
        or result.get("publicationAllowed") is not False
    ):
        raise RenderArtifactError("V3 glyph reveal v2 artifact lineage is invalid")
    _integer(
        result.get("outputByteSize"),
        "outputByteSize",
        minimum=1,
        maximum=10**12,
    )
    output_digest = _closed_mapping(
        result.get("outputDigest"),
        set(_GLYPH_REVEAL_OUTPUT_DIGEST_FIELDS_V2),
        "outputDigest",
    )
    if (
        output_digest.get("fileDigestAlgorithm") != "sha256"
        or output_digest.get("decodedFramePixelDigestSpec")
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or output_digest.get("pixelMode") != "RGBA"
    ):
        raise RenderArtifactError("V3 glyph reveal v2 output digest is invalid")
    _prefixed_digest(output_digest.get("fileDigest"), "outputDigest.fileDigest")
    _prefixed_digest(
        output_digest.get("decodedFramePixelDigest"),
        "outputDigest.decodedFramePixelDigest",
    )
    output = request["output"]
    expected_media = {
        "width": output["width"],
        "height": output["height"],
        "frameCount": output["totalFrames"],
        "frameRate": output["frameRate"],
    }
    for field, maximum in (
        ("width", 131_072),
        ("height", 131_072),
        ("frameCount", 10_000_000),
        ("frameRate", 1_000),
    ):
        _integer(
            output_digest.get(field),
            f"outputDigest.{field}",
            minimum=1,
            maximum=maximum,
        )
    output_probe = _closed_mapping(
        result.get("outputMediaProbe"),
        set(_GLYPH_REVEAL_OUTPUT_MEDIA_PROBE_FIELDS_V2),
        "outputMediaProbe",
    )
    for field, maximum in (
        ("width", 131_072),
        ("height", 131_072),
        ("frameCount", 10_000_000),
        ("frameRate", 1_000),
    ):
        _integer(
            output_probe.get(field),
            f"outputMediaProbe.{field}",
            minimum=1,
            maximum=maximum,
        )
    if (
        {field: output_digest[field] for field in expected_media} != expected_media
        or output_probe != expected_media
    ):
        raise RenderArtifactError(
            "V3 glyph reveal v2 output media contract is invalid"
        )
    renderer_identity = result.get("rendererIdentity")
    renderer_version = result.get("rendererVersion")
    ffmpeg_identity = result.get("ffmpegIdentity")
    if (
        renderer_identity != GLYPH_REVEAL_RENDERER_IDENTITY_V2
        or renderer_version != GLYPH_REVEAL_RENDERER_VERSION_V2
        or not isinstance(ffmpeg_identity, str)
        or ffmpeg_identity != ffmpeg_identity.strip()
        or not 1 <= len(ffmpeg_identity) <= 500
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in ffmpeg_identity
        )
    ):
        raise RenderArtifactError("V3 glyph reveal v2 runtime identity is invalid")
    expected_runtime_digest = _runtime_evidence_digest_v2(
        ffmpeg_identity=ffmpeg_identity,
        renderer_identity=renderer_identity,
        renderer_version=renderer_version,
    )
    if result.get("runtimeEvidenceDigest") != expected_runtime_digest:
        raise RenderArtifactError("V3 glyph reveal v2 runtime evidence is invalid")
    return result


class V4CompositionExecutor:
    adapter_identity = "v4.local-composition-executor.v1"
    provenance = "LOCAL_EVIDENCE"

    def __init__(self, composer: DeterministicFfmpegComposer) -> None:
        self.composer = composer
        self.artifact_root = Path(composer.artifact_root).resolve()

    @classmethod
    def from_artifact_root(cls, artifact_root: Path | str) -> "V4CompositionExecutor":
        """Compose the V4 execution boundary without exposing V3 to V5 callers."""
        return cls(DeterministicFfmpegComposer(artifact_root))

    def compose(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = self.composer.compose(
                workspace_ref=command["workspaceRef"],
                run_ref=command["productionRunRef"],
                timeline_digest=command["timelineDigest"],
                items=command["items"],
                output=command["output"],
            )
        except (KeyError, TypeError, RenderArtifactError) as exc:
            raise CompositionExecutionError("V3 preview composition failed") from exc
        return {
            **result,
            "adapterIdentity": self.adapter_identity,
            "provenance": self.provenance,
            "gpuUsed": False,
            "publicationAllowed": False,
        }

    def compose_glyph_reveal(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Delegate one digest-pinned M13 glyph reveal to V3.

        AssetVersion resolution and semantic inspection stay in V5.  This bridge
        carries only the closed execution projection needed by the local render
        core and does not admit the resulting candidate.
        """

        request = _validate_glyph_reveal_request(command)
        try:
            result = self.composer.compose_glyph_reveal(
                workspace_ref=request["workspaceRef"],
                run_ref=request["productionRunRef"],
                requirement_digest=request["requirementDigest"],
                execution_request_digest=request["payloadDigest"],
                base_plate={
                    "storageKey": request["basePlate"]["storageKey"],
                    "fileDigest": request["basePlate"]["fileDigest"],
                },
                masks=[
                    {
                        "storageKey": mask["storageKey"],
                        "fileDigest": mask["fileDigest"],
                        "pixelDigest": mask["pixelDigest"],
                        "pixelDigestSpec": mask["pixelDigestSpec"],
                        "width": mask["width"],
                        "height": mask["height"],
                    }
                    for mask in request["masks"]
                ],
                frame_range_start=request["frameRangeStart"],
                frame_range_end=request["frameRangeEnd"],
                reveal_frame_count=request["revealFrameCount"],
                composite_params=request["compositeParams"],
                output=request["output"],
            )
            if (
                not isinstance(result, Mapping)
                or result.get("requirementDigest")
                != request["requirementDigest"]
                or result.get("executionRequestDigest")
                != request["payloadDigest"]
                or result.get("publicationAllowed") is not False
            ):
                raise RenderArtifactError(
                    "V3 glyph reveal artifact lineage is invalid"
                )
            evidence = _sealed(
                {
                    "schemaVersion": (
                        GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION
                    ),
                    "storageKey": result["storageKey"],
                    "byteSize": result["byteSize"],
                    "sha256": result["sha256"],
                    "probe": deepcopy(result["probe"]),
                    "outputDigest": deepcopy(result["outputDigest"]),
                    "composerIdentity": result["composerIdentity"],
                    "adapterIdentity": self.adapter_identity,
                    "runtimeIdentity": result["runtimeIdentity"],
                    "ffmpegVersion": result["ffmpegVersion"],
                    "ffprobeVersion": result["ffprobeVersion"],
                    "provenance": self.provenance,
                    "gpuUsed": False,
                    "publicationAllowed": False,
                    "requirementDigest": request["requirementDigest"],
                    "executionRequestDigest": request["payloadDigest"],
                }
            )
            if set(evidence) != _GLYPH_REVEAL_ARTIFACT_EVIDENCE_FIELDS:
                raise RenderArtifactError(
                    "V4 glyph reveal artifact evidence fields are invalid"
                )
            return evidence
        except (
            KeyError,
            TypeError,
            RenderArtifactError,
            CompositionRequestValidationError,
        ) as exc:
            raise CompositionExecutionError(
                "V3 glyph reveal composition failed"
            ) from exc

    def compose_glyph_reveal_v2(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Execute only the sealed, explicit-schedule M13 glyph v2 projection."""

        request = _validate_glyph_reveal_request_v2(command)
        try:
            raw_result = self.composer.compose_glyph_reveal_v2(
                workspace_ref=request["workspaceRef"],
                run_ref=request["productionRunRef"],
                requirement_ref=request["requirementRef"],
                requirement_digest=request["requirementDigest"],
                execution_request_ref=request["executionRequestRef"],
                execution_request_digest=request["payloadDigest"],
                base_plate={
                    "storageKey": request["basePlate"]["storageKey"],
                    "fileDigest": request["basePlate"]["fileDigest"],
                },
                masks=[
                    {
                        "assetVersionRef": mask["assetVersionRef"],
                        "revealOrdinal": mask["revealOrdinal"],
                        "storageKey": mask["storageKey"],
                        "fileDigest": mask["fileDigest"],
                        "pixelDigest": mask["pixelDigest"],
                        "pixelDigestSpec": mask["pixelDigestSpec"],
                        "width": mask["width"],
                        "height": mask["height"],
                    }
                    for mask in request["masks"]
                ],
                frame_range_start=request["frameRangeStartInclusive"],
                frame_range_end=request["frameRangeEndExclusive"],
                reveal_schedule=deepcopy(request["revealSchedule"]),
                composite_params=request["compositeParams"],
                output=request["output"],
            )
            result = _validate_v3_glyph_reveal_result_v2(
                raw_result,
                request=request,
            )
            output_digest = deepcopy(result["outputDigest"])
            artifact_evidence_ref = _artifact_evidence_ref_v2(
                execution_request_digest=request["payloadDigest"],
                file_digest=output_digest["fileDigest"],
            )
            evidence = _sealed(
                {
                    "schemaVersion": (
                        GLYPH_REVEAL_ARTIFACT_EVIDENCE_SCHEMA_VERSION_V2
                    ),
                    "artifactEvidenceRef": artifact_evidence_ref,
                    "outputStorageKey": result["outputStorageKey"],
                    "outputByteSize": result["outputByteSize"],
                    "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
                    "outputDigest": output_digest,
                    "rendererIdentity": result["rendererIdentity"],
                    "rendererVersion": result["rendererVersion"],
                    "ffmpegIdentity": result["ffmpegIdentity"],
                    "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
                    "provenance": self.provenance,
                    "gpuUsed": False,
                    "publicationAllowed": False,
                    "requirementRef": request["requirementRef"],
                    "requirementDigest": request["requirementDigest"],
                    "executionRequestRef": request["executionRequestRef"],
                    "executionRequestDigest": request["payloadDigest"],
                }
            )
            if set(evidence) != _GLYPH_REVEAL_ARTIFACT_EVIDENCE_FIELDS_V2:
                raise RenderArtifactError(
                    "V4 glyph reveal v2 artifact evidence fields are invalid"
                )
            return evidence
        except (
            AttributeError,
            KeyError,
            TypeError,
            RenderArtifactError,
            CompositionRequestValidationError,
        ) as exc:
            raise CompositionExecutionError(
                "V3 glyph reveal v2 composition failed"
            ) from exc

    def finalize(self, command: Mapping[str, Any]) -> dict[str, Any]:
        try:
            result = self.composer.finalize(
                workspace_ref=command["workspaceRef"],
                run_ref=command["productionRunRef"],
                preview_storage_key=command["previewStorageKey"],
                master_key=command["masterKey"],
            )
        except (KeyError, TypeError, RenderArtifactError) as exc:
            raise CompositionExecutionError("V3 master finalization failed") from exc
        return {
            **result,
            "adapterIdentity": self.adapter_identity,
            "provenance": self.provenance,
            "gpuUsed": False,
            "publicationAllowed": False,
        }
