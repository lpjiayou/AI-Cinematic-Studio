"""Closed, pure A14B engineering template; never a SH09 frozen-graph claim.

Node signatures were checked against official ComfyUI at COMFYUI_COMMIT. The
missing original freeze prevents promotion of this TEST_ONLY template. Neither a
profile nor a valid graph grants permission to contact a runtime.
"""
from __future__ import annotations

from copy import deepcopy
import re

from .backend_registry import (BackendValidationError, canonical, exact,
    hex_digest, integer, ref)
from .method_aware_execution import validate_output, validate_source

A14B_PROFILE_SCHEMA = "v4.comfyui-a14b-i2v-backend-profile.v1"
A14B_ADAPTER_IDENTITY = "v4.comfyui-wan22-a14b-image-to-video.v1"
A14B_CAPABILITY = "self-hosted-wan22-a14b-image-to-video-v1"
A14B_COMPILER_IDENTITY = "v4.generation-dispatch-a14b-compiler.v1"
A14B_TEMPLATE_REF = "comfyui-a14b-dual-expert-png49-test-only-v1"
COMFYUI_COMMIT = "a7b1d39d342d102f305797fb5ba12dc304d9c1f5"
A14B_MODEL_ROLES = ("HIGH_NOISE_EXPERT", "LOW_NOISE_EXPERT", "TEXT_ENCODER",
    "VAE", "HIGH_NOISE_LORA", "LOW_NOISE_LORA")
A14B_POSTPROCESS = {
    "profileId": "ACS-SPIKE0-POST-49TO48-24FPS-R1",
    "keptZeroBasedIndices": list(range(48)), "droppedZeroBasedIndices": [48],
    "width": 704, "height": 1280, "durationFrames": 48, "frameRate": 24,
    "mediaType": "video/mp4"}
A14B_FINAL_OUTPUT = {"mediaKind": "video", "mediaType": "video/mp4",
    "width": 704, "height": 1280, "durationFrames": 48, "frameRate": 24}

# Contracts of the inputs USED by this one template, not a general node registry.
A14B_NODE_INPUT_CONTRACTS = {
    "UNETLoader": {"unet_name": "MODEL_FILENAME", "weight_dtype": "ENUM:default"},
    "CLIPLoader": {"clip_name": "MODEL_FILENAME", "type": "ENUM:wan", "device": "ENUM:default"},
    "VAELoader": {"vae_name": "MODEL_FILENAME"},
    "LoraLoaderModelOnly": {"model": "MODEL", "lora_name": "MODEL_FILENAME", "strength_model": "FLOAT"},
    "ModelSamplingSD3": {"model": "MODEL", "shift": "FLOAT"},
    "CLIPTextEncode": {"text": "STRING", "clip": "CLIP"},
    "LoadImage": {"image": "IMAGE_FILENAME"},
    "WanImageToVideo": {"positive": "CONDITIONING", "negative": "CONDITIONING", "vae": "VAE",
        "width": "INT", "height": "INT", "length": "INT", "batch_size": "INT", "start_image": "IMAGE"},
    "KSamplerAdvanced": {"model": "MODEL", "add_noise": "ENUM:enable,disable", "noise_seed": "INT",
        "steps": "INT", "cfg": "FLOAT", "sampler_name": "ENUM:euler", "scheduler": "ENUM:simple",
        "positive": "CONDITIONING", "negative": "CONDITIONING", "latent_image": "LATENT",
        "start_at_step": "INT", "end_at_step": "INT", "return_with_leftover_noise": "ENUM:enable,disable"},
    "VAEDecode": {"samples": "LATENT", "vae": "VAE"},
    "SaveImage": {"images": "IMAGE", "filename_prefix": "STRING"},
}
A14B_REQUIRED_NODES = tuple(sorted(A14B_NODE_INPUT_CONTRACTS))


def _require(condition, label):
    if not condition:
        raise BackendValidationError(label)


def _text(value, label):
    _require(type(value) is str and 0 < len(value) <= 4000 and value == value.strip()
        and not any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value), label)


def _number(value, label, *, maximum=100):
    _require(type(value) in (int, float) and 0 < value <= maximum, label)


def _relative(value, label, *, image=False, model=False):
    # No formatting expansions, URL/path suffixes, traversal, drive or UNC paths.
    _require(type(value) is str and len(value) <= 200 and re.fullmatch(
        r"[A-Za-z0-9_-]+(?:[./-][A-Za-z0-9_-]+)*", value) is not None
        and ".." not in value and (not model or "/" not in value)
        and (not image or value.endswith(".png")), label)


def validate_a14b_models(files):
    _require(type(files) is list and len(files) == 6, "A14B requires six model originals")
    roles, names, digests = [], [], []
    for model in files:
        exact(model, {"role", "name", "sha256", "sizeBytes"}, "A14B model")
        _require(model["role"] in A14B_MODEL_ROLES, "unknown A14B model role")
        _relative(model["name"], "model name", model=True)
        hex_digest(model["sha256"], "model sha256")
        integer(model["sizeBytes"], "model sizeBytes", maximum=10**12)
        roles.append(model["role"])
        names.append(model["name"])
        digests.append(model["sha256"])
    _require(roles == list(A14B_MODEL_ROLES) and len(set(names)) == len(set(digests)) == 6,
        "A14B model roles, ordering, names and originals must be unique")
    return {model["role"]: model for model in files}


def validate_a14b_profile(value):
    exact(value, {"schemaVersion", "parameters", "modelFiles"}, "A14B profile")
    _require(value["schemaVersion"] == A14B_PROFILE_SCHEMA, "A14B profile schema is invalid")
    models = validate_a14b_models(value["modelFiles"])
    p = exact(value["parameters"], {"compilerIdentity", "templateRef", "evidenceClass", "comfyuiCommit",
        "positivePrompt", "negativePrompt", "seed", "steps", "cfg", "samplerName", "scheduler",
        "modelPairs", "input", "nativeOutput", "postprocess", "resourceRequirements"}, "A14B parameters")
    _require(p["compilerIdentity"] == A14B_COMPILER_IDENTITY and p["templateRef"] == A14B_TEMPLATE_REF
        and p["comfyuiCommit"] == COMFYUI_COMMIT and p["evidenceClass"] == "TEST_ONLY",
        "only the explicitly TEST_ONLY A14B engineering template is available")
    _text(p["positivePrompt"], "positive prompt")
    _text(p["negativePrompt"], "negative prompt")
    integer(p["seed"], "A14B seed", minimum=0, maximum=2**64 - 1)
    integer(p["steps"], "A14B steps", minimum=2, maximum=100)
    _number(p["cfg"], "A14B cfg")
    _require(p["samplerName"] == "euler" and p["scheduler"] == "simple", "A14B sampler is unavailable")
    pairs = p["modelPairs"]
    _require(type(pairs) is list and len(pairs) == 2, "A14B expert pairs missing")
    for index, pair in enumerate(pairs):
        exact(pair, {"expertRole", "expertSha256", "loraRole", "loraSha256", "strengthModel", "modelShift",
            "startAtStep", "endAtStep", "addNoise", "returnWithLeftoverNoise"}, "A14B expert pair")
        expert, lora = (("HIGH_NOISE_EXPERT", "HIGH_NOISE_LORA"), ("LOW_NOISE_EXPERT", "LOW_NOISE_LORA"))[index]
        _require(pair["expertRole"] == expert and pair["loraRole"] == lora
            and pair["expertSha256"] == models[expert]["sha256"] and pair["loraSha256"] == models[lora]["sha256"],
            "A14B expert/LoRA original pairing changed")
        _number(pair["strengthModel"], "LoRA strength")
        _number(pair["modelShift"], "model shift")
        integer(pair["startAtStep"], "start step", minimum=0, maximum=p["steps"])
        integer(pair["endAtStep"], "end step", minimum=1, maximum=p["steps"])
        _require(pair["startAtStep"] < pair["endAtStep"], "empty sampling segment")
        expected_noise = "enable" if index == 0 else "disable"
        _require(pair["addNoise"] == pair["returnWithLeftoverNoise"] == expected_noise,
            "A14B staged noise semantics changed")
    _require(pairs[0]["startAtStep"] == 0 and pairs[0]["endAtStep"] == pairs[1]["startAtStep"]
        and pairs[1]["endAtStep"] == p["steps"], "A14B stages must partition all steps")
    source = exact(p["input"], {"imageName", "contentDigest"}, "A14B input")
    _relative(source["imageName"], "A14B input image", image=True)
    hex_digest(source["contentDigest"], "A14B input digest")
    native = exact(p["nativeOutput"], {"nodeId", "mediaType", "frameCount", "width", "height", "filenamePrefix"}, "native output")
    _require(canonical({key: val for key, val in native.items() if key != "filenamePrefix"}) == canonical(
        {"nodeId": "16", "mediaType": "image/png", "frameCount": 49, "width": 704, "height": 1280}), "native49 contract changed")
    _relative(native["filenamePrefix"], "native output prefix")
    _require(canonical(p["postprocess"]) == canonical(A14B_POSTPROCESS), "49-to-48 postprocess changed")
    resources = exact(p["resourceRequirements"], {"gpuCount", "minimumVramBytes", "deviceType"}, "A14B resources")
    _require(type(resources["gpuCount"]) is int and resources["gpuCount"] == 1 and resources["deviceType"] == "cuda",
        "A14B requires one CUDA device")
    integer(resources["minimumVramBytes"], "minimum VRAM bytes")
    return deepcopy(dict(value))


def compile_a14b_workflow(*, generation_request_ref, source_asset, backend_profile, output_constraints):
    """Reconstruct the sole fixed template; never accept a caller-supplied graph."""
    ref(generation_request_ref, "generation request")
    validate_source(source_asset)
    validate_output(output_constraints)
    profile = validate_a14b_profile(backend_profile)
    p = profile["parameters"]
    _require(canonical(output_constraints) == canonical(A14B_FINAL_OUTPUT), "A14B final output changed")
    _require(source_asset["mediaType"] == "image/png" and p["input"]["contentDigest"] == source_asset["contentDigest"],
        "A14B input original changed")
    models = {model["role"]: model["name"] for model in profile["modelFiles"]}
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}
    high, low = p["modelPairs"]
    graph = {
        "1": node("UNETLoader", unet_name=models["HIGH_NOISE_EXPERT"], weight_dtype="default"),
        "2": node("CLIPLoader", clip_name=models["TEXT_ENCODER"], type="wan", device="default"),
        "3": node("VAELoader", vae_name=models["VAE"]),
        "4": node("UNETLoader", unet_name=models["LOW_NOISE_EXPERT"], weight_dtype="default"),
        "5": node("CLIPTextEncode", text=p["positivePrompt"], clip=["2", 0]),
        "6": node("CLIPTextEncode", text=p["negativePrompt"], clip=["2", 0]),
        "7": node("WanImageToVideo", positive=["5", 0], negative=["6", 0], vae=["3", 0], width=704,
            height=1280, length=49, batch_size=1, start_image=["12", 0]),
        "8": node("LoraLoaderModelOnly", model=["1", 0], lora_name=models["HIGH_NOISE_LORA"], strength_model=high["strengthModel"]),
        "9": node("LoraLoaderModelOnly", model=["4", 0], lora_name=models["LOW_NOISE_LORA"], strength_model=low["strengthModel"]),
        "10": node("ModelSamplingSD3", model=["8", 0], shift=high["modelShift"]),
        "11": node("ModelSamplingSD3", model=["9", 0], shift=low["modelShift"]),
        "12": node("LoadImage", image=p["input"]["imageName"]),
        "15": node("VAEDecode", samples=["14", 0], vae=["3", 0]),
        "16": node("SaveImage", images=["15", 0], filename_prefix=p["nativeOutput"]["filenamePrefix"]),
    }
    for node_id, model_id, latent, pair in (("13", "10", ["7", 2], high), ("14", "11", ["13", 0], low)):
        graph[node_id] = node("KSamplerAdvanced", model=[model_id, 0], add_noise=pair["addNoise"], noise_seed=p["seed"],
            steps=p["steps"], cfg=p["cfg"], sampler_name=p["samplerName"], scheduler=p["scheduler"], positive=["7", 0],
            negative=["7", 1], latent_image=latent, start_at_step=pair["startAtStep"], end_at_step=pair["endAtStep"],
            return_with_leftover_noise=pair["returnWithLeftoverNoise"])
    return graph


def validate_a14b_workflow(graph, **compiler_inputs):
    expected = compile_a14b_workflow(**compiler_inputs)
    _require(canonical(graph) == canonical(expected), "A14B full workflow differs from fixed compiler")
    return deepcopy(expected)
