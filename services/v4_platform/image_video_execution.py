"""Versioned technical image/video input bridge into the original media queue.

An uploaded input is an evidence object, not a Script, Shot or AssetVersion.
The original dispatch lease, one-shot consumer and result lifecycle still own
execution. This module validates and builds immutable data; it cannot send.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from typing import Any, Mapping

from .backend_registry import (BackendValidationError, digest, exact,
    execution_classification, hex_digest, integer, ref, validate_decision)

USER_IMAGE_VIDEO_REQUEST_SCHEMA = "v5.user-image-video-generation-request.v1"
USER_IMAGE_VIDEO_ENVELOPE_SCHEMA = "v4.user-image-video-execution-envelope.v1"
USER_IMAGE_VIDEO_JOB_SCHEMA = "v4.media-job.v5"
USER_IMAGE_VIDEO_SUBJECT_SCHEMA = "v5.user-image-video-subject.v1"
SCOPE_FIELDS = frozenset({"workspaceRef", "projectRef", "seriesRef", "episodeRef", "productionRunRef"})
INPUT_FIELDS = frozenset({"inputRef", "contentDigest", "mediaType", "byteSize", "width", "height"})
SUBJECT_FIELDS = frozenset({"generationRef", "inputDigest", "inputImage", "description",
    "descriptionDigest", "cameraInstruction", "outputConstraints", "executionClass", "executionMethod"})
REQUEST_FIELDS = SCOPE_FIELDS | SUBJECT_FIELDS | {"schemaVersion", "generationRequestRef",
    "generationRequestVersionRef", "version", "adapterCapability", "executionMode",
    "requestedProvenance", "dispatchGrantBinding", "createdAt", "publicationAllowed", "payloadDigest"}
ENVELOPE_FIELDS = SCOPE_FIELDS | SUBJECT_FIELDS | {"schemaVersion", "generationRequestRef",
    "generationRequestDigest", "backendBinding", "dispatchGrantBinding", "envelopeDigest"}
OUTPUT = {"mediaKind": "video", "mediaType": "video/mp4", "width": 704,
    "height": 1280, "durationFrames": 48, "frameRate": 24}


def validate_input_image(value: Any) -> dict[str, Any]:
    exact(value, INPUT_FIELDS, "technical input image")
    ref(value["inputRef"], "inputRef")
    hex_digest(value["contentDigest"], "input content digest")
    if value["mediaType"] != "image/png":
        raise BackendValidationError("technical input must be normalized PNG")
    integer(value["byteSize"], "input byteSize", maximum=20 * 1024 * 1024)
    for key in ("width", "height"):
        integer(value[key], "input " + key, maximum=16384)
    return deepcopy(dict(value))


def _validate_subject_fields(value: Mapping[str, Any]) -> None:
    for key in SCOPE_FIELDS | {"generationRef"}:
        ref(value[key], key)
    hex_digest(value["inputDigest"], "inputDigest")
    validate_input_image(value["inputImage"])
    text = value["description"]
    if (not isinstance(text, str) or not text.strip() or len(text) > 4000
            or any(ord(character) < 32 for character in text)
            or value["descriptionDigest"] != sha256(text.encode("utf-8")).hexdigest()):
        raise BackendValidationError("technical description or digest is invalid")
    if (value["cameraInstruction"] != {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"}
            or value["outputConstraints"] != OUTPUT
            or any(type(value["outputConstraints"].get(key)) is not int
                for key in ("width", "height", "durationFrames", "frameRate"))
            or (value["executionClass"], value["executionMethod"])
                != ("MICRO_MOTION", "SINGLE_ANCHOR_I2V")):
        raise BackendValidationError("technical image/video output or execution shape is invalid")


def validate_user_image_video_request(value: Any) -> dict[str, Any]:
    from .method_aware_execution import validate_dispatch_grant_binding
    exact(value, REQUEST_FIELDS, "technical image/video request")
    if (value["schemaVersion"] != USER_IMAGE_VIDEO_REQUEST_SCHEMA
            or type(value["version"]) is not int or value["version"] != 1
            or value["publicationAllowed"] is not False
            or value["payloadDigest"] != digest({k: v for k, v in value.items() if k != "payloadDigest"})):
        raise BackendValidationError("technical image/video request version or seal is invalid")
    _validate_subject_fields(value)
    for key in ("generationRequestRef", "generationRequestVersionRef", "adapterCapability"):
        ref(value[key], key)
    if value["generationRequestVersionRef"] != value["generationRequestRef"] + ":v1":
        raise BackendValidationError("technical request immutable version is invalid")
    if (value["executionMode"], value["requestedProvenance"]) != (
            "INTERNAL_SELF_HOSTED", "SELF_HOSTED_AI_GENERATED"):
        # Exact mode/provenance compatibility is also checked against the
        # selected immutable backend by the envelope validator.
        raise BackendValidationError("technical execution classification is invalid")
    try:
        if not isinstance(value["createdAt"], str) or not value["createdAt"].endswith("Z"):
            raise ValueError("UTC required")
        datetime.fromisoformat(value["createdAt"][:-1] + "+00:00")
    except ValueError as exc:
        raise BackendValidationError("technical request createdAt is invalid") from exc
    validate_dispatch_grant_binding(value["dispatchGrantBinding"])
    return deepcopy(dict(value))


def validate_user_image_video_context(request: Mapping[str, Any], context: Any) -> None:
    exact(context, {"sourceText", "outputConstraints"}, "technical execution context")
    if (context["sourceText"] != request["description"]
            or context["outputConstraints"] != request["outputConstraints"]):
        raise BackendValidationError("technical input context changed")


def validate_user_image_video_envelope(value: Any, request: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from .method_aware_execution import validate_dispatch_grant_binding
    exact(value, ENVELOPE_FIELDS, "technical execution envelope")
    if (value["schemaVersion"] != USER_IMAGE_VIDEO_ENVELOPE_SCHEMA
            or value["envelopeDigest"] != digest({k: v for k, v in value.items() if k != "envelopeDigest"})):
        raise BackendValidationError("technical envelope version or seal is invalid")
    _validate_subject_fields(value)
    ref(value["generationRequestRef"], "generationRequestRef")
    hex_digest(value["generationRequestDigest"], "generationRequestDigest")
    validate_dispatch_grant_binding(value["dispatchGrantBinding"])
    decision = validate_decision(value["backendBinding"])
    if request is not None:
        request = validate_user_image_video_request(request)
        if (any(value[key] != request[key] for key in SCOPE_FIELDS | SUBJECT_FIELDS
                | {"generationRequestRef", "dispatchGrantBinding"})
                or value["generationRequestDigest"] != request["payloadDigest"]):
            raise BackendValidationError("technical request/envelope lineage mismatch")
        mode, provenance = execution_classification(decision)
        if (request["adapterCapability"] != decision["adapterCapability"]
                or (request["executionMode"], request["requestedProvenance"]) != (mode, provenance)):
            raise BackendValidationError("technical backend classification mismatch")
    return deepcopy(dict(value))


def build_user_image_video_request(verified_grant: Mapping[str, Any], *, generation_request_ref: str | None = None) -> dict[str, Any]:
    """Called only by the V5 verified-Grant route while its gate is held."""
    subject = verified_grant["subject"]
    exact(subject, SUBJECT_FIELDS | {"schemaVersion"}, "technical dispatch subject")
    if subject["schemaVersion"] != USER_IMAGE_VIDEO_SUBJECT_SCHEMA:
        raise BackendValidationError("technical subject version is invalid")
    decision = validate_decision(verified_grant["executionBinding"]["backendDecision"])
    mode, provenance = execution_classification(decision)
    request_ref = generation_request_ref or "image-video-request-" + digest({
        "grantRef": verified_grant["generationDispatchGrantRef"], "grantDigest": verified_grant["payloadDigest"]})
    value = {"schemaVersion": USER_IMAGE_VIDEO_REQUEST_SCHEMA,
        **{key: verified_grant[key] for key in SCOPE_FIELDS},
        **{key: deepcopy(subject[key]) for key in SUBJECT_FIELDS},
        "generationRequestRef": request_ref, "generationRequestVersionRef": request_ref + ":v1",
        "version": 1, "adapterCapability": decision["adapterCapability"],
        "executionMode": mode, "requestedProvenance": provenance,
        "dispatchGrantBinding": {"generationDispatchGrantRef": verified_grant["generationDispatchGrantRef"],
            "generationDispatchGrantDigest": verified_grant["payloadDigest"],
            "subjectDigest": verified_grant["subjectDigest"],
            "approvedPlanDigest": verified_grant["approval"]["approvedPlanDigest"]},
        "createdAt": verified_grant["createdAt"], "publicationAllowed": False}
    value["payloadDigest"] = digest(value)
    return validate_user_image_video_request(value)


def build_user_image_video_envelope(request: Mapping[str, Any], backend_decision: Mapping[str, Any]) -> dict[str, Any]:
    request = validate_user_image_video_request(request)
    value = {"schemaVersion": USER_IMAGE_VIDEO_ENVELOPE_SCHEMA,
        **{key: deepcopy(request[key]) for key in SCOPE_FIELDS | SUBJECT_FIELDS},
        "generationRequestRef": request["generationRequestRef"],
        "generationRequestDigest": request["payloadDigest"],
        "backendBinding": deepcopy(dict(backend_decision)),
        "dispatchGrantBinding": deepcopy(request["dispatchGrantBinding"])}
    value["envelopeDigest"] = digest(value)
    return validate_user_image_video_envelope(value, request)


def compile_user_image_video_workflow(*, generation_request_ref: str, input_image: Mapping[str, Any],
        backend_profile: Mapping[str, Any], output_constraints: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse the exact graph through a local byte-shape adapter, never a fact.

    The established pure compiler's source parameter predates technical inputs.
    Its Ref slots are unused graph-construction metadata. This private mapping
    is neither returned, persisted, admitted, nor passed to an Asset owner.
    The public request/envelope retain only ``inputImage`` identity.
    """
    from .generation_dispatch_a14b_live import compile_live_workflow
    image = validate_input_image(input_image)
    byte_source = {"assetRef": image["inputRef"], "assetVersionRef": image["inputRef"],
        "assetVersionDigest": digest(image), **{key: image[key] for key in
            ("contentDigest", "mediaType", "byteSize", "width", "height")}}
    return compile_live_workflow(generation_request_ref=generation_request_ref,
        source_asset=byte_source, backend_profile=backend_profile, output_constraints=output_constraints)
