"""V4 bridge from current semantic requests to immutable execution envelopes."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from .backend_registry import (BackendValidationError, canonical, digest, exact,
    execution_classification, hex_digest, integer, ref, validate_decision)

EXECUTION_ENVELOPE_SCHEMA = "v4.method-aware-media-execution-envelope.v1"
METHOD_AWARE_JOB_SCHEMA_VERSION = "v4.media-job.v3"
SCOPE_FIELDS = {"workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef"}
LINEAGE_FIELDS = {"generationRequestRef", "generationRequestDigest", "creativeShotVersionRef",
                  "creativeShotVersionDigest", "beatRef", "beatDigest"}
SOURCE_FIELDS = {"assetRef", "assetVersionRef", "assetVersionDigest", "contentDigest",
                 "mediaType", "byteSize", "width", "height"}
OUTPUT_FIELDS = {"mediaKind", "mediaType", "width", "height", "durationFrames", "frameRate"}
ENVELOPE_FIELDS = {"schemaVersion", *SCOPE_FIELDS, *LINEAGE_FIELDS, "executionClass",
    "executionMethod", "sourceAsset", "semanticIntent", "outputConstraints", "backendBinding", "envelopeDigest"}


def validate_output(value: Any) -> None:
    exact(value, OUTPUT_FIELDS, "output constraints")
    if value["mediaKind"] != "video" or value["mediaType"] != "video/mp4":
        raise BackendValidationError("output media type is invalid")
    for field in ("width", "height"):
        integer(value[field], field, maximum=16384)
    integer(value["frameRate"], "frameRate", maximum=240)
    integer(value["durationFrames"], "durationFrames", maximum=1_000_000)


def validate_context(request: Mapping[str, Any], context: Any) -> None:
    exact(context, {"sourceText", "outputConstraints"}, "execution context")
    text = context["sourceText"]
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise BackendValidationError("source action text is invalid")
    action = request.get("sourceAction", {})
    if sha256(text.encode("utf-8")).hexdigest() != action.get("sourceTextDigest"):
        raise BackendValidationError("source action text digest mismatch")
    validate_output(context["outputConstraints"])
    frame_range = request["frameRange"]
    if context["outputConstraints"]["durationFrames"] != frame_range["endFrameExclusive"] - frame_range["startFrameInclusive"]:
        raise BackendValidationError("output duration disagrees with the source beat")


def validate_source(value: Any) -> None:
    exact(value, SOURCE_FIELDS, "source asset")
    for name in ("assetRef", "assetVersionRef"):
        ref(value[name], name)
    for name in ("assetVersionDigest", "contentDigest"):
        hex_digest(value[name], name)
    if value["mediaType"] not in {"image/png", "image/jpeg"}:
        raise BackendValidationError("source asset mediaType is invalid")
    integer(value["byteSize"], "source byteSize", maximum=100_000_000)
    for name in ("width", "height"):
        integer(value[name], "source " + name, maximum=16384)


def validate_envelope(value: Any, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    exact(value, ENVELOPE_FIELDS, "execution envelope")
    if value["schemaVersion"] != EXECUTION_ENVELOPE_SCHEMA:
        raise BackendValidationError("execution envelope schema is invalid")
    if value["envelopeDigest"] != digest({k:v for k,v in value.items() if k != "envelopeDigest"}):
        raise BackendValidationError("execution envelope digest mismatch")
    for key in SCOPE_FIELDS | LINEAGE_FIELDS:
        (hex_digest if key.endswith("Digest") else ref)(value[key], key)
    if (value["executionClass"], value["executionMethod"]) != ("MICRO_MOTION", "SINGLE_ANCHOR_I2V"):
        raise BackendValidationError("execution method is unavailable")
    validate_decision(value["backendBinding"])
    validate_source(value["sourceAsset"])
    validate_output(value["outputConstraints"])
    intent = exact(value["semanticIntent"], {"cameraInstruction", "sourceAction", "frameRange"}, "semantic intent")
    camera = exact(intent["cameraInstruction"], {"framing", "movement"}, "camera instruction")
    if any(not isinstance(t, str) or not t.strip() or len(t)>160 for t in camera.values()):
        raise BackendValidationError("camera instruction is invalid")
    action = exact(intent["sourceAction"], {"sourceSpan", "sourceTextDigest", "sourceText"}, "source action")
    span = exact(action["sourceSpan"], {"scriptSceneRef", "sourceField", "sourceIndex", "startOffsetInclusive", "endOffsetExclusive"}, "source span")
    ref(span["scriptSceneRef"], "scriptSceneRef")
    if span["sourceField"] not in {"ACTION", "DIALOGUE", "NARRATION", "SUBTITLE_TEXT"}:
        raise BackendValidationError("sourceField is invalid")
    for key in ("sourceIndex", "startOffsetInclusive", "endOffsetExclusive"):
        integer(span[key], key, minimum=0)
    if span["endOffsetExclusive"] <= span["startOffsetInclusive"]:
        raise BackendValidationError("source span is empty")
    frames = exact(intent["frameRange"], {"startFrameInclusive", "endFrameExclusive"}, "frame range")
    for key in frames:
        integer(frames[key], key, minimum=0)
    if frames["endFrameExclusive"] <= frames["startFrameInclusive"]:
        raise BackendValidationError("frame range is empty")
    validate_context({"sourceAction": action, "frameRange": frames},
                     {"sourceText": action["sourceText"], "outputConstraints": value["outputConstraints"]})
    if len(action["sourceText"]) != span["endOffsetExclusive"] - span["startOffsetInclusive"]:
        raise BackendValidationError("source text length changed")
    if request is not None:
        # Reuse the existing closed public DTO without adding execution fields.
        from .media_jobs import _validate_method_aware_video_request
        _validate_method_aware_video_request(request)
        for key in SCOPE_FIELDS | {"generationRequestRef", "creativeShotVersionRef", "creativeShotVersionDigest", "beatRef", "beatDigest", "executionClass", "executionMethod"}:
            if request[key] != value[key]:
                raise BackendValidationError("execution envelope request lineage mismatch")
        if request["payloadDigest"] != value["generationRequestDigest"]:
            raise BackendValidationError("generation request digest mismatch")
        expected = {"assetRef": request["sourceImageAssetRef"],
            "assetVersionRef": request["sourceImageAssetVersionRef"],
            "assetVersionDigest": request["sourceImageAssetVersionDigest"],
            "contentDigest": request["sourceImageContentDigest"], "mediaType": request["sourceImageMediaType"]}
        if any(value["sourceAsset"][k] != v for k,v in expected.items()):
            raise BackendValidationError("source AssetVersion binding mismatch")
        if request["cameraInstruction"] != camera or request["frameRange"] != frames or request["sourceAction"] != {k:v for k,v in action.items() if k != "sourceText"}:
            raise BackendValidationError("semantic intent mismatch")
        mode, provenance = execution_classification(value["backendBinding"])
        if (request["adapterCapability"] != value["backendBinding"]["adapterCapability"]
                or request["executionMode"] != mode or request["requestedProvenance"] != provenance):
            raise BackendValidationError("request/backend classification mismatch")
    return deepcopy(dict(value))


class MethodAwareExecutionEnvelopeBuilder:
    def build(self, request, source_asset, decision, profile, context):
        validate_decision(decision)
        validate_context(request, context)
        validate_source(source_asset)
        if digest(profile) != decision["backendProfileDigest"]:
            raise BackendValidationError("backend profile digest mismatch")
        value = {"schemaVersion": EXECUTION_ENVELOPE_SCHEMA,
            **{k:request[k] for k in SCOPE_FIELDS},
            **{k:request[k] for k in LINEAGE_FIELDS - {"generationRequestDigest"}},
            "generationRequestDigest": request["payloadDigest"],
            "executionClass": request["executionClass"], "executionMethod": request["executionMethod"],
            "sourceAsset": deepcopy(source_asset),
            "semanticIntent": {"cameraInstruction": deepcopy(request["cameraInstruction"]),
                "sourceAction": {**deepcopy(request["sourceAction"]), "sourceText": context["sourceText"]},
                "frameRange": deepcopy(request["frameRange"])},
            "outputConstraints": deepcopy(context["outputConstraints"]), "backendBinding": deepcopy(decision)}
        value["envelopeDigest"] = digest(value)
        return validate_envelope(value, request)


class ContentAddressedSourceImages:
    """Bytes locator only. Asset identity always comes from the sealed V5 request."""
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise BackendValidationError("source image root is unavailable")

    def path_for(self, request: Mapping[str, Any]) -> Path:
        content = hex_digest(request["sourceImageContentDigest"], "source content digest")
        suffix = {"image/png": ".png", "image/jpeg": ".jpg"}.get(request["sourceImageMediaType"])
        if suffix is None:
            raise BackendValidationError("source image type is unsupported")
        path = self.root / (content + suffix)
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.root:
            raise BackendValidationError("digest-bound source bytes are unavailable")
        return path

    def resolve(self, request: Mapping[str, Any]) -> dict[str, Any]:
        path = self.path_for(request)
        size = integer(path.stat().st_size, "source image size", maximum=100_000_000)
        if sha256(path.read_bytes()).hexdigest() != request["sourceImageContentDigest"]:
            raise BackendValidationError("source bytes changed")
        try:
            result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height", "-of", "json", str(path)],
                check=True, capture_output=True, text=True, timeout=30)
            streams = json.loads(result.stdout)["streams"]
            if len(streams) != 1 or streams[0]["codec_name"] != {"image/png":"png", "image/jpeg":"mjpeg"}[request["sourceImageMediaType"]]:
                raise ValueError("source format")
            width, height = streams[0]["width"], streams[0]["height"]
        except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
            raise BackendValidationError("source image probe is invalid") from exc
        if path.stat().st_size != size or sha256(path.read_bytes()).hexdigest() != request["sourceImageContentDigest"]:
            raise BackendValidationError("source changed while probing")
        value = {"assetRef": request["sourceImageAssetRef"], "assetVersionRef": request["sourceImageAssetVersionRef"],
            "assetVersionDigest": request["sourceImageAssetVersionDigest"], "contentDigest": request["sourceImageContentDigest"],
            "mediaType": request["sourceImageMediaType"], "byteSize": size, "width": width, "height": height}
        validate_source(value)
        return value


def output_probe_request(envelope: Mapping[str, Any]) -> dict[str, Any]:
    output = envelope["outputConstraints"]
    return {"mediaKind": output["mediaKind"], "mediaType": output["mediaType"],
            "parameters": {k:v for k,v in output.items() if k not in {"mediaKind", "mediaType"}}}


def validate_execution_result(execution: Any, envelope: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"schemaVersion", "backendBindingDigest", "providerId", "modelId", "region", "endpointClass",
        "adapterIdentity", "providerRequestRef", "costCurrency", "costMinor", "runtimeAttestationRef",
        "runtimeAttestationDigest", "executionEvidenceDigest", "executionEvidence", "executionDevice", "gpuUsed"}
    exact(execution, fields, "method-aware execution result")
    binding = envelope["backendBinding"]
    if execution["schemaVersion"] != "v4.method-aware-execution-result.v1" or execution["backendBindingDigest"] != digest(binding):
        raise BackendValidationError("execution result binding mismatch")
    for name in ("providerId", "modelId", "region", "endpointClass", "adapterIdentity", "costCurrency", "runtimeAttestationRef", "runtimeAttestationDigest"):
        if execution[name] != binding[name]:
            raise BackendValidationError("adapter changed its bound backend")
    ref(execution["providerRequestRef"], "providerRequestRef")
    integer(execution["costMinor"], "costMinor", minimum=0, maximum=binding["maxCostMinor"])
    hex_digest(execution["executionEvidenceDigest"], "execution evidence digest")
    if (not isinstance(execution["executionEvidence"], Mapping)
            or digest(execution["executionEvidence"]) != execution["executionEvidenceDigest"]
            or type(execution["gpuUsed"]) is not bool
            or not isinstance(execution["executionDevice"], str)
            or not execution["executionDevice"].strip() or len(execution["executionDevice"]) > 200):
        raise BackendValidationError("execution evidence is invalid")
    return deepcopy(dict(execution))
