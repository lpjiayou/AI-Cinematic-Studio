"""Pure bridge to the existing Wan graph compiler for an exact selected plan."""
from __future__ import annotations

from copy import deepcopy

from .backend_registry import BackendValidationError, exact, hex_digest, integer, ref
from .comfyui import compile_wan_workflow
from .method_aware_execution import validate_output, validate_source


def compile_generation_dispatch_workflow(*, generation_request_ref, source_text,
        camera_instruction, source_asset, backend_profile, output_constraints):
    """Return only graph data. Every selected execution value is explicit."""
    ref(generation_request_ref, "generationRequestRef")
    validate_source(source_asset)
    validate_output(output_constraints)
    exact(camera_instruction, {"framing", "movement"}, "camera instruction")
    if (camera_instruction != {"framing": "MEDIUM_CLOSE_UP", "movement": "LOCKED"}
            or not isinstance(source_text, str) or not source_text.strip()
            or len(source_text) > 4000 or source_asset["mediaType"] != "image/png"):
        raise BackendValidationError("exact I2V source is unavailable")
    exact(backend_profile, {"schemaVersion", "parameters", "modelFiles"}, "profile")
    from .generation_dispatch_a14b_profile import A14B_PROFILE_SCHEMA, compile_a14b_workflow
    if backend_profile["schemaVersion"] == A14B_PROFILE_SCHEMA:
        return compile_a14b_workflow(generation_request_ref=generation_request_ref,
            source_asset=source_asset, backend_profile=backend_profile, output_constraints=output_constraints)
    if backend_profile["schemaVersion"] != "v4.comfyui-i2v-backend-profile.v1":
        raise BackendValidationError("I2V profile version is unavailable")
    parameters = exact(backend_profile["parameters"],
        {"seed", "steps", "cfg", "samplerName", "scheduler", "modelShift", "negativePrompt"},
        "I2V parameters")
    integer(parameters["seed"], "seed", minimum=0, maximum=2**64 - 1)
    integer(parameters["steps"], "steps", maximum=100)
    for name in ("cfg", "modelShift"):
        if type(parameters[name]) not in (int, float) or not 0 < parameters[name] <= 100:
            raise BackendValidationError("invalid I2V numeric parameter")
    negative = parameters["negativePrompt"]
    if (parameters["samplerName"] != "uni_pc" or parameters["scheduler"] != "simple"
            or type(negative) is not str or not 0 < len(negative) <= 4000
            or negative != negative.strip() or any(ord(c) < 32 for c in negative)):
        raise BackendValidationError("invalid I2V sampling selection")
    files = backend_profile["modelFiles"]
    if type(files) is not list or len(files) != 3:
        raise BackendValidationError("three explicit model selections are required")
    models = {}
    for model in files:
        exact(model, {"role", "name", "sha256"}, "model")
        role, name = model["role"], model["name"]
        if (role not in {"UNET", "TEXT_ENCODER", "VAE"} or role in models
                or type(name) is not str or not 0 < len(name) <= 200
                or "/" in name or "\\" in name or ".." in name
                or any(ord(c) < 32 for c in name)):
            raise BackendValidationError("invalid or repeated model selection")
        hex_digest(model["sha256"], "model digest")
        models[role] = name
    if len(set(models.values())) != 3:
        raise BackendValidationError("model names must be distinct")
    output = output_constraints
    if output["durationFrames"] % 4 or output["width"] % 16 or output["height"] % 16:
        raise BackendValidationError("I2V output shape is incompatible")
    request = {"generationRequestRef": generation_request_ref,
        "parameters": {**deepcopy(parameters),
            **{k: v for k, v in output.items() if k not in {"mediaKind", "mediaType"}}}}
    return compile_wan_workflow(request, unet_name=models["UNET"],
        clip_name=models["TEXT_ENCODER"], vae_name=models["VAE"],
        prompt_text=f"{source_text}; framing: {camera_instruction['framing']}; movement: {camera_instruction['movement']}",
        negative_prompt_text=negative,
        start_image_name="acs-k2-m11/" + source_asset["contentDigest"] + ".png",
        latent_frame_count=output["durationFrames"] + 1)
