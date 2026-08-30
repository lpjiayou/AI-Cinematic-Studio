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
    CANONICAL_PCM_CHANNEL_COUNT,
    CANONICAL_PCM_SAMPLE_RATE,
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DeterministicFfmpegComposer,
    DigestError,
    PCM_CONTENT_DIGEST_SPEC,
    RenderArtifactError,
    file_digest,
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
TIMELINE_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V1 = (
    "v4.m13-composition-execution-request.v1"
)
TIMELINE_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION_V1 = (
    "v4.m13-composition-result.v1"
)
TIMELINE_PREVIEW_RENDERER_IDENTITY_V1 = (
    "v3.deterministic-timeline-preview-ffmpeg"
)
TIMELINE_PREVIEW_RENDERER_VERSION_V1 = "1"
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
_TIMELINE_PREVIEW_COMMAND_FIELDS_V1 = frozenset(
    {
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "videoInput",
        "audioMix",
        "subtitleManifest",
        "output",
    }
)
_TIMELINE_PREVIEW_EXECUTION_REQUEST_FIELDS_V1 = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "videoInput",
        "audioMix",
        "subtitleManifest",
        "output",
        "publicationAllowed",
        "payloadDigest",
    }
)
_TIMELINE_PREVIEW_VIDEO_INPUT_FIELDS_V1 = frozenset(
    {
        "glyphRevealRequirementRef",
        "glyphRevealRequirementDigest",
        "glyphRevealExecutionRequestRef",
        "glyphRevealExecutionRequestDigest",
        "glyphRevealArtifactEvidenceRef",
        "glyphRevealArtifactEvidenceDigest",
        "storageKey",
        "fileDigest",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "codec",
        "pixelFormat",
        "width",
        "height",
        "frameCount",
        "frameRate",
    }
)
_TIMELINE_PREVIEW_AUDIO_MIX_FIELDS_V1 = frozenset(
    {
        "mixRequestRef",
        "mixRequestDigest",
        "timelineVersionRef",
        "timelineVersionDigest",
        "stemSetVersionRef",
        "stemSetDigest",
        "sampleRate",
        "channelCount",
        "durationSamples",
        "roundingRule",
        "mixParameters",
        "mixParametersDigest",
        "clips",
    }
)
_TIMELINE_PREVIEW_AUDIO_CLIP_FIELDS_V1 = frozenset(
    {
        "clipRef",
        "clipDigest",
        "stemMemberRef",
        "stemMemberDigest",
        "audioRole",
        "assetVersionRef",
        "assetVersionType",
        "assetVersionDigest",
        "technicalValidationRef",
        "technicalValidationDigest",
        "storageKey",
        "fileDigest",
        "pcmContentDigest",
        "sampleRate",
        "sourceChannelCount",
        "sourceSampleCount",
        "sourceStartSample",
        "sourceEndSampleExclusive",
        "timelineStartFrame",
        "timelineEndFrameExclusive",
        "timelineStartSample",
        "timelineEndSampleExclusive",
        "gainDb",
        "fadeInSamples",
        "fadeOutSamples",
    }
)
_TIMELINE_PREVIEW_OUTPUT_FIELDS_V1 = frozenset(
    {
        "width",
        "height",
        "frameRate",
        "totalFrames",
        "sampleRate",
        "channelCount",
        "durationSamples",
        "container",
        "videoCodec",
        "pixelFormat",
        "audioCodec",
        "audioBitRate",
    }
)
_TIMELINE_PREVIEW_OUTPUT_DIGEST_FIELDS_V1 = frozenset(
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
_TIMELINE_PREVIEW_OUTPUT_MEDIA_PROBE_FIELDS_V1 = frozenset(
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
_V3_TIMELINE_PREVIEW_RESULT_FIELDS_V1 = frozenset(
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
        "subtitleManifestRef",
        "subtitleManifestDigest",
        "publicationAllowed",
    }
)
_TIMELINE_PREVIEW_RESULT_FIELDS_V1 = frozenset(
    {
        "schemaVersion",
        "compositionResultRef",
        "artifactRef",
        "executionRequestRef",
        "executionRequestDigest",
        "timelineVersionRef",
        "timelineVersionDigest",
        "inputBindingsDigest",
        "outputStorageKey",
        "outputByteSize",
        "outputMediaProbe",
        "outputDigest",
        "subtitleManifestRef",
        "subtitleManifestDigest",
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
_TIMELINE_PREVIEW_ROLE_PRIORITY = {
    "dialogue": 3,
    "narration": 3,
    "sfx": 2,
    "ambience": 1,
    "music": 0,
}
_TIMELINE_PREVIEW_ROLE_GAIN_DB = {
    "dialogue": 0,
    "narration": 0,
    "sfx": -6,
    "ambience": -12,
    "music": -18,
}
_TIMELINE_PREVIEW_DUCKING = {
    "threshold": "0.125",
    "ratio": "8",
    "attackMilliseconds": 5,
    "releaseMilliseconds": 180,
    "makeup": "1",
    "knee": "2",
    "link": "maximum",
    "detection": "rms",
    "levelSc": "1",
    "mix": "1",
}
_TIMELINE_PREVIEW_LIMITER = {
    "limit": "0.95",
    "attackMilliseconds": 5,
    "releaseMilliseconds": 50,
    "level": False,
    "latency": True,
}


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


def _timeline_preview_frame_rate_v1(value: Any, field: str) -> tuple[int, int]:
    record = _closed_mapping(value, {"numerator", "denominator"}, field)
    numerator = _integer(
        record["numerator"], f"{field}.numerator", minimum=1, maximum=1_000_000
    )
    denominator = _integer(
        record["denominator"],
        f"{field}.denominator",
        minimum=1,
        maximum=1_000_000,
    )
    from fractions import Fraction

    reduced = Fraction(numerator, denominator)
    if reduced.numerator != numerator or reduced.denominator != denominator:
        raise CompositionRequestValidationError(f"{field} must be reduced")
    return numerator, denominator


def _timeline_preview_frame_to_sample_v1(
    frame: int, frame_rate: tuple[int, int]
) -> int:
    numerator, denominator = frame_rate
    return frame * CANONICAL_PCM_SAMPLE_RATE * denominator // numerator


def _timeline_preview_mix_parameters_v1() -> dict[str, Any]:
    return {
        "rolePriority": deepcopy(_TIMELINE_PREVIEW_ROLE_PRIORITY),
        "roleGainDb": deepcopy(_TIMELINE_PREVIEW_ROLE_GAIN_DB),
        "ducking": deepcopy(_TIMELINE_PREVIEW_DUCKING),
        "limiter": deepcopy(_TIMELINE_PREVIEW_LIMITER),
    }


def _seal_timeline_preview_v1(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise CompositionRequestValidationError(
            "timeline preview record cannot predeclare payloadDigest"
        )
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return result


def _build_timeline_preview_execution_request_v1(
    value: Any,
) -> dict[str, Any]:
    command = _closed_mapping(
        value,
        set(_TIMELINE_PREVIEW_COMMAND_FIELDS_V1),
        "timeline preview command",
    )
    for field in (
        "workspaceRef",
        "productionRunRef",
        "timelineVersionRef",
    ):
        _ref(command[field], field)
    _raw_digest(command["timelineVersionDigest"], "timelineVersionDigest")

    video = _closed_mapping(
        command["videoInput"],
        set(_TIMELINE_PREVIEW_VIDEO_INPUT_FIELDS_V1),
        "videoInput",
    )
    for field in (
        "glyphRevealRequirementRef",
        "glyphRevealExecutionRequestRef",
        "glyphRevealArtifactEvidenceRef",
    ):
        _ref(video[field], f"videoInput.{field}")
    for field in (
        "glyphRevealRequirementDigest",
        "glyphRevealExecutionRequestDigest",
        "glyphRevealArtifactEvidenceDigest",
    ):
        _raw_digest(video[field], f"videoInput.{field}")
    _storage_key_v2(video["storageKey"], "videoInput.storageKey")
    _prefixed_digest(video["fileDigest"], "videoInput.fileDigest")
    _prefixed_digest(
        video["decodedFramePixelDigest"],
        "videoInput.decodedFramePixelDigest",
    )
    if (
        video["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or video["codec"] != "h264"
        or video["pixelFormat"] not in {"yuv420p", "yuv422p", "yuv444p"}
    ):
        raise CompositionRequestValidationError("videoInput content is invalid")
    video_width = _integer(
        video["width"], "videoInput.width", minimum=1, maximum=131_072
    )
    video_height = _integer(
        video["height"], "videoInput.height", minimum=1, maximum=131_072
    )
    video_frames = _integer(
        video["frameCount"],
        "videoInput.frameCount",
        minimum=1,
        maximum=10_000_000,
    )
    video_rate = _timeline_preview_frame_rate_v1(
        video["frameRate"], "videoInput.frameRate"
    )
    if video_rate[1] != 1:
        raise CompositionRequestValidationError(
            "timeline preview vertical slice requires integral frameRate"
        )

    output = _closed_mapping(
        command["output"],
        set(_TIMELINE_PREVIEW_OUTPUT_FIELDS_V1),
        "output",
    )
    output_rate = _timeline_preview_frame_rate_v1(
        output["frameRate"], "output.frameRate"
    )
    output_width = _integer(
        output["width"], "output.width", minimum=1, maximum=131_072
    )
    output_height = _integer(
        output["height"], "output.height", minimum=1, maximum=131_072
    )
    total_frames = _integer(
        output["totalFrames"],
        "output.totalFrames",
        minimum=1,
        maximum=10_000_000,
    )
    duration_samples = _integer(
        output["durationSamples"],
        "output.durationSamples",
        minimum=1,
        maximum=28_800_000,
    )
    output_sample_rate = _integer(
        output["sampleRate"],
        "output.sampleRate",
        minimum=1,
        maximum=384_000,
    )
    output_channel_count = _integer(
        output["channelCount"],
        "output.channelCount",
        minimum=1,
        maximum=8,
    )
    output_audio_bit_rate = _integer(
        output["audioBitRate"],
        "output.audioBitRate",
        minimum=1,
        maximum=10_000_000,
    )
    if (
        output_width != video_width
        or output_height != video_height
        or output["totalFrames"] != video_frames
        or output_rate != video_rate
        or output_sample_rate != CANONICAL_PCM_SAMPLE_RATE
        or output_channel_count != CANONICAL_PCM_CHANNEL_COUNT
        or duration_samples
        != _timeline_preview_frame_to_sample_v1(total_frames, output_rate)
        or output["container"] != "mp4"
        or output["videoCodec"] != "h264"
        or output["pixelFormat"] != video["pixelFormat"]
        or output["audioCodec"] != "aac"
        or output_audio_bit_rate != 128_000
    ):
        raise CompositionRequestValidationError("output contract is invalid")

    subtitle = _closed_mapping(
        command["subtitleManifest"],
        {"subtitleManifestRef", "subtitleManifestDigest"},
        "subtitleManifest",
    )
    _ref(subtitle["subtitleManifestRef"], "subtitleManifestRef")
    _raw_digest(subtitle["subtitleManifestDigest"], "subtitleManifestDigest")

    audio_mix = _closed_mapping(
        command["audioMix"],
        set(_TIMELINE_PREVIEW_AUDIO_MIX_FIELDS_V1),
        "audioMix",
    )
    for field in ("mixRequestRef", "timelineVersionRef", "stemSetVersionRef"):
        _ref(audio_mix[field], f"audioMix.{field}")
    for field in (
        "mixRequestDigest",
        "timelineVersionDigest",
        "stemSetDigest",
        "mixParametersDigest",
    ):
        _raw_digest(audio_mix[field], f"audioMix.{field}")
    mix_parameters = _timeline_preview_mix_parameters_v1()
    mix_sample_rate = _integer(
        audio_mix["sampleRate"],
        "audioMix.sampleRate",
        minimum=1,
        maximum=384_000,
    )
    mix_channel_count = _integer(
        audio_mix["channelCount"],
        "audioMix.channelCount",
        minimum=1,
        maximum=8,
    )
    mix_duration_samples = _integer(
        audio_mix["durationSamples"],
        "audioMix.durationSamples",
        minimum=1,
        maximum=28_800_000,
    )
    if (
        audio_mix["timelineVersionRef"] != command["timelineVersionRef"]
        or audio_mix["timelineVersionDigest"] != command["timelineVersionDigest"]
        or mix_sample_rate != CANONICAL_PCM_SAMPLE_RATE
        or mix_channel_count != CANONICAL_PCM_CHANNEL_COUNT
        or mix_duration_samples != duration_samples
        or audio_mix["roundingRule"] != "FLOOR_EACH_BOUNDARY"
        or audio_mix["mixParameters"] != mix_parameters
        or audio_mix["mixParametersDigest"]
        != sha256(_canonical_json(mix_parameters)).hexdigest()
    ):
        raise CompositionRequestValidationError("audioMix contract is invalid")
    clips = audio_mix["clips"]
    if not isinstance(clips, list) or not clips or len(clips) > 64:
        raise CompositionRequestValidationError("audioMix.clips is invalid")
    role_types = {
        "dialogue": "DialogueAssetVersion",
        "narration": "DialogueAssetVersion",
        "sfx": "SfxAssetVersion",
        "ambience": "AmbienceAssetVersion",
        "music": "MusicAssetVersion",
    }
    seen_clip_refs: set[str] = set()
    seen_stem_refs: set[str] = set()
    normalized_clips: list[dict[str, Any]] = []
    for index, raw_clip in enumerate(clips):
        clip = _closed_mapping(
            raw_clip,
            set(_TIMELINE_PREVIEW_AUDIO_CLIP_FIELDS_V1),
            f"audioMix.clips[{index}]",
        )
        clip_ref = _ref(clip["clipRef"], f"audioMix.clips[{index}].clipRef")
        stem_ref = _ref(
            clip["stemMemberRef"], f"audioMix.clips[{index}].stemMemberRef"
        )
        if clip_ref in seen_clip_refs or stem_ref in seen_stem_refs:
            raise CompositionRequestValidationError("audioMix clip is duplicated")
        seen_clip_refs.add(clip_ref)
        seen_stem_refs.add(stem_ref)
        for field in ("assetVersionRef", "technicalValidationRef"):
            _ref(clip[field], f"audioMix.clips[{index}].{field}")
        for field in (
            "clipDigest",
            "stemMemberDigest",
            "assetVersionDigest",
            "technicalValidationDigest",
            "fileDigest",
            "pcmContentDigest",
        ):
            _raw_digest(clip[field], f"audioMix.clips[{index}].{field}")
        _storage_key_v2(
            clip["storageKey"], f"audioMix.clips[{index}].storageKey"
        )
        role = clip["audioRole"]
        clip_sample_rate = _integer(
            clip["sampleRate"],
            f"audioMix.clips[{index}].sampleRate",
            minimum=1,
            maximum=384_000,
        )
        source_channel_count = _integer(
            clip["sourceChannelCount"],
            f"audioMix.clips[{index}].sourceChannelCount",
            minimum=1,
            maximum=8,
        )
        if (
            role not in role_types
            or clip["assetVersionType"] != role_types[role]
            or clip_sample_rate != CANONICAL_PCM_SAMPLE_RATE
            or source_channel_count not in {1, 2}
        ):
            raise CompositionRequestValidationError(
                "audioMix clip role or source format is invalid"
            )
        source_count = _integer(
            clip["sourceSampleCount"],
            f"audioMix.clips[{index}].sourceSampleCount",
            minimum=1,
            maximum=28_800_000,
        )
        source_start = _integer(
            clip["sourceStartSample"],
            f"audioMix.clips[{index}].sourceStartSample",
            minimum=0,
            maximum=28_799_999,
        )
        source_end = _integer(
            clip["sourceEndSampleExclusive"],
            f"audioMix.clips[{index}].sourceEndSampleExclusive",
            minimum=1,
            maximum=28_800_000,
        )
        timeline_start_frame = _integer(
            clip["timelineStartFrame"],
            f"audioMix.clips[{index}].timelineStartFrame",
            minimum=0,
            maximum=total_frames - 1,
        )
        timeline_end_frame = _integer(
            clip["timelineEndFrameExclusive"],
            f"audioMix.clips[{index}].timelineEndFrameExclusive",
            minimum=1,
            maximum=total_frames,
        )
        timeline_start_sample = _integer(
            clip["timelineStartSample"],
            f"audioMix.clips[{index}].timelineStartSample",
            minimum=0,
            maximum=duration_samples - 1,
        )
        timeline_end_sample = _integer(
            clip["timelineEndSampleExclusive"],
            f"audioMix.clips[{index}].timelineEndSampleExclusive",
            minimum=1,
            maximum=duration_samples,
        )
        gain = clip["gainDb"]
        if isinstance(gain, bool) or not isinstance(gain, int) or not -96 <= gain <= 24:
            raise CompositionRequestValidationError(
                f"audioMix.clips[{index}].gainDb is invalid"
            )
        fade_in = _integer(
            clip["fadeInSamples"],
            f"audioMix.clips[{index}].fadeInSamples",
            minimum=0,
            maximum=28_800_000,
        )
        fade_out = _integer(
            clip["fadeOutSamples"],
            f"audioMix.clips[{index}].fadeOutSamples",
            minimum=0,
            maximum=28_800_000,
        )
        source_span = source_end - source_start
        timeline_span = timeline_end_sample - timeline_start_sample
        if (
            source_start >= source_end
            or source_end > source_count
            or timeline_start_frame >= timeline_end_frame
            or timeline_start_sample
            != _timeline_preview_frame_to_sample_v1(
                timeline_start_frame, output_rate
            )
            or timeline_end_sample
            != _timeline_preview_frame_to_sample_v1(
                timeline_end_frame, output_rate
            )
            or source_span != timeline_span
            or fade_in + fade_out > source_span
        ):
            raise CompositionRequestValidationError(
                "audioMix clip timing is invalid"
            )
        normalized_clips.append(clip)
    if clips != sorted(
        normalized_clips,
        key=lambda item: (
            -_TIMELINE_PREVIEW_ROLE_PRIORITY[item["audioRole"]],
            item["clipRef"],
        ),
    ):
        raise CompositionRequestValidationError("audioMix.clips is not canonical")

    input_bindings_digest = sha256(
        _canonical_json(
            {
                "videoInput": video,
                "audioMix": audio_mix,
                "subtitleManifest": subtitle,
            }
        )
    ).hexdigest()
    output_contract_digest = sha256(_canonical_json(output)).hexdigest()
    execution_request_ref = "m13-composition-execution-" + sha256(
        _canonical_json(
            {
                "timelineVersionRef": command["timelineVersionRef"],
                "timelineVersionDigest": command["timelineVersionDigest"],
                "inputBindingsDigest": input_bindings_digest,
                "outputContractDigest": output_contract_digest,
            }
        )
    ).hexdigest()[:32]
    request = _seal_timeline_preview_v1(
        {
            "schemaVersion": TIMELINE_PREVIEW_EXECUTION_REQUEST_SCHEMA_VERSION_V1,
            "executionRequestRef": execution_request_ref,
            "workspaceRef": command["workspaceRef"],
            "productionRunRef": command["productionRunRef"],
            "timelineVersionRef": command["timelineVersionRef"],
            "timelineVersionDigest": command["timelineVersionDigest"],
            "inputBindingsDigest": input_bindings_digest,
            "videoInput": video,
            "audioMix": audio_mix,
            "subtitleManifest": subtitle,
            "output": output,
            "publicationAllowed": False,
        }
    )
    if set(request) != _TIMELINE_PREVIEW_EXECUTION_REQUEST_FIELDS_V1:
        raise CompositionRequestValidationError(
            "timeline preview execution request fields are invalid"
        )
    return request


def _expected_timeline_preview_storage_key_v1(
    request: Mapping[str, Any],
) -> str:
    workspace_hash = sha256(
        str(request["workspaceRef"]).encode("utf-8")
    ).hexdigest()[:20]
    run_hash = sha256(
        str(request["productionRunRef"]).encode("utf-8")
    ).hexdigest()[:20]
    return (
        f"{workspace_hash}/{run_hash}/composition/"
        f"preview-{request['payloadDigest']}.mp4"
    )


def _validate_v3_timeline_preview_result_v1(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    result = _closed_mapping(
        value,
        set(_V3_TIMELINE_PREVIEW_RESULT_FIELDS_V1),
        "V3 timeline preview result",
    )
    expected_storage_key = _expected_timeline_preview_storage_key_v1(request)
    if (
        _storage_key_v2(result["outputStorageKey"], "outputStorageKey")
        != expected_storage_key
        or result["executionRequestRef"] != request["executionRequestRef"]
        or result["executionRequestDigest"] != request["payloadDigest"]
        or result["timelineVersionRef"] != request["timelineVersionRef"]
        or result["timelineVersionDigest"] != request["timelineVersionDigest"]
        or result["inputBindingsDigest"] != request["inputBindingsDigest"]
        or result["subtitleManifestRef"]
        != request["subtitleManifest"]["subtitleManifestRef"]
        or result["subtitleManifestDigest"]
        != request["subtitleManifest"]["subtitleManifestDigest"]
        or result["publicationAllowed"] is not False
    ):
        raise RenderArtifactError("V3 timeline preview lineage is invalid")
    _integer(
        result["outputByteSize"],
        "outputByteSize",
        minimum=1,
        maximum=10**12,
    )
    internal_path = result.get("internalPath")
    if not isinstance(internal_path, str) or not internal_path:
        raise RenderArtifactError("V3 timeline preview internal path is invalid")
    try:
        actual_path = Path(internal_path).resolve(strict=True)
        expected_path = (artifact_root / expected_storage_key).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RenderArtifactError(
            "V3 timeline preview artifact is unavailable"
        ) from exc
    if actual_path != expected_path or artifact_root not in actual_path.parents:
        raise RenderArtifactError("V3 timeline preview path lineage is invalid")
    try:
        before_hash = actual_path.stat()
        actual_file_digest = file_digest(actual_path)
        after_hash = actual_path.stat()
        identity_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            before_hash.st_size != result["outputByteSize"]
            or any(
                getattr(before_hash, field) != getattr(after_hash, field)
                for field in identity_fields
            )
        ):
            raise RenderArtifactError("V3 timeline preview byte size is invalid")
    except (OSError, DigestError) as exc:
        raise RenderArtifactError(
            "V3 timeline preview artifact is unavailable"
        ) from exc

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
    output_probe = _closed_mapping(
        result["outputMediaProbe"],
        set(_TIMELINE_PREVIEW_OUTPUT_MEDIA_PROBE_FIELDS_V1),
        "outputMediaProbe",
    )
    if output_probe != expected_probe:
        raise RenderArtifactError(
            "V3 timeline preview output media contract is invalid"
        )
    output_digest = _closed_mapping(
        result["outputDigest"],
        set(_TIMELINE_PREVIEW_OUTPUT_DIGEST_FIELDS_V1),
        "outputDigest",
    )
    _prefixed_digest(output_digest["fileDigest"], "outputDigest.fileDigest")
    _prefixed_digest(
        output_digest["decodedFramePixelDigest"],
        "outputDigest.decodedFramePixelDigest",
    )
    _raw_digest(
        output_digest["pcmContentDigest"],
        "outputDigest.pcmContentDigest",
    )
    if (
        output_digest["fileDigest"] != actual_file_digest
        or
        output_digest["fileDigestAlgorithm"] != "sha256"
        or output_digest["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or output_digest["pixelMode"] != "RGBA"
        or output_digest["decodedFramePixelDigest"]
        != request["videoInput"]["decodedFramePixelDigest"]
        or output_digest["width"] != output["width"]
        or output_digest["height"] != output["height"]
        or output_digest["frameCount"] != output["totalFrames"]
        or output_digest["frameRate"] != output["frameRate"]
        or output_digest["pcmDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
        or output_digest["sampleRate"] != output["sampleRate"]
        or output_digest["channelCount"] != output["channelCount"]
        or output_digest["sampleCount"] != output["durationSamples"]
    ):
        raise RenderArtifactError("V3 timeline preview output digest is invalid")
    renderer_identity = result.get("rendererIdentity")
    renderer_version = result.get("rendererVersion")
    ffmpeg_identity = result.get("ffmpegIdentity")
    if (
        renderer_identity != TIMELINE_PREVIEW_RENDERER_IDENTITY_V1
        or renderer_version != TIMELINE_PREVIEW_RENDERER_VERSION_V1
        or not isinstance(ffmpeg_identity, str)
        or ffmpeg_identity != ffmpeg_identity.strip()
        or not 1 <= len(ffmpeg_identity) <= 500
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in ffmpeg_identity
        )
    ):
        raise RenderArtifactError("V3 timeline preview runtime identity is invalid")
    expected_runtime_digest = _runtime_evidence_digest_v2(
        ffmpeg_identity=ffmpeg_identity,
        renderer_identity=renderer_identity,
        renderer_version=renderer_version,
    )
    if result["runtimeEvidenceDigest"] != expected_runtime_digest:
        raise RenderArtifactError("V3 timeline preview runtime evidence is invalid")
    return result


def _timeline_preview_artifact_ref_v1(
    *,
    execution_request_digest: str,
    file_digest: str,
    pixel_digest: str,
    pcm_digest: str,
) -> str:
    semantic = {
        "executionRequestDigest": execution_request_digest,
        "fileDigest": file_digest,
        "decodedFramePixelDigest": pixel_digest,
        "pcmContentDigest": pcm_digest,
    }
    return "m13-preview-artifact-" + sha256(
        _canonical_json(semantic)
    ).hexdigest()[:32]


def _timeline_preview_result_ref_v1(
    *, execution_request_digest: str, artifact_ref: str
) -> str:
    return "m13-composition-result-" + sha256(
        _canonical_json(
            {
                "executionRequestDigest": execution_request_digest,
                "artifactRef": artifact_ref,
            }
        )
    ).hexdigest()[:32]


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

    def compose_timeline_preview_v1(
        self, command: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Seal and execute one non-GPU M12-to-M13 preview projection."""

        request = _build_timeline_preview_execution_request_v1(command)
        try:
            raw_result = self.composer.compose_timeline_preview_v1(request)
            result = _validate_v3_timeline_preview_result_v1(
                raw_result,
                request=request,
                artifact_root=self.artifact_root,
            )
            output_digest = deepcopy(result["outputDigest"])
            artifact_ref = _timeline_preview_artifact_ref_v1(
                execution_request_digest=request["payloadDigest"],
                file_digest=output_digest["fileDigest"],
                pixel_digest=output_digest["decodedFramePixelDigest"],
                pcm_digest=output_digest["pcmContentDigest"],
            )
            composition_result_ref = _timeline_preview_result_ref_v1(
                execution_request_digest=request["payloadDigest"],
                artifact_ref=artifact_ref,
            )
            sealed = _seal_timeline_preview_v1(
                {
                    "schemaVersion": (
                        TIMELINE_PREVIEW_COMPOSITION_RESULT_SCHEMA_VERSION_V1
                    ),
                    "compositionResultRef": composition_result_ref,
                    "artifactRef": artifact_ref,
                    "executionRequestRef": request["executionRequestRef"],
                    "executionRequestDigest": request["payloadDigest"],
                    "timelineVersionRef": request["timelineVersionRef"],
                    "timelineVersionDigest": request["timelineVersionDigest"],
                    "inputBindingsDigest": request["inputBindingsDigest"],
                    "outputStorageKey": result["outputStorageKey"],
                    "outputByteSize": result["outputByteSize"],
                    "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
                    "outputDigest": output_digest,
                    "subtitleManifestRef": result["subtitleManifestRef"],
                    "subtitleManifestDigest": result[
                        "subtitleManifestDigest"
                    ],
                    "rendererIdentity": result["rendererIdentity"],
                    "rendererVersion": result["rendererVersion"],
                    "ffmpegIdentity": result["ffmpegIdentity"],
                    "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
                    "adapterIdentity": self.adapter_identity,
                    "provenance": self.provenance,
                    "providerUsed": False,
                    "gpuUsed": False,
                    "publicationAllowed": False,
                }
            )
            if set(sealed) != _TIMELINE_PREVIEW_RESULT_FIELDS_V1:
                raise RenderArtifactError(
                    "V4 timeline preview result fields are invalid"
                )
            return sealed
        except (
            AttributeError,
            KeyError,
            TypeError,
            RenderArtifactError,
            CompositionRequestValidationError,
        ) as exc:
            raise CompositionExecutionError(
                "V3 timeline preview composition failed"
            ) from exc

    def compose_timeline_preview_v2(
        self,
        command: Mapping[str, Any],
        *,
        resolved_artifacts: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Delegate the additive effect Preview through the same V4 owner."""

        from services.v3_render_core.masked_surface import (
            DeterministicMaskedSurfaceExecutor,
        )
        from .masked_surface_effects import (
            MaskedSurfaceExecutionError,
            V4MaskedSurfaceEffectExecutor,
        )

        try:
            executor = V4MaskedSurfaceEffectExecutor(
                self.artifact_root,
                DeterministicMaskedSurfaceExecutor(self.artifact_root),
            )
            return executor.compose_timeline_preview_v2(
                command,
                resolved_artifacts=resolved_artifacts,
            )
        except MaskedSurfaceExecutionError as exc:
            raise CompositionExecutionError(
                "V3 effect timeline preview composition failed"
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
