"""Synthetic v2 materials only; no private prompt, model pins, host or Grant."""
from copy import deepcopy
from services.v4_platform.backend_registry import digest
from services.v4_platform.generation_dispatch_a14b_exact import (
    EXACT_PROFILE_SCHEMA, EXACT_COMPILER_IDENTITY, EXACT_TEMPLATE_REF,
    EXACT_ADAPTER_IDENTITY, EXACT_CAPABILITY, EXACT_NODE_INPUT_CONTRACTS, encoding_profile)
from services.v4_platform.comfyui_a14b_runtime import EXACT_RUNTIME_ATTESTATION_SCHEMA
from tests.support.generation_dispatch_a14b_fixtures import (
    make_a14b_profile, make_a14b_runtime, make_a14b_execution_fixture)


def exact_profile(source_digest=None, tools=None):
    profile = make_a14b_profile(source_digest)
    profile["schemaVersion"] = EXACT_PROFILE_SCHEMA
    p = profile["parameters"]
    p.update(compilerIdentity=EXACT_COMPILER_IDENTITY, templateRef=EXACT_TEMPLATE_REF,
        cameraDisposition="TEST_ONLY_NOT_APPROVAL", steps=4,
        positivePrompt="TEST_ONLY synthetic subject. Camera: a locked medium close-up.")
    p["nativeOutput"]["nodeId"] = "41"
    for index, pair in enumerate(p["modelPairs"]):
        pair.update(modelShift=8.0, startAtStep=index * 2, endAtStep=(index + 1) * 2)
    p["postprocess"] = encoding_profile(tools or {"ffmpegSha256": "a" * 64, "ffprobeSha256": "b" * 64})
    return profile


def exact_runtime(profile, process_identity=None, execution_config=None):
    value = make_a14b_runtime(profile, process_identity, execution_config)
    value["schemaVersion"] = EXACT_RUNTIME_ATTESTATION_SCHEMA
    value["facts"].update(comfyuiVersion="0.35.0", compilerIdentity=EXACT_COMPILER_IDENTITY,
        templateRef=EXACT_TEMPLATE_REF, nodeInputContracts=deepcopy(EXACT_NODE_INPUT_CONTRACTS))
    value["factsDigest"] = digest(value["facts"])
    value["payloadDigest"] = digest({k: v for k, v in value.items() if k != "payloadDigest"})
    return value


def exact_fixture(case, endpoint, tools):
    return make_a14b_execution_fixture(case, endpoint,
        profile_factory=lambda source: exact_profile(source, tools), runtime_factory=exact_runtime,
        adapter_identity=EXACT_ADAPTER_IDENTITY, adapter_capability=EXACT_CAPABILITY)
