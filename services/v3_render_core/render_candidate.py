"""Closed CPU-only final rendering for M13 non-publishing candidates.

The executor accepts only a server-sealed V4 request.  It derives its FFmpeg
graph in code, pins both runtime binaries and every input, publishes with the
existing no-replace descriptor path, and remeasures decoded video and PCM
content before returning technical evidence.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from typing import Any, Mapping

from .composition import (
    RenderArtifactError,
    _PinnedRegularFile,
    _PinnedRuntimeBinary,
    _fixed_environment,
    _glyph_probe,
    _publish_timeline_output_v1,
    _runtime_path,
    _stage_timeline_preview_input,
    _stream_frame_count,
    _stream_frame_rate,
    _stream_integer,
)
from .digests import (
    DECODED_FRAME_PIXEL_DIGEST_SPEC_V2,
    PCM_CONTENT_DIGEST_SPEC,
    DigestError,
    canonical_pcm_digest_metadata,
    decoded_frame_pixel_digest_metadata,
)


RENDER_CORE_REQUEST_SCHEMA_VERSION = "v4.m13-render-core-execution-request.v1"
RENDER_CORE_RESULT_SCHEMA_VERSION = "v3.m13-render-core-result.v1"
VIDEO_COMPOSITION_PLAN_SCHEMA_VERSION = "v3.m13-video-composition-plan.v1"
RENDERER_IDENTITY = "v3-deterministic-render-core"
RENDERER_VERSION = "1"
SUBTITLE_TIMING_DIGEST_SPEC = "sha256/canonical-subtitle-timing-json/v1"

_RAW_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@/-]{0,511}\Z")

_REQUEST_FIELDS = frozenset(
    {
        "schemaVersion",
        "executionRequestRef",
        "executionRequestDigest",
        "workspaceRef",
        "productionRunRef",
        "outputArtifactBindingRef",
        "sourceArtifact",
        "videoCompositionPlan",
        "renderProfile",
        "subtitleCues",
        "subtitleFont",
        "publicationAllowed",
        "payloadDigest",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "storageKey",
        "byteSize",
        "fileDigest",
        "decodedFramePixelDigest",
        "decodedFramePixelDigestSpec",
        "pcmContentDigest",
        "pcmContentDigestSpec",
        "mediaProbe",
    }
)
_SOURCE_MEDIA_PROBE_FIELDS = frozenset(
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
_PROFILE_FIELDS = frozenset(
    {
        "outputProfile",
        "videoEncoding",
        "colorMetadata",
        "audioEncoding",
        "subtitleMode",
        "subtitleTimingDigest",
        "rendererIdentity",
        "rendererVersion",
        "ffmpegBinaryDigest",
        "ffprobeBinaryDigest",
    }
)
_OUTPUT_PROFILE_FIELDS = frozenset(
    {
        "profileRef",
        "width",
        "height",
        "frameRateNumerator",
        "frameRateDenominator",
        "pixelAspectRatioNumerator",
        "pixelAspectRatioDenominator",
        "resizeMode",
        "backgroundPolicy",
        "safeArea",
    }
)
_SAFE_AREA_FIELDS = frozenset(
    {"leftPixels", "topPixels", "rightPixels", "bottomPixels"}
)
_VIDEO_ENCODING_FIELDS = frozenset(
    {
        "codec",
        "pixelFormat",
        "qualityMode",
        "qualityValue",
        "profile",
        "level",
        "gopFrames",
        "deterministicThreadPolicy",
    }
)
_COLOR_FIELDS = frozenset(
    {"colorPrimaries", "colorTransfer", "colorSpace", "colorRange"}
)
_AUDIO_ENCODING_FIELDS = frozenset(
    {"enabled", "codec", "sampleRate", "channelCount", "bitrate"}
)
_FONT_FIELDS = frozenset(
    {"storageKey", "fileDigest", "byteSize", "fontFamily"}
)
_CUE_FIELDS = frozenset(
    {
        "cueRef",
        "clipRef",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "text",
        "textDigest",
        "language",
        "wordTiming",
    }
)
_WORD_FIELDS = frozenset(
    {
        "wordRef",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "text",
        "textDigest",
    }
)
_VIDEO_COMPOSITION_PLAN_FIELDS = frozenset(
    {
        "schemaVersion",
        "canvasWidth",
        "canvasHeight",
        "frameRate",
        "totalFrames",
        "maskLayerPlanDigest",
        "clips",
        "payloadDigest",
    }
)
_VIDEO_COMPOSITION_CLIP_FIELDS = frozenset(
    {
        "clipRef",
        "clipDigest",
        "timelineStartFrameInclusive",
        "timelineEndFrameExclusive",
        "sourceInFrameInclusive",
        "sourceOutFrameExclusive",
        "layer",
        "zOrder",
        "opacity",
        "blendMode",
        "transitionIn",
        "transitionOut",
        "speed",
        "transform",
        "maskBindingDigests",
    }
)
_VIDEO_COMPOSITION_TRANSITION_FIELDS = frozenset(
    {"kind", "durationFrames", "curve", "alignment"}
)
_VIDEO_COMPOSITION_SPEED_FIELDS = frozenset({"numerator", "denominator"})
_VIDEO_COMPOSITION_TRANSFORM_FIELDS = frozenset(
    {
        "positionXPixels",
        "positionYPixels",
        "scaleX",
        "scaleY",
        "rotationMilliDegrees",
        "anchorXPixels",
        "anchorYPixels",
        "opacity",
    }
)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError("render request is not canonical JSON") from exc


def _closed(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise RenderArtifactError(f"{label} contract is invalid")
    result = deepcopy(dict(value))
    _reject_floats(result)
    return result


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise RenderArtifactError("float render authority is forbidden")
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RenderArtifactError("render object key is invalid")
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def _ref(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or _REF.fullmatch(value) is None
        or value.startswith(("/", "\\"))
        or ".." in value.split("/")
        or "://" in value
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _raw_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _RAW_DIGEST.fullmatch(value) is None:
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _content_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or (
        _RAW_DIGEST.fullmatch(value) is None
        and _PREFIXED_DIGEST.fullmatch(value) is None
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int = 4_000_000_000) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _signed_integer(value: Any, label: str, *, bound: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < -bound
        or value > bound
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _storage_key(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise RenderArtifactError(f"{label} is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or str(path) != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise RenderArtifactError(f"{label} is invalid")
    return value


def _rate(value: Any, label: str) -> Fraction:
    record = _closed(value, frozenset({"numerator", "denominator"}), label)
    numerator = _integer(record["numerator"], f"{label}.numerator", minimum=1)
    denominator = _integer(record["denominator"], f"{label}.denominator", minimum=1)
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        raise RenderArtifactError(f"{label} is not reduced")
    return result


def _canonical_subtitle_timing(cues: list[dict[str, Any]]) -> str:
    projection = []
    for cue in cues:
        projection.append(
            {
                **{key: deepcopy(value) for key, value in cue.items() if key != "text"},
                "wordTiming": [
                    {
                        key: deepcopy(value)
                        for key, value in word.items()
                        if key != "text"
                    }
                    for word in cue["wordTiming"]
                ],
            }
        )
    return sha256(
        _canonical_json(
            {
                "schemaVersion": "v5.m13-canonical-subtitle-timing.v1",
                "cues": projection,
            }
        )
    ).hexdigest()


def _validate_video_composition_plan(value: Any) -> dict[str, Any]:
    plan = _closed(
        value,
        _VIDEO_COMPOSITION_PLAN_FIELDS,
        "videoCompositionPlan",
    )
    supplied = _raw_digest(plan.pop("payloadDigest"), "video plan payloadDigest")
    if supplied != sha256(_canonical_json(plan)).hexdigest():
        raise RenderArtifactError("video composition plan seal is invalid")
    plan["payloadDigest"] = supplied
    if plan["schemaVersion"] != VIDEO_COMPOSITION_PLAN_SCHEMA_VERSION:
        raise RenderArtifactError("video composition plan schema is unsupported")
    width = _integer(plan["canvasWidth"], "video canvas width", minimum=2)
    height = _integer(plan["canvasHeight"], "video canvas height", minimum=2)
    if width % 2 or height % 2:
        raise RenderArtifactError("video composition canvas must be even")
    rate = _rate(plan["frameRate"], "video composition frameRate")
    total_frames = _integer(
        plan["totalFrames"], "video composition totalFrames", minimum=1
    )
    _raw_digest(plan["maskLayerPlanDigest"], "maskLayerPlanDigest")
    if not isinstance(plan["clips"], list) or not plan["clips"]:
        raise RenderArtifactError("video composition clips are invalid")
    clips: list[dict[str, Any]] = []
    for index, raw in enumerate(plan["clips"]):
        clip = _closed(
            raw,
            _VIDEO_COMPOSITION_CLIP_FIELDS,
            f"video composition clip {index}",
        )
        _ref(clip["clipRef"], "video clipRef")
        _raw_digest(clip["clipDigest"], "video clipDigest")
        timeline_start = _integer(
            clip["timelineStartFrameInclusive"], "video timeline start"
        )
        timeline_end = _integer(
            clip["timelineEndFrameExclusive"],
            "video timeline end",
            minimum=1,
            maximum=total_frames,
        )
        source_start = _integer(
            clip["sourceInFrameInclusive"], "video source start"
        )
        source_end = _integer(
            clip["sourceOutFrameExclusive"], "video source end", minimum=1
        )
        if timeline_start >= timeline_end or source_start >= source_end:
            raise RenderArtifactError("video composition clip range is invalid")
        _integer(clip["layer"], "video layer", maximum=1024)
        _signed_integer(clip["zOrder"], "video zOrder", bound=1_000_000)
        _integer(clip["opacity"], "video opacity", maximum=1000)
        if clip["blendMode"] != "NORMAL":
            raise RenderArtifactError("video blend mode is unsupported")
        speed = _closed(
            clip["speed"], _VIDEO_COMPOSITION_SPEED_FIELDS, "video speed"
        )
        speed_rate = _rate(speed, "video speed")
        if (
            (source_end - source_start) * speed_rate.denominator
            != (timeline_end - timeline_start) * speed_rate.numerator
        ):
            raise RenderArtifactError("video speed/source duration is inexact")
        transform = _closed(
            clip["transform"],
            _VIDEO_COMPOSITION_TRANSFORM_FIELDS,
            "video transform",
        )
        for field in (
            "positionXPixels",
            "positionYPixels",
            "rotationMilliDegrees",
            "anchorXPixels",
            "anchorYPixels",
        ):
            value = transform[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise RenderArtifactError(f"video transform {field} is invalid")
        for field in ("scaleX", "scaleY"):
            _rate(transform[field], f"video transform {field}")
        _integer(transform["opacity"], "video transform opacity", maximum=1000)
        for field in ("transitionIn", "transitionOut"):
            transition = clip[field]
            if transition is None:
                continue
            transition = _closed(
                transition,
                _VIDEO_COMPOSITION_TRANSITION_FIELDS,
                f"video {field}",
            )
            duration = _integer(
                transition["durationFrames"],
                f"video {field} duration",
                maximum=timeline_end - timeline_start,
            )
            if (
                transition["kind"]
                not in {"CUT", "CROSSFADE", "FADE_IN", "FADE_OUT", "DIP_TO_BLACK"}
                or transition["curve"] != "LINEAR"
                or transition["alignment"] not in {"START", "CENTER", "END"}
                or (transition["kind"] == "CUT") != (duration == 0)
                or (field == "transitionIn" and transition["kind"] == "FADE_OUT")
                or (field == "transitionOut" and transition["kind"] == "FADE_IN")
            ):
                raise RenderArtifactError("video transition is unsupported")
            clip[field] = transition
        masks = clip["maskBindingDigests"]
        if not isinstance(masks, list):
            raise RenderArtifactError("video mask binding digests are invalid")
        for digest in masks:
            _raw_digest(digest, "video mask binding digest")
        if masks:
            raise RenderArtifactError(
                "clip-local video masks are not available in the R1 source projection"
            )
        clip["speed"] = speed
        clip["transform"] = transform
        clips.append(clip)
    canonical = sorted(
        clips,
        key=lambda item: (
            item["layer"],
            item["zOrder"],
            item["timelineStartFrameInclusive"],
            item["clipRef"],
        ),
    )
    if clips != canonical or len({item["clipRef"] for item in clips}) != len(clips):
        raise RenderArtifactError("video composition clip order is not canonical")
    plan["clips"] = clips
    plan["frameRate"] = {
        "numerator": rate.numerator,
        "denominator": rate.denominator,
    }
    return plan


def build_video_composition_plan(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _VIDEO_COMPOSITION_PLAN_FIELDS - frozenset(
        {"schemaVersion", "payloadDigest"}
    )
    selected = _closed(command, fields, "video composition plan command")
    result = {
        "schemaVersion": VIDEO_COMPOSITION_PLAN_SCHEMA_VERSION,
        **selected,
    }
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return _validate_video_composition_plan(result)


def _validate_cues(value: Any, *, frame_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RenderArtifactError("subtitleCues is invalid")
    result: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        cue = _closed(raw, _CUE_FIELDS, f"subtitle cue {index}")
        _ref(cue["cueRef"], "subtitle cueRef")
        _ref(cue["clipRef"], "subtitle clipRef")
        start = _integer(cue["timelineStartFrameInclusive"], "subtitle start")
        end = _integer(cue["timelineEndFrameExclusive"], "subtitle end", minimum=1)
        text = cue["text"]
        if (
            start >= end
            or end > frame_count
            or not isinstance(text, str)
            or not text
            or text != text.strip()
            or cue["textDigest"] != sha256(text.encode("utf-8")).hexdigest()
        ):
            raise RenderArtifactError("subtitle cue authority is stale")
        _ref(cue["language"], "subtitle language")
        words = cue["wordTiming"]
        if not isinstance(words, list):
            raise RenderArtifactError("subtitle word timing is invalid")
        normalized_words: list[dict[str, Any]] = []
        for word_index, raw_word in enumerate(words):
            word = _closed(raw_word, _WORD_FIELDS, f"subtitle word {word_index}")
            _ref(word["wordRef"], "subtitle wordRef")
            word_start = _integer(word["timelineStartFrameInclusive"], "word start")
            word_end = _integer(word["timelineEndFrameExclusive"], "word end", minimum=1)
            word_text = word["text"]
            if (
                word_start < start
                or word_end > end
                or word_start >= word_end
                or not isinstance(word_text, str)
                or not word_text
                or word["textDigest"]
                != sha256(word_text.encode("utf-8")).hexdigest()
            ):
                raise RenderArtifactError("subtitle word authority is stale")
            normalized_words.append(word)
        if normalized_words != sorted(
            normalized_words,
            key=lambda item: (
                item["timelineStartFrameInclusive"],
                item["timelineEndFrameExclusive"],
                item["wordRef"],
            ),
        ):
            raise RenderArtifactError("subtitle words are not canonical")
        cue["wordTiming"] = normalized_words
        result.append(cue)
    if result != sorted(
        result,
        key=lambda item: (
            item["timelineStartFrameInclusive"],
            item["timelineEndFrameExclusive"],
            item["clipRef"],
        ),
    ):
        raise RenderArtifactError("subtitle cues are not canonical")
    return result


def validate_render_core_request(value: Any) -> dict[str, Any]:
    request = _closed(value, _REQUEST_FIELDS, "render-core request")
    supplied = _raw_digest(request.pop("payloadDigest"), "payloadDigest")
    if supplied != sha256(_canonical_json(request)).hexdigest():
        raise RenderArtifactError("render-core request seal is invalid")
    request["payloadDigest"] = supplied
    if (
        request["schemaVersion"] != RENDER_CORE_REQUEST_SCHEMA_VERSION
        or request["publicationAllowed"] is not False
    ):
        raise RenderArtifactError("render-core execution boundary is invalid")
    for field in (
        "executionRequestRef",
        "workspaceRef",
        "productionRunRef",
        "outputArtifactBindingRef",
    ):
        _ref(request[field], field)
    _raw_digest(request["executionRequestDigest"], "executionRequestDigest")
    source = _closed(request["sourceArtifact"], _SOURCE_FIELDS, "sourceArtifact")
    _storage_key(source["storageKey"], "sourceArtifact.storageKey")
    _integer(source["byteSize"], "sourceArtifact.byteSize", minimum=1)
    for field in ("fileDigest", "decodedFramePixelDigest", "pcmContentDigest"):
        _content_digest(source[field], f"sourceArtifact.{field}")
    if (
        source["decodedFramePixelDigestSpec"]
        != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
        or source["pcmContentDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
    ):
        raise RenderArtifactError("sourceArtifact content contract is invalid")
    probe = _closed(
        source["mediaProbe"],
        _SOURCE_MEDIA_PROBE_FIELDS,
        "sourceArtifact.mediaProbe",
    )
    profile = _closed(request["renderProfile"], _PROFILE_FIELDS, "renderProfile")
    output = _closed(profile["outputProfile"], _OUTPUT_PROFILE_FIELDS, "outputProfile")
    width = _integer(output["width"], "output width", minimum=2, maximum=131_072)
    height = _integer(output["height"], "output height", minimum=2, maximum=131_072)
    if width % 2 or height % 2:
        raise RenderArtifactError("render output dimensions must be even")
    frame_rate = Fraction(
        _integer(output["frameRateNumerator"], "frame rate numerator", minimum=1),
        _integer(output["frameRateDenominator"], "frame rate denominator", minimum=1),
    )
    if (
        frame_rate.numerator != output["frameRateNumerator"]
        or frame_rate.denominator != output["frameRateDenominator"]
        or output["pixelAspectRatioNumerator"] != 1
        or output["pixelAspectRatioDenominator"] != 1
        or output["resizeMode"] not in {"EXACT", "FIT_PAD", "FILL_CROP"}
        or output["backgroundPolicy"]
        not in {"BLACK", "TIMELINE_BACKGROUND", "TRANSPARENT_WHEN_SUPPORTED"}
    ):
        raise RenderArtifactError("outputProfile is unsupported")
    safe_area = _closed(output["safeArea"], _SAFE_AREA_FIELDS, "safeArea")
    for field in _SAFE_AREA_FIELDS:
        _integer(safe_area[field], field, maximum=max(width, height))
    if (
        safe_area["leftPixels"] + safe_area["rightPixels"] >= width
        or safe_area["topPixels"] + safe_area["bottomPixels"] >= height
    ):
        raise RenderArtifactError("safeArea exceeds output dimensions")
    output["safeArea"] = safe_area
    _ref(output["profileRef"], "profileRef")
    video = _closed(profile["videoEncoding"], _VIDEO_ENCODING_FIELDS, "videoEncoding")
    if (
        video["codec"] != "H264"
        or video["pixelFormat"] != "YUV420P"
        or video["qualityMode"] != "CRF"
        or video["deterministicThreadPolicy"] != "SINGLE_THREAD"
        or video["profile"] not in {"BASELINE", "MAIN", "HIGH"}
        or video["level"] not in {"3.1", "4.0", "4.1", "5.0", "5.1"}
    ):
        raise RenderArtifactError("videoEncoding is unsupported")
    _integer(video["qualityValue"], "qualityValue", maximum=51)
    _integer(video["gopFrames"], "gopFrames", minimum=1, maximum=10_000)
    color = _closed(profile["colorMetadata"], _COLOR_FIELDS, "colorMetadata")
    if any(color[field] != expected for field, expected in {
        "colorPrimaries": "BT709",
        "colorTransfer": "BT709",
        "colorSpace": "BT709",
    }.items()) or color["colorRange"] not in {"TV", "PC"}:
        raise RenderArtifactError("colorMetadata is unsupported")
    audio = _closed(profile["audioEncoding"], _AUDIO_ENCODING_FIELDS, "audioEncoding")
    if (
        audio["enabled"] is not True
        or audio["codec"] != "AAC"
        or audio["sampleRate"] != 48_000
        or audio["channelCount"] != 2
        or not 8_000 <= audio["bitrate"] <= 1_536_000
    ):
        raise RenderArtifactError("R1 render audio contract is unsupported")
    mode = profile["subtitleMode"]
    if mode not in {"NONE", "SIDECAR", "BURN_IN"}:
        raise RenderArtifactError("subtitleMode is unsupported")
    for field in (
        "rendererIdentity",
        "rendererVersion",
    ):
        _ref(profile[field], field)
    if (
        profile["rendererIdentity"] != RENDERER_IDENTITY
        or profile["rendererVersion"] != RENDERER_VERSION
    ):
        raise RenderArtifactError("renderer identity is unsupported")
    for field in ("ffmpegBinaryDigest", "ffprobeBinaryDigest"):
        _raw_digest(profile[field], field)
    source_width = _integer(probe["width"], "source width", minimum=2)
    source_height = _integer(probe["height"], "source height", minimum=2)
    if (
        source_width % 2
        or source_height % 2
        or probe["container"] != "mp4"
        or probe["videoCodec"] != "h264"
        or probe["pixelFormat"] != "yuv420p"
        or probe["audioCodec"] != "aac"
        or probe["sampleRate"] != 48_000
        or probe["channelCount"] != 2
        or probe.get("frameRate")
        != {"numerator": frame_rate.numerator, "denominator": frame_rate.denominator}
    ):
        raise RenderArtifactError("source frame-rate contract is stale")
    frame_count = _integer(probe["frameCount"], "source frameCount", minimum=1)
    sample_count = _integer(probe["sampleCount"], "source sampleCount", minimum=1)
    if (
        frame_count * 48_000 * frame_rate.denominator
        != sample_count * frame_rate.numerator
    ):
        raise RenderArtifactError("source duration contract is stale")
    video_plan = _validate_video_composition_plan(
        request["videoCompositionPlan"]
    )
    if (
        video_plan["canvasWidth"] != source_width
        or video_plan["canvasHeight"] != source_height
        or video_plan["frameRate"] != probe["frameRate"]
        or video_plan["totalFrames"] != frame_count
        or any(
            item["sourceOutFrameExclusive"] > frame_count
            for item in video_plan["clips"]
        )
    ):
        raise RenderArtifactError("video composition plan source is stale")
    cues = _validate_cues(request["subtitleCues"], frame_count=frame_count)
    timing_digest = _canonical_subtitle_timing(cues)
    expected_timing = profile["subtitleTimingDigest"]
    if mode == "NONE":
        if expected_timing is not None or cues or request["subtitleFont"] is not None:
            raise RenderArtifactError("NONE subtitle binding is invalid")
    else:
        if expected_timing != timing_digest:
            raise RenderArtifactError("subtitle timing digest is stale")
        if mode == "SIDECAR" and request["subtitleFont"] is not None:
            raise RenderArtifactError("SIDECAR cannot bind a render font")
        if mode == "BURN_IN":
            font = _closed(request["subtitleFont"], _FONT_FIELDS, "subtitleFont")
            _storage_key(font["storageKey"], "subtitleFont.storageKey")
            _raw_digest(font["fileDigest"], "subtitleFont.fileDigest")
            _integer(font["byteSize"], "subtitleFont.byteSize", minimum=1)
            if not isinstance(font["fontFamily"], str) or not font["fontFamily"].strip():
                raise RenderArtifactError("subtitle font family is invalid")
            request["subtitleFont"] = font
    request["sourceArtifact"] = source
    source["mediaProbe"] = probe
    request["videoCompositionPlan"] = video_plan
    profile["outputProfile"] = output
    profile["videoEncoding"] = video
    profile["colorMetadata"] = color
    profile["audioEncoding"] = audio
    request["renderProfile"] = profile
    request["subtitleCues"] = cues
    return request


def build_render_core_request(command: Mapping[str, Any]) -> dict[str, Any]:
    fields = _REQUEST_FIELDS - frozenset({"schemaVersion", "payloadDigest"})
    selected = _closed(command, fields, "render-core request command")
    result = {
        "schemaVersion": RENDER_CORE_REQUEST_SCHEMA_VERSION,
        **selected,
    }
    result["payloadDigest"] = sha256(_canonical_json(result)).hexdigest()
    return validate_render_core_request(result)


def render_candidate_storage_key(
    workspace_ref: str,
    production_run_ref: str,
    storage_binding_ref: str,
    *,
    sidecar: bool = False,
) -> str:
    _ref(workspace_ref, "workspaceRef")
    _ref(production_run_ref, "productionRunRef")
    binding = _ref(storage_binding_ref, "storageBindingRef")
    workspace_hash = sha256(workspace_ref.encode("utf-8")).hexdigest()[:20]
    run_hash = sha256(production_run_ref.encode("utf-8")).hexdigest()[:20]
    identity = sha256(binding.encode("utf-8")).hexdigest()
    suffix = ".vtt" if sidecar else ".mp4"
    return f"{workspace_hash}/{run_hash}/render-candidates/render-{identity}{suffix}"


def _scale_filter(profile: Mapping[str, Any]) -> str:
    width = profile["width"]
    height = profile["height"]
    mode = profile["resizeMode"]
    if mode == "EXACT":
        return f"scale={width}:{height}:flags=bicubic"
    if mode == "FIT_PAD":
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
            "force_divisible_by=2:flags=bicubic,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:"
        "force_divisible_by=2:flags=bicubic,"
        f"crop={width}:{height}"
    )


def _probe_streams(
    probe: Mapping[str, Any],
    *,
    label: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    streams = probe.get("streams")
    format_record = probe.get("format")
    if (
        not isinstance(streams, list)
        or len(streams) != 2
        or not isinstance(format_record, Mapping)
        or "mp4"
        not in str(format_record.get("format_name", "")).split(",")
    ):
        raise RenderArtifactError(f"{label} container or stream layout is invalid")
    videos = [
        item
        for item in streams
        if isinstance(item, Mapping) and item.get("codec_type") == "video"
    ]
    audios = [
        item
        for item in streams
        if isinstance(item, Mapping) and item.get("codec_type") == "audio"
    ]
    if len(videos) != 1 or len(audios) != 1:
        raise RenderArtifactError(f"{label} stream layout is invalid")
    return videos[0], audios[0]


def _validate_source_media_probe(
    probe: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    video, audio = _probe_streams(probe, label="render source")
    try:
        sample_rate = int(audio.get("sample_rate"))
        channels = int(audio.get("channels"))
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError("render source audio probe is invalid") from exc
    if (
        video.get("codec_name") != expected["videoCodec"]
        or video.get("pix_fmt") != expected["pixelFormat"]
        or _stream_integer(video, "width", label="render source width")
        != expected["width"]
        or _stream_integer(video, "height", label="render source height")
        != expected["height"]
        or _stream_frame_count(video, label="render source")
        != expected["frameCount"]
        or _stream_frame_rate(video, label="render source")
        != _rate(expected["frameRate"], "render source frameRate")
        or audio.get("codec_name") != expected["audioCodec"]
        or sample_rate != expected["sampleRate"]
        or channels != expected["channelCount"]
    ):
        raise RenderArtifactError("render source media probe changed")


def _render_media_probe(
    probe: Mapping[str, Any],
    *,
    output: Mapping[str, Any],
    color: Mapping[str, Any],
    frame_rate: Fraction,
    frame_count: int,
    duration_samples: int,
) -> dict[str, Any]:
    video, audio = _probe_streams(probe, label="render output")
    try:
        sample_rate = int(audio.get("sample_rate"))
        channels = int(audio.get("channels"))
    except (TypeError, ValueError) as exc:
        raise RenderArtifactError("render output audio probe is invalid") from exc
    expected_range = "tv" if color["colorRange"] == "TV" else "pc"
    if (
        video.get("codec_name") != "h264"
        or video.get("pix_fmt") != "yuv420p"
        or _stream_integer(video, "width", label="render width")
        != output["width"]
        or _stream_integer(video, "height", label="render height")
        != output["height"]
        or _stream_frame_count(video, label="render output") != frame_count
        or _stream_frame_rate(video, label="render output") != frame_rate
        or video.get("color_primaries") != "bt709"
        or video.get("color_transfer") != "bt709"
        or video.get("color_space") != "bt709"
        or video.get("color_range") != expected_range
        or audio.get("codec_name") != "aac"
        or sample_rate != 48_000
        or channels != 2
    ):
        raise RenderArtifactError("render output media probe is invalid")
    return {
        "container": "mp4",
        "videoCodec": "h264",
        "width": output["width"],
        "height": output["height"],
        "frameRate": {
            "numerator": frame_rate.numerator,
            "denominator": frame_rate.denominator,
        },
        "frameCount": frame_count,
        "pixelFormat": "yuv420p",
        "colorMetadata": deepcopy(color),
        "audioCodec": "aac",
        "audioSampleRate": 48_000,
        "audioChannels": 2,
        "audioSampleCount": duration_samples,
        "duration": {
            "samples": duration_samples,
            "sampleRate": 48_000,
        },
    }


def _video_composition_graph(
    plan: Mapping[str, Any], *, final_video_filter: str
) -> str:
    """Build the closed trim/speed/transition/transform/layer graph in code."""

    clips = plan["clips"]
    rate = _rate(plan["frameRate"], "video composition frameRate")
    filters: list[str] = []
    if len(clips) == 1:
        filters.append("[0:v]null[src0]")
    else:
        outputs = "".join(f"[src{index}]" for index in range(len(clips)))
        filters.append(f"[0:v]split={len(clips)}{outputs}")
    filters.append(
        f"color=c=black:s={plan['canvasWidth']}x{plan['canvasHeight']}:"
        f"r={rate.numerator}/{rate.denominator},"
        f"trim=end_frame={plan['totalFrames']},setpts=PTS-STARTPTS,"
        "format=rgba[canvas0]"
    )
    canvas_label = "canvas0"
    for index, clip in enumerate(clips):
        speed = clip["speed"]
        transform = clip["transform"]
        scale_x = _rate(transform["scaleX"], "video transform scaleX")
        scale_y = _rate(transform["scaleY"], "video transform scaleY")
        start = clip["timelineStartFrameInclusive"]
        span = clip["timelineEndFrameExclusive"] - start
        chain = (
            f"[src{index}]trim=start_frame={clip['sourceInFrameInclusive']}:"
            f"end_frame={clip['sourceOutFrameExclusive']},"
            f"setpts=(PTS-STARTPTS)*{speed['denominator']}/{speed['numerator']},"
            "format=rgba,"
            f"scale=w='max(2,2*trunc(iw*{scale_x.numerator}/"
            f"(2*{scale_x.denominator})))':"
            f"h='max(2,2*trunc(ih*{scale_y.numerator}/"
            f"(2*{scale_y.denominator})))':flags=bicubic"
        )
        rotation = transform["rotationMilliDegrees"]
        if rotation:
            angle = f"({rotation}*PI/180000)"
            chain += (
                f",rotate=a='{angle}':ow='rotw({angle})':"
                f"oh='roth({angle})':fillcolor=black@0"
            )
        opacity = clip["opacity"] * transform["opacity"] // 1000
        if opacity != 1000:
            chain += f",colorchannelmixer=aa={opacity / 1000:.3f}"
        transition_in = clip["transitionIn"]
        if transition_in is not None and transition_in["kind"] in {
            "CROSSFADE",
            "FADE_IN",
            "DIP_TO_BLACK",
        }:
            chain += (
                f",fade=t=in:s=0:n={transition_in['durationFrames']}:alpha=1"
            )
        transition_out = clip["transitionOut"]
        if transition_out is not None and transition_out["kind"] in {
            "CROSSFADE",
            "FADE_OUT",
            "DIP_TO_BLACK",
        }:
            chain += (
                f",fade=t=out:s={span - transition_out['durationFrames']}:"
                f"n={transition_out['durationFrames']}:alpha=1"
            )
        chain += (
            f",setpts=PTS+{start * rate.denominator}/{rate.numerator}/TB"
            f"[clip{index}]"
        )
        filters.append(chain)
        output_label = f"canvas{index + 1}"
        x = transform["positionXPixels"] - transform["anchorXPixels"]
        y = transform["positionYPixels"] - transform["anchorYPixels"]
        filters.append(
            f"[{canvas_label}][clip{index}]overlay=x={x}:y={y}:"
            f"eof_action=pass:shortest=0:format=auto[{output_label}]"
        )
        canvas_label = output_label
    filters.append(
        f"[{canvas_label}]trim=end_frame={plan['totalFrames']},"
        f"setpts=PTS-STARTPTS,{final_video_filter}[vout]"
    )
    return ";".join(filters)


def _vtt_timestamp(frame: int, rate: Fraction) -> str:
    milliseconds = frame * 1000 * rate.denominator // rate.numerator
    hours, remaining = divmod(milliseconds, 3_600_000)
    minutes, remaining = divmod(remaining, 60_000)
    seconds, millis = divmod(remaining, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _vtt_bytes(cues: list[Mapping[str, Any]], rate: Fraction) -> bytes:
    lines = ["WEBVTT", ""]
    for index, cue in enumerate(cues, start=1):
        text = cue["text"].replace("\r", " ").replace("\n", " ")
        if "-->" in text:
            raise RenderArtifactError("subtitle text contains a forbidden cue token")
        lines.extend(
            [
                str(index),
                f"{_vtt_timestamp(cue['timelineStartFrameInclusive'], rate)} --> "
                f"{_vtt_timestamp(cue['timelineEndFrameExclusive'], rate)}",
                text,
                "",
            ]
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _publish_bytes_no_replace(
    *,
    root: Path,
    path: Path,
    content: bytes,
    temporary_directory: Path,
) -> None:
    """Publish bytes through the same held-descriptor path as video output."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".render-sidecar-",
            suffix=".vtt",
            dir=temporary_directory,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        with _PinnedRegularFile(
            temporary_path, label="render subtitle sidecar source"
        ) as pinned:
            _publish_timeline_output_v1(
                root=root,
                directory=path.parent,
                source=pinned,
                expected_file_digest=f"sha256:{sha256(content).hexdigest()}",
                output_name=path.name,
            )
            pinned.require_stable()
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


class DeterministicRenderCandidateExecutor:
    def __init__(self, artifact_root: Path | str) -> None:
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def render(self, value: Mapping[str, Any]) -> dict[str, Any]:
        request = validate_render_core_request(value)
        profile = request["renderProfile"]
        source = request["sourceArtifact"]
        output = profile["outputProfile"]
        video = profile["videoEncoding"]
        audio = profile["audioEncoding"]
        color = profile["colorMetadata"]
        frame_rate = Fraction(
            output["frameRateNumerator"], output["frameRateDenominator"]
        )
        video_plan = request["videoCompositionPlan"]
        frame_count = video_plan["totalFrames"]
        duration_samples = (
            frame_count * 48_000 * frame_rate.denominator // frame_rate.numerator
        )
        with (
            _PinnedRuntimeBinary(_runtime_path("ffmpeg"), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(_runtime_path("ffprobe"), label="FFprobe") as ffprobe,
            tempfile.TemporaryDirectory(
                prefix=".render-candidate-work-", dir=self.artifact_root
            ) as temporary,
        ):
            if (
                ffmpeg.binary_digest != profile["ffmpegBinaryDigest"]
                or ffprobe.binary_digest != profile["ffprobeBinaryDigest"]
            ):
                raise RenderArtifactError("render runtime binary digest drifted")
            work_root = Path(temporary)
            work_root.chmod(0o700)
            source_path = work_root / "source.mp4"
            _stage_timeline_preview_input(
                root=self.artifact_root,
                storage_key=source["storageKey"],
                expected_digest=source["fileDigest"],
                destination=source_path,
                prefixed_digest=source["fileDigest"].startswith("sha256:"),
            )
            with _PinnedRegularFile(source_path, label="render candidate source") as pinned_source:
                if (
                    pinned_source.descriptor is None
                    or os.fstat(pinned_source.descriptor).st_size
                    != source["byteSize"]
                ):
                    raise RenderArtifactError("render source byte size changed")
                pass_fds = (
                    *pinned_source.pass_fds,
                    *ffmpeg.pass_fds,
                    *ffprobe.pass_fds,
                )
                source_probe = _glyph_probe(
                    pinned_source.descriptor_path,
                    ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
                _validate_source_media_probe(
                    source_probe,
                    source["mediaProbe"],
                )
                try:
                    measured_pixels = decoded_frame_pixel_digest_metadata(
                        pinned_source.descriptor_path,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=pass_fds,
                    )
                    measured_pcm = canonical_pcm_digest_metadata(
                        pinned_source.source_path,
                        expected_sample_count=source["mediaProbe"]["sampleCount"],
                        allow_aac_frame_padding=True,
                        ffmpeg_path=ffmpeg.executable_path,
                        ffprobe_path=ffprobe.executable_path,
                        pass_fds=(*ffmpeg.pass_fds, *ffprobe.pass_fds),
                        _input_descriptor=pinned_source.descriptor,
                    )
                except DigestError as exc:
                    raise RenderArtifactError("render source content digest failed") from exc
                if (
                    measured_pixels["fileDigest"] != source["fileDigest"]
                    or measured_pixels["decodedFramePixelDigest"]
                    != source["decodedFramePixelDigest"]
                    or measured_pixels["decodedFramePixelDigestSpec"]
                    != source["decodedFramePixelDigestSpec"]
                    or measured_pcm["pcmContentDigest"] != source["pcmContentDigest"]
                    or measured_pcm["pcmDigestSpec"] != source["pcmContentDigestSpec"]
                    or measured_pixels["width"] != source["mediaProbe"]["width"]
                    or measured_pixels["height"] != source["mediaProbe"]["height"]
                    or measured_pixels["frameCount"]
                    != source["mediaProbe"]["frameCount"]
                    or measured_pcm["sampleRate"]
                    != source["mediaProbe"]["sampleRate"]
                    or measured_pcm["channelCount"]
                    != source["mediaProbe"]["channelCount"]
                    or measured_pcm["sampleCount"]
                    != source["mediaProbe"]["sampleCount"]
                ):
                    raise RenderArtifactError("render source content changed")
                font_path: Path | None = None
                if request["subtitleFont"] is not None:
                    font_path = work_root / "subtitle-font.ttf"
                    font = request["subtitleFont"]
                    _stage_timeline_preview_input(
                        root=self.artifact_root,
                        storage_key=font["storageKey"],
                        expected_digest=font["fileDigest"],
                        destination=font_path,
                        prefixed_digest=False,
                    )
                    if font_path.stat().st_size != font["byteSize"]:
                        raise RenderArtifactError("subtitle font size changed")

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
                    "-fflags",
                    "+bitexact",
                    "-hwaccel",
                    "none",
                    "-noautorotate",
                    "-i",
                    str(pinned_source.descriptor_path),
                ]
                scale = _scale_filter(output)
                if profile["subtitleMode"] == "BURN_IN":
                    vtt_path = work_root / "subtitles.vtt"
                    vtt_path.write_bytes(_vtt_bytes(request["subtitleCues"], frame_rate))
                    escaped_vtt = str(vtt_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                    escaped_fonts = str(font_path.parent).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                    family = request["subtitleFont"]["fontFamily"].replace("'", "").replace(",", " ")
                    font_size = max(12, min(72, output["width"] // 18))
                    margin = max(8, output["height"] // 24)
                    video_filter = (
                        f"{scale},setsar=1,subtitles=filename='{escaped_vtt}':"
                        f"fontsdir='{escaped_fonts}':force_style='FontName={family},"
                        f"FontSize={font_size},Alignment=2,MarginV={margin},"
                        "BorderStyle=3,Outline=1,Shadow=0',format=yuv420p"
                    )
                else:
                    video_filter = f"{scale},setsar=1,format=yuv420p"
                video_graph = _video_composition_graph(
                    video_plan,
                    final_video_filter=video_filter,
                )
                command.extend(
                    [
                        "-filter_complex",
                        video_graph,
                        "-af",
                        f"atrim=end_sample={duration_samples},asetpts=N/SR/TB,"
                        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo",
                        "-map",
                        "[vout]",
                        "-map",
                        "0:a:0",
                        "-frames:v",
                        str(frame_count),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "medium",
                        "-crf",
                        str(video["qualityValue"]),
                        "-profile:v",
                        video["profile"].lower(),
                        "-level:v",
                        video["level"],
                        "-pix_fmt",
                        "yuv420p",
                        "-g",
                        str(video["gopFrames"]),
                        "-keyint_min",
                        str(video["gopFrames"]),
                        "-sc_threshold",
                        "0",
                        "-x264-params",
                        "threads=1:lookahead_threads=1:sliced_threads=0:sync-lookahead=0",
                        "-color_primaries",
                        "bt709",
                        "-color_trc",
                        "bt709",
                        "-colorspace",
                        "bt709",
                        "-color_range",
                        "tv" if color["colorRange"] == "TV" else "pc",
                        "-c:a",
                        "aac",
                        "-b:a",
                        str(audio["bitrate"]),
                        "-ar",
                        "48000",
                        "-ac",
                        "2",
                        "-flags:v",
                        "+bitexact",
                        "-flags:a",
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
                        str(frame_rate.numerator * 512),
                        "-n",
                        str(candidate),
                    ]
                )
                try:
                    subprocess.run(
                        command,
                        check=True,
                        capture_output=True,
                        timeout=600,
                        env=_fixed_environment(),
                        pass_fds=pass_fds,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    raise RenderArtifactError("deterministic final render failed") from exc
                result = self._verify_and_publish(
                    candidate=candidate,
                    request=request,
                    frame_rate=frame_rate,
                    frame_count=frame_count,
                    duration_samples=duration_samples,
                    ffmpeg=ffmpeg,
                    ffprobe=ffprobe,
                )
                pinned_source.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
            return result

    def _verify_and_publish(
        self,
        *,
        candidate: Path,
        request: Mapping[str, Any],
        frame_rate: Fraction,
        frame_count: int,
        duration_samples: int,
        ffmpeg: _PinnedRuntimeBinary,
        ffprobe: _PinnedRuntimeBinary,
    ) -> dict[str, Any]:
        output = request["renderProfile"]["outputProfile"]
        with _PinnedRegularFile(candidate, label="render candidate output") as pinned:
            pass_fds = (*pinned.pass_fds, *ffmpeg.pass_fds, *ffprobe.pass_fds)
            probe = _glyph_probe(
                pinned.descriptor_path,
                ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            try:
                pixels = decoded_frame_pixel_digest_metadata(
                    pinned.descriptor_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
                pcm = canonical_pcm_digest_metadata(
                    pinned.source_path,
                    expected_sample_count=duration_samples,
                    allow_aac_frame_padding=True,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=(*ffmpeg.pass_fds, *ffprobe.pass_fds),
                    _input_descriptor=pinned.descriptor,
                )
            except DigestError as exc:
                raise RenderArtifactError("render output content digest failed") from exc
            if (
                pixels["width"] != output["width"]
                or pixels["height"] != output["height"]
                or pixels["frameCount"] != frame_count
                or pixels["decodedFramePixelDigestSpec"]
                != DECODED_FRAME_PIXEL_DIGEST_SPEC_V2
                or pcm["pcmDigestSpec"] != PCM_CONTENT_DIGEST_SPEC
                or pcm["sampleRate"] != 48_000
                or pcm["channelCount"] != 2
                or pcm["sampleCount"] != duration_samples
            ):
                raise RenderArtifactError("render output content contract is invalid")
            media_probe = _render_media_probe(
                probe,
                output=output,
                color=request["renderProfile"]["colorMetadata"],
                frame_rate=frame_rate,
                frame_count=frame_count,
                duration_samples=duration_samples,
            )
            storage_key = render_candidate_storage_key(
                request["workspaceRef"],
                request["productionRunRef"],
                request["outputArtifactBindingRef"],
            )
            destination = self.artifact_root / storage_key
            published = _publish_timeline_output_v1(
                root=self.artifact_root,
                directory=destination.parent,
                source=pinned,
                expected_file_digest=pixels["fileDigest"],
                output_name=destination.name,
            )
            subtitle_sidecar = None
            if request["renderProfile"]["subtitleMode"] == "SIDECAR":
                sidecar_content = _vtt_bytes(request["subtitleCues"], frame_rate)
                sidecar_key = render_candidate_storage_key(
                    request["workspaceRef"],
                    request["productionRunRef"],
                    request["outputArtifactBindingRef"],
                    sidecar=True,
                )
                sidecar_path = self.artifact_root / sidecar_key
                _publish_bytes_no_replace(
                    root=self.artifact_root,
                    path=sidecar_path,
                    content=sidecar_content,
                    temporary_directory=candidate.parent,
                )
                subtitle_sidecar = {
                    "storageKey": sidecar_key,
                    "mediaType": "text/vtt",
                    "byteSize": len(sidecar_content),
                    "fileDigest": sha256(sidecar_content).hexdigest(),
                }
            pinned.require_stable()
        ffmpeg.require_stable()
        ffprobe.require_stable()
        timing_digest = _canonical_subtitle_timing(request["subtitleCues"])
        result = {
            "schemaVersion": RENDER_CORE_RESULT_SCHEMA_VERSION,
            "internalPath": str(published),
            "outputStorageKey": storage_key,
            "outputArtifactBindingRef": request["outputArtifactBindingRef"],
            "outputByteSize": published.stat().st_size,
            "outputMediaProbe": media_probe,
            "fileDigest": pixels["fileDigest"],
            "decodedFramePixelDigest": pixels["decodedFramePixelDigest"],
            "decodedFramePixelDigestSpec": pixels["decodedFramePixelDigestSpec"],
            "pcmContentDigest": pcm["pcmContentDigest"],
            "pcmContentDigestSpec": pcm["pcmDigestSpec"],
            "subtitleTimingDigest": timing_digest,
            "subtitleTimingDigestSpec": SUBTITLE_TIMING_DIGEST_SPEC,
            "subtitleSidecar": subtitle_sidecar,
            "rendererIdentity": RENDERER_IDENTITY,
            "rendererVersion": RENDERER_VERSION,
            "ffmpegBinaryDigest": ffmpeg.binary_digest,
            "ffprobeBinaryDigest": ffprobe.binary_digest,
            "executionRequestRef": request["executionRequestRef"],
            "executionRequestDigest": request["executionRequestDigest"],
            "gpuUsed": False,
            "providerUsed": False,
            "publicationAllowed": False,
        }
        # Close the publication window before V4 may report success.  This is
        # deliberately a fresh path open and a fresh runtime pin, not reuse of
        # the pre-publication candidate descriptor.
        self.inspect(
            workspace_ref=request["workspaceRef"],
            production_run_ref=request["productionRunRef"],
            storage_binding_ref=request["outputArtifactBindingRef"],
            expected={
                "byteSize": result["outputByteSize"],
                "mediaType": "video/mp4",
                "mediaProbe": result["outputMediaProbe"],
                "fileDigest": result["fileDigest"],
                "decodedFramePixelDigest": result[
                    "decodedFramePixelDigest"
                ],
                "decodedFramePixelDigestSpec": result[
                    "decodedFramePixelDigestSpec"
                ],
                "pcmContentDigest": result["pcmContentDigest"],
                "pcmContentDigestSpec": result["pcmContentDigestSpec"],
                "subtitleSidecar": result["subtitleSidecar"],
                "ffmpegBinaryDigest": result["ffmpegBinaryDigest"],
                "ffprobeBinaryDigest": result["ffprobeBinaryDigest"],
            },
        )
        return result

    def inspect(
        self,
        *,
        workspace_ref: str,
        production_run_ref: str,
        storage_binding_ref: str,
        expected: Mapping[str, Any],
    ) -> dict[str, Any]:
        storage_key = render_candidate_storage_key(
            workspace_ref, production_run_ref, storage_binding_ref
        )
        path = self.artifact_root / storage_key
        if not path.exists():
            raise RenderArtifactError("render candidate artifact is unavailable")
        with (
            _PinnedRuntimeBinary(_runtime_path("ffmpeg"), label="FFmpeg") as ffmpeg,
            _PinnedRuntimeBinary(_runtime_path("ffprobe"), label="FFprobe") as ffprobe,
            _PinnedRegularFile(path, label="published render candidate") as pinned,
        ):
            if (
                ffmpeg.binary_digest != expected.get("ffmpegBinaryDigest")
                or ffprobe.binary_digest != expected.get("ffprobeBinaryDigest")
            ):
                raise RenderArtifactError("render candidate runtime drifted")
            pass_fds = (*pinned.pass_fds, *ffmpeg.pass_fds, *ffprobe.pass_fds)
            media_probe = expected.get("mediaProbe")
            if not isinstance(media_probe, Mapping):
                raise RenderArtifactError("render candidate media probe is invalid")
            fresh_probe = _glyph_probe(
                pinned.descriptor_path,
                ffprobe.executable_path,
                pass_fds=pass_fds,
            )
            try:
                expected_rate = _rate(
                    media_probe["frameRate"],
                    "render candidate frameRate",
                )
                expected_frames = _integer(
                    media_probe["frameCount"],
                    "render candidate frameCount",
                    minimum=1,
                )
                expected_samples = _integer(
                    media_probe["audioSampleCount"],
                    "render candidate audioSampleCount",
                    minimum=1,
                )
                measured_probe = _render_media_probe(
                    fresh_probe,
                    output={
                        "width": media_probe["width"],
                        "height": media_probe["height"],
                    },
                    color=media_probe["colorMetadata"],
                    frame_rate=expected_rate,
                    frame_count=expected_frames,
                    duration_samples=expected_samples,
                )
            except (KeyError, TypeError) as exc:
                raise RenderArtifactError(
                    "render candidate media probe is invalid"
                ) from exc
            if measured_probe != media_probe:
                raise RenderArtifactError("render candidate media probe drifted")
            try:
                pixels = decoded_frame_pixel_digest_metadata(
                    pinned.descriptor_path,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=pass_fds,
                )
                pcm = canonical_pcm_digest_metadata(
                    pinned.source_path,
                    expected_sample_count=expected_samples,
                    allow_aac_frame_padding=True,
                    ffmpeg_path=ffmpeg.executable_path,
                    ffprobe_path=ffprobe.executable_path,
                    pass_fds=(*ffmpeg.pass_fds, *ffprobe.pass_fds),
                    _input_descriptor=pinned.descriptor,
                )
            except (DigestError, KeyError, TypeError) as exc:
                raise RenderArtifactError("render candidate remeasurement failed") from exc
            if (
                os.fstat(pinned.descriptor).st_size != expected.get("byteSize")
                or pixels.get("fileDigest") != expected.get("fileDigest")
                or pixels.get("decodedFramePixelDigest")
                != expected.get("decodedFramePixelDigest")
                or pixels.get("decodedFramePixelDigestSpec")
                != expected.get("decodedFramePixelDigestSpec")
                or pcm.get("pcmContentDigest") != expected.get("pcmContentDigest")
                or pcm.get("pcmDigestSpec") != expected.get("pcmContentDigestSpec")
                or pixels.get("width") != media_probe.get("width")
                or pixels.get("height") != media_probe.get("height")
                or pixels.get("frameCount") != media_probe.get("frameCount")
                or pcm.get("sampleRate") != media_probe.get("audioSampleRate")
                or pcm.get("channelCount") != media_probe.get("audioChannels")
                or pcm.get("sampleCount") != media_probe.get("audioSampleCount")
            ):
                raise RenderArtifactError("render candidate artifact was tampered")
            sidecar = expected.get("subtitleSidecar")
            if sidecar is not None:
                sidecar_path = self.artifact_root / render_candidate_storage_key(
                    workspace_ref,
                    production_run_ref,
                    storage_binding_ref,
                    sidecar=True,
                )
                try:
                    with _PinnedRegularFile(
                        sidecar_path, label="published render subtitle sidecar"
                    ) as pinned_sidecar:
                        if pinned_sidecar.descriptor is None:
                            raise RenderArtifactError(
                                "render subtitle sidecar is not pinned"
                            )
                        content = bytearray()
                        offset = 0
                        while True:
                            block = os.pread(
                                pinned_sidecar.descriptor, 1024 * 1024, offset
                            )
                            if not block:
                                break
                            content.extend(block)
                            offset += len(block)
                        pinned_sidecar.require_stable()
                except (OSError, RenderArtifactError) as exc:
                    raise RenderArtifactError(
                        "render subtitle sidecar is unavailable"
                    ) from exc
                if (
                    len(content) != sidecar.get("byteSize")
                    or sha256(content).hexdigest() != sidecar.get("fileDigest")
                ):
                    raise RenderArtifactError("render subtitle sidecar was tampered")
            pinned.require_stable()
            ffmpeg.require_stable()
            ffprobe.require_stable()
            return {
                "path": path,
                "storageKey": storage_key,
                "byteSize": expected["byteSize"],
                "sha256": expected["fileDigest"].removeprefix("sha256:"),
                "mediaType": expected.get("mediaType", "video/mp4"),
            }


__all__ = [
    "DeterministicRenderCandidateExecutor",
    "RENDERER_IDENTITY",
    "RENDERER_VERSION",
    "RENDER_CORE_REQUEST_SCHEMA_VERSION",
    "RENDER_CORE_RESULT_SCHEMA_VERSION",
    "VIDEO_COMPOSITION_PLAN_SCHEMA_VERSION",
    "build_render_core_request",
    "build_video_composition_plan",
    "render_candidate_storage_key",
    "validate_render_core_request",
]
