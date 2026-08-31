"""Closed V4 orchestration for M13-E4 distance/state rendering.

V5 owns the immutable Requirement/Result chain.  This module accepts only the
path-free V5 execution projection, re-resolves and physically measures the
exact server-held AssetVersions, derives one sealed V3 request, and converts
the V3 result into the existing runtime/artifact evidence trio.  It owns no
Timeline, motion, visual-state, or AssetVersion authority.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping

from services.v3_render_core.composition import (
    RenderArtifactError,
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
)
from services.v3_render_core.digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    IMAGE_PIXEL_DIGEST_SPEC,
    DigestError,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)


DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION = (
    "v5.m13-distance-state-execution-request.v1"
)
DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION = (
    "v4.m13-distance-state-execution-request.v1"
)
DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-distance-state-runtime-evidence.v1"
)
DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION = (
    "v4.m13-distance-state-artifact-evidence.v1"
)
DISTANCE_STATE_RENDERER_IDENTITY = "v3.deterministic-distance-state-ffmpeg"
DISTANCE_STATE_RENDERER_VERSION = "1"
DISTANCE_STATE_PROVENANCE = "LOCAL_EVIDENCE"
DISTANCE_STATE_TRANSITION = "DISTANCE_STATE_TRANSITION"

_RAW = re.compile(r"[0-9a-f]{64}\Z")
_CONTENT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")

_BASE_FIELDS = frozenset(
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
_IMAGE_FIELDS = frozenset(
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
_PREVIEW_BINDING_FIELDS = frozenset(
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
_PREVIEW_RESOLUTION_FIELDS = frozenset(
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
_PREVIEW_ARTIFACT_STORAGE_FIELDS = frozenset(
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
_RUNTIME_FIELDS = frozenset(
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
        "executionManifestDigest",
        "gpuUsed",
        "publicationAllowed",
        "payloadDigest",
    }
)
_ARTIFACT_FIELDS = frozenset(
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
        "derivedDistanceFacts",
        "appliedStateScheduleDigest",
        "runtimeEvidenceRef",
        "runtimeEvidenceDigest",
        "provenance",
        "publicationAllowed",
        "payloadDigest",
    }
)
_BINDING_FIELDS = frozenset(
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
        "executionManifestDigest",
        "runtimeEvidenceDigest",
        "v5ExecutionRequestRef",
        "v5ExecutionRequestDigest",
        "v3ExecutionRequestDigest",
        "requirementRef",
        "requirementDigest",
        "effectMode",
        "derivedDistanceFacts",
        "appliedStateScheduleDigest",
        "publicationAllowed",
    }
)


class DistanceStateExecutionError(RuntimeError):
    """The V4/V3 deterministic distance-state boundary failed."""


class DistanceStateRequestValidationError(DistanceStateExecutionError):
    """The V5 request is malformed, open, or stale."""


class DistanceStateAssetResolutionError(DistanceStateExecutionError):
    """A resolved current AssetVersion or stored artifact is stale."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DistanceStateRequestValidationError(
            "distance/state value is not canonical JSON"
        ) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise DistanceStateRequestValidationError("payloadDigest is derived")
    result["payloadDigest"] = sha256(_canonical(result)).hexdigest()
    return result


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DistanceStateRequestValidationError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _raw(value: Any, label: str) -> str:
    if not isinstance(value, str) or _RAW.fullmatch(value) is None:
        raise DistanceStateRequestValidationError(f"{label} is invalid")
    return value


def _content(value: Any, label: str) -> str:
    if not isinstance(value, str) or _CONTENT.fullmatch(value) is None:
        raise DistanceStateRequestValidationError(f"{label} is invalid")
    return value


def _ref(value: Any, label: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise DistanceStateRequestValidationError(f"{label} is invalid")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise DistanceStateRequestValidationError(f"{label} is invalid")
    return value


def _storage_key(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise DistanceStateAssetResolutionError(f"{label} is invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise DistanceStateAssetResolutionError(f"{label} is invalid")
    return value


def _server_file(root: Path, storage_key: Any, *, label: str) -> Path:
    key = _storage_key(storage_key, f"{label}.storageKey")
    current = root
    try:
        for part in PurePosixPath(key).parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise DistanceStateAssetResolutionError(
                    f"{label} storage contains a symlink"
                )
        metadata = os.stat(current, follow_symlinks=False)
        resolved = current.resolve(strict=True)
    except DistanceStateAssetResolutionError:
        raise
    except OSError as exc:
        raise DistanceStateAssetResolutionError(
            f"{label} storage is unavailable"
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or root not in resolved.parents
    ):
        raise DistanceStateAssetResolutionError(f"{label} storage is invalid")
    return resolved


def validate_distance_state_execution_request(value: Any) -> dict[str, Any]:
    """Validate through the one V5 contract implementation."""

    try:
        from services.v5_core_os.episode_production.distance_state import (
            DistanceStateExecutionRequest,
        )

        request = DistanceStateExecutionRequest.from_mapping(value).as_dict()
    except Exception as exc:
        raise DistanceStateRequestValidationError(
            "distance/state V5 execution request is invalid"
        ) from exc
    if (
        request.get("schemaVersion")
        != DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION
        or request.get("effectMode") != DISTANCE_STATE_TRANSITION
        or request.get("publicationAllowed") is not False
    ):
        raise DistanceStateRequestValidationError(
            "distance/state execution boundary is invalid"
        )
    return request


def _resolved_base(value: Any) -> dict[str, Any]:
    record = _closed(value, _BASE_FIELDS, "resolved basePlate")
    _ref(record["assetVersionRef"], "basePlate.assetVersionRef")
    _raw(record["assetVersionDigest"], "basePlate.assetVersionDigest")
    _storage_key(record["storageKey"], "basePlate.storageKey")
    _content(record["fileDigest"], "basePlate.fileDigest")
    _content(record["pixelDigest"], "basePlate.pixelDigest")
    width = _integer(record["width"], "basePlate.width", 2, 16_384)
    height = _integer(record["height"], "basePlate.height", 2, 16_384)
    _integer(record["frameCount"], "basePlate.frameCount", 1, 10_000_000)
    _integer(record["frameRate"], "basePlate.frameRate", 1, 240)
    if (
        width % 2
        or height % 2
        or record["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or record["pixelFormat"] != "yuv420p"
    ):
        raise DistanceStateAssetResolutionError(
            "basePlate media contract is unsupported"
        )
    return record


def _resolved_image(value: Any, label: str) -> dict[str, Any]:
    record = _closed(value, _IMAGE_FIELDS, label)
    _ref(record["assetVersionRef"], f"{label}.assetVersionRef")
    _raw(record["assetVersionDigest"], f"{label}.assetVersionDigest")
    _storage_key(record["storageKey"], f"{label}.storageKey")
    _content(record["fileDigest"], f"{label}.fileDigest")
    _content(record["pixelDigest"], f"{label}.pixelDigest")
    _integer(record["width"], f"{label}.width", 1, 16_384)
    _integer(record["height"], f"{label}.height", 1, 16_384)
    if (
        record["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC
        or record["pixelMode"] != "RGBA"
    ):
        raise DistanceStateAssetResolutionError(f"{label} must be canonical RGBA PNG")
    return record


def _measure_base(root: Path, base: Mapping[str, Any]) -> None:
    from services.v3_render_core.masked_surface import _probe_video

    path = _server_file(root, base["storageKey"], label="basePlate")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise DistanceStateExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        with (
            _PinnedRegularFile(path, label="distance/state basePlate") as pinned,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            pass_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            if file_digest(pinned.descriptor_path) != base["fileDigest"]:
                raise DistanceStateAssetResolutionError("basePlate file digest is stale")
            probe = _probe_video(
                pinned.descriptor_path,
                SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                ),
            )
            pixels = decoded_frame_pixel_digest_metadata(
                pinned.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            pinned.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
    except DistanceStateAssetResolutionError:
        raise
    except (DigestError, RenderArtifactError, OSError) as exc:
        raise DistanceStateAssetResolutionError("basePlate could not be measured") from exc
    if (
        probe["width"] != base["width"]
        or probe["height"] != base["height"]
        or probe["frameCount"] != base["frameCount"]
        or probe["frameRate"].denominator != 1
        or probe["frameRate"].numerator != base["frameRate"]
        or probe["realFrameRate"] != probe["frameRate"]
        or probe["startTime"] != 0
        or probe["duration"] != probe["frameCount"] / probe["frameRate"]
        or probe["pixelFormat"] != "yuv420p"
        or pixels.get("fileDigest") != base["fileDigest"]
        or pixels.get("decodedFramePixelDigest") != base["pixelDigest"]
        or pixels.get("decodedFramePixelDigestSpec") != base["pixelDigestSpec"]
        or pixels.get("width") != base["width"]
        or pixels.get("height") != base["height"]
        or pixels.get("frameCount") != base["frameCount"]
    ):
        raise DistanceStateAssetResolutionError("basePlate media facts are stale")


def _measure_image(root: Path, image: Mapping[str, Any], label: str) -> None:
    path = _server_file(root, image["storageKey"], label=label)
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise DistanceStateExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        with (
            _PinnedRegularFile(path, label=label) as pinned,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            pass_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            if file_digest(pinned.descriptor_path) != image["fileDigest"]:
                raise DistanceStateAssetResolutionError(f"{label} file digest is stale")
            with tempfile.TemporaryDirectory(
                prefix=".held-distance-image-", dir=root
            ) as alias_root:
                alias = Path(alias_root) / "held.png"
                os.symlink(pinned.descriptor_path, alias)
                measured = image_digest_metadata(
                    alias,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
            pinned.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
    except DistanceStateAssetResolutionError:
        raise
    except (DigestError, RenderArtifactError, OSError) as exc:
        raise DistanceStateAssetResolutionError(f"{label} could not be measured") from exc
    if (
        measured.get("pixel_digest") != image["pixelDigest"]
        or measured.get("pixel_digest_spec") != image["pixelDigestSpec"]
        or measured.get("pixel_mode") != image["pixelMode"]
        or measured.get("width") != image["width"]
        or measured.get("height") != image["height"]
    ):
        raise DistanceStateAssetResolutionError(f"{label} pixels are stale")


def _resolve_assets(
    request: Mapping[str, Any],
    resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    *,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    spec = request["transitionSpec"]
    variant_claims: dict[str, str] = {}
    for item in spec["visualStateDefinitions"]:
        reference = item["variantAssetVersionRef"]
        if reference is not None:
            previous = variant_claims.setdefault(
                reference, item["variantAssetVersionDigest"]
            )
            if previous != item["variantAssetVersionDigest"]:
                raise DistanceStateAssetResolutionError(
                    "variant AssetVersion digest is ambiguous"
                )
    expected_refs = {spec["basePlateAssetVersionRef"], *variant_claims}
    if spec["targetKind"] == "OVERLAY_LAYER":
        expected_refs.update(
            {
                spec["subjectLayerAssetVersionRef"],
                spec["maskAssetVersionRef"],
            }
        )
    if (
        not isinstance(resolved_asset_versions, Mapping)
        or set(resolved_asset_versions) != expected_refs
        or None in expected_refs
        or len(expected_refs) != 1 + len(variant_claims) + (
            2 if spec["targetKind"] == "OVERLAY_LAYER" else 0
        )
    ):
        raise DistanceStateAssetResolutionError(
            "resolved AssetVersion roles are not exact and distinct"
        )
    base = _resolved_base(resolved_asset_versions[spec["basePlateAssetVersionRef"]])
    expected_base = {
        "assetVersionRef": spec["basePlateAssetVersionRef"],
        "assetVersionDigest": spec["basePlateAssetVersionDigest"],
        "fileDigest": spec["basePlateFileDigest"],
        "pixelDigest": spec["basePlatePixelDigest"],
        "width": spec["canvasWidth"],
        "height": spec["canvasHeight"],
        "frameCount": spec["frameCount"],
        "frameRate": spec["frameRate"],
    }
    if any(base[field] != expected for field, expected in expected_base.items()):
        raise DistanceStateAssetResolutionError("basePlate authority is stale")
    subject: dict[str, Any] | None = None
    mask: dict[str, Any] | None = None
    if spec["targetKind"] == "OVERLAY_LAYER":
        subject = _resolved_image(
            resolved_asset_versions[spec["subjectLayerAssetVersionRef"]],
            "resolved subjectLayer",
        )
        mask = _resolved_image(
            resolved_asset_versions[spec["maskAssetVersionRef"]],
            "resolved mask",
        )
        claims = (
            (
                subject,
                spec["subjectLayerAssetVersionRef"],
                spec["subjectLayerAssetVersionDigest"],
                spec["subjectLayerFileDigest"],
                spec["subjectLayerPixelDigest"],
            ),
            (
                mask,
                spec["maskAssetVersionRef"],
                spec["maskAssetVersionDigest"],
                spec["maskFileDigest"],
                spec["maskPixelDigest"],
            ),
        )
        for record, reference, digest, file_digest_value, pixel_digest in claims:
            if (
                record["assetVersionRef"] != reference
                or record["assetVersionDigest"] != digest
                or record["fileDigest"] != file_digest_value
                or record["pixelDigest"] != pixel_digest
            ):
                raise DistanceStateAssetResolutionError(
                    "overlay AssetVersion authority is stale"
                )
        if (subject["width"], subject["height"]) != (
            mask["width"],
            mask["height"],
        ):
            raise DistanceStateAssetResolutionError(
                "subjectLayer and explicit mask dimensions differ"
            )
    variants = []
    for reference in sorted(variant_claims):
        record = _resolved_image(
            resolved_asset_versions[reference], "resolved variant"
        )
        if (
            record["assetVersionRef"] != reference
            or record["assetVersionDigest"] != variant_claims[reference]
            or subject is None
            or (record["width"], record["height"])
            != (subject["width"], subject["height"])
        ):
            raise DistanceStateAssetResolutionError(
                "variant AssetVersion authority is stale or incompatible"
            )
        variants.append(record)
    _measure_base(root, base)
    if subject is not None and mask is not None:
        _measure_image(root, subject, "subjectLayer")
        _measure_image(root, mask, "explicit mask")
        for index, variant in enumerate(variants):
            _measure_image(root, variant, f"variant {index}")
    return base, subject, mask, variants


def rebuild_distance_state_v3_request(
    execution_request: Mapping[str, Any],
    resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    artifact_root: Path | str,
) -> dict[str, Any]:
    """Rebuild the sole closed, storage-resolved V3 projection."""

    request = validate_distance_state_execution_request(execution_request)
    root = Path(artifact_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise DistanceStateAssetResolutionError("artifact root is invalid")
    base, subject, mask, variants = _resolve_assets(
        request, resolved_asset_versions, root=root
    )
    spec = request["transitionSpec"]
    target_shot = {
        "shotRef": spec["targetShotRef"],
        "shotVersionRef": spec["targetShotVersionRef"],
        "shotVersionDigest": spec["targetShotVersionDigest"],
    }
    output = {
        "width": base["width"],
        "height": base["height"],
        "frameCount": base["frameCount"],
        "frameRate": base["frameRate"],
        "pixelFormat": "yuv420p",
        "container": "mp4",
        "videoCodec": "h264",
    }
    values = {
        "schemaVersion": DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION,
        "v5ExecutionRequestRef": request["executionRequestRef"],
        "v5ExecutionRequestDigest": request["payloadDigest"],
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "effectMode": DISTANCE_STATE_TRANSITION,
        "targetShot": target_shot,
        "targetKind": spec["targetKind"],
        "basePlate": base,
        "subjectLayer": subject,
        "mask": mask,
        "variantAssets": variants,
        "frameRangeStartInclusive": spec["frameRangeStartInclusive"],
        "frameRangeEndExclusive": spec["frameRangeEndExclusive"],
        "transitionMode": spec["transitionMode"],
        "coordinateSpace": spec["coordinateSpace"],
        "motionKeyframes": deepcopy(spec["motionKeyframes"]),
        "distanceContract": deepcopy(spec["distanceContract"]),
        "startStateRef": spec["startStateRef"],
        "endStateRef": spec["endStateRef"],
        "visualStateDefinitions": deepcopy(spec["visualStateDefinitions"]),
        "visualStateSchedule": deepcopy(spec["visualStateSchedule"]),
        "blendMode": spec["blendMode"],
        "layer": spec["layer"],
        "output": output,
        "publicationAllowed": False,
    }
    return _seal(values)


def _verify_sealed(
    value: Any, fields: frozenset[str], label: str
) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = _raw(result.pop("payloadDigest"), f"{label}.payloadDigest")
    if supplied != sha256(_canonical(result)).hexdigest():
        raise DistanceStateExecutionError(f"{label} seal is stale")
    result["payloadDigest"] = supplied
    return result


def _evidence_ref(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + sha256(_canonical(value)).hexdigest()[:32]


def _runtime_text(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= 500
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise DistanceStateExecutionError(f"{label} is invalid")
    return value


def _validate_probe(value: Any, label: str) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_FIELDS, label)
    width = _integer(result["width"], f"{label}.width", 2, 16_384)
    height = _integer(result["height"], f"{label}.height", 2, 16_384)
    _integer(result["frameCount"], f"{label}.frameCount", 1, 10_000_000)
    _integer(result["frameRate"], f"{label}.frameRate", 1, 240)
    if (
        width % 2
        or height % 2
        or result["pixelFormat"] != "yuv420p"
        or result["container"] != "mp4"
        or result["videoCodec"] != "h264"
    ):
        raise DistanceStateExecutionError(f"{label} media contract is invalid")
    return result


def _validate_output_digest(value: Any, label: str) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_DIGEST_FIELDS, label)
    _content(result["fileDigest"], f"{label}.fileDigest")
    _content(
        result["decodedFramePixelDigest"],
        f"{label}.decodedFramePixelDigest",
    )
    _integer(result["width"], f"{label}.width", 2, 16_384)
    _integer(result["height"], f"{label}.height", 2, 16_384)
    _integer(result["frameCount"], f"{label}.frameCount", 1, 10_000_000)
    _integer(result["frameRate"], f"{label}.frameRate", 1, 240)
    if (
        result["fileDigestAlgorithm"] != "sha256"
        or result["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or result["pixelMode"] != "RGBA"
    ):
        raise DistanceStateExecutionError(f"{label} digest contract is invalid")
    return result


def validate_distance_state_runtime_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(
        value, _RUNTIME_FIELDS, "distance/state runtime evidence"
    )
    if (
        result["schemaVersion"]
        != DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] != DISTANCE_STATE_TRANSITION
        or result["rendererIdentity"] != DISTANCE_STATE_RENDERER_IDENTITY
        or result["rendererVersion"] != DISTANCE_STATE_RENDERER_VERSION
        or result["gpuUsed"] is not False
        or result["publicationAllowed"] is not False
    ):
        raise DistanceStateExecutionError(
            "distance/state runtime evidence authority is invalid"
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
        _raw(result[field], field)
    _runtime_text(result["ffmpegIdentity"], "ffmpegIdentity")
    _content(result["executionManifestDigest"], "executionManifestDigest")
    expected = _evidence_ref(
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
    if result["runtimeEvidenceRef"] != expected:
        raise DistanceStateExecutionError(
            "distance/state runtime evidence ref is stale"
        )
    return result


def validate_distance_state_artifact_evidence(
    value: Any,
    *,
    runtime_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = _verify_sealed(
        value, _ARTIFACT_FIELDS, "distance/state artifact evidence"
    )
    if (
        result["schemaVersion"]
        != DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] != DISTANCE_STATE_TRANSITION
        or result["provenance"] != DISTANCE_STATE_PROVENANCE
        or result["publicationAllowed"] is not False
    ):
        raise DistanceStateExecutionError(
            "distance/state artifact evidence authority is invalid"
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
        "appliedStateScheduleDigest",
    ):
        _raw(result[field], field)
    _integer(
        result["outputByteSize"],
        "outputByteSize",
        1,
        10**12,
    )
    probe = _validate_probe(result["outputMediaProbe"], "outputMediaProbe")
    digest = _validate_output_digest(result["outputDigest"], "outputDigest")
    if any(
        digest[field] != probe[field]
        for field in ("width", "height", "frameCount", "frameRate")
    ):
        raise DistanceStateExecutionError(
            "distance/state artifact media facts disagree"
        )
    facts = result["derivedDistanceFacts"]
    if facts is not None:
        _closed(
            facts,
            frozenset(
                {
                    "metric",
                    "startValue",
                    "endValue",
                    "tolerance",
                    "direction",
                    "referenceX",
                    "referenceY",
                }
            ),
            "derivedDistanceFacts",
        )
    expected_ref = _evidence_ref(
        "m13-distance-state-artifact-evidence-",
        {
            "v3ExecutionRequestDigest": result["v3ExecutionRequestDigest"],
            "fileDigest": digest["fileDigest"],
            "runtimeEvidenceDigest": result["runtimeEvidenceDigest"],
        },
    )
    if result["artifactEvidenceRef"] != expected_ref:
        raise DistanceStateExecutionError(
            "distance/state artifact evidence ref is stale"
        )
    if runtime_evidence is not None:
        runtime = validate_distance_state_runtime_evidence(runtime_evidence)
        for field in (
            "workspaceRef",
            "productionRunRef",
            "requirementRef",
            "requirementDigest",
            "executionRequestRef",
            "executionRequestDigest",
            "v3ExecutionRequestDigest",
            "effectMode",
        ):
            if runtime[field] != result[field]:
                raise DistanceStateExecutionError(
                    "distance/state evidence lineage is crossed"
                )
        if (
            runtime["runtimeEvidenceRef"] != result["runtimeEvidenceRef"]
            or runtime["payloadDigest"] != result["runtimeEvidenceDigest"]
        ):
            raise DistanceStateExecutionError(
                "distance/state runtime binding is stale"
            )
    return result


def _expected_output_key(value: Mapping[str, Any]) -> str:
    workspace = sha256(str(value["workspaceRef"]).encode("utf-8")).hexdigest()[:20]
    run = sha256(str(value["productionRunRef"]).encode("utf-8")).hexdigest()[:20]
    return str(
        PurePosixPath(
            workspace,
            run,
            "distance-state",
            f"distance-state-{value['v3ExecutionRequestDigest']}.mp4",
        )
    )


def _measure_output(
    artifact_root: Path,
    *,
    storage_key: str,
    byte_size: int,
    output_probe: Mapping[str, Any],
    output_digest: Mapping[str, Any],
    ffmpeg_identity: str,
) -> Path:
    from services.v3_render_core.masked_surface import _probe_video

    path = _server_file(artifact_root, storage_key, label="distance/state output")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise DistanceStateExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        with (
            _PinnedRegularFile(path, label="distance/state output") as pinned,
            _PinnedRuntimeBinary(
                Path(ffmpeg_path).resolve(), label="FFmpeg"
            ) as ffmpeg,
            _PinnedRuntimeBinary(
                Path(ffprobe_path).resolve(), label="FFprobe"
            ) as ffprobe,
        ):
            if (
                pinned.descriptor is None
                or os.fstat(pinned.descriptor).st_size != byte_size
            ):
                raise DistanceStateExecutionError(
                    "distance/state output byte size is stale"
                )
            if ffmpeg.version_identity() != ffmpeg_identity:
                raise DistanceStateExecutionError(
                    "distance/state FFmpeg identity is stale"
                )
            pass_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            if file_digest(pinned.descriptor_path) != output_digest["fileDigest"]:
                raise DistanceStateExecutionError(
                    "distance/state output file digest is stale"
                )
            probe = _probe_video(
                pinned.descriptor_path,
                SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                ),
            )
            measured = decoded_frame_pixel_digest_metadata(
                pinned.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            pinned.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
    except DistanceStateExecutionError:
        raise
    except (DigestError, RenderArtifactError, OSError) as exc:
        raise DistanceStateExecutionError(
            "distance/state output could not be remeasured"
        ) from exc
    expected_probe = dict(output_probe)
    if (
        probe["width"] != expected_probe["width"]
        or probe["height"] != expected_probe["height"]
        or probe["frameCount"] != expected_probe["frameCount"]
        or probe["frameRate"].denominator != 1
        or probe["frameRate"].numerator != expected_probe["frameRate"]
        or probe["realFrameRate"] != probe["frameRate"]
        or probe["startTime"] != 0
        or probe["duration"] != probe["frameCount"] / probe["frameRate"]
        or probe["pixelFormat"] != expected_probe["pixelFormat"]
        or probe["videoCodec"] != expected_probe["videoCodec"]
        or expected_probe["container"] not in str(probe["formatName"]).split(",")
        or measured.get("fileDigest") != output_digest["fileDigest"]
        or measured.get("decodedFramePixelDigest")
        != output_digest["decodedFramePixelDigest"]
        or measured.get("decodedFramePixelDigestSpec")
        != output_digest["decodedFramePixelDigestSpec"]
        or any(
            measured.get(field) != output_digest[field]
            for field in ("width", "height", "frameCount")
        )
    ):
        raise DistanceStateExecutionError(
            "distance/state output media identity is stale"
        )
    return path


def _validate_v3_result(
    value: Any,
    *,
    request: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    result = _closed(value, _V3_RESULT_FIELDS, "V3 distance/state result")
    expected_lineage = {
        "v5ExecutionRequestRef": request["v5ExecutionRequestRef"],
        "v5ExecutionRequestDigest": request["v5ExecutionRequestDigest"],
        "v3ExecutionRequestDigest": request["payloadDigest"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "effectMode": request["effectMode"],
    }
    if (
        any(result[field] != expected for field, expected in expected_lineage.items())
        or result["publicationAllowed"] is not False
        or result["rendererIdentity"] != DISTANCE_STATE_RENDERER_IDENTITY
        or result["rendererVersion"] != DISTANCE_STATE_RENDERER_VERSION
        or result["derivedDistanceFacts"] != request["distanceContract"]
    ):
        raise DistanceStateExecutionError("V3 distance/state lineage is stale")
    _runtime_text(result["ffmpegIdentity"], "ffmpegIdentity")
    _content(result["executionManifestDigest"], "executionManifestDigest")
    _content(result["runtimeEvidenceDigest"], "runtimeEvidenceDigest")
    _raw(result["appliedStateScheduleDigest"], "appliedStateScheduleDigest")
    byte_size = _integer(
        result["outputByteSize"], "outputByteSize", 1, 10**12
    )
    probe = _validate_probe(result["outputMediaProbe"], "outputMediaProbe")
    output_digest = _validate_output_digest(
        result["outputDigest"], "outputDigest"
    )
    if probe != request["output"] or any(
        output_digest[field] != probe[field]
        for field in ("width", "height", "frameCount", "frameRate")
    ):
        raise DistanceStateExecutionError("V3 distance/state output is stale")
    runtime_identity = {
        "ffmpegIdentity": result["ffmpegIdentity"],
        "rendererIdentity": result["rendererIdentity"],
        "rendererVersion": result["rendererVersion"],
        "executionManifestDigest": result["executionManifestDigest"],
    }
    if result["runtimeEvidenceDigest"] != (
        "sha256:" + sha256(_canonical(runtime_identity)).hexdigest()
    ):
        raise DistanceStateExecutionError("V3 runtime identity is stale")
    expected_key = _expected_output_key(
        {
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "v3ExecutionRequestDigest": request["payloadDigest"],
        }
    )
    if result["outputStorageKey"] != expected_key:
        raise DistanceStateExecutionError("V3 output storage lineage is stale")
    path = _measure_output(
        artifact_root,
        storage_key=expected_key,
        byte_size=byte_size,
        output_probe=probe,
        output_digest=output_digest,
        ffmpeg_identity=result["ffmpegIdentity"],
    )
    if result["internalPath"] != str(path):
        raise DistanceStateExecutionError("V3 internal output path is stale")
    return result


def _requirement_from_execution_request(
    execution_request: Mapping[str, Any],
) -> dict[str, Any]:
    from services.v5_core_os.episode_production.distance_state import (
        DISTANCE_STATE_TRANSITION_REQUIREMENT_SCHEMA_VERSION,
        parse_distance_state_requirement,
    )

    value = {
        "schemaVersion": DISTANCE_STATE_TRANSITION_REQUIREMENT_SCHEMA_VERSION,
        "workspaceRef": execution_request["workspaceRef"],
        "productionRunRef": execution_request["productionRunRef"],
        "requirementRef": execution_request["requirementRef"],
        "effectMode": execution_request["effectMode"],
        **deepcopy(execution_request["transitionSpec"]),
        "publicationAllowed": False,
        "payloadDigest": execution_request["requirementDigest"],
    }
    return parse_distance_state_requirement(value).as_dict()


def _build_evidence(
    *,
    v5: Mapping[str, Any],
    v3: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    from services.v5_core_os.episode_production.distance_state import (
        build_distance_state_artifact_evidence,
        build_distance_state_runtime_evidence,
        parse_distance_state_requirement,
    )

    requirement = parse_distance_state_requirement(
        _requirement_from_execution_request(v5)
    )
    runtime_contract = build_distance_state_runtime_evidence(
        requirement=requirement,
        execution_request=v5,
        execution_facts={
            "v3ExecutionRequestDigest": v3["payloadDigest"],
            "rendererIdentity": result["rendererIdentity"],
            "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"],
            "executionManifestDigest": result["executionManifestDigest"],
        },
    )
    runtime = runtime_contract.as_dict()
    artifact_contract = build_distance_state_artifact_evidence(
        requirement=requirement,
        execution_request=v5,
        runtime_evidence=runtime_contract,
        execution_facts={
            "v3ExecutionRequestDigest": v3["payloadDigest"],
            "outputByteSize": result["outputByteSize"],
            "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
            "outputDigest": deepcopy(result["outputDigest"]),
            "derivedDistanceFacts": deepcopy(result["derivedDistanceFacts"]),
            "appliedStateScheduleDigest": result[
                "appliedStateScheduleDigest"
            ],
        },
    )
    artifact = artifact_contract.as_dict()
    runtime = validate_distance_state_runtime_evidence(runtime)
    artifact = validate_distance_state_artifact_evidence(
        artifact, runtime_evidence=runtime
    )
    bindings = {
        "workspaceRef": v5["workspaceRef"],
        "productionRunRef": v5["productionRunRef"],
        "requirementRef": v5["requirementRef"],
        "requirementDigest": v5["requirementDigest"],
        "executionRequestRef": v5["executionRequestRef"],
        "executionRequestDigest": v5["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    if set(bindings) != _BINDING_FIELDS:
        raise DistanceStateExecutionError(
            "distance/state evidence bindings are invalid"
        )
    return {
        "artifactEvidence": artifact,
        "runtimeEvidence": runtime,
        "evidenceBindings": bindings,
    }


def _resolve_distance_state_preview_stage_impl(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path | str,
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild one exact E4 stage for the existing Timeline Preview owner."""

    from services.v5_core_os.episode_production.distance_state import (
        build_distance_state_execution_request,
        parse_distance_state_requirement,
        parse_distance_state_result,
    )

    root = Path(artifact_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise DistanceStateAssetResolutionError("artifact root is invalid")
    bound = _closed(binding, _PREVIEW_BINDING_FIELDS, "distance/state binding")
    resolved = _closed(
        resolution,
        _PREVIEW_RESOLUTION_FIELDS,
        f"distance/state execution {bound['resultRef']}",
    )
    preview_base = _resolved_base(base)
    requirement_wrapper = parse_distance_state_requirement(
        resolved["requirement"]
    )
    requirement = requirement_wrapper.as_dict()
    request = validate_distance_state_execution_request(
        resolved["executionRequest"]
    )
    if request != build_distance_state_execution_request(
        requirement_wrapper
    ).as_dict():
        raise DistanceStateExecutionError(
            "distance/state execution request is stale"
        )
    runtime = validate_distance_state_runtime_evidence(
        resolved["runtimeEvidence"]
    )
    artifact = validate_distance_state_artifact_evidence(
        resolved["artifactEvidence"], runtime_evidence=runtime
    )
    result = parse_distance_state_result(resolved["result"]).as_dict()

    expected_lineage = {
        "workspaceRef": request["workspaceRef"],
        "productionRunRef": request["productionRunRef"],
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "effectMode": DISTANCE_STATE_TRANSITION,
    }
    if any(
        runtime[field] != expected
        or artifact[field] != expected
        or result[field] != expected
        for field, expected in expected_lineage.items()
    ):
        raise DistanceStateExecutionError(
            "distance/state Requirement, evidence, and Result lineage disagree"
        )
    expected_result = {
        "resultRef": bound["resultRef"],
        "payloadDigest": bound["resultDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "outputFileDigest": artifact["outputDigest"]["fileDigest"],
        "outputDecodedFramePixelDigest": artifact["outputDigest"][
            "decodedFramePixelDigest"
        ],
        "outputMediaProbe": artifact["outputMediaProbe"],
        "derivedDistanceFacts": artifact["derivedDistanceFacts"],
        "appliedStateScheduleDigest": artifact[
            "appliedStateScheduleDigest"
        ],
    }
    if any(result[field] != expected for field, expected in expected_result.items()):
        raise DistanceStateExecutionError("distance/state Result binding is stale")
    expected_binding = {
        "effectMode": DISTANCE_STATE_TRANSITION,
        "requirementRef": request["requirementRef"],
        "requirementDigest": request["requirementDigest"],
        "resultRef": result["resultRef"],
        "resultDigest": result["payloadDigest"],
        "executionRequestRef": request["executionRequestRef"],
        "executionRequestDigest": request["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
        "frameRangeStartInclusive": requirement[
            "frameRangeStartInclusive"
        ],
        "frameRangeEndExclusive": requirement["frameRangeEndExclusive"],
    }
    if any(bound[field] != expected for field, expected in expected_binding.items()):
        raise DistanceStateExecutionError(
            "distance/state Timeline binding does not match its evidence chain"
        )

    stage = rebuild_distance_state_v3_request(
        request,
        resolved["assetVersions"],
        root,
    )
    if (
        runtime["v3ExecutionRequestDigest"] != stage["payloadDigest"]
        or artifact["v3ExecutionRequestDigest"] != stage["payloadDigest"]
    ):
        raise DistanceStateExecutionError(
            "distance/state evidence does not bind the rebuilt V3 request"
        )
    if any(stage["basePlate"][field] != preview_base[field] for field in _BASE_FIELDS):
        raise DistanceStateAssetResolutionError(
            "distance/state stage does not use the exact preview baseVideo"
        )

    output = artifact["outputDigest"]
    probe = artifact["outputMediaProbe"]
    workspace_hash = sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
    run_hash = sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
    expected_storage = {
        "artifactEvidenceRef": artifact["artifactEvidenceRef"],
        "artifactEvidenceDigest": artifact["payloadDigest"],
        "storageKey": str(
            PurePosixPath(
                workspace_hash,
                run_hash,
                "distance-state",
                f"distance-state-{stage['payloadDigest']}.mp4",
            )
        ),
        "fileDigest": output["fileDigest"],
        "pixelDigest": output["decodedFramePixelDigest"],
        "pixelDigestSpec": output["decodedFramePixelDigestSpec"],
        "width": output["width"],
        "height": output["height"],
        "frameCount": output["frameCount"],
        "frameRate": output["frameRate"],
        "pixelFormat": probe["pixelFormat"],
    }
    storage = _closed(
        resolved["artifactStorage"],
        _PREVIEW_ARTIFACT_STORAGE_FIELDS,
        "distance/state artifactStorage",
    )
    if storage != expected_storage:
        raise DistanceStateAssetResolutionError(
            "distance/state artifactStorage does not match evidence"
        )
    if verify_distance_state_artifact(
        root, artifact, runtime_evidence=runtime
    ) != artifact:
        raise DistanceStateAssetResolutionError(
            "distance/state artifact verification projection is stale"
        )
    return stage


def resolve_distance_state_preview_stage(
    binding: Mapping[str, Any],
    resolution: Any,
    *,
    artifact_root: Path | str,
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """Translate V5 contract failures into the subordinate V4 boundary."""

    from services.v5_core_os.episode_production.foundation import (
        EpisodeProductionError,
    )

    try:
        return _resolve_distance_state_preview_stage_impl(
            binding,
            resolution,
            artifact_root=artifact_root,
            base=base,
        )
    except DistanceStateExecutionError:
        raise
    except EpisodeProductionError as exc:
        raise DistanceStateExecutionError(
            "distance/state execution chain could not be resolved"
        ) from exc


class V4DistanceStateExecutor:
    """Subordinate V4 execution boundary owned by the existing composition."""

    def __init__(self, artifact_root: Path | str, v3_executor: Any) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise DistanceStateAssetResolutionError("artifact root is invalid")
        if not callable(getattr(v3_executor, "execute", None)):
            raise DistanceStateExecutionError("V3 distance/state executor is required")
        self.v3_executor = v3_executor

    @classmethod
    def from_artifact_root(
        cls, artifact_root: Path | str
    ) -> "V4DistanceStateExecutor":
        from services.v3_render_core.distance_state import (
            DeterministicDistanceStateExecutor,
        )

        root = Path(artifact_root).resolve()
        return cls(root, DeterministicDistanceStateExecutor(root))

    def execute(
        self,
        execution_request: Mapping[str, Any],
        *,
        resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        v5 = validate_distance_state_execution_request(execution_request)
        v3 = rebuild_distance_state_v3_request(
            v5,
            resolved_asset_versions,
            self.artifact_root,
        )
        try:
            raw = self.v3_executor.execute(v3)
        except DistanceStateExecutionError:
            raise
        except Exception as exc:
            raise DistanceStateExecutionError(
                "V3 distance/state execution failed"
            ) from exc
        result = _validate_v3_result(
            raw, request=v3, artifact_root=self.artifact_root
        )
        return _build_evidence(v5=v5, v3=v3, result=result)


def verify_distance_state_artifact(
    artifact_root: Path | str,
    artifact_evidence: Mapping[str, Any],
    *,
    runtime_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Physically remeasure a path-free persisted E4 artifact projection."""

    root = Path(artifact_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise DistanceStateAssetResolutionError("artifact root is invalid")
    runtime = validate_distance_state_runtime_evidence(runtime_evidence)
    artifact = validate_distance_state_artifact_evidence(
        artifact_evidence, runtime_evidence=runtime
    )
    storage_key = _expected_output_key(artifact)
    _measure_output(
        root,
        storage_key=storage_key,
        byte_size=artifact["outputByteSize"],
        output_probe=artifact["outputMediaProbe"],
        output_digest=artifact["outputDigest"],
        ffmpeg_identity=runtime["ffmpegIdentity"],
    )
    return deepcopy(artifact)


__all__ = [
    "DISTANCE_STATE_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "DISTANCE_STATE_EXECUTION_REQUEST_SCHEMA_VERSION",
    "DISTANCE_STATE_PROVENANCE",
    "DISTANCE_STATE_RENDERER_IDENTITY",
    "DISTANCE_STATE_RENDERER_VERSION",
    "DISTANCE_STATE_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "DISTANCE_STATE_TRANSITION",
    "DISTANCE_STATE_V3_REQUEST_SCHEMA_VERSION",
    "DistanceStateAssetResolutionError",
    "DistanceStateExecutionError",
    "DistanceStateRequestValidationError",
    "V4DistanceStateExecutor",
    "rebuild_distance_state_v3_request",
    "resolve_distance_state_preview_stage",
    "validate_distance_state_artifact_evidence",
    "validate_distance_state_execution_request",
    "validate_distance_state_runtime_evidence",
    "verify_distance_state_artifact",
]
