"""Closed V4 bridge for deterministic M13-E3 overlays.

V5 owns the immutable Requirement/Result/evidence journal and V3 owns the
rendering primitive.  This module independently validates the sealed V5
execution projection, remeasures the server-held inputs, derives the one
closed V3 request, and returns path-free evidence records.
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

from services.v3_render_core import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    DigestError,
    IMAGE_PIXEL_DIGEST_SPEC,
    decoded_frame_pixel_digest_metadata,
    file_digest,
    image_digest_metadata,
)
from services.v3_render_core.composition import (
    RenderArtifactError,
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
)


OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION = "v5.m13-overlay-execution-request.v1"
OVERLAY_V3_REQUEST_SCHEMA_VERSION = "v4.m13-overlay-execution-request.v1"
OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.m13-overlay-artifact-evidence.v1"
OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION = "v4.m13-overlay-runtime-evidence.v1"
OVERLAY_RENDERER_IDENTITY = "v3.deterministic-overlay-ffmpeg"
OVERLAY_RENDERER_VERSION = "1"
OVERLAY_PROVENANCE = "LOCAL_EVIDENCE"

NAMEPLATE_TEXT = "NAMEPLATE_TEXT"
FACE_MARK_COMPENSATION = "FACE_MARK_COMPENSATION"
OVERLAY_EFFECT_MODES = (NAMEPLATE_TEXT, FACE_MARK_COMPENSATION)

_RAW_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion", "executionRequestRef", "workspaceRef",
        "productionRunRef", "requirementRef", "requirementDigest",
        "effectMode", "overlaySpec", "publicationAllowed", "payloadDigest",
    }
)
_BASE_FIELDS = frozenset(
    {
        "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
        "pixelDigest", "pixelDigestSpec", "width", "height", "frameCount",
        "frameRate", "pixelFormat",
    }
)
_FONT_FIELDS = frozenset(
    {
        "assetVersionRef", "assetVersionDigest", "storageBindingRef",
        "fileDigest", "byteSize", "mediaType", "fontFormat",
        "validationRef", "validationDigest", "licenseBindingRef",
        "licenseBindingDigest",
    }
)
_V3_FONT_FIELDS = frozenset(
    {
        "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
        "validationRef", "validationDigest", "licenseBindingRef",
        "licenseBindingDigest",
    }
)
_MARK_FIELDS = frozenset(
    {
        "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
        "pixelDigest", "pixelDigestSpec", "pixelMode", "width", "height",
    }
)
_OUTPUT_FIELDS = frozenset(
    {"width", "height", "frameCount", "frameRate", "pixelFormat", "container", "videoCodec"}
)
_V3_FIELDS = frozenset(
    {
        "schemaVersion", "v5ExecutionRequestRef", "v5ExecutionRequestDigest",
        "workspaceRef", "productionRunRef", "requirementRef",
        "requirementDigest", "effectMode", "basePlate", "overlayAsset",
        "overlaySpec", "output", "publicationAllowed", "payloadDigest",
    }
)
_OUTPUT_DIGEST_FIELDS = frozenset(
    {
        "fileDigest", "fileDigestAlgorithm", "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec", "pixelMode", "width", "height",
        "frameCount", "frameRate",
    }
)
_V3_RESULT_FIELDS = frozenset(
    {
        "internalPath", "outputStorageKey", "outputByteSize", "outputMediaProbe",
        "outputDigest", "rendererIdentity", "rendererVersion", "ffmpegIdentity",
        "executionManifestDigest", "runtimeEvidenceDigest", "v5ExecutionRequestRef",
        "v5ExecutionRequestDigest", "v3ExecutionRequestDigest", "requirementRef",
        "requirementDigest", "effectMode", "publicationAllowed",
    }
)
_RUNTIME_FIELDS = frozenset(
    {
        "schemaVersion", "runtimeEvidenceRef", "workspaceRef", "productionRunRef",
        "requirementRef", "requirementDigest", "executionRequestRef",
        "executionRequestDigest", "v3ExecutionRequestDigest", "effectMode",
        "rendererIdentity", "rendererVersion", "ffmpegIdentity",
        "executionManifestDigest", "gpuUsed", "publicationAllowed", "payloadDigest",
    }
)
_ARTIFACT_FIELDS = frozenset(
    {
        "schemaVersion", "artifactEvidenceRef", "workspaceRef", "productionRunRef",
        "requirementRef", "requirementDigest", "executionRequestRef",
        "executionRequestDigest", "v3ExecutionRequestDigest", "effectMode",
        "outputByteSize", "outputMediaProbe", "outputDigest", "runtimeEvidenceRef",
        "runtimeEvidenceDigest", "provenance", "publicationAllowed", "payloadDigest",
    }
)
_EVIDENCE_BINDING_FIELDS = frozenset(
    {
        "workspaceRef", "productionRunRef", "requirementRef", "requirementDigest",
        "executionRequestRef", "executionRequestDigest", "artifactEvidenceRef",
        "artifactEvidenceDigest", "runtimeEvidenceRef", "runtimeEvidenceDigest",
    }
)
_NAMEPLATE_SPEC_FIELDS = frozenset(
    {
        "targetShot", "frameRangeStartInclusive", "frameRangeEndExclusive",
        "blendMode", "layer", "resolvedText", "resolvedTextDigest", "language",
        "layout", "positionKeyframes", "scaleKeyframes", "rotationKeyframes",
        "perspectiveKeyframes", "opacityCurve", "trackingKeyframes",
    }
)
_FACE_SPEC_FIELDS = frozenset(
    {
        "targetShot", "frameRangeStartInclusive", "frameRangeEndExclusive",
        "blendMode", "layer", "markType", "faceRegion", "trackingSourceKind",
        "trackingKeyframes", "scaleKeyframes", "rotationKeyframes",
        "opacityCurve", "occlusionPolicy",
    }
)
_V5_COMMON_OVERLAY_SPEC_FIELDS = frozenset(
    {
        "targetShotRef", "targetShotVersionRef", "targetShotVersionDigest",
        "basePlateAssetVersionRef", "basePlateAssetVersionDigest",
        "basePlateFileDigest", "basePlatePixelDigest",
        "frameRangeStartInclusive", "frameRangeEndExclusive", "blendMode",
        "layer",
    }
)
_V5_NAMEPLATE_OVERLAY_SPEC_FIELDS = _V5_COMMON_OVERLAY_SPEC_FIELDS | frozenset(
    {
        "textSourceKind", "textSourceRef", "textSourceVersionRef",
        "textSourceDigest", "resolvedText", "resolvedTextDigest", "language",
        "fontAssetVersionRef", "fontAssetVersionDigest", "fontFileDigest",
        "fontTechnicalValidationRef", "fontTechnicalValidationDigest",
        "fontLicenseBindingVersionRef", "fontLicenseBindingVersionDigest",
        "layout", "positionKeyframes", "scaleKeyframes",
        "rotationKeyframes", "perspectiveKeyframes", "opacityCurve",
        "trackingKeyframes",
    }
)
_V5_FACE_OVERLAY_SPEC_FIELDS = _V5_COMMON_OVERLAY_SPEC_FIELDS | frozenset(
    {
        "characterRef", "identityReferenceRef", "identityReferenceVersionRef",
        "identityReferenceContentDigest", "identityReferenceProjectionDigest",
        "identityLockRef", "identityLockVersionRef", "identityLockDigest",
        "markType", "markAssetVersionRef", "markAssetVersionDigest",
        "markFileDigest", "markPixelDigest", "faceRegion",
        "trackingSourceKind", "trackingKeyframes", "scaleKeyframes",
        "rotationKeyframes", "opacityCurve", "occlusionPolicy",
    }
)


class OverlayExecutionError(RuntimeError):
    """The closed V4/V3 deterministic-overlay boundary failed."""


class OverlayRequestValidationError(OverlayExecutionError):
    """The V5 execution projection is open, malformed, or stale."""


class OverlayAssetResolutionError(OverlayExecutionError):
    """A server-held input is missing, changed, or out of scope."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OverlayRequestValidationError("overlay value is not canonical JSON") from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise OverlayRequestValidationError("payloadDigest is derived")
    result["payloadDigest"] = sha256(_canonical(result)).hexdigest()
    return result


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise OverlayRequestValidationError(f"{label} fields are invalid")
    return deepcopy(dict(value))


def _ref(value: Any, field: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise OverlayRequestValidationError(f"{field} is invalid")
    return value


def _raw_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _RAW_SHA.fullmatch(value) is None:
        raise OverlayRequestValidationError(f"{field} is invalid")
    return value


def _prefixed_digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _PREFIXED_SHA.fullmatch(value) is None:
        raise OverlayRequestValidationError(f"{field} is invalid")
    return value


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise OverlayRequestValidationError(f"{field} is invalid")
    return value


def validate_overlay_execution_request(value: Any) -> dict[str, Any]:
    request = _closed(value, _REQUEST_FIELDS, "overlay execution request")
    supplied = _raw_digest(request.pop("payloadDigest"), "payloadDigest")
    if supplied != sha256(_canonical(request)).hexdigest():
        raise OverlayRequestValidationError("overlay execution request seal is stale")
    request["payloadDigest"] = supplied
    if (
        request["schemaVersion"] != OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION
        or request["effectMode"] not in OVERLAY_EFFECT_MODES
        or request["publicationAllowed"] is not False
    ):
        raise OverlayRequestValidationError("overlay execution request identity is invalid")
    for field in ("executionRequestRef", "workspaceRef", "productionRunRef", "requirementRef"):
        _ref(request[field], field)
    _raw_digest(request["requirementDigest"], "requirementDigest")
    spec_fields = (
        _V5_NAMEPLATE_OVERLAY_SPEC_FIELDS
        if request["effectMode"] == NAMEPLATE_TEXT
        else _V5_FACE_OVERLAY_SPEC_FIELDS
    )
    request["overlaySpec"] = _closed(
        request["overlaySpec"], spec_fields, "overlaySpec"
    )
    expected_ref = "overlay-execution-" + sha256(
        _canonical(
            {"requirementRef": request["requirementRef"], "requirementDigest": request["requirementDigest"]}
        )
    ).hexdigest()[:32]
    if request["executionRequestRef"] != expected_ref:
        raise OverlayRequestValidationError("executionRequestRef derivation is stale")
    return request


def _storage_key(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise OverlayAssetResolutionError(f"{field} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or value != str(path) or any(part in {"", ".", ".."} for part in path.parts):
        raise OverlayAssetResolutionError(f"{field} is invalid")
    return value


def _server_file(root: Path, storage_key: Any, *, label: str) -> Path:
    key = _storage_key(storage_key, f"{label}.storageKey")
    current = root
    try:
        for part in PurePosixPath(key).parts:
            current = current / part
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                raise OverlayAssetResolutionError(f"{label} storage contains a symlink")
        metadata = os.stat(current, follow_symlinks=False)
        resolved = current.resolve(strict=True)
    except OverlayAssetResolutionError:
        raise
    except OSError as exc:
        raise OverlayAssetResolutionError(f"{label} storage is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0 or root not in resolved.parents:
        raise OverlayAssetResolutionError(f"{label} storage is invalid")
    return resolved


def _resolved(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    try:
        result = _closed(value, fields, label)
        _ref(result["assetVersionRef"], f"{label}.assetVersionRef")
        _raw_digest(result["assetVersionDigest"], f"{label}.assetVersionDigest")
        if "storageKey" in result:
            _storage_key(result["storageKey"], f"{label}.storageKey")
        else:
            _ref(result["storageBindingRef"], f"{label}.storageBindingRef")
        if fields == _FONT_FIELDS:
            _raw_digest(result["fileDigest"], f"{label}.fileDigest")
            _integer(result["byteSize"], f"{label}.byteSize", 1, 1_000_000_000)
            if result["mediaType"] not in {"font/ttf", "font/otf"} or result["fontFormat"] not in {"TTF", "OTF"}:
                raise OverlayRequestValidationError(f"{label} font media facts are invalid")
            for field in ("validationRef", "licenseBindingRef"):
                _ref(result[field], f"{label}.{field}")
            for field in ("validationDigest", "licenseBindingDigest"):
                _raw_digest(result[field], f"{label}.{field}")
        else:
            _prefixed_digest(result["fileDigest"], f"{label}.fileDigest")
        if "pixelDigest" in result:
            _prefixed_digest(result["pixelDigest"], f"{label}.pixelDigest")
        return result
    except OverlayRequestValidationError as exc:
        raise OverlayAssetResolutionError(f"{label} is invalid") from exc


def _stage_current_font(
    *,
    root: Path,
    request: Mapping[str, Any],
    resolved: Mapping[str, Any],
    font_asset_authority: Any,
) -> dict[str, Any]:
    """Re-resolve and copy a held canonical FONT fd into private V3 staging."""

    require_current = getattr(
        font_asset_authority, "require_current_font_asset_projection", None
    )
    open_current = getattr(font_asset_authority, "open_current_font_file", None)
    if not callable(require_current) or not callable(open_current):
        raise OverlayAssetResolutionError("current FONT authority is unavailable")
    text = request["overlaySpec"].get("resolvedText")
    try:
        projection = require_current(
            request["workspaceRef"], request["productionRunRef"],
            resolved["assetVersionRef"], resolved["assetVersionDigest"],
            required_text=text,
        )
    except Exception as exc:
        raise OverlayAssetResolutionError("current FONT projection is unavailable") from exc
    if not isinstance(projection, Mapping):
        raise OverlayAssetResolutionError("current FONT projection is invalid")
    asset = projection.get("fontAssetVersion")
    validation = projection.get("fontTechnicalValidation")
    license_binding = projection.get("fontLicenseBindingVersion")
    expected = {
        "assetVersionRef": asset.get("assetVersionRef") if isinstance(asset, Mapping) else None,
        "assetVersionDigest": asset.get("payloadDigest") if isinstance(asset, Mapping) else None,
        "storageBindingRef": projection.get("storageBindingRef"),
        "fileDigest": asset.get("fileDigest") if isinstance(asset, Mapping) else None,
        "byteSize": asset.get("byteSize") if isinstance(asset, Mapping) else None,
        "mediaType": asset.get("mediaType") if isinstance(asset, Mapping) else None,
        "fontFormat": asset.get("fontFormat") if isinstance(asset, Mapping) else None,
        "validationRef": validation.get("validationRef") if isinstance(validation, Mapping) else None,
        "validationDigest": validation.get("payloadDigest") if isinstance(validation, Mapping) else None,
        "licenseBindingRef": license_binding.get("licenseBindingVersionRef") if isinstance(license_binding, Mapping) else None,
        "licenseBindingDigest": license_binding.get("payloadDigest") if isinstance(license_binding, Mapping) else None,
    }
    if dict(resolved) != expected:
        raise OverlayAssetResolutionError("current FONT projection changed")
    descriptor: int | None = None
    try:
        descriptor = open_current(
            resolved["storageBindingRef"],
            expected_file_digest=resolved["fileDigest"],
            expected_byte_size=resolved["byteSize"],
            declared_media_type=resolved["mediaType"],
            required_text=text,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != resolved["byteSize"]:
            raise OverlayAssetResolutionError("held FONT descriptor is invalid")
        workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
        run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
        directory = root / workspace / run / "deterministic-overlay-inputs"
        directory.mkdir(parents=True, exist_ok=True)
        directory = directory.resolve(strict=True)
        if root not in directory.parents or directory.is_symlink():
            raise OverlayAssetResolutionError("FONT staging directory is invalid")
        suffix = ".ttf" if resolved["fontFormat"] == "TTF" else ".otf"
        destination = directory / f"font-{resolved['fileDigest']}{suffix}"
        os.lseek(descriptor, 0, os.SEEK_SET)
        with tempfile.NamedTemporaryFile(
            prefix=".font-stage-", suffix=suffix, dir=directory, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            remaining = resolved["byteSize"]
            digest = sha256()
            while remaining:
                block = os.read(descriptor, min(1024 * 1024, remaining))
                if not block:
                    raise OverlayAssetResolutionError("held FONT ended early")
                digest.update(block); temporary.write(block); remaining -= len(block)
            if os.read(descriptor, 1):
                raise OverlayAssetResolutionError("held FONT size changed")
            temporary.flush(); os.fsync(temporary.fileno())
        if digest.hexdigest() != resolved["fileDigest"]:
            raise OverlayAssetResolutionError("held FONT digest changed")
        os.replace(temporary_path, destination)
        os.chmod(destination, 0o600)
        staged = _server_file(
            root, str(destination.relative_to(root)), label="staged FONT"
        )
        if file_digest(staged) != f"sha256:{resolved['fileDigest']}":
            raise OverlayAssetResolutionError("staged FONT digest is stale")
    except OverlayAssetResolutionError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise OverlayAssetResolutionError("current FONT staging failed") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if "temporary_path" in locals() and temporary_path.exists():
            temporary_path.unlink()
    return {
        "assetVersionRef": resolved["assetVersionRef"],
        "assetVersionDigest": resolved["assetVersionDigest"],
        "storageKey": str(staged.relative_to(root)),
        "fileDigest": f"sha256:{resolved['fileDigest']}",
        "validationRef": resolved["validationRef"],
        "validationDigest": resolved["validationDigest"],
        "licenseBindingRef": resolved["licenseBindingRef"],
        "licenseBindingDigest": resolved["licenseBindingDigest"],
    }


def _semantic_spec(request: Mapping[str, Any]) -> dict[str, Any]:
    source = request["overlaySpec"]
    target = {
        "shotRef": source.get("targetShotRef"),
        "shotVersionRef": source.get("targetShotVersionRef"),
        "shotVersionDigest": source.get("targetShotVersionDigest"),
    }
    for field in ("shotRef", "shotVersionRef"):
        _ref(target[field], f"targetShot.{field}")
    _raw_digest(target["shotVersionDigest"], "targetShot.shotVersionDigest")
    common = {
        "targetShot": target,
        "frameRangeStartInclusive": source.get("frameRangeStartInclusive"),
        "frameRangeEndExclusive": source.get("frameRangeEndExclusive"),
        "blendMode": source.get("blendMode"),
        "layer": source.get("layer"),
    }
    names = (
        ("resolvedText", "resolvedTextDigest", "language", "layout", "positionKeyframes",
         "scaleKeyframes", "rotationKeyframes", "perspectiveKeyframes", "opacityCurve",
         "trackingKeyframes")
        if request["effectMode"] == NAMEPLATE_TEXT
        else ("markType", "faceRegion", "trackingSourceKind", "trackingKeyframes",
              "scaleKeyframes", "rotationKeyframes", "opacityCurve", "occlusionPolicy")
    )
    result = {**common, **{name: deepcopy(source.get(name)) for name in names}}
    expected = _NAMEPLATE_SPEC_FIELDS if request["effectMode"] == NAMEPLATE_TEXT else _FACE_SPEC_FIELDS
    if set(result) != expected or any(value is None for value in result.values()):
        raise OverlayRequestValidationError("overlay render semantics are incomplete")
    return result


def rebuild_overlay_v3_request(
    execution_request: Mapping[str, Any],
    *,
    resolved_asset_versions: Mapping[str, Mapping[str, Any]],
    artifact_root: Path | str,
    font_asset_authority: Any | None = None,
) -> dict[str, Any]:
    """Rebuild and remeasure the exact standalone V3 overlay request."""

    request = validate_overlay_execution_request(execution_request)
    root = Path(artifact_root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise OverlayAssetResolutionError("artifact root is invalid")
    source = request["overlaySpec"]
    base_ref = source.get("basePlateAssetVersionRef")
    overlay_ref = source.get(
        "fontAssetVersionRef" if request["effectMode"] == NAMEPLATE_TEXT else "markAssetVersionRef"
    )
    if not isinstance(resolved_asset_versions, Mapping) or set(resolved_asset_versions) != {base_ref, overlay_ref}:
        raise OverlayAssetResolutionError("resolved AssetVersion set is not exact")
    base = _resolved(resolved_asset_versions[base_ref], _BASE_FIELDS, "resolved basePlate")
    overlay_fields = _FONT_FIELDS if request["effectMode"] == NAMEPLATE_TEXT else _MARK_FIELDS
    resolved_overlay = _resolved(resolved_asset_versions[overlay_ref], overlay_fields, "resolved overlayAsset")
    base_claims = {
        "assetVersionRef": source.get("basePlateAssetVersionRef"),
        "assetVersionDigest": source.get("basePlateAssetVersionDigest"),
        "fileDigest": source.get("basePlateFileDigest"),
        "pixelDigest": source.get("basePlatePixelDigest"),
    }
    if any(base[field] != expected for field, expected in base_claims.items()):
        raise OverlayAssetResolutionError("basePlate binding is stale")
    if request["effectMode"] == NAMEPLATE_TEXT:
        claims = {
            "assetVersionRef": source.get("fontAssetVersionRef"),
            "assetVersionDigest": source.get("fontAssetVersionDigest"),
            "fileDigest": source.get("fontFileDigest"),
            "validationRef": source.get("fontTechnicalValidationRef"),
            "validationDigest": source.get("fontTechnicalValidationDigest"),
            "licenseBindingRef": source.get("fontLicenseBindingVersionRef"),
            "licenseBindingDigest": source.get("fontLicenseBindingVersionDigest"),
        }
    else:
        claims = {
            "assetVersionRef": source.get("markAssetVersionRef"),
            "assetVersionDigest": source.get("markAssetVersionDigest"),
            "fileDigest": source.get("markFileDigest"),
            "pixelDigest": source.get("markPixelDigest"),
        }
    if any(resolved_overlay[field] != expected for field, expected in claims.items()):
        raise OverlayAssetResolutionError("overlayAsset binding is stale")
    overlay = (
        _stage_current_font(
            root=root, request=request, resolved=resolved_overlay,
            font_asset_authority=font_asset_authority,
        )
        if request["effectMode"] == NAMEPLATE_TEXT
        else resolved_overlay
    )
    try:
        width = _integer(base["width"], "base.width", 2, 16_384)
        height = _integer(base["height"], "base.height", 2, 16_384)
        frame_count = _integer(base["frameCount"], "base.frameCount", 1, 10_000_000)
        _integer(base["frameRate"], "base.frameRate", 1, 240)
    except OverlayRequestValidationError as exc:
        raise OverlayAssetResolutionError("base media facts are invalid") from exc
    if (
        width % 2 or height % 2 or base["pixelFormat"] != "yuv420p"
        or base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or source.get("frameRangeEndExclusive", frame_count + 1) > frame_count
    ):
        raise OverlayAssetResolutionError("base media contract is unsupported")
    base_path = _server_file(root, base["storageKey"], label="resolved basePlate")
    overlay_path = _server_file(root, overlay["storageKey"], label="resolved overlayAsset")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise OverlayExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        from services.v3_render_core.masked_surface import _probe_video

        with (
            _PinnedRegularFile(base_path, label="resolved basePlate") as pinned_base,
            _PinnedRegularFile(overlay_path, label="resolved overlayAsset") as pinned_overlay,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            pass_fds = tuple(
                dict.fromkeys(
                    pinned_base.pass_fds + pinned_overlay.pass_fds
                    + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            if file_digest(pinned_base.descriptor_path) != base["fileDigest"]:
                raise OverlayAssetResolutionError("basePlate file digest is stale")
            probe = _probe_video(
                pinned_base.descriptor_path,
                SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                ),
            )
            if (
                probe["width"] != width or probe["height"] != height
                or probe["frameCount"] != frame_count
                or probe["frameRate"].denominator != 1
                or probe["frameRate"].numerator != base["frameRate"]
                or probe["realFrameRate"] != probe["frameRate"]
                or probe["startTime"] != 0
                or probe["duration"] != probe["frameCount"] / probe["frameRate"]
                or probe["pixelFormat"] != base["pixelFormat"]
            ):
                raise OverlayAssetResolutionError("basePlate media facts are stale")
            base_pixels = decoded_frame_pixel_digest_metadata(
                pinned_base.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            if (
                base_pixels.get("decodedFramePixelDigest") != base["pixelDigest"]
                or base_pixels.get("decodedFramePixelDigestSpec") != base["pixelDigestSpec"]
                or base_pixels.get("width") != width or base_pixels.get("height") != height
                or base_pixels.get("frameCount") != frame_count
            ):
                raise OverlayAssetResolutionError("basePlate decoded-frame identity is stale")
            if file_digest(pinned_overlay.descriptor_path) != overlay["fileDigest"]:
                raise OverlayAssetResolutionError("overlayAsset file digest is stale")
            if request["effectMode"] == FACE_MARK_COMPENSATION:
                with tempfile.TemporaryDirectory(
                    prefix=".held-mark-", dir=root
                ) as alias_root:
                    alias = Path(alias_root) / "held-mark.png"
                    os.symlink(pinned_overlay.descriptor_path, alias)
                    mark = image_digest_metadata(
                        alias,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=pass_fds,
                    )
                if (
                    mark.get("pixel_digest") != overlay["pixelDigest"]
                    or mark.get("pixel_digest_spec") != overlay["pixelDigestSpec"]
                    or mark.get("pixel_mode") != overlay["pixelMode"]
                    or mark.get("width") != overlay["width"] or mark.get("height") != overlay["height"]
                    or overlay["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC or overlay["pixelMode"] != "RGBA"
                ):
                    raise OverlayAssetResolutionError("mark decoded-pixel identity is stale")
            pinned_base.require_stable(); pinned_overlay.require_stable()
            ffmpeg.require_stable(); ffprobe.require_stable()
    except OverlayAssetResolutionError:
        raise
    except DigestError as exc:
        raise OverlayAssetResolutionError("overlay inputs could not be remeasured") from exc
    result = _seal(
        {
            "schemaVersion": OVERLAY_V3_REQUEST_SCHEMA_VERSION,
            "v5ExecutionRequestRef": request["executionRequestRef"],
            "v5ExecutionRequestDigest": request["payloadDigest"],
            "workspaceRef": request["workspaceRef"],
            "productionRunRef": request["productionRunRef"],
            "requirementRef": request["requirementRef"],
            "requirementDigest": request["requirementDigest"],
            "effectMode": request["effectMode"],
            "basePlate": base,
            "overlayAsset": overlay,
            "overlaySpec": _semantic_spec(request),
            "output": {
                "width": width, "height": height, "frameCount": frame_count,
                "frameRate": base["frameRate"], "pixelFormat": "yuv420p",
                "container": "mp4", "videoCodec": "h264",
            },
            "publicationAllowed": False,
        }
    )
    if set(result) != _V3_FIELDS:
        raise OverlayExecutionError("derived V3 request fields are invalid")
    return result


def _evidence_ref(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + sha256(_canonical(value)).hexdigest()[:32]


def _verify_sealed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = _raw_digest(result.pop("payloadDigest"), f"{label}.payloadDigest")
    if supplied != sha256(_canonical(result)).hexdigest():
        raise OverlayExecutionError(f"{label} seal is stale")
    result["payloadDigest"] = supplied
    return result


def validate_overlay_runtime_evidence(value: Any) -> dict[str, Any]:
    result = _verify_sealed(value, _RUNTIME_FIELDS, "overlay runtime evidence")
    if (
        result["schemaVersion"] != OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] not in OVERLAY_EFFECT_MODES
        or result["rendererIdentity"] != OVERLAY_RENDERER_IDENTITY
        or result["rendererVersion"] != OVERLAY_RENDERER_VERSION
        or result["gpuUsed"] is not False or result["publicationAllowed"] is not False
    ):
        raise OverlayExecutionError("overlay runtime evidence authority is invalid")
    for field in ("runtimeEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "executionRequestRef"):
        _ref(result[field], field)
    for field in ("requirementDigest", "executionRequestDigest", "v3ExecutionRequestDigest"):
        _raw_digest(result[field], field)
    _prefixed_digest(result["executionManifestDigest"], "executionManifestDigest")
    expected = _evidence_ref(
        "m13-overlay-runtime-evidence-",
        {key: result[key] for key in ("v3ExecutionRequestDigest", "rendererIdentity", "rendererVersion", "ffmpegIdentity", "executionManifestDigest")},
    )
    if result["runtimeEvidenceRef"] != expected:
        raise OverlayExecutionError("runtimeEvidenceRef derivation is stale")
    return result


def validate_overlay_artifact_evidence(value: Any, *, runtime_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = _verify_sealed(value, _ARTIFACT_FIELDS, "overlay artifact evidence")
    if (
        result["schemaVersion"] != OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION
        or result["effectMode"] not in OVERLAY_EFFECT_MODES
        or result["provenance"] != OVERLAY_PROVENANCE
        or result["publicationAllowed"] is not False
    ):
        raise OverlayExecutionError("overlay artifact evidence authority is invalid")
    for field in ("artifactEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "executionRequestRef", "runtimeEvidenceRef"):
        _ref(result[field], field)
    for field in ("requirementDigest", "executionRequestDigest", "v3ExecutionRequestDigest", "runtimeEvidenceDigest"):
        _raw_digest(result[field], field)
    if not isinstance(result["outputMediaProbe"], Mapping) or set(result["outputMediaProbe"]) != _OUTPUT_FIELDS:
        raise OverlayExecutionError("artifact media probe is invalid")
    if not isinstance(result["outputDigest"], Mapping) or set(result["outputDigest"]) != _OUTPUT_DIGEST_FIELDS:
        raise OverlayExecutionError("artifact output digest is invalid")
    expected = _evidence_ref(
        "m13-overlay-artifact-evidence-",
        {"v3ExecutionRequestDigest": result["v3ExecutionRequestDigest"], "fileDigest": result["outputDigest"]["fileDigest"], "runtimeEvidenceDigest": result["runtimeEvidenceDigest"]},
    )
    if result["artifactEvidenceRef"] != expected:
        raise OverlayExecutionError("artifactEvidenceRef derivation is stale")
    if runtime_evidence is not None:
        runtime = validate_overlay_runtime_evidence(runtime_evidence)
        for field in ("workspaceRef", "productionRunRef", "requirementRef", "requirementDigest", "executionRequestRef", "executionRequestDigest", "v3ExecutionRequestDigest", "effectMode"):
            if runtime[field] != result[field]:
                raise OverlayExecutionError("overlay evidence lineage is crossed")
        if runtime["runtimeEvidenceRef"] != result["runtimeEvidenceRef"] or runtime["payloadDigest"] != result["runtimeEvidenceDigest"]:
            raise OverlayExecutionError("overlay runtime binding is stale")
    return result


def _expected_output_key(request: Mapping[str, Any]) -> str:
    workspace = sha256(request["workspaceRef"].encode()).hexdigest()[:20]
    run = sha256(request["productionRunRef"].encode()).hexdigest()[:20]
    return str(PurePosixPath(workspace, run, "deterministic-overlays", f"overlay-{request['payloadDigest']}.mp4"))


def _validate_v3_result(value: Any, *, request: Mapping[str, Any], artifact_root: Path) -> dict[str, Any]:
    try:
        result = _closed(value, _V3_RESULT_FIELDS, "V3 overlay result")
    except OverlayRequestValidationError as exc:
        raise OverlayExecutionError("V3 overlay result fields are invalid") from exc
    for field in ("v5ExecutionRequestRef", "v5ExecutionRequestDigest", "requirementRef", "requirementDigest", "effectMode"):
        expected = request[field]
        if result[field] != expected:
            raise OverlayExecutionError("V3 overlay result lineage is stale")
    if result["v3ExecutionRequestDigest"] != request["payloadDigest"] or result["publicationAllowed"] is not False:
        raise OverlayExecutionError("V3 overlay result request binding is stale")
    if result["outputStorageKey"] != _expected_output_key(request):
        raise OverlayExecutionError("V3 overlay output key is stale")
    path = _server_file(artifact_root, result["outputStorageKey"], label="V3 overlay output")
    if result["internalPath"] != str(path):
        raise OverlayExecutionError("V3 overlay output file facts are stale")
    if result["outputMediaProbe"] != request["output"]:
        raise OverlayExecutionError("V3 overlay output probe is stale")
    output = result["outputDigest"]
    if not isinstance(output, Mapping) or set(output) != _OUTPUT_DIGEST_FIELDS:
        raise OverlayExecutionError("V3 overlay output digest fields are invalid")
    _prefixed_digest(output["fileDigest"], "output.fileDigest")
    _prefixed_digest(output["decodedFramePixelDigest"], "output.decodedFramePixelDigest")
    _prefixed_digest(result["executionManifestDigest"], "executionManifestDigest")
    runtime = {
        "ffmpegIdentity": result["ffmpegIdentity"],
        "rendererIdentity": result["rendererIdentity"],
        "rendererVersion": result["rendererVersion"],
        "executionManifestDigest": result["executionManifestDigest"],
    }
    if (
        result["rendererIdentity"] != OVERLAY_RENDERER_IDENTITY
        or result["rendererVersion"] != OVERLAY_RENDERER_VERSION
        or result["runtimeEvidenceDigest"] != "sha256:" + sha256(_canonical(runtime)).hexdigest()
    ):
        raise OverlayExecutionError("V3 overlay runtime identity is stale")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise OverlayExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        from services.v3_render_core.masked_surface import _probe_video

        with (
            _PinnedRegularFile(path, label="V3 overlay output") as pinned,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            if os.fstat(pinned.descriptor).st_size != result["outputByteSize"]:
                raise OverlayExecutionError("V3 overlay output byte size is stale")
            pass_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            if file_digest(pinned.descriptor_path) != output["fileDigest"]:
                raise OverlayExecutionError("V3 overlay output file digest is stale")
            probe = _probe_video(
                pinned.descriptor_path,
                SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                ),
            )
            if (
                probe["width"] != request["output"]["width"]
                or probe["height"] != request["output"]["height"]
                or probe["frameCount"] != request["output"]["frameCount"]
                or probe["frameRate"].denominator != 1
                or probe["frameRate"].numerator != request["output"]["frameRate"]
                or probe["realFrameRate"] != probe["frameRate"]
                or probe["startTime"] != 0
                or probe["duration"] != probe["frameCount"] / probe["frameRate"]
                or probe["pixelFormat"] != "yuv420p"
                or probe["videoCodec"] != "h264"
                or "mp4" not in str(probe["formatName"]).split(",")
            ):
                raise OverlayExecutionError("V3 overlay output probe is stale")
            measured = decoded_frame_pixel_digest_metadata(
                pinned.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            pinned.require_stable(); ffmpeg.require_stable(); ffprobe.require_stable()
    except OverlayExecutionError:
        raise
    except (DigestError, RenderArtifactError) as exc:
        raise OverlayExecutionError("V3 overlay output cannot be remeasured") from exc
    if (
        measured.get("fileDigest") != output["fileDigest"]
        or measured.get("decodedFramePixelDigest") != output["decodedFramePixelDigest"]
        or measured.get("decodedFramePixelDigestSpec") != output["decodedFramePixelDigestSpec"]
        or any(output[name] != request["output"][name] for name in ("width", "height", "frameCount", "frameRate"))
        or output["fileDigestAlgorithm"] != "sha256"
        or output["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or output["pixelMode"] != "RGBA"
    ):
        raise OverlayExecutionError("V3 overlay output content is stale")
    return result


def _build_evidence(*, v5: Mapping[str, Any], v3: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    runtime = _seal(
        {
            "schemaVersion": OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION,
            "runtimeEvidenceRef": _evidence_ref(
                "m13-overlay-runtime-evidence-",
                {key: value for key, value in {
                    "v3ExecutionRequestDigest": v3["payloadDigest"],
                    "rendererIdentity": result["rendererIdentity"],
                    "rendererVersion": result["rendererVersion"],
                    "ffmpegIdentity": result["ffmpegIdentity"],
                    "executionManifestDigest": result["executionManifestDigest"],
                }.items()},
            ),
            "workspaceRef": v5["workspaceRef"], "productionRunRef": v5["productionRunRef"],
            "requirementRef": v5["requirementRef"], "requirementDigest": v5["requirementDigest"],
            "executionRequestRef": v5["executionRequestRef"], "executionRequestDigest": v5["payloadDigest"],
            "v3ExecutionRequestDigest": v3["payloadDigest"], "effectMode": v5["effectMode"],
            "rendererIdentity": result["rendererIdentity"], "rendererVersion": result["rendererVersion"],
            "ffmpegIdentity": result["ffmpegIdentity"], "executionManifestDigest": result["executionManifestDigest"],
            "gpuUsed": False, "publicationAllowed": False,
        }
    )
    artifact_identity = {
        "v3ExecutionRequestDigest": v3["payloadDigest"],
        "fileDigest": result["outputDigest"]["fileDigest"],
        "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    artifact = _seal(
        {
            "schemaVersion": OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION,
            "artifactEvidenceRef": _evidence_ref("m13-overlay-artifact-evidence-", artifact_identity),
            "workspaceRef": v5["workspaceRef"], "productionRunRef": v5["productionRunRef"],
            "requirementRef": v5["requirementRef"], "requirementDigest": v5["requirementDigest"],
            "executionRequestRef": v5["executionRequestRef"], "executionRequestDigest": v5["payloadDigest"],
            "v3ExecutionRequestDigest": v3["payloadDigest"], "effectMode": v5["effectMode"],
            "outputByteSize": result["outputByteSize"], "outputMediaProbe": deepcopy(result["outputMediaProbe"]),
            "outputDigest": deepcopy(result["outputDigest"]), "runtimeEvidenceRef": runtime["runtimeEvidenceRef"],
            "runtimeEvidenceDigest": runtime["payloadDigest"], "provenance": OVERLAY_PROVENANCE,
            "publicationAllowed": False,
        }
    )
    runtime = validate_overlay_runtime_evidence(runtime)
    artifact = validate_overlay_artifact_evidence(artifact, runtime_evidence=runtime)
    bindings = {
        "workspaceRef": v5["workspaceRef"], "productionRunRef": v5["productionRunRef"],
        "requirementRef": v5["requirementRef"], "requirementDigest": v5["requirementDigest"],
        "executionRequestRef": v5["executionRequestRef"], "executionRequestDigest": v5["payloadDigest"],
        "artifactEvidenceRef": artifact["artifactEvidenceRef"], "artifactEvidenceDigest": artifact["payloadDigest"],
        "runtimeEvidenceRef": runtime["runtimeEvidenceRef"], "runtimeEvidenceDigest": runtime["payloadDigest"],
    }
    if set(bindings) != _EVIDENCE_BINDING_FIELDS:
        raise OverlayExecutionError("overlay evidence bindings are invalid")
    return {
        "artifactEvidence": artifact,
        "runtimeEvidence": runtime,
        "evidenceBindings": bindings,
    }


class V4DeterministicOverlayExecutor:
    """Subordinate V4 executor; it creates no Asset or identity authority."""

    def __init__(
        self,
        artifact_root: Path | str,
        v3_executor: Any,
        *,
        font_asset_authority: Any | None = None,
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise OverlayAssetResolutionError("artifact root is invalid")
        if not callable(getattr(v3_executor, "execute", None)):
            raise OverlayExecutionError("V3 overlay executor is required")
        self.v3_executor = v3_executor
        self.font_asset_authority = font_asset_authority

    @classmethod
    def from_artifact_root(
        cls,
        artifact_root: Path | str,
        *,
        font_asset_authority: Any | None = None,
    ) -> "V4DeterministicOverlayExecutor":
        from services.v3_render_core.deterministic_overlays import DeterministicOverlayExecutor
        root = Path(artifact_root).resolve()
        return cls(
            root,
            DeterministicOverlayExecutor(root),
            font_asset_authority=font_asset_authority,
        )

    def execute(self, execution_request: Mapping[str, Any], *, resolved_asset_versions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        v5 = validate_overlay_execution_request(execution_request)
        v3 = rebuild_overlay_v3_request(
            v5,
            resolved_asset_versions=resolved_asset_versions,
            artifact_root=self.artifact_root,
            font_asset_authority=self.font_asset_authority,
        )
        try:
            raw = self.v3_executor.execute(v3)
        except OverlayExecutionError:
            raise
        except Exception as exc:
            raise OverlayExecutionError("V3 deterministic overlay execution failed") from exc
        result = _validate_v3_result(raw, request=v3, artifact_root=self.artifact_root)
        return _build_evidence(v5=v5, v3=v3, result=result)


def inspect_deterministic_overlay_image(artifact_root: Path | str, asset: Mapping[str, Any]) -> dict[str, Any]:
    """Measure one caller-path-free canonical mark through held file/runtime FDs."""

    fields = frozenset({"assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest", "mediaType", "byteSize"})
    value = _closed(asset, fields, "overlay image inspection input")
    _ref(value["assetVersionRef"], "assetVersionRef")
    _raw_digest(value["assetVersionDigest"], "assetVersionDigest")
    _prefixed_digest(value["fileDigest"], "fileDigest")
    _integer(value["byteSize"], "byteSize", 1, 1_000_000_000)
    root = Path(artifact_root).resolve()
    path = _server_file(root, value["storageKey"], label="overlay image")
    if value["mediaType"] != "image/png" or path.stat().st_size != value["byteSize"]:
        raise OverlayAssetResolutionError("overlay image media facts are stale")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise OverlayExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        with (
            _PinnedRegularFile(path, label="overlay image") as pinned,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            if file_digest(pinned.descriptor_path) != value["fileDigest"]:
                raise OverlayAssetResolutionError("overlay image file digest is stale")
            combined_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            with tempfile.TemporaryDirectory(
                prefix=".held-mark-", dir=root
            ) as alias_root:
                alias = Path(alias_root) / "held-mark.png"
                os.symlink(pinned.descriptor_path, alias)
                facts = image_digest_metadata(
                    alias, ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=combined_fds,
                )
            pinned.require_stable(); ffmpeg.require_stable(); ffprobe.require_stable()
    except (DigestError, RenderArtifactError) as exc:
        raise OverlayAssetResolutionError("overlay image inspection failed") from exc
    return {
        "assetVersionRef": value["assetVersionRef"],
        "assetVersionDigest": value["assetVersionDigest"],
        "fileDigest": value["fileDigest"],
        "pixelDigest": facts["pixel_digest"],
        "pixelDigestSpec": facts["pixel_digest_spec"],
        "pixelMode": facts["pixel_mode"],
        "width": facts["width"], "height": facts["height"],
    }


def inspect_deterministic_overlay_video(
    artifact_root: Path | str,
    asset: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure one caller-path-free video through held file/runtime FDs."""

    from services.v3_render_core.masked_surface import _probe_video

    fields = frozenset(
        {
            "assetVersionRef", "assetVersionDigest", "storageKey",
            "fileDigest", "mediaType", "byteSize",
        }
    )
    value = _closed(asset, fields, "overlay video inspection input")
    _ref(value["assetVersionRef"], "assetVersionRef")
    _raw_digest(value["assetVersionDigest"], "assetVersionDigest")
    _prefixed_digest(value["fileDigest"], "fileDigest")
    _integer(value["byteSize"], "byteSize", 1, 4_000_000_000)
    root = Path(artifact_root).resolve()
    path = _server_file(root, value["storageKey"], label="overlay video")
    if value["mediaType"] != "video/mp4" or path.stat().st_size != value["byteSize"]:
        raise OverlayAssetResolutionError("overlay video media facts are stale")
    ffmpeg_path, ffprobe_path = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if ffmpeg_path is None or ffprobe_path is None:
        raise OverlayExecutionError("pinned FFmpeg runtime is unavailable")
    try:
        with (
            _PinnedRegularFile(path, label="overlay video") as pinned,
            _PinnedRuntimeBinary(Path(ffmpeg_path).resolve(), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(Path(ffprobe_path).resolve(), label="FFprobe") as ffprobe,
        ):
            if file_digest(pinned.descriptor_path) != value["fileDigest"]:
                raise OverlayAssetResolutionError("overlay video file digest is stale")
            combined_fds = tuple(
                dict.fromkeys(
                    pinned.pass_fds + ffmpeg.pass_fds + ffprobe.pass_fds
                )
            )
            probe = _probe_video(
                pinned.descriptor_path,
                SimpleNamespace(
                    executable_path=ffprobe.executable_path,
                    pass_fds=combined_fds,
                ),
            )
            if (
                probe["frameRate"].denominator != 1
                or probe["realFrameRate"] != probe["frameRate"]
                or probe["startTime"] != 0
                or probe["duration"]
                != probe["frameCount"] / probe["frameRate"]
                or probe["pixelFormat"] != "yuv420p"
                or probe["videoCodec"] != "h264"
                or "mp4" not in str(probe["formatName"]).split(",")
            ):
                raise OverlayAssetResolutionError(
                    "overlay video must be exact CFR yuv420p H.264 MP4"
                )
            pixels = decoded_frame_pixel_digest_metadata(
                pinned.descriptor_path,
                ffmpeg_path=ffmpeg.executable_path,
                ffprobe_path=ffprobe.executable_path,
                pass_fds=combined_fds,
            )
            pinned.require_stable(); ffmpeg.require_stable(); ffprobe.require_stable()
    except OverlayAssetResolutionError:
        raise
    except (DigestError, RenderArtifactError) as exc:
        raise OverlayAssetResolutionError("overlay video inspection failed") from exc
    if (
        pixels.get("fileDigest") != value["fileDigest"]
        or pixels.get("width") != probe["width"]
        or pixels.get("height") != probe["height"]
        or pixels.get("frameCount") != probe["frameCount"]
        or pixels.get("decodedFramePixelDigestSpec")
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
    ):
        raise OverlayAssetResolutionError("overlay video decoded identity is stale")
    return {
        "assetVersionRef": value["assetVersionRef"],
        "assetVersionDigest": value["assetVersionDigest"],
        "fileDigest": value["fileDigest"],
        "pixelDigest": pixels["decodedFramePixelDigest"],
        "pixelDigestSpec": pixels["decodedFramePixelDigestSpec"],
        "width": probe["width"], "height": probe["height"],
        "frameCount": probe["frameCount"],
        "frameRate": probe["frameRate"].numerator,
        "pixelFormat": probe["pixelFormat"],
    }


__all__ = [
    "FACE_MARK_COMPENSATION", "NAMEPLATE_TEXT", "OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "OVERLAY_EFFECT_MODES", "OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION", "OVERLAY_PROVENANCE",
    "OVERLAY_RENDERER_IDENTITY", "OVERLAY_RENDERER_VERSION", "OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION",
    "OVERLAY_V3_REQUEST_SCHEMA_VERSION", "OverlayAssetResolutionError", "OverlayExecutionError",
    "OverlayRequestValidationError", "V4DeterministicOverlayExecutor", "inspect_deterministic_overlay_image",
    "inspect_deterministic_overlay_video",
    "rebuild_overlay_v3_request", "validate_overlay_artifact_evidence",
    "validate_overlay_execution_request", "validate_overlay_runtime_evidence",
]
