"""Closed M13-E3 contracts and durable evidence chains for overlays.

Callers may select only existing source/asset refs and closed render parameters.
Resolved text, FONT lineage, identity lineage, and mark content facts are injected
by server-held current readers and are sealed into immutable Requirements.
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

NAMEPLATE_TEXT = "NAMEPLATE_TEXT"
FACE_MARK_COMPENSATION = "FACE_MARK_COMPENSATION"
OVERLAY_EFFECT_MODES = frozenset({NAMEPLATE_TEXT, FACE_MARK_COMPENSATION})
NAMEPLATE_TEXT_REQUIREMENT_SCHEMA_VERSION = "v5.m13-nameplate-text-requirement.v1"
FACE_MARK_COMPENSATION_REQUIREMENT_SCHEMA_VERSION = "v5.m13-face-mark-compensation-requirement.v1"
OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION = "v5.m13-overlay-execution-request.v1"
OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION = "v4.m13-overlay-artifact-evidence.v1"
OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION = "v4.m13-overlay-runtime-evidence.v1"
NAMEPLATE_TEXT_RESULT_SCHEMA_VERSION = "v5.m13-nameplate-text-result.v1"
FACE_MARK_COMPENSATION_RESULT_SCHEMA_VERSION = "v5.m13-face-mark-compensation-result.v1"

NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND = "NameplateTextRequirement"
FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND = "FaceMarkCompensationRequirement"
OVERLAY_EXECUTION_REQUEST_RECORD_KIND = "OverlayExecutionRequest"
OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND = "OverlayArtifactEvidence"
OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND = "OverlayRuntimeEvidence"
NAMEPLATE_TEXT_RESULT_RECORD_KIND = "NameplateTextResult"
FACE_MARK_COMPENSATION_RESULT_RECORD_KIND = "FaceMarkCompensationResult"

OVERLAY_RENDERER_IDENTITY = "v3.deterministic-overlay-ffmpeg"
OVERLAY_RENDERER_VERSION = "1"
OVERLAY_EVIDENCE_PROVENANCE = "LOCAL_EVIDENCE"
DECODED_FRAME_PIXEL_DIGEST_SPEC = (
    "RGBA8/display-identity/frame-major/row-major/"
    "width-height-frame-count-bound/v2"
)

_RAW_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CONTENT_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FORBIDDEN = (
    "path", "storage", "filter", "argv", "argument", "expression",
    "random", "seed", "shell", "command", "html", "svg", "css",
    "model", "network", "environment",
)
_INTERPOLATIONS = frozenset({"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"})
_BLEND_MODES = frozenset({"NORMAL", "MULTIPLY", "SCREEN", "OVERLAY", "ADD", "DARKEN", "LIGHTEN"})

_COMMON = frozenset({
    "workspaceRef", "productionRunRef", "requirementRef", "effectMode",
    "targetShotRef", "targetShotVersionRef", "targetShotVersionDigest",
    "basePlateAssetVersionRef", "basePlateAssetVersionDigest",
    "basePlateFileDigest", "basePlatePixelDigest",
    "frameRangeStartInclusive", "frameRangeEndExclusive", "blendMode", "layer",
})
_COMMON_PUBLIC = _COMMON - frozenset({"basePlateFileDigest", "basePlatePixelDigest"})
_NAMEPLATE_PUBLIC = _COMMON_PUBLIC | frozenset({
    "textSourceKind", "textSourceRef", "textSourceVersionRef", "textSourceDigest",
    "fontAssetVersionRef", "fontAssetVersionDigest", "layout",
    "positionKeyframes", "scaleKeyframes", "rotationKeyframes",
    "perspectiveKeyframes", "opacityCurve", "trackingKeyframes",
})
_NAMEPLATE_INTERNAL = _NAMEPLATE_PUBLIC | frozenset({
    "basePlateFileDigest", "basePlatePixelDigest",
    "resolvedText", "resolvedTextDigest", "language", "fontFileDigest",
    "fontTechnicalValidationRef", "fontTechnicalValidationDigest",
    "fontLicenseBindingVersionRef", "fontLicenseBindingVersionDigest",
})
_FACE_PUBLIC = _COMMON_PUBLIC | frozenset({
    "characterRef", "markType", "markAssetVersionRef", "markAssetVersionDigest",
    "faceRegion", "trackingSourceKind", "trackingKeyframes", "scaleKeyframes",
    "rotationKeyframes", "opacityCurve", "occlusionPolicy",
})
_FACE_INTERNAL = _FACE_PUBLIC | frozenset({
    "basePlateFileDigest", "basePlatePixelDigest",
    "identityReferenceRef", "identityReferenceVersionRef",
    "identityReferenceContentDigest", "identityReferenceProjectionDigest",
    "identityLockRef", "identityLockVersionRef", "identityLockDigest",
    "markFileDigest", "markPixelDigest",
})
_LAYOUT = frozenset({"writingMode", "alignment", "fontSizeMilliPixels", "letterSpacingMilliPixels", "lineSpacingMilliPixels", "maxWidthPixels", "maxHeightPixels"})
_POINT = frozenset({"frame", "xPermille", "yPermille", "interpolation"})
_SCALE = _POINT
_ROTATION = frozenset({"frame", "degreesMilli", "interpolation"})
_OPACITY = frozenset({"frame", "valuePermille", "interpolation"})
_PERSPECTIVE = frozenset({"frame", "quadPermille", "interpolation"})
_TEXT_RESOLUTION = frozenset({"textSourceKind", "textSourceRef", "textSourceVersionRef", "textSourceDigest", "resolvedText", "resolvedTextDigest", "language"})
_FONT_RESOLUTION = frozenset({"fontAssetVersionRef", "fontAssetVersionDigest", "fontFileDigest", "fontTechnicalValidationRef", "fontTechnicalValidationDigest", "fontLicenseBindingVersionRef", "fontLicenseBindingVersionDigest"})
_MARK_RESOLUTION = frozenset({"markAssetVersionRef", "markAssetVersionDigest", "markFileDigest", "markPixelDigest"})
_BASE_RESOLUTION = frozenset({"basePlateAssetVersionRef", "basePlateAssetVersionDigest", "basePlateFileDigest", "basePlatePixelDigest"})
_REQUEST = frozenset({"schemaVersion", "executionRequestRef", "workspaceRef", "productionRunRef", "requirementRef", "requirementDigest", "effectMode", "overlaySpec", "publicationAllowed", "payloadDigest"})
_RUNTIME = frozenset({"schemaVersion", "runtimeEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "requirementDigest", "executionRequestRef", "executionRequestDigest", "v3ExecutionRequestDigest", "effectMode", "rendererIdentity", "rendererVersion", "ffmpegIdentity", "executionManifestDigest", "gpuUsed", "publicationAllowed", "payloadDigest"})
_PROBE = frozenset({"width", "height", "frameCount", "frameRate", "pixelFormat", "container", "videoCodec"})
_OUTPUT_DIGEST = frozenset({"fileDigest", "fileDigestAlgorithm", "decodedFramePixelDigest", "decodedFramePixelDigestSpec", "pixelMode", "width", "height", "frameCount", "frameRate"})
_ARTIFACT = frozenset({"schemaVersion", "artifactEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "requirementDigest", "executionRequestRef", "executionRequestDigest", "v3ExecutionRequestDigest", "effectMode", "outputByteSize", "outputMediaProbe", "outputDigest", "runtimeEvidenceRef", "runtimeEvidenceDigest", "provenance", "publicationAllowed", "payloadDigest"})
_BINDINGS = frozenset({"workspaceRef", "productionRunRef", "requirementRef", "requirementDigest", "executionRequestRef", "executionRequestDigest", "artifactEvidenceRef", "artifactEvidenceDigest", "runtimeEvidenceRef", "runtimeEvidenceDigest"})
_RESULT = frozenset({"schemaVersion", "workspaceRef", "productionRunRef", "resultRef", "effectMode", "requirementRef", "requirementDigest", "executionRequestRef", "executionRequestDigest", "artifactEvidenceRef", "artifactEvidenceDigest", "runtimeEvidenceRef", "runtimeEvidenceDigest", "outputFileDigest", "outputDecodedFramePixelDigest", "outputMediaProbe", "state", "assetAdmissionState", "masterState", "exportState", "publicationAllowed", "payloadDigest"})


class DeterministicOverlayContractError(EpisodeProductionError):
    code = "m13_deterministic_overlay_contract_invalid"


class DeterministicOverlayStaleInputError(StaleInputError):
    code = "m13_deterministic_overlay_source_stale"


class DeterministicOverlayJournalError(RepositoryUnavailableError):
    code = "m13_deterministic_overlay_journal_invalid"


def _reject(value: Any) -> None:
    if isinstance(value, float):
        raise DeterministicOverlayContractError("float authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or any(part in key.replace("_", "").lower() for part in _FORBIDDEN):
                raise DeterministicOverlayContractError(f"{key!s} is forbidden")
            _reject(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject(item)


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise DeterministicOverlayContractError(f"{label} fields are invalid")
    result = deepcopy(dict(value))
    _reject(result)
    return result


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(value))
    if "payloadDigest" in result:
        raise DeterministicOverlayContractError("payloadDigest is derived")
    _reject(result)
    result["payloadDigest"] = _digest(result)
    return result


def _sealed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    result = _closed(value, fields, label)
    supplied = result.pop("payloadDigest")
    if not isinstance(supplied, str) or _RAW_SHA.fullmatch(supplied) is None or supplied != _digest(result):
        raise DeterministicOverlayStaleInputError(f"{label} payloadDigest is stale")
    result["payloadDigest"] = supplied
    return result


def _ref(value: Any, field: str) -> str:
    try:
        return _required_ref(value, field)
    except EpisodeProductionError as exc:
        raise DeterministicOverlayContractError(f"{field} is invalid") from exc


def _raw(value: Any, field: str) -> str:
    if not isinstance(value, str) or _RAW_SHA.fullmatch(value) is None:
        raise DeterministicOverlayContractError(f"{field} must be a raw sha256")
    return value


def _content(value: Any, field: str) -> str:
    if not isinstance(value, str) or _CONTENT_SHA.fullmatch(value) is None:
        raise DeterministicOverlayContractError(f"{field} must be a sha256 content digest")
    return value


def _integer(value: Any, field: str, minimum: int = 0, maximum: int = 10_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise DeterministicOverlayContractError(f"{field} is invalid")
    return value


def _text(value: Any, field: str, maximum: int = 16_384) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise DeterministicOverlayContractError(f"{field} is invalid")
    return value


def _resolved_text_value(value: Any) -> str:
    result = _text(value, "resolvedText", 16_384)
    if len(result.encode("utf-8")) > 16_384:
        raise DeterministicOverlayContractError("resolvedText exceeds the UTF-8 byte limit")
    return result


def _timestamp(value: Any) -> str:
    text = _text(value, "createdAt", 100)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeterministicOverlayContractError("createdAt is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DeterministicOverlayContractError("createdAt must include timezone")
    return text


def _keyframes(value: Any, fields: frozenset[str], ranges: Mapping[str, tuple[int, int]], label: str, start: int, end: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 4096:
        raise DeterministicOverlayContractError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    prior = -1
    for index, raw in enumerate(value):
        item = _closed(raw, fields, f"{label}[{index}]")
        frame = _integer(item["frame"], f"{label}[{index}].frame")
        if frame < start or frame >= end or frame <= prior or item["interpolation"] not in _INTERPOLATIONS:
            raise DeterministicOverlayContractError(f"{label} is not ordered and in range")
        for field, limits in ranges.items():
            _integer(item[field], f"{label}[{index}].{field}", *limits)
        if "quadPermille" in item:
            quad = item["quadPermille"]
            if not isinstance(quad, list) or len(quad) != 8:
                raise DeterministicOverlayContractError("quadPermille is invalid")
            for coordinate in quad:
                _integer(coordinate, "quadPermille", -4000, 5000)
        prior = frame
        result.append(item)
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise DeterministicOverlayContractError(f"{label} must close the frame range")
    return result


def _require_constant_keyframe_values(value: Sequence[Mapping[str, Any]], fields: tuple[str, ...], label: str) -> None:
    if any(len({item[field] for item in value}) != 1 for field in fields):
        raise DeterministicOverlayContractError(f"{label} animation is unsupported by renderer v1")


@dataclass(frozen=True, slots=True)
class _Contract:
    _value: Mapping[str, Any]
    def as_dict(self) -> dict[str, Any]: return deepcopy(dict(self._value))
    @property
    def payload_digest(self) -> str: return str(self._value["payloadDigest"])
    @property
    def workspace_ref(self) -> str: return str(self._value["workspaceRef"])
    @property
    def production_run_ref(self) -> str: return str(self._value["productionRunRef"])
    @property
    def requirement_ref(self) -> str: return str(self._value["requirementRef"])
    @property
    def effect_mode(self) -> str: return str(self._value["effectMode"])


def _common(result: dict[str, Any], mode: str) -> tuple[int, int]:
    if result["effectMode"] != mode:
        raise DeterministicOverlayContractError("effectMode is invalid")
    for field in ("workspaceRef", "productionRunRef", "requirementRef", "targetShotRef", "targetShotVersionRef", "basePlateAssetVersionRef"):
        _ref(result[field], field)
    for field in ("targetShotVersionDigest", "basePlateAssetVersionDigest"):
        _raw(result[field], field)
    for field in ("basePlateFileDigest", "basePlatePixelDigest"):
        _content(result[field], field)
    start = _integer(result["frameRangeStartInclusive"], "frameRangeStartInclusive")
    end = _integer(result["frameRangeEndExclusive"], "frameRangeEndExclusive", 1, 10_000_001)
    if start >= end:
        raise DeterministicOverlayContractError("frame range is empty")
    if result["blendMode"] != "NORMAL":
        raise DeterministicOverlayContractError("renderer v1 requires NORMAL blendMode")
    _integer(result["layer"], "layer", 0, 1024)
    if result["publicationAllowed"] is not False:
        raise DeterministicOverlayContractError("publicationAllowed must be false")
    return start, end


@dataclass(frozen=True, slots=True)
class NameplateTextRequirement(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "NameplateTextRequirement":
        result = _sealed(value, _NAMEPLATE_INTERNAL | {"schemaVersion", "publicationAllowed", "payloadDigest"}, "NameplateTextRequirement")
        if result["schemaVersion"] != NAMEPLATE_TEXT_REQUIREMENT_SCHEMA_VERSION:
            raise DeterministicOverlayContractError("Nameplate schema is unsupported")
        start, end = _common(result, NAMEPLATE_TEXT)
        if result["textSourceKind"] != "SCRIPT_TEXT":
            raise DeterministicOverlayContractError("only SCRIPT_TEXT is supported")
        for field in ("textSourceRef", "textSourceVersionRef", "fontAssetVersionRef", "fontTechnicalValidationRef", "fontLicenseBindingVersionRef"):
            _ref(result[field], field)
        for field in ("textSourceDigest", "resolvedTextDigest", "fontAssetVersionDigest", "fontFileDigest", "fontTechnicalValidationDigest", "fontLicenseBindingVersionDigest"):
            _raw(result[field], field)
        text = _resolved_text_value(result["resolvedText"])
        if result["resolvedTextDigest"] != _digest({"utf8": text}):
            raise DeterministicOverlayStaleInputError("resolved text is stale")
        if result["language"] != "und":
            raise DeterministicOverlayContractError("SCRIPT_TEXT language must be und")
        layout = _closed(result["layout"], _LAYOUT, "layout")
        if layout["writingMode"] not in {"HORIZONTAL_LTR", "VERTICAL_RTL"} or layout["alignment"] not in {"START", "CENTER", "END"}:
            raise DeterministicOverlayContractError("layout is invalid")
        _integer(layout["fontSizeMilliPixels"], "fontSizeMilliPixels", 1000, 512_000)
        _integer(layout["letterSpacingMilliPixels"], "letterSpacingMilliPixels", -1_000_000, 1_000_000)
        _integer(layout["lineSpacingMilliPixels"], "lineSpacingMilliPixels", 1, 512_000)
        _integer(layout["maxWidthPixels"], "maxWidthPixels", 1, 131_072)
        _integer(layout["maxHeightPixels"], "maxHeightPixels", 1, 131_072)
        if layout["fontSizeMilliPixels"] % 1000 or layout["lineSpacingMilliPixels"] % 1000 or layout["letterSpacingMilliPixels"] != 0:
            raise DeterministicOverlayContractError("renderer v1 requires whole-pixel font/line sizes and zero letter spacing")
        result["layout"] = layout
        result["positionKeyframes"] = _keyframes(result["positionKeyframes"], _POINT, {"xPermille": (0, 1000), "yPermille": (0, 1000)}, "positionKeyframes", start, end)
        result["scaleKeyframes"] = _keyframes(result["scaleKeyframes"], _SCALE, {"xPermille": (1, 4000), "yPermille": (1, 4000)}, "scaleKeyframes", start, end)
        result["rotationKeyframes"] = _keyframes(result["rotationKeyframes"], _ROTATION, {"degreesMilli": (-360000, 360000)}, "rotationKeyframes", start, end)
        result["perspectiveKeyframes"] = _keyframes(result["perspectiveKeyframes"], _PERSPECTIVE, {}, "perspectiveKeyframes", start, end)
        result["opacityCurve"] = _keyframes(result["opacityCurve"], _OPACITY, {"valuePermille": (0, 1000)}, "opacityCurve", start, end)
        result["trackingKeyframes"] = _keyframes(result["trackingKeyframes"], _POINT, {"xPermille": (-1000, 1000), "yPermille": (-1000, 1000)}, "trackingKeyframes", start, end)
        # FFmpeg perspective order is TL, TR, BL, BR.
        identity_quad = [0, 0, 1000, 0, 0, 1000, 1000, 1000]
        if any(item["quadPermille"] != identity_quad for item in result["perspectiveKeyframes"]):
            raise DeterministicOverlayContractError("renderer v1 requires identity perspective")
        _require_constant_keyframe_values(result["scaleKeyframes"], ("xPermille", "yPermille"), "scaleKeyframes")
        _require_constant_keyframe_values(result["rotationKeyframes"], ("degreesMilli",), "rotationKeyframes")
        _require_constant_keyframe_values(result["opacityCurve"], ("valuePermille",), "opacityCurve")
        return cls(result)


@dataclass(frozen=True, slots=True)
class FaceMarkCompensationRequirement(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "FaceMarkCompensationRequirement":
        result = _sealed(value, _FACE_INTERNAL | {"schemaVersion", "publicationAllowed", "payloadDigest"}, "FaceMarkCompensationRequirement")
        if result["schemaVersion"] != FACE_MARK_COMPENSATION_REQUIREMENT_SCHEMA_VERSION:
            raise DeterministicOverlayContractError("FaceMark schema is unsupported")
        start, end = _common(result, FACE_MARK_COMPENSATION)
        for field in ("characterRef", "identityReferenceRef", "identityReferenceVersionRef", "identityLockRef", "identityLockVersionRef", "markAssetVersionRef"):
            _ref(result[field], field)
        for field in ("identityReferenceContentDigest", "identityReferenceProjectionDigest", "identityLockDigest", "markAssetVersionDigest"):
            _raw(result[field], field)
        for field in ("markFileDigest", "markPixelDigest"):
            _content(result[field], field)
        if result["markType"] not in {"MOLE", "SCAR"} or result["faceRegion"] not in {"LEFT_CHEEK", "RIGHT_CHEEK", "LEFT_BROW", "RIGHT_BROW", "NOSE_BRIDGE", "CHIN", "FOREHEAD"}:
            raise DeterministicOverlayContractError("mark semantics are invalid")
        if result["trackingSourceKind"] != "EXPLICIT_KEYFRAMES":
            raise DeterministicOverlayContractError("only explicit tracking keyframes are supported")
        if result["occlusionPolicy"] != "ALWAYS_VISIBLE_WITHIN_TRACK":
            raise DeterministicOverlayContractError("occlusion policy is unsupported by renderer v1")
        result["trackingKeyframes"] = _keyframes(result["trackingKeyframes"], _POINT, {"xPermille": (0, 1000), "yPermille": (0, 1000)}, "trackingKeyframes", start, end)
        result["scaleKeyframes"] = _keyframes(result["scaleKeyframes"], _SCALE, {"xPermille": (1, 4000), "yPermille": (1, 4000)}, "scaleKeyframes", start, end)
        result["rotationKeyframes"] = _keyframes(result["rotationKeyframes"], _ROTATION, {"degreesMilli": (-360000, 360000)}, "rotationKeyframes", start, end)
        result["opacityCurve"] = _keyframes(result["opacityCurve"], _OPACITY, {"valuePermille": (0, 1000)}, "opacityCurve", start, end)
        _require_constant_keyframe_values(result["scaleKeyframes"], ("xPermille", "yPermille"), "scaleKeyframes")
        _require_constant_keyframe_values(result["rotationKeyframes"], ("degreesMilli",), "rotationKeyframes")
        _require_constant_keyframe_values(result["opacityCurve"], ("valuePermille",), "opacityCurve")
        return cls(result)


OverlayRequirement = NameplateTextRequirement | FaceMarkCompensationRequirement


def _resolved_text(value: Any) -> dict[str, Any]:
    result = _closed(value, _TEXT_RESOLUTION, "resolved_text_source")
    if result["textSourceKind"] != "SCRIPT_TEXT" or result["language"] != "und":
        raise DeterministicOverlayContractError("resolved text source is unsupported")
    for field in ("textSourceRef", "textSourceVersionRef"): _ref(result[field], field)
    for field in ("textSourceDigest", "resolvedTextDigest"): _raw(result[field], field)
    if result["resolvedTextDigest"] != _digest({"utf8": _resolved_text_value(result["resolvedText"])}):
        raise DeterministicOverlayStaleInputError("resolved text source is stale")
    return result


def _resolved_font(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and set(value) == _FONT_RESOLUTION:
        result = _closed(value, _FONT_RESOLUTION, "resolved_font")
    elif isinstance(value, Mapping) and set(value) == {"fontAssetVersion", "fontTechnicalValidation", "fontLicenseBindingVersion", "storageBindingRef", "publicationAllowed"}:
        asset, validation, license_value = value["fontAssetVersion"], value["fontTechnicalValidation"], value["fontLicenseBindingVersion"]
        if not all(isinstance(item, Mapping) for item in (asset, validation, license_value)) or value["publicationAllowed"] is not False:
            raise DeterministicOverlayContractError("resolved_font is invalid")
        result = {
            "fontAssetVersionRef": asset.get("assetVersionRef"), "fontAssetVersionDigest": asset.get("payloadDigest"), "fontFileDigest": asset.get("fileDigest"),
            "fontTechnicalValidationRef": validation.get("validationRef"), "fontTechnicalValidationDigest": validation.get("payloadDigest"),
            "fontLicenseBindingVersionRef": license_value.get("licenseBindingVersionRef"), "fontLicenseBindingVersionDigest": license_value.get("payloadDigest"),
        }
        if asset.get("technicalValidationRef") != result["fontTechnicalValidationRef"] or asset.get("technicalValidationDigest") != result["fontTechnicalValidationDigest"] or asset.get("licenseBindingVersionRef") != result["fontLicenseBindingVersionRef"] or asset.get("licenseBindingVersionDigest") != result["fontLicenseBindingVersionDigest"] or validation.get("validationState") != "PASS" or license_value.get("revocationState") != "ACTIVE" or any(license_value.get(field) is not True for field in ("technicalPreviewAllowed", "renderCandidateUseAllowed")):
            raise DeterministicOverlayStaleInputError("resolved FONT lineage is stale")
    else:
        raise DeterministicOverlayContractError("resolved_font fields are invalid")
    for field in ("fontAssetVersionRef", "fontTechnicalValidationRef", "fontLicenseBindingVersionRef"): _ref(result[field], field)
    for field in _FONT_RESOLUTION - {"fontAssetVersionRef", "fontTechnicalValidationRef", "fontLicenseBindingVersionRef"}: _raw(result[field], field)
    return result


def _identity(value: Any, public: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping): raise DeterministicOverlayContractError("identity_projection is invalid")
    required = {"workspaceRef", "productionRunRef", "characterRef", "referenceRef", "referenceVersionRef", "contentDigest", "projectionDigest", "identityLockRef", "identityLockVersionRef", "identityLockDigest"}
    if not required <= set(value): raise DeterministicOverlayContractError("identity_projection fields are invalid")
    if any(value.get(field) != public[field] for field in ("workspaceRef", "productionRunRef", "characterRef")):
        raise DeterministicOverlayStaleInputError("identity projection scope is stale")
    result = {"identityReferenceRef": value["referenceRef"], "identityReferenceVersionRef": value["referenceVersionRef"], "identityReferenceContentDigest": value["contentDigest"], "identityReferenceProjectionDigest": value["projectionDigest"], "identityLockRef": value["identityLockRef"], "identityLockVersionRef": value["identityLockVersionRef"], "identityLockDigest": value["identityLockDigest"]}
    for field in ("identityReferenceRef", "identityReferenceVersionRef", "identityLockRef", "identityLockVersionRef"): _ref(result[field], field)
    for field in ("identityReferenceContentDigest", "identityReferenceProjectionDigest", "identityLockDigest"): _raw(result[field], field)
    return result


def _resolved_media(value: Any, *, prefix: str) -> dict[str, Any]:
    named = _BASE_RESOLUTION if prefix == "basePlate" else _MARK_RESOLUTION
    if not isinstance(value, Mapping):
        raise DeterministicOverlayContractError(f"resolved_{prefix} is invalid")
    if named <= set(value):
        result = {field: deepcopy(value[field]) for field in named}
    elif {"assetVersionRef", "assetVersionDigest", "fileDigest", "pixelDigest"} <= set(value):
        result = {
            f"{prefix}AssetVersionRef": value["assetVersionRef"],
            f"{prefix}AssetVersionDigest": value["assetVersionDigest"],
            f"{prefix}FileDigest": value["fileDigest"],
            f"{prefix}PixelDigest": value["pixelDigest"],
        }
    else:
        raise DeterministicOverlayContractError(f"resolved_{prefix} fields are invalid")
    _ref(result[f"{prefix}AssetVersionRef"], f"{prefix}AssetVersionRef")
    _raw(result[f"{prefix}AssetVersionDigest"], f"{prefix}AssetVersionDigest")
    _content(result[f"{prefix}FileDigest"], f"{prefix}FileDigest")
    _content(result[f"{prefix}PixelDigest"], f"{prefix}PixelDigest")
    return result


def _resolved_base_dimensions(value: Mapping[str, Any]) -> tuple[int, int]:
    if not isinstance(value, Mapping) or "width" not in value or "height" not in value:
        raise DeterministicOverlayContractError("resolved_base media dimensions are required")
    return (
        _integer(value["width"], "resolved_base.width", 1, 131_072),
        _integer(value["height"], "resolved_base.height", 1, 131_072),
    )


def build_nameplate_text_requirement(public_fields: Mapping[str, Any], *, resolved_base: Mapping[str, Any], resolved_text_source: Mapping[str, Any], resolved_font: Mapping[str, Any]) -> NameplateTextRequirement:
    public = _closed(public_fields, _NAMEPLATE_PUBLIC, "Nameplate public Requirement")
    base = _resolved_media(resolved_base, prefix="basePlate"); base_width, base_height = _resolved_base_dimensions(resolved_base); text = _resolved_text(resolved_text_source); font = _resolved_font(resolved_font)
    for field in ("basePlateAssetVersionRef", "basePlateAssetVersionDigest"):
        if public[field] != base[field]: raise DeterministicOverlayStaleInputError("base plate selection is stale")
    for field in ("textSourceKind", "textSourceRef", "textSourceVersionRef", "textSourceDigest"):
        if public[field] != text[field]: raise DeterministicOverlayStaleInputError("TextSource selection is stale")
    for field in ("fontAssetVersionRef", "fontAssetVersionDigest"):
        if public[field] != font[field]: raise DeterministicOverlayStaleInputError("FONT selection is stale")
    if not isinstance(public["layout"], Mapping) or public["layout"].get("maxWidthPixels", base_width + 1) > base_width or public["layout"].get("maxHeightPixels", base_height + 1) > base_height:
        raise DeterministicOverlayContractError("Nameplate layout exceeds the current base plate")
    return NameplateTextRequirement.from_mapping(_seal({"schemaVersion": NAMEPLATE_TEXT_REQUIREMENT_SCHEMA_VERSION, **public, **base, **text, **font, "publicationAllowed": False}))


def build_face_mark_compensation_requirement(public_fields: Mapping[str, Any], *, resolved_base: Mapping[str, Any], identity_projection: Mapping[str, Any], resolved_mark: Mapping[str, Any]) -> FaceMarkCompensationRequirement:
    public = _closed(public_fields, _FACE_PUBLIC, "FaceMark public Requirement")
    base = _resolved_media(resolved_base, prefix="basePlate"); _resolved_base_dimensions(resolved_base); identity = _identity(identity_projection, public); mark = _resolved_media(resolved_mark, prefix="mark")
    for field in ("basePlateAssetVersionRef", "basePlateAssetVersionDigest"):
        if public[field] != base[field]: raise DeterministicOverlayStaleInputError("base plate selection is stale")
    for field in ("markAssetVersionRef", "markAssetVersionDigest"):
        if public[field] != mark[field]: raise DeterministicOverlayStaleInputError("mark selection is stale")
    return FaceMarkCompensationRequirement.from_mapping(_seal({"schemaVersion": FACE_MARK_COMPENSATION_REQUIREMENT_SCHEMA_VERSION, **public, **base, **identity, **mark, "publicationAllowed": False}))


def parse_overlay_requirement(value: Any) -> OverlayRequirement:
    if not isinstance(value, Mapping): raise DeterministicOverlayContractError("Requirement must be an object")
    if value.get("schemaVersion") == NAMEPLATE_TEXT_REQUIREMENT_SCHEMA_VERSION: return NameplateTextRequirement.from_mapping(value)
    if value.get("schemaVersion") == FACE_MARK_COMPENSATION_REQUIREMENT_SCHEMA_VERSION: return FaceMarkCompensationRequirement.from_mapping(value)
    raise DeterministicOverlayContractError("Requirement schema is unsupported")


@dataclass(frozen=True, slots=True)
class OverlayExecutionRequest(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "OverlayExecutionRequest":
        result = _sealed(value, _REQUEST, "OverlayExecutionRequest")
        if result["schemaVersion"] != OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION or result["effectMode"] not in OVERLAY_EFFECT_MODES or result["publicationAllowed"] is not False:
            raise DeterministicOverlayContractError("execution request identity is invalid")
        for field in ("executionRequestRef", "workspaceRef", "productionRunRef", "requirementRef"): _ref(result[field], field)
        _raw(result["requirementDigest"], "requirementDigest")
        if not isinstance(result["overlaySpec"], Mapping): raise DeterministicOverlayContractError("overlaySpec is invalid")
        return cls(result)
    @property
    def execution_request_ref(self) -> str: return str(self._value["executionRequestRef"])


def build_overlay_execution_request(requirement: OverlayRequirement) -> OverlayExecutionRequest:
    if type(requirement) not in {NameplateTextRequirement, FaceMarkCompensationRequirement}: raise DeterministicOverlayContractError("exact overlay Requirement required")
    source = requirement.as_dict()
    excluded = {"schemaVersion", "workspaceRef", "productionRunRef", "requirementRef", "effectMode", "publicationAllowed", "payloadDigest"}
    spec = {key: deepcopy(value) for key, value in source.items() if key not in excluded}
    ref = "overlay-execution-" + _digest({"requirementRef": source["requirementRef"], "requirementDigest": source["payloadDigest"]})[:32]
    return OverlayExecutionRequest.from_mapping(_seal({"schemaVersion": OVERLAY_EXECUTION_REQUEST_SCHEMA_VERSION, "executionRequestRef": ref, "workspaceRef": source["workspaceRef"], "productionRunRef": source["productionRunRef"], "requirementRef": source["requirementRef"], "requirementDigest": source["payloadDigest"], "effectMode": source["effectMode"], "overlaySpec": spec, "publicationAllowed": False}))


def validate_overlay_execution_request_binding(execution_request: OverlayExecutionRequest | Mapping[str, Any], requirement: OverlayRequirement | Mapping[str, Any]) -> OverlayExecutionRequest:
    req = parse_overlay_requirement(requirement) if isinstance(requirement, Mapping) else requirement
    request = OverlayExecutionRequest.from_mapping(execution_request) if isinstance(execution_request, Mapping) else execution_request
    if type(req) not in {NameplateTextRequirement, FaceMarkCompensationRequirement} or type(request) is not OverlayExecutionRequest or request.as_dict() != build_overlay_execution_request(req).as_dict():
        raise DeterministicOverlayStaleInputError("execution request is not the exact Requirement projection")
    return request


def parse_overlay_execution_request(value: Any) -> OverlayExecutionRequest:
    return OverlayExecutionRequest.from_mapping(value)


def _lineage(requirement: OverlayRequirement, request: OverlayExecutionRequest) -> dict[str, Any]:
    return {
        "workspaceRef": requirement.workspace_ref,
        "productionRunRef": requirement.production_run_ref,
        "requirementRef": requirement.requirement_ref,
        "requirementDigest": requirement.payload_digest,
        "executionRequestRef": request.execution_request_ref,
        "executionRequestDigest": request.payload_digest,
        "effectMode": requirement.effect_mode,
    }


def _runtime_ref(value: Mapping[str, Any]) -> str:
    return "m13-overlay-runtime-evidence-" + _digest({
        "v3ExecutionRequestDigest": value["v3ExecutionRequestDigest"],
        "rendererIdentity": value["rendererIdentity"],
        "rendererVersion": value["rendererVersion"],
        "ffmpegIdentity": value["ffmpegIdentity"],
        "executionManifestDigest": value["executionManifestDigest"],
    })[:32]


@dataclass(frozen=True, slots=True)
class OverlayRuntimeEvidence(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "OverlayRuntimeEvidence":
        result = _sealed(value, _RUNTIME, "OverlayRuntimeEvidence")
        if result["schemaVersion"] != OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION or result["effectMode"] not in OVERLAY_EFFECT_MODES:
            raise DeterministicOverlayContractError("runtime evidence identity is invalid")
        for field in ("runtimeEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "executionRequestRef"):
            _ref(result[field], field)
        for field in ("requirementDigest", "executionRequestDigest", "v3ExecutionRequestDigest"):
            _raw(result[field], field)
        _content(result["executionManifestDigest"], "executionManifestDigest")
        for field in ("rendererIdentity", "rendererVersion", "ffmpegIdentity"):
            _text(result[field], field, 500)
        if result["rendererIdentity"] != OVERLAY_RENDERER_IDENTITY or result["rendererVersion"] != OVERLAY_RENDERER_VERSION or result["gpuUsed"] is not False or result["publicationAllowed"] is not False:
            raise DeterministicOverlayContractError("runtime evidence authority is invalid")
        if result["runtimeEvidenceRef"] != _runtime_ref(result):
            raise DeterministicOverlayStaleInputError("runtimeEvidenceRef is stale")
        return cls(result)
    @property
    def runtime_evidence_ref(self) -> str: return str(self._value["runtimeEvidenceRef"])


def build_overlay_runtime_evidence(*, requirement: OverlayRequirement, execution_request: OverlayExecutionRequest, execution_facts: Mapping[str, Any]) -> OverlayRuntimeEvidence:
    request = validate_overlay_execution_request_binding(execution_request, requirement)
    facts = _closed(execution_facts, frozenset({"v3ExecutionRequestDigest", "rendererIdentity", "rendererVersion", "ffmpegIdentity", "executionManifestDigest"}), "overlay runtime facts")
    base = {"schemaVersion": OVERLAY_RUNTIME_EVIDENCE_SCHEMA_VERSION, **_lineage(requirement, request), **facts, "gpuUsed": False, "publicationAllowed": False}
    base["runtimeEvidenceRef"] = _runtime_ref(base)
    return OverlayRuntimeEvidence.from_mapping(_seal(base))


def _probe(value: Any) -> dict[str, Any]:
    result = _closed(value, _PROBE, "outputMediaProbe")
    for field in ("width", "height", "frameCount", "frameRate"):
        _integer(result[field], f"outputMediaProbe.{field}", 1, 10_000_001)
    if result["pixelFormat"] != "yuv420p" or result["container"] != "mp4" or result["videoCodec"] != "h264":
        raise DeterministicOverlayContractError("output media codec contract is invalid")
    return result


def _output_digest(value: Any) -> dict[str, Any]:
    result = _closed(value, _OUTPUT_DIGEST, "outputDigest")
    _content(result["fileDigest"], "outputDigest.fileDigest")
    _content(result["decodedFramePixelDigest"], "outputDigest.decodedFramePixelDigest")
    for field in ("width", "height", "frameCount", "frameRate"):
        _integer(result[field], f"outputDigest.{field}", 1, 10_000_001)
    if result["fileDigestAlgorithm"] != "sha256" or result["decodedFramePixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC or result["pixelMode"] != "RGBA":
        raise DeterministicOverlayContractError("output digest contract is invalid")
    return result


def _artifact_ref(value: Mapping[str, Any]) -> str:
    return "m13-overlay-artifact-evidence-" + _digest({
        "v3ExecutionRequestDigest": value["v3ExecutionRequestDigest"],
        "fileDigest": value["outputDigest"]["fileDigest"],
        "runtimeEvidenceDigest": value["runtimeEvidenceDigest"],
    })[:32]


@dataclass(frozen=True, slots=True)
class OverlayArtifactEvidence(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "OverlayArtifactEvidence":
        result = _sealed(value, _ARTIFACT, "OverlayArtifactEvidence")
        if result["schemaVersion"] != OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION or result["effectMode"] not in OVERLAY_EFFECT_MODES:
            raise DeterministicOverlayContractError("artifact evidence identity is invalid")
        for field in ("artifactEvidenceRef", "workspaceRef", "productionRunRef", "requirementRef", "executionRequestRef", "runtimeEvidenceRef"):
            _ref(result[field], field)
        for field in ("requirementDigest", "executionRequestDigest", "v3ExecutionRequestDigest", "runtimeEvidenceDigest"):
            _raw(result[field], field)
        _integer(result["outputByteSize"], "outputByteSize", 1, 10**13)
        result["outputMediaProbe"] = _probe(result["outputMediaProbe"])
        result["outputDigest"] = _output_digest(result["outputDigest"])
        if any(result["outputMediaProbe"][field] != result["outputDigest"][field] for field in ("width", "height", "frameCount", "frameRate")):
            raise DeterministicOverlayStaleInputError("output media and digest facts differ")
        if result["provenance"] != OVERLAY_EVIDENCE_PROVENANCE or result["publicationAllowed"] is not False:
            raise DeterministicOverlayContractError("artifact evidence authority is invalid")
        if result["artifactEvidenceRef"] != _artifact_ref(result):
            raise DeterministicOverlayStaleInputError("artifactEvidenceRef is stale")
        return cls(result)
    @property
    def artifact_evidence_ref(self) -> str: return str(self._value["artifactEvidenceRef"])


def build_overlay_artifact_evidence(*, requirement: OverlayRequirement, execution_request: OverlayExecutionRequest, runtime_evidence: OverlayRuntimeEvidence, execution_facts: Mapping[str, Any]) -> OverlayArtifactEvidence:
    request = validate_overlay_execution_request_binding(execution_request, requirement)
    runtime = runtime_evidence if type(runtime_evidence) is OverlayRuntimeEvidence else OverlayRuntimeEvidence.from_mapping(runtime_evidence)
    facts = _closed(execution_facts, frozenset({"v3ExecutionRequestDigest", "outputByteSize", "outputMediaProbe", "outputDigest"}), "overlay artifact facts")
    base = {"schemaVersion": OVERLAY_ARTIFACT_EVIDENCE_SCHEMA_VERSION, **_lineage(requirement, request), **facts, "runtimeEvidenceRef": runtime.runtime_evidence_ref, "runtimeEvidenceDigest": runtime.payload_digest, "provenance": OVERLAY_EVIDENCE_PROVENANCE, "publicationAllowed": False}
    base["artifactEvidenceRef"] = _artifact_ref(base)
    artifact = OverlayArtifactEvidence.from_mapping(_seal(base))
    validate_overlay_execution_evidence(requirement=requirement, execution_request=request, artifact_evidence=artifact, runtime_evidence=runtime)
    return artifact


def validate_overlay_execution_evidence(*, requirement: OverlayRequirement | Mapping[str, Any], execution_request: OverlayExecutionRequest | Mapping[str, Any], artifact_evidence: OverlayArtifactEvidence | Mapping[str, Any], runtime_evidence: OverlayRuntimeEvidence | Mapping[str, Any]) -> tuple[OverlayArtifactEvidence, OverlayRuntimeEvidence]:
    req = parse_overlay_requirement(requirement) if isinstance(requirement, Mapping) else requirement
    request = validate_overlay_execution_request_binding(execution_request, req)
    artifact = OverlayArtifactEvidence.from_mapping(artifact_evidence) if isinstance(artifact_evidence, Mapping) else artifact_evidence
    runtime = OverlayRuntimeEvidence.from_mapping(runtime_evidence) if isinstance(runtime_evidence, Mapping) else runtime_evidence
    if type(artifact) is not OverlayArtifactEvidence or type(runtime) is not OverlayRuntimeEvidence:
        raise DeterministicOverlayContractError("exact overlay evidence wrappers are required")
    expected = _lineage(req, request)
    artifact_value, runtime_value = artifact.as_dict(), runtime.as_dict()
    for field, value in expected.items():
        if artifact_value[field] != value or runtime_value[field] != value:
            raise DeterministicOverlayStaleInputError("overlay evidence lineage is stale")
    if artifact_value["v3ExecutionRequestDigest"] != runtime_value["v3ExecutionRequestDigest"] or artifact_value["runtimeEvidenceRef"] != runtime.runtime_evidence_ref or artifact_value["runtimeEvidenceDigest"] != runtime.payload_digest:
        raise DeterministicOverlayStaleInputError("artifact/runtime binding is stale")
    return artifact, runtime


@dataclass(frozen=True, slots=True)
class OverlayResult(_Contract):
    @classmethod
    def from_mapping(cls, value: Any) -> "OverlayResult":
        result = _sealed(value, _RESULT, "OverlayResult")
        if result["effectMode"] not in OVERLAY_EFFECT_MODES:
            raise DeterministicOverlayContractError("Result effectMode is invalid")
        expected_schema = NAMEPLATE_TEXT_RESULT_SCHEMA_VERSION if result["effectMode"] == NAMEPLATE_TEXT else FACE_MARK_COMPENSATION_RESULT_SCHEMA_VERSION
        if result["schemaVersion"] != expected_schema or result["state"] != "COMPOSED_CANDIDATE" or result["assetAdmissionState"] != "NOT_ADMITTED" or result["masterState"] != "NOT_CREATED" or result["exportState"] != "NOT_CREATED" or result["publicationAllowed"] is not False:
            raise DeterministicOverlayContractError("Result state is invalid")
        for field in ("workspaceRef", "productionRunRef", "resultRef", "requirementRef", "executionRequestRef", "artifactEvidenceRef", "runtimeEvidenceRef"):
            _ref(result[field], field)
        for field in ("requirementDigest", "executionRequestDigest", "artifactEvidenceDigest", "runtimeEvidenceDigest"):
            _raw(result[field], field)
        _content(result["outputFileDigest"], "outputFileDigest"); _content(result["outputDecodedFramePixelDigest"], "outputDecodedFramePixelDigest")
        result["outputMediaProbe"] = _probe(result["outputMediaProbe"])
        expected_ref = "overlay-result-" + _digest({key: result[key] for key in ("effectMode", "requirementDigest", "executionRequestDigest", "artifactEvidenceDigest", "runtimeEvidenceDigest", "outputFileDigest", "outputDecodedFramePixelDigest")})[:32]
        if result["resultRef"] != expected_ref:
            raise DeterministicOverlayStaleInputError("resultRef is stale")
        return cls(result)
    @property
    def result_ref(self) -> str: return str(self._value["resultRef"])


NameplateTextResult = OverlayResult
FaceMarkCompensationResult = OverlayResult


def parse_overlay_result(value: Any) -> OverlayResult:
    return OverlayResult.from_mapping(value)


def build_overlay_result(*, requirement: OverlayRequirement, execution_request: OverlayExecutionRequest, evidence_bindings: Mapping[str, Any], artifact_evidence: OverlayArtifactEvidence | Mapping[str, Any]) -> OverlayResult:
    request = validate_overlay_execution_request_binding(execution_request, requirement)
    artifact = OverlayArtifactEvidence.from_mapping(artifact_evidence) if isinstance(artifact_evidence, Mapping) else artifact_evidence
    if type(artifact) is not OverlayArtifactEvidence: raise DeterministicOverlayContractError("exact artifact evidence wrapper required")
    bindings = _closed(evidence_bindings, _BINDINGS, "evidenceBindings")
    expected = {**_lineage(requirement, request), "artifactEvidenceRef": artifact.artifact_evidence_ref, "artifactEvidenceDigest": artifact.payload_digest, "runtimeEvidenceRef": artifact.as_dict()["runtimeEvidenceRef"], "runtimeEvidenceDigest": artifact.as_dict()["runtimeEvidenceDigest"]}
    if any(bindings[field] != value for field, value in expected.items() if field in bindings):
        raise DeterministicOverlayStaleInputError("evidence bindings are stale")
    output = artifact.as_dict()["outputDigest"]
    base = {"schemaVersion": NAMEPLATE_TEXT_RESULT_SCHEMA_VERSION if requirement.effect_mode == NAMEPLATE_TEXT else FACE_MARK_COMPENSATION_RESULT_SCHEMA_VERSION, "workspaceRef": requirement.workspace_ref, "productionRunRef": requirement.production_run_ref, "effectMode": requirement.effect_mode, "requirementRef": requirement.requirement_ref, "requirementDigest": requirement.payload_digest, "executionRequestRef": request.execution_request_ref, "executionRequestDigest": request.payload_digest, "artifactEvidenceRef": artifact.artifact_evidence_ref, "artifactEvidenceDigest": artifact.payload_digest, "runtimeEvidenceRef": artifact.as_dict()["runtimeEvidenceRef"], "runtimeEvidenceDigest": artifact.as_dict()["runtimeEvidenceDigest"], "outputFileDigest": output["fileDigest"], "outputDecodedFramePixelDigest": output["decodedFramePixelDigest"], "outputMediaProbe": artifact.as_dict()["outputMediaProbe"], "state": "COMPOSED_CANDIDATE", "assetAdmissionState": "NOT_ADMITTED", "masterState": "NOT_CREATED", "exportState": "NOT_CREATED", "publicationAllowed": False}
    base["resultRef"] = "overlay-result-" + _digest({key: base[key] for key in ("effectMode", "requirementDigest", "executionRequestDigest", "artifactEvidenceDigest", "runtimeEvidenceDigest", "outputFileDigest", "outputDecodedFramePixelDigest")})[:32]
    return OverlayResult.from_mapping(_seal(base))


def overlay_requirement_record_kind(value: OverlayRequirement) -> str:
    if type(value) is NameplateTextRequirement: return NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND
    if type(value) is FaceMarkCompensationRequirement: return FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND
    raise DeterministicOverlayContractError("exact overlay Requirement required")


def overlay_result_record_kind(value: OverlayResult) -> str:
    if type(value) is not OverlayResult: raise DeterministicOverlayContractError("exact overlay Result required")
    return NAMEPLATE_TEXT_RESULT_RECORD_KIND if value.effect_mode == NAMEPLATE_TEXT else FACE_MARK_COMPENSATION_RESULT_RECORD_KIND


@dataclass(frozen=True, slots=True)
class ResolvedOverlayResultChain:
    requirement: OverlayRequirement
    execution_request: OverlayExecutionRequest
    artifact_evidence: OverlayArtifactEvidence
    runtime_evidence: OverlayRuntimeEvidence
    result: OverlayResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement.as_dict(),
            "executionRequest": self.execution_request.as_dict(),
            "artifactEvidence": self.artifact_evidence.as_dict(),
            "runtimeEvidence": self.runtime_evidence.as_dict(),
            "result": self.result.as_dict(),
        }


def _validated_chain(*, requirement: OverlayRequirement | Mapping[str, Any], execution_request: OverlayExecutionRequest | Mapping[str, Any], artifact_evidence: OverlayArtifactEvidence | Mapping[str, Any], runtime_evidence: OverlayRuntimeEvidence | Mapping[str, Any], result: OverlayResult | Mapping[str, Any]) -> ResolvedOverlayResultChain:
    req = parse_overlay_requirement(requirement) if isinstance(requirement, Mapping) else requirement
    request = validate_overlay_execution_request_binding(execution_request, req)
    artifact, runtime = validate_overlay_execution_evidence(requirement=req, execution_request=request, artifact_evidence=artifact_evidence, runtime_evidence=runtime_evidence)
    parsed_result = parse_overlay_result(result) if isinstance(result, Mapping) else result
    if type(parsed_result) is not OverlayResult:
        raise DeterministicOverlayContractError("exact overlay Result wrapper required")
    bindings = {
        "workspaceRef": req.workspace_ref,
        "productionRunRef": req.production_run_ref,
        "requirementRef": req.requirement_ref,
        "requirementDigest": req.payload_digest,
        "executionRequestRef": request.execution_request_ref,
        "executionRequestDigest": request.payload_digest,
        "artifactEvidenceRef": artifact.artifact_evidence_ref,
        "artifactEvidenceDigest": artifact.payload_digest,
        "runtimeEvidenceRef": runtime.runtime_evidence_ref,
        "runtimeEvidenceDigest": runtime.payload_digest,
    }
    expected = build_overlay_result(requirement=req, execution_request=request, evidence_bindings=bindings, artifact_evidence=artifact)
    if parsed_result.as_dict() != expected.as_dict():
        raise DeterministicOverlayStaleInputError("Result is not the exact overlay execution projection")
    return ResolvedOverlayResultChain(req, request, artifact, runtime, parsed_result)


def _record_key(client_key: str, slot: str) -> str:
    return _digest({"schemaVersion": "v5.m13-overlay-record-idempotency.v1", "clientIdempotencyKey": _idempotency_key(client_key), "slot": slot})


def _chain_records(chain: ResolvedOverlayResultChain, *, idempotency_key: str, created_at: str) -> tuple[EvidenceRecord, ...]:
    values = (
        (overlay_requirement_record_kind(chain.requirement), chain.requirement.requirement_ref, chain.requirement.as_dict()),
        (OVERLAY_EXECUTION_REQUEST_RECORD_KIND, chain.execution_request.execution_request_ref, chain.execution_request.as_dict()),
        (OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND, chain.artifact_evidence.artifact_evidence_ref, chain.artifact_evidence.as_dict()),
        (OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND, chain.runtime_evidence.runtime_evidence_ref, chain.runtime_evidence.as_dict()),
        (overlay_result_record_kind(chain.result), chain.result.result_ref, chain.result.as_dict()),
    )
    chain_digest = _digest({"schemaVersion": "v5.m13-overlay-result-chain.v1", "workspaceRef": chain.requirement.workspace_ref, "productionRunRef": chain.requirement.production_run_ref, "members": [{"recordKind": kind, "recordRef": ref, "payloadDigest": payload["payloadDigest"]} for kind, ref, payload in values]})
    timestamp = _timestamp(created_at)
    return tuple(EvidenceRecord(
        workspaceRef=chain.requirement.workspace_ref,
        productionRunRef=chain.requirement.production_run_ref,
        recordKind=kind,
        recordRef=ref,
        recordVersion=1,
        idempotencyKey=_record_key(idempotency_key, f"{index}:{kind}"),
        requestDigest=_digest({"schemaVersion": "v5.m13-overlay-record-append.v1", "chainDigest": chain_digest, "recordKind": kind, "recordRef": ref, "payloadDigest": payload["payloadDigest"]}),
        createdAt=timestamp,
        payload=payload,
        payloadDigest=payload["payloadDigest"],
    ) for index, (kind, ref, payload) in enumerate(values))


def _record_payload(repository: EpisodeProductionEvidenceRepository, *, workspace_ref: str, production_run_ref: str, record_ref: str, expected_kind: str | frozenset[str], expected_digest: str) -> dict[str, Any]:
    workspace, run_ref, ref = _ref(workspace_ref, "workspaceRef"), _ref(production_run_ref, "productionRunRef"), _ref(record_ref, "recordRef")
    digest = _raw(expected_digest, "record payloadDigest")
    stored = repository.get_record(workspace, run_ref, ref, 1)
    if stored is None: raise DeterministicOverlayJournalError("overlay evidence record is missing")
    try:
        record = _closed(stored, frozenset({"workspaceRef", "productionRunRef", "recordKind", "recordRef", "recordVersion", "idempotencyKey", "requestDigest", "createdAt", "payload", "payloadDigest"}), "overlay evidence record")
        kinds = expected_kind if isinstance(expected_kind, frozenset) else frozenset({expected_kind})
        if record["workspaceRef"] != workspace or record["productionRunRef"] != run_ref or record["recordKind"] not in kinds or record["recordRef"] != ref or record["recordVersion"] != 1 or record["payloadDigest"] != digest:
            raise DeterministicOverlayJournalError("overlay evidence record identity is stale")
        _idempotency_key(record["idempotencyKey"]); _raw(record["requestDigest"], "record requestDigest"); _timestamp(record["createdAt"])
        if not isinstance(record["payload"], Mapping): raise DeterministicOverlayJournalError("overlay evidence payload is invalid")
        payload = deepcopy(dict(record["payload"]))
        if payload.get("payloadDigest") != digest: raise DeterministicOverlayJournalError("overlay evidence payload digest is stale")
        return payload
    except DeterministicOverlayJournalError:
        raise
    except EpisodeProductionError as exc:
        raise DeterministicOverlayJournalError("overlay evidence record is invalid") from exc


def resolve_overlay_result_chain(repository: EpisodeProductionEvidenceRepository, *, workspace_ref: str, production_run_ref: str, result_ref: str, result_digest: str) -> ResolvedOverlayResultChain:
    result_payload = _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=result_ref, expected_kind=frozenset({NAMEPLATE_TEXT_RESULT_RECORD_KIND, FACE_MARK_COMPENSATION_RESULT_RECORD_KIND}), expected_digest=result_digest)
    result = parse_overlay_result(result_payload); value = result.as_dict()
    if value["resultRef"] != result_ref: raise DeterministicOverlayJournalError("Result record ref is stale")
    _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=result_ref, expected_kind=overlay_result_record_kind(result), expected_digest=result_digest)
    requirement_payload = _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=value["requirementRef"], expected_kind=NAMEPLATE_TEXT_REQUIREMENT_RECORD_KIND if value["effectMode"] == NAMEPLATE_TEXT else FACE_MARK_COMPENSATION_REQUIREMENT_RECORD_KIND, expected_digest=value["requirementDigest"])
    request_payload = _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=value["executionRequestRef"], expected_kind=OVERLAY_EXECUTION_REQUEST_RECORD_KIND, expected_digest=value["executionRequestDigest"])
    artifact_payload = _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=value["artifactEvidenceRef"], expected_kind=OVERLAY_ARTIFACT_EVIDENCE_RECORD_KIND, expected_digest=value["artifactEvidenceDigest"])
    runtime_payload = _record_payload(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, record_ref=value["runtimeEvidenceRef"], expected_kind=OVERLAY_RUNTIME_EVIDENCE_RECORD_KIND, expected_digest=value["runtimeEvidenceDigest"])
    return _validated_chain(requirement=requirement_payload, execution_request=request_payload, artifact_evidence=artifact_payload, runtime_evidence=runtime_payload, result=result)


def resolve_overlay_result(repository: EpisodeProductionEvidenceRepository, *, workspace_ref: str, production_run_ref: str, result_ref: str, result_digest: str) -> OverlayResult:
    return resolve_overlay_result_chain(repository, workspace_ref=workspace_ref, production_run_ref=production_run_ref, result_ref=result_ref, result_digest=result_digest).result


def append_overlay_result_chain(repository: EpisodeProductionEvidenceRepository, *, requirement: OverlayRequirement | Mapping[str, Any], execution_request: OverlayExecutionRequest | Mapping[str, Any], artifact_evidence: OverlayArtifactEvidence | Mapping[str, Any], runtime_evidence: OverlayRuntimeEvidence | Mapping[str, Any], result: OverlayResult | Mapping[str, Any], idempotency_key: str, created_at: str, expected_record_journal_head: str | None = None) -> tuple[ResolvedOverlayResultChain, bool]:
    chain = _validated_chain(requirement=requirement, execution_request=execution_request, artifact_evidence=artifact_evidence, runtime_evidence=runtime_evidence, result=result)
    records = _chain_records(chain, idempotency_key=idempotency_key, created_at=created_at)
    _, replayed = repository.append_records(records, expected_record_journal_head=expected_record_journal_head)
    resolved = resolve_overlay_result_chain(repository, workspace_ref=chain.requirement.workspace_ref, production_run_ref=chain.requirement.production_run_ref, result_ref=chain.result.result_ref, result_digest=chain.result.payload_digest)
    if resolved.as_dict() != chain.as_dict(): raise DeterministicOverlayJournalError("stored overlay result chain differs from append")
    return resolved, replayed


append_overlay_result = append_overlay_result_chain


__all__ = [name for name in globals() if name.isupper()] + [
    "DeterministicOverlayContractError", "DeterministicOverlayStaleInputError", "DeterministicOverlayJournalError",
    "NameplateTextRequirement", "FaceMarkCompensationRequirement", "OverlayRequirement",
    "OverlayExecutionRequest", "OverlayArtifactEvidence", "OverlayRuntimeEvidence", "OverlayResult",
    "NameplateTextResult", "FaceMarkCompensationResult", "ResolvedOverlayResultChain",
    "build_nameplate_text_requirement", "build_face_mark_compensation_requirement",
    "parse_overlay_requirement", "build_overlay_execution_request", "parse_overlay_execution_request",
    "validate_overlay_execution_request_binding", "build_overlay_runtime_evidence",
    "build_overlay_artifact_evidence", "validate_overlay_execution_evidence",
    "build_overlay_result", "parse_overlay_result", "append_overlay_result_chain",
    "append_overlay_result", "resolve_overlay_result_chain", "resolve_overlay_result",
    "overlay_requirement_record_kind", "overlay_result_record_kind",
]
