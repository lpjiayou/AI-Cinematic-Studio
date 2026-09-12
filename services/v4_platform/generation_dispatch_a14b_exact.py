"""Pure, versioned original-topology candidate. No runtime or approval authority.

The v1 engineering graph stays closed and unchanged. This v2 compiler reconstructs
the sixteen-node topology (including CLIPLoader's *absent* device input), never
loads an arbitrary graph, and binds a complete encoder profile before dispatch.
"""
from copy import deepcopy

from .backend_registry import canonical, digest, exact, hex_digest, integer
from .generation_dispatch_a14b_profile import (
    A14B_PROFILE_SCHEMA, A14B_COMPILER_IDENTITY, A14B_TEMPLATE_REF,
    A14B_POSTPROCESS, A14B_NODE_INPUT_CONTRACTS, _require,
    validate_a14b_profile, compile_a14b_workflow)

EXACT_PROFILE_SCHEMA = "v4.comfyui-a14b-i2v-backend-profile.v2"
EXACT_ADAPTER_IDENTITY = "v4.comfyui-wan22-a14b-image-to-video.v2"
EXACT_CAPABILITY = "self-hosted-wan22-a14b-image-to-video-v2"
EXACT_COMPILER_IDENTITY = "v4.generation-dispatch-a14b-compiler.v2"
EXACT_TEMPLATE_REF = "comfyui-a14b-original-topology-png49-v2"
ENCODING_SCHEMA = "v4.a14b-native49-encoding.v2"
EXACT_REQUEST_SCHEMA = "v4.generation-dispatch-live-transport-request.v2"
EXACT_DERIVATION_SCHEMA = "v4.native-frame-derivation.v2"
EXACT_NODE_INPUT_CONTRACTS = deepcopy(A14B_NODE_INPUT_CONTRACTS)
EXACT_NODE_INPUT_CONTRACTS["CLIPLoader"].pop("device")
ENGINEERING_TO_SOURCE = dict(zip(
    ("1", "4", "2", "3", "12", "8", "9", "10", "11", "5", "6", "7", "13", "14", "15", "16"),
    ("1", "2", "3", "4", "5", "10", "11", "12", "13", "20", "21", "22", "30", "31", "40", "41")))


def encoding_profile(tool_identity):
    """Explicit candidate resolution, not a claim about the historical binary.

    medium / movflags=0 are fixed-tool observed defaults of the original omitted
    options. Explicit single-thread encoding is a reproducibility delta for review.
    """
    value = {"schemaVersion": ENCODING_SCHEMA,
        "profileId": "a14b-original-crf16-49to48-v2", "keepIndices": list(range(48)),
        "dropIndices": [48], "frameRate": 24, "width": 704, "height": 1280,
        "frameCount": 48, "codec": "libx264", "container": "mp4", "pixelFormat": "yuv420p",
        "crf": 16, "preset": "medium", "movflags": "0", "threads": 1,
        "sourceStartNumber": 1, "temporaryStartNumber": 0,
        "durationToleranceMs": [1980, 2020], "toolIdentity": deepcopy(tool_identity)}
    return validate_encoding(value)


def validate_encoding(value):
    expected = {"schemaVersion": ENCODING_SCHEMA, "profileId": "a14b-original-crf16-49to48-v2",
        "keepIndices": list(range(48)), "dropIndices": [48], "frameRate": 24,
        "width": 704, "height": 1280, "frameCount": 48, "codec": "libx264", "container": "mp4",
        "pixelFormat": "yuv420p", "crf": 16, "preset": "medium", "movflags": "0", "threads": 1,
        "sourceStartNumber": 1, "temporaryStartNumber": 0, "durationToleranceMs": [1980, 2020]}
    exact(value, {*expected, "toolIdentity"}, "complete encoding profile")
    _require(canonical({k: value[k] for k in expected}) == canonical(expected), "encoding profile changed")
    tools = exact(value["toolIdentity"], {"ffmpegSha256", "ffprobeSha256"}, "fixed encoder tools")
    for pin in tools.values():
        hex_digest(pin, "tool SHA256")
    return deepcopy(value)


def _engineering_projection(value):
    projected = deepcopy(value)
    projected["schemaVersion"] = A14B_PROFILE_SCHEMA
    p = projected["parameters"]
    p.update(compilerIdentity=A14B_COMPILER_IDENTITY, templateRef=A14B_TEMPLATE_REF, evidenceClass="TEST_ONLY")
    p.pop("cameraDisposition")
    p["nativeOutput"]["nodeId"] = "16"
    p["postprocess"] = deepcopy(A14B_POSTPROCESS)
    # v1's generic integer cap is a TEST_ONLY bound, not a real GPU byte limit.
    # v2 validates the actual byte count independently before this projection.
    p["resourceRequirements"]["minimumVramBytes"] = 1
    return projected


def validate_exact_profile(value):
    exact(value, {"schemaVersion", "parameters", "modelFiles"}, "original-topology profile")
    _require(value["schemaVersion"] == EXACT_PROFILE_SCHEMA, "wrong exact schema")
    p = value["parameters"]
    _require(p["compilerIdentity"] == EXACT_COMPILER_IDENTITY and p["templateRef"] == EXACT_TEMPLATE_REF,
        "wrong exact compiler/template")
    _require((p["evidenceClass"], p["cameraDisposition"]) in {
        ("OFFLINE_SOURCE_CANDIDATE", "PROPOSED_PENDING_OWNER_ACCEPTANCE"),
        ("TEST_ONLY", "TEST_ONLY_NOT_APPROVAL")}, "candidate is not camera approval")
    _require(p["nativeOutput"]["nodeId"] == "41", "original output must be 41")
    validate_encoding(p["postprocess"])
    integer(p["resourceRequirements"]["minimumVramBytes"], "exact VRAM bytes", maximum=10**12)
    validate_a14b_profile(_engineering_projection(value))
    _require(p["steps"] == 4 and type(p["steps"]) is int and p["cfg"] == 1.0, "four-step sampling required")
    for index, pair in enumerate(p["modelPairs"]):
        _require(pair["modelShift"] == 8.0 and pair["strengthModel"] == 1.0
            and pair["startAtStep"] == index * 2 and pair["endAtStep"] == (index + 1) * 2,
            "original sampling segments changed")
    return deepcopy(value)


def compile_exact_workflow(**inputs):
    profile = validate_exact_profile(inputs["backend_profile"])
    graph = compile_a14b_workflow(**{**inputs, "backend_profile": _engineering_projection(profile)})
    result = {}
    for node_id, node in graph.items():
        for key, val in list(node["inputs"].items()):
            if type(val) is list:
                node["inputs"][key] = [ENGINEERING_TO_SOURCE[val[0]], val[1]]
        result[ENGINEERING_TO_SOURCE[node_id]] = node
    result["3"]["inputs"].pop("device")
    return result


def validate_exact_workflow(graph, **inputs):
    expected = compile_exact_workflow(**inputs)
    _require(canonical(graph) == canonical(expected), "original topology/inputs/links changed")
    return expected


def exact_readiness(profile):
    validate_exact_profile(profile)
    return {"ready": False, "systemRuntimeBound": False, "promptSubmissionAuthorized": False,
        "reason": "CAMERA_PROMPT_APPROVAL_PENDING" if profile["parameters"]["evidenceClass"] != "TEST_ONLY"
            else "TEST_ONLY_NOT_RUNTIME_AUTHORITY"}


def validate_exact_request_binding(request):
    encoding = validate_encoding(request["postprocessBinding"])
    _require(request["schemaVersion"] == EXACT_REQUEST_SCHEMA
        and request["outputBinding"]["nodeId"] == "41"
        and request["outputBinding"]["mediaType"] == "image/png", "exact request version/output mismatch")
    graph = request["workflow"]
    _require(set(graph) == set(ENGINEERING_TO_SOURCE.values())
        and graph["41"]["class_type"] == "SaveImage"
        and graph["41"]["inputs"]["images"] == ["40", 0]
        and "device" not in graph["3"]["inputs"], "exact request topology mismatch")
    return encoding


def validate_exact_derivation(value, native, artifact_digest):
    exact(value, {"schemaVersion", "profileId", "nativeSequenceDigest", "keptIndices", "droppedIndices",
        "frameRate", "width", "height", "frameCount", "outputSha256", "encoding", "encodingDigest",
        "sourceToTemporaryToOutput"}, "exact derivation")
    config = validate_encoding(value["encoding"])
    _require(value["schemaVersion"] == EXACT_DERIVATION_SCHEMA and len(native) == 49
        and value["encodingDigest"] == digest(config) and value["nativeSequenceDigest"] == digest(native)
        and value["outputSha256"] == artifact_digest, "exact derivation digest mismatch")
    for key, target in (("profileId", "profileId"), ("keptIndices", "keepIndices"), ("droppedIndices", "dropIndices"),
                        ("frameRate", "frameRate"), ("width", "width"), ("height", "height"), ("frameCount", "frameCount")):
        _require(canonical(value[key]) == canonical(config[target]), "exact derivation changed")
    _require(value["sourceToTemporaryToOutput"] == [[i + 1, i, i] for i in range(48)], "frame index mapping changed")
    return deepcopy(value)
