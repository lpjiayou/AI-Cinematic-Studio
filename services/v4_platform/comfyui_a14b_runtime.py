"""Pure, explicitly typed A14B runtime-original validation; no collection or I/O.

The caller must obtain the complete original through its trusted pinned reader.
This TEST_ONLY template describes synthetic capability facts, not a current GPU
attestation, billing proof or a runtime approval.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re

from .backend_registry import canonical, digest, exact, hex_digest, integer, ref
from .generation_dispatch_a14b_profile import (A14B_COMPILER_IDENTITY, A14B_REQUIRED_NODES,
    A14B_NODE_INPUT_CONTRACTS, A14B_TEMPLATE_REF, COMFYUI_COMMIT, _require,
    _text, validate_a14b_models, validate_a14b_profile)

A14B_RUNTIME_ATTESTATION_SCHEMA = "v4.comfyui-a14b-runtime-attestation.v1"
EXACT_RUNTIME_ATTESTATION_SCHEMA = "v4.comfyui-a14b-runtime-attestation.v2"
A14B_CAPABILITY_MODE = "A14B_IMAGE_TO_VIDEO"


def _process(value):
    exact(value, {"schemaVersion", "instanceRef", "hostBootIdDigest", "pidNamespaceIdDigest",
        "comfyuiPid", "processStartTicks", "comfyuiCommit", "launchConfigDigest"}, "A14B process")
    _require(value["schemaVersion"] == "v5.generation-dispatch-runtime-process.v1", "process schema changed")
    ref(value["instanceRef"], "instanceRef")
    for key in ("hostBootIdDigest", "pidNamespaceIdDigest", "launchConfigDigest"):
        hex_digest(value[key], key)
    integer(value["comfyuiPid"], "ComfyUI PID")
    _require(type(value["processStartTicks"]) is str and re.fullmatch(r"0|[1-9][0-9]*", value["processStartTicks"]) is not None,
        "process start ticks changed")
    _require(value["comfyuiCommit"] == COMFYUI_COMMIT, "ComfyUI code is not the pinned commit")


def _launch(value):
    exact(value, {"argv", "environmentProjection"}, "A14B launch")
    _require(type(value["argv"]) is list and bool(value["argv"]), "launch argv missing")
    for arg in value["argv"]:
        _text(arg, "launch argument")
    items = value["environmentProjection"]
    _require(type(items) is list, "launch environment missing")
    names = []
    for item in items:
        exact(item, {"name", "value"}, "environment item")
        _require(type(item["name"]) is str and re.fullmatch(r"[A-Z_][A-Z0-9_]*", item["name"]) is not None
            and type(item["value"]) is str and "\0" not in item["value"], "unsafe environment item")
        names.append(item["name"])
    _require(names == sorted(set(names)), "environment ordering or uniqueness changed")


def validate_a14b_runtime_attestation(value, *, backend_profile=None, process_identity=None, execution_config=None):
    """Return validated facts, optionally checking exact profile/process/config.

    Generic validation does not assert correspondence to a selected profile; the
    trusted consumer must pass all three selected materials before first sending.
    """
    exact(value, {"schemaVersion", "attestationRef", "observedAt", "factsDigest", "facts",
        "authorityState", "publicationAllowed", "payloadDigest", "capabilityMode"}, "A14B attestation")
    from .generation_dispatch_a14b_exact import (EXACT_COMPILER_IDENTITY, EXACT_TEMPLATE_REF,
        EXACT_NODE_INPUT_CONTRACTS, validate_exact_profile)
    is_exact = value["schemaVersion"] == EXACT_RUNTIME_ATTESTATION_SCHEMA
    _require(value["schemaVersion"] in {A14B_RUNTIME_ATTESTATION_SCHEMA, EXACT_RUNTIME_ATTESTATION_SCHEMA} and value["capabilityMode"] == A14B_CAPABILITY_MODE,
        "A14B runtime type changed")
    ref(value["attestationRef"], "attestationRef")
    timestamp = value["observedAt"]
    _require(type(timestamp) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", timestamp) is not None,
        "A14B observation timestamp is invalid")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        from .backend_registry import BackendValidationError
        raise BackendValidationError("A14B observation timestamp is invalid") from exc
    _require(value["authorityState"] == "TECHNICAL_EVIDENCE_ONLY" and value["publicationAllowed"] is False,
        "A14B attestation is not execution authority")
    facts = exact(value["facts"], {"providerId", "modelId", "region", "endpointClass", "comfyuiVersion",
        "pythonVersion", "pytorchVersion", "deviceName", "deviceType", "vramTotalBytes", "gpuCount",
        "requiredNodes", "nodeInputContracts", "modelFiles", "objectInfoDigest", "modelDigestVerification",
        "startImageCapability", "evidenceClass", "backendProfileDigest", "compilerIdentity", "templateRef",
        "comfyuiCommit", "processIdentity", "processIdentityDigest", "launchConfiguration", "launchConfigDigest"}, "A14B facts")
    for key in ("providerId", "modelId", "region", "endpointClass", "comfyuiVersion", "pythonVersion", "pytorchVersion", "deviceName"):
        _text(facts[key], key)
    _require(facts["endpointClass"] == "TEST_ONLY_LOOPBACK" and facts["evidenceClass"] == "TEST_ONLY",
        "only isolated synthetic A14B runtime evidence is supported")
    _require(facts["comfyuiCommit"] == COMFYUI_COMMIT and facts["comfyuiVersion"] == ("0.35.0" if is_exact else COMFYUI_COMMIT)
        and facts["compilerIdentity"] == (EXACT_COMPILER_IDENTITY if is_exact else A14B_COMPILER_IDENTITY)
        and facts["templateRef"] == (EXACT_TEMPLATE_REF if is_exact else A14B_TEMPLATE_REF),
        "A14B runtime code/compiler/template mismatch")
    _require(facts["requiredNodes"] == list(A14B_REQUIRED_NODES)
        and canonical(facts["nodeInputContracts"]) == canonical(EXACT_NODE_INPUT_CONTRACTS if is_exact else A14B_NODE_INPUT_CONTRACTS), "A14B node inputs changed")
    _require(facts["startImageCapability"] == "LOAD_IMAGE_TO_WAN_IMAGE_TO_VIDEO_VERIFIED"
        and facts["modelDigestVerification"] == "LOCAL_FILE_SHA256_VERIFIED", "A14B originals not verified")
    validate_a14b_models(facts["modelFiles"])
    _require(type(facts["gpuCount"]) is int and facts["gpuCount"] == 1 and facts["deviceType"] == "cuda",
        "A14B device capability mismatch")
    if is_exact:
        integer(facts["vramTotalBytes"], "VRAM bytes", maximum=10**12)
    else:
        integer(facts["vramTotalBytes"], "VRAM bytes")
    for key in ("objectInfoDigest", "backendProfileDigest", "processIdentityDigest", "launchConfigDigest"):
        hex_digest(facts[key], key)
    _process(facts["processIdentity"])
    _launch(facts["launchConfiguration"])
    _require(facts["processIdentityDigest"] == digest(facts["processIdentity"])
        and facts["launchConfigDigest"] == digest(facts["launchConfiguration"])
        and facts["processIdentity"]["launchConfigDigest"] == facts["launchConfigDigest"], "A14B process/launch correspondence changed")
    if backend_profile is not None:
        profile = (validate_exact_profile if is_exact else validate_a14b_profile)(backend_profile)
        _require(profile["parameters"]["evidenceClass"] == "TEST_ONLY", "historical evidence is not a current observation")
        _require(facts["backendProfileDigest"] == digest(profile)
            and canonical(facts["modelFiles"]) == canonical(profile["modelFiles"]), "A14B runtime/profile originals differ")
        _require(facts["vramTotalBytes"] >= profile["parameters"]["resourceRequirements"]["minimumVramBytes"],
            "A14B resource requirement unavailable")
    if process_identity is not None:
        _process(process_identity)
        _require(canonical(facts["processIdentity"]) == canonical(process_identity), "A14B current process differs")
    if execution_config is not None:
        _require(canonical(facts["launchConfiguration"]) == canonical(execution_config.get("launchConfiguration"))
            and facts["launchConfigDigest"] == execution_config.get("launchConfigDigest"), "A14B current launch differs")
    _require(value["factsDigest"] == digest(facts)
        and value["payloadDigest"] == digest({key: item for key, item in value.items() if key != "payloadDigest"}),
        "A14B attestation seal changed")
    return deepcopy(dict(facts))
