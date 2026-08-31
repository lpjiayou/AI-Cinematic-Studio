"""Closed deterministic FFmpeg renderer for M13-E3 overlays."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from types import SimpleNamespace
from typing import Any, Mapping

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

OVERLAY_V3_REQUEST_SCHEMA_VERSION = "v4.m13-overlay-execution-request.v1"
OVERLAY_RENDERER_IDENTITY = "v3.deterministic-overlay-ffmpeg"
OVERLAY_RENDERER_VERSION = "1"

_RAW = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_INPUT_LABEL = re.compile(r"[A-Za-z0-9_]+(?::[A-Za-z0-9_]+)?\Z")
_INTERPOLATIONS = {"STEP", "LINEAR", "EASE_IN", "EASE_OUT", "EASE_IN_OUT"}
_REQUEST = {
    "schemaVersion", "v5ExecutionRequestRef", "v5ExecutionRequestDigest",
    "workspaceRef", "productionRunRef", "requirementRef", "requirementDigest",
    "effectMode", "basePlate", "overlayAsset", "overlaySpec", "output",
    "publicationAllowed", "payloadDigest",
}
_BASE = {
    "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
    "pixelDigest", "pixelDigestSpec", "width", "height", "frameCount",
    "frameRate", "pixelFormat",
}
_FONT = {
    "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
    "validationRef", "validationDigest", "licenseBindingRef",
    "licenseBindingDigest",
}
_MARK = {
    "assetVersionRef", "assetVersionDigest", "storageKey", "fileDigest",
    "pixelDigest", "pixelDigestSpec", "pixelMode", "width", "height",
}
_OUTPUT = {
    "width", "height", "frameCount", "frameRate", "pixelFormat", "container",
    "videoCodec",
}
_SHOT = {"shotRef", "shotVersionRef", "shotVersionDigest"}
_COMMON_SPEC = {
    "targetShot", "frameRangeStartInclusive", "frameRangeEndExclusive",
    "blendMode", "layer",
}
_NAMEPLATE_SPEC = _COMMON_SPEC | {
    "resolvedText", "resolvedTextDigest", "language", "layout",
    "positionKeyframes", "scaleKeyframes", "rotationKeyframes",
    "perspectiveKeyframes", "opacityCurve", "trackingKeyframes",
}
_FACE_SPEC = _COMMON_SPEC | {
    "markType", "faceRegion", "trackingSourceKind", "trackingKeyframes",
    "scaleKeyframes", "rotationKeyframes", "opacityCurve", "occlusionPolicy",
}
_LAYOUT = {
    "writingMode", "alignment", "fontSizeMilliPixels",
    "letterSpacingMilliPixels", "lineSpacingMilliPixels", "maxWidthPixels",
    "maxHeightPixels",
}
_POINT = {"frame", "xPermille", "yPermille", "interpolation"}
_ROTATION = {"frame", "degreesMilli", "interpolation"}
_OPACITY = {"frame", "valuePermille", "interpolation"}
_PERSPECTIVE = {"frame", "quadPermille", "interpolation"}
_IDENTITY_QUAD = [0, 0, 1000, 0, 0, 1000, 1000, 1000]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _closed(value: object, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderArtifactError(f"{label} is not closed-world")
    return deepcopy(dict(value))


def _ref(value: object, label: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _digest(value: object, label: str, *, prefixed: bool = False) -> str:
    if not isinstance(value, str) or ( _SHA if prefixed else _RAW).fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _int(value: object, label: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _keyframes(
    value: object, fields: set[str], bounds: Mapping[str, tuple[int, int]],
    start: int, end: int, label: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 4096:
        raise RenderArtifactError(f"{label} is invalid")
    result: list[dict[str, Any]] = []
    previous = -1
    for index, raw in enumerate(value):
        item = _closed(raw, fields, f"{label}[{index}]")
        frame = _int(item["frame"], f"{label}.frame", start, end - 1)
        if frame <= previous or item["interpolation"] not in _INTERPOLATIONS:
            raise RenderArtifactError(f"{label} order is invalid")
        for field, (low, high) in bounds.items():
            _int(item[field], f"{label}.{field}", low, high)
        result.append(item)
        previous = frame
    if result[0]["frame"] != start or result[-1]["frame"] != end - 1:
        raise RenderArtifactError(f"{label} endpoints are invalid")
    return result


def _constant(items: list[dict[str, Any]], field: str, label: str) -> int:
    values = {item[field] for item in items}
    if len(values) != 1:
        raise RenderArtifactError(f"animated {label} is unsupported by renderer v1")
    return int(next(iter(values)))


def _validate_base(value: object) -> dict[str, Any]:
    base = _closed(value, _BASE, "basePlate")
    _ref(base["assetVersionRef"], "basePlate.assetVersionRef")
    _digest(base["assetVersionDigest"], "basePlate.assetVersionDigest")
    _digest(base["fileDigest"], "basePlate.fileDigest", prefixed=True)
    _digest(base["pixelDigest"], "basePlate.pixelDigest", prefixed=True)
    width = _int(base["width"], "basePlate.width", 2, 16384)
    height = _int(base["height"], "basePlate.height", 2, 16384)
    _int(base["frameCount"], "basePlate.frameCount", 1, 10_000_000)
    _int(base["frameRate"], "basePlate.frameRate", 1, 240)
    if (
        not isinstance(base["storageKey"], str)
        or base["pixelDigestSpec"] != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or base["pixelFormat"] != "yuv420p" or width % 2 or height % 2
    ):
        raise RenderArtifactError("basePlate media contract is unsupported")
    return base


def _validate_asset(value: object, mode: str) -> dict[str, Any]:
    asset = _closed(value, _FONT if mode == "NAMEPLATE_TEXT" else _MARK, "overlayAsset")
    _ref(asset["assetVersionRef"], "overlayAsset.assetVersionRef")
    _digest(asset["assetVersionDigest"], "overlayAsset.assetVersionDigest")
    _digest(asset["fileDigest"], "overlayAsset.fileDigest", prefixed=True)
    if not isinstance(asset["storageKey"], str):
        raise RenderArtifactError("overlayAsset.storageKey is invalid")
    if mode == "NAMEPLATE_TEXT":
        for field in ("validationRef", "licenseBindingRef"):
            _ref(asset[field], f"overlayAsset.{field}")
        for field in ("validationDigest", "licenseBindingDigest"):
            _digest(asset[field], f"overlayAsset.{field}")
    else:
        _digest(asset["pixelDigest"], "overlayAsset.pixelDigest", prefixed=True)
        _int(asset["width"], "overlayAsset.width", 1, 16384)
        _int(asset["height"], "overlayAsset.height", 1, 16384)
        if asset["pixelDigestSpec"] != IMAGE_PIXEL_DIGEST_SPEC or asset["pixelMode"] != "RGBA":
            raise RenderArtifactError("face-mark pixel contract is unsupported")
    return asset


def _common_spec(spec: dict[str, Any], base: Mapping[str, Any]) -> tuple[int, int]:
    shot = _closed(spec["targetShot"], _SHOT, "targetShot")
    _ref(shot["shotRef"], "targetShot.shotRef")
    _ref(shot["shotVersionRef"], "targetShot.shotVersionRef")
    _digest(shot["shotVersionDigest"], "targetShot.shotVersionDigest")
    start = _int(spec["frameRangeStartInclusive"], "frameRangeStartInclusive", 0, base["frameCount"] - 1)
    end = _int(spec["frameRangeEndExclusive"], "frameRangeEndExclusive", 1, base["frameCount"])
    if end <= start or spec["blendMode"] != "NORMAL":
        raise RenderArtifactError("overlay range or blend mode is unsupported")
    _int(spec["layer"], "layer", 0, 1024)
    spec["targetShot"] = shot
    return start, end


def _validate_spec(value: object, mode: str, base: Mapping[str, Any]) -> dict[str, Any]:
    spec = _closed(value, _NAMEPLATE_SPEC if mode == "NAMEPLATE_TEXT" else _FACE_SPEC, "overlaySpec")
    start, end = _common_spec(spec, base)
    if mode == "NAMEPLATE_TEXT":
        text = spec["resolvedText"]
        if (
            not isinstance(text, str) or not text or len(text.encode("utf-8")) > 16384
            or "\x00" in text or _RAW.fullmatch(str(spec["resolvedTextDigest"])) is None
            or sha256(_canonical({"utf8": text})).hexdigest() != spec["resolvedTextDigest"]
        ):
            raise RenderArtifactError("resolved text is invalid or stale")
        if not isinstance(spec["language"], str) or not 1 <= len(spec["language"]) <= 35:
            raise RenderArtifactError("language is invalid")
        layout = _closed(spec["layout"], _LAYOUT, "layout")
        if layout["writingMode"] not in {"HORIZONTAL_LTR", "VERTICAL_RTL"} or layout["alignment"] not in {"START", "CENTER", "END"}:
            raise RenderArtifactError("layout mode is invalid")
        for field, high in (("fontSizeMilliPixels", 512000), ("lineSpacingMilliPixels", 512000), ("letterSpacingMilliPixels", 512000)):
            _int(layout[field], field, 0 if field != "fontSizeMilliPixels" else 1000, high)
        _int(layout["maxWidthPixels"], "maxWidthPixels", 1, base["width"])
        _int(layout["maxHeightPixels"], "maxHeightPixels", 1, base["height"])
        if layout["fontSizeMilliPixels"] % 1000 or layout["lineSpacingMilliPixels"] % 1000 or layout["letterSpacingMilliPixels"] != 0:
            raise RenderArtifactError("renderer v1 requires integer sizes and zero letter spacing")
        spec["layout"] = layout
        spec["positionKeyframes"] = _keyframes(spec["positionKeyframes"], _POINT, {"xPermille": (0, 1000), "yPermille": (0, 1000)}, start, end, "positionKeyframes")
        spec["trackingKeyframes"] = _keyframes(spec["trackingKeyframes"], _POINT, {"xPermille": (-1000, 1000), "yPermille": (-1000, 1000)}, start, end, "trackingKeyframes")
        spec["perspectiveKeyframes"] = _keyframes(spec["perspectiveKeyframes"], _PERSPECTIVE, {}, start, end, "perspectiveKeyframes")
        if any(item["quadPermille"] != _IDENTITY_QUAD for item in spec["perspectiveKeyframes"]):
            raise RenderArtifactError("renderer v1 supports identity perspective only")
    else:
        if spec["markType"] not in {"MOLE", "SCAR"}:
            raise RenderArtifactError("markType is invalid")
        if spec["faceRegion"] not in {"LEFT_CHEEK", "RIGHT_CHEEK", "LEFT_BROW", "RIGHT_BROW", "NOSE_BRIDGE", "CHIN", "FOREHEAD"}:
            raise RenderArtifactError("faceRegion is invalid")
        if spec["trackingSourceKind"] != "EXPLICIT_KEYFRAMES" or spec["occlusionPolicy"] != "ALWAYS_VISIBLE_WITHIN_TRACK":
            raise RenderArtifactError("face-mark tracking/occlusion policy is unsupported")
        spec["trackingKeyframes"] = _keyframes(spec["trackingKeyframes"], _POINT, {"xPermille": (0, 1000), "yPermille": (0, 1000)}, start, end, "trackingKeyframes")
    spec["scaleKeyframes"] = _keyframes(spec["scaleKeyframes"], _POINT, {"xPermille": (1, 4000), "yPermille": (1, 4000)}, start, end, "scaleKeyframes")
    spec["rotationKeyframes"] = _keyframes(spec["rotationKeyframes"], _ROTATION, {"degreesMilli": (-360000, 360000)}, start, end, "rotationKeyframes")
    spec["opacityCurve"] = _keyframes(spec["opacityCurve"], _OPACITY, {"valuePermille": (0, 1000)}, start, end, "opacityCurve")
    for field, key in (("scaleKeyframes", "xPermille"), ("scaleKeyframes", "yPermille"), ("rotationKeyframes", "degreesMilli"), ("opacityCurve", "valuePermille")):
        _constant(spec[field], key, field)
    return spec


def _validate(value: Mapping[str, Any]) -> dict[str, Any]:
    request = _closed(value, _REQUEST, "overlay request")
    claimed = request.pop("payloadDigest")
    _digest(claimed, "payloadDigest")
    if claimed != sha256(_canonical(request)).hexdigest():
        raise RenderArtifactError("overlay request seal is invalid")
    request["payloadDigest"] = claimed
    mode = request["effectMode"]
    if request["schemaVersion"] != OVERLAY_V3_REQUEST_SCHEMA_VERSION or mode not in {"NAMEPLATE_TEXT", "FACE_MARK_COMPENSATION"} or request["publicationAllowed"] is not False:
        raise RenderArtifactError("overlay request identity is invalid")
    for field in ("v5ExecutionRequestRef", "workspaceRef", "productionRunRef", "requirementRef"):
        _ref(request[field], field)
    for field in ("v5ExecutionRequestDigest", "requirementDigest"):
        _digest(request[field], field)
    base = _validate_base(request["basePlate"])
    request["basePlate"] = base
    request["overlayAsset"] = _validate_asset(request["overlayAsset"], mode)
    request["overlaySpec"] = _validate_spec(request["overlaySpec"], mode, base)
    output = _closed(request["output"], _OUTPUT, "output")
    if output != {"width": base["width"], "height": base["height"], "frameCount": base["frameCount"], "frameRate": base["frameRate"], "pixelFormat": "yuv420p", "container": "mp4", "videoCodec": "h264"}:
        raise RenderArtifactError("overlay output does not match basePlate")
    request["output"] = output
    return request


def validate_overlay_preview_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Preview stages through the exact standalone V3 contract."""
    return _validate(stage)


def _expression(items: list[dict[str, Any]], field: str) -> str:
    expression = str(items[-1][field])
    for left, right in reversed(list(zip(items, items[1:]))):
        start, end = left["frame"], right["frame"]
        progress = f"((n-{start})/{end - start})"
        kind = left["interpolation"]
        eased = {
            "STEP": "0", "LINEAR": progress,
            "EASE_IN": f"({progress}*{progress})",
            "EASE_OUT": f"(1-(1-{progress})*(1-{progress}))",
            "EASE_IN_OUT": f"if(lt({progress},0.5),2*{progress}*{progress},1-2*(1-{progress})*(1-{progress}))",
        }[kind]
        segment = f"({left[field]}+({right[field]}-{left[field]})*{eased})"
        expression = f"if(lt(n,{end}),{segment},{expression})"
    return expression


def overlay_text_bytes(stage: Mapping[str, Any]) -> bytes:
    request = _validate(stage)
    if request["effectMode"] != "NAMEPLATE_TEXT":
        raise RenderArtifactError("face-mark stage has no text")
    text = request["overlaySpec"]["resolvedText"]
    if request["overlaySpec"]["layout"]["writingMode"] == "VERTICAL_RTL":
        if "\t" in text or "\r" in text:
            raise RenderArtifactError("vertical text control characters are unsupported")
        text = "\n".join(character for paragraph in text.split("\n") for character in paragraph)
    return text.encode("utf-8")


def _filter_path(value: Path | str, label: str) -> str:
    path = str(value)
    if not path or any(character in path for character in "'\\\n\r\x00"):
        raise RenderArtifactError(f"{label} is invalid")
    return path.replace(":", "\\:")


def build_overlay_stage_filters(
    stage: Mapping[str, Any], *, input_label: str, prefix: str,
    font_path: Path | None = None, text_path: Path | None = None,
    overlay_input_label: str | None = None,
) -> tuple[list[str], str]:
    """Generate the sole graph shared by standalone and six-stage Preview."""
    request = _validate(stage)
    if _LABEL.fullmatch(prefix) is None or _INPUT_LABEL.fullmatch(input_label) is None or (overlay_input_label is not None and _INPUT_LABEL.fullmatch(overlay_input_label) is None):
        raise RenderArtifactError("overlay graph label is invalid")
    spec = request["overlaySpec"]
    sx = _constant(spec["scaleKeyframes"], "xPermille", "scaleKeyframes")
    sy = _constant(spec["scaleKeyframes"], "yPermille", "scaleKeyframes")
    rotation = _constant(spec["rotationKeyframes"], "degreesMilli", "rotationKeyframes")
    opacity = _constant(spec["opacityCurve"], "valuePermille", "opacityCurve")
    filters: list[str] = []
    source = f"{prefix}source"
    if request["effectMode"] == "NAMEPLATE_TEXT":
        if font_path is None or text_path is None or overlay_input_label is not None:
            raise RenderArtifactError("nameplate graph bindings are invalid")
        layout = spec["layout"]
        align = {"START": "0", "CENTER": "(w-text_w)/2", "END": "w-text_w"}[layout["alignment"]]
        filters.append(
            f"color=c=black@0.0:s={layout['maxWidthPixels']}x{layout['maxHeightPixels']}:r={request['output']['frameRate']},format=rgba,"
            f"drawtext=fontfile='{_filter_path(font_path, 'font path')}':textfile='{_filter_path(text_path, 'text path')}':expansion=none:text_shaping=0:fontcolor=white:fontsize={layout['fontSizeMilliPixels']//1000}:line_spacing={layout['lineSpacingMilliPixels']//1000}:x='{align}':y=0[{source}]"
        )
        px, py = _expression(spec["positionKeyframes"], "xPermille"), _expression(spec["positionKeyframes"], "yPermille")
        tx, ty = _expression(spec["trackingKeyframes"], "xPermille"), _expression(spec["trackingKeyframes"], "yPermille")
        x, y = f"((W-w)*({px})/1000+W*({tx})/1000)", f"((H-h)*({py})/1000+H*({ty})/1000)"
        source_width, source_height = layout["maxWidthPixels"], layout["maxHeightPixels"]
    else:
        if overlay_input_label is None or font_path is not None or text_path is not None:
            raise RenderArtifactError("face-mark graph bindings are invalid")
        source = overlay_input_label
        tx, ty = _expression(spec["trackingKeyframes"], "xPermille"), _expression(spec["trackingKeyframes"], "yPermille")
        x, y = f"((W-w)*({tx})/1000)", f"((H-h)*({ty})/1000)"
        source_width, source_height = request["overlayAsset"]["width"], request["overlayAsset"]["height"]
    width, height = max(1, source_width * sx // 1000), max(1, source_height * sy // 1000)
    scaled = f"{prefix}scaled"
    filters.append(f"[{source}]format=rgba,scale={width}:{height}:flags=neighbor,colorchannelmixer=aa={opacity/1000:.3f}[{scaled}]")
    transformed = scaled
    if rotation:
        transformed = f"{prefix}rotated"
        angle = f"({rotation}*PI/180000)"
        filters.append(f"[{scaled}]rotate=a='{angle}':ow='rotw({angle})':oh='roth({angle})':fillcolor=black@0[{transformed}]")
    output = f"{prefix}out"
    filters.append(f"[{input_label}][{transformed}]overlay=x='{x}':y='{y}':enable='between(n,{spec['frameRangeStartInclusive']},{spec['frameRangeEndExclusive']-1})':eof_action=pass:shortest=0:format=auto,format=yuv420p[{output}]")
    return filters, output


class DeterministicOverlayExecutor:
    """Execute a sealed overlay with held runtimes and digest-pinned inputs."""
    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if not self.artifact_root.is_dir() or self.artifact_root.is_symlink():
            raise RenderArtifactError("overlay artifact root is invalid")

    def execute(self, value: Mapping[str, Any]) -> dict[str, Any]:
        request = _validate(value)
        base_source = _safe_glyph_input(
            self.artifact_root, request["basePlate"]["storageKey"]
        )
        overlay_source = _safe_glyph_input(
            self.artifact_root, request["overlayAsset"]["storageKey"]
        )
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")
        if ffmpeg_path is None or ffprobe_path is None:
            raise RenderArtifactError("pinned FFmpeg runtime is unavailable")
        with _PinnedRuntimeBinary(
            Path(os.path.realpath(ffmpeg_path)), label="FFmpeg"
        ) as ffmpeg, _PinnedRuntimeBinary(
            Path(os.path.realpath(ffprobe_path)), label="FFprobe"
        ) as ffprobe:
            return self._execute_validated(
                request,
                base_source=base_source,
                overlay_source=overlay_source,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
            )

    def _execute_validated(
        self,
        request: Mapping[str, Any],
        *,
        base_source: Path,
        overlay_source: Path,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        output = request["output"]
        runtime_fds = tuple(dict.fromkeys(ffmpeg.pass_fds + ffprobe.pass_fds))
        ffmpeg_identity = ffmpeg.version_identity()
        with tempfile.TemporaryDirectory(
            prefix=".overlay-work-", dir=self.artifact_root
        ) as temporary:
            work_root = Path(temporary)
            work_root.chmod(0o700)
            inputs = work_root / "inputs"
            inputs.mkdir(mode=0o700)
            base_path = inputs / "base.media"
            layer_path = inputs / (
                "font.sfnt"
                if request["effectMode"] == "NAMEPLATE_TEXT"
                else "mark.png"
            )
            _stage_digest_pinned_input(
                base_source, base_path, request["basePlate"]["fileDigest"]
            )
            _stage_digest_pinned_input(
                overlay_source,
                layer_path,
                request["overlayAsset"]["fileDigest"],
            )
            candidate = work_root / "candidate.mp4"
            with _PinnedRegularFile(
                base_path, label="staged overlay base"
            ) as base_pin, _PinnedRegularFile(
                layer_path, label="staged overlay layer"
            ) as layer_pin:
                held_fds = tuple(
                    dict.fromkeys(
                        runtime_fds + base_pin.pass_fds + layer_pin.pass_fds
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
                    base_digest = decoded_frame_pixel_digest_metadata(
                        base_pin.descriptor_path,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=held_fds,
                    )
                except DigestError as exc:
                    raise RenderArtifactError(
                        "overlay base pixel digest failed"
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
                    raise RenderArtifactError("overlay base pixels changed")

                command = self._command_prefix(
                    ffmpeg=ffmpeg,
                    base_path=base_pin.descriptor_path,
                )
                if request["effectMode"] == "NAMEPLATE_TEXT":
                    text_path = inputs / "resolved-text.utf8"
                    _write_exact(text_path, overlay_text_bytes(request))
                    with _PinnedRegularFile(
                        text_path, label="nameplate text"
                    ) as text_pin:
                        _require_font_cmap(
                            layer_pin.descriptor,
                            request["overlaySpec"]["resolvedText"],
                        )
                        filters, output_label = build_overlay_stage_filters(
                            request,
                            input_label="0:v",
                            prefix="overlay",
                            font_path=layer_pin.descriptor_path,
                            text_path=text_pin.descriptor_path,
                        )
                        pass_fds = tuple(
                            dict.fromkeys(held_fds + text_pin.pass_fds)
                        )
                        self._run(
                            command,
                            filters=filters,
                            output_label=output_label,
                            output=output,
                            candidate=candidate,
                            pass_fds=pass_fds,
                        )
                        text_pin.require_stable()
                else:
                    with tempfile.TemporaryDirectory(
                        prefix=".held-mark-", dir=work_root
                    ) as alias_root:
                        mark_alias = Path(alias_root) / "held-mark.png"
                        os.symlink(layer_pin.descriptor_path, mark_alias)
                        _require_mark_pixels(
                            mark_alias,
                            request["overlayAsset"],
                            ffmpeg=ffmpeg,
                            ffprobe=ffprobe,
                            pass_fds=held_fds,
                        )
                    command.extend(
                        [
                            "-loop",
                            "1",
                            "-framerate",
                            str(output["frameRate"]),
                            "-i",
                            str(layer_pin.descriptor_path),
                        ]
                    )
                    filters, output_label = build_overlay_stage_filters(
                        request,
                        input_label="0:v",
                        prefix="overlay",
                        overlay_input_label="1:v",
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
                layer_pin.require_stable()

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
                    "overlay output digest failed"
                ) from exc
            if (
                output_digest["width"] != output["width"]
                or output_digest["height"] != output["height"]
                or output_digest["frameCount"] != output["frameCount"]
            ):
                raise RenderArtifactError("overlay output media facts changed")
            output_digest["frameRate"] = output["frameRate"]
            execution_manifest_digest = "sha256:" + sha256(
                _canonical(
                    {
                        "schemaVersion": OVERLAY_V3_REQUEST_SCHEMA_VERSION,
                        "v3ExecutionRequestDigest": request["payloadDigest"],
                        "rendererIdentity": OVERLAY_RENDERER_IDENTITY,
                        "rendererVersion": OVERLAY_RENDERER_VERSION,
                        "output": output,
                        "textFileDigest": (
                            "sha256:"
                            + sha256(overlay_text_bytes(request)).hexdigest()
                            if request["effectMode"] == "NAMEPLATE_TEXT"
                            else None
                        ),
                    }
                )
            ).hexdigest()
            directory = (
                self.artifact_root
                / sha256(request["workspaceRef"].encode("utf-8")).hexdigest()[:20]
                / sha256(request["productionRunRef"].encode("utf-8")).hexdigest()[:20]
                / "deterministic-overlays"
            )
            with _PinnedRegularFile(
                candidate, label="overlay candidate"
            ) as pinned:
                destination = _publish_timeline_output_v1(
                    root=self.artifact_root,
                    directory=directory,
                    source=pinned,
                    expected_file_digest=output_digest["fileDigest"],
                    output_name=f"overlay-{request['payloadDigest']}.mp4",
                )
            ffmpeg.require_stable()
            ffprobe.require_stable()

        runtime = {
            "ffmpegIdentity": ffmpeg_identity,
            "rendererIdentity": OVERLAY_RENDERER_IDENTITY,
            "rendererVersion": OVERLAY_RENDERER_VERSION,
            "executionManifestDigest": execution_manifest_digest,
        }
        return {
            "internalPath": str(destination),
            "outputStorageKey": str(
                destination.relative_to(self.artifact_root)
            ),
            "outputByteSize": destination.stat().st_size,
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
                "FFmpeg overlay execution failed"
                + (f": {message}" if message else "")
            ) from exc


def _write_exact(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        raise RenderArtifactError("nameplate text staging failed") from exc


def _require_mark_pixels(
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
        raise RenderArtifactError("face-mark pixel digest failed") from exc
    if (
        measured["pixel_digest"] != binding["pixelDigest"]
        or measured["pixel_digest_spec"] != binding["pixelDigestSpec"]
        or measured["pixel_mode"] != binding["pixelMode"]
        or measured["width"] != binding["width"]
        or measured["height"] != binding["height"]
    ):
        raise RenderArtifactError("face-mark pixels changed")


def _require_font_cmap(descriptor: int | None, text: str) -> None:
    """Parse Unicode cmap formats 4/12; never allow missing-glyph fallback."""
    if descriptor is None or not hasattr(os, "pread"):
        raise RenderArtifactError("nameplate font is not held")
    try:
        size = os.fstat(descriptor).st_size
        if not 12 < size <= 128 * 1024 * 1024:
            raise ValueError
        data = os.pread(descriptor, size, 0)
        if len(data) != size or data[:4] not in {
            b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1",
        }:
            raise ValueError
        table_count = struct.unpack_from(">H", data, 4)[0]
        cmap: memoryview | None = None
        for index in range(table_count):
            tag, _, offset, length = struct.unpack_from(
                ">4sIII", data, 12 + index * 16
            )
            if tag == b"cmap" and offset + length <= len(data):
                cmap = memoryview(data)[offset:offset + length]
                break
        if cmap is None:
            raise ValueError
        subtable_count = struct.unpack_from(">H", cmap, 2)[0]
        subtables: list[memoryview] = []
        for index in range(subtable_count):
            platform, encoding, offset = struct.unpack_from(
                ">HHI", cmap, 4 + index * 8
            )
            if (
                (platform == 0 or (platform == 3 and encoding in {1, 10}))
                and offset + 2 <= len(cmap)
            ):
                subtables.append(cmap[offset:])
        for codepoint in {ord(char) for char in text if not char.isspace()}:
            if not any(_cmap_contains(table, codepoint) for table in subtables):
                raise RenderArtifactError(
                    f"nameplate font is missing U+{codepoint:04X}"
                )
    except RenderArtifactError:
        raise
    except (OSError, ValueError, struct.error) as exc:
        raise RenderArtifactError("nameplate font cmap is invalid") from exc


def _cmap_contains(table: memoryview, codepoint: int) -> bool:
    try:
        format_number = struct.unpack_from(">H", table, 0)[0]
        if format_number == 12:
            length = struct.unpack_from(">I", table, 4)[0]
            count = struct.unpack_from(">I", table, 12)[0]
            if length > len(table) or 16 + count * 12 > length:
                return False
            for index in range(count):
                start, end, glyph = struct.unpack_from(
                    ">III", table, 16 + index * 12
                )
                if start <= codepoint <= end:
                    return glyph + codepoint - start != 0
            return False
        if format_number != 4 or codepoint > 0xFFFF:
            return False
        length = struct.unpack_from(">H", table, 2)[0]
        segment_count = struct.unpack_from(">H", table, 6)[0] // 2
        if segment_count <= 0 or length > len(table):
            return False
        end_offset = 14
        start_offset = end_offset + segment_count * 2 + 2
        delta_offset = start_offset + segment_count * 2
        range_offset = delta_offset + segment_count * 2
        for index in range(segment_count):
            end = struct.unpack_from(">H", table, end_offset + index * 2)[0]
            start = struct.unpack_from(">H", table, start_offset + index * 2)[0]
            if start <= codepoint <= end:
                delta = struct.unpack_from(
                    ">h", table, delta_offset + index * 2
                )[0]
                distance = struct.unpack_from(
                    ">H", table, range_offset + index * 2
                )[0]
                if distance == 0:
                    return (codepoint + delta) & 0xFFFF != 0
                glyph_offset = (
                    range_offset + index * 2 + distance
                    + 2 * (codepoint - start)
                )
                if glyph_offset + 2 > length:
                    return False
                glyph = struct.unpack_from(">H", table, glyph_offset)[0]
                return glyph != 0 and (glyph + delta) & 0xFFFF != 0
        return False
    except (IndexError, struct.error):
        return False


__all__ = [
    "DeterministicOverlayExecutor", "OVERLAY_RENDERER_IDENTITY",
    "OVERLAY_RENDERER_VERSION", "OVERLAY_V3_REQUEST_SCHEMA_VERSION",
    "build_overlay_stage_filters", "overlay_text_bytes",
    "validate_overlay_preview_stage",
]
